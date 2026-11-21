"""Fase 4: sección "Perfiles y permisos" (solo lectura)."""
import pytest

from app.permisos import CAPACIDADES, ROLES

PUBLIC_ID = "c" * 32

CASOS_DENEGADOS = [
    (texto, ruta, rol)
    for texto, permitidos, ruta in CAPACIDADES
    if ruta
    for rol in ROLES
    if rol not in permitidos
]


@pytest.mark.parametrize("texto,ruta,rol", CASOS_DENEGADOS)
def test_matriz_coincide_con_permisos_reales(
    client, login_como, texto, ruta, rol
):
    """Si un rol sin permiso no recibe 403, la matriz miente."""
    login_como(rol)

    assert client.get(ruta).status_code == 403, (texto, ruta, rol)


def test_solo_admin_valida_facturas(client, login_como):
    permitidos = {t: p for t, p, _ in CAPACIDADES}["Validar facturas"]
    assert permitidos == {"Administrador"}
    login_como("Emisor")

    for accion in ("aprobar", "observar"):
        respuesta = client.post(f"/solicitudes/{PUBLIC_ID}/factura/{accion}")
        assert respuesta.status_code == 403


def test_emisor_solo_consulta_sus_solicitudes(app, monkeypatch):
    """Fila "Consultar todas las solicitudes": el Emisor queda acotado."""
    from types import SimpleNamespace

    from app.solicitudes import routes

    monkeypatch.setattr(
        routes, "current_user", SimpleNamespace(id=7, role_name="Emisor")
    )
    with app.test_request_context("/solicitudes/"):
        where, parametros, _, _ = routes.construir_filtros()

    assert where == "WHERE s.emisor_id = %s"
    assert parametros == (7,)


def test_todos_los_roles_ven_el_panel():
    texto, permitidos, ruta = CAPACIDADES[0]
    assert ruta == "/dashboard"
    assert permitidos == set(ROLES)


PERFILES = [
    {"id": 1, "nombre": "Administrador",
     "descripcion": "Acceso completo al sistema", "usuarios_activos": 1},
    {"id": 2, "nombre": "Emisor",
     "descripcion": "Puede crear y gestionar sus solicitudes",
     "usuarios_activos": 3},
    {"id": 3, "nombre": "Lector",
     "descripcion": "<b>Lectura</b>", "usuarios_activos": 0},
]


def test_seccion_perfiles_para_admin(client, login_como, monkeypatch):
    consultas = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, parametros=None):
            consultas.append(sql)

        def fetchall(self):
            if "usuarios_activos" in consultas[-1]:
                return PERFILES
            if "FROM roles" in consultas[-1]:
                return [{"id": p["id"], "nombre": p["nombre"]} for p in PERFILES]
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

    respuesta = client.get("/admin/usuarios")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Perfiles y permisos" in html
    assert "Acceso completo al sistema" in html
    assert "&lt;b&gt;Lectura&lt;/b&gt;" in html
    for texto, _, _ in CAPACIDADES:
        assert texto in html
    assert 'aria-label="Permitido"' in html
    assert "No permitido" in html

    sql_perfiles = next(s for s in consultas if "usuarios_activos" in s)
    assert "u.activo = 1" in sql_perfiles
    assert not any(
        s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for s in consultas
    )
