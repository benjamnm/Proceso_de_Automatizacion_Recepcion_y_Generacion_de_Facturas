import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select


def test_editar_solicitud_propia_persistida(request):
    """E2E-SOL-002: edicion propia unica, version, auditoria y datos inmutables."""
    ctx=request.config._qa_edit_context
    evidencia=Path(ctx["evidencia"])
    antes=ctx["antes"]
    nuevo=ctx["datos_nuevos"]
    pid=ctx["public_id"]
    driver=None
    fallo=False
    try:
        opciones=webdriver.ChromeOptions()
        opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000)
        driver.set_page_load_timeout(30)
        caps=driver.capabilities
        (evidencia/"navegador.json").write_text(json.dumps({
            "browser":caps.get("browserName"),"browser_version":caps.get("browserVersion"),
            "chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"]
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"])
        driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        usuario=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,".topbar-usuario-texto")))
        assert "Emisor Sintetico QA" in usuario.text
        driver.get(base+"/solicitudes/"+pid+"/editar")
        concepto=wait.until(EC.visibility_of_element_located((By.ID,"concepto")))
        form=concepto.find_element(By.XPATH,"./ancestor::form")
        assert form.find_element(By.CSS_SELECTOR,"input[name='version']").get_attribute("value")=="1"
        assert form.find_element(By.CSS_SELECTOR,"input[name='cliente_id']").get_attribute("value")==str(antes["cliente_id"])
        assert form.find_element(By.CSS_SELECTOR,"input[name='csrf_token']").get_attribute("value")
        assert concepto.get_attribute("value")==antes["concepto"]
        assert driver.find_element(By.ID,"monto_bruto").get_attribute("value")==antes["monto_bruto"]
        assert driver.find_element(By.ID,"fecha_emision").get_attribute("value")==antes["fecha_emision"]
        assert Select(driver.find_element(By.ID,"tipo_afectacion")).first_selected_option.get_attribute("value")==antes["tipo_afectacion"]
        assert driver.find_element(By.ID,"nro_orden_compra").get_attribute("value")==antes["nro_orden_compra"]
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-002-formulario-antes.png"))
        concepto.clear();concepto.send_keys(nuevo["concepto"])
        monto=driver.find_element(By.ID,"monto_bruto");monto.clear();monto.send_keys(nuevo["monto_bruto"])
        Select(driver.find_element(By.ID,"tipo_afectacion")).select_by_value(nuevo["tipo_afectacion"])
        oc=driver.find_element(By.ID,"nro_orden_compra");oc.clear();oc.send_keys(nuevo["nro_orden_compra"])
        assert driver.find_element(By.ID,"fecha_emision").get_attribute("value")==antes["fecha_emision"]
        assert driver.execute_script("return arguments[0].checkValidity();",form)
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-002-formulario-modificado.png"))
        inicio=len(ctx["eventos"])
        ruta="/solicitudes/"+pid+"/editar"
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==ruta for e in ctx["eventos"][inicio:]))
        envios=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==ruta]
        assert len(envios)==1,"Numero inesperado de POST de edicion"
        assert envios[0]["status"]==302,"La edicion no fue aceptada; no se reintentara"
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        wait.until(lambda d:urlsplit(d.current_url).path!=ruta)
        driver.get(base+"/solicitudes/"+pid)
        wait.until(EC.presence_of_element_located((By.TAG_NAME,"body")))
        assert nuevo["concepto"] in driver.page_source
        assert antes["concepto"] not in driver.page_source
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-002-detalle-despues.png"))
        v=ctx["verificar_persistencia"]()
        assert v["total_solicitudes"]==3
        assert v["solicitudes_aisladas_sin_cambios"] is True
        assert v["campos_inmutables_sin_cambios"] is True
        f=v["solicitud"]
        assert f["id"]==antes["id"] and f["public_id"]==pid and f["emisor_id"]==ctx["emisor_id"]
        assert f["concepto"]==nuevo["concepto"] and f["monto_bruto"]==nuevo["monto_bruto"]
        assert f["tipo_afectacion"]==nuevo["tipo_afectacion"] and f["nro_orden_compra"]==nuevo["nro_orden_compra"]
        assert f["fecha_emision"]==antes["fecha_emision"]
        assert f["version"]==2 and f["estado_nombre"]=="Pendiente" and f["origen_nombre"]=="Web"
        assert v["total_auditoria"]==2 and v["auditoria_creacion_sin_cambios"] is True
        assert len(v["auditorias_edicion"])==1
        e=v["auditorias_edicion"][0]
        assert e["usuario_id"]==ctx["emisor_id"]
        d=e["detalle"]
        assert d["solicitud_afectada_id"]==antes["id"] and d["public_id"]==pid
        assert d["estado"]=="Pendiente" and d["version_anterior"]==1 and d["version_nueva"]==2
        esperado={"concepto":{"anterior":antes["concepto"],"nuevo":nuevo["concepto"]},
            "nro_orden_compra":{"anterior":antes["nro_orden_compra"],"nuevo":nuevo["nro_orden_compra"]},
            "monto_bruto":{"anterior":antes["monto_bruto"],"nuevo":nuevo["monto_bruto"]},
            "tipo_afectacion":{"anterior":antes["tipo_afectacion"],"nuevo":nuevo["tipo_afectacion"]}}
        assert d["cambios"]==esperado
        assert all(v["conteos_relacionados"][t]==0 for t in ("facturas","registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["edicion_verificada"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-SOL-002-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise