import smtplib
import ssl

import pytest

from app.services import correo
from app.services.correo import (
    ErrorCorreo,
    construir_mensaje,
    enviar,
    validar_configuracion,
)

CONFIG_BASE = {
    "SMTP_HOST": "smtp.ejemplo.cl",
    "SMTP_PORT": 587,
    "SMTP_SECURITY": "starttls",
    "SMTP_USER": "usuario",
    "SMTP_PASSWORD": "secreta",
    "SMTP_FROM": "Facturaciones SpA <no-responder@facturaciones.cl>",
    "SMTP_TIMEOUT": 5,
}


def cfg(**cambios):
    datos = dict(CONFIG_BASE)
    datos.update(cambios)
    return validar_configuracion(datos)


def mensaje_prueba(**cambios):
    datos = {
        "remitente": CONFIG_BASE["SMTP_FROM"],
        "remitente_correo": "no-responder@facturaciones.cl",
        "destinatario": "cliente@ejemplo.com",
        "asunto": "Documento XML",
        "cuerpo": "Hola",
    }
    datos.update(cambios)
    return construir_mensaje(**datos)


# --- Configuración ---------------------------------------------------

def test_configuracion_valida():
    resultado = cfg()
    assert resultado["host"] == "smtp.ejemplo.cl"
    assert resultado["remitente_correo"] == "no-responder@facturaciones.cl"


@pytest.mark.parametrize("cambios", [
    {"SMTP_HOST": ""},
    {"SMTP_FROM": ""},
    {"SMTP_FROM": "sin-arroba"},
    {"SMTP_SECURITY": "tls"},
    {"SMTP_PORT": "abc"},
    {"SMTP_PORT": 70000},
    # Sin cifrado solo se permite contra un servidor local.
    {"SMTP_SECURITY": "none"},
])
def test_configuracion_invalida(cambios):
    with pytest.raises(ErrorCorreo) as exc:
        cfg(**cambios)
    assert exc.value.codigo == "CONFIGURACION"


def test_sin_cifrado_permitido_en_localhost():
    assert cfg(SMTP_HOST="localhost", SMTP_SECURITY="none",
               SMTP_PORT=1025)["seguridad"] == "none"


# --- Mensaje -----------------------------------------------------------

def test_mensaje_con_adjunto_xml():
    m = mensaje_prueba(responder_a="emisor@facturaciones.cl",
                       adjunto=("factura.xml", b"<DTE/>"))
    assert m["To"] == "cliente@ejemplo.com"
    assert m["Reply-To"] == "emisor@facturaciones.cl"
    assert m["Message-ID"].endswith("@facturaciones.cl>")
    adjuntos = list(m.iter_attachments())
    assert len(adjuntos) == 1
    assert adjuntos[0].get_content_type() == "application/xml"
    assert adjuntos[0].get_filename() == "factura.xml"
    assert adjuntos[0].get_content() == b"<DTE/>"


def test_mensaje_bloquea_inyeccion_de_cabeceras():
    m = mensaje_prueba(asunto="Hola\r\nBcc: victima@ejemplo.com")
    assert "\n" not in m["Subject"]
    assert m["Bcc"] is None
    assert b"\nBcc:" not in m.as_bytes()


# --- Transporte (servidor SMTP simulado) -------------------------------

class SMTPFalso:
    instancias = []
    error_en = None          # nombre del método que debe fallar
    error = None
    rechazados = {}

    def __init__(self, host, puerto, timeout=None, context=None):
        self.host, self.puerto, self.context = host, puerto, context
        self.llamadas = []
        SMTPFalso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _registrar(self, nombre):
        self.llamadas.append(nombre)
        if SMTPFalso.error_en == nombre:
            raise SMTPFalso.error

    def ehlo(self):
        self._registrar("ehlo")

    def starttls(self, context=None):
        self._registrar("starttls")

    def login(self, usuario, password):
        self._registrar("login")

    def send_message(self, mensaje):
        self._registrar("send_message")
        return SMTPFalso.rechazados


@pytest.fixture
def smtp_falso(monkeypatch):
    SMTPFalso.instancias = []
    SMTPFalso.error_en = None
    SMTPFalso.error = None
    SMTPFalso.rechazados = {}
    monkeypatch.setattr(correo.smtplib, "SMTP", SMTPFalso)
    monkeypatch.setattr(correo.smtplib, "SMTP_SSL", SMTPFalso)
    return SMTPFalso


def test_envio_starttls_con_login(smtp_falso):
    m = mensaje_prueba()
    assert enviar(m, cfg()) == m["Message-ID"]
    assert smtp_falso.instancias[0].llamadas == [
        "ehlo", "starttls", "ehlo", "login", "send_message",
    ]


def test_envio_ssl_usa_contexto_verificado(smtp_falso):
    enviar(mensaje_prueba(), cfg(SMTP_SECURITY="ssl", SMTP_PORT=465))
    contexto = smtp_falso.instancias[0].context
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True
    assert "starttls" not in smtp_falso.instancias[0].llamadas


def test_envio_local_sin_login(smtp_falso):
    enviar(mensaje_prueba(), cfg(SMTP_HOST="localhost", SMTP_PORT=1025,
                                 SMTP_SECURITY="none", SMTP_USER=""))
    assert smtp_falso.instancias[0].llamadas == ["ehlo", "send_message"]


@pytest.mark.parametrize("metodo, error, codigo", [
    ("login", smtplib.SMTPAuthenticationError(535, b"Bad credentials"),
     "AUTENTICACION"),
    ("starttls", smtplib.SMTPNotSupportedError("STARTTLS no soportado"),
     "TLS_NO_DISPONIBLE"),
    ("starttls", ssl.SSLError("certificado inválido"), "TLS"),
    ("send_message",
     smtplib.SMTPRecipientsRefused({"x@y.cl": (550, b"No such user")}),
     "DESTINATARIO_RECHAZADO"),
    ("send_message",
     smtplib.SMTPSenderRefused(553, b"Sender not allowed", "a@b.cl"),
     "REMITENTE_RECHAZADO"),
    ("ehlo", smtplib.SMTPServerDisconnected("cerrado"), "CONEXION"),
    ("ehlo", ConnectionRefusedError("rechazada"), "CONEXION"),
    ("ehlo", TimeoutError("timeout"), "CONEXION"),
    ("send_message", smtplib.SMTPDataError(554, b"Rejected"), "SMTP"),
])
def test_errores_se_traducen(smtp_falso, metodo, error, codigo):
    smtp_falso.error_en = metodo
    smtp_falso.error = error
    with pytest.raises(ErrorCorreo) as exc:
        enviar(mensaje_prueba(), cfg())
    assert exc.value.codigo == codigo
    assert "secreta" not in exc.value.detalle


def test_no_degrada_a_texto_plano_si_falta_starttls(smtp_falso):
    smtp_falso.error_en = "starttls"
    smtp_falso.error = smtplib.SMTPNotSupportedError("sin STARTTLS")
    with pytest.raises(ErrorCorreo):
        enviar(mensaje_prueba(), cfg())
    assert "send_message" not in smtp_falso.instancias[0].llamadas


def test_destinatario_rechazado_parcial(smtp_falso):
    smtp_falso.rechazados = {"cliente@ejemplo.com": (550, b"No")}
    with pytest.raises(ErrorCorreo) as exc:
        enviar(mensaje_prueba(), cfg())
    assert exc.value.codigo == "DESTINATARIO_RECHAZADO"
