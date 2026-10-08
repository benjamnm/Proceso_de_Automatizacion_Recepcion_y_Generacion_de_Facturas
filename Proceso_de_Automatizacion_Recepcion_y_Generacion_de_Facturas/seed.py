import pymysql
from werkzeug.security import generate_password_hash

# Crear usuario administrador
conn = pymysql.connect(
    host="127.0.0.1",
    user="root",
    password="",
    database="facturaciones_spa_mvp",
    charset="utf8mb4"
)

try:
    with conn.cursor() as cursor:
        # Verificar si existe el rol Administrador
        cursor.execute("SELECT id FROM roles WHERE nombre = 'Administrador'")
        role = cursor.fetchone()

        if role is None:
            cursor.execute(
                "INSERT INTO roles (nombre, descripcion) VALUES ('Administrador', 'Acceso completo')"
            )
            conn.commit()
            cursor.execute("SELECT id FROM roles WHERE nombre = 'Administrador'")
            role = cursor.fetchone()

        # Verificar si existe el usuario
        cursor.execute(
            "SELECT id FROM usuarios WHERE email = 'admin@facturaciones.cl'"
        )
        user = cursor.fetchone()

        if user is None:
            password_hash = generate_password_hash("Admin12345")
            cursor.execute("""
                INSERT INTO usuarios (
                    rol_id, rut, nombre, email, password_hash, activo
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                role['id'],
                "11111111-1",
                "Administrador de Prueba",
                "admin@facturaciones.cl",
                password_hash,
                True
            ))
            conn.commit()

        print("Usuario creado: admin@facturaciones.cl")
        print("Contraseña: Admin12345")

finally:
    conn.close()