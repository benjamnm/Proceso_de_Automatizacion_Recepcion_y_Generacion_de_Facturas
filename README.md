# Proceso de Automatización Recepción y Generación de Facturas.

Proyecto CAPSTONE 005D

Integrantes: Carla Correa, Vicente Oyarzún, Benjamín Arevalo, Vicente Valenzuela.

Asignatura: Capstone

Docente: Cindy Contador.

**Descripción del proyecto**

Aplicación web la cual permite centralizar y gestionar las solicitudes de facturación de Facturaciones SpA, permitiendo a los usuarios internos registrar manualmente las solicitudes, consultar sus antecedentes y realizar seguimiento de su estado. El sistema contempla el registro del canal de origen de cada solicitud (correo electrónico, WhatsApp o web), la validación de los campos obligatorios, la administración de clientes y usuarios según sus roles y el control de los estados del trámite: Pendiente, En revisión y Emitida.

Además, permite asociar el archivo XML correspondiente a la factura emitida, conservarlo como respaldo para auditoría y enviarlo por correo electrónico mediante SMTP. La aplicación incorpora un historial de acciones para facilitar la trazabilidad de las operaciones realizadas por los usuarios.

## Estructura de la Plataforma Web

```text
Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/
├── app/
│   ├── __pycache__/
│   ├── admin/
│   │   ├── __pycache__/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── auditoria.html
│   │   ├── usuario_editar.html
│   │   └── usuarios.html
│   ├── auth/
│   │   ├── __pycache__/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── login.html
│   ├── clientes/
│   │   ├── __pycache__/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── formulario.html
│   │   └── listado.html
│   ├── services/
│   │   ├── __pycache__/
│   │   ├── __init__.py
│   │   ├── clientes.py
│   │   ├── solicitudes.py
│   │   ├── tokens_solicitud.py
│   │   ├── usuarios.py
│   │   └── validaciones.py
│   ├── solicitudes/
│   │   ├── __pycache__/
│   │   ├── detalle.html
│   │   ├── editar.html
│   │   ├── listado.html
│   │   └── nueva.html
│   ├── static/
│   │   ├── CSS/
│   │   │   ├── app.css
│   │   │   └── login.css
│   │   └── js/
│   │       ├── login.js
│   │       └── solicitudes.js
│   ├── templates/
│   │   ├── admin/
│   │   ├── auth/
│   │   ├── clientes/
│   │   ├── solicitudes/
│   │   ├── base.html
│   │   └── dashboard.html
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
│   └── security.py
├── docs/
├── instance/
├── migrations/
├── test/
├── venv/
├── .env.example
├── .gitignore
├── config.py
├── package-lock.json
├── package.json
├── requirements.txt
├── run.py
├── seed.py
├── .env.local
├── README.md
└── requirements.txt
```

