import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_bloqueo_tras_cinco_fallos(request):
    """E2E-AUTH-005: cinco 401 y un 429 con clave valida, misma IP/correo."""
    ctx = request.config._qa_lock_context
    evidencia = Path(ctx["evidencia"])
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1440,1000")
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(1440, 1000)
        driver.set_page_load_timeout(30)
        caps = driver.capabilities
        (evidencia / "navegador.json").write_text(json.dumps({
            "browser": caps.get("browserName"), "browser_version": caps.get("browserVersion"),
            "chromedriver_version": caps.get("chrome", {}).get("chromedriverVersion"),
        }, indent=2), encoding="utf-8")
        wait = WebDriverWait(driver, 20)
        inicio = time.monotonic()

        def enviar_una_vez(clave, esperado):
            assert time.monotonic() - inicio < ctx["ventana_segundos"], "La ventana expiro; no se altera el reloj"
            driver.get(ctx["base_url"] + "/auth/login")
            correo = wait.until(EC.visibility_of_element_located((By.ID, "email")))
            correo.send_keys(ctx["email"])
            driver.find_element(By.ID, "password").send_keys(clave)
            form = correo.find_element(By.XPATH, "./ancestor::form")
            assert form.find_element(By.CSS_SELECTOR, "input[name='csrf_token']").get_attribute("value")
            previos = len(ctx["eventos"])
            form.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            wait.until(lambda d: len(ctx["eventos"]) > previos)
            eventos = ctx["eventos"][previos:]
            assert len(eventos) == 1, "Se observo un numero inesperado de POST"
            assert eventos[0]["status"] == esperado, "Codigo HTTP distinto del esperado"
            assert eventos[0]["sesion_autenticada"] is False
            assert urlsplit(driver.current_url).netloc == urlsplit(ctx["base_url"]).netloc
            assert urlsplit(driver.current_url).path == "/auth/login"
            alerta = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-danger")))
            return alerta.text.strip()

        for _ in range(5):
            mensaje = enviar_una_vez(ctx["clave_invalida"], 401)
            assert mensaje == "El correo o la contraseña no son válidos."
        driver.find_element(By.ID, "password").clear()
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-005-cinco-fallos.png"))
        mensaje = enviar_una_vez(ctx["clave_valida"], 429)
        assert "Demasiados intentos" in mensaje
        assert not driver.find_elements(By.CSS_SELECTOR, "form[action='/auth/logout']")
        assert ctx["ultimo_login_sin_cambios"](), "Se modifico ultimo_login"
        driver.find_element(By.ID, "password").clear()
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-005-bloqueo.png"))
        driver.get(ctx["base_url"] + "/dashboard")
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        assert driver.find_element(By.ID, "email").is_displayed()
        assert len(ctx["eventos"]) == 6
        ctx["bloqueo_verificado"] = True
    except Exception:
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                    campo.clear()
                driver.save_screenshot(str(evidencia / "E2E-AUTH-005-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            driver.quit()