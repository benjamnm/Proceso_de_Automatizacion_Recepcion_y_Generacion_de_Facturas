from ..models import get_db_connection
from .usuarios import registrar_evento


class ErrorGestionCliente(Exception):
    pass


CAMPOS_CLIENTE = (
    "rut",
    "razon_social",
    "giro",
    "direccion",
    "email_contacto",
)


def comprobar_administrador(cursor, actor_id):
    cursor.execute(
        """
        SELECT id
        FROM roles
        WHERE nombre = %s
        FOR UPDATE
        """,
        ("Administrador",),
    )
    rol = cursor.fetchone()

    if rol is None:
        raise ErrorGestionCliente(
            "No existe el rol Administrador."
        )

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
        or actor["rol_id"] != rol["id"]
    ):
        raise ErrorGestionCliente(
            "Su cuenta no tiene autorización para esta operación."
        )


def guardar_cliente(actor_id, datos, cliente_id=None, ip=None):
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            comprobar_administrador(cursor, actor_id)

            anterior = None

            if cliente_id is not None:
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
                    FOR UPDATE
                    """,
                    (cliente_id,),
                )
                anterior = cursor.fetchone()

                if anterior is None:
                    raise ErrorGestionCliente(
                        "El cliente ya no existe."
                    )

                if datos["rut"] != anterior["rut"]:
                    raise ErrorGestionCliente(
                        "El RUT no puede cambiarse desde esta pantalla."
                    )

            cursor.execute(
                """
                SELECT id
                FROM clientes
                WHERE rut = %s
                """,
                (datos["rut"],),
            )
            existente = cursor.fetchone()

            if (
                existente is not None
                and existente["id"] != cliente_id
            ):
                raise ErrorGestionCliente(
                    "Ya existe un cliente con ese RUT."
                )

            if anterior is None:
                cursor.execute(
                    """
                    INSERT INTO clientes (
                        rut,
                        razon_social,
                        giro,
                        direccion,
                        email_contacto,
                        activo
                    )
                    VALUES (%s, %s, %s, %s, %s, 1)
                    """,
                    tuple(datos[campo] for campo in CAMPOS_CLIENTE),
                )

                cliente_id = cursor.lastrowid
                accion = "CLIENTE_CREADO"

                detalle = {
                    "cliente_afectado_id": cliente_id,
                    "datos_iniciales": {
                        campo: datos[campo]
                        for campo in CAMPOS_CLIENTE
                    },
                }

            else:
                cambios = {
                    campo: {
                        "anterior": anterior[campo],
                        "nuevo": datos[campo],
                    }
                    for campo in CAMPOS_CLIENTE
                    if anterior[campo] != datos[campo]
                }

                if not cambios:
                    connection.rollback()
                    return cliente_id, False

                cursor.execute(
                    """
                    UPDATE clientes
                    SET razon_social = %s,
                        giro = %s,
                        direccion = %s,
                        email_contacto = %s
                    WHERE id = %s
                    """,
                    (
                        datos["razon_social"],
                        datos["giro"],
                        datos["direccion"],
                        datos["email_contacto"],
                        cliente_id,
                    ),
                )

                accion = "CLIENTE_EDITADO"
                detalle = {
                    "cliente_afectado_id": cliente_id,
                    "cambios": cambios,
                }

        registrar_evento(
            connection,
            actor_id,
            accion,
            detalle,
            ip,
        )

        connection.commit()
        return cliente_id, True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()