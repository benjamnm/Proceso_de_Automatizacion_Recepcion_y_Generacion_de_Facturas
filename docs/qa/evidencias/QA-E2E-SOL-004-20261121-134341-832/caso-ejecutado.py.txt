import json
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_guardar_solicitud_sin_cambios(request):
    ctx=request.config._qa_nochange_context
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
        detalle="/solicitudes/"+ctx["public_id"]
        ruta=detalle+"/editar"
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"])
        driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        driver.get(base+ruta)
        concepto=wait.until(EC.visibility_of_element_located((By.ID,"concepto")))
        form=concepto.find_element(By.XPATH,"./ancestor::form")
        campos=("cliente_id","concepto","monto_bruto","fecha_emision","tipo_afectacion","nro_orden_compra","version")
        valores={k:form.find_element(By.NAME,k).get_attribute("value") for k in campos}
        esperados={k:str(ctx["solicitud"][k]) for k in campos}
        assert valores==esperados,"El formulario no refleja los datos persistidos"
        assert valores["version"]=="3"
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        assert driver.execute_script("return arguments[0].checkValidity();",form)
        (evidencia/"valores-formulario.json").write_text(json.dumps(valores,indent=2),encoding="utf-8")
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-004-formulario-sin-modificar.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==ruta for e in ctx["eventos"][inicio:]))
        envios=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==ruta]
        assert len(envios)==1
        envio=envios[0]
        assert envio["status"]==302 and envio["usuario_id"]==2 and envio["version_formulario"]=="3"
        assert urlsplit(envio["location"]).path==detalle
        assert envio["campos_recibidos"]=={k:valores[k] for k in campos if k!="version"}
        wait.until(lambda d:urlsplit(d.current_url).path==detalle)
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        aviso=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,".alert-info")))
        assert "No había cambios para guardar." in aviso.text
        ctx["aviso_verificado"]=True
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-004-aviso-sin-cambios.png"))
        verificacion=ctx["verificar"]()
        assert verificacion["solicitudes_sin_cambios"] is True
        assert verificacion["auditoria_sin_cambios"] is True
        assert verificacion["conteos_relacionados_sin_cambios"] is True
        assert verificacion["total_solicitudes"]==3 and verificacion["total_auditoria"]==3
        assert verificacion["version"]==3
        driver.get(base+ruta)
        wait.until(EC.visibility_of_element_located((By.ID,"concepto")))
        assert driver.find_element(By.NAME,"version").get_attribute("value")=="3"
        assert driver.find_element(By.ID,"concepto").get_attribute("value")==valores["concepto"]
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-004-formulario-recargado-v3.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["guardado_sin_cambios_verificado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-SOL-004-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise