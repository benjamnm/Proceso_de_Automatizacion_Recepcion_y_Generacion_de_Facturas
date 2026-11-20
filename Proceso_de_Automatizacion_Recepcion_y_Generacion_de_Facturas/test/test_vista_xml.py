"""Vista previa del diseño y formato de la factura (XML)."""
import pytest

from app.services.dte_sii import construir_dte
from app.services.facturas import construir_datos
from app.services.registros_xml import ErrorArchivoXML
from app.services.vista_xml import ErrorVistaXML, formatear_xml, interpretar_dte
from test_facturas import SOLICITUD

PID = "b" * 32
VISTA = f"/solicitudes/{PID}/factura/vista"

EMISOR = {
    "rut": "76123456-0", "razon_social": "Facturaciones SpA",
    "giro": "Servicios informáticos", "acteco": "620200",
    "direccion": "Av. Uno 123", "comuna": "Santiago",
}
CONFIG_EMISOR = {
    "EMPRESA_RUT": "76.123.456-0", "EMPRESA_RAZON_SOCIAL": "Facturaciones SpA",
    "EMPRESA_GIRO": "Servicios informáticos", "EMPRESA_ACTECO": "620200",
    "EMPRESA_DIRECCION": "Av. Uno 123", "EMPRESA_COMUNA": "Santiago",
}


def _dte(concepto="Asesoría ñandú"):
    datos = construir_datos(dict(SOLICITUD, concepto=concepto))
    return construir_dte(datos, EMISOR, folio=15), datos


def flashes(client):
    with client.session_transaction() as sesion:
        return [m for _, m in sesion.get("_flashes", [])]


# --- Servicio --------------------------------------------------------------

def test_interpreta_el_dte_generado_por_el_sistema():
    contenido, datos = _dte()
    dte = interpretar_dte(contenido)

    assert dte["tipo"] == "33"
    assert dte["tipo_nombre"] == "Factura electrónica"
    assert dte["folio"] == "15"
    assert dte["emisor"]["razon_social"] == "Facturaciones SpA"
    assert dte["receptor"]["rut"] == datos["receptor"]["rut"]
    assert dte["detalle"][0]["nombre"] == "Asesoría ñandú"   # ISO-8859-1
    assert dte["totales"]["total"] == datos["totales"]["monto_total"]
    assert dte["totales"]["iva"] == datos["totales"]["iva"]
    assert dte["timbrado"] is False and dte["firmado"] is False


def test_interpreta_dte_con_espacio_de_nombres_y_timbre():
    contenido = (
        b'<?xml version="1.0"?><DTE xmlns="http://www.sii.cl/SiiDte" version="1.0">'
        b'<Documento ID="x"><Encabezado><IdDoc><TipoDTE>61</TipoDTE>'
        b'<Folio>9</Folio></IdDoc><Totales><MntTotal>100</MntTotal></Totales>'
        b'</Encabezado><Detalle><NmbItem>Anula</NmbItem></Detalle>'
        b'<Referencia><TpoDocRef>33</TpoDocRef><FolioRef>15</FolioRef></Referencia>'
        b'<TED version="1.0"/></Documento></DTE>'
    )
    dte = interpretar_dte(contenido)

    assert dte["tipo_nombre"] == "Nota de crédito electrónica"
    assert dte["timbrado"] is True
    assert dte["totales"]["total"] == 100
    assert dte["referencias"][0]["tipo_nombre"] == "Factura electrónica"


def test_xml_que_no_es_dte_devuelve_none():
    assert interpretar_dte(b"<pedido><item/></pedido>") is None


@pytest.mark.parametrize("contenido", [
    b"<no-cerrado>",
    b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "a">]><x>&e;</x>',
])
def test_rechaza_xml_invalido_o_con_dtd(contenido):
    with pytest.raises(ErrorVistaXML):
        interpretar_dte(contenido)


def test_formato_indenta_y_conserva_declaracion():
    contenido, _ = _dte()
    formato = formatear_xml(contenido)

    assert formato["coloreado"] is True
    assert formato["texto"].startswith('<?xml version="1.0" encoding="ISO-8859-1"?>')
    assert "\n  <Documento" in formato["texto"]
    assert "Asesoría ñandú" in formato["texto"]
    tipos = {tipo for linea in formato["lineas"] for tipo, _ in linea}
    assert {"nombre", "atributo", "valor", "comentario"} <= tipos


def test_formato_de_xml_no_indentable_se_muestra_tal_cual():
    formato = formatear_xml(b"<a>sin cerrar")
    assert formato["texto"] == "<a>sin cerrar"


# --- Rutas -------------------------------------------------------------------

def _solicitud():
    return dict(SOLICITUD, public_id=PID, estado_nombre="En revisión",
                origen_nombre="Manual", version=3, emisor_id=1, id=5)


def _versiones(estado="EN_REVISION"):
    _, datos = _dte()
    return [{"id": 15, "version": 2, "estado": estado, "tipo_dte": 33,
             "datos": datos}], None


def test_anonimo_redirige_al_login(client):
    respuesta = client.get(VISTA)
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_origen_desconocido_es_404(client, login_como):
    login_como("Emisor")
    assert client.get(VISTA + "?origen=otro").status_code == 404


def test_emisor_no_ve_el_archivo_sii(client, login_como):
    login_como("Emisor")
    assert client.get(VISTA + "?origen=sii").status_code == 403


def test_lector_no_accede(client, login_como):
    login_como("Lector")
    assert client.get(VISTA).status_code == 403


@pytest.mark.parametrize("estado,borrador", [
    ("EN_REVISION", True), ("APROBADA", False),
])
def test_borrador_muestra_diseno_y_formato(client, app, login_como, monkeypatch,
                                           estado, borrador):
    app.config.update(CONFIG_EMISOR)
    monkeypatch.setattr("app.solicitudes.routes.obtener_solicitud_autorizada",
                        lambda pid: _solicitud())
    monkeypatch.setattr("app.solicitudes.routes.listar_versiones",
                        lambda sid: _versiones(estado))
    login_como("Emisor")

    respuesta = client.get(VISTA)
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "FACTURA ELECTRÓNICA" in html          # recuadro del diseño
    assert "N° 15" in html
    assert "Formato XML" in html
    assert 'class="xml-nombre">DTE</span>' in html
    assert ("BORRADOR" in html) is borrador


def test_borrador_sin_datos_del_emisor_avisa(client, app, login_como, monkeypatch):
    app.config.update({clave: "" for clave in CONFIG_EMISOR})
    monkeypatch.setattr("app.solicitudes.routes.obtener_solicitud_autorizada",
                        lambda pid: _solicitud())
    monkeypatch.setattr("app.solicitudes.routes.listar_versiones",
                        lambda sid: _versiones())
    login_como("Administrador")

    respuesta = client.get(VISTA)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/solicitudes/{PID}/factura")
    assert any("EMPRESA_" in m for m in flashes(client))


def test_xml_cargado_se_escapa_y_se_audita(client, login_como, monkeypatch, tmp_path):
    archivo = tmp_path / "x.xml"
    archivo.write_bytes(b"<nota><texto>&lt;script&gt;alert(1)&lt;/script&gt;</texto></nota>")
    auditorias = []
    monkeypatch.setattr(
        "app.solicitudes.routes.obtener_xml_autorizado",
        lambda actor_id, public_id: (
            {"id": actor_id}, {"id": 5},
            {"id": 8, "nombre_original": "nota.xml", "sha256": "f" * 64},
            str(archivo),
        ),
    )
    monkeypatch.setattr("app.solicitudes.routes._auditar_vista",
                        lambda actor_id, detalle: auditorias.append(detalle))
    login_como("Emisor", user_id=4)

    respuesta = client.get(VISTA + "?origen=cargado")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "<script>alert(1)" not in html
    assert "no tiene la estructura de un DTE" in html
    assert auditorias == [{
        "solicitud_afectada_id": 5, "public_id": PID, "registro_xml_id": 8,
        "origen": "XML_CARGADO", "sha256": "f" * 64,
    }]


def test_xml_cargado_inexistente_vuelve_al_detalle(client, login_como, monkeypatch):
    def sin_xml(actor_id, public_id):
        raise ErrorArchivoXML("La solicitud todavía no tiene XML.")

    monkeypatch.setattr("app.solicitudes.routes.obtener_xml_autorizado", sin_xml)
    login_como("Emisor")

    respuesta = client.get(VISTA + "?origen=cargado")

    assert respuesta.headers["Location"].endswith(f"/solicitudes/{PID}")
    assert "La solicitud todavía no tiene XML." in flashes(client)
