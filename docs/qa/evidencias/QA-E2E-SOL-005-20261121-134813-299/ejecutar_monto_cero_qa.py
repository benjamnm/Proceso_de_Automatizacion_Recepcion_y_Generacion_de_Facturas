import contextlib
import csv
import getpass
import hashlib
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
app_dir=Path(sys.argv[1]);referencia=Path(sys.argv[2]);evidencia=Path(__file__).resolve().parent
sys.path.insert(0,str(app_dir))
DB,USER,EMAIL="facturaciones_spa_qa","qa_facturaciones","qa.emisor@example.invalid"
PID="ee2e8fdb51290c59ae0ab6457a3ba001"
original_connect=pymysql.connect
resultado={"ejecucion":"QA-E2E-SOL-005","caso":"E2E-SOL-005","inicio":datetime.now().astimezone().isoformat(),
    "base":DB,"pruebas_iniciadas":False,"codigo_pytest":None,
    "alcance":"un POST real con monto cero; error de servidor y de campo; sin cambios de datos ni auditoria"}
ctx={"eventos":[],"monto_cero_rechazado":False,"aviso_verificado":False}
servidor=None;hilo=None;clave_bd=None;codigo=2;antes=None


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


def por_pid(estado):
    return next((s for s in estado["solicitudes"] if s["public_id"]==PID),None)


try:
    resultado["fase"]="verificacion_previa"
    with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
        hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
    archivo=referencia/"estado-final.json"
    if hashlib.sha256(archivo.read_bytes()).hexdigest()!=hashes.get(archivo.name):raise RuntimeError("HASH_REFERENCIA_NO_COINCIDE")
    esperado=json.loads(archivo.read_text(encoding="utf-8-sig"))
    resultado["referencia_estado_sha256"]=hashes[archivo.name]
    print("Solo QA. Un envio real con monto 0 en ID 3. Se espera rechazo y conservar el monto 459000.")
    clave_bd=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    clave_web=getpass.getpass("Clave WEB de qa.emisor@example.invalid: ")
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad=cur.fetchone()
            if identidad!={"bd":DB,"cuenta":USER+"@127.0.0.1"}:raise RuntimeError("CONEXION_NO_ES_QA")
            resultado["cuenta_bd_verificada"]=identidad["cuenta"]
            cur.execute("SELECT u.id,u.password_hash,u.activo,u.debe_cambiar_password,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE u.email=%s",(EMAIL,))
            actor=cur.fetchone()
            if not actor or actor["id"]!=2 or actor["rol"]!="Emisor" or actor["activo"]!=1 or actor["debe_cambiar_password"]:raise RuntimeError("EMISOR_QA_NO_VALIDO")
            if not check_password_hash(actor["password_hash"],clave_web):raise RuntimeError("CLAVE_WEB_NO_COINCIDE")
            del actor["password_hash"]
    finally:conn.close()
    antes=leer_estado()
    original=por_pid(antes)
    if antes!=esperado:raise RuntimeError("ESTADO_QA_CAMBIO_DESDE_SOL_003_REVISAR_SIN_RESTAURAR")
    if len(antes["solicitudes"])!=3 or len(antes["auditoria"])!=3 or not original or original["version"]!=3 or original["emisor_id"]!=2 or original["estado_nombre"]!="Pendiente":raise RuntimeError("ESTADO_PREVIO_NO_ESPERADO")
    (evidencia/"estado-antes.json").write_text(json.dumps(antes,indent=2),encoding="utf-8")
    if input("Autorizar intento con monto cero. Escribe PROBAR MONTO CERO QA: ").strip()!="PROBAR MONTO CERO QA":raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args,**kwargs):
        if args or kwargs.get("host")!="127.0.0.1" or int(kwargs.get("port",3306))!=3306 or kwargs.get("database")!=DB or kwargs.get("user")!=USER:raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
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
            edicion=request.method=="POST" and request.path=="/solicitudes/"+PID+"/editar"
            evento={"ruta":request.path,"metodo":request.method,"status":respuesta.status_code,
                "location":respuesta.headers.get("Location"),
                "version_formulario":request.form.get("version") if edicion else None,
                "usuario_id":int(current_user.id) if current_user.is_authenticated else None}
            if edicion:
                evento["campos_recibidos"]={k:request.form.get(k) for k in ("cliente_id","concepto","monto_bruto","fecha_emision","tipo_afectacion","nro_orden_compra")}
            ctx["eventos"].append(evento)
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

    def verificar():
        estado=leer_estado()
        actual=por_pid(estado)
        v={"total_solicitudes":len(estado["solicitudes"]),"total_auditoria":len(estado["auditoria"]),
            "version":actual.get("version") if actual else None,"solicitud":actual,
            "solicitudes_sin_cambios":estado["solicitudes"]==antes["solicitudes"],
            "auditoria_sin_cambios":estado["auditoria"]==antes["auditoria"],
            "conteos_relacionados_sin_cambios":estado["conteos"]==antes["conteos"],
            "estado_comparado_sin_cambios":estado==antes}
        (evidencia/"verificacion-persistencia.json").write_text(json.dumps(v,indent=2),encoding="utf-8")
        ctx["verificacion"]=v
        return v
    ctx.update(base_url=base_url,evidencia=str(evidencia),email=EMAIL,password=clave_web,public_id=PID,solicitud=original,verificar=verificar)
    del clave_web
    class ContextoQA:
        def pytest_configure(self,config):config._qa_zero_context=ctx
    argumentos=["e2e/test_monto_cero_solicitud_qa.py","-o","addopts=","-v","-ra","--tb=short","--assert=plain",
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
    print("Ejecucion detenida. Conservar datos y revisar evidencia antes de repetir.")
finally:
    ctx.pop("password",None)
    if servidor is not None:
        if hilo is not None and hilo.is_alive():servidor.shutdown();hilo.join(timeout=10)
        servidor.server_close();resultado["servidor_qa_detenido"]=hilo is None or not hilo.is_alive()
    if antes is not None:
        try:
            final=leer_estado()
            (evidencia/"estado-final.json").write_text(json.dumps(final,indent=2),encoding="utf-8")
            resultado["total_solicitudes_despues"]=len(final["solicitudes"])
            resultado["total_auditoria_despues"]=len(final["auditoria"])
            resultado["version_despues"]=(por_pid(final) or {}).get("version")
            resultado["estado_comparado_sin_cambios"]=final==antes
        except Exception as exc:resultado["error_verificacion_final"]=type(exc).__name__
    resultado["monto_cero_rechazado"]=ctx["monto_cero_rechazado"]
    resultado["aviso_verificado"]=ctx["aviso_verificado"]
    resultado["error_monto_verificado"]=ctx.get("error_monto_verificado",False)
    resultado["verificacion"]=ctx.get("verificacion")
    resultado["eventos_http"]=ctx["eventos"]
    resultado["error_cierre_navegador"]=ctx.get("error_cierre_navegador")
    resultado["fin"]=datetime.now().astimezone().isoformat()
    resultado["junit_generado"]=(evidencia/"selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia/"resultado.json").write_text(json.dumps(resultado,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)