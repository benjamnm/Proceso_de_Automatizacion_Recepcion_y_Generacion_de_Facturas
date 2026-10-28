import io

import pytest


@pytest.mark.parametrize("ruta", [
    "/dashboard", "/solicitudes/", "/solicitudes/nueva",
    "/clientes/", "/admin/usuarios", "/admin/auditoria",
])
def test_rutas_protegidas_redirigen_al_login(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_logout_no_acepta_get(client):
    assert client.get("/auth/logout").status_code == 405


def test_pagina_404_personalizada(client):
    respuesta = client.get("/no-existe")
    assert respuesta.status_code == 404
    assert "no existe".encode() in respuesta.data


def test_lector_no_accede_a_solicitudes(client, login_como):
    login_como("Lector")
    respuesta = client.get("/solicitudes/")
    assert respuesta.status_code == 403
    assert "permisos".encode() in respuesta.data


@pytest.mark.parametrize("ruta", ["/clientes/", "/admin/usuarios"])
def test_emisor_no_accede_a_administracion(client, login_como, ruta):
    login_como("Emisor")
    assert client.get(ruta).status_code == 403


def test_xml_demasiado_grande_redirige_con_mensaje(client, login_como):
    login_como("Emisor")
    public_id = "a" * 32
    grande = io.BytesIO(b"x" * (7 * 1024 * 1024))

    respuesta = client.post(
        f"/solicitudes/{public_id}/xml",
        data={"archivo_xml": (grande, "f.xml")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/solicitudes/{public_id}")

    with client.session_transaction() as sesion:
        mensajes = [m for _, m in sesion.get("_flashes", [])]
    assert any("5 MB" in m for m in mensajes)
