import ast
import csv
import getpass
import hashlib
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pymysql

warnings.simplefilter("error",getpass.GetPassWarning)
ref=Path(sys.argv[1]);aprobacion=Path(sys.argv[2]);app=Path(sys.argv[3]);ev=Path(__file__).resolve().parent
DB,USER="facturaciones_spa_qa","qa_facturaciones"
PID="ee2e8fdb51290c59ae0ab6457a3ba001"
r={"ejecucion":"QA-VERIF-FAC-005-DESCARGA","inicio":datetime.now().astimezone().isoformat(),
    "pytest_ejecutado":False,"selenium_ejecutado":False,"descarga_repetida":False,"reaprobacion":False,
    "sql_escritura":False,"base":DB,"estado":"PENDIENTE"}
c=None;codigo=2


def manifiesto(raiz):
    with (raiz/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
        return {x["archivo"].replace("\\","/"):x["sha256"].lower() for x in csv.DictReader(f)}


def verificar_archivo(raiz,nombre,hashes):
    p=raiz/nombre
    if not p.resolve().is_relative_to(raiz.resolve()):raise RuntimeError("ARCHIVO_FUERA_DE_EVIDENCIA")
    if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes.get(nombre):raise RuntimeError("HASH_EVIDENCIA_NO_COINCIDE")
    return p


def leer(nombre):return json.loads((ref/nombre).read_text(encoding="utf-8-sig"))


def leer_estado(conn):
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
        if isinstance(a["detalle"],(str,bytes,bytearray)):a["detalle"]=json.loads(a["detalle"])
    for f in facturas:
        for k in ("datos","cambios"):
            if isinstance(f.get(k),(str,bytes,bytearray)):f[k]=json.loads(f[k])
    return json.loads(json.dumps({"solicitudes":solicitudes,"auditoria":auditoria,"conteos":conteos,"facturas":facturas},default=str))


try:
    h=manifiesto(ref)
    nombres=("resultado.json","estado-antes.json","estado-final.json","verificacion-xml-descarga.json",
        "verificacion-delta-aprobacion.json","emisor-sintetico-qa.json","caso-ejecutado.py.txt",
        "caso-original-corregido-no-reejecutado.py.txt","DTE-QA-descargado-sin-validez-tributaria.xml")
    for nombre in nombres:verificar_archivo(ref,nombre,h)
    anterior=leer("estado-antes.json");final=leer("estado-final.json");ejecucion=leer("resultado.json")
    descarga=leer("verificacion-xml-descarga.json");delta_previo=leer("verificacion-delta-aprobacion.json")
    s=next(x for x in final["solicitudes"] if x["public_id"]==PID)
    f=next(x for x in final["facturas"] if x["solicitud_id"]==3 and x["version"]==2)
    nuevas=final["auditoria"][len(anterior["auditoria"]):]
    esperado={"solicitud_afectada_id":3,"public_id":PID,"factura_id":f["id"],"version_factura":2,"sha256":f["archivo_sii_sha256"]}
    checks={
        "referencia_fallida_en_cierre":ejecucion.get("codigo_pytest")==1 and ejecucion.get("verificacion_complementaria_y_logout") is False,
        "solo_auditoria_cambio":set(anterior)==set(final) and all(anterior[k]==final[k] for k in anterior if k!="auditoria"),
        "totales_correctos":len(final["solicitudes"])==5 and len(final["facturas"])==2 and len(anterior["auditoria"])==10 and len(final["auditoria"])==11,
        "auditoria_previa_intacta":final["auditoria"][:10]==anterior["auditoria"],
        "unico_evento_descarga_correcto":len(nuevas)==1 and nuevas[0]["id"]==11 and nuevas[0]["usuario_id"]==1 and nuevas[0]["accion"]=="ARCHIVO_SII_DESCARGADO" and nuevas[0]["detalle"]==esperado,
        "estado_aprobado_conservado":s["version"]==8 and s["estado_nombre"]=="Aprobada" and f["estado"]=="APROBADA",
        "xml_y_descarga_completados":ejecucion.get("xml_local_verificado") is True and ejecucion.get("descarga_autenticada_verificada") is True and descarga.get("estructura_y_datos_verificados") is True and descarga.get("coincide_bd_y_archivo_local") is True,
        "delta_aprobacion_previo_confirmado":delta_previo.get("delta_aprobacion_archivada_verificado") is True}
    eventos=ejecucion["eventos_http"]
    peticiones=[e for e in eventos if e["ruta"]=="/solicitudes/"+PID+"/factura/sii" and e["metodo"]=="GET"]
    checks["descarga_autenticada_http_200"]=len(peticiones)==1 and peticiones[0]["status"]==200 and peticiones[0]["usuario_id"]==1
    salidas=[e for e in eventos if e["ruta"]=="/auth/logout" and e["metodo"]=="POST"]
    checks["logout_y_panel_protegido"]=len(salidas)==1 and salidas[0]["status"]==302 and salidas[0]["usuario_id"] is None and any(e["ruta"]=="/dashboard" and e["status"]==302 and e["usuario_id"] is None for e in eventos)
    checks["sin_post_de_negocio"]=all(e["ruta"] in {"/auth/login","/auth/logout"} for e in eventos if e["metodo"]=="POST")
    nombre_xml=f["archivo_sii"]
    if not nombre_xml or Path(nombre_xml).name!=nombre_xml:raise RuntimeError("NOMBRE_XML_NO_ESPERADO")
    original_xml=verificar_archivo(aprobacion,"datos-temporales/sii/"+nombre_xml,manifiesto(aprobacion))
    contenido=original_xml.read_bytes();sha=hashlib.sha256(contenido).hexdigest()
    copia=(ref/"DTE-QA-descargado-sin-validez-tributaria.xml").read_bytes()
    checks["sha_original_bd_descarga_y_auditoria"]=sha==f["archivo_sii_sha256"]==descarga["sha256"]==hashlib.sha256(copia).hexdigest()==nuevas[0]["detalle"].get("sha256") if len(nuevas)==1 else False
    xml=ET.fromstring(contenido);documento=xml.find("Documento")
    checks["xml_local_tipo_folio_y_total"]=xml.tag=="DTE" and documento is not None and documento.findtext("Encabezado/IdDoc/TipoDTE")=="34" and documento.findtext("Encabezado/IdDoc/Folio")==str(f["id"]) and documento.findtext("Encabezado/Totales/MntExe")=="459000" and documento.findtext("Encabezado/Totales/MntTotal")=="459000"
    checks["xml_concepto_y_receptor"]=documento is not None and documento.findtext("Detalle/NmbItem")==f["datos"]["detalle"]["concepto"][:80] and documento.findtext("Encabezado/Receptor/RUTRecep")==f["datos"]["receptor"]["rut"]
    checks["xml_sin_firma_ni_ted"]=not any(n.tag.rsplit("}",1)[-1] in {"Signature","TED"} for n in xml.iter())
    ruta_fuente=app/"app"/"solicitudes"/"routes.py"
    texto=ruta_fuente.read_text(encoding="utf-8-sig")
    funciones=[n for n in ast.parse(texto).body if isinstance(n,ast.FunctionDef) and any(isinstance(x,ast.Constant) and x.value=="ARCHIVO_SII_DESCARGADO" for x in ast.walk(n))]
    checks["evento_explicito_en_ruta_local"]=len(funciones)==1
    r["verificaciones"]=checks
    (ev/"verificacion-delta-descarga.json").write_text(json.dumps({"referencia":str(ref),"verificaciones":checks,"evento_nuevo":nuevas},indent=2),encoding="utf-8")
    if not all(checks.values()):raise RuntimeError("EVIDENCIA_NO_CUMPLE_DELTA_EXACTO_NO_SE_CAMBIAN_TESTS")
    (ev/"ruta-descarga-verificada.py.txt").write_text(ast.get_source_segment(texto,funciones[0]),encoding="utf-8")
    print("Verificacion de evidencia correcta: unica diferencia, auditoria ARCHIVO_SII_DESCARGADO ID 11.")
    clave=getpass.getpass("Clave MariaDB de qa_facturaciones para verificacion SOLO LECTURA: ")
    c=pymysql.connect(host="127.0.0.1",port=3306,user=USER,password=clave,database=DB,charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,connect_timeout=10,read_timeout=15,write_timeout=15)
    clave=None
    with c.cursor() as cur:
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.execute("SELECT DATABASE() AS bd,CURRENT_USER() AS cuenta")
        if cur.fetchone()!={"bd":DB,"cuenta":USER+"@127.0.0.1"}:raise RuntimeError("CONEXION_NO_ES_QA")
    actual=leer_estado(c)
    c.close();c=None
    r["bd_actual_igual_al_cierre_archivado"]=actual==final
    if actual!=final:raise RuntimeError("BD_CAMBIO_DESDE_EL_CIERRE_NO_SE_ADOPTA_NUEVO_ESTADO")
    (ev/"estado-final.json").write_text(json.dumps(actual,indent=2),encoding="utf-8")
    fuentes=[("caso-ejecutado.py.txt","test_xml_existente_navegador_qa.py"),("caso-original-corregido-no-reejecutado.py.txt","test_aprobacion_xml_local_qa.py")]
    cambios=[]
    for archivo,nombre in fuentes:
        viejo=(ref/archivo).read_text(encoding="utf-8-sig")
        if nombre=="test_xml_existente_navegador_qa.py":
            marcador='        assert ctx["verificar"]()["estado_igual_al_inicial"] is True'
            if viejo.count(marcador)!=1:raise RuntimeError("ASERCION_FINAL_COMPLEMENTARIA_NO_IDENTIFICADA")
            nuevo=viejo.replace(marcador,'        cierre=ctx["verificar"]()\n        assert cierre["total_solicitudes"]==5 and cierre["total_facturas"]==2\n        assert cierre["total_auditoria"]==11\n        assert cierre["solicitud"]==v["solicitud"]\n        assert cierre["factura_v1"]==v["factura_v1"] and cierre["factura_v2"]==v["factura_v2"]\n        assert cierre["otras_solicitudes_sin_cambios"] and cierre["auditorias_previas_sin_cambios"]\n        assert cierre["conteos"]==v["conteos"] and cierre["archivos_sii"]==v["archivos_sii"]\n        assert len(cierre["auditorias_nuevas"])==1\n        descarga=cierre["auditorias_nuevas"][-1]\n        assert descarga["usuario_id"]==1 and descarga["accion"]=="ARCHIVO_SII_DESCARGADO"\n        assert descarga["detalle"]=={"solicitud_afectada_id":3,"public_id":pid,"factura_id":f["id"],\n            "version_factura":2,"sha256":f["archivo_sii_sha256"]}\n'.rstrip(),1)
        else:
            marcador='        ctx["aprobacion_xml_verificada"]=True'
            if viejo.count(marcador)!=1:raise RuntimeError("CIERRE_ORIGINAL_NO_IDENTIFICADO")
            nuevo=viejo.replace(marcador,'        cierre=ctx["verificar"]()\n        assert cierre["total_solicitudes"]==5 and cierre["total_facturas"]==2\n        assert cierre["total_auditoria"]==11\n        assert cierre["solicitud"]==v["solicitud"]\n        assert cierre["factura_v1"]==v["factura_v1"] and cierre["factura_v2"]==v["factura_v2"]\n        assert cierre["otras_solicitudes_sin_cambios"] and cierre["auditorias_previas_sin_cambios"]\n        assert cierre["conteos"]==v["conteos"] and cierre["archivos_sii"]==v["archivos_sii"]\n        assert len(cierre["auditorias_nuevas"])==2\n        assert [a["accion"] for a in cierre["auditorias_nuevas"]]==["FACTURA_APROBADA","ARCHIVO_SII_DESCARGADO"]\n        descarga=cierre["auditorias_nuevas"][-1]\n        assert descarga["usuario_id"]==1 and descarga["accion"]=="ARCHIVO_SII_DESCARGADO"\n        assert descarga["detalle"]=={"solicitud_afectada_id":3,"public_id":pid,"factura_id":f["id"],\n            "version_factura":2,"sha256":f["archivo_sii_sha256"]}\n'+marcador,1)
        ast.parse(nuevo);compile(nuevo,nombre,"exec")
        destino=app/"e2e"/nombre
        if destino.exists() and destino.read_text(encoding="utf-8-sig") not in (viejo,nuevo):raise RuntimeError("TEST_LOCAL_DISTINTO_NO_SE_SOBRESCRIBE")
        cambios.append((destino,nuevo))
    if input("Escribe AJUSTAR EXPECTATIVA QA para corregir SOLO los tests, sin ejecutarlos: ").strip()!="AJUSTAR EXPECTATIVA QA":raise RuntimeError("CANCELADO_POR_USUARIO_TESTS_NO_MODIFICADOS")
    for destino,nuevo in cambios:
        destino.write_text(nuevo,encoding="utf-8")
        (ev/(destino.name+".corregido-no-ejecutado.txt")).write_text(nuevo,encoding="utf-8")
    r.update(estado="VERIFICACION_CONFORME_CON_AUDITORIA_ESPERADA",total_solicitudes=5,total_facturas=2,total_auditoria=11,
        solicitud_version=8,solicitud_estado="Aprobada",xml_sha256=sha,xml_original_sin_cambios=hashlib.sha256(original_xml.read_bytes()).hexdigest()==sha,
        tests_corregidos_no_ejecutados=[d.name for d,_ in cambios],junit_previos_sin_modificar=True,
        referencia_cierre=str(ref),referencia_aprobacion_y_xml=str(aprobacion))
    codigo=0
except Exception as exc:
    r["estado"]="VERIFICACION_DETENIDA";r["error_tipo"]=type(exc).__name__
    if isinstance(exc,RuntimeError):r["error_controlado"]=str(exc)
    elif isinstance(exc,pymysql.MySQLError) and exc.args:r["codigo_error_bd"]=exc.args[0]
finally:
    if c:
        try:c.close()
        except Exception:pass
    r["fin"]=datetime.now().astimezone().isoformat()
    (ev/"resultado.json").write_text(json.dumps(r,indent=2),encoding="utf-8")
raise SystemExit(codigo)