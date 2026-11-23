import json
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_rechazar_formulario_desactualizado(request):
    ctx=request.config._qa_stale_context
    evidencia=Path(ctx["evidencia"])
    driver=None
    fallo=False
    try:
        opciones=webdriver.ChromeOptions()
        opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000)
        driver.set_page_load_timeout(30)
        caps=driver.capabilities
        (evidencia/"navegador.json").write_text(json.dumps({"browser":caps.get("browserName"),
            "browser_version":caps.get("browserVersion"),"chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"]
        ruta="/solicitudes/"+ctx["public_id"]+"/editar"
        detalle="/solicitudes/"+ctx["public_id"]
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"])
        driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        driver.get(base+ruta)
        primera=driver.current_window_handle
        wait.until(EC.visibility_of_element_located((By.ID,"concepto")))
        assert driver.find_element(By.NAME,"version").get_attribute("value")=="2"
        assert driver.find_element(By.ID,"concepto").get_attribute("value")==ctx["original"]["concepto"]
        driver.switch_to.new_window("tab")
        segunda=driver.current_window_handle
        driver.get(base+ruta)
        wait.until(EC.visibility_of_element_located((By.ID,"concepto")))
        assert driver.find_element(By.NAME,"version").get_attribute("value")=="2"
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-003-segunda-abierta-v2.png"))

        def rellenar(datos):
            for nombre in ("concepto","monto_bruto"):
                elemento=driver.find_element(By.ID,nombre)
                elemento.clear();elemento.send_keys(datos[nombre])
            form=driver.find_element(By.ID,"concepto").find_element(By.XPATH,"./ancestor::form")
            assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
            assert driver.execute_script("return arguments[0].checkValidity();",form)
            return form

        def enviar(form,esperado):
            inicio=len(ctx["eventos"])
            form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
            wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==ruta for e in ctx["eventos"][inicio:]))
            eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==ruta]
            assert len(eventos)==1
            assert eventos[0]["status"]==esperado,"Respuesta HTTP inesperada"
            assert eventos[0]["version_formulario"]=="2"
            assert eventos[0]["usuario_id"]==ctx["emisor_id"]

        driver.switch_to.window(primera)
        enviar(rellenar(ctx["aceptado"]),302)
        wait.until(lambda d:urlsplit(d.current_url).path==detalle)
        assert ctx["aceptado"]["concepto"] in driver.page_source
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-003-primer-guardado.png"))
        v=ctx["verificar"]("aceptado")
        assert v["total_solicitudes"]==3 and v["total_auditoria"]==3
        assert v["originales_sin_cambios"] and v["inmutables_sin_cambios"] and v["auditorias_previas_sin_cambios"]
        assert v["solicitud"]["version"]==3
        assert v["solicitud"]["concepto"]==ctx["aceptado"]["concepto"]
        assert v["solicitud"]["monto_bruto"]==ctx["aceptado"]["monto_bruto"]
        assert len(v["auditorias_nuevas"])==1
        evento=v["auditorias_nuevas"][0]
        assert evento["accion"]=="SOLICITUD_EDITADA" and evento["usuario_id"]==ctx["emisor_id"]
        d=evento["detalle"]
        assert d["public_id"]==ctx["public_id"] and d["solicitud_afectada_id"]==3
        assert d["version_anterior"]==2 and d["version_nueva"]==3
        assert d["cambios"]=={k:{"anterior":ctx["original"][k],"nuevo":ctx["aceptado"][k]} for k in ("concepto","monto_bruto")}

        driver.switch_to.window(segunda)
        assert driver.find_element(By.NAME,"version").get_attribute("value")=="2"
        form=rellenar(ctx["obsoleto"])
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-003-intento-obsoleto.png"))
        enviar(form,200)
        assert urlsplit(driver.current_url).path==ruta
        aviso=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,".alert-danger")))
        assert "La solicitud cambió desde que abrió el formulario." in aviso.text
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-003-conflicto-visible.png"))
        final=ctx["verificar"]("tras_obsoleto")
        assert final["sin_cambios_desde_aceptado"] is True,"El formulario obsoleto altero datos o auditoria"
        assert final["solicitud"]["version"]==3
        assert final["solicitud"]["concepto"]==ctx["aceptado"]["concepto"]
        assert final["solicitud"]["monto_bruto"]==ctx["aceptado"]["monto_bruto"]
        assert final["total_auditoria"]==3
        driver.get(base+detalle)
        assert ctx["aceptado"]["concepto"] in driver.page_source
        assert ctx["obsoleto"]["concepto"] not in driver.page_source
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-003-detalle-final.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["conflicto_verificado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-SOL-003-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise