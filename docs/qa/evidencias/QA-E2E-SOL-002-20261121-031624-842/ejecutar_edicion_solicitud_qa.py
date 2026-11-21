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
from urllib.request import ProxyHandler,build_opener

import pymysql
import pytest
from werkzeug.security import check_password_hash

warnings.simplefilter("error",getpass.GetPassWarning)
app_dir=Path(sys.argv[1]);evidencia=Path(__file__).resolve().parent
sys.path.insert(0,str(app_dir))
DB,USER,EMAIL="facturaciones_spa_qa","qa_facturaciones","qa.emisor@example.invalid"
PID_A="07738979a51988f9e9b80314703efdca"
PID_B="79abf9736ffbea95925ac870ebf2945c"
PID="ee2e8fdb51290c59ae0ab6457a3ba001"
BASE_CONCEPTO="QA-CREACION-WEB-80979053"
original_connect=pymysql.connect
resultado={"ejecucion":"QA-E2E-SOL-002","caso":"E2E-SOL-002","inicio":datetime.now().astimezone().isoformat(),
    "base":DB,"pruebas_iniciadas":False,"codigo_pytest":None,
    "alcance":"edicion propia de la solicitud 3; version, campos inmutables y auditoria"}
ctx={"eventos":[],"edicion_verificada":False}
servidor=None;hilo=None;clave_bd=None;codigo=2;antes=None;datos=None
MUTABLES={"concepto","nro_orden_compra","monto_bruto","tipo_afectacion","version","actualizado_en"}


def conectar_qa():
    return original_connect(host="127.0.0.1",port=3306,user=USER,password=clave_bd,database=DB,
        charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,connect_timeout=10,read_timeout=15,write_timeout=15)


def normalizar(objeto):
    return json.loads(json.dumps(objeto,default=str,ensure_ascii=True))


