import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

referencia=Path(sys.argv[1]);evidencia=Path(sys.argv[2]);destino=Path(sys.argv[3])
with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for nombre in ("resultado.json","estado-final.json","ejecutar_idempotencia_qa.py"):
    p=referencia/nombre
    if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes.get(nombre):raise RuntimeError("HASH_REFERENCIA_SOL_008_NO_COINCIDE")
r=json.loads((referencia/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("ejecucion")!="QA-E2E-SOL-008" or r.get("codigo_pytest")!=0 or r.get("reenvio_idempotente_verificado") is not True or r.get("estado_final_igual_al_primer_alta") is not True or r.get("total_solicitudes_despues")!=4 or r.get("total_auditoria_despues")!=4:raise RuntimeError("SOL_008_NO_TIENE_CIERRE_APROBADO")
origen=referencia/"ejecutar_idempotencia_qa.py"
source=origen.read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-SOL-008","E2E-SOL-009"),
 ("_qa_idempotency_context","_qa_keyconflict_context"),
 ("test_idempotencia_creacion_qa.py","test_conflicto_clave_creacion_qa.py"),
 ("reenvio_idempotente_verificado","conflicto_clave_verificado"),
 ('"idempotencia"','"conflicto_clave"'),
 ('len(antes["solicitudes"])!=3 or len(antes["auditoria"])!=3',
  'len(antes["solicitudes"])!=4 or len(antes["auditoria"])!=4'),
 ('estado["auditoria"][:3]','estado["auditoria"][:4]'),
 ('estado["auditoria"][3:]','estado["auditoria"][4:]'),
 ("QA-IDEMPOTENCIA-WEB-","QA-CLAVE-CONFLICTO-WEB-"),
 ("QA-OC-IDEMPOTENCIA","QA-OC-CLAVE-CONFLICTO"),
 ("alta web y reenvio identico con misma clave; una solicitud y una auditoria nuevas, sin duplicados",
  "alta web; misma clave con concepto y monto distintos rechazada sin alterar datos ni agregar auditoria"),
 ("Solo QA. Se creara UNA solicitud nueva y se reenviara el MISMO formulario. Se conservara el alta.",
  "Solo QA. Se creara una solicitud nueva y se intentara reutilizar su clave con datos distintos. Se conserva el alta."),
 ("Autorizar alta nueva y reenvio identico. Escribe PROBAR IDEMPOTENCIA QA: ",
  "Autorizar alta y conflicto de clave. Escribe PROBAR CONFLICTO CLAVE QA: "),
 ("PROBAR IDEMPOTENCIA QA","PROBAR CONFLICTO CLAVE QA")
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