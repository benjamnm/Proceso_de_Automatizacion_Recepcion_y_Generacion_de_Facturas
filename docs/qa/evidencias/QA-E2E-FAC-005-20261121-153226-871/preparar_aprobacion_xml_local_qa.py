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
for n in ("resultado.json","estado-final.json","ejecutar_reenvio_factura_v2_qa.py","caso-ejecutado.py.txt"):
    if hashlib.sha256((ref/n).read_bytes()).hexdigest()!=hashes.get(n):raise RuntimeError("HASH_REFERENCIA_FAC_004_NO_COINCIDE")
r=json.loads((ref/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("codigo_pytest")!=0 or r.get("reenvio_v2_verificado") is not True or r.get("solicitud_version_despues")!=7 or r.get("total_auditoria_despues")!=9:raise RuntimeError("CIERRE_FAC_004_NO_CONFIRMADO")
estado=json.loads((ref/"estado-final.json").read_text(encoding="utf-8-sig"))
f2=[f for f in estado["facturas"] if f["solicitud_id"]==3 and f["version"]==2]
if len(estado["facturas"])!=2 or len(f2)!=1 or f2[0]["estado"]!="EN_REVISION" or f2[0]["archivo_sii"] is not None:raise RuntimeError("FACTURA_V2_NO_ESPERADA")
anterior=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.parse(anterior).body if isinstance(n,ast.FunctionDef) and n.name=="cerrar_alertas_y_logout"]
if len(nodos)!=1:raise RuntimeError("HELPER_LOGOUT_NO_IDENTIFICADO")
helper=ast.get_source_segment(anterior,nodos[0])+"\n\n\n"
caso=(ev/"plantilla-caso.py.txt").read_text(encoding="utf-8").replace("__HELPER__",helper,1)
ast.parse(caso);compile(caso,"caso_fac_005","exec")
destino=app/"e2e"/"test_aprobacion_xml_local_qa.py"
if destino.exists() and destino.read_text(encoding="utf-8-sig")!=caso:raise RuntimeError("CASO_LOCAL_DIFERENTE_NO_SE_SOBRESCRIBE")
s=(ref/"ejecutar_reenvio_factura_v2_qa.py").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.walk(ast.parse(s)) if isinstance(n,ast.FunctionDef) and n.name=="verificar"]
if len(nodos)!=1:raise RuntimeError("VERIFICADOR_ORIGEN_NO_IDENTIFICADO")
n=nodos[0];lineas=s.splitlines(keepends=True)
s="".join(lineas[:n.lineno-1])+textwrap.indent('def verificar():\n    d=leer_estado();s=objetivo(d)\n    anteriores={f["id"]:f for f in antes["facturas"]}\n    actuales={f["id"]:f for f in d["facturas"]}\n    base_v2=next(f for f in antes["facturas"] if f["solicitud_id"]==3 and f["version"]==2)\n    v2=actuales.get(base_v2["id"])\n    mutables={"estado","revisada_por","revisada_en","archivo_sii","archivo_sii_sha256"}\n    carpeta=Path(ConfigQA.SII_FOLDER).resolve()\n    archivos=[]\n    for p in sorted(carpeta.rglob("*")):\n        if p.is_file():\n            if not p.resolve().is_relative_to(carpeta):raise RuntimeError("ARCHIVO_SII_FUERA_DE_EVIDENCIA_QA")\n            contenido=p.read_bytes()\n            archivos.append({"nombre":p.relative_to(carpeta).as_posix(),"bytes":len(contenido),"sha256":hashlib.sha256(contenido).hexdigest()})\n    v={"estado_igual_al_inicial":d==antes,"total_solicitudes":len(d["solicitudes"]),"total_auditoria":len(d["auditoria"]),"total_facturas":len(d["facturas"]),\n        "solicitud":s,"factura_v1":actuales.get(1),"factura_v2":v2,\n        "factura_v1_intacta":actuales.get(1)==anteriores.get(1),\n        "contenido_v2_conservado":bool(v2) and all(v2[k]==base_v2[k] for k in base_v2 if k not in mutables),\n        "sin_facturas_adicionales":set(actuales)==set(anteriores),\n        "campos_solicitud_conservados":bool(s) and all(s[k]==original[k] for k in original if k not in {"estado_id","estado_nombre","version","actualizado_en"}),\n        "otras_solicitudes_sin_cambios":all(next((x for x in d["solicitudes"] if x["public_id"]==a["public_id"]),None)==a for a in antes["solicitudes"] if a["public_id"]!=PID),\n        "auditorias_previas_sin_cambios":d["auditoria"][:len(antes["auditoria"])]==antes["auditoria"],\n        "auditorias_nuevas":d["auditoria"][len(antes["auditoria"]):],"conteos":d["conteos"],"archivos_sii":archivos}\n    ctx["verificacion"]=v\n    (evidencia/"verificacion-persistencia.json").write_text(json.dumps(v,indent=2),encoding="utf-8")\n    return v\n',"    ")+"".join(lineas[n.end_lineno:])
emisor={'EMPRESA_RUT': '22222222-2', 'EMPRESA_RAZON_SOCIAL': 'Emisor Sintetico QA Sin Validez Tributaria', 'EMPRESA_GIRO': 'Servicios sinteticos de prueba QA', 'EMPRESA_ACTECO': '620200', 'EMPRESA_DIRECCION': 'Direccion sintetica QA 123', 'EMPRESA_COMUNA': 'Comuna QA'}
campos="".join("        "+k+"="+repr(v)+"\n" for k,v in emisor.items())
reemplazos=[
 ("E2E-FAC-004","E2E-FAC-005"),
 ("test_reenvio_factura_v2_qa.py","test_aprobacion_xml_local_qa.py"),
 ("reenvio_v2_verificado","aprobacion_xml_verificada"),
 ("qa.emisor@example.invalid","qa.admin@example.invalid"),
 ('actor["id"]!=2 or actor["rol"]!="Emisor"','actor["id"]!=1 or actor["rol"]!="Administrador"'),
 ('len(antes["auditoria"])!=8','len(antes["auditoria"])!=9'),
 ('len(antes["facturas"])!=1','len(antes["facturas"])!=2'),
 ('original["version"]!=6','original["version"]!=7'),
 ('original["estado_nombre"]!="En corrección"','original["estado_nombre"]!="En revisión"'),
 ("Emisor reenvia solicitud corregida; genera factura v2; conserva v1 observada y auditorias previas",
  "Administrador aprueba v2 y genera XML local de prueba; descarga autenticada; v1 intacta; sin emision SII"),
 ("Solo QA. Reenvio persistido: solicitud 3 v6 a v7 En revision; factura v2 nueva; v1 observada intacta.",
  "Solo QA. Aprobacion persistida: solicitud 3 v7 a v8 Aprobada; v2 APROBADA y XML local con emisor sintetico. Sin envio al SII."),
 ("Autorizar reenvio y factura v2. Escribe REENVIAR FACTURA QA: ",
  "Autorizar aprobacion interna y XML local. Escribe APROBAR FACTURA QA: "),
 ("REENVIAR FACTURA QA","APROBAR FACTURA QA"),
 ('        SMTP_HOST="";',campos+'        SMTP_HOST="";'),
 ("Genera v2 por reenvio; conserva v1 y su observacion; no aprueba ni genera XML SII; no acredita entrega SMTP",
  "Aprobacion interna y XML local con datos sinteticos; descarga autenticada; no firma, TED, CAF, validacion XSD ni envio/aceptacion SII"),
 ('    resultado["fin"]=datetime.now().astimezone().isoformat()',
  '    resultado["xml_local_verificado"]=ctx.get("xml_local_verificado",False)\n    resultado["descarga_autenticada_verificada"]=ctx.get("descarga_autenticada_verificada",False)\n    resultado["emisor_xml"]="sintetico QA; sobreescrito solo en proceso; .env intacto"\n    resultado["fin"]=datetime.now().astimezone().isoformat()')
]
registro=[]
for viejo,nuevo in reemplazos:
    cantidad=s.count(viejo)
    if not cantidad:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":cantidad});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_fac_005","exec")
destino.write_text(caso,encoding="utf-8")
(ev/"caso-ejecutado.py.txt").write_text(caso,encoding="utf-8")
(ev/"referencia-factura-v2.json").write_text(json.dumps(f2[0],indent=2),encoding="utf-8")
(ev/"emisor-sintetico-qa.json").write_text(json.dumps(emisor,indent=2),encoding="utf-8")
(ev/"ejecutar_aprobacion_xml_local_qa.py").write_text(s,encoding="utf-8")
(ev/"derivacion-runner.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,
    "verificador":"aprobacion v2, invariancia v1 y lectura de archivo QA", "helper_logout":"extraido del caso previo con hash verificado"},indent=2),encoding="utf-8")