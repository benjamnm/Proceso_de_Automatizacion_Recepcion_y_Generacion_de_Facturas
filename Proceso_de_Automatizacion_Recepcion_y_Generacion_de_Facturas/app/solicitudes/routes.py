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

from . import solicitudes_bp
from ..models import get_db_connection
from ..security import solicitud_required
from ..services.solicitudes import (
    ErrorGestionSolicitud,
    crear_solicitud,
)
from ..services.validaciones import validar_solicitud


CAMPOS_FORMULARIO = (
    "cliente_id",
    "concepto",
    "nro_orden_compra",
    "fecha_emision",
    "monto_bruto",
    "tipo_afectacion",
)


@solicitudes_bp.route("/nueva", methods=["GET", "POST"])
@solicitud_required
def nueva():
    values = {campo: "" for campo in CAMPOS_FORMULARIO}
    errores = {}

    if request.method == "POST":
        values = {
            campo: request.form.get(campo, "")
            for campo in CAMPOS_FORMULARIO
        }

        datos, errores = validar_solicitud(values)

        if not errores:
            try:
                public_id = crear_solicitud(
                    actor_id=int(current_user.id),
                    datos=datos,
                    ip=request.remote_addr,
                )

            except ErrorGestionSolicitud as exc:
                errores["general"] = str(exc)

            except pymysql.MySQLError:
                current_app.logger.exception(
                    "Error al crear una solicitud"
                )
                errores["general"] = (
                    "No se pudo guardar la solicitud. "
                    "Revise el registro del servidor e intente nuevamente."
                )

            else:
                flash(
                    "Solicitud creada con estado Pendiente.",
                    "success",
                )
                return redirect(
                    url_for(
                        "solicitudes.detalle",
                        public_id=public_id,
                    )
                )

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
                WHERE activo = 1
                ORDER BY razon_social
                """
            )
            clientes = cursor.fetchall()

    finally:
        connection.close()

    return render_template(
        "solicitudes/nueva.html",
        clientes=clientes,
        values=values,
        errores=errores,
    )


@solicitudes_bp.get("/<string:public_id>")
@solicitud_required
def detalle(public_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT
                    s.*,
                    e.nombre AS estado_nombre,
                    o.nombre AS origen_nombre
                FROM solicitudes AS s
                INNER JOIN estados_solicitud AS e
                    ON e.id = s.estado_id
                INNER JOIN origenes_solicitud AS o
                    ON o.id = s.origen_id
                WHERE s.public_id = %s
            """
            parametros = [public_id]

            if current_user.role_name != "Administrador":
                sql += " AND s.emisor_id = %s"
                parametros.append(int(current_user.id))

            cursor.execute(sql, tuple(parametros))
            solicitud = cursor.fetchone()

    finally:
        connection.close()

    if solicitud is None:
        abort(404)

    return render_template(
        "solicitudes/detalle.html",
        solicitud=solicitud,
    )