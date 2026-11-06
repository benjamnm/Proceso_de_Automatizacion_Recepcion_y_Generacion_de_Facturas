from unittest.mock import MagicMock, Mock

import pytest
from flask import url_for
from werkzeug.security import check_password_hash

from app.admin import routes


def url_usuarios(app):
    with app.test_request_context():
        return url_for("admin.usuarios")


def inserciones_usuario(cursor):
    return [
        llamada
        for llamada in cursor.execute.call_args_list
        if "INSERT INTO usuarios" in llamada.args[0]
    ]


@pytest.fixture
def datos_usuario():
    return {
        "nombre": "Emisor QA",
        "email": "emisor.qa@example.com",
        "rol_id": "20",
        "password": "ClaveInicial-QA-2026",
        "password_confirm": "ClaveInicial-QA-2026",
    }


@pytest.fixture
def entorno_usuarios(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = cursor

    roles = [
        {"id": 10, "nombre": "Administrador"},
        {"id": 20, "nombre": "Emisor"},
        {"id": 30, "nombre": "Lector"},
    ]

    usuarios = [
        {
            "id": 50,
            "nombre": "Emisor registrado QA",
            "email": "registrado.qa@example.com",
            "activo": 1,
            "rol_nombre": "Emisor",
        }
    ]

    # Primer fetchall: roles. Segundo: listado de usuarios.
    cursor.fetchall.side_effect = [roles, usuarios]
    cursor.fetchone.return_value = None
    cursor.lastrowid = 51

    abrir_conexion = Mock(return_value=connection)
    auditoria = Mock()

    monkeypatch.setattr(
        routes,
        "get_db_connection",
        abrir_conexion,
    )
    monkeypatch.setattr(
        routes,
        "registrar_evento",
        auditoria,
    )

    return {
        "connection": connection,
        "cursor": cursor,
        "abrir_conexion": abrir_conexion,
        "auditoria": auditoria,
    }


@pytest.mark.parametrize("rol", ["Emisor", "Lector"])
@pytest.mark.parametrize("metodo", ["GET", "POST"])
def test_solo_administrador_accede_a_gestion(
    app,
    client,
    login_como,
    entorno_usuarios,
    datos_usuario,
    rol,
    metodo,
):
    login_como(rol=rol)

    respuesta = client.open(
        url_usuarios(app),
        method=metodo,
        data=datos_usuario if metodo == "POST" else None,
    )

    assert respuesta.status_code == 403
    entorno_usuarios["abrir_conexion"].assert_not_called()


def test_administrador_consulta_emisores_registrados(
    app,
    client,
    login_como,
    entorno_usuarios,
):
    login_como(rol="Administrador")

    respuesta = client.get(url_usuarios(app))

    assert respuesta.status_code == 200

    html = respuesta.get_data(as_text=True)

    assert "Gestión de usuarios" in html
    assert "Emisor registrado QA" in html
    assert "registrado.qa@example.com" in html
    assert "Emisor" in html
    assert 'name="nombre"' in html
    assert 'name="email"' in html
    assert 'name="rol_id"' in html
    assert 'name="password"' in html
    assert 'name="password_confirm"' in html

    entorno_usuarios["connection"].close.assert_called_once()


def test_administrador_crea_usuario_con_perfil_emisor(
    app,
    client,
    login_como,
    entorno_usuarios,
    datos_usuario,
):
    login_como(rol="Administrador")

    respuesta = client.post(
        url_usuarios(app),
        data=datos_usuario,
        follow_redirects=False,
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(
        url_usuarios(app)
    )

    inserciones = inserciones_usuario(
        entorno_usuarios["cursor"]
    )

    assert len(inserciones) == 1

    _, parametros = inserciones[0].args

    rol_id, nombre, email, password_hash, activo = parametros

    assert rol_id == 20
    assert nombre == "Emisor QA"
    assert email == "emisor.qa@example.com"
    assert activo == 1

    assert password_hash != datos_usuario["password"]
    assert check_password_hash(
        password_hash,
        datos_usuario["password"],
    )

    entorno_usuarios["connection"].commit.assert_called_once()
    entorno_usuarios["connection"].rollback.assert_not_called()
    entorno_usuarios["connection"].close.assert_called_once()


def test_creacion_registra_auditoria_sin_contrasena(
    app,
    client,
    login_como,
    entorno_usuarios,
    datos_usuario,
):
    actor = login_como(rol="Administrador")

    respuesta = client.post(
        url_usuarios(app),
        data=datos_usuario,
    )

    assert respuesta.status_code == 302

    auditoria = entorno_usuarios["auditoria"]
    auditoria.assert_called_once()

    argumentos = auditoria.call_args.args

    assert argumentos[0] is entorno_usuarios["connection"]
    assert argumentos[1] == int(actor.id)
    assert argumentos[2] == "USUARIO_CREADO"

    detalle = argumentos[3]

    assert detalle == {
        "usuario_afectado_id": 51,
        "datos_iniciales": {
            "nombre": "Emisor QA",
            "email": "emisor.qa@example.com",
            "rol_id": 20,
            "activo": 1,
        },
    }

    assert datos_usuario["password"] not in str(detalle)
    assert "password_hash" not in str(detalle)


@pytest.mark.parametrize(
    "campo, valor, mensaje",
    [
        (
            "nombre",
            " ",
            "El nombre debe tener entre 2 y 120 caracteres.",
        ),
        (
            "email",
            "correo-invalido",
            "Ingrese un correo electrónico válido.",
        ),
        (
            "rol_id",
            "999",
            "Seleccione un rol válido.",
        ),
        (
            "password",
            "corta",
            "La contraseña debe tener entre 12 y 128 caracteres.",
        ),
        (
            "password_confirm",
            "OtraClave-QA-2026",
            "Las contraseñas no coinciden.",
        ),
    ],
)
def test_rechaza_datos_invalidos_sin_crear_usuario(
    app,
    client,
    login_como,
    entorno_usuarios,
    datos_usuario,
    campo,
    valor,
    mensaje,
):
    login_como(rol="Administrador")
    datos_usuario[campo] = valor

    respuesta = client.post(
        url_usuarios(app),
        data=datos_usuario,
    )

    assert respuesta.status_code == 200
    assert mensaje in respuesta.get_data(as_text=True)

    assert inserciones_usuario(
        entorno_usuarios["cursor"]
    ) == []

    entorno_usuarios["connection"].commit.assert_not_called()
    entorno_usuarios["auditoria"].assert_not_called()


def test_rechaza_correo_ya_registrado(
    app,
    client,
    login_como,
    entorno_usuarios,
    datos_usuario,
):
    login_como(rol="Administrador")

    entorno_usuarios["cursor"].fetchone.return_value = {
        "id": 80
    }

    respuesta = client.post(
        url_usuarios(app),
        data=datos_usuario,
    )

    assert respuesta.status_code == 200

    assert (
        "Ya existe un usuario con ese correo."
        in respuesta.get_data(as_text=True)
    )

    assert inserciones_usuario(
        entorno_usuarios["cursor"]
    ) == []

    entorno_usuarios["connection"].commit.assert_not_called()
    entorno_usuarios["auditoria"].assert_not_called()