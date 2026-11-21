import pytest

from app import create_app
from app.models import get_db_connection
from config import TestingConfig


def test_create_app_exige_secret_key():
    class SinClave(TestingConfig):
        SECRET_KEY = ""

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(SinClave)


def test_conexion_usa_la_configuracion(app, monkeypatch):
    capturado = {}

    def conectar_falso(**kwargs):
        capturado.update(kwargs)
        return object()

    monkeypatch.setattr("app.models.pymysql.connect", conectar_falso)
    app.config.update(DB_HOST="db.local", DB_PORT="3307",
                      DB_USER="app", DB_PASSWORD="secreta", DB_NAME="bd_x")

    with app.app_context():
        get_db_connection()

    assert capturado["host"] == "db.local"
    assert capturado["port"] == 3307
    assert capturado["user"] == "app"
    assert capturado["password"] == "secreta"
    assert capturado["database"] == "bd_x"
    assert capturado["charset"] == "utf8mb4"


def test_carpetas_relativas_se_resuelven_desde_el_proyecto(monkeypatch, tmp_path):
    from config import BASE_DIR, _carpeta

    monkeypatch.setenv("CARPETA_PRUEBA", "Registros_Correo")
    assert _carpeta("CARPETA_PRUEBA", "x") == str(BASE_DIR / "Registros_Correo")

    monkeypatch.setenv("CARPETA_PRUEBA", str(tmp_path))
    assert _carpeta("CARPETA_PRUEBA", "x") == str(tmp_path)

    monkeypatch.delenv("CARPETA_PRUEBA")
    assert _carpeta("CARPETA_PRUEBA", "app/registros/sii") == str(
        BASE_DIR / "app" / "registros" / "sii"
    )
