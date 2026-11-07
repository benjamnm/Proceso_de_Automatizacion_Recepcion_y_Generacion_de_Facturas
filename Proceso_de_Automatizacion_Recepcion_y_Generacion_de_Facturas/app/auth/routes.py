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
from werkzeug.security import check_password_hash, generate_password_hash

from . import auth_bp
from ..models import User

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
        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("La sesión se cerró correctamente.", "success")
    return redirect(url_for("auth.login"))
