from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from app.services import solicitudes as servicio


@pytest.fixture
def datos_solicitud():
    return {
        "cliente_id": "15",
        "concepto": "Servicio de desarrollo",
        "monto_bruto": "150000",
        "fecha_emision": "2026-11-05",
        "tipo_afectacion": "AFECTA",
        "nro_orden_compra": "OC-QA-002",
    }


@pytest.fixture
def entorno_registro(monkeypatch):
    connection = MagicMock()
    cursor = MagicMock()

    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.lastrowid = 100

    actor = {
        "id": 7,
        "rol_nombre": "Emisor",
        "email": "emisor@example.com",
    }

    cliente = {
        "id": 15,
        "rut": "12345678-5",
        "razon_social": "Cliente QA",
        "giro": "Servicios informáticos",
        "direccion": "Dirección de prueba 123",
        "email_contacto": "cliente@example.com",
        "activo": 1,
    }

    monkeypatch.setattr(
        servicio,
        "get_db_connection",
        lambda: connection,
    )

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

    def preparar_respuestas(existente=None):
        cursor.fetchone.side_effect = [
            existente,
            cliente.copy(),
            {"id": 1},  # Catálogo Pendiente.
            {"id": 2},  # Catálogo Web.
        ]

    preparar_respuestas()

    return {
        "connection": connection,
        "cursor": cursor,
        "actor": actor,
        "cliente": cliente,
        "comprobar_actor": comprobar_actor,
        "auditoria": auditoria,
        "preparar_respuestas": preparar_respuestas,
    }


def crear(datos, clave="a" * 32):
    return servicio.crear_solicitud(
        actor_id=7,
        datos=datos,
        clave_idempotencia=clave,
        ip="127.0.0.1",
    )


def obtener_insert_solicitud(cursor):
    inserts = [
        llamada
        for llamada in cursor.execute.call_args_list
        if "INSERT INTO solicitudes" in llamada.args[0]
    ]

    assert len(inserts) == 1
    return inserts[0].args[1]


def test_registro_valido_confirma_transaccion(
    datos_solicitud,
    entorno_registro,
):
    public_id = crear(datos_solicitud)

    registro = obtener_insert_solicitud(
        entorno_registro["cursor"]
    )

    assert public_id == registro["public_id"]
    assert len(public_id) == 32
    assert all(caracter in "0123456789abcdef" for caracter in public_id)

    entorno_registro["connection"].commit.assert_called_once()
    entorno_registro["connection"].rollback.assert_not_called()
    entorno_registro["connection"].close.assert_called_once()


def test_asocia_emisor_validado_no_emisor_del_formulario(
    datos_solicitud,
    entorno_registro,
):
    datos_solicitud["emisor_id"] = "999"

    crear(datos_solicitud)

    registro = obtener_insert_solicitud(
        entorno_registro["cursor"]
    )

    assert registro["emisor_id"] == 7
    assert registro["email_emisor"] == "emisor@example.com"

    entorno_registro["comprobar_actor"].assert_called_once_with(
        entorno_registro["cursor"],
        7,
    )


def test_registra_datos_validados_del_cliente(
    datos_solicitud,
    entorno_registro,
):
    crear(datos_solicitud)

    registro = obtener_insert_solicitud(
        entorno_registro["cursor"]
    )

    assert registro["cliente_id"] == 15
    assert registro["rut"] == "12345678-5"
    assert registro["nombre"] == "Cliente QA"
    assert registro["giro"] == "Servicios informáticos"
    assert registro["direccion"] == "Dirección de prueba 123"
    assert registro["email_contacto_receptor"] == "cliente@example.com"


def test_registra_campos_de_facturacion(
    datos_solicitud,
    entorno_registro,
):
    crear(datos_solicitud)

    registro = obtener_insert_solicitud(
        entorno_registro["cursor"]
    )

    assert registro["concepto"] == "Servicio de desarrollo"
    assert registro["monto_bruto"] == Decimal("150000")
    assert registro["fecha_emision"] == date(2026, 11, 5)
    assert registro["tipo_afectacion"] == "AFECTA"
    assert registro["nro_orden_compra"] == "OC-QA-002"


def test_estado_pendiente_y_origen_web_actual(
    datos_solicitud,
    entorno_registro,
):
    crear(datos_solicitud)

    cursor = entorno_registro["cursor"]

    consultas_estado = [
        llamada
        for llamada in cursor.execute.call_args_list
        if "FROM estados_solicitud" in llamada.args[0]
    ]
    consultas_origen = [
        llamada
        for llamada in cursor.execute.call_args_list
        if "FROM origenes_solicitud" in llamada.args[0]
    ]

    assert len(consultas_estado) == 1
    assert consultas_estado[0].args[1] == ("Pendiente",)

    assert len(consultas_origen) == 1
    assert consultas_origen[0].args[1] == ("Web",)

    registro = obtener_insert_solicitud(cursor)
    assert registro["estado_id"] == 1
    assert registro["origen_id"] == 2


def test_auditoria_identifica_al_usuario_que_registra(
    datos_solicitud,
    entorno_registro,
):
    public_id = crear(datos_solicitud)

    entorno_registro["auditoria"].assert_called_once()

    argumentos = entorno_registro["auditoria"].call_args.args

    assert argumentos[0] is entorno_registro["connection"]
    assert argumentos[1] == 7
    assert argumentos[2] == "SOLICITUD_CREADA"
    assert argumentos[4] == "127.0.0.1"

    detalle = argumentos[3]

    assert detalle["solicitud_afectada_id"] == 100
    assert detalle["public_id"] == public_id
    assert detalle["estado"] == "Pendiente"
    assert detalle["origen"] == "Web"


def test_cliente_inactivo_impide_registro(
    datos_solicitud,
    entorno_registro,
):
    cliente = entorno_registro["cliente"].copy()
    cliente["activo"] = 0

    entorno_registro["cursor"].fetchone.side_effect = [
        None,
        cliente,
    ]

    with pytest.raises(
        servicio.ErrorGestionSolicitud,
        match="inactivo",
    ):
        crear(datos_solicitud)

    entorno_registro["connection"].commit.assert_not_called()
    entorno_registro["connection"].rollback.assert_called_once()
    entorno_registro["auditoria"].assert_not_called()


def test_reenvio_idempotente_recupera_solicitud(
    datos_solicitud,
    entorno_registro,
):
    limpio, errores = servicio.validar_solicitud(datos_solicitud)
    assert errores == {}

    existente = {
        "public_id": "b" * 32,
        "huella_creacion": servicio.huella_de_creacion(limpio),
    }

    entorno_registro["cursor"].fetchone.side_effect = [
        existente,
    ]

    public_id = crear(datos_solicitud)

    assert public_id == existente["public_id"]

    inserts = [
        llamada
        for llamada in entorno_registro["cursor"].execute.call_args_list
        if "INSERT INTO solicitudes" in llamada.args[0]
    ]

    assert inserts == []
    entorno_registro["connection"].commit.assert_not_called()
    entorno_registro["auditoria"].assert_not_called()


def test_fallo_auditoria_no_confirma_registro(
    datos_solicitud,
    entorno_registro,
):
    entorno_registro["auditoria"].side_effect = RuntimeError(
        "Auditoría no disponible"
    )

    with pytest.raises(RuntimeError, match="Auditoría"):
        crear(datos_solicitud)

    entorno_registro["connection"].commit.assert_not_called()
    entorno_registro["connection"].rollback.assert_called_once()
    entorno_registro["connection"].close.assert_called_once()