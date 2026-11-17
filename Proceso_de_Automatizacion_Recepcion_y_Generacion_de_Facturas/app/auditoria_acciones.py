"""Acciones de auditoría visibles en la interfaz y su texto legible.

Lista blanca compartida por la página de auditoría y la actividad reciente
del panel. Solo el Administrador ve datos de auditoría.
"""

ACCIONES_VISIBLES = (
    "USUARIO_CREADO",
    "USUARIO_EDITADO",
    "USUARIO_DESACTIVADO",
    "USUARIO_REACTIVADO",
    "CLIENTE_CREADO",
    "CLIENTE_EDITADO",
    "SOLICITUD_CREADA",
    "SOLICITUD_EDITADA",
    "SOLICITUD_ESTADO_CAMBIADO",
    "XML_CARGADO",
    "XML_REEMPLAZADO",
    "XML_DESCARGADO",
    "CORREO_ENVIADO",
    "CORREO_FALLIDO",
    "CORREO_RECIBIDO",
    "CORREO_REQUIERE_REVISION",
    "CORREO_REPROCESADO",
    "CORREO_DESCARTADO",
    "CORREO_ENTRANTE_DESCARGADO",
    "FACTURA_GENERADA",
    "FACTURA_OBSERVADA",
    "FACTURA_APROBADA",
    "ARCHIVO_SII_DESCARGADO",
    "NOTIFICACION_ENVIADA",
    "NOTIFICACION_FALLIDA",
    "ADJUNTO_CARGADO",
    "ADJUNTO_DESCARGADO",
)

ETIQUETAS_ACCION = {
    "USUARIO_CREADO": "Usuario creado",
    "USUARIO_EDITADO": "Usuario editado",
    "USUARIO_DESACTIVADO": "Usuario desactivado",
    "USUARIO_REACTIVADO": "Usuario reactivado",
    "CLIENTE_CREADO": "Cliente creado",
    "CLIENTE_EDITADO": "Cliente editado",
    "SOLICITUD_CREADA": "Solicitud creada",
    "SOLICITUD_EDITADA": "Solicitud editada",
    "SOLICITUD_ESTADO_CAMBIADO": "Estado de solicitud cambiado",
    "XML_CARGADO": "XML cargado",
    "XML_REEMPLAZADO": "XML reemplazado",
    "XML_DESCARGADO": "XML descargado",
    "CORREO_ENVIADO": "Correo enviado",
    "CORREO_FALLIDO": "Envío de correo fallido",
    "CORREO_RECIBIDO": "Correo recibido",
    "CORREO_REQUIERE_REVISION": "Correo requiere revisión",
    "CORREO_REPROCESADO": "Correo reprocesado",
    "CORREO_DESCARTADO": "Correo descartado",
    "CORREO_ENTRANTE_DESCARGADO": "Correo entrante descargado",
    "FACTURA_GENERADA": "Factura generada",
    "FACTURA_OBSERVADA": "Factura observada",
    "FACTURA_APROBADA": "Factura aprobada",
    "ARCHIVO_SII_DESCARGADO": "Archivo SII descargado",
    "NOTIFICACION_ENVIADA": "Notificación enviada",
    "NOTIFICACION_FALLIDA": "Notificación fallida",
    "ADJUNTO_CARGADO": "Documento adjuntado",
    "ADJUNTO_DESCARGADO": "Documento adjunto descargado",
}


def etiqueta_accion(accion):
    return ETIQUETAS_ACCION.get(accion, accion)


def marcadores_acciones():
    """Marcadores %s para usar en un IN (...) con ACCIONES_VISIBLES."""
    return ", ".join(["%s"] * len(ACCIONES_VISIBLES))
