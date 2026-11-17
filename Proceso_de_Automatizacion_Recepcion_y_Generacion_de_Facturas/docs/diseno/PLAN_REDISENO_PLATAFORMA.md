# Plan de rediseño visual completo — Facturaciones SpA (con logo)

> **Para:** Claude Code, ejecutando fase por fase.
> **Alcance:** solo diseño. Se cambia cómo se ve la plataforma completa (tema, colores, tipografía, layout, logo e imágenes). No cambia lo que hace.
> **Referencia visual:** `docs/diseno/referencia/` (maqueta estática de 11 páginas).
> **Recursos de marca listos para usar:** `docs/diseno/assets/` (logo, favicon e ilustración ya optimizados).
> **Reemplaza a:** `docs/diseno/PLAN_IMPLEMENTACION_DISENO.md`. Si ambos se contradicen, manda este.

---

## 0. Resumen en una línea

Pasar de tema oscuro con barra superior azul a **tema claro salvia/grafito con barra lateral y logo**, reutilizando Bootstrap 5.3 y cambiando solo plantillas Jinja (marcado y clases), CSS e imágenes.

---

## 1. Reglas obligatorias

Aplican a **todas** las fases. Si una tarea choca con una regla, gana la regla y la tarea se omite (dejar nota en el resumen de la fase).

### 1.1 Archivos que se pueden modificar o crear

| Ruta (relativa a la carpeta que contiene `app/`) | Permitido |
|---|---|
| `app/templates/**/*.html` | Solo marcado, clases, envoltorios, íconos y textos decorativos ya existentes |
| `app/templates/_ui.html` | **Crear**: macros de presentación (sección 4.4) |
| `app/static/css/app.css` | Reescribir |
| `app/static/css/login.css` | Reescribir |
| `app/static/img/*` | **Crear**: copiar desde `docs/diseno/assets/` |
| `app/static/fonts/inter/*` | **Crear**: solo si la persona dejó los archivos (Fase 0) |

**Cualquier otro archivo queda prohibido**, en particular: `app/**/*.py` (incluida la CSP de `app/security.py`), `app/static/js/*.js`, `test/**`, `config.py`, `seed.py`, `requirements*.txt`, el SQL y `docs/diseno/referencia/**`.

### 1.2 Prohibido en las plantillas

1. Crear, quitar o renombrar rutas, endpoints, formularios, campos o valores enviados.
2. Agregar funcionalidad que hoy no existe: botones, enlaces, filtros, buscadores, contadores, modales, columnas, paginación, “Recordarme”, “¿Olvidaste tu contraseña?”, tarjetas de estadísticas, “Actividad reciente”.
3. Copiar JavaScript de la maqueta (`js/solicitudes.js`, `js/nueva-solicitud.js` o scripts en línea).
4. Escribir `style="..."`, `onclick=`, `onsubmit=` o `<script>` en línea. **`test/test_seguridad.py::test_plantillas_sin_javascript_ni_estilos_en_linea` lo verifica.**
5. Cargar Lucide (`unpkg.com`) o Google Fonts. La CSP solo permite `'self'` y `https://cdn.jsdelivr.net`, e imágenes `'self' data:`.
6. Mostrar datos de ejemplo de la maqueta (nombres, montos, “Datos de demostración”, “SOL-001”).
7. Copiar `docs/diseno/referencia/css/styles.css`. Tiene 11.138 líneas, 419 colores y 234 `!important`. Se usa solo como referencia visual.

### 1.3 Se preserva exactamente

- **Atributos funcionales:** `name`, `id`, `for`, `action`, `method`, `enctype`, `value`, `required`, `maxlength`, `minlength`, `pattern`, `inputmode`, `accept`, `autocomplete`, `novalidate` y campos ocultos (`csrf_token`, `token_envio`, `version`, etc.). Se pueden **agregar** `id` nuevos para el layout; no se puede quitar ni renombrar ninguno.
- **Lógica Jinja:** cada `{% if %}`, `{% for %}`, `{% set %}`, macro, `url_for(...)`, condición por rol (`current_user.role_name`) y `migas`.
- **Hooks de JavaScript:**
  - `static/js/app.js`: `data-confirmar`, `data-bloquear-envio`, `button[type='submit']`.
  - `static/js/login.js`: `.needs-validation`, `#password`, `#togglePassword`, `#passwordIcon` y las clases `bi-eye` / `bi-eye-slash` del ícono.
