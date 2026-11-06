from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest
from flask import url_for

from app.services import solicitudes as servicio
from app.solicitudes import routes


@pytest.fixture
def datos_edicion():
    return {
        "cliente_id": "15",
        "concepto": "Concepto corregido",
        "nro_orden_compra": "OC-100",
        "fecha_emision": "2026-11-05",
        "monto_bruto": "150000",
        "tipo_afectacion": "AFECTA",
    }


@pytest.fixture
def entorno_edicion(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.rowcount = 1

    actor = {
        "id": 7,
        "rol_nombre": "Emisor",
    }

    solicitud = {
        "id": 100,
        "public_id": "solicitud-hu07",
        "emisor_id": 7,
        "cliente_id": 15,
        "estado_id": 1,
        "version": 3,
        "concepto": "Concepto original",
        "nro_orden_compra": "OC-100",
        "fecha_emision": date(2026, 11, 5),
        "monto_bruto": Decimal("150000"),
        "tipo_afectacion": "AFECTA",
    }

    estado = {"nombre": "Pendiente"}

    cursor.fetchone.side_effect = [
        solicitud,
        estado,
    ]

    auditoria = Mock()
    abrir_conexion = Mock(return_value=connection)

    monkeypatch.setattr(
        servicio,
        "get_db_connection",
        abrir_conexion,
    )
    monkeypatch.setattr(
        servicio,
        "comprobar_actor",
        Mock(return_value=actor),
    )
    monkeypatch.setattr(
        servicio,
        "registrar_evento",
        auditoria,
    )

    return {
        "connection": connection,
        "cursor": cursor,
        "actor": actor,
        "solicitud": solicitud,
        "estado": estado,
        "auditoria": auditoria,
        "abrir_conexion": abrir_conexion,
    }


def editar(datos, *, version=3):
    return servicio.editar_solicitud(
        actor_id=7,
        public_id="solicitud-hu07",
        datos=datos,
        version_esperada=version,
        ip="127.0.0.1",
    )


def test_emisor_edita_solicitud_propia_pendiente(
    datos_edicion,
    entorno_edicion,
):
    resultado = editar(datos_edicion)

    assert resultado is True

    entorno_edicion["connection"].commit.assert_called_once()
    entorno_edicion["connection"].rollback.assert_not_called()
    entorno_edicion["connection"].close.assert_called_once()

    actualizaciones = [
        llamada
        for llamada in entorno_edicion["cursor"].execute.call_args_list
        if "UPDATE solicitudes" in llamada.args[0]
    ]

    assert len(actualizaciones) == 1

    sql, parametros = actualizaciones[0].args

    assert "version = version + 1" in sql
    assert parametros[0] == "Concepto corregido"
    assert parametros[-3:] == (100, 3, 1)


def test_emisor_no_edita_solicitud_ajena(
    datos_edicion,
    entorno_edicion,
):
    entorno_edicion["solicitud"]["emisor_id"] = 99

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="no está disponible",
    ):
        editar(datos_edicion)

    entorno_edicion["connection"].commit.assert_not_called()
    entorno_edicion["connection"].rollback.assert_called_once()
    entorno_edicion["auditoria"].assert_not_called()


def test_administrador_edita_solicitud_de_otro_emisor(
    datos_edicion,
    entorno_edicion,
):
    entorno_edicion["actor"]["rol_nombre"] = "Administrador"
    entorno_edicion["solicitud"]["emisor_id"] = 99

    assert editar(datos_edicion) is True

    entorno_edicion["connection"].commit.assert_called_once()


@pytest.mark.parametrize(
    "estado",
    ["En revisión", "Emitida", "Rechazada"],
)
def test_rechaza_estado_distinto_de_pendiente(
    datos_edicion,
    entorno_edicion,
    estado,
):
    entorno_edicion["estado"]["nombre"] = estado

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="Pendientes",
    ):
        editar(datos_edicion)

    entorno_edicion["connection"].commit.assert_not_called()
    entorno_edicion["connection"].rollback.assert_called_once()
    entorno_edicion["auditoria"].assert_not_called()


def test_rechaza_formulario_desactualizado(
    datos_edicion,
    entorno_edicion,
):
    entorno_edicion["solicitud"]["version"] = 4

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="cambió",
    ):
        editar(datos_edicion, version=3)

    entorno_edicion["connection"].commit.assert_not_called()
    entorno_edicion["connection"].rollback.assert_called_once()


def test_no_permite_cambiar_cliente(
    datos_edicion,
    entorno_edicion,
):
    datos_edicion["cliente_id"] = "99"

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="cambiar el cliente",
    ):
        editar(datos_edicion)

    entorno_edicion["connection"].commit.assert_not_called()
    entorno_edicion["auditoria"].assert_not_called()


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("concepto", "   "),
        ("monto_bruto", "0"),
        ("fecha_emision", "2026-02-30"),
        ("tipo_afectacion", "OTRA"),
    ],
)
def test_datos_modificados_se_validan_antes_de_abrir_conexion(
    datos_edicion,
    entorno_edicion,
    campo,
    valor,
):
    datos_edicion[campo] = valor

    with pytest.raises(servicio.ErrorGestionSolicitud):
        editar(datos_edicion)

    entorno_edicion["abrir_conexion"].assert_not_called()
    entorno_edicion["auditoria"].assert_not_called()


def test_auditoria_registra_actor_y_cambio(
    datos_edicion,
    entorno_edicion,
):
    editar(datos_edicion)

    entorno_edicion["auditoria"].assert_called_once()

    argumentos = entorno_edicion["auditoria"].call_args.args

    assert argumentos[0] is entorno_edicion["connection"]
    assert argumentos[1] == 7
    assert argumentos[2] == "SOLICITUD_EDITADA"
    assert argumentos[4] == "127.0.0.1"

    detalle = argumentos[3]

    assert detalle["solicitud_afectada_id"] == 100
    assert detalle["public_id"] == "solicitud-hu07"
    assert detalle["version_anterior"] == 3
    assert detalle["version_nueva"] == 4
    assert detalle["cambios"] == {
        "concepto": {
            "anterior": "Concepto original",
            "nuevo": "Concepto corregido",
        }
    }


def test_sin_cambios_no_actualiza_ni_audita(
    datos_edicion,
    entorno_edicion,
):
    datos_edicion["concepto"] = "Concepto original"

    assert editar(datos_edicion) is False

    actualizaciones = [
        llamada
        for llamada in entorno_edicion["cursor"].execute.call_args_list
        if "UPDATE solicitudes" in llamada.args[0]
    ]

    assert actualizaciones == []
    entorno_edicion["connection"].commit.assert_not_called()
    entorno_edicion["auditoria"].assert_not_called()


def test_fallo_de_auditoria_no_confirma_edicion(
    datos_edicion,
    entorno_edicion,
):
    entorno_edicion["auditoria"].side_effect = RuntimeError(
        "Auditoría no disponible"
    )

    with pytest.raises(RuntimeError, match="Auditoría"):
        editar(datos_edicion)

    entorno_edicion["connection"].commit.assert_not_called()
    entorno_edicion["connection"].rollback.assert_called_once()


def test_lector_no_accede_a_ruta_real_de_edicion(
    app,
    client,
    login_como,
    monkeypatch,
):
    login_como(rol="Lector")

    conexion = Mock()
    monkeypatch.setattr(routes, "get_db_connection", conexion)

    with app.test_request_context():
        url = url_for(
            "solicitudes.editar",
            public_id="solicitud-hu07",
        )

    respuesta = client.get(url, follow_redirects=False)

    assert respuesta.status_code == 403
    conexion.assert_not_called()