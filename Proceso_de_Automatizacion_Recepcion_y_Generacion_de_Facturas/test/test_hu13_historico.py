from datetime import date
from unittest.mock import MagicMock, Mock

import pytest
from flask import url_for

from app.solicitudes import routes


def url_listado(app):
    with app.test_request_context():
        return url_for("solicitudes.listado")


@pytest.fixture
def entorno_historico(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = cursor

    # Listado como Administrador:
    # estados, responsables y resultados.
    cursor.fetchall.side_effect = [[], [], []]
    cursor.fetchone.return_value = {"total": 0}

    abrir_conexion = Mock(return_value=connection)

    monkeypatch.setattr(
        routes,
        "get_db_connection",
        abrir_conexion,
    )

    return {
        "connection": connection,
        "cursor": cursor,
        "abrir_conexion": abrir_conexion,
    }


def test_administrador_consulta_periodo_anterior(
    app,
    client,
    login_como,
    entorno_historico,
):
    login_como(rol="Administrador")

    respuesta = client.get(
        url_listado(app),
        query_string={
            "desde": "2020-01-01",
            "hasta": "2020-12-31",
        },
    )

    assert respuesta.status_code == 200

    consultas = [
        llamada
        for llamada in entorno_historico["cursor"].execute.call_args_list
        if "FROM solicitudes AS s" in llamada.args[0]
    ]

    # Conteo y recuperación de resultados.
    assert len(consultas) == 2

    for llamada in consultas:
        sql, parametros = llamada.args

        assert "s.fecha_emision >= %s" in sql
        assert "s.fecha_emision <= %s" in sql
        assert parametros[:2] == (
            date(2020, 1, 1),
            date(2020, 12, 31),
        )

    entorno_historico["connection"].close.assert_called_once()


def test_periodo_invertido_no_consulta_solicitudes(
    app,
    client,
    login_como,
    entorno_historico,
):
    login_como(rol="Administrador")

    respuesta = client.get(
        url_listado(app),
        query_string={
            "desde": "2020-12-31",
            "hasta": "2020-01-01",
        },
    )

    assert respuesta.status_code == 200

    consultas = [
        llamada
        for llamada in entorno_historico["cursor"].execute.call_args_list
        if "FROM solicitudes AS s" in llamada.args[0]
    ]

    assert consultas == []


def test_consulta_historica_no_emite_sentencias_de_escritura(
    app,
    client,
    login_como,
    entorno_historico,
):
    login_como(rol="Administrador")

    respuesta = client.get(
        url_listado(app),
        query_string={
            "desde": "2020-01-01",
            "hasta": "2020-12-31",
        },
    )

    assert respuesta.status_code == 200

    for llamada in entorno_historico["cursor"].execute.call_args_list:
        sql = llamada.args[0].lstrip().upper()
        assert sql.startswith("SELECT")

    entorno_historico["connection"].commit.assert_not_called()


def test_consulta_historica_requiere_autenticacion(
    app,
    client,
    entorno_historico,
):
    respuesta = client.get(
        url_listado(app),
        query_string={
            "desde": "2020-01-01",
            "hasta": "2020-12-31",
        },
        follow_redirects=False,
    )

    assert respuesta.status_code in (302, 401)
    entorno_historico["abrir_conexion"].assert_not_called()


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "HU13 pendiente: el decorador actual rechaza al Lector. "
        "Se requiere permiso de lectura separado y alcance definido."
    ),
)
def test_lector_puede_acceder_a_consulta_historica(
    app,
    client,
    login_como,
    entorno_historico,
):
    login_como(rol="Lector")

    # Respuestas previstas para el listado no Administrador,
    # si posteriormente se habilita su acceso.
    entorno_historico["cursor"].fetchall.side_effect = [
        [],
        [],
    ]

    respuesta = client.get(
        url_listado(app),
        query_string={
            "desde": "2020-01-01",
            "hasta": "2020-12-31",
        },
    )

    assert respuesta.status_code == 200