import contextlib
import csv
import getpass
import hashlib
import json
import logging
import os
import re
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

warnings.simplefilter("error",getpass.GetPassWarning)
app_dir=Path(sys.argv[1])
fixture_dir=Path(sys.argv[2])
evidencia=Path(__file__).resolve().parent
sys.path.insert(0,str(app_dir))
DB,USER="facturaciones_spa_qa","qa_facturaciones"
original_connect=pymysql.connect
resultado={"ejecucion":"QA-E2E-HORIZ-001","casos":["E2E-HORIZ-001","E2E-HORIZ-002"],
    "inicio":datetime.now().astimezone().isoformat(),"base":DB,"pruebas_iniciadas":False,"codigo_pytest":None,
    "alcance":"listado propio; detalle y formulario propios; GET y POST ajenos; snapshots sin cambios"}
ctx={"cuentas":{},"solicitudes":{},"eventos":[],"verificaciones":[],"emisores_completados":[],"errores_cierre":[]}
servidor=None
hilo=None
clave_bd=None
codigo=2
antes=None


def conectar_qa():
    return original_connect(host="127.0.0.1",port=3306,user=USER,password=clave_bd,
        database=DB,charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,read_timeout=15,write_timeout=15)


def snapshot():
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM solicitudes ORDER BY id")
            filas=cur.fetchall()
        texto=json.dumps(filas,sort_keys=True,ensure_ascii=True,default=str,separators=(",",":"))
        return {"filas":json.loads(texto),"sha256":hashlib.sha256(texto.encode("utf-8")).hexdigest()}
    finally:
        conn.close()


