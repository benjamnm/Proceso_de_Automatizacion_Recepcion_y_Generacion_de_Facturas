from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user
)

from . import auth_bp
from ..extensions import db, login_manager
from ..models import User


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if user is None or not user.check_password(password):
            flash(
                "El correo o la contraseña no son válidos.",
                "danger"
            )
            return render_template("auth/login.html")

        if not user.activo:
            flash(
                "El usuario se encuentra desactivado.",
                "warning"
            )
            return render_template("auth/login.html")

        user.ultimo_login = datetime.utcnow()
        db.session.commit()

        login_user(user, remember=False)

        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()

    flash(
        "La sesión se cerró correctamente.",
        "success"
    )

    return redirect(url_for("auth.login"))