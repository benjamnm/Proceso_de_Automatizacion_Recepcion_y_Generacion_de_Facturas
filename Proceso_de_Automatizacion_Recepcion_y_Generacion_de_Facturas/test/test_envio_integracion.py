"""Flujo completo de envío: BD simulada con estado + servidor SMTP real
(socket local). Verifica las tres fases sin MySQL ni Internet."""
import email
import hashlib
import socket
import threading
from datetime import date
from decimal import Decimal
from email import policy

import pytest

from app.services import correos_solicitud
from app.services.correos_solicitud import (
    ErrorEnvioCorreo,
    enviar_xml_solicitud,
)

XML = b'<?xml version="1.0"?><DTE><Documento ID="F1"/></DTE>'


# --- Servidor SMTP mínimo ------------------------------------------------

class ServidorSMTP:
    def __init__(self, rechazar_rcpt=False):
        self.rechazar_rcpt = rechazar_rcpt
        self.mensajes = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.puerto = self.sock.getsockname()[1]
        self.hilo = threading.Thread(target=self._atender, daemon=True)
        self.hilo.start()

    def _atender(self):
        conn, _ = self.sock.accept()
        archivo = conn.makefile("rb")
        enviar = lambda linea: conn.sendall(linea.encode() + b"\r\n")
        enviar("220 prueba ESMTP")
        while True:
            linea = archivo.readline()
            if not linea:
                break
            comando = linea.decode().strip().upper()
            if comando.startswith(("EHLO", "HELO")):
                enviar("250-prueba\r\n250 SIZE 10000000")
            elif comando.startswith("MAIL FROM"):
                enviar("250 OK")
            elif comando.startswith("RCPT TO"):
                enviar("550 No such user" if self.rechazar_rcpt else "250 OK")
            elif comando == "DATA":
                enviar("354 Fin con <CRLF>.<CRLF>")
                datos = b""
                while True:
                    parte = archivo.readline()
                    if parte == b".\r\n":
                        break
                    datos += parte
                self.mensajes.append(datos)
                enviar("250 Encolado")
            elif comando == "QUIT":
                enviar("221 Adiós")
                break
            else:
                enviar("250 OK")
        conn.close()
        self.sock.close()


# --- BD simulada ------------------------------------------------------------

class Estado:
    def __init__(self, rol="Emisor", emisor_id=7, estado="Pendiente",
                 correo="prueba@ejemplo.com", sha=None):
        self.rol = rol
        self.solicitud = {
            "id": 1, "public_id": "6a5c43b82d54be589a4494a623378d59",
            "emisor_id": emisor_id, "rut": "12345678-5",
            "nombre": "Cliente de Prueba MVP",
            "concepto": "Facturaciones de prueba 10/2026",
            "monto_bruto": Decimal("980000"), "fecha_emision": date(2026, 10, 16),
            "tipo_afectacion": "AFECTA", "nro_orden_compra": None,
            "email_contacto_receptor": correo,
            "email_emisor": "emisor@facturaciones.cl",
            "estado_nombre": estado,
        }
        self.registro = {
            "id": 3, "nombre_original": "factura_F1.xml",
            "nombre_almacenado": "a" * 32 + ".xml",
            "sha256": sha or hashlib.sha256(XML).hexdigest(),
        }
        self.envios = {}
        self.auditoria = []
        self.commits = 0
        self.rollbacks = 0


class Cursor:
    def __init__(self, estado, pendientes):
        self.e, self.pendientes = estado, pendientes
        self.resultado, self.lastrowid = None, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        e = self.e
        if "FROM roles WHERE nombre" in s:
            self.resultado = {"id": 1}
        elif "FROM usuarios WHERE id" in s:
            self.resultado = {"id": 7, "rol_id": 2, "email": "x", "activo": 1}
        elif "SELECT nombre FROM roles WHERE id" in s:
            self.resultado = {"nombre": e.rol}
        elif "FROM solicitudes AS s" in s:
            self.resultado = dict(e.solicitud) if params[0] == e.solicitud["public_id"] else None
        elif "FROM registros_xml" in s:
            self.resultado = dict(e.registro) if e.registro else None
        elif "FROM envios_correo" in s and "EN_PROCESO" in s:
            vivos = [i for i, f in e.envios.items() if f["estado"] == "EN_PROCESO"]
            self.resultado = {"id": vivos[0]} if vivos else None
        elif s.startswith("INSERT INTO envios_correo"):
            nuevo = len(e.envios) + 1
            self.pendientes.append(("envio", nuevo, {
                "estado": "EN_PROCESO", "destinatario": params[3],
                "adjunto_sha256": params[7], "message_id": params[8],
            }))
            self.lastrowid = nuevo
        elif s.startswith("UPDATE envios_correo"):
            self.pendientes.append(("update", params[3], {
                "estado": params[0], "error_codigo": params[1],
            }))
        elif s.startswith("INSERT INTO auditoria"):
            self.pendientes.append(("auditoria", params[1], params[2]))
        else:
            raise AssertionError(f"SQL no esperado: {s[:80]}")

    def fetchone(self):
        return self.resultado


class Conexion:
    def __init__(self, estado):
        self.e, self.pendientes = estado, []

    def begin(self):
        pass

    def cursor(self):
        return Cursor(self.e, self.pendientes)

    def commit(self):
        for tipo, clave, datos in self.pendientes:
            if tipo == "envio":
                self.e.envios[clave] = datos
            elif tipo == "update" and self.e.envios[clave]["estado"] == "EN_PROCESO":
                self.e.envios[clave].update(datos)
            elif tipo == "auditoria":
                self.e.auditoria.append((clave, datos))
        self.pendientes.clear()
        self.e.commits += 1

    def rollback(self):
        self.pendientes.clear()
        self.e.rollbacks += 1

    def close(self):
        pass


@pytest.fixture
def entorno(app, tmp_path, monkeypatch):
    def _crear(servidor=None, **kwargs):
        estado = Estado(**kwargs)
        carpeta = tmp_path / "xml"
        carpeta.mkdir(exist_ok=True)
        (carpeta / estado.registro["nombre_almacenado"]).write_bytes(XML)
        app.config.update(
            XML_UPLOAD_FOLDER=str(carpeta),
            SMTP_HOST="localhost", SMTP_SECURITY="none", SMTP_USER="",
            SMTP_PORT=servidor.puerto if servidor else 1,
            SMTP_TIMEOUT=5,
            SMTP_FROM="Facturaciones SpA <no-responder@facturaciones.cl>",
        )
        monkeypatch.setattr(correos_solicitud, "get_db_connection",
                            lambda: Conexion(estado))
        return estado
    return _crear


def test_envio_completo_por_red(app, entorno):
    servidor = ServidorSMTP()
    estado = entorno(servidor)

    with app.test_request_context():
        resultado = enviar_xml_solicitud(7, estado.solicitud["public_id"], "1.2.3.4")
    servidor.hilo.join(5)

    assert resultado["estado"] == "ENVIADO" and resultado["registrado"]
    assert estado.envios[1]["estado"] == "ENVIADO"
    assert estado.envios[1]["adjunto_sha256"] == hashlib.sha256(XML).hexdigest()
    assert estado.auditoria[0][0] == "CORREO_ENVIADO"

    recibido = email.message_from_bytes(servidor.mensajes[0], policy=policy.default)
    assert recibido["To"] == "prueba@ejemplo.com"
    assert recibido["Reply-To"] == "emisor@facturaciones.cl"
    assert recibido["Message-ID"] == estado.envios[1]["message_id"]
    adjunto = next(recibido.iter_attachments())
    assert adjunto.get_filename() == "factura_F1.xml"
    assert adjunto.get_content() == XML


def test_destinatario_rechazado_queda_fallido(app, entorno):
    servidor = ServidorSMTP(rechazar_rcpt=True)
    estado = entorno(servidor)

    with app.test_request_context():
        resultado = enviar_xml_solicitud(7, estado.solicitud["public_id"])
    servidor.hilo.join(5)

    assert resultado["estado"] == "FALLIDO"
    assert resultado["error_codigo"] == "DESTINATARIO_RECHAZADO"
    assert estado.envios[1]["estado"] == "FALLIDO"
    assert estado.auditoria[0][0] == "CORREO_FALLIDO"


def test_servidor_caido_queda_fallido(app, entorno):
    estado = entorno(None)   # puerto 1: conexión rechazada

    with app.test_request_context():
        resultado = enviar_xml_solicitud(7, estado.solicitud["public_id"])

    assert resultado["error_codigo"] == "CONEXION"
    assert estado.envios[1]["estado"] == "FALLIDO"


def test_envio_en_curso_bloquea_duplicado(app, entorno):
    estado = entorno(None)
    estado.envios[1] = {"estado": "EN_PROCESO"}

    with app.test_request_context(), pytest.raises(ErrorEnvioCorreo, match="en curso"):
        enviar_xml_solicitud(7, estado.solicitud["public_id"])
    assert len(estado.envios) == 1 and estado.rollbacks == 1


@pytest.mark.parametrize("kwargs, texto", [
    ({"emisor_id": 99}, "no está disponible"),
    ({"estado": "Rechazada"}, "estado actual"),
    ({"correo": None}, "correo de receptor"),
    ({"sha": "0" * 64}, "SHA-256"),
])
def test_validaciones_previas_no_registran_envio(app, entorno, kwargs, texto):
    estado = entorno(None, **kwargs)

    with app.test_request_context(), pytest.raises(ErrorEnvioCorreo, match=texto):
        enviar_xml_solicitud(7, estado.solicitud["public_id"])
    assert estado.envios == {} and estado.auditoria == []


def test_sin_xml_no_envia(app, entorno):
    estado = entorno(None)
    estado.registro = None
    with app.test_request_context(), pytest.raises(ErrorEnvioCorreo, match="cargar el XML"):
        enviar_xml_solicitud(7, estado.solicitud["public_id"])


def test_administrador_puede_enviar_solicitud_ajena(app, entorno):
    servidor = ServidorSMTP()
    estado = entorno(servidor, rol="Administrador", emisor_id=99)
    with app.test_request_context():
        assert enviar_xml_solicitud(7, estado.solicitud["public_id"])["estado"] == "ENVIADO"
    servidor.hilo.join(5)


def test_sin_configuracion_smtp(app, entorno):
    estado = entorno(None)
    app.config["SMTP_HOST"] = ""
    with app.test_request_context(), pytest.raises(ErrorEnvioCorreo, match="no está configurado"):
        enviar_xml_solicitud(7, estado.solicitud["public_id"])
