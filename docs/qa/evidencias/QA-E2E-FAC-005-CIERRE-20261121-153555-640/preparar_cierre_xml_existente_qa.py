import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

ref=Path(sys.argv[1]);ev=Path(sys.argv[2]);app=Path(sys.argv[3])
with (ref/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={r["archivo"].replace("\\","/"):r["sha256"].lower() for r in csv.DictReader(f)}
for nombre in ("resultado.json","estado-antes.json","estado-final.json","emisor-sintetico-qa.json","ejecutar_aprobacion_xml_local_qa.py","caso-ejecutado.py.txt"):
    if hashlib.sha256((ref/nombre).read_bytes()).hexdigest()!=hashes.get(nombre):raise RuntimeError("HASH_EVIDENCIA_FAC_005_NO_COINCIDE")
def leer(nombre):return json.loads((ref/nombre).read_text(encoding="utf-8-sig"))
r=leer("resultado.json");antes=leer("estado-antes.json");despues=leer("estado-final.json")
if r.get("codigo_pytest")!=1 or r.get("solicitud_version_despues")!=8 or r.get("total_auditoria_despues")!=10:raise RuntimeError("REFERENCIA_NO_ES_EL_INTENTO_ESPERADO")
pid="ee2e8fdb51290c59ae0ab6457a3ba001"
sa=next(x for x in antes["solicitudes"] if x["public_id"]==pid)
sb=next(x for x in despues["solicitudes"] if x["public_id"]==pid)
fa={x["id"]:x for x in antes["facturas"]};fb={x["id"]:x for x in despues["facturas"]}
v2a=next(x for x in antes["facturas"] if x["solicitud_id"]==3 and x["version"]==2)
v2=fb[v2a["id"]]
mutables={"estado","revisada_por","revisada_en","archivo_sii","archivo_sii_sha256"}
if not v2.get("archivo_sii") or Path(v2["archivo_sii"]).name!=v2["archivo_sii"]:raise RuntimeError("NOMBRE_XML_NO_ESPERADO")
clave_xml="datos-temporales/sii/"+v2["archivo_sii"]
xml_origen=ref/"datos-temporales"/"sii"/v2["archivo_sii"]
raiz_xml=(ref/"datos-temporales"/"sii").resolve()
if not xml_origen.resolve().is_relative_to(raiz_xml):raise RuntimeError("XML_FUERA_DE_EVIDENCIA_QA")
sha=hashlib.sha256(xml_origen.read_bytes()).hexdigest()
comprobaciones={
    "totales_esperados":len(antes["solicitudes"])==len(despues["solicitudes"])==5 and len(antes["auditoria"])==9 and len(despues["auditoria"])==10 and len(antes["facturas"])==len(despues["facturas"])==2,
    "solicitud_aprobada":sa["version"]==7 and sb["version"]==8 and sa["estado_nombre"]=="En revisión" and sb["estado_nombre"]=="Aprobada",
    "datos_solicitud_conservados":all(sa[k]==sb[k] for k in sa if k not in {"estado_id","estado_nombre","version","actualizado_en"}),
    "otras_solicitudes_intactas":[s for s in antes["solicitudes"] if s["public_id"]!=pid]==[s for s in despues["solicitudes"] if s["public_id"]!=pid],
    "v1_intacta":fa[1]==fb[1],"sin_facturas_adicionales":set(fa)==set(fb),
    "v2_aprobada":v2a["estado"]=="EN_REVISION" and v2["estado"]=="APROBADA" and v2["revisada_por"]==1 and v2["revisada_en"] is not None,
    "contenido_v2_intacto":all(v2a[k]==v2[k] for k in v2a if k not in mutables),
    "conteos_auxiliares_intactos":antes["conteos"]==despues["conteos"],
    "auditoria_previa_intacta":despues["auditoria"][:9]==antes["auditoria"],
    "xml_original_bd_y_manifiesto_coinciden":sha==v2["archivo_sii_sha256"]==hashes.get(clave_xml)}
a=despues["auditoria"][-1]
comprobaciones["auditoria_aprobacion_correcta"]=a["usuario_id"]==1 and a["accion"]=="FACTURA_APROBADA" and a["detalle"]=={
    "solicitud_afectada_id":3,"public_id":pid,"factura_id":v2["id"],"version_factura":2,"tipo_dte":34,
    "monto_total":v2["monto_total"],"archivo_sii_sha256":sha,"estado_anterior":"En revisión","estado_nuevo":"Aprobada","version_anterior":7,"version_nueva":8}
delta={"referencia":str(ref),"comprobaciones":comprobaciones,"delta_aprobacion_archivada_verificado":all(comprobaciones.values()),
    "xml_original":clave_xml,"sha256_xml_original":sha,"limite":"No repite aprobacion ni regeneracion; no cambia JUnit fallido"}
(ev/"verificacion-delta-aprobacion.json").write_text(json.dumps(delta,indent=2),encoding="utf-8")
if not delta["delta_aprobacion_archivada_verificado"]:raise RuntimeError("DELTA_APROBACION_NO_ESPERADO_NO_SE_INICIA_SELENIUM")
original=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
nodos=[n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=="cerrar_alertas_y_logout"]
if len(nodos)!=1:raise RuntimeError("HELPER_LOGOUT_NO_IDENTIFICADO")
helper_logout=ast.get_source_segment(original,nodos[0])+"\n\n\n"
helper_descarga='def descargar_en_sesion_del_navegador(driver, url, ev):\n    import base64\n    actual=urlsplit(driver.current_url)\n    destino=urlsplit(url)\n    assert (destino.scheme,destino.netloc)==(actual.scheme,actual.netloc)\n    driver.set_script_timeout(25)\n    resultado=driver.execute_async_script("""\n        const destino=new URL(arguments[0],location.href);\n        const fin=arguments[arguments.length-1];\n        if(destino.origin!==location.origin){fin({error:\'origen_distinto\'});return;}\n        const control=new AbortController();\n        const timer=setTimeout(()=>control.abort(),18000);\n        fetch(destino.href,{method:\'GET\',credentials:\'same-origin\',redirect:\'error\',\n            cache:\'no-store\',signal:control.signal})\n        .then(async r=>{\n            const a=new Uint8Array(await r.arrayBuffer());\n            let bin=\'\';\n            for(let i=0;i<a.length;i+=8192)\n                bin+=String.fromCharCode.apply(null,a.subarray(i,i+8192));\n            fin({status:r.status,url:r.url,redirected:r.redirected,\n                content_type:r.headers.get(\'Content-Type\')||\'\',\n                content_disposition:r.headers.get(\'Content-Disposition\')||\'\',\n                b64:btoa(bin)});\n        }).catch(e=>fin({error:e.name})).finally(()=>clearTimeout(timer));\n    """,url)\n    metadatos={k:v for k,v in resultado.items() if k!=\'b64\'}\n    metadatos[\'cliente\']=\'fetch mismo origen en Chrome; credenciales gestionadas por navegador\'\n    metadatos[\'proteccion_sesion\']=\'sin cambios; no se exportan cookies\'\n    (ev/\'respuesta-descarga-navegador.json\').write_text(json.dumps(metadatos,indent=2),encoding=\'utf-8\')\n    assert not resultado.get(\'error\'),metadatos\n    assert resultado[\'status\']==200 and resultado[\'url\']==url and not resultado[\'redirected\']\n    tipo=resultado[\'content_type\'];disposicion=resultado[\'content_disposition\']\n    assert \'xml\' in tipo.lower() and \'attachment\' in disposicion.lower()\n    return base64.b64decode(resultado[\'b64\'],validate=True),tipo,disposicion\n\n\n'
inicio='        sha=hashlib.sha256(contenido).hexdigest()'
fin='        assert all(v["conteos"][t]==0'
if original.count(inicio)!=1 or original.count(fin)!=1:raise RuntimeError("VERIFICACION_XML_ORIGINAL_NO_IDENTIFICADA")
xml_checks=original[original.index(inicio):original.index(fin)]
caso=(ev/"plantilla-caso.py.txt").read_text(encoding="utf-8").replace("__HELPERS__",helper_logout+helper_descarga,1).replace("__XML__",xml_checks,1)
ast.parse(caso);compile(caso,"caso_cierre_fac_005","exec")
corregido=original
bloque='        cookie="; ".join(c["name"]+"="+c["value"] for c in driver.get_cookies())\n        peticion=Request(url,headers={"Cookie":cookie})\n        with build_opener(ProxyHandler({})).open(peticion,timeout=20) as respuesta:\n            assert respuesta.status==200 and respuesta.geturl()==url\n            tipo=respuesta.headers.get("Content-Type","")\n            disposicion=respuesta.headers.get("Content-Disposition","")\n            assert "xml" in tipo.lower() and "attachment" in disposicion.lower()\n            contenido=respuesta.read()\n        cookie=None;peticion=None\n'
if corregido.count(bloque)!=1:raise RuntimeError("BLOQUE_DESCARGA_ORIGINAL_NO_IDENTIFICADO")
corregido=corregido.replace(bloque,'        contenido,tipo,disposicion=descargar_en_sesion_del_navegador(driver,url,ev)\n',1)
marca='def test_admin_aprueba_v2_xml_local_y_descarga_autenticada(request):'
if corregido.count(marca)!=1:raise RuntimeError("CASO_ORIGINAL_NO_IDENTIFICADO")
corregido=corregido.replace(marca,helper_descarga+marca,1)
ast.parse(corregido);compile(corregido,"caso_original_corregido","exec")
s=(ref/"ejecutar_aprobacion_xml_local_qa.py").read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-FAC-005","E2E-FAC-005-CIERRE"),
 ("test_aprobacion_xml_local_qa.py","test_xml_existente_navegador_qa.py"),
 ("aprobacion_xml_verificada","verificacion_complementaria_y_logout"),
 ('len(antes["auditoria"])!=9','len(antes["auditoria"])!=10'),
 ('original["version"]!=7','original["version"]!=8'),
 ('original["estado_nombre"]!="En revisión"','original["estado_nombre"]!="Aprobada"'),
 ('SII_FOLDER=str(evidencia/"datos-temporales"/"sii")','SII_FOLDER=str(referencia/"datos-temporales"/"sii")'),
 ("Administrador aprueba v2 y genera XML local de prueba; descarga autenticada; v1 intacta; sin emision SII",
  "Verifica aprobacion existente y XML original; descarga desde misma sesion Chrome; sin reaprobar ni regenerar"),
 ("Solo QA. Aprobacion persistida: solicitud 3 v7 a v8 Aprobada; v2 APROBADA y XML local con emisor sintetico. Sin envio al SII.",
  "Solo QA. Lee aprobacion y XML existentes; descarga desde Chrome; no vuelve a aprobar ni genera otro archivo."),
 ("Autorizar aprobacion interna y XML local. Escribe APROBAR FACTURA QA: ",
  "Autorizar comprobacion sin aprobar ni regenerar. Escribe VERIFICAR XML EXISTENTE QA: "),
 ("APROBAR FACTURA QA","VERIFICAR XML EXISTENTE QA"),
 ("Aprobacion interna y XML local con datos sinteticos; descarga autenticada; no firma, TED, CAF, validacion XSD ni envio/aceptacion SII",
  "Complementaria: XML existente y descarga fetch mismo origen; seguridad de sesion intacta; no reaprobar ni regenerar; original sigue fallido"),
 ('    resultado["fin"]=datetime.now().astimezone().isoformat()',
  '    resultado["delta_aprobacion_archivada_verificado"]=True\n    resultado["caso_original_corregido_reejecutado"]=False\n    resultado["xml_original_preservado_sha256"]='+repr(sha)+'\n    resultado["fin"]=datetime.now().astimezone().isoformat()')]
registro=[]
for viejo,nuevo in reemplazos:
    n=s.count(viejo)
    if not n:raise RuntimeError("RUNNER_ORIGEN_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":n});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_cierre_fac_005","exec")
destino_original=app/"e2e"/"test_aprobacion_xml_local_qa.py"
if destino_original.exists() and destino_original.read_text(encoding="utf-8-sig") not in (original,corregido):raise RuntimeError("CASO_ORIGINAL_LOCAL_DIFERENTE_NO_SE_SOBRESCRIBE")
destino=app/"e2e"/"test_xml_existente_navegador_qa.py"
if destino.exists() and destino.read_text(encoding="utf-8-sig")!=caso:raise RuntimeError("CASO_COMPLEMENTARIO_DIFERENTE_NO_SE_SOBRESCRIBE")
destino_original.write_text(corregido,encoding="utf-8")
destino.write_text(caso,encoding="utf-8")
(ev/"caso-original-corregido-no-reejecutado.py.txt").write_text(corregido,encoding="utf-8")
(ev/"caso-ejecutado.py.txt").write_text(caso,encoding="utf-8")
(ev/"emisor-sintetico-qa.json").write_text(json.dumps(leer("emisor-sintetico-qa.json"),indent=2),encoding="utf-8")
(ev/"ejecutar_cierre_xml_existente_qa.py").write_text(s,encoding="utf-8")
(ev/"derivacion-y-ajuste.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,
    "ajuste":"descarga fetch mismo origen en navegador; sin exportar cookies ni desactivar proteccion de sesion",
    "archivo_original":"solo lectura desde evidencia anterior; no se copia para servirlo ni se regenera"},indent=2),encoding="utf-8")