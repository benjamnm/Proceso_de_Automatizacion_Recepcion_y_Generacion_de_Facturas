import json
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


def test_correccion_existente_factura_historica_y_logout(request):
    ctx=request.config._qa_invoice_context
    ev=Path(ctx["evidencia"])
    delta=json.loads((ev/"verificacion-delta-edicion.json").read_text(encoding="utf-8"))
    driver=None;fallo=False
    try:
        opciones=webdriver.ChromeOptions();opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000);driver.set_page_load_timeout(30)
        wait=WebDriverWait(driver,20)
        caps=driver.capabilities
        (ev/"navegador.json").write_text(json.dumps({"browser":caps.get("browserName"),"browser_version":caps.get("browserVersion")},indent=2),encoding="utf-8")
        base=ctx["base_url"];raiz="/solicitudes/"+ctx["public_id"]
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"]);driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard"
        driver.get(base+raiz+"/factura")
        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME,"body"),"En corrección"))
        assert driver.find_element(By.CSS_SELECTOR,"dd.texto-preformateado").text==delta["concepto_anterior"]
        assert "OBSERVADA" in driver.find_element(By.TAG_NAME,"body").text
        assert driver.save_screenshot(str(ev/"factura-v1-concepto-historico.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,".alert-warning a[href$='/editar']"))).click()
        concepto=wait.until(EC.visibility_of_element_located((By.ID,"concepto")))
        form=concepto.find_element(By.XPATH,"./ancestor::form")
        assert concepto.get_attribute("value")==delta["concepto_nuevo"]
        assert form.find_element(By.NAME,"version").get_attribute("value")=="6"
        assert form.find_element(By.NAME,"cliente_id").get_attribute("value")=="1"
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        original=ctx["solicitud_original"]
        assert original["concepto"]==delta["concepto_nuevo"]
        for k in ("monto_bruto","fecha_emision","tipo_afectacion","nro_orden_compra"):
            assert form.find_element(By.NAME,k).get_attribute("value")==str(original[k])
        assert driver.save_screenshot(str(ev/"solicitud-concepto-corregido-solo-lectura.png"))
        v=ctx["verificar"]()
        assert v["estado_igual_al_inicial"] is True
        assert v["total_solicitudes"]==5 and v["total_auditoria"]==8 and v["total_facturas"]==1
        assert v["solicitud"]["version"]==6 and v["solicitud"]["estado_nombre"]=="En corrección"
        assert v["facturas_previas_sin_cambios"] and v["auditorias_previas_sin_cambios"]
        assert v["otras_solicitudes_sin_cambios"] and not v["auditorias_nuevas"]
        assert v["factura"]["datos"]["detalle"]["concepto"]==delta["concepto_anterior"]
        assert ctx["intentos_smtp"]==0 and v["archivos_sii_en_carpeta_qa"]==0
        inicio=len(ctx["eventos"])
        ctx["alertas_cerradas_logout"]=cerrar_alertas_y_logout(driver,wait)
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        salidas=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]=="/auth/logout"]
        assert len(salidas)==1 and salidas[0]["status"]==302 and salidas[0]["usuario_id"] is None
        driver.get(base+"/dashboard")
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        panel=[e for e in ctx["eventos"] if e["ruta"]=="/dashboard"][-1]
        assert panel["status"]==302 and panel["usuario_id"] is None
        assert all(e["ruta"] in {"/auth/login","/auth/logout"} for e in ctx["eventos"] if e["metodo"]=="POST")
        assert ctx["verificar"]()["estado_igual_al_inicial"] is True
        ctx["verificacion_complementaria_y_logout"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(ev/"fallo-complementaria.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise