import json
from datetime import date
from decimal import Decimal

import pytest
from defusedxml import ElementTree

from app.services.dte_sii import ErrorDTE, advertencias, construir_dte, datos_emisor
from app.services.facturas import (
    ErrorFactura,
    calcular_totales,
    comparar_datos,
    construir_datos,
    generar_version,
    huella_datos,
)
from app.services.solicitudes import ErrorGestionSolicitud, cambiar_estado_solicitud

SOLICITUD = {
    "id": 1, "public_id": "6a5c43b82d54be589a4494a623378d59",
    "rut": "12345678-5", "nombre": "Cliente de Prueba MVP",
    "giro": "Servicios de pruebas MVP", "direccion": "Avenida Falsa 1234",
    "email_contacto_receptor": "prueba@ejemplo.com",
    "concepto": "Facturaciones de prueba 10/2026",
    "nro_orden_compra": "fsa9087f8987asf",
    "fecha_emision": date(2026, 10, 16),
    "monto_bruto": Decimal("980000"), "tipo_afectacion": "AFECTA",
}

EMISOR_CFG = {
    "EMPRESA_RUT": "76.123.456-0", "EMPRESA_RAZON_SOCIAL": "Facturaciones SpA",
    "EMPRESA_GIRO": "Servicios de facturación", "EMPRESA_ACTECO": "620200",
    "EMPRESA_DIRECCION": "Av. Siempre Viva 742", "EMPRESA_COMUNA": "Ñuñoa",
}


def test_totales_afecta():
    t = calcular_totales(Decimal("980000"), "AFECTA")
    assert (t["tipo_dte"], t["monto_neto"], t["iva"], t["monto_total"]) == (
        33, 823529, 156471, 980000)
    assert t["diferencia_redondeo"] == 0


def test_totales_exenta():
    t = calcular_totales(500000, "EXENTA")
    assert (t["tipo_dte"], t["monto_exento"], t["iva"], t["monto_total"]) == (
        34, 500000, 0, 500000)


@pytest.mark.parametrize("bruto", [1, 2, 5, 99, 119, 1190, 9999, 123457, 980000])
def test_totales_cumplen_regla_sii(bruto):
    t = calcular_totales(bruto, "AFECTA")
    assert t["monto_total"] == t["monto_neto"] + t["iva"]
    assert abs(t["diferencia_redondeo"]) <= 1
    assert t["monto_total"] - bruto == t["diferencia_redondeo"]


def test_comparar_datos_detecta_solo_diferencias():
    a = construir_datos(SOLICITUD)
    b = construir_datos(dict(SOLICITUD, giro="Otro giro", monto_bruto=Decimal("1190000")))
    cambios = comparar_datos(a, b)
    assert cambios["receptor.giro"] == {"anterior": "Servicios de pruebas MVP",
                                        "nuevo": "Otro giro"}
    assert cambios["totales.monto_total"]["nuevo"] == 1190000
    assert "detalle.concepto" not in cambios
    assert comparar_datos(a, construir_datos(SOLICITUD)) == {}


def test_huella_no_depende_del_orden():
    datos = construir_datos(SOLICITUD)
    reordenado = json.loads(json.dumps(datos, sort_keys=False))
    reordenado = dict(reversed(list(reordenado.items())))
    assert huella_datos(datos) == huella_datos(reordenado)


class CursorFacturas:
    def __init__(self, anterior=None):
        self.anterior = anterior
        self.insertado = None
        self.lastrowid = 10

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        if s.startswith("SELECT id, version, estado, datos"):
            self.resultado = self.anterior
        elif s.startswith("INSERT INTO facturas"):
            self.insertado = params
        else:
            raise AssertionError(s[:60])

    def fetchone(self):
        return self.resultado


def test_primera_version():
    cursor = CursorFacturas()
    factura = generar_version(cursor, dict(SOLICITUD), generada_por=1)
    assert factura["version"] == 1
    assert factura["cambios"] is None
    assert cursor.insertado[1] == 1          # version
    assert cursor.insertado[8] is None       # cambios


def test_version_2_registra_cambios():
    anterior = {"id": 9, "version": 1, "estado": "OBSERVADA",
                "datos": json.dumps(construir_datos(SOLICITUD))}
    cursor = CursorFacturas(anterior)
    corregida = dict(SOLICITUD, concepto="Concepto corregido")

    factura = generar_version(cursor, corregida, generada_por=1)

    assert factura["version"] == 2
    assert factura["version_anterior"] == 1
    assert factura["cambios"] == {"detalle.concepto": {
        "anterior": "Facturaciones de prueba 10/2026",
        "nuevo": "Concepto corregido"}}
    assert json.loads(cursor.insertado[8]) == factura["cambios"]


def test_reenvio_sin_cambios_se_rechaza():
    anterior = {"id": 9, "version": 1, "estado": "OBSERVADA",
                "datos": json.dumps(construir_datos(SOLICITUD))}
    with pytest.raises(ErrorFactura, match="no tiene cambios"):
        generar_version(CursorFacturas(anterior), dict(SOLICITUD), 1)


def test_cambio_directo_solo_permite_rechazo():
    # Aprobar o enviar a revisión pasa por services/facturas (versiones).
    with pytest.raises(ErrorGestionSolicitud, match="revisión de la factura"):
        cambiar_estado_solicitud(1, "a" * 32, "Aprobada", 1)


def test_emisor_incompleto_o_invalido():
    with pytest.raises(ErrorDTE, match="EMPRESA_COMUNA"):
        datos_emisor(dict(EMISOR_CFG, EMPRESA_COMUNA=""))
    with pytest.raises(ErrorDTE, match="ACTECO"):
        datos_emisor(dict(EMISOR_CFG, EMPRESA_ACTECO="abc"))
    with pytest.raises(ErrorDTE, match="RUT"):
        datos_emisor(dict(EMISOR_CFG, EMPRESA_RUT="76.123.456-1"))


def _leer(contenido):
    raiz = ElementTree.fromstring(contenido)
    return raiz, (lambda ruta: raiz.findtext(ruta))


def test_dte_factura_afecta():
    contenido = construir_dte(construir_datos(SOLICITUD),
                              datos_emisor(EMISOR_CFG), folio=15)
    assert contenido.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
    raiz, t = _leer(contenido)
    assert raiz.find("Documento").get("ID") == "F15T33"
    assert t("Documento/Encabezado/IdDoc/TipoDTE") == "33"
    assert t("Documento/Encabezado/IdDoc/FchEmis") == "2026-10-16"
    assert t("Documento/Encabezado/Emisor/RUTEmisor") == "76123456-0"
    assert t("Documento/Encabezado/Emisor/CmnaOrigen") == "Ñuñoa"
    assert t("Documento/Encabezado/Receptor/RUTRecep") == "12345678-5"
    assert t("Documento/Encabezado/Totales/MntNeto") == "823529"
    assert t("Documento/Encabezado/Totales/IVA") == "156471"
    assert t("Documento/Encabezado/Totales/MntTotal") == "980000"
    assert t("Documento/Detalle/MontoItem") == "823529"
    assert t("Documento/Referencia/TpoDocRef") == "801"
    assert t("Documento/Referencia/FolioRef") == "fsa9087f8987asf"


def test_dte_exenta_sin_iva_ni_referencia():
    datos = construir_datos(dict(SOLICITUD, tipo_afectacion="EXENTA",
                                 nro_orden_compra=None))
    raiz, t = _leer(construir_dte(datos, datos_emisor(EMISOR_CFG), folio=1))
    assert t("Documento/Encabezado/IdDoc/TipoDTE") == "34"
    assert t("Documento/Encabezado/Totales/MntExe") == "980000"
    assert raiz.find("Documento/Encabezado/Totales/IVA") is None
    assert raiz.find("Documento/Referencia") is None


def test_dte_recorta_y_advierte_campos_largos():
    datos = construir_datos(dict(SOLICITUD, giro="G" * 60, concepto="C" * 120))
    assert any("GiroRecep" in a for a in advertencias(datos))
    _, t = _leer(construir_dte(datos, datos_emisor(EMISOR_CFG), folio=1))
    assert t("Documento/Encabezado/Receptor/GiroRecep") == "G" * 40
    assert t("Documento/Detalle/NmbItem") == "C" * 80
    assert t("Documento/Detalle/DscItem") == "C" * 120
