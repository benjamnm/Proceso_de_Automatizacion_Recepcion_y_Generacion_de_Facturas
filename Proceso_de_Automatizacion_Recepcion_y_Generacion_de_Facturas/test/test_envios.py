import pytest

from app.services.envios_solicitud import (
    ErrorTokenEnvio,
    generar_token_envio,
    verificar_token_envio,
)


def test_token_ida_y_vuelta(app):
    with app.app_context():
        token = generar_token_envio(7)
        clave = verificar_token_envio(token, 7)
    assert len(clave) == 32


def test_token_de_otro_usuario(app):
    with app.app_context():
        token = generar_token_envio(7)
        with pytest.raises(ErrorTokenEnvio):
            verificar_token_envio(token, 8)


def test_token_alterado(app):
    with app.app_context():
        token = generar_token_envio(7)
        with pytest.raises(ErrorTokenEnvio):
            verificar_token_envio(token[:-2] + "xx", 7)
