from flask import Blueprint

solicitudes_bp = Blueprint(
    "solicitudes",
    __name__,
    url_prefix="/solicitudes",
)

from . import routes