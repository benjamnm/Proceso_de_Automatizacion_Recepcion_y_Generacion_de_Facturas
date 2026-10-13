from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if (
            not current_user.is_active
            or current_user.role_name != "Administrador"
        ):
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view

def solicitud_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if (
            not current_user.is_active
            or current_user.role_name
            not in {"Administrador", "Emisor"}
        ):
            abort(403)

        return view(*args, **kwargs)

    return wrapped_view