"""Cambio, restablecimiento y recuperación de contraseñas."""
import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app.security import CLAVE_HUELLA
from app.services import contrasenas
from app.services.contrasenas import (
    ALFABETO_TEMPORAL,
    ErrorPassword,
    generar_temporal,
    huella_sesion,
    validar_nueva,
)


def flashes(client):
    with client.session_transaction() as sesion:
        return [m for _, m in sesion.get("_flashes", [])]


# --- Reglas ----------------------------------------------------------------

def test_temporal_es_aleatoria_y_sin_caracteres_ambiguos():
    claves = {generar_temporal() for _ in range(50)}
    assert len(claves) == 50
    for clave in claves:
        assert len(clave) == 16
        assert set(clave) <= set(ALFABETO_TEMPORAL)
        assert not set(clave) & set("0O1lI")


@pytest.mark.parametrize("nueva,confirmacion,mensaje", [
    ("corta", "corta", "entre 12 y 128"),
    ("x" * 129, "x" * 129, "entre 12 y 128"),
    ("una-clave-larga", "otra-clave-larga", "no coinciden"),
])
def test_valida_la_contrasena_nueva(nueva, confirmacion, mensaje):
    with pytest.raises(ErrorPassword, match=mensaje):
        validar_nueva(nueva, confirmacion)


def test_huella_cambia_con_la_contrasena_y_no_expone_el_hash():
    h1 = huella_sesion("hash-a", "secreto")
    assert h1 == huella_sesion("hash-a", "secreto")
    assert h1 != huella_sesion("hash-b", "secreto")
    assert h1 != huella_sesion("hash-a", "otro-secreto")
    assert "hash-a" not in h1


# --- Servicio con una BD simulada ------------------------------------------

class Cursor:
    def __init__(self, bd):
        self.bd = bd
        self.rowcount = 0
        self.lastrowid = 99

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, parametros=None):
        self.bd.consultas.append((" ".join(sql.split()), parametros))
        self.rowcount = 1

    def fetchone(self):
        sql = self.bd.consultas[-1][0]
        for clave, fila in self.bd.respuestas.items():
            if clave in sql:
                return fila
        return None


class Conexion:
    def __init__(self, respuestas):
        self.consultas = []
        self.respuestas = respuestas
        self.confirmada = False

    def cursor(self):
        return Cursor(self)

    def begin(self):
        pass

    def commit(self):
        self.confirmada = True

    def rollback(self):
        pass

    def close(self):
        pass


def _bd(monkeypatch, respuestas):
    conexion = Conexion(respuestas)
    monkeypatch.setattr(contrasenas, "get_db_connection", lambda: conexion)
    return conexion


ADMIN = {"id": 1, "activo": 1, "rol_nombre": "Administrador"}
OBJETIVO = {"id": 7, "nombre": "Ana", "email": "ana@empresa.cl", "activo": 1}


def test_restablecer_genera_temporal_sin_dejarla_en_auditoria(app, monkeypatch):
    bd = _bd(monkeypatch, {"FROM usuarios AS u": ADMIN, "FROM usuarios WHERE": OBJETIVO})

    with app.app_context():
        resultado = contrasenas.restablecer(1, 7, "generar", exigir_cambio=False)

    clave = resultado["password"]
    assert len(clave) == 16
    assert resultado["exigir_cambio"] is True      # temporal: siempre se cambia
    assert bd.confirmada

    update = next(p for s, p in bd.consultas if s.startswith("UPDATE usuarios"))
    assert check_password_hash(update[0], clave)
    assert update[1:] == (1, 7)

    auditoria = next(p for s, p in bd.consultas if "INSERT INTO auditoria" in s)
    assert auditoria[1] == "PASSWORD_RESTABLECIDA"
    assert clave not in auditoria[2] and update[0] not in auditoria[2]

    assert any("recuperaciones_password" in s and "ATENDIDA" in s
               for s, _ in bd.consultas)


