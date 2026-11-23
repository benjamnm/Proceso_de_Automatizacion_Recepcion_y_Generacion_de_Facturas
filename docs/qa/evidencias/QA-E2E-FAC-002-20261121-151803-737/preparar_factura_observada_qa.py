import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

ref=Path(sys.argv[1]);ev=Path(sys.argv[2]);app=Path(sys.argv[3])
with (ref/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for n in ("resultado.json","estado-final.json","ejecutar_cierre_factura_qa.py","caso-ejecutado.py.txt"):
    if hashlib.sha256((ref/n).read_bytes()).hexdigest()!=hashes.get(n):raise RuntimeError("HASH_REFERENCIA_CIERRE_FAC_001_NO_COINCIDE")
r=json.loads((ref/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("codigo_pytest")!=0 or r.get("verificacion_complementaria_y_logout") is not True or r.get("estado_final_sin_cambios") is not True:raise RuntimeError("CIERRE_PREVIO_NO_CONFIRMADO")
anterior=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
arbol=ast.parse(anterior)
funciones=[n for n in arbol.body if isinstance(n,ast.FunctionDef) and n.name=="cerrar_alertas_y_logout"]
if len(funciones)!=1:raise RuntimeError("HELPER_LOGOUT_NO_IDENTIFICADO")
helper=ast.get_source_segment(anterior,funciones[0])+"\n\n\n"
plantilla=(ev/"plantilla-caso.py.txt").read_text(encoding="utf-8")
caso=plantilla.replace("__HELPER__",helper,1)
ast.parse(caso);compile(caso,"caso_fac_002","exec")
destino=app/"e2e"/"test_factura_observada_qa.py"
if destino.exists() and destino.read_text(encoding="utf-8-sig")!=caso:raise RuntimeError("CASO_LOCAL_DIFERENTE_NO_SE_SOBRESCRIBE")
s=(ref/"ejecutar_cierre_factura_qa.py").read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-FAC-001-CIERRE","E2E-FAC-002"),
 ("test_factura_existente_logout_qa.py","test_factura_observada_qa.py"),
 ("verificacion_complementaria_y_logout","devolucion_correccion_verificada"),
 ("qa.emisor@example.invalid","qa.admin@example.invalid"),
 ('actor["id"]!=2 or actor["rol"]!="Emisor"','actor["id"]!=1 or actor["rol"]!="Administrador"'),
 ("verificacion complementaria de factura existente y logout; no se regenera ni sustituye el resultado fallido",
  "Administrador devuelve factura v1 a correccion; solicitud v4 a v5; auditoria y contenido inmutable"),
 ("Solo QA. Se verificara la factura existente y el logout. No se genera otra factura.",
  "Solo QA. Administrador observa factura 1; solicitud 3 pasa a En correccion v5. No se genera otra factura."),
 ("Autorizar verificacion sin regenerar. Escribe VERIFICAR FACTURA EXISTENTE QA: ",
  "Autorizar devolucion persistida. Escribe DEVOLVER FACTURA QA: "),
 ("VERIFICAR FACTURA EXISTENTE QA","DEVOLVER FACTURA QA"),
 ('request.method=="POST" and request.path.endswith("/factura/revision")',
  'request.method=="POST" and request.path.startswith("/solicitudes/")'),
 ('d["auditoria"]==antes["auditoria"]','d["auditoria"][:len(antes["auditoria"])]==antes["auditoria"]'),
 ('v={"estado_comparado_sin_cambios":d==antes,',
  'v={"estado_igual_al_inicial":d==antes,"contenido_factura_conservado":len(d["facturas"])==1 and all(d["facturas"][0][k]==antes["facturas"][0][k] for k in antes["facturas"][0] if k not in {"estado","revisada_por","revisada_en","observacion"}),'),
 ('"estado_final_sin_cambios"','"estado_final_igual_al_inicial"'),
 ('"alcance_cierre"','"alcance_caso"'),
 ("Complementa el intento fallido; no reejecuta la generacion ni convierte su JUnit en aprobado",
  "Devolucion a correccion; no aprueba ni regenera factura ni genera XML SII")
]
registro=[]
for viejo,nuevo in reemplazos:
    cantidad=s.count(viejo)
    if not cantidad:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":cantidad});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_fac_002","exec")
destino.write_text(caso,encoding="utf-8")
(ev/"caso-ejecutado.py.txt").write_text(caso,encoding="utf-8")
(ev/"ejecutar_factura_observada_qa.py").write_text(s,encoding="utf-8")
(ev/"derivacion-runner.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,
    "helper_logout":"extraido del caso previo con hash verificado"},indent=2),encoding="utf-8")