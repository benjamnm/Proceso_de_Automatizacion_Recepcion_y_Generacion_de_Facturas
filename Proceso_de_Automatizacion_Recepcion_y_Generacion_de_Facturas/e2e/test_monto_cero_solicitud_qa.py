import json
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_rechazar_monto_cero_sin_alterar_solicitud(request):
    ctx=request.config._qa_zero_context
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
        monto=wait.until(EC.visibility_of_element_located((By.ID,"monto_bruto")))
        form=monto.find_element(By.XPATH,"./ancestor::form")
        campos=("cliente_id","concepto","monto_bruto","fecha_emision","tipo_afectacion","nro_orden_compra","version")
        originales={k:form.find_element(By.NAME,k).get_attribute("value") for k in campos}
        assert originales=={k:str(ctx["solicitud"][k]) for k in campos}
        assert originales["version"]=="3" and originales["monto_bruto"]=="459000"
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-005-formulario-antes.png"))
        monto.clear();monto.send_keys("0")
        enviados={k:form.find_element(By.NAME,k).get_attribute("value") for k in campos}
        assert enviados==dict(originales,monto_bruto="0")
        nativa=driver.execute_script("return arguments[0].checkValidity();",form)
        assert nativa is True,"El navegador bloquea el formulario: aun no se probo el rechazo del servidor"
        (evidencia/"datos-intento.json").write_text(json.dumps({"antes":originales,"intento":enviados,
            "validacion_nativa_permite_envio":nativa},indent=2),encoding="utf-8")
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-005-intento-monto-cero.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==ruta for e in ctx["eventos"][inicio:]))
        eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==ruta]
        assert len(eventos)==1
        e=eventos[0]
        assert e["status"]==200 and e["location"] is None
        assert e["usuario_id"]==2 and e["version_formulario"]=="3"
        assert e["campos_recibidos"]=={k:enviados[k] for k in campos if k!="version"}
        assert urlsplit(driver.current_url).path==ruta
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        mensaje="El monto debe ser mayor que cero."
        alerta=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,".alert-danger")))
        assert mensaje in alerta.text
        campo=driver.find_element(By.ID,"monto_bruto")
        assert campo.get_attribute("value")=="0"
        assert campo.get_attribute("aria-invalid")=="true"
        assert "is-invalid" in campo.get_attribute("class").split()
        ids=(campo.get_attribute("aria-describedby") or "").split()
        assert any(mensaje in elemento.text for i in ids for elemento in driver.find_elements(By.ID,i))
        ctx["aviso_verificado"]=True
        ctx["error_monto_verificado"]=True
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-005-error-servidor.png"))
        v=ctx["verificar"]()
        assert v["solicitudes_sin_cambios"] and v["auditoria_sin_cambios"]
        assert v["conteos_relacionados_sin_cambios"] and v["estado_comparado_sin_cambios"]
        assert v["total_solicitudes"]==3 and v["total_auditoria"]==3 and v["version"]==3
        assert v["solicitud"]["monto_bruto"]=="459000"
        driver.get(base+ruta)
        wait.until(EC.visibility_of_element_located((By.ID,"monto_bruto")))
        assert driver.find_element(By.ID,"monto_bruto").get_attribute("value")=="459000"
        assert driver.find_element(By.NAME,"version").get_attribute("value")=="3"
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-005-recarga-monto-original.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["monto_cero_rechazado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-SOL-005-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise