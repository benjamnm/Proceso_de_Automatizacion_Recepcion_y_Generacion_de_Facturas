import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ADMIN_RUTAS = ("/admin/usuarios", "/clientes/", "/admin/correos", "/admin/auditoria")


@pytest.mark.parametrize("perfil", ["Emisor", "Lector"])
def test_restriccion_administrativa_por_perfil(request, perfil):
    """E2E-RBAC-001/002: permisos verticales; no decide el pendiente HU13."""
    ctx = request.config._qa_rbac_context
    evidencia = Path(ctx["evidencia"])
    cuenta = ctx["cuentas"][perfil]
    driver = None
    fallo = False
    slug = perfil.lower()
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1440,1000")
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(1440, 1000)
        driver.set_page_load_timeout(30)
        caps = driver.capabilities
        (evidencia / f"navegador-{slug}.json").write_text(json.dumps({
            "browser": caps.get("browserName"), "browser_version": caps.get("browserVersion"),
            "chromedriver_version": caps.get("chrome", {}).get("chromedriverVersion"),
        }, indent=2), encoding="utf-8")
        wait = WebDriverWait(driver, 20)
        base = ctx["base_url"]

        def abrir_y_verificar(ruta, esperado):
            antes = len(ctx["eventos"])
            driver.get(base + ruta)
            wait.until(lambda d: any(e["metodo"] == "GET" and e["ruta"] == ruta
                                    for e in ctx["eventos"][antes:]))
            eventos = [e for e in ctx["eventos"][antes:]
                       if e["metodo"] == "GET" and e["ruta"] == ruta]
            assert len(eventos) == 1
            assert eventos[0]["status"] == esperado, "Respuesta HTTP inesperada"
            assert urlsplit(driver.current_url).netloc == urlsplit(base).netloc
            if esperado in (200, 403):
                assert eventos[0]["perfil"] == perfil
                assert urlsplit(driver.current_url).path == ruta
            ctx["verificaciones"].append({"perfil": perfil, "ruta": ruta,
                "http": eventos[0]["status"], "aprobada": True})

        driver.get(base + "/auth/login")
        correo = wait.until(EC.visibility_of_element_located((By.ID, "email")))
        correo.send_keys(cuenta["email"])
        driver.find_element(By.ID, "password").send_keys(cuenta["password"])
        form = correo.find_element(By.XPATH, "./ancestor::form")
        assert form.find_element(By.CSS_SELECTOR, "input[name='csrf_token']").get_attribute("value")
        previos = len(ctx["eventos"])
        form.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        wait.until(lambda d: urlsplit(d.current_url).path != "/auth/login" or
                   bool(d.find_elements(By.CSS_SELECTOR, ".alert-danger")))
        assert urlsplit(driver.current_url).path == "/dashboard", "No se reintentara el login"
        login = [e for e in ctx["eventos"][previos:]
                 if e["metodo"] == "POST" and e["ruta"] == "/auth/login"]
        assert len(login) == 1 and login[0]["status"] == 302 and login[0]["perfil"] == perfil
        usuario = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-usuario-texto")))
        assert cuenta["nombre"] in usuario.text
        assert usuario.find_element(By.CSS_SELECTOR, "span").text.strip() == perfil
        abrir_y_verificar("/dashboard", 200)
        for ruta in ADMIN_RUTAS:
            assert not driver.find_elements(By.CSS_SELECTOR, f".sidebar-nav a[href='{ruta}']")
        if perfil == "Emisor":
            assert driver.find_element(By.CSS_SELECTOR, ".sidebar-nav a[href='/solicitudes/']").is_displayed()
        assert ctx["ultimo_login_actualizado"](perfil)
        assert driver.save_screenshot(str(evidencia / f"{slug}-panel.png"))
        if perfil == "Emisor":
            abrir_y_verificar("/solicitudes/", 200)
        for ruta in ADMIN_RUTAS:
            abrir_y_verificar(ruta, 403)
        assert driver.save_screenshot(str(evidencia / f"{slug}-acceso-administrativo-denegado.png"))
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        abrir_y_verificar("/dashboard", 302)
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        assert driver.find_element(By.ID, "email").is_displayed()
        ctx["perfiles_completados"].append(perfil)
    except Exception:
        fallo = True
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                    campo.clear()
                driver.save_screenshot(str(evidencia / f"{slug}-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                ctx["errores_cierre"].append({"perfil": perfil, "tipo": type(exc).__name__})
                if not fallo:
                    raise