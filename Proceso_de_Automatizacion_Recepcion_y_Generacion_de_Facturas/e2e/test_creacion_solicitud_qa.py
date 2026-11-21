import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select


def test_crear_solicitud_web_persistida(request):
    """E2E-SOL-001: envio unico por formulario, fila nueva y auditoria."""
    ctx=request.config._qa_create_context
    evidencia=Path(ctx["evidencia"])
    datos=ctx["datos"]
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
        assert usuario.find_element(By.CSS_SELECTOR,"span").text.strip()=="Emisor"
        driver.get(base+"/solicitudes/nueva")
        cliente=wait.until(EC.visibility_of_element_located((By.ID,"cliente_id")))
        Select(cliente).select_by_value(str(datos["cliente_id"]))
        driver.find_element(By.ID,"concepto").send_keys(datos["concepto"])
        driver.find_element(By.ID,"monto_bruto").send_keys(datos["monto_bruto"])
        fecha=driver.find_element(By.ID,"fecha_emision")
        # Solo el control de fecha se rellena por DOM para no depender del formato regional.
        driver.execute_script("arguments[0].value=arguments[1]; arguments[0].dispatchEvent(new Event('input',{bubbles:true})); arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",fecha,datos["fecha_emision"])
        assert fecha.get_attribute("value")==datos["fecha_emision"]
        Select(driver.find_element(By.ID,"tipo_afectacion")).select_by_value(datos["tipo_afectacion"])
        driver.find_element(By.ID,"nro_orden_compra").send_keys(datos["nro_orden_compra"])
        form=cliente.find_element(By.XPATH,"./ancestor::form")
        assert form.find_element(By.CSS_SELECTOR,"input[name='csrf_token']").get_attribute("value")
        assert form.find_element(By.CSS_SELECTOR,"input[name='token_envio']").get_attribute("value")
        assert driver.execute_script("return arguments[0].checkValidity();",form)
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-001-formulario.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]=="/solicitudes/nueva" for e in ctx["eventos"][inicio:]))
        envios=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]=="/solicitudes/nueva"]
        assert len(envios)==1,"Numero inesperado de POST de creacion"
        assert envios[0]["status"]==302,"El formulario no fue aceptado; no se reintentara"
        wait.until(lambda d:re.fullmatch(r"/solicitudes/[0-9a-f]{32}",urlsplit(d.current_url).path) is not None)
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        public_id=urlsplit(driver.current_url).path.rsplit("/",1)[1]
        ctx["public_id_creado"]=public_id
        assert urlsplit(envios[0]["location"]).path=="/solicitudes/"+public_id
        assert datos["concepto"] in driver.page_source
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-001-detalle.png"))
        verificacion=ctx["verificar_persistencia"](public_id)
        assert verificacion["total_solicitudes"]==3
        assert verificacion["coincidencias_concepto"]==1
        assert verificacion["originales_sin_cambios"] is True
        fila=verificacion["solicitud"]
        assert fila["emisor_id"]==ctx["emisor_id"]
        assert fila["email_emisor"]==ctx["email"]
        assert fila["cliente_id"]==datos["cliente_id"]
        assert fila["concepto"]==datos["concepto"]
        assert fila["monto_bruto"]==datos["monto_bruto"]
        assert fila["fecha_emision"]==datos["fecha_emision"]
        assert fila["tipo_afectacion"]==datos["tipo_afectacion"]
        assert fila["nro_orden_compra"]==datos["nro_orden_compra"]
        assert fila["estado_nombre"]=="Pendiente" and fila["origen_nombre"]=="Web"
        assert fila["version"]==1
        assert fila["rut"]==ctx["cliente"]["rut"] and fila["nombre"]==ctx["cliente"]["razon_social"]
        assert fila["direccion"]==ctx["cliente"]["direccion"] and fila["giro"]==ctx["cliente"]["giro"]
        assert fila["email_contacto_receptor"]==ctx["cliente"]["email_contacto"]
        assert verificacion["clave_creacion_presente"] and verificacion["huella_creacion_presente"]
        assert len(verificacion["auditorias_creacion"])==1
        evento=verificacion["auditorias_creacion"][0]
        assert evento["usuario_id"]==ctx["emisor_id"]
        assert evento["detalle"]["public_id"]==public_id
        assert evento["detalle"]["solicitud_afectada_id"]==fila["id"]
        assert evento["detalle"]["concepto"]==datos["concepto"]
        assert all(verificacion["conteos_relacionados"][t]==0 for t in ("facturas","registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"))
        driver.get(base+"/solicitudes/")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,f"a[href='/solicitudes/{public_id}']")))
        assert datos["concepto"] in driver.page_source
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-001-listado.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["creacion_verificada"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-SOL-001-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise