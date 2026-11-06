from unittest.mock import Mock

import pytest
from flask import jsonify, url_for
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from app.models import User


PASSWORD_PRUEBA = "ClaveSoloParaPruebas123!"


@pytest.fixture
def cuenta_prueba(monkeypatch):
    usuario = User(
        id=50,
        rol_id=1,
        rut="12345678-5",
        nombre="Usuario QA",
        email="usuario.qa@example.com",
        telefono=None,
        password_hash=generate_password_hash(PASSWORD_PRUEBA),
        activo=1,
        ultimo_login=None,
        creado_en=None,
        role={"nombre": "Emisor"},
    )

    def buscar_por_email(cls, email):
        if (
            email.strip().lower() == usuario.email
            and usuario.is_active
        ):
            return usuario
        return None

    def buscar_por_id(cls, user_id):
        if (
            str(user_id) == str(usuario.id)
            and usuario.is_active
        ):
            return usuario
        return None

    monkeypatch.setattr(
        User,
        "get_by_email",
        classmethod(buscar_por_email),
    )
    monkeypatch.setattr(
        User,
        "get_by_id",
        classmethod(buscar_por_id),
    )

    registrar_login = Mock()
    monkeypatch.setattr(usuario, "registrar_login", registrar_login)

    return usuario, registrar_login


@pytest.fixture
def recurso_protegido(app):
    @app.get("/_qa/hu01/perfil")
    @login_required
    def qa_hu01_perfil():
        return jsonify(
            usuario_id=str(current_user.id),
            perfil=current_user.role_name,
        )

    return "/_qa/hu01/perfil"


def obtener_url(app, endpoint):
    with app.test_request_context():
        return url_for(endpoint)


def iniciar_sesion(client, app, email, password):
    return client.post(
        obtener_url(app, "auth.login"),
        data={
            "email": email,
            "password": password,
        },
        follow_redirects=False,
    )


def test_pantalla_login_disponible(app, client):
    respuesta = client.get(obtener_url(app, "auth.login"))

    assert respuesta.status_code == 200

    html = respuesta.get_data(as_text=True)
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert 'type="password"' in html


@pytest.mark.parametrize(
    "perfil",
    ["Administrador", "Emisor", "Lector"],
)
def test_credenciales_validas_inician_sesion_e_identifican_perfil(
    app,
    client,
    cuenta_prueba,
    recurso_protegido,
    perfil,
):
    usuario, registrar_login = cuenta_prueba
    usuario.role = {"nombre": perfil}

    respuesta = iniciar_sesion(
        client,
        app,
        usuario.email,
        PASSWORD_PRUEBA,
    )

    assert respuesta.status_code == 302

    with client.session_transaction() as sesion:
        assert sesion["_user_id"] == str(usuario.id)

    registrar_login.assert_called_once()

    perfil_actual = client.get(recurso_protegido)

    assert perfil_actual.status_code == 200
    assert perfil_actual.get_json() == {
        "usuario_id": str(usuario.id),
        "perfil": perfil,
    }


@pytest.mark.parametrize(
    "email, password",
    [
        ("usuario.qa@example.com", "ContraseñaIncorrecta"),
        ("no.existe@example.com", PASSWORD_PRUEBA),
        ("", ""),
        ("usuario.qa@example.com", ""),
    ],
)
def test_credenciales_invalidas_no_crean_sesion(
    app,
    client,
    cuenta_prueba,
    email,
    password,
):
    _, registrar_login = cuenta_prueba

    respuesta = iniciar_sesion(client, app, email, password)

    assert respuesta.status_code == 200
    assert (
        "El correo o la contraseña no son válidos."
        in respuesta.get_data(as_text=True)
    )

    with client.session_transaction() as sesion:
        assert "_user_id" not in sesion

    registrar_login.assert_not_called()


def test_correo_se_normaliza_antes_de_autenticar(
    app,
    client,
    cuenta_prueba,
):
    usuario, _ = cuenta_prueba

    iniciar_sesion(
        client,
        app,
        f"  {usuario.email.upper()}  ",
        PASSWORD_PRUEBA,
    )

    with client.session_transaction() as sesion:
        assert sesion["_user_id"] == str(usuario.id)


def test_cuenta_inactiva_no_inicia_sesion(
    app,
    client,
    cuenta_prueba,
):
    usuario, registrar_login = cuenta_prueba
    usuario.activo = 0

    respuesta = iniciar_sesion(
        client,
        app,
        usuario.email,
        PASSWORD_PRUEBA,
    )

    assert respuesta.status_code == 200
    assert (
        "El correo o la contraseña no son válidos."
        in respuesta.get_data(as_text=True)
    )

    with client.session_transaction() as sesion:
        assert "_user_id" not in sesion

    registrar_login.assert_not_called()


def test_cierre_sesion_impide_acceso_posterior(
    app,
    client,
    cuenta_prueba,
    recurso_protegido,
):
    usuario, _ = cuenta_prueba

    iniciar_sesion(
        client,
        app,
        usuario.email,
        PASSWORD_PRUEBA,
    )

    assert client.get(recurso_protegido).status_code == 200

    respuesta = client.post(
        obtener_url(app, "auth.logout"),
        follow_redirects=False,
    )

    assert respuesta.status_code == 302

    with client.session_transaction() as sesion:
        assert "_user_id" not in sesion

    acceso = client.get(
        recurso_protegido,
        follow_redirects=False,
    )

    assert acceso.status_code == 302

    with app.test_request_context():
        destino_login = url_for("auth.login")

    from urllib.parse import urlsplit

    assert urlsplit(acceso.headers["Location"]).path == (
        urlsplit(destino_login).path
    )


def test_logout_no_admite_get(
    app,
    client,
    cuenta_prueba,
):
    usuario, _ = cuenta_prueba

    iniciar_sesion(
        client,
        app,
        usuario.email,
        PASSWORD_PRUEBA,
    )

    respuesta = client.get(
        obtener_url(app, "auth.logout"),
        follow_redirects=False,
    )

    assert respuesta.status_code == 405

    with client.session_transaction() as sesion:
        assert sesion["_user_id"] == str(usuario.id)