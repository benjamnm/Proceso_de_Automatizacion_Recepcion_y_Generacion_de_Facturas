import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

referencia=Path(sys.argv[1]);evidencia=Path(sys.argv[2]);destino=Path(sys.argv[3])
with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for nombre in ("resultado.json","estado-final.json","ejecutar_monto_cero_qa.py"):
    p=referencia/nombre
    if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes.get(nombre):raise RuntimeError("HASH_REFERENCIA_SOL_005_NO_COINCIDE")
resultado=json.loads((referencia/"resultado.json").read_text(encoding="utf-8-sig"))
if resultado.get("ejecucion")!="QA-E2E-SOL-005" or resultado.get("codigo_pytest")!=0 or resultado.get("monto_cero_rechazado") is not True or resultado.get("error_monto_verificado") is not True or resultado.get("estado_comparado_sin_cambios") is not True or resultado.get("version_despues")!=3:
    raise RuntimeError("SOL_005_NO_TIENE_CIERRE_APROBADO_NO_SE_INICIA_SOL_006")
(evidencia/"cierre-previo-verificado.json").write_text(json.dumps({"ejecucion":resultado["ejecucion"],"codigo_pytest":0,
    "monto_cero_rechazado":True,"error_monto_verificado":True,"estado_comparado_sin_cambios":True,
    "version_despues":3,"referencia":str(referencia),"sha256_resultado":hashes["resultado.json"]},indent=2),encoding="utf-8")
origen=referencia/"ejecutar_monto_cero_qa.py"
source=origen.read_text(encoding="utf-8-sig")
ast.parse(source)
reemplazos=[
    ("E2E-SOL-005","E2E-SOL-006"),
    ("_qa_zero_context","_qa_native_context"),
    ("test_monto_cero_solicitud_qa.py","test_formato_nativo_monto_qa.py"),
    ("monto_cero_rechazado","bloqueo_nativo_verificado"),
    ("error_monto_verificado","patron_nativo_verificado"),
    ("un POST real con monto cero; error de servidor y de campo; sin cambios de datos ni auditoria",
     "dos formatos invalidos bloqueados por navegador; sin POST de edicion observado ni cambios de negocio"),
    ("Solo QA. Un envio real con monto 0 en ID 3. Se espera rechazo y conservar el monto 459000.",
     "Solo QA. Dos casos de formato nativo en ID 3: 1.000 y -1. No se espera POST de edicion."),
    ("Autorizar intento con monto cero. Escribe PROBAR MONTO CERO QA: ",
     "Autorizar pruebas nativas de formato. Escribe PROBAR FORMATO QA: "),
    ("PROBAR MONTO CERO QA","PROBAR FORMATO QA"),
    ('resultado["aviso_verificado"]=ctx["aviso_verificado"]',
     'resultado["aviso_verificado"]=ctx["aviso_verificado"]\n    resultado["patrones_completados"]=ctx.get("patrones_completados",[])')
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