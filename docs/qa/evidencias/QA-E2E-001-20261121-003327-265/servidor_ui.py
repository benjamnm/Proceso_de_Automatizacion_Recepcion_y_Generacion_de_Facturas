import json
import os
import secrets
import sys
from pathlib import Path

app_dir = Path(sys.argv[1])
evidencia = Path(sys.argv[2])
sys.path.insert(0, str(app_dir))

import pymysql
import smtplib
import imaplib


def conexion_prohibida(*args, **kwargs):
    raise RuntimeError("QA_UI_SMOKE: conexion de datos o correo no permitida")


pymysql.connect = conexion_prohibida
smtplib.SMTP = conexion_prohibida
smtplib.SMTP_SSL = conexion_prohibida
imaplib.IMAP4 = conexion_prohibida
imaplib.IMAP4_SSL = conexion_prohibida

from app import create_app
from config import Config
from werkzeug.serving import make_server


class ConfigUISmoke(Config):
    TESTING = False
    DEBUG = False
    SECRET_KEY = secrets.token_hex(32)
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = False
    BANDEJA_REVISION_SEGUNDOS = 0
    SMTP_HOST = ""
    SMTP_USER = ""
    SMTP_PASSWORD = ""
    IMAP_HOST = ""
    IMAP_USER = ""
    IMAP_PASSWORD = ""
    DB_HOST = "127.0.0.1"
    DB_NAME = "qa_ui_smoke_no_conectar"
    DB_USER = "qa_ui_smoke_no_conectar"
    DB_PASSWORD = ""
    XML_UPLOAD_FOLDER = str(evidencia / "datos-temporales" / "xml")
    ADJUNTOS_FOLDER = str(evidencia / "datos-temporales" / "adjuntos")
    CORREOS_FOLDER = str(evidencia / "datos-temporales" / "correos")
    SII_FOLDER = str(evidencia / "datos-temporales" / "sii")


app = create_app(ConfigUISmoke)
servidor = make_server("127.0.0.1", 0, app)
info = {
    "pid": os.getpid(),
    "base_url": f"http://127.0.0.1:{servidor.server_port}",
    "testing": app.testing,
    "debug": app.debug,
    "csrf_activo": app.config["WTF_CSRF_ENABLED"],
    "revision_automatica_segundos": app.config["BANDEJA_REVISION_SEGUNDOS"],
    "conexiones_mysql_smtp_imap": "bloqueadas en este proceso",
    "alcance": "pantalla publica; no apto para pruebas de autenticacion real",
}
(evidencia / "servidor.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
servidor.serve_forever()