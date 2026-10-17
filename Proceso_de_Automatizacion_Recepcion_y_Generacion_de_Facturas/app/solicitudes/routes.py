import re
import pymysql
import os

from datetime import date
from decimal import Decimal

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from . import solicitudes_bp
from ..models import get_db_connection
from ..security import solicitud_required

from ..services.usuarios import registrar_evento

from ..services.envios_solicitud import (
    ErrorTokenEnvio,
    generar_token_envio,
    verificar_token_envio,
)
from ..services.solicitudes import (
    ErrorGestionSolicitud,
    TRANSICIONES_ESTADO,
    cambiar_estado_solicitud,
    crear_solicitud,
    editar_solicitud,
    validar_solicitud,
)
from ..services.validaciones import (
    ErrorValidacion,
    normalizar_rut,
)
from ..services.registros_xml import (
    ErrorArchivoXML,
    guardar_xml,
    obtener_xml_autorizado,
)


CAMPOS_FORMULARIO = (
    "cliente_id",
    "concepto",
    "nro_orden_compra",
    "fecha_emision",
    "monto_bruto",
    "tipo_afectacion",
)

CAMPOS_FILTRO = (
    "rut",
    "desde",
    "hasta",
    "monto",
    "estado_id",
    "emisor_id",
)


def leer_formulario():
    return {
        campo: request.form.get(campo, "")
        for campo in CAMPOS_FORMULARIO
    }


def obtener_clientes_activos():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, rut, razon_social
                FROM clientes
                WHERE activo = 1
                ORDER BY razon_social
                """
            )
            return cursor.fetchall()

    finally:
        connection.close()


def obtener_solicitud_autorizada(public_id):
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

    return solicitud


def construir_filtros():
    filtros = {
        campo: request.args.get(campo, "").strip()
        for campo in CAMPOS_FILTRO
    }

    condiciones = []
    parametros = []
    errores = []
    fechas = {}

    es_admin = current_user.role_name == "Administrador"

    if not es_admin:
        condiciones.append("s.emisor_id = %s")
        parametros.append(int(current_user.id))

    if filtros["rut"]:
        try:
            rut = normalizar_rut(filtros["rut"])
            condiciones.append("s.rut = %s")
            parametros.append(rut)

        except ErrorValidacion as exc:
            errores.append(str(exc))

    for campo, operador in (
        ("desde", ">="),
        ("hasta", "<="),
    ):
        valor = filtros[campo]

        if not valor:
            continue

        try:
            if not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                valor,
            ):
                raise ValueError

            fechas[campo] = date.fromisoformat(valor)

            condiciones.append(
                f"s.fecha_emision {operador} %s"
            )
            parametros.append(fechas[campo])

        except ValueError:
            errores.append(
                f"La fecha '{campo}' no es válida."
            )

    if (
        "desde" in fechas
        and "hasta" in fechas
        and fechas["desde"] > fechas["hasta"]
    ):
        errores.append(
            "La fecha inicial no puede ser posterior a la final."
        )

    if filtros["monto"]:
        if (
            not re.fullmatch(
                r"[0-9]{1,14}",
                filtros["monto"],
            )
            or Decimal(filtros["monto"]) <= 0
        ):
            errores.append(
                "El monto debe ser un entero positivo, "
                "sin puntos ni comas."
            )
        else:
            condiciones.append("s.monto_bruto = %s")
            parametros.append(Decimal(filtros["monto"]))

    for campo, columna in (
        ("estado_id", "s.estado_id"),
        ("emisor_id", "s.emisor_id"),
    ):
        valor = filtros[campo]

        if not valor:
            continue

        if campo == "emisor_id" and not es_admin:
            errores.append(
                "Solo el Administrador puede filtrar "
                "por responsable."
            )
            continue

        if (
            not re.fullmatch(r"[0-9]{1,10}", valor)
            or int(valor) <= 0
            or int(valor) > 4294967295
        ):
            errores.append(
                f"El filtro '{campo}' no es válido."
            )
            continue

        condiciones.append(f"{columna} = %s")
        parametros.append(int(valor))

    where = (
        "WHERE " + " AND ".join(condiciones)
        if condiciones
        else ""
    )

    return where, tuple(parametros), filtros, errores


@solicitudes_bp.route("/nueva", methods=["GET", "POST"])
@solicitud_required
def nueva():
    values = {
        campo: ""
        for campo in CAMPOS_FORMULARIO
    }
    errores = {}

    token_envio = (
        generar_token_envio(current_user.id)
        if request.method == "GET"
        else request.form.get("token_envio", "")
    )

    if request.method == "POST":
        values = leer_formulario()
        _, errores = validar_solicitud(values)

        try:
            clave_idempotencia = verificar_token_envio(
                token_envio,
                current_user.id,
            )

        except ErrorTokenEnvio as exc:
            errores["envio"] = str(exc)

        if not errores:
            try:
                public_id = crear_solicitud(
                    actor_id=int(current_user.id),
                    datos=values,
                    clave_idempotencia=clave_idempotencia,
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
                    "Puede reintentar desde este formulario."
                )

            else:
                flash(
                    "Solicitud registrada o recuperada correctamente.",
                    "success",
                )

                return redirect(url_for(
                    "solicitudes.detalle",
                    public_id=public_id,
                ))

    return render_template(
        "solicitudes/nueva.html",
        clientes=obtener_clientes_activos(),
        values=values,
        errores=errores,
        editando=False,
        solicitud=None,
        version=None,
        token_envio=token_envio,
    )


@solicitudes_bp.get("/")
@solicitud_required
def listado():
    pagina = max(
        request.args.get("pagina", 1, type=int),
        1,
    )
    por_pagina = 20
    offset = (pagina - 1) * por_pagina

    where, parametros, filtros, errores = construir_filtros()
    es_admin = current_user.role_name == "Administrador"

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nombre
                FROM estados_solicitud
                ORDER BY nombre
                """
            )
            estados = cursor.fetchall()

            responsables = []

            if es_admin:
                cursor.execute(
                    """
                    SELECT id, nombre
                    FROM usuarios
                    ORDER BY nombre
                    """
                )
                responsables = cursor.fetchall()

            solicitudes = []
            total = 0

            if not errores:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM solicitudes AS s
                    {where}
                    """,
                    parametros,
                )
                total = cursor.fetchone()["total"]

                cursor.execute(
                    f"""
                    SELECT
                        s.public_id,
                        s.rut,
                        s.nombre,
                        s.fecha_emision,
                        s.monto_bruto,
                        s.email_emisor,
                        e.nombre AS estado_nombre
                    FROM solicitudes AS s
                    INNER JOIN estados_solicitud AS e
                        ON e.id = s.estado_id
                    {where}
                    ORDER BY s.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    parametros + (por_pagina, offset),
                )
                solicitudes = cursor.fetchall()

    finally:
        connection.close()

    argumentos = {
        campo: valor
        for campo, valor in filtros.items()
        if valor
    }

    return render_template(
        "solicitudes/listado.html",
        solicitudes=solicitudes,
        filtros=filtros,
        errores=errores,
        estados=estados,
        responsables=responsables,
        es_admin=es_admin,
        total=total,
        pagina=pagina,
        anterior_url=(
            url_for(
                "solicitudes.listado",
                pagina=pagina - 1,
                **argumentos,
            )
            if pagina > 1
            else None
        ),
        siguiente_url=(
            url_for(
                "solicitudes.listado",
                pagina=pagina + 1,
                **argumentos,
            )
            if offset + por_pagina < total
            else None
        ),
    )


@solicitudes_bp.get("/<string:public_id>")
@solicitud_required
def detalle(public_id):
    solicitud = obtener_solicitud_autorizada(public_id)

    estados_permitidos = (
        TRANSICIONES_ESTADO.get(solicitud["estado_nombre"], ())
        if current_user.role_name == "Administrador"
        else ()
    )

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nombre_original, tamano, sha256, subido_en
                FROM registros_xml
                WHERE solicitud_id = %s
                """,
                (solicitud["id"],),
            )
            registro_xml = cursor.fetchone()

    finally:
        connection.close()

    return render_template(
        "solicitudes/detalle.html",
        solicitud=solicitud,
        registro_xml=registro_xml,
        estados_permitidos=estados_permitidos,
    )

@solicitudes_bp.post("/<string:public_id>/xml")
@solicitud_required
def cargar_xml(public_id):
    archivo = request.files.get("archivo_xml")

    if archivo is None:
        flash("Seleccione un archivo XML.", "danger")
    else:
        try:
            guardar_xml(
                actor_id=int(current_user.id),
                public_id=public_id,
                archivo=archivo,
                ip=request.remote_addr,
            )
        except ErrorArchivoXML as exc:
            flash(str(exc), "danger")
        except pymysql.MySQLError:
            current_app.logger.exception("Error de BD al cargar XML.")
            flash("No se pudo registrar el XML.", "danger")
        except OSError:
            current_app.logger.exception("Error al guardar el XML.")
            flash("No se pudo guardar el archivo.", "danger")
        else:
            flash("XML cargado correctamente.", "success")

    return redirect(url_for("solicitudes.detalle", public_id=public_id))


@solicitudes_bp.get("/<string:public_id>/xml/descargar")
@solicitud_required
def descargar_xml(public_id):
    try:
        actor, solicitud, registro_xml, ruta = obtener_xml_autorizado(
            actor_id=int(current_user.id),
            public_id=public_id,
        )
    except ErrorArchivoXML as exc:
        flash(str(exc), "danger")
        return redirect(url_for("solicitudes.detalle", public_id=public_id))

    connection = get_db_connection()

    try:
        registrar_evento(
            connection,
            actor["id"],
            "XML_DESCARGADO",
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": public_id,
                "registro_xml_id": registro_xml["id"],
                "sha256": registro_xml["sha256"],
            },
            request.remote_addr,
        )
        connection.commit()
    except pymysql.MySQLError:
        connection.rollback()
        current_app.logger.exception("No se pudo auditar la descarga.")
        flash("No se pudo registrar la descarga.", "danger")
        return redirect(url_for("solicitudes.detalle", public_id=public_id))
    finally:
        connection.close()

    return send_file(
        ruta,
        mimetype="application/xml",
        as_attachment=True,
        download_name=registro_xml["nombre_original"],
        max_age=0,
    )


@solicitudes_bp.route(
    "/<string:public_id>/editar",
    methods=["GET", "POST"],
)
@solicitud_required
def editar(public_id):
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT
                    s.*,
                    e.nombre AS estado_nombre
                FROM solicitudes AS s
                INNER JOIN estados_solicitud AS e
                    ON e.id = s.estado_id
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

    if solicitud["estado_nombre"] != "Pendiente":
        flash(
            "Solo se pueden editar solicitudes Pendientes.",
            "warning",
        )
        return redirect(url_for(
            "solicitudes.detalle",
            public_id=public_id,
        ))

    values = {
        campo: (
            str(solicitud[campo])
            if solicitud[campo] is not None
            else ""
        )
        for campo in CAMPOS_FORMULARIO
    }

    version = str(solicitud["version"])
    errores = {}

    if request.method == "POST":
        values = {
            campo: request.form.get(campo, "")
            for campo in CAMPOS_FORMULARIO
        }

        version = request.form.get("version", "")
        _, errores = validar_solicitud(values)

        if not errores:
            try:
                changed = editar_solicitud(
                    actor_id=int(current_user.id),
                    public_id=public_id,
                    datos=values,
                    version_esperada=version,
                    ip=request.remote_addr,
                )

            except ErrorGestionSolicitud as exc:
                errores["general"] = str(exc)

            except pymysql.MySQLError:
                current_app.logger.exception(
                    "Error al editar la solicitud %s",
                    public_id,
                )
                errores["general"] = (
                    "No se pudieron guardar los cambios. "
                    "Intente nuevamente."
                )

            else:
                flash(
                    "Solicitud actualizada correctamente."
                    if changed
                    else "No había cambios para guardar.",
                    "success" if changed else "info",
                )

                return redirect(url_for(
                    "solicitudes.detalle",
                    public_id=public_id,
                ))

    return render_template(
        "solicitudes/editar.html",
        solicitud=solicitud,
        values=values,
        errores=errores,
        version=version,
    )
    
@solicitudes_bp.post("/<string:public_id>/estado")
@solicitud_required
def cambiar_estado(public_id):
    if current_user.role_name != "Administrador":
        abort(403)

    try:
        cambiar_estado_solicitud(
            actor_id=int(current_user.id),
            public_id=public_id,
            estado_destino=request.form.get(
                "estado_destino",
                "",
            ),
            version_esperada=request.form.get(
                "version",
                "",
            ),
            motivo_rechazo=request.form.get(
                "motivo_rechazo",
                "",
            ),
            ip=request.remote_addr,
        )

    except ErrorGestionSolicitud as exc:
        flash(str(exc), "danger")

    except pymysql.MySQLError:
        current_app.logger.exception(
            "Error al cambiar el estado de la solicitud %s",
            public_id,
        )
        flash(
            "No se pudo cambiar el estado. Intente nuevamente.",
            "danger",
        )

    else:
        flash(
            "Estado actualizado correctamente.",
            "success",
        )

    return redirect(url_for(
        "solicitudes.detalle",
        public_id=public_id,
    ))