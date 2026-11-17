"""Fase 5: documentos adjuntos al crear una solicitud."""
import io
import os
from datetime import date

import pymysql
import pytest
from werkzeug.datastructures import FileStorage

from app import create_app
from app.services import adjuntos as servicio
from app.services import solicitudes as servicio_solicitudes
from app.services.adjuntos import ErrorAdjunto, leer_adjuntos
from app.services.solicitudes import huella_con_adjuntos, huella_de_creacion
from config import TestingConfig

PUBLIC_ID = "d" * 32
CLAVE = "e" * 32

PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
def app(tmp_path):
    """App propia de estas pruebas, con carpeta de adjuntos temporal."""
    class Config(TestingConfig):
        XML_UPLOAD_FOLDER = str(tmp_path / "xml")
        ADJUNTOS_FOLDER = str(tmp_path / "adjuntos")

    return create_app(Config)


def archivo(contenido, nombre):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre)


def leer(app, *archivos):
    with app.app_context():
        return leer_adjuntos(list(archivos))


def flashes(client):
    with client.session_transaction() as sesion:
        return [m for _, m in sesion.get("_flashes", [])]


# --- leer_adjuntos ---------------------------------------------------------

def test_tipos_validos(app):
    resultado = leer(
        app,
        archivo(PDF, "factura.pdf"),
        archivo(PNG, "foto.PNG"),
        archivo(JPEG, "scan.jpeg"),
    )

    assert [a["tipo"] for a in resultado] == ["PDF", "PNG", "JPEG"]
    assert [a["mimetype"] for a in resultado] == [
        "application/pdf", "image/png", "image/jpeg",
    ]
    assert resultado[0]["tamano"] == len(PDF)
    assert len(resultado[0]["sha256"]) == 64
    assert resultado[1]["extension"] == ".png"


def test_jpg_es_jpeg(app):
    assert leer(app, archivo(JPEG, "a.jpg"))[0]["tipo"] == "JPEG"


def test_extension_y_contenido_deben_coincidir(app):
    with pytest.raises(ErrorAdjunto, match="no corresponde"):
        leer(app, archivo(PNG, "documento.pdf"))


@pytest.mark.parametrize("nombre", ["programa.exe", "dibujo.svg",
                                    "pagina.html", "planilla.docx",
                                    "sin_extension"])
def test_extensiones_no_permitidas(app, nombre):
    with pytest.raises(ErrorAdjunto, match="PDF, PNG o JPG"):
        leer(app, archivo(PDF, nombre))


def test_archivo_vacio(app):
    with pytest.raises(ErrorAdjunto, match="vacío"):
        leer(app, archivo(b"", "vacio.pdf"))


def test_archivo_demasiado_grande(app):
    contenido = PDF + b"0" * (5 * 1024 * 1024 + 1 - len(PDF))

    with pytest.raises(ErrorAdjunto, match="5 MB"):
        leer(app, archivo(contenido, "grande.pdf"))


def test_archivo_justo_en_el_limite(app):
    contenido = PDF + b"0" * (5 * 1024 * 1024 - len(PDF))

    assert leer(app, archivo(contenido, "limite.pdf"))[0]["tamano"] == (
        5 * 1024 * 1024
    )


def test_maximo_tres_archivos(app):
    with pytest.raises(ErrorAdjunto, match="máximo 3"):
        leer(app, *[archivo(PDF, f"{i}.pdf") for i in range(4)])


def test_nombre_demasiado_largo(app):
    with pytest.raises(ErrorAdjunto, match="255"):
        leer(app, archivo(PDF, "x" * 252 + ".pdf"))


@pytest.mark.parametrize("nombre", ["../../x.pdf", "..\\..\\x.pdf",
                                    "a\x00b.pdf", "a\nb.pdf"])
def test_nombre_con_ruta_o_control_se_rechaza(app, nombre):
    with pytest.raises(ErrorAdjunto, match="no es válido"):
        leer(app, archivo(PDF, nombre))


def test_nombre_que_secure_filename_deja_sin_extension(app):
    with pytest.raises(ErrorAdjunto, match="no es válido"):
        # secure_filename("файл.pdf") == "pdf": pierde la extensión.
        leer(app, archivo(PDF, "файл.pdf"))


@pytest.mark.parametrize("marca", [b"/JavaScript", b"/JS", b"/Launch",
                                   b"/EmbeddedFile", b"/J#61vaScript"])
def test_pdf_activo_se_rechaza(app, marca):
    contenido = PDF + b"\n<< /S " + marca + b" (app.alert(1)) >>"

    with pytest.raises(ErrorAdjunto, match="elementos activos"):
        leer(app, archivo(contenido, "activo.pdf"))


def test_pdf_con_palabra_parecida_no_se_rechaza(app):
    contenido = PDF + b"\n<< /JSONData 1 >>"

    assert leer(app, archivo(contenido, "ok.pdf"))[0]["tipo"] == "PDF"


def test_parte_sin_nombre_se_ignora(app):
    resultado = leer(
        app, archivo(b"", ""), archivo(PDF, "a.pdf"), None
    )

    assert [a["nombre_original"] for a in resultado] == ["a.pdf"]


# --- crear_solicitud con conexión simulada ---------------------------------

DATOS = {
    "cliente_id": "3",
    "concepto": "Servicio",
    "nro_orden_compra": "",
    "fecha_emision": "2026-01-15",
    "monto_bruto": "1000",
    "tipo_afectacion": "AFECTA",
}


class Cursor:
    def __init__(self, bd):
        self.bd = bd
        self.lastrowid = None
        self._resultado = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, parametros=None):
        s = " ".join(sql.split())
        self.bd.sql.append((s, parametros))
        self._resultado = None

        if s.startswith("SELECT id FROM roles"):
            self._resultado = {"id": 1}
        elif s.startswith("SELECT id, rol_id, email, activo FROM usuarios"):
            self._resultado = {"id": 7, "rol_id": 2,
                               "email": "e@test.cl", "activo": 1}
        elif s.startswith("SELECT nombre FROM roles"):
            self._resultado = {"nombre": "Emisor"}
        elif "clave_idempotencia = %s" in s:
            self._resultado = self.bd.existente
        elif "FROM clientes" in s:
            self._resultado = {"id": 3, "rut": "1-9", "razon_social": "C",
                               "giro": "G", "direccion": "D",
                               "email_contacto": None, "activo": 1}
        elif "FROM estados_solicitud" in s or "FROM origenes_solicitud" in s:
            self._resultado = {"id": 1}
        elif s.startswith("INSERT INTO solicitudes"):
            self.lastrowid = 50
        elif s.startswith("INSERT INTO adjuntos_solicitud"):
            self.bd.siguiente_adjunto += 1
            self.lastrowid = self.bd.siguiente_adjunto
        elif s.startswith("INSERT INTO auditoria"):
            if self.bd.fallar_auditoria:
                raise pymysql.err.OperationalError(1205, "lock")
            self.bd.eventos.append(parametros[1])

    def fetchone(self):
        return self._resultado


class Conexion:
    def __init__(self):
        self.sql = []
        self.eventos = []
        self.existente = None
        self.fallar_auditoria = False
        self.siguiente_adjunto = 100
        self.commits = 0
        self.rollbacks = 0

    def begin(self):
        pass

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


@pytest.fixture
def bd(monkeypatch):
    conexion = Conexion()
    monkeypatch.setattr(servicio_solicitudes, "get_db_connection",
                        lambda: conexion)
    monkeypatch.setattr(
        servicio_solicitudes, "validar_cliente",
        lambda c: ({"rut": c["rut"], "razon_social": c["razon_social"],
                    "direccion": c["direccion"], "giro": c["giro"],
                    "email_contacto": c["email_contacto"]}, {}),
    )
    return conexion


def archivos_en(carpeta):
    return os.listdir(carpeta) if os.path.isdir(carpeta) else []


def test_crear_con_adjuntos_guarda_filas_archivos_y_eventos(app, bd):
    with app.app_context():
        adjuntos = leer_adjuntos([archivo(PDF, "a.pdf"),
                                  archivo(PNG, "b.png")])
        public_id = servicio_solicitudes.crear_solicitud(
            7, DATOS, CLAVE, "127.0.0.1", adjuntos=adjuntos
        )

    carpeta = app.config["ADJUNTOS_FOLDER"]
    guardados = archivos_en(carpeta)

    assert len(public_id) == 32
    assert bd.commits == 1
    assert len(guardados) == 2
    assert {os.path.splitext(n)[1] for n in guardados} == {".pdf", ".png"}
    assert bd.eventos == ["SOLICITUD_CREADA", "ADJUNTO_CARGADO",
                          "ADJUNTO_CARGADO"]

    inserts = [p for s, p in bd.sql
               if s.startswith("INSERT INTO adjuntos_solicitud")]
    assert [p[1] for p in inserts] == ["a.pdf", "b.png"]
    assert all(p[0] == 50 and p[6] == 7 for p in inserts)
    assert {p[2] for p in inserts} == set(guardados)


