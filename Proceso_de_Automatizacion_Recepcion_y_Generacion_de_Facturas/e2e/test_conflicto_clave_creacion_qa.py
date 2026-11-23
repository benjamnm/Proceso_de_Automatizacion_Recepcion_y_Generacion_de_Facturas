import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select


def test_misma_clave_datos_distintos_rechazados(request):
    ctx=request.config._qa_keyconflict_context
    evidencia=Path(ctx["evidencia"])
    driver=None;payload=None;alterado=None;fallo=False
    try:
        opciones=webdriver.ChromeOptions()
        opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000)
        driver.set_page_load_timeout(30);driver.set_script_timeout(30)
        caps=driver.capabilities
        (evidencia/"navegador.json").write_text(json.dumps({"browser":caps.get("browserName"),
            "browser_version":caps.get("browserVersion"),"chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"]
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"])
        driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        driver.get(base+"/solicitudes/nueva")
        cliente=wait.until(EC.visibility_of_element_located((By.ID,"cliente_id")))
        datos=ctx["datos_creacion"]
        Select(cliente).select_by_value(str(datos["cliente_id"]))
        driver.find_element(By.ID,"concepto").send_keys(datos["concepto"])
        driver.find_element(By.ID,"monto_bruto").send_keys(datos["monto_bruto"])
        fecha=driver.find_element(By.ID,"fecha_emision")
        driver.execute_script("arguments[0].value=arguments[1];arguments[0].dispatchEvent(new Event('input',{bubbles:true}));arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",fecha,datos["fecha_emision"])
        Select(driver.find_element(By.ID,"tipo_afectacion")).select_by_value(datos["tipo_afectacion"])
        driver.find_element(By.ID,"nro_orden_compra").send_keys(datos["nro_orden_compra"])
        form=cliente.find_element(By.XPATH,"./ancestor::form")
        assert driver.execute_script("return arguments[0].checkValidity();",form)
        payload=driver.execute_script("return Object.fromEntries(Array.from(new FormData(arguments[0]).entries()).filter(([k,v])=>typeof v==='string'));",form)
        assert payload.get("csrf_token") and payload.get("token_envio")
        assert all(payload[k]==str(datos[k]) for k in datos)
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-009-formulario-inicial.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:re.fullmatch(r"/solicitudes/[0-9a-f]{32}",urlsplit(d.current_url).path) is not None)
        pid=urlsplit(driver.current_url).path.rsplit("/",1)[1]
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        ctx["public_id_nuevo"]=pid
        eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]=="/solicitudes/nueva"]
        assert len(eventos)==1 and eventos[0]["status"]==302 and eventos[0]["usuario_id"]==2
        assert urlsplit(eventos[0]["location"]).path=="/solicitudes/"+pid
        assert eventos[0]["campos_recibidos"]=={k:str(v) for k,v in datos.items()}
        primero=ctx["verificar_creacion"](pid,"primer_alta")
        assert primero["total_solicitudes"]==5 and primero["total_auditoria"]==5
        assert primero["originales_sin_cambios"] and primero["auditorias_previas_sin_cambios"]
        assert primero["coincidencias_concepto"]==1
        fila=primero["solicitud_nueva"]
        assert fila["version"]==1 and fila["emisor_id"]==2
        assert fila["estado_nombre"]=="Pendiente" and fila["origen_nombre"]=="Web"
        assert all(str(fila[k])==str(v) for k,v in datos.items())
        assert len(primero["auditorias_nuevas"])==1
        evento=primero["auditorias_nuevas"][0]
        assert evento["accion"]=="SOLICITUD_CREADA" and evento["usuario_id"]==2
        assert evento["detalle"]["public_id"]==pid and evento["detalle"]["solicitud_afectada_id"]==fila["id"]
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-009-primera-creacion.png"))
        ctx["creacion_web_verificada"]=True
        alterado=dict(payload,concepto=datos["concepto"]+"-ALTERADO",monto_bruto="999000")
        assert {k for k in payload if payload[k]!=alterado[k]}=={"concepto","monto_bruto"}
        assert alterado["token_envio"]==payload["token_envio"] and alterado["csrf_token"]==payload["csrf_token"]
        (evidencia/"datos-intento-alterado.json").write_text(json.dumps({k:alterado[k] for k in datos},indent=2),encoding="utf-8")
        inicio=len(ctx["eventos"])
        respuesta=driver.execute_async_script(r"""
            const [url,data,done]=arguments;
            fetch(url,{method:'POST',credentials:'same-origin',
              headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data)})
            .then(async r=>{
                const doc=new DOMParser().parseFromString(await r.text(),'text/html');
                const aviso=doc.querySelector('.alert-danger');
                const token=doc.querySelector('input[name="token_envio"]');
                done({status:r.status,ruta_final:new URL(r.url).pathname,redirected:r.redirected,
                  error:(aviso?.textContent||'').replace(/\s+/g,' ').trim(),
                  concepto_respuesta:doc.getElementById('concepto')?.value,
                  monto_respuesta:doc.getElementById('monto_bruto')?.value,
                  mismo_token_creacion:token?.value===data.token_envio});
            }).catch(()=>done({error_transporte:'REENVIO_NO_COMPLETADO'}));
        """,base+"/solicitudes/nueva",alterado)
        payload=None;alterado=None
        (evidencia/"respuesta-reenvio-alterado.json").write_text(json.dumps(respuesta,indent=2),encoding="utf-8")
        assert "error_transporte" not in respuesta
        assert respuesta["status"]==200 and respuesta["redirected"] is False
        assert respuesta["ruta_final"]=="/solicitudes/nueva"
        assert "Este formulario ya se utilizó con otros datos. Abra una solicitud nueva." in respuesta["error"]
        assert respuesta["concepto_respuesta"]==datos["concepto"]+"-ALTERADO"
        assert respuesta["monto_respuesta"]=="999000" and respuesta["mismo_token_creacion"] is True
        eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]=="/solicitudes/nueva"]
        assert len(eventos)==1 and eventos[0]["status"]==200 and eventos[0]["location"] is None
        assert eventos[0]["usuario_id"]==2
        esperado={k:str(v) for k,v in datos.items()}
        esperado.update(concepto=datos["concepto"]+"-ALTERADO",monto_bruto="999000")
        assert eventos[0]["campos_recibidos"]==esperado
        final=ctx["verificar_creacion"](pid,"tras_reenvio_alterado")
        assert final["total_solicitudes"]==5 and final["total_auditoria"]==5
        assert final["igual_al_primer_alta"] is True and final["coincidencias_concepto"]==1
        assert final["solicitud_nueva"]["version"]==1
        driver.get(base+"/solicitudes/"+pid)
        assert datos["concepto"] in driver.page_source
        assert datos["concepto"]+"-ALTERADO" not in driver.page_source
        assert driver.save_screenshot(str(evidencia/"E2E-SOL-009-detalle-conservado.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["etapas_completadas"]=["creacion","rechazo_datos_distintos"]
        ctx["persistencia_creacion_verificada"]=True
        ctx["conflicto_clave_verificado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-SOL-009-fallo.png"))
            except Exception:pass
        raise
    finally:
        payload=None;alterado=None
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise