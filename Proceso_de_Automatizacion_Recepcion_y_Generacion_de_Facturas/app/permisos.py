"""Qué puede hacer cada rol, según los decoradores actuales.

Documentación de solo lectura para la sección "Perfiles y permisos".
No concede ni restringe nada: la autorización real está en app/security.py
(admin_required, solicitud_required) y en los controles dentro de cada ruta.
test/test_permisos.py verifica que cada fila con ruta coincida con el
comportamiento real.
"""

ROLES = ("Administrador", "Emisor", "Lector")

CAPACIDADES = (
    # (texto visible, roles permitidos, ruta de ejemplo para el test)
    ("Ver el panel principal",
     {"Administrador", "Emisor", "Lector"}, "/dashboard"),
    ("Crear y consultar sus solicitudes",
     {"Administrador", "Emisor"}, "/solicitudes/"),
    ("Consultar todas las solicitudes",
     {"Administrador"}, None),
    ("Validar facturas",
     {"Administrador"}, None),
    ("Gestionar clientes",
     {"Administrador"}, "/clientes/"),
    ("Gestionar usuarios",
     {"Administrador"}, "/admin/usuarios"),
    ("Revisar la bandeja de correos",
     {"Administrador"}, "/admin/correos"),
    ("Consultar la auditoría",
     {"Administrador"}, "/admin/auditoria"),
)