def test_si_falla_la_auditoria_no_quedan_archivos(app, bd):
    bd.fallar_auditoria = True

    with app.app_context():
        adjuntos = leer_adjuntos([archivo(PDF, "a.pdf"),
                                  archivo(JPEG, "b.jpg")])
        with pytest.raises(pymysql.MySQLError):
            servicio_solicitudes.crear_solicitud(
                7, DATOS, CLAVE, adjuntos=adjuntos
            )

    assert archivos_en(app.config["ADJUNTOS_FOLDER"]) == []
    assert bd.rollbacks == 1
    assert bd.commits == 0


def test_repeticion_idempotente_no_escribe_archivos(app, bd):
    with app.app_context():
        adjuntos = leer_adjuntos([archivo(PDF, "a.pdf")])
        limpio, _ = servicio_solicitudes.validar_solicitud(DATOS)
        bd.existente = {
            "public_id": PUBLIC_ID,
            "huella_creacion": huella_con_adjuntos(
                huella_de_creacion(limpio), adjuntos
            ),
        }

        resultado = servicio_solicitudes.crear_solicitud(
            7, DATOS, CLAVE, adjuntos=adjuntos
        )

    assert resultado == PUBLIC_ID
    assert archivos_en(app.config["ADJUNTOS_FOLDER"]) == []
    assert not any(s.startswith("INSERT") for s, _ in bd.sql)


def test_mismo_formulario_con_otros_archivos_se_detecta(app, bd):
    with app.app_context():
        limpio, _ = servicio_solicitudes.validar_solicitud(DATOS)
        bd.existente = {
            "public_id": PUBLIC_ID,
            "huella_creacion": huella_de_creacion(limpio),
        }
        adjuntos = leer_adjuntos([archivo(PDF, "otro.pdf")])

        with pytest.raises(servicio_solicitudes.ErrorGestionSolicitud,
                           match="otros datos"):
            servicio_solicitudes.crear_solicitud(
                7, DATOS, CLAVE, adjuntos=adjuntos
            )

    assert archivos_en(app.config["ADJUNTOS_FOLDER"]) == []


def test_sin_adjuntos_la_huella_no_cambia():
    limpio, _ = servicio_solicitudes.validar_solicitud(DATOS)
    huella = huella_de_creacion(limpio)

    assert huella_con_adjuntos(huella, None) == huella
    assert huella_con_adjuntos(huella, []) == huella

    a = {"sha256": "1" * 64}
    b = {"sha256": "2" * 64}
    assert huella_con_adjuntos(huella, [a, b]) == huella_con_adjuntos(
        huella, [b, a]
    )
    assert huella_con_adjuntos(huella, [a]) != huella


def test_sin_adjuntos_no_toca_la_tabla_ni_el_detalle(app, bd):
    with app.app_context():
        servicio_solicitudes.crear_solicitud(7, DATOS, CLAVE)

    assert bd.eventos == ["SOLICITUD_CREADA"]
    assert not any("adjuntos_solicitud" in s for s, _ in bd.sql)
    auditoria = next(p for s, p in bd.sql if s.startswith("INSERT INTO auditoria"))
    assert '"adjuntos"' not in auditoria[2]


# --- obtener_adjunto_autorizado --------------------------------------------

def _preparar_autorizacion(monkeypatch, app, fila_adjunto, solicitud_id=9):
    class CursorAdjunto:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, parametros=None):
            pass

        def fetchone(self):
            return fila_adjunto

    class ConexionAdjunto:
        def cursor(self):
            return CursorAdjunto()

        def close(self):
            pass

    monkeypatch.setattr(servicio, "get_db_connection", ConexionAdjunto)
    monkeypatch.setattr(servicio, "obtener_actor",
                        lambda c, a: {"id": a, "rol_nombre": "Emisor"})
    monkeypatch.setattr(servicio, "obtener_solicitud",
                        lambda c, actor, pid: {"id": solicitud_id})


def test_adjunto_de_otra_solicitud_se_rechaza(app, monkeypatch):
    _preparar_autorizacion(monkeypatch, app, {
        "id": 1, "solicitud_id": 99, "nombre_original": "a.pdf",
        "nombre_almacenado": "a" * 32 + ".pdf", "tipo": "PDF",
        "tamano": 10, "sha256": "0" * 64,
    })

    with app.app_context(), pytest.raises(ErrorAdjunto, match="no está disponible"):
        servicio.obtener_adjunto_autorizado(7, PUBLIC_ID, 1)


def test_nombre_almacenado_con_ruta_se_rechaza(app, monkeypatch):
    _preparar_autorizacion(monkeypatch, app, {
        "id": 1, "solicitud_id": 9, "nombre_original": "a.pdf",
        "nombre_almacenado": "../secreto.pdf", "tipo": "PDF",
        "tamano": 10, "sha256": "0" * 64,
    })

    with app.app_context(), pytest.raises(ErrorAdjunto, match="no es válido"):
        servicio.obtener_adjunto_autorizado(7, PUBLIC_ID, 1)


def test_emisor_no_dueno_no_obtiene_el_adjunto(app, monkeypatch):
    from app.services.registros_xml import ErrorArchivoXML

    _preparar_autorizacion(monkeypatch, app, None)

    def ajena(cursor, actor, public_id):
        raise ErrorArchivoXML("La solicitud no está disponible.")

    monkeypatch.setattr(servicio, "obtener_solicitud", ajena)

    with app.app_context(), pytest.raises(ErrorAdjunto, match="no está disponible"):
        servicio.obtener_adjunto_autorizado(8, PUBLIC_ID, 1)


# --- Rutas -----------------------------------------------------------------

class ConexionAuditoria:
    def __init__(self, eventos):
        self.eventos = eventos

    def cursor(self):
        eventos = self.eventos

        class C:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, parametros=None):
                eventos.append(parametros[1])

        return C()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_descarga_es_attachment_con_mime_del_servidor(
    app, client, login_como, monkeypatch, tmp_path
):
    ruta = tmp_path / "guardado.pdf"
    ruta.write_bytes(PDF)
    eventos = []

    monkeypatch.setattr(
        "app.solicitudes.routes.obtener_adjunto_autorizado",
        lambda **kw: (
            {"id": 7}, {"id": 9},
            {"id": 1, "nombre_original": "Cotización.pdf", "sha256": "0" * 64,
             "mimetype": "application/pdf"},
            str(ruta),
        ),
    )
    monkeypatch.setattr("app.solicitudes.routes.get_db_connection",
                        lambda: ConexionAuditoria(eventos))
    login_como("Emisor", user_id=7)

    respuesta = client.get(f"/solicitudes/{PUBLIC_ID}/adjuntos/1")

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Disposition"].startswith("attachment")
    assert respuesta.headers["Content-Type"] == "application/pdf"
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.data == PDF
    assert eventos == ["ADJUNTO_DESCARGADO"]
    respuesta.close()


def test_descarga_no_autorizada_vuelve_al_detalle(
    client, login_como, monkeypatch
):
    def rechazar(**kw):
        raise ErrorAdjunto("La solicitud no está disponible.")

    monkeypatch.setattr(
        "app.solicitudes.routes.obtener_adjunto_autorizado", rechazar
    )
    login_como("Emisor", user_id=8)

    respuesta = client.get(f"/solicitudes/{PUBLIC_ID}/adjuntos/1")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/solicitudes/{PUBLIC_ID}")
    assert any("no está disponible" in m for m in flashes(client))


def test_lector_no_descarga_adjuntos(client, login_como):
    login_como("Lector")

    assert client.get(
        f"/solicitudes/{PUBLIC_ID}/adjuntos/1"
    ).status_code == 403


