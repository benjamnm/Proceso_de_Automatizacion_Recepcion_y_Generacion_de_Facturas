"""Fase 3: totales del panel y actividad reciente."""
import json
from datetime import datetime

from app.auditoria_acciones import ACCIONES_VISIBLES, ETIQUETAS_ACCION
from app.services import panel

PUBLIC_ID = "ab" * 16

# Lista que tenía admin.auditoria() antes de la Fase 3.
ACCIONES_ORIGINALES = (
    "USUARIO_CREADO", "USUARIO_EDITADO", "USUARIO_DESACTIVADO",
    "USUARIO_REACTIVADO", "CLIENTE_CREADO", "CLIENTE_EDITADO",
    "SOLICITUD_CREADA", "SOLICITUD_EDITADA", "SOLICITUD_ESTADO_CAMBIADO",
    "XML_CARGADO", "XML_REEMPLAZADO", "XML_DESCARGADO", "CORREO_ENVIADO",
    "CORREO_FALLIDO", "CORREO_RECIBIDO", "CORREO_REQUIERE_REVISION",
    "CORREO_REPROCESADO", "CORREO_DESCARTADO", "CORREO_ENTRANTE_DESCARGADO",
    "FACTURA_GENERADA", "FACTURA_OBSERVADA", "FACTURA_APROBADA",
    "ARCHIVO_SII_DESCARGADO", "NOTIFICACION_ENVIADA", "NOTIFICACION_FALLIDA",
)
ESTADOS = [
    {"id": 1, "nombre": "Pendiente", "total": 2},
    {"id": 2, "nombre": "En revisión", "total": 1},
    {"id": 3, "nombre": "Rechazada", "total": 0},
    {"id": 4, "nombre": "En corrección", "total": 0},
    {"id": 5, "nombre": "Aprobada", "total": 4},
]


class CursorFalso:
    """Registra cada consulta y responde según el texto del SQL."""

    def __init__(self, auditoria=None):
        self.consultas = []
        self.auditoria = auditoria or []
        self._ultimo = ""

    def execute(self, sql, parametros=None):
        self._ultimo = sql
        self.consultas.append((sql, parametros))

    def fetchall(self):
        if "estados_solicitud AS e" in self._ultimo and "COUNT" in self._ultimo:
            return [dict(e) for e in ESTADOS]
        if "FROM auditoria" in self._ultimo:
            return self.auditoria
        if "s.actualizado_en" in self._ultimo:
            return [{
                "public_id": PUBLIC_ID, "nombre": "Cliente",
                "actualizado_en": datetime(2026, 1, 1),
                "estado_nombre": "Pendiente",
            }]
        return []

    def fetchone(self):
        if "FROM usuarios" in self._ultimo or "FROM clientes" in self._ultimo:
            return {"activos": 3, "total": 4}
        return {"total": 9}


def test_resumen_emisor_limita_todo_a_sus_solicitudes(app):
    cursor = CursorFalso()

    with app.app_context():
        resumen = panel.resumen_emisor(cursor, 7)

    assert cursor.consultas
    for sql, parametros in cursor.consultas:
        assert "emisor_id = %s" in sql
        assert parametros[0] == 7
        assert "auditoria" not in sql

    # La condición de alcance va en el ON para conservar estados en 0.
    sql_estados = cursor.consultas[0][0]
    assert "ON s.estado_id = e.id AND s.emisor_id = %s" in sql_estados
    assert "WHERE" not in sql_estados

    assert set(resumen) == {"estados", "solicitudes_total", "actividad"}
    assert resumen["solicitudes_total"] == 7
    assert resumen["estados"]["Rechazada"]["total"] == 0
    assert resumen["actividad"][0]["public_id"] == PUBLIC_ID


def test_resumen_admin_conserva_claves_del_panel(app):
    cursor = CursorFalso()

    with app.app_context():
        resumen = panel.resumen_administrador(cursor)

    assert resumen["estados"]["En revisión"] == {
        "id": 2, "nombre": "En revisión", "total": 1,
    }
    assert resumen["correos_por_revisar"] == 9
    assert resumen["usuarios"] == {"activos": 3, "total": 4}
    assert resumen["clientes"] == {"activos": 3, "total": 4}
    assert resumen["eventos_total"] == 9
    assert resumen["solicitudes_total"] == 7

    sql_usuarios, params = next(
        (s, p) for s, p in cursor.consultas if "FROM usuarios" in s
    )
    assert "email <> %s" in sql_usuarios
    assert params == (app.config["SISTEMA_CORREO_EMAIL"],)


