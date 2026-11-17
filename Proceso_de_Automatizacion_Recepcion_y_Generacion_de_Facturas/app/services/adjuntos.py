"""Documentos adjuntos de una solicitud (PDF, PNG o JPEG).

Reglas:
- Tipo validado por extensión Y por los primeros bytes del contenido.
- PDF con contenido activo (JavaScript, Launch, archivos incrustados) se
  rechaza. Es una revisión simple: la protección principal es que la
  descarga siempre es "attachment" con el MIME fijado por el servidor.
- Archivos fuera de /static, con nombre aleatorio (uuid4).
- Nunca queda un archivo sin su fila ni una fila sin su archivo: quien
  llama hace rollback y borra las rutas escritas si algo falla.
"""
import hashlib
import os
import re
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from ..models import get_db_connection
from .registros_xml import ErrorArchivoXML, obtener_actor, obtener_solicitud


class ErrorAdjunto(Exception):
    pass


# extensión -> tipo guardado en la BD
EXTENSIONES = {
    ".pdf": "PDF",
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
}

FIRMAS = {
    "PDF": b"%PDF-",
    "PNG": b"\x89PNG\r\n\x1a\n",
    "JPEG": b"\xff\xd8\xff",
}

# El MIME de descarga lo fija el servidor, nunca el navegador.
MIMETYPES = {
    "PDF": "application/pdf",
    "PNG": "image/png",
    "JPEG": "image/jpeg",
}

PATRON_PDF_ACTIVO = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFile)(?![A-Za-z0-9])"
)
PATRON_ESCAPE_NOMBRE_PDF = re.compile(rb"#([0-9A-Fa-f]{2})")
PATRON_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _pdf_activo(contenido):
    # Los nombres PDF admiten escapes #xx (p. ej. /J#61vaScript).
    normalizado = PATRON_ESCAPE_NOMBRE_PDF.sub(
        lambda m: bytes([int(m.group(1), 16)]), contenido
    )
    return PATRON_PDF_ACTIVO.search(normalizado) is not None


def _validar_nombre(nombre):
    if not 1 <= len(nombre) <= 255:
        raise ErrorAdjunto(
            "El nombre de un archivo adjunto debe tener entre 1 y 255 "
            "caracteres."
        )

    if PATRON_CONTROL.search(nombre) or "/" in nombre or "\\" in nombre:
        raise ErrorAdjunto(
            f"El nombre del archivo «{nombre[:60]}» no es válido."
        )

    extension = os.path.splitext(nombre)[1].lower()

    if extension not in EXTENSIONES:
        raise ErrorAdjunto(
            "Solo se permiten adjuntos PDF, PNG o JPG."
        )

    if os.path.splitext(secure_filename(nombre))[1].lower() != extension:
        raise ErrorAdjunto(
            f"El nombre del archivo «{nombre[:60]}» no es válido."
        )

    return extension


def leer_adjuntos(archivos):
    """Valida los archivos recibidos. No toca disco ni BD."""
    archivos = [
        archivo for archivo in (archivos or [])
        if archivo is not None and (archivo.filename or "").strip()
    ]

    maximo = current_app.config["MAX_ADJUNTOS_SOLICITUD"]
    limite = current_app.config["MAX_ADJUNTO_BYTES"]
    limite_mb = limite // (1024 * 1024)

    if len(archivos) > maximo:
        raise ErrorAdjunto(
            f"Puede adjuntar como máximo {maximo} archivos."
        )

    adjuntos = []

    for archivo in archivos:
        nombre = archivo.filename.strip()
        extension = _validar_nombre(nombre)
        tipo = EXTENSIONES[extension]

        contenido = archivo.read(limite + 1)

        if not contenido:
            raise ErrorAdjunto(f"El archivo «{nombre[:60]}» está vacío.")

        if len(contenido) > limite:
            raise ErrorAdjunto(
                f"El archivo «{nombre[:60]}» supera el límite de "
                f"{limite_mb} MB."
            )

        if not contenido.startswith(FIRMAS[tipo]):
            raise ErrorAdjunto(
                f"El contenido de «{nombre[:60]}» no corresponde a un "
                f"archivo {tipo}."
            )

        if tipo == "PDF" and _pdf_activo(contenido):
            raise ErrorAdjunto(
                f"El PDF «{nombre[:60]}» contiene elementos activos "
                "(scripts o archivos incrustados) y no se puede adjuntar."
            )

        adjuntos.append({
            "nombre_original": nombre,
            "contenido": contenido,
            "tipo": tipo,
            "extension": extension,
            "mimetype": MIMETYPES[tipo],
            "tamano": len(contenido),
            "sha256": hashlib.sha256(contenido).hexdigest(),
        })

    return adjuntos


def eliminar_rutas(rutas):
    for ruta in rutas:
        try:
            if os.path.isfile(ruta):
                os.remove(ruta)
        except OSError:
            current_app.logger.exception(
                "No se pudo limpiar un adjunto tras un error."
            )


def guardar_adjuntos(cursor, solicitud_id, actor_id, adjuntos):
    """Inserta filas y escribe archivos. No hace commit.

    Devuelve (ids, rutas_escritas). Si falla a medio camino, borra lo que
    alcanzó a escribir antes de propagar el error.
    """
    carpeta = current_app.config["ADJUNTOS_FOLDER"]
    os.makedirs(carpeta, exist_ok=True)

    ids = []
    rutas = []

    try:
        for adjunto in adjuntos:
            nombre_almacenado = uuid.uuid4().hex + adjunto["extension"]

            cursor.execute(
                """
                INSERT INTO adjuntos_solicitud (
                    solicitud_id, nombre_original, nombre_almacenado,
                    tipo, tamano, sha256, subido_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    solicitud_id,
                    adjunto["nombre_original"],
                    nombre_almacenado,
                    adjunto["tipo"],
                    adjunto["tamano"],
                    adjunto["sha256"],
                    actor_id,
                ),
            )
            ids.append(cursor.lastrowid)

            ruta = os.path.join(carpeta, nombre_almacenado)
            with open(ruta, "xb") as destino:
                rutas.append(ruta)
                destino.write(adjunto["contenido"])

    except Exception:
        eliminar_rutas(rutas)
        raise

    return ids, rutas


def listar_adjuntos(solicitud_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nombre_original, tipo, tamano, subido_en
                FROM adjuntos_solicitud
                WHERE solicitud_id = %s
                ORDER BY id
                """,
                (solicitud_id,),
            )
            return cursor.fetchall()
    finally:
        connection.close()


def obtener_adjunto_autorizado(actor_id, public_id, adjunto_id):
    """Mismo control de acceso que el XML: Administrador o Emisor dueño."""
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            try:
                actor = obtener_actor(cursor, actor_id)
                solicitud = obtener_solicitud(cursor, actor, public_id)
            except ErrorArchivoXML as exc:
                raise ErrorAdjunto(str(exc)) from exc

            cursor.execute(
                """
                SELECT id, solicitud_id, nombre_original,
                       nombre_almacenado, tipo, tamano, sha256
                FROM adjuntos_solicitud
                WHERE id = %s
                """,
                (adjunto_id,),
            )
            adjunto = cursor.fetchone()
    finally:
        connection.close()

    if adjunto is None or adjunto["solicitud_id"] != solicitud["id"]:
        raise ErrorAdjunto("El documento adjunto no está disponible.")

    nombre = adjunto["nombre_almacenado"]

    if os.path.basename(nombre) != nombre or adjunto["tipo"] not in MIMETYPES:
        raise ErrorAdjunto("El registro del documento no es válido.")

    ruta = os.path.join(current_app.config["ADJUNTOS_FOLDER"], nombre)

    if not os.path.isfile(ruta):
        raise ErrorAdjunto("El documento adjunto no está disponible.")

    adjunto["mimetype"] = MIMETYPES[adjunto["tipo"]]
    return actor, solicitud, adjunto, ruta
