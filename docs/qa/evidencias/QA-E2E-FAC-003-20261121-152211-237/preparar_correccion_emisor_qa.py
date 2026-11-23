import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

ref=Path(sys.argv[1]);ev=Path(sys.argv[2]);app=Path(sys.argv[3])
with (ref/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for n in ("resultado.json","estado-final.json","ejecutar_factura_observada_qa.py","caso-ejecutado.py.txt"):
    if hashlib.sha256((ref/n).read_bytes()).hexdigest()!=hashes.get(n):raise RuntimeError("HASH_REFERENCIA_FAC_002_NO_COINCIDE")
r=json.loads((ref/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("codigo_pytest")!=0 or r.get("devolucion_correccion_verificada") is not True or r.get("solicitud_version_despues")!=5 or r.get("total_auditoria_despues")!=7:raise RuntimeError("CIERRE_FAC_002_NO_CONFIRMADO")
anterior=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.parse(anterior).body if isinstance(n,ast.FunctionDef) and n.name=="cerrar_alertas_y_logout"]
if len(nodos)!=1:raise RuntimeError("HELPER_LOGOUT_NO_IDENTIFICADO")
helper=ast.get_source_segment(anterior,nodos[0])+"\n\n\n"
caso=(ev/"plantilla-caso.py.txt").read_text(encoding="utf-8").replace("__HELPER__",helper,1)
ast.parse(caso);compile(caso,"caso_fac_003","exec")
destino=app/"e2e"/"test_correccion_emisor_qa.py"
if destino.exists() and destino.read_text(encoding="utf-8-sig")!=caso:raise RuntimeError("CASO_LOCAL_DIFERENTE_NO_SE_SOBRESCRIBE")
s=(ref/"ejecutar_factura_observada_qa.py").read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-FAC-002","E2E-FAC-003"),
 ("test_factura_observada_qa.py","test_correccion_emisor_qa.py"),
 ("devolucion_correccion_verificada","correccion_emisor_verificada"),
 ("qa.admin@example.invalid","qa.emisor@example.invalid"),
 ('actor["id"]!=1 or actor["rol"]!="Administrador"','actor["id"]!=2 or actor["rol"]!="Emisor"'),
 ('len(antes["auditoria"])!=6','len(antes["auditoria"])!=7'),
 ('original["version"]!=4','original["version"]!=5'),
 ('original["estado_nombre"]!="En revisión"','original["estado_nombre"]!="En corrección"'),
 ("Administrador devuelve factura v1 a correccion; solicitud v4 a v5; auditoria y contenido inmutable",
  "Emisor corrige concepto en solicitud observada; version 5 a 6; factura v1 sin cambios; no reenvio"),
 ("Solo QA. Administrador observa factura 1; solicitud 3 pasa a En correccion v5. No se genera otra factura.",
  "Solo QA. Emisor corrige concepto de solicitud 3; sigue En correccion y pasa de v5 a v6; factura 1 intacta."),
 ("Autorizar devolucion persistida. Escribe DEVOLVER FACTURA QA: ",
  "Autorizar edicion persistida. Escribe CORREGIR SOLICITUD QA: "),
 ("DEVOLVER FACTURA QA","CORREGIR SOLICITUD QA"),
 ('if k not in {"estado_id","estado_nombre","version","actualizado_en"}',
  'if k not in {"concepto","version","actualizado_en"}'),
 ('"campos_conservados":conservados','"campos_no_editados_conservados":conservados'),
 ('"contenido_factura_conservado":len(d["facturas"])==1 and all(d["facturas"][0][k]==antes["facturas"][0][k] for k in antes["facturas"][0] if k not in {"estado","revisada_por","revisada_en","observacion"})',
  '"facturas_previas_sin_cambios":d["facturas"]==antes["facturas"]'),
 ("Devolucion a correccion; no aprueba ni regenera factura ni genera XML SII",
  "Corrige solo concepto en solicitud; conserva factura observada; no reenvia ni aprueba ni genera XML SII")
]
registro=[]
for viejo,nuevo in reemplazos:
    cantidad=s.count(viejo)
    if not cantidad:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":cantidad});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_fac_003","exec")
destino.write_text(caso,encoding="utf-8")
(ev/"caso-ejecutado.py.txt").write_text(caso,encoding="utf-8")
(ev/"ejecutar_correccion_emisor_qa.py").write_text(s,encoding="utf-8")
(ev/"derivacion-runner.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,
    "helper_logout":"extraido del caso previo con hash verificado"},indent=2),encoding="utf-8")