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
DB, USER = "facturaciones_spa_qa", "qa_facturaciones"
original_connect = pymysql.connect
resultado = {"ejecucion": "QA-E2E-RBAC-001", "casos": ["E2E-RBAC-001", "E2E-RBAC-002"],
    "inicio": datetime.now().astimezone().isoformat(), "base": DB,
    "pruebas_iniciadas": False, "codigo_pytest": None,
    "alcance": "permisos verticales GET; no decide HU13 ni prueba aislamiento entre emisores"}
ctx = {"cuentas": {}, "eventos": [], "verificaciones": [], "perfiles_completados": [], "errores_cierre": []}
servidor = None
hilo = None
clave_bd = None
codigo = 2
previos_login = {}
ids = {}


def conectar_qa():
    return original_connect(host="127.0.0.1", port=3306, user=USER, password=clave_bd,
        database=DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10, read_timeout=15, write_timeout=15)


try:
    print("Prueba de Emisor y Lector solo en QA. Dos logins; consultas GET de permisos.")
    clave_bd = getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    resultado["fase"] = "verificacion_previa"
    conn = conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad = cur.fetchone()
            if identidad != {"bd": DB, "cuenta": USER + "@127.0.0.1"}:
                raise RuntimeError("CONEXION_NO_ES_QA")
            cur.execute("SELECT u.id,u.nombre,u.email,u.password_hash,u.activo,u.debe_cambiar_password,"
                "u.ultimo_login,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id")
            filas = cur.fetchall()
            esperadas = {
                "qa.admin@example.invalid": ("Administrador", "Administrador Sintetico QA"),
                "qa.emisor@example.invalid": ("Emisor", "Emisor Sintetico QA"),
                "qa.lector@example.invalid": ("Lector", "Lector Sintetico QA"),
            }
            if len(filas) != 3 or {f["email"] for f in filas} != set(esperadas):
                raise RuntimeError("CUENTAS_QA_NO_ESPERADAS")
            for fila in filas:
                rol, nombre = esperadas[fila["email"]]
                if fila["rol"] != rol or fila["nombre"] != nombre or fila["activo"] != 1 or fila["debe_cambiar_password"]:
                    raise RuntimeError("ESTADO_DE_CUENTA_NO_ESPERADO")
                previos_login[rol] = fila["ultimo_login"]
                ids[rol] = fila["id"]
            for tabla in ("clientes", "solicitudes"):
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
                if cur.fetchone()["total"] != 0:
                    raise RuntimeError("HAY_DATOS_DE_NEGOCIO_NO_ESPERADOS")
        for rol in ("Emisor", "Lector"):
            fila = next(f for f in filas if f["rol"] == rol)
            clave = getpass.getpass("Clave WEB de " + fila["email"] + ": ")
            if not check_password_hash(fila["password_hash"], clave):
                raise RuntimeError("CLAVE_WEB_NO_COINCIDE_NO_SE_INICIARA_LA_PRUEBA")
            ctx["cuentas"][rol] = {"email": fila["email"], "nombre": fila["nombre"], "password": clave}
            del clave
        for fila in filas:
            del fila["password_hash"]
        resultado["cuenta_bd_verificada"] = identidad["cuenta"]
        resultado["ultimo_login_antes"] = {rol: str(v) if v else None for rol,v in previos_login.items()}
    finally:
        conn.close()
    if input("Se actualizaran los ultimos accesos de Emisor y Lector QA. Escribe PERFILES QA: ").strip() != "PERFILES QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args, **kwargs):
        if args or kwargs.get("host") != "127.0.0.1" or int(kwargs.get("port",3306)) != 3306:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        if kwargs.get("database") != DB or kwargs.get("user") != USER:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        for nombre, valor in (("connect_timeout",10),("read_timeout",15),("write_timeout",15)):
            kwargs.setdefault(nombre, valor)
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
    rutas_observadas = {"/auth/login", "/auth/logout", "/dashboard", "/solicitudes/",
        "/admin/usuarios", "/clientes/", "/admin/correos", "/admin/auditoria"}

    @app.after_request
    def observar(respuesta):
        if request.path in rutas_observadas:
            ctx["eventos"].append({"ruta": request.path,"metodo": request.method,
                "status": respuesta.status_code,
                "perfil": current_user.role_name if current_user.is_authenticated else None})
        return respuesta

    handler = logging.FileHandler(evidencia / "servidor.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for logger in (logging.getLogger("werkzeug"), app.logger):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.INFO)
    servidor = make_server("127.0.0.1",0,app)
    base_url = f"http://127.0.0.1:{servidor.server_port}"
    hilo = threading.Thread(target=servidor.serve_forever,daemon=True)
    hilo.start()
    (evidencia / "servidor.json").write_text(json.dumps({"base_url":base_url,
        "base_datos":DB,"csrf_activo":True,"smtp_imap":"bloqueados",
        "revision_automatica_segundos":0,"testing":False,"debug":False},indent=2),encoding="utf-8")
    with build_opener(ProxyHandler({})).open(base_url+"/auth/login",timeout=15) as r:
        resultado["http_login"] = r.status
        if r.status != 200:
            raise RuntimeError("LOGIN_NO_DEVUELVE_200")

    def ultimo_login_actualizado(rol):
        conn=conectar_qa()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT ultimo_login FROM usuarios WHERE id=%s",(ids[rol],))
                actual=cur.fetchone()["ultimo_login"]
            return actual is not None and (previos_login[rol] is None or actual>previos_login[rol])
        finally:
            conn.close()

    ctx.update(base_url=base_url,evidencia=str(evidencia),ultimo_login_actualizado=ultimo_login_actualizado)
    class ContextoQA:
        def pytest_configure(self,config):
            config._qa_rbac_context=ctx
    argumentos=["e2e/test_perfiles_verticales_qa.py","-o","addopts=","-v","-ra",
        "--tb=short","--assert=plain","--color=no","-p","no:cacheprovider",
        f"--junitxml={evidencia / 'selenium-junit.xml'}"]
    (evidencia / "argumentos-pytest.json").write_text(json.dumps(argumentos,indent=2),encoding="utf-8")
    os.environ.pop("PYTEST_ADDOPTS",None)
    resultado["fase"]="ejecucion_selenium"
    resultado["pruebas_iniciadas"]=True
    with (evidencia / "selenium.log").open("w",encoding="utf-8") as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            codigo=int(pytest.main(argumentos,plugins=[ContextoQA()]))
    resultado["codigo_pytest"]=codigo
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT u.email,u.ultimo_login,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id ORDER BY u.email")
            despues=cur.fetchall()
        resultado["ultimo_login_despues"]={f["rol"]:str(f["ultimo_login"]) if f["ultimo_login"] else None for f in despues}
        admin=next(f for f in despues if f["rol"]=="Administrador")
        resultado["ultimo_login_admin_sin_cambios"]=admin["ultimo_login"]==previos_login["Administrador"]
    finally:
        conn.close()
except Exception as exc:
    resultado["error_tipo"]=type(exc).__name__
    if isinstance(exc,RuntimeError):
        resultado["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args and isinstance(exc.args[0],int):
        resultado["codigo_error_bd"]=exc.args[0]
    print("Ejecucion detenida; revisa resultado.json sin compartir claves.")
finally:
    for cuenta in ctx["cuentas"].values():
        cuenta.pop("password",None)
    if servidor is not None:
        if hilo is not None and hilo.is_alive():
            servidor.shutdown()
            hilo.join(timeout=10)
        servidor.server_close()
        resultado["servidor_qa_detenido"]=hilo is None or not hilo.is_alive()
    resultado["perfiles_completados"]=ctx["perfiles_completados"]
    resultado["verificaciones_http"]=ctx["verificaciones"]
    resultado["eventos_http"]=ctx["eventos"]
    resultado["errores_cierre_navegador"]=ctx["errores_cierre"]
    resultado["hu13"]="PENDIENTE; no se evalua acceso historico del Lector"
    resultado["fin"]=datetime.now().astimezone().isoformat()
    resultado["junit_generado"]=(evidencia / "selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia / "resultado.json").write_text(json.dumps(resultado,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)