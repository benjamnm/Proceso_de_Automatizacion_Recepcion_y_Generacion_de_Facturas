PUBLIC_ID = "1234abcd" + "0" * 24


def _solicitud(estado):
    return {
        "id": 7, "public_id": PUBLIC_ID, "estado_nombre": estado,
        "origen_nombre": "Web", "version": 3,
    }


def _abrir_factura(client, login_como, monkeypatch, rol, estado):
    monkeypatch.setattr(
        "app.solicitudes.routes.obtener_solicitud_autorizada",
        lambda pid: _solicitud(estado),
    )
    monkeypatch.setattr(
        "app.solicitudes.routes.listar_versiones", lambda sid: ([], None)
    )
    login_como(rol)
    return client.get(f"/solicitudes/{PUBLIC_ID}/factura").get_data(as_text=True)


def test_menu_del_administrador(client, login_como, monkeypatch):
    monkeypatch.setattr("app.resumen_panel", lambda: None)
    login_como("Administrador")

    html = client.get("/dashboard").get_data(as_text=True)

    for destino in ("/solicitudes/", "/admin/correos", "/clientes/",
                    "/admin/usuarios", "/admin/auditoria"):
        assert f'href="{destino}"' in html
    assert "Cerrar sesión" in html
    assert "Volver" not in html


def test_menu_del_emisor_no_muestra_administracion(client, login_como, monkeypatch):
    monkeypatch.setattr("app.resumen_panel", lambda: None)
    login_como("Emisor")

    html = client.get("/dashboard").get_data(as_text=True)

    assert 'href="/solicitudes/nueva"' in html
    assert 'href="/admin/usuarios"' not in html
    assert 'href="/clientes/"' not in html


def test_factura_tiene_migas_volver_y_pestanas(client, login_como, monkeypatch):
    html = _abrir_factura(client, login_como, monkeypatch, "Emisor", "En corrección")
    detalle = f"/solicitudes/{PUBLIC_ID}"

    assert 'aria-label="Ruta de navegación"' in html
    assert f'<a href="{detalle}" class="btn btn-outline-secondary btn-sm">' in html
    assert "Solicitud 1234abcd" in html
    assert f'href="{detalle}/editar"' in html
    assert 'aria-current="step">En corrección' in html


def test_pestana_editar_oculta_si_no_es_editable(client, login_como, monkeypatch):
    html = _abrir_factura(client, login_como, monkeypatch, "Administrador", "Aprobada")

    assert f'href="/solicitudes/{PUBLIC_ID}/editar"' not in html


def test_volver_desde_listado_lleva_al_panel(client, login_como, monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args):
            pass

        def fetchall(self):
            return []

        def fetchone(self):
            return {"total": 0}

    class Conexion:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(
        "app.solicitudes.routes.get_db_connection", lambda: Conexion()
    )
    login_como("Emisor")

    html = client.get("/solicitudes/").get_data(as_text=True)

    assert '<a href="/dashboard" class="btn btn-outline-secondary btn-sm">' in html
