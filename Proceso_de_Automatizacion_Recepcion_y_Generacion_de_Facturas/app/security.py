import threading
import time
from functools import wraps

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, logout_user

CDN = "https://cdn.jsdelivr.net"
CLAVE_ACTIVIDAD = "_ultima_actividad"

POLITICA_CONTENIDO = "; ".join((
    "default-src 'self'",
    f"script-src 'self' {CDN}",
    f"style-src 'self' {CDN}",
    f"font-src 'self' {CDN}",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if (
            not current_user.is_active
            or current_user.role_name != "Administrador"
        ):
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view


def solicitud_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if (
            not current_user.is_active
            or current_user.role_name
            not in {"Administrador", "Emisor"}
        ):
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view


class LimitadorIntentos:
    """Cuenta intentos fallidos por clave dentro de una ventana de tiempo.

    Vive en memoria del proceso: con varios procesos (p. ej. gunicorn -w 4)
    cada uno lleva su propia cuenta, lo que multiplica el límite efectivo.
    """

    def __init__(self, ventana_segundos):
        self.ventana = ventana_segundos
        self._fallos = {}
        self._candado = threading.Lock()

    def _vigentes(self, clave, ahora):
        fallos = [t for t in self._fallos.get(clave, ()) if ahora - t < self.ventana]
        if fallos:
            self._fallos[clave] = fallos
        else:
            self._fallos.pop(clave, None)
        return fallos

    def espera(self, limites):
        """limites: {clave: maximo}. Segundos de bloqueo restantes (0 = libre)."""
        ahora = time.monotonic()
        restante = 0
        with self._candado:
            for clave, maximo in limites.items():
                fallos = self._vigentes(clave, ahora)
                if len(fallos) >= maximo:
                    restante = max(restante, self.ventana - (ahora - fallos[-maximo]))
        return int(restante) + 1 if restante else 0

    def registrar_fallo(self, claves):
        ahora = time.monotonic()
        with self._candado:
            for clave in claves:
                self._vigentes(clave, ahora)
                self._fallos.setdefault(clave, []).append(ahora)

    def limpiar(self, claves):
        with self._candado:
            for clave in claves:
                self._fallos.pop(clave, None)


def controlar_inactividad():
    if request.endpoint == "static" or not current_user.is_authenticated:
        return None

    ahora = int(time.time())
    ultima = session.get(CLAVE_ACTIVIDAD)
    limite = current_app.config["SESSION_INACTIVIDAD"].total_seconds()

    if isinstance(ultima, int) and ahora - ultima > limite:
        logout_user()
        session.clear()
        flash(
            "Su sesión se cerró por inactividad. Inicie sesión nuevamente.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    session[CLAVE_ACTIVIDAD] = ahora
    return None


def aplicar_cabeceras_seguridad(respuesta):
    cabeceras = respuesta.headers
    cabeceras.setdefault("Content-Security-Policy", POLITICA_CONTENIDO)
    cabeceras.setdefault("X-Content-Type-Options", "nosniff")
    cabeceras.setdefault("X-Frame-Options", "DENY")
    cabeceras.setdefault("Referrer-Policy", "same-origin")
    cabeceras.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    cabeceras.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )

    # Las páginas y descargas contienen datos tributarios y personales:
    # no deben quedar en la caché del navegador ni de proxies.
    if request.endpoint != "static":
        cabeceras["Cache-Control"] = "no-store"
        cabeceras["Pragma"] = "no-cache"

    if request.is_secure:
        cabeceras.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    return respuesta
