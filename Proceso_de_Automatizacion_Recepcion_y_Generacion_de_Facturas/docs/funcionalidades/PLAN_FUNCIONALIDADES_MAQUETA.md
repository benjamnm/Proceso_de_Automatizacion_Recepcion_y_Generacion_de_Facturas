# Plan de implementación — Funcionalidades nuevas para el rediseño (Facturaciones SpA)

> **Para:** Claude Code, ejecutando fase por fase.
> **Objetivo:** agregar al backend las cinco funcionalidades que la maqueta muestra y que hoy no existen. Así, el rediseño posterior (`docs/diseno/PLAN_REDISENO_PLATAFORMA.md`) puede aplicarse completo sin datos ficticios.
> **Base revisada:** `app/solicitudes/routes.py`, `app/services/solicitudes.py`, `app/services/registros_xml.py`, `app/admin/routes.py`, `app/services/usuarios.py`, `app/__init__.py`, `app/security.py`, `config.py`, `migrations/001–003`, `test/*`.

---

## 0. Alcance

| # | Funcionalidad | ¿Requiere migración? |
|---|---|---|
| F1 | Columnas Concepto, Origen y Responsable en el listado de solicitudes | No |
| F2 | Búsqueda de solicitudes por cliente o concepto, con resultados completos y paginados en el servidor | No (índice opcional en 004) |
| F3 | Totales (solicitudes por estado, usuarios, clientes, eventos) y “Actividad reciente” | No (índice opcional en 004) |
| F4 | Sección “Perfiles y permisos” (solo lectura) | No |
| F5 | Adjuntar documentos al crear una solicitud | **Sí: `migrations/004_adjuntos_solicitud.sql`** |

**Orden de las fases:** de menor a mayor riesgo. F5 va al final porque es la única que crea una tabla, guarda archivos y cambia un límite global.

**Diseño:** en este plan las plantillas solo se tocan lo necesario y con las clases de Bootstrap actuales. El aspecto final lo aplica después el plan de rediseño, que se actualizará para incluir estas funcionalidades.

---

## 1. Reglas obligatorias

### 1.1 No romper nada existente
1. **Ningún test existente se modifica ni se elimina.** Solo se agregan tests nuevos. Si uno existente falla, se corrige el código, no el test.
2. **No se modifica:**
   - `app/security.py`: decoradores, CSP, límite de intentos de login, inactividad y cabeceras;
   - `app/auth/**`;
   - `app/extensions.py`;
   - las migraciones 001–003;
   - el flujo de facturas (`services/facturas.py`, `dte_sii.py`, `notificaciones.py`), el de correo (`correo*.py`, `extraccion_correo.py`) y `envios_solicitud.py`.
3. **Las rutas existentes conservan:**
   - URL, método y decorador de permisos;
   - los nombres de los campos de formulario y de los parámetros GET que ya existen;
   - los mensajes que los tests verifican.
4. **Las claves que ya entrega `resumen_panel()`** (`estados['En revisión']` con `id` y `total`, `correos_por_revisar`) se mantienen con el mismo formato, porque `dashboard.html` las usa. `app.resumen_panel` debe seguir existiendo con ese nombre (los tests la reemplazan con `monkeypatch`).
5. Las migraciones **no se ejecutan contra la base de datos**: Claude Code solo escribe el archivo `.sql`. Lo ejecuta la persona en phpMyAdmin, después de respaldar.

### 1.2 Seguridad, en cada consulta y cada ruta nueva
- **SQL siempre con parámetros** (`%s`). Solo se puede interpolar en el texto SQL un `WHERE` armado con fragmentos fijos del código, como ya hace `construir_filtros()`.
- **Mismo alcance por rol que hoy:**
  - el Emisor solo ve sus solicitudes (`s.emisor_id = current_user.id`);
  - el Administrador ve todo;
  - el Lector no accede a solicitudes.

  Toda consulta nueva sobre solicitudes reutiliza esa condición.
- **Auditoría:** la tabla `auditoria` (con IP y detalle) es solo para el Administrador. Ningún dato de auditoría se muestra al Emisor.
- **Escritura:** toda escritura nueva registra un evento con `registrar_evento()`, en la misma transacción que la escritura.
- **Archivos:**
  - se guardan fuera de `/static`, con nombre aleatorio;
  - se descargan solo por una ruta protegida y siempre como descarga, nunca para verse en el navegador;
  - se validan por contenido, no solo por extensión.
- **Plantillas:** sin `style=`, `onclick=`, `onsubmit=` ni `<script>` en línea (`test_seguridad.py`).

### 1.3 Archivos que se pueden tocar

| Archivo | Uso |
|---|---|
| `app/solicitudes/routes.py` | F1, F2, F5 |
| `app/services/solicitudes.py` | F5: parámetro opcional `adjuntos` en `crear_solicitud` |
| `app/services/panel.py` (nuevo) | F3 |
| `app/services/adjuntos.py` (nuevo) | F5 |
| `app/permisos.py` (nuevo) | F4 |
| `app/auditoria_acciones.py` (nuevo) | F3: lista blanca y etiquetas de eventos |
| `app/__init__.py` | F3: `resumen_panel()`; F5: rama nueva en el manejador 413 |
| `app/admin/routes.py` | F3: usar la lista blanca compartida; F4 |
| `config.py`, `.env.example`, `.gitignore` | F5 |
| `migrations/004_adjuntos_solicitud.sql` (nuevo) | F5 |
| `app/registros/adjuntos/.gitkeep` (nuevo) | F5 |
| `app/templates/solicitudes/listado.html`, `nueva.html`, `detalle.html`, `dashboard.html`, `admin/usuarios.html` | Marcado mínimo con Bootstrap actual |
| `test/test_*.py` (nuevos) | Tests de cada fase |

### 1.4 Forma de trabajo
- Rama `feat/funcionalidades-maqueta`, creada desde la rama principal actualizada.
- Una fase = un commit, con `pytest -q` en verde.
- Al cerrar cada fase, entregar un resumen: archivos tocados, tests agregados, resultado de `pytest` y qué **no** se verificó (consultas reales contra MariaDB, render en navegador).

---

## 2. Fase 0 — Preparación

1. Ejecutar `pytest -q` y anotar el resultado base. Si algo falla antes de empezar, detenerse e informar.
2. **Confirmar el esquema real.** El volcado `facturaciones_spa_mvp.sql` del proyecto es anterior a la migración 003. El esquema vigente es ese volcado **más** `migrations/001–003`. Pedir a la persona que ejecute en phpMyAdmin y pegue el resultado:
   ```sql
   SHOW CREATE TABLE solicitudes;
   SHOW CREATE TABLE auditoria;
   SELECT id, nombre FROM estados_solicitud ORDER BY id;
   SELECT id, nombre FROM origenes_solicitud ORDER BY id;
   SELECT id, nombre, descripcion FROM roles ORDER BY id;
   ```
   Si algo no coincide con lo que asume este plan (sección 8), detenerse y avisar.
3. Sin commit.

---

## 3. Fase 1 — Columnas Concepto, Origen y Responsable (F1)

**Hoy:** la consulta de `listado()` trae `public_id, rut, nombre, fecha_emision, monto_bruto, email_emisor, estado_nombre`.

**Cambios en `listado()` (`app/solicitudes/routes.py`):**
- Agregar a la consulta de datos:
  ```sql
  s.concepto,
  o.nombre AS origen_nombre,
  u.nombre AS responsable_nombre
  ...
  INNER JOIN origenes_solicitud AS o ON o.id = s.origen_id
  LEFT JOIN usuarios AS u ON u.id = s.emisor_id
  ```
- Se usa `LEFT JOIN` con `usuarios` para que una fila nunca desaparezca. `emisor_id` es `NOT NULL` con clave foránea, pero el `LEFT JOIN` es más seguro ante datos raros.
- La consulta `COUNT(*)` **no** cambia: los joins nuevos no filtran.

**Plantilla `solicitudes/listado.html`:**
- **Concepto:** `{{ solicitud.concepto | truncate(60, True) }}`, con el texto completo en el atributo `title`. Jinja lo escapa.
- **Origen:** `{{ solicitud.origen_nombre }}`.
- **Responsable:** `{{ solicitud.responsable_nombre or '—' }}`, **solo si `es_admin`**. Al Emisor no le aporta nada, porque solo ve sus propias solicitudes.
- La tabla ya está dentro de `.table-responsive`; verificarlo.

**Tests nuevos (`test/test_listado_columnas.py`):**
- Con `get_db_connection` simulado, como en `test_volver_desde_listado_lleva_al_panel`: el Administrador ve el encabezado “Responsable” y el Emisor no.
- La columna Concepto escapa HTML: un concepto `<b>x</b>` se ve como texto.

**Commit:** `feat(solicitudes): columnas concepto, origen y responsable en el listado`

---

## 4. Fase 2 — Búsqueda por cliente o concepto (F2)

**Problema:** el filtro actual es solo por RUT exacto. Filtrar con JavaScript la página visible daría resultados incompletos, porque el listado pagina de a 20.

**Solución:** dos filtros nuevos **en el servidor**, que se combinan con los existentes y se conservan al paginar.

| Parámetro GET | Qué busca | Validación |
|---|---|---|
| `q` | Texto libre en razón social histórica (`s.nombre`) **o** concepto (`s.concepto`) | Se recortan los espacios. Si viene vacío se ignora; si no, 2 a 100 caracteres. Se rechazan caracteres de control. Error: “La búsqueda debe tener entre 2 y 100 caracteres.” |
| `cliente_id` | Cliente exacto (`s.cliente_id`) | Igual que `estado_id`: entero de 1 a 4294967295 |

**Cambios en `construir_filtros()`:**
1. Agregar `"q"` y `"cliente_id"` a `CAMPOS_FILTRO`. Con eso, `argumentos` ya los conserva en `anterior_url` y `siguiente_url`.
2. Para `q`, escapar los comodines antes de usar `LIKE`:
   ```python
   patron = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
   condiciones.append("(s.nombre LIKE %s OR s.concepto LIKE %s)")
   parametros.extend([patron, patron])
   ```
   La colación `utf8mb4_unicode_ci` ya ignora mayúsculas y tildes.
3. `cliente_id` se agrega al bucle que hoy valida `estado_id` y `emisor_id`, con la columna `s.cliente_id`. **No** se restringe solo al Administrador: el Emisor sigue limitado a sus solicitudes por la condición de alcance que ya existe.

**Lista de clientes para el selector (nueva función `obtener_clientes_filtro()`):**
- **Administrador:** todos los clientes, activos e inactivos, porque hay solicitudes históricas:
  `SELECT id, rut, razon_social FROM clientes ORDER BY razon_social`.
- **Emisor:** solo los clientes de **sus** solicitudes, para no mostrarle la cartera completa:
  ```sql
  SELECT DISTINCT c.id, c.rut, c.razon_social
  FROM solicitudes AS s
  INNER JOIN clientes AS c ON c.id = s.cliente_id
  WHERE s.emisor_id = %s
  ORDER BY c.razon_social
  ```

**Plantilla `listado.html`:**
- Agregar al formulario de filtros existente (GET) un campo `q` (`maxlength="100"`, etiqueta “Cliente o concepto”) y un `select` `cliente_id` (“Todos los clientes” + la lista).
- El filtro RUT existente no cambia.

**Rendimiento:** `LIKE '%texto%'` recorre la tabla. Para el volumen de un MVP local es suficiente. Si más adelante crece, evaluar un índice `FULLTEXT`; no hacerlo ahora, porque cambia el comportamiento con palabras cortas.

**Tests nuevos (`test/test_busqueda_solicitudes.py`)** sobre `construir_filtros()` en un `test_request_context`:
- `q` produce la condición `LIKE` con `%` y `_` escapados, y dos parámetros iguales.
- `q` de 1 carácter o de 101 caracteres → error; vacío → sin condición.
- `cliente_id=abc` → error; `cliente_id=5` → condición `s.cliente_id = %s`.
- Emisor con `q`: la primera condición sigue siendo `s.emisor_id = %s`.
- `siguiente_url` conserva `q` y `cliente_id` (test de ruta con conexión simulada que devuelve `total = 25`).

**Commit:** `feat(solicitudes): búsqueda por cliente o concepto en el servidor`

---

## 5. Fase 3 — Totales y “Actividad reciente” (F3)

### 5.1 Lista blanca de eventos compartida (`app/auditoria_acciones.py`, nuevo)
- Mover la tupla de acciones que hoy está escrita dentro del SQL de `admin.auditoria()` a una constante `ACCIONES_VISIBLES`, con **los mismos 25 valores**. Agregar las de F5 (`ADJUNTO_CARGADO`, `ADJUNTO_DESCARGADO`) en la Fase 5, no antes.
- Agregar `ETIQUETAS_ACCION`, un diccionario `accion → texto legible`. Ejemplos: `SOLICITUD_CREADA → "Solicitud creada"`, `FACTURA_APROBADA → "Factura aprobada"`. Una acción sin etiqueta muestra el código tal cual.
- `admin.auditoria()` construye el `IN (...)` con marcadores: `", ".join(["%s"] * len(ACCIONES_VISIBLES))`, pasando la tupla como parámetros. **El resultado de la página de auditoría no debe cambiar.**

### 5.2 Servicio `app/services/panel.py` (nuevo)

`resumen_administrador()` devuelve:
```python
{
  "estados": {nombre: {"id", "nombre", "total"}},  # TODOS los estados (LEFT JOIN, incluye ceros)
  "solicitudes_total": int,
  "correos_por_revisar": int,                       # misma consulta que hoy
  "usuarios": {"activos": int, "total": int},       # excluye al usuario técnico (email = SISTEMA_CORREO_EMAIL)
  "clientes": {"activos": int, "total": int},
  "eventos_total": int,                             # COUNT(*) de auditoria con accion IN ACCIONES_VISIBLES
  "actividad": [ ... ],                             # últimos 8 eventos (ver 5.3)
}
```

