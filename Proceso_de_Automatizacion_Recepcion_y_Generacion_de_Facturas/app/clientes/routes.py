import pymysql

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from . import clientes_bp
from ..models import get_db_connection
from ..security import admin_required
from ..services.clientes import (
    ErrorGestionCliente,
    guardar_cliente,
)
from ..services.validaciones import validar_cliente


CAMPOS_FORMULARIO = (
    "rut",
    "razon_social",
    "giro",
    "direccion",
    "email_contacto",
)


def datos_formulario():
    return {
        campo: request.form.get(campo, "")
        for campo in CAMPOS_FORMULARIO
    }


@clientes_bp.get("/")
@admin_required
def listado():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    rut,
                    razon_social,
                    email_contacto,
                    activo
                FROM clientes
                ORDER BY id DESC
                LIMIT 100
                """
            )
            clientes = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "clientes/listado.html",
        clientes=clientes,
    )


@clientes_bp.route("/nuevo", methods=["GET", "POST"])
@admin_required
def nuevo():
    return procesar_formulario()


@clientes_bp.route(
    "/<int:cliente_id>/editar",
    methods=["GET", "POST"],
)
@admin_required
def editar(cliente_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    rut,
                    razon_social,
                    giro,
                    direccion,
                    email_contacto
                FROM clientes
                WHERE id = %s
                """,
                (cliente_id,),
            )
            cliente = cursor.fetchone()

    finally:
        connection.close()

    if cliente is None:
        abort(404)

    return procesar_formulario(cliente)


def procesar_formulario(cliente=None):
    editando = cliente is not None

    values = {
        campo: cliente[campo] if editando else ""
        for campo in CAMPOS_FORMULARIO
    }
    errores = {}

    if request.method == "POST":
        values = datos_formulario()
        datos, errores = validar_cliente(values)

        if not errores:
            try:
                _, changed = guardar_cliente(
                    actor_id=int(current_user.id),
                    datos=datos,
                    cliente_id=cliente["id"] if editando else None,
                    ip=request.remote_addr,
                )

            except ErrorGestionCliente as exc:
                errores["general"] = str(exc)

            except pymysql.err.IntegrityError:
                errores["general"] = (
                    "No se pudo guardar. "
                    "Compruebe que el RUT no esté registrado."
                )

            except pymysql.MySQLError:
                current_app.logger.exception(
                    "Error al guardar un cliente"
                )
                errores["general"] = (
                    "Ocurrió un error de base de datos. "
                    "Intente nuevamente."
                )

            else:
                mensaje = (
                    "Cliente actualizado correctamente."
                    if editando
                    else "Cliente creado correctamente."
                )

                flash(
                    mensaje if changed else "No había cambios para guardar.",
                    "success" if changed else "info",
                )

                return redirect(url_for("clientes.listado"))

    return render_template(
        "clientes/formulario.html",
        cliente=cliente,
        editando=editando,
        values=values,
        errores=errores,
    )