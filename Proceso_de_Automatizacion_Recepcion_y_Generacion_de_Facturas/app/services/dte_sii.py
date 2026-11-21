"""Archivo DTE (XML) para el SII a partir de una versión aprobada.

Estructura según el formato DTE v1.0 del SII (Factura electrónica 33 y
Factura exenta 34): Encabezado (IdDoc, Emisor, Receptor, Totales),
Detalle y Referencia a la orden de compra (TpoDocRef 801).

Límite del MVP: el archivo queda SIN firma electrónica ni timbre (TED).
Para emitirlo ante el SII se debe firmar con el certificado digital de
la empresa y un folio autorizado (CAF). El Folio aquí es provisional.
"""
import re
from xml.etree import ElementTree as ET

from .registros_xml import ErrorArchivoXML, validar_xml
from .validaciones import ErrorValidacion, normalizar_rut

# Largo máximo de cada campo en el esquema del SII.
LARGOS = {
    "RznSoc": 100, "GiroEmis": 80, "DirOrigen": 70, "CmnaOrigen": 20,
    "RznSocRecep": 100, "GiroRecep": 40, "CorreoRecep": 80,
    "DirRecep": 70, "NmbItem": 80, "DscItem": 1000, "FolioRef": 18,
}

CAMPOS_EMISOR = {
    "EMPRESA_RUT": "rut",
    "EMPRESA_RAZON_SOCIAL": "razon_social",
    "EMPRESA_GIRO": "giro",
    "EMPRESA_ACTECO": "acteco",
    "EMPRESA_DIRECCION": "direccion",
    "EMPRESA_COMUNA": "comuna",
}

NOTA = (
    " Generado por Facturaciones SpA. Documento SIN firma electronica "
    "ni timbre (TED); folio provisional. Debe firmarse con certificado "
    "digital y folio CAF antes de enviarse al SII. "
)


class ErrorDTE(Exception):
    pass


def datos_emisor(config):
    faltan = [c for c in CAMPOS_EMISOR if not str(config.get(c) or "").strip()]
    if faltan:
        raise ErrorDTE(
            "Faltan los datos del emisor en .env: " + ", ".join(faltan) + "."
        )

    emisor = {
        clave: str(config.get(variable)).strip()
        for variable, clave in CAMPOS_EMISOR.items()
    }

    try:
        emisor["rut"] = normalizar_rut(emisor["rut"])
    except ErrorValidacion as exc:
        raise ErrorDTE(f"EMPRESA_RUT no es válido: {exc}") from exc

    if not re.fullmatch(r"[0-9]{5,6}", emisor["acteco"]):
        raise ErrorDTE("EMPRESA_ACTECO debe ser el código SII de 5 o 6 dígitos.")

    return emisor


def advertencias(datos):
    """Campos que exceden el largo del SII y se recortarán en el DTE."""
    revisar = {
        "RznSocRecep": datos["receptor"]["razon_social"],
        "GiroRecep": datos["receptor"]["giro"],
        "DirRecep": datos["receptor"]["direccion"],
        "CorreoRecep": datos["receptor"].get("email") or "",
        "NmbItem": datos["detalle"]["concepto"],
        "FolioRef": datos["detalle"].get("nro_orden_compra") or "",
    }
    avisos = []
    for campo, valor in revisar.items():
        if campo == "NmbItem":
            continue  # el concepto completo va en DscItem
        if len(valor) > LARGOS[campo]:
            avisos.append(
                f"{campo} supera {LARGOS[campo]} caracteres y se recortará."
            )
    diferencia = datos["totales"].get("diferencia_redondeo", 0)
    if diferencia:
        avisos.append(
            f"Por redondeo del IVA el total difiere en ${diferencia} "
            f"del monto bruto solicitado."
        )
    return avisos


def _hijo(padre, etiqueta, valor):
    elemento = ET.SubElement(padre, etiqueta)
    texto = str(valor)
    if etiqueta in LARGOS:
        texto = texto[:LARGOS[etiqueta]]
    elemento.text = texto
    return elemento