`resumen_emisor(usuario_id)` devuelve:
```python
{
  "estados": {...},          # solo sus solicitudes (… AND s.emisor_id = %s dentro del LEFT JOIN)
  "solicitudes_total": int,
  "actividad": [ ... ],      # sus 5 solicitudes actualizadas más recientemente (ver 5.3)
}
```

**Detalle importante del SQL:** en el `LEFT JOIN` de estados, la condición de alcance va **en el `ON`**, no en el `WHERE`. Si va en el `WHERE`, desaparecen los estados con total 0:
```sql
SELECT e.id, e.nombre, COUNT(s.id) AS total
FROM estados_solicitud AS e
LEFT JOIN solicitudes AS s
  ON s.estado_id = e.id AND s.emisor_id = %s
GROUP BY e.id, e.nombre
```

### 5.3 “Actividad reciente”
- **Administrador:** últimos 8 eventos de `auditoria` con `accion IN ACCIONES_VISIBLES`, ordenados por `a.id DESC`, con `LEFT JOIN usuarios` para el nombre del responsable. Se entrega **solo**: `creado_en`, `etiqueta`, `usuario_nombre` y `public_id`, este último **solo si** el detalle lo trae y cumple `^[0-9a-f]{32}$`. **No** se entregan ni la IP ni el detalle completo.
- **Emisor:** **no** usa auditoría. Consulta sus últimas 5 solicitudes:
  `SELECT s.public_id, s.nombre, s.actualizado_en, e.nombre AS estado_nombre … WHERE s.emisor_id = %s ORDER BY s.actualizado_en DESC LIMIT 5`.

### 5.4 `resumen_panel()` en `app/__init__.py`
- Mantener el nombre y la firma.
- Administrador → `resumen_administrador()`; Emisor → `resumen_emisor(current_user.id)`; otro rol → `None`.
- Mantener el `try/except pymysql.MySQLError` que devuelve `None` y deja una advertencia en el log.
- Las claves `estados` y `correos_por_revisar` siguen sirviendo a las tarjetas actuales: `estados.get('En revisión')` todavía existe.

### 5.5 Plantilla `dashboard.html`
- **Bloque “Resumen”, para cualquier `resumen` no nulo:**
  - una tarjeta por estado con su total, cada una enlazada a `solicitudes.listado` con `estado_id`;
  - el total de solicitudes.
- **Solo Administrador:** usuarios activos/total (enlace a `admin.usuarios`), clientes activos/total (enlace a `clientes.listado`) y eventos (enlace a `admin.auditoria`).
- **“Actividad reciente”:** una tabla simple. Si hay `public_id`, la fila enlaza a `solicitudes.detalle`.
- Las tarjetas existentes se conservan.
- **La palabra “Volver” no puede aparecer** (`test_navegacion`).
- Si `resumen` es `None`, la página se ve como hoy.

### 5.6 Tests nuevos (`test/test_panel.py`)
- **SQL:** `resumen_emisor(7)` con un cursor falso que registra el SQL y los parámetros: todas las consultas incluyen `emisor_id` con el parámetro 7 y ninguna toca `auditoria`.
- **Actividad del Administrador:** un evento con detalle `{"public_id": "<script>"}` no produce `public_id` en la salida; la IP nunca aparece en la salida.
- **Ruta `/dashboard`** con `app.resumen_panel` reemplazado:
  - el Administrador ve “Usuarios” y “Actividad reciente”;
  - el Emisor no ve “Usuarios”;
  - el Lector ve el panel sin resumen;
  - `"Volver"` no aparece.
- **Auditoría:** `admin.auditoria()` sigue usando las 25 acciones. Comparar el tamaño de la tupla y verificar que el SQL use marcadores `%s`.

**Commit:** `feat(panel): totales por estado, usuarios, clientes y actividad reciente`

---

## 6. Fase 4 — “Perfiles y permisos” (F4)

**Decisión:** la sección es **de solo lectura** y describe los permisos **reales**. Hacer editables los permisos exigiría cambiar el modelo de autorización (tablas de permisos y decoradores nuevos), lo que pone en riesgo la seguridad. Queda fuera de alcance (sección 10).

### 6.1 `app/permisos.py` (nuevo)
Una sola fuente que documenta qué puede hacer cada rol, escrita según los decoradores **actuales**: `admin_required` = Administrador; `solicitud_required` = Administrador y Emisor; `login_required` = cualquier usuario activo.

