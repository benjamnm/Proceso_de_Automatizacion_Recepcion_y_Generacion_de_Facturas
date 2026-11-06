import re
import secrets

from flask import current_app
from itsdangerous import (
    BadData,
    URLSafeTimedSerializer,
)


class ErrorTokenEnvio(ValueError):
    pass


def obtener_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt="solicitud-creacion-v1",
    )


def generar_token_envio(usuario_id):
    return obtener_serializer().dumps({
        "usuario_id": int(usuario_id),
        "clave": secrets.token_hex(16),
    })


def verificar_token_envio(token, usuario_id):
    try:
        datos = obtener_serializer().loads(
            token,
            max_age=86400,
        )
    except BadData as exc:
        raise ErrorTokenEnvio(
            "El formulario venció o no es válido. "
            "Abra una solicitud nueva."
        ) from exc

    if not isinstance(datos, dict):
        raise ErrorTokenEnvio("El formulario no es válido.")

    if datos.get("usuario_id") != int(usuario_id):
        raise ErrorTokenEnvio(
            "El formulario pertenece a otra cuenta."
        )

    clave = datos.get("clave")

    if (
        not isinstance(clave, str)
        or not re.fullmatch(r"[0-9a-f]{32}", clave)
    ):
        raise ErrorTokenEnvio(
            "La clave del formulario no es válida."
        )

    return clave