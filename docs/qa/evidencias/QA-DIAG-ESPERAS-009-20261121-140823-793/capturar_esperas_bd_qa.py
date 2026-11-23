import getpass
import hashlib
import json
import re
import sys
import threading
import time
import warnings
from datetime import datetime
from pathlib import Path

import pymysql

warnings.simplefilter("error",getpass.GetPassWarning)
evidencia=Path(__file__).resolve().parent
DB="facturaciones_spa_qa"
r={"id":"QA-DIAG-ESPERAS-009","inicio":datetime.now().astimezone().isoformat(),
   "solo_lectura":True,"muestras":[],"consulta_actor":{},"limitacion":"No registra texto SQL ni hashes de password; visibilidad depende de PROCESS"}
ready=threading.Event();done=threading.Event();obs=None;hilo=None;codigo=2
clave_qa=None;clave_observador=None


def conectar(usuario,clave):
    return pymysql.connect(host="127.0.0.1",port=3306,user=usuario,password=clave,database=DB,
       charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,autocommit=True,
       connect_timeout=10,read_timeout=15,write_timeout=15)


def reproducir():
    c=None
    etapa="conexion_lector"
    try:
        c=conectar("qa_facturaciones",clave_qa)
        with c.cursor() as cur:
            cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta,CONNECTION_ID() AS id")
            identidad=cur.fetchone()
            if identidad["bd"]!=DB or identidad["cuenta"]!="qa_facturaciones@127.0.0.1":raise RuntimeError("LECTOR_NO_ES_QA")
            r["consulta_actor"]["conexion_id"]=identidad["id"]
            etapa="lectura_actor"
            inicio=time.perf_counter()
            ready.set()
            cur.execute("SELECT u.id,u.password_hash,u.activo,u.debe_cambiar_password,r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE u.email=%s",("qa.emisor@example.invalid",))
            fila=cur.fetchone()
            r["consulta_actor"].update(estado="OK",segundos=round(time.perf_counter()-inicio,4),actor_encontrado=fila is not None)
            if fila:fila.pop("password_hash",None)
    except Exception as exc:
        r["consulta_actor"].update(estado="ERROR",fase=etapa,tipo=type(exc).__name__)
        if etapa=="lectura_actor":r["consulta_actor"]["segundos"]=round(time.perf_counter()-inicio,4)
        if isinstance(exc,pymysql.MySQLError) and exc.args:r["consulta_actor"]["codigo_error_bd"]=exc.args[0]
        if isinstance(exc,RuntimeError):r["consulta_actor"]["error_controlado"]=str(exc)
    finally:
        if c:
            try:c.close()
            except Exception:pass
        ready.set();done.set()


def consultar(nombre,sql):
    try:
        with obs.cursor() as cur:
            cur.execute(sql)
            return {"estado":"OK","filas":cur.fetchall()}
    except Exception as exc:
        resultado={"estado":"NO_DISPONIBLE","tipo":type(exc).__name__}
        if isinstance(exc,pymysql.MySQLError) and exc.args:resultado["codigo_error_bd"]=exc.args[0]
        return resultado


def capturar():
    muestra={"momento":datetime.now().astimezone().isoformat()}
    procesos=consultar("procesos","SHOW FULL PROCESSLIST")
    if procesos["estado"]=="OK":
        filas=[]
        for p in procesos["filas"]:
            texto=p.get("Info") or ""
            registro={k:p.get(k) for k in ("Id","User","Command","Time","State")}
            bd=p.get("db")
            registro["base"]=bd if bd in (DB,None) else "[otra_base]"
            registro["tipo_sql"]=texto.split(None,1)[0].upper() if texto.strip() else None
            registro["tablas_qa_mencionadas"]=[t for t in ("usuarios","roles","solicitudes","clientes") if re.search(r"\b"+t+r"\b",texto,re.I)]
            registro["sha256_sql"]=hashlib.sha256(texto.encode()).hexdigest() if texto else None
            filas.append(registro)
        muestra["procesos"]={"estado":"OK","filas":filas}
    else:muestra["procesos"]=procesos
    muestra["transacciones"]=consultar("transacciones","SELECT trx_id,trx_state,trx_started,trx_wait_started,trx_mysql_thread_id,trx_tables_locked,trx_rows_locked FROM information_schema.INNODB_TRX")
    muestra["esperas_innodb"]=consultar("esperas","SELECT requesting_trx_id,blocking_trx_id FROM information_schema.INNODB_LOCK_WAITS")
    muestra["metadata_qa"]=consultar("metadata","SELECT THREAD_ID,LOCK_MODE,LOCK_DURATION,LOCK_TYPE,TABLE_SCHEMA,TABLE_NAME FROM information_schema.METADATA_LOCK_INFO WHERE TABLE_SCHEMA='facturaciones_spa_qa'")
    r["muestras"].append(muestra)


try:
    print("Diagnostico de esperas. No reinicia, no mata sesiones y no modifica tablas ni plugins.")
    clave_qa=getpass.getpass("Clave MariaDB qa_facturaciones: ")
    observador=input("Cuenta observadora con PROCESS, si dispones de ella [Enter: qa_facturaciones]: ").strip() or "qa_facturaciones"
    clave_observador=clave_qa if observador=="qa_facturaciones" else getpass.getpass("Clave de la cuenta observadora (solo lectura): ")
    obs=conectar(observador,clave_observador)
    identidad=consultar("identidad","SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta,CONNECTION_ID() AS id,VERSION() AS version_servidor")
    if identidad["estado"]!="OK" or identidad["filas"][0]["bd"]!=DB:raise RuntimeError("OBSERVADOR_NO_CONECTADO_A_QA")
    r["observador"]=identidad["filas"][0]
    with obs.cursor() as cur:
        cur.execute("SHOW GRANTS")
        grants=[str(v) for fila in cur.fetchall() for v in fila.values()]
        r["process_global_detectado"]=any(re.search(r"GRANT.*\bPROCESS\b.* ON \*\.\*",g,re.I) or re.search(r"GRANT ALL PRIVILEGES ON \*\.\*",g,re.I) for g in grants)
        del grants
    hilo=threading.Thread(target=reproducir,daemon=True)
    hilo.start();ready.wait(timeout=12)
    time.sleep(1)
    capturar()
    if not done.wait(timeout=2):capturar()
    hilo.join(timeout=20)
    r["lector_finalizado"]=not hilo.is_alive()
    r["estado"]="CAPTURA_REALIZADA_NO_ES_RESULTADO_FUNCIONAL"
    codigo=0
except Exception as exc:
    r["estado"]="DIAGNOSTICO_INCOMPLETO";r["error_tipo"]=type(exc).__name__
    if isinstance(exc,RuntimeError):r["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args:r["codigo_error_bd"]=exc.args[0]
finally:
    if hilo is not None and hilo.is_alive():hilo.join(timeout=20)
    if obs:
        try:obs.close()
        except Exception:pass
    clave_qa=None;clave_observador=None
    r["fin"]=datetime.now().astimezone().isoformat()
    (evidencia/"resultado.json").write_text(json.dumps(r,default=str,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)