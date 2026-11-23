import getpass
import hashlib
import json
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import pymysql

warnings.simplefilter("error",getpass.GetPassWarning)
evidencia=Path(__file__).resolve().parent
DB="facturaciones_spa_qa";USER="qa_facturaciones"
IDS=(151,152,154)
SHA="4f9356bf60b65ecb347c490ee0cdcc9a6464763edf7ea0d89a8a216c2bf14c3f"
r={"id":"QA-LIMPIEZA-LECTURAS-009","inicio":datetime.now().astimezone().isoformat(),
   "solo_lectura":False,"accion":"cancelacion acotada de conexiones de lecturas QA identificadas",
   "ids_permitidos":list(IDS),"acciones":[]}
c=None;codigo=2


def procesos():
    with c.cursor() as cur:
        cur.execute("SHOW FULL PROCESSLIST")
        return cur.fetchall()


def sanitizar(filas):
    resultado=[]
    for fila in filas:
        texto=fila.get("Info") or ""
        resultado.append({"Id":fila.get("Id"),"User":fila.get("User"),"base":fila.get("db"),
            "Command":fila.get("Command"),"Time":fila.get("Time"),"State":fila.get("State"),
            "sha256_sql":hashlib.sha256(texto.encode("utf-8")).hexdigest() if texto else None})
    return resultado


def coincide(p):
    if not p:return False
    texto=p.get("Info") or ""
    return (p.get("Id") in IDS and p.get("User")==USER and p.get("db")==DB
       and p.get("Command")=="Query" and int(p.get("Time") or 0)>=15
       and (p.get("State") or "").lower() in {"statistics","opening tables","waiting for table metadata lock"}
       and hashlib.sha256(texto.encode("utf-8")).hexdigest()==SHA)


try:
    clave=getpass.getpass("Clave MariaDB de qa_facturaciones: ")
    c=pymysql.connect(host="127.0.0.1",port=3306,user=USER,password=clave,database=DB,
        charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,autocommit=True,
        connect_timeout=10,read_timeout=15,write_timeout=15)
    clave=None
    with c.cursor() as cur:
        cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta,CONNECTION_ID() AS id")
        identidad=cur.fetchone()
    if identidad["bd"]!=DB or identidad["cuenta"]!=USER+"@127.0.0.1":raise RuntimeError("NO_ES_CUENTA_QA_ESPERADA")
    r["identidad"]=identidad
    inicial=procesos()
    r["procesos_antes"]=sanitizar(inicial)
    candidatos=[p["Id"] for p in inicial if coincide(p)]
    r["candidatos_verificados"]=candidatos
    print(json.dumps({"ids_que_se_proponen_cancelar":candidatos,
        "condiciones":"IDs 151/152/154, cuenta y base QA, SELECT exacto por hash, espera >=15 s",
        "alcance":"KILL CONNECTION solo de candidatos; ninguna tabla ni otro usuario"},ensure_ascii=True,indent=2))
    if not candidatos:
        r["estado"]="SIN_CANDIDATOS_NO_SE_EJECUTO_KILL"
        codigo=0
    else:
        if input("Escribe CANCELAR LECTURAS QA para confirmar estos IDs: ").strip()!="CANCELAR LECTURAS QA":raise RuntimeError("CANCELADO_POR_USUARIO")
        for ident in candidatos:
            actual=next((p for p in procesos() if p["Id"]==ident),None)
            if not coincide(actual):
                r["acciones"].append({"id":ident,"estado":"OMITIDO_YA_NO_COINCIDE"})
                continue
            accion={"id":ident,"comando":"KILL CONNECTION "+str(ident),"estado":"INTENTO"}
            r["acciones"].append(accion)
            try:
                with c.cursor() as cur:cur.execute("KILL CONNECTION "+str(int(ident)))
                accion["estado"]="ORDEN_ACEPTADA"
            except pymysql.MySQLError as exc:
                accion["estado"]="ERROR_O_RESULTADO_NO_CONFIRMADO"
                accion["codigo_error_bd"]=exc.args[0] if exc.args else None
                raise
        time.sleep(2)
        despues=procesos()
        r["procesos_despues"]=sanitizar(despues)
        r["ids_objetivo_aun_visibles"]=[p["Id"] for p in despues if p["Id"] in IDS]
        r["estado"]="ORDENES_REGISTRADAS_REVISAR_PROCESOS_DESPUES"
        codigo=0
except Exception as exc:
    r["estado"]="OPERACION_DETENIDA";r["error_tipo"]=type(exc).__name__
    if isinstance(exc,RuntimeError):r["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args:r["codigo_error_bd"]=exc.args[0]
finally:
    if c:
        try:c.close()
        except Exception:pass
    r["fin"]=datetime.now().astimezone().isoformat()
    (evidencia/"resultado.json").write_text(json.dumps(r,default=str,ensure_ascii=True,indent=2),encoding="utf-8")
raise SystemExit(codigo)