import ast
import csv
import hashlib
import json
import sys
from pathlib import Path

ref=Path(sys.argv[1]);ev=Path(sys.argv[2]);app=Path(sys.argv[3])
with (ref/"manifiesto-sha256.csv").open(encoding="utf-8-sig",newline="") as f:
    hashes={x["archivo"]:x["sha256"].lower() for x in csv.DictReader(f)}
for n in ("ejecutar_factura_revision_qa.py","caso-ejecutado.py.txt","resultado.json","estado-final.json"):
    if hashlib.sha256((ref/n).read_bytes()).hexdigest()!=hashes.get(n):raise RuntimeError("HASH_EVIDENCIA_FAC_001_NO_COINCIDE")
r=json.loads((ref/"resultado.json").read_text(encoding="utf-8-sig"))
if r.get("codigo_pytest")!=1 or r.get("total_facturas_despues")!=1 or r.get("solicitud_version_despues")!=4 or r.get("total_auditoria_despues")!=6:raise RuntimeError("REFERENCIA_NO_CORRESPONDE_AL_FALLO_DE_CIERRE")
s=(ref/"ejecutar_factura_revision_qa.py").read_text(encoding="utf-8-sig")
reemplazos=[
 ("E2E-FAC-001","E2E-FAC-001-CIERRE"),
 ("test_factura_revision_qa.py","test_factura_existente_logout_qa.py"),
 ("factura_revision_verificada","verificacion_complementaria_y_logout"),
 ("generacion de factura exenta v1 para solicitud 3; estado En revision y auditoria; sin SMTP ni XML SII",
  "verificacion complementaria de factura existente y logout; no se regenera ni sustituye el resultado fallido"),
 ("Solo QA. ID 3: Pendiente v3 a En revision v4; una factura v1. SMTP vacio; sin aprobacion ni XML SII.",
  "Solo QA. Se verificara la factura existente y el logout. No se genera otra factura."),
 ('len(antes["auditoria"])!=5','len(antes["auditoria"])!=6'),
 ('or antes["facturas"] or not original','or len(antes["facturas"])!=1 or not original'),
 ('original["version"]!=3','original["version"]!=4'),
 ('original["estado_nombre"]!="Pendiente"','original["estado_nombre"]!="En revisión"'),
 ("Autorizar generacion persistida. Escribe GENERAR FACTURA QA: ",
  "Autorizar verificacion sin regenerar. Escribe VERIFICAR FACTURA EXISTENTE QA: "),
 ("GENERAR FACTURA QA","VERIFICAR FACTURA EXISTENTE QA"),
 ('v={"total_solicitudes":','v={"estado_comparado_sin_cambios":d==antes,"total_solicitudes":'),
 ('d["auditoria"][:5]==antes["auditoria"]','d["auditoria"]==antes["auditoria"]'),
 ('d["auditoria"][5:]','d["auditoria"][len(antes["auditoria"]):]'),
 ('    resultado["fin"]=datetime.now().astimezone().isoformat()',
  '    resultado["alertas_cerradas_logout"]=ctx.get("alertas_cerradas_logout")\n    resultado["alcance_cierre"]="Complementa el intento fallido; no reejecuta la generacion ni convierte su JUnit en aprobado"\n    resultado["estado_final_sin_cambios"]=(final==antes) if antes is not None and "final" in locals() else None\n    resultado["fin"]=datetime.now().astimezone().isoformat()')
]
registro=[]
for viejo,nuevo in reemplazos:
    n=s.count(viejo)
    if not n:raise RuntimeError("RUNNER_DISTINTO_DEL_ESPERADO")
    registro.append({"anterior":viejo,"nuevo":nuevo,"ocurrencias":n});s=s.replace(viejo,nuevo)
ast.parse(s);compile(s,"runner_cierre","exec")
(ev/"ejecutar_cierre_factura_qa.py").write_text(s,encoding="utf-8")
original=(ref/"caso-ejecutado.py.txt").read_text(encoding="utf-8-sig")
linea='        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action=\'/auth/logout\'] button[type=\'submit\']"))).click()'
if original.count(linea)!=1:raise RuntimeError("NO_SE_ENCONTRO_LOGOUT_ORIGINAL_UNICO")
corregido=original.replace(linea,'        ctx["alertas_cerradas_logout"]=cerrar_alertas_y_logout(driver,wait)',1)
marca='def test_generar_factura_exenta_y_enviar_revision(request):'
if corregido.count(marca)!=1:raise RuntimeError("CASO_ORIGINAL_DISTINTO")
corregido=corregido.replace(marca,'def cerrar_alertas_y_logout(driver, wait):\n    from selenium.common.exceptions import StaleElementReferenceException\n\n    def libre(elemento):\n        try:\n            if not elemento.is_displayed() or not elemento.is_enabled():\n                return False\n            return driver.execute_script("""\n                const e=arguments[0],r=e.getBoundingClientRect();\n                const x=r.left+r.width/2,y=r.top+r.height/2;\n                if(x<0 || y<0 || x>=innerWidth || y>=innerHeight) return false;\n                const p=document.elementFromPoint(x,y);\n                return p===e || e.contains(p);\n            """,elemento)\n        except StaleElementReferenceException:\n            return False\n\n    cerradas=0\n    for _ in range(8):\n        def accion(d):\n            try:\n                alertas=[a for a in d.find_elements(By.CSS_SELECTOR,".flash-container .alert.show") if a.is_displayed()]\n                if not alertas:return ("sin_alertas",None,None)\n                for alerta in reversed(alertas):\n                    for boton in alerta.find_elements(By.CSS_SELECTOR,"button[data-bs-dismiss=\'alert\']"):\n                        if libre(boton):return ("cerrar",boton,alerta)\n                return False\n            except StaleElementReferenceException:\n                return False\n        tipo,boton,alerta=wait.until(accion)\n        if tipo=="sin_alertas":break\n        boton.click()\n        wait.until(EC.invisibility_of_element(alerta))\n        cerradas+=1\n    else:\n        raise AssertionError("Demasiadas alertas pendientes; no se fuerza el logout")\n\n    def objetivo(d):\n        botones=d.find_elements(By.CSS_SELECTOR,"form[action=\'/auth/logout\'] button[type=\'submit\']")\n        return next((b for b in botones if libre(b)),False)\n    wait.until(objetivo).click()\n    return cerradas\n\n\n'+marca,1)
ast.parse(corregido)
destino=app/"e2e"/"test_factura_revision_qa.py"
if destino.exists():
    actual=destino.read_text(encoding="utf-8-sig")
    if actual not in (original,corregido):raise RuntimeError("CASO_LOCAL_MODIFICADO_NO_SE_SOBRESCRIBE")
destino.write_text(corregido,encoding="utf-8")
(ev/"caso-generacion-corregido-no-reejecutado.py.txt").write_text(corregido,encoding="utf-8")
(ev/"derivacion-y-ajuste.json").write_text(json.dumps({"referencia":str(ref),"transformaciones":registro,
    "ajuste":"Solo test Selenium; cierre de alertas por boton y comprobacion de oclusion antes de logout",
    "caso_original_corregido_reejecutado":False},indent=2),encoding="utf-8")