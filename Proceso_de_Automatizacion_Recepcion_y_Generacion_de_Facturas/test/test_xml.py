import io

import pytest
from werkzeug.datastructures import FileStorage

from app.services.registros_xml import ErrorArchivoXML, guardar_xml, validar_xml

XML_VALIDO = b'<?xml version="1.0" encoding="ISO-8859-1"?><DTE><Documento/></DTE>'


def test_xml_valido_se_acepta():
    validar_xml(XML_VALIDO)


@pytest.mark.parametrize("contenido", [
    b"",
    b"<a><b></a>",
    # XXE: entidad externa
    b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM '
    b'"file:///etc/passwd">]><a>&x;</a>',
    # Expansion de entidades (billion laughs)
    b'<!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><l>&b;</l>',
    # DTD externa
    b'<!DOCTYPE a SYSTEM "http://ejemplo.invalid/a.dtd"><a/>',
])
def test_xml_peligroso_o_invalido_se_rechaza(contenido):
    with pytest.raises(ErrorArchivoXML):
        validar_xml(contenido)


def archivo(nombre, contenido=XML_VALIDO):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre)


@pytest.mark.parametrize("nombre", ["", "factura.pdf", "factura.xml.exe"])
def test_guardar_xml_rechaza_nombres(app, nombre):
    with app.app_context(), pytest.raises(ErrorArchivoXML):
        guardar_xml(1, "a" * 32, archivo(nombre))


def test_guardar_xml_rechaza_tamano(app):
    app.config["MAX_XML_UPLOAD_BYTES"] = 10
    with app.app_context(), pytest.raises(ErrorArchivoXML, match="límite"):
        guardar_xml(1, "a" * 32, archivo("f.xml"))
