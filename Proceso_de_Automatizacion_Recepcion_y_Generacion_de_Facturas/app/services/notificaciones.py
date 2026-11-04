"""Aviso al Administrador: "la factura vN está lista para validar".

Mismo esquema de tres fases que correos_solicitud (sin bloqueos de BD
durante SMTP). Cada aviso queda en envios_correo (tipo
NOTIFICACION_ADMIN) y en auditoria. Nunca lanza excepciones: la factura
ya está guardada y un fallo de correo no debe deshacerla.
"""
import json

from flask import current_app, render_template

from ..models import get_db_connection
from .correo import ErrorCorreo, construir_mensaje, enviar, limpiar_cabecera, validar_configuracion
from .usuarios import registrar_evento
from .validaciones import ErrorValidacion, normalizar_correo

# Cabecera propia: la bandeja IMAP ignora estos correos (evita bucles
# si el Administrador usa la misma casilla).
CABECERA_ORIGEN = "X-Facturaciones-Origen"
VALOR_ORIGEN = "notificacion"


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


def componer(solicitud, factura, correo_entrante, base_url):
    datos = factura["datos"]
    if isinstance(datos, str):
        datos = json.loads(datos)

    observaciones = (correo_entrante or {}).get("observaciones") or {}
    if isinstance(observaciones, str):
        observaciones = json.loads(observaciones)

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
        enlace=f"{base_url.rstrip('/')}/solicitudes/{solicitud['public_id']}/factura",
    )
    return asunto, cuerpo


def _preparar(actor_id, solicitud_id, cfg):
    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, public_id, nombre FROM solicitudes WHERE id = %s",
                (solicitud_id,),
            )
            solicitud = cursor.fetchone()

            cursor.execute(
                """
                SELECT id, version, datos, cambios
                FROM facturas
                WHERE solicitud_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (solicitud_id,),
            )
            factura = cursor.fetchone()

            if solicitud is None or factura is None:
                connection.rollback()
                return None, []

            cursor.execute(
                """
                SELECT remitente, asunto, observaciones
                FROM correos_entrantes
                WHERE solicitud_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (solicitud_id,),
            )
            correo_entrante = cursor.fetchone()

            asunto, cuerpo = componer(
                solicitud, factura, correo_entrante,
                current_app.config["APP_BASE_URL"],
            )

            pendientes = []
            for destinatario in destinatarios(cursor, current_app.config):
                mensaje = construir_mensaje(
                    remitente=cfg["remitente"],
                    remitente_correo=cfg["remitente_correo"],
                    destinatario=destinatario,
                    asunto=asunto,
                    cuerpo=cuerpo,
                    cabeceras_extra={CABECERA_ORIGEN: VALOR_ORIGEN},
                )
                cursor.execute(
                    """
                    INSERT INTO envios_correo (
                        solicitud_id, registro_xml_id, tipo, enviado_por,
                        destinatario, asunto, message_id, smtp_host, estado
                    )
                    VALUES (%s, NULL, 'NOTIFICACION_ADMIN', %s, %s, %s, %s,
                            %s, 'EN_PROCESO')
                    """,
                    (
                        solicitud_id, actor_id, destinatario, asunto,
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


def _finalizar(actor_id, solicitud, envio_id, destinatario, error, ip):
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


def notificar_factura_generada(actor_id, solicitud_id, ip=None):
    """Devuelve {"enviados": n, "fallidos": n, "error": str|None}."""
    resultado = {"enviados": 0, "fallidos": 0, "error": None}

    try:
        cfg = validar_configuracion()
        solicitud, pendientes = _preparar(actor_id, solicitud_id, cfg)
    except ErrorCorreo as exc:
        current_app.logger.warning("Aviso no enviado: %s", exc)
        resultado["error"] = str(exc)
        return resultado
    except Exception:
        current_app.logger.exception("No se pudo preparar el aviso al Administrador")
        resultado["error"] = "No se pudo preparar el aviso."
        return resultado

    if solicitud is not None and not pendientes:
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
        _finalizar(actor_id, solicitud, envio_id, destinatario, error, ip)
        resultado["fallidos" if error else "enviados"] += 1

    return resultado
