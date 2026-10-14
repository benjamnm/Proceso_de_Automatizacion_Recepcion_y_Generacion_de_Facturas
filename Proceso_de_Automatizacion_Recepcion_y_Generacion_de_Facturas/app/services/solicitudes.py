import hashlib
import json
import re
import secrets

from datetime import date
from decimal import Decimal

from ..models import get_db_connection
from .usuarios import registrar_evento
from .validaciones import validar_cliente


class ErrorGestionSolicitud(Exception):
    pass


def validar_solicitud(datos):
    limpio = {}
    errores = {}

    cliente_id = str(datos.get("cliente_id", "")).strip()

    if not re.fullmatch(r"[0-9]{1,10}", cliente_id):
        errores["cliente_id"] = "Seleccione un cliente válido."
    elif not 1 <= int(cliente_id) <= 4294967295:
        errores["cliente_id"] = "Seleccione un cliente válido."
    else:
        limpio["cliente_id"] = int(cliente_id)

    concepto = str(datos.get("concepto", "")).strip()

    if not concepto:
        errores["concepto"] = "Ingrese el concepto de facturación."
    elif len(concepto) > 500:
        errores["concepto"] = (
            "El concepto no puede superar 500 caracteres."
        )
    else:
        limpio["concepto"] = concepto

    monto = str(datos.get("monto_bruto", "")).strip()

    if not re.fullmatch(r"[0-9]{1,14}", monto):
        errores["monto_bruto"] = (
            "Ingrese un monto entero de hasta 14 dígitos, "
            "sin puntos ni comas."
        )
    elif Decimal(monto) <= 0:
        errores["monto_bruto"] = "El monto debe ser mayor que cero."
    else:
        limpio["monto_bruto"] = Decimal(monto)

    fecha_principal = datos.get("fecha_emision")
    fecha_alternativa = datos.get("fecha_emision_solicitada")

    if (
        fecha_principal is not None
        and fecha_alternativa is not None
        and str(fecha_principal) != str(fecha_alternativa)
    ):
        errores["fecha_emision"] = (
            "Se recibieron dos fechas de emisión diferentes."
        )
    else:
        fecha = (
            fecha_principal
            if fecha_principal is not None
            else fecha_alternativa
        )

        fecha = str(fecha or "").strip()

        try:
            if not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                fecha,
            ):
                raise ValueError

            limpio["fecha_emision"] = date.fromisoformat(fecha)

        except ValueError:
            errores["fecha_emision"] = "Ingrese una fecha válida."

    afectacion = datos.get("tipo_afectacion", "")

    if afectacion not in {"AFECTA", "EXENTA"}:
        errores["tipo_afectacion"] = (
            "Seleccione una afectación tributaria válida."
        )
    else:
        limpio["tipo_afectacion"] = afectacion

    orden = str(datos.get("nro_orden_compra") or "").strip()

    if len(orden) > 40:
        errores["nro_orden_compra"] = (
            "La orden de compra no puede superar 40 caracteres."
        )
    else:
        limpio["nro_orden_compra"] = orden or None

    return limpio, errores


def huella_de_creacion(datos):
    contenido = {
        "cliente_id": datos["cliente_id"],
        "concepto": datos["concepto"],
        "monto_bruto": str(datos["monto_bruto"]),
        "fecha_emision": datos["fecha_emision"].isoformat(),
        "tipo_afectacion": datos["tipo_afectacion"],
        "nro_orden_compra": datos["nro_orden_compra"],
    }

    serializado = json.dumps(
        contenido,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serializado.encode("utf-8")
    ).hexdigest()


def comprobar_actor(cursor, actor_id):
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
            "No tiene autorización para esta operación."
        )

    actor["rol_nombre"] = rol["nombre"]
    return actor