- **Cadenas que verifica `test/test_navegacion.py`:**
  - `aria-label="Ruta de navegación"`
  - `<a href="{{ ns.volver }}" class="btn btn-outline-secondary btn-sm">` (botón **Volver** de las migas): mismas clases, **mismo orden** y nada entre `href` y `class`.
  - Texto `Cerrar sesión`.
  - En `_proceso.html`: `aria-current="step">{{ paso }}` sin espacio ni salto de línea entre `>` y el texto (también para `Rechazada`).
  - `href` del menú: `/dashboard`, `/solicitudes/`, `/solicitudes/nueva`, `/admin/correos`, `/clientes/`, `/admin/usuarios`, `/admin/auditoria`, con las mismas condiciones de rol.
  - El panel (`/dashboard`) **no** puede contener la palabra `Volver` en ninguna parte (barra lateral y topbar incluidas).
  - Texto `Solicitud 1234abcd` en el encabezado de `factura.html`.
- **Bootstrap 5.3.3 y Bootstrap Icons 1.11.3** desde jsDelivr con sus `integrity` actuales.

### 1.4 Forma de trabajo

- Trabajar en una rama nueva (`feat/rediseno-visual`), nunca en la principal.
- **Leer completa cada plantilla antes de editarla.**
- Una fase = un commit, con `pytest -q` en verde antes de cada commit.
- Si un test falla: **revertir el marcado, no el test**.
- Al final de cada fase, entregar un resumen breve: archivos tocados, resultado de `pytest` y qué **no** se pudo verificar (render real en navegador, móvil).

---

## 2. Diagnóstico

| Aspecto | Actual | Objetivo |
|---|---|---|
| Tema | Oscuro: `data-bs-theme="dark"`, fondo `#171812`, barra `#192f58` | Claro: fondo `#F5F6F3`, tarjetas blancas, salvia/grafito |
| Layout | `navbar` superior colapsable | Barra lateral de 250 px con logo y topbar con usuario. En móvil, la barra lateral se abre como *offcanvas* de Bootstrap |
| Marca | Logo falso de 4 cuadrados (`.brand-mark`) y texto | Logo real `logo-facturaciones.png` y favicon |
| Tipografía | Arial | Inter alojada en el servidor, con respaldo `system-ui` |
| Íconos | Bootstrap Icons | Bootstrap Icons (se mantienen; la maqueta usa Lucide y no pasa la CSP) |
| Estados | `badge text-bg-*` sólidos | Etiquetas redondeadas de fondo suave, mismas clases |
| CSS propio | `app.css` (1,7 KB) y `login.css` (5 KB) | `app.css` consolidado (< 900 líneas) y `login.css` nuevo |

**Por qué el logo obliga a cambiar el tema:** el texto del logo es verde casi negro (`#0B2E11`). Sobre el fondo oscuro actual el contraste es de 1,2:1 y sobre la barra azul de 1,1:1, así que no se ve. Sobre blanco es de 14,9:1. **El logo solo se usa sobre fondos claros.**

