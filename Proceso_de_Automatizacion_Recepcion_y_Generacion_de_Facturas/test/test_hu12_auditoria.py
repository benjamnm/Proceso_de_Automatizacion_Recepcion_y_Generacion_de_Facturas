import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from flask import url_for

from app.admin import routes as admin_routes
from app.services.usuarios import registrar_evento


def url_auditoria(app):
    with app.test_request_context():
        return url_for("admin.auditoria")


@pytest.fixture
def base_auditoria(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchall.return_value = []

    monkeypatch.setattr(
        admin_routes,
        "get_db_connection",
        lambda: connection,
    )

    return connection, cursor


def evento_prueba(
    *,
    evento_id=1,
    solicitud_id=101,
    public_id="solicitud-qa-101",
):
    return {
        "id": evento_id,
        "accion": "SOLICITUD_CREADA",
        "detalle": json.dumps({
            "solicitud_afectada_id": solicitud_id,
            "public_id": public_id,
            "estado": "Pendiente",
        }),
        "ip": "127.0.0.1",
        "creado_en": datetime(2026, 11, 6, 12, 30),
        "usuario_nombre": "Administrador QA",
    }


def test_registrar_evento_envia_actor_accion_y_detalle():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value

    detalle = {
        "solicitud_afectada_id": 101,
        "estado_anterior": "Pendiente",
        "estado_nuevo": "En revisión",
    }

    registrar_evento(
        connection,
        actor_id=7,
        accion="SOLICITUD_ESTADO_CAMBIADO",
        detalle=detalle,
        ip="127.0.0.1",
    )

    cursor.execute.assert_called_once()

    sql, parametros = cursor.execute.call_args.args

    assert "INSERT INTO auditoria" in sql
    assert parametros[0] == 7
    assert parametros[1] == "SOLICITUD_ESTADO_CAMBIADO"
    assert json.loads(parametros[2]) == detalle
    assert parametros[3] == "127.0.0.1"

    # El servicio llamador controla la transacción completa.
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()


def test_administrador_consulta_evento_existente(
    app,
    client,
    login_como,
    base_auditoria,
):
    login_como(rol="Administrador")
    connection, cursor = base_auditoria
    cursor.fetchall.return_value = [evento_prueba()]

    respuesta = client.get(url_auditoria(app))

    assert respuesta.status_code == 200

    html = respuesta.get_data(as_text=True)

    assert "SOLICITUD_CREADA" in html
    assert "Administrador QA" in html
    assert "2026-11-06" in html
    assert "12:30" in html
    assert "solicitud-qa-101" in html

    connection.close.assert_called_once()


@pytest.mark.parametrize("rol", ["Emisor", "Lector"])
def test_perfil_no_administrador_no_consulta_auditoria(
    app,
    client,
    login_como,
    base_auditoria,
    rol,
):
    login_como(rol=rol)
    _, cursor = base_auditoria

    respuesta = client.get(url_auditoria(app))

    assert respuesta.status_code == 403
    cursor.execute.assert_not_called()


def test_auditoria_vacia_muestra_mensaje(
    app,
    client,
    login_como,
    base_auditoria,
):
    login_como(rol="Administrador")
    _, cursor = base_auditoria
    cursor.fetchall.return_value = []

    respuesta = client.get(url_auditoria(app))

    assert respuesta.status_code == 200
    assert "Todavía no hay eventos." in respuesta.get_data(
        as_text=True
    )


def test_consulta_incluye_eventos_de_solicitud(
    app,
    client,
    login_como,
    base_auditoria,
):
    login_como(rol="Administrador")
    _, cursor = base_auditoria

    respuesta = client.get(url_auditoria(app))

    assert respuesta.status_code == 200

    consulta = " ".join(
        llamada.args[0]
        for llamada in cursor.execute.call_args_list
    )

    assert "SOLICITUD_CREADA" in consulta
    assert "SOLICITUD_EDITADA" in consulta
    assert "SOLICITUD_ESTADO_CAMBIADO" in consulta


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HU12.2 pendiente: la ruta actual no aplica un filtro "
        "parametrizado por solicitud."
    ),
)
def test_consulta_aplica_filtro_parametrizado_por_solicitud(
    app,
    client,
    login_como,
    base_auditoria,
):
    login_como(rol="Administrador")
    _, cursor = base_auditoria

    respuesta = client.get(
        url_auditoria(app),
        query_string={"solicitud_id": "101"},
    )

    assert respuesta.status_code == 200

    consultas_filtradas = [
        llamada
        for llamada in cursor.execute.call_args_list
        if len(llamada.args) > 1
        and llamada.args[1]
        and any(
            str(valor) == "101"
            for valor in llamada.args[1]
        )
        and "solicitud_afectada_id" in llamada.args[0]
    ]

    assert consultas_filtradas, (
        "La consulta debe aplicar el identificador de solicitud "
        "como parámetro de la búsqueda, no ignorarlo."
    )