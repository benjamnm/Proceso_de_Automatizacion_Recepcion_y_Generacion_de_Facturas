import re

import pymysql
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
    ESTADOS_CAMBIO_DIRECTO,
    ESTADOS_EDITABLES,
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
from ..services.dte_sii import advertencias as advertencias_dte
from ..services.facturas import (
    ErrorFactura,
    aprobar_factura,
    enviar_a_revision,
    listar_versiones,
    obtener_archivo_sii,
    observar_factura,
)
from ..services.notificaciones import (
    notificar_factura_aprobada,
    notificar_factura_generada,
)
from ..services.correos_solicitud import (
    ESTADOS_QUE_ADMITEN_ENVIO,
    ErrorEnvioCorreo,
    enviar_xml_solicitud,
    listar_envios,
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
        tuple(
            estado
            for estado in TRANSICIONES_ESTADO.get(solicitud["estado_nombre"], ())
            if estado in ESTADOS_CAMBIO_DIRECTO
        )
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

            cursor.execute(
                """
                SELECT version, estado
                FROM facturas
                WHERE solicitud_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (solicitud["id"],),
            )
            factura_actual = cursor.fetchone()

    finally:
        connection.close()

    return render_template(
        "solicitudes/detalle.html",
        solicitud=solicitud,
        registro_xml=registro_xml,
        factura_actual=factura_actual,
        editable=solicitud["estado_nombre"] in ESTADOS_EDITABLES,
        estados_permitidos=estados_permitidos,
        envios=listar_envios(solicitud["id"]),
        permite_envio=(
            registro_xml is not None
            and solicitud["estado_nombre"] in ESTADOS_QUE_ADMITEN_ENVIO
            and bool(solicitud["email_contacto_receptor"])
        ),
    )


@solicitudes_bp.post("/<string:public_id>/correo")
@solicitud_required
def enviar_correo(public_id):
    try:
        resultado = enviar_xml_solicitud(
            actor_id=int(current_user.id),
            public_id=public_id,
            ip=request.remote_addr,
        )

    except ErrorEnvioCorreo as exc:
        flash(str(exc), "danger")

    except pymysql.MySQLError:
        current_app.logger.exception(
            "Error de BD al preparar el envío de %s", public_id
        )
        flash("No se pudo preparar el envío. Intente nuevamente.", "danger")

    else:
        if resultado["estado"] == "ENVIADO":
            flash(
                f"XML enviado a {resultado['destinatario']}.",
                "success",
            )
        else:
            flash(
                f"El envío falló: {resultado['mensaje']}",
                "danger",
            )

        if not resultado["registrado"]:
            flash(
                "No se pudo registrar el resultado del envío. "
                "Revise el historial antes de reintentar.",
                "warning",
            )

    return redirect(url_for("solicitudes.detalle", public_id=public_id))


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
    solicitud = obtener_solicitud_autorizada(public_id)

    if solicitud["estado_nombre"] not in ESTADOS_EDITABLES:
        flash(
            "Solo se pueden editar solicitudes Pendientes o En corrección.",
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
        values = leer_formulario()
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

                destino = (
                    "solicitudes.factura"
                    if solicitud["estado_nombre"] == "En corrección"
                    else "solicitudes.detalle"
                )
                return redirect(url_for(destino, public_id=public_id))

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


def _error_bd(mensaje, public_id):
    current_app.logger.exception("%s (%s)", mensaje, public_id)
    flash(f"{mensaje}. Intente nuevamente.", "danger")


@solicitudes_bp.get("/<string:public_id>/factura")
@solicitud_required
def factura(public_id):
    solicitud = obtener_solicitud_autorizada(public_id)
    versiones, correo = listar_versiones(solicitud["id"])
    vigente = versiones[0] if versiones else None

    return render_template(
        "solicitudes/factura.html",
        solicitud=solicitud,
        versiones=versiones,
        vigente=vigente,
        correo=correo,
        advertencias=advertencias_dte(vigente["datos"]) if vigente else [],
        es_admin=current_user.role_name == "Administrador",
        editable=solicitud["estado_nombre"] in ESTADOS_EDITABLES,
        emisor_configurado=all(
            str(current_app.config.get(c) or "").strip()
            for c in ("EMPRESA_RUT", "EMPRESA_RAZON_SOCIAL", "EMPRESA_GIRO",
                      "EMPRESA_ACTECO", "EMPRESA_DIRECCION", "EMPRESA_COMUNA")
        ),
    )


@solicitudes_bp.post("/<string:public_id>/factura/revision")
@solicitud_required
def factura_revision(public_id):
    try:
        resultado = enviar_a_revision(
            actor_id=int(current_user.id),
            public_id=public_id,
            version_esperada=request.form.get("version", ""),
            ip=request.remote_addr,
        )
    except (ErrorFactura, ErrorGestionSolicitud) as exc:
        flash(str(exc), "danger")
    except pymysql.MySQLError:
        _error_bd("No se pudo generar la factura", public_id)
    else:
        flash(
            f"Factura versión {resultado['version']} generada y enviada a "
            f"revisión.",
            "success",
        )
        if resultado["notificar"]:
            aviso = notificar_factura_generada(
                int(current_user.id), resultado["solicitud_id"],
                request.remote_addr,
            )
            if aviso["error"] or aviso["fallidos"]:
                flash(
                    "La factura quedó guardada, pero no se pudo avisar al "
                    "Administrador por correo.",
                    "warning",
                )

    return redirect(url_for("solicitudes.factura", public_id=public_id))


@solicitudes_bp.post("/<string:public_id>/factura/aprobar")
@solicitud_required
def factura_aprobar(public_id):
    if current_user.role_name != "Administrador":
        abort(403)

    try:
        version = aprobar_factura(
            actor_id=int(current_user.id),
            public_id=public_id,
            version_esperada=request.form.get("version", ""),
            ip=request.remote_addr,
        )
    except ErrorFactura as exc:
        flash(str(exc), "danger")
    except pymysql.MySQLError:
        _error_bd("No se pudo aprobar la factura", public_id)
    except OSError:
        current_app.logger.exception("No se pudo escribir el DTE")
        flash("No se pudo guardar el archivo para el SII.", "danger")
    else:
        flash(
            f"Factura versión {version} validada. "
            f"El archivo para el SII está disponible.",
            "success",
        )
        aviso = notificar_factura_aprobada(
            int(current_user.id), public_id, request.remote_addr,
        )
        if aviso["error"] or aviso["fallidos"]:
            flash(
                "La factura quedó validada, pero no se pudo enviar el "
                f"archivo SII por correo: {aviso['error'] or 'falló el envío'}. "
                "Puede descargarlo desde esta pantalla.",
                "warning",
            )
        else:
            flash(
                f"Archivo SII enviado por correo a {aviso['enviados']} "
                "destinatario(s).",
                "info",
            )

    return redirect(url_for("solicitudes.factura", public_id=public_id))


@solicitudes_bp.post("/<string:public_id>/factura/observar")
@solicitud_required
def factura_observar(public_id):
    if current_user.role_name != "Administrador":
        abort(403)

    try:
        version = observar_factura(
            actor_id=int(current_user.id),
            public_id=public_id,
            version_esperada=request.form.get("version", ""),
            observacion=request.form.get("observacion", ""),
            ip=request.remote_addr,
        )
    except ErrorFactura as exc:
        flash(str(exc), "danger")
    except pymysql.MySQLError:
        _error_bd("No se pudo registrar la observación", public_id)
    else:
        flash(
            f"Versión {version} devuelta a corrección. Corrija los datos y "
            f"reenvíela para generar la versión {version + 1}.",
            "info",
        )

    return redirect(url_for("solicitudes.factura", public_id=public_id))


@solicitudes_bp.get("/<string:public_id>/factura/sii")
@solicitud_required
def descargar_sii(public_id):
    if current_user.role_name != "Administrador":
        abort(403)

    try:
        actor, fila, ruta = obtener_archivo_sii(int(current_user.id), public_id)
    except ErrorFactura as exc:
        flash(str(exc), "danger")
        return redirect(url_for("solicitudes.factura", public_id=public_id))

    connection = get_db_connection()
    try:
        registrar_evento(
            connection, actor["id"], "ARCHIVO_SII_DESCARGADO",
            {
                "solicitud_afectada_id": fila["id"],
                "public_id": public_id,
                "factura_id": fila["factura_id"],
                "version_factura": fila["version"],
                "sha256": fila["archivo_sii_sha256"],
            },
            request.remote_addr,
        )
        connection.commit()
    except pymysql.MySQLError:
        connection.rollback()
        current_app.logger.exception("No se pudo auditar la descarga SII.")
        flash("No se pudo registrar la descarga.", "danger")
        return redirect(url_for("solicitudes.factura", public_id=public_id))
    finally:
        connection.close()

    return send_file(
        ruta,
        mimetype="application/xml",
        as_attachment=True,
        download_name=(
            f"DTE_{fila['tipo_dte']}_{public_id[:8]}_v{fila['version']}.xml"
        ),
        max_age=0,
    )
