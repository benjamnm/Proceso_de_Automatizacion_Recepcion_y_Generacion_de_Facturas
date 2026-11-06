import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Modo depuración solo si FLASK_DEBUG=1 en .env (nunca en producción).
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
