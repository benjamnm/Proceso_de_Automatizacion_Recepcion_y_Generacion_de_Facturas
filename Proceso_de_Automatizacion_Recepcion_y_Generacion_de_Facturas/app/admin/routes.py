import pymysql

from email_validator import EmailNotValidError, validate_email
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import generate_password_hash

from . import admin_bp
from ..models import get_db_connection
from ..security import admin_required


@admin_bp.route("/usuarios", methods=["GET", "POST"])
@admin_required
def usuarios():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, nombre FROM roles ORDER BY nombre"
            )
            roles = cursor.fetchall()

        errors = []
        values = {
            "nombre": "",
            "email": "",
            "rol_id": "",
        }

        if request.method == "POST":
            values = {
                "nombre": request.form.get("nombre", "").strip(),
                "email": request.form.get("email", "").strip().lower(),
                "rol_id": request.form.get("rol_id", ""),
            }

            password = request.form.get("password", "")
            confirmation = request.form.get("password_confirm", "")

            if not 2 <= len(values["nombre"]) <= 120:
                errors.append(
                    "El nombre debe tener entre 2 y 120 caracteres."
                )

            try:
                validated = validate_email(
                    values["email"],
                    check_deliverability=False,
                )
                values["email"] = validated.normalized.lower()

                if len(values["email"]) > 150:
                    errors.append(
                        "El correo no puede superar 150 caracteres."
                    )

            except EmailNotValidError:
                errors.append("Ingrese un correo electrónico válido.")

            try:
                role_id = int(values["rol_id"])
            except (TypeError, ValueError):
                role_id = None

            valid_role_ids = {role["id"] for role in roles}

            if role_id not in valid_role_ids:
                errors.append("Seleccione un rol válido.")

            if not 12 <= len(password) <= 128:
                errors.append(
                    "La contraseña debe tener entre 12 y 128 caracteres."
                )

            if password != confirmation:
                errors.append("Las contraseñas no coinciden.")

            if not errors:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM usuarios WHERE email = %s",
                        (values["email"],),
                    )

                    if cursor.fetchone() is not None:
                        errors.append(
                            "Ya existe un usuario con ese correo."
                        )

            if not errors:
                password_hash = generate_password_hash(password)

                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO usuarios (
                                rol_id,
                                nombre,
                                email,
                                password_hash,
                                activo
                            )
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                role_id,
                                values["nombre"],
                                values["email"],
                                password_hash,
                                1,
                            ),
                        )

                    connection.commit()

                except pymysql.err.IntegrityError:
                    connection.rollback()
                    errors.append(
                        "No se pudo crear el usuario. "
                        "Compruebe que el correo no esté registrado."
                    )

                except pymysql.MySQLError:
                    connection.rollback()
                    current_app.logger.exception(
                        "Error al crear un usuario"
                    )
                    errors.append(
                        "Ocurrió un error al guardar. "
                        "Intente nuevamente."
                    )

                else:
                    flash("Usuario creado correctamente.", "success")
                    return redirect(url_for("admin.usuarios"))

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.nombre,
                    u.email,
                    u.activo,
                    r.nombre AS rol_nombre
                FROM usuarios AS u
                INNER JOIN roles AS r ON r.id = u.rol_id
                ORDER BY u.id DESC
                """
            )
            users = cursor.fetchall()

        return render_template(
            "admin/usuarios.html",
            usuarios=users,
            roles=roles,
            errors=errors,
            values=values,
        )

    finally:
        connection.close()