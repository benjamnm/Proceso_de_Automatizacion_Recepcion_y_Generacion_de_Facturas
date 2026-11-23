import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

referencia=Path(sys.argv[1]);evidencia=Path(sys.argv[2]);destino=Path(sys.argv[3])
with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for nombre in ("resultado.json","estado-final.json","ejecutar_formato_nativo_qa.py"):
    p=referencia/nombre
    if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes.get(nombre):raise RuntimeError("HASH_REFERENCIA_SOL_006_NO_COINCIDE")
r=json.loads((referencia/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("ejecucion")!="QA-E2E-SOL-006" or r.get("codigo_pytest")!=0 or r.get("bloqueo_nativo_verificado") is not True or r.get("estado_comparado_sin_cambios") is not True or set(r.get("patrones_completados",[]))!={"separador","negativo"}:
    raise RuntimeError("SOL_006_NO_TIENE_CIERRE_APROBADO")
(evidencia/"cierre-previo-verificado.json").write_text(json.dumps({"ejecucion":r["ejecucion"],"codigo_pytest":0,
    "patrones_completados":r["patrones_completados"],"referencia":str(referencia),"sha256_resultado":hashes["resultado.json"]},indent=2),encoding="utf-8")
origen=referencia/"ejecutar_formato_nativo_qa.py"
source=origen.read_text(encoding="utf-8-sig")
ast.parse(source)
reemplazos=[
    ("E2E-SOL-006","E2E-SOL-007"),
    ("_qa_native_context","_qa_backendformat_context"),
    ("test_formato_nativo_monto_qa.py","test_formato_backend_monto_qa.py"),
    ("bloqueo_nativo_verificado","rechazo_backend_verificado"),
    ("patron_nativo_verificado","error_formato_backend_verificado"),
    ("patrones_completados","formatos_backend_completados"),
    ("aviso_verificado","respuesta_error_verificada"),
    ("dos formatos invalidos bloqueados por navegador; sin POST de edicion observado ni cambios de negocio",
     "dos POST de formato invalido desde navegador; rechazo backend con CSRF y sesion; sin cambios de negocio"),
    ("Solo QA. Dos casos de formato nativo en ID 3: 1.000 y -1. No se espera POST de edicion.",
     "Solo QA. Se enviaran dos POST invalidos (1.000 y -1) a ID 3 con sesion y CSRF; se espera rechazo backend."),
    ("Autorizar pruebas nativas de formato. Escribe PROBAR FORMATO QA: ",
     "Autorizar dos POST invalidos en QA. Escribe PROBAR FORMATO BACKEND QA: "),
    ("PROBAR FORMATO QA","PROBAR FORMATO BACKEND QA")
]
registro=[]
for viejo,nuevo in reemplazos:
    cantidad=source.count(viejo)
    if cantidad==0:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_NO_SE_PUEDE_DERIVAR")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":cantidad})
    source=source.replace(viejo,nuevo)
ast.parse(source);compile(source,str(destino),"exec")
destino.write_text(source,encoding="utf-8")
(evidencia/"derivacion-runner.json").write_text(json.dumps({"origen":str(origen),"sha256_origen":hashes[origen.name],
    "sha256_generado":hashlib.sha256(destino.read_bytes()).hexdigest(),"transformaciones":registro},indent=2),encoding="utf-8")