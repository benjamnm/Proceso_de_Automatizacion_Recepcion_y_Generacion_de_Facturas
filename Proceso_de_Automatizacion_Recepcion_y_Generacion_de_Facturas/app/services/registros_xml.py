import hashlib
import os
import uuid

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from flask import current_app
from werkzeug.utils import secure_filename

from ..models import get_db_connection
from .solicitudes import ErrorGestionSolicitud, comprobar_actor
from .usuarios import registrar_evento


class ErrorArchivoXML(Exception):
    pass


ESTADOS_QUE_ADMITEN_XML = ("Pendiente", "En revisión")


def validar_xml(contenido):
    if not contenido:
        raise ErrorArchivoXML("El archivo XML está vacío.")

    try:
        ElementTree.fromstring(
            contenido,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise ErrorArchivoXML(
            "El archivo no es XML válido o contiene "
            "una estructura XML no permitida."
        ) from exc


def obtener_actor(cursor, actor_id):
    try:
        return comprobar_actor(cursor, actor_id)
    except ErrorGestionSolicitud as exc:
        raise ErrorArchivoXML(str(exc)) from exc


def obtener_solicitud(cursor, actor, public_id, bloquear=False):
    sufijo = " FOR UPDATE" if bloquear else ""

    cursor.execute(
        """
        SELECT s.id, s.public_id, s.emisor_id,
               e.nombre AS estado_nombre
        FROM solicitudes AS s
        INNER JOIN estados_solicitud AS e ON e.id = s.estado_id
        WHERE s.public_id = %s
        """ + sufijo,
        (public_id,),
    )
    solicitud = cursor.fetchone()

    if solicitud is None or (
        actor["rol_nombre"] != "Administrador"
        and solicitud["emisor_id"] != actor["id"]
    ):
        raise ErrorArchivoXML("La solicitud no está disponible.")

    return solicitud


def guardar_xml(actor_id, public_id, archivo, ip=None):
    nombre_original = (archivo.filename or "").strip()

    if not nombre_original:
        raise ErrorArchivoXML("Seleccione un archivo.")

    if len(nombre_original) > 255:
        raise ErrorArchivoXML("El nombre del archivo es demasiado largo.")

    if not nombre_original.lower().endswith(".xml"):
        raise ErrorArchivoXML("Solo se permiten archivos .xml.")

    if not secure_filename(nombre_original).lower().endswith(".xml"):
        raise ErrorArchivoXML("El nombre del archivo no es válido.")

    limite = current_app.config["MAX_XML_UPLOAD_BYTES"]
    contenido = archivo.read(limite + 1)

    if len(contenido) > limite:
        raise ErrorArchivoXML("El XML supera el límite de 5 MB.")

    validar_xml(contenido)

    sha256 = hashlib.sha256(contenido).hexdigest()
    nombre_almacenado = f"{uuid.uuid4().hex}.xml"
    carpeta = current_app.config["XML_UPLOAD_FOLDER"]
    ruta_nueva = os.path.join(carpeta, nombre_almacenado)
    ruta_anterior = None

    os.makedirs(carpeta, exist_ok=True)
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = obtener_actor(cursor, actor_id)
            solicitud = obtener_solicitud(
                cursor, actor, public_id, bloquear=True
            )

            if solicitud["estado_nombre"] not in ESTADOS_QUE_ADMITEN_XML:
                raise ErrorArchivoXML(
                    "El estado actual no permite cargar XML."
                )

            cursor.execute(
                """
                SELECT id, nombre_almacenado
                FROM registros_xml
                WHERE solicitud_id = %s
                FOR UPDATE
                """,
                (solicitud["id"],),
            )
            anterior = cursor.fetchone()

            if anterior:
                accion = "XML_REEMPLAZADO"
                ruta_anterior = os.path.join(
                    carpeta, anterior["nombre_almacenado"]
                )
                cursor.execute(
                    """
                    UPDATE registros_xml
                    SET nombre_original = %s,
                        nombre_almacenado = %s,
                        tamano = %s,
                        sha256 = %s,
                        subido_por = %s,
                        subido_en = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        nombre_original, nombre_almacenado,
                        len(contenido), sha256,
                        actor["id"], anterior["id"],
                    ),
                )
                registro_id = anterior["id"]
            else:
                accion = "XML_CARGADO"
                cursor.execute(
                    """
                    INSERT INTO registros_xml (
                        solicitud_id, nombre_original,
                        nombre_almacenado, tamano,
                        sha256, subido_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        solicitud["id"], nombre_original,
                        nombre_almacenado, len(contenido),
                        sha256, actor["id"],
                    ),
                )
                registro_id = cursor.lastrowid

        with open(ruta_nueva, "xb") as destino:
            destino.write(contenido)

        registrar_evento(
            connection,
            actor["id"],
            accion,
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": public_id,
                "registro_xml_id": registro_id,
                "nombre_original": nombre_original,
                "tamano": len(contenido),
                "sha256": sha256,
            },
            ip,
        )

        connection.commit()

        if ruta_anterior and os.path.isfile(ruta_anterior):
            try:
                os.remove(ruta_anterior)
            except OSError:
                current_app.logger.exception(
                    "No se pudo eliminar el XML reemplazado."
                )

        return registro_id

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


def obtener_xml_autorizado(actor_id, public_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            actor = obtener_actor(cursor, actor_id)
            solicitud = obtener_solicitud(cursor, actor, public_id)

            cursor.execute(
                """
                SELECT id, nombre_original, nombre_almacenado,
                       tamano, sha256, subido_en
                FROM registros_xml
                WHERE solicitud_id = %s
                """,
                (solicitud["id"],),
            )
            registro_xml = cursor.fetchone()

        if registro_xml is None:
            raise ErrorArchivoXML("La solicitud todavía no tiene XML.")

        nombre = registro_xml["nombre_almacenado"]

        if os.path.basename(nombre) != nombre:
            raise ErrorArchivoXML("El registro del archivo no es válido.")

        ruta = os.path.join(
            current_app.config["XML_UPLOAD_FOLDER"], nombre
        )

        if not os.path.isfile(ruta):
            raise ErrorArchivoXML(
                "El archivo registrado no está disponible."
            )

        return actor, solicitud, registro_xml, ruta

    finally:
        connection.close()