def leer_estado():
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT s.*,e.nombre AS estado_nombre,o.nombre AS origen_nombre FROM solicitudes s JOIN estados_solicitud e ON e.id=s.estado_id JOIN origenes_solicitud o ON o.id=s.origen_id ORDER BY s.id")
            filas=cur.fetchall()
            cur.execute("SELECT id,usuario_id,accion,detalle,creado_en FROM auditoria ORDER BY id")
            auditoria=cur.fetchall()
            conteos={}
            for tabla in ("facturas","registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"):
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`");conteos[tabla]=cur.fetchone()["total"]
        for f in filas:
            f.pop("clave_idempotencia",None);f.pop("huella_creacion",None)
        for a in auditoria:
            if isinstance(a["detalle"],str):a["detalle"]=json.loads(a["detalle"])
        return {"solicitudes":normalizar(filas),"auditoria":normalizar(auditoria),"conteos":conteos}
    finally:conn.close()


def por_pid(estado,pid):
    return next((s for s in estado["solicitudes"] if s["public_id"]==pid),None)


try:
    resultado["fase"]="verificacion_previa"
    print("Se editara UNA vez la solicitud creada por web (ID 3). Solo QA; no repetir tras un fallo sin revisar.")
    clave_bd=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    clave_web=getpass.getpass("Clave WEB de qa.emisor@example.invalid: ")
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad=cur.fetchone()
            if identidad!={"bd":DB,"cuenta":USER+"@127.0.0.1"}:raise RuntimeError("CONEXION_NO_ES_QA")
            resultado["cuenta_bd_verificada"]=identidad["cuenta"]
            cur.execute("SELECT u.id,u.nombre,u.password_hash,u.activo,u.debe_cambiar_password,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE u.email=%s",(EMAIL,))
            actor=cur.fetchone()
            if not actor or actor["id"]!=2 or actor["rol"]!="Emisor" or actor["activo"]!=1 or actor["debe_cambiar_password"]:raise RuntimeError("EMISOR_QA_NO_VALIDO")
            if not check_password_hash(actor["password_hash"],clave_web):raise RuntimeError("CLAVE_WEB_NO_COINCIDE")
            id_emisor=actor["id"]
    finally:conn.close()
    antes=leer_estado()
    base3=por_pid(antes,PID)
    if len(antes["solicitudes"])!=3 or len(antes["auditoria"])!=1 or any(v!=0 for v in antes["conteos"].values()):raise RuntimeError("ESTADO_PREVIO_NO_ESPERADO")
    if not base3 or base3["id"]!=3 or base3["emisor_id"]!=id_emisor or base3["version"]!=1 or base3["estado_nombre"]!="Pendiente" or base3["concepto"]!=BASE_CONCEPTO:raise RuntimeError("SOLICITUD_BASE_NO_ESPERADA")
    if antes["auditoria"][0]["accion"]!="SOLICITUD_CREADA" or not por_pid(antes,PID_A) or not por_pid(antes,PID_B):raise RuntimeError("AUDITORIA_O_FIXTURES_NO_ESPERADOS")
    marca=secrets.token_hex(4)
    datos={"concepto":"QA-EDITADA-WEB-"+marca,"monto_bruto":"412000","tipo_afectacion":"EXENTA","nro_orden_compra":"QA-OC-ED-"+marca}
    (evidencia/"datos-edicion.json").write_text(json.dumps({"antes":base3,"nuevos":datos},indent=2),encoding="utf-8")
    (evidencia/"estado-antes.json").write_text(json.dumps(antes,indent=2),encoding="utf-8")
    print("Cambios: concepto, monto 357000 a 412000, AFECTA a EXENTA, orden de compra. Fecha y cliente no cambian.")
    if input("Se conservara la edicion y su auditoria. Escribe EDITAR SOLICITUD QA: ").strip()!="EDITAR SOLICITUD QA":raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args,**kwargs):
        if args or kwargs.get("host")!="127.0.0.1" or int(kwargs.get("port",3306))!=3306 or kwargs.get("database")!=DB or kwargs.get("user")!=USER:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        for n,v in (("connect_timeout",10),("read_timeout",15),("write_timeout",15)):kwargs.setdefault(n,v)
        return original_connect(**kwargs)
    pymysql.connect=conexion_restringida
    import smtplib,imaplib
    def correo_bloqueado(*a,**k):raise RuntimeError("CORREO_REAL_BLOQUEADO_EN_QA")
    smtplib.SMTP=correo_bloqueado;smtplib.SMTP_SSL=correo_bloqueado;imaplib.IMAP4=correo_bloqueado;imaplib.IMAP4_SSL=correo_bloqueado
    from app import create_app
    from config import Config
    from flask import request
    from flask_login import current_user
    from werkzeug.serving import make_server
    class ConfigQA(Config):
        TESTING=False;DEBUG=False;SECRET_KEY=secrets.token_hex(32)
        WTF_CSRF_ENABLED=True;SESSION_COOKIE_SECURE=False;BANDEJA_REVISION_SEGUNDOS=0
        DB_HOST="127.0.0.1";DB_PORT=3306;DB_NAME=DB;DB_USER=USER;DB_PASSWORD=clave_bd
        SMTP_HOST="";SMTP_USER="";SMTP_PASSWORD="";IMAP_HOST="";IMAP_USER="";IMAP_PASSWORD=""
        XML_UPLOAD_FOLDER=str(evidencia/"datos-temporales"/"xml")
        ADJUNTOS_FOLDER=str(evidencia/"datos-temporales"/"adjuntos")
        CORREOS_FOLDER=str(evidencia/"datos-temporales"/"correos")
        SII_FOLDER=str(evidencia/"datos-temporales"/"sii")
    app=create_app(ConfigQA)
    @app.after_request
    def observar(respuesta):
        if request.path.startswith("/solicitudes/") or request.path in {"/auth/login","/auth/logout","/dashboard"}:
            ctx["eventos"].append({"ruta":request.path,"metodo":request.method,"status":respuesta.status_code,
                "location":respuesta.headers.get("Location"),"usuario_id":int(current_user.id) if current_user.is_authenticated else None})
        return respuesta
    handler=logging.FileHandler(evidencia/"servidor.log",encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for logger in (logging.getLogger("werkzeug"),app.logger):
        logger.handlers.clear();logger.addHandler(handler);logger.propagate=False;logger.setLevel(logging.INFO)
    servidor=make_server("127.0.0.1",0,app)
    base_url=f"http://127.0.0.1:{servidor.server_port}"
    hilo=threading.Thread(target=servidor.serve_forever,daemon=True);hilo.start()
    (evidencia/"servidor.json").write_text(json.dumps({"base_url":base_url,"base_datos":DB,"csrf_activo":True,
        "smtp_imap":"bloqueados","revision_automatica_segundos":0,"testing":False,"debug":False},indent=2),encoding="utf-8")
    with build_opener(ProxyHandler({})).open(base_url+"/auth/login",timeout=15) as r:
        resultado["http_login"]=r.status
        if r.status!=200:raise RuntimeError("LOGIN_NO_DEVUELVE_200")

    def verificar_persistencia():
        d=leer_estado()
        f=por_pid(d,PID)
        inmutables=bool(f) and all(f[k]==base3[k] for k in base3 if k not in MUTABLES)
        aisladas=all(por_pid(d,p)==por_pid(antes,p) for p in (PID_A,PID_B))
        ediciones=[a for a in d["auditoria"] if a["accion"]=="SOLICITUD_EDITADA" and a["detalle"].get("public_id")==PID]
        v={"total_solicitudes":len(d["solicitudes"]),"solicitud":f,"campos_inmutables_sin_cambios":inmutables,
            "solicitudes_aisladas_sin_cambios":aisladas,"total_auditoria":len(d["auditoria"]),
            "auditoria_creacion_sin_cambios":d["auditoria"][:1]==antes["auditoria"],
            "auditorias_edicion":ediciones,"conteos_relacionados":d["conteos"]}
        ctx["persistencia"]=v
        (evidencia/"verificacion-persistencia.json").write_text(json.dumps(v,indent=2),encoding="utf-8")
        return v

    ctx.update(base_url=base_url,evidencia=str(evidencia),email=EMAIL,password=clave_web,emisor_id=id_emisor,
        antes=base3,datos_nuevos=datos,public_id=PID,verificar_persistencia=verificar_persistencia)
    del clave_web
    class ContextoQA:
        def pytest_configure(self,config):config._qa_edit_context=ctx
    argumentos=["e2e/test_edicion_solicitud_qa.py","-o","addopts=","-v","-ra","--tb=short","--assert=plain",
        "--color=no","-p","no:cacheprovider",f"--junitxml={evidencia/'selenium-junit.xml'}"]
    (evidencia/"argumentos-pytest.json").write_text(json.dumps(argumentos,indent=2),encoding="utf-8")
    os.environ.pop("PYTEST_ADDOPTS",None)
    resultado["fase"]="ejecucion_selenium";resultado["pruebas_iniciadas"]=True
    with (evidencia/"selenium.log").open("w",encoding="utf-8") as log:
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):codigo=int(pytest.main(argumentos,plugins=[ContextoQA()]))
    resultado["codigo_pytest"]=codigo
except Exception as exc:
    resultado["error_tipo"]=type(exc).__name__
    if isinstance(exc,RuntimeError):resultado["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args and isinstance(exc.args[0],int):resultado["codigo_error_bd"]=exc.args[0]
    print("Ejecucion detenida. Revisar evidencia y datos antes de repetir.")
finally:
    ctx.pop("password",None)
    if servidor is not None:
        if hilo is not None and hilo.is_alive():servidor.shutdown();hilo.join(timeout=10)
        servidor.server_close();resultado["servidor_qa_detenido"]=hilo is None or not hilo.is_alive()
    if antes is not None:
        try:
            d=leer_estado()
            (evidencia/"estado-despues.json").write_text(json.dumps(d,indent=2),encoding="utf-8")
            resultado["total_solicitudes_despues"]=len(d["solicitudes"])
            resultado["total_auditoria_despues"]=len(d["auditoria"])
            resultado["version_despues"]=(por_pid(d,PID) or {}).get("version")
        except Exception as exc:resultado["error_verificacion_final"]=type(exc).__name__
    resultado["edicion_verificada"]=ctx["edicion_verificada"]
    resultado["persistencia"]=ctx.get("persistencia")
    resultado["eventos_http"]=ctx["eventos"]
    resultado["error_cierre_navegador"]=ctx.get("error_cierre_navegador")
    resultado["fin"]=datetime.now().astimezone().isoformat()
    resultado["junit_generado"]=(evidencia/"selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia/"resultado.json").write_text(json.dumps(resultado,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)