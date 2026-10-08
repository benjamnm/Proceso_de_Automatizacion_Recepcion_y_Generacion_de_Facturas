from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.SmallInteger, primary_key=True)
    nombre = db.Column(db.String(30), nullable=False, unique=True)
    descripcion = db.Column(db.String(150))

    usuarios = db.relationship(
        "User",
        back_populates="role"
    )


class User(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)

    rol_id = db.Column(
        db.SmallInteger,
        db.ForeignKey("roles.id"),
        nullable=False
    )

    rut = db.Column(db.String(12), unique=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    telefono = db.Column(db.String(20))

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    activo = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    ultimo_login = db.Column(db.DateTime)
    creado_en = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    role = db.relationship(
        "Role",
        back_populates="usuarios"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(
            self.password_hash,
            password
        )

    @property
    def is_active(self) -> bool:
        return self.activo

    @property
    def role_name(self) -> str:
        return self.role.nombre if self.role else ""