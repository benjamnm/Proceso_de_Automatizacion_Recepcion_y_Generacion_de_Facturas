"""Totales y actividad reciente del panel principal.

Las funciones reciben un cursor abierto; quien llama maneja la conexión
y los errores de BD (ver resumen_panel() en app/__init__.py).

Alcance:
- Administrador: totales globales y últimos eventos de auditoría
  (sin IP ni detalle completo).
- Emisor: solo sus solicitudes; nunca consulta la tabla auditoria.
"""
import json
import re

from flask import current_app

from ..auditoria_acciones import (
    ACCIONES_VISIBLES,
    etiqueta_accion,
    marcadores_acciones,
)

LIMITE_ACTIVIDAD_ADMIN = 8
LIMITE_ACTIVIDAD_EMISOR = 5
PATRON_PUBLIC_ID = re.compile(r"[0-9a-f]{32}")


def _estados(cursor, emisor_id=None):
    # La condición de alcance va en el ON para conservar estados con 0.
    if emisor_id is None:
        cursor.execute(
            """
            SELECT e.id, e.nombre, COUNT(s.id) AS total
            FROM estados_solicitud AS e
            LEFT JOIN solicitudes AS s
                ON s.estado_id = e.id
            GROUP BY e.id, e.nombre
            ORDER BY e.id
            """
        )
    else:
        cursor.execute(
            """
            SELECT e.id, e.nombre, COUNT(s.id) AS total
            FROM estados_solicitud AS e
            LEFT JOIN solicitudes AS s
                ON s.estado_id = e.id AND s.emisor_id = %s
            GROUP BY e.id, e.nombre
            ORDER BY e.id
            """,
            (emisor_id,),
        )

    estados = {}
    for fila in cursor.fetchall():
        estados[fila["nombre"]] = {
            "id": fila["id"],
            "nombre": fila["nombre"],
            "total": int(fila["total"]),
        }
    return estados


def _public_id_de(detalle):
    if isinstance(detalle, (bytes, bytearray)):
        detalle = detalle.decode("utf-8", "replace")
    if isinstance(detalle, str):
        try:
            detalle = json.loads(detalle)
        except ValueError:
            return None
    if not isinstance(detalle, dict):
        return None

    valor = detalle.get("public_id")
    if isinstance(valor, str) and PATRON_PUBLIC_ID.fullmatch(valor):
        return valor
    return None


def actividad_administrador(cursor, limite=LIMITE_ACTIVIDAD_ADMIN):
    cursor.execute(
        f"""
        SELECT a.accion, a.detalle, a.creado_en,
               u.nombre AS usuario_nombre
        FROM auditoria AS a
        LEFT JOIN usuarios AS u
            ON u.id = a.usuario_id
        WHERE a.accion IN ({marcadores_acciones()})
        ORDER BY a.id DESC
        LIMIT %s
        """,
        ACCIONES_VISIBLES + (limite,),
    )

    # Se entrega solo lo necesario: nunca la IP ni el detalle completo.
    return [
        {
            "creado_en": fila["creado_en"],
            "etiqueta": etiqueta_accion(fila["accion"]),
            "usuario_nombre": fila.get("usuario_nombre"),
            "public_id": _public_id_de(fila.get("detalle")),
        }
        for fila in cursor.fetchall()
    ]


def resumen_administrador(cursor):
    estados = _estados(cursor)

    cursor.execute(
        """
        SELECT COUNT(*) AS total FROM correos_entrantes
        WHERE estado IN ('REQUIERE_REVISION', 'ERROR')
        """
    )
    correos = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(activo = 1), 0) AS activos, COUNT(*) AS total
        FROM usuarios
        WHERE email <> %s
        """,
        (current_app.config["SISTEMA_CORREO_EMAIL"],),
    )
    usuarios = cursor.fetchone()

    cursor.execute(
        """
        SELECT COALESCE(SUM(activo = 1), 0) AS activos, COUNT(*) AS total
        FROM clientes
        """
    )
    clientes = cursor.fetchone()

    cursor.execute(
        f"""
        SELECT COUNT(*) AS total FROM auditoria
        WHERE accion IN ({marcadores_acciones()})
        """,
        ACCIONES_VISIBLES,
    )
    eventos = cursor.fetchone()["total"]

    return {
        "estados": estados,
        "solicitudes_total": sum(e["total"] for e in estados.values()),
        "correos_por_revisar": int(correos),
        "usuarios": {
            "activos": int(usuarios["activos"]),
            "total": int(usuarios["total"]),
        },
        "clientes": {
            "activos": int(clientes["activos"]),
            "total": int(clientes["total"]),
        },
        "eventos_total": int(eventos),
        "actividad": actividad_administrador(cursor),
    }


def resumen_emisor(cursor, usuario_id):
    usuario_id = int(usuario_id)
    estados = _estados(cursor, emisor_id=usuario_id)

    cursor.execute(
        """
        SELECT s.public_id, s.nombre, s.actualizado_en,
               e.nombre AS estado_nombre
        FROM solicitudes AS s
        INNER JOIN estados_solicitud AS e
            ON e.id = s.estado_id
        WHERE s.emisor_id = %s
        ORDER BY s.actualizado_en DESC, s.id DESC
        LIMIT %s
        """,
        (usuario_id, LIMITE_ACTIVIDAD_EMISOR),
    )
    actividad = cursor.fetchall()

    return {
        "estados": estados,
        "solicitudes_total": sum(e["total"] for e in estados.values()),
        "actividad": list(actividad),
    }
