from datetime import date
from email.message import EmailMessage

import pytest

from app.services.extraccion_correo import (
    es_automatico,
    es_facturacion,
    extraer_datos,
    normalizar_fecha,
    normalizar_monto,
    texto_del_mensaje,
    verificacion_remitente,
)

HOY = date(2026, 11, 4)


def correo(cuerpo="", asunto="Solicitud de factura", html=None, adjuntos=(),
           **cabeceras):
    m = EmailMessage()
    m["From"] = "Cliente <prueba@ejemplo.com>"
    m["To"] = "facturas@facturaciones.cl"
    m["Subject"] = asunto
    for nombre, valor in cabeceras.items():
        m[nombre.replace("_", "-")] = valor
    m.set_content(cuerpo)
    if html:
        m.add_alternative(html, subtype="html")
    for nombre, contenido in adjuntos:
        m.add_attachment(contenido, maintype="application", subtype="xml",
                         filename=nombre)
    return m


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Solicitud de FACTURACIÓN", ""),
    ("Hola", "Necesito que me facturen... perdón, que emitan la factura."),
    ("OC 4500", "Adjunto orden de compra para facturar."),
    ("Re: pendiente", "Favor enviar el DTE."),
])
def test_detecta_correos_de_facturacion(asunto, cuerpo):
    assert es_facturacion(asunto, cuerpo)


@pytest.mark.parametrize("asunto,cuerpo", [
    ("Reunión del lunes", "Confirmo asistencia."),
    ("Newsletter", "Las mejores ofertas de la semana"),
])
def test_ignora_correos_sin_tema_de_facturacion(asunto, cuerpo):
    assert not es_facturacion(asunto, cuerpo)


@pytest.mark.parametrize("cabeceras", [
    {"Auto_Submitted": "auto-replied"},
    {"Precedence": "bulk"},
    {"X_Facturaciones_Origen": "notificacion"},
    {"List_Id": "<lista.ejemplo.com>"},
])
def test_detecta_mensajes_automaticos(cabeceras):
    assert es_automatico(correo("Factura", **cabeceras))


def test_mensaje_normal_no_es_automatico():
    assert not es_automatico(correo("Factura"))


def test_verificacion_spf_dmarc():
    assert verificacion_remitente(correo()) == "desconocida"
    assert verificacion_remitente(correo(
        Authentication_Results="mx.ejemplo; spf=pass; dmarc=pass")) == "aprobada"
    assert verificacion_remitente(correo(
        Authentication_Results="mx.ejemplo; spf=pass; dmarc=fail")) == "fallida"


@pytest.mark.parametrize("valor,esperado", [
    ("$980.000", ("980000", False)),
    ("980000 CLP", ("980000", False)),
    ("$ 1.234.567,00", ("1234567", False)),
    ("1.000.000 + IVA", ("1000000", True)),
    ("500.000 neto", ("500000", True)),
    ("12,5", (None, False)),
    ("cero", (None, False)),
    ("0", (None, False)),
])
def test_normalizar_monto(valor, esperado):
    assert normalizar_monto(valor) == esperado


@pytest.mark.parametrize("valor,esperado", [
    ("2026-10-16", "2026-10-16"),
    ("16-10-2026", "2026-10-16"),
    ("16/10/2026", "2026-10-16"),
    ("31-02-2026", None),
    ("mañana", None),
])
def test_normalizar_fecha(valor, esperado):
    assert normalizar_fecha(valor) == esperado


CUERPO = """Estimados, solicito la factura de octubre:

RUT: 12.345.678-5
Concepto: Servicios de asesoría octubre 2026
Monto: $980.000
Fecha de emisión: 16-10-2026
Afectación: Afecta
N° OC: 4500012345

> Fecha: 01-01-2020  (texto citado, se ignora)
Saludos
"""


def test_extrae_campos_del_cuerpo():
    datos, alertas = extraer_datos(correo(CUERPO), hoy=HOY)
    assert datos == {
        "rut": "12345678-5",
        "concepto": "Servicios de asesoría octubre 2026",
        "monto_bruto": "980000",
        "fecha_emision": "2026-10-16",
        "tipo_afectacion": "AFECTA",
        "nro_orden_compra": "4500012345",
    }
    assert alertas == []


def test_monto_neto_se_convierte_a_bruto():
    datos, alertas = extraer_datos(
        correo("Concepto: Asesoría\nMonto: 1.000.000 + IVA\nTipo: exenta"),
        hoy=HOY,
    )
    assert datos["monto_bruto"] == "1190000"
    assert datos["tipo_afectacion"] == "EXENTA"
    assert any("neto" in a for a in alertas)


def test_valores_por_defecto_quedan_alertados():
    datos, alertas = extraer_datos(correo("Concepto: Asesoría\nMonto: 1000"),
                                   hoy=HOY)
    assert datos["fecha_emision"] == "2026-11-04"
    assert datos["tipo_afectacion"] == "AFECTA"
    assert datos["rut"] is None
    assert len(alertas) == 2


def test_rut_suelto_en_el_texto():
    datos, _ = extraer_datos(
        correo("Para la empresa 12345678-5 necesito factura"), hoy=HOY
    )
    assert datos["rut"] == "12345678-5"


def test_rut_invalido_genera_alerta():
    datos, alertas = extraer_datos(correo("RUT: 12.345.678-9"), hoy=HOY)
    assert datos["rut"] is None
    assert any("RUT" in a for a in alertas)


def test_cuerpo_html_se_convierte_a_texto():
    html = ("<html><head><style>p{}</style></head><body>"
            "<p>Concepto: Diseño web</p><p>Monto: 500.000</p>"
            "<script>alert(1)</script></body></html>")
    mensaje = correo("", html=html)
    mensaje.get_body(("plain",)).set_content("")  # sin texto plano útil
    datos, _ = extraer_datos(mensaje, hoy=HOY)
    assert datos["monto_bruto"] == "500000"
    assert "alert" not in texto_del_mensaje(correo("", html=html))


XML = (b'<?xml version="1.0"?><DocumentoPrueba><Encabezado>'
       b"<FechaEmision>2026-10-16</FechaEmision>"
       b"<TipoAfectacion>EXENTA</TipoAfectacion>"
       b"<OrdenCompra>OC-77</OrdenCompra></Encabezado>"
       b"<Receptor><RUT>12345678-5</RUT></Receptor>"
       b"<Detalle><Concepto>Desde XML</Concepto>"
       b'<MontoBruto moneda="CLP">750000</MontoBruto></Detalle>'
       b"</DocumentoPrueba>")


def test_adjunto_xml_prevalece_y_alerta_diferencias():
    datos, alertas = extraer_datos(
        correo("Concepto: Desde el cuerpo", adjuntos=[("sol.xml", XML)]),
        hoy=HOY,
    )
    assert datos["concepto"] == "Desde XML"
    assert datos["monto_bruto"] == "750000"
    assert datos["tipo_afectacion"] == "EXENTA"
    assert datos["nro_orden_compra"] == "OC-77"
    assert any("difiere" in a for a in alertas)


def test_adjunto_xml_peligroso_se_ignora():
    xxe = (b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM '
           b'"file:///etc/passwd">]><a><Concepto>&x;</Concepto></a>')
    datos, alertas = extraer_datos(
        correo("Concepto: Normal", adjuntos=[("x.xml", xxe)]), hoy=HOY
    )
    assert datos["concepto"] == "Normal"
    assert any("no es XML válido" in a for a in alertas)
