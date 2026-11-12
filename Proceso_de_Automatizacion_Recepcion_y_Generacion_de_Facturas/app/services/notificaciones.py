"""Avisos por correo al Administrador.

- Factura generada: "la factura vN está lista para validar".
- Factura aprobada: "la factura vN fue validada", con el DTE para el SII
  adjunto.

Mismo esquema de tres fases que correos_solicitud (sin bloqueos de BD
durante SMTP). Cada aviso queda en envios_correo (tipo
NOTIFICACION_ADMIN) y en auditoria. Nunca lanza excepciones: la factura
ya está guardada y un fallo de correo no debe deshacerla.
"""
import hashlib
import json
import os

from flask import current_app, render_template

from ..models import get_db_connection
from .correo import ErrorCorreo, construir_mensaje, enviar, limpiar_cabecera, validar_configuracion
from .usuarios import registrar_evento
from .validaciones import ErrorValidacion, normalizar_correo

# Cabecera propia: la bandeja IMAP ignora estos correos (evita bucles
# si el Administrador usa la misma casilla).
CABECERA_ORIGEN = "X-Facturaciones-Origen"
VALOR_ORIGEN = "notificacion"


class ErrorAviso(Exception):
    pass


def destinatarios(cursor, config):
    configurados = [c.strip() for c in str(config.get("NOTIFICAR_A") or "").split(",")]
    correos = []

    if any(configurados):
        candidatos = configurados
    else:
        cursor.execute(
            """
            SELECT u.email
            FROM usuarios AS u
            INNER JOIN roles AS r ON r.id = u.rol_id
            WHERE r.nombre = 'Administrador' AND u.activo = 1
            ORDER BY u.id
            """
        )
        candidatos = [fila["email"] for fila in cursor.fetchall()]

    for candidato in candidatos:
        if not candidato:
            continue
        try:
            correo = normalizar_correo(candidato)
        except ErrorValidacion:
            current_app.logger.warning("NOTIFICAR_A contiene un correo inválido.")
            continue
        if correo not in correos:
            correos.append(correo)

    return correos


def _monto(valor):
    return "{:,.0f}".format(valor).replace(",", ".")


def _cargar_json(valor):
    return json.loads(valor) if isinstance(valor, (str, bytes)) else valor


def _enlace(base_url, solicitud):
    return f"{base_url.rstrip('/')}/solicitudes/{solicitud['public_id']}/factura"


def componer(solicitud, factura, correo_entrante, base_url):
    datos = _cargar_json(factura["datos"])
    observaciones = _cargar_json(
        (correo_entrante or {}).get("observaciones")
    ) or {}

    asunto = limpiar_cabecera(
        f"[Facturaciones] Factura v{factura['version']} lista para validar - "
        f"{solicitud['nombre']} - {solicitud['public_id'][:8]}",
        200,
    )
    cuerpo = render_template(
        "correos/notificacion_factura.txt",
        solicitud=solicitud,
        factura=factura,
        datos=datos,
        correo=correo_entrante,
        alertas=observaciones.get("alertas", []),
        total=_monto(datos["totales"]["monto_total"]),
        enlace=_enlace(base_url, solicitud),
    )
    return asunto, cuerpo


def componer_aprobada(solicitud, factura, base_url):
    datos = _cargar_json(factura["datos"])

    asunto = limpiar_cabecera(
        f"[Facturaciones] Factura v{factura['version']} aprobada - archivo "
        f"SII - {solicitud['nombre']} - {solicitud['public_id'][:8]}",
        200,
    )
    cuerpo = render_template(
        "correos/factura_aprobada.txt",
        solicitud=solicitud,
        factura=factura,
        datos=datos,
        total=_monto(datos["totales"]["monto_total"]),
        enlace=_enlace(base_url, solicitud),
    )
    return asunto, cuerpo


def nombre_archivo_dte(factura, public_id):
    return f"DTE_{factura['tipo_dte']}_{public_id[:8]}_v{factura['version']}.xml"


def _leer_dte(factura):
    nombre = factura["archivo_sii"] or ""
    if not nombre or os.path.basename(nombre) != nombre:
        raise ErrorAviso("El registro del archivo SII no es válido.")

    ruta = os.path.join(current_app.config["SII_FOLDER"], nombre)
    with open(ruta, "rb") as archivo:
        contenido = archivo.read()

    if hashlib.sha256(contenido).hexdigest() != factura["archivo_sii_sha256"]:
        raise ErrorAviso("El archivo SII no coincide con su huella SHA-256.")

    return contenido


def _contenido_generada(cursor, solicitud):
    cursor.execute(
        """
        SELECT id, version, datos, cambios
        FROM facturas
        WHERE solicitud_id = %s
        ORDER BY version DESC
        LIMIT 1
        """,
        (solicitud["id"],),
    )
    factura = cursor.fetchone()
    if factura is None:
        return None

    cursor.execute(
        """
        SELECT remitente, asunto, observaciones
        FROM correos_entrantes
        WHERE solicitud_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (solicitud["id"],),
    )
    asunto, cuerpo = componer(
        solicitud, factura, cursor.fetchone(),
        current_app.config["APP_BASE_URL"],
    )
    return factura, asunto, cuerpo, None


def _contenido_aprobada(cursor, solicitud):
    cursor.execute(
        """
        SELECT id, version, tipo_dte, datos, archivo_sii, archivo_sii_sha256
        FROM facturas
        WHERE solicitud_id = %s AND estado = 'APROBADA'
        ORDER BY version DESC
        LIMIT 1
        """,
        (solicitud["id"],),
    )
    factura = cursor.fetchone()
    if factura is None:
        return None

    asunto, cuerpo = componer_aprobada(
        solicitud, factura, current_app.config["APP_BASE_URL"]
    )
    adjunto = (
        nombre_archivo_dte(factura, solicitud["public_id"]),
        _leer_dte(factura),
    )
    return factura, asunto, cuerpo, adjunto


def _preparar(actor_id, columna, valor, contenido_fn, cfg):
    # "columna" solo recibe valores fijos desde este módulo.
    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id, public_id, nombre FROM solicitudes WHERE {columna} = %s",
                (valor,),
            )
            solicitud = cursor.fetchone()
            contenido = contenido_fn(cursor, solicitud) if solicitud else None

            if contenido is None:
                connection.rollback()
                return None, []

            factura, asunto, cuerpo, adjunto = contenido
            pendientes = []
            for destinatario in destinatarios(cursor, current_app.config):
                mensaje = construir_mensaje(
                    remitente=cfg["remitente"],
                    remitente_correo=cfg["remitente_correo"],
                    destinatario=destinatario,
                    asunto=asunto,
                    cuerpo=cuerpo,
                    adjunto=adjunto,
                    cabeceras_extra={CABECERA_ORIGEN: VALOR_ORIGEN},
                )
                cursor.execute(
                    """
                    INSERT INTO envios_correo (
                        solicitud_id, registro_xml_id, tipo, enviado_por,
                        destinatario, asunto, adjunto_nombre, adjunto_sha256,
                        message_id, smtp_host, estado
                    )
                    VALUES (%s, NULL, 'NOTIFICACION_ADMIN', %s, %s, %s, %s,
                            %s, %s, %s, 'EN_PROCESO')
                    """,
                    (
                        solicitud["id"], actor_id, destinatario, asunto,
                        adjunto[0] if adjunto else None,
                        factura.get("archivo_sii_sha256") if adjunto else None,
                        mensaje["Message-ID"], cfg["host"],
                    ),
                )
                pendientes.append((cursor.lastrowid, destinatario, mensaje))

        connection.commit()
        solicitud["version_factura"] = factura["version"]
        return solicitud, pendientes

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _finalizar(actor_id, solicitud, envio_id, destinatario, aviso, error, ip):
    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE envios_correo
                SET estado = %s, error_codigo = %s, error_detalle = %s,
                    finalizado_en = NOW()
                WHERE id = %s AND estado = 'EN_PROCESO'
                """,
                (
                    "FALLIDO" if error else "ENVIADO",
                    error.codigo if error else None,
                    error.detalle if error else None,
                    envio_id,
                ),
            )
        registrar_evento(
            connection, actor_id,
            "NOTIFICACION_FALLIDA" if error else "NOTIFICACION_ENVIADA",
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": solicitud["public_id"],
                "version_factura": solicitud["version_factura"],
                "aviso": aviso,
                "envio_correo_id": envio_id,
                "destinatario": destinatario,
                "error_codigo": error.codigo if error else None,
            },
            ip,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        current_app.logger.exception("No se pudo cerrar el aviso %s", envio_id)
    finally:
        connection.close()


def _notificar(actor_id, columna, valor, contenido_fn, aviso, ip):
    """Devuelve {"enviados": n, "fallidos": n, "error": str|None}."""
    resultado = {"enviados": 0, "fallidos": 0, "error": None}

    try:
        cfg = validar_configuracion()
        solicitud, pendientes = _preparar(
            actor_id, columna, valor, contenido_fn, cfg
        )
    except (ErrorCorreo, ErrorAviso) as exc:
        current_app.logger.warning("Aviso %s no enviado: %s", aviso, exc)
        resultado["error"] = str(exc)
        return resultado
    except Exception:
        current_app.logger.exception("No se pudo preparar el aviso %s", aviso)
        resultado["error"] = "No se pudo preparar el aviso."
        return resultado

    if solicitud is None:
        resultado["error"] = "No se encontró la factura a notificar."
    elif not pendientes:
        resultado["error"] = "No hay Administradores activos a quienes avisar."

    for envio_id, destinatario, mensaje in pendientes:
        error = None
        try:
            enviar(mensaje, cfg)
        except ErrorCorreo as exc:
            error = exc
            current_app.logger.warning(
                "Aviso %s fallido: %s (%s)", envio_id, exc.codigo, exc.detalle
            )
        _finalizar(actor_id, solicitud, envio_id, destinatario, aviso, error, ip)
        resultado["fallidos" if error else "enviados"] += 1

    return resultado


def notificar_factura_generada(actor_id, solicitud_id, ip=None):
    return _notificar(
        actor_id, "id", solicitud_id, _contenido_generada,
        "FACTURA_GENERADA", ip,
    )


def notificar_factura_aprobada(actor_id, public_id, ip=None):
    return _notificar(
        actor_id, "public_id", public_id, _contenido_aprobada,
        "FACTURA_APROBADA", ip,
    )
