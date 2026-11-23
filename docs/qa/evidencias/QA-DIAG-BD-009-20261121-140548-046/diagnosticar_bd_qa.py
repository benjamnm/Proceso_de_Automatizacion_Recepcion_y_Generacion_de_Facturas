import csv
import getpass
import hashlib
import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import pymysql
from werkzeug.security import check_password_hash

warnings.simplefilter("error",getpass.GetPassWarning)
evidencia=Path(__file__).resolve().parent
referencia=Path(sys.argv[1])
r={"id":"QA-DIAG-BD-009","inicio":datetime.now().astimezone().isoformat(),"solo_lectura":True,
   "base":"facturaciones_spa_qa","pasos":[],"pruebas_selenium_iniciadas":False}
conn=None;codigo=2;fase="referencia";clave_bd=None;clave_web=None;actor=None


def consulta(nombre,sql,params=None):
    global fase
    fase=nombre
    inicio=time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql,params)
            filas=cur.fetchall()
        r["pasos"].append({"paso":nombre,"estado":"OK","segundos":round(time.perf_counter()-inicio,4)})
        return filas
    except Exception:
        r["pasos"].append({"paso":nombre,"estado":"ERROR","segundos":round(time.perf_counter()-inicio,4)})
        raise


try:
    with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
        hashes={x["archivo"]:x["sha256"].lower() for x in csv.DictReader(f)}
    archivo=referencia/"estado-final.json"
    if hashlib.sha256(archivo.read_bytes()).hexdigest()!=hashes.get(archivo.name):raise RuntimeError("HASH_REFERENCIA_SOL_008_NO_COINCIDE")
    esperado=json.loads(archivo.read_text(encoding="utf-8-sig"))
    clave_bd=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    clave_web=getpass.getpass("Clave WEB de qa.emisor@example.invalid (solo comparacion local de hash): ")
    fase="conexion"
    inicio=time.perf_counter()
    conn=pymysql.connect(host="127.0.0.1",port=3306,user="qa_facturaciones",password=clave_bd,
       database="facturaciones_spa_qa",charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,
       connect_timeout=10,read_timeout=15,write_timeout=15)
    r["pasos"].append({"paso":"conexion","estado":"OK","segundos":round(time.perf_counter()-inicio,4)})
    identidad=consulta("identidad","SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta,VERSION() AS version_servidor,CONNECTION_ID() AS conexion_id")[0]
    r["identidad"]=identidad
    if identidad["bd"]!="facturaciones_spa_qa" or identidad["cuenta"]!="qa_facturaciones@127.0.0.1":raise RuntimeError("CONEXION_NO_ES_QA")
    r["timeouts_sesion"]=consulta("timeouts_sesion","SHOW SESSION VARIABLES WHERE Variable_name IN ('wait_timeout','interactive_timeout','net_read_timeout','net_write_timeout','max_allowed_packet')")
    # Solo afecta a esta transaccion del diagnostico.
    consulta("iniciar_transaccion_solo_lectura","START TRANSACTION READ ONLY")
    filas=consulta("lectura_actor","SELECT u.id,u.password_hash,u.activo,u.debe_cambiar_password,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE u.email=%s",("qa.emisor@example.invalid",))
    if len(filas)!=1:raise RuntimeError("ACTOR_QA_NO_ENCONTRADO")
    actor=filas[0]
    r["actor"]={k:actor[k] for k in ("id","activo","debe_cambiar_password","rol")}
    if actor["id"]!=2 or actor["rol"]!="Emisor" or actor["activo"]!=1 or actor["debe_cambiar_password"]:raise RuntimeError("ACTOR_QA_NO_ESPERADO")
    fase="comparacion_local_password"
    inicio=time.perf_counter()
    coincide=check_password_hash(actor["password_hash"],clave_web)
    r["pasos"].append({"paso":fase,"estado":"OK" if coincide else "NO_COINCIDE","segundos":round(time.perf_counter()-inicio,4)})
    actor.pop("password_hash",None)
    clave_web=None
    if not coincide:raise RuntimeError("CLAVE_WEB_NO_COINCIDE")
    consulta("consulta_tras_comparar_hash","SELECT 1 AS conexion_operativa")
    solicitudes=consulta("lectura_solicitudes","SELECT s.*,e.nombre AS estado_nombre,o.nombre AS origen_nombre FROM solicitudes s JOIN estados_solicitud e ON e.id=s.estado_id JOIN origenes_solicitud o ON o.id=s.origen_id ORDER BY s.id")
    for f in solicitudes:f.pop("clave_idempotencia",None);f.pop("huella_creacion",None)
    auditoria=consulta("lectura_auditoria","SELECT id,usuario_id,accion,detalle,creado_en FROM auditoria ORDER BY id")
    for a in auditoria:
        if isinstance(a["detalle"],str):a["detalle"]=json.loads(a["detalle"])
    conteos={}
    for tabla in ("facturas","registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"):
        conteos[tabla]=consulta("conteo_"+tabla,f"SELECT COUNT(*) AS total FROM `{tabla}`")[0]["total"]
    estado=json.loads(json.dumps({"solicitudes":solicitudes,"auditoria":auditoria,"conteos":conteos},default=str))
    (evidencia/"estado-observado.json").write_text(json.dumps(estado,indent=2),encoding="utf-8")
    r["coincide_con_cierre_SOL_008"]=estado==esperado
    r["total_solicitudes"]=len(solicitudes);r["total_auditoria"]=len(auditoria)
    if estado!=esperado:raise RuntimeError("ESTADO_DISTINTO_DEL_CIERRE_SOL_008_NO_REPETIR_PRUEBA")
    r["estado"]="DIAGNOSTICO_CORRECTO_EN_ESTA_EJECUCION"
    codigo=0
except Exception as exc:
    r["estado"]="DIAGNOSTICO_DETENIDO";r["fase_error"]=fase;r["error_tipo"]=type(exc).__name__
    if isinstance(exc,pymysql.MySQLError) and exc.args:
        r["codigo_error_bd"]=exc.args[0]
        mensaje=str(exc.args[1]) if len(exc.args)>1 else ""
        for secreto in (clave_bd,clave_web):
            if secreto:mensaje=mensaje.replace(secreto,"[OCULTO]")
        r["mensaje_error_bd"]=mensaje[:500]
    elif isinstance(exc,RuntimeError):r["error_controlado"]=str(exc)
finally:
    if actor:actor.pop("password_hash",None)
    clave_bd=None;clave_web=None
    if conn is not None:
        try:conn.rollback()
        except Exception as exc:r["error_cierre_transaccion"]=type(exc).__name__
        try:conn.close()
        except Exception as exc:r["error_cierre_conexion"]=type(exc).__name__
    r["fin"]=datetime.now().astimezone().isoformat()
    (evidencia/"resultado.json").write_text(json.dumps(r,indent=2,ensure_ascii=True),encoding="utf-8")
raise SystemExit(codigo)