"""Cambio, restablecimiento y recuperación de contraseñas.

- cambiar_propia: el usuario cambia su contraseña (exige la actual).
- restablecer: el Administrador asigna una contraseña nueva a otra cuenta,
  generada (temporal, se muestra una sola vez) o definida por él. Puede
  exigir que el usuario la cambie al iniciar sesión.
- solicitar_recuperacion: "¿Olvidó su contraseña?" desde el login. Deja
  una solicitud PENDIENTE que el Administrador atiende o descarta. No
  revela si el correo existe.

Ninguna contraseña (ni su hash) se guarda en auditoria. Requiere la
migración 005.
"""
import hashlib
import hmac
import secrets

from flask import current_app, render_template
from werkzeug.security import check_password_hash, generate_password_hash

from ..models import get_db_connection
from .usuarios import registrar_evento
from .validaciones import ErrorValidacion, normalizar_correo

LARGO_MINIMO = 12
LARGO_MAXIMO = 128
LARGO_TEMPORAL = 16
# Sin caracteres ambiguos (0/O, 1/l/I) para dictarla sin errores.
ALFABETO_TEMPORAL = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
MODOS_RESTABLECER = ("generar", "definir")


class ErrorPassword(Exception):
    pass


def validar_nueva(password, confirmacion):
    password = password or ""
    if not LARGO_MINIMO <= len(password) <= LARGO_MAXIMO:
        raise ErrorPassword(
            f"La contraseña debe tener entre {LARGO_MINIMO} y "
            f"{LARGO_MAXIMO} caracteres."
        )
    if password != (confirmacion or ""):
        raise ErrorPassword("Las contraseñas no coinciden.")
    return password


def generar_temporal(largo=LARGO_TEMPORAL):
    return "".join(secrets.choice(ALFABETO_TEMPORAL) for _ in range(largo))


