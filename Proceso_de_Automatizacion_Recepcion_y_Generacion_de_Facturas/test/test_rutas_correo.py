import pytest

from app.services.correos_solicitud import ErrorEnvioCorreo

PUBLIC_ID = "a" * 32
URL = f"/solicitudes/{PUBLIC_ID}/correo"


def mensajes(client):
    with client.session_transaction() as sesion:
        return [(c, m) for c, m in sesion.get("_flashes", [])]


@pytest.fixture
def servicio(monkeypatch):
    llamadas = []

    def falso(resultado=None, error=None):
        def _enviar(**kwargs):
            llamadas.append(kwargs)
            if error:
                raise error
            return resultado

        monkeypatch.setattr(
            "app.solicitudes.routes.enviar_xml_solicitud", _enviar
        )
        return llamadas

    return falso


def test_anonimo_redirige_al_login(client):
    respuesta = client.post(URL)
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_lector_no_puede_enviar(client, login_como, servicio):
    llamadas = servicio(resultado={})
    login_como("Lector")
    assert client.post(URL).status_code == 403
    assert llamadas == []


def test_get_no_permitido(client, login_como):
    login_como("Emisor")
    assert client.get(URL).status_code == 405


def test_envio_exitoso(client, login_como, servicio):
    llamadas = servicio(resultado={
        "estado": "ENVIADO", "destinatario": "c@ejemplo.com",
        "mensaje": None, "registrado": True,
    })
    login_como("Emisor", user_id=7)

    respuesta = client.post(URL)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/solicitudes/{PUBLIC_ID}")
    assert llamadas[0]["actor_id"] == 7
    assert llamadas[0]["public_id"] == PUBLIC_ID
    assert ("success", "XML enviado a c@ejemplo.com.") in mensajes(client)


def test_envio_fallido_informa(client, login_como, servicio):
    servicio(resultado={
        "estado": "FALLIDO", "destinatario": "c@ejemplo.com",
        "mensaje": "El servidor SMTP rechazó las credenciales.",
        "registrado": True,
    })
    login_como("Administrador")
    client.post(URL)
    categoria, texto = mensajes(client)[0]
    assert categoria == "danger"
    assert "credenciales" in texto


def test_resultado_no_registrado_advierte(client, login_como, servicio):
    servicio(resultado={
        "estado": "ENVIADO", "destinatario": "c@ejemplo.com",
        "mensaje": None, "registrado": False,
    })
    login_como("Administrador")
    client.post(URL)
    assert any(c == "warning" for c, _ in mensajes(client))


def test_error_de_validacion(client, login_como, servicio):
    servicio(error=ErrorEnvioCorreo("Debe cargar el XML antes de enviarlo."))
    login_como("Emisor")
    client.post(URL)
    assert ("danger", "Debe cargar el XML antes de enviarlo.") in mensajes(client)


def test_comando_smtp_prueba(app, monkeypatch):
    enviados = []
    app.config.update(
        SMTP_HOST="localhost", SMTP_PORT=1025, SMTP_SECURITY="none",
        SMTP_FROM="Facturaciones SpA <no-responder@facturaciones.cl>",
    )
    monkeypatch.setattr(
        "app.cli.enviar",
        lambda mensaje, cfg: enviados.append(mensaje) or mensaje["Message-ID"],
    )

    resultado = app.test_cli_runner().invoke(
        args=["smtp-prueba", "yo@ejemplo.com"]
    )

    assert resultado.exit_code == 0, resultado.output
    assert "Correo enviado a yo@ejemplo.com" in resultado.output
    assert enviados[0]["To"] == "yo@ejemplo.com"
