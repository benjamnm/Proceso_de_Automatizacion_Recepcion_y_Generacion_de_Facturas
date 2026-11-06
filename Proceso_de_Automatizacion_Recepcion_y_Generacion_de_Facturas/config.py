import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# El archivo .env vive junto a este config.py y nunca se versiona.
load_dotenv(BASE_DIR / ".env")


def _entero(nombre, por_defecto):
    valor = os.getenv(nombre, "").strip()
    return int(valor) if valor else por_defecto


def _booleano(nombre, por_defecto=False):
    valor = os.getenv(nombre, "").strip().lower()
    if not valor:
        return por_defecto
    return valor in {"1", "true", "si", "sí", "yes", "on"}


class Config:
    # Obligatoria: create_app() se niega a iniciar sin ella.
    SECRET_KEY = os.getenv("SECRET_KEY", "")

    # Base de datos (XAMPP por defecto, salvo la contraseña).
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = _entero("DB_PORT", 3306)
    DB_NAME = os.getenv("DB_NAME", "facturaciones_spa_mvp")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Sesión y cookies.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _booleano("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True

    # Almacenamiento privado de XML (fuera de /static).
    XML_UPLOAD_FOLDER = os.getenv(
        "XML_UPLOAD_FOLDER",
        str(BASE_DIR / "app" / "registros" / "xml"),
    )
    MAX_XML_UPLOAD_BYTES = 5 * 1024 * 1024
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    # SMTP (se usa a partir del Incremento 1).
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _entero("SMTP_PORT", 587)
    SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    SMTP_TIMEOUT = _entero("SMTP_TIMEOUT", 20)


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-solo-para-pruebas"
    WTF_CSRF_ENABLED = False
    DB_NAME = os.getenv("DB_NAME_TEST", "facturaciones_spa_mvp_test")
