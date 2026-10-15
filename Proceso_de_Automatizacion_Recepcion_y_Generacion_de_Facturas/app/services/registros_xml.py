import hashlib
import os
import uuid

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from flask import current_app

from werkzeug.utils import secure_filename

from ..models import get_db_connection
from .usuarios import registrar_evento


class ErrorRegistroXML(Exception):
    pass


ESTADOS_QUE_ADMITEN_XML = {
    "Pendiente",
    "En revisión",
}


def validar_xml(contenido):
    if not contenido:
        raise ErrorRegistroXML("El registro XML está vacío.")

    try:
        ElementTree.fromstring(
            contenido,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise ErrorRegistroXML(
            "El registro no es XML válido o contiene "
            "una estructura XML no permitida."
        ) from exc
    except Exception as exc:
        raise ErrorRegistroXML(
            "No se pudo analizar el registro XML."
        ) from exc


def obtener_actor(cursor, actor_id):
    cursor.execute(
        """
        SELECT id, rol_id, activo
        FROM usuarios
        WHERE id = %s
        FOR UPDATE
        """,
        (actor_id,),
    )
    actor = cursor.fetchone()

    if actor is None or not actor["activo"]:
        raise ErrorRegistroXML("Su cuenta no está disponible.")

    cursor.execute(
        "SELECT nombre FROM roles WHERE id = %s",
        (actor["rol_id"],),
    )
    rol = cursor.fetchone()

    if rol is None or rol["nombre"] not in {
        "Administrador",
        "Emisor",
    }:
        raise ErrorRegistroXML(
            "No tiene autorización para gestionar XML."
        )

    actor["rol_nombre"] = rol["nombre"]
    return actor


def obtener_solicitud(cursor, actor, public_id):
    cursor.execute(
        """
        SELECT
            s.id,
            s.public_id,
            s.emisor_id,
            s.estado_id,
            e.nombre AS estado_nombre
        FROM solicitudes AS s
        INNER JOIN estados_solicitud AS e
            ON e.id = s.estado_id
        WHERE s.public_id = %s
        FOR UPDATE
        """,
        (public_id,),
    )
    solicitud = cursor.fetchone()

    if solicitud is None:
        raise ErrorRegistroXML(
            "La solicitud no está disponible."
        )

    if (
        actor["rol_nombre"] != "Administrador"
        and solicitud["emisor_id"] != actor["id"]
    ):
        # Devuelve el mismo mensaje para no revelar si existe.
        raise ErrorRegistroXML(
            "La solicitud no está disponible."
        )

    if solicitud["estado_nombre"] not in ESTADOS_QUE_ADMITEN_XML:
        raise ErrorRegistroXML(
            "El estado actual de la solicitud "
            "no permite cargar XML."
        )

    return solicitud


def guardar_xml(
    actor_id,
    public_id,
    archivo,
    ip=None,
):
    nombre_original = (archivo.filename or "").strip()

    if not nombre_original:
        raise ErrorRegistroXML("Seleccione un archivo.")

    if len(nombre_original) > 255:
        raise ErrorRegistroXML(
            "El nombre del archivo es demasiado largo."
        )

    if not nombre_original.lower().endswith(".xml"):
        raise ErrorRegistroXML(
            "Solo se permiten archivos con extensión .xml."
        )

    nombre_seguro = secure_filename(nombre_original)

    if not nombre_seguro or not nombre_seguro.lower().endswith(".xml"):
        raise ErrorRegistroXML(
            "El nombre del archivo no es válido."
        )

    limite = current_app.config["MAX_XML_UPLOAD_BYTES"]
    contenido = archivo.read(limite + 1)

    if len(contenido) > limite:
        raise ErrorRegistroXML(
            "El XML supera el límite de 5 MB."
        )

    validar_xml(contenido)

    sha256 = hashlib.sha256(contenido).hexdigest()
    nombre_almacenado = f"{uuid.uuid4().hex}.xml"
    carpeta = current_app.config["XML_UPLOAD_FOLDER"]
    ruta_nueva = os.path.join(carpeta, nombre_almacenado)

    os.makedirs(carpeta, exist_ok=True)

    connection = get_db_connection()
    ruta_anterior = None

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = obtener_actor(cursor, actor_id)
            solicitud = obtener_solicitud(
                cursor,
                actor,
                public_id,
            )

            cursor.execute(
                """
                SELECT id, nombre_almacenado
                FROM archivos_xml
                WHERE solicitud_id = %s
                FOR UPDATE
                """,
                (solicitud["id"],),
            )
            anterior = cursor.fetchone()

            if anterior:
                accion = "XML_REEMPLAZADO"
                ruta_anterior = os.path.join(
                    carpeta,
                    anterior["nombre_almacenado"],
                )

                cursor.execute(
                    """
                    UPDATE archivos_xml
                    SET nombre_original = %s,
                        nombre_almacenado = %s,
                        tamano_bytes = %s,
                        sha256 = %s,
                        subido_por = %s,
                        subido_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        nombre_original,
                        nombre_almacenado,
                        len(contenido),
                        sha256,
                        actor["id"],
                        anterior["id"],
                    ),
                )

                archivo_id = anterior["id"]

            else:
                accion = "XML_CARGADO"

                cursor.execute(
                    """
                    INSERT INTO archivos_xml (
                        solicitud_id,
                        nombre_original,
                        nombre_almacenado,
                        tamano_bytes,
                        sha256,
                        subido_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        solicitud["id"],
                        nombre_original,
                        nombre_almacenado,
                        len(contenido),
                        sha256,
                        actor["id"],
                    ),
                )

                archivo_id = cursor.lastrowid

        with open(ruta_nueva, "xb") as destino:
            destino.write(contenido)

        registrar_evento(
            connection,
            actor["id"],
            accion,
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": public_id,
                "registro_xml_id": archivo_id,
                "nombre_original": nombre_original,
                "tamano_bytes": len(contenido),
                "sha256": sha256,
            },
            ip,
        )

        connection.commit()

        if (
            ruta_anterior
            and ruta_anterior != ruta_nueva
            and os.path.isfile(ruta_anterior)
        ):
            try:
                os.remove(ruta_anterior)
            except OSError:
                current_app.logger.exception(
                    "No se pudo eliminar el XML reemplazado."
                )

        return archivo_id

    except Exception:
        connection.rollback()

        if os.path.isfile(ruta_nueva):
            try:
                os.remove(ruta_nueva)
            except OSError:
                current_app.logger.exception(
                    "No se pudo limpiar el XML tras un error."
                )

        raise

    finally:
        connection.close()


def obtener_xml_autorizado(
    actor_id,
    public_id,
):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, rol_id, activo
                FROM usuarios
                WHERE id = %s
                """,
                (actor_id,),
            )
            actor = cursor.fetchone()

            if actor is None or not actor["activo"]:
                raise ErrorRegistroXML(
                    "Su cuenta no está disponible."
                )

            cursor.execute(
                "SELECT nombre FROM roles WHERE id = %s",
                (actor["rol_id"],),
            )
            rol = cursor.fetchone()

            if rol is None or rol["nombre"] not in {
                "Administrador",
                "Emisor",
            }:
                raise ErrorRegistroXML(
                    "No tiene autorización para descargar XML."
                )

            actor["rol_nombre"] = rol["nombre"]

            cursor.execute(
                """
                SELECT id, public_id, emisor_id
                FROM solicitudes
                WHERE public_id = %s
                """,
                (public_id,),
            )
            solicitud = cursor.fetchone()

            if solicitud is None:
                raise ErrorRegistroXML(
                    "La solicitud no está disponible."
                )

            if (
                actor["rol_nombre"] != "Administrador"
                and solicitud["emisor_id"] != actor["id"]
            ):
                raise ErrorRegistroXML(
                    "La solicitud no está disponible."
                )

            cursor.execute(
                """
                SELECT
                    id,
                    nombre_original,
                    nombre_almacenado,
                    tamano_bytes,
                    sha256,
                    subido_en
                FROM archivos_xml
                WHERE solicitud_id = %s
                """,
                (solicitud["id"],),
            )
            registro_xml = cursor.fetchone()

            if registro_xml is None:
                raise ErrorRegistroXML(
                    "La solicitud todavía no tiene XML."
                )

        ruta = os.path.join(
            current_app.config["XML_UPLOAD_FOLDER"],
            registro_xml["nombre_almacenado"],
        )

        if not os.path.isfile(ruta):
            raise ErrorRegistroXML(
                "El archivo registrado no está disponible."
            )

        return actor, solicitud, registro_xml, ruta

    finally:
        connection.close()