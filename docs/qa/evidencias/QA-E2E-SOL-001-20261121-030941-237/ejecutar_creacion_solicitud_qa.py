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
app_dir=Path(sys.argv[1]);fixture_dir=Path(sys.argv[2]);evidencia=Path(__file__).resolve().parent
sys.path.insert(0,str(app_dir))
DB,USER,EMAIL="facturaciones_spa_qa","qa_facturaciones","qa.emisor@example.invalid"
original_connect=pymysql.connect
resultado={"ejecucion":"QA-E2E-SOL-001","caso":"E2E-SOL-001","inicio":datetime.now().astimezone().isoformat(),
    "base":DB,"pruebas_iniciadas":False,"codigo_pytest":None,
    "alcance":"creacion web sin adjuntos; fila persistida, propietario, snapshot receptor y auditoria"}
ctx={"eventos":[],"creacion_verificada":False}
servidor=None;hilo=None;clave_bd=None;codigo=2;antes=None;datos=None


def conectar_qa():
    return original_connect(host="127.0.0.1",port=3306,user=USER,password=clave_bd,database=DB,
        charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,connect_timeout=10,read_timeout=15,write_timeout=15)


def normalizar(objeto):
    return json.loads(json.dumps(objeto,default=str,ensure_ascii=True))


def leer_solicitudes():
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT s.*,e.nombre AS estado_nombre,o.nombre AS origen_nombre FROM solicitudes s JOIN estados_solicitud e ON e.id=s.estado_id JOIN origenes_solicitud o ON o.id=s.origen_id ORDER BY s.id")
            filas=cur.fetchall()
        for fila in filas:
            fila.pop("clave_idempotencia",None);fila.pop("huella_creacion",None)
        return normalizar(filas)
    finally:conn.close()


