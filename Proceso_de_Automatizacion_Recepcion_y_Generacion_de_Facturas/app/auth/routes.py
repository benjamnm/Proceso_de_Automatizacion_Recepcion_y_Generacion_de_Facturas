from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
import threading

import pymysql
from werkzeug.security import check_password_hash, generate_password_hash

from . import auth_bp
from ..models import User
from ..security import recordar_password_en_sesion
from ..services.contrasenas import (
    ErrorPassword,
    avisar_recuperacion_a_admins,
    cambiar_propia,
    solicitar_recuperacion,
)

LARGO_MAXIMO_PASSWORD = 128
# Se compara contra este hash cuando la cuenta no existe, para que el
# tiempo de respuesta no revele qué correos están registrados.
HASH_FICTICIO = generate_password_hash("cuenta-inexistente")


def _credenciales_validas(email, password):
    if not email or not password or len(password) > LARGO_MAXIMO_PASSWORD:
        check_password_hash(HASH_FICTICIO, "x")
        return None

    # get_by_email solo devuelve cuentas activas: el mensaje es el mismo
    # para cuenta inexistente, inactiva o clave errónea.
    user = User.get_by_email(email)

    if user is None:
        check_password_hash(HASH_FICTICIO, password)
        return None

    return user if user.check_password(password) else None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:150]
        password = request.form.get("password", "")
        ip = request.remote_addr or "desconocida"

        config = current_app.config
        limitador = current_app.extensions["limitador_login"]
        limites = {
            f"ip:{ip}": config["LOGIN_MAX_INTENTOS_IP"],
            f"cuenta:{ip}:{email}": config["LOGIN_MAX_INTENTOS"],
        }

        espera = limitador.espera(limites)
        if espera:
            minutos = -(-espera // 60)
            flash(
                "Demasiados intentos fallidos. Espere "
                f"{minutos} minuto(s) antes de volver a intentarlo.",
                "danger",
            )
            return render_template("auth/login.html"), 429

        user = _credenciales_validas(email, password)

        if user is None:
            limitador.registrar_fallo(limites)
            current_app.logger.warning(
                "Inicio de sesión fallido desde %s", ip
            )
            flash("El correo o la contraseña no son válidos.", "danger")
            return render_template("auth/login.html"), 401

        limitador.limpiar([f"cuenta:{ip}:{email}"])
        # Sesión nueva tras autenticar: evita la fijación de sesión.
        session.clear()
        user.registrar_login()
        login_user(user, remember=False)
        recordar_password_en_sesion(user.password_hash)

        if user.debe_cambiar_password:
            flash(
                "Está usando una contraseña temporal. Defina una contraseña "
                "nueva para continuar.",
                "warning",
            )
            return redirect(url_for("auth.cambiar_password"))

        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


def _avisar_sin_esperar(usuario):
    """El aviso SMTP va en segundo plano: si la respuesta esperara al
    correo, su demora revelaría qué direcciones tienen cuenta."""
    app = current_app._get_current_object()

    if app.testing:
        avisar_recuperacion_a_admins(usuario)
        return

    def tarea():
        with app.app_context():
            avisar_recuperacion_a_admins(usuario)

    threading.Thread(target=tarea, name="aviso-recuperacion", daemon=True).start()


MENSAJE_RECUPERACION = (
    "Si el correo corresponde a una cuenta activa, el Administrador recibió "
    "su solicitud. Le entregará una contraseña temporal después de "
    "verificar su identidad."
)


@auth_bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    """"¿Olvidó su contraseña?": avisa al Administrador sin revelar si el
    correo existe (la respuesta es siempre la misma)."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        ip = request.remote_addr or "desconocida"
        limitador = current_app.extensions["limitador_login"]
        limites = {f"recuperar:{ip}": current_app.config["RECUPERACION_MAX_IP"]}

        espera = limitador.espera(limites)
        if espera:
            minutos = -(-espera // 60)
            flash(
                "Demasiadas solicitudes. Espere "
                f"{minutos} minuto(s) antes de volver a intentarlo.",
                "danger",
            )
            return render_template("auth/recuperar.html"), 429

        limitador.registrar_fallo(list(limites))

        try:
            usuario = solicitar_recuperacion(
                request.form.get("email", ""), request.remote_addr
            )
        except pymysql.MySQLError:
            current_app.logger.exception("No se pudo registrar la recuperación")
            flash(
                "No se pudo registrar la solicitud. Intente nuevamente o "
                "contacte al Administrador.",
                "danger",
            )
            return render_template("auth/recuperar.html"), 503

        if usuario is not None:
            _avisar_sin_esperar(usuario)

        flash(MENSAJE_RECUPERACION, "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/recuperar.html")


@auth_bp.route("/password", methods=["GET", "POST"])
@login_required
def cambiar_password():
    error = None

    if request.method == "POST":
        try:
            nuevo_hash = cambiar_propia(
                usuario_id=int(current_user.id),
                actual=request.form.get("password_actual", ""),
                nueva=request.form.get("password", ""),
                confirmacion=request.form.get("password_confirm", ""),
                ip=request.remote_addr,
            )
        except ErrorPassword as exc:
            error = str(exc)
        except pymysql.MySQLError:
            current_app.logger.exception("No se pudo cambiar la contraseña")
            error = (
                "No se pudo guardar la contraseña. Intente nuevamente "
                "(si persiste, verifique que se ejecutó la migración 005)."
            )
        else:
            # La sesión actual sigue abierta; las demás se cierran solas.
            recordar_password_en_sesion(nuevo_hash)
            flash("Contraseña actualizada correctamente.", "success")
            return redirect(url_for("dashboard"))

    return render_template(
        "auth/cambiar_password.html",
        error=error,
        obligatorio=current_user.debe_cambiar_password,
    )


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("La sesión se cerró correctamente.", "success")
    return redirect(url_for("auth.login"))
