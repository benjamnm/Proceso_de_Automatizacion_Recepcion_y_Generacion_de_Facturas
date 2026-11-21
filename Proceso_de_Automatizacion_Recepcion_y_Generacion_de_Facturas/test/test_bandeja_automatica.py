"""Actualización automática de la bandeja y aviso de correo en revisión."""
import pytest

from app.security import CLAVE_ACTIVIDAD
from app.services import correo_entrante, revision_automatica
from app.services.notificaciones import componer_revision

FIRMA = {"firma": "abc123", "por_revisar": 2, "por_validar": 5}

CORREO = {
    "id": 7, "remitente": "cliente@ejemplo.cl",
    "asunto": "Solicitud de factura", "estado": "REQUIERE_REVISION",
    "recibido_en": "2026-11-19 10:00:00",
    "datos_extraidos": '{"rut": null, "concepto": "Asesoría", "monto_bruto": "1000"}',
    "observaciones": '{"motivos": ["No se identificó al cliente."],'
                     ' "alertas": ["Remitente distinto al registrado."]}',
}


# --- Aviso al Administrador -------------------------------------------------

def test_aviso_de_revision_indica_que_fallo(app):
    with app.test_request_context():
        asunto, cuerpo = componer_revision(CORREO, "https://facturas.ejemplo.cl/")

    assert asunto.startswith("[Facturaciones] Correo de facturación requiere revisión")
    assert "#7" in asunto and "\n" not in asunto
    assert "No se identificó al cliente." in cuerpo
    assert "Remitente distinto al registrado." in cuerpo
    assert "Asesoría" in cuerpo
    assert "(no detectado)" in cuerpo            # RUT ausente
    assert "https://facturas.ejemplo.cl/admin/correos?estado=REQUIERE_REVISION" in cuerpo


def test_aviso_de_error_tecnico_no_lista_datos(app):
    correo = dict(CORREO, estado="ERROR", datos_extraidos=None,
                  observaciones='{"motivos": ["Error técnico"], "alertas": []}')
    with app.test_request_context():
        asunto, cuerpo = componer_revision(correo, "http://x")

    assert "con error" in asunto
    assert "Error técnico" in cuerpo
    assert "Datos detectados" not in cuerpo
    assert "estado=ERROR" in cuerpo


def test_asunto_sin_inyeccion_de_cabeceras(app):
    correo = dict(CORREO, remitente="a@b.cl\r\nBcc: espia@x.cl")
    with app.test_request_context():
        asunto, _ = componer_revision(correo, "http://x")
    assert "\r" not in asunto and "\n" not in asunto


@pytest.mark.parametrize("estado, clave", [
    ("REQUIERE_REVISION", "requieren_revision"), ("ERROR", "errores"),
])
def test_proceso_avisa_cuando_requiere_revision(app, monkeypatch, estado, clave):
    avisados = []
    monkeypatch.setattr(correo_entrante, "get_db_connection", lambda: _ConexionIds([11]))
    monkeypatch.setattr(correo_entrante, "procesar_correo",
                        lambda correo_id: {"estado": estado, "motivos": ["x"]})
    monkeypatch.setattr(
        correo_entrante, "notificar_correo_en_revision",
        lambda correo_id: avisados.append(correo_id) or
        {"enviados": 1, "fallidos": 0, "error": None},
    )

    with app.app_context():
        resumen = correo_entrante.procesar_pendientes()

    assert avisados == [11]
    assert resumen[clave] == 1
    assert resumen["avisos_enviados"] == 1


def test_proceso_exitoso_no_envia_aviso_de_revision(app, monkeypatch):
    avisados = []
    monkeypatch.setattr(correo_entrante, "get_db_connection", lambda: _ConexionIds([11]))
    monkeypatch.setattr(correo_entrante, "procesar_correo",
                        lambda correo_id: {"estado": "PROCESADO", "nueva": False})
    monkeypatch.setattr(correo_entrante, "notificar_correo_en_revision",
                        lambda correo_id: avisados.append(correo_id))

    with app.app_context():
        correo_entrante.procesar_pendientes()

    assert avisados == []


class _ConexionIds:
    def __init__(self, ids):
        self.ids = ids

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args):
        pass

    def fetchall(self):
        return [{"id": i} for i in self.ids]

    def close(self):
        pass


# --- Actualización automática de la página ----------------------------------

def test_novedades_solo_para_administrador(client, login_como):
    assert client.get("/admin/correos/novedades").status_code == 302   # anónimo
    login_como("Emisor")
    assert client.get("/admin/correos/novedades").status_code == 403


def test_novedades_devuelve_firma(client, login_como, monkeypatch):
    monkeypatch.setattr("app.admin.routes.firma_bandeja", lambda: FIRMA)
    login_como("Administrador")

    respuesta = client.get("/admin/correos/novedades")

    assert respuesta.status_code == 200
    assert respuesta.get_json() == FIRMA
    assert respuesta.headers["Cache-Control"] == "no-store"


def test_pagina_incluye_auto_actualizacion(client, login_como, monkeypatch):
    monkeypatch.setattr("app.admin.routes.listar_correos", lambda estado: [])
    monkeypatch.setattr("app.admin.routes.firma_bandeja", lambda: FIRMA)
    login_como("Administrador")

    html = client.get("/admin/correos").get_data(as_text=True)

    assert 'data-firma="abc123"' in html
    assert "/admin/correos/novedades" in html
    assert "js/auto-actualizar.js" in html


def test_auto_actualizacion_desactivable(app, client, login_como, monkeypatch):
    app.config["BANDEJA_REFRESCO_SEGUNDOS"] = 0
    monkeypatch.setattr("app.admin.routes.listar_correos", lambda estado: [])
    monkeypatch.setattr("app.admin.routes.firma_bandeja", lambda: FIRMA)
    login_como("Administrador")

    html = client.get("/admin/correos").get_data(as_text=True)

    assert "data-auto-actualizar" not in html


def _actividad(client):
    with client.session_transaction() as sesion:
        return sesion.get(CLAVE_ACTIVIDAD)


def _fijar_actividad(client, valor):
    with client.session_transaction() as sesion:
        sesion[CLAVE_ACTIVIDAD] = valor


@pytest.mark.parametrize("ruta", [
    "/admin/correos/novedades", "/admin/correos?auto=1",
])
def test_sondeo_no_renueva_inactividad(client, login_como, monkeypatch, ruta):
    monkeypatch.setattr("app.admin.routes.listar_correos", lambda estado: [])
    monkeypatch.setattr("app.admin.routes.firma_bandeja", lambda: FIRMA)
    login_como("Administrador")
    import time
    hace_un_rato = int(time.time()) - 60
    _fijar_actividad(client, hace_un_rato)

    assert client.get(ruta).status_code == 200
    assert _actividad(client) == hace_un_rato


def test_visita_normal_si_renueva_inactividad(client, login_como, monkeypatch):
    monkeypatch.setattr("app.admin.routes.listar_correos", lambda estado: [])
    monkeypatch.setattr("app.admin.routes.firma_bandeja", lambda: FIRMA)
    login_como("Administrador")
    import time
    hace_un_rato = int(time.time()) - 60
    _fijar_actividad(client, hace_un_rato)

    client.get("/admin/correos")

    assert _actividad(client) > hace_un_rato


def test_sondeo_con_sesion_vencida_cierra_sesion(app, client, login_como):
    login_como("Administrador")
    _fijar_actividad(client, 1)   # muy antiguo

    respuesta = client.get("/admin/correos/novedades")

    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


# --- Revisión automática en segundo plano -----------------------------------

def test_revision_automatica_no_arranca_en_pruebas(app):
    app.config["BANDEJA_REVISION_SEGUNDOS"] = 60
    assert revision_automatica.iniciar(app) is False


def test_revision_automatica_registra_resultado(app, monkeypatch):
    monkeypatch.setattr(revision_automatica, "revisar_bandeja", lambda descargar: {
        "descarga": None, "error_descarga": None,
        "proceso": {"procesados": 1, "requieren_revision": 0, "errores": 0,
                    "avisos_enviados": 1, "avisos_fallidos": 0},
    })

    revision_automatica.ejecutar_una_vez(app)

    estado = revision_automatica.estado()
    assert estado["ultima"] is not None
    assert estado["error"] is None
    assert estado["resumen"]["procesados"] == 1


def test_revision_automatica_tolera_ejecucion_en_curso(app, monkeypatch):
    def en_curso(descargar):
        raise correo_entrante.ErrorCorreoEntrante("EN_CURSO", "En curso")

    monkeypatch.setattr(revision_automatica, "revisar_bandeja", en_curso)
    revision_automatica.ejecutar_una_vez(app)   # no lanza


def test_revision_automatica_nunca_lanza(app, monkeypatch):
    def falla(descargar):
        raise RuntimeError("boom")

    monkeypatch.setattr(revision_automatica, "revisar_bandeja", falla)
    revision_automatica.ejecutar_una_vez(app)

    assert "Error inesperado" in revision_automatica.estado()["error"]
