from datetime import date
from decimal import Decimal

import pytest

from app.services.solicitudes import validar_solicitud
from app.services.validaciones import (
    ErrorValidacion,
    normalizar_correo,
    normalizar_rut,
    validar_cliente,
)


@pytest.mark.parametrize("entrada, esperado", [
    ("11.111.111-1", "11111111-1"),
    ("76.086.428-5", "76086428-5"),
    ("12345678-5", "12345678-5"),
    ("5126663-3", "5126663-3"),
    ("10.000.013-k", "10000013-K"),
])
def test_rut_valido(entrada, esperado):
    assert normalizar_rut(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    "11111111-2", "0-0", "abc", "", "123456789-0", None,
])
def test_rut_invalido(entrada):
    with pytest.raises(ErrorValidacion):
        normalizar_rut(entrada)


def test_correo_normaliza_dominio():
    assert normalizar_correo(" Contacto@Empresa.CL ") == "Contacto@empresa.cl"


def test_correo_invalido():
    with pytest.raises(ErrorValidacion):
        normalizar_correo("no-es-correo")


def test_validar_cliente_reporta_campos():
    limpio, errores = validar_cliente({"rut": "11111111-2"})
    assert {"rut", "razon_social", "giro", "direccion",
            "email_contacto"} <= set(errores)
    assert limpio == {}


def datos_solicitud(**cambios):
    datos = {
        "cliente_id": "5", "concepto": "Servicio mensual",
        "monto_bruto": "119000", "fecha_emision": "2026-10-28",
        "tipo_afectacion": "AFECTA", "nro_orden_compra": "",
    }
    datos.update(cambios)
    return datos


def test_solicitud_valida():
    limpio, errores = validar_solicitud(datos_solicitud())
    assert errores == {}
    assert limpio["monto_bruto"] == Decimal("119000")
    assert limpio["fecha_emision"] == date(2026, 10, 28)
    assert limpio["nro_orden_compra"] is None


@pytest.mark.parametrize("campo, valor", [
    ("cliente_id", "0"),
    ("cliente_id", "abc"),
    ("concepto", "   "),
    ("concepto", "x" * 501),
    ("monto_bruto", "1.000"),
    ("monto_bruto", "0"),
    ("fecha_emision", "28-10-2026"),
    ("fecha_emision", "2026-02-30"),
    ("tipo_afectacion", "OTRA"),
    ("nro_orden_compra", "x" * 41),
])
def test_solicitud_invalida(campo, valor):
    _, errores = validar_solicitud(datos_solicitud(**{campo: valor}))
    assert campo in errores
