from datetime import date
from decimal import Decimal

import pytest

from app.services.filtros_solicitud import (
    construir_filtros_solicitud,
)


def test_sin_filtros():
    condiciones, parametros, filtros, errores = (
        construir_filtros_solicitud({})
    )

    assert condiciones == []
    assert parametros == ()
    assert errores == {}
    assert all(valor == "" for valor in filtros.values())


def test_rut_se_normaliza():
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud({"rut": "12.345.678-5"})
    )

    assert errores == {}
    assert condiciones == ["s.rut = %s"]
    assert parametros == ("12345678-5",)


def test_rango_fechas_inclusivo():
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud({
            "desde": "2026-11-01",
            "hasta": "2026-11-04",
        })
    )

    assert errores == {}
    assert condiciones == [
        "s.fecha_emision >= %s",
        "s.fecha_emision <= %s",
    ]
    assert parametros == (
        date(2026, 11, 1),
        date(2026, 11, 4),
    )


def test_monto_exacto():
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud({"monto": "150000"})
    )

    assert errores == {}
    assert condiciones == ["s.monto_bruto = %s"]
    assert parametros == (Decimal("150000"),)


def test_filtros_combinados():
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud(
            {
                "rut": "12345678-5",
                "desde": "2026-11-01",
                "hasta": "2026-11-04",
                "monto": "150000",
                "estado_id": "2",
                "emisor_id": "7",
            },
            permitir_filtro_emisor=True,
        )
    )

    assert errores == {}
    assert " AND ".join(condiciones) == (
        "s.rut = %s"
        " AND s.fecha_emision >= %s"
        " AND s.fecha_emision <= %s"
        " AND s.monto_bruto = %s"
        " AND s.estado_id = %s"
        " AND s.emisor_id = %s"
    )
    assert parametros == (
        "12345678-5",
        date(2026, 11, 1),
        date(2026, 11, 4),
        Decimal("150000"),
        2,
        7,
    )


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("rut", "12345678-9"),
        ("desde", "2026-02-30"),
        ("hasta", "04-11-2026"),
        ("monto", "0"),
        ("monto", "-100"),
        ("monto", "1.000"),
        ("monto", "100,50"),
        ("monto", "9" * 15),
        ("estado_id", "0"),
        ("estado_id", "abc"),
        ("estado_id", "4294967296"),
        ("emisor_id", "-1"),
        ("emisor_id", "1 OR 1=1"),
    ],
)
def test_rechaza_filtro_invalido(campo, valor):
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud(
            {campo: valor},
            permitir_filtro_emisor=True,
        )
    )

    assert campo in errores
    assert condiciones == []
    assert parametros == ()


def test_rechaza_rango_invertido():
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud({
            "desde": "2026-11-05",
            "hasta": "2026-11-01",
        })
    )

    assert "hasta" in errores
    assert condiciones == []
    assert parametros == ()


def test_permite_mismo_dia_en_ambos_extremos():
    _, parametros, _, errores = construir_filtros_solicitud({
        "desde": "2026-11-04",
        "hasta": "2026-11-04",
    })

    assert errores == {}
    assert parametros == (
        date(2026, 11, 4),
        date(2026, 11, 4),
    )


def test_emisor_requiere_permiso_explicito():
    condiciones, parametros, _, errores = (
        construir_filtros_solicitud({"emisor_id": "7"})
    )

    assert "emisor_id" in errores
    assert condiciones == []
    assert parametros == ()


def test_error_no_permite_busqueda_parcial():
    condiciones, parametros, filtros, errores = (
        construir_filtros_solicitud({
            "monto": "150000",
            "hasta": "fecha-invalida",
        })
    )

    assert "hasta" in errores
    assert filtros["monto"] == "150000"
    assert condiciones == []
    assert parametros == ()


def test_no_modifica_argumentos_originales():
    argumentos = {"monto": " 150000 "}
    original = argumentos.copy()

    _, parametros, filtros, errores = (
        construir_filtros_solicitud(argumentos)
    )

    assert errores == {}
    assert argumentos == original
    assert filtros["monto"] == "150000"
    assert parametros == (Decimal("150000"),)