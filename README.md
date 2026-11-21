# Proceso de Automatización Recepción y Generación de Facturas

Proyecto CAPSTONE 005D — Carla Correa, Vicente Oyarzún, Benjamín Arevalo, Vicente Valenzuela. Docente: Cindy Contador.

Aplicación web (Flask + MySQL) que centraliza las solicitudes de facturación de Facturaciones SpA: registro manual o automático desde correo (IMAP), validación de datos, gestión de clientes y usuarios por rol, versiones de factura con validación del Administrador, generación del DTE (XML) para el SII y auditoría de todas las acciones.

Estados de una solicitud: Pendiente → En revisión → Aprobada, con En corrección y Rechazada.

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

El flujo correo → factura → SII y las medidas de seguridad están en [docs/flujo_correo_factura.md](Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/docs/flujo_correo_factura.md).

## Estructura

```text
Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/
├── app/
│   ├── admin/ auth/ clientes/ solicitudes/   # blueprints (rutas)
│   ├── cli/                                  # comandos flask (smtp-prueba, imap-prueba, correo-revisar)
│   ├── services/                             # lógica de negocio
│   ├── registros/                            # datos privados (XML, correos, DTE, adjuntos); no se versionan
│   ├── static/ templates/
│   ├── security.py permisos.py models.py
├── docs/
├── migrations/
├── test/
├── config.py run.py seed.py
└── .env.example
```
