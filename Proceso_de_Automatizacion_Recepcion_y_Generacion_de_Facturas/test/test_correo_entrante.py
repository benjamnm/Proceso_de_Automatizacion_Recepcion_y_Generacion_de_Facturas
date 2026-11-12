import hashlib
import imaplib
import json
import ssl
from datetime import date
from decimal import Decimal
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest

from app.services import correo_entrante
from app.services.correo_entrante import (
    ErrorCorreoEntrante,
    conectar,
    descargar_correos,
    metadatos,
    procesar_correo,
    validar_configuracion_imap,
)

BASE = {
    "IMAP_HOST": "imap.ejemplo.cl", "IMAP_PORT": 993, "IMAP_SECURITY": "ssl",
    "IMAP_USER": "facturas@ejemplo.cl", "IMAP_PASSWORD": "secreta",
    "IMAP_MAILBOX": "INBOX", "IMAP_TIMEOUT": 5, "IMAP_MAX_MENSAJES": 10,
    "IMAP_MAX_BYTES": 50_000,
}


def cfg(**cambios):
    return validar_configuracion_imap(dict(BASE, **cambios))


def mensaje(asunto, cuerpo, remitente="prueba@ejemplo.com", **cabeceras):
    m = EmailMessage()
    m["From"] = remitente
    m["To"] = "facturas@ejemplo.cl"
    m["Subject"] = asunto
    m["Message-ID"] = f"<{abs(hash(asunto + cuerpo))}@ejemplo.com>"
    for nombre, valor in cabeceras.items():
        m[nombre.replace("_", "-")] = valor
    m.set_content(cuerpo)
    return m


@pytest.mark.parametrize("cambios", [
    {"IMAP_HOST": ""}, {"IMAP_USER": ""}, {"IMAP_SECURITY": "tls"},
    {"IMAP_PORT": "x"}, {"IMAP_MAILBOX": 'INBOX"; DELETE'},
    {"IMAP_SECURITY": "none"},   # sin cifrado fuera de localhost
])
def test_configuracion_imap_invalida(cambios):
    with pytest.raises(ErrorCorreoEntrante) as exc:
        cfg(**cambios)
    assert exc.value.codigo == "CONFIGURACION"


def test_sin_cifrado_solo_en_localhost():
    assert cfg(IMAP_HOST="localhost", IMAP_SECURITY="none")["seguridad"] == "none"


class IMAPFalso:
    def __init__(self, host, puerto, ssl_context=None, timeout=None):
        self.host, self.puerto, self.ssl_context = host, puerto, ssl_context
        self.llamadas = []
        IMAPFalso.ultima = self

    def starttls(self, ssl_context=None):
        self.llamadas.append("starttls")

    def login(self, usuario, password):
        if password == "mala":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        self.llamadas.append("login")

    def select(self, buzon):
        self.llamadas.append(("select", buzon))
        return "OK", [b"3"]


def test_conexion_ssl_usa_contexto_verificado():
    conectar(cfg(), fabrica_ssl=IMAPFalso, fabrica=None)
    contexto = IMAPFalso.ultima.ssl_context
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert IMAPFalso.ultima.llamadas == ["login", ("select", '"INBOX"')]


def test_conexion_starttls_cifra_antes_del_login():
    conectar(cfg(IMAP_SECURITY="starttls", IMAP_PORT=143),
             fabrica_ssl=None, fabrica=IMAPFalso)
    assert IMAPFalso.ultima.llamadas[:2] == ["starttls", "login"]


def test_credenciales_rechazadas():
    with pytest.raises(ErrorCorreoEntrante) as exc:
        conectar(cfg(IMAP_PASSWORD="mala"), fabrica_ssl=IMAPFalso, fabrica=None)
    assert exc.value.codigo == "AUTENTICACION"
    assert "mala" not in str(exc.value) + exc.value.detalle


class BandejaFalsa:
    def __init__(self, mensajes):
        self.mensajes = {str(i + 1).encode(): m for i, m in enumerate(mensajes)}
        self.vistos, self.cerrada = [], False

    def uid(self, comando, *args):
        if comando == "SEARCH":
            return "OK", [b" ".join(self.mensajes)]
        if comando == "FETCH":
            uid, partes = args
            crudo = self.mensajes[uid]
            if partes == "(RFC822.SIZE)":
                return "OK", [uid + b" (UID " + uid + b" RFC822.SIZE "
                              + str(len(crudo)).encode() + b")"]
            return "OK", [(uid + b" (BODY[] {n}", crudo), b")"]
        if comando == "STORE":
            self.vistos.append(args[0])
            return "OK", []
        raise AssertionError(comando)

    def logout(self):
        self.cerrada = True


def test_descarga_solo_guarda_facturacion_y_respeta_el_resto(app, monkeypatch):
    bandeja = BandejaFalsa([
        mensaje("Solicitud de factura", "Monto: 1000").as_bytes(),
        mensaje("Reunión", "Nos vemos el lunes").as_bytes(),
        mensaje("Factura", "x" * 60_000).as_bytes(),                  # muy grande
        mensaje("Re: factura", "Fuera de oficina",
                Auto_Submitted="auto-replied").as_bytes(),
    ])
    guardados = []
    monkeypatch.setattr(correo_entrante, "guardar_correo",
                        lambda crudo, m: guardados.append(m["Subject"]) or "nuevo")

    with app.app_context():
        resumen = descargar_correos(cfg(), conectar_fn=lambda c: bandeja)

    assert guardados == ["Solicitud de factura"]
    assert bandeja.vistos == [b"1"]     # el resto queda NO leído
    assert resumen == {"revisados": 4, "guardados": 1, "duplicados": 0,
                       "ignorados": 2, "omitidos_tamano": 1, "errores": 0}
    assert bandeja.cerrada


def test_metadatos_saneados():
    # Asunto codificado que al decodificarse contiene CRLF (inyección).
    crudo = (b"From: PRUEBA@Ejemplo.com\r\n"
             b"Subject: =?utf-8?q?Factura=0D=0ABcc=3A_x=40y.cl?=\r\n"
             b"\r\nhola\r\n")
    m = BytesParser(policy=policy.default).parsebytes(crudo)
    datos = metadatos(crudo, m)
    assert datos["message_id"].startswith("<sin-id-")
    assert "\n" not in datos["asunto"]
    assert datos["remitente"] == "prueba@ejemplo.com"
    assert len(datos["huella"]) == 64


CLIENTE = {"id": 1, "rut": "12345678-5", "razon_social": "Cliente de Prueba MVP",
           "giro": "Servicios", "direccion": "Avenida Falsa 1234",
           "email_contacto": "prueba@ejemplo.com", "activo": 1}

CUERPO = ("RUT: 12.345.678-5\nConcepto: Servicios octubre\n"
          "Monto: $980.000\nFecha: 16-10-2026\nAfectación: afecta\n")


class BD:
    def __init__(self, crudo, clientes=(CLIENTE,)):
        self.correo = {
            "id": 5, "estado": "RECIBIDO", "remitente": "prueba@ejemplo.com",
            "nombre_almacenado": "a" * 32 + ".eml",
            "sha256": hashlib.sha256(crudo).hexdigest(),
            "huella_message_id": "f" * 64,
        }
        self.clientes = list(clientes)
        self.solicitudes, self.facturas, self.auditoria = [], [], []
        self.commits = self.rollbacks = 0

    # interfaz de conexión
    def begin(self): pass
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): pass
    def cursor(self): return CursorBD(self)


class CursorBD:
    def __init__(self, bd):
        self.bd, self.res, self.lastrowid = bd, None, None

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def fetchone(self):
        if isinstance(self.res, list):
            return self.res[0] if self.res else None
        return self.res

    def fetchall(self):
        return self.res or []

    def execute(self, sql, p=()):
        s, bd = " ".join(sql.split()), self.bd
        if s.startswith("SELECT id, email FROM usuarios"):
            self.res = {"id": 99, "email": "sistema.correo@facturaciones.cl"}
        elif s.startswith("SELECT * FROM correos_entrantes"):
            self.res = dict(bd.correo)
        elif "FROM clientes WHERE LOWER(email_contacto)" in s:
            self.res = [c for c in bd.clientes if c["email_contacto"] == p[0]]
        elif "FROM clientes WHERE rut" in s:
            self.res = next((c for c in bd.clientes if c["rut"] == p[0]), None)
        elif "FROM solicitudes WHERE emisor_id" in s:
            self.res = None
        elif s.startswith("SELECT id FROM estados_solicitud"):
            self.res = {"id": 2}
        elif s.startswith("SELECT id FROM origenes_solicitud"):
            self.res = {"id": 2}
        elif s.startswith("INSERT INTO solicitudes"):
            bd.solicitudes.append(dict(p))
            self.lastrowid = 40
        elif s.startswith("SELECT id, version, estado, datos"):
            self.res = None
        elif s.startswith("INSERT INTO facturas"):
            bd.facturas.append(p)
            self.lastrowid = 70
        elif s.startswith("UPDATE correos_entrantes SET estado = 'ERROR'"):
            bd.correo.update(estado="ERROR", observaciones=json.loads(p[0]))
        elif s.startswith("UPDATE correos_entrantes"):
            bd.correo.update(estado=p[0], cliente_id=p[1], solicitud_id=p[2],
                             observaciones=json.loads(p[4]) if p[4] else None)
        elif s.startswith("INSERT INTO auditoria"):
            bd.auditoria.append((p[1], json.loads(p[2])))
        else:
            raise AssertionError(f"SQL no esperado: {s[:80]}")


@pytest.fixture
def entorno(app, monkeypatch, tmp_path):
    def _preparar(cuerpo, remitente="prueba@ejemplo.com", clientes=(CLIENTE,)):
        crudo = mensaje("Solicitud de factura", cuerpo, remitente).as_bytes()
        app.config["CORREOS_FOLDER"] = str(tmp_path)
        (tmp_path / ("a" * 32 + ".eml")).write_bytes(crudo)
        bd = BD(crudo, clientes)
        bd.correo["remitente"] = remitente
        monkeypatch.setattr(correo_entrante, "get_db_connection", lambda: bd)
        return bd
    return _preparar


def test_correo_completo_crea_solicitud_y_factura_v1(app, entorno):
    bd = entorno(CUERPO)
    with app.app_context():
        resultado = procesar_correo(5)

    assert resultado["estado"] == "PROCESADO" and resultado["nueva"]
    solicitud = bd.solicitudes[0]
    assert solicitud["origen_id"] == 2 and solicitud["emisor_id"] == 99
    assert solicitud["monto_bruto"] == Decimal("980000")
    assert solicitud["fecha_emision"] == date(2026, 10, 16)
    assert solicitud["clave_idempotencia"] == "f" * 64
    assert bd.facturas[0][1] == 1                       # versión 1
    assert bd.correo["estado"] == "PROCESADO"
    assert bd.correo["solicitud_id"] == 40
    acciones = [a for a, _ in bd.auditoria]
    assert acciones == ["SOLICITUD_CREADA", "FACTURA_GENERADA"]
    assert bd.auditoria[1][1]["version_factura"] == 1
    assert bd.commits == 1


def test_remitente_desconocido_queda_para_revision(app, entorno):
    bd = entorno("Concepto: Algo\nMonto: 1000", remitente="otro@desconocido.cl")
    with app.app_context():
        resultado = procesar_correo(5)

    assert resultado["estado"] == "REQUIERE_REVISION"
    assert bd.solicitudes == [] and bd.facturas == []
    assert "No se identificó al cliente" in bd.correo["observaciones"]["motivos"][0]
    assert bd.auditoria[0][0] == "CORREO_REQUIERE_REVISION"


def test_faltan_datos_obligatorios(app, entorno):
    bd = entorno("Hola, necesito una factura por favor.")
    with app.app_context():
        resultado = procesar_correo(5)

    assert resultado["estado"] == "REQUIERE_REVISION"
    motivos = " ".join(bd.correo["observaciones"]["motivos"])
    assert "concepto" in motivos and "monto" in motivos


def test_rut_de_otro_cliente_genera_alerta_de_seguridad(app, entorno):
    otro = dict(CLIENTE, id=2, email_contacto="contacto@cliente.cl")
    bd = entorno(CUERPO, remitente="intruso@gmail.com", clientes=(otro,))
    with app.app_context():
        resultado = procesar_correo(5)

    assert resultado["estado"] == "PROCESADO"
    assert any("no es el correo de contacto" in a
               for a in bd.correo["observaciones"]["alertas"])


def test_eml_alterado_no_se_procesa(app, entorno, tmp_path, monkeypatch):
    bd = entorno(CUERPO)
    (tmp_path / ("a" * 32 + ".eml")).write_bytes(b"alterado")
    with app.app_context():
        resultado = procesar_correo(5)

    assert resultado["estado"] == "ERROR"
    assert bd.solicitudes == []
    assert bd.rollbacks >= 1
