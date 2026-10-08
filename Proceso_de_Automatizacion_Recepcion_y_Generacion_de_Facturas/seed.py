from app import create_app
from app.extensions import db
from app.models import Role, User

app = create_app()

with app.app_context():
    db.create_all()

    admin_role = db.session.scalar(
        db.select(Role).where(
            Role.nombre == "Administrador"
        )
    )

    if admin_role is None:
        admin_role = Role(
            nombre="Administrador",
            descripcion="Acceso completo al sistema"
        )
        db.session.add(admin_role)
        db.session.flush()

    admin = db.session.scalar(
        db.select(User).where(
            User.email == "admin@facturaciones.cl"
        )
    )

    if admin is None:
        admin = User(
            rol_id=admin_role.id,
            rut="11111111-1",
            nombre="Administrador de Prueba",
            email="admin@facturaciones.cl",
            activo=True
        )

        admin.set_password("Admin12345")
        db.session.add(admin)

    db.session.commit()

    print("Usuario: admin@facturaciones.cl")
    print("Contraseña temporal: Admin12345")