**Estrategia técnica:** el 90 % de la interfaz usa clases de Bootstrap (`card`, `btn`, `form-control`, `table`, `badge`, `alert`, `text-body-secondary`). Se re-tematiza Bootstrap con sus variables CSS (`--bs-*`), de modo que la mayoría de las plantillas cambian de aspecto **sin editar su marcado**. Solo se reescriben `base.html`, `auth/login.html` y `errores/error.html`, más ajustes puntuales de clases en el resto.

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
{# Solo presentación: no contiene lógica de negocio. #}

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
```

Uso de `estado_solicitud`:
- `solicitudes/listado.html` (columna Estado; hoy es siempre `text-bg-secondary`).
- `solicitudes/detalle.html` (bloque “Gestión del estado”, `{{ solicitud.estado_nombre }}`).

En ambos casos se importa con `{% from "_ui.html" import estado_solicitud %}`. El texto visible no cambia. **No usarlo en `_proceso.html`**: ahí se conserva el marcado y solo cambia el CSS.

### 4.5 Tipografía

Inter 400/500/600/700, alojada en el servidor.
- Si la persona dejó `app/static/fonts/inter/Inter-{400,500,600,700}.woff2` en la Fase 0: declarar `@font-face` con `font-display: swap` y agregar la licencia `OFL.txt` en la misma carpeta.
- Si **no** están: **no** declarar `@font-face` (evita errores 404) y dejar que `--fuente` use `system-ui`. Avisarlo en el resumen.
- Jerarquía: `h1`/`.h2` de página en 1,6 rem, peso 600, `letter-spacing: -0.02em`; `.h5` de tarjeta en 1,05 rem, peso 600; texto base en 0,9375 rem.

### 4.6 Íconos

Se mantienen Bootstrap Icons. Cambios opcionales en el menú para acercarse a la maqueta: Panel `bi-grid-1x2`, Solicitudes `bi-file-earmark-text`, Nueva solicitud `bi-file-earmark-plus`, Bandeja `bi-inbox`, Clientes `bi-building`, Usuarios `bi-people`, Auditoría `bi-clock-history`. Todos los íconos decorativos con `aria-hidden="true"`.

---

## 5. Fases

### Fase 0 — Preparación

1. Crear la rama `feat/rediseno-visual` desde la rama principal actualizada.
2. Ejecutar `pytest -q` y anotar el resultado base. Si algo falla **antes** de tocar nada, detenerse e informar.
3. Crear `app/static/img/` y copiar los 5 archivos de `docs/diseno/assets/` (sección 3) con los mismos nombres. `login-ilustracion.png` mantiene ese nombre.
4. Comprobar si existen `app/static/fonts/inter/*.woff2`. **Claude Code no descarga fuentes**: si faltan, seguir con el respaldo (4.5) y avisarlo.
5. Commit: `chore(ui): agrega logo, favicon e ilustración optimizados`.

> **Paso para la persona (opcional, antes de la Fase 1):** descargar Inter desde https://rsms.me/inter/ y dejar `Inter-400.woff2`, `Inter-500.woff2`, `Inter-600.woff2`, `Inter-700.woff2` y `OFL.txt` en `app/static/fonts/inter/`.

### Fase 1 — Fundamentos (CSS global)

Reescribir `app/static/css/app.css` en este orden:

```
1. @font-face (solo si existen los archivos)
2. Tokens (:root) ........................... 4.1
3. Re-tema de Bootstrap ..................... 4.2
4. Base: body, títulos, enlaces, :focus-visible con var(--anillo-foco)
5. Shell: .app-shell, .sidebar, .topbar, .app-main, .flash-container, migas
6. Componentes: botones, tarjetas, formularios, tablas, badges (4.3), alertas, pestañas, .pasos-proceso, avatar
7. Utilidades existentes que se conservan: .texto-preformateado, .ancho-limitado
8. Excepciones por página (mínimas)
9. Responsive: solo dos cortes, 991.98px y 575.98px
```

- Conservar las clases que hoy usan las plantillas: `.flash-container`, `.texto-preformateado`, `.ancho-limitado`, `.pasos-proceso` (y su flecha `→` entre pasos, ahora en color secundario).
- Eliminar las variables del tema oscuro (`--navy`, `--dark`, `--input`, `--mint`) y `.barra-principal`.
- En `base.html`, cambiar solo `data-bs-theme="dark"` → `data-bs-theme="light"` en esta fase (el layout se cambia en la Fase 2).
- Objetivo: menos de 900 líneas, sin colores sueltos fuera de los tokens y sin `!important` fuera de 4.3.
- Commit: `style(ui): tema claro salvia y re-tema de Bootstrap`.

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
                <p class="sidebar-grupo">Menú principal</p>
                <ul class="nav flex-column">
                    {# Panel, Solicitudes, Nueva solicitud: mismas llamadas y condiciones que hoy #}
                </ul>

                {% if current_user.role_name == 'Administrador' %}
                <p class="sidebar-grupo">Administración</p>
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

            {# flash: mismo bloque que hoy #}
            {# migas: mismo bloque que hoy, sin tocar el <a … class="btn btn-outline-secondary btn-sm"> #}

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
- **Menú:** los 7 enlaces, sus `endpoint`, sus condiciones de rol y su cálculo de `activo` quedan **idénticos**. Solo se reparten en los dos grupos. El grupo “Administración” va dentro de la condición de Administrador, así que el Emisor no lo ve.
- **Estilo del menú** (scope `.sidebar .nav-link` para no afectar a `.nav-tabs`):
  - enlace: texto `#687168`, 0,875 rem, padding 0,7 rem, radio 8 px, ícono a 1,1 rem;
  - hover: fondo `--color-salvia-tenue`;
  - activo: fondo `--color-salvia-claro`, texto grafito, peso 600 e ícono `--color-salvia-oscuro`.
- **Títulos de grupo** (`.sidebar-grupo`): 0,6875 rem, mayúsculas, `letter-spacing: .08em`, peso 700, color secundario.
- **Barra lateral:** fondo blanco, borde derecho `--color-borde`, ancho `--ancho-sidebar`. En ≥ 992 px es fija (`position: sticky; top: 0; height: 100vh; overflow-y: auto`). En < 992 px Bootstrap la convierte en *offcanvas*: el JS de Bootstrap ya cargado la maneja con atributos `data-bs-*`, sin JavaScript propio.
- **`.app-shell`:** `display: flex`; **`.app-main`:** `flex: 1; min-width: 0`, padding de 2 rem a 2,5 rem en escritorio y de 1 rem en móvil.
- **Topbar:** borde inferior `--color-borde`, padding inferior de 1 rem. Avatar circular de 40 px con fondo `--color-salvia-claro`, iniciales en grafito y peso 600. En < 576 px ocultar `.topbar-usuario-texto`.
- **Contenido:** las páginas siguen usando `<main class="container …">`. En `.app-main`, `.container` puede quedar con `max-width: 1200px` y `margin-inline: 0`.
- **Flash:** se mantiene en posición fija arriba a la derecha, con radio 12 px y `--sombra-hover`.
- **Eliminar** `navbar`, `navbar-dark`, `text-white`, `btn-outline-light` y `.barra-principal`.
- **La palabra “Volver” no puede aparecer en el shell.**
- Commit: `feat(ui): barra lateral con logo, topbar y favicon`.

### Fase 3 — Login y página de error

**`auth/login.html` + `static/css/login.css`.** Sigue extendiendo `base.html` (sin sesión no se dibuja el shell).

- **Panel izquierdo** (`.login-brand-panel`), visible solo en ≥ 992 px. Fondo `--color-salvia-claro` con un degradado suave hacia `--color-salvia-tenue`. Contenido, de arriba abajo:
  1. Logo `logo-facturaciones@2x.png` mostrado a 280 px de ancho (`width="280" height="81"`), `alt="Facturaciones SpA"`.
  2. Textos **existentes** reestilizados: “SISTEMA DE GESTIÓN” (pequeño, mayúsculas, color secundario) y “Recepción y Generación de Facturas” (2,4 rem, peso 700, grafito). Bajar del tamaño actual de 5,3 rem.
  3. `login-ilustracion.png` (`alt=""`, `width="720" height="381"`, escalada al 100 % del ancho disponible con un máximo de 460 px).
  4. Pie existente “Conforme SII · Chile · 2026”, con el ícono cambiado de `bi-star` a `bi-shield-check`.
- **Eliminar** `.brand-mark` (los 4 cuadrados) y `.brand-name`: los reemplaza el logo real.
- **Panel derecho:** fondo blanco y formulario centrado con un ancho máximo de 400 px. En < 992 px, mostrar arriba del título el logo a 180 px (`<img class="login-logo-movil d-lg-none" …>`).
- El formulario, sus campos, `invalid-feedback`, el botón de mostrar contraseña y la nota de seguridad **se conservan tal cual**. Solo cambian clases visuales.
- `.btn-login`: mismo aspecto que `.btn-primary` (4.2), ancho completo, 44 px de alto.
- `.password-toggle`: borde `--color-borde`, fondo blanco, ícono en color secundario.
- `login.css` usa solo tokens de `app.css`, sin colores sueltos.

**`errores/error.html`:**
- Si **no** hay sesión: mostrar el logo (180 px) arriba del código de error. Con sesión, el logo ya está en la barra lateral.
- El código del error va en grafito, peso 700, y el mensaje en color secundario. Los botones existentes se mantienen.
- Agregar `aria-hidden="true"` a los íconos que no lo tienen.

Commit: `feat(ui): login y error con logo e ilustración`.

### Fase 4 — Panel principal (`dashboard.html`)

- Encabezado: “Panel principal” como título de página y “Bienvenido/a, {nombre}.” en color secundario.
- Las tarjetas existentes se mantienen (mismo número, textos, enlaces y condiciones). Solo cambia su aspecto:
  - el ícono del título pasa a un recuadro de 40×40 px con fondo `--color-salvia-claro`, radio 10 px e ícono `--color-salvia-oscuro`, encima del título;
  - hover de tarjeta: `--sombra-hover` y `translateY(-2px)`, salvo si el usuario prefiere `prefers-reduced-motion: reduce`;
  - la tarjeta `border-primary` (“Facturas por validar”) mantiene su borde de acento;
  - los contadores existentes (`badge text-bg-primary` / `text-bg-warning`) toman el estilo de 4.3 automáticamente.
- Quitar `<h5>` sueltos solo si se reemplazan por la misma jerarquía (`h2.h5`). No agregar tarjetas, totales ni “Actividad reciente”.
- Commit: `style(ui): panel principal`.

### Fase 5 — Solicitudes

Archivos: `listado.html`, `nueva.html`, `detalle.html`, `factura.html`, `editar.html`, `_proceso.html`.

- **`listado.html`:**
  - encabezado con título y botón “Nueva solicitud” (ya existe);
  - el panel de filtros en tarjeta queda igual, pero la etiqueta de cada filtro pasa a 0,8125 rem con peso 600;
  - en la tabla, los montos van con `fw-semibold`;
  - la columna Estado usa `estado_solicitud(solicitud.estado_nombre)` (4.4);
  - las acciones quedan como hoy (enlaces/botones `btn-sm`).
- **`nueva.html` / `editar.html`:**
  - tarjeta con un encabezado separado por borde;
  - **sin** agrupar campos en secciones numeradas si eso obliga a mover campos entre formularios. Solo agrupar visualmente si los campos ya son contiguos;
  - pie de acciones alineado a la derecha.
- **`_proceso.html`:**
  - solo CSS: `.pasos-proceso` con etiquetas tipo píldora (4.3) y la flecha en color secundario;
  - `.nav-tabs` subrayadas (4.2);
  - **no tocar** el marcado `aria-current="step">{{ paso }}`.
- **`detalle.html` / `factura.html`:**
  - las tarjetas existentes toman el estilo global;
  - los pares etiqueta/valor (`dl`, `row`) muestran la etiqueta en 0,8125 rem y color secundario, y el valor en grafito con `fw-medium`;
  - en `detalle.html`, el estado de “Gestión del estado” usa `estado_solicitud`;
  - en `factura.html`, el diccionario `colores` y sus clases no cambian;
  - las tarjetas `border-primary` / `border-success` mantienen su borde de acento;
  - `alert-secondary` queda como aviso neutro.
- Commit: `style(ui): solicitudes, detalle y factura`.

### Fase 6 — Clientes

- **`clientes/listado.html`:**
  - tabla en tarjeta;
  - a la izquierda del nombre, un avatar con `iniciales(cliente.<campo de nombre existente>)` (círculo de 32 px, `aria-hidden="true"`). Verificar el nombre real del campo en la plantilla;
  - las etiquetas activo/inactivo quedan como están (`text-bg-success` / `text-bg-secondary` → 4.3).
- **`clientes/formulario.html`:**
  - tarjeta con rejilla de 2 columnas en ≥ 768 px (`row g-3` + `col-md-6`) **solo reordenando columnas, no campos**;
  - acciones Cancelar/Guardar al pie con los textos actuales.
- Sin buscador, filtros ni indicadores nuevos.
- Commit: `style(ui): clientes`.

### Fase 7 — Administración

- **`admin/usuarios.html`:**
  - se mantiene el layout de 2 columnas (crear usuario / usuarios registrados);
  - avatar de iniciales en la tabla;
  - etiquetas de rol y estado con 4.3 (sin cambiar sus clases);
  - las acciones quedan como `btn-sm`.
- **`admin/usuario_editar.html`:** tarjeta de formulario con encabezado e ícono `bi-person` en recuadro salvia y acciones al pie.
- **`admin/correos.html`:**
  - botón “Revisar bandeja” existente como primario;
  - aviso IMAP (`alert-warning`) con el estilo global;
  - selector de estado (`form-select`) re-tematizado;
  - tabla en tarjeta;
  - **el diccionario `colores` no cambia** (`'dark'` ya se ve neutro gracias a 4.3).
- **`admin/auditoria.html`:** tabla en tarjeta y fechas en `small` con color secundario.
- Commit: `style(ui): administración`.

### Fase 8 — Responsive, accesibilidad y revisión final

- **Responsive:**
  - 1280 px: barra lateral visible y contenido con aire;
  - 992 px: la barra lateral pasa a *offcanvas* y aparece el botón ☰;
  - 576 px: topbar compacta, tablas dentro de `.table-responsive` (ya existe en 7 lugares) y botones de acción que bajan de línea sin superponerse.
- **Accesibilidad:**
  - `:focus-visible` visible en enlaces, botones, campos y elementos del menú;
  - orden de tabulación: botón de menú → menú → contenido;
  - el *offcanvas* se cierra con Escape (Bootstrap) y devuelve el foco;
  - todos los íconos decorativos con `aria-hidden="true"`.
- Comprobar que ninguna combinación de texto/fondo baje de 4,5:1. Los pares de la sección 4 ya están medidos; si se introduce otro, medirlo.
- `@media print`: ocultar `.sidebar`, `.topbar`, `.flash-container` y las migas.
- Commit: `style(ui): responsive, foco y estilos de impresión`.

---

## 6. Verificación

Ejecutar desde la carpeta que contiene `app/`.

### 6.1 Automática (obligatoria antes de cada commit)

```bash
# 1. Tests
pytest -q

# 2. Nada fuera del alcance (debe salir vacío)
git diff --name-only main... | grep -vE '^(.*/)?app/(templates/|static/(css|img|fonts)/)' | grep -v 'docs/diseno/'

