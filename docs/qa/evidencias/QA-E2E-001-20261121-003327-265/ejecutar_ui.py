import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

app_dir = Path(sys.argv[1])
evidencia = Path(__file__).resolve().parent
inicio = datetime.now().astimezone().isoformat()
resultado = {"ejecucion": "QA-E2E-001", "caso": "E2E-LOGIN-001", "inicio": inicio,
             "pruebas_iniciadas": False, "codigo_pytest": None}
servidor = None
codigo = 2
try:
    with (evidencia / "flask-stdout.log").open("w", encoding="utf-8") as stdout,          (evidencia / "flask-stderr.log").open("w", encoding="utf-8") as stderr:
        servidor = subprocess.Popen([
            sys.executable, "-X", "utf8", "-u", str(evidencia / "servidor_ui.py"),
            str(app_dir), str(evidencia),
        ], cwd=app_dir, stdout=stdout, stderr=stderr)
        limite = time.monotonic() + 40
        info = None
        opener = build_opener(ProxyHandler({}))
        while time.monotonic() < limite:
            if servidor.poll() is not None:
                raise RuntimeError("El servidor QA termino durante el arranque; revisar flask-stderr.log")
            archivo = evidencia / "servidor.json"
            if archivo.exists():
                try:
                    info = json.loads(archivo.read_text(encoding="utf-8"))
                    if info["pid"] != servidor.pid:
                        raise RuntimeError("El PID no corresponde al servidor iniciado")
                    with opener.open(info["base_url"] + "/auth/login", timeout=2) as r:
                        if r.status == 200:
                            resultado["http_login"] = r.status
                            break
                except (OSError, ValueError):
                    pass
            time.sleep(0.3)
        else:
            raise RuntimeError("No se confirmo HTTP 200 del servidor QA dentro del plazo")
        entorno = dict(os.environ, E2E_EVIDENCIA=str(evidencia), E2E_BASE_URL=info["base_url"])
        argumentos = [sys.executable, "-X", "utf8", "-m", "pytest", "e2e/test_login_smoke.py",
                      "-o", "addopts=", "-v", "-ra", "--tb=short", "--color=no",
                      f"--junitxml={evidencia / 'selenium-junit.xml'}"]
        (evidencia / "comando-pytest.json").write_text(json.dumps(argumentos, indent=2), encoding="utf-8")
        resultado["pruebas_iniciadas"] = True
        with (evidencia / "selenium.log").open("w", encoding="utf-8") as log:
            prueba = subprocess.run(argumentos, cwd=app_dir, env=entorno, stdout=log, stderr=subprocess.STDOUT)
        codigo = prueba.returncode
        resultado["codigo_pytest"] = codigo
except Exception as exc:
    resultado["error_orquestacion"] = str(exc)
    print(str(exc), file=sys.stderr)
finally:
    if servidor is not None:
        if servidor.poll() is None:
            servidor.terminate()
            try:
                servidor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                servidor.kill()
                servidor.wait()
        resultado["servidor_qa_detenido"] = servidor.poll() is not None
    resultado["fin"] = datetime.now().astimezone().isoformat()
    resultado["junit_generado"] = (evidencia / "selenium-junit.xml").exists()
    (evidencia / "resultado-ejecucion.json").write_text(json.dumps(resultado, indent=2), encoding="utf-8")
raise SystemExit(codigo)