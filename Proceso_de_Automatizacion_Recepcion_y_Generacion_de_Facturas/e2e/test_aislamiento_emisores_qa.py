import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.parametrize("etiqueta", ["A", "B"])
def test_aislamiento_entre_emisores(request, etiqueta):
    """E2E-HORIZ-001/002: control positivo propio, GET/POST ajenos y no mutacion."""
    ctx=request.config._qa_horizontal_context
    evidencia=Path(ctx["evidencia"])
    propia=ctx["solicitudes"][etiqueta]
    ajena=ctx["solicitudes"]["B" if etiqueta=="A" else "A"]
    cuenta=ctx["cuentas"][etiqueta]
    base=ctx["base_url"]
    driver=None
    fallo=False
    try:
        opciones=webdriver.ChromeOptions()
        opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000)
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        caps=driver.capabilities
        (evidencia/f"navegador-{etiqueta}.json").write_text(json.dumps({
            "browser":caps.get("browserName"),"browser_version":caps.get("browserVersion"),
            "chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)

        def abrir(ruta,esperado):
            inicio=len(ctx["eventos"])
            driver.get(base+ruta)
            wait.until(lambda d:any(e["metodo"]=="GET" and e["ruta"]==ruta
                                    for e in ctx["eventos"][inicio:]))
            eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="GET" and e["ruta"]==ruta]
            assert len(eventos)==1
            assert eventos[0]["status"]==esperado,"HTTP inesperado"
            assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
            if esperado!=302:
                assert urlsplit(driver.current_url).path==ruta
                assert eventos[0]["usuario_id"]==cuenta["id"]
            ctx["verificaciones"].append({"emisor":etiqueta,"metodo":"GET","ruta":ruta,"http":eventos[0]["status"]})

        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(cuenta["email"])
        driver.find_element(By.ID,"password").send_keys(cuenta["password"])
        antes=len(ctx["eventos"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        login=[e for e in ctx["eventos"][antes:] if e["metodo"]=="POST" and e["ruta"]=="/auth/login"]
        assert len(login)==1 and login[0]["status"]==302 and login[0]["usuario_id"]==cuenta["id"]
        usuario=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,".topbar-usuario-texto")))
        assert cuenta["nombre"] in usuario.text
        assert usuario.find_element(By.CSS_SELECTOR,"span").text.strip()=="Emisor"

        abrir("/solicitudes/",200)
        assert propia["concepto"] in driver.find_element(By.TAG_NAME,"body").text
        assert ajena["concepto"] not in driver.page_source
        assert ajena["public_id"] not in driver.page_source
        assert driver.find_elements(By.CSS_SELECTOR,f"a[href='/solicitudes/{propia['public_id']}']")
        assert driver.save_screenshot(str(evidencia/f"emisor-{etiqueta}-listado-propio.png"))

        ruta_propia="/solicitudes/"+propia["public_id"]
        ruta_ajena="/solicitudes/"+ajena["public_id"]
        abrir(ruta_propia,200)
        assert propia["concepto"] in driver.page_source
        abrir(ruta_propia+"/editar",200)
        campo=driver.find_element(By.NAME,"concepto")
        assert campo.get_attribute("value")==propia["concepto"]

        abrir(ruta_ajena,404)
        assert ajena["concepto"] not in driver.page_source
        assert driver.save_screenshot(str(evidencia/f"emisor-{etiqueta}-detalle-ajeno-denegado.png"))
        abrir(ruta_ajena+"/editar",404)
        assert ajena["concepto"] not in driver.page_source

        # Token valido de la misma sesion: el rechazo no debe deberse a CSRF ausente.
        abrir(ruta_propia+"/editar",200)
        token=driver.find_element(By.CSS_SELECTOR,"input[name='csrf_token']").get_attribute("value")
        assert token
        carga={"csrf_token":token,"version":str(ajena["version"]),
            "cliente_id":str(ajena["cliente_id"]),"concepto":"QA-INTENTO-AJENO-"+etiqueta,
            "monto_bruto":str(ajena["monto_bruto"]),"fecha_emision":ajena["fecha_emision"],
            "tipo_afectacion":ajena["tipo_afectacion"],"nro_orden_compra":ajena["nro_orden_compra"] or ""}
        inicio=len(ctx["eventos"])
        respuesta=driver.execute_async_script("""
            const [url, data, marker, done] = arguments;
            fetch(url, {method:'POST',credentials:'same-origin',
                headers:{'Content-Type':'application/x-www-form-urlencoded'},
                body:new URLSearchParams(data)}).then(async r => {
                    const text=await r.text();
                    done({status:r.status,ruta_final:new URL(r.url).pathname,
                          expone_concepto_ajeno:text.includes(marker)});
                }).catch(() => done({error:'FETCH_NO_COMPLETADO'}));
        """,base+ruta_ajena+"/editar",carga,ajena["concepto"])
        del carga,token
        assert "error" not in respuesta
        assert respuesta["status"]==404,"POST ajeno no fue rechazado como se esperaba"
        assert respuesta["ruta_final"]==ruta_ajena+"/editar"
        assert respuesta["expone_concepto_ajeno"] is False
        eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==ruta_ajena+"/editar"]
        assert len(eventos)==1 and eventos[0]["status"]==404
        assert eventos[0]["usuario_id"]==cuenta["id"]
        ctx["verificaciones"].append({"emisor":etiqueta,"metodo":"POST","ruta":ruta_ajena+"/editar","http":respuesta["status"],"csrf_valido_de_sesion":True})
        assert ctx["solicitudes_sin_cambios"](),"Se modificaron solicitudes; conservar evidencia sin restaurar"
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        abrir("/dashboard",302)
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["emisores_completados"].append(etiqueta)
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):
                    campo.clear()
                driver.save_screenshot(str(evidencia/f"emisor-{etiqueta}-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                ctx["errores_cierre"].append({"emisor":etiqueta,"tipo":type(exc).__name__})
                if not fallo:
                    raise