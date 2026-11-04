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

    # SMTP: correo de salida.
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _entero("SMTP_PORT", 587)
    SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "")
    SMTP_TIMEOUT = _entero("SMTP_TIMEOUT", 20)

    # IMAP: correo de entrada (bandeja que recibe las solicitudes).
    IMAP_HOST = os.getenv("IMAP_HOST", "")
    IMAP_PORT = _entero("IMAP_PORT", 993)
    IMAP_SECURITY = os.getenv("IMAP_SECURITY", "ssl").lower()
    IMAP_USER = os.getenv("IMAP_USER", "")
    IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")
    IMAP_MAILBOX = os.getenv("IMAP_MAILBOX", "INBOX")
    IMAP_TIMEOUT = _entero("IMAP_TIMEOUT", 30)
    IMAP_MAX_MENSAJES = _entero("IMAP_MAX_MENSAJES", 25)
    IMAP_MAX_BYTES = _entero("IMAP_MAX_BYTES", 10 * 1024 * 1024)

    # Repositorios privados (fuera de /static).
    CORREOS_FOLDER = os.getenv(
        "CORREOS_FOLDER",
        str(BASE_DIR / "app" / "registros" / "correos"),
    )
    SII_FOLDER = os.getenv(
        "SII_FOLDER",
        str(BASE_DIR / "app" / "registros" / "sii"),
    )

    # Usuario técnico creado por la migración 003.
    SISTEMA_CORREO_EMAIL = os.getenv(
        "SISTEMA_CORREO_EMAIL", "sistema.correo@facturaciones.cl"
    )

    # Avisos al Administrador. Vacío = todos los Administradores activos.
    NOTIFICAR_A = os.getenv("NOTIFICAR_A", "")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000")

    # Datos del emisor para el archivo DTE (SII).
    EMPRESA_RUT = os.getenv("EMPRESA_RUT", "")
    EMPRESA_RAZON_SOCIAL = os.getenv("EMPRESA_RAZON_SOCIAL", "")
    EMPRESA_GIRO = os.getenv("EMPRESA_GIRO", "")
    EMPRESA_ACTECO = os.getenv("EMPRESA_ACTECO", "")
    EMPRESA_DIRECCION = os.getenv("EMPRESA_DIRECCION", "")
    EMPRESA_COMUNA = os.getenv("EMPRESA_COMUNA", "")


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-solo-para-pruebas"
    WTF_CSRF_ENABLED = False
    DB_NAME = os.getenv("DB_NAME_TEST", "facturaciones_spa_mvp_test")
