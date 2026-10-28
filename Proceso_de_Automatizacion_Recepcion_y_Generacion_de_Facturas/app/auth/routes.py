from flask import flash, redirect, render_template, request, url_for
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user
)

from . import auth_bp
from ..models import User


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # get_by_email solo devuelve cuentas activas: el mensaje es
        # el mismo para cuenta inexistente, inactiva o clave errónea.
        user = User.get_by_email(email)

        if user is None or not user.check_password(password):
            flash(
                "El correo o la contraseña no son válidos.",
                "danger"
            )
            return render_template("auth/login.html")

        user.registrar_login()
        login_user(user, remember=False)
        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("La sesión se cerró correctamente.", "success")
    return redirect(url_for("auth.login"))
