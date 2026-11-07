from flask import (
    Flask,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
import pymysql
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import RequestEntityTooLarge

from config import Config
from .extensions import csrf, login_manager
from .security import (
    LimitadorIntentos,
    aplicar_cabeceras_seguridad,
    controlar_inactividad,
)

LARGO_MINIMO_SECRET_KEY = 32


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if len(app.config.get("SECRET_KEY") or "") < LARGO_MINIMO_SECRET_KEY:
        raise RuntimeError(
            "Falta SECRET_KEY o es demasiado corta (mínimo "
            f"{LARGO_MINIMO_SECRET_KEY} caracteres). Copie .env.example "
            "como .env y defina una clave aleatoria."
        )

    login_manager.init_app(app)
    csrf.init_app(app)
    app.extensions["limitador_login"] = LimitadorIntentos(
        app.config["LOGIN_BLOQUEO_MINUTOS"] * 60
    )
    app.before_request(controlar_inactividad)
    app.after_request(aplicar_cabeceras_seguridad)

    from .auth.routes import auth_bp
    from .admin import admin_bp
    from .clientes import clientes_bp
    from .solicitudes import solicitudes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(solicitudes_bp)

    registrar_manejadores_error(app)

    from .cli import registrar_comandos
    registrar_comandos(app)

    @app.get("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", resumen=resumen_panel())

    return app


def resumen_panel():
    """Contadores del panel del Administrador. None si la BD no responde."""
    if current_user.role_name != "Administrador":
        return None

    from .models import get_db_connection

    try:
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT e.id, e.nombre, COUNT(s.id) AS total
                    FROM estados_solicitud AS e
                    LEFT JOIN solicitudes AS s ON s.estado_id = e.id
                    WHERE e.nombre IN ('En revisión', 'En corrección')
                    GROUP BY e.id, e.nombre
                    """
                )
                estados = {f["nombre"]: f for f in cursor.fetchall()}
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total FROM correos_entrantes
                    WHERE estado IN ('REQUIERE_REVISION', 'ERROR')
                    """
                )
                correos = cursor.fetchone()["total"]
        finally:
            connection.close()
    except pymysql.MySQLError:
        current_app.logger.warning("No se pudo calcular el resumen del panel.")
        return None

    return {"estados": estados, "correos_por_revisar": correos}


def _pagina_error(codigo, mensaje):
    return render_template(
        "errores/error.html", codigo=codigo, mensaje=mensaje
    ), codigo


def registrar_manejadores_error(app):
    @app.errorhandler(RequestEntityTooLarge)
    def archivo_demasiado_grande(error):
        public_id = (request.view_args or {}).get("public_id")

        if request.endpoint == "solicitudes.cargar_xml" and public_id:
            flash("El archivo supera el tamaño máximo permitido (5 MB).",
                  "danger")
            return redirect(url_for(
                "solicitudes.detalle",
                public_id=public_id,
            ))

        return _pagina_error(
            413, "El contenido enviado supera el tamaño permitido."
        )

    @app.errorhandler(CSRFError)
    def formulario_vencido(error):
        return _pagina_error(
            400,
            "El formulario venció o no es válido. Vuelva a la pantalla "
            "anterior, recárguela e intente nuevamente.",
        )

    @app.errorhandler(403)
    def prohibido(error):
        return _pagina_error(
            403, "No tiene permisos para acceder a este recurso."
        )

    @app.errorhandler(404)
    def no_encontrado(error):
        return _pagina_error(
            404, "El recurso solicitado no existe o no está disponible."
        )

    @app.errorhandler(500)
    def error_interno(error):
        return _pagina_error(
            500,
            "Ocurrió un error inesperado. Si persiste, informe al "
            "Administrador.",
        )


@login_manager.user_loader
def load_user(user_id):
    from .models import User

    try:
        return User.get_by_id(int(user_id))
    except (TypeError, ValueError):
        return None
