from unittest.mock import MagicMock, Mock

import pytest

from app.services import solicitudes as servicio


@pytest.fixture
def entorno(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.rowcount = 1

    monkeypatch.setattr(
        servicio,
        "get_db_connection",
        lambda: connection,
    )

    actor = {
        "id": 1,
        "rol_nombre": "Administrador",
    }

    comprobar_actor = Mock(return_value=actor)
    auditoria = Mock()

    monkeypatch.setattr(
        servicio,
        "comprobar_actor",
        comprobar_actor,
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
        "auditoria": auditoria,
    }


def preparar_respuestas(
    entorno,
    *,
    estado_actual="Pendiente",
    version=1,
    estado_destino="En revisión",
):
    entorno["cursor"].fetchone.side_effect = [
        {
            "id": 10,
            "estado_id": 1,
            "version": version,
            "motivo_rechazo": None,
        },
        {
            "id": 1,
            "nombre": estado_actual,
        },
        {
            "id": 2,
            "nombre": estado_destino,
        },
    ]


def ejecutar_cambio(**cambios):
    argumentos = {
        "actor_id": 1,
        "public_id": "solicitud-prueba",
        "estado_destino": "En revisión",
        "version_esperada": 1,
    }
    argumentos.update(cambios)

    return servicio.cambiar_estado_solicitud(**argumentos)


def test_administrador_cambia_pendiente_a_revision(entorno):
    preparar_respuestas(entorno)

    resultado = ejecutar_cambio()

    assert resultado is True
    entorno["connection"].commit.assert_called_once()
    entorno["connection"].rollback.assert_not_called()
    entorno["connection"].close.assert_called_once()


def test_cambio_registra_actor_y_estados(entorno):
    preparar_respuestas(entorno)

    ejecutar_cambio()

    entorno["auditoria"].assert_called_once()

    argumentos = entorno["auditoria"].call_args.args

    assert argumentos[0] is entorno["connection"]
    assert argumentos[1] == 1
    assert argumentos[2] == "SOLICITUD_ESTADO_CAMBIADO"

    detalle = argumentos[3]

    assert detalle["solicitud_afectada_id"] == 10
    assert detalle["estado_anterior"] == "Pendiente"
    assert detalle["estado_nuevo"] == "En revisión"
    assert detalle["version_anterior"] == 1
    assert detalle["version_nueva"] == 2


@pytest.mark.parametrize("rol", ["Emisor", "Lector"])
def test_servicio_rechaza_actor_no_administrador(entorno, rol):
    entorno["actor"]["rol_nombre"] = rol

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="Solo un Administrador",
    ):
        ejecutar_cambio()

    entorno["connection"].commit.assert_not_called()
    entorno["connection"].rollback.assert_called_once()
    entorno["auditoria"].assert_not_called()


def test_rechaza_transicion_no_definida(entorno):
    preparar_respuestas(entorno)

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="no está permitido",
    ):
        ejecutar_cambio(estado_destino="ESTADO_INEXISTENTE")

    entorno["connection"].commit.assert_not_called()
    entorno["connection"].rollback.assert_called_once()
    entorno["auditoria"].assert_not_called()


def test_rechaza_version_desactualizada(entorno):
    preparar_respuestas(entorno, version=2)

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="cambió",
    ):
        ejecutar_cambio(version_esperada=1)

    entorno["connection"].commit.assert_not_called()
    entorno["connection"].rollback.assert_called_once()
    entorno["auditoria"].assert_not_called()


def test_rechazada_exige_motivo(entorno):
    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="motivo",
    ):
        ejecutar_cambio(
            estado_destino="Rechazada",
            motivo_rechazo="",
        )

    entorno["connection"].begin.assert_not_called()
    entorno["connection"].commit.assert_not_called()


def test_rechazo_con_motivo_registra_detalle(entorno):
    preparar_respuestas(
        entorno,
        estado_destino="Rechazada",
    )

    ejecutar_cambio(
        estado_destino="Rechazada",
        motivo_rechazo="Antecedentes inconsistentes.",
    )

    detalle = entorno["auditoria"].call_args.args[3]

    assert detalle["estado_nuevo"] == "Rechazada"
    assert detalle["motivo_rechazo_nuevo"] == (
        "Antecedentes inconsistentes."
    )
    entorno["connection"].commit.assert_called_once()


def test_fallo_auditoria_revierte_operacion(entorno):
    preparar_respuestas(entorno)
    entorno["auditoria"].side_effect = RuntimeError(
        "Auditoría no disponible"
    )

    with pytest.raises(RuntimeError, match="Auditoría"):
        ejecutar_cambio()

    entorno["connection"].commit.assert_not_called()
    entorno["connection"].rollback.assert_called_once()
    entorno["connection"].close.assert_called_once()


def test_actualizacion_sin_fila_afectada_se_rechaza(entorno):
    preparar_respuestas(entorno)
    entorno["cursor"].rowcount = 0

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="No se pudo aplicar",
    ):
        ejecutar_cambio()

    entorno["connection"].commit.assert_not_called()
    entorno["connection"].rollback.assert_called_once()
    entorno["auditoria"].assert_not_called()