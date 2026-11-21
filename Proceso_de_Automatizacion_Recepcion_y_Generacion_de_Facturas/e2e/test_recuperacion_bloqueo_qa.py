import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def test_recuperacion_tras_ventana_real(request):
    """E2E-AUTH-006: bloqueo y recuperacion real sin reiniciar el servidor."""
    ctx = request.config._qa_recovery_context
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
        inicio_secuencia = time.monotonic()

        def enviar_una_vez(clave, esperado):
            driver.get(ctx["base_url"] + "/auth/login")
            correo = wait.until(EC.visibility_of_element_located((By.ID, "email")))
            correo.send_keys(ctx["email"])
            driver.find_element(By.ID, "password").send_keys(clave)
            form = correo.find_element(By.XPATH, "./ancestor::form")
            assert form.find_element(By.CSS_SELECTOR, "input[name='csrf_token']").get_attribute("value")
            previos = len(ctx["eventos"])
            form.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            wait.until(lambda d: len(ctx["eventos"]) > previos)
            nuevos = ctx["eventos"][previos:]
            assert len(nuevos) == 1, "Numero inesperado de POST"
            assert nuevos[0]["status"] == esperado, "HTTP distinto del esperado"
            assert urlsplit(driver.current_url).netloc == urlsplit(ctx["base_url"]).netloc
            return nuevos[0]

        ctx["progreso"]("PROVOCANDO_BLOQUEO", 0)
        for _ in range(5):
            assert time.monotonic() - inicio_secuencia < ctx["ventana_segundos"]
            evento = enviar_una_vez(ctx["clave_invalida"], 401)
            assert evento["sesion_autenticada"] is False
            alerta = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-danger")))
            assert alerta.text.strip() == "El correo o la contraseña no son válidos."
        assert time.monotonic() - inicio_secuencia < ctx["ventana_segundos"]
        evento = enviar_una_vez(ctx["clave_valida"], 429)
        assert evento["sesion_autenticada"] is False
        alerta = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".alert-danger")))
        assert "Demasiados intentos" in alerta.text
        assert ctx["ultimo_login_igual"](), "Cambio ultimo_login durante el bloqueo"
        driver.find_element(By.ID, "password").clear()
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-006-bloqueo.png"))
        ctx["bloqueo_confirmado"] = True

        espera = ctx["ventana_segundos"] + 5
        ctx["espera_inicio"] = datetime.now().astimezone().isoformat()
        ctx["reintento_no_antes_de"] = (datetime.now().astimezone() + timedelta(seconds=espera)).isoformat()
        inicio_espera = time.monotonic()
        objetivo = inicio_espera + espera
        ultimo_aviso = None
        while True:
            restante = objetivo - time.monotonic()
            if restante <= 0:
                break
            tramo = math.ceil(restante / 60)
            if tramo != ultimo_aviso:
                ctx["progreso"]("ESPERANDO_VENTANA_REAL", math.ceil(restante))
                ultimo_aviso = tramo
            time.sleep(min(10, restante))
        ctx["espera_real_segundos"] = time.monotonic() - inicio_espera
        assert ctx["espera_real_segundos"] >= espera
        ctx["progreso"]("VERIFICANDO_RECUPERACION", 0)
        # GET nuevo obtiene formulario/CSRF fresco; no reutiliza el de antes de la espera.
        evento = enviar_una_vez(ctx["clave_valida"], 302)
        assert evento["sesion_autenticada"] is True
        wait.until(lambda d: urlsplit(d.current_url).path == "/dashboard")
        usuario = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".topbar-usuario-texto")))
        assert "Administrador Sintetico QA" in usuario.text
        assert "Administrador" in usuario.text
        assert ctx["ultimo_login_cambio"](), "El acceso no actualizo ultimo_login"
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-006-recuperacion.png"))
        ctx["recuperacion_confirmada"] = True
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "form[action='/auth/logout'] button[type='submit']"))).click()
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        driver.get(ctx["base_url"] + "/dashboard")
        wait.until(lambda d: urlsplit(d.current_url).path == "/auth/login")
        assert driver.find_element(By.ID, "email").is_displayed()
        assert driver.save_screenshot(str(evidencia / "E2E-AUTH-006-cierre.png"))
        assert len(ctx["eventos"]) == 7
        ctx["progreso"]("CASO_COMPLETADO", 0)
    except Exception:
        ctx["progreso"]("CASO_NO_COMPLETADO", 0)
        if driver is not None:
            try:
                for campo in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                    campo.clear()
                driver.save_screenshot(str(evidencia / "E2E-AUTH-006-fallo.png"))
            except Exception:
                pass
        raise
    finally:
        if driver is not None:
            driver.quit()