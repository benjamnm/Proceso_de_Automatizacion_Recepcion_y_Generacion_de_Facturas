import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_pantalla_login_chrome():
    """E2E-LOGIN-001: pantalla QA y toggle, sin enviar credenciales."""
    evidencia = Path(os.environ["E2E_EVIDENCIA"])
    base_url = os.environ["E2E_BASE_URL"]
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1440,1000")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.set_window_size(1440, 1000)
        caps = driver.capabilities
        (evidencia / "navegador.json").write_text(json.dumps({
            "browser": caps.get("browserName"),
            "browser_version": caps.get("browserVersion"),
            "chromedriver_version": caps.get("chrome", {}).get("chromedriverVersion"),
            "window": driver.get_window_size(),
        }, indent=2), encoding="utf-8")
        driver.get(base_url + "/auth/login")
        wait = WebDriverWait(driver, 15)
        correo = wait.until(EC.visibility_of_element_located((By.ID, "email")))
        password = wait.until(EC.visibility_of_element_located((By.ID, "password")))
        toggle = wait.until(EC.element_to_be_clickable((By.ID, "togglePassword")))
        formulario = correo.find_element(By.XPATH, "./ancestor::form")
        boton = formulario.find_element(By.CSS_SELECTOR, "button[type='submit']")
        csrf = formulario.find_element(By.CSS_SELECTOR, "input[name='csrf_token']")
        assert urlsplit(driver.current_url).netloc == urlsplit(base_url).netloc
        assert urlsplit(driver.current_url).path == "/auth/login"
        assert "Iniciar sesión" in driver.title
        assert correo.get_attribute("type") == "email" and correo.is_enabled()
        assert password.get_attribute("type") == "password" and password.is_enabled()
        assert boton.is_displayed() and boton.is_enabled()
        assert boton.text.strip() == "Iniciar sesión"
        assert formulario.get_attribute("method").lower() == "post"
        assert urlsplit(formulario.get_attribute("action")).path == "/auth/login"
        assert csrf.get_attribute("type") == "hidden"
        assert bool(csrf.get_attribute("value")), "Token CSRF vacio"
        assert driver.find_element(By.CSS_SELECTOR, "a[href='/auth/recuperar']").is_displayed()
        toggle.click()
        wait.until(lambda d: password.get_attribute("type") == "text")
        toggle.click()
        wait.until(lambda d: password.get_attribute("type") == "password")
        assert driver.save_screenshot(str(evidencia / "E2E-LOGIN-001-aprobado.png"))
    except Exception:
        if driver is not None:
            try:
                driver.save_screenshot(str(evidencia / "E2E-LOGIN-001-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            driver.quit()