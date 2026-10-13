from flask import Flask, app, redirect, render_template, url_for
from flask_login import login_required
from .solicitudes import solicitudes_bp


from config import Config
from .extensions import csrf, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    login_manager.init_app(app)
    csrf.init_app(app)

    from .auth.routes import auth_bp
    app.register_blueprint(auth_bp)
    
    from .admin import admin_bp
    app.register_blueprint(admin_bp)
    
    from .clientes import clientes_bp
    app.register_blueprint(clientes_bp)
    
    from .solicitudes import solicitudes_bp
    app.register_blueprint(solicitudes_bp)

    @app.get("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    return app


@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return User.get_by_id(int(user_id))