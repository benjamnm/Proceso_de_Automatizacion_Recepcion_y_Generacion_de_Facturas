# Proceso de Automatización Recepción y Generación de Facturas.

Proyecto CAPSTONE 005D

Integrantes: Benjamín Arevalo, Carla Correa, Vicente Valenzuela.

Asignatura: Capstone

Docente: Cindy Contador.

**Descripción del proyecto**

Aplicación web (Flask + MySQL) que centraliza y gestiona las solicitudes de facturación de Facturaciones SpA. Los usuarios internos pueden registrar las solicitudes manualmente o recibirlas de forma automática desde el correo electrónico (IMAP), donde el sistema clasifica el mensaje, extrae los datos de facturación y guarda sus adjuntos (PDF, PNG o JPEG). El sistema valida los campos obligatorios, administra clientes y usuarios según sus roles, y controla los estados del trámite: Pendiente, En revisión y Aprobada, además de En corrección y Rechazada.

Cada solicitud maneja versiones de factura que el Administrador valida. Con una versión aprobada se genera el archivo DTE (XML) para el SII, que puede revisarse en una vista previa, conservarse como respaldo para auditoría y enviarse por correo mediante SMTP. La aplicación incluye un panel con totales y actividad reciente, notificaciones por correo al Administrador, cambio y recuperación de contraseñas, y un historial de acciones para la trazabilidad de las operaciones realizadas por los usuarios.

## Puesta en marcha

Desde la carpeta `Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/`:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env      # completar SECRET_KEY, BD, SMTP/IMAP y EMPRESA_*
```

1. Sobre la base `facturaciones_spa_mvp`, ejecutar los scripts de `migrations/` en orden (001 a 005).
2. `python seed.py` crea los roles y el Administrador inicial.
3. `python run.py` inicia el servidor en <http://127.0.0.1:5000>.
4. `pytest` ejecuta las pruebas.

El flujo correo → factura → SII y las medidas de seguridad están descritos en `docs/flujo_correo_factura.md`.

## Estructura de la Plataforma Web

```text
Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/
├── CAPSTONE/                          # Documentación académica (Fase 2)
│   └── Fase 2/
│       ├── Evidencia Grupal/
│       └── Evidencia Individual/
├── Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/
│   ├── app/
│   │   ├── admin/                     # Usuarios, auditoría y bandeja de correos
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── auth/                      # Inicio de sesión y contraseñas
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── cli/                       # Comandos flask (smtp-prueba, imap-prueba, correo-revisar)
│   │   │   └── __init__.py
│   │   ├── clientes/
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── solicitudes/
│   │   │   ├── __init__.py
│   │   │   └── routes.py
│   │   ├── services/                  # Lógica de negocio
│   │   │   ├── __init__.py
│   │   │   ├── adjuntos.py            # Documentos adjuntos (PDF, PNG, JPEG)
│   │   │   ├── clientes.py
│   │   │   ├── contrasenas.py         # Cambio, restablecimiento y recuperación
│   │   │   ├── correo.py              # Transporte SMTP
│   │   │   ├── correo_entrante.py     # Lectura IMAP y creación de solicitudes
│   │   │   ├── correos_solicitud.py   # Envío del XML al receptor
│   │   │   ├── dte_sii.py             # Generación del DTE (XML) para el SII
│   │   │   ├── envios_solicitud.py
│   │   │   ├── extraccion_correo.py   # Clasificación y extracción de datos
│   │   │   ├── facturas.py            # Versiones de factura y validación
│   │   │   ├── notificaciones.py      # Avisos al Administrador
│   │   │   ├── panel.py               # Totales y actividad del panel
│   │   │   ├── registros_xml.py
│   │   │   ├── revision_automatica.py # Revisión de la bandeja en segundo plano
│   │   │   ├── solicitudes.py
│   │   │   ├── usuarios.py
│   │   │   ├── validaciones.py
│   │   │   └── vista_xml.py           # Vista previa del XML
│   │   ├── registros/                 # Datos privados; no se versionan
│   │   │   ├── adjuntos/
│   │   │   ├── correos/
│   │   │   ├── sii/
│   │   │   └── xml/
│   │   ├── static/
│   │   │   ├── css/
│   │   │   │   ├── app.css
│   │   │   │   └── login.css
│   │   │   ├── img/
│   │   │   └── js/
│   │   │       ├── app.js
│   │   │       ├── auto-actualizar.js
│   │   │       ├── login.js
│   │   │       └── ui.js
│   │   ├── templates/
│   │   │   ├── admin/                 # auditoria, correos, usuarios, usuario_editar, password_restablecida
│   │   │   ├── auth/                  # login, recuperar, cambiar_password
│   │   │   ├── clientes/              # formulario, listado
│   │   │   ├── correos/               # Plantillas de texto de los correos enviados
│   │   │   ├── errores/               # error
│   │   │   ├── solicitudes/           # listado, nueva, detalle, editar, factura, vista_xml, _proceso
│   │   │   ├── _ui.html
│   │   │   ├── base.html
│   │   │   └── dashboard.html
│   │   ├── __init__.py
│   │   ├── auditoria_acciones.py
│   │   ├── extensions.py
│   │   ├── models.py
│   │   ├── permisos.py
│   │   └── security.py
│   ├── docs/
│   │   └── flujo_correo_factura.md
│   ├── migrations/                    # Scripts SQL 001 a 005
│   ├── test/                          # Pruebas con pytest
│   ├── .env.example
│   ├── config.py
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── run.py
│   └── seed.py
├── .gitignore
└── README.md
```
