import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.parametrize("monto_invalido,etiqueta",[("1.000","separador"),("-1","negativo")])
def test_bloqueo_nativo_formato_monto(request,monto_invalido,etiqueta):
    ctx=request.config._qa_native_context
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
        (evidencia/("navegador-"+etiqueta+".json")).write_text(json.dumps({"browser":caps.get("browserName"),
            "browser_version":caps.get("browserVersion"),"chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"]
        ruta="/solicitudes/"+ctx["public_id"]+"/editar"
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
        assert driver.execute_script("return arguments[0].checkValidity();",form) is True
        boton=form.find_element(By.CSS_SELECTOR,"button[type='submit']")
        assert boton.is_enabled() and boton.is_displayed()
        monto.clear();monto.send_keys(monto_invalido)
        assert {k:form.find_element(By.NAME,k).get_attribute("value") for k in campos}==dict(originales,monto_bruto=monto_invalido)
        validez=driver.execute_script("return {pattern:arguments[0].pattern,patternMismatch:arguments[0].validity.patternMismatch,valid:arguments[0].validity.valid,validationMessage:arguments[0].validationMessage};",monto)
        assert validez["patternMismatch"] is True and validez["valid"] is False
        assert validez["validationMessage"]
        assert driver.execute_script("return arguments[0].checkValidity();",form) is False
        inicio=len(ctx["eventos"])
        boton.click()
        hubo_post=False
        try:
            WebDriverWait(driver,2,poll_frequency=0.1).until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==ruta for e in ctx["eventos"][inicio:]))
            hubo_post=True
        except TimeoutException:
            pass
        assert hubo_post is False,"El formulario invalido llego al servidor; bloqueo nativo no demostrado"
        assert urlsplit(driver.current_url).path==ruta
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        assert monto.get_attribute("value")==monto_invalido
        assert driver.save_screenshot(str(evidencia/("E2E-SOL-006-"+etiqueta+"-invalido.png")))
        v=ctx["verificar"]()
        assert v["estado_comparado_sin_cambios"] and v["version"]==3
        assert v["total_solicitudes"]==3 and v["total_auditoria"]==3
        comprobacion={"etiqueta":etiqueta,"monto_intentado":monto_invalido,"validez_nativa":validez,
            "ventana_observacion_sin_post_segundos":2,"post_edicion_observados":0,
            "estado_comparado_sin_cambios":v["estado_comparado_sin_cambios"],
            "limitacion":"Valida bloqueo del navegador; no rechazo de este formato en backend"}
        (evidencia/("verificacion-"+etiqueta+".json")).write_text(json.dumps(comprobacion,indent=2,ensure_ascii=True),encoding="utf-8")
        monto.clear();monto.send_keys(originales["monto_bruto"])
        assert driver.execute_script("return arguments[0].checkValidity();",form) is True
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx.setdefault("patrones_completados",[]).append(etiqueta)
        ctx["aviso_verificado"]=True
        ctx["patron_nativo_verificado"]=True
        ctx["bloqueo_nativo_verificado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/("E2E-SOL-006-"+etiqueta+"-fallo.png")))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise