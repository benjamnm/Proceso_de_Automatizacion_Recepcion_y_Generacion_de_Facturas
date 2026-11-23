import hashlib
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def cerrar_alertas_y_logout(driver, wait):
    from selenium.common.exceptions import StaleElementReferenceException

    def libre(elemento):
        try:
            if not elemento.is_displayed() or not elemento.is_enabled():
                return False
            return driver.execute_script("""
                const e=arguments[0],r=e.getBoundingClientRect();
                const x=r.left+r.width/2,y=r.top+r.height/2;
                if(x<0 || y<0 || x>=innerWidth || y>=innerHeight) return false;
                const p=document.elementFromPoint(x,y);
                return p===e || e.contains(p);
            """,elemento)
        except StaleElementReferenceException:
            return False

    cerradas=0
    for _ in range(8):
        def accion(d):
            try:
                alertas=[a for a in d.find_elements(By.CSS_SELECTOR,".flash-container .alert.show") if a.is_displayed()]
                if not alertas:return ("sin_alertas",None,None)
                for alerta in reversed(alertas):
                    for boton in alerta.find_elements(By.CSS_SELECTOR,"button[data-bs-dismiss='alert']"):
                        if libre(boton):return ("cerrar",boton,alerta)
                return False
            except StaleElementReferenceException:
                return False
        tipo,boton,alerta=wait.until(accion)
        if tipo=="sin_alertas":break
        boton.click()
        wait.until(EC.invisibility_of_element(alerta))
        cerradas+=1
    else:
        raise AssertionError("Demasiadas alertas pendientes; no se fuerza el logout")

    def objetivo(d):
        botones=d.find_elements(By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']")
        return next((b for b in botones if libre(b)),False)
    wait.until(objetivo).click()
    return cerradas


def test_emisor_reenvia_y_genera_v2_con_v1_intacta(request):
    ctx=request.config._qa_invoice_context
    ev=Path(ctx["evidencia"])
    anterior=json.loads((ev/"referencia-factura-v1.json").read_text(encoding="utf-8"))
    driver=None;fallo=False
    try:
        opciones=webdriver.ChromeOptions();opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000);driver.set_page_load_timeout(30)
        wait=WebDriverWait(driver,20)
        caps=driver.capabilities
        (ev/"navegador.json").write_text(json.dumps({"browser":caps.get("browserName"),"browser_version":caps.get("browserVersion"),"chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        base=ctx["base_url"];pid=ctx["public_id"];ruta="/solicitudes/"+pid+"/factura"
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"]);driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard"
        assert driver.find_element(By.CSS_SELECTOR,".topbar-usuario-texto span").text.strip()=="Emisor"
        driver.get(base+ruta)
        accion=ruta+"/revision"
        form=wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,"form[action='"+accion+"']")))
        assert form.find_element(By.NAME,"version").get_attribute("value")=="6"
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        assert driver.find_element(By.CSS_SELECTOR,"h1 .badge").text=="v1"
        assert driver.find_element(By.CSS_SELECTOR,"dd.texto-preformateado").text==anterior["datos"]["detalle"]["concepto"]
        assert "En corrección" in driver.find_element(By.TAG_NAME,"body").text
        assert driver.save_screenshot(str(ev/"E2E-FAC-004-antes-reenviar.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==accion for e in ctx["eventos"][inicio:]))
        envios=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==accion]
        assert len(envios)==1
        e=envios[0]
        assert e["status"]==302 and e["usuario_id"]==2 and e["version_formulario"]=="6"
        assert urlsplit(e["location"]).path==ruta
        wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR,"h1 .badge"),"v2"))
        assert driver.find_element(By.CSS_SELECTOR,"h1 .badge").text=="v2"
        assert urlsplit(driver.current_url).path==ruta
        cuerpo=driver.find_element(By.TAG_NAME,"body").text
        assert "En revisión" in cuerpo and "Factura exenta (34)" in cuerpo and "459.000" in cuerpo
        assert "no se pudo avisar al Administrador" in cuerpo
        assert driver.find_element(By.CSS_SELECTOR,"dd.texto-preformateado").text==ctx["solicitud_original"]["concepto"]
        assert not driver.find_elements(By.CSS_SELECTOR,"form[action='"+accion+"']")
        assert driver.save_screenshot(str(ev/"E2E-FAC-004-v2-en-revision.png"))
        v=ctx["verificar"]()
        assert v["total_solicitudes"]==5 and v["total_auditoria"]==9 and v["total_facturas"]==2
        assert v["otras_solicitudes_sin_cambios"] and v["campos_solicitud_conservados"]
        assert v["facturas_previas_sin_cambios"] and v["auditorias_previas_sin_cambios"]
        assert v["solicitud"]["version"]==7 and v["solicitud"]["estado_nombre"]=="En revisión"
        assert v["factura_v1"]==anterior and v["factura_v1"]["estado"]=="OBSERVADA"
        assert len(v["facturas_nuevas"])==1
        f=v["factura_v2"]
        assert f is not None and f["id"]!=anterior["id"] and f["solicitud_id"]==3
        assert f["version"]==2 and f["estado"]=="EN_REVISION" and f["generada_por"]==2
        assert f["tipo_dte"]==34
        for k,n in {"monto_neto":0,"monto_exento":459000,"iva":0,"monto_total":459000}.items():
            assert Decimal(str(f[k]))==Decimal(n)
        assert f["revisada_por"] is None and f["revisada_en"] is None and f["observacion"] is None
        assert f["archivo_sii"] is None and f["archivo_sii_sha256"] is None
        datos_esperados=json.loads(json.dumps(anterior["datos"]))
        datos_esperados["detalle"]["concepto"]=ctx["solicitud_original"]["concepto"]
        assert f["datos"]==datos_esperados
        cambios={"detalle.concepto":{"anterior":anterior["datos"]["detalle"]["concepto"],"nuevo":datos_esperados["detalle"]["concepto"]}}
        assert f["cambios"]==cambios
        huella=hashlib.sha256(json.dumps(f["datos"],sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        assert f["huella"]==huella and f["huella"]!=anterior["huella"]
        assert len(v["auditorias_nuevas"])==1
        a=v["auditorias_nuevas"][0]
        assert a["accion"]=="FACTURA_GENERADA" and a["usuario_id"]==2
        assert a["detalle"]=={"solicitud_afectada_id":3,"public_id":pid,"factura_id":f["id"],
            "version_factura":2,"version_factura_anterior":1,"cambios":cambios,"totales":datos_esperados["totales"],
            "estado_anterior":"En corrección","estado_nuevo":"En revisión","version_anterior":6,"version_nueva":7}
        assert all(v["conteos"][t]==0 for t in ("registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"))
        assert ctx["intentos_smtp"]==0 and v["archivos_sii_en_carpeta_qa"]==0
        inicio=len(ctx["eventos"])
        ctx["alertas_cerradas_logout"]=cerrar_alertas_y_logout(driver,wait)
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        salidas=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]=="/auth/logout"]
        assert len(salidas)==1 and salidas[0]["status"]==302 and salidas[0]["usuario_id"] is None
        ctx["reenvio_v2_verificado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(ev/"E2E-FAC-004-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise