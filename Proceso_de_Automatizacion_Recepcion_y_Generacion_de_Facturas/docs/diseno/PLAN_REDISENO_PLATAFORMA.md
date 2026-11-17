# Plan de rediseño visual completo v2 — Facturaciones SpA (con logo)

> **Para:** Claude Code, ejecutando fase por fase.
> **Rama de trabajo:** `feat/facturaciones-v2-sec` (sección 1.4). Todo el plan se ejecuta y se compara contra esta rama; `main` no interviene.
> **Versión:** 2. Las cinco funcionalidades de la maqueta ya existen en el backend (totales y actividad reciente, búsqueda por cliente o concepto, adjuntos al crear la solicitud, columnas Concepto/Origen/Responsable, “Perfiles y permisos”). Este plan **solo las viste**; no las vuelve a implementar.
> **Alcance:** solo diseño. Se aplica la maqueta completa, página por página. No cambia lo que hace la plataforma.
> **Referencia visual:** `docs/diseno/referencia/` (maqueta estática de 11 páginas). Solo se mira; no se copia su código.
> **Recursos de marca listos:** `docs/diseno/assets/` (logo, favicon e ilustración ya optimizados).
> **Reemplaza a:** la v1 de este archivo y a `docs/diseno/PLAN_IMPLEMENTACION_DISENO.md`. Si se contradicen, manda este.

---

## 0. Resumen en una línea

Pasar de tema oscuro con barra superior azul a **tema claro salvia/grafito con barra lateral, logo y el diseño completo de la maqueta**, cambiando solo plantillas Jinja (marcado y clases), CSS, imágenes y, como máximo, un JavaScript nuevo de presentación.

---

## 1. Reglas obligatorias

Aplican a **todas** las fases. Si una tarea choca con una regla, gana la regla y la tarea se omite (dejar nota en el resumen de la fase).

### 1.1 Archivos que se pueden modificar o crear

| Ruta (relativa a la carpeta del proyecto, la que contiene `app/`) | Permitido |
|---|---|
| `app/templates/**/*.html` | Marcado, clases, envoltorios, íconos y textos decorativos. Se pueden **usar** variables de contexto que la plantilla ya recibe (sección 2.2) |
| `app/templates/_ui.html` | **Crear**: macros de presentación (sección 4.4) |
| `app/static/css/app.css` | Reescribir |
| `app/static/css/login.css` | Reescribir |
| `app/static/js/ui.js` | **Crear (opcional, Fase 6)**: solo presentación (contador de caracteres). Sección 4.7 |
| `app/static/img/*` | **Crear**: copiar desde `docs/diseno/assets/` |
| `app/static/fonts/inter/*` | **Crear**: solo si la persona dejó los archivos (Fase 0) |

**Cualquier otro archivo queda prohibido**, en particular: `app/**/*.py` (incluidas `app/security.py` y la CSP, `permisos.py`, `services/panel.py`, `auditoria_acciones.py`), `app/static/js/app.js`, `app/static/js/login.js`, `migrations/**`, `test/**`, `config.py`, `seed.py`, `requirements*.txt`, el SQL y `docs/diseno/referencia/**`.

### 1.2 Prohibido en las plantillas

1. Crear, quitar o renombrar rutas, endpoints, formularios, campos o valores enviados.
2. Pedir al backend datos que hoy no entrega (nuevas consultas, nuevas variables de contexto, nuevos parámetros GET). Si un elemento de la maqueta los necesita, **no se aplica** (tabla 2.3).
3. Copiar JavaScript de la maqueta (`js/solicitudes.js`, `js/nueva-solicitud.js`, `js/usuarios.js` o scripts en línea). Sus filtros, validaciones y datos son simulados.
4. Escribir `style="..."`, `onclick=`, `onsubmit=` o `<script>` en línea. **`test/test_seguridad.py::test_plantillas_sin_javascript_ni_estilos_en_linea` lo verifica.**
5. Cargar Lucide (`unpkg.com`) o Google Fonts. La CSP solo permite `'self'` y `https://cdn.jsdelivr.net`, e imágenes `'self' data:`.
6. Mostrar datos de ejemplo de la maqueta (nombres, montos, “Datos de demostración”, “SOL-001”, avisos de demo).
7. Copiar `docs/diseno/referencia/css/styles.css`. Tiene 11.138 líneas, 419 colores y 234 `!important`. Se usa solo como referencia visual.
8. Quitar o debilitar controles de seguridad ya presentes en el marcado: `csrf_token`, `token_envio`, `version`, `enctype`, `accept`, `maxlength`, `data-confirmar`, `data-bloquear-envio`, `novalidate`, `autocomplete`, y los `|e`/autoescape de Jinja. Nunca usar `|safe`.

### 1.3 Se preserva exactamente

- **Atributos funcionales:** `name`, `id`, `for`, `action`, `method`, `enctype`, `value`, `required`, `maxlength`, `minlength`, `pattern`, `inputmode`, `accept`, `multiple`, `autocomplete`, `novalidate` y campos ocultos. Se pueden **agregar** `id` nuevos; no se puede quitar ni renombrar ninguno.
- **Lógica Jinja:** cada `{% if %}`, `{% for %}`, `{% set %}`, macro, `url_for(...)`, condición por rol (`current_user.role_name`) y `migas`. Incluye las ramas `adjuntos is none` / lista / vacío del detalle y las distintas tablas de actividad de Administrador y Emisor.
- **Filtros GET del listado:** `q`, `cliente_id`, `rut`, `desde`, `hasta`, `monto`, `estado_id`, `emisor_id` (solo Administrador), con los mismos `name` y `value`.
- **Hooks de JavaScript existentes:**
  - `static/js/app.js`: `data-confirmar`, `data-bloquear-envio`, `button[type='submit']`.
  - `static/js/login.js`: `.needs-validation`, `#password`, `#togglePassword`, `#passwordIcon` y las clases `bi-eye` / `bi-eye-slash`.
- **Cadenas que verifica `test/test_navegacion.py`:**
  - `aria-label="Ruta de navegación"`
  - `<a href="{{ ns.volver }}" class="btn btn-outline-secondary btn-sm">` (botón **Volver** de las migas): mismas clases, **mismo orden** y nada entre `href` y `class`.
  - Texto `Cerrar sesión`.
  - En `_proceso.html`: `aria-current="step">{{ paso }}` sin espacio ni salto de línea entre `>` y el texto (también `Rechazada`).
  - `href` del menú: `/dashboard`, `/solicitudes/`, `/solicitudes/nueva`, `/admin/correos`, `/clientes/`, `/admin/usuarios`, `/admin/auditoria`, con las mismas condiciones de rol. El Emisor no ve `/admin/usuarios` ni `/clientes/`; la pestaña **Editar** no aparece si la solicitud no es editable.
  - El panel (`/dashboard`) **no** puede contener la palabra `Volver`.
  - Texto `Solicitud 1234abcd` en el encabezado de `factura.html`.
- **Cadenas que verifican los tests de las funcionalidades ya implementadas** (existen en `feat/facturaciones-v2-sec`):

  | Test | Plantilla | Debe seguir apareciendo (o no) |
  |---|---|---|
  | `test_panel.py` | `dashboard.html` | Administrador: `Usuarios activos`, `Clientes activos`, `Eventos registrados`, `Actividad reciente`, la etiqueta de acción (p. ej. `Factura aprobada`), `href="/solicitudes/<public_id>"` y `href="/solicitudes/?estado_id=<id>"` (los enlaces de las tarjetas por estado se generan igual que hoy) |
  | `test_panel.py` | `dashboard.html` y `base.html` | Emisor: `Resumen`, `Actividad reciente` y el nombre de la solicitud; **no** pueden aparecer `Usuarios`, `Clientes activos` ni `href="/admin/auditoria"` en ninguna parte de la página (shell incluido) |
  | `test_panel.py` | `dashboard.html` | Lector con `resumen` en `None`: aparece `Panel principal` y **no** `Actividad reciente` |
  | `test_rutas_factura.py` | `dashboard.html` | Administrador sin BD: aparece `Facturas por validar` (el acceso rápido queda **fuera** de la condición de `resumen`) |
  | `test_listado_columnas.py` | `solicitudes/listado.html` | Exactamente `<th scope="col">Concepto</th>`, `<th scope="col">Origen</th>` y `<th scope="col">Responsable</th>` (solo Administrador). **No agregar clases ni atributos a esos `<th>`**: el estilo de cabecera va por CSS (`.table thead th`). Valores escapados (`&lt;b&gt;x&lt;/b&gt;`) |
  | `test_busqueda_solicitudes.py` | `solicitudes/listado.html` | Texto `Siguiente` en la paginación |
  | `test_adjuntos.py` | `solicitudes/nueva.html` | `enctype="multipart/form-data"`, `name="adjuntos"`, `accept=".pdf,.png,.jpg,.jpeg"` y los mensajes `Solo se permiten adjuntos PDF, PNG o JPG.` / `vuelva a seleccionarlos` |
  | `test_adjuntos.py` | `solicitudes/detalle.html` | `Documentos adjuntos`, `href="/solicitudes/<public_id>/adjuntos/<id>"`, nombre escapado, tamaño (`2 KB`), `Sin documentos adjuntos.`, `No se pudieron cargar los documentos adjuntos.` y `Receptor histórico` |
  | `test_permisos.py` | `admin/usuarios.html` | `Perfiles y permisos`, descripción del perfil escapada, el texto de cada capacidad, `aria-label="Permitido"` y `No permitido` |
  | `test_rutas_factura.py` | `solicitudes/factura.html` | `Factura correcta: generar archivo SII` (Administrador), `Historial de versiones`, `Generar factura y enviar a revisión`, `Versión 2`, `Corregido`, alertas; el Emisor no ve `generar archivo SII` |
  | `test_rutas_factura.py` | `admin/correos.html` | Motivos de observación, `Reprocesar` y autoescape (sin `<script>` crudo) |

  Regla práctica: **los textos visibles existentes no se reescriben**; se pueden envolver, mover dentro de la misma condición o cambiar de clase.
- **Bootstrap 5.3.3 y Bootstrap Icons 1.11.3** desde jsDelivr con sus `integrity` actuales.
- **Tests:** correr todo `test/` (21 archivos en la rama) y no modificar ninguno. Si uno falla, se revierte el marcado.

### 1.4 Forma de trabajo

- **Rama:** se trabaja directamente sobre `feat/facturaciones-v2-sec`, que ya contiene las funcionalidades, sus tests, la maqueta (`docs/diseno/referencia/`) y los recursos de marca (`docs/diseno/assets/`). No se crea otra rama ni se cambia a `main`, `dev` o `QA`.
- **Punto de partida:** en la Fase 0 se crea la etiqueta local `rediseno-base` sobre el commit inicial. Todas las comparaciones de la sección 6 usan `rediseno-base`, y deshacer el rediseño completo es `git reset --hard rediseno-base` (solo si la persona lo pide).
- **Estructura del repositorio:** la raíz de Git es `Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/` y el proyecto está en la subcarpeta del mismo nombre. **Todos los comandos se ejecutan desde la subcarpeta** (la que contiene `app/`, `test/` y `docs/`), y los `git diff` usan `--relative`.
- **No hacer `git push`, `rebase`, `merge` ni `stash`** salvo que la persona lo pida. El árbol de trabajo debe estar limpio antes de empezar.
- **Leer completa cada plantilla antes de editarla** (el marcado de las cinco plantillas ampliadas es distinto del original).
- Una fase = un commit, con `pytest -q` en verde antes de cada commit.
- Si un test falla: **revertir el marcado, no el test**.
- Al final de cada fase, resumen breve: archivos tocados, resultado de `pytest` y qué **no** se pudo verificar (render real en navegador, móvil).

---

## 2. Diagnóstico

### 2.1 Diferencias visuales

| Aspecto | Actual | Objetivo (maqueta) |
|---|---|---|
| Tema | Oscuro: `data-bs-theme="dark"`, fondo `#171812`, barra `#192f58` | Claro: fondo `#F5F6F3`, tarjetas blancas, salvia/grafito |
| Layout | `navbar` superior colapsable | Barra lateral de 250 px con logo y grupos “Menú principal” / “Administración”; topbar con avatar de iniciales. En móvil, *offcanvas* de Bootstrap |
| Marca | Logo falso de 4 cuadrados (`.brand-mark`) y texto | Logo real y favicon |
| Panel | Tarjetas de acceso y tabla de actividad sin jerarquía | Banda de bienvenida, “Resumen general”, “Accesos rápidos” y “Actividad reciente” |
| Listado | Filtros sueltos y estado siempre gris | Chips de estado, tarjeta de filtros, tabla con cabecera en mayúsculas y etiquetas de estado por color |
| Detalle | Tarjetas apiladas | Banner de estado con borde de acento, rejillas etiqueta/valor, adjuntos y XML como filas con ícono |
| Nueva solicitud | Formulario plano | Secciones numeradas, ayudas de campo, contador de caracteres, lista de adjuntos |
| Usuarios | Dos columnas planas | Tarjetas de totales, formulario, tabla con avatares y “Perfiles y permisos” como tarjetas + matriz |
| Tipografía | Arial | Inter alojada en el servidor, con respaldo `system-ui` |
| Íconos | Bootstrap Icons | Bootstrap Icons (la maqueta usa Lucide y no pasa la CSP) |

**Por qué el logo obliga a cambiar el tema:** su texto es verde casi negro (`#0B2E11`). Sobre el fondo oscuro el contraste es 1,2:1 y sobre la barra azul 1,1:1; sobre blanco, 14,9:1. **El logo solo va sobre fondos claros.**

**Estrategia técnica:** el 90 % de la interfaz usa clases de Bootstrap. Se re-tematiza con variables `--bs-*` y se agregan unas pocas clases propias en español (`.metrica`, `.chip-estado`, `.banner-estado`…) para lo que Bootstrap no resuelve. No se importa el CSS de la maqueta.

### 2.2 Datos que ya entrega el backend (no se tocan, solo se usan)

Nombres confirmados en `feat/facturaciones-v2-sec`. Aun así, leer la plantilla antes de usarlos; si alguno no está, el elemento no se aplica.

| Pantalla | Variables disponibles hoy |
|---|---|
| `dashboard.html` | `resumen` (`estados` con `id`/`nombre`/`total`, `solicitudes_total`; Administrador además `correos_por_revisar`, `usuarios.activos/total`, `clientes.activos/total`, `eventos_total`, `actividad` con `creado_en`, `etiqueta`, `usuario_nombre`, `public_id`; Emisor: `actividad` con `public_id`, `nombre`, `actualizado_en`, `estado_nombre`). Puede ser `None` si la BD falla: se conserva esa rama |
| `solicitudes/listado.html` | Solicitudes con RUT, cliente, concepto, monto, fecha, origen, responsable (Administrador) y estado; `estados`, `clientes`, filtros activos y paginación. El parámetro de página es **`pagina`** (`routes.py`, 20 por página); las URL Anterior/Siguiente ya llegan calculadas |
| `solicitudes/nueva.html` | `clientes` (`id`, `rut`, `razon_social`), `values`, `errores`, `token_envio`. El campo concepto es `id="concepto"` con `maxlength="500"`; la ayuda de adjuntos dice “Opcional. PDF, PNG o JPG; hasta 3 archivos de 5 MB.” |
| `solicitudes/detalle.html` | Solicitud, `adjuntos` (`none` / lista / vacío), XML, envíos de correo, estados para gestión |
| `admin/usuarios.html` | `usuarios` (cada uno con `activo`), `perfiles` (con `usuarios_activos`) y la matriz de capacidades ya renderizada en la plantilla |
| `clientes/listado.html` | `clientes` con `rut`, `razon_social`, `email_contacto` y estado |

### 2.3 Qué de la maqueta se aplica y qué no

| Elemento de la maqueta | ¿Se aplica? | Motivo |
|---|---|---|
| Barra lateral, topbar, avatar con iniciales, logo | Sí | Solo marcado y CSS |
| Banda de bienvenida del panel | Sí | Usa `current_user.nombre` |
| “Resumen general” (6 tarjetas) | Sí | Usa `resumen.*` existente. Las tarjetas del Administrador y del Emisor son las que hoy existen; no se inventan otras |
| “Accesos rápidos” | Sí | Mismos enlaces y condiciones de rol de hoy |
| “Actividad reciente” | Sí | Usa `resumen.actividad`; sin IP ni detalle completo |
| Chips de estado en el listado | **Sí, sin conteos** | Son enlaces a `estado_id` con `estados` ya entregado. El conteo por estado no llega al listado |
| Buscador por cliente o concepto | Sí | Es el campo `q` existente (formulario GET, no filtro en JS) |
| Columnas Concepto, Origen, Responsable | Sí | Ya vienen en la consulta |
| Botón “Limpiar filtros” | Sí | Enlace a `url_for('solicitudes.listado')` |
| Secciones numeradas en “Nueva solicitud” | Sí | Solo agrupar campos contiguos; sin mover campos entre formularios |
| Contador de caracteres del concepto | Sí (opcional) | JS nuevo mínimo (4.7); `maxlength="500"` sigue siendo la validación real |
| Ficha de solo lectura del cliente al elegirlo | **No** | El contexto solo trae RUT y razón social dentro del `<option>`; mostrar más exige datos nuevos |
| Adjuntos al crear | Sí (visual) | Mismo `input name="adjuntos"` múltiple, `accept` y límites; se muestran las restricciones como texto de ayuda |
| Arrastrar y soltar archivos, vista previa | **No** | Exige JS y lógica propios |
| Tarjetas de totales en “Usuarios” | Sí, con datos de contexto | Total `usuarios\|length`, activos `usuarios\|selectattr('activo')\|list\|length`, inactivos por diferencia |
| Buscador y filtro de usuarios en vivo | **No** | Filtro en JS sobre datos parciales; no existe en el backend |
| “Perfiles y permisos” (tarjetas y matriz) | Sí | Ya existe; solo se rediseña |
| Autocompletado del RUT / cliente | **No** | Sin endpoint |
| “Recordarme”, “¿Olvidaste tu contraseña?” | **No** | Sin backend |
| Pestañas del detalle como en la maqueta | Parcial | Se conservan las pestañas reales (`_proceso.html`: Solicitud / Factura / Editar). No se crean pestañas JS |
| Historial de versiones en el detalle | Solo si ya existe en `factura.html` | Se reestiliza; no se agrega |
| Datos y avisos de demostración | **No** | Regla 1.2.6 |

---

## 3. Recursos de marca (ya preparados)

Están en `docs/diseno/assets/`. **No hay que regenerarlos**: solo copiarlos a `app/static/img/` en la Fase 0.

| Archivo | Tamaño | Uso |
|---|---|---|
| `logo-facturaciones.png` | 360×105 px, 24 KB | Barra lateral (se muestra a 180×53), login en móvil, página de error |
| `logo-facturaciones@2x.png` | 720×209 px, 62 KB | `srcset` 2x y logo grande del login (se muestra a 280 px de ancho) |
| `favicon-32.png` | 32×32 px | Ícono de la pestaña del navegador |
| `apple-touch-icon.png` | 180×180 px | Ícono al guardar en la pantalla de inicio (iOS/Android) |
| `login-ilustracion.png` | 720×381 px, 244 KB | Panel izquierdo del login. **Sin el logo incrustado** y con el borde suavizado |

Diferencias con los originales de la maqueta: se recortó el margen transparente del logo, que pesaba 260 KB. A la ilustración (1 MB) se le quitó el logo incrustado, que habría duplicado la marca en el login, y se le suavizó el borde irregular. El favicon es el ícono del documento del logo sobre un cuadrado salvia claro.

Uso de los recursos:
- Logo: `alt="Facturaciones SpA"`, con `width` y `height` como atributos HTML (no `style`).
- Ilustración: `alt=""` porque es decorativa.
- **Nunca** colocar el logo sobre fondos oscuros o salvia medio (`#748273`).

---

## 4. Decisiones de diseño

### 4.1 Tokens (`app.css`, primer bloque)

Valores tomados de la maqueta. Se oscurecieron **tres** colores para cumplir el contraste mínimo de WCAG AA (4,5:1 en texto normal); el valor original y el medido se anotan en el comentario de cada uno.

```css
:root {
    /* Superficies */
    --color-fondo: #F5F6F3;
    --color-superficie: #FFFFFF;
    --color-superficie-suave: #F8F9F7;   /* cabeceras de tabla, hover de filas */
    --color-borde: #E2E5E0;
    --color-borde-fuerte: #C9D1C6;

    /* Marca */
    --color-salvia: #748273;             /* SOLO decorativo: bordes de foco, íconos grandes. No usar con texto */
    --color-salvia-oscuro: #626F61;      /* botón primario. Blanco sobre él: 5,3:1 (el #748273 original da 4,05) */
    --color-salvia-hover: #4E5A4D;       /* hover/activo del primario: 7,3:1 */
    --color-salvia-claro: #D9E1D5;       /* ítem activo del menú, recuadro de íconos */
    --color-salvia-tenue: #EDF0EB;       /* hover de menú y botones secundarios */
    --color-verde-enlace: #287B5C;       /* enlaces: 5,15:1 sobre blanco */
    --color-verde-enlace-hover: #1F5F47;
    --color-grafito: #303633;            /* texto principal: 12,3:1 */

    /* Texto */
    --color-texto: #303633;
    --color-texto-secundario: #687068;   /* 5,1:1 sobre blanco (el #858D83 original da 3,4) */

    /* Estados: fondo / texto (todos ≥ 4,9:1) */
    --estado-neutro-bg: #ECEEF0;  --estado-neutro-tx: #3E4650;
    --estado-info-bg:   #E3ECFB;  --estado-info-tx:   #1E4FA8;
    --estado-aviso-bg:  #FCEFD6;  --estado-aviso-tx:  #8A5300;
    --estado-ok-bg:     #DDF3E5;  --estado-ok-tx:     #15633E;
    --estado-error-bg:  #FCE8E6;  --estado-error-tx:  #A94442;

    /* Forma */
    --radio-sm: 8px;
    --radio-md: 12px;
    --radio-lg: 14px;
    --sombra-tarjeta: 0 2px 8px rgba(48, 54, 51, 0.04);
    --sombra-hover: 0 6px 16px rgba(48, 54, 51, 0.08);
    --anillo-foco: 0 0 0 3px rgba(98, 111, 97, 0.25);

    /* Layout y tipografía */
    --ancho-sidebar: 250px;
    --fuente: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
}
```

El texto tenue de la maqueta (`#92998F`, 2,9:1) **no se usa** para texto; donde aparezca, se reemplaza por `--color-texto-secundario`.

### 4.2 Re-tema de Bootstrap (`app.css`, segundo bloque)

Bootstrap declara sus variables en `:root, [data-bs-theme=light]`. `app.css` se carga después, así que el mismo selector las sobrescribe:

```css
:root,
[data-bs-theme="light"] {
    --bs-body-font-family: var(--fuente);
    --bs-body-bg: var(--color-fondo);
    --bs-body-color: var(--color-texto);
    --bs-emphasis-color: var(--color-grafito);
    --bs-secondary-color: var(--color-texto-secundario);   /* alimenta .text-body-secondary (32 usos) */
    --bs-tertiary-bg: var(--color-superficie-suave);
    --bs-border-color: var(--color-borde);
    --bs-border-radius: var(--radio-sm);
    --bs-border-radius-lg: var(--radio-md);
    --bs-border-radius-xl: var(--radio-lg);

    --bs-link-color: var(--color-verde-enlace);
    --bs-link-color-rgb: 40, 123, 92;
    --bs-link-hover-color: var(--color-verde-enlace-hover);
    --bs-link-hover-color-rgb: 31, 95, 71;

    --bs-primary: #626F61;
    --bs-primary-rgb: 98, 111, 97;
    --bs-primary-text-emphasis: #3F4A3E;
    --bs-primary-bg-subtle: #EDF0EB;
    --bs-primary-border-subtle: #D9E1D5;

    --bs-focus-ring-color: rgba(98, 111, 97, 0.25);
}
```

Componentes que se re-tematizan **sin tocar el HTML**. Usar las variables por componente de Bootstrap (`--bs-btn-*`, `--bs-card-*`, `--bs-table-*`, `--bs-nav-*`, `--bs-badge-*`, `--bs-alert-*`) antes que reglas sueltas:

| Componente | Resultado esperado |
|---|---|
| `.btn-primary` | Fondo `--color-salvia-oscuro`, texto blanco, hover/activo `--color-salvia-hover`, radio 8 px, peso 600 |
| `.btn-outline-primary` | Borde y texto `--color-salvia-oscuro`; hover con fondo `--color-salvia-tenue` |
| `.btn-outline-secondary` | Texto grafito, borde `--color-borde-fuerte`, hover `--color-salvia-tenue`. Lo usan el botón **Volver** y “Cerrar sesión” |
| `.btn-success`, `.btn-warning` | Mantener la semántica de Bootstrap y solo ajustar el radio. Son botones de aprobar y devolver |
| `.card` | Fondo blanco, borde `--color-borde`, radio 12 px, `--sombra-tarjeta`. `.card.border-primary` / `.border-success` con borde izquierdo de 4 px del color correspondiente |
| `.form-control`, `.form-select` | Fondo blanco, borde `--color-borde`, radio 8 px; en `:focus`, borde `--color-salvia` y `box-shadow: var(--anillo-foco)` (Bootstrap fija el foco azul sin variable, así que se necesita regla propia) |
| `.form-check-input:checked` | Fondo y borde `--color-salvia-oscuro` |
| `.table` | Fondo transparente, borde `--color-borde`; `thead th` con fondo `--color-superficie-suave`, texto secundario, 0,75 rem, mayúsculas, `letter-spacing: .04em`, peso 600; hover de fila `--color-superficie-suave` |
| `.nav-tabs` (`_proceso.html`) | Pestañas subrayadas: sin cajas, línea inferior `--color-borde`; la activa con texto grafito, peso 600 y borde inferior de 2 px `--color-salvia-oscuro` |
| `.alert` | Radio 12 px y borde de 1 px. Los colores *subtle* de Bootstrap 5.3 ya son claros y se mantienen |
| `.breadcrumb` | Texto secundario; separador `›` |
| `.pagination` (si existe) | Enlaces grafito; el activo con fondo `--color-salvia-oscuro` |

### 4.3 Etiquetas de estado (`.badge`)

Las plantillas ya usan `badge text-bg-{primary|secondary|success|warning|danger|info|dark}`, a veces calculado con diccionarios `colores` en `admin/correos.html` y `solicitudes/factura.html`. **No se cambian esas clases ni esos diccionarios.** Se reestiliza en CSS:

```css
.badge {
    --bs-badge-padding-x: 0.7em;
    --bs-badge-padding-y: 0.45em;
    --bs-badge-font-weight: 600;
    --bs-badge-border-radius: 999px;
}

/* Bootstrap declara .text-bg-* con !important; solo aquí se permite !important para ganarle. */
.badge.text-bg-primary,
.badge.text-bg-info      { background-color: var(--estado-info-bg) !important;   color: var(--estado-info-tx) !important; }
.badge.text-bg-secondary,
.badge.text-bg-dark      { background-color: var(--estado-neutro-bg) !important; color: var(--estado-neutro-tx) !important; }
.badge.text-bg-success   { background-color: var(--estado-ok-bg) !important;     color: var(--estado-ok-tx) !important; }
.badge.text-bg-warning   { background-color: var(--estado-aviso-bg) !important;  color: var(--estado-aviso-tx) !important; }
.badge.text-bg-danger    { background-color: var(--estado-error-bg) !important;  color: var(--estado-error-tx) !important; }
```

**Este es el único lugar del CSS con `!important`.**

### 4.4 Macros de presentación (`app/templates/_ui.html`, nuevo)

```jinja
{# Solo presentación: no contiene lógica de negocio ni consulta datos. #}

{% macro estado_solicitud(nombre) -%}
{%- set clases = {
    'Pendiente': 'secondary',
    'En revisión': 'primary',
    'En corrección': 'warning',
    'Aprobada': 'success',
    'Rechazada': 'danger',
} -%}
<span class="badge text-bg-{{ clases.get(nombre, 'secondary') }}">{{ nombre }}</span>
{%- endmacro %}

{% macro iniciales(nombre) -%}
{{ (nombre or '?').split()[:2] | map('first') | join('') | upper }}
{%- endmacro %}

{# Tarjeta de resumen: icono, valor, etiqueta y, si se da, un enlace existente. #}
{% macro metrica(valor, etiqueta, icono, url=None) -%}
<div class="metrica">
    <span class="metrica-icono" aria-hidden="true"><i class="bi {{ icono }}"></i></span>
    <div class="metrica-texto">
        <span class="metrica-valor">{{ valor }}</span>
        {% if url %}<a class="metrica-etiqueta stretched-link" href="{{ url }}">{{ etiqueta }}</a>
        {% else %}<span class="metrica-etiqueta">{{ etiqueta }}</span>{% endif %}
    </div>
</div>
{%- endmacro %}
```

Uso:
- `estado_solicitud`: columna Estado de `solicitudes/listado.html` y bloque “Gestión del estado” / banner de `solicitudes/detalle.html`. **No usarlo en `_proceso.html`** (ahí se conserva el marcado y solo cambia el CSS).
- `iniciales`: topbar, tabla de usuarios y de clientes.
- `metrica`: “Resumen general” del panel y tarjetas de totales de Usuarios.
- Se importan con `{% from "_ui.html" import … %}`. Jinja escapa los valores por defecto; no usar `|safe`.

### 4.5 Tipografía

Inter 400/500/600/700, alojada en el servidor.
- Si la persona dejó `app/static/fonts/inter/Inter-{400,500,600,700}.woff2` en la Fase 0: declarar `@font-face` con `font-display: swap` y agregar la licencia `OFL.txt` en la misma carpeta.
- Si **no** están: **no** declarar `@font-face` (evita errores 404) y dejar que `--fuente` use `system-ui`. Avisarlo en el resumen.
- Jerarquía: `h1`/`.h2` de página en 1,6 rem, peso 600, `letter-spacing: -0.02em`; `.h5` de tarjeta en 1,05 rem, peso 600; texto base en 0,9375 rem.

### 4.6 Íconos

Se mantienen Bootstrap Icons. Cambios opcionales en el menú para acercarse a la maqueta: Panel `bi-grid-1x2`, Solicitudes `bi-file-earmark-text`, Nueva solicitud `bi-file-earmark-plus`, Bandeja `bi-inbox`, Clientes `bi-building`, Usuarios `bi-people`, Auditoría `bi-clock-history`. Todos los íconos decorativos con `aria-hidden="true"`.

### 4.7 JavaScript nuevo permitido (opcional)

Un único archivo, `app/static/js/ui.js`, cargado con `<script src="{{ url_for('static', filename='js/ui.js') }}"></script>` desde el `{% block scripts %}` de `nueva.html` (nunca en línea; la CSP ya permite `'self'`). Solo presentación:

```js
(() => {
    "use strict";
    const campo = document.querySelector("#concepto");
    const contador = document.querySelector("#contador-concepto");
    if (!campo || !contador) return;
    const max = campo.maxLength;
    const actualizar = () => { contador.textContent = `${campo.value.length} / ${max}`; };
    campo.addEventListener("input", actualizar);
    actualizar();
})();
```

Reglas: no hace `fetch`, no valida, no deshabilita nada y la página funciona igual sin él. Verificar que el `id` del campo concepto sea `concepto` (si no, usar el real). **No modificar `app.js` ni `login.js`.**

### 4.8 Clases de componentes de la maqueta (`app.css`, bloque “Componentes”)

Nombres propios, sin copiar `styles.css`. Cada clase usa solo tokens.

| Clase | Aspecto |
|---|---|
| `.bienvenida` | Banda del panel: fondo `--color-salvia-claro`→`--color-salvia-tenue`, radio 14 px, padding 1,5 rem; título 1,6 rem y texto secundario |
| `.metrica` | Tarjeta blanca (radio 12 px, borde, sombra) en rejilla `repeat(auto-fill, minmax(220px, 1fr))`; recuadro de ícono 40×40 en `--color-salvia-claro`; valor 1,6 rem peso 700; etiqueta secundaria. Hover: `--sombra-hover` y `translateY(-2px)` salvo `prefers-reduced-motion` |
| `.acceso-rapido` | Tarjeta enlace con ícono, título, descripción y flecha `bi-arrow-right`; la de “Facturas por validar” con borde izquierdo de 4 px `--color-salvia-oscuro` |
| `.seccion-titulo` | Encabezado de sección: 0,75 rem, mayúsculas, `letter-spacing: .08em`, peso 700, color secundario |
| `.chip-estado` | Enlace redondeado (999 px), borde `--color-borde`, fondo blanco; activo con fondo `--color-salvia-claro` y peso 600 |
| `.panel-filtros` | Tarjeta de filtros con rejilla `row g-3`; etiquetas de 0,8125 rem peso 600 |
| `.banner-estado` | Tarjeta del detalle con borde izquierdo de 4 px según estado (neutro, info, aviso, ok, error) y etiqueta de estado a la derecha |
| `.detalle-rejilla` | `dl` en 2–3 columnas: `dt` 0,8125 rem secundario, `dd` grafito peso 500 |
| `.fila-archivo` | Fila con recuadro de ícono (`bi-file-earmark-pdf`, `bi-file-earmark-image` o `bi-file-earmark-code`), nombre, tamaño y acción existente |
| `.seccion-formulario` | Bloque numerado (círculo 28 px con el número en `--color-salvia-claro`) con título y línea separadora |
| `.ayuda-campo` | Texto de ayuda de 0,8125 rem en color secundario bajo el campo; con `.contador` alineado a la derecha |
| `.avatar` | Círculo de 40 px (32 px en tablas), fondo `--color-salvia-claro`, iniciales grafito peso 600 |
| `.tarjeta-perfil` | Tarjeta de “Perfiles y permisos” con recuadro de ícono, nombre del perfil, descripción y cantidad de activos |
| `.matriz-permisos` | Tabla capacidades × perfiles. Se conserva el marcado actual de cada celda (`<i class="bi bi-check-lg" … aria-label="Permitido">` y `<span class="visually-hidden">No permitido</span>`); solo cambia el CSS: check en `--estado-ok-tx`, celda vacía con `—` decorativo vía CSS (`::before`) |

---

## 5. Fases

Las fases 0–3 construyen la base (recursos, CSS, shell, login). Las fases 4–10 aplican la maqueta página por página.

### Fase 0 — Preparación

1. Desde la subcarpeta del proyecto:
   ```bash
   git switch feat/facturaciones-v2-sec
   git status --short          # debe salir vacío; si no, detenerse e informar
   ```
2. Si `docs/diseno/PLAN_REDISENO_PLATAFORMA.md` aparece modificado (es esta v2), hacer primero `git add docs/diseno/PLAN_REDISENO_PLATAFORMA.md && git commit -m "docs(ui): plan de rediseño v2 sobre feat/facturaciones-v2-sec"`.
3. Crear la etiqueta de partida: `git tag rediseno-base` (local; no se sube).
4. Ejecutar `pytest -q` y anotar el resultado base. Si algo falla **antes** de tocar nada, detenerse e informar.
5. Confirmar que las funcionalidades existen leyendo (sin editar) `app/__init__.py::resumen_panel`, `app/services/panel.py`, `app/permisos.py` y las plantillas ampliadas (`dashboard`, `solicitudes/listado`, `nueva`, `detalle`, `admin/usuarios`). Anotar los nombres reales de variables que se usarán (sección 2.2). Lo que no exista se marca “no aplicado”.
6. Crear `app/static/img/` y copiar los 5 archivos de `docs/diseno/assets/` con los mismos nombres.
7. Comprobar si existen `app/static/fonts/inter/*.woff2`. **Claude Code no descarga fuentes**: si faltan, usar el respaldo (4.5) y avisarlo.
8. Commit: `chore(ui): agrega logo, favicon e ilustración optimizados`.

> **Paso para la persona (opcional, antes de la Fase 1):** descargar Inter desde https://rsms.me/inter/ y dejar `Inter-400.woff2`, `Inter-500.woff2`, `Inter-600.woff2`, `Inter-700.woff2` y `OFL.txt` en `app/static/fonts/inter/`.

### Fase 1 — Fundamentos (CSS global)

Reescribir `app/static/css/app.css` en este orden:

```
1. @font-face (solo si existen los archivos)
2. Tokens (:root) ........................... 4.1
3. Re-tema de Bootstrap ..................... 4.2
4. Base: body, títulos, enlaces, :focus-visible con var(--anillo-foco)
5. Shell: .app-shell, .sidebar, .topbar, .app-main, .flash-container, migas
6. Componentes de Bootstrap: botones, tarjetas, formularios, tablas, badges (4.3), alertas, pestañas, .pasos-proceso
7. Componentes de la maqueta ................. 4.8
8. Utilidades que se conservan: .texto-preformateado, .ancho-limitado
9. Responsive: solo dos cortes, 991.98px y 575.98px
10. @media print
```

- Conservar las clases que hoy usan las plantillas: `.flash-container`, `.texto-preformateado`, `.ancho-limitado`, `.pasos-proceso` (y su flecha `→` en color secundario).
- Eliminar variables del tema oscuro (`--navy`, `--dark`, `--input`, `--mint`) y `.barra-principal`.
- En `base.html`, cambiar solo `data-bs-theme="dark"` → `"light"` en esta fase.
- Objetivo: menos de 1.100 líneas, sin colores fuera de los tokens y sin `!important` fuera de 4.3.
- Commit: `style(ui): tema claro salvia, re-tema de Bootstrap y componentes`.

### Fase 2 — Shell de la aplicación (`base.html`) con logo

Estructura objetivo. Los `{% block %}` no pueden repetirse, por eso la envoltura se abre y se cierra con el mismo `if`:

```jinja
<!doctype html>
<html lang="es" data-bs-theme="light">
<head>
    {# … meta, title, Bootstrap e íconos SIN cambios … #}
    <link rel="icon" type="image/png" sizes="32x32"
          href="{{ url_for('static', filename='img/favicon-32.png') }}">
    <link rel="apple-touch-icon"
          href="{{ url_for('static', filename='img/apple-touch-icon.png') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
    {% block styles %}{% endblock %}
</head>
<body>
    {% from "_ui.html" import iniciales %}
    {% macro enlace_menu(endpoint, texto, icono, activo) %} … igual que hoy … {% endmacro %}

    {% if current_user.is_authenticated %}
    {% set endpoint = request.endpoint or '' %}
    <div class="app-shell">
        <aside class="sidebar offcanvas-lg offcanvas-start" tabindex="-1"
               id="menu-principal" aria-label="Menú principal">
            <div class="sidebar-logo">
                <a href="{{ url_for('dashboard') }}">
                    <img src="{{ url_for('static', filename='img/logo-facturaciones.png') }}"
                         srcset="{{ url_for('static', filename='img/logo-facturaciones.png') }} 1x,
                                 {{ url_for('static', filename='img/logo-facturaciones@2x.png') }} 2x"
                         width="180" height="53" alt="Facturaciones SpA">
                </a>
                <button type="button" class="btn-close d-lg-none"
                        data-bs-dismiss="offcanvas" data-bs-target="#menu-principal"
                        aria-label="Cerrar menú"></button>
            </div>

            <nav class="sidebar-nav">
                <p class="seccion-titulo">Menú principal</p>
                <ul class="nav flex-column">
                    {# Panel, Solicitudes, Nueva solicitud: mismas llamadas y condiciones que hoy #}
                </ul>

                {% if current_user.role_name == 'Administrador' %}
                <p class="seccion-titulo">Administración</p>
                <ul class="nav flex-column">
                    {# Bandeja, Clientes, Usuarios, Auditoría: mismas llamadas y condiciones #}
                </ul>
                {% endif %}
            </nav>
        </aside>

        <div class="app-main">
            <header class="topbar">
                <button type="button" class="btn btn-outline-secondary btn-sm d-lg-none"
                        data-bs-toggle="offcanvas" data-bs-target="#menu-principal"
                        aria-controls="menu-principal" aria-label="Mostrar menú">
                    <i class="bi bi-list" aria-hidden="true"></i>
                </button>

                <div class="topbar-usuario ms-auto">
                    <span class="avatar" aria-hidden="true">{{ iniciales(current_user.nombre) }}</span>
                    <div class="topbar-usuario-texto">
                        <strong>{{ current_user.nombre }}</strong>
                        <span>{{ current_user.role_name }}</span>
                    </div>
                    <form method="POST" action="{{ url_for('auth.logout') }}">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <button type="submit" class="btn btn-outline-secondary btn-sm">
                            <i class="bi bi-box-arrow-right" aria-hidden="true"></i>
                            Cerrar sesión
                        </button>
                    </form>
                </div>
            </header>
    {% endif %}

            {# flash y migas: mismos bloques que hoy; no tocar el <a … class="btn btn-outline-secondary btn-sm"> #}

            {% block content %}{% endblock %}

    {% if current_user.is_authenticated %}
        </div>
    </div>
    {% endif %}

    {# scripts: iguales que hoy #}
</body>
</html>
```

Detalles:
- **Menú:** los 7 enlaces, sus `endpoint`, condiciones de rol y cálculo de `activo` quedan **idénticos**; solo se reparten en dos grupos. El Emisor no ve “Administración”. El ítem “Nueva solicitud” sigue marcándose solo en `solicitudes.nueva`.
- **Estilo del menú** (`.sidebar .nav-link`, para no afectar `.nav-tabs`): enlace de texto `#687168`, 0,875 rem, padding 0,7 rem, radio 8 px; hover `--color-salvia-tenue`; activo `--color-salvia-claro`, grafito, peso 600 e ícono `--color-salvia-oscuro`.
- **Barra lateral:** fondo blanco, borde derecho `--color-borde`, ancho `--ancho-sidebar`. En ≥ 992 px, `position: sticky; top: 0; height: 100vh; overflow-y: auto`. En < 992 px es *offcanvas* de Bootstrap, sin JS propio.
- **`.app-shell`:** `display: flex`; **`.app-main`:** `flex: 1; min-width: 0`, padding 2–2,5 rem (1 rem en móvil).
- **Topbar:** borde inferior `--color-borde`. En < 576 px se oculta `.topbar-usuario-texto`.
- **Contenido:** las páginas conservan su `container`; dentro de `.app-main` queda con `max-width: 1200px` y `margin-inline: 0`.
- **Flash:** posición fija arriba a la derecha, radio 12 px y `--sombra-hover`.
- **Eliminar** `navbar`, `navbar-dark`, `text-white`, `btn-outline-light` y `.barra-principal`.
- **La palabra “Volver” no puede aparecer en el shell.**
- Commit: `feat(ui): barra lateral con logo, topbar y favicon`.

### Fase 3 — Login y página de error

**`auth/login.html` + `login.css`** (sigue extendiendo `base.html`; sin sesión no se dibuja el shell).

- **Panel izquierdo** (`.login-brand-panel`, visible solo en ≥ 992 px): fondo degradado `--color-salvia-claro`→`--color-salvia-tenue`. De arriba abajo: logo `@2x` mostrado a 280 px (`width="280" height="81"`); textos **existentes** “SISTEMA DE GESTIÓN” y “Recepción y Generación de Facturas” (2,4 rem, peso 700); `login-ilustracion.png` (`alt=""`, `width="720" height="381"`, máximo 460 px); pie existente con `bi-shield-check`.
- **Eliminar** `.brand-mark` y `.brand-name`.
- **Panel derecho:** fondo blanco, formulario centrado de máximo 400 px. En < 992 px, logo de 180 px sobre el título (`class="login-logo-movil d-lg-none"`).
- El formulario, sus campos, `invalid-feedback`, el botón de mostrar contraseña y la nota de seguridad **se conservan tal cual**. **No** se agrega “Recordarme” ni “¿Olvidaste tu contraseña?”.
- `.btn-login` con el aspecto de `.btn-primary`, ancho completo, 44 px; `.password-toggle` con borde `--color-borde` e ícono secundario.

**`errores/error.html`:** sin sesión, logo de 180 px sobre el código; con sesión ya está en la barra. Código en grafito peso 700, mensaje secundario, botones existentes, íconos con `aria-hidden="true"`. Debe seguir cubriendo 403, 404 y 413.

Commit: `feat(ui): login y error con logo e ilustración`.

### Fase 4 — Panel principal (`dashboard.html`)

Estructura de la maqueta, con los datos y condiciones **que la plantilla ya tiene**:

1. **Bienvenida** (`.bienvenida`): título `Panel principal` (texto exigido por `test_panel.py`), “Bienvenido/a, {nombre}.” y el rol; un botón “Nueva solicitud” solo para Administrador y Emisor.
2. **Resumen general** (`.seccion-titulo` + rejilla de `metrica`):
   - Administrador: una tarjeta por estado (`resumen.estados.values()`, con su enlace a `estado_id` si hoy lo tiene), más usuarios, clientes y eventos con los textos y números actuales.
   - Emisor: una tarjeta por estado de **sus** solicitudes.
   - Si `resumen` es `None` (error de BD o Lector), conservar la rama actual: sin “Resumen general” ni “Actividad reciente”.
3. **Accesos rápidos** (`.acceso-rapido`): **fuera** de la condición de `resumen` (el Administrador sin BD debe seguir viendo “Facturas por validar”). Las tarjetas que hoy existen (nueva solicitud, ver solicitudes, facturas por validar con acento, bandeja con su contador, auditoría, usuarios, clientes), con las mismas condiciones de rol. La `alert-info` del flujo pasa a una nota con ícono al pie.
4. **Actividad reciente:** tabla dentro de una tarjeta con enlace “Ver todas” a la ruta existente. Se conservan las **dos** variantes (Administrador: fecha, acción, usuario, solicitud; Emisor: solicitud, estado, actualización), con `estado_solicitud` en la del Emisor. Sin IP ni detalle completo. Si no hay actividad, el mensaje vacío actual.

- No agregar tarjetas, totales ni enlaces que hoy no existan. No usar la palabra “Volver”. En la vista del Emisor no puede aparecer la palabra `Usuarios` (ni en etiquetas ni en textos de ayuda).
- Commit: `style(ui): panel con bienvenida, resumen, accesos y actividad`.

### Fase 5 — Listado de solicitudes (`solicitudes/listado.html`)

1. Encabezado: título y botón “Nueva solicitud” existente.
2. **Chips de estado** (`.chip-estado`): “Todas” + un chip por estado de `estados` (el mismo contexto que alimenta el `select` Estado). Cada chip es un **enlace GET** que conserva los filtros activos salvo el número de página y fija `estado_id`; el activo coincide con el valor actual. **Sin conteos.** El `select` Estado se conserva (es el campo real del formulario).
   - El parámetro de página es `pagina`: se excluye para volver a la página 1.
   - Construir la URL con `url_for`, nunca concatenando texto:
     ```jinja
     {% set filtros = request.args.to_dict() %}
     {% set _ = filtros.pop('pagina', None) %}
     {% set _ = filtros.pop('estado_id', None) %}
     <a class="chip-estado{{ ' active' if not request.args.get('estado_id') }}"
        href="{{ url_for('solicitudes.listado', **filtros) }}">Todas</a>
     {% for estado in estados %}
     <a class="chip-estado{{ ' active' if request.args.get('estado_id') == estado.id|string }}"
        href="{{ url_for('solicitudes.listado', estado_id=estado.id, **filtros) }}">{{ estado.nombre }}</a>
     {% endfor %}
     ```
     Ajustar `estados`, `estado.id` y `estado.nombre` a los nombres reales de la plantilla; agregar `aria-current="true"` al chip activo.
3. **Tarjeta de filtros** (`.panel-filtros`): campos `q`, `cliente_id`, `rut`, `desde`, `hasta`, `monto`, `estado_id`, `emisor_id` (solo Administrador) con sus `name` y `value` actuales; botón Filtrar y enlace “Limpiar filtros” a `url_for('solicitudes.listado')`.
4. **Tabla** en tarjeta con `.table-responsive`, cabecera en mayúsculas **solo por CSS** (los `<th scope="col">…</th>` no cambian): RUT, Cliente, Concepto (truncado con `title`, conservar), Monto (`fw-semibold`), Fecha, Origen, Responsable (solo Administrador), Estado con `estado_solicitud`, Acciones (Ver / Factura / Editar, mismas condiciones).
5. Paginación Anterior/Siguiente con el estilo de `.pagination`, misma lógica y mismos textos (`Siguiente` lo verifica un test). Mensaje vacío existente.
- Commit: `style(ui): listado de solicitudes con chips y filtros`.

### Fase 6 — Nueva solicitud y edición (`nueva.html`, `editar.html`)

- Tarjeta con encabezado e ícono. Mantener `enctype="multipart/form-data"`, `data-bloquear-envio`, `csrf_token`, `token_envio` y el orden de los campos.
- **Secciones numeradas** (`.seccion-formulario`) solo con campos contiguos: 1 “Cliente y concepto” (`cliente_id`, `concepto`), 2 “Datos de facturación” (`monto_bruto`, `fecha_emision`, `tipo_afectacion`, `nro_orden_compra`), 3 “Documentos adjuntos” (`adjuntos`). No mover campos entre secciones si cambia el orden de envío.
- **Concepto:** `.ayuda-campo` con `<span id="contador-concepto" class="contador">0 / 500</span>` (texto inicial estático; `ui.js` lo actualiza). Si se implementa 4.7, cargar `ui.js` desde `{% block scripts %}`.
- **Adjuntos:** `input` con `.form-control`, mismas restricciones (`multiple`, `accept=".pdf,.png,.jpg,.jpeg"`); se conserva el texto de ayuda existente “Opcional. PDF, PNG o JPG; hasta 3 archivos de 5 MB.” y los mensajes de error de adjuntos.
- **Errores de validación:** `invalid-feedback` y valores recuperados (`values`) como hoy.
- **Botones:** conservar los tres (Registrar solicitud, Cancelar, Abrir formulario nuevo) con los mismos textos, alineados a la derecha. No hay ficha del cliente (tabla 2.3).
- `editar.html`: mismo estilo; sin la sección de adjuntos si hoy no existe.
- Commit: `style(ui): nueva solicitud en secciones y edición`.

### Fase 7 — Detalle, factura y proceso (`detalle.html`, `factura.html`, `_proceso.html`)

- **Encabezado:** “Solicitud {public_id[:8]}” (en `factura.html` debe seguir el texto `Solicitud 1234abcd`), `estado_solicitud` y las migas.
- **`_proceso.html`:** solo CSS. `.pasos-proceso` con píldoras (4.3), `.nav-tabs` subrayadas (4.2). **No tocar** `aria-current="step">{{ paso }}`.
- **Banner de estado** (`.banner-estado`) al inicio del detalle: borde izquierdo según estado y etiqueta; incluye el **motivo de rechazo** donde hoy se muestra.
- **Tarjetas** (mismo contenido y condiciones):
  - Receptor histórico y Datos de facturación en `.detalle-rejilla`; monto y concepto destacados.
  - **Documentos adjuntos:** respetar `adjuntos is none` (aviso de que no se pudieron cargar), lista (`.fila-archivo` con ícono por extensión, nombre, tamaño y enlace/botón de descarga existente) y vacío (mensaje actual). Nombres siempre escapados.
  - **Documento XML:** estado actual y formulario de carga (`archivo_xml`) con su `enctype`.
  - **Envío por correo:** botón existente con `data-confirmar` y tabla de envíos en `.table-responsive`.
  - **Gestión del estado** (Administrador): botones aprobar / devolver / rechazar con sus `data-confirmar` y campo de motivo; `btn-success` / `btn-warning` / `btn-danger` mantienen su semántica.
- “Continuar a la factura” se mantiene.
- `factura.html`: el diccionario `colores` y sus clases no cambian; versiones en tabla de tarjeta.
- Commit: `style(ui): detalle de solicitud, factura y proceso`.

### Fase 8 — Clientes (`clientes/listado.html`, `clientes/formulario.html`)

- **Listado:** encabezado con botón “Nuevo cliente” (ya existe), tabla en tarjeta con avatar `iniciales(cliente.razon_social)` (32 px, `aria-hidden="true"`), RUT, correo de contacto y etiqueta activo/inactivo (4.3). Acciones existentes como `btn-sm`.
- **Formulario:** tarjeta con rejilla `row g-3` + `col-md-6` **reordenando columnas, no campos**; acciones Cancelar/Guardar al pie con los textos actuales.
- Sin buscador, filtros ni totales nuevos.
- Commit: `style(ui): clientes`.

### Fase 9 — Usuarios, perfiles y permisos (`admin/usuarios.html`, `usuario_editar.html`)

- **Encabezado** “Gestión de usuarios”.
- **Totales** (`metrica`): total, activos e inactivos calculados en la plantilla desde `usuarios` y `usuario.activo` (tabla 2.3).
- **Crear usuario** (columna izquierda): `form` con sus campos, ícono en recuadro salvia y botón primario. Si hay botón de mostrar contraseña, **no** reutilizar los ids de `login.js` (`#password`, `#togglePassword`) ni agregar JS.
- **Usuarios registrados** (derecha): tabla en tarjeta con avatar de iniciales, nombre, correo, etiqueta de rol y estado, y acciones Editar / Desactivar–Reactivar con sus `data-confirmar`. Mensaje vacío existente. **Sin buscador.**
- **Perfiles y permisos:**
  - una `.tarjeta-perfil` por perfil de `perfiles` (nombre, descripción si existe, `usuarios_activos`);
  - `.matriz-permisos` capacidades × perfiles dentro de `.table-responsive`, **con el marcado actual de cada celda** (`aria-label="Permitido"` / `visually-hidden` “No permitido”).
- `usuario_editar.html`: tarjeta con encabezado, `bi-person` en recuadro salvia y acciones al pie.
- Commit: `style(ui): usuarios, perfiles y permisos`.

### Fase 10 — Bandeja de correos y auditoría (`admin/correos.html`, `admin/auditoria.html`)

- **Correos:** botón “Revisar bandeja” como primario, aviso IMAP (`alert-warning`), selector de estado re-tematizado, tabla en tarjeta. El diccionario `colores` no cambia (`'dark'` se ve neutro por 4.3).
- **Auditoría:** tabla en tarjeta, fechas en `small` secundario, etiquetas de acción como badges neutros si ya son `badge`. No mostrar IP ni detalles que hoy no se muestren.
- Commit: `style(ui): bandeja de correos y auditoría`.

### Fase 11 — Responsive, accesibilidad y revisión final

- **Responsive:** 1280 px (barra visible), 992 px (*offcanvas* y botón ☰), 576 px (topbar compacta, tablas en `.table-responsive`, rejilla de métricas a 1 columna, chips con scroll horizontal, botones que bajan de línea).
- **Accesibilidad:** `:focus-visible` en enlaces, botones, campos y menú; orden de tabulación botón → menú → contenido; Escape cierra el *offcanvas*; íconos decorativos con `aria-hidden="true"`; chips con `aria-current="true"` en el activo; tarjetas-enlace con un único enlace (`stretched-link`).
- **Contraste:** ningún par texto/fondo bajo 4,5:1; medir cualquier par nuevo.
- **Impresión:** ocultar `.sidebar`, `.topbar`, `.flash-container` y migas.
- Commit: `style(ui): responsive, foco y estilos de impresión`.

---

## 6. Verificación

Ejecutar desde la subcarpeta del proyecto (la que contiene `app/`), en la rama `feat/facturaciones-v2-sec`. La base de comparación es la etiqueta `rediseno-base` (Fase 0):

```bash
BASE=rediseno-base
git rev-parse --abbrev-ref HEAD   # debe imprimir feat/facturaciones-v2-sec
```

### 6.1 Automática (obligatoria antes de cada commit)

