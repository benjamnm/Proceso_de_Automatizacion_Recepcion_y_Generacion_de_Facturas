import os

from app import create_app
from app.services import revision_automatica

app = create_app()

# Con el recargador de depuración el módulo se ejecuta dos veces (proceso
# vigilante + proceso servidor): el hilo solo arranca en el servidor.
_debug = os.getenv("FLASK_DEBUG", "0") == "1"
if not _debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    revision_automatica.iniciar(app)

if __name__ == "__main__":
    # Modo depuración solo si FLASK_DEBUG=1 en .env (nunca en producción).
    app.run(debug=_debug)
