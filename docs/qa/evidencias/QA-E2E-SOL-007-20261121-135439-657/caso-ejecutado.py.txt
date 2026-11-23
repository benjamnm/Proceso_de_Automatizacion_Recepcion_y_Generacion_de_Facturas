import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.parametrize("monto_invalido,etiqueta",[("1.000","separador"),("-1","negativo")])
def test_backend_rechaza_formato_monto(request,monto_invalido,etiqueta):
    ctx=request.config._qa_backendformat_context
    evidencia=Path(ctx["evidencia"])
    driver=None
    fallo=False
    try:
        opciones=webdriver.ChromeOptions()
        opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000)
        driver.set_page_load_timeout(30);driver.set_script_timeout(30)
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
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        assert driver.save_screenshot(str(evidencia/("E2E-SOL-007-"+etiqueta+"-formulario-origen.png")))
        inicio=len(ctx["eventos"])
        respuesta=driver.execute_async_script(r"""
            const [form, monto, done] = arguments;
            const data=new FormData(form);
            data.set('monto_bruto', monto);
            fetch(form.action,{method:'POST',credentials:'same-origin',body:data})
              .then(async r=>{
                const html=await r.text();
                const doc=new DOMParser().parseFromString(html,'text/html');
                const campo=doc.getElementById('monto_bruto');
                const alerta=doc.querySelector('.alert-danger');
                const ids=campo ? (campo.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean) : [];
                const normalize=t=>(t||'').replace(/\s+/g,' ').trim();
                done({status:r.status,ruta_final:new URL(r.url).pathname,redirected:r.redirected,
                  alerta:normalize(alerta ? alerta.textContent : ''),
                  monto_respuesta:campo ? campo.value : null,
                  aria_invalid:campo ? campo.getAttribute('aria-invalid') : null,
                  clase_invalida:campo ? campo.classList.contains('is-invalid') : false,
                  descripcion:ids.map(id=>normalize(doc.getElementById(id)?.textContent)).join(' ')});
              }).catch(()=>done({error:'FETCH_O_LECTURA_NO_COMPLETADOS'}));
        """,form,monto_invalido)
        (evidencia/("respuesta-servidor-"+etiqueta+".json")).write_text(json.dumps(respuesta,indent=2,ensure_ascii=True),encoding="utf-8")
        assert "error" not in respuesta
        assert respuesta["status"]==200 and respuesta["ruta_final"]==ruta and respuesta["redirected"] is False
        eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==ruta]
        assert len(eventos)==1
        e=eventos[0]
        assert e["status"]==200 and e["location"] is None
        assert e["usuario_id"]==2 and e["version_formulario"]=="3"
        enviados=dict(originales,monto_bruto=monto_invalido)
        assert e["campos_recibidos"]=={k:enviados[k] for k in campos if k!="version"}
        mensaje="Ingrese un monto entero de hasta 14 dígitos, sin puntos ni comas."
        assert mensaje in respuesta["alerta"]
        assert mensaje in respuesta["descripcion"]
        assert respuesta["monto_respuesta"]==monto_invalido
        assert respuesta["aria_invalid"]=="true" and respuesta["clase_invalida"] is True
        v=ctx["verificar"]()
        assert v["estado_comparado_sin_cambios"] and v["version"]==3
        assert v["total_solicitudes"]==3 and v["total_auditoria"]==3
        assert v["solicitud"]["monto_bruto"]=="459000"
        (evidencia/("verificacion-"+etiqueta+".json")).write_text(json.dumps({"monto_enviado":monto_invalido,
            "post_edicion_observados":1,"validacion":"servidor; POST desde navegador con sesion y CSRF originales",
            "estado_comparado_sin_cambios":True,"version":3,"monto_persistido":"459000"},indent=2),encoding="utf-8")
        driver.get(base+ruta)
        wait.until(EC.visibility_of_element_located((By.ID,"monto_bruto")))
        assert driver.find_element(By.ID,"monto_bruto").get_attribute("value")=="459000"
        assert driver.find_element(By.NAME,"version").get_attribute("value")=="3"
        assert driver.save_screenshot(str(evidencia/("E2E-SOL-007-"+etiqueta+"-recarga-persistida.png")))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,"form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx.setdefault("formatos_backend_completados",[]).append(etiqueta)
        ctx["respuesta_error_verificada"]=True
        ctx["error_formato_backend_verificado"]=True
        ctx["rechazo_backend_verificado"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/("E2E-SOL-007-"+etiqueta+"-fallo.png")))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise