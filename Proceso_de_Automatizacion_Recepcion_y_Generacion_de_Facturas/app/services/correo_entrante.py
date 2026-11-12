"""Correo de entrada (IMAP): descarga, repositorio y creación de factura.

Etapa 1 - descargar_correos():
    Lee los mensajes NO LEÍDOS con BODY.PEEK (no los marca). Solo los de
    facturación se guardan como .eml en el repositorio privado
    (CORREOS_FOLDER) con su SHA-256 y quedan RECIBIDO; recién entonces
    se marcan como leídos. El resto queda intacto en la bandeja.

Etapa 2 - procesar_pendientes():
    Toma cada correo RECIBIDO, verifica su integridad, extrae los datos,
    identifica al cliente y crea la solicitud (origen Correo) con su
    factura v1 En revisión. Luego avisa al Administrador por SMTP.
    Si faltan datos queda REQUIERE_REVISION con los motivos.

revisar_bandeja() ejecuta ambas etapas con un bloqueo de MySQL
(GET_LOCK) para que dos ejecuciones simultáneas no se pisen.

Seguridad:
- IMAP solo cifrado (SSL o STARTTLS); sin cifrado solo con localhost.
- Límite de tamaño por mensaje antes de descargarlo.
- Idempotencia por Message-ID (huella única) y por clave_idempotencia.
- El HTML nunca se renderiza; los XML se leen con defusedxml.
- Falla de SPF/DMARC o remitente no registrado -> revisión manual.
"""
import hashlib
import imaplib
import json
import os
import re
import secrets
import ssl
import uuid
from datetime import timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime

from flask import current_app

from ..models import get_db_connection
from .correo import HOSTS_LOCALES, limpiar_cabecera
from .extraccion_correo import (
    es_automatico,
    es_facturacion,
    extraer_datos,
    texto_del_mensaje,
    verificacion_remitente,
)
from .facturas import evento_factura_generada, generar_version
from .notificaciones import notificar_factura_generada
from .solicitudes import (
    ErrorGestionSolicitud,
    comprobar_actor,
    huella_de_creacion,
    insertar_solicitud,
    validar_solicitud,
)
from .usuarios import registrar_evento
from .validaciones import ErrorValidacion, normalizar_correo, validar_cliente

MODOS_SEGURIDAD = {"ssl", "starttls", "none"}
NOMBRE_BLOQUEO = "facturaciones_correo_entrante"
ESTADOS_REPROCESABLES = ("REQUIERE_REVISION", "ERROR")
ESTADOS_DESCARTABLES = ("RECIBIDO", "REQUIERE_REVISION", "ERROR")


