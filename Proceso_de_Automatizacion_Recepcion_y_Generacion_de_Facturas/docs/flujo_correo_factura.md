# Flujo: correo → factura → validación → SII

## 1. Resumen

| Paso | Qué ocurre | Dónde |
|---|---|---|
| 1 | Llega un correo a la casilla de facturación. | Servidor de correo |
| 2 | `correo-revisar` lee los **no leídos** por IMAP (TLS). Solo los de facturación se guardan como `.eml` (SHA-256) en `app/registros/correos/` y quedan `RECIBIDO`. El resto queda intacto. | `services/correo_entrante.py` |
| 3 | Se extraen RUT, concepto, monto, fecha, afectación y OC (cuerpo o XML adjunto), se identifica al cliente y se crea la solicitud (origen **Correo**) con su **factura v1** en estado **En revisión**. | `services/extraccion_correo.py`, `services/facturas.py` |
| 4 | Se avisa por SMTP al Administrador: «Factura v1 lista para validar» con enlace. | `services/notificaciones.py` |
| 5a | Admin valida OK → **Aprobada** y se genera el **DTE XML** (33/34) para el SII en `app/registros/sii/`. | `/solicitudes/<id>/factura` |
| 5b | Admin observa → **En corrección** con la observación. Se corrigen los datos (solicitud o ficha del cliente) y se reenvía: se crea la **v2** con el detalle de cambios en `facturas.cambios` y en `auditoria` (`FACTURA_GENERADA`). Vuelve al paso 4. | idem |

Correos incompletos o de remitentes no registrados quedan `REQUIERE_REVISION` en **Admin › Bandeja de correos** (reprocesar tras registrar al cliente, o descartar con motivo).

## 2. Puesta en marcha

1. Respaldar la BD y ejecutar `migrations/003_flujo_correo_factura.sql` en phpMyAdmin.
2. Completar en `.env` las secciones IMAP, `NOTIFICAR_A`/`APP_BASE_URL` y `EMPRESA_*` (ver `.env.example`).
3. Probar:
   ```
   flask --app run smtp-prueba su_correo@dominio.cl
   flask --app run imap-prueba
   flask --app run correo-revisar
   ```
4. Programar la revisión (Programador de tareas de Windows, cada 5 minutos):
   ```
   Programa:   C:\Github\Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas\Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas\venv\Scripts\flask.exe
   Argumentos: --app run correo-revisar
   Iniciar en: C:\Github\Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas\Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas
   ```
   También existe el botón **Revisar bandeja ahora** en la bandeja del Administrador. Dos ejecuciones simultáneas se excluyen con `GET_LOCK`.

## 3. Formato sugerido para los clientes

```
Asunto: Solicitud de factura
RUT: 12.345.678-5
Concepto: Servicios de asesoría octubre 2026
Monto: $980.000            (bruto; "1.000.000 + IVA" se interpreta como neto)
Fecha de emisión: 16-10-2026
Afectación: Afecta
Orden de compra: 4500012345
```

## 4. Seguridad aplicada

- IMAP y SMTP solo cifrados (SSL/STARTTLS, certificado verificado); texto plano únicamente contra `localhost`. Nunca se degrada si falta STARTTLS.
- Lectura con `BODY.PEEK`: solo se marcan como leídos los correos efectivamente guardados.
- Límite de tamaño previo a la descarga (`IMAP_MAX_BYTES`); XML adjuntos con `defusedxml` (sin DTD/entidades).
- El HTML de los correos nunca se renderiza; el `.eml` se entrega solo como descarga auditada.
- Idempotencia: huella única del `Message-ID` + `clave_idempotencia` en `solicitudes`.
- Integridad SHA-256 de `.eml`, versiones de factura y DTE antes de usarlos.
- Remitente no registrado o falla SPF/DMARC → revisión manual; RUT de otro contacto → alerta visible al validar.
- Avisos propios (`X-Facturaciones-Origen`), respuestas automáticas y listas se ignoran (evita bucles).
- Solo el Administrador valida, observa, descarga DTE y gestiona la bandeja; todo queda en `auditoria`.

## 5. Límite conocido

El DTE generado **no incluye firma electrónica ni timbre (TED)** y su folio es provisional. Para emitirlo ante el SII debe firmarse con el certificado digital de la empresa y un folio autorizado (CAF), con un software certificado o un servicio de firma.
