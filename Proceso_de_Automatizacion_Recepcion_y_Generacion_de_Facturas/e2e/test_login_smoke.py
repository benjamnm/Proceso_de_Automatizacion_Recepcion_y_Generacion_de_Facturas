import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_pantalla_login_chrome():
    """E2E-LOGIN-001: formulario de acceso visible, sin enviar credenciales."""
    evidencia = Path(os.environ["E2E_EVIDENCIA"])
    evidencia.mkdir(parents=True, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1440,1000")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.set_window_size(1440, 1000)

        caps = driver.capabilities
        versiones = {
            "browser": caps.get("browserName"),
            "browser_version": caps.get("browserVersion"),
            "chromedriver_version": caps.get("chrome", {}).get(
                "chromedriverVersion"
            ),
            "window": driver.get_window_size(),
        }
        (evidencia / "navegador.json").write_text(
            json.dumps(versiones, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        driver.get("http://127.0.0.1:5000/auth/login")
        wait = WebDriverWait(driver, 15)

        correo = wait.until(
            EC.visibility_of_element_located((By.ID, "email"))
        )
        password = wait.until(
            EC.visibility_of_element_located((By.ID, "password"))
        )
        boton = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "form button[type='submit']")
            )
        )
        toggle = wait.until(
            EC.visibility_of_element_located((By.ID, "togglePassword"))
        )

        url = urlsplit(driver.current_url)
        assert url.hostname == "127.0.0.1"
        assert url.path == "/auth/login"
        assert "Iniciar sesión" in driver.title

        assert correo.get_attribute("type") == "email"
        assert correo.is_enabled()
        assert password.get_attribute("type") == "password"
        assert password.is_enabled()
        assert boton.is_enabled()
        assert boton.text.strip() == "Iniciar sesión"
        assert toggle.is_enabled()

        formulario = correo.find_element(By.XPATH, "./ancestor::form")
        assert formulario.get_attribute("method").lower() == "post"

        csrf = formulario.find_element(
            By.CSS_SELECTOR, "input[name='csrf_token']"
        )
        assert csrf.get_attribute("type") == "hidden"
        assert bool(csrf.get_attribute("value")), "Token CSRF vacío"

        assert driver.save_screenshot(
            str(evidencia / "E2E-LOGIN-001-aprobado.png")
        ), "No se pudo guardar la captura de aprobación"

    except Exception:
        if driver is not None:
            try:
                driver.save_screenshot(
                    str(evidencia / "E2E-LOGIN-001-fallo.png")
                )
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            driver.quit()
