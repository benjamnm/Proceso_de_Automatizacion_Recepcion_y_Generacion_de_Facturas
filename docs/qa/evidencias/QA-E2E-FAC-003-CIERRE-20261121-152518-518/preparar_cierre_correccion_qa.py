import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

ref=Path(sys.argv[1]);ev=Path(sys.argv[2]);app=Path(sys.argv[3])
with (ref/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for n in ("resultado.json","estado-antes.json","estado-final.json","correccion-enviada.json","ejecutar_correccion_emisor_qa.py","caso-ejecutado.py.txt"):
    if hashlib.sha256((ref/n).read_bytes()).hexdigest()!=hashes.get(n):raise RuntimeError("HASH_EVIDENCIA_FAC_003_NO_COINCIDE")
def leer(nombre):return json.loads((ref/nombre).read_text(encoding="utf-8-sig"))
r=leer("resultado.json");antes=leer("estado-antes.json");despues=leer("estado-final.json");enviado=leer("correccion-enviada.json")
if r.get("codigo_pytest")!=1 or r.get("solicitud_version_despues")!=6 or r.get("total_auditoria_despues")!=8:raise RuntimeError("REFERENCIA_NO_ES_EL_INTENTO_ESPERADO")
pid="ee2e8fdb51290c59ae0ab6457a3ba001"
a=next(x for x in antes["solicitudes"] if x["public_id"]==pid)
b=next(x for x in despues["solicitudes"] if x["public_id"]==pid)
comprobaciones={
    "totales_esperados":len(antes["solicitudes"])==len(despues["solicitudes"])==5 and len(antes["auditoria"])==7 and len(despues["auditoria"])==8 and len(antes["facturas"])==len(despues["facturas"])==1,
    "version_y_estado":a["id"]==b["id"]==3 and a["version"]==5 and b["version"]==6 and a["estado_nombre"]==b["estado_nombre"]=="En corrección",
    "concepto_corregido":a["concepto"]==enviado["concepto_anterior"] and b["concepto"]==enviado["concepto_nuevo"] and a["concepto"]!=b["concepto"],
    "otros_campos_conservados":all(a[k]==b[k] for k in a if k not in {"concepto","version","actualizado_en"}),
    "otras_solicitudes_intactas":[x for x in antes["solicitudes"] if x["public_id"]!=pid]==[x for x in despues["solicitudes"] if x["public_id"]!=pid],
    "facturas_intactas":antes["facturas"]==despues["facturas"],
    "conteos_auxiliares_intactos":antes["conteos"]==despues["conteos"],
    "auditoria_previa_intacta":despues["auditoria"][:7]==antes["auditoria"]}
e=despues["auditoria"][-1]
comprobaciones["auditoria_edicion_correcta"]=e["usuario_id"]==2 and e["accion"]=="SOLICITUD_EDITADA" and e["detalle"]=={
    "solicitud_afectada_id":3,"public_id":pid,"estado":"En corrección","version_anterior":5,"version_nueva":6,
    "cambios":{"concepto":{"anterior":a["concepto"],"nuevo":b["concepto"]}}}
http=[e for e in r["eventos_http"] if e["metodo"]=="POST" and e["ruta"]=="/solicitudes/"+pid+"/editar"]
comprobaciones["redireccion_archivada_a_factura"]=len(http)==1 and http[0]["status"]==302 and http[0]["location"]=="/solicitudes/"+pid+"/factura" and http[0]["usuario_id"]==2 and http[0]["version_formulario"]=="5"
delta={"referencia":str(ref),"concepto_anterior":a["concepto"],"concepto_nuevo":b["concepto"],"comprobaciones":comprobaciones,"delta_archivado_verificado":all(comprobaciones.values()),"limite":"Verifica archivos del intento fallido; no reejecuta el POST ni cambia su JUnit"}
(ev/"verificacion-delta-edicion.json").write_text(json.dumps(delta,ensure_ascii=True,indent=2),encoding="utf-8")
if not delta["delta_archivado_verificado"]:raise RuntimeError("DELTA_ARCHIVADO_NO_ESPERADO_NO_SE_INICIA_SELENIUM")
original=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=="cerrar_alertas_y_logout"]
if len(nodos)!=1:raise RuntimeError("HELPER_LOGOUT_NO_IDENTIFICADO")
helper=ast.get_source_segment(original,nodos[0])+"\n\n\n"
caso=(ev/"plantilla-caso.py.txt").read_text(encoding="utf-8").replace("__HELPER__",helper,1)
ast.parse(caso);compile(caso,"caso_cierre_fac_003","exec")
linea='        assert urlsplit(e["location"]).path in {raiz,raiz+"/editar"}'
corregido=original
if corregido.count(linea)!=1:raise RuntimeError("ASERCION_ORIGINAL_NO_IDENTIFICADA")
corregido=corregido.replace(linea,'        assert urlsplit(e["location"]).path==raiz+"/factura"',1)
bloque='        def guardado(d):\n            if nuevo in d.find_element(By.TAG_NAME,"body").text:return True\n            return any(x.get_attribute("value")==nuevo for x in d.find_elements(By.ID,"concepto"))\n        wait.until(guardado)'
nuevo='        wait.until(lambda d:urlsplit(d.current_url).path==raiz+"/factura")\n        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME,"body"),"En corrección"))\n        assert driver.find_element(By.CSS_SELECTOR,"dd.texto-preformateado").text==original["concepto"]'
if corregido.count(bloque)!=1:raise RuntimeError("ESPERA_CONCEPTO_ORIGINAL_NO_IDENTIFICADA")
corregido=corregido.replace(bloque,nuevo,1)
ast.parse(corregido);compile(corregido,"caso_original_corregido","exec")
s=(ref/"ejecutar_correccion_emisor_qa.py").read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-FAC-003","E2E-FAC-003-CIERRE"),
 ("test_correccion_emisor_qa.py","test_correccion_existente_logout_qa.py"),
 ("correccion_emisor_verificada","verificacion_complementaria_y_logout"),
 ('len(antes["auditoria"])!=7','len(antes["auditoria"])!=8'),
 ('original["version"]!=5','original["version"]!=6'),
 ("Emisor corrige concepto en solicitud observada; version 5 a 6; factura v1 sin cambios; no reenvio",
  "Verifica correccion existente y factura historica; logout; sin editar ni reenviar; complementa intento fallido"),
 ("Solo QA. Emisor corrige concepto de solicitud 3; sigue En correccion y pasa de v5 a v6; factura 1 intacta.",
  "Solo QA. Verificacion de correccion ya persistida y factura historica, seguida de logout. No se guarda ni reenvia."),
 ("Autorizar edicion persistida. Escribe CORREGIR SOLICITUD QA: ",
  "Autorizar comprobacion sin guardar. Escribe VERIFICAR CORRECCION QA: "),
 ("CORREGIR SOLICITUD QA","VERIFICAR CORRECCION QA"),
 ("Corrige solo concepto en solicitud; conserva factura observada; no reenvia ni aprueba ni genera XML SII",
  "Comprobacion complementaria sin guardar ni reenviar; original conserva JUnit fallido"),
 ('    resultado["fin"]=datetime.now().astimezone().isoformat()',
  '    resultado["delta_edicion_archivada_verificado"]=True\n    resultado["caso_original_corregido_reejecutado"]=False\n    resultado["fin"]=datetime.now().astimezone().isoformat()')]
