from datetime import datetime

import pymysql
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


def get_db_connection():
    """Obtiene conexión directa a MySQL"""
    return pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="facturaciones_spa_mvp",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )


class User(UserMixin):
    def __init__(self, id, rol_id, rut, nombre, email, telefono,
                 password_hash, activo, ultimo_login, creado_en, role=None):
        self.id = id
        self.rol_id = rol_id
        self.rut = rut
        self.nombre = nombre
        self.email = email
        self.telefono = telefono
        self.password_hash = password_hash
        self.activo = activo
        self.ultimo_login = ultimo_login
        self.creado_en = creado_en
        self.role = role

    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT u.*, r.nombre as role_nombre
                    FROM usuarios u
                    JOIN roles r ON u.rol_id = r.id
                    WHERE u.id = %s AND u.activo = TRUE
                """, (user_id,))
                result = cursor.fetchone()

                if result:
                    return User(
                        id=result['id'],
                        rol_id=result['rol_id'],
                        rut=result['rut'],
                        nombre=result['nombre'],
                        email=result['email'],
                        telefono=result['telefono'],
                        password_hash=result['password_hash'],
                        activo=result['activo'],
                        ultimo_login=result['ultimo_login'],
                        creado_en=result['creado_en'],
                        role={'nombre': result['role_nombre']}
                    )
                return None
        finally:
            conn.close()

    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT u.*, r.nombre as role_nombre
                    FROM usuarios u
                    JOIN roles r ON u.rol_id = r.id
                    WHERE u.email = %s AND u.activo = TRUE
                """, (email.lower().strip(),))
                result = cursor.fetchone()

                if result:
                    return User(
                        id=result['id'],
                        rol_id=result['rol_id'],
                        rut=result['rut'],
                        nombre=result['nombre'],
                        email=result['email'],
                        telefono=result['telefono'],
                        password_hash=result['password_hash'],
                        activo=result['activo'],
                        ultimo_login=result['ultimo_login'],
                        creado_en=result['creado_en'],
                        role={'nombre': result['role_nombre']}
                    )
                return None
        finally:
            conn.close()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.activo

    @property
    def role_name(self):
        return self.role['nombre'] if self.role else ""