def test_actividad_admin_no_expone_ip_ni_detalle(app):
    auditoria = [
        {
            "accion": "SOLICITUD_CREADA",
            "detalle": json.dumps({"public_id": "<script>", "ip": "1.2.3.4"}),
            "creado_en": datetime(2026, 1, 2),
            "usuario_nombre": "Ana",
            "ip": "10.0.0.99",
        },
        {
            "accion": "FACTURA_APROBADA",
            "detalle": json.dumps({"public_id": PUBLIC_ID}),
            "creado_en": datetime(2026, 1, 3),
            "usuario_nombre": None,
            "ip": "10.0.0.99",
        },
        {
            "accion": "ACCION_DESCONOCIDA",
            "detalle": "no es json",
            "creado_en": datetime(2026, 1, 4),
            "usuario_nombre": "Ana",
            "ip": "10.0.0.99",
        },
    ]
    cursor = CursorFalso(auditoria)

    actividad = panel.actividad_administrador(cursor)

    assert actividad[0]["public_id"] is None
    assert actividad[0]["etiqueta"] == "Solicitud creada"
    assert actividad[1]["public_id"] == PUBLIC_ID
    assert actividad[2]["etiqueta"] == "ACCION_DESCONOCIDA"
    assert actividad[2]["public_id"] is None
    for item in actividad:
        assert set(item) == {"creado_en", "etiqueta", "usuario_nombre", "public_id"}
    assert "10.0.0.99" not in repr(actividad)
    assert "1.2.3.4" not in repr(actividad)

    sql, parametros = cursor.consultas[0]
    assert "a.ip" not in sql
    assert parametros[:-1] == ACCIONES_VISIBLES
    assert parametros[-1] == panel.LIMITE_ACTIVIDAD_ADMIN


RESUMEN_ADMIN = {
    "estados": {e["nombre"]: dict(e) for e in ESTADOS},
    "solicitudes_total": 7,
    "correos_por_revisar": 2,
    "usuarios": {"activos": 3, "total": 4},
    "clientes": {"activos": 5, "total": 6},
    "eventos_total": 40,
    "actividad": [{
        "creado_en": datetime(2026, 1, 3), "etiqueta": "Factura aprobada",
        "usuario_nombre": "Ana", "public_id": PUBLIC_ID,
    }],
}

RESUMEN_EMISOR = {
    "estados": {e["nombre"]: dict(e) for e in ESTADOS},
    "solicitudes_total": 7,
    "actividad": [{
        "public_id": PUBLIC_ID, "nombre": "Cliente Uno",
        "actualizado_en": datetime(2026, 1, 1), "estado_nombre": "Pendiente",
    }],
}


def test_panel_admin_muestra_totales(client, login_como, monkeypatch):
    monkeypatch.setattr("app.resumen_panel", lambda: RESUMEN_ADMIN)
    login_como("Administrador")

    html = client.get("/dashboard").get_data(as_text=True)

    assert "Usuarios activos" in html
    assert "Clientes activos" in html
    assert "Eventos registrados" in html
    assert "Actividad reciente" in html
    assert "Factura aprobada" in html
    assert f'href="/solicitudes/{PUBLIC_ID}"' in html
    assert 'href="/solicitudes/?estado_id=2"' in html
    assert "Volver" not in html


def test_panel_emisor_sin_datos_de_administracion(client, login_como, monkeypatch):
    monkeypatch.setattr("app.resumen_panel", lambda: RESUMEN_EMISOR)
    login_como("Emisor")

    html = client.get("/dashboard").get_data(as_text=True)

    assert "Resumen" in html
    assert "Actividad reciente" in html
    assert "Cliente Uno" in html
    assert "Usuarios" not in html
    assert "Clientes activos" not in html
    assert 'href="/admin/auditoria"' not in html
    assert "Volver" not in html


def test_panel_lector_sin_resumen(client, login_como, monkeypatch):
    monkeypatch.setattr("app.resumen_panel", lambda: None)
    login_como("Lector")

    respuesta = client.get("/dashboard")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Panel principal" in html
    assert "Actividad reciente" not in html
    assert "Volver" not in html


def test_resumen_panel_none_para_lector(app, login_como, client, monkeypatch):
    llamado = []
    monkeypatch.setattr(
        "app.models.get_db_connection", lambda: llamado.append(1)
    )
    login_como("Lector")

    client.get("/dashboard")

    assert llamado == []


def test_auditoria_usa_las_25_acciones_con_marcadores(
    client, login_como, monkeypatch
):
    consultas = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, parametros=None):
            consultas.append((sql, parametros))

        def fetchall(self):
            return []

    class Conexion:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(
        "app.admin.routes.get_db_connection", lambda: Conexion()
    )
    login_como("Administrador")

    assert client.get("/admin/auditoria").status_code == 200

    sql, parametros = consultas[0]
    # Las 25 acciones originales siguen visibles (Fase 5 suma 2 de adjuntos).
    assert set(ACCIONES_ORIGINALES) <= set(ACCIONES_VISIBLES)
    assert len(ACCIONES_ORIGINALES) == 25
    assert len(set(ACCIONES_VISIBLES)) == len(ACCIONES_VISIBLES)
    assert parametros == ACCIONES_VISIBLES
    assert sql.count("%s") == len(ACCIONES_VISIBLES)
    assert "'USUARIO_CREADO'" not in sql


def test_todas_las_acciones_visibles_tienen_etiqueta():
    assert set(ETIQUETAS_ACCION) == set(ACCIONES_VISIBLES)