def crear_solicitud(
    actor_id,
    datos,
    clave_idempotencia,
    ip=None,
):
    limpio, errores = validar_solicitud(datos)

    if errores:
        raise ErrorGestionSolicitud(
            " ".join(errores.values())
        )

    if (
        not isinstance(clave_idempotencia, str)
        or not re.fullmatch(
            r"[0-9a-f]{32}",
            clave_idempotencia,
        )
    ):
        raise ErrorGestionSolicitud(
            "La clave de creación no es válida."
        )

    huella = huella_de_creacion(limpio)
    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = comprobar_actor(cursor, actor_id)

            cursor.execute(
                """
                SELECT public_id, huella_creacion
                FROM solicitudes
                WHERE emisor_id = %s
                  AND clave_idempotencia = %s
                FOR UPDATE
                """,
                (actor["id"], clave_idempotencia),
            )
            existente = cursor.fetchone()

            if existente is not None:
                if existente["huella_creacion"] != huella:
                    raise ErrorGestionSolicitud(
                        "Este formulario ya se utilizó con otros datos. "
                        "Abra una solicitud nueva."
                    )

                connection.rollback()
                return existente["public_id"]

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
                (limpio["cliente_id"],),
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
                    "Debe corregirse antes de continuar."
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

            registro = {
                "public_id": secrets.token_hex(16),
                "emisor_id": actor["id"],
                "cliente_id": cliente["id"],
                "estado_id": estado["id"],
                "origen_id": origen["id"],
                "rut": receptor["rut"],
                "nombre": receptor["razon_social"],
                "direccion": receptor["direccion"],
                "giro": receptor["giro"],
                "email_contacto_receptor": receptor["email_contacto"],
                "concepto": limpio["concepto"],
                "nro_orden_compra": limpio["nro_orden_compra"],
                "fecha_emision": limpio["fecha_emision"],
                "monto_bruto": limpio["monto_bruto"],
                "tipo_afectacion": limpio["tipo_afectacion"],
                "email_emisor": actor["email"],
                "clave_idempotencia": clave_idempotencia,
                "huella_creacion": huella,
            }

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
                    email_emisor,
                    clave_idempotencia,
                    huella_creacion
                )
                VALUES (
                    %(public_id)s,
                    %(emisor_id)s,
                    %(cliente_id)s,
                    %(estado_id)s,
                    %(origen_id)s,
                    %(rut)s,
                    %(nombre)s,
                    %(direccion)s,
                    %(giro)s,
                    %(email_contacto_receptor)s,
                    %(concepto)s,
                    %(nro_orden_compra)s,
                    %(fecha_emision)s,
                    %(monto_bruto)s,
                    %(tipo_afectacion)s,
                    %(email_emisor)s,
                    %(clave_idempotencia)s,
                    %(huella_creacion)s
                )
                """,
                registro,
            )

            solicitud_id = cursor.lastrowid

        registrar_evento(
            connection,
            actor["id"],
            "SOLICITUD_CREADA",
            {
                "solicitud_afectada_id": solicitud_id,
                "public_id": registro["public_id"],
                "cliente_id": cliente["id"],
                "estado": "Pendiente",
                "origen": "Web",
                "concepto": limpio["concepto"],
                "monto_bruto": str(limpio["monto_bruto"]),
                "fecha_emision": limpio["fecha_emision"].isoformat(),
                "tipo_afectacion": limpio["tipo_afectacion"],
                "nro_orden_compra": limpio["nro_orden_compra"],
                "receptor_historico": {
                    "rut": receptor["rut"],
                    "nombre": receptor["razon_social"],
                    "direccion": receptor["direccion"],
                    "giro": receptor["giro"],
                    "email": receptor["email_contacto"],
                },
            },
            ip,
        )

        connection.commit()
        return registro["public_id"]

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def editar_solicitud(
    actor_id,
    public_id,
    datos,
    version_esperada,
    ip=None,
):
    limpio, errores = validar_solicitud(datos)

    if errores:
        raise ErrorGestionSolicitud(
            " ".join(errores.values())
        )

    try:
        version_esperada = int(version_esperada)

        if version_esperada <= 0:
            raise ValueError

    except (TypeError, ValueError):
        raise ErrorGestionSolicitud(
            "La versión del formulario no es válida."
        )

    connection = get_db_connection()

    try:
        connection.begin()

        with connection.cursor() as cursor:
            actor = comprobar_actor(cursor, actor_id)

            cursor.execute(
                """
                SELECT *
                FROM solicitudes
                WHERE public_id = %s
                FOR UPDATE
                """,
                (public_id,),
            )
            solicitud = cursor.fetchone()

            if solicitud is None:
                raise ErrorGestionSolicitud(
                    "La solicitud no está disponible."
                )

            if (
                actor["rol_nombre"] != "Administrador"
                and solicitud["emisor_id"] != actor["id"]
            ):
                raise ErrorGestionSolicitud(
                    "La solicitud no está disponible."
                )

            cursor.execute(
                """
                SELECT nombre
                FROM estados_solicitud
                WHERE id = %s
                FOR UPDATE
                """,
                (solicitud["estado_id"],),
            )
            estado = cursor.fetchone()

            if estado is None or estado["nombre"] != "Pendiente":
                raise ErrorGestionSolicitud(
                    "Solo se pueden editar solicitudes Pendientes."
                )

            if solicitud["version"] != version_esperada:
                raise ErrorGestionSolicitud(
                    "La solicitud cambió desde que abrió el formulario. "
                    "Recargue los datos guardados antes de volver a editar."
                )

            if solicitud["cliente_id"] != limpio["cliente_id"]:
                raise ErrorGestionSolicitud(
                    "No puede cambiar el cliente de esta solicitud."
                )

            campos_editables = (
                "concepto",
                "nro_orden_compra",
                "fecha_emision",
                "monto_bruto",
                "tipo_afectacion",
            )

            cambios = {
                campo: {
                    "anterior": (
                        str(solicitud[campo])
                        if solicitud[campo] is not None
                        else None
                    ),
                    "nuevo": (
                        str(limpio[campo])
                        if limpio[campo] is not None
                        else None
                    ),
                }
                for campo in campos_editables
                if solicitud[campo] != limpio[campo]
            }

            if not cambios:
                connection.rollback()
                return False

            cursor.execute(
                """
                UPDATE solicitudes
                SET concepto = %s,
                    nro_orden_compra = %s,
                    fecha_emision = %s,
                    monto_bruto = %s,
                    tipo_afectacion = %s,
                    version = version + 1
                WHERE id = %s
                  AND version = %s
                  AND estado_id = %s
                """,
                (
                    limpio["concepto"],
                    limpio["nro_orden_compra"],
                    limpio["fecha_emision"],
                    limpio["monto_bruto"],
                    limpio["tipo_afectacion"],
                    solicitud["id"],
                    version_esperada,
                    solicitud["estado_id"],
                ),
            )

            if cursor.rowcount != 1:
                raise ErrorGestionSolicitud(
                    "No se pudo aplicar la edición. "
                    "Recargue el formulario."
                )

        registrar_evento(
            connection,
            actor["id"],
            "SOLICITUD_EDITADA",
            {
                "solicitud_afectada_id": solicitud["id"],
                "public_id": public_id,
                "version_anterior": version_esperada,
                "version_nueva": version_esperada + 1,
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