"""Envío del XML de una solicitud al receptor, con auditoría.

Flujo en tres fases para no mantener bloqueos de BD durante la conexión
SMTP:

1. Transacción corta: permisos, estado, XML íntegro, sin otro envío en
   curso. Inserta envios_correo en EN_PROCESO y confirma.
2. Envío SMTP, fuera de la transacción.
3. Transacción corta: cierra la fila como ENVIADO o FALLIDO y registra
   CORREO_ENVIADO o CORREO_FALLIDO en auditoria.

Si el proceso se interrumpe entre 2 y 3, la fila queda EN_PROCESO y
bloquea reenvíos durante VENTANA_EN_PROCESO_MIN minutos, para evitar
duplicados al cliente.
"""
import hashlib
import os

from flask import current_app, render_template

from ..models import get_db_connection
from .correo import (
    ErrorCorreo,
    construir_mensaje,
    enviar,
    limpiar_cabecera,
    validar_configuracion,
)
from .solicitudes import ErrorGestionSolicitud, comprobar_actor
from .usuarios import registrar_evento
from .validaciones import ErrorValidacion, normalizar_correo

ESTADOS_QUE_ADMITEN_ENVIO = ("Pendiente", "En revisión")
VENTANA_EN_PROCESO_MIN = 10


class ErrorEnvioCorreo(Exception):
    pass


def componer_correo(solicitud):
    asunto = limpiar_cabecera(
        f"Documento XML - {solicitud['nombre']} - "
        f"Solicitud {solicitud['public_id'][:8]}",
        200,
    )
    cuerpo = render_template(
        "correos/envio_xml.txt",
        solicitud=solicitud,
        monto=(
            "{:,.0f}".format(solicitud["monto_bruto"]).replace(",", ".")
        ),
    )
    return asunto, cuerpo


def _leer_xml_verificado(registro_xml):
    nombre = registro_xml["nombre_almacenado"]

    if os.path.basename(nombre) != nombre:
        raise ErrorEnvioCorreo("El registro del XML no es válido.")

    ruta = os.path.join(current_app.config["XML_UPLOAD_FOLDER"], nombre)

    try:
        with open(ruta, "rb") as archivo:
            contenido = archivo.read()
    except OSError as exc:
        raise ErrorEnvioCorreo(
            "El archivo XML registrado no está disponible."
        ) from exc

    if hashlib.sha256(contenido).hexdigest() != registro_xml["sha256"]:
        current_app.logger.error(
            "Integridad XML fallida en registro %s", registro_xml["id"]
        )
        raise ErrorEnvioCorreo(
            "El XML almacenado no coincide con su huella SHA-256. "
            "Vuelva a cargarlo antes de enviarlo."
        )

    return contenido