def construir_dte(datos, emisor, folio):
    """Devuelve el XML (bytes ISO-8859-1) del DTE sin firmar."""
    totales = datos["totales"]
    tipo = int(totales["tipo_dte"])

    if tipo not in (33, 34):
        raise ErrorDTE("Tipo de documento no soportado.")
    if int(folio) <= 0:
        raise ErrorDTE("El folio debe ser positivo.")

    receptor = datos["receptor"]
    detalle = datos["detalle"]

    raiz = ET.Element("DTE", {"version": "1.0"})
    documento = ET.SubElement(raiz, "Documento", {"ID": f"F{folio}T{tipo}"})
    encabezado = ET.SubElement(documento, "Encabezado")

    id_doc = ET.SubElement(encabezado, "IdDoc")
    _hijo(id_doc, "TipoDTE", tipo)
    _hijo(id_doc, "Folio", int(folio))
    _hijo(id_doc, "FchEmis", datos["fecha_emision"])

    nodo_emisor = ET.SubElement(encabezado, "Emisor")
    _hijo(nodo_emisor, "RUTEmisor", emisor["rut"])
    _hijo(nodo_emisor, "RznSoc", emisor["razon_social"])
    _hijo(nodo_emisor, "GiroEmis", emisor["giro"])
    _hijo(nodo_emisor, "Acteco", emisor["acteco"])
    _hijo(nodo_emisor, "DirOrigen", emisor["direccion"])
    _hijo(nodo_emisor, "CmnaOrigen", emisor["comuna"])

    nodo_receptor = ET.SubElement(encabezado, "Receptor")
    _hijo(nodo_receptor, "RUTRecep", receptor["rut"])
    _hijo(nodo_receptor, "RznSocRecep", receptor["razon_social"])
    _hijo(nodo_receptor, "GiroRecep", receptor["giro"])
    if receptor.get("email"):
        _hijo(nodo_receptor, "CorreoRecep", receptor["email"])
    _hijo(nodo_receptor, "DirRecep", receptor["direccion"])

    nodo_totales = ET.SubElement(encabezado, "Totales")
    if tipo == 33:
        _hijo(nodo_totales, "MntNeto", totales["monto_neto"])
        _hijo(nodo_totales, "TasaIVA", totales["tasa_iva"])
        _hijo(nodo_totales, "IVA", totales["iva"])
        precio = totales["monto_neto"]
    else:
        _hijo(nodo_totales, "MntExe", totales["monto_exento"])
        precio = totales["monto_exento"]
    _hijo(nodo_totales, "MntTotal", totales["monto_total"])

    linea = ET.SubElement(documento, "Detalle")
    _hijo(linea, "NroLinDet", 1)
    _hijo(linea, "NmbItem", detalle["concepto"])
    if len(detalle["concepto"]) > LARGOS["NmbItem"]:
        _hijo(linea, "DscItem", detalle["concepto"])
    _hijo(linea, "QtyItem", 1)
    _hijo(linea, "PrcItem", precio)
    _hijo(linea, "MontoItem", precio)

    if detalle.get("nro_orden_compra"):
        referencia = ET.SubElement(documento, "Referencia")
        _hijo(referencia, "NroLinRef", 1)
        _hijo(referencia, "TpoDocRef", 801)
        _hijo(referencia, "FolioRef", detalle["nro_orden_compra"])
        _hijo(referencia, "FchRef", datos["fecha_emision"])

    cuerpo = ET.tostring(raiz, encoding="ISO-8859-1", xml_declaration=False)
    contenido = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>\n'
        + f"<!--{NOTA}-->\n".encode("ascii")
        + cuerpo
        + b"\n"
    )

    try:
        validar_xml(contenido)
    except ErrorArchivoXML as exc:
        raise ErrorDTE("El DTE generado no es XML válido.") from exc

    return contenido
