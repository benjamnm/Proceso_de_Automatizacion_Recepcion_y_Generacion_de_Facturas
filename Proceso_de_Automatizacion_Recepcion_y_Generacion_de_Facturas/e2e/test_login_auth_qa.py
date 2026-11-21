import json
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_admin_qa_login_logout(request):
    """E2E-AUTH-002: autenticacion persistida exclusiva de QA, un solo envio."""
    ctx = request.config._qa_auth_context
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
        (evidencia / "navegador.json").write_text(json.dumps({
            "browser": caps.get("browserName"),
            "browser_version": caps.get("browserVersion"),
            "chromedriver_version": caps.get("chrome", {}).get("chromedriverVersion"),
        }, indent=2), encoding="utf-8")
        wait = WebDriverWait(driver, 20)
        driver.get(base + "/dashboard")
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        correo = wait.until(EC.visibility_of_element_located((By.ID, "email")))
        password = driver.find_element(By.ID, "password")
        correo.send_keys(ctx["email"])
        password.send_keys(ctx["password"])
        formulario = correo.find_element(By.XPATH, "./ancestor::form")
        csrf = formulario.find_element(By.CSS_SELECTOR, "input[name='csrf_token']")
        assert bool(csrf.get_attribute("value")), "Falta token CSRF"
        formulario.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        ctx["envios_login"] += 1
        wait.until(lambda d: urlsplit(d.current_url).path != "/auth/login" or
                   bool(d.find_elements(By.CSS_SELECTOR, ".alert-danger")))
        assert urlsplit(driver.current_url).netloc == urlsplit(base).netloc
        assert urlsplit(driver.current_url).path == "/dashboard", "No se alcanzo el panel; no se reintentara"
        usuario = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-usuario-texto")))
        assert "Administrador Sintetico QA" in usuario.text
        assert "Administrador" in usuario.text
        assert driver.find_element(By.CSS_SELECTOR, "a[href='/admin/usuarios']").is_displayed()
        assert ctx["ultimo_login_actualizado"](), "No se confirmo la actualizacion persistida del ultimo login"
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-002-panel-qa.png"))
        salir = wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "form[action='/auth/logout'] button[type='submit']"
        )))
        salir.click()
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        driver.get(base + "/dashboard")
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        assert driver.find_element(By.ID, "email").is_displayed()
        assert not driver.find_elements(By.CSS_SELECTOR, "form[action='/auth/logout']")
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-002-cierre-qa.png"))
    except Exception:
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                    campo.clear()
                driver.save_screenshot(str(evidencia / "E2E-AUTH-002-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            driver.quit()