"""Clasificación y extracción de datos de un correo de facturación.

Funciones puras (sin BD ni red) para poder probarlas de forma aislada.

Formato recomendado para los clientes (una línea por dato):

    RUT: 12.345.678-5
    Concepto: Servicios de asesoría octubre 2026
    Monto: $980.000            (bruto; "1.000.000 + IVA" se toma como neto)
    Fecha de emisión: 16-10-2026
    Afectación: Afecta | Exenta
    Orden de compra: 4500012345

También se acepta un adjunto .xml con etiquetas RUT, Concepto,
MontoBruto, FechaEmision, TipoAfectacion y OrdenCompra (o sus
equivalentes DTE: RUTRecep, NmbItem, MntTotal, FchEmis). Si un dato
viene en ambos, prevalece el XML y se deja una alerta.
"""
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from .validaciones import ErrorValidacion, normalizar_rut

PATRON_FACTURACION = re.compile(
    r"\b(factur\w*|orden\s+de\s+compra|dte)\b"
)
PATRON_RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK]\b")
LIMITE_XML = 1024 * 1024

ALIAS = {
    "rut": ("rut", "rut receptor", "rut cliente", "rut empresa"),
    "concepto": (
        "concepto", "glosa", "detalle", "descripcion", "servicio", "item",
    ),
    "monto_bruto": (
        "monto", "monto bruto", "monto total", "total", "valor",
        "importe", "monto a facturar", "total a facturar",
    ),
    "monto_neto": ("monto neto", "neto", "valor neto", "total neto"),
    "fecha_emision": (
        "fecha", "fecha emision", "fecha de emision", "fecha factura",
        "fecha de facturacion",
    ),
    "tipo_afectacion": (
        "afectacion", "tipo afectacion", "tipo de afectacion",
        "afecta o exenta", "tipo", "iva",
    ),
    "nro_orden_compra": (
        "orden de compra", "oc", "nro oc", "n oc", "no oc", "numero oc",
        "nro orden de compra", "numero de orden de compra",
    ),
}
CAMPO_POR_ALIAS = {a: campo for campo, alias in ALIAS.items() for a in alias}

ETIQUETAS_XML = {
    "rut": "rut", "rutrecep": "rut",
    "concepto": "concepto", "nmbitem": "concepto",
    "montobruto": "monto_bruto", "mnttotal": "monto_bruto",
    "fechaemision": "fecha_emision", "fchemis": "fecha_emision",
    "tipoafectacion": "tipo_afectacion",
    "ordencompra": "nro_orden_compra",
}

CAMPOS = (
    "rut", "concepto", "monto_bruto", "fecha_emision",
    "tipo_afectacion", "nro_orden_compra",
)


def normalizar_texto(texto):
    sin_tildes = unicodedata.normalize("NFKD", str(texto or ""))
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def es_facturacion(asunto, cuerpo):
    return bool(PATRON_FACTURACION.search(
        normalizar_texto(f"{asunto}\n{cuerpo}")
    ))


def es_automatico(mensaje, origen_propio=("X-Facturaciones-Origen",)):
    """Respuestas automáticas, listas, rebotes o avisos propios."""
    if any(mensaje.get(c) for c in origen_propio):
        return True
    auto = str(mensaje.get("Auto-Submitted") or "no").strip().lower()
    if auto != "no":
        return True
    precedencia = str(mensaje.get("Precedence") or "").strip().lower()
    if precedencia in {"bulk", "junk", "list", "auto_reply"}:
        return True
    if mensaje.get("List-Id") or mensaje.get("X-Autoreply"):
        return True
    remitente = normalizar_texto(mensaje.get("From"))
    return "mailer-daemon" in remitente or "postmaster@" in remitente


def verificacion_remitente(mensaje):
    """Lee Authentication-Results (SPF/DKIM/DMARC) si el servidor lo agrega.

    Devuelve "fallida", "aprobada" o "desconocida".
    """
    resultados = " ".join(
        str(v) for v in (mensaje.get_all("Authentication-Results") or [])
    ).lower()
    if not resultados:
        return "desconocida"
    if re.search(r"\b(dmarc|spf)=fail\b", resultados):
        return "fallida"
    if re.search(r"\b(dmarc|spf|dkim)=pass\b", resultados):
        return "aprobada"
    return "desconocida"


class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes, self._ignorar = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self._ignorar += 1
        elif tag in {"br", "p", "div", "tr", "li"}:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"} and self._ignorar:
            self._ignorar -= 1

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)


def html_a_texto(html):
    parser = _TextoHTML()
    parser.feed(html)
    return "".join(parser.partes)


def texto_del_mensaje(mensaje):
    planos, html = [], []
    for parte in mensaje.walk():
        if parte.is_multipart() or parte.get_content_disposition() == "attachment":
            continue
        tipo = parte.get_content_type()
        try:
            contenido = parte.get_content()
        except (LookupError, UnicodeError):
            continue
        if tipo == "text/plain":
            planos.append(contenido)
        elif tipo == "text/html":
            html.append(html_a_texto(contenido))
    texto = "\n".join(planos) if any(p.strip() for p in planos) else "\n".join(html)
    return "\n".join(
        linea for linea in texto.splitlines()
        if not linea.lstrip().startswith(">")
    )


def adjuntos_xml(mensaje, limite=LIMITE_XML):
    adjuntos = []
    for parte in mensaje.iter_attachments():
        nombre = parte.get_filename() or ""
        if not (
            nombre.lower().endswith(".xml")
            or parte.get_content_type() in {"application/xml", "text/xml"}
        ):
            continue
        contenido = parte.get_payload(decode=True) or b""
        if 0 < len(contenido) <= limite:
            adjuntos.append((nombre, contenido))
    return adjuntos


def _etiqueta(texto):
    texto = normalizar_texto(texto)
    texto = re.sub(r"[°º.#\-_*•()]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def campos_desde_texto(texto):
    encontrados = {}
    for linea in texto.splitlines():
        coincidencia = re.match(r"^\s*([^:=\n]{2,40}?)\s*[:=]\s*(.+?)\s*$", linea)
        if not coincidencia:
            continue
        campo = CAMPO_POR_ALIAS.get(_etiqueta(coincidencia.group(1)))
        if campo and campo not in encontrados:
            encontrados[campo] = coincidencia.group(2)

    if "rut" not in encontrados:
        for candidato in PATRON_RUT.findall(texto):
            try:
                normalizar_rut(candidato)
            except ErrorValidacion:
                continue
            encontrados["rut"] = candidato
            break

    return encontrados


def campos_desde_xml(contenido):
    try:
        raiz = ElementTree.fromstring(
            contenido, forbid_dtd=True, forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException):
        return None

    encontrados = {}
    for elemento in raiz.iter():
        nombre = str(elemento.tag).rsplit("}", 1)[-1].lower()
        campo = ETIQUETAS_XML.get(nombre)
        texto = (elemento.text or "").strip()
        if campo and texto and campo not in encontrados:
            encontrados[campo] = texto
    return encontrados


def normalizar_monto(valor):
    """'$ 1.234.567' -> ('1234567', es_neto). None si no es válido."""
    texto = normalizar_texto(valor)
    es_neto = bool(re.search(r"(\+|mas)\s*iva|\bneto\b", texto))
    texto = re.sub(r"(\+|mas)\s*iva|\bneto\b|\bclp\b|\bpesos\b|\$", " ", texto)
    texto = texto.replace(" ", "")
    texto = re.sub(r",0+$", "", texto)

    if re.fullmatch(r"[0-9]{1,3}(\.[0-9]{3})+", texto):
        texto = texto.replace(".", "")
    if not re.fullmatch(r"[0-9]{1,14}", texto) or int(texto) <= 0:
        return None, es_neto
    return str(int(texto)), es_neto


def normalizar_fecha(valor):
    texto = str(valor or "").strip()
    for patron, orden in (
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "amd"),
        (r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", "dma"),
    ):
        coincidencia = re.fullmatch(patron, texto)
        if coincidencia:
            a, b, c = (int(g) for g in coincidencia.groups())
            anio, mes, dia = (a, b, c) if orden == "amd" else (c, b, a)
            try:
                return date(anio, mes, dia).isoformat()
            except ValueError:
                return None
    return None


def normalizar_afectacion(valor):
    texto = normalizar_texto(valor)
    if re.search(r"\bexent", texto):
        return "EXENTA"
    if re.search(r"\bafect", texto):
        return "AFECTA"
    return None


def extraer_datos(mensaje, hoy=None):
    """Devuelve (datos, alertas). datos usa las claves de CAMPOS."""
    hoy = hoy or date.today()
    alertas = []

    desde_texto = campos_desde_texto(texto_del_mensaje(mensaje))
    desde_xml = {}
    for nombre, contenido in adjuntos_xml(mensaje):
        campos = campos_desde_xml(contenido)
        if campos is None:
            alertas.append(f"El adjunto {nombre} no es XML válido; se ignoró.")
        elif not desde_xml:
            desde_xml = campos

    crudos = dict(desde_texto)
    for campo, valor in desde_xml.items():
        if campo in crudos and normalizar_texto(crudos[campo]) != normalizar_texto(valor):
            alertas.append(
                f"El dato '{campo}' difiere entre el cuerpo y el XML; "
                f"se usó el del XML."
            )
        crudos[campo] = valor

    datos = {campo: None for campo in CAMPOS}

    if crudos.get("rut"):
        try:
            datos["rut"] = normalizar_rut(crudos["rut"])
        except ErrorValidacion:
            alertas.append("El RUT indicado en el correo no es válido.")

    if crudos.get("concepto"):
        datos["concepto"] = re.sub(r"\s+", " ", crudos["concepto"]).strip()[:500]

    neto_crudo = crudos.get("monto_neto")
    if crudos.get("monto_bruto"):
        monto, es_neto = normalizar_monto(crudos["monto_bruto"])
        if monto is None:
            alertas.append("El monto indicado no es un número válido.")
        elif es_neto:
            neto_crudo = monto
        else:
            datos["monto_bruto"] = monto

    if datos["monto_bruto"] is None and neto_crudo:
        neto, _ = normalizar_monto(neto_crudo)
        if neto is None:
            alertas.append("El monto neto indicado no es un número válido.")
        else:
            bruto = (Decimal(neto) * Decimal("1.19")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
            datos["monto_bruto"] = str(bruto)
            alertas.append(
                f"El monto se informó neto ({neto}); se calculó el bruto "
                f"con IVA ({bruto})."
            )

    if crudos.get("fecha_emision"):
        datos["fecha_emision"] = normalizar_fecha(crudos["fecha_emision"])
        if datos["fecha_emision"] is None:
            alertas.append("La fecha indicada no es válida; se usó la de hoy.")
    if datos["fecha_emision"] is None:
        if not crudos.get("fecha_emision"):
            alertas.append("El correo no indica fecha; se usó la de hoy.")
        datos["fecha_emision"] = hoy.isoformat()

    datos["tipo_afectacion"] = normalizar_afectacion(
        crudos.get("tipo_afectacion")
    )
    if datos["tipo_afectacion"] is None:
        datos["tipo_afectacion"] = "AFECTA"
        alertas.append("No se indicó afectación; se asumió AFECTA (con IVA).")

    if crudos.get("nro_orden_compra"):
        datos["nro_orden_compra"] = crudos["nro_orden_compra"].strip()[:40]

    return datos, alertas
