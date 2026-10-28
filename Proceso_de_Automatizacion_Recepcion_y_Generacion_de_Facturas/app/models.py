import pymysql
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash


def get_db_connection():
    """Abre una conexión MySQL con los datos de la configuración activa."""
    config = current_app.config

    return pymysql.connect(
        host=config["DB_HOST"],
        port=int(config["DB_PORT"]),
        user=config["DB_USER"],
        password=config["DB_PASSWORD"],
        database=config["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
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

    @classmethod
    def _desde_fila(cls, fila):
        if fila is None:
            return None

        return cls(
            id=fila["id"],
            rol_id=fila["rol_id"],
            rut=fila["rut"],
            nombre=fila["nombre"],
            email=fila["email"],
            telefono=fila["telefono"],
            password_hash=fila["password_hash"],
            activo=fila["activo"],
            ultimo_login=fila["ultimo_login"],
            creado_en=fila["creado_en"],
            role={"nombre": fila["role_nombre"]},
        )

    @classmethod
    def _buscar(cls, columna, valor):
        # "columna" solo recibe valores fijos desde este módulo.
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT u.*, r.nombre AS role_nombre
                    FROM usuarios u
                    JOIN roles r ON u.rol_id = r.id
                    WHERE u.{columna} = %s AND u.activo = TRUE
                    """,
                    (valor,),
                )
                return cls._desde_fila(cursor.fetchone())
        finally:
            conn.close()

    @classmethod
    def get_by_id(cls, user_id):
        return cls._buscar("id", user_id)

    @classmethod
    def get_by_email(cls, email):
        return cls._buscar("email", email.lower().strip())

    def registrar_login(self):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE usuarios SET ultimo_login = UTC_TIMESTAMP() "
                    "WHERE id = %s",
                    (self.id,),
                )
            conn.commit()
        finally:
            conn.close()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return bool(self.activo)

    @property
    def role_name(self):
        return self.role["nombre"] if self.role else ""