def huella_sesion(password_hash, clave):
    """Identifica la contraseña vigente sin exponer su hash en la cookie.

    Si la contraseña cambia, la huella guardada en las sesiones abiertas
    deja de coincidir y esas sesiones se cierran.
    """
    return hmac.new(
        str(clave).encode("utf-8"),
        str(password_hash or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def _es_cuenta_tecnica(email):
    return email == current_app.config.get("SISTEMA_CORREO_EMAIL")


def _cerrar_recuperaciones(cursor, usuario_id, atendida_por):
    cursor.execute(
        """
        UPDATE recuperaciones_password
        SET estado = 'ATENDIDA', atendida_por = %s, atendida_en = NOW()
        WHERE usuario_id = %s AND estado = 'PENDIENTE'
        """,
        (atendida_por, usuario_id),
    )
    return cursor.rowcount


def _guardar_hash(cursor, usuario_id, password, debe_cambiar):
    nuevo_hash = generate_password_hash(password)
    cursor.execute(
        """
        UPDATE usuarios
        SET password_hash = %s,
            debe_cambiar_password = %s,
            password_actualizada_en = NOW()
        WHERE id = %s
        """,
        (nuevo_hash, 1 if debe_cambiar else 0, usuario_id),
    )
    return nuevo_hash


def cambiar_propia(usuario_id, actual, nueva, confirmacion, ip=None):
    """Devuelve el hash nuevo (para mantener abierta la sesión actual)."""
    actual = actual or ""
    if not actual or len(actual) > LARGO_MAXIMO:
        raise ErrorPassword("La contraseña actual no es correcta.")
    nueva = validar_nueva(nueva, confirmacion)
    if nueva == actual:
        raise ErrorPassword("La contraseña nueva debe ser distinta de la actual.")

    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, password_hash, activo
                FROM usuarios
                WHERE id = %s
                FOR UPDATE
                """,
                (usuario_id,),
            )
            usuario = cursor.fetchone()

            if usuario is None or not usuario["activo"]:
                raise ErrorPassword("Su cuenta no está disponible.")
            if not check_password_hash(usuario["password_hash"], actual):
                raise ErrorPassword("La contraseña actual no es correcta.")

            nuevo_hash = _guardar_hash(cursor, usuario_id, nueva, False)
            cerradas = _cerrar_recuperaciones(cursor, usuario_id, usuario_id)

        registrar_evento(
            connection, usuario_id, "PASSWORD_CAMBIADA",
            {
                "usuario_afectado_id": usuario_id,
                "motivo": "Cambio realizado por el propio usuario.",
                "recuperaciones_cerradas": cerradas,
            },
            ip,
        )
        connection.commit()
        return nuevo_hash

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def restablecer(actor_id, usuario_id, modo, password="", confirmacion="",
                exigir_cambio=True, ip=None):
    """El Administrador asigna una contraseña nueva a otra cuenta.

    Devuelve {"usuario": {...}, "password": str|None, "exigir_cambio": bool}.
    "password" solo trae valor si se generó una temporal: se muestra una
    vez y no se guarda en ninguna parte.
    """
    if modo not in MODOS_RESTABLECER:
        raise ErrorPassword("Seleccione cómo asignar la contraseña.")

    if modo == "generar":
        password = generar_temporal()
        exigir_cambio = True  # una contraseña temporal siempre se cambia
    else:
        password = validar_nueva(password, confirmacion)

    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.activo, r.nombre AS rol_nombre
                FROM usuarios AS u
                INNER JOIN roles AS r ON r.id = u.rol_id
                WHERE u.id = %s
                """,
                (actor_id,),
            )
            actor = cursor.fetchone()
            if (
                actor is None
                or not actor["activo"]
                or actor["rol_nombre"] != "Administrador"
            ):
                raise ErrorPassword(
                    "Su cuenta no tiene autorización para esta operación."
                )

            if actor_id == usuario_id:
                raise ErrorPassword(
                    "Para su propia cuenta use «Cambiar contraseña»."
                )

            cursor.execute(
                """
                SELECT id, nombre, email, activo
                FROM usuarios
                WHERE id = %s
                FOR UPDATE
                """,
                (usuario_id,),
            )
            usuario = cursor.fetchone()
            if usuario is None:
                raise ErrorPassword("El usuario ya no existe.")
            if _es_cuenta_tecnica(usuario["email"]):
                raise ErrorPassword(
                    "La cuenta técnica del sistema no admite contraseña."
                )

            _guardar_hash(cursor, usuario_id, password, exigir_cambio)
            atendidas = _cerrar_recuperaciones(cursor, usuario_id, actor_id)

        registrar_evento(
            connection, actor_id, "PASSWORD_RESTABLECIDA",
            {
                "usuario_afectado_id": usuario_id,
                "modo": modo,
                "exige_cambio": bool(exigir_cambio),
                "recuperaciones_atendidas": atendidas,
                "motivo": (
                    "Contraseña temporal generada por el Administrador."
                    if modo == "generar"
                    else "Contraseña definida por el Administrador."
                ),
            },
            ip,
        )
        connection.commit()

        return {
            "usuario": usuario,
            "password": password if modo == "generar" else None,
            "exigir_cambio": bool(exigir_cambio),
        }

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def solicitar_recuperacion(email, ip=None):
    """Registra la solicitud si el correo es de una cuenta activa.

    Devuelve el usuario cuando se creó una solicitud nueva (para avisar al
    Administrador) y None en cualquier otro caso. Quien llama debe
    responder siempre lo mismo, exista o no la cuenta.
    """
    try:
        # Las cuentas se guardan en minúsculas (ver admin.usuarios).
        email = normalizar_correo(str(email or "")[:150]).lower()
    except ErrorValidacion:
        return None

    if _es_cuenta_tecnica(email):
        return None

    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nombre, email
                FROM usuarios
                WHERE email = %s AND activo = 1
                FOR UPDATE
                """,
                (email,),
            )
            usuario = cursor.fetchone()
            if usuario is None:
                connection.rollback()
                return None

            cursor.execute(
                """
                SELECT id
                FROM recuperaciones_password
                WHERE usuario_id = %s AND estado = 'PENDIENTE'
                LIMIT 1
                """,
                (usuario["id"],),
            )
            if cursor.fetchone() is not None:
                # Ya hay una pendiente: no se duplica ni se vuelve a avisar.
                connection.rollback()
                return None

            cursor.execute(
                """
                INSERT INTO recuperaciones_password (usuario_id, ip)
                VALUES (%s, %s)
                """,
                (usuario["id"], (ip or "")[:45] or None),
            )
            recuperacion_id = cursor.lastrowid

        registrar_evento(
            connection, usuario["id"], "PASSWORD_RECUPERACION_SOLICITADA",
            {
                "usuario_afectado_id": usuario["id"],
                "recuperacion_id": recuperacion_id,
            },
            ip,
        )
        connection.commit()
        usuario["recuperacion_id"] = recuperacion_id
        return usuario

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def listar_pendientes():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rp.id, rp.usuario_id, rp.solicitada_en, rp.ip,
                       u.nombre, u.email, u.activo
                FROM recuperaciones_password AS rp
                INNER JOIN usuarios AS u ON u.id = rp.usuario_id
                WHERE rp.estado = 'PENDIENTE'
                ORDER BY rp.id
                """
            )
            return cursor.fetchall()
    finally:
        connection.close()


