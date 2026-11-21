"""Vista previa de un XML de factura: diseño (DTE) y formato (código).

- interpretar_dte(): extrae los datos de un DTE del SII (con o sin espacio
  de nombres, firmado o no) para dibujar la factura. Devuelve None si el
  XML no es un DTE reconocible (p. ej. un XML cargado de otro tipo).
- formatear_xml(): devuelve el XML indentado y dividido en piezas
  (etiqueta, atributo, valor, texto, comentario) para colorearlo en la
  plantilla. Las piezas son texto plano: Jinja las escapa al mostrarlas.

Todo el análisis usa defusedxml (sin DTD, entidades ni recursos externos).
"""
import re

from defusedxml import ElementTree
from defusedxml import minidom
from defusedxml.common import DefusedXmlException

# Sobre este tamaño el código se muestra sin indentar ni colorear.
LIMITE_FORMATO = 1024 * 1024

TIPOS_DTE = {
    "33": "Factura electrónica",
    "34": "Factura no afecta o exenta electrónica",
    "39": "Boleta electrónica",
    "41": "Boleta exenta electrónica",
    "46": "Factura de compra electrónica",
    "52": "Guía de despacho electrónica",
    "56": "Nota de débito electrónica",
    "61": "Nota de crédito electrónica",
}

TIPOS_REFERENCIA = {
    "801": "Orden de compra",
    "802": "Nota de pedido",
    "803": "Contrato",
    "804": "Resolución",
    "HES": "Hoja de entrada de servicio",
    "33": "Factura electrónica",
    "34": "Factura exenta electrónica",
    "52": "Guía de despacho electrónica",
    "56": "Nota de débito electrónica",
    "61": "Nota de crédito electrónica",
}


class ErrorVistaXML(Exception):
    pass


def decodificar(contenido):
    """Texto del XML según la codificación que declara (por defecto UTF-8)."""
    if isinstance(contenido, str):
        return contenido

    cabecera = contenido[:200].decode("ascii", errors="ignore")
    declarada = re.search(r"encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']", cabecera)
    codificaciones = [declarada.group(1)] if declarada else []
    codificaciones += ["utf-8", "iso-8859-1"]

    for codificacion in codificaciones:
        try:
            return contenido.decode(codificacion)
        except (LookupError, UnicodeDecodeError):
            continue
    return contenido.decode("utf-8", errors="replace")


def _local(etiqueta):
    """Nombre sin espacio de nombres: '{http://www.sii.cl/SiiDte}DTE' -> 'DTE'."""
    return etiqueta.rsplit("}", 1)[-1] if isinstance(etiqueta, str) else ""


def _hijo(nodo, nombre):
    if nodo is None:
        return None
    for elemento in nodo:
        if _local(elemento.tag) == nombre:
            return elemento
    return None


def _hijos(nodo, nombre):
    if nodo is None:
        return []
    return [e for e in nodo if _local(e.tag) == nombre]


def _texto(nodo, *nombres):
    """Texto del primer hijo existente entre los nombres dados ('' si no hay)."""
    for nombre in nombres:
        elemento = _hijo(nodo, nombre)
        if elemento is not None and elemento.text and elemento.text.strip():
            return elemento.text.strip()
    return ""


def _buscar(raiz, nombre):
    for elemento in raiz.iter():
        if _local(elemento.tag) == nombre:
            return elemento
    return None


def _entero(valor):
    try:
        return int(round(float(valor)))
    except (TypeError, ValueError):
        return None


def interpretar_dte(contenido):
    try:
        raiz = ElementTree.fromstring(
            contenido, forbid_dtd=True, forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise ErrorVistaXML("El archivo no es XML válido.") from exc

    documento = _buscar(raiz, "Documento")
    if documento is None:
        documento = _buscar(raiz, "Exportaciones")
    encabezado = _hijo(documento, "Encabezado")
    if documento is None or encabezado is None:
        return None

    id_doc = _hijo(encabezado, "IdDoc")
    emisor = _hijo(encabezado, "Emisor")
    receptor = _hijo(encabezado, "Receptor")
    totales = _hijo(encabezado, "Totales")
    tipo = _texto(id_doc, "TipoDTE")

    return {
        "tipo": tipo,
        "tipo_nombre": TIPOS_DTE.get(tipo, f"Documento tributario {tipo}".strip()),
        "folio": _texto(id_doc, "Folio"),
        "fecha_emision": _texto(id_doc, "FchEmis"),
        "fecha_vencimiento": _texto(id_doc, "FchVenc"),
        "emisor": {
            "rut": _texto(emisor, "RUTEmisor"),
            "razon_social": _texto(emisor, "RznSoc", "RznSocEmisor"),
            "giro": _texto(emisor, "GiroEmis", "GiroEmisor"),
            "acteco": [e.text.strip() for e in _hijos(emisor, "Acteco") if e.text],
            "direccion": _texto(emisor, "DirOrigen"),
            "comuna": _texto(emisor, "CmnaOrigen"),
            "ciudad": _texto(emisor, "CiudadOrigen"),
        },
        "receptor": {
            "rut": _texto(receptor, "RUTRecep"),
            "razon_social": _texto(receptor, "RznSocRecep"),
            "giro": _texto(receptor, "GiroRecep"),
            "direccion": _texto(receptor, "DirRecep"),
            "comuna": _texto(receptor, "CmnaRecep"),
            "ciudad": _texto(receptor, "CiudadRecep"),
            "correo": _texto(receptor, "CorreoRecep"),
            "contacto": _texto(receptor, "Contacto"),
        },
        "totales": {
            "neto": _entero(_texto(totales, "MntNeto")),
            "exento": _entero(_texto(totales, "MntExe")),
            "tasa_iva": _texto(totales, "TasaIVA"),
            "iva": _entero(_texto(totales, "IVA")),
            "total": _entero(_texto(totales, "MntTotal")),
        },
        "detalle": [
            {
                "linea": _texto(linea, "NroLinDet"),
                "nombre": _texto(linea, "NmbItem"),
                "descripcion": _texto(linea, "DscItem"),
                "cantidad": _texto(linea, "QtyItem"),
                "unidad": _texto(linea, "UnmdItem"),
                "precio": _entero(_texto(linea, "PrcItem")),
                "descuento": _entero(_texto(linea, "DescuentoMonto")),
                "exento": _texto(linea, "IndExe") == "1",
                "monto": _entero(_texto(linea, "MontoItem")),
            }
            for linea in _hijos(documento, "Detalle")
        ],
        "referencias": [
            {
                "tipo": _texto(ref, "TpoDocRef"),
                "tipo_nombre": TIPOS_REFERENCIA.get(
                    _texto(ref, "TpoDocRef"), _texto(ref, "TpoDocRef")
                ),
                "folio": _texto(ref, "FolioRef"),
                "fecha": _texto(ref, "FchRef"),
                "razon": _texto(ref, "RazonRef"),
            }
            for ref in _hijos(documento, "Referencia")
        ],
        "timbrado": _buscar(raiz, "TED") is not None,
        "firmado": _buscar(raiz, "Signature") is not None,
    }


# --- Formato (código fuente) ---------------------------------------------

_PIEZA = re.compile(
    r"(?P<comentario><!--.*?-->)"
    r"|(?P<declaracion><\?.*?\?>)"
    r"|(?P<cdata><!\[CDATA\[.*?\]\]>)"
    r"|(?P<etiqueta></?[^<>]+?/?>)"
    r"|(?P<texto>[^<]+)"
    r"|(?P<otro><)",
    re.DOTALL,
)
_ETIQUETA = re.compile(r"^(</?)([^\s/>]+)(.*?)(/?>)$", re.DOTALL)
_ATRIBUTO = re.compile(r"(\s+)([^\s=]+)(\s*=\s*)(\"[^\"]*\"|'[^']*')")


def _piezas_etiqueta(etiqueta):
    partes = _ETIQUETA.match(etiqueta)
    if not partes:
        return [("texto", etiqueta)]

    apertura, nombre, atributos, cierre = partes.groups()
    piezas = [("simbolo", apertura), ("nombre", nombre)]
    posicion = 0
    for atributo in _ATRIBUTO.finditer(atributos):
        if atributo.start() > posicion:
            piezas.append(("texto", atributos[posicion:atributo.start()]))
        espacio, clave, igual, valor = atributo.groups()
        piezas += [
            ("texto", espacio), ("atributo", clave),
            ("simbolo", igual), ("valor", valor),
        ]
        posicion = atributo.end()
    if posicion < len(atributos):
        piezas.append(("texto", atributos[posicion:]))
    piezas.append(("simbolo", cierre))
    return piezas


def _indentar(contenido, texto):
    """Indenta con minidom (seguro) conservando la declaración original.

    Se analizan los bytes originales para que el analizador respete la
    codificación declarada (los DTE del SII usan ISO-8859-1).
    """
    documento = minidom.parseString(
        contenido, forbid_dtd=True, forbid_entities=True,
        forbid_external=True,
    )
    bonito = documento.toprettyxml(indent="  ")
    lineas = [linea for linea in bonito.splitlines() if linea.strip()]
    # minidom antepone su propia declaración: se reemplaza por la original.
    if lineas and lineas[0].startswith("<?xml"):
        lineas = lineas[1:]
    declaracion = re.match(r"\s*(<\?xml[^>]*\?>)", texto)
    if declaracion:
        lineas.insert(0, declaracion.group(1))
    return "\n".join(lineas)


def formatear_xml(contenido):
    """Devuelve {"texto", "lineas": [[(tipo, texto), ...], ...], "coloreado"}."""
    texto = decodificar(contenido).lstrip("﻿")

    if len(texto) > LIMITE_FORMATO:
        return {
            "texto": texto,
            "lineas": [[("texto", linea)] for linea in texto.splitlines()],
            "coloreado": False,
        }

    try:
        texto = _indentar(contenido, texto)
    except Exception:  # XML no indentable: se muestra tal cual.
        pass

    lineas = []
    for linea in texto.splitlines():
        piezas = []
        for coincidencia in _PIEZA.finditer(linea):
            tipo = coincidencia.lastgroup
            valor = coincidencia.group(tipo)
            if tipo == "etiqueta":
                piezas += _piezas_etiqueta(valor)
            else:
                piezas.append(("texto" if tipo == "otro" else tipo, valor))
        lineas.append(piezas)

    return {"texto": texto, "lineas": lineas, "coloreado": True}
