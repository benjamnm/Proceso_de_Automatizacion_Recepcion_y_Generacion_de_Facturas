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
resultado={"ejecucion":"QA-E2E-FAC-003-CIERRE","caso":"E2E-FAC-003-CIERRE","inicio":datetime.now().astimezone().isoformat(),
    "base":DB,"pruebas_iniciadas":False,"codigo_pytest":None,
    "alcance":"Verifica correccion existente y factura historica; logout; sin editar ni reenviar; complementa intento fallido"}
ctx={"eventos":[],"verificacion_complementaria_y_logout":False,"intentos_smtp":0}
servidor=None;hilo=None;clave_bd=None;codigo=2;antes=None


def conectar_qa():
    return original_connect(host="127.0.0.1",port=3306,user=USER,password=clave_bd,database=DB,
        charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,connect_timeout=10,read_timeout=15,write_timeout=15)


def normalizar(objeto):return json.loads(json.dumps(objeto,default=str,ensure_ascii=True))


def leer_estado():
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT s.*,e.nombre AS estado_nombre,o.nombre AS origen_nombre FROM solicitudes s JOIN estados_solicitud e ON e.id=s.estado_id JOIN origenes_solicitud o ON o.id=s.origen_id ORDER BY s.id")
            solicitudes=cur.fetchall()
            cur.execute("SELECT id,usuario_id,accion,detalle,creado_en FROM auditoria ORDER BY id");auditoria=cur.fetchall()
            conteos={}
            for t in ("facturas","registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"):
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{t}`");conteos[t]=cur.fetchone()["total"]
            cur.execute("SELECT * FROM facturas ORDER BY id");facturas=cur.fetchall()
        for s in solicitudes:s.pop("clave_idempotencia",None);s.pop("huella_creacion",None)
        for a in auditoria:
            if isinstance(a["detalle"],str):a["detalle"]=json.loads(a["detalle"])
        for f in facturas:
            for k in ("datos","cambios"):
                if isinstance(f.get(k),str):f[k]=json.loads(f[k])
        return normalizar({"solicitudes":solicitudes,"auditoria":auditoria,"conteos":conteos,"facturas":facturas})
    finally:conn.close()


def objetivo(estado):return next((s for s in estado["solicitudes"] if s["public_id"]==PID),None)


try:
    resultado["fase"]="verificacion_previa"
    with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
        hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
    archivo=referencia/"estado-final.json"
    if hashlib.sha256(archivo.read_bytes()).hexdigest()!=hashes.get(archivo.name):raise RuntimeError("HASH_REFERENCIA_SOL_009_NO_COINCIDE")
    esperado=json.loads(archivo.read_text(encoding="utf-8-sig"))
    resultado["referencia_estado_sha256"]=hashes[archivo.name]
    print("Solo QA. Verificacion de correccion ya persistida y factura historica, seguida de logout. No se guarda ni reenvia.")
    clave_bd=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    clave_web=getpass.getpass("Clave WEB de qa.emisor@example.invalid: ")
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta");identidad=cur.fetchone()
            if identidad!={"bd":DB,"cuenta":USER+"@127.0.0.1"}:raise RuntimeError("CONEXION_NO_ES_QA")
            resultado["cuenta_bd_verificada"]=identidad["cuenta"]
            cur.execute("SELECT u.id,u.password_hash,u.activo,u.debe_cambiar_password,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE u.email=%s",(EMAIL,))
            actor=cur.fetchone()
            if not actor or actor["id"]!=2 or actor["rol"]!="Emisor" or actor["activo"]!=1 or actor["debe_cambiar_password"]:raise RuntimeError("EMISOR_QA_NO_VALIDO")
            if not check_password_hash(actor["password_hash"],clave_web):raise RuntimeError("CLAVE_WEB_NO_COINCIDE")
            del actor["password_hash"]
    finally:conn.close()
    antes=leer_estado()
    if {k:antes[k] for k in esperado}!=esperado:raise RuntimeError("ESTADO_QA_DISTINTO_DEL_CIERRE_SOL_009")
    original=objetivo(antes)
    if len(antes["solicitudes"])!=5 or len(antes["auditoria"])!=8 or len(antes["facturas"])!=1 or not original or original["id"]!=3 or original["emisor_id"]!=2 or original["version"]!=6 or original["estado_nombre"]!="En corrección" or original["tipo_afectacion"]!="EXENTA" or original["monto_bruto"]!="459000":raise RuntimeError("BASE_PREVIA_NO_ESPERADA")
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rut,razon_social,giro,direccion,email_contacto,activo FROM clientes WHERE id=%s",(original["cliente_id"],));cliente=cur.fetchone()
        mapeo={"rut":"rut","razon_social":"nombre","giro":"giro","direccion":"direccion","email_contacto":"email_contacto_receptor"}
        if not cliente or cliente["activo"]!=1 or any(cliente[k]!=original[v] for k,v in mapeo.items()):raise RuntimeError("CLIENTE_CAMBIO_REVISAR_RECEPTOR_ANTES_DE_GENERAR")
    finally:conn.close()
    (evidencia/"estado-antes.json").write_text(json.dumps(antes,indent=2),encoding="utf-8")
    if input("Autorizar comprobacion sin guardar. Escribe VERIFICAR CORRECCION QA: ").strip()!="VERIFICAR CORRECCION QA":raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args,**kwargs):
        if args or kwargs.get("host")!="127.0.0.1" or int(kwargs.get("port",3306))!=3306 or kwargs.get("database")!=DB or kwargs.get("user")!=USER:raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        for n,v in (("connect_timeout",10),("read_timeout",15),("write_timeout",15)):kwargs.setdefault(n,v)
        return original_connect(**kwargs)
    pymysql.connect=conexion_restringida
    import smtplib,imaplib
    def smtp_bloqueado(*a,**k):
        ctx["intentos_smtp"]+=1
        raise RuntimeError("SMTP_REAL_BLOQUEADO_EN_QA")
    def imap_bloqueado(*a,**k):raise RuntimeError("IMAP_REAL_BLOQUEADO_EN_QA")
    smtplib.SMTP=smtp_bloqueado;smtplib.SMTP_SSL=smtp_bloqueado;imaplib.IMAP4=imap_bloqueado;imaplib.IMAP4_SSL=imap_bloqueado
    from app import create_app
    from config import Config
    from flask import request
    from flask_login import current_user
    from werkzeug.serving import make_server
    class ConfigQA(Config):
        TESTING=False;DEBUG=False;SECRET_KEY=secrets.token_hex(32)
        WTF_CSRF_ENABLED=True;SESSION_COOKIE_SECURE=False;BANDEJA_REVISION_SEGUNDOS=0
        DB_HOST="127.0.0.1";DB_PORT=3306;DB_NAME=DB;DB_USER=USER;DB_PASSWORD=clave_bd
        SMTP_HOST="";SMTP_FROM="";SMTP_USER="";SMTP_PASSWORD="";IMAP_HOST="";IMAP_USER="";IMAP_PASSWORD=""
        XML_UPLOAD_FOLDER=str(evidencia/"datos-temporales"/"xml")
        ADJUNTOS_FOLDER=str(evidencia/"datos-temporales"/"adjuntos")
        CORREOS_FOLDER=str(evidencia/"datos-temporales"/"correos")
        SII_FOLDER=str(evidencia/"datos-temporales"/"sii")
    app=create_app(ConfigQA)
    @app.after_request
    def observar(respuesta):
        if request.path.startswith("/solicitudes/") or request.path in {"/auth/login","/auth/logout","/dashboard"}:
            ctx["eventos"].append({"ruta":request.path,"metodo":request.method,"status":respuesta.status_code,
                "location":respuesta.headers.get("Location"),
                "version_formulario":request.form.get("version") if request.method=="POST" and request.path.startswith("/solicitudes/") else None,
                "usuario_id":int(current_user.id) if current_user.is_authenticated else None})
        return respuesta
    handler=logging.FileHandler(evidencia/"servidor.log",encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    for logger in (logging.getLogger("werkzeug"),app.logger):
        logger.handlers.clear();logger.addHandler(handler);logger.propagate=False;logger.setLevel(logging.INFO)
    servidor=make_server("127.0.0.1",0,app)
    base_url=f"http://127.0.0.1:{servidor.server_port}"
    hilo=threading.Thread(target=servidor.serve_forever,daemon=True);hilo.start()
    (evidencia/"servidor.json").write_text(json.dumps({"base_url":base_url,"base_datos":DB,"csrf_activo":True,
        "smtp_host_y_from":"vacios en proceso QA","smtp_imap":"bloqueados","revision_automatica_segundos":0,
        "testing":False,"debug":False,"alcance_correo":"no prueba entrega ni notificaciones exitosas"},indent=2),encoding="utf-8")
    with build_opener(ProxyHandler({})).open(base_url+"/auth/login",timeout=15) as r:
        resultado["http_login"]=r.status
        if r.status!=200:raise RuntimeError("LOGIN_NO_DEVUELVE_200")

    def verificar():
        d=leer_estado();s=objetivo(d)
        conservados=bool(s) and all(s[k]==original[k] for k in original if k not in {"concepto","version","actualizado_en"})
        v={"estado_igual_al_inicial":d==antes,"facturas_previas_sin_cambios":d["facturas"]==antes["facturas"],"total_solicitudes":len(d["solicitudes"]),"total_auditoria":len(d["auditoria"]),"total_facturas":len(d["facturas"]),
            "solicitud":s,"factura":d["facturas"][0] if len(d["facturas"])==1 else None,
            "otras_solicitudes_sin_cambios":all(next((x for x in d["solicitudes"] if x["public_id"]==a["public_id"]),None)==a for a in antes["solicitudes"] if a["public_id"]!=PID),
            "campos_no_editados_conservados":conservados,"auditorias_previas_sin_cambios":d["auditoria"][:len(antes["auditoria"])]==antes["auditoria"],
            "auditorias_nuevas":d["auditoria"][len(antes["auditoria"]):],"conteos":d["conteos"],
            "archivos_sii_en_carpeta_qa":sum(1 for p in Path(ConfigQA.SII_FOLDER).rglob("*") if p.is_file())}
        ctx["verificacion"]=v
        (evidencia/"verificacion-persistencia.json").write_text(json.dumps(v,indent=2),encoding="utf-8")
        return v
    ctx.update(base_url=base_url,evidencia=str(evidencia),email=EMAIL,password=clave_web,public_id=PID,solicitud_original=original,verificar=verificar)
    del clave_web
    class ContextoQA:
        def pytest_configure(self,config):config._qa_invoice_context=ctx
    argumentos=["e2e/test_correccion_existente_logout_qa.py","-o","addopts=","-v","-ra","--tb=short","--assert=plain",
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
    elif isinstance(exc,pymysql.MySQLError) and exc.args:resultado["codigo_error_bd"]=exc.args[0]
    print("Ejecucion detenida. Conservar evidencia y datos antes de repetir.")
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
            resultado["total_facturas_despues"]=len(final["facturas"])
            resultado["solicitud_version_despues"]=(objetivo(final) or {}).get("version")
            resultado["solicitud_estado_despues"]=(objetivo(final) or {}).get("estado_nombre")
        except Exception as exc:resultado["error_verificacion_final"]=type(exc).__name__
    resultado["verificacion_complementaria_y_logout"]=ctx["verificacion_complementaria_y_logout"]
    resultado["intentos_smtp"]=ctx["intentos_smtp"]
    resultado["notificacion_correo"]="deshabilitada por configuracion QA; no se acredita entrega"
    resultado["verificacion"]=ctx.get("verificacion")
    resultado["eventos_http"]=ctx["eventos"]
    resultado["error_cierre_navegador"]=ctx.get("error_cierre_navegador")
    resultado["alertas_cerradas_logout"]=ctx.get("alertas_cerradas_logout")
    resultado["alcance_caso"]="Comprobacion complementaria sin guardar ni reenviar; original conserva JUnit fallido"
    resultado["estado_final_igual_al_inicial"]=(final==antes) if antes is not None and "final" in locals() else None
    resultado["delta_edicion_archivada_verificado"]=True
    resultado["caso_original_corregido_reejecutado"]=False
    resultado["fin"]=datetime.now().astimezone().isoformat()
    resultado["junit_generado"]=(evidencia/"selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia/"resultado.json").write_text(json.dumps(resultado,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)