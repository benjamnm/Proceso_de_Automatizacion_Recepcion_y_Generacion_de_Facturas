from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flask import url_for

from app.services import solicitudes as servicio
from app.solicitudes import routes


@pytest.fixture
def datos_validos():
    return {
        "cliente_id": "1",
        "concepto": "Servicio de desarrollo",
        "monto_bruto": "150000",
        "fecha_emision": "2026-11-04",
        "tipo_afectacion": "AFECTA",
        "nro_orden_compra": "OC-100",
    }


def test_solicitud_valida(datos_validos):
    limpio, errores = servicio.validar_solicitud(datos_validos)

    assert errores == {}
    assert limpio["cliente_id"] == 1
    assert limpio["monto_bruto"] == Decimal("150000")
    assert limpio["fecha_emision"] == date(2026, 11, 4)


def test_campos_obligatorios_ausentes():
    _, errores = servicio.validar_solicitud({})

    assert set(errores) == {
        "cliente_id",
        "concepto",
        "monto_bruto",
        "fecha_emision",
        "tipo_afectacion",
    }


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("cliente_id", ""),
        ("cliente_id", "0"),
        ("cliente_id", "-1"),
        ("cliente_id", "abc"),
        ("cliente_id", "4294967296"),
        ("concepto", ""),
        ("concepto", "   "),
        ("concepto", "x" * 501),
        ("concepto", None),
        ("monto_bruto", ""),
        ("monto_bruto", "0"),
        ("monto_bruto", "-100"),
        ("monto_bruto", "1.000"),
        ("monto_bruto", "1000,50"),
        ("monto_bruto", "1000.50"),
        ("monto_bruto", "9" * 15),
        ("monto_bruto", None),
        ("fecha_emision", ""),
        ("fecha_emision", "2026-02-30"),
        ("fecha_emision", "04-11-2026"),
        ("fecha_emision", "2026-1-1"),
        ("tipo_afectacion", ""),
        ("tipo_afectacion", "OTRA"),
        ("tipo_afectacion", ["AFECTA"]),
        ("nro_orden_compra", "x" * 41),
        ("nro_orden_compra", ["OC-100"]),
    ],
)
def test_rechaza_campo_invalido(datos_validos, campo, valor):
    datos_validos[campo] = valor

    _, errores = servicio.validar_solicitud(datos_validos)

    assert campo in errores


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("concepto", "x" * 500),
        ("monto_bruto", "1"),
        ("monto_bruto", "9" * 14),
        ("fecha_emision", "2024-02-29"),
        ("tipo_afectacion", "EXENTA"),
        ("nro_orden_compra", "x" * 40),
    ],
)
def test_acepta_limites_validos(datos_validos, campo, valor):
    datos_validos[campo] = valor

    _, errores = servicio.validar_solicitud(datos_validos)

    assert errores == {}


@pytest.mark.parametrize("valor", ["", "   ", None])
def test_orden_compra_opcional(datos_validos, valor):
    datos_validos["nro_orden_compra"] = valor

    limpio, errores = servicio.validar_solicitud(datos_validos)

    assert errores == {}
    assert limpio["nro_orden_compra"] is None


def test_fecha_alternativa_admitida(datos_validos):
    fecha = datos_validos.pop("fecha_emision")
    datos_validos["fecha_emision_solicitada"] = fecha

    limpio, errores = servicio.validar_solicitud(datos_validos)

    assert errores == {}
    assert limpio["fecha_emision"] == date(2026, 11, 4)


def test_fechas_diferentes_rechazadas(datos_validos):
    datos_validos["fecha_emision_solicitada"] = "2026-11-05"

    _, errores = servicio.validar_solicitud(datos_validos)

    assert "fecha_emision" in errores


def test_no_modifica_datos_originales(datos_validos):
    datos_validos["concepto"] = "  Servicio de desarrollo  "
    original = datos_validos.copy()

    limpio, errores = servicio.validar_solicitud(datos_validos)

    assert errores == {}
    assert datos_validos == original
    assert limpio["concepto"] == "Servicio de desarrollo"


def test_servicio_invalido_no_abre_conexion(monkeypatch):
    conexion = Mock()
    monkeypatch.setattr(servicio, "get_db_connection", conexion)

    with pytest.raises(servicio.ErrorGestionSolicitud):
        servicio.crear_solicitud(
            actor_id=1,
            datos={},
            clave_idempotencia="a" * 32,
        )

    conexion.assert_not_called()


def url_nueva(app):
    with app.test_request_context():
        return url_for("solicitudes.nueva")


def preparar_ruta(monkeypatch):
    monkeypatch.setattr(
        routes,
        "obtener_clientes_activos",
        lambda: [
            {
                "id": 1,
                "rut": "12345678-5",
                "razon_social": "Cliente de prueba",
            }
        ],
    )

    monkeypatch.setattr(
        routes,
        "verificar_token_envio",
        lambda token, usuario_id: "a" * 32,
    )


def test_formulario_invalido_conserva_datos(
    app,
    client,
    login_como,
    monkeypatch,
    datos_validos,
):
    login_como(rol="Emisor")
    preparar_ruta(monkeypatch)

    crear = Mock()
    monkeypatch.setattr(routes, "crear_solicitud", crear)

    datos_validos["monto_bruto"] = "0"
    datos_validos["token_envio"] = "token-de-prueba"

    respuesta = client.post(
        url_nueva(app),
        data=datos_validos,
    )

    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "El monto debe ser mayor que cero." in html
    assert 'id="monto_bruto_error"' in html
    assert 'aria-invalid="true"' in html
    assert "Servicio de desarrollo" in html
    assert 'value="OC-100"' in html
    assert 'value="0"' in html
    assert 'value="2026-11-04"' in html
    crear.assert_not_called()


def test_formulario_valido_continua_al_registro(
    app,
    client,
    login_como,
    monkeypatch,
    datos_validos,
):
    login_como(rol="Emisor")
    preparar_ruta(monkeypatch)

    crear = Mock(return_value="solicitud-de-prueba")
    monkeypatch.setattr(routes, "crear_solicitud", crear)

    datos_validos["token_envio"] = "token-de-prueba"

    respuesta = client.post(
        url_nueva(app),
        data=datos_validos,
        follow_redirects=False,
    )

    assert respuesta.status_code == 302
    crear.assert_called_once()

    argumentos = crear.call_args.kwargs
    assert argumentos["actor_id"] == 1
    assert argumentos["datos"]["concepto"] == "Servicio de desarrollo"
    assert argumentos["clave_idempotencia"] == "a" * 32


def test_error_del_servicio_conserva_formulario(
    app,
    client,
    login_como,
    monkeypatch,
    datos_validos,
):
    login_como(rol="Emisor")
    preparar_ruta(monkeypatch)

    crear = Mock(
        side_effect=servicio.ErrorGestionSolicitud(
            "El cliente no existe o está inactivo."
        )
    )
    monkeypatch.setattr(routes, "crear_solicitud", crear)

    datos_validos["token_envio"] = "token-de-prueba"

    respuesta = client.post(
        url_nueva(app),
        data=datos_validos,
    )

    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "El cliente no existe o está inactivo." in html
    assert "Servicio de desarrollo" in html
    assert 'value="150000"' in html
    assert 'value="OC-100"' in html