```bash
BASE=rediseno-base   # etiqueta creada en la Fase 0

# 1. Tests (todos los existentes, incluidos los de las funcionalidades nuevas)
pytest -q

# 2. Nada fuera del alcance (debe salir vacío)
git diff --name-only --relative "$BASE" \
  | grep -vE '^app/(templates/|static/(css|img|fonts)/|static/js/ui\.js$)' \
  | grep -v '^docs/diseno/'

# 3. Restos del tema oscuro o dependencias bloqueadas (debe salir vacío)
grep -rnE 'data-bs-theme="dark"|navbar-dark|text-white|btn-outline-light|unpkg\.com|fonts\.googleapis|lucide|barra-principal|--navy|--mint' app/templates app/static/css

# 4. Estilos o JS en línea, y |safe (debe salir vacío)
grep -rnE 'style=|onclick=|onsubmit=|<script>|\|\s*safe' app/templates

# 5. !important solo en el bloque de .badge (revisar cada coincidencia)
grep -n '!important' app/static/css/*.css

# 6. Ningún JS existente modificado (debe salir vacío)
git diff --name-only --relative "$BASE" -- app/static/js/app.js app/static/js/login.js

# 7. Ningún atributo funcional ni lógica Jinja eliminados (debe imprimir solo "OK …")
patron='(name|id|for|action|method|enctype|accept|value|required|maxlength|minlength|pattern|multiple|novalidate|autocomplete|data-[a-z-]+)="[^"]*"|url_for\([^)]*\)|\{%-? *(if|elif|else|for|set|from|import|macro|call)[^%]*%\}'
for f in $(git diff --name-only --relative "$BASE" -- app/templates); do
  [ -f "$f" ] || continue
  git cat-file -e "$BASE:./$f" 2>/dev/null || { echo "NUEVO $f"; continue; }
  faltan=$(comm -23 <(git show "$BASE:./$f" | grep -oE "$patron" | sort -u) <(grep -oE "$patron" "$f" | sort -u))
  [ -z "$faltan" ] && echo "OK $f" || { echo "REVISAR $f"; echo "$faltan"; }
done

# 8. Cadenas que exigen los tests de navegación (cada una debe aparecer)
grep -c 'aria-label="Ruta de navegación"' app/templates/base.html
grep -c 'class="btn btn-outline-secondary btn-sm"' app/templates/base.html
grep -c 'aria-current="step">{{ paso }}' app/templates/solicitudes/_proceso.html
grep -c '<th scope="col">Concepto</th>' app/templates/solicitudes/listado.html
grep -c 'aria-label="Permitido"' app/templates/admin/usuarios.html

# 9. Ningún texto visible protegido por tests desapareció (debe salir vacío)
for s in "Panel principal" "Facturas por validar" "Actividad reciente" "Usuarios activos" \
         "Clientes activos" "Eventos registrados" "Siguiente" "Documentos adjuntos" \
         "Sin documentos adjuntos." "No se pudieron cargar los documentos adjuntos." \
         "Receptor histórico" "Perfiles y permisos" "No permitido" "Reprocesar" \
         "Historial de versiones" "Cerrar sesión"; do
  grep -rqF "$s" app/templates || echo "FALTA: $s"
done
```

> En la verificación 7 solo es aceptable que falte algo si se movió a `_ui.html` o a `base.html` sin cambiar su comportamiento; explicarlo en el resumen. La base es siempre `rediseno-base`, nunca `main` (puede no tener las funcionalidades ni sus tests).

### 6.2 Manual (la hace la persona en el navegador)

Para **Administrador** y **Emisor** (y **Lector** para el panel y el error 403):

1. **Login:** logo e ilustración sin bordes extraños; mostrar/ocultar contraseña y errores de validación funcionan.
2. **Favicon** visible; sin 404 ni errores de CSP en la consola.
3. **Barra lateral:** ítem activo correcto; el Emisor no ve “Administración”; ☰ y Escape funcionan bajo 992 px.
4. **Panel:** los totales coinciden con los de antes del rediseño; la actividad muestra lo mismo; el Emisor solo ve lo suyo.
5. **Listado:** buscar por `q` (cliente o concepto), filtrar por cliente y por estado, chips de estado, paginación con filtros conservados, columnas Concepto/Origen/Responsable.
6. **Nueva solicitud:** crear con 0, 1 y varios adjuntos; archivo de tipo o tamaño no permitido muestra el error existente; contador de caracteres (si se implementó); el doble clic no duplica el envío.
7. **Detalle:** adjuntos se descargan; cargar XML; enviar correo; aprobar / devolver / rechazar con confirmación; banner y motivo de rechazo.
8. **Usuarios:** crear, editar, desactivar/reactivar; “Perfiles y permisos” coincide con los permisos reales.
9. **Clientes, Bandeja de correos y Auditoría:** formularios guardan, tablas se leen.
10. **Error:** abrir una ruta inexistente con y sin sesión; subir un archivo muy grande (413).
11. **Impresión** del detalle sin barra lateral.

---

## 7. Commits sugeridos

Todos sobre `feat/facturaciones-v2-sec`, con `pytest -q` en verde. Si la persona usa atribución de Claude Code en sus commits, se mantiene la que tenga configurada.

1. `chore(ui): agrega logo, favicon e ilustración optimizados`
2. `style(ui): tema claro salvia, re-tema de Bootstrap y componentes`
3. `feat(ui): barra lateral con logo, topbar y favicon`
4. `feat(ui): login y error con logo e ilustración`
5. `style(ui): panel con bienvenida, resumen, accesos y actividad`
6. `style(ui): listado de solicitudes con chips y filtros`
7. `style(ui): nueva solicitud en secciones y edición`
8. `style(ui): detalle de solicitud, factura y proceso`
9. `style(ui): clientes`
10. `style(ui): usuarios, perfiles y permisos`
11. `style(ui): bandeja de correos y auditoría`
12. `style(ui): responsive, foco y estilos de impresión`

---

## 8. Prompt para Claude Code (repetir por fase)

```
Trabaja en la rama feat/facturaciones-v2-sec, desde la subcarpeta del proyecto
(la que contiene app/). No cambies de rama, no hagas push, rebase ni merge.
Lee docs/diseno/PLAN_REDISENO_PLATAFORMA.md (v2) completo.
Ejecuta SOLO la Fase N. (En la Fase 0 crea la etiqueta rediseno-base;
en las demás, compárate siempre contra ella.)
Las funcionalidades de la maqueta ya existen en el backend: solo las vistes,
no las reimplementes. Cumple la sección 1 sin excepciones: cambias plantillas,
CSS, imágenes y, como máximo, app/static/js/ui.js; nunca rutas, Python,
migraciones, tests, la CSP ni app.js / login.js.
Lee cada plantilla completa antes de editarla y confirma que cada variable
que uses ya existe en su contexto; si no existe, no apliques ese elemento.
Al terminar, corre las verificaciones de la sección 6.1 y, si todo pasa,
haz el commit indicado en la sección 7.
Entrega un resumen corto: archivos tocados, resultado de pytest y de cada
verificación, elementos "no aplicados" y lo que no pudiste comprobar visualmente.
Si una tarea choca con una regla, no la hagas y explica por qué.
```

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Un test compara marcado exacto (botón Volver, `aria-current`, menú) | Cadenas en 1.3 y verificación 6.1-8. Si falla, revertir el marcado, no el test |
| `.text-bg-*` de Bootstrap usa `!important` | Sobrescribir solo con `.badge.text-bg-*`; único `!important` permitido (4.3) |
| El *offcanvas* no abre en móvil | Requiere `bootstrap.bundle.min.js` (ya cargado) y que `id="menu-principal"` coincida con `data-bs-target` |
| Archivos de Inter ausentes | Sin `@font-face` cae a `system-ui` |
| La envoltura `.app-shell` rompe login o error sin sesión | Se abre y cierra con `{% if current_user.is_authenticated %}`; probar ambas páginas sin sesión |
| Se reimplementa lógica por imitar la maqueta | Regla 1.2 y tabla 2.3. Ante la duda, no aplicar |
| Chips de estado pierden filtros o rompen la paginación | Construir la URL con `request.args` excluyendo solo la página; probar con `q` + `cliente_id` activos |
| Un campo de contexto no existe con el nombre esperado (por ejemplo, estado del usuario) | Verificar en Fase 0; si falta, omitir el elemento |
| Nombres de archivo de adjuntos con caracteres especiales | Jinja escapa por defecto; prohibido `|safe` (verificación 6.1-4) |
| `resumen` o `adjuntos` en `None` por error de BD | Conservar las ramas existentes y probar ese caso con el estado vacío |
| Un texto protegido por tests (tabla 1.3) se reescribe al imitar la maqueta | Verificación 6.1-9; los textos existentes no se cambian |
| Se trabaja contra `main` y se comparan archivos sin las funcionalidades | Base fija `rediseno-base` y verificación de rama al inicio de 6.1 |
| Comandos ejecutados desde la raíz de Git (carpeta exterior) | Rutas relativas fallan; ejecutar siempre desde la subcarpeta con `--relative` |
| Logo sobre fondo oscuro o salvia medio | Solo sobre blanco o `--color-salvia-claro` |
| Estados desconocidos en el macro | Caen a gris sin romper nada |

---

## 10. Fuera de alcance

- Modo oscuro alternativo o selector de tema.
- Funcionalidades de la maqueta sin backend: ficha de solo lectura del cliente, conteos por estado en los chips, buscador y filtros de usuarios en vivo, autocompletado, arrastrar y soltar archivos, “Recordarme”, recuperación de contraseña.
- Cambios en la CSP, rutas, servicios, permisos, migraciones o base de datos.
- Rediseño de correos enviados (`correos/*.txt`) o de documentos PDF/XML.
