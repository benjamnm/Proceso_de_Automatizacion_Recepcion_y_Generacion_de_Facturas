import sys
from pathlib import Path

import pytest
from flask_login.utils import _create_identifier

# Permite "from app import ..." y "from config import ..." al ejecutar pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.models import User
from config import TestingConfig


@pytest.fixture
def app(tmp_path):
    class Config(TestingConfig):
        XML_UPLOAD_FOLDER = str(tmp_path / "xml")

    return create_app(Config)


@pytest.fixture
def client(app):
    return app.test_client()


def usuario_falso(user_id=1, rol="Administrador"):
    return User(
        id=user_id, rol_id=1, rut="11111111-1", nombre=f"Usuario {rol}",
        email=f"{rol.lower()}@test.cl", telefono=None, password_hash="x",
        activo=1, ultimo_login=None, creado_en=None,
        role={"nombre": rol},
    )


@pytest.fixture
def login_como(client, monkeypatch):
    """Inicia sesión con un usuario simulado, sin tocar la base de datos."""
    def _login(rol="Administrador", user_id=1):
        usuario = usuario_falso(user_id, rol)
        monkeypatch.setattr(
            User, "get_by_id", classmethod(lambda cls, _id: usuario)
        )
        with client.application.test_request_context(
            environ_base=client.environ_base
        ):
            identificador = _create_identifier()
        with client.session_transaction() as sesion:
            sesion["_user_id"] = str(user_id)
            sesion["_fresh"] = True
            sesion["_id"] = identificador
        return usuario

    return _login