```python
CAPACIDADES = (
    # (texto visible, roles permitidos, ruta de ejemplo para el test)
    ("Ver el panel principal",              {"Administrador", "Emisor", "Lector"}, "/dashboard"),
    ("Crear y consultar sus solicitudes",   {"Administrador", "Emisor"},           "/solicitudes/"),
    ("Consultar todas las solicitudes",     {"Administrador"},                     None),
    ("Validar facturas",                    {"Administrador"},                     None),
    ("Gestionar clientes",                  {"Administrador"},                     "/clientes/"),
    ("Gestionar usuarios",                  {"Administrador"},                     "/admin/usuarios"),
    ("Revisar la bandeja de correos",       {"Administrador"},                     "/admin/correos"),
    ("Consultar la auditoría",              {"Administrador"},                     "/admin/auditoria"),
)
```

Antes de dar por cerrada la lista, verificar en el código cada fila con `ruta = None` (por ejemplo, que aprobar factura exige Administrador dentro de `factura_aprobar`) y corregir el texto si no coincide.

### 6.2 Ruta y plantilla
- En `admin.usuarios()`, consultar además `SELECT r.id, r.nombre, r.descripcion, COUNT(u.id) AS usuarios_activos FROM roles r LEFT JOIN usuarios u ON u.rol_id = r.id AND u.activo = 1 GROUP BY r.id, r.nombre, r.descripcion ORDER BY r.id`. Pasar `perfiles` y `capacidades` a la plantilla.
- **Este cambio en `admin.usuarios()` es solo de lectura**: la creación de usuarios no se toca.
- En `admin/usuarios.html`, agregar al final una sección “Perfiles y permisos”: una tarjeta por rol (nombre, descripción de la BD, usuarios activos) y una tabla de capacidades × roles con ✓/—, usando `bi-check-lg` y `aria-label`.

### 6.3 Tests nuevos (`test/test_permisos.py`)
- **Consistencia:** para cada capacidad con ruta y cada rol que **no** la tiene, `GET ruta` → 403. Si la ruta no responde 403 para un rol no permitido, la matriz miente y el test falla.
- La sección aparece para el Administrador (`/admin/usuarios` con conexión simulada) y el Emisor recibe 403 en `/admin/usuarios` (ya cubierto por un test existente).

> **Pregunta abierta para la persona, sin bloquear la fase:** hoy el rol **Lector** solo puede ver el panel. La sección lo mostrará así. Si el Lector debe consultar solicitudes, es un cambio de permisos aparte, que no se hace en este plan.

**Commit:** `feat(admin): sección de perfiles y permisos de solo lectura`

---

## 7. Fase 5 — Adjuntar documentos al crear una solicitud (F5)

### 7.1 Reglas del adjunto

