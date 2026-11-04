import pymysql
import pytest

from app.services.correo import construir_mensaje
from app.services.facturas import ErrorFactura, construir_datos
from app.services.notificaciones import componer
from test_facturas import SOLICITUD

PID = "a" * 32
BASE = f"/solicitudes/{PID}/factura"


def flashes(client):
    with client.session_transaction() as sesion:
        return [m for _, m in sesion.get("_flashes", [])]


def simular(monkeypatch, ruta, resultado=None, error=None):
    llamadas = []

    def falso(*args, **kwargs):
        llamadas.append(kwargs or args)
        if error:
            raise error
        return resultado

    monkeypatch.setattr(ruta, falso)
    return llamadas


@pytest.mark.parametrize("ruta", [BASE, BASE + "/sii", "/admin/correos"])
def test_anonimo_redirige_al_login(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


@pytest.mark.parametrize("ruta", ["/aprobar", "/observar"])
def test_emisor_no_puede_validar(client, login_como, monkeypatch, ruta):
    llamadas = simular(monkeypatch, "app.solicitudes.routes.aprobar_factura", 1)
    login_como("Emisor")
    assert client.post(BASE + ruta, data={"version": "1"}).status_code == 403
    assert llamadas == []


def test_emisor_no_descarga_archivo_sii(client, login_como):
    login_como("Emisor")
    assert client.get(BASE + "/sii").status_code == 403


@pytest.mark.parametrize("rol", ["Emisor", "Lector"])
def test_bandeja_solo_para_administrador(client, login_como, rol):
    login_como(rol)
    assert client.get("/admin/correos").status_code == 403
    assert client.post("/admin/correos/revisar").status_code == 403


def test_lector_no_envia_a_revision(client, login_como):
    login_como("Lector")
    assert client.post(BASE + "/revision").status_code == 403


def test_admin_aprueba(client, login_como, monkeypatch):
    llamadas = simular(monkeypatch, "app.solicitudes.routes.aprobar_factura", 2)
    login_como("Administrador", user_id=1)

    respuesta = client.post(BASE + "/aprobar", data={"version": "6"})

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(BASE)
    assert llamadas[0]["actor_id"] == 1
    assert llamadas[0]["version_esperada"] == "6"
    assert any("versión 2 validada" in m for m in flashes(client))


def test_admin_observa_con_error_de_negocio(client, login_como, monkeypatch):
    simular(monkeypatch, "app.solicitudes.routes.observar_factura",
            error=ErrorFactura("Indique qué debe corregirse"))
    login_como("Administrador")
    client.post(BASE + "/observar", data={"version": "1", "observacion": ""})
    assert "Indique qué debe corregirse" in flashes(client)


def test_emisor_envia_a_revision_y_se_avisa_al_admin(client, login_como, monkeypatch):
    simular(monkeypatch, "app.solicitudes.routes.enviar_a_revision",
            {"version": 2, "notificar": True, "solicitud_id": 9})
    avisos = simular(monkeypatch, "app.solicitudes.routes.notificar_factura_generada",
                     {"enviados": 0, "fallidos": 1, "error": None})
    login_como("Emisor", user_id=7)

    client.post(BASE + "/revision", data={"version": "3"})

    assert avisos == [(7, 9, "127.0.0.1")]
    mensajes = flashes(client)
    assert any("versión 2 generada" in m for m in mensajes)
    assert any("no se pudo avisar" in m for m in mensajes)


def test_error_de_bd_no_expone_detalles(client, login_como, monkeypatch):
    simular(monkeypatch, "app.solicitudes.routes.enviar_a_revision",
            error=pymysql.err.OperationalError(2003, "secreto interno"))
    login_como("Administrador")
    client.post(BASE + "/revision", data={"version": "1"})
    assert not any("secreto" in m for m in flashes(client))


def test_admin_revisa_bandeja(client, login_como, monkeypatch):
    simular(monkeypatch, "app.admin.routes.revisar_bandeja", {
        "descarga": {"revisados": 3, "guardados": 1, "duplicados": 0,
                     "ignorados": 2, "omitidos_tamano": 0, "errores": 0},
        "error_descarga": None,
        "proceso": {"procesados": 1, "requieren_revision": 0, "errores": 0,
                    "avisos_enviados": 1, "avisos_fallidos": 0},
    })
    login_como("Administrador")
    respuesta = client.post("/admin/correos/revisar")
    assert respuesta.status_code == 302
    assert any("Facturas generadas: 1" in m for m in flashes(client))


def test_panel_admin_funciona_sin_bd(client, login_como, monkeypatch):
    def sin_bd():
        raise pymysql.err.OperationalError(2003, "sin conexión")

    monkeypatch.setattr("app.models.get_db_connection", sin_bd)
    login_como("Administrador")
    respuesta = client.get("/dashboard")
    assert respuesta.status_code == 200
    assert "Facturas por validar".encode() in respuesta.data


def test_aviso_al_admin_incluye_version_enlace_y_alertas(app):
    datos = construir_datos(SOLICITUD)
    with app.test_request_context():
        asunto, cuerpo = componer(
            {"public_id": SOLICITUD["public_id"], "nombre": "Cliente\r\nBcc: x"},
            {"version": 2, "datos": datos},
            {"remitente": "prueba@ejemplo.com",
             "observaciones": {"alertas": ["Se asumió AFECTA"]}},
            "http://127.0.0.1:5000/",
        )
    assert asunto.startswith("[Facturaciones] Factura v2 lista para validar")
    assert "\n" not in asunto
    assert f"http://127.0.0.1:5000/solicitudes/{SOLICITUD['public_id']}/factura" in cuerpo
    assert "980.000 CLP" in cuerpo
    assert "Se asumió AFECTA" in cuerpo
    assert "corrige la anterior" in cuerpo


def test_cabeceras_extra_solo_x_y_saneadas():
    m = construir_mensaje(
        remitente="F <no-responder@facturaciones.cl>",
        remitente_correo="no-responder@facturaciones.cl",
        destinatario="a@b.cl", asunto="A", cuerpo="B",
        cabeceras_extra={"X-Facturaciones-Origen": "notificacion\r\nBcc: x@y.cl",
                         "Bcc": "victima@y.cl"},
    )
    assert m["X-Facturaciones-Origen"] == "notificacion Bcc: x@y.cl"
    assert m["Bcc"] is None


# --- Plantillas ----------------------------------------------------------------

def _solicitud(estado):
    return dict(SOLICITUD, estado_nombre=estado, origen_nombre="Correo",
                version=6, emisor_id=1, cliente_id=1, motivo_rechazo=None,
                email_emisor="prueba@ejemplo.com")


def _versiones():
    v1 = construir_datos(SOLICITUD)
    v2 = construir_datos(dict(SOLICITUD, concepto="Corregido"))
    return [
        {"id": 2, "version": 2, "estado": "EN_REVISION", "tipo_dte": 33,
         "datos": v2, "cambios": {"detalle.concepto": {"anterior": "A", "nuevo": "Corregido"}},
         "generada_en": "2026-11-04", "generada_por_nombre": "Emisor",
         "revisada_en": None, "revisada_por_nombre": None, "observacion": None,
         "archivo_sii": None, "archivo_sii_sha256": None},
        {"id": 1, "version": 1, "estado": "OBSERVADA", "tipo_dte": 33,
         "datos": v1, "cambios": None, "generada_en": "2026-11-03",
         "generada_por_nombre": "Sistema", "revisada_en": "2026-11-03",
         "revisada_por_nombre": "Admin", "observacion": "Concepto incorrecto",
         "archivo_sii": None, "archivo_sii_sha256": None},
    ]


@pytest.mark.parametrize("rol,estado,esperado", [
    ("Administrador", "En revisión", "Factura correcta: generar archivo SII"),
    ("Emisor", "En revisión", "Historial de versiones"),
    ("Emisor", "En corrección", "Generar factura y enviar a revisión"),
])
def test_pantalla_factura(client, login_como, monkeypatch, rol, estado, esperado):
    monkeypatch.setattr("app.solicitudes.routes.obtener_solicitud_autorizada",
                        lambda pid: _solicitud(estado))
    monkeypatch.setattr("app.solicitudes.routes.listar_versiones", lambda sid: (
        _versiones(), {"remitente": "prueba@ejemplo.com", "asunto": "Factura",
                       "fecha_correo": None,
                       "observaciones": {"alertas": ["Se asumió AFECTA"]}}))
    login_como(rol)

    respuesta = client.get(BASE)

    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert esperado in html
    assert "Versión 2" in html and "Corregido" in html
    assert "Se asumió AFECTA" in html
    if rol != "Administrador":
        assert "generar archivo SII" not in html


def test_pantalla_bandeja(client, login_como, monkeypatch):
    monkeypatch.setattr("app.admin.routes.listar_correos", lambda estado: [{
        "id": 3, "remitente": "x@y.cl", "asunto": "<script>alert(1)</script>",
        "fecha_correo": None, "estado": "REQUIERE_REVISION", "tamano": 10,
        "intentos": 1, "recibido_en": "2026-11-04", "procesado_en": None,
        "datos_extraidos": {"monto_bruto": "1000"}, "public_id": None,
        "cliente_nombre": None,
        "observaciones": {"motivos": ["No se identificó al cliente"], "alertas": []},
    }])
    login_como("Administrador")

    html = client.get("/admin/correos").get_data(as_text=True)

    assert "No se identificó al cliente" in html
    assert "<script>alert(1)</script>" not in html   # autoescape
    assert "Reprocesar" in html
