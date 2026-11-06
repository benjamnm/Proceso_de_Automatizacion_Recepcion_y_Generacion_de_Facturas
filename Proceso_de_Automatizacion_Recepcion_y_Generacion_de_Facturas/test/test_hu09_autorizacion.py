from urllib.parse import urlsplit

import pytest
from flask import url_for

from app.security import admin_required, solicitud_required


@pytest.fixture
def rutas_de_prueba(app):
    @app.get("/_qa/administracion")
    @admin_required
    def qa_administracion():
        return "Administración autorizada", 200

    @app.get("/_qa/operacion_solicitud")
    @solicitud_required
    def qa_operacion_solicitud():
        return "Operación autorizada", 200


def test_administrador_accede_a_funcion_administrativa(
    rutas_de_prueba,
    client,
    login_como,
):
    login_como(rol="Administrador")

    respuesta = client.get("/_qa/administracion")

    assert respuesta.status_code == 200


@pytest.mark.parametrize("rol", ["Emisor", "Lector"])
def test_perfiles_no_administrativos_reciben_403(
    rutas_de_prueba,
    client,
    login_como,
    rol,
):
    login_como(rol=rol)

    respuesta = client.get("/_qa/administracion")

    assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ["Administrador", "Emisor"])
def test_perfiles_actuales_autorizados_en_solicitud(
    rutas_de_prueba,
    client,
    login_como,
    rol,
):
    login_como(rol=rol)

    respuesta = client.get("/_qa/operacion_solicitud")

    assert respuesta.status_code == 200


def test_lector_no_recibe_permiso_general_de_solicitudes(
    rutas_de_prueba,
    client,
    login_como,
):
    login_como(rol="Lector")

    respuesta = client.get("/_qa/operacion_solicitud")

    assert respuesta.status_code == 403


@pytest.mark.parametrize(
    "ruta",
    [
        "/_qa/administracion",
        "/_qa/operacion_solicitud",
    ],
)
def test_usuario_no_autenticado_no_accede(
    rutas_de_prueba,
    client,
    ruta,
):
    respuesta = client.get(ruta, follow_redirects=False)

    assert respuesta.status_code in {302, 401}


@pytest.mark.parametrize(
    "ruta",
    [
        "/_qa/administracion",
        "/_qa/operacion_solicitud",
    ],
)
def test_usuario_inactivo_no_accede(
    rutas_de_prueba,
    app,
    client,
    login_como,
    ruta,
):
    usuario = login_como(rol="Administrador")
    usuario.activo = 0

    assert not usuario.is_active

    respuesta = client.get(ruta, follow_redirects=False)

    assert respuesta.status_code == 302

    destino = respuesta.headers.get("Location")
    assert destino, "Debe existir un destino de redirección."

    endpoint_login = app.login_manager.login_view
    assert endpoint_login, "Debe existir un login configurado."

    with app.test_request_context():
        url_login = url_for(endpoint_login)

    assert urlsplit(destino).path == urlsplit(url_login).path

    contenido = respuesta.get_data(as_text=True)
    assert "Administración autorizada" not in contenido
    assert "Operación autorizada" not in contenido