try:
    resultado["fase"]="verificacion_fixture"
    with (fixture_dir/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
        hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
    origen=fixture_dir/"fixtures-aislamiento.json"
    if hashlib.sha256(origen.read_bytes()).hexdigest()!=hashes.get(origen.name):
        raise RuntimeError("HASH_DE_FIXTURES_NO_COINCIDE")
    fixture=json.loads(origen.read_text(encoding="utf-8-sig"))
    if fixture.get("base")!=DB or fixture.get("id")!="QA-DATOS-003":
        raise RuntimeError("FIXTURES_NO_ESPERADOS")
    solicitudes={s["etiqueta"]:s for s in fixture["solicitudes"]}
    if set(solicitudes)!={"A","B"} or len(fixture["solicitudes"])!=2:
        raise RuntimeError("SE_NECESITAN_DOS_SOLICITUDES")
    if len({s["public_id"] for s in solicitudes.values()})!=2 or any(not re.fullmatch(r"[0-9a-f]{32}",s["public_id"]) for s in solicitudes.values()):
        raise RuntimeError("IDENTIFICADORES_NO_VALIDOS")
    if fixture["emisor_a"]["email"]!="qa.emisor@example.invalid" or fixture["emisor_b"]["email"]!="qa.emisor2@example.invalid":
        raise RuntimeError("EMISORES_NO_ESPERADOS")
    (evidencia/"fixtures-utilizados.json").write_text(json.dumps(fixture,ensure_ascii=True,indent=2),encoding="utf-8")
    print("Solo QA: dos emisores; acceso propio y un POST de edicion ajena por cada uno.")
    print("Se espera que los POST sean rechazados; si se modifica un fixture se detiene sin restaurarlo.")
    clave_bd=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    resultado["fase"]="verificacion_base"
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad=cur.fetchone()
            if identidad!={"bd":DB,"cuenta":USER+"@127.0.0.1"}:
                raise RuntimeError("CONEXION_NO_ES_QA")
            resultado["cuenta_bd_verificada"]=identidad["cuenta"]
            cur.execute("SELECT u.id,u.nombre,u.email,u.password_hash,u.activo,u.debe_cambiar_password,u.ultimo_login,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id")
            usuarios=cur.fetchall()
            if len(usuarios)!=4 or {u["email"] for u in usuarios}!={"qa.admin@example.invalid","qa.emisor@example.invalid","qa.lector@example.invalid","qa.emisor2@example.invalid"}:
                raise RuntimeError("CUENTAS_QA_NO_ESPERADAS")
            for etiqueta,clave in (("A","emisor_a"),("B","emisor_b")):
                f=fixture[clave]
                u=next(u for u in usuarios if u["email"]==f["email"])
                if u["id"]!=f["id"] or u["nombre"]!=f["nombre"] or u["rol"]!="Emisor" or u["activo"]!=1 or u["debe_cambiar_password"]:
                    raise RuntimeError("EMISOR_QA_NO_VALIDO")
                ctx["cuentas"][etiqueta]={"id":u["id"],"email":u["email"],"nombre":u["nombre"]}
            conteos={}
            for tabla in ("usuarios","clientes","solicitudes"):
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`")
                conteos[tabla]=cur.fetchone()["total"]
            if conteos!={"usuarios":4,"clientes":1,"solicitudes":2}:
                raise RuntimeError("DATOS_QA_NO_ESPERADOS")
            cur.execute("SELECT s.*,e.nombre AS estado_nombre FROM solicitudes s JOIN estados_solicitud e ON e.id=s.estado_id ORDER BY s.id")
            filas=cur.fetchall()
            for etiqueta,f in solicitudes.items():
                actual=next((s for s in filas if s["public_id"]==f["public_id"]),None)
                if not actual or actual["id"]!=f["id"] or actual["emisor_id"]!=ctx["cuentas"][etiqueta]["id"] or actual["concepto"]!=f["concepto"]:
                    raise RuntimeError("PROPIEDAD_DE_SOLICITUD_NO_COINCIDE")
                if actual["version"]!=1 or actual["estado_nombre"]!="Pendiente" or actual["cliente_id"]!=fixture["cliente"]["id"]:
                    raise RuntimeError("ESTADO_DE_SOLICITUD_NO_ESPERADO")
                ctx["solicitudes"][etiqueta]={
                    "id":actual["id"],"public_id":actual["public_id"],"concepto":actual["concepto"],
                    "version":actual["version"],"cliente_id":actual["cliente_id"],"monto_bruto":str(actual["monto_bruto"]),
                    "fecha_emision":actual["fecha_emision"].isoformat(),"tipo_afectacion":actual["tipo_afectacion"],
                    "nro_orden_compra":actual["nro_orden_compra"]}
        for etiqueta in ("A","B"):
            cuenta=ctx["cuentas"][etiqueta]
            u=next(u for u in usuarios if u["id"]==cuenta["id"])
            clave=getpass.getpass("Clave WEB de "+cuenta["email"]+": ")
            if not check_password_hash(u["password_hash"],clave):
                raise RuntimeError("CLAVE_WEB_NO_COINCIDE_NO_SE_INICIARA_PRUEBA")
            cuenta["password"]=clave
            del clave
        for u in usuarios:
            del u["password_hash"]
    finally:
        conn.close()
    antes=snapshot()
    (evidencia/"solicitudes-antes.json").write_text(json.dumps(antes,indent=2),encoding="utf-8")
    if input("Autorizar pruebas GET y POST sobre fixtures QA. Escribe AISLAMIENTO QA: ").strip()!="AISLAMIENTO QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args,**kwargs):
        if args or kwargs.get("host")!="127.0.0.1" or int(kwargs.get("port",3306))!=3306:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        if kwargs.get("database")!=DB or kwargs.get("user")!=USER:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        for nombre,valor in (("connect_timeout",10),("read_timeout",15),("write_timeout",15)):
            kwargs.setdefault(nombre,valor)
        return original_connect(**kwargs)

    pymysql.connect=conexion_restringida
    import smtplib
    import imaplib
    def correo_bloqueado(*args,**kwargs):
        raise RuntimeError("CORREO_REAL_BLOQUEADO_EN_QA")
    smtplib.SMTP=correo_bloqueado
    smtplib.SMTP_SSL=correo_bloqueado
    imaplib.IMAP4=correo_bloqueado
    imaplib.IMAP4_SSL=correo_bloqueado
    from app import create_app
    from config import Config
    from flask import request
    from flask_login import current_user
    from werkzeug.serving import make_server

    class ConfigQA(Config):
        TESTING=False
        DEBUG=False
        SECRET_KEY=secrets.token_hex(32)
        WTF_CSRF_ENABLED=True
        SESSION_COOKIE_SECURE=False
        BANDEJA_REVISION_SEGUNDOS=0
        DB_HOST="127.0.0.1"
        DB_PORT=3306
        DB_NAME=DB
        DB_USER=USER
        DB_PASSWORD=clave_bd
        SMTP_HOST=""
        SMTP_USER=""
        SMTP_PASSWORD=""
        IMAP_HOST=""
        IMAP_USER=""
        IMAP_PASSWORD=""
        XML_UPLOAD_FOLDER=str(evidencia/"datos-temporales"/"xml")
        ADJUNTOS_FOLDER=str(evidencia/"datos-temporales"/"adjuntos")
        CORREOS_FOLDER=str(evidencia/"datos-temporales"/"correos")
        SII_FOLDER=str(evidencia/"datos-temporales"/"sii")

    app=create_app(ConfigQA)
    @app.after_request
    def observar(respuesta):
        if request.path.startswith("/solicitudes/") or request.path in {"/auth/login","/auth/logout","/dashboard"}:
            ctx["eventos"].append({"ruta":request.path,"metodo":request.method,"status":respuesta.status_code,
                "usuario_id":int(current_user.id) if current_user.is_authenticated else None})
        return respuesta

    handler=logging.FileHandler(evidencia/"servidor.log",encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for logger in (logging.getLogger("werkzeug"),app.logger):
        logger.handlers.clear();logger.addHandler(handler);logger.propagate=False;logger.setLevel(logging.INFO)
    servidor=make_server("127.0.0.1",0,app)
    base_url=f"http://127.0.0.1:{servidor.server_port}"
    hilo=threading.Thread(target=servidor.serve_forever,daemon=True)
    hilo.start()
    (evidencia/"servidor.json").write_text(json.dumps({"base_url":base_url,"base_datos":DB,
        "csrf_activo":True,"testing":False,"debug":False,"smtp_imap":"bloqueados",
        "revision_automatica_segundos":0},indent=2),encoding="utf-8")
    with build_opener(ProxyHandler({})).open(base_url+"/auth/login",timeout=15) as r:
        resultado["http_login"]=r.status
        if r.status!=200:raise RuntimeError("LOGIN_NO_DEVUELVE_200")

    def solicitudes_sin_cambios():
        actual=snapshot()
        (evidencia/"solicitudes-despues.json").write_text(json.dumps(actual,indent=2),encoding="utf-8")
        return actual==antes

    ctx.update(base_url=base_url,evidencia=str(evidencia),solicitudes_sin_cambios=solicitudes_sin_cambios)
    class ContextoQA:
        def pytest_configure(self,config):config._qa_horizontal_context=ctx
    argumentos=["e2e/test_aislamiento_emisores_qa.py","-o","addopts=","-v","-ra","-x",
        "--tb=short","--assert=plain","--color=no","-p","no:cacheprovider",
        f"--junitxml={evidencia/'selenium-junit.xml'}"]
    (evidencia/"argumentos-pytest.json").write_text(json.dumps(argumentos,indent=2),encoding="utf-8")
    os.environ.pop("PYTEST_ADDOPTS",None)
    resultado["fase"]="ejecucion_selenium"
    resultado["pruebas_iniciadas"]=True
    with (evidencia/"selenium.log").open("w",encoding="utf-8") as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            codigo=int(pytest.main(argumentos,plugins=[ContextoQA()]))
    resultado["codigo_pytest"]=codigo
except Exception as exc:
    resultado["error_tipo"]=type(exc).__name__
    if isinstance(exc,RuntimeError):resultado["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args and isinstance(exc.args[0],int):resultado["codigo_error_bd"]=exc.args[0]
    print("Ejecucion detenida. Revisar resultado.json sin compartir claves.")
finally:
    for cuenta in ctx["cuentas"].values():cuenta.pop("password",None)
    if servidor is not None:
        if hilo is not None and hilo.is_alive():servidor.shutdown();hilo.join(timeout=10)
        servidor.server_close()
        resultado["servidor_qa_detenido"]=hilo is None or not hilo.is_alive()
    if antes is not None:
        try:
            despues=snapshot()
            (evidencia/"solicitudes-despues.json").write_text(json.dumps(despues,indent=2),encoding="utf-8")
            resultado["solicitudes_sin_cambios"]=despues==antes
        except Exception as exc:
            resultado["error_verificacion_final"]=type(exc).__name__
    resultado["emisores_completados"]=ctx["emisores_completados"]
    resultado["verificaciones_http"]=ctx["verificaciones"]
    resultado["eventos_http"]=ctx["eventos"]
    resultado["errores_cierre_navegador"]=ctx["errores_cierre"]
    resultado["fin"]=datetime.now().astimezone().isoformat()
    resultado["junit_generado"]=(evidencia/"selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia/"resultado.json").write_text(json.dumps(resultado,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)