try:
    resultado["fase"]="verificacion_previa"
    with (fixture_dir/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
        hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
    archivo_fixture=fixture_dir/"fixtures-aislamiento.json"
    if hashlib.sha256(archivo_fixture.read_bytes()).hexdigest()!=hashes.get(archivo_fixture.name):raise RuntimeError("HASH_FIXTURE_NO_COINCIDE")
    fixture=json.loads(archivo_fixture.read_text(encoding="utf-8-sig"))
    if fixture.get("base")!=DB or fixture["emisor_a"]["email"]!=EMAIL:raise RuntimeError("FIXTURE_NO_ES_QA")
    print("Se creara UNA solicitud por formulario web, solo QA. No repetir tras un fallo sin revisar datos.")
    clave_bd=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    clave_web=getpass.getpass("Clave WEB de qa.emisor@example.invalid: ")
    conn=conectar_qa()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
            identidad=cur.fetchone()
            if identidad!={"bd":DB,"cuenta":USER+"@127.0.0.1"}:raise RuntimeError("CONEXION_NO_ES_QA")
            resultado["cuenta_bd_verificada"]=identidad["cuenta"]
            esperados={"usuarios":4,"roles":3,"clientes":1,"solicitudes":2,"estados_solicitud":5,"origenes_solicitud":2,
                "auditoria":0,"facturas":0,"registros_xml":0,"adjuntos_solicitud":0,"envios_correo":0,"correos_entrantes":0,"recuperaciones_password":0}
            conteos={}
            for tabla in esperados:
                cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`");conteos[tabla]=cur.fetchone()["total"]
            if conteos!=esperados:raise RuntimeError("DATOS_NO_ESPERADOS_REVISAR_ANTES_DE_CREAR")
            resultado["conteos_antes"]=conteos
            cur.execute("SELECT u.*,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE u.email=%s",(EMAIL,))
            actor=cur.fetchone()
            if not actor or actor["id"]!=fixture["emisor_a"]["id"] or actor["nombre"]!="Emisor Sintetico QA" or actor["rol"]!="Emisor" or actor["activo"]!=1 or actor["debe_cambiar_password"]:
                raise RuntimeError("EMISOR_QA_NO_VALIDO")
            if not check_password_hash(actor["password_hash"],clave_web):raise RuntimeError("CLAVE_WEB_NO_COINCIDE")
            id_emisor=actor["id"]
            del actor["password_hash"]
            cur.execute("SELECT id,rut,razon_social,direccion,giro,email_contacto,activo FROM clientes WHERE id=%s",(fixture["cliente"]["id"],))
            cliente=cur.fetchone()
            if not cliente or not cliente["activo"] or any(cliente[c]!=fixture["cliente"][c] for c in ("rut","razon_social","direccion","giro","email_contacto")):
                raise RuntimeError("CLIENTE_QA_NO_ESPERADO")
        antes=leer_solicitudes()
        originales={s["public_id"]:s for s in antes}
        if set(originales)!={s["public_id"] for s in fixture["solicitudes"]}:raise RuntimeError("SOLICITUDES_BASE_NO_ESPERADAS")
        for s in fixture["solicitudes"]:
            actual=originales[s["public_id"]]
            if actual["version"]!=1 or actual["estado_nombre"]!="Pendiente" or actual["emisor_id"]!=s["emisor_id"] or actual["concepto"]!=s["concepto"]:
                raise RuntimeError("FIXTURES_BASE_CAMBIARON")
    finally:conn.close()
    marca=secrets.token_hex(4)
    datos={"cliente_id":cliente["id"],"concepto":"QA-CREACION-WEB-"+marca,"monto_bruto":"357000",
        "fecha_emision":datetime.now().astimezone().date().isoformat(),"tipo_afectacion":"AFECTA","nro_orden_compra":"QA-OC-"+marca}
    (evidencia/"datos-formulario.json").write_text(json.dumps(datos,indent=2),encoding="utf-8")
    (evidencia/"solicitudes-antes.json").write_text(json.dumps(antes,indent=2),encoding="utf-8")
    print("Datos sinteticos: concepto "+datos["concepto"]+", monto 357000, afecta, sin adjuntos.")
    if input("Se conservara la nueva solicitud y su auditoria. Escribe CREAR SOLICITUD QA: ").strip()!="CREAR SOLICITUD QA":
        raise RuntimeError("CANCELADO_POR_USUARIO")

    def conexion_restringida(*args,**kwargs):
        if args or kwargs.get("host")!="127.0.0.1" or int(kwargs.get("port",3306))!=3306 or kwargs.get("database")!=DB or kwargs.get("user")!=USER:
            raise RuntimeError("CONEXION_FUERA_DE_QA_BLOQUEADA")
        for nombre,valor in (("connect_timeout",10),("read_timeout",15),("write_timeout",15)):kwargs.setdefault(nombre,valor)
        return original_connect(**kwargs)
    pymysql.connect=conexion_restringida
    import smtplib,imaplib
    def correo_bloqueado(*args,**kwargs):raise RuntimeError("CORREO_REAL_BLOQUEADO_EN_QA")
    smtplib.SMTP=correo_bloqueado;smtplib.SMTP_SSL=correo_bloqueado
    imaplib.IMAP4=correo_bloqueado;imaplib.IMAP4_SSL=correo_bloqueado
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

    def verificar_persistencia(public_id):
        despues=leer_solicitudes()
        conn=conectar_qa()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT clave_idempotencia,huella_creacion FROM solicitudes WHERE public_id=%s",(public_id,))
                internos=cur.fetchone() or {}
                cur.execute("SELECT id,usuario_id,accion,detalle,creado_en FROM auditoria WHERE accion=%s ORDER BY id",("SOLICITUD_CREADA",))
                auditorias=[]
                for fila in cur.fetchall():
                    fila["detalle"]=json.loads(fila["detalle"]) if isinstance(fila["detalle"],str) else fila["detalle"]
                    if fila["detalle"].get("public_id")==public_id:auditorias.append(fila)
                relacionados={}
                for tabla in ("facturas","registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"):
                    cur.execute(f"SELECT COUNT(*) AS total FROM `{DB}`.`{tabla}`");relacionados[tabla]=cur.fetchone()["total"]
            verificacion={"total_solicitudes":len(despues),
                "coincidencias_concepto":sum(s["concepto"]==datos["concepto"] for s in despues),
                "solicitud":next((s for s in despues if s["public_id"]==public_id),None),
                "originales_sin_cambios":all(next((s for s in despues if s["public_id"]==original["public_id"]),None)==original for original in antes),
                "auditorias_creacion":normalizar(auditorias),"conteos_relacionados":relacionados,
                "clave_creacion_presente":bool(internos.get("clave_idempotencia")),
                "huella_creacion_presente":len(internos.get("huella_creacion") or "")==64}
            ctx["persistencia"]=verificacion
            (evidencia/"verificacion-persistencia.json").write_text(json.dumps(verificacion,indent=2),encoding="utf-8")
            return verificacion
        finally:conn.close()

    ctx.update(base_url=base_url,evidencia=str(evidencia),email=EMAIL,password=clave_web,emisor_id=id_emisor,
        datos=datos,cliente=cliente,verificar_persistencia=verificar_persistencia)
    del clave_web
    class ContextoQA:
        def pytest_configure(self,config):config._qa_create_context=ctx
    argumentos=["e2e/test_creacion_solicitud_qa.py","-o","addopts=","-v","-ra","--tb=short","--assert=plain",
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
            despues=leer_solicitudes()
            (evidencia/"solicitudes-despues.json").write_text(json.dumps(despues,indent=2),encoding="utf-8")
            resultado["total_solicitudes_despues"]=len(despues)
            resultado["fixtures_originales_sin_cambios"]=all(next((s for s in despues if s["public_id"]==o["public_id"]),None)==o for o in antes)
            if datos:resultado["nuevas_por_concepto"]=[{"id":s["id"],"public_id":s["public_id"],"emisor_id":s["emisor_id"],"concepto":s["concepto"]} for s in despues if s["concepto"]==datos["concepto"]]
        except Exception as exc:resultado["error_verificacion_final"]=type(exc).__name__
    resultado["creacion_verificada"]=ctx["creacion_verificada"]
    resultado["public_id_creado"]=ctx.get("public_id_creado")
    resultado["persistencia"]=ctx.get("persistencia")
    resultado["eventos_http"]=ctx["eventos"]
    resultado["error_cierre_navegador"]=ctx.get("error_cierre_navegador")
    resultado["fin"]=datetime.now().astimezone().isoformat()
    resultado["junit_generado"]=(evidencia/"selenium-junit.xml").exists()
    logging.shutdown()
    (evidencia/"resultado.json").write_text(json.dumps(resultado,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)