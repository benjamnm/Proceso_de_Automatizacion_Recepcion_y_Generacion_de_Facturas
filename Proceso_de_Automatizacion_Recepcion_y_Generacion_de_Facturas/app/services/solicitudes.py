import secrets

from ..models import get_db_connection
from .usuarios import registrar_evento
from .validaciones import validar_cliente


class ErrorGestionSolicitud(Exception):
    pass


def crear_solicitud(actor_id, datos, ip=None):
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            # Conserva el orden de bloqueo usado en los otros módulos.
            cursor.execute(
                """
                SELECT id
                FROM roles
                WHERE nombre = %s
                FOR UPDATE
                """,
                ("Administrador",),
            )

            if cursor.fetchone() is None:
                raise ErrorGestionSolicitud(
                    "No existe el rol Administrador."
                )

            cursor.execute(
                """
                SELECT id, rol_id, email, activo
                FROM usuarios
                WHERE id = %s
                FOR UPDATE
                """,
                (actor_id,),
            )
            actor = cursor.fetchone()

            if actor is None or not actor["activo"]:
                raise ErrorGestionSolicitud(
                    "Su cuenta no está disponible."
                )

            cursor.execute(
                "SELECT nombre FROM roles WHERE id = %s",
                (actor["rol_id"],),
            )
            rol = cursor.fetchone()

            if (
                rol is None
                or rol["nombre"] not in {"Administrador", "Emisor"}
            ):
                raise ErrorGestionSolicitud(
                    "No tiene autorización para crear solicitudes."
                )

            cursor.execute(
                """
                SELECT
                    id,
                    rut,
                    razon_social,
                    giro,
                    direccion,
                    email_contacto,
                    activo
                FROM clientes
                WHERE id = %s
                FOR UPDATE
                """,
                (datos["cliente_id"],),
            )
            cliente = cursor.fetchone()

            if cliente is None or not cliente["activo"]:
                raise ErrorGestionSolicitud(
                    "El cliente no existe o está inactivo."
                )

            receptor, errores_cliente = validar_cliente(cliente)

            if errores_cliente:
                raise ErrorGestionSolicitud(
                    "La ficha del cliente contiene datos inválidos. "
                    "Un Administrador debe corregirla antes de continuar."
                )

            cursor.execute(
                """
                SELECT id
                FROM estados_solicitud
                WHERE nombre = %s
                """,
                ("Pendiente",),
            )
            estado = cursor.fetchone()

            cursor.execute(
                """
                SELECT id
                FROM origenes_solicitud
                WHERE nombre = %s
                """,
                ("Web",),
            )
            origen = cursor.fetchone()

            if estado is None or origen is None:
                raise ErrorGestionSolicitud(
                    "Faltan los catálogos Pendiente o Web."
                )

            public_id = secrets.token_hex(16)

            cursor.execute(
                """
                INSERT INTO solicitudes (
                    public_id,
                    emisor_id,
                    cliente_id,
                    estado_id,
                    origen_id,
                    rut,
                    nombre,
                    direccion,
                    giro,
                    email_contacto_receptor,
                    concepto,
                    nro_orden_compra,
                    fecha_emision,
                    monto_bruto,
                    tipo_afectacion,
                    email_emisor
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    public_id,
                    actor_id,
                    cliente["id"],
                    estado["id"],
                    origen["id"],
                    receptor["rut"],
                    receptor["razon_social"],
                    receptor["direccion"],
                    receptor["giro"],
                    receptor["email_contacto"],
                    datos["concepto"],
                    datos["nro_orden_compra"],
                    datos["fecha_emision"],
                    datos["monto_bruto"],
                    datos["tipo_afectacion"],
                    actor["email"],
                ),
            )

            solicitud_id = cursor.lastrowid

        registrar_evento(
            connection,
            actor_id,
            "SOLICITUD_CREADA",
            {
                "solicitud_afectada_id": solicitud_id,
                "public_id": public_id,
                "cliente_id": cliente["id"],
                "estado": "Pendiente",
                "origen": "Web",
                "monto_bruto": str(datos["monto_bruto"]),
                "tipo_afectacion": datos["tipo_afectacion"],
            },
            ip,
        )

        connection.commit()
        return public_id

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()