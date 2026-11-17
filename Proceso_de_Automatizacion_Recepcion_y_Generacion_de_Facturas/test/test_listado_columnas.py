"""Fase 1: columnas Concepto, Origen y Responsable en el listado."""
from datetime import date
from decimal import Decimal

FILA = {
    "public_id": "a" * 32,
    "rut": "11111111-1",
    "nombre": "Cliente Uno",
    "fecha_emision": date(2026, 1, 10),
    "monto_bruto": Decimal("119000"),
    "email_emisor": "emisor@test.cl",
    "concepto": "<b>x</b>",
    "estado_nombre": "Pendiente",
    "origen_nombre": "Web",
    "responsable_nombre": "Ana Responsable",
}


def _conexion_con_filas(filas, sql_ejecutado):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, *args):
            sql_ejecutado.append(sql)

        def fetchall(self):
            if sql_ejecutado and "s.public_id" in sql_ejecutado[-1]:
                return filas
            return []

        def fetchone(self):
            return {"total": len(filas)}

    class Conexion:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    return Conexion()


def _listado(client, login_como, monkeypatch, rol):
    sql = []
    monkeypatch.setattr(
        "app.solicitudes.routes.get_db_connection",
        lambda: _conexion_con_filas([FILA], sql),
    )
    login_como(rol)
    respuesta = client.get("/solicitudes/")
    assert respuesta.status_code == 200
    return respuesta.get_data(as_text=True), sql


def test_admin_ve_columna_responsable(client, login_como, monkeypatch):
    html, _ = _listado(client, login_como, monkeypatch, "Administrador")

    assert '<th scope="col">Responsable</th>' in html
    assert "Ana Responsable" in html
    assert '<th scope="col">Concepto</th>' in html
    assert '<th scope="col">Origen</th>' in html


def test_emisor_no_ve_columna_responsable(client, login_como, monkeypatch):
    html, _ = _listado(client, login_como, monkeypatch, "Emisor")

    assert '<th scope="col">Responsable</th>' not in html
    assert "Ana Responsable" not in html
    assert '<th scope="col">Concepto</th>' in html
    assert '<th scope="col">Origen</th>' in html


def test_concepto_se_escapa(client, login_como, monkeypatch):
    html, _ = _listado(client, login_como, monkeypatch, "Administrador")

    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_consulta_usa_joins_que_no_filtran(client, login_como, monkeypatch):
    _, sql = _listado(client, login_como, monkeypatch, "Emisor")

    datos = next(s for s in sql if "s.public_id" in s)
    conteo = next(s for s in sql if "COUNT(*)" in s)

    assert "LEFT JOIN usuarios AS u" in datos
    assert "INNER JOIN origenes_solicitud AS o" in datos
    assert "JOIN" not in conteo