registro=[]
for viejo,nuevo in reemplazos:
    n=s.count(viejo)
    if not n:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":n});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_cierre_fac_003","exec")
destino_original=app/"e2e"/"test_correccion_emisor_qa.py"
if destino_original.exists() and destino_original.read_text(encoding="utf-8-sig") not in (original,corregido):raise RuntimeError("CASO_ORIGINAL_LOCAL_DIFERENTE_NO_SE_SOBRESCRIBE")
destino=app/"e2e"/"test_correccion_existente_logout_qa.py"
if destino.exists() and destino.read_text(encoding="utf-8-sig")!=caso:raise RuntimeError("CASO_COMPLEMENTARIO_DIFERENTE_NO_SE_SOBRESCRIBE")
destino_original.write_text(corregido,encoding="utf-8")
destino.write_text(caso,encoding="utf-8")
(ev/"caso-original-corregido-no-reejecutado.py.txt").write_text(corregido,encoding="utf-8")
(ev/"caso-ejecutado.py.txt").write_text(caso,encoding="utf-8")
(ev/"ejecutar_cierre_correccion_qa.py").write_text(s,encoding="utf-8")
(ev/"derivacion-y-ajuste.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,"ajustes_caso_original":["espera redireccion a factura","verifica concepto historico en factura; concepto nuevo se comprueba en SQL"],"caso_original_reejecutado":False},indent=2),encoding="utf-8")