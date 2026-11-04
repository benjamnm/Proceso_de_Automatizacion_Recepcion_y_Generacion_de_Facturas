import pymysql
import json

from email_validator import EmailNotValidError, validate_email
from flask import (
    current_app,
    send_file,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    abort,
)
from flask_login import current_user

from ..services.usuarios import (
    ErrorGestionUsuario,
    modificar_usuario,
    registrar_evento,
)

from werkzeug.security import generate_password_hash

from ..services.correo_entrante import (
    ErrorCorreoEntrante,
    descartar_correo,
    listar_correos,
    obtener_eml_autorizado,
    reprocesar_correo,
    revisar_bandeja,
)

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
                        
                        nuevo_usuario_id = cursor.lastrowid
                        registrar_evento(
                            connection,
                            int(current_user.id),
                            "USUARIO_CREADO",
                            {
                                "usuario_afectado_id": nuevo_usuario_id,
                                "datos_iniciales": {
                                    "nombre": values["nombre"],
                                    "email": values["email"],
                                    "rol_id": role_id,
                                    "activo": 1,
                                },
                            },
                            request.remote_addr,
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
        
@admin_bp.route(
    "/usuarios/<int:usuario_id>/editar",
    methods=["GET", "POST"],
)
@admin_required
def usuario_editar(usuario_id):
    connection = get_db_connection()
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id,  nombre, email, rol_id, activo
                FROM usuarios
                WHERE id = %s
                """,
                (usuario_id,),
            )
            usuario = cursor.fetchone()
            
            if usuario is None:
                abort(404, description="Usuario no encontrado.")
                
            cursor.execute(
                "SELECT id, nombre FROM roles ORDER BY nombre"
            )
            roles = cursor.fetchall()
    finally:
        connection.close()
    
    error = None
    values = {
        "nombre": usuario["nombre"],
        "email": usuario["email"],
        "rol_id": str(usuario["rol_id"])
    }
    
    if request.method == "POST":
        values = {
            "nombre": request.form.get("nombre", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "rol_id": request.form.get("rol_id", ""),
        }
        
        try:
            changed = modificar_usuario(
                actor_id=int(current_user.id),
                usuario_id=usuario_id,
                operacion="editar",
                datos=values,
                ip=request.remote_addr,
            )
        
        except ErrorGestionUsuario as exc:
            error = str(exc)
        
        except pymysql.err.IntegrityError:
            error = ( 
                "No se pudo guardar, reintente nuevamente. "
                "Compruebe que el correo no esté registrado."
            )
        
        except pymysql.MySQLError:
            current_app.logger.exception(
                "Error al editar el usuario %s", usuario_id,
            )
            error = "Error en la base de datos. Intente nuevamente."
        else:
            flash("Usuario editado correctamente."
                  if changed
                  else "No se realizaron cambios.", "success" if changed else "info",
                  )
            return redirect(url_for("admin.usuarios"))
    return render_template(
        "admin/usuario_editar.html",
        usuario=usuario,
        roles=roles,
        values=values,
        error=error,
    )

@admin_bp.post("/usuarios/<int:usuario_id>/estado")
@admin_required
def usuario_estado(usuario_id):
    try:
        changed = modificar_usuario(
            actor_id=int(current_user.id),
            usuario_id=usuario_id,
            operacion="estado",
            datos={
                "activo": request.form.get("activo")
            },
            ip=request.remote_addr,
        )
    
    except ErrorGestionUsuario as exc:
        flash(str(exc), "danger")
        
    except pymysql.MySQLError:
        current_app.logger.exception(
            "Error al cambiar el estado del usuario %s", usuario_id,
        )
        flash(
            "No se logro cambiar el estado, reintente nuevamente.", "danger",
        )
        
    else:
        flash(
            "Estado actualizado correctamente."
            if changed
            else "La cuenta ya tenia ese estado.",
            "success" if changed else "info",
        )
    
    return redirect(url_for("admin.usuarios"))

@admin_bp.get("/auditoria")
@admin_required
def auditoria():
    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.accion,
                    a.detalle,
                    a.ip,
                    a.creado_en,
                    u.nombre AS usuario_nombre
                FROM auditoria AS a
                LEFT JOIN usuarios AS u
                    ON u.id = a.usuario_id
                WHERE a.accion IN (
                    'USUARIO_CREADO',
                    'USUARIO_EDITADO',
                    'USUARIO_DESACTIVADO',
                    'USUARIO_REACTIVADO',
                    'CLIENTE_CREADO',
                    'CLIENTE_EDITADO',
                    'SOLICITUD_CREADA',
                    'SOLICITUD_EDITADA',
                    'SOLICITUD_ESTADO_CAMBIADO',
                    'XML_CARGADO',
                    'XML_REEMPLAZADO',
                    'XML_DESCARGADO',
                    'CORREO_ENVIADO',
                    'CORREO_FALLIDO',
                    'CORREO_RECIBIDO',
                    'CORREO_REQUIERE_REVISION',
                    'CORREO_REPROCESADO',
                    'CORREO_DESCARTADO',
                    'CORREO_ENTRANTE_DESCARGADO',
                    'FACTURA_GENERADA',
                    'FACTURA_OBSERVADA',
                    'FACTURA_APROBADA',
                    'ARCHIVO_SII_DESCARGADO',
                    'NOTIFICACION_ENVIADA',
                    'NOTIFICACION_FALLIDA'
                )
                ORDER BY a.id DESC
                LIMIT 100
                """
            )
            eventos = cursor.fetchall()

        for evento in eventos:
            detalle = evento["detalle"]

            if isinstance(detalle, (str, bytes)):
                detalle = json.loads(detalle)

            evento["detalle"] = detalle

    finally:
        connection.close()

    return render_template(
        "admin/auditoria.html",
        eventos=eventos,
    )


# --- Bandeja de correos entrantes ----------------------------------------

ESTADOS_CORREO = (
    "RECIBIDO", "PROCESADO", "REQUIERE_REVISION", "DESCARTADO", "ERROR",
)


@admin_bp.get("/correos")
@admin_required
def correos():
    estado = request.args.get("estado", "")
    if estado and estado not in ESTADOS_CORREO:
        estado = ""

    return render_template(
        "admin/correos.html",
        correos=listar_correos(estado or None),
        estado=estado,
        estados=ESTADOS_CORREO,
        imap_configurado=bool(current_app.config.get("IMAP_HOST")),
    )


@admin_bp.post("/correos/revisar")
@admin_required
def correos_revisar():
    try:
        resultado = revisar_bandeja()
    except ErrorCorreoEntrante as exc:
        flash(str(exc), "warning")
    except pymysql.MySQLError:
        current_app.logger.exception("Error de BD al revisar la bandeja")
        flash("No se pudo revisar la bandeja. Intente nuevamente.", "danger")
    else:
        if resultado["error_descarga"]:
            flash(f"Bandeja IMAP: {resultado['error_descarga']}", "danger")
        if resultado["descarga"]:
            d = resultado["descarga"]
            flash(
                f"Correos revisados: {d['revisados']} · de facturación "
                f"guardados: {d['guardados']} · ignorados: {d['ignorados']} · "
                f"omitidos por tamaño: {d['omitidos_tamano']}.",
                "info",
            )
        p = resultado["proceso"]
        flash(
            f"Facturas generadas: {p['procesados']} · requieren revisión: "
            f"{p['requieren_revision']} · errores: {p['errores']} · avisos "
            f"enviados: {p['avisos_enviados']}.",
            "success" if not p["errores"] else "warning",
        )

    return redirect(url_for("admin.correos"))


@admin_bp.post("/correos/<int:correo_id>/reprocesar")
@admin_required
def correo_reprocesar(correo_id):
    try:
        resultado = reprocesar_correo(
            int(current_user.id), correo_id, request.remote_addr
        )
    except ErrorCorreoEntrante as exc:
        flash(str(exc), "danger")
    except pymysql.MySQLError:
        current_app.logger.exception("Error al reprocesar el correo %s", correo_id)
        flash("No se pudo reprocesar el correo.", "danger")
    else:
        if resultado["estado"] == "PROCESADO":
            flash("Factura generada desde el correo.", "success")
            return redirect(url_for(
                "solicitudes.factura", public_id=resultado["public_id"]
            ))
        flash(
            "El correo sigue requiriendo revisión: "
            + " ".join(resultado["motivos"]),
            "warning",
        )

    return redirect(url_for("admin.correos"))


@admin_bp.post("/correos/<int:correo_id>/descartar")
@admin_required
def correo_descartar(correo_id):
    try:
        descartar_correo(
            int(current_user.id), correo_id,
            request.form.get("motivo", ""), request.remote_addr,
        )
    except ErrorCorreoEntrante as exc:
        flash(str(exc), "danger")
    except pymysql.MySQLError:
        current_app.logger.exception("Error al descartar el correo %s", correo_id)
        flash("No se pudo descartar el correo.", "danger")
    else:
        flash("Correo descartado.", "success")

    return redirect(url_for("admin.correos"))


@admin_bp.get("/correos/<int:correo_id>/eml")
@admin_required
def correo_eml(correo_id):
    try:
        actor, correo, ruta = obtener_eml_autorizado(int(current_user.id), correo_id)
    except ErrorCorreoEntrante as exc:
        flash(str(exc), "danger")
        return redirect(url_for("admin.correos"))

    connection = get_db_connection()
    try:
        registrar_evento(
            connection, actor["id"], "CORREO_ENTRANTE_DESCARGADO",
            {"correo_entrante_id": correo_id, "sha256": correo["sha256"]},
            request.remote_addr,
        )
        connection.commit()
    except pymysql.MySQLError:
        connection.rollback()
        current_app.logger.exception("No se pudo auditar la descarga del .eml.")
        flash("No se pudo registrar la descarga.", "danger")
        return redirect(url_for("admin.correos"))
    finally:
        connection.close()

    # Se entrega como descarga (nunca se renderiza en el navegador).
    return send_file(
        ruta,
        mimetype="message/rfc822",
        as_attachment=True,
        download_name=f"correo_{correo_id}.eml",
        max_age=0,
    )
