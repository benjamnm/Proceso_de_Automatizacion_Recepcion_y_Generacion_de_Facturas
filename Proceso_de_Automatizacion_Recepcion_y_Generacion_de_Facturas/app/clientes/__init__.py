from flask import Blueprint

clientes_bp = Blueprint(
    "clientes",
    __name__,
    url_prefix="/clientes",
)

from . import routes