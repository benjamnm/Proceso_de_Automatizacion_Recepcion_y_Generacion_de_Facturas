import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

referencia=Path(sys.argv[1]);evidencia=Path(sys.argv[2]);destino=Path(sys.argv[3])
with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
origen=referencia/"ejecutar_guardado_sin_cambios_qa.py"
sha=hashlib.sha256(origen.read_bytes()).hexdigest()
if sha!=hashes.get(origen.name):raise RuntimeError("HASH_DEL_RUNNER_SOL_004_NO_COINCIDE")
source=origen.read_text(encoding="utf-8-sig")
ast.parse(source)
reemplazos=[
    ("E2E-SOL-004","E2E-SOL-005"),
    ("_qa_nochange_context","_qa_zero_context"),
    ("test_guardado_sin_cambios_qa.py","test_monto_cero_solicitud_qa.py"),
    ("guardado_sin_cambios_verificado","monto_cero_rechazado"),
    ("un POST real sin cambiar valores; aviso, version 3 conservada y sin nueva auditoria",
     "un POST real con monto cero; error de servidor y de campo; sin cambios de datos ni auditoria"),
    ("Solo QA. Un envio real del formulario ID 3 sin modificar campos. No se espera cambio de negocio.",
     "Solo QA. Un envio real con monto 0 en ID 3. Se espera rechazo y conservar el monto 459000."),
    ("Autorizar un envio sin cambios. Escribe GUARDAR SIN CAMBIOS QA: ",
     "Autorizar intento con monto cero. Escribe PROBAR MONTO CERO QA: "),
    ("GUARDAR SIN CAMBIOS QA","PROBAR MONTO CERO QA"),
    ('resultado["aviso_verificado"]=ctx["aviso_verificado"]',
     'resultado["aviso_verificado"]=ctx["aviso_verificado"]\n    resultado["error_monto_verificado"]=ctx.get("error_monto_verificado",False)')
]
registro=[]
for viejo,nuevo in reemplazos:
    cantidad=source.count(viejo)
    if cantidad==0:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_NO_SE_PUEDE_DERIVAR")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":cantidad})
    source=source.replace(viejo,nuevo)
ast.parse(source)
compile(source,str(destino),"exec")
destino.write_text(source,encoding="utf-8")
(evidencia/"derivacion-runner.json").write_text(json.dumps({"origen":str(origen),"sha256_origen":sha,
    "sha256_generado":hashlib.sha256(destino.read_bytes()).hexdigest(),"transformaciones":registro},indent=2),encoding="utf-8")