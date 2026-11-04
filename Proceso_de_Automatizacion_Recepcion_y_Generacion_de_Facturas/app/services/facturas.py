"""Versiones de factura y validación del Administrador.

Cada vez que una solicitud entra a "En revisión" se genera una versión
nueva e inmutable en la tabla facturas (v1, v2, ...). La versión guarda
la foto completa de los datos y la diferencia con la versión anterior,
que también queda en auditoria (FACTURA_GENERADA).

Flujo:
    Pendiente / En corrección --enviar_a_revision--> En revisión (vN)
    En revisión --aprobar_factura--> Aprobada (+ archivo DTE para SII)
    En revisión --observar_factura--> En corrección
"""
import hashlib
import json
import os
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from flask import current_app

from ..models import get_db_connection
from .dte_sii import ErrorDTE, construir_dte, datos_emisor
from .solicitudes import ErrorGestionSolicitud, comprobar_actor
from .usuarios import registrar_evento
from .validaciones import validar_cliente

TASA_IVA = Decimal("19")
ESTADOS_ORIGEN_REVISION = ("Pendiente", "En corrección")
LIMITE_OBSERVACION = 500


class ErrorFactura(Exception):
    pass


# --- Cálculos y datos (sin BD) -------------------------------------------

def _redondear(valor):
    return int(Decimal(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calcular_totales(monto_bruto, tipo_afectacion):
    """Desglosa el monto bruto (con IVA) en neto, IVA y total.

    El SII exige IVA = round(neto * 19%) y total = neto + IVA, por lo que
    el total puede diferir en $1 del bruto informado: se informa como
    diferencia_redondeo para que el Administrador lo vea.
    """
    bruto = int(Decimal(monto_bruto))

    if tipo_afectacion == "EXENTA":
        return {
            "tipo_dte": 34,
            "monto_bruto": bruto,
            "monto_neto": 0,
            "monto_exento": bruto,
            "tasa_iva": 0,
            "iva": 0,
            "monto_total": bruto,
            "diferencia_redondeo": 0,
        }

    neto = _redondear(Decimal(bruto) * 100 / (100 + TASA_IVA))
    iva = _redondear(Decimal(neto) * TASA_IVA / 100)
    total = neto + iva

    return {
        "tipo_dte": 33,
        "monto_bruto": bruto,
        "monto_neto": neto,
        "monto_exento": 0,
        "tasa_iva": int(TASA_IVA),
        "iva": iva,
        "monto_total": total,
        "diferencia_redondeo": total - bruto,
    }


def construir_datos(solicitud):
    """Foto de la factura a partir de una fila de solicitudes."""
    fecha = solicitud["fecha_emision"]
    if isinstance(fecha, date):
        fecha = fecha.isoformat()

    return {
        "solicitud_public_id": solicitud["public_id"],
        "fecha_emision": str(fecha),
        "tipo_afectacion": solicitud["tipo_afectacion"],
        "receptor": {
            "rut": solicitud["rut"],
            "razon_social": solicitud["nombre"],
            "giro": solicitud["giro"],
            "direccion": solicitud["direccion"],
            "email": solicitud.get("email_contacto_receptor"),
        },
        "detalle": {
            "concepto": solicitud["concepto"],
            "nro_orden_compra": solicitud.get("nro_orden_compra"),
        },
        "totales": calcular_totales(
            solicitud["monto_bruto"], solicitud["tipo_afectacion"]
        ),
    }


def huella_datos(datos):
    serializado = json.dumps(
        datos, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _aplanar(datos, prefijo=""):
    plano = {}
    for clave, valor in datos.items():
        ruta = f"{prefijo}{clave}"
        if isinstance(valor, dict):
            plano.update(_aplanar(valor, ruta + "."))
        else:
            plano[ruta] = valor
    return plano


def comparar_datos(anterior, nuevo):
    """Devuelve {campo: {"anterior": x, "nuevo": y}} solo con diferencias."""
    a, n = _aplanar(anterior or {}), _aplanar(nuevo)
    return {
        campo: {"anterior": a.get(campo), "nuevo": n.get(campo)}
        for campo in sorted(set(a) | set(n))
        if a.get(campo) != n.get(campo)
    }


def _cargar_json(valor):
    if valor is None:
        return None
    if isinstance(valor, (bytes, bytearray)):
        valor = valor.decode("utf-8")
    if isinstance(valor, str):
        return json.loads(valor)
    return valor


# --- Operaciones dentro de una transacción ------------------------------

def _estado_id(cursor, nombre):
    cursor.execute(
        "SELECT id FROM estados_solicitud WHERE nombre = %s", (nombre,)
    )
    fila = cursor.fetchone()
    if fila is None:
        raise ErrorFactura(
            f"Falta el estado '{nombre}'. Ejecute la migración 003."
        )
    return fila["id"]


def ultima_version(cursor, solicitud_id, bloquear=False):
    cursor.execute(
        """
        SELECT id, version, estado, datos, huella, tipo_dte, monto_total
        FROM facturas
        WHERE solicitud_id = %s
        ORDER BY version DESC
        LIMIT 1
        """ + (" FOR UPDATE" if bloquear else ""),
        (solicitud_id,),
    )
    return cursor.fetchone()


def generar_version(cursor, solicitud, generada_por):
    """Inserta la versión siguiente. La solicitud debe estar bloqueada."""
    anterior = ultima_version(cursor, solicitud["id"], bloquear=True)
    datos = construir_datos(solicitud)

    if anterior is None:
        version, cambios = 1, None
    else:
        cambios = comparar_datos(_cargar_json(anterior["datos"]), datos)
        if not cambios:
            raise ErrorFactura(
                f"La factura no tiene cambios respecto de la versión "
                f"{anterior['version']}. Corrija los datos antes de "
                f"reenviarla a revisión."
            )
        version = anterior["version"] + 1

    totales = datos["totales"]
    huella = huella_datos(datos)

    cursor.execute(
        """
        INSERT INTO facturas (
            solicitud_id, version, estado, tipo_dte,
            monto_neto, monto_exento, iva, monto_total,
            datos, cambios, huella, generada_por
        )
        VALUES (%s, %s, 'EN_REVISION', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            solicitud["id"], version, totales["tipo_dte"],
            totales["monto_neto"], totales["monto_exento"],
            totales["iva"], totales["monto_total"],
            json.dumps(datos, ensure_ascii=False),
            json.dumps(cambios, ensure_ascii=False) if cambios else None,
            huella, generada_por,
        ),
    )

    return {
        "factura_id": cursor.lastrowid,
        "version": version,
        "version_anterior": anterior["version"] if anterior else None,
        "cambios": cambios,
        "datos": datos,
    }


def evento_factura_generada(solicitud, factura, extra=None):
    detalle = {
        "solicitud_afectada_id": solicitud["id"],
        "public_id": solicitud["public_id"],
        "factura_id": factura["factura_id"],
        "version_factura": factura["version"],
        "version_factura_anterior": factura["version_anterior"],
        "cambios": factura["cambios"],
        "totales": factura["datos"]["totales"],
    }
    detalle.update(extra or {})
    return detalle


def _refrescar_receptor(cursor, solicitud):
    """Toma los datos vigentes del cliente (corregidos en su ficha)."""
    cursor.execute(
        """
        SELECT id, rut, razon_social, giro, direccion, email_contacto, activo
        FROM clientes
        WHERE id = %s
        FOR UPDATE
        """,
        (solicitud["cliente_id"],),
    )
    cliente = cursor.fetchone()

    if cliente is None or not cliente["activo"]:
        raise ErrorFactura("El cliente de la solicitud no está activo.")

    receptor, errores = validar_cliente(cliente)
    if errores:
        raise ErrorFactura(
            "La ficha del cliente tiene datos inválidos: "
            + " ".join(errores.values())
        )

    nuevos = {
        "rut": receptor["rut"],
        "nombre": receptor["razon_social"],
        "giro": receptor["giro"],
        "direccion": receptor["direccion"],
        "email_contacto_receptor": receptor["email_contacto"],
    }

    if any(solicitud[c] != v for c, v in nuevos.items()):
        cursor.execute(
            """
            UPDATE solicitudes
            SET rut = %s, nombre = %s, giro = %s, direccion = %s,
                email_contacto_receptor = %s
            WHERE id = %s
            """,
            (
                nuevos["rut"], nuevos["nombre"], nuevos["giro"],
                nuevos["direccion"], nuevos["email_contacto_receptor"],
                solicitud["id"],
            ),
        )
        solicitud.update(nuevos)

    return solicitud


def _bloquear_solicitud(cursor, actor, public_id, version_esperada):
    try:
        version_esperada = int(version_esperada)
        if version_esperada <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ErrorFactura("La versión del formulario no es válida.")

    cursor.execute(
        """
        SELECT s.*, e.nombre AS estado_nombre
        FROM solicitudes AS s
        INNER JOIN estados_solicitud AS e ON e.id = s.estado_id
        WHERE s.public_id = %s
        FOR UPDATE
        """,
        (public_id,),
    )
    solicitud = cursor.fetchone()

    if solicitud is None or (
        actor["rol_nombre"] != "Administrador"
        and solicitud["emisor_id"] != actor["id"]
    ):
        raise ErrorFactura("La solicitud no está disponible.")

    if solicitud["version"] != version_esperada:
        raise ErrorFactura(
            "La solicitud cambió desde que abrió la pantalla. "
            "Recargue antes de continuar."
        )

    return solicitud


def _actor(cursor, actor_id, solo_admin=False):
    try:
        actor = comprobar_actor(cursor, actor_id)
    except ErrorGestionSolicitud as exc:
        raise ErrorFactura(str(exc)) from exc

    if solo_admin and actor["rol_nombre"] != "Administrador":
        raise ErrorFactura("Solo un Administrador puede validar facturas.")

    return actor


def _cambiar_estado(cursor, solicitud, estado_nombre):
    estado_id = _estado_id(cursor, estado_nombre)
    cursor.execute(
        """
        UPDATE solicitudes
        SET estado_id = %s, motivo_rechazo = NULL, version = version + 1
        WHERE id = %s AND version = %s
        """,
        (estado_id, solicitud["id"], solicitud["version"]),
    )
    if cursor.rowcount != 1:
        raise ErrorFactura("No se pudo aplicar el cambio. Recargue.")


# --- Casos de uso ----------------------------------------------------------

def enviar_a_revision(actor_id, public_id, version_esperada, ip=None):
    """Genera la versión siguiente y deja la solicitud En revisión.

    Devuelve {"version": N, "notificar": bool, "solicitud_id": id}.
    La notificación se envía fuera, después del commit.
    """
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = _actor(cursor, actor_id)
            solicitud = _bloquear_solicitud(
                cursor, actor, public_id, version_esperada
            )
            estado = solicitud["estado_nombre"]

            # "En revisión" sin versión: solicitudes previas a la 003.
            sin_version = (
                estado == "En revisión"
                and ultima_version(cursor, solicitud["id"]) is None
            )

            if estado not in ESTADOS_ORIGEN_REVISION and not sin_version:
                raise ErrorFactura(
                    "Solo se envían a revisión solicitudes Pendientes "
                    "o En corrección."
                )

            solicitud = _refrescar_receptor(cursor, solicitud)
            factura = generar_version(cursor, solicitud, actor["id"])
            _cambiar_estado(cursor, solicitud, "En revisión")

        registrar_evento(
            connection, actor["id"], "FACTURA_GENERADA",
            evento_factura_generada(solicitud, factura, {
                "estado_anterior": estado,
                "estado_nuevo": "En revisión",
                "version_anterior": solicitud["version"],
                "version_nueva": solicitud["version"] + 1,
            }),
            ip,
        )
        connection.commit()

        return {
            "solicitud_id": solicitud["id"],
            "version": factura["version"],
            # Si lo envía un Emisor, el Administrador debe enterarse.
            "notificar": actor["rol_nombre"] != "Administrador",
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def observar_factura(actor_id, public_id, version_esperada, observacion,
                     ip=None):
    """El Administrador indica qué corregir. Pasa a En corrección."""
    observacion = str(observacion or "").strip()

    if len(observacion) < 5:
        raise ErrorFactura("Indique qué debe corregirse (mínimo 5 caracteres).")
    if len(observacion) > LIMITE_OBSERVACION:
        raise ErrorFactura(
            f"La observación no puede superar {LIMITE_OBSERVACION} caracteres."
        )

    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = _actor(cursor, actor_id, solo_admin=True)
            solicitud = _bloquear_solicitud(
                cursor, actor, public_id, version_esperada
            )

            if solicitud["estado_nombre"] != "En revisión":
                raise ErrorFactura("La factura no está en revisión.")

            factura = ultima_version(cursor, solicitud["id"], bloquear=True)
            if factura is None or factura["estado"] != "EN_REVISION":
                raise ErrorFactura("No hay una versión de factura en revisión.")

            cursor.execute(
                """
                UPDATE facturas
                SET estado = 'OBSERVADA', revisada_por = %s,
                    revisada_en = NOW(), observacion = %s
                WHERE id = %s
                """,
                (actor["id"], observacion, factura["id"]),
            )
            _cambiar_estado(cursor, solicitud, "En corrección")

        registrar_evento(
            connection, actor["id"], "FACTURA_OBSERVADA",
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": public_id,
                "factura_id": factura["id"],
                "version_factura": factura["version"],
                "observacion": observacion,
                "estado_anterior": "En revisión",
                "estado_nuevo": "En corrección",
                "version_anterior": solicitud["version"],
                "version_nueva": solicitud["version"] + 1,
            },
            ip,
        )
        connection.commit()
        return factura["version"]

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def aprobar_factura(actor_id, public_id, version_esperada, ip=None):
    """El Administrador valida la versión vigente y se genera el DTE."""
    try:
        emisor = datos_emisor(current_app.config)
    except ErrorDTE as exc:
        raise ErrorFactura(str(exc)) from exc

    carpeta = current_app.config["SII_FOLDER"]
    os.makedirs(carpeta, exist_ok=True)
    ruta = None
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = _actor(cursor, actor_id, solo_admin=True)
            solicitud = _bloquear_solicitud(
                cursor, actor, public_id, version_esperada
            )

            if solicitud["estado_nombre"] != "En revisión":
                raise ErrorFactura("La factura no está en revisión.")

            factura = ultima_version(cursor, solicitud["id"], bloquear=True)
            if factura is None or factura["estado"] != "EN_REVISION":
                raise ErrorFactura("No hay una versión de factura en revisión.")

            datos = _cargar_json(factura["datos"])
            if huella_datos(datos) != factura["huella"]:
                current_app.logger.error(
                    "Huella de factura %s no coincide", factura["id"]
                )
                raise ErrorFactura(
                    "Los datos de la factura no coinciden con su huella. "
                    "Devuélvala a corrección y genere una versión nueva."
                )

            try:
                contenido = construir_dte(datos, emisor, folio=factura["id"])
            except ErrorDTE as exc:
                raise ErrorFactura(str(exc)) from exc

            sha256 = hashlib.sha256(contenido).hexdigest()
            nombre = f"{uuid.uuid4().hex}.xml"
            ruta = os.path.join(carpeta, nombre)

            with open(ruta, "xb") as destino:
                destino.write(contenido)

            cursor.execute(
                """
                UPDATE facturas
                SET estado = 'APROBADA', revisada_por = %s,
                    revisada_en = NOW(), archivo_sii = %s,
                    archivo_sii_sha256 = %s
                WHERE id = %s
                """,
                (actor["id"], nombre, sha256, factura["id"]),
            )
            _cambiar_estado(cursor, solicitud, "Aprobada")

        registrar_evento(
            connection, actor["id"], "FACTURA_APROBADA",
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": public_id,
                "factura_id": factura["id"],
                "version_factura": factura["version"],
                "tipo_dte": factura["tipo_dte"],
                "monto_total": str(factura["monto_total"]),
                "archivo_sii_sha256": sha256,
                "estado_anterior": "En revisión",
                "estado_nuevo": "Aprobada",
                "version_anterior": solicitud["version"],
                "version_nueva": solicitud["version"] + 1,
            },
            ip,
        )
        connection.commit()
        return factura["version"]

    except Exception:
        connection.rollback()
        if ruta and os.path.isfile(ruta):
            try:
                os.remove(ruta)
            except OSError:
                current_app.logger.exception("No se pudo limpiar el DTE.")
        raise

    finally:
        connection.close()


# --- Consultas -------------------------------------------------------------

def listar_versiones(solicitud_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT f.id, f.version, f.estado, f.tipo_dte,
                       f.monto_neto, f.monto_exento, f.iva, f.monto_total,
                       f.datos, f.cambios, f.generada_en, f.revisada_en,
                       f.observacion, f.archivo_sii, f.archivo_sii_sha256,
                       g.nombre AS generada_por_nombre,
                       r.nombre AS revisada_por_nombre
                FROM facturas AS f
                LEFT JOIN usuarios AS g ON g.id = f.generada_por
                LEFT JOIN usuarios AS r ON r.id = f.revisada_por
                WHERE f.solicitud_id = %s
                ORDER BY f.version DESC
                """,
                (solicitud_id,),
            )
            versiones = cursor.fetchall()

            cursor.execute(
                """
                SELECT id, remitente, asunto, fecha_correo, observaciones
                FROM correos_entrantes
                WHERE solicitud_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (solicitud_id,),
            )
            correo = cursor.fetchone()

    finally:
        connection.close()

    for fila in versiones:
        fila["datos"] = _cargar_json(fila["datos"])
        fila["cambios"] = _cargar_json(fila["cambios"])

    if correo:
        correo["observaciones"] = _cargar_json(correo["observaciones"]) or {}

    return versiones, correo


def obtener_archivo_sii(actor_id, public_id):
    """Devuelve (actor, solicitud, factura, ruta) del DTE aprobado."""
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            actor = _actor(cursor, actor_id, solo_admin=True)
            cursor.execute(
                """
                SELECT s.id, s.public_id, f.id AS factura_id, f.version,
                       f.tipo_dte, f.archivo_sii, f.archivo_sii_sha256
                FROM solicitudes AS s
                INNER JOIN facturas AS f ON f.solicitud_id = s.id
                WHERE s.public_id = %s AND f.estado = 'APROBADA'
                ORDER BY f.version DESC
                LIMIT 1
                """,
                (public_id,),
            )
            fila = cursor.fetchone()
    finally:
        connection.close()

    if fila is None or not fila["archivo_sii"]:
        raise ErrorFactura("La solicitud no tiene un archivo SII generado.")

    nombre = fila["archivo_sii"]
    if os.path.basename(nombre) != nombre:
        raise ErrorFactura("El registro del archivo no es válido.")

    ruta = os.path.join(current_app.config["SII_FOLDER"], nombre)

    try:
        with open(ruta, "rb") as archivo:
            contenido = archivo.read()
    except OSError as exc:
        raise ErrorFactura("El archivo SII no está disponible.") from exc

    if hashlib.sha256(contenido).hexdigest() != fila["archivo_sii_sha256"]:
        current_app.logger.error("Integridad DTE fallida: %s", fila["factura_id"])
        raise ErrorFactura("El archivo SII no coincide con su huella SHA-256.")

    return actor, fila, ruta