# 3. Restos del tema oscuro o dependencias bloqueadas (debe salir vacío)
grep -rnE 'data-bs-theme="dark"|navbar-dark|text-white|btn-outline-light|unpkg\.com|fonts\.googleapis|lucide|barra-principal|--navy|--mint' app/templates app/static/css

# 4. Estilos o JS en línea (debe salir vacío)
grep -rnE 'style=|onclick=|onsubmit=|<script>' app/templates

# 5. !important solo en el bloque de .badge (revisar cada coincidencia)
grep -n '!important' app/static/css/*.css

# 6. Ningún atributo funcional ni lógica Jinja eliminados (debe imprimir solo "OK …")
patron='(name|id|for|action|method|enctype|value|required|maxlength|minlength|pattern|accept|data-[a-z-]+)="[^"]*"|url_for\([^)]*\)|\{%-? *(if|elif|for|set|from|import|macro|call)[^%]*%\}'
for f in $(git diff --name-only --relative main... -- app/templates); do
  [ -f "$f" ] || continue
  git cat-file -e "main:./$f" 2>/dev/null || { echo "NUEVO $f"; continue; }
  faltan=$(comm -23 <(git show "main:./$f" | grep -oE "$patron" | sort -u) <(grep -oE "$patron" "$f" | sort -u))
  [ -z "$faltan" ] && echo "OK $f" || { echo "REVISAR $f"; echo "$faltan"; }
done
```

> En la verificación 6 solo es aceptable que falte algo si se movió a `_ui.html` o a `base.html` sin cambiar su comportamiento. Si aparece, explicarlo en el resumen de la fase.

### 6.2 Manual (la hace la persona en el navegador)

Para **Administrador** y **Emisor**:

1. **Login:** el logo y la ilustración se ven sin bordes extraños; mostrar/ocultar la contraseña funciona; los errores de validación aparecen.
2. **Favicon** visible en la pestaña.
3. **Barra lateral:** el logo se ve nítido; el ítem activo coincide con la página; el Emisor no ve “Administración”.
4. **Pantalla < 992 px:** el botón ☰ abre y cierra el menú y Escape lo cierra.
5. **Solicitudes:** filtros, paginación (si existe), nueva, detalle, factura, editar, aprobar/devolver (confirmación `data-confirmar`) y envío por correo funcionan como antes.
6. **Estados:** cada estado tiene su color; los pasos del proceso y las pestañas se ven bien.
7. **Clientes, Usuarios, Bandeja de correos y Auditoría:** los formularios guardan y las tablas se leen.
8. **Página de error:** abrir una ruta inexistente con y sin sesión.
9. **Consola del navegador:** sin errores de CSP ni 404 de recursos.

---

## 7. Commits sugeridos

1. `chore(ui): agrega logo, favicon e ilustración optimizados`
2. `style(ui): tema claro salvia y re-tema de Bootstrap`
3. `feat(ui): barra lateral con logo, topbar y favicon`
4. `feat(ui): login y error con logo e ilustración`
5. `style(ui): panel principal`
6. `style(ui): solicitudes, detalle y factura`
7. `style(ui): clientes`
8. `style(ui): administración`
9. `style(ui): responsive, foco y estilos de impresión`

---

## 8. Prompt para Claude Code (repetir por fase)

```
Lee docs/diseno/PLAN_REDISENO_PLATAFORMA.md completo.
Ejecuta SOLO la Fase N.
Cumple las reglas de la sección 1 sin excepciones: solo cambias diseño
(plantillas, CSS e imágenes), nunca rutas, Python, JavaScript, tests ni la CSP.
Lee cada plantilla completa antes de editarla.
Al terminar, corre todas las verificaciones de la sección 6.1 y, si todo pasa,
haz el commit indicado en la sección 7.
Entrega un resumen corto: archivos tocados, resultado de pytest y de cada
verificación, y lo que no pudiste comprobar visualmente.
Si una tarea de la fase choca con una regla, no la hagas y explica por qué.
```

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Un test compara marcado exacto (botón Volver, `aria-current`, menú) | Cadenas listadas en 1.3. Si un test falla, revertir el marcado, no el test |
| `.text-bg-*` de Bootstrap usa `!important` | Sobrescribir solo con `.badge.text-bg-*` (mayor especificidad), único `!important` permitido (4.3) |
| El *offcanvas* no abre en móvil | Requiere `bootstrap.bundle.min.js` (ya cargado) y que el `id="menu-principal"` coincida con `data-bs-target` |
| Archivos de Inter ausentes | Sin `@font-face`, la fuente cae a `system-ui` y nada se rompe |
| Al envolver el contenido en `.app-shell` se rompe el login o la página de error sin sesión | La envoltura se abre y cierra con `{% if current_user.is_authenticated %}`; probar ambas páginas sin sesión |
| Se agrega funcionalidad por imitar la maqueta | Regla 1.2 y verificación 6.1-6. Ante la duda, no agregar |
| Logo sobre fondo oscuro o salvia medio | Regla de la sección 3: el logo solo va sobre blanco o `--color-salvia-claro` |
| Los nombres de estado no coinciden con el macro | Los valores salen de `_proceso.html` (`Pendiente`, `En revisión`, `En corrección`, `Aprobada`, `Rechazada`); un estado desconocido cae a gris sin romper nada |

---

## 10. Fuera de alcance

- Modo oscuro alternativo o selector de tema.
- Funcionalidades de la maqueta inexistentes en el backend: buscadores, filtros en vivo, estadísticas, historial de actividad, autocompletado de clientes, carga de adjuntos, “Recordarme”, recuperación de contraseña.
- Cambios en la CSP, en rutas, en servicios o en la base de datos.
- Rediseño de correos HTML enviados al cliente o de documentos PDF/XML.