| Regla | Valor |
|---|---|
| Tipos permitidos | PDF (`.pdf`), PNG (`.png`) y JPEG (`.jpg`, `.jpeg`). **Sin** Office, ZIP, HTML ni SVG (pueden traer macros o scripts) |
| Validación de tipo | La extensión **y** los primeros bytes deben coincidir: PDF `%PDF-`, PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff` |
| PDF activo | Se rechaza un PDF que contenga `/JavaScript`, `/JS`, `/Launch` o `/EmbeddedFile`. Es una revisión simple; la descarga forzada (abajo) es la protección principal |
| Tamaño por archivo | Máximo 5 MB (`MAX_ADJUNTO_BYTES`); un archivo vacío se rechaza |
| Cantidad | Máximo 3 por solicitud (`MAX_ADJUNTOS_SOLICITUD`) |
| Nombre original | De 1 a 255 caracteres, sin caracteres de control ni separadores de ruta; `secure_filename()` debe conservar la extensión. Se guarda solo como dato visible |
| Nombre en disco | `uuid4().hex + extensión`, en `ADJUNTOS_FOLDER` (privado, fuera de `/static`) |
| Tipo MIME al descargar | Lo fija el servidor según el tipo detectado, **nunca** el que envía el navegador |
| Descarga | Siempre `as_attachment=True` y `max_age=0`. Las cabeceras globales ya aplican `nosniff` y `no-store` |
| Quién puede descargar | Las mismas personas que pueden ver la solicitud (Administrador o Emisor dueño) |
| Auditoría | `ADJUNTO_CARGADO` (uno por archivo, con `adjunto_id`, nombre, tamaño y `sha256`) y `ADJUNTO_DESCARGADO` |

### 7.2 Migración `migrations/004_adjuntos_solicitud.sql`
Re-ejecutable y con el mismo encabezado y advertencia de respaldo que la 003:

```sql
CREATE TABLE IF NOT EXISTS `adjuntos_solicitud` (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `solicitud_id` int(10) UNSIGNED NOT NULL,
  `nombre_original` varchar(255) NOT NULL,
  `nombre_almacenado` varchar(40) NOT NULL,
  `tipo` enum('PDF','PNG','JPEG') NOT NULL,
  `tamano` int(10) UNSIGNED NOT NULL,
  `sha256` char(64) NOT NULL,
  `subido_por` int(10) UNSIGNED NOT NULL,
  `subido_en` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_adjuntos_almacenado` (`nombre_almacenado`),
  KEY `idx_adjuntos_solicitud` (`solicitud_id`),
  KEY `idx_adjuntos_subido_por` (`subido_por`),
  CONSTRAINT `fk_adjuntos_solicitud`
    FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`),
  CONSTRAINT `fk_adjuntos_usuario`
    FOREIGN KEY (`subido_por`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Opcional (F3): acelera la actividad reciente del Emisor.
ALTER TABLE `solicitudes`
  ADD KEY IF NOT EXISTS `idx_solicitud_emisor_actualizado` (`emisor_id`, `actualizado_en`);

-- Verificación
SHOW CREATE TABLE `adjuntos_solicitud`;
```

### 7.3 Configuración
- **`config.py`:**
  - `ADJUNTOS_FOLDER`, con el mismo patrón que `XML_UPLOAD_FOLDER` y valor por defecto `app/registros/adjuntos`;
  - `MAX_ADJUNTO_BYTES = 5 * 1024 * 1024`;
  - `MAX_ADJUNTOS_SOLICITUD = 3`;
  - **`MAX_CONTENT_LENGTH` pasa de 6 MB a 16 MB**: 3 archivos de 5 MB más el formulario. Ver el impacto en 7.7.
- **`.env.example`:** agregar `ADJUNTOS_FOLDER=` comentado, como opcional.
- **`.gitignore`:** agregar, con el mismo patrón de las carpetas `xml`, `correos` y `sii`:
  ```
  Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/app/registros/adjuntos/*
  !Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/app/registros/adjuntos/.gitkeep
  ```
  Crear `app/registros/adjuntos/.gitkeep`.
- **`test/conftest.py` no se modifica.** Los tests de F5 crean su propia app con `ADJUNTOS_FOLDER = tmp_path / "adjuntos"`.

### 7.4 Servicio `app/services/adjuntos.py` (nuevo)
- `class ErrorAdjunto(Exception)`.
- **`leer_adjuntos(archivos) -> list[dict]`:**
  - ignora las partes sin nombre (el navegador envía una vacía si no se eligió archivo);
  - aplica las reglas de 7.1 leyendo como máximo `limite + 1` bytes;
  - devuelve `{"nombre_original", "contenido", "tipo", "extension", "mimetype", "tamano", "sha256"}`;
  - no toca disco ni BD.
- **`guardar_adjuntos(cursor, solicitud_id, actor_id, adjuntos) -> (ids, rutas_escritas)`:**
  - inserta las filas;
  - escribe cada archivo con `open(ruta, "xb")`;
  - devuelve las rutas escritas para poder limpiarlas;
  - **no** hace commit.
- **`listar_adjuntos(solicitud_id)`:** `id`, `nombre_original`, `tipo`, `tamano` y `subido_en`, sin el nombre en disco.
- **`obtener_adjunto_autorizado(actor_id, public_id, adjunto_id)`:**
  - reutiliza `obtener_actor` y `obtener_solicitud` de `registros_xml.py` (mismo control de dueño);
  - exige `adjunto.solicitud_id == solicitud.id`;
  - valida que `os.path.basename(nombre_almacenado) == nombre_almacenado` y que el archivo exista;
  - devuelve los datos y la ruta.

### 7.5 Integración en `crear_solicitud()`
- **Firma:** `crear_solicitud(actor_id, datos, clave_idempotencia, ip=None, adjuntos=None)`. Con `adjuntos=None` el comportamiento queda **idéntico** al actual.
- **Idempotencia:** si hay adjuntos, la huella incluye sus `sha256` ordenados:
  `huella = sha256(huella_de_creacion(limpio) + "|" + ",".join(sorted(shas)))`.
  Sin adjuntos, la huella es la de siempre. Así, reenviar el mismo formulario con otros archivos se detecta como “otros datos”.
- **Repetición del mismo envío** (`existente` encontrado): no se escriben archivos y se devuelve el `public_id` existente, como hoy.
- **Solicitud nueva:**
  1. después de `insertar_solicitud`, llamar a `guardar_adjuntos(...)`;
  2. registrar `SOLICITUD_CREADA` (agregando `"adjuntos": n` al detalle) y un `ADJUNTO_CARGADO` por archivo;
  3. hacer `commit`.
- **Si falla cualquier paso:** `rollback` y borrar todas las rutas escritas, como hace `guardar_xml()`. Nunca debe quedar un archivo sin su fila ni una fila sin su archivo.

### 7.6 Rutas (`app/solicitudes/routes.py`)
- **`nueva()` en POST:**
  - `adjuntos = leer_adjuntos(request.files.getlist("adjuntos"))` dentro de un `try`;
  - si ocurre un `ErrorAdjunto`, se guarda en `errores["adjuntos"]` y se muestra con los demás errores;
  - se pasa `adjuntos` a `crear_solicitud`;
  - un `OSError` al escribir se registra en el log y se informa con “No se pudo guardar un archivo adjunto. Puede reintentar.”
- **Nueva ruta** `GET /solicitudes/<public_id>/adjuntos/<int:adjunto_id>` → `descargar_adjunto`, con `@solicitud_required`:
  - mismo patrón que `descargar_xml()`: auditar `ADJUNTO_DESCARGADO` y luego `send_file(ruta, mimetype=<del servidor>, as_attachment=True, download_name=nombre_original, max_age=0)`;
  - si no está autorizado o no existe, mostrar el mensaje y volver al detalle.
- **`detalle()`:** pasar `adjuntos=listar_adjuntos(solicitud["id"])`.
- **Manejador 413 (`app/__init__.py`):** agregar una rama para `request.endpoint == "solicitudes.nueva"` que muestre el aviso “Los archivos superan el tamaño máximo permitido (5 MB por archivo, 3 archivos).” y redirija a `solicitudes.nueva`. **La rama de `cargar_xml` no cambia.**
- Agregar `ADJUNTO_CARGADO` y `ADJUNTO_DESCARGADO` a `ACCIONES_VISIBLES` y a `ETIQUETAS_ACCION`.

### 7.7 Impacto de subir `MAX_CONTENT_LENGTH` y cómo se contiene
- Los otros formularios aceptan cuerpos más grandes, hasta 16 MB. El riesgo es acotado: la app corre en local y los campos de texto siguen limitados por `MAX_FORM_MEMORY_SIZE` de Werkzeug (500 KB por defecto).
- **XML:** sigue limitado a 5 MB por `guardar_xml()`, que lee `limite + 1`. El test `test_xml_demasiado_grande_redirige_con_mensaje` (7 MB) ahora llega a `guardar_xml()` en vez de al manejador 413. **Confirmar que sigue pasando:** el mensaje “El XML supera el límite de 5 MB.” contiene “5 MB” y la ruta redirige al detalle. Si no pasa, ajustar `cargar_xml()`, **no** el test.
- **Correos entrantes:** `IMAP_MAX_BYTES` es independiente y no cambia.

### 7.8 Plantillas
- **`solicitudes/nueva.html`:**
  - agregar `enctype="multipart/form-data"` al `<form>`, sin cambiar sus otros atributos;
  - agregar un campo `<input type="file" name="adjuntos" id="adjuntos" class="form-control" multiple accept=".pdf,.png,.jpg,.jpeg">`, con un `form-text` que diga “Opcional. PDF, PNG o JPG; hasta 3 archivos de 5 MB.”;
  - si hay `errores.adjuntos`, mostrarlo, y avisar que al corregir errores hay que volver a seleccionar los archivos (el navegador no los conserva).
- **`solicitudes/detalle.html`:** una tarjeta “Documentos adjuntos” con la tabla de nombre, tipo, tamaño (KB), fecha y enlace “Descargar” a `solicitudes.descargar_adjunto`. Si no hay adjuntos: “Sin documentos adjuntos.”

### 7.9 Tests nuevos (`test/test_adjuntos.py`)
- **`leer_adjuntos`:**
  - PDF, PNG y JPEG válidos → OK;
  - `.pdf` que empieza con `PNG` → error;
  - `.exe`, `.svg` o `.html` → error;
  - 0 bytes → error;
  - 5 MB + 1 → error;
  - 4 archivos → error;
  - nombre de 256 caracteres → error;
  - nombre `../../x.pdf` → se rechaza o se neutraliza sin salir de la carpeta;
  - PDF con `/JavaScript` → error;
  - una parte sin nombre → se ignora.
- **`crear_solicitud` con conexión simulada:**
  - si `registrar_evento` falla, no queda ningún archivo en `tmp_path`;
  - en una repetición idempotente no se escriben archivos;
  - con `adjuntos=None` la huella es idéntica a la de hoy.
- **Descarga:**
  - el Emisor que no es dueño recibe el mensaje “no está disponible” (simulando `obtener_adjunto_autorizado`);
  - un `adjunto_id` de otra solicitud es rechazado;
  - la respuesta lleva `Content-Disposition: attachment` y el MIME del servidor.
- **Ruta `nueva`:** 17 MB → aviso de 5 MB y redirección a `/solicitudes/nueva`.
- **Plantillas:** la de nueva contiene `enctype="multipart/form-data"`, y el test de plantillas sin JS en línea sigue verde.

**Commit:** `feat(solicitudes): adjuntos PDF/imagen al crear una solicitud`

> **Paso para la persona antes de probar F5 en su equipo:** respaldar la BD (phpMyAdmin → Exportar → Rápido → SQL) y ejecutar `migrations/004_adjuntos_solicitud.sql`. Sin la tabla, crear una solicitud **con** adjuntos falla y se informa con un mensaje; crear una **sin** adjuntos sigue funcionando.

---

## 8. Supuestos del esquema (validar en la Fase 0)

| Supuesto | Fuente |
|---|---|
| Existen los estados `Pendiente`, `En revisión`, `Rechazada`, `En corrección` y `Aprobada` | Volcado + migración 003 |
| Existen los orígenes `Web` y `Correo` | Volcado + migración 003 |
| `solicitudes` tiene `concepto`, `origen_id`, `emisor_id`, `cliente_id` y `actualizado_en` | Volcado |
| `roles` tiene `descripcion` | Volcado |
| `auditoria.detalle` es JSON válido (`CHECK json_valid`) | Volcado |
| Existe el usuario técnico `sistema.correo@facturaciones.cl` | Migración 003 |
| Las tablas son InnoDB y MariaDB ≥ 10.5, que admite `ADD KEY IF NOT EXISTS` | Volcado (10.11.16) |

---

## 9. Verificación final

```bash
# Desde la carpeta que contiene app/
pytest -q

# Nada fuera del alcance (debe salir vacío)
git diff --name-only --relative main... | grep -vE '^(app/(solicitudes/routes\.py|services/(solicitudes|panel|adjuntos)\.py|permisos\.py|auditoria_acciones\.py|__init__\.py|admin/routes\.py|templates/(solicitudes/(listado|nueva|detalle)|dashboard|admin/usuarios)\.html|registros/adjuntos/\.gitkeep)|config\.py|\.env\.example|migrations/004_adjuntos_solicitud\.sql|test/test_(listado_columnas|busqueda_solicitudes|panel|permisos|adjuntos)\.py)$'

# Ningún test existente modificado (debe salir vacío)
git diff --name-only --relative --diff-filter=MD main... -- test/

# SQL con f-strings: revisar a mano que cada caso interpole solo fragmentos fijos
grep -n 'f"""' app/solicitudes/routes.py app/services/*.py app/admin/routes.py app/__init__.py

# Nada de JS ni estilos en línea
grep -rnE 'style=|onclick=|onsubmit=|<script>' app/templates
```

`.gitignore` está en la raíz del repositorio, fuera de la carpeta `app/`. Revisarlo aparte con `git diff main... -- ../.gitignore`.

**Prueba manual (la hace la persona), con Administrador y con Emisor:**
1. **Listado:** las nuevas columnas aparecen; Responsable solo para el Administrador.
2. **Búsqueda:** por texto de concepto y de razón social; combinada con estado y fechas; la página 2 conserva los filtros.
3. **Panel:** los totales coinciden con conteos manuales en phpMyAdmin; la actividad reciente enlaza al detalle; el Emisor no ve usuarios, clientes ni auditoría.
4. **Usuarios:** la sección “Perfiles y permisos” coincide con lo que cada rol realmente puede abrir.
5. **Adjuntos:**
   - crear con 0, 1 y 3 archivos;
   - intentar 4 archivos, un `.docx`, un `.pdf` renombrado desde `.txt` y un archivo de 6 MB;
   - descargar como dueño, como Administrador y como otro Emisor (este último debe ser rechazado).
6. **Regresión:** cargar y descargar XML, enviar a revisión, aprobar u observar, enviar por correo, la bandeja de correos y la auditoría siguen funcionando.

---

## 10. Fuera de alcance
- Permisos editables desde la interfaz (requiere un modelo de permisos nuevo).
- Cambiar qué puede hacer el rol Lector.
- Agregar o eliminar adjuntos después de crear la solicitud.
- Vista previa de PDF o imágenes en el navegador (todo se descarga).
- Antivirus sobre los adjuntos.
- Búsqueda `FULLTEXT`.
- El rediseño visual: se hace después con el plan de rediseño actualizado.

---

## 11. Prompt para Claude Code (repetir por fase)

```
Lee docs/funcionalidades/PLAN_FUNCIONALIDADES_MAQUETA.md completo.
Ejecuta SOLO la Fase N.
Cumple la sección 1 sin excepciones: no modifiques ni borres tests existentes,
no toques app/security.py, auth, ni los flujos de factura y correo; todo SQL
con parámetros; respeta el alcance por rol.
Lee cada archivo completo antes de editarlo.
No ejecutes migraciones contra la base de datos: solo escribe el archivo .sql.
Al terminar, corre pytest -q y las verificaciones de la sección 9 que apliquen,
y haz el commit indicado en la fase.
Entrega un resumen: archivos tocados, tests agregados, resultado de pytest y lo
que no pudiste verificar contra MariaDB o en el navegador.
Si algo del esquema real no coincide con la sección 8, detente y pregunta.
```