class ErrorCorreoEntrante(Exception):
    def __init__(self, codigo, mensaje, detalle=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.detalle = (detalle or mensaje)[:500]


def validar_configuracion_imap(config=None):
    config = config if config is not None else current_app.config
    host = str(config.get("IMAP_HOST") or "").strip()
    seguridad = str(config.get("IMAP_SECURITY") or "").strip().lower()
    usuario = str(config.get("IMAP_USER") or "").strip()

    if not host or not usuario:
        raise ErrorCorreoEntrante(
            "CONFIGURACION",
            "La bandeja de entrada no está configurada (IMAP_HOST e IMAP_USER).",
        )
    if seguridad not in MODOS_SEGURIDAD:
        raise ErrorCorreoEntrante(
            "CONFIGURACION", "IMAP_SECURITY debe ser ssl, starttls o none."
        )
    if seguridad == "none" and host.lower() not in HOSTS_LOCALES:
        raise ErrorCorreoEntrante(
            "CONFIGURACION",
            "IMAP_SECURITY=none solo se permite con un servidor local.",
        )
    try:
        puerto = int(config.get("IMAP_PORT") or 0)
    except (TypeError, ValueError):
        puerto = 0
    if not 1 <= puerto <= 65535:
        raise ErrorCorreoEntrante("CONFIGURACION", "IMAP_PORT no es válido.")

    buzon = str(config.get("IMAP_MAILBOX") or "INBOX").strip()
    if not re.fullmatch(r"[\w ./\-\[\]]{1,100}", buzon):
        raise ErrorCorreoEntrante("CONFIGURACION", "IMAP_MAILBOX no es válido.")

    return {
        "host": host,
        "puerto": puerto,
        "seguridad": seguridad,
        "usuario": usuario,
        "password": str(config.get("IMAP_PASSWORD") or ""),
        "buzon": buzon,
        "timeout": int(config.get("IMAP_TIMEOUT") or 30),
        "max_mensajes": max(1, int(config.get("IMAP_MAX_MENSAJES") or 25)),
        "max_bytes": max(1024, int(config.get("IMAP_MAX_BYTES") or 10485760)),
    }


def conectar(cfg, fabrica_ssl=imaplib.IMAP4_SSL, fabrica=imaplib.IMAP4):
    contexto = ssl.create_default_context()
    try:
        if cfg["seguridad"] == "ssl":
            conexion = fabrica_ssl(
                cfg["host"], cfg["puerto"],
                ssl_context=contexto, timeout=cfg["timeout"],
            )
        else:
            conexion = fabrica(cfg["host"], cfg["puerto"], timeout=cfg["timeout"])
            if cfg["seguridad"] == "starttls":
                # Si el servidor no ofrece STARTTLS, imaplib lanza error:
                # nunca se continúa en texto plano.
                conexion.starttls(ssl_context=contexto)

        conexion.login(cfg["usuario"], cfg["password"])
        tipo, _ = conexion.select(f'"{cfg["buzon"]}"')
        if tipo != "OK":
            raise ErrorCorreoEntrante(
                "BUZON", f"No existe la carpeta {cfg['buzon']}."
            )
        return conexion

    except ErrorCorreoEntrante:
        raise
    except ssl.SSLError as exc:
        raise ErrorCorreoEntrante(
            "TLS", "No se pudo establecer una conexión IMAP cifrada.",
            type(exc).__name__,
        ) from exc
    except imaplib.IMAP4.abort as exc:
        raise ErrorCorreoEntrante(
            "CONEXION", "El servidor IMAP cerró la conexión.", type(exc).__name__,
        ) from exc
    except imaplib.IMAP4.error as exc:
        texto = limpiar_cabecera(str(exc), 200)
        codigo = "TLS_NO_DISPONIBLE" if "STARTTLS" in texto.upper() else "AUTENTICACION"
        raise ErrorCorreoEntrante(
            codigo, "El servidor IMAP rechazó la conexión o las credenciales.",
            texto,
        ) from exc
    except OSError as exc:
        raise ErrorCorreoEntrante(
            "CONEXION", "No se pudo conectar con el servidor IMAP.",
            type(exc).__name__,
        ) from exc


def _cerrar(conexion):
    try:
        conexion.logout()
    except Exception:
        pass


def obtener_usuario_sistema(cursor):
    cursor.execute(
        "SELECT id, email FROM usuarios WHERE email = %s",
        (current_app.config["SISTEMA_CORREO_EMAIL"],),
    )
    usuario = cursor.fetchone()
    if usuario is None:
        raise ErrorCorreoEntrante(
            "CONFIGURACION",
            "Falta el usuario técnico del correo entrante. "
            "Ejecute migrations/003_flujo_correo_factura.sql.",
        )
    return usuario


def _json(valor):
    return json.dumps(valor, ensure_ascii=False) if valor is not None else None


def _cargar(valor):
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    return json.loads(valor) if isinstance(valor, str) else valor


def _ruta_eml(nombre):
    if os.path.basename(nombre) != nombre or not nombre.endswith(".eml"):
        raise ErrorCorreoEntrante("REGISTRO", "El registro del correo no es válido.")
    return os.path.join(current_app.config["CORREOS_FOLDER"], nombre)


def metadatos(crudo, mensaje):
    message_id = limpiar_cabecera(mensaje.get("Message-ID"), 255)
    if not message_id:
        message_id = f"<sin-id-{hashlib.sha256(crudo).hexdigest()}@local>"

    remitente = parseaddr(str(mensaje.get("From") or ""))[1]
    try:
        remitente = normalizar_correo(remitente).lower()
    except ErrorValidacion:
        remitente = limpiar_cabecera(remitente, 150) or "desconocido"

    fecha = None
    try:
        fecha = parsedate_to_datetime(str(mensaje.get("Date")))
        if fecha.tzinfo:
            fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, IndexError):
        fecha = None

    return {
        "message_id": message_id,
        "huella": hashlib.sha256(message_id.encode("utf-8")).hexdigest(),
        "remitente": remitente[:150],
        "asunto": limpiar_cabecera(mensaje.get("Subject"), 200) or "(sin asunto)",
        "fecha": fecha,
    }


