from datetime import date
from decimal import Decimal

import pytest

from app.services import correos_solicitud
from app.services.correos_solicitud import (
    ErrorEnvioCorreo,
    componer_correo,
)

SOLICITUD = {
    "public_id": "6a5c43b82d54be589a4494a623378d59",
    "rut": "12345678-5",
    "nombre": "Cliente de Prueba MVP",
    "concepto": "Facturaciones de prueba 10/2026",
    "monto_bruto": Decimal("980000"),
    "tipo_afectacion": "AFECTA",
    "fecha_emision": date(2026, 10, 16),
    "nro_orden_compra": "OC-77",
    "email_emisor": "admin@facturaciones.cl",
}


def test_componer_correo(app):
    with app.test_request_context():
        asunto, cuerpo = componer_correo(SOLICITUD)
    assert asunto == (
        "Documento XML - Cliente de Prueba MVP - Solicitud 6a5c43b8"
    )
    assert "980.000 CLP (AFECTA)" in cuerpo
    assert "OC-77" in cuerpo
    assert "admin@facturaciones.cl" in cuerpo
    assert "<" not in cuerpo


def test_asunto_sin_saltos_de_linea(app):
    solicitud = dict(SOLICITUD, nombre="Empresa\r\nBcc: x@y.cl")
    with app.test_request_context():
        asunto, _ = componer_correo(solicitud)
    assert "\n" not in asunto and "\r" not in asunto


def test_xml_alterado_se_bloquea(app, tmp_path):
    carpeta = tmp_path / "xml"
    carpeta.mkdir(exist_ok=True)
    (carpeta / "abc.xml").write_bytes(b"<DTE>modificado</DTE>")
    app.config["XML_UPLOAD_FOLDER"] = str(carpeta)
    registro = {"id": 1, "nombre_almacenado": "abc.xml", "sha256": "0" * 64}

    with app.app_context(), pytest.raises(ErrorEnvioCorreo, match="SHA-256"):
        correos_solicitud._leer_xml_verificado(registro)


def test_nombre_almacenado_con_ruta_se_bloquea(app):
    registro = {"id": 1, "nombre_almacenado": "../config.py", "sha256": "0"}
    with app.app_context(), pytest.raises(ErrorEnvioCorreo):
        correos_solicitud._leer_xml_verificado(registro)
