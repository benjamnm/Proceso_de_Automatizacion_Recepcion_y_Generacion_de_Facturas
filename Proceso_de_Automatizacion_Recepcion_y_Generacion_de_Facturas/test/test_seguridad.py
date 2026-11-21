import time
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.models import User
from app.security import CLAVE_ACTIVIDAD
from config import TestingConfig
from conftest import usuario_falso

PLANTILLAS = Path(__file__).resolve().parents[1] / "app" / "templates"


def _usuario_con_clave(clave):
    usuario = usuario_falso()
    usuario.password_hash = generate_password_hash(clave)
    usuario.registrar_login = lambda: None
    return usuario


def _login(client, password, email="admin@test.cl"):
    return client.post(
        "/auth/login", data={"email": email, "password": password}
    )


def test_cabeceras_de_seguridad(client):
    respuesta = client.get("/auth/login")
    cabeceras = respuesta.headers

    assert "frame-ancestors 'none'" in cabeceras["Content-Security-Policy"]
    assert "'unsafe-inline'" not in cabeceras["Content-Security-Policy"]
    assert cabeceras["X-Content-Type-Options"] == "nosniff"
    assert cabeceras["X-Frame-Options"] == "DENY"
    assert cabeceras["Cache-Control"] == "no-store"


def test_estaticos_pueden_cachearse(client):
    respuesta = client.get("/static/js/app.js")
    assert respuesta.status_code == 200
    assert respuesta.headers.get("Cache-Control") != "no-store"
    respuesta.close()


def test_create_app_rechaza_secret_key_corta():
    class ClaveCorta(TestingConfig):
        SECRET_KEY = "corta"

    with pytest.raises(RuntimeError, match="demasiado corta"):
        create_app(ClaveCorta)


def test_login_fallido_usa_mensaje_generico(client, monkeypatch):
    monkeypatch.setattr(User, "get_by_email", classmethod(lambda cls, e: None))

    respuesta = _login(client, "cualquier-clave")

    assert respuesta.status_code == 401
    assert "El correo o la contraseña no son válidos." in respuesta.get_data(as_text=True)


def test_login_se_bloquea_tras_intentos_fallidos(client, app, monkeypatch):
    usuario = _usuario_con_clave("clave-correcta-123")
    monkeypatch.setattr(User, "get_by_email", classmethod(lambda cls, e: usuario))

    for _ in range(app.config["LOGIN_MAX_INTENTOS"]):
        assert _login(client, "clave-erronea").status_code == 401

    bloqueado = _login(client, "clave-correcta-123")

    assert bloqueado.status_code == 429
    assert "Demasiados intentos" in bloqueado.get_data(as_text=True)


def test_login_correcto_regenera_la_sesion(client, monkeypatch):
    usuario = _usuario_con_clave("clave-correcta-123")
    monkeypatch.setattr(User, "get_by_email", classmethod(lambda cls, e: usuario))

    with client.session_transaction() as sesion:
        sesion["dato_previo"] = "inyectado"

    respuesta = _login(client, "clave-correcta-123")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as sesion:
        assert "dato_previo" not in sesion
        assert sesion["_user_id"] == "1"


def test_password_demasiado_larga_no_se_evalua(client, monkeypatch):
    def no_debe_consultarse(cls, email):
        raise AssertionError("No debe consultar la BD")

    monkeypatch.setattr(User, "get_by_email", classmethod(no_debe_consultarse))
    assert _login(client, "x" * 129).status_code == 401


def test_sesion_expira_por_inactividad(client, app, login_como):
    login_como("Administrador")
    limite = int(app.config["SESSION_INACTIVIDAD"].total_seconds())
    with client.session_transaction() as sesion:
        sesion[CLAVE_ACTIVIDAD] = int(time.time()) - limite - 5

    respuesta = client.get("/solicitudes/")

    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]
    with client.session_transaction() as sesion:
        assert "_user_id" not in sesion


def test_formulario_sin_csrf_muestra_error_amigable(tmp_path):
    class ConCsrf(TestingConfig):
        WTF_CSRF_ENABLED = True

    cliente = create_app(ConCsrf).test_client()
    respuesta = cliente.post("/auth/login", data={"email": "a@b.cl"})

    assert respuesta.status_code == 400
    assert "El formulario venció" in respuesta.get_data(as_text=True)


def test_plantillas_sin_javascript_ni_estilos_en_linea():
    for plantilla in PLANTILLAS.rglob("*.html"):
        contenido = plantilla.read_text(encoding="utf-8")
        for patron in ("onsubmit=", "onclick=", "style=", "<script>"):
            assert patron not in contenido, f"{patron} en {plantilla.name}"
