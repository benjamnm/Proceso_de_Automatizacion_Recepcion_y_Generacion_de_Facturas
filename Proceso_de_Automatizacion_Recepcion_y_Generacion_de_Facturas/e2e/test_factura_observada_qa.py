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


def test_administrador_devuelve_factura_a_correccion(request):
    ctx=request.config._qa_invoice_context
    evidencia=Path(ctx["evidencia"])
    driver=None;fallo=False
    try:
        opciones=webdriver.ChromeOptions();opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000);driver.set_page_load_timeout(30)
        caps=driver.capabilities
        (evidencia/"navegador.json").write_text(json.dumps({"browser":caps.get("browserName"),
            "browser_version":caps.get("browserVersion"),"chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"];pid=ctx["public_id"]
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"]);driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        identidad=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,".topbar-usuario-texto")))
        assert identidad.find_element(By.CSS_SELECTOR,"span").text.strip()=="Administrador"
        ruta="/solicitudes/"+pid+"/factura"
        driver.get(base+ruta)
        observacion=wait.until(EC.visibility_of_element_located((By.ID,"observacion")))
        form=observacion.find_element(By.XPATH,"./ancestor::form")
        accion=urlsplit(form.get_attribute("action")).path
        assert accion.startswith("/solicitudes/"+pid+"/factura/")
        assert form.find_element(By.NAME,"version").get_attribute("value")=="4"
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        texto="QA: precisar el alcance del servicio antes de aprobar."
        observacion.send_keys(texto)
        assert driver.execute_script("return arguments[0].checkValidity();",form)
        (evidencia/"observacion-enviada.json").write_text(json.dumps({"public_id":pid,"version_solicitud":4,
            "observacion":texto,"accion":accion},indent=2),encoding="utf-8")
        assert driver.save_screenshot(str(evidencia/"E2E-FAC-002-observacion-formulario.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["ruta"]==accion and e["metodo"]=="POST" for e in ctx["eventos"][inicio:]))
        envios=[e for e in ctx["eventos"][inicio:] if e["ruta"]==accion and e["metodo"]=="POST"]
        assert len(envios)==1
        e=envios[0]
        assert e["status"]==302 and e["usuario_id"]==1 and e["version_formulario"]=="4"
        assert urlsplit(e["location"]).path==ruta
        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME,"body"),"En corrección"))
        cuerpo=driver.find_element(By.TAG_NAME,"body").text
        assert texto in cuerpo and "OBSERVADA" in cuerpo
        assert driver.save_screenshot(str(evidencia/"E2E-FAC-002-devuelta-a-correccion.png"))
        v=ctx["verificar"]()
        assert v["total_solicitudes"]==5 and v["total_auditoria"]==7 and v["total_facturas"]==1
        assert v["otras_solicitudes_sin_cambios"] and v["campos_conservados"]
        assert v["auditorias_previas_sin_cambios"] and v["contenido_factura_conservado"]
        assert v["solicitud"]["version"]==5 and v["solicitud"]["estado_nombre"]=="En corrección"
        f=v["factura"]
        assert f["id"]==1 and f["solicitud_id"]==3 and f["version"]==1
        assert f["estado"]=="OBSERVADA" and f["revisada_por"]==1
        assert f["revisada_en"] is not None and f["observacion"]==texto
        assert f["archivo_sii"] is None and f["archivo_sii_sha256"] is None
        assert len(v["auditorias_nuevas"])==1
        a=v["auditorias_nuevas"][0]
        assert a["accion"]=="FACTURA_OBSERVADA" and a["usuario_id"]==1
        d=a["detalle"]
        assert d["solicitud_afectada_id"]==3 and d["public_id"]==pid
        assert d["factura_id"]==1 and d["version_factura"]==1 and d["observacion"]==texto
        assert d["estado_anterior"]=="En revisión" and d["estado_nuevo"]=="En corrección"
        assert d["version_anterior"]==4 and d["version_nueva"]==5
        assert all(v["conteos"][t]==0 for t in ("registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"))
        assert ctx["intentos_smtp"]==0 and v["archivos_sii_en_carpeta_qa"]==0
        inicio=len(ctx["eventos"])
        ctx["alertas_cerradas_logout"]=cerrar_alertas_y_logout(driver,wait)
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        salidas=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]=="/auth/logout"]
        assert len(salidas)==1 and salidas[0]["status"]==302 and salidas[0]["usuario_id"] is None
        ctx["devolucion_correccion_verificada"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-FAC-002-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise