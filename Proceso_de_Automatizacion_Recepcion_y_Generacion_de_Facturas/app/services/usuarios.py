import json

from email_validator import EmailNotValidError, validate_email

from ..models import get_db_connection


class ErrorGestionUsuario(Exception):
    pass


def registrar_evento(
    connection,
    actor_id,
    accion,
    detalle,
    ip=None,
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auditoria (
                usuario_id,
                accion,
                detalle,
                ip
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                actor_id,
                accion,
                json.dumps(detalle, ensure_ascii=False),
                ip,
            ),
        )


def snapshot(usuario):
    return {
        "id": usuario["id"],
        "nombre": usuario["nombre"],
        "email": usuario["email"],
        "rol_id": usuario["rol_id"],
        "activo": int(usuario["activo"]),
    }


def validar_datos(nombre, email, rol_id):
    nombre = nombre.strip()

    if not 2 <= len(nombre) <= 120:
        raise ErrorGestionUsuario(
            "El nombre debe tener entre 2 y 120 caracteres."
        )

    try:
        resultado = validate_email(
            email.strip(),
            check_deliverability=False,
        )
        email = resultado.normalized.lower()
    except EmailNotValidError:
        raise ErrorGestionUsuario(
            "Ingrese un correo electrónico válido."
        )

    if len(email) > 150:
        raise ErrorGestionUsuario(
            "El correo no puede superar 150 caracteres."
        )

    try:
        rol_id = int(rol_id)
    except (TypeError, ValueError):
        raise ErrorGestionUsuario("Seleccione un rol válido.")

    return nombre, email, rol_id


def modificar_usuario(
    actor_id,
    usuario_id,
    operacion,
    datos=None,
    ip=None,
):
    if operacion not in {"editar", "estado"}:
        raise ErrorGestionUsuario("Operación no permitida.")

    if operacion == "editar":
        nombre, email, nuevo_rol_id = validar_datos(
            datos.get("nombre", ""),
            datos.get("email", ""),
            datos.get("rol_id", ""),
        )
    else:
        estado = datos.get("activo")

        if estado not in {"0", "1"}:
            raise ErrorGestionUsuario("Estado no válido.")

        nuevo_estado = int(estado)

    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            # Todas las modificaciones de este servicio
            # adquieren primero el mismo bloqueo.
            cursor.execute(
                """
                SELECT id
                FROM roles
                WHERE nombre = %s
                FOR UPDATE
                """,
                ("Administrador",),
            )
            rol_admin = cursor.fetchone()

            if rol_admin is None:
                raise ErrorGestionUsuario(
                    "No existe el rol Administrador."
                )

            admin_role_id = rol_admin["id"]

            cursor.execute(
                """
                SELECT id, rol_id, activo
                FROM usuarios
                WHERE id = %s
                FOR UPDATE
                """,
                (actor_id,),
            )
            actor = cursor.fetchone()

            if (
                actor is None
                or not actor["activo"]
                or actor["rol_id"] != admin_role_id
            ):
                raise ErrorGestionUsuario(
                    "Su cuenta no tiene autorización para esta operación."
                )

            cursor.execute(
                """
                SELECT id, nombre, email, rol_id, activo
                FROM usuarios
                WHERE id = %s
                FOR UPDATE
                """,
                (usuario_id,),
            )
            usuario = cursor.fetchone()

            if usuario is None:
                raise ErrorGestionUsuario(
                    "El usuario ya no existe."
                )

            anterior = snapshot(usuario)
            nuevo = dict(anterior)

            if operacion == "editar":
                cursor.execute(
                    "SELECT id FROM roles WHERE id = %s",
                    (nuevo_rol_id,),
                )

                if cursor.fetchone() is None:
                    raise ErrorGestionUsuario(
                        "El rol seleccionado no existe."
                    )

                if (
                    actor_id == usuario_id
                    and nuevo_rol_id != usuario["rol_id"]
                ):
                    raise ErrorGestionUsuario(
                        "No puede cambiar su propio rol."
                    )

                cursor.execute(
                    """
                    SELECT id
                    FROM usuarios
                    WHERE email = %s AND id <> %s
                    """,
                    (email, usuario_id),
                )

                if cursor.fetchone() is not None:
                    raise ErrorGestionUsuario(
                        "El correo pertenece a otra cuenta."
                    )

                nuevo.update(
                    nombre=nombre,
                    email=email,
                    rol_id=nuevo_rol_id,
                )

                accion = "USUARIO_EDITADO"

            else:
                if actor_id == usuario_id and nuevo_estado == 0:
                    raise ErrorGestionUsuario(
                        "No puede desactivar su propia cuenta."
                    )

                nuevo["activo"] = nuevo_estado

                accion = (
                    "USUARIO_REACTIVADO"
                    if nuevo_estado == 1
                    else "USUARIO_DESACTIVADO"
                )

            pierde_admin_activo = (
                anterior["activo"] == 1
                and anterior["rol_id"] == admin_role_id
                and (
                    nuevo["activo"] == 0
                    or nuevo["rol_id"] != admin_role_id
                )
            )

            if pierde_admin_activo:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM usuarios
                    WHERE rol_id = %s AND activo = 1
                    """,
                    (admin_role_id,),
                )

                if cursor.fetchone()["total"] <= 1:
                    raise ErrorGestionUsuario(
                        "Debe permanecer al menos un Administrador activo."
                    )

            if anterior == nuevo:
                connection.rollback()
                return False

            cursor.execute(
                """
                UPDATE usuarios
                SET nombre = %s,
                    email = %s,
                    rol_id = %s,
                    activo = %s
                WHERE id = %s
                """,
                (
                    nuevo["nombre"],
                    nuevo["email"],
                    nuevo["rol_id"],
                    nuevo["activo"],
                    usuario_id,
                ),
            )

        cambios = {
            campo: {
                "anterior": anterior[campo],
                "nuevo": nuevo[campo],
            }
            for campo in ("nombre", "email", "rol_id", "activo")
            if anterior[campo] != nuevo[campo]
        }

        registrar_evento(
            connection,
            actor_id,
            accion,
            {
                "usuario_afectado_id": usuario_id,
                "cambios": cambios,
            },
            ip,
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()