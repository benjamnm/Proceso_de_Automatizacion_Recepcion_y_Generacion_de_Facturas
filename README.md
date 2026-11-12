# Proceso de Automatización Recepción y Generación de Facturas.

Proyecto CAPSTONE 005D

Integrantes: Carla Correa, Vicente Oyarzún, Benjamín Arevalo, Vicente Valenzuela.

Asignatura: Capstone

Docente: Cindy Contador.

Aplicación web que permite centralizar y administrar las solicitudes de emisión de facturas recibidas desde distintos canales de comunicación.
El sistema registra los datos de cada solicitud, identifica el canal de origen (ya sea correo electrónico o WhatsApp), aplica validaciones sobre los campos obligatorios, controla el estado del trámite y genera un historial medible de las acciones realizadas por los usuarios dentro de la aplicación.

## Flujo automatizado de facturación

Correo de facturación (IMAP) → repositorio de correos → factura generada (v1) → aviso al Administrador (SMTP) → validación → archivo DTE para el SII. Si la factura se devuelve a corrección, el reenvío genera una nueva versión con registro de cambios en la auditoría.

Instalación y operación: `Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/docs/flujo_correo_factura.md`.