def test_restablecer_definida_respeta_exigir_cambio(app, monkeypatch):
    bd = _bd(monkeypatch, {"FROM usuarios AS u": ADMIN, "FROM usuarios WHERE": OBJETIVO})

    with app.app_context():
        resultado = contrasenas.restablecer(
            1, 7, "definir", "clave-definida-123", "clave-definida-123",
            exigir_cambio=False,
        )

    assert resultado["password"] is None
    update = next(p for s, p in bd.consultas if s.startswith("UPDATE usuarios"))
    assert check_password_hash(update[0], "clave-definida-123")
    assert update[1] == 0


@pytest.mark.parametrize("actor,usuario_id,mensaje", [
    ({"id": 1, "activo": 1, "rol_nombre": "Emisor"}, 7, "autorización"),
    (ADMIN, 1, "propia cuenta"),
])
def test_restablecer_rechaza(app, monkeypatch, actor, usuario_id, mensaje):
    bd = _bd(monkeypatch, {"FROM usuarios AS u": actor, "FROM usuarios WHERE": OBJETIVO})

    with app.app_context(), pytest.raises(ErrorPassword, match=mensaje):
        contrasenas.restablecer(1, usuario_id, "generar")

    assert not bd.confirmada


def test_restablecer_no_toca_la_cuenta_tecnica(app, monkeypatch):
    tecnica = dict(OBJETIVO, email=app.config["SISTEMA_CORREO_EMAIL"])
    _bd(monkeypatch, {"FROM usuarios AS u": ADMIN, "FROM usuarios WHERE": tecnica})

    with app.app_context(), pytest.raises(ErrorPassword, match="técnica"):
        contrasenas.restablecer(1, 7, "generar")


def test_cambiar_propia_exige_la_actual(app, monkeypatch):
    fila = {"id": 7, "password_hash": generate_password_hash("clave-actual-123"),
            "activo": 1}
    _bd(monkeypatch, {"FROM usuarios": fila})

    with app.app_context(), pytest.raises(ErrorPassword, match="actual no es correcta"):
        contrasenas.cambiar_propia(7, "otra-cosa-123", "clave-nueva-1234", "clave-nueva-1234")


def test_cambiar_propia_guarda_y_quita_la_obligacion(app, monkeypatch):
    fila = {"id": 7, "password_hash": generate_password_hash("clave-actual-123"),
            "activo": 1}
    bd = _bd(monkeypatch, {"FROM usuarios": fila})

    with app.app_context():
        nuevo = contrasenas.cambiar_propia(
            7, "clave-actual-123", "clave-nueva-1234", "clave-nueva-1234"
        )

    assert check_password_hash(nuevo, "clave-nueva-1234")
    update = next(p for s, p in bd.consultas if s.startswith("UPDATE usuarios"))
    assert update == (nuevo, 0, 7)


def test_recuperacion_no_duplica_pendientes(app, monkeypatch):
    bd = _bd(monkeypatch, {
        "FROM usuarios": {"id": 7, "nombre": "Ana", "email": "ana@empresa.cl"},
        "FROM recuperaciones_password": {"id": 3},
    })

    with app.app_context():
        assert contrasenas.solicitar_recuperacion("ANA@empresa.cl") is None

    assert bd.consultas[0][1] == ("ana@empresa.cl",)
    assert not any(s.startswith("INSERT") for s, _ in bd.consultas)


def test_recuperacion_registra_y_audita(app, monkeypatch):
    bd = _bd(monkeypatch, {
        "FROM usuarios": {"id": 7, "nombre": "Ana", "email": "ana@empresa.cl"},
    })

    with app.app_context():
        usuario = contrasenas.solicitar_recuperacion("ana@empresa.cl", "10.0.0.1")

    assert usuario["recuperacion_id"] == 99
    acciones = [p[1] for s, p in bd.consultas if "INSERT INTO auditoria" in s]
    assert acciones == ["PASSWORD_RECUPERACION_SOLICITADA"]


# --- Rutas -------------------------------------------------------------------

@pytest.mark.parametrize("devuelve", [None, {"id": 7, "nombre": "Ana"}])
def test_recuperar_responde_igual_exista_o_no(client, monkeypatch, devuelve):
    avisos = []
    monkeypatch.setattr("app.auth.routes.solicitar_recuperacion",
                        lambda email, ip: devuelve)
    monkeypatch.setattr("app.auth.routes.avisar_recuperacion_a_admins",
                        avisos.append)

    respuesta = client.post("/auth/recuperar", data={"email": "x@y.cl"})

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/auth/login")
    assert any("Si el correo corresponde" in m for m in flashes(client))
    assert avisos == ([devuelve] if devuelve else [])


def test_recuperar_limita_por_ip(client, app, monkeypatch):
    monkeypatch.setattr("app.auth.routes.solicitar_recuperacion",
                        lambda email, ip: None)
    for _ in range(app.config["RECUPERACION_MAX_IP"]):
        client.post("/auth/recuperar", data={"email": "x@y.cl"})

    assert client.post("/auth/recuperar", data={"email": "x@y.cl"}).status_code == 429


def test_login_muestra_enlace_de_recuperacion(client):
    html = client.get("/auth/login").get_data(as_text=True)
    assert "/auth/recuperar" in html


def test_temporal_obliga_a_cambiarla(client, login_como):
    usuario = login_como("Emisor")
    usuario.debe_cambiar_password = True

    respuesta = client.get("/dashboard")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/auth/password")

    html = client.get("/auth/password").get_data(as_text=True)
    assert "contraseña temporal" in html


def test_sesion_se_cierra_si_la_contrasena_cambio(client, login_como):
    login_como("Emisor")
    with client.session_transaction() as sesion:
        sesion[CLAVE_HUELLA] = "huella-de-una-contrasena-anterior"

    respuesta = client.get("/dashboard")

    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_cambiar_password_mantiene_la_sesion_actual(client, app, login_como, monkeypatch):
    login_como("Lector", user_id=3)
    monkeypatch.setattr("app.auth.routes.cambiar_propia",
                        lambda **kwargs: "hash-nuevo")

    respuesta = client.post("/auth/password", data={
        "password_actual": "a", "password": "b", "password_confirm": "b",
    })

    assert respuesta.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as sesion:
        assert sesion[CLAVE_HUELLA] == huella_sesion("hash-nuevo", app.config["SECRET_KEY"])


def test_cambiar_password_muestra_error(client, login_como, monkeypatch):
    login_como("Emisor")

    def falla(**kwargs):
        raise ErrorPassword("La contraseña actual no es correcta.")

    monkeypatch.setattr("app.auth.routes.cambiar_propia", falla)
    html = client.post("/auth/password", data={}).get_data(as_text=True)
    assert "La contraseña actual no es correcta." in html


@pytest.mark.parametrize("ruta", [
    "/admin/usuarios/7/password", "/admin/recuperaciones/3/descartar",
])
def test_solo_admin_restablece(client, login_como, ruta):
    login_como("Emisor")
    assert client.post(ruta, data={"modo": "generar"}).status_code == 403


def test_admin_ve_la_temporal_una_vez_y_no_en_la_sesion(client, login_como, monkeypatch):
    llamadas = []

    def falso(**kwargs):
        llamadas.append(kwargs)
        return {"usuario": OBJETIVO, "password": "TemporalSegura23", "exigir_cambio": True}

    monkeypatch.setattr("app.admin.routes.restablecer", falso)
    login_como("Administrador", user_id=1)

    respuesta = client.post("/admin/usuarios/7/password", data={"modo": "generar"})
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "TemporalSegura23" in html
    assert llamadas[0]["actor_id"] == 1 and llamadas[0]["usuario_id"] == 7
    with client.session_transaction() as sesion:
        assert "TemporalSegura23" not in str(dict(sesion))


def test_admin_descarta_recuperacion(client, login_como, monkeypatch):
    llamadas = []
    monkeypatch.setattr("app.admin.routes.descartar_recuperacion",
                        lambda *args: llamadas.append(args))
    login_como("Administrador", user_id=1)

    respuesta = client.post("/admin/recuperaciones/3/descartar")

    assert respuesta.headers["Location"].endswith("/admin/usuarios")
    assert llamadas == [(1, 3, "127.0.0.1")]
