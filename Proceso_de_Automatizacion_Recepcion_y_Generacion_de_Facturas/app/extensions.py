from flask_login import LoginManager
from flask_wtf import CSRFProtect

login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Debes iniciar sesión para acceder."
login_manager.login_message_category = "warning"
# Cierra la sesión si cambia la IP o el navegador del usuario (robo de cookie).
login_manager.session_protection = "strong"
