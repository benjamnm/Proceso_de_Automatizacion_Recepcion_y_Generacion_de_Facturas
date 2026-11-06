"""Crea los roles base y un Administrador inicial.

Uso:
    python seed.py

La contraseña se solicita por consola y no se muestra ni se imprime.
Opcionalmente defina ADMIN_EMAIL en .env (por defecto admin@facturaciones.cl).
"""
import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from app import create_app
from app.models import get_db_connection

ROLES_BASE = (
    ("Administrador", "Acceso completo"),
    ("Emisor", "Gestiona sus propias solicitudes"),
    ("Lector", "Solo lectura"),
)


def pedir_password():
    password = getpass.getpass("Contraseña del Administrador (12-128): ")
    confirmacion = getpass.getpass("Repita la contraseña: ")

    if not 12 <= len(password) <= 128:
        sys.exit("La contraseña debe tener entre 12 y 128 caracteres.")

    if password != confirmacion:
        sys.exit("Las contraseñas no coinciden.")

    return password


def main():
    email = os.getenv("ADMIN_EMAIL", "admin@facturaciones.cl").strip().lower()
    app = create_app()

    with app.app_context():
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                for nombre, descripcion in ROLES_BASE:
                    cursor.execute(
                        "SELECT id FROM roles WHERE nombre = %s",
                        (nombre,),
                    )
                    if cursor.fetchone() is None:
                        cursor.execute(
                            "INSERT INTO roles (nombre, descripcion) "
                            "VALUES (%s, %s)",
                            (nombre, descripcion),
                        )
                        print(f"Rol creado: {nombre}")

                cursor.execute(
                    "SELECT id FROM usuarios WHERE email = %s",
                    (email,),
                )
                if cursor.fetchone() is not None:
                    conn.commit()
                    print(f"El usuario {email} ya existe. Sin cambios.")
                    return

                cursor.execute(
                    "SELECT id FROM roles WHERE nombre = %s",
                    ("Administrador",),
                )
                rol_admin = cursor.fetchone()

                cursor.execute(
                    """
                    INSERT INTO usuarios (
                        rol_id, rut, nombre, email, password_hash, activo
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        rol_admin["id"],
                        "11111111-1",
                        "Administrador de Prueba",
                        email,
                        generate_password_hash(pedir_password()),
                        1,
                    ),
                )

            conn.commit()
            print(f"Administrador creado: {email}")

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()


if __name__ == "__main__":
    main()