def descartar_recuperacion(actor_id, recuperacion_id, ip=None):
    connection = get_db_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, usuario_id
                FROM recuperaciones_password
                WHERE id = %s AND estado = 'PENDIENTE'
                FOR UPDATE
                """,
                (recuperacion_id,),
            )
            solicitud = cursor.fetchone()
            if solicitud is None:
                raise ErrorPassword("La solicitud ya fue atendida o no existe.")

            cursor.execute(
                """
                UPDATE recuperaciones_password
                SET estado = 'DESCARTADA', atendida_por = %s,
                    atendida_en = NOW()
                WHERE id = %s
                """,
                (actor_id, recuperacion_id),
            )

        registrar_evento(
            connection, actor_id, "PASSWORD_RECUPERACION_DESCARTADA",
            {
                "usuario_afectado_id": solicitud["usuario_id"],
                "recuperacion_id": recuperacion_id,
            },
            ip,
        )
        connection.commit()

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# --- Correos (opcionales, nunca lanzan excepciones) -----------------------

def _enviar(destinatarios, asunto, cuerpo):
    from .correo import ErrorCorreo, construir_mensaje, enviar, validar_configuracion
    from .notificaciones import CABECERA_ORIGEN, VALOR_ORIGEN

    try:
        cfg = validar_configuracion()
    except ErrorCorreo as exc:
        return str(exc)

    error = None
    for destinatario in destinatarios:
        mensaje = construir_mensaje(
            remitente=cfg["remitente"],
            remitente_correo=cfg["remitente_correo"],
            destinatario=destinatario,
            asunto=asunto,
            cuerpo=cuerpo,
            cabeceras_extra={CABECERA_ORIGEN: VALOR_ORIGEN},
        )
        try:
            enviar(mensaje, cfg)
        except ErrorCorreo as exc:
            current_app.logger.warning(
                "Correo de contraseña no enviado: %s (%s)", exc.codigo, exc.detalle
            )
            error = str(exc)
    return error


def avisar_recuperacion_a_admins(usuario):
    """Avisa a los Administradores que hay una solicitud de recuperación."""
    from .notificaciones import destinatarios

    try:
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                correos = destinatarios(cursor, current_app.config)
        finally:
            connection.close()

        cuerpo = render_template(
            "correos/recuperacion_password.txt",
            usuario=usuario,
            enlace=(
                f"{current_app.config['APP_BASE_URL'].rstrip('/')}"
                f"/admin/usuarios/{usuario['id']}/editar#restablecer"
            ),
        )
        return _enviar(
            correos,
            "[Facturaciones] Solicitud de recuperación de contraseña",
            cuerpo,
        )
    except Exception:
        current_app.logger.exception("No se pudo avisar la recuperación.")
        return "No se pudo enviar el aviso."


def enviar_temporal_al_usuario(usuario, password):
    """Envía la contraseña temporal al correo del usuario (opcional)."""
    try:
        cuerpo = render_template(
            "correos/password_temporal.txt",
            usuario=usuario,
            password=password,
            enlace=f"{current_app.config['APP_BASE_URL'].rstrip('/')}/auth/login",
        )
        return _enviar(
            [usuario["email"]],
            "[Facturaciones] Su contraseña temporal",
            cuerpo,
        )
    except Exception:
        current_app.logger.exception("No se pudo enviar la contraseña temporal.")
        return "No se pudo enviar el correo."
