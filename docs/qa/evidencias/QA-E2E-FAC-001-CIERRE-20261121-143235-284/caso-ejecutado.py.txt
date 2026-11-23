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


def test_factura_existente_y_logout_sin_regenerar(request):
    ctx=request.config._qa_invoice_context
    evidencia=Path(ctx["evidencia"])
    driver=None;fallo=False
    try:
        opciones=webdriver.ChromeOptions();opciones.add_argument("--window-size=1440,1000")
        driver=webdriver.Chrome(options=opciones)
        driver.set_window_size(1440,1000);driver.set_page_load_timeout(30)
        wait=WebDriverWait(driver,20)
        base=ctx["base_url"];pid=ctx["public_id"]
        driver.get(base+"/auth/login")
        correo=wait.until(EC.visibility_of_element_located((By.ID,"email")))
        correo.send_keys(ctx["email"]);driver.find_element(By.ID,"password").send_keys(ctx["password"])
        correo.find_element(By.XPATH,"./ancestor::form").find_element(By.CSS_SELECTOR,"button[type='submit']").click()
        wait.until(lambda d:urlsplit(d.current_url).path!="/auth/login" or bool(d.find_elements(By.CSS_SELECTOR,".alert-danger")))
        assert urlsplit(driver.current_url).path=="/dashboard"
        driver.get(base+"/solicitudes/"+pid+"/factura")
        wait.until(EC.text_to_be_present_in_element((By.TAG_NAME,"body"),"Factura exenta (34)"))
        cuerpo=driver.find_element(By.TAG_NAME,"body").text
        assert "En revisión" in cuerpo and "459.000" in cuerpo
        assert ctx["solicitud_original"]["concepto"] in cuerpo
        assert not driver.find_elements(By.CSS_SELECTOR,"form[action$='/factura/revision']")
        assert driver.save_screenshot(str(evidencia/"factura-existente-sin-regenerar.png"))
        v=ctx["verificar"]()
        assert v["estado_comparado_sin_cambios"] is True
        assert v["total_solicitudes"]==5 and v["total_auditoria"]==6 and v["total_facturas"]==1
        assert v["solicitud"]["version"]==4 and v["solicitud"]["estado_nombre"]=="En revisión"
        f=v["factura"]
        assert f["id"]==1 and f["solicitud_id"]==3 and f["version"]==1 and f["estado"]=="EN_REVISION"
        assert f["tipo_dte"]==34 and f["generada_por"]==2
        for k,n in {"monto_neto":0,"monto_exento":459000,"iva":0,"monto_total":459000}.items():
            assert Decimal(str(f[k]))==Decimal(n)
        assert f["archivo_sii"] is None and f["archivo_sii_sha256"] is None
        huella=hashlib.sha256(json.dumps(f["datos"],sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        assert f["huella"]==huella
        assert not v["auditorias_nuevas"]
        assert v["auditorias_previas_sin_cambios"] and v["otras_solicitudes_sin_cambios"]
        inicio=len(ctx["eventos"])
        ctx["alertas_cerradas_logout"]=cerrar_alertas_y_logout(driver,wait)
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        salidas=[e for e in ctx["eventos"][inicio:] if e["ruta"]=="/auth/logout" and e["metodo"]=="POST"]
        assert len(salidas)==1 and salidas[0]["status"]==302 and salidas[0]["usuario_id"] is None
        driver.get(base+"/dashboard")
        wait.until(lambda d:urlsplit(d.current_url).path=="/auth/login")
        panel=[e for e in ctx["eventos"] if e["ruta"]=="/dashboard"][-1]
        assert panel["status"]==302 and panel["usuario_id"] is None
        assert not any(e["metodo"]=="POST" and e["ruta"].endswith("/factura/revision") for e in ctx["eventos"])
        assert ctx["verificar"]()["estado_comparado_sin_cambios"] is True
        assert driver.save_screenshot(str(evidencia/"logout-confirmado-login.png"))
        ctx["verificacion_complementaria_y_logout"]=True
    except Exception:
        fallo=True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR,"input[type='password']"):campo.clear()
                driver.save_screenshot(str(evidencia/"fallo-complementaria.png"))
            except Exception:pass
        raise
    finally:
        if driver is not None:
            try:driver.quit()
            except Exception as exc:
                ctx["error_cierre_navegador"]=type(exc).__name__
                if not fallo:raise