def test_nueva_con_17_mb_redirige_con_aviso(client, login_como):
    login_como("Emisor")
    grande = io.BytesIO(b"%PDF-" + b"0" * (17 * 1024 * 1024))

    respuesta = client.post(
        "/solicitudes/nueva",
        data={"adjuntos": (grande, "grande.pdf")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/solicitudes/nueva")
    assert any("5 MB" in m for m in flashes(client))


def test_nueva_muestra_error_de_adjunto(client, login_como, monkeypatch):
    llamadas = []
    monkeypatch.setattr("app.solicitudes.routes.obtener_clientes_activos",
                        lambda: [])
    monkeypatch.setattr("app.solicitudes.routes.crear_solicitud",
                        lambda **kw: llamadas.append(kw))
    login_como("Emisor")

    respuesta = client.post(
        "/solicitudes/nueva",
        data={**DATOS, "adjuntos": (io.BytesIO(b"MZ..."), "virus.exe")},
        content_type="multipart/form-data",
    )
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Solo se permiten adjuntos PDF, PNG o JPG." in html
    assert "vuelva a seleccionarlos" in html
    assert llamadas == []


def test_nueva_pasa_los_adjuntos_al_servicio(client, login_como, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        "app.solicitudes.routes.verificar_token_envio", lambda t, u: CLAVE
    )
    monkeypatch.setattr(
        "app.solicitudes.routes.crear_solicitud",
        lambda **kw: llamadas.append(kw) or PUBLIC_ID,
    )
    login_como("Emisor")

    respuesta = client.post(
        "/solicitudes/nueva",
        data={**DATOS, "adjuntos": [(io.BytesIO(PDF), "a.pdf"),
                                    (io.BytesIO(PNG), "b.png")]},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 302
    assert [a["nombre_original"] for a in llamadas[0]["adjuntos"]] == [
        "a.pdf", "b.png",
    ]


def test_nueva_sin_archivos_pasa_none(client, login_como, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        "app.solicitudes.routes.verificar_token_envio", lambda t, u: CLAVE
    )
    monkeypatch.setattr(
        "app.solicitudes.routes.crear_solicitud",
        lambda **kw: llamadas.append(kw) or PUBLIC_ID,
    )
    login_como("Emisor")

    client.post(
        "/solicitudes/nueva",
        data={**DATOS, "adjuntos": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )

    assert llamadas[0]["adjuntos"] is None


def test_plantilla_nueva_es_multipart(client, login_como, monkeypatch):
    monkeypatch.setattr("app.solicitudes.routes.obtener_clientes_activos",
                        lambda: [])
    login_como("Emisor")

    html = client.get("/solicitudes/nueva").get_data(as_text=True)

    assert 'enctype="multipart/form-data"' in html
    assert 'name="adjuntos"' in html
    assert 'accept=".pdf,.png,.jpg,.jpeg"' in html


def _detalle(client, login_como, monkeypatch, adjuntos):
    monkeypatch.setattr(
        "app.solicitudes.routes.obtener_solicitud_autorizada",
        lambda pid: {
            "id": 9, "public_id": PUBLIC_ID, "estado_nombre": "Aprobada",
            "origen_nombre": "Web", "version": 1, "rut": "1-9",
            "nombre": "C", "giro": "G", "direccion": "D",
            "email_contacto_receptor": None, "concepto": "X",
            "monto_bruto": 1000, "fecha_emision": date(2026, 1, 1),
            "tipo_afectacion": "AFECTA", "nro_orden_compra": None,
            "email_emisor": "e@test.cl", "motivo_rechazo": None,
        },
    )

    class C:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *a):
            pass

        def fetchone(self):
            return None

    class Conexion:
        def cursor(self):
            return C()

        def close(self):
            pass

    monkeypatch.setattr("app.solicitudes.routes.get_db_connection", Conexion)
    monkeypatch.setattr("app.solicitudes.routes.listar_envios", lambda sid: [])
    monkeypatch.setattr("app.solicitudes.routes.listar_adjuntos", adjuntos)
    login_como("Emisor")
    return client.get(f"/solicitudes/{PUBLIC_ID}").get_data(as_text=True)


def test_detalle_lista_adjuntos(client, login_como, monkeypatch):
    html = _detalle(client, login_como, monkeypatch, lambda sid: [{
        "id": 4, "nombre_original": "<b>oc</b>.pdf", "tipo": "PDF",
        "tamano": 2048, "subido_en": "2026-01-01 10:00",
    }])

    assert "Documentos adjuntos" in html
    assert f'href="/solicitudes/{PUBLIC_ID}/adjuntos/4"' in html
    assert "&lt;b&gt;oc&lt;/b&gt;.pdf" in html
    assert "2 KB" in html


def test_detalle_sin_adjuntos(client, login_como, monkeypatch):
    html = _detalle(client, login_como, monkeypatch, lambda sid: [])

    assert "Sin documentos adjuntos." in html


def test_detalle_funciona_sin_la_migracion_004(client, login_como, monkeypatch):
    def sin_tabla(sid):
        raise pymysql.err.ProgrammingError(1146, "Table doesn't exist")

    html = _detalle(client, login_como, monkeypatch, sin_tabla)

    assert "No se pudieron cargar los documentos adjuntos." in html
    assert "Receptor histórico" in html
