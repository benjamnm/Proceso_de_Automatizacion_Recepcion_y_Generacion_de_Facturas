import hashlib
import json
from decimal import Decimal
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


def test_generar_factura_exenta_y_enviar_revision(request):
    ctx=request.config._qa_invoice_context
    evidencia=Path(ctx["evidencia"])
    driver=None;fallo=False
    try:
        opciones=webdriver.ChromeOptions()
        opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000);driver.set_page_load_timeout(30)
        caps=driver.capabilities
        (evidencia/"navegador.json").write_text(json.dumps({"browser":caps.get("browserName"),
            "browser_version":caps.get("browserVersion"),"chromedriver_version":caps.get("chrome",{}).get("chromedriverVersion")},indent=2),encoding="utf-8")
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"];pid=ctx["public_id"]
        ruta="/solicitudes/"+pid+"/factura"
        accion=ruta+"/revision"
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"])
        driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard","Login no alcanzo panel; no se reintenta"
        driver.get(base+ruta)
        form=wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,"form[action='"+accion+"']")))
        assert form.find_element(By.NAME,"version").get_attribute("value")=="3"
        assert form.find_element(By.NAME,"csrf_token").get_attribute("value")
        assert "Aún no se ha generado una versión de factura" in driver.find_element(By.TAG_NAME,"body").text
        assert driver.save_screenshot(str(evidencia/"E2E-FAC-001-antes-generar.png"))
        inicio=len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:any(e["metodo"]=="POST" and e["ruta"]==accion for e in ctx["eventos"][inicio:]))
        eventos=[e for e in ctx["eventos"][inicio:] if e["metodo"]=="POST" and e["ruta"]==accion]
        assert len(eventos)==1
        e=eventos[0]
        assert e["status"]==302 and e["usuario_id"]==2 and e["version_formulario"]=="3"
        assert urlsplit(e["location"]).path==ruta
        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME,"body"),"Factura exenta (34)"))
        assert urlsplit(driver.current_url).path==ruta
        assert urlsplit(driver.current_url).netloc==urlsplit(base).netloc
        cuerpo=driver.find_element(By.TAG_NAME,"body").text
        assert "Factura versión 1 generada y enviada a revisión." in cuerpo
        assert "En revisión" in cuerpo and "459.000" in cuerpo
        assert ctx["solicitud_original"]["concepto"] in cuerpo
        assert "no se pudo avisar al Administrador" in cuerpo
        assert not driver.find_elements(By.CSS_SELECTOR,"form[action='"+accion+"']")
        assert driver.save_screenshot(str(evidencia/"E2E-FAC-001-version-1-en-revision.png"))
        v=ctx["verificar"]()
        assert v["total_solicitudes"]==5 and v["total_auditoria"]==6 and v["total_facturas"]==1
        assert v["otras_solicitudes_sin_cambios"] and v["campos_conservados"] and v["auditorias_previas_sin_cambios"]
        solicitud=v["solicitud"]
        assert solicitud["version"]==4 and solicitud["estado_nombre"]=="En revisión"
        f=v["factura"]
        assert f["solicitud_id"]==3 and f["version"]==1 and f["estado"]=="EN_REVISION"
        assert f["generada_por"]==2 and f["tipo_dte"]==34
        for k,esperado in {"monto_neto":0,"monto_exento":459000,"iva":0,"monto_total":459000}.items():
            assert Decimal(str(f[k]))==Decimal(esperado)
        assert f["archivo_sii"] is None and f["archivo_sii_sha256"] is None
        assert f["cambios"] is None and f["revisada_por"] is None
        datos=f["datos"];original=ctx["solicitud_original"]
        assert datos["solicitud_public_id"]==pid and datos["fecha_emision"]==original["fecha_emision"]
        assert datos["tipo_afectacion"]=="EXENTA"
        assert datos["detalle"]=={"concepto":original["concepto"],"nro_orden_compra":original["nro_orden_compra"]}
        assert datos["receptor"]=={"rut":original["rut"],"razon_social":original["nombre"],"giro":original["giro"],"direccion":original["direccion"],"email":original["email_contacto_receptor"]}
        totales={"tipo_dte":34,"monto_bruto":459000,"monto_neto":0,"monto_exento":459000,"tasa_iva":0,"iva":0,"monto_total":459000,"diferencia_redondeo":0}
        assert datos["totales"]==totales
        huella=hashlib.sha256(json.dumps(datos,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        assert f["huella"]==huella
        assert len(v["auditorias_nuevas"])==1
        a=v["auditorias_nuevas"][0]
        assert a["accion"]=="FACTURA_GENERADA" and a["usuario_id"]==2
        d=a["detalle"]
        assert d["solicitud_afectada_id"]==3 and d["public_id"]==pid and d["factura_id"]==f["id"]
        assert d["version_factura"]==1 and d["version_factura_anterior"] is None
        assert d["estado_anterior"]=="Pendiente" and d["estado_nuevo"]=="En revisión"
        assert d["version_anterior"]==3 and d["version_nueva"]==4 and d["totales"]==totales
        assert all(v["conteos"][t]==0 for t in ("registros_xml","adjuntos_solicitud","envios_correo","correos_entrantes"))
        assert ctx["intentos_smtp"]==0 and v["archivos_sii_en_carpeta_qa"]==0
        ctx["alertas_cerradas_logout"]=cerrar_alertas_y_logout(driver,wait)
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        ctx["factura_revision_verificada"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"E2E-FAC-001-fallo.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise