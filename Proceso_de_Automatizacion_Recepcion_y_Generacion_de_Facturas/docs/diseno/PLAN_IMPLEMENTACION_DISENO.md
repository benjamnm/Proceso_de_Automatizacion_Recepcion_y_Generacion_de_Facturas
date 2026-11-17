# Plan de implementación — Capa de diseño (Facturaciones SpA)

> Documento para ejecutar con Claude Code, fase por fase.
> Alcance: **solo presentación** (HTML/Jinja de las plantillas, CSS, íconos, tipografía e imágenes).
> Referencia visual: maqueta estática `FacturacionesSpA-Frontend` (11 páginas HTML, `css/styles.css`, 2 JS, 2 imágenes).

---

## 1. Reglas obligatorias para Claude Code

Aplicar en **todas** las fases. Si una tarea choca con alguna regla, la regla manda y la tarea se omite.

### 1.1 Prohibido
1. Crear, quitar o renombrar rutas, endpoints, blueprints, formularios, campos (`name`), consultas SQL o funciones en `app/services/`, `app/*/routes.py`, `app/models.py`, `app/__init__.py`.
2. Agregar botones, enlaces, filtros, buscadores, contadores, modales, paneles de lectura o columnas que no existan hoy en la plantilla Jinja equivalente.
3. Portar JavaScript de comportamiento de la maqueta (`js/solicitudes.js`, `js/nueva-solicitud.js`, scripts inline de cada página: filtros en vivo, pestañas por JS, modales, autocompletado de cliente, búsqueda local).
4. Usar `<script>` inline, atributos `style="..."`, `onclick`, Lucide (`unpkg.com/lucide@latest`) o Google Fonts: la CSP de `app/security.py` los bloquea y **no se debe modificar la CSP**.
5. Mostrar datos ficticios de la maqueta (contadores, “Datos de demostración”, “Las acciones del prototipo…”, nombres de ejemplo).

### 1.2 Preservar sin cambios
- Atributos funcionales: `name`, `id`, `for`, `action`, `method`, `enctype`, `value`, `required`, `maxlength`, `inputmode`, `accept`, campos ocultos (`csrf_token`, `token_envio`, `version`).
- Hooks de JS existentes: `data-confirmar`, `data-bloquear-envio` (`static/js/app.js`), `.needs-validation`, `#password`, `#togglePassword`, `#passwordIcon` (`static/js/login.js`).
- Lógica Jinja: condiciones por rol (`current_user.role_name`), `{% if %}`/`{% for %}`, macros, `migas`, `url_for(...)`.
- Cadenas verificadas por `test/test_navegacion.py`:
  - `aria-label="Ruta de navegación"`
  - `<a href="{url}" class="btn btn-outline-secondary btn-sm">` (botón **Volver** de las migas: conservar **exactamente** estas clases y orden de atributos)
  - Texto `Cerrar sesión`, `aria-current="step">{estado}` en `_proceso.html`
  - Los `href` del menú: `/solicitudes/`, `/solicitudes/nueva`, `/admin/correos`, `/clientes/`, `/admin/usuarios`, `/admin/auditoria`
  - El panel (`/dashboard`) **no** debe contener la palabra `Volver`.
- Bootstrap 5.3.3 y Bootstrap Icons 1.11.3 desde jsDelivr con SRI (ya permitidos por la CSP).

### 1.3 Forma de trabajo
- Un incremento por fase, con `pytest` en verde antes de cada commit.
- Commit convencional sugerido al final de cada fase (sección 6).
- Al terminar cada fase, listar lo **no verificado** en el entorno (render visual real, navegadores).

---

## 2. Diagnóstico: frontend actual vs. maqueta

### 2.1 Estado actual
| Aspecto | Actual |
|---|---|
| Tema | Oscuro (`data-bs-theme="dark"`), barra superior azul marino `#192f58`, fondo `#171812` |
| Layout | `navbar` horizontal de Bootstrap con colapso móvil; contenido en `.container` |
| CSS propio | `static/css/app.css` (≈1,7 KB) + `static/css/login.css` (≈5 KB) |
| Íconos | Bootstrap Icons |
| Tipografía | Arial / Helvetica |
| Componentes | Clases de Bootstrap (`card`, `btn`, `form-control`, `table`, `badge text-bg-*`, `alert`, `nav-tabs`) |

### 2.2 Maqueta
| Aspecto | Maqueta |
|---|---|
| Tema | Claro, paleta salvia/grafito (`--sage #748273`, `--graphite #303633`, fondo `#F5F6F3`) |
| Layout | Barra lateral fija 250 px (logo, “MENÚ PRINCIPAL”, “ADMINISTRACIÓN”, pie) + *topbar* con título, subtítulo, avatar con iniciales y “Cerrar sesión” |
| Tipografía | Inter 400/500/600/700 |
| Íconos | Lucide (vía script) |
| Componentes | Tarjetas blancas borde `#E2E5E0`, radio 12–14 px, sombra suave; tablas con cabecera `#F8F9F7` en mayúsculas; insignias de estado tipo píldora; pestañas subrayadas; formularios en tarjetas numeradas |
| CSS | `styles.css` de **11.138 líneas** con capas sucesivas de “ajustes” y “mejoras” que se sobrescriben; incluye reglas de funcionalidades inexistentes en el backend |

### 2.3 Comparación por pantalla

Leyenda: **Adoptar** = aplicar estilo/estructura visual. **Excluir** = es funcionalidad nueva o dato inexistente.

| Pantalla actual (Jinja) | Maqueta | Adoptar | Excluir |
|---|---|---|---|
| `base.html` | todas | Sidebar + topbar, avatar con iniciales de `current_user.nombre`, rol bajo el nombre, logo, títulos de grupo de menú, estilo de flash y migas | Ninguno de los ítems del menú cambia: se conservan los 7 actuales con sus condiciones de rol (incluido “Nueva solicitud”) |
| `auth/login.html` | `login.html` | Dos paneles: izquierdo con logo + ilustración sobre fondo salvia claro; derecho con formulario minimalista, botón salvia ancho completo, nota de seguridad | “Recordarme”, “¿Olvidaste tu contraseña?”. El toggle de contraseña **ya existe** (`login.js`): solo se re-estiliza |
| `dashboard.html` | `index.html` | Bloque de bienvenida, tarjetas de acceso con ícono en recuadro salvia, insignias con los contadores que **ya** entrega `resumen` (facturas por validar, correos por revisar), aviso “Flujo” como tarjeta informativa | Tarjetas con totales de solicitudes/usuarios/clientes/actividad, “Actividad reciente”, “Datos de demostración”, “Accesos rápidos” duplicados |
| `solicitudes/listado.html` | `solicitudes.html` | Encabezado con botón “Nueva solicitud”, panel de filtros en tarjeta con rejilla de 3 columnas, tabla con cabecera en mayúsculas, montos en negrita, insignias de estado por color, acciones como enlaces/botones discretos, paginación estilizada | Tarjetas-resumen con conteos por estado, columnas Concepto/Origen/Responsable, filtrado en vivo por JS, placeholder “RUT o cliente” (el filtro actual es solo RUT) |
| `solicitudes/nueva.html` | `nueva-solicitud.html` | Formulario en tarjetas con encabezados numerados (“1. Cliente”, “2. Datos de facturación”) agrupando los campos **existentes**, acciones Cancelar/Guardar al pie | Campos RUT/Razón social/Correo autocompletados al elegir cliente (`nueva-solicitud.js`), carga de documentos adjuntos |
| `solicitudes/detalle.html`, `factura.html`, `editar.html`, `_proceso.html` | `detalle-solicitud.html` | Tarjeta “Estado actual” con borde lateral de color y los pasos existentes; pestañas subrayadas (siguen siendo **enlaces** a las 3 rutas actuales); tarjetas con rejilla de 2 columnas etiqueta/valor; tablas de envíos y versiones; botones aprobar/devolver con estilos de la maqueta | Pestañas conmutadas por JS, “Restaurar datos”, chip de referencia “SOL-001” si no existe el dato, mensajes inline de JS |
| `clientes/listado.html` | `clientes.html` | Tarjeta de listado, avatar de iniciales por cliente, insignia activo/inactivo, acciones con ícono | Indicadores (tarjetas de totales), buscador y filtro de la maqueta, paginación si no existe hoy |
| `clientes/formulario.html` | `formulario-cliente.html` | Tarjeta de formulario en rejilla de 2 columnas, enlace “← Volver” estilizado **solo si ya existe**, botones Cancelar/Registrar | Notificación flotante por JS |
| `admin/usuarios.html` | `usuarios.html` | Layout de 2 columnas (crear usuario / usuarios registrados), avatar de iniciales, insignias de rol y estado, acciones discretas | Tarjetas de estadísticas, buscador y filtro de estado, sección “Perfiles y permisos”, botón “Ver auditoría”, toggle de contraseña (no existe aquí hoy) |
| `admin/usuario_editar.html` | `editar-usuario.html` | Tarjeta de formulario con encabezado e ícono, acciones al pie | Lo que no exista en la plantilla actual |
| `admin/correos.html` | `correos.html` | Botón “Revisar bandeja” (ya existe como `submit`), aviso IMAP como alerta ámbar suave, selector de estado estilizado, tabla dentro de tarjeta, insignias por estado de correo, botones Descargar .eml / Reprocesar / Descartar con los estilos de la maqueta | Tarjetas de estadísticas, buscador de texto, menú de categorías lateral, panel de lectura, modal de descarte (se mantiene el formulario actual con `motivo`) |
| `admin/auditoria.html` | `historial.html` | Tabla en tarjeta, cabecera en mayúsculas, “Ver detalle” estilizado (manteniendo el mecanismo actual) | Estadísticas, buscador, filtro por tipo, “Limpiar filtros”, detalle expandible por JS |
| `errores/error.html` | — | Tarjeta centrada con tokens del tema | — |

---

## 3. Decisiones técnicas

### 3.1 Bootstrap se mantiene
Las plantillas usan Bootstrap en ≈30 patrones (rejilla `row/col-*`, `form-control`, `form-select`, `table`, `alert`, `badge`) y su JS solo para `collapse` (menú móvil) y `alert` (cerrar flash). Reemplazarlo implicaría reescribir todo el marcado. Estrategia:
1. Quitar `data-bs-theme="dark"` (tema claro).
2. Re-tematizar Bootstrap sobrescribiendo sus variables CSS (`--bs-body-bg`, `--bs-body-color`, `--bs-border-color`, `--bs-primary-rgb`, etc.) y sus componentes (`.card`, `.btn-primary`, `.btn-outline-*`, `.form-control`, `.table`, `.badge`, `.alert`, `.nav-tabs`).
3. Agregar clases propias solo para lo que Bootstrap no cubre (sidebar, topbar, tarjetas de métrica, insignias de estado, cabeceras de sección).

Colisiones de nombres detectadas entre la maqueta y Bootstrap: `.nav-link`, `.form-group`, `.status`, `.logo`. **No** usar esos nombres en el CSS nuevo; usar prefijos (`.sidebar-link`, `.campo`, `.estado`, `.marca`).

### 3.2 CSS: no copiar `styles.css`
Motivos: 11.138 líneas, 58 bloques `@media`, reglas repetidas que se pisan (p. ej. `.detail-tab` definido dos veces con valores distintos, `.document-preview` duplicado), más de 40 tonos grises/verdes distintos y estilos para funcionalidades excluidas.

Se reemplaza el contenido de `app/static/css/app.css` (mismo nombre, no se toca el `<link>`) por un CSS consolidado (objetivo: < 900 líneas) con este orden:

```
1. @font-face (Inter local)
2. Tokens (:root)
3. Re-tema de Bootstrap (variables --bs-*)
4. Base (body, títulos, enlaces, foco)
5. Shell (sidebar, topbar, contenido, flash, migas)
6. Componentes (botones, tarjetas, formularios, tablas, insignias, alertas, pestañas, pasos, paginación, avatar)
7. Páginas (solo excepciones puntuales)
8. Responsive (2 puntos de quiebre: 992px y 576px)
```

`app/static/css/login.css` se reescribe con la estructura del login de la maqueta usando los tokens de `app.css`.

### 3.3 Tokens de diseño (extraídos de la maqueta y normalizados)

```css
:root {
    /* Superficies */
    --color-fondo: #F5F6F3;
    --color-superficie: #FFFFFF;
    --color-superficie-suave: #F8F9F7;   /* cabeceras de tabla, hover */
    --color-borde: #E2E5E0;

    /* Marca */
    --color-salvia: #748273;              /* botón primario, foco */
    --color-salvia-claro: #D9E1D5;        /* ítem activo, recuadro de íconos */
    --color-salvia-tenue: #EDF0EB;
    --color-verde-enlace: #287B5C;        /* enlaces y “Volver” */
    --color-grafito: #303633;             /* texto principal, hover primario */

    /* Texto */
    --color-texto: #303633;
    --color-texto-secundario: #858D83;
    --color-texto-tenue: #92998F;

    /* Estados (fondo / texto) */
    --estado-neutro-bg: #ECEEF0;   --estado-neutro-tx: #3E4650;   /* Pendiente, Descartado */
    --estado-info-bg: #E3ECFB;     --estado-info-tx: #1E4FA8;     /* En revisión, Recibido */
    --estado-aviso-bg: #FCEFD6;    --estado-aviso-tx: #8A5300;    /* En corrección, Requiere revisión */
    --estado-ok-bg: #DDF3E5;       --estado-ok-tx: #15633E;       /* Aprobada, Procesado, Activo */
    --estado-error-bg: #FCE8E6;    --estado-error-tx: #A94442;    /* Rechazada, Error, Inactivo */

    /* Forma */
    --radio-sm: 8px;
    --radio-md: 12px;
    --radio-lg: 14px;
    --sombra-tarjeta: 0 2px 8px rgba(48, 54, 51, 0.03);
    --sombra-hover: 0 6px 16px rgba(48, 54, 51, 0.07);
    --anillo-foco: 0 0 0 3px rgba(116, 130, 115, 0.12);

    /* Layout */
    --ancho-sidebar: 250px;
    --fuente: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
}
```

### 3.4 Tipografía
Google Fonts está bloqueado por la CSP (`font-src 'self' https://cdn.jsdelivr.net`). Se usa Inter **auto-alojada**:
- Ruta: `app/static/fonts/inter/Inter-{400,500,600,700}.woff2` (licencia SIL OFL; incluir `OFL.txt`).
- Los archivos los descarga la persona (Claude Code no debe descargar binarios). Si no están, el `font-family` cae a `system-ui` sin romper nada.

### 3.5 Íconos: Lucide → Bootstrap Icons
Lucide requiere script externo sin SRI e inicialización inline (ambos bloqueados por la CSP). Equivalencias:

| Lucide (maqueta) | Bootstrap Icons |
|---|---|
| layout-dashboard | `bi-grid-1x2` |
| file-text | `bi-file-earmark-text` |
| file-plus / plus | `bi-file-earmark-plus` / `bi-plus-lg` |
| building-2 | `bi-building` |
| inbox / mail | `bi-inbox` / `bi-envelope` |
| users / user | `bi-people` / `bi-person` |
| history | `bi-clock-history` |
| log-out | `bi-box-arrow-right` |
| arrow-left | `bi-arrow-left` |
| eye / eye-off | `bi-eye` / `bi-eye-slash` |
| pencil / edit | `bi-pencil` |
| download | `bi-download` |
| upload | `bi-upload` |
| send | `bi-send` |
| check-circle | `bi-check-circle` |
| rotate-ccw / refresh-cw | `bi-arrow-counterclockwise` / `bi-arrow-repeat` |
| trash / x-circle | `bi-trash` / `bi-x-circle` |
| shield-check | `bi-shield-check` |
| receipt | `bi-receipt` |
| info | `bi-info-circle` |
| lock | `bi-lock` |

Todos los íconos decorativos con `aria-hidden="true"`.

### 3.6 Imágenes
Copiar desde la maqueta:
- `assets/logo-facturaciones.png` → `app/static/img/logo-facturaciones.png`
- `assets/login-illustration-facturaciones.png` → `app/static/img/login-ilustracion.png`

`img-src 'self' data:` ya lo permite. Usar `alt` descriptivo en el logo y `alt=""` en la ilustración (decorativa).

### 3.7 Mapeo de estados a insignias
Crear `app/templates/_ui.html` con macros **solo de presentación** (sin lógica de negocio):

```jinja
{% macro estado_solicitud(nombre) -%}
{%- set clases = {
    'Pendiente': 'estado-neutro',
    'En revisión': 'estado-info',
    'En corrección': 'estado-aviso',
    'Aprobada': 'estado-ok',
    'Rechazada': 'estado-error',
} -%}
<span class="estado {{ clases.get(nombre, 'estado-neutro') }}">{{ nombre }}</span>
{%- endmacro %}

{% macro estado_correo(codigo, texto) -%}
{%- set clases = {
    'RECIBIDO': 'estado-info',
    'PROCESADO': 'estado-ok',
    'REQUIERE_REVISION': 'estado-aviso',
    'ERROR': 'estado-error',
    'DESCARTADO': 'estado-neutro',
} -%}
<span class="estado {{ clases.get(codigo, 'estado-neutro') }}">{{ texto or codigo }}</span>
{%- endmacro %}

{% macro iniciales(nombre) -%}
{{ (nombre or '?').split()[:2] | map('first') | join('') | upper }}
{%- endmacro %}
```

> Antes de usar `estado_correo`, Claude Code debe verificar en `admin/correos.html` y en `app/services/correo_entrante.py` los códigos reales de estado y el texto que hoy se muestra; ajustar el diccionario a esos valores sin cambiar el texto visible.

---

## 4. Fases de implementación

### Fase 0 — Preparación
**Archivos:** ninguno de la app.
1. Crear la rama de trabajo (no `main`).
2. Descomprimir la maqueta en `docs/diseno/referencia/FacturacionesSpA-Frontend/` (solo consulta; no se sirve).
3. Ejecutar `pytest` y registrar el resultado base.

**Criterio de aceptación:** `pytest` en verde; maqueta accesible para consulta.

---

### Fase 1 — Fundamentos visuales
**Archivos:** `app/static/css/app.css` (reescritura), `app/static/fonts/inter/*` (los aporta la persona), `app/static/img/*`.
1. Copiar las 2 imágenes (3.6).
2. Reescribir `app.css` con secciones 1–4 de 3.2: `@font-face`, tokens (3.3), re-tema de Bootstrap y base.
3. Re-tema de Bootstrap mínimo:
   - `--bs-body-bg`, `--bs-body-color`, `--bs-body-font-family`, `--bs-border-color`, `--bs-secondary-color`, `--bs-link-color(-rgb)`, `--bs-primary(-rgb)`.
   - `.btn-primary` (salvia → grafito en hover), `.btn-outline-primary`, `.btn-outline-secondary`, `.btn-outline-success`, `.btn-outline-danger`.
   - `.form-control`, `.form-select` (alto 44 px, radio 8 px, foco salvia con `--anillo-foco`).
   - `.card` (blanca, borde, radio 14 px, sombra suave), `.table` (cabecera `--color-superficie-suave`, 11 px mayúsculas, filas con hover).
   - `.badge.text-bg-*` → tonos de estado (3.3) para que las insignias existentes se vean bien aunque aún no se migren.
   - `.alert-*` → fondos suaves con borde del tono.

**Criterio de aceptación:** todas las páginas renderizan en tema claro sin errores de CSP en consola; `pytest` en verde.

---

### Fase 2 — Shell de la aplicación (`base.html`)
**Archivos:** `app/templates/base.html`, `app/static/css/app.css` (sección 5).
1. Quitar `data-bs-theme="dark"` de `<html>`.
2. Si `current_user.is_authenticated`, envolver el contenido en:
   ```
   .app-shell
     aside.sidebar#menu-principal (logo, grupos "MENÚ PRINCIPAL" / "ADMINISTRACIÓN", pie)
     div.app-main
       header.topbar (título, subtítulo, perfil, cerrar sesión)
       flash + migas
       {% block content %}
   ```
   Si no está autenticado (login, errores públicos), renderizar solo `{% block content %}` sin shell.
3. Menú lateral: reutilizar la macro `enlace_menu` cambiando solo clases/marcado (`.sidebar-link`, `.active`, `aria-current`). Agrupar:
   - **MENÚ PRINCIPAL:** Panel, Solicitudes, Nueva solicitud (Administrador/Emisor), Bandeja de correos, Clientes (Administrador).
   - **ADMINISTRACIÓN** (solo Administrador): Usuarios, Auditoría.
   - Mismos textos, endpoints, íconos equivalentes y condiciones de rol que hoy.
4. Topbar: nuevos bloques Jinja `{% block page_title %}` y `{% block page_subtitle %}` (vacíos por defecto). Perfil: avatar con `iniciales(current_user.nombre)`, nombre y rol (`current_user.role_name`). El formulario POST de logout se mantiene idéntico (solo cambian clases del botón; el texto “Cerrar sesión” se conserva).
5. Móvil (< 992 px): la sidebar se oculta y se muestra con el **mismo** `navbar-toggler` + `data-bs-toggle="collapse"` actual (`data-bs-target="#menu-principal"`). No se agrega JS.
6. Flash: mantener el marcado de `alert-dismissible`; re-estilizar `.flash-container` (esquina superior derecha, tarjeta blanca con borde izquierdo del tono).
7. Migas: mantener el bloque completo. El botón Volver conserva **exactamente** `class="btn btn-outline-secondary btn-sm"`; su aspecto se define con `.migas .btn-outline-secondary` en CSS.

**Criterio de aceptación:** `test_navegacion.py` en verde sin modificar; menú idéntico en ítems por rol; logout funciona; menú móvil abre/cierra.

---

### Fase 3 — Componentes compartidos
**Archivos:** `app/templates/_ui.html` (nuevo, solo macros visuales), `app/templates/solicitudes/_proceso.html`, `app/static/css/app.css` (sección 6).
1. Crear `_ui.html` (3.7).
2. `_proceso.html`:
   - Pasos (`ol.pasos-proceso`) dentro de una tarjeta “Estado actual” con borde izquierdo del color del estado vigente. Conservar `aria-label="Etapa del proceso"` y `aria-current="step"` exactamente en el `<span>` actual (el test busca `aria-current="step">En corrección`, sin espacios entre `>` y el texto).
   - Pestañas: `ul.nav.nav-tabs` → estilo subrayado de la maqueta (`border-bottom: 3px`, activo en verde). Siguen siendo `<a>` a las rutas actuales; se mantiene el filtro `if clave != 'editar' or editable`.
3. CSS de componentes: `.estado` + variantes, `.avatar`, `.tarjeta-seccion` (encabezado con título + subtítulo + acción opcional), `.dato` (etiqueta 11 px tenue / valor 13 px), `.rejilla-datos` (2 columnas → 1 en móvil), `.acciones-formulario` (borde superior, alineado a la derecha), paginación.

**Criterio de aceptación:** `pytest` en verde; pestaña “Editar” sigue oculta cuando no es editable.

---

### Fase 4 — Login
**Archivos:** `app/templates/auth/login.html`, `app/static/css/login.css`.
1. Panel izquierdo: fondo degradado salvia claro (`#EEF2EC → #E3EADF`), logo arriba, ilustración centrada (`login-ilustracion.png`), formas decorativas solo con CSS (`::before/::after`).
2. Panel derecho: título “Iniciar sesión”, subtítulo, campos con etiquetas en negrita, botón salvia de ancho completo, nota de seguridad existente con ícono `bi-lock`.
3. Conservar: `form.needs-validation`, ids `email`, `password`, `togglePassword`, `passwordIcon`, `invalid-feedback`, `csrf_token`, `input-group`.
4. Eliminar del marcado actual solo elementos decorativos que no existan en la maqueta (p. ej. “Conforme SII · Chile · 2026”, `bi-star`) si se decide replicar fielmente; **no** agregar “Recordarme” ni “¿Olvidaste tu contraseña?”.
5. Responsive: < 992 px ocultar panel izquierdo.

**Criterio de aceptación:** login funcional, validación del navegador y toggle de contraseña operativos.

---

### Fase 5 — Panel principal
**Archivos:** `app/templates/dashboard.html`.
1. `page_title` = “Panel principal”; `page_subtitle` = “Bienvenido/a, {{ current_user.nombre }}.”
2. Mantener las mismas tarjetas, textos, condiciones de rol y enlaces. Estilo de tarjeta de la maqueta: ícono en recuadro salvia 42 px, título, descripción, enlace/botón al pie.
3. Insignias existentes (`por_validar.total`, `resumen.correos_por_revisar`) como número destacado dentro de su tarjeta (mismo dato, misma condición).
4. Alerta “Flujo” → tarjeta informativa con ícono `bi-info-circle`.

**Excluir:** contadores no provistos por `resumen_panel()`, actividad reciente, accesos rápidos duplicados.

**Criterio de aceptación:** `test_menu_del_administrador` y `test_menu_del_emisor_no_muestra_administracion` en verde; el panel no contiene “Volver”.

---

### Fase 6 — Solicitudes
**Archivos:** `solicitudes/listado.html`, `nueva.html`, `editar.html`, `detalle.html`, `factura.html`.

**6.1 Listado**
- Encabezado de sección: “Solicitudes de facturación”, texto de resultados actual, botón “Nueva solicitud” salvia.
- Filtros en tarjeta “Filtros de búsqueda”, rejilla 3 columnas con los **mismos 6 campos** (Responsable solo si `es_admin`); botones “Aplicar filtros” (primario) y “Limpiar” (secundario).
- Tabla: mismas 6 columnas; RUT en tono secundario, cliente en negrita, monto en negrita con el formato actual, estado con `estado_solicitud()`; acciones Ver / Factura / Editar (misma condición) como botones pequeños delineados.
- Paginación: mismos enlaces y texto.

**6.2 Nueva / Editar**
- Agrupar campos existentes en tarjetas: “1. Cliente” (`cliente_id`) y “2. Datos de facturación” (resto). En Editar, la tarjeta “Receptor histórico” se mantiene como datos de solo lectura con `.rejilla-datos`.
- Acciones al pie: Cancelar (secundario) + Guardar (primario), con los textos y destinos actuales.
- Errores: alerta `alert-danger` re-estilizada (sin mensajes inline por JS).

**6.3 Detalle / Factura**
- Encabezado: “Solicitud …” (texto actual) + insignia de estado.
- `navegacion_proceso` (Fase 3) arriba.
- Cada `<h2>` actual pasa a ser el título de una `.tarjeta-seccion`; pares etiqueta/valor con `.rejilla-datos`.
- Documento XML: estado vacío con borde punteado (`.document-preview` de la maqueta) cuando no hay XML; formulario de carga existente estilizado.
- Envío por correo: botón primario existente; tabla de envíos con insignias Enviado/Fallido/En proceso (`estado-ok` / `estado-error` / `estado-info`).
- Validación (Factura): botones existentes con estilo “Aprobar” (salvia) y “Devolver a corrección” (delineado ámbar); textarea `observacion` estilizado.
- Historial de versiones: cada `<article>` como tarjeta interna; tabla de cambios estilo maqueta.
- Gestión del estado y Motivo del rechazo (Detalle): misma lógica, estilos de formulario.

**Criterio de aceptación:** `test_rutas.py`, `test_rutas_factura.py`, `test_navegacion.py` en verde; todos los formularios envían los mismos campos.

---

### Fase 7 — Clientes
**Archivos:** `clientes/listado.html`, `clientes/formulario.html`.
- Listado: encabezado “Gestión de clientes” + botón existente; tabla en tarjeta; columna Razón social con avatar de iniciales; Estado con `estado-ok` (Activo) / `estado-error` o `estado-neutro` (Inactivo); acciones existentes con ícono + texto accesible.
- Formulario: tarjeta “Información del cliente”, rejilla 2 columnas con los 5 campos actuales; `rut` de solo lectura al editar (lógica actual); acciones Cancelar/Guardar.

**Criterio de aceptación:** alta y edición de cliente funcionan igual; `pytest` en verde.

---

### Fase 8 — Administración
**Archivos:** `admin/usuarios.html`, `admin/usuario_editar.html`, `admin/correos.html`, `admin/auditoria.html`.
- **Usuarios:** rejilla 2 columnas en ≥ 1200 px (“Crear usuario” 1/3, “Usuarios registrados” 2/3); avatar + nombre, correo secundario, insignia de rol (Administrador lila suave `#EAE8F2/#77708E`, Emisor salvia, otros neutro), insignia de estado; acciones de activar/desactivar con los formularios y `data-confirmar` actuales.
- **Editar usuario:** tarjeta de formulario con encabezado e ícono `bi-person`, aviso de cuenta propia como alerta suave.
- **Bandeja de correos:** botón “Revisar bandeja” (formulario actual) arriba a la derecha; aviso IMAP como alerta ámbar; filtro de estado (select + botón “Filtrar” actuales) en barra de herramientas; tabla en tarjeta con remitente en negrita y asunto debajo, insignia `estado_correo()`, motivos/alertas como lista tenue, `<details>` de datos extraídos estilizado; acciones Descargar .eml (delineado), Reprocesar (salvia), Descartar (delineado rojo) conservando el formulario con `motivo`.
- **Auditoría:** tabla en tarjeta con cabecera en mayúsculas; acción como texto en negrita; “Ver detalle” con el mecanismo actual estilizado.

**Criterio de aceptación:** `test_rutas_correo.py`, `test_seguridad.py` y resto en verde; acciones POST intactas.

---

### Fase 9 — Error, responsive y QA visual
**Archivos:** `errores/error.html`, `app.css` (sección 8).
1. Página de error: tarjeta centrada, código grande en salvia, mensaje y enlace actual.
2. Responsive:
   - < 992 px: sidebar colapsable, topbar en columna, rejillas a 1–2 columnas.
   - < 576 px: tablas con `table-responsive` (ya presente) y `min-width` para no comprimir columnas; acciones en columna.
   - Corregir el desborde horizontal visible en la maqueta de Solicitudes (tabla y botón “Nueva” se salen del contenedor a 1440 px).
3. Accesibilidad: contraste mínimo AA en texto secundario sobre blanco (`#858D83` sobre `#FFF` ≈ 3,5:1 → usar `--color-texto-secundario` solo en texto ≥ 14 px o subirlo a `#6B7369` en texto pequeño); foco visible en todos los controles.

**Criterio de aceptación:** checklist de la sección 5 completo.

---

## 5. Verificación final

### 5.1 Automática
```bash
pytest
# No debe haber coincidencias:
grep -rnE 'style="|onclick=|<script>|unpkg\.com|fonts\.googleapis|data-lucide' app/templates
grep -n 'data-bs-theme="dark"' app/templates/base.html
```

### 5.2 Manual (por rol: Administrador y Emisor)
- [ ] Sin errores de CSP en la consola del navegador en ninguna página.
- [ ] Menú lateral con los mismos ítems por rol que antes; ítem activo correcto.
- [ ] Login, logout, crear/editar solicitud, cargar XML, enviar correo, enviar a revisión, aprobar/devolver, generar DTE, crear/editar cliente, crear/editar/desactivar usuario, revisar bandeja, reprocesar/descartar correo y filtros funcionan igual.
- [ ] Mensajes flash visibles y descartables.
- [ ] Migas y botón Volver presentes donde estaban.
- [ ] Vista a 1440, 1024, 768 y 390 px sin desbordes.
- [ ] Inter cargada (o caída limpia a `system-ui` si no se agregaron los archivos).

---

## 6. Commits sugeridos

| Fase | Commit |
|---|---|
| 1 | `style(ui): agregar tokens, tipografía Inter local y re-tema claro de Bootstrap` |
| 2 | `style(ui): reemplazar barra superior por sidebar y topbar en base.html` |
| 3 | `style(ui): agregar macros visuales de estado y re-estilizar navegación de proceso` |
| 4 | `style(auth): aplicar diseño de login de dos paneles` |
| 5 | `style(dashboard): aplicar diseño de tarjetas al panel principal` |
| 6 | `style(solicitudes): aplicar diseño a listado, formularios, detalle y factura` |
| 7 | `style(clientes): aplicar diseño a listado y formulario de clientes` |
| 8 | `style(admin): aplicar diseño a usuarios, bandeja de correos y auditoría` |
| 9 | `style(ui): ajustar página de error, responsive y contraste` |

---

## 7. Prompt sugerido para Claude Code (repetir por fase)

```
Lee docs/diseno/PLAN_IMPLEMENTACION_DISENO.md completo, en especial la sección 1 (reglas).
Ejecuta solo la Fase N.
Consulta la maqueta en docs/diseno/referencia/FacturacionesSpA-Frontend/ únicamente como
referencia visual; no copies su CSS completo ni su JavaScript.
Antes de editar, muestra qué archivos vas a tocar.
Al terminar: ejecuta pytest, ejecuta los grep de la sección 5.1, resume los cambios,
indica qué no pudiste verificar visualmente y propone el commit de la sección 6.
No modifiques rutas, servicios, modelos, la CSP ni los tests.
```

---

## 8. Riesgos y supuestos

| Riesgo / supuesto | Mitigación |
|---|---|
| Códigos de estado de correo distintos a los supuestos en 3.7 | Verificar en `correo_entrante.py` antes de la Fase 8 |
| Plantillas con contenido no revisado en detalle (textos exactos de `detalle.html`, `factura.html`, `correos.html`) | Claude Code debe leer cada plantilla completa antes de editarla y limitarse a clases/envoltorios |
| Tests que comparan marcado exacto | Mantener las cadenas listadas en 1.2; si un test falla, revertir el marcado, no el test |
| Archivos Inter no disponibles | Fallback a `system-ui` ya previsto |
| La maqueta tiene inconsistencias internas (dos tonos de verde para activo: `#D9E1D5` y `#E8EFE8`; dos estilos de pestaña) | Este plan fija un único valor por token (3.3) |
