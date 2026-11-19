"""Revisión automática de la bandeja de correos en segundo plano.

Un hilo daemon ejecuta revisar_bandeja() cada BANDEJA_REVISION_SEGUNDOS
(0 = desactivado). revisar_bandeja() ya usa GET_LOCK de MySQL, así que
no se pisa con el botón «Revisar bandeja ahora», con la tarea programada
(flask correo-revisar) ni con otro proceso del servidor.

El estado de la última ejecución se guarda en memoria del proceso y se
muestra en la página de la bandeja.
"""
import threading
from datetime import datetime

from .correo_entrante import ErrorCorreoEntrante, revisar_bandeja

MINIMO_SEGUNDOS = 30

_estado = {
    "activa": False,
    "intervalo": 0,
    "ultima": None,
    "error": None,
    "resumen": None,
}
_candado = threading.Lock()
_detener = threading.Event()


def estado():
    with _candado:
        return dict(_estado)


def _actualizar(**campos):
    with _candado:
        _estado.update(campos)


def ejecutar_una_vez(app):
    """Una pasada de revisión. Nunca lanza excepciones."""
    with app.app_context():
        try:
            resultado = revisar_bandeja(
                descargar=bool(app.config.get("IMAP_HOST"))
            )
        except ErrorCorreoEntrante as exc:
            # EN_CURSO: otra revisión está corriendo; no es un error.
            if exc.codigo != "EN_CURSO":
                app.logger.warning("Revisión automática: %s", exc)
                _actualizar(ultima=datetime.now(), error=str(exc))
            return
        except Exception:
            app.logger.exception("Error en la revisión automática de la bandeja")
            _actualizar(ultima=datetime.now(),
                        error="Error inesperado. Revise el registro.")
            return

    _actualizar(
        ultima=datetime.now(),
        error=resultado["error_descarga"],
        resumen=resultado["proceso"],
    )


def _bucle(app, intervalo):
    while not _detener.wait(intervalo):
        ejecutar_una_vez(app)


def iniciar(app):
    """Arranca el hilo si BANDEJA_REVISION_SEGUNDOS > 0. Idempotente."""
    try:
        intervalo = int(app.config.get("BANDEJA_REVISION_SEGUNDOS") or 0)
    except (TypeError, ValueError):
        intervalo = 0

    if intervalo <= 0 or app.config.get("TESTING"):
        return False

    intervalo = max(MINIMO_SEGUNDOS, intervalo)
    with _candado:
        if _estado["activa"]:
            return False
        _estado.update(activa=True, intervalo=intervalo)

    _detener.clear()
    hilo = threading.Thread(
        target=_bucle, args=(app, intervalo),
        name="revision-bandeja", daemon=True,
    )
    hilo.start()
    app.logger.info("Revisión automática de la bandeja cada %s s.", intervalo)
    return True


def detener():
    _detener.set()
    _actualizar(activa=False)
