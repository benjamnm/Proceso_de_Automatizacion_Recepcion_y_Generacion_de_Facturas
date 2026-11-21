import json
import os
import secrets
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

app_dir = Path(sys.argv[1])
evidencia = Path(__file__).resolve().parent
sys.path.insert(0, str(app_dir))
resultado = {
    "ejecucion": "QA-E2E-002", "caso": "E2E-LOGIN-001",
    "inicio": datetime.now().astimezone().isoformat(),
    "pruebas_iniciadas": False, "codigo_pytest": None,
    "servidor_iniciado": False,
    "modalidad": "servidor WSGI propio en hilo; sin comparacion de PID",
}
servidor = None
hilo = None
codigo = 2
try:
    import pymysql
    import smtplib
    import imaplib

    def conexion_prohibida(*args, **kwargs):
        raise RuntimeError("QA_UI_SMOKE: conexion MySQL/SMTP/IMAP no permitida")

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
    base_url = f"http://127.0.0.1:{servidor.server_port}"
    hilo = threading.Thread(target=servidor.serve_forever, name="qa-ui-smoke", daemon=True)
    hilo.start()
    resultado["servidor_iniciado"] = True
    info = {
        "base_url": base_url, "pid_orquestador": os.getpid(),
        "csrf_activo": app.config["WTF_CSRF_ENABLED"],
        "testing": app.testing, "debug": app.debug,
        "revision_automatica_segundos": app.config["BANDEJA_REVISION_SEGUNDOS"],
        "conexiones_mysql_smtp_imap": "bloqueadas en el proceso servidor",
        "alcance": "pantalla publica; sin autenticacion real",
    }
    (evidencia / "servidor.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    opener = build_opener(ProxyHandler({}))
    with opener.open(base_url + "/auth/login", timeout=15) as respuesta:
        if respuesta.status != 200:
            raise RuntimeError("El login no devolvio HTTP 200")
        resultado["http_login"] = respuesta.status
    entorno = dict(os.environ, E2E_EVIDENCIA=str(evidencia), E2E_BASE_URL=base_url,
                   PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    argumentos = [sys.executable, "-X", "utf8", "-m", "pytest", "e2e/test_login_smoke.py",
                  "-o", "addopts=", "-v", "-ra", "--tb=short", "--color=no",
                  f"--junitxml={evidencia / 'selenium-junit.xml'}"]
    (evidencia / "comando-pytest.json").write_text(json.dumps(argumentos, indent=2), encoding="utf-8")
    with (evidencia / "selenium.log").open("w", encoding="utf-8") as log:
        resultado["pruebas_iniciadas"] = True
        prueba = subprocess.run(argumentos, cwd=app_dir, env=entorno,
                               stdout=log, stderr=subprocess.STDOUT)
    codigo = prueba.returncode
    resultado["codigo_pytest"] = codigo
except Exception as exc:
    resultado["error_orquestacion"] = str(exc)
    print(str(exc), file=sys.stderr)
finally:
    if servidor is not None:
        if hilo is not None and hilo.is_alive():
            servidor.shutdown()
            hilo.join(timeout=10)
        servidor.server_close()
        resultado["servidor_qa_detenido"] = hilo is None or not hilo.is_alive()
    else:
        resultado["servidor_qa_detenido"] = None
    resultado["fin"] = datetime.now().astimezone().isoformat()
    resultado["junit_generado"] = (evidencia / "selenium-junit.xml").exists()
    (evidencia / "resultado-ejecucion.json").write_text(json.dumps(resultado, indent=2), encoding="utf-8")
raise SystemExit(codigo)