"""Fase 2: búsqueda por cliente o concepto en el servidor."""
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from app.solicitudes import routes

ERROR_Q = "La búsqueda debe tener entre 2 y 100 caracteres."


def _filtros(app, monkeypatch, query, rol="Administrador", user_id=1):
    monkeypatch.setattr(
        routes,
        "current_user",
        SimpleNamespace(id=user_id, role_name=rol),
    )
    with app.test_request_context("/solicitudes/", query_string=query):
        return routes.construir_filtros()


def test_q_escapa_comodines_y_usa_dos_parametros(app, monkeypatch):
    where, parametros, _, errores = _filtros(
        app, monkeypatch, {"q": " 50%_a\\b "}
    )

    assert errores == []
    assert "(s.nombre LIKE %s OR s.concepto LIKE %s)" in where
    patron = "%50\\%\\_a\\\\b%"
    assert parametros == (patron, patron)


@pytest.mark.parametrize("valor", ["a", "x" * 101, "ab\x00c", "ab\nc"])
def test_q_invalida_da_error(app, monkeypatch, valor):
    where, parametros, _, errores = _filtros(app, monkeypatch, {"q": valor})

    assert errores == [ERROR_Q]
    assert "LIKE" not in where
    assert parametros == ()


def test_q_vacia_se_ignora(app, monkeypatch):
    where, parametros, _, errores = _filtros(app, monkeypatch, {"q": "   "})

    assert (where, parametros, errores) == ("", (), [])


def test_q_de_100_caracteres_es_valida(app, monkeypatch):
    _, _, _, errores = _filtros(app, monkeypatch, {"q": "x" * 100})

    assert errores == []


@pytest.mark.parametrize("valor", ["abc", "0", "-1", "4294967296"])
def test_cliente_id_invalido(app, monkeypatch, valor):
    where, _, _, errores = _filtros(app, monkeypatch, {"cliente_id": valor})

    assert errores == ["El filtro 'cliente_id' no es válido."]
    assert "cliente_id" not in where


def test_cliente_id_valido(app, monkeypatch):
    where, parametros, _, errores = _filtros(
        app, monkeypatch, {"cliente_id": "5"}
    )

    assert errores == []
    assert where == "WHERE s.cliente_id = %s"
    assert parametros == (5,)


def test_emisor_conserva_su_alcance_al_buscar(app, monkeypatch):
    where, parametros, _, errores = _filtros(
        app, monkeypatch, {"q": "servicio", "cliente_id": "5"},
        rol="Emisor", user_id=7,
    )

    assert errores == []
    assert where.startswith("WHERE s.emisor_id = %s AND ")
    assert parametros[0] == 7
    assert "s.cliente_id = %s" in where


def _conexion_simulada(sql_ejecutado, total=25):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, parametros=None):
            sql_ejecutado.append((sql, parametros))

        def fetchall(self):
            return []

        def fetchone(self):
            return {"total": total}

    class Conexion:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    return Conexion()


def test_paginacion_conserva_q_y_cliente(client, login_como, monkeypatch):
    sql = []
    monkeypatch.setattr(
        "app.solicitudes.routes.get_db_connection",
        lambda: _conexion_simulada(sql),
    )
    login_como("Administrador")

    respuesta = client.get(
        "/solicitudes/",
        query_string={"q": "asesoría", "cliente_id": "5"},
    )
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Siguiente" in html

    href = html.split("Siguiente")[0].rsplit('href="', 1)[1].split('"')[0]
    argumentos = parse_qs(urlparse(href.replace("&amp;", "&")).query)

    assert argumentos["q"] == ["asesoría"]
    assert argumentos["cliente_id"] == ["5"]
    assert argumentos["pagina"] == ["2"]


def test_emisor_solo_ve_sus_clientes_en_selector(
    client, login_como, monkeypatch
):
    sql = []
    monkeypatch.setattr(
        "app.solicitudes.routes.get_db_connection",
        lambda: _conexion_simulada(sql, total=0),
    )
    login_como("Emisor", user_id=7)

    client.get("/solicitudes/")

    consulta, parametros = next(
        (s, p) for s, p in sql if "razon_social" in s
    )
    assert "WHERE s.emisor_id = %s" in consulta
    assert parametros == (7,)


def test_admin_ve_todos_los_clientes_en_selector(
    client, login_como, monkeypatch
):
    sql = []
    monkeypatch.setattr(
        "app.solicitudes.routes.get_db_connection",
        lambda: _conexion_simulada(sql, total=0),
    )
    login_como("Administrador")

    client.get("/solicitudes/")

    consulta, _ = next((s, p) for s, p in sql if "razon_social" in s)
    assert "WHERE" not in consulta
    assert "activo" not in consulta