def guardar_correo(crudo, mensaje):
    """Guarda el .eml y su fila. Devuelve 'nuevo' o 'duplicado'."""
    datos = metadatos(crudo, mensaje)
    carpeta = current_app.config["CORREOS_FOLDER"]
    os.makedirs(carpeta, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.eml"
    ruta = os.path.join(carpeta, nombre)
    sha256 = hashlib.sha256(crudo).hexdigest()
    connection = get_db_connection()

    try:
        connection.begin()
        with connection.cursor() as cursor:
            sistema = obtener_usuario_sistema(cursor)
            cursor.execute(
                "SELECT id FROM correos_entrantes WHERE huella_message_id = %s",
                (datos["huella"],),
            )
            if cursor.fetchone() is not None:
                connection.rollback()
                return "duplicado"

            cursor.execute(
                """
                INSERT INTO correos_entrantes (
                    huella_message_id, message_id, remitente, asunto,
                    fecha_correo, nombre_almacenado, tamano, sha256
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    datos["huella"], datos["message_id"], datos["remitente"],
                    datos["asunto"], datos["fecha"], nombre, len(crudo), sha256,
                ),
            )
            correo_id = cursor.lastrowid

        with open(ruta, "xb") as destino:
            destino.write(crudo)

        registrar_evento(
            connection, sistema["id"], "CORREO_RECIBIDO",
            {
                "correo_entrante_id": correo_id,
                "remitente": datos["remitente"],
                "asunto": datos["asunto"],
                "tamano": len(crudo),
                "sha256": sha256,
            },
        )
        connection.commit()
        return "nuevo"

    except Exception:
        connection.rollback()
        if os.path.isfile(ruta):
            try:
                os.remove(ruta)
            except OSError:
                current_app.logger.exception("No se pudo limpiar el .eml.")
        raise
    finally:
        connection.close()


def _tamano(respuesta):
    for parte in respuesta or []:
        texto = parte[0] if isinstance(parte, tuple) else parte
        if isinstance(texto, bytes):
            coincidencia = re.search(rb"RFC822\.SIZE (\d+)", texto)
            if coincidencia:
                return int(coincidencia.group(1))
    return None


def _contenido(respuesta):
    for parte in respuesta or []:
        if isinstance(parte, tuple) and len(parte) == 2:
            return parte[1]
    return None


def descargar_correos(cfg=None, conectar_fn=conectar):
    cfg = cfg or validar_configuracion_imap()
    resumen = {"revisados": 0, "guardados": 0, "duplicados": 0,
               "ignorados": 0, "omitidos_tamano": 0, "errores": 0}
    conexion = conectar_fn(cfg)

    try:
        tipo, datos = conexion.uid("SEARCH", None, "UNSEEN")
        if tipo != "OK":
            raise ErrorCorreoEntrante("IMAP", "No se pudo buscar en la bandeja.")
        uids = (datos[0] or b"").split()[: cfg["max_mensajes"]]

        for uid in uids:
            resumen["revisados"] += 1
            _, respuesta = conexion.uid("FETCH", uid, "(RFC822.SIZE)")
            tamano = _tamano(respuesta)
            if tamano is None or tamano > cfg["max_bytes"]:
                resumen["omitidos_tamano"] += 1
                current_app.logger.warning("Correo UID %s omitido por tamaño.", uid)
                continue

            _, respuesta = conexion.uid("FETCH", uid, "(BODY.PEEK[])")
            crudo = _contenido(respuesta)
            if not crudo or len(crudo) > cfg["max_bytes"]:
                resumen["omitidos_tamano"] += 1
                continue

            mensaje = BytesParser(policy=policy.default).parsebytes(crudo)
            if es_automatico(mensaje) or not es_facturacion(
                mensaje.get("Subject"), texto_del_mensaje(mensaje)
            ):
                resumen["ignorados"] += 1
                continue

            try:
                estado = guardar_correo(crudo, mensaje)
            except Exception:
                resumen["errores"] += 1
                current_app.logger.exception("No se pudo guardar el UID %s", uid)
                continue

            resumen["guardados" if estado == "nuevo" else "duplicados"] += 1
            conexion.uid("STORE", uid, "+FLAGS", "(\\Seen)")

        return resumen
    finally:
        _cerrar(conexion)


def resolver_cliente(cursor, remitente, rut):
    """Devuelve (cliente | None, alertas, motivos)."""
    alertas, motivos = [], []
    columnas = "id, rut, razon_social, giro, direccion, email_contacto, activo"

    cursor.execute(
        f"SELECT {columnas} FROM clientes "
        "WHERE LOWER(email_contacto) = %s AND activo = 1",
        (remitente.lower(),),
    )
    por_correo = cursor.fetchall()

    if rut:
        cursor.execute(
            f"SELECT {columnas} FROM clientes WHERE rut = %s AND activo = 1",
            (rut,),
        )
        por_rut = cursor.fetchone()
        if por_rut is None:
            motivos.append(f"El RUT {rut} no corresponde a un cliente activo.")
            return None, alertas, motivos
        if por_rut["email_contacto"].lower() != remitente.lower():
            alertas.append(
                "El remitente no es el correo de contacto registrado del "
                "cliente: confirme que la solicitud es legítima."
            )
        return por_rut, alertas, motivos

    if len(por_correo) == 1:
        return por_correo[0], alertas, motivos
    if len(por_correo) > 1:
        motivos.append(
            "El remitente está asociado a varios clientes; el correo debe "
            "indicar el RUT."
        )
    else:
        motivos.append(
            "No se identificó al cliente: el remitente no está registrado y "
            "el correo no indica un RUT de cliente activo."
        )
    return None, alertas, motivos


def _leer_eml(correo):
    with open(_ruta_eml(correo["nombre_almacenado"]), "rb") as archivo:
        crudo = archivo.read()
    if hashlib.sha256(crudo).hexdigest() != correo["sha256"]:
        raise ErrorCorreoEntrante(
            "INTEGRIDAD", "El .eml almacenado no coincide con su huella SHA-256."
        )
    return crudo


def _marcar(cursor, correo_id, estado, **campos):
    cursor.execute(
        """
        UPDATE correos_entrantes
        SET estado = %s, cliente_id = %s, solicitud_id = %s,
            datos_extraidos = %s, observaciones = %s,
            intentos = intentos + 1, procesado_en = NOW()
        WHERE id = %s
        """,
        (
            estado, campos.get("cliente_id"), campos.get("solicitud_id"),
            _json(campos.get("datos")), _json(campos.get("observaciones")),
            correo_id,
        ),
    )


def _id_catalogo(cursor, tabla, nombre):
    # "tabla" solo recibe valores fijos desde este módulo.
    cursor.execute(f"SELECT id FROM {tabla} WHERE nombre = %s", (nombre,))
    fila = cursor.fetchone()
    if fila is None:
        raise ErrorCorreoEntrante(
            "CONFIGURACION", f"Falta '{nombre}' en {tabla}. Ejecute la migración 003."
        )
    return fila["id"]


def procesar_correo(correo_id):
    """Devuelve {"estado", "solicitud_id", "public_id", "motivos"}."""
    connection = get_db_connection()

    try:
        connection.begin()
        with connection.cursor() as cursor:
            sistema = obtener_usuario_sistema(cursor)
            cursor.execute(
                "SELECT * FROM correos_entrantes WHERE id = %s FOR UPDATE",
                (correo_id,),
            )
            correo = cursor.fetchone()
            if correo is None or correo["estado"] != "RECIBIDO":
                connection.rollback()
                return {"estado": "OMITIDO", "solicitud_id": None,
                        "public_id": None, "motivos": []}

            crudo = _leer_eml(correo)
            mensaje = BytesParser(policy=policy.default).parsebytes(crudo)
            datos, alertas = extraer_datos(mensaje)
            motivos = []

            if verificacion_remitente(mensaje) == "fallida":
                motivos.append(
                    "El correo no superó la verificación SPF/DMARC "
                    "(posible suplantación del remitente)."
                )

            cliente, alertas_cliente, motivos_cliente = resolver_cliente(
                cursor, correo["remitente"], datos["rut"]
            )
            alertas += alertas_cliente
            motivos += motivos_cliente

            limpio = {}
            if cliente is not None:
                receptor, errores_cliente = validar_cliente(cliente)
                if errores_cliente:
                    motivos.append(
                        "La ficha del cliente tiene datos inválidos: "
                        + " ".join(errores_cliente.values())
                    )
                limpio, errores = validar_solicitud({
                    "cliente_id": cliente["id"],
                    "concepto": datos["concepto"] or "",
                    "monto_bruto": datos["monto_bruto"] or "",
                    "fecha_emision": datos["fecha_emision"] or "",
                    "tipo_afectacion": datos["tipo_afectacion"] or "",
                    "nro_orden_compra": datos["nro_orden_compra"] or "",
                })
                motivos += list(errores.values())

            observaciones = {"alertas": alertas, "motivos": motivos}

            if motivos:
                _marcar(cursor, correo_id, "REQUIERE_REVISION",
                        cliente_id=cliente["id"] if cliente else None,
                        datos=datos, observaciones=observaciones)
                registrar_evento(
                    connection, sistema["id"], "CORREO_REQUIERE_REVISION",
                    {"correo_entrante_id": correo_id, "motivos": motivos},
                )
                connection.commit()
                return {"estado": "REQUIERE_REVISION", "solicitud_id": None,
                        "public_id": None, "motivos": motivos}

            # Idempotencia: la huella del Message-ID es la clave (64 hex).
            cursor.execute(
                """
                SELECT id, public_id FROM solicitudes
                WHERE emisor_id = %s AND clave_idempotencia = %s
                """,
                (sistema["id"], correo["huella_message_id"]),
            )
            existente = cursor.fetchone()
            if existente is not None:
                _marcar(cursor, correo_id, "PROCESADO",
                        cliente_id=cliente["id"], solicitud_id=existente["id"],
                        datos=datos, observaciones=observaciones)
                connection.commit()
                return {"estado": "PROCESADO", "solicitud_id": existente["id"],
                        "public_id": existente["public_id"], "motivos": [],
                        "nueva": False}

            registro = {
                "public_id": secrets.token_hex(16),
                "emisor_id": sistema["id"],
                "cliente_id": cliente["id"],
                "estado_id": _id_catalogo(cursor, "estados_solicitud", "En revisión"),
                "origen_id": _id_catalogo(cursor, "origenes_solicitud", "Correo"),
                "rut": receptor["rut"],
                "nombre": receptor["razon_social"],
                "direccion": receptor["direccion"],
                "giro": receptor["giro"],
                "email_contacto_receptor": receptor["email_contacto"],
                "concepto": limpio["concepto"],
                "nro_orden_compra": limpio["nro_orden_compra"],
                "fecha_emision": limpio["fecha_emision"],
                "monto_bruto": limpio["monto_bruto"],
                "tipo_afectacion": limpio["tipo_afectacion"],
                "email_emisor": correo["remitente"],
                "clave_idempotencia": correo["huella_message_id"],
                "huella_creacion": huella_de_creacion(limpio),
            }
            solicitud_id = insertar_solicitud(cursor, registro)
            solicitud = dict(registro, id=solicitud_id)
            factura = generar_version(cursor, solicitud, sistema["id"])

            _marcar(cursor, correo_id, "PROCESADO",
                    cliente_id=cliente["id"], solicitud_id=solicitud_id,
                    datos=datos, observaciones=observaciones)

        registrar_evento(
            connection, sistema["id"], "SOLICITUD_CREADA",
            {
                "solicitud_afectada_id": solicitud_id,
                "public_id": registro["public_id"],
                "cliente_id": cliente["id"],
                "estado": "En revisión",
                "origen": "Correo",
                "correo_entrante_id": correo_id,
                "remitente": correo["remitente"],
                "concepto": limpio["concepto"],
                "monto_bruto": str(limpio["monto_bruto"]),
                "fecha_emision": limpio["fecha_emision"].isoformat(),
                "tipo_afectacion": limpio["tipo_afectacion"],
                "nro_orden_compra": limpio["nro_orden_compra"],
                "alertas": alertas,
            },
        )
        registrar_evento(
            connection, sistema["id"], "FACTURA_GENERADA",
            evento_factura_generada(solicitud, factura, {
                "estado_nuevo": "En revisión",
                "correo_entrante_id": correo_id,
            }),
        )
        connection.commit()
        return {"estado": "PROCESADO", "solicitud_id": solicitud_id,
                "public_id": registro["public_id"], "motivos": [],
                "nueva": True, "sistema_id": sistema["id"]}

    except Exception as exc:
        connection.rollback()
        current_app.logger.exception("Error al procesar el correo %s", correo_id)
        _registrar_error(correo_id, exc)
        return {"estado": "ERROR", "solicitud_id": None, "public_id": None,
                "motivos": [getattr(exc, "detalle", type(exc).__name__)]}

    finally:
        connection.close()


def _registrar_error(correo_id, exc):
    detalle = (
        str(exc) if isinstance(exc, ErrorCorreoEntrante)
        else "Error técnico al procesar el correo. Revise el registro de la aplicación."
    )
    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE correos_entrantes
                SET estado = 'ERROR', observaciones = %s,
                    intentos = intentos + 1, procesado_en = NOW()
                WHERE id = %s AND estado = 'RECIBIDO'
                """,
                (_json({"motivos": [detalle], "alertas": []}), correo_id),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        current_app.logger.exception("No se pudo marcar el error del correo %s", correo_id)
    finally:
        connection.close()


def procesar_pendientes(limite=50):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM correos_entrantes
                WHERE estado = 'RECIBIDO'
                ORDER BY id
                LIMIT %s
                """,
                (limite,),
            )
            ids = [fila["id"] for fila in cursor.fetchall()]
    finally:
        connection.close()

    resumen = {"procesados": 0, "requieren_revision": 0, "errores": 0,
               "avisos_enviados": 0, "avisos_fallidos": 0}

    for correo_id in ids:
        resultado = procesar_correo(correo_id)
        if resultado["estado"] == "PROCESADO":
            resumen["procesados"] += 1
            if resultado.get("nueva"):
                aviso = notificar_factura_generada(
                    resultado["sistema_id"], resultado["solicitud_id"]
                )
                resumen["avisos_enviados"] += aviso["enviados"]
                resumen["avisos_fallidos"] += aviso["fallidos"]
        elif resultado["estado"] == "REQUIERE_REVISION":
            resumen["requieren_revision"] += 1
        elif resultado["estado"] == "ERROR":
            resumen["errores"] += 1

    return resumen


def revisar_bandeja(descargar=True):
    """Ejecuta las dos etapas con exclusión mutua.

    Devuelve {"descarga": dict | None, "error_descarga": str | None,
              "proceso": dict}.
    """
    bloqueo = get_db_connection()
    try:
        with bloqueo.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0) AS ok", (NOMBRE_BLOQUEO,))
            if not (cursor.fetchone() or {}).get("ok"):
                raise ErrorCorreoEntrante(
                    "EN_CURSO", "Ya hay una revisión de la bandeja en curso."
                )
        try:
            descarga, error = None, None
            if descargar:
                try:
                    descarga = descargar_correos()
                except ErrorCorreoEntrante as exc:
                    error = f"[{exc.codigo}] {exc}"
                    current_app.logger.warning("IMAP: %s | %s", exc, exc.detalle)
            return {"descarga": descarga, "error_descarga": error,
                    "proceso": procesar_pendientes()}
        finally:
            with bloqueo.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (NOMBRE_BLOQUEO,))
    finally:
        bloqueo.close()


def _admin(cursor, actor_id):
    try:
        actor = comprobar_actor(cursor, actor_id)
    except ErrorGestionSolicitud as exc:
        raise ErrorCorreoEntrante("PERMISO", str(exc)) from exc
    if actor["rol_nombre"] != "Administrador":
        raise ErrorCorreoEntrante("PERMISO", "Solo un Administrador puede gestionar la bandeja.")
    return actor


def _cambiar_estado_correo(actor_id, correo_id, permitidos, nuevo, accion,
                           motivo=None, ip=None):
    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            actor = _admin(cursor, actor_id)
            cursor.execute(
                "SELECT id, estado FROM correos_entrantes WHERE id = %s FOR UPDATE",
                (correo_id,),
            )
            correo = cursor.fetchone()
            if correo is None:
                raise ErrorCorreoEntrante("REGISTRO", "El correo no existe.")
            if correo["estado"] not in permitidos:
                raise ErrorCorreoEntrante(
                    "ESTADO", "El estado actual del correo no permite esta acción."
                )
            cursor.execute(
                "UPDATE correos_entrantes SET estado = %s WHERE id = %s",
                (nuevo, correo_id),
            )
        registrar_evento(
            connection, actor["id"], accion,
            {"correo_entrante_id": correo_id, "estado_anterior": correo["estado"],
             "estado_nuevo": nuevo, "motivo": motivo},
            ip,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def reprocesar_correo(actor_id, correo_id, ip=None):
    """Vuelve a RECIBIDO y lo procesa (p. ej., tras registrar al cliente)."""
    _cambiar_estado_correo(actor_id, correo_id, ESTADOS_REPROCESABLES,
                           "RECIBIDO", "CORREO_REPROCESADO", ip=ip)
    resultado = procesar_correo(correo_id)
    if resultado.get("nueva"):
        notificar_factura_generada(resultado["sistema_id"], resultado["solicitud_id"])
    return resultado


def descartar_correo(actor_id, correo_id, motivo, ip=None):
    motivo = str(motivo or "").strip()
    if not 5 <= len(motivo) <= 300:
        raise ErrorCorreoEntrante("VALIDACION", "Indique el motivo (5 a 300 caracteres).")
    _cambiar_estado_correo(actor_id, correo_id, ESTADOS_DESCARTABLES,
                           "DESCARTADO", "CORREO_DESCARTADO", motivo, ip)


def listar_correos(estado=None, limite=100):
    condiciones, parametros = "", []
    if estado:
        condiciones = "WHERE c.estado = %s"
        parametros.append(estado)
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id, c.remitente, c.asunto, c.fecha_correo, c.estado,
                       c.tamano, c.intentos, c.recibido_en, c.procesado_en,
                       c.datos_extraidos, c.observaciones,
                       s.public_id, cl.razon_social AS cliente_nombre
                FROM correos_entrantes AS c
                LEFT JOIN solicitudes AS s ON s.id = c.solicitud_id
                LEFT JOIN clientes AS cl ON cl.id = c.cliente_id
                {condiciones}
                ORDER BY c.id DESC
                LIMIT %s
                """,
                tuple(parametros) + (limite,),
            )
            filas = cursor.fetchall()
    finally:
        connection.close()

    for fila in filas:
        fila["datos_extraidos"] = _cargar(fila["datos_extraidos"]) or {}
        fila["observaciones"] = _cargar(fila["observaciones"]) or {}
    return filas


def obtener_eml_autorizado(actor_id, correo_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            actor = _admin(cursor, actor_id)
            cursor.execute(
                "SELECT id, nombre_almacenado, sha256 FROM correos_entrantes WHERE id = %s",
                (correo_id,),
            )
            correo = cursor.fetchone()
    finally:
        connection.close()

    if correo is None:
        raise ErrorCorreoEntrante("REGISTRO", "El correo no existe.")
    _leer_eml(correo)
    return actor, correo, _ruta_eml(correo["nombre_almacenado"])
