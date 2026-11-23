import ast
import csv
import hashlib
import json
import sys
import textwrap
from pathlib import Path

ref=Path(sys.argv[1]);ev=Path(sys.argv[2]);app=Path(sys.argv[3])
with (ref/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for n in ("resultado.json","estado-final.json","ejecutar_cierre_correccion_qa.py","caso-ejecutado.py.txt"):
    if hashlib.sha256((ref/n).read_bytes()).hexdigest()!=hashes.get(n):raise RuntimeError("HASH_REFERENCIA_CIERRE_FAC_003_NO_COINCIDE")
r=json.loads((ref/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("codigo_pytest")!=0 or r.get("verificacion_complementaria_y_logout") is not True or r.get("estado_final_igual_al_inicial") is not True or r.get("delta_edicion_archivada_verificado") is not True:raise RuntimeError("CIERRE_PREVIO_NO_CONFIRMADO")
estado=json.loads((ref/"estado-final.json").read_text(encoding="utf-8-sig"))
if len(estado["facturas"])!=1 or estado["facturas"][0]["id"]!=1 or estado["facturas"][0]["estado"]!="OBSERVADA":raise RuntimeError("FACTURA_V1_NO_ESPERADA")
anterior=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.parse(anterior).body if isinstance(n,ast.FunctionDef) and n.name=="cerrar_alertas_y_logout"]
if len(nodos)!=1:raise RuntimeError("HELPER_LOGOUT_NO_IDENTIFICADO")
helper=ast.get_source_segment(anterior,nodos[0])+"\n\n\n"
caso=(ev/"plantilla-caso.py.txt").read_text(encoding="utf-8").replace("__HELPER__",helper,1)
ast.parse(caso);compile(caso,"caso_fac_004","exec")
destino=app/"e2e"/"test_reenvio_factura_v2_qa.py"
if destino.exists() and destino.read_text(encoding="utf-8-sig")!=caso:raise RuntimeError("CASO_LOCAL_DIFERENTE_NO_SE_SOBRESCRIBE")
s=(ref/"ejecutar_cierre_correccion_qa.py").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.walk(ast.parse(s)) if isinstance(n,ast.FunctionDef) and n.name=="verificar"]
if len(nodos)!=1:raise RuntimeError("VERIFICADOR_ORIGEN_NO_IDENTIFICADO")
n=nodos[0];lineas=s.splitlines(keepends=True)
s="".join(lineas[:n.lineno-1])+textwrap.indent('def verificar():\n    d=leer_estado();s=objetivo(d)\n    anteriores={f["id"]:f for f in antes["facturas"]}\n    actuales={f["id"]:f for f in d["facturas"]}\n    nuevas=[f for f in d["facturas"] if f["id"] not in anteriores]\n    v2=[f for f in nuevas if f["solicitud_id"]==3 and f["version"]==2]\n    v={"estado_igual_al_inicial":d==antes,\n        "total_solicitudes":len(d["solicitudes"]),"total_auditoria":len(d["auditoria"]),"total_facturas":len(d["facturas"]),\n        "solicitud":s,"factura_v1":actuales.get(1),"factura_v2":v2[0] if len(v2)==1 else None,"facturas_nuevas":nuevas,\n        "facturas_previas_sin_cambios":all(actuales.get(i)==f for i,f in anteriores.items()),\n        "campos_solicitud_conservados":bool(s) and all(s[k]==original[k] for k in original if k not in {"estado_id","estado_nombre","version","actualizado_en"}),\n        "otras_solicitudes_sin_cambios":all(next((x for x in d["solicitudes"] if x["public_id"]==a["public_id"]),None)==a for a in antes["solicitudes"] if a["public_id"]!=PID),\n        "auditorias_previas_sin_cambios":d["auditoria"][:len(antes["auditoria"])]==antes["auditoria"],\n        "auditorias_nuevas":d["auditoria"][len(antes["auditoria"]):],"conteos":d["conteos"],\n        "archivos_sii_en_carpeta_qa":sum(1 for p in Path(ConfigQA.SII_FOLDER).rglob("*") if p.is_file())}\n    ctx["verificacion"]=v\n    (evidencia/"verificacion-persistencia.json").write_text(json.dumps(v,indent=2),encoding="utf-8")\n    return v\n',"    ")+"".join(lineas[n.end_lineno:])
reemplazos=[
 ("E2E-FAC-003-CIERRE","E2E-FAC-004"),
 ("test_correccion_existente_logout_qa.py","test_reenvio_factura_v2_qa.py"),
 ("verificacion_complementaria_y_logout","reenvio_v2_verificado"),
 ("Verifica correccion existente y factura historica; logout; sin editar ni reenviar; complementa intento fallido",
  "Emisor reenvia solicitud corregida; genera factura v2; conserva v1 observada y auditorias previas"),
 ("Solo QA. Verificacion de correccion ya persistida y factura historica, seguida de logout. No se guarda ni reenvia.",
  "Solo QA. Reenvio persistido: solicitud 3 v6 a v7 En revision; factura v2 nueva; v1 observada intacta."),
 ("Autorizar comprobacion sin guardar. Escribe VERIFICAR CORRECCION QA: ",
  "Autorizar reenvio y factura v2. Escribe REENVIAR FACTURA QA: "),
 ("VERIFICAR CORRECCION QA","REENVIAR FACTURA QA"),
 ("Comprobacion complementaria sin guardar ni reenviar; original conserva JUnit fallido",
  "Genera v2 por reenvio; conserva v1 y su observacion; no aprueba ni genera XML SII; no acredita entrega SMTP"),
 ('    resultado["delta_edicion_archivada_verificado"]=True\n',''),
 ('    resultado["caso_original_corregido_reejecutado"]=False\n','')
]
registro=[]
for viejo,nuevo in reemplazos:
    cantidad=s.count(viejo)
    if not cantidad:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":cantidad});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_fac_004","exec")
destino.write_text(caso,encoding="utf-8")
(ev/"caso-ejecutado.py.txt").write_text(caso,encoding="utf-8")
(ev/"referencia-factura-v1.json").write_text(json.dumps(estado["facturas"][0],indent=2),encoding="utf-8")
(ev/"ejecutar_reenvio_factura_v2_qa.py").write_text(s,encoding="utf-8")
(ev/"derivacion-runner.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,"verificador":"reemplazado por verificador multiversion v1/v2", "helper_logout":"extraido del caso previo con hash verificado"},indent=2),encoding="utf-8")