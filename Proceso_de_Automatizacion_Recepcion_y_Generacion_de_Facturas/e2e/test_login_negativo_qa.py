import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@pytest.mark.parametrize("escenario", ["clave_incorrecta", "cuenta_inexistente"])
def test_login_negativo_sin_sesion(request, escenario):
    """E2E-AUTH-003/004: un POST por escenario, sin reintentos."""
    ctx = request.config._qa_negative_context
    evidencia = Path(ctx["evidencia"])
    base = ctx["base_url"]
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1440,1000")
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(1440, 1000)
        driver.set_page_load_timeout(30)
        caps = driver.capabilities
        (evidencia / f"navegador-{escenario}.json").write_text(json.dumps({
            "browser": caps.get("browserName"),
            "browser_version": caps.get("browserVersion"),
            "chromedriver_version": caps.get("chrome", {}).get("chromedriverVersion"),
        }, indent=2), encoding="utf-8")
        wait = WebDriverWait(driver, 20)
        driver.get(base + "/auth/login")
        correo = wait.until(EC.visibility_of_element_located((By.ID, "email")))
        password = driver.find_element(By.ID, "password")
        correo.send_keys(ctx["emails"][escenario])
        password.send_keys(ctx["clave_invalida"])
        formulario = correo.find_element(By.XPATH, "./ancestor::form")
        assert formulario.find_element(By.CSS_SELECTOR, "input[name='csrf_token']").get_attribute("value")
        cantidad_previa = len(ctx["eventos"])
        formulario.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        wait.until(lambda d: len(ctx["eventos"]) > cantidad_previa)
        nuevos = ctx["eventos"][cantidad_previa:]
        assert len(nuevos) == 1, "No hubo exactamente un POST en el escenario"
        assert nuevos[0]["status"] == 401, "El login negativo no devolvio 401"
        assert nuevos[0]["sesion_autenticada"] is False, "Se concedio sesion"
        alerta = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-danger")))
        mensaje = alerta.text.strip()
        assert mensaje == "El correo o la contraseña no son válidos."
        assert urlsplit(driver.current_url).netloc == urlsplit(base).netloc
        assert urlsplit(driver.current_url).path == "/auth/login"
        assert not driver.find_elements(By.CSS_SELECTOR, "form[action='/auth/logout']")
        assert ctx["ultimo_login_sin_cambios"](), "Cambio el ultimo login persistido"
        driver.find_element(By.ID, "password").clear()
        assert driver.save_screenshot(str(evidencia / f"{escenario}-rechazo.png"))
        driver.get(base + "/dashboard")
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        assert driver.find_element(By.ID, "email").is_displayed()
        ctx["resultados"].append({
            "escenario": escenario, "http": nuevos[0]["status"],
            "mensaje": mensaje, "sesion_autenticada": False,
            "panel_protegido": True, "ultimo_login_sin_cambios": True,
        })
    except Exception:
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                    campo.clear()
                driver.save_screenshot(str(evidencia / f"{escenario}-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            driver.quit()