def _preparar_envio(actor_id, public_id):
    """Fase 1. Devuelve (actor, solicitud, envio_id, mensaje, cfg)."""
    cfg = validar_configuracion()
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            try:
                actor = comprobar_actor(cursor, actor_id)
            except ErrorGestionSolicitud as exc:
                raise ErrorEnvioCorreo(str(exc)) from exc

            cursor.execute(
                """
                SELECT s.id, s.public_id, s.emisor_id, s.rut, s.nombre,
                       s.concepto, s.monto_bruto, s.fecha_emision,
                       s.tipo_afectacion, s.nro_orden_compra,
                       s.email_contacto_receptor, s.email_emisor,
                       e.nombre AS estado_nombre
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
                raise ErrorEnvioCorreo("La solicitud no está disponible.")

            if solicitud["estado_nombre"] not in ESTADOS_QUE_ADMITEN_ENVIO:
                raise ErrorEnvioCorreo(
                    "El estado actual no permite enviar el XML."
                )

            try:
                destinatario = normalizar_correo(
                    solicitud["email_contacto_receptor"] or ""
                )
            except ErrorValidacion as exc:
                raise ErrorEnvioCorreo(
                    "La solicitud no tiene un correo de receptor válido."
                ) from exc

            cursor.execute(
                """
                SELECT id, nombre_original, nombre_almacenado, sha256
                FROM registros_xml
                WHERE solicitud_id = %s
                """,
                (solicitud["id"],),
            )
            registro_xml = cursor.fetchone()

            if registro_xml is None:
                raise ErrorEnvioCorreo(
                    "Debe cargar el XML antes de enviarlo."
                )

            cursor.execute(
                """
                SELECT id
                FROM envios_correo
                WHERE solicitud_id = %s
                  AND estado = 'EN_PROCESO'
                  AND creado_en > NOW() - INTERVAL %s MINUTE
                LIMIT 1
                """,
                (solicitud["id"], VENTANA_EN_PROCESO_MIN),
            )

            if cursor.fetchone() is not None:
                raise ErrorEnvioCorreo(
                    "Ya hay un envío en curso para esta solicitud. "
                    "Espere unos minutos y revise el historial."
                )

            contenido = _leer_xml_verificado(registro_xml)
            asunto, cuerpo = componer_correo(solicitud)
            responder_a = solicitud["email_emisor"]

            mensaje = construir_mensaje(
                remitente=cfg["remitente"],
                remitente_correo=cfg["remitente_correo"],
                destinatario=destinatario,
                asunto=asunto,
                cuerpo=cuerpo,
                responder_a=responder_a,
                adjunto=(registro_xml["nombre_original"], contenido),
            )

            cursor.execute(
                """
                INSERT INTO envios_correo (
                    solicitud_id, registro_xml_id, enviado_por,
                    destinatario, responder_a, asunto,
                    adjunto_nombre, adjunto_sha256, message_id,
                    smtp_host, estado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'EN_PROCESO')
                """,
                (
                    solicitud["id"], registro_xml["id"], actor["id"],
                    destinatario, responder_a, asunto,
                    registro_xml["nombre_original"], registro_xml["sha256"],
                    mensaje["Message-ID"], cfg["host"],
                ),
            )
            envio_id = cursor.lastrowid

        connection.commit()

        solicitud["destinatario"] = destinatario
        solicitud["registro_xml_id"] = registro_xml["id"]
        solicitud["adjunto_sha256"] = registro_xml["sha256"]
        return actor, solicitud, envio_id, mensaje, cfg

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def _finalizar_envio(actor, solicitud, envio_id, error, ip):
    """Fase 3. Devuelve True si el resultado quedó registrado."""
    estado = "FALLIDO" if error else "ENVIADO"
    accion = "CORREO_FALLIDO" if error else "CORREO_ENVIADO"
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE envios_correo
                SET estado = %s,
                    error_codigo = %s,
                    error_detalle = %s,
                    finalizado_en = NOW()
                WHERE id = %s AND estado = 'EN_PROCESO'
                """,
                (
                    estado,
                    error.codigo if error else None,
                    error.detalle if error else None,
                    envio_id,
                ),
            )

        registrar_evento(
            connection,
            actor["id"],
            accion,
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": solicitud["public_id"],
                "envio_correo_id": envio_id,
                "destinatario": solicitud["destinatario"],
                "registro_xml_id": solicitud["registro_xml_id"],
                "sha256": solicitud["adjunto_sha256"],
                "error_codigo": error.codigo if error else None,
            },
            ip,
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        current_app.logger.exception(
            "No se pudo registrar el resultado del envío %s", envio_id
        )
        return False

    finally:
        connection.close()


def enviar_xml_solicitud(actor_id, public_id, ip=None):
    """Devuelve un dict con: estado, destinatario, mensaje, registrado."""
    try:
        actor, solicitud, envio_id, mensaje, cfg = _preparar_envio(
            actor_id, public_id
        )
    except ErrorCorreo as exc:
        # Solo errores de configuración llegan aquí (antes de registrar).
        raise ErrorEnvioCorreo(str(exc)) from exc

    error = None

    try:
        enviar(mensaje, cfg)
    except ErrorCorreo as exc:
        error = exc
        current_app.logger.warning(
            "Envío %s fallido: %s (%s)", envio_id, exc.codigo, exc.detalle
        )

    registrado = _finalizar_envio(actor, solicitud, envio_id, error, ip)

    return {
        "envio_id": envio_id,
        "estado": "FALLIDO" if error else "ENVIADO",
        "destinatario": solicitud["destinatario"],
        "error_codigo": error.codigo if error else None,
        "mensaje": str(error) if error else None,
        "registrado": registrado,
    }


def listar_envios(solicitud_id, limite=20):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT e.id, e.destinatario, e.estado, e.error_codigo,
                       e.adjunto_nombre, e.adjunto_sha256,
                       e.creado_en, e.finalizado_en,
                       u.nombre AS enviado_por_nombre
                FROM envios_correo AS e
                LEFT JOIN usuarios AS u ON u.id = e.enviado_por
                WHERE e.solicitud_id = %s
                ORDER BY e.id DESC
                LIMIT %s
                """,
                (solicitud_id, limite),
            )
            return cursor.fetchall()

    finally:
        connection.close()
