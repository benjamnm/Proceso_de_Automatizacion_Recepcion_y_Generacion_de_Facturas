import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

referencia=Path(sys.argv[1]);evidencia=Path(sys.argv[2]);destino=Path(sys.argv[3])
with (referencia/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"]:r["sha256"].lower() for r in csv.DictReader(f)}
for nombre in ("resultado.json","estado-final.json","ejecutar_formato_backend_qa.py"):
    p=referencia/nombre
    if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes.get(nombre):raise RuntimeError("HASH_REFERENCIA_SOL_007_NO_COINCIDE")
r=json.loads((referencia/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("ejecucion")!="QA-E2E-SOL-007" or r.get("codigo_pytest")!=0 or r.get("rechazo_backend_verificado") is not True or r.get("estado_comparado_sin_cambios") is not True:raise RuntimeError("SOL_007_NO_TIENE_CIERRE_APROBADO")
origen=referencia/"ejecutar_formato_backend_qa.py"
source=origen.read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-SOL-007","E2E-SOL-008"),
 ("_qa_backendformat_context","_qa_idempotency_context"),
 ("test_formato_backend_monto_qa.py","test_idempotencia_creacion_qa.py"),
 ("rechazo_backend_verificado","reenvio_idempotente_verificado"),
 ("error_formato_backend_verificado","persistencia_creacion_verificada"),
 ("formatos_backend_completados","etapas_completadas"),
 ("respuesta_error_verificada","creacion_web_verificada"),
 ("estado_comparado_sin_cambios","estado_igual_al_inicial"),
 ("version_despues","version_solicitud_original_3"),
 ("dos POST de formato invalido desde navegador; rechazo backend con CSRF y sesion; sin cambios de negocio",
  "alta web y reenvio identico con misma clave; una solicitud y una auditoria nuevas, sin duplicados"),
 ("Solo QA. Se enviaran dos POST invalidos (1.000 y -1) a ID 3 con sesion y CSRF; se espera rechazo backend.",
  "Solo QA. Se creara UNA solicitud nueva y se reenviara el MISMO formulario. Se conservara el alta."),
 ("Autorizar dos POST invalidos en QA. Escribe PROBAR FORMATO BACKEND QA: ",
  "Autorizar alta nueva y reenvio identico. Escribe PROBAR IDEMPOTENCIA QA: "),
 ("PROBAR FORMATO BACKEND QA","PROBAR IDEMPOTENCIA QA"),
 ('edicion=request.method=="POST" and request.path=="/solicitudes/"+PID+"/editar"',
  'edicion=request.method=="POST" and request.path=="/solicitudes/"+PID+"/editar"\n            creacion=request.method=="POST" and request.path=="/solicitudes/nueva"'),
 ('if edicion:', 'if edicion or creacion:'),
 ('    if input("Autorizar alta nueva y reenvio identico.',
  '    datos_creacion={"cliente_id":original["cliente_id"],"concepto":"QA-IDEMPOTENCIA-WEB-"+secrets.token_hex(4),"monto_bruto":"238000","fecha_emision":datetime.now().astimezone().date().isoformat(),"tipo_afectacion":"EXENTA","nro_orden_compra":"QA-OC-IDEMPOTENCIA"}\n    (evidencia/"datos-creacion.json").write_text(json.dumps(datos_creacion,indent=2),encoding="utf-8")\n    if input("Autorizar alta nueva y reenvio identico.'),
 ('    ctx.update(base_url=base_url,evidencia=str(evidencia),email=EMAIL,password=clave_web,public_id=PID,solicitud=original,verificar=verificar)',
  '    def verificar_creacion(public_id,etapa):\n        estado=leer_estado()\n        fila=next((s for s in estado["solicitudes"] if s["public_id"]==public_id),None)\n        v={"total_solicitudes":len(estado["solicitudes"]),"total_auditoria":len(estado["auditoria"]),\n            "solicitud_nueva":fila,"coincidencias_concepto":sum(s["concepto"]==datos_creacion["concepto"] for s in estado["solicitudes"]),\n            "originales_sin_cambios":all(next((s for s in estado["solicitudes"] if s["public_id"]==a["public_id"]),None)==a for a in antes["solicitudes"]),\n            "auditorias_previas_sin_cambios":estado["auditoria"][:3]==antes["auditoria"],\n            "auditorias_nuevas":estado["auditoria"][3:]}\n        if estado["conteos"]!=antes["conteos"]:raise RuntimeError("CONTEOS_RELACIONADOS_CAMBIARON_INESPERADAMENTE")\n        if etapa=="primer_alta":ctx["primer_estado"]=estado\n        else:v["igual_al_primer_alta"]=estado==ctx.get("primer_estado")\n        (evidencia/("estado-"+etapa+".json")).write_text(json.dumps(estado,indent=2),encoding="utf-8")\n        (evidencia/("verificacion-"+etapa+".json")).write_text(json.dumps(v,indent=2),encoding="utf-8")\n        ctx["idempotencia"]=v\n        return v\n\n'+'    ctx.update(base_url=base_url,evidencia=str(evidencia),email=EMAIL,password=clave_web,public_id=PID,solicitud=original,verificar=verificar,datos_creacion=datos_creacion,verificar_creacion=verificar_creacion)'),
 ('    resultado["fin"]=datetime.now().astimezone().isoformat()',
  '    resultado["public_id_nuevo"]=ctx.get("public_id_nuevo")\n    resultado["idempotencia"]=ctx.get("idempotencia")\n    resultado["estado_final_igual_al_primer_alta"]=(final==ctx["primer_estado"]) if "primer_estado" in ctx and "final" in locals() else None\n    resultado["fin"]=datetime.now().astimezone().isoformat()')
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