import contextlib
import getpass
import json
import logging
import os
import secrets
import sys
import threading
import warnings
from datetime import datetime
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import pymysql
import pytest
from werkzeug.security import check_password_hash

warnings.simplefilter("error", getpass.GetPassWarning)
app_dir = Path(sys.argv[1])
evidencia = Path(__file__).resolve().parent
sys.path.insert(0, str(app_dir))
DB, USER, EMAIL = "facturaciones_spa_qa", "qa_facturaciones", "qa.admin@example.invalid"
resultado = {
    "ejecucion": "QA-E2E-AUTH-001", "caso": "E2E-AUTH-002",
    "inicio": datetime.now().astimezone().isoformat(), "base": DB,
    "pruebas_iniciadas": False, "codigo_pytest": None,
}
servidor = None
hilo = None
ctx = {}
codigo = 2
original_connect = pymysql.connect
clave_bd = None


def conectar_qa():
    return original_connect(
        host="127.0.0.1", port=3306, user=USER, password=clave_bd,
        database=DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10, read_timeout=15, write_timeout=15,
    )


try:
    print("Solo QA. No se usaran credenciales del .env para conectar a la base.")
    clave_bd = getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    clave_web = getpass.getpass("Clave WEB de qa.admin@example.invalid: ")
    resultado["fase"] = "verificacion_previa"
    conn = conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad = cur.fetchone()
            if identidad != {"bd": DB, "cuenta": USER + "@127.0.0.1"}:
                raise RuntimeError("CONEXION_NO_ES_QA")
            cur.execute(
                "SELECT u.id,u.nombre,u.password_hash,u.activo,u.debe_cambiar_password,"
                "u.ultimo_login,r.nombre AS rol FROM usuarios u "
                "JOIN roles r ON r.id=u.rol_id WHERE u.email=%s", (EMAIL,),
            )
            actor = cur.fetchone()
            if not actor or actor["rol"] != "Administrador" or actor["activo"] != 1:
                raise RuntimeError("ADMINISTRADOR_QA_NO_VALIDO")
            if actor["nombre"] != "Administrador Sintetico QA" or actor["debe_cambiar_password"]:
                raise RuntimeError("ESTADO_ADMINISTRADOR_NO_ESPERADO")
            if not check_password_hash(actor["password_hash"], clave_web):
                raise RuntimeError("CLAVE_WEB_NO_COINCIDE_NO_SE_INTENTARA_LOGIN")
            anterior = actor["ultimo_login"]
            id_actor = actor["id"]
            del actor["password_hash"]
            for tabla in ("clientes", "solicitudes"):
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
                if cur.fetchone()["total"] != 0:
                    raise RuntimeError("DATOS_QA_NO_ESPERADOS")
            cur.execute("SELECT COUNT(*) AS total FROM usuarios")
            if cur.fetchone()["total"] != 1:
                raise RuntimeError("HAY_OTRAS_CUENTAS_REVISAR_ANTES_DE_CAPTURAR")
        resultado["cuenta_bd_verificada"] = identidad["cuenta"]
        resultado["ultimo_login_antes"] = str(anterior) if anterior else None
    finally:
        conn.close()
    if input("Se actualizara ultimo_login solo en QA. Escribe PROBAR QA: ").strip() != "PROBAR QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args, **kwargs):
        if args or kwargs.get("host") != "127.0.0.1" or int(kwargs.get("port", 3306)) != 3306:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        if kwargs.get("database") != DB or kwargs.get("user") != USER:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        kwargs.setdefault("connect_timeout", 10)
        kwargs.setdefault("read_timeout", 15)
        kwargs.setdefault("write_timeout", 15)
        return original_connect(**kwargs)

    pymysql.connect = conexion_restringida
    import smtplib
    import imaplib

    def correo_bloqueado(*args, **kwargs):
        raise RuntimeError("CORREO_REAL_BLOQUEADO_EN_QA")

    smtplib.SMTP = correo_bloqueado
    smtplib.SMTP_SSL = correo_bloqueado
    imaplib.IMAP4 = correo_bloqueado
    imaplib.IMAP4_SSL = correo_bloqueado
    from app import create_app
    from config import Config
    from werkzeug.serving import make_server

    class ConfigQA(Config):
        TESTING = False
        DEBUG = False
        SECRET_KEY = secrets.token_hex(32)
        WTF_CSRF_ENABLED = True
        SESSION_COOKIE_SECURE = False
        BANDEJA_REVISION_SEGUNDOS = 0
        DB_HOST = "127.0.0.1"
        DB_PORT = 3306
        DB_NAME = DB
        DB_USER = USER
        DB_PASSWORD = clave_bd
        SMTP_HOST = ""
        SMTP_USER = ""
        SMTP_PASSWORD = ""
        IMAP_HOST = ""
        IMAP_USER = ""
        IMAP_PASSWORD = ""
        XML_UPLOAD_FOLDER = str(evidencia / "datos-temporales" / "xml")
        ADJUNTOS_FOLDER = str(evidencia / "datos-temporales" / "adjuntos")
        CORREOS_FOLDER = str(evidencia / "datos-temporales" / "correos")
        SII_FOLDER = str(evidencia / "datos-temporales" / "sii")

    app = create_app(ConfigQA)
    handler = logging.FileHandler(evidencia / "servidor.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for logger in (logging.getLogger("werkzeug"), app.logger):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.INFO)
    servidor = make_server("127.0.0.1", 0, app)
    base_url = f"http://127.0.0.1:{servidor.server_port}"
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    (evidencia / "servidor.json").write_text(json.dumps({
        "base_url": base_url, "base_datos": DB, "cuenta_bd": USER,
        "csrf_activo": True, "debug": False, "testing": False,
        "smtp_imap": "bloqueados", "revision_automatica_segundos": 0,
    }, indent=2), encoding="utf-8")
    with build_opener(ProxyHandler({})).open(base_url + "/auth/login", timeout=15) as r:
        resultado["http_login"] = r.status
        if r.status != 200:
            raise RuntimeError("LOGIN_NO_DEVUELVE_200")

    def ultimo_login_actualizado():
        conn = conectar_qa()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT ultimo_login FROM usuarios WHERE id=%s", (id_actor,))
                actual = cur.fetchone()["ultimo_login"]
            resultado["ultimo_login_despues"] = str(actual) if actual else None
            return actual is not None and (anterior is None or actual > anterior)
        finally:
            conn.close()

    ctx.update(base_url=base_url, evidencia=str(evidencia), email=EMAIL,
               password=clave_web, envios_login=0, ultimo_login_actualizado=ultimo_login_actualizado)
    del clave_web

    class ContextoQA:
        def pytest_configure(self, config):
            config._qa_auth_context = ctx

    argumentos = ["e2e/test_login_auth_qa.py", "-o", "addopts=", "-v", "-ra",
                  "--tb=short", "--assert=plain", "--color=no", "-p", "no:cacheprovider",
                  f"--junitxml={evidencia / 'selenium-junit.xml'}"]
    (evidencia / "argumentos-pytest.json").write_text(json.dumps(argumentos, indent=2), encoding="utf-8")
    os.environ.pop("PYTEST_ADDOPTS", None)
    resultado["fase"] = "ejecucion_selenium"
    resultado["pruebas_iniciadas"] = True
    with (evidencia / "selenium.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            codigo = int(pytest.main(argumentos, plugins=[ContextoQA()]))
    resultado["codigo_pytest"] = codigo
    resultado["envios_login_navegador"] = ctx["envios_login"]
except Exception as exc:
    resultado["error_tipo"] = type(exc).__name__
    if isinstance(exc, RuntimeError):
        resultado["error_controlado"] = str(exc)
    elif isinstance(exc, pymysql.MySQLError) and exc.args and isinstance(exc.args[0], int):
        resultado["codigo_error_bd"] = exc.args[0]
    print("Ejecucion detenida. Revisar resultado.json sin compartir claves.")
finally:
    ctx.pop("password", None)
    if servidor is not None:
        if hilo is not None and hilo.is_alive():
            servidor.shutdown()
            hilo.join(timeout=10)
        servidor.server_close()
        resultado["servidor_qa_detenido"] = hilo is None or not hilo.is_alive()
    resultado["fin"] = datetime.now().astimezone().isoformat()
    resultado["junit_generado"] = (evidencia / "selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia / "resultado.json").write_text(json.dumps(resultado, indent=2), encoding="utf-8")
raise SystemExit(codigo)