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
original_connect = pymysql.connect
resultado = {
    "ejecucion": "QA-E2E-NEG-001", "casos": ["E2E-AUTH-003", "E2E-AUTH-004"],
    "inicio": datetime.now().astimezone().isoformat(), "base": DB,
    "pruebas_iniciadas": False, "codigo_pytest": None,
}
ctx = {"eventos": [], "resultados": []}
servidor = None
hilo = None
codigo = 2
clave_bd = None


def conectar_qa():
    return original_connect(
        host="127.0.0.1", port=3306, user=USER, password=clave_bd,
        database=DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10, read_timeout=15, write_timeout=15,
    )


try:
    print("Dos pruebas negativas solo en QA. No se solicita la clave WEB valida.")
    clave_bd = getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    resultado["fase"] = "verificacion_previa"
    conn = conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad = cur.fetchone()
            if identidad != {"bd": DB, "cuenta": USER + "@127.0.0.1"}:
                raise RuntimeError("CONEXION_NO_ES_QA")
            cur.execute(
                "SELECT u.id,u.nombre,u.password_hash,u.ultimo_login,u.activo,"
                "u.debe_cambiar_password,r.nombre AS rol FROM usuarios u "
                "JOIN roles r ON r.id=u.rol_id WHERE u.email=%s", (EMAIL,),
            )
            actor = cur.fetchone()
            if not actor or actor["rol"] != "Administrador" or actor["activo"] != 1:
                raise RuntimeError("ADMINISTRADOR_QA_NO_VALIDO")
            if actor["nombre"] != "Administrador Sintetico QA" or actor["debe_cambiar_password"]:
                raise RuntimeError("ESTADO_ADMINISTRADOR_NO_ESPERADO")
            clave_invalida = secrets.token_urlsafe(24)
            if check_password_hash(actor["password_hash"], clave_invalida):
                raise RuntimeError("NO_SE_PUDO_PREPARAR_CLAVE_INCORRECTA")
            id_actor = actor["id"]
            anterior = actor["ultimo_login"]
            del actor["password_hash"]
            email_ausente = "qa.ausente." + secrets.token_hex(6) + "@example.invalid"
            cur.execute("SELECT COUNT(*) AS total FROM usuarios WHERE email=%s", (email_ausente,))
            if cur.fetchone()["total"] != 0:
                raise RuntimeError("CUENTA_NEGATIVA_NO_ESTA_AUSENTE")
            cur.execute("SELECT COUNT(*) AS total FROM usuarios")
            if cur.fetchone()["total"] != 1:
                raise RuntimeError("HAY_OTRAS_CUENTAS_REVISAR_DATOS_QA")
            for tabla in ("clientes", "solicitudes"):
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
                if cur.fetchone()["total"] != 0:
                    raise RuntimeError("HAY_DATOS_QA_NO_ESPERADOS")
        resultado["cuenta_bd_verificada"] = identidad["cuenta"]
        resultado["ultimo_login_antes"] = str(anterior) if anterior else None
    finally:
        conn.close()
    if input("Habra dos rechazos controlados en un servidor nuevo. Escribe NEGATIVA QA: ").strip() != "NEGATIVA QA":
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
    from flask import request
    from flask_login import current_user
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
    if app.config["LOGIN_MAX_INTENTOS"] < 2 or app.config["LOGIN_MAX_INTENTOS_IP"] < 3:
        raise RuntimeError("LIMITES_DE_LOGIN_DEMASIADO_BAJOS_PARA_DOS_CASOS_SIN_BLOQUEO")
    resultado["limites_login"] = {
        "por_cuenta": app.config["LOGIN_MAX_INTENTOS"],
        "por_ip": app.config["LOGIN_MAX_INTENTOS_IP"],
        "nota": "No se alteraron los limites heredados; servidor nuevo",
    }

    @app.after_request
    def observar_login(respuesta):
        if request.path == "/auth/login" and request.method == "POST":
            ctx["eventos"].append({
                "status": respuesta.status_code,
                "sesion_autenticada": bool(current_user.is_authenticated),
            })
        return respuesta

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
        "csrf_activo": True, "smtp_imap": "bloqueados", "debug": False,
        "testing": False, "revision_automatica_segundos": 0,
    }, indent=2), encoding="utf-8")
    with build_opener(ProxyHandler({})).open(base_url + "/auth/login", timeout=15) as r:
        resultado["http_login"] = r.status
        if r.status != 200:
            raise RuntimeError("LOGIN_NO_DEVUELVE_200")

    def ultimo_login_sin_cambios():
        conn = conectar_qa()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT ultimo_login FROM usuarios WHERE id=%s", (id_actor,))
                actual = cur.fetchone()["ultimo_login"]
            resultado["ultimo_login_despues"] = str(actual) if actual else None
            return actual == anterior
        finally:
            conn.close()

    ctx.update(base_url=base_url, evidencia=str(evidencia),
               emails={"clave_incorrecta": EMAIL, "cuenta_inexistente": email_ausente},
               clave_invalida=clave_invalida, ultimo_login_sin_cambios=ultimo_login_sin_cambios)
    del clave_invalida

    class ContextoQA:
        def pytest_configure(self, config):
            config._qa_negative_context = ctx

    argumentos = ["e2e/test_login_negativo_qa.py", "-o", "addopts=", "-v", "-ra",
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
    resultado["ultimo_login_sin_cambios"] = ultimo_login_sin_cambios()
    resultado["post_login_observados"] = ctx["eventos"]
    resultado["escenarios_verificados"] = ctx["resultados"]
except Exception as exc:
    resultado["error_tipo"] = type(exc).__name__
    if isinstance(exc, RuntimeError):
        resultado["error_controlado"] = str(exc)
    elif isinstance(exc, pymysql.MySQLError) and exc.args and isinstance(exc.args[0], int):
        resultado["codigo_error_bd"] = exc.args[0]
    print("Ejecucion detenida. Revisa resultado.json sin compartir claves.")
finally:
    ctx.pop("clave_invalida", None)
    if servidor is not None:
        if hilo is not None and hilo.is_alive():
            servidor.shutdown()
            hilo.join(timeout=10)
        servidor.server_close()
        resultado["servidor_qa_detenido"] = hilo is None or not hilo.is_alive()
    resultado["post_login_observados"] = ctx["eventos"]
    resultado["escenarios_verificados"] = ctx["resultados"]
    resultado["fin"] = datetime.now().astimezone().isoformat()
    resultado["junit_generado"] = (evidencia / "selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
raise SystemExit(codigo)