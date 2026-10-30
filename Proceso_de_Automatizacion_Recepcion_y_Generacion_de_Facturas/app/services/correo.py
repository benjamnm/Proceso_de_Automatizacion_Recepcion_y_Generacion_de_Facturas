"""Transporte SMTP seguro.

Reglas:
- Cifrado obligatorio (STARTTLS o SSL) salvo en un servidor local de
  pruebas (localhost), por ejemplo Mailpit.
- Si el servidor no ofrece STARTTLS, se aborta: nunca se degrada a texto
  plano.
- Los errores se traducen a códigos estables para la auditoría y nunca
  incluyen credenciales.
"""
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from flask import current_app

from .validaciones import ErrorValidacion, normalizar_correo

MODOS_SEGURIDAD = {"starttls", "ssl", "none"}
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}
LIMITE_ASUNTO = 200
LIMITE_DETALLE = 500


class ErrorCorreo(Exception):
    def __init__(self, codigo, mensaje, detalle=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.detalle = (detalle or mensaje)[:LIMITE_DETALLE]


def limpiar_cabecera(valor, limite):
    """Elimina saltos de línea y espacios repetidos (evita inyección)."""
    texto = re.sub(r"\s+", " ", str(valor or "")).strip()
    return texto[:limite]


def validar_configuracion(config=None):
    config = config if config is not None else current_app.config

    host = str(config.get("SMTP_HOST") or "").strip()
    remitente = str(config.get("SMTP_FROM") or "").strip()
    seguridad = str(config.get("SMTP_SECURITY") or "").strip().lower()

    if not host or not remitente:
        raise ErrorCorreo(
            "CONFIGURACION",
            "El envío de correos no está configurado (SMTP_HOST y SMTP_FROM).",
        )

    if seguridad not in MODOS_SEGURIDAD:
        raise ErrorCorreo(
            "CONFIGURACION",
            "SMTP_SECURITY debe ser starttls, ssl o none.",
        )

    if seguridad == "none" and host.lower() not in HOSTS_LOCALES:
        raise ErrorCorreo(
            "CONFIGURACION",
            "SMTP_SECURITY=none solo se permite con un servidor local.",
        )

    try:
        puerto = int(config.get("SMTP_PORT") or 0)
    except (TypeError, ValueError):
        puerto = 0

    if not 1 <= puerto <= 65535:
        raise ErrorCorreo("CONFIGURACION", "SMTP_PORT no es válido.")

    nombre, direccion = parseaddr(remitente)

    try:
        direccion = normalizar_correo(direccion)
    except ErrorValidacion as exc:
        raise ErrorCorreo(
            "CONFIGURACION", "SMTP_FROM no contiene un correo válido."
        ) from exc

    return {
        "host": host,
        "puerto": puerto,
        "seguridad": seguridad,
        "usuario": str(config.get("SMTP_USER") or ""),
        "password": str(config.get("SMTP_PASSWORD") or ""),
        "remitente": remitente,
        "remitente_correo": direccion,
        "remitente_nombre": nombre,
        "timeout": int(config.get("SMTP_TIMEOUT") or 20),
    }


def construir_mensaje(
    *,
    remitente,
    remitente_correo,
    destinatario,
    asunto,
    cuerpo,
    responder_a=None,
    adjunto=None,
):
    """adjunto: tupla (nombre_archivo, contenido_bytes) de un XML."""
    mensaje = EmailMessage()
    mensaje["From"] = limpiar_cabecera(remitente, 300)
    mensaje["To"] = limpiar_cabecera(destinatario, 150)
    mensaje["Subject"] = limpiar_cabecera(asunto, LIMITE_ASUNTO)
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid(
        domain=remitente_correo.rsplit("@", 1)[-1]
    )

    if responder_a:
        mensaje["Reply-To"] = limpiar_cabecera(responder_a, 150)

    mensaje.set_content(cuerpo)

    if adjunto is not None:
        nombre, contenido = adjunto
        mensaje.add_attachment(
            contenido,
            maintype="application",
            subtype="xml",
            filename=limpiar_cabecera(nombre, 255),
        )

    return mensaje


def _detalle(exc):
    codigo = getattr(exc, "smtp_code", None)
    respuesta = getattr(exc, "smtp_error", b"")

    if isinstance(respuesta, bytes):
        respuesta = respuesta.decode("utf-8", "replace")

    texto = f"{type(exc).__name__}"
    if codigo:
        texto += f" {codigo}"
    if respuesta:
        texto += f": {limpiar_cabecera(respuesta, 300)}"

    return texto


def enviar(mensaje, cfg):
    """Envía el mensaje. Devuelve el Message-ID o lanza ErrorCorreo."""
    contexto = ssl.create_default_context()

    try:
        if cfg["seguridad"] == "ssl":
            servidor = smtplib.SMTP_SSL(
                cfg["host"], cfg["puerto"],
                timeout=cfg["timeout"], context=contexto,
            )
        else:
            servidor = smtplib.SMTP(
                cfg["host"], cfg["puerto"], timeout=cfg["timeout"],
            )

        with servidor:
            servidor.ehlo()

            if cfg["seguridad"] == "starttls":
                servidor.starttls(context=contexto)
                servidor.ehlo()

            if cfg["usuario"]:
                servidor.login(cfg["usuario"], cfg["password"])

            rechazados = servidor.send_message(mensaje)

        if rechazados:
            raise ErrorCorreo(
                "DESTINATARIO_RECHAZADO",
                "El servidor rechazó el destinatario.",
                f"Rechazados: {', '.join(rechazados)}",
            )

        return mensaje["Message-ID"]

    except ErrorCorreo:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise ErrorCorreo(
            "AUTENTICACION",
            "El servidor SMTP rechazó las credenciales.",
            _detalle(exc),
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise ErrorCorreo(
            "DESTINATARIO_RECHAZADO",
            "El servidor rechazó el destinatario.",
            _detalle(exc),
        ) from exc
    except smtplib.SMTPSenderRefused as exc:
        raise ErrorCorreo(
            "REMITENTE_RECHAZADO",
            "El servidor rechazó el remitente configurado.",
            _detalle(exc),
        ) from exc
    except smtplib.SMTPNotSupportedError as exc:
        raise ErrorCorreo(
            "TLS_NO_DISPONIBLE",
            "El servidor no ofrece una conexión cifrada (STARTTLS).",
            _detalle(exc),
        ) from exc
    except (smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError) as exc:
        raise ErrorCorreo(
            "CONEXION",
            "Se perdió la conexión con el servidor SMTP.",
            _detalle(exc),
        ) from exc
    except smtplib.SMTPException as exc:
        raise ErrorCorreo(
            "SMTP",
            "El servidor SMTP devolvió un error.",
            _detalle(exc),
        ) from exc
    except ssl.SSLError as exc:
        raise ErrorCorreo(
            "TLS",
            "No se pudo establecer una conexión cifrada segura.",
            _detalle(exc),
        ) from exc
    except OSError as exc:
        raise ErrorCorreo(
            "CONEXION",
            "No se pudo conectar con el servidor SMTP.",
            _detalle(exc),
        ) from exc
