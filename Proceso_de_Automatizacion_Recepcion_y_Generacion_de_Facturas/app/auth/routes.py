from datetime import datetime

import pymysql
from flask import flash, redirect, render_template, request, url_for
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user
)

from . import auth_bp
from ..extensions import login_manager
from ..models import User


@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(int(user_id))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.get_by_email(email)

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

        # Actualizar último login
        conn = pymysql.connect(
            host="127.0.0.1",
            user="root",
            password="",
            database="facturaciones_spa_mvp",
            charset="utf8mb4"
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE usuarios SET ultimo_login = %s WHERE id = %s",
                    (datetime.utcnow(), user.id)
                )
            conn.commit()
        finally:
            conn.close()

        login_user(user, remember=False)
        return redirect(url_for("dashboard"))

    return render_template("auth/login.html")


@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()
    flash("La sesión se cerró correctamente.", "success")
    return redirect(url_for("auth.login"))