# Plan de implementación de seguridad – Capstone Facturación

> **Destinatario:** Claude Code, ejecutándose en la raíz del repositorio
> `Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas`.
> **Contexto:** proyecto de título (Capstone). La plataforma se desarrolla para **Facturaciones SpA**,
> **cliente ficticio** del proyecto; el diseño y el desarrollo funcional continúan tal como van.
> El repositorio es **público en GitHub** y lo revisan los **evaluadores**, que deben poder
> ejecutarlo localmente con **su propio `.env`**, sin cuentas reales y sin correr riesgos.
> Terminada la entrega, el proyecto se convertirá en una **estructura base reutilizable** (fase FT).
> **Objetivo:** cerrar todas las brechas de la *Matriz de cumplimiento de seguridad*
> (ISO/IEC 27001/27002, OWASP Top 10, API Security Top 10, ASVS L2, NIST SP 800-63B,
> Ley 21.719, Ley 21.459, RBAC y auditoría, SPF/DKIM/DMARC) y **demostrar** el cumplimiento
> con pruebas automatizadas y un comando de verificación.
> **Fecha del plan:** 11-11-2026 · **Versión:** 6 (**cliente ficticio Facturaciones SpA, evaluadores y estructura base**).
> **Modelo de despliegue:** cada persona instala una **instancia local independiente** en su
> propio equipo (BD MariaDB propia, secretos propios, correo propio u opcional). La aplicación y la
> base de datos escuchan solo en `127.0.0.1`; nada queda expuesto a la red. Sin servidor central.
>
> **Tres perfiles de uso (D25)**
>
> | Perfil (`APP_ENTORNO`) | Quién | Datos | Correo |
> |---|---|---|---|
> | `desarrollo` | Equipo del proyecto | Pruebas locales | Mailpit/GreenMail local |
> | `evaluacion` | Evaluadores del Capstone | **Demo ficticia de Facturaciones SpA** | **Solo sandbox local** (no puede enviar a Internet) |
> | `operacion` | Personal (ficticio) de Facturaciones SpA, una instancia por persona | Reales del cliente | Buzón IMAP y credencial SMTP propios, con TLS |
>
> **Principios rectores**
> 1. **Seguro por defecto:** sin contraseñas por defecto, sin secretos en el repositorio, sin datos reales, sin puertos expuestos, correo desactivado hasta configurarlo.
> 2. **Falla cerrada:** si la configuración es insegura para su perfil, la aplicación **no arranca** y explica cómo corregirlo.
> 3. **Seguro aunque se omitan pasos opcionales:** el endurecimiento del sistema operativo suma capas, pero la plataforma no depende de él para no exponer datos.
> 4. **Verificable por cualquiera:** versiones firmadas con suma de verificación y procedencia, dependencias con hashes, y un comando que informa el estado de seguridad del equipo.
> 5. **Repositorio confiable:** historial sin secretos ni datos personales, análisis automáticos en GitHub y canal privado para reportar vulnerabilidades.
> 6. **Ficción segura:** todo lo ficticio (empresa, clientes, correos, RUT) usa dominios reservados `.example` y marcas visibles; nada apunta a personas o dominios reales.

---

## 0. Cómo ejecutar este plan

1. Lea el plan completo antes de editar. Luego lea `CLAUDE.md` (si existe), `README.md`,
   `docs/flujo_correo_factura.md`, `config.py`, `app/__init__.py`, `app/security.py`,
   `app/models.py`, `app/services/usuarios.py` y `test/conftest.py`.
2. Ejecute las fases **en orden** (F0, **FR**, F1 → F12, **FL**, **FE**, **FI**, F13). FR va primero porque revisa que el historial del repositorio no contenga secretos ni datos antes de seguir agregando código. **FT** (estructura base) se ejecuta **solo después de la entrega final** y en otro repositorio (D28). Cada fase termina con:
   - `pytest` completo en verde (desde la carpeta de la aplicación),
   - un commit con el mensaje convencional indicado,
   - una línea en `docs/seguridad/BITACORA_IMPLEMENTACION.md` con: fase, archivos, pruebas nuevas, resultado.
3. Si una fase falla y no puede resolverse en 3 intentos, **deténgase**, documente el bloqueo en la bitácora
   y pregunte al usuario. No desactive pruebas ni controles para "pasar".
4. Al final ejecute la **Fase F13 (verificación integral)**; el trabajo solo está terminado cuando
   `flask --app run seguridad-verificar` termina con código 0 y la matriz
   `docs/seguridad/MATRIZ_CUMPLIMIENTO.md` no tiene filas en ❌.

### Rutas de referencia

| Alias | Ruta |
|---|---|
| `RAIZ` | raíz del repositorio (contiene `.gitignore`, `README.md`) |
| `APP_DIR` | `RAIZ/Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/` (contiene `config.py`, `run.py`, `app/`, `test/`, `migrations/`) |

Todas las rutas de este plan son relativas a `APP_DIR` salvo que digan `RAIZ/`.

---

## 1. Decisiones de diseño (revisar antes de ejecutar)

El equipo puede cambiar estos valores **antes** de entregar el plan. Claude Code los aplica tal como estén.

| # | Decisión | Valor adoptado | Alternativa |
|---|---|---|---|
| D1 | Permisos del rol **Lector** | Solo lectura de listado, detalle y factura de **todas** las solicitudes; sin acciones ni descargas. | Sin acceso a datos (solo panel) y corregir su descripción en `roles`. |
| D2 | **Segregación de funciones** | `SEGREGACION_FUNCIONES=auto`: se exige automáticamente cuando la instancia tiene **≥ 2 Administradores activos** (quien creó la solicitud o generó la versión vigente no puede aprobarla). Con un solo Administrador, control compensatorio: **reautenticación reforzada** (contraseña + TOTP) para aprobar/observar facturas y descargar el archivo SII, y exportación sellada de auditoría disponible para revisión por un tercero. | `1` (siempre) o `0` (nunca; desaconsejado). |
| D3 | **MFA** | TOTP (RFC 6238) obligatorio para `Administrador`; implementado con biblioteca estándar; secreto cifrado con Fernet (`cryptography`). 10 códigos de recuperación de un solo uso. | Extender a todos los roles con `MFA_ROLES_OBLIGATORIOS`. |
| D4 | **Contraseñas** | Mínimo 15, máximo 128, sin reglas de composición, lista local de contraseñas comunes/comprometidas, no puede contener el correo ni el nombre. | Mínimo 12 si se exige MFA a todos. |
| D5 | **Inactividad / sesión máxima** | 30 min de inactividad y 12 h máximo absoluto. | 60 min / 12 h. |
| D6 | **Zona horaria** | BD en UTC (`SET time_zone = '+00:00'` por conexión); se muestra en `America/Santiago` (configurable). Los registros anteriores no se convierten: se documenta la fecha de corte. | Convertir históricos con una migración. |
| D7 | **Retención** | `.eml` procesados o descartados: 365 días; intentos de login: 90 días; auditoría, facturas, XML y archivos SII: no se eliminan desde la app (obligación tributaria y evidencia; mínimo 6 años). Configurable. | Ajustar con el docente. |
| D8 | **Cifrado en reposo** | **Fuertemente recomendado** (BitLocker/FileVault/LUKS). La app no puede imponerlo en equipos ajenos: `seguridad-verificar` lo informa como **ADVERTENCIA** visible y la guía explica cómo activarlo. | Cifrado de `.eml`/XML con Fernet (fuera de este plan). |
| D9 | **Correo entrante sin autenticación verificable** | Va a revisión manual cuando `IMAP_EXIGIR_AUTENTICACION=1` (por defecto `1`). | `0` solo en desarrollo. |
| D10 | **Correo en eventos `LOGIN_FALLIDO`** | Se guarda el correo intentado (≤150 caracteres) como evidencia; cubierto por la retención. | Guardar solo su SHA-256. |
| D11 | **Modelo de operación** | **Instancia local independiente por persona y equipo.** La app y MariaDB escuchan solo en `127.0.0.1`; HTTP por *loopback* (el tráfico no sale del equipo). Ninguna opción del proyecto permite exponerla a la red. | Acceso por red: fuera de alcance (requeriría HTTPS y otro plan). |
| D12 | **Servidor de aplicación** | `waitress` (multiplataforma); el servidor de desarrollo de Flask solo en `desarrollo`. | — |
| D13 | **Ejecución** | Manual con `iniciar` (`scripts/iniciar.ps1` o `python scripts/iniciar.py`) usando la cuenta **estándar** de la persona. Inicio automático al iniciar sesión: **opcional** (script de Windows). La app se niega a correr como administrador/root. | Inicio automático por defecto. |
| D14 | **Base de datos** | MariaDB local (XAMPP o instalación independiente) en `127.0.0.1`, `root` con contraseña. La app **verifica** al arrancar que `root` no acepta contraseña vacía y que MariaDB no escucha en otras interfaces; si falla, no arranca fuera de `desarrollo`. | Docker Compose con MariaDB publicado solo en `127.0.0.1` (opcional, documentado). |
| D15 | **Identidad de instalación** | `INSTALACION_ID` aleatorio (`INST-` + 8 hex) generado por el instalador, guardado en `.env` y en la tabla `instalacion`. La app no arranca si no coinciden (detecta `.env` o BD copiados). Se incluye en exportaciones, respaldos, archivos SII y cabecera `X-Facturacion-Instalacion`. | — |
| D16 | **Instalación guiada multiplataforma** | `scripts/instalar.py` (solo biblioteca estándar de Python) instala de forma segura en Windows, macOS y Linux. Endurecimiento del sistema operativo: scripts **opcionales** en `scripts/windows/` (simulación por defecto). | Instalación manual según §6. |
| D17 | **Correo** | **Desactivado por defecto** (`CORREO_SALIENTE_HABILITADO=0`, `CORREO_ENTRANTE_HABILITADO=0`). En `evaluacion` solo se permite el **sandbox local** (Mailpit/GreenMail en `127.0.0.1`), para que los evaluadores prueben el flujo completo sin cuentas reales ni envíos a Internet. En `operacion`, cada persona de Facturaciones SpA usa **su propio buzón IMAP y su propia credencial SMTP**, solo con TLS; SPF/DKIM/DMARC del dominio del cliente se configuran una vez y `flask correo-dns` lo verifica. | — |
| D18 | **Distribución** | Instalar solo **versiones publicadas** (GitHub Releases `vX.Y.Z`) con etiqueta firmada, `SHA256SUMS`, SBOM y atestación de procedencia; dependencias con `--require-hashes`. El instalador verifica que el código está en una etiqueta publicada y sin modificaciones locales. | Instalar desde `main` (solo desarrollo, con advertencia). |
| D19 | **Repositorio público** | Sin secretos, datos reales, volcados de BD, correos `.eml`, XML de clientes ni nombres de personas en archivos **ni en el historial**. Escaneo de secretos en cada push. En un repositorio público **todas las ramas publicadas son visibles**: el desarrollo diario se hace en un **repositorio privado** (o ramas solo locales) y al público se suben solo `main` y etiquetas de versión. | Mantener ramas de trabajo públicas (desaconsejado). |
| D20 | **Folios DTE** | El folio es provisional y se repite entre instalaciones. Los archivos SII llevan `INSTALACION_ID` y una advertencia; no deben usarse ante el SII. Con CAF real, cada instalación necesitará su rango propio (registrado en `instalacion`). | — |
| D21 | **Datos personales** | En el escenario del proyecto, **Facturaciones SpA** es la responsable del tratamiento de los datos de sus clientes en todas sus instancias; el aviso de privacidad y el registro de tratamientos se redactan a su nombre (ficticio). En `evaluacion` solo hay datos ficticios. Para reutilizaciones futuras (FT), quien instale será responsable de los datos que cargue. El repositorio no contiene datos personales reales. | — |
| D22 | **Modo demostración** | Base del perfil `evaluacion`. `flask demo-cargar` carga un escenario **ficticio de Facturaciones SpA** (clientes, solicitudes en distintos estados, facturas con versiones, correos de ejemplo; dominios `.example`, RUT ficticios marcados como tales) y usuarios de demo con contraseñas aleatorias mostradas **una sola vez** en consola. Muestra una franja "MODO DEMOSTRACIÓN"; el correo queda bloqueado. `flask demo-borrar` los elimina. | Sin modo demo. |
| D23 | **Recursos externos** | Bootstrap y Bootstrap Icons se incluyen **localmente** en `app/static/vendor/` (verificados con los mismos hashes SRI actuales); la CSP queda en `'self'`. La app no contacta Internet salvo SMTP/IMAP configurados. Sin telemetría. | CDN con SRI (actual). |
| D24 | **Licencia** | Durante la evaluación: según las reglas de la institución (`[COMPLETAR]`). Para la estructura base (FT): licencia abierta (p. ej. MIT o Apache-2.0) si la institución lo permite. | — |
| D25 | **Perfiles** | `APP_ENTORNO` = `desarrollo` \| `evaluacion` \| `operacion`, con reglas de arranque distintas (F1). Los tres comparten todos los controles de la aplicación (autenticación, MFA, RBAC, auditoría, cabeceras, *loopback*). | — |
| D26 | **Identidad ficticia del cliente** | Se conserva el nombre **Facturaciones SpA** en la interfaz. Todo correo, dominio y RUT del cliente y de sus clientes usa valores **ficticios y reservados**: dominio `facturaciones-spa.example` (RFC 2606) en lugar de `facturaciones.cl` (dominio que podría pertenecer a un tercero real), RUT de empresa ficticio documentado como tal y franja "Cliente ficticio – proyecto académico" en `evaluacion`. | Mantener `facturaciones.cl` (desaconsejado: riesgo de enviar o suplantar a un dominio real). |
| D27 | **Operación de Facturaciones SpA** | Varias personas del cliente, **una instancia local por persona** con BD y buzón propios; un **Responsable de Seguridad** del cliente gobierna altas, bajas, versiones aprobadas y revisión de auditorías, con registros **fuera del repositorio** (`GUIA_OPERACION_FACTURACIONES_SPA.md`). | — |
| D28 | **Entrega y estructura base** | La versión evaluada se congela con la etiqueta `v1.0.0-entrega` (rama y etiqueta protegidas). La estructura base se crea **después**, en un **repositorio nuevo** generado desde esa etiqueta (FT), para no alterar lo que revisan los evaluadores. | Convertir el mismo repositorio (desaconsejado durante la evaluación). |

---

## 2. Reglas de trabajo para Claude Code

- **Rama:** trabaje en la rama de desarrollo actual (no `main`). No haga `push` ni abra PR salvo que el autor lo pida.
- **Secretos:** nunca lea, imprima ni modifique `APP_DIR/.env` ni `RAIZ/.env.local`. Toda variable nueva se documenta en `.env.example` y en `config.py` con valor por defecto seguro.
- **Base de datos:** antes de aplicar cualquier migración ejecute un respaldo (F0). Aplique migraciones primero en `facturaciones_spa_mvp_test` y luego en `facturaciones_spa_mvp`. No borre datos.
- **Dependencias:** solo se agregan `cryptography`, `tzdata`, `waitress` (runtime) y `pip-audit`, `bandit`, `pip-tools` (desarrollo), con versión fijada; `requirements.txt` se genera con hashes (FI).
- **Repositorio público:** no agregar nombres de personas reales, correos reales (usar `@example.com`), RUT reales, volcados de BD, `.eml`, XML de clientes, informes de cumplimiento ni `INSTALACION_ID` de equipos reales. Las pruebas y la documentación usan datos ficticios.
- **Git:** no hacer `push`, no reescribir historial ni cambiar la configuración de GitHub. Si FR encuentra secretos en el historial, **detenerse** y pedir instrucciones al autor.
- **Sistema operativo:** Claude Code **no** ejecuta comandos que cambien la configuración de Windows, el firewall, BitLocker, cuentas de usuario ni `my.ini`/`config.inc.php` de XAMPP. Para eso genera scripts con modo de simulación por defecto (`-Aplicar` explícito) y documentación; los ejecuta el equipo como administrador (§6).
- **Estilo:** respete el estilo existente: español en nombres, `pymysql` con `%s`, servicios en `app/services/`, auditoría con `registrar_evento`, errores de dominio con excepciones propias, plantillas sin JavaScript ni estilos en línea (lo exige `test_plantillas_sin_javascript_ni_estilos_en_linea`).
- **Pruebas:** siga el patrón de `test/conftest.py` (`login_como`, `monkeypatch` sobre `User` y servicios). Toda medida nueva lleva al menos una prueba positiva y una negativa.
- **Compatibilidad:** XAMPP (MariaDB 10.11) en Windows; los scripts de sistema se escriben en PowerShell.
- **Commits:** un commit por fase con el mensaje indicado y el trailer de co-autoría habitual.

---

## 3. Fases

### F0 – Preparación y línea base

**Pasos**
1. Confirmar rama actual (`git status`, `git branch --show-current`).
2. Respaldo de BD con `C:\xampp\mysql\bin\mysqldump.exe` a `RAIZ/respaldos/AAAAMMDD_HHMM_pre_seguridad.sql` (crear carpeta; agregar `respaldos/` al `.gitignore`).
3. `pip install -r requirements-dev.txt` y ejecutar `pytest`. Registrar en la bitácora el número de pruebas y su resultado.
4. Agregar dependencias con versión fijada (última estable compatible al momento de ejecutar):
   - `requirements.txt`: `cryptography==<x.y.z>`, `tzdata==<aaaa.n>`, `waitress==<x.y.z>`.
   - `requirements-dev.txt`: `pip-audit==<x.y.z>`, `bandit==<x.y.z>`, `pip-tools==<x.y.z>`, `cyclonedx-bom==<x.y.z>` (SBOM).
5. Crear `docs/seguridad/BITACORA_IMPLEMENTACION.md`.

**Aceptación:** pruebas en verde (o fallas preexistentes documentadas), respaldo creado.
**Commit:** `chore(seguridad): línea base, respaldo y dependencias de seguridad`

---

### FR – Repositorio público y cadena de suministro

**Cierra:** A06, A08, 27002 5.23 (servicios en la nube), 8.4 (acceso al código fuente), 8.8, 8.25–8.29, 8.32; ASVS V10/V14; confianza de quien descarga el proyecto.

#### FR.1 Auditoría del contenido y del historial

1. `git ls-files` y revisar que no estén versionados: `.env*` (salvo `.env.example`), `*.eml`, `*.xml` de clientes, volcados `*.sql` con datos, `Registros_*`, `respaldos/`, `logs/`, `informes/`, certificados (`*.pfx`, `*.p12`, `*.pem`, `*.key`). Revisar `.vscode/settings.json` (no debe tener rutas personales ni credenciales).
2. Escanear **todo el historial y todas las ramas** con `gitleaks detect --source . --log-opts="--all"` (binario oficial, verificar su SHA-256) y buscar además: contraseñas, `SECRET_KEY`, tokens SMTP/IMAP, hashes `scrypt:`, RUT y correos reales (`git log --all -p | grep -E` con patrones de RUT y de correo, excluyendo `example.com`).
3. Resultado en `docs/seguridad/BITACORA_IMPLEMENTACION.md` (sin reproducir los secretos: solo archivo, commit y tipo).
4. **Si hay hallazgos:** detenerse y presentar al autor: (a) qué secreto rotar **primero** (un secreto publicado se considera comprometido aunque se borre); (b) opción de reescritura con `git filter-repo` + `push --force` y aviso a quienes clonaron. La reescritura la decide y ejecuta el autor.

#### FR.2 Archivos de gobierno del repositorio (raíz)

| Archivo | Contenido |
|---|---|
| `SECURITY.md` | Versiones soportadas; cómo reportar vulnerabilidades **en privado** (GitHub *Private vulnerability reporting*); qué incluir; plazos de respuesta orientativos; alcance (instalación local, no hosting); agradecimientos. |
| `README.md` | Sección "Instalación segura en 5 pasos" (descargar versión publicada → verificar → `instalar.py` → primer ingreso con MFA → `seguridad-verificar`), advertencias claras (solo uso local, no exponer a Internet, no cargar datos reales sin leer `PRIVACIDAD`), enlace a `SECURITY.md` y a la guía. |
| `LICENSE` | Según D24. |
| `CONTRIBUTING.md` | Reglas: sin secretos ni datos reales, pruebas obligatorias, `pre-commit` instalado, cambios de seguridad revisados. |
| `.github/ISSUE_TEMPLATE/*.yml` | Formularios que advierten no publicar contraseñas, `.env`, correos ni datos de clientes, y derivan vulnerabilidades a `SECURITY.md`. |
| `.github/pull_request_template.md` | Lista de verificación de seguridad (pruebas, sin secretos, migraciones re-ejecutables, documentación). |
| `.github/CODEOWNERS` | El autor como revisor obligatorio de `app/security.py`, `app/permisos.py`, `app/auth/`, `migrations/`, `scripts/`, `.github/`. |
| `.gitattributes` | Fin de línea consistente (`*.ps1 text eol=crlf`, `*.sh text eol=lf`, `*.py text eol=lf`). |
| `.pre-commit-config.yaml` | Ganchos: `gitleaks`, `bandit`, detección de claves privadas y archivos grandes, verificación de que `.env` no se agregue. Versiones fijadas por *commit*. |

#### FR.3 Integración continua endurecida (`.github/workflows/`)

Reglas para **todos** los workflows: `permissions: contents: read` a nivel de archivo (ampliar solo por trabajo cuando sea necesario); acciones fijadas por **SHA completo de commit** con comentario de versión; `actions/checkout` con `persist-credentials: false`; nunca `pull_request_target` con código del PR; sin secretos en trabajos que ejecutan código de terceros.

| Workflow | Disparador | Contenido |
|---|---|---|
| `seguridad.yml` | `push`, `pull_request` | Python fijado; `pip install --require-hashes -r requirements-dev.txt`; `pip-audit`; `bandit -r app -ll`; `gitleaks`; `pytest`. MariaDB `10.11` como servicio **solo si** alguna prueba lo requiere, cargando `000_esquema_base.sql` + migraciones. |
| `codeql.yml` | `push` a `main`, PR, semanal | CodeQL para Python (gratuito en repositorios públicos), o activar el *default setup* de GitHub. |
| `scorecard.yml` | semanal, `push` a `main` | OpenSSF Scorecard; publica resultados en *Security → Code scanning*. |
| `release.yml` | `push` de etiqueta `v*` | Genera el `.zip` de la fuente, `SHA256SUMS`, SBOM CycloneDX de `requirements.txt`, atestación de procedencia (`actions/attest-build-provenance`, con `id-token: write` y `attestations: write` solo en ese trabajo) y crea la *GitHub Release*. |

`.github/dependabot.yml`: `pip` (carpeta de la app) y `github-actions`, semanal, con agrupación de actualizaciones menores.

#### FR.4 Dependencias reproducibles

- Mover dependencias directas a `requirements.in` y `requirements-dev.in`; generar `requirements.txt` y `requirements-dev.txt` con `pip-compile --generate-hashes`. Instalación siempre con `--require-hashes`.
- Fijar versión de Python soportada en `.python-version` y en el README; `instalar.py` la valida.
- `pip-audit` sin vulnerabilidades sin excepción documentada en `docs/seguridad/EXCEPCIONES.md` (riesgo, mitigación, fecha de revisión).
- Prueba `test_dependencias_fijadas` (cada paquete con `==` y `--hash=sha256:`).

#### FR.5 Configuración de GitHub (la aplica el autor; Claude Code la documenta en `docs/seguridad/CONFIGURACION_GITHUB.md`)

- Cuenta del autor con **2FA** (preferir llave de seguridad o *passkey*).
- *Settings → Code security*: **Secret scanning** y **Push protection**, **Dependabot alerts** y **security updates**, **Private vulnerability reporting**, **CodeQL**.
- *Rulesets* para `main`: sin *force push* ni borrado, PR obligatorio, verificaciones `seguridad` y `codeql` en verde, historial lineal; regla para etiquetas `v*` (solo el autor puede crearlas; no se pueden mover ni borrar).
- *Actions*: permisos del `GITHUB_TOKEN` en **solo lectura** por defecto; aprobación obligatoria para workflows de colaboradores externos; permitir solo acciones de GitHub y verificadas o fijadas por SHA.
- Firma de commits y etiquetas (`git config commit.gpgsign true`, `tag.gpgSign true`, con SSH o GPG registrada en GitHub).
- **Ramas de trabajo privadas (D19):** crear un repositorio privado de desarrollo con el remoto público como segundo remoto; publicar solo `main` y etiquetas. Revisar *Branches* del público y eliminar ramas de trabajo ya publicadas (siguen en clones existentes: no deben contener secretos, ver FR.1).

**Commit:** `chore(repo): gobierno de seguridad del repositorio, CI endurecida, dependencias con hashes y publicación verificable`

---

### F1 – Configuración segura por entorno

**Cierra:** A02, A05, API8, ASVS V3/V9/V14, 27002 8.9 y 8.17, NIST (reautenticación).

**`config.py`** – nuevas variables (todas en `.env.example` con comentario):

| Variable | Defecto | Uso |
|---|---|---|
| `APP_ENTORNO` | `desarrollo` | `desarrollo` \| `evaluacion` \| `operacion` (D25) |
| `APP_HOST` | `127.0.0.1` | interfaz de escucha de `waitress`; en operación **solo** se acepta `127.0.0.1` |
| `APP_PUERTO` | `5000` | puerto de `waitress` |
| `APP_HOSTS_CONFIABLES` | `127.0.0.1,localhost` | se carga en `TRUSTED_HOSTS` de Flask (anti *DNS rebinding*) |
| `WAITRESS_HILOS` | `8` | hilos del servidor |
| `SESSION_MINUTOS_INACTIVIDAD` | `30` | D5 |
| `SESSION_HORAS_MAXIMAS` | `12` | sesión absoluta |
| `ZONA_HORARIA_VISUAL` | `America/Santiago` | D6 |
| `LOG_CARPETA` | `APP_DIR/logs` | log rotativo |
| `MFA_CLAVE_CIFRADO` | vacío | clave Fernet (F5) |
| `MFA_ROLES_OBLIGATORIOS` | `Administrador` | D3 |
| `SEGREGACION_FUNCIONES` | `auto` | D2: `auto` \| `1` \| `0` |
| `INSTALACION_ID` | vacío | D15; lo genera el instalador (`^INST-[0-9a-f]{8}$`); obligatorio fuera de `desarrollo` |
| `CONTACTO_SEGURIDAD_EMAIL` | vacío | opcional; copia de alertas de seguridad |
| `CORREO_SALIENTE_HABILITADO` | `0` | D17 |
| `CORREO_ENTRANTE_HABILITADO` | `0` | D17 |
| `MODO_DEMO` | `0` | D22 (lo activa `demo-cargar`) |
| `REAUTENTICACION_MINUTOS` | `5` | D2; validez de la reautenticación reforzada |
| `IMAP_AUTHSERV_ID` | vacío | F8 |
| `IMAP_EXIGIR_AUTENTICACION` | `1` | D9 |
| `CORREO_DKIM_SELECTORES` | vacío | F8, lista separada por comas |
| `RETENCION_CORREOS_DIAS` | `365` | D7 |
| `RETENCION_INTENTOS_LOGIN_DIAS` | `90` | D7 |
| `ALERTA_UMBRAL_FALLOS_24H` | `20` | F10 |

Cambiar en `.env.example`: `DB_USER=facturacion_app` (no `root`) y `SESSION_MINUTOS_INACTIVIDAD=30`.
`TestingConfig`: `APP_ENTORNO="desarrollo"`, `SEGREGACION_FUNCIONES=True`, `INSTALACION_ID="INST-00000000"`, `MFA_CLAVE_CIFRADO=<clave Fernet fija de pruebas>`, `LOG_CARPETA=None` (sin archivo).

**`app/__init__.py` → `validar_configuracion_operacion(app)`** (llamada en `create_app` después de cargar config). Si `APP_ENTORNO` es `evaluacion` u `operacion`, lanzar `RuntimeError` con la lista completa de incumplimientos.

**Diferencias por perfil**

| Regla | `evaluacion` | `operacion` |
|---|---|---|
| Correo saliente/entrante | Solo hosts *loopback* (`127.0.0.1`/`localhost`); `SMTP_SECURITY`/`IMAP_SECURITY=none` permitido **solo** ahí; cualquier host externo → incumplimiento | Solo `starttls`/`ssl`; credenciales obligatorias si está habilitado |
| `MODO_DEMO` | Obligatorio `1` (franja "Cliente ficticio – proyecto académico") | Debe ser `0` (no se mezclan datos ficticios con reales) |
| `IMAP_EXIGIR_AUTENTICACION` | Puede ser `0` (el sandbox no agrega `Authentication-Results`), con aviso visible | Obligatorio `1` con `IMAP_AUTHSERV_ID` |
| Dominio de `SMTP_FROM` | Debe terminar en `.example` | No puede ser proveedor público (`gmail.com`, etc.) |
| Resto de reglas de esta sección | Se aplican | Se aplican |

Reglas comunes (incumplimiento en ambos perfiles):
- `APP_HOST` distinto de `127.0.0.1` (la app nunca escucha en la red);
- `DB_HOST` distinto de `127.0.0.1`/`localhost`;
- `DB_USER` es `root` o `DB_PASSWORD` está vacía;
- `FLASK_DEBUG=1`;
- `APP_BASE_URL` distinto de `http://127.0.0.1:<APP_PUERTO>` o `http://localhost:<APP_PUERTO>`;
- `APP_HOSTS_CONFIABLES` vacío o con algún valor que no sea `127.0.0.1`, `localhost` o `*.localhost`;
- `INSTALACION_ID` vacío, con formato inválido o distinto del registrado en la tabla `instalacion` (D15);
- el proceso se ejecuta como administrador (Windows: `ctypes.windll.shell32.IsUserAnAdmin()`; POSIX: `os.geteuid() == 0`) (D13);
- `root` de MariaDB acepta contraseña vacía en `DB_HOST` (intento de conexión con `root`/`''` y tiempo de espera de 2 s; si conecta → incumplimiento) (D14);
- MariaDB escucha fuera de *loopback* (`SHOW VARIABLES LIKE 'bind_address'` distinto de `127.0.0.1`/`localhost`/`::1`) (D14);
- correo habilitado que no respeta la tabla anterior para el perfil;
- `SECRET_KEY` igual al valor de ejemplo de la documentación o con baja entropía (< 32 caracteres hexadecimales distintos de un patrón repetido);
- `SMTP_SECURITY` o `IMAP_SECURITY` es `none` (Mailpit/GreenMail solo en `desarrollo`);
- `MFA_CLAVE_CIFRADO` vacía o inválida para Fernet;
- `IMAP_HOST` definido e `IMAP_AUTHSERV_ID` vacío;
- el dominio de `SMTP_FROM` es un proveedor público (`gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.com`, `live.com`);
- alguna carpeta privada (`XML_UPLOAD_FOLDER`, `CORREOS_FOLDER`, `SII_FOLDER`, `LOG_CARPETA`) dentro de `app/static`.

`SESSION_COOKIE_SECURE` puede quedar en `0`: el tráfico va por *loopback* y nunca sale del equipo. Justificarlo en la Declaración de Aplicabilidad (27002 8.24) y en `GUIA_INSTALACION.md`. Se mantienen `HttpOnly` y `SameSite=Lax`.

En `desarrollo` no se lanza error, pero `seguridad-verificar` lista los incumplimientos como advertencias.

**`serve.py`** acepta `evaluacion` y `operacion` (FL.1).

**Advertencias (no impiden arrancar; se muestran en consola, en `seguridad-verificar` y en una franja del panel del Administrador):** disco sin cifrado detectable (D8); carpeta de la app dentro de OneDrive/Dropbox/Google Drive/iCloud (los secretos y datos se sincronizarían a la nube); versión instalada que no corresponde a una etiqueta publicada (D18); ausencia de respaldo en los últimos 7 días.

**Correo desactivado por defecto (D17):** si `CORREO_SALIENTE_HABILITADO=0`, `services/correo.py::enviar` lanza `ErrorCorreo("DESHABILITADO", …)` y la UI oculta los botones de envío; si `CORREO_ENTRANTE_HABILITADO=0`, `revisar_bandeja` no se conecta. En `MODO_DEMO=1` solo se permite el sandbox local (perfil `evaluacion`).

**Recursos locales (D23):** copiar `bootstrap.min.css`, `bootstrap.bundle.min.js`, `bootstrap-icons.min.css` y sus fuentes (versiones 5.3.3 y 1.11.3) a `app/static/vendor/` con sus licencias; verificar que el SHA-384 de cada archivo coincide con el `integrity` actual de `base.html` antes de reemplazar; servirlos desde `url_for('static', …)` manteniendo `integrity`; quitar el CDN de la CSP (`script-src 'self'`, `style-src 'self'`, `font-src 'self'`). Prueba `test_csp_sin_origenes_externos` y `test_vendor_coincide_con_sri`.

**`.env.example` (correcciones):** `DB_USER=facturacion_app`; los ejemplos de Docker para Mailpit/GreenMail publican puertos **solo en loopback** (`docker run -p 127.0.0.1:3025:3025 -p 127.0.0.1:3143:3143 …`, `-p 127.0.0.1:1025:1025 -p 127.0.0.1:8025:8025`); ningún valor de ejemplo debe servir como secreto real (usar `CAMBIAR_…`). Prueba `test_env_example_sin_puertos_publicos_ni_root`.

**Anti *DNS rebinding*:** `app.config["TRUSTED_HOSTS"] = [h.strip() for h in APP_HOSTS_CONFIABLES.split(",") if h.strip()]` (soportado por Flask ≥ 3.1; el proyecto usa 3.1.3). Una petición con otro `Host` responde 400. Esto impide que una página web maliciosa abierta en el mismo equipo use un dominio propio que resuelva a `127.0.0.1` para hablar con la app.

**Sin proxy:** no se usa `ProxyFix`; `request.remote_addr` siempre será `127.0.0.1` y se registra tal cual en la auditoría (el actor se identifica por su cuenta, no por IP).

**`run.py`:** solo para desarrollo; si `APP_ENTORNO != "desarrollo"`, terminar con mensaje que indique usar `serve.py` (FL).

**Sesión máxima absoluta** (`app/security.py`): guardar `session["_inicio_sesion"]` en el login; en `controlar_inactividad` cerrar la sesión si supera `SESSION_HORAS_MAXIMAS`. Registrar evento `SESION_EXPIRADA` (F3) con motivo `inactividad` o `maxima`.

**Zona horaria** (`app/models.py`): en `pymysql.connect(...)` agregar `init_command="SET time_zone = '+00:00'"`. Registrar en `app/__init__.py` un filtro Jinja `hora_local` que convierta `datetime` ingenuo (UTC) a `ZONA_HORARIA_VISUAL` con `zoneinfo` y formato `dd-mm-aaaa HH:MM`. Reemplazar en las plantillas la presentación de fechas de auditoría, `ultimo_login`, correos y facturas por `|hora_local`. Documentar la fecha de corte en `docs/seguridad/POLITICA_RETENCION.md` (sección "Marcas de tiempo").

**Log de aplicación:** si `LOG_CARPETA` está definida, `RotatingFileHandler(LOG_CARPETA/app.log, maxBytes=5 MB, backupCount=10, encoding="utf-8")`, formato `%(asctime)sZ %(levelname)s %(name)s %(message)s` con `time.gmtime`. Agregar `logs/` al `.gitignore`. No registrar contraseñas, códigos MFA ni cuerpos de correo.

**Pruebas (`test/test_configuracion.py`, `test/test_seguridad.py`):**
- `test_operacion_rechaza_configuracion_insegura` y `test_evaluacion_rechaza_configuracion_insegura` (parametrizadas por regla; verifican que el mensaje enumere cada incumplimiento).
- `test_operacion_acepta_configuracion_segura`, `test_evaluacion_acepta_sandbox_local`.
- `test_evaluacion_rechaza_smtp_externo` (p. ej. `SMTP_HOST=smtp-relay.brevo.com`), `test_evaluacion_exige_modo_demo`, `test_operacion_rechaza_modo_demo`.
- `test_operacion_rechaza_host_distinto_de_loopback` (`APP_HOST=0.0.0.0`).
- `test_rechaza_ejecucion_como_administrador`, `test_rechaza_root_sin_password` (monkeypatch de `pymysql.connect`), `test_rechaza_mariadb_fuera_de_loopback`.
- `test_correo_deshabilitado_no_envia`, `test_demo_solo_permite_sandbox_local`.
- `test_advierte_carpeta_sincronizada_en_la_nube`.
- `test_host_no_confiable_responde_400` (petición con `Host: atacante.example`).
- `test_run_py_se_niega_fuera_de_desarrollo`.
- `test_conexion_fija_zona_horaria_utc` (inspeccionar argumentos de `pymysql.connect` con `monkeypatch`).
- `test_sesion_expira_por_tiempo_maximo`.
- `test_filtro_hora_local_convierte_utc`.

**Commit:** `feat(seguridad): configuración por entorno, sesión máxima, UTC y log rotativo`

---

### F2 – Migración 004: esquema de seguridad

Crear `migrations/004_seguridad.sql` (re-ejecutable, MariaDB 10.11):

```sql
START TRANSACTION;

ALTER TABLE `usuarios`
  ADD COLUMN IF NOT EXISTS `debe_cambiar_password` tinyint(1) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `password_actualizada_en` datetime DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `sesion_version` int(10) UNSIGNED NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `mfa_secreto_cifrado` varchar(255) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `mfa_habilitado` tinyint(1) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `mfa_ultimo_paso` bigint(20) UNSIGNED DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `anonimizado_en` datetime DEFAULT NULL;

ALTER TABLE `clientes`
  ADD COLUMN IF NOT EXISTS `anonimizado_en` datetime DEFAULT NULL;

ALTER TABLE `auditoria`
  ADD COLUMN IF NOT EXISTS `hash_anterior` char(64) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS `hash` char(64) DEFAULT NULL,
  ADD KEY IF NOT EXISTS `idx_auditoria_accion` (`accion`, `creado_en`);

CREATE TABLE IF NOT EXISTS `mfa_codigos_recuperacion` (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `usuario_id` int(10) UNSIGNED NOT NULL,
  `codigo_hash` varchar(255) NOT NULL,
  `usado_en` datetime DEFAULT NULL,
  `creado_en` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_mfa_codigos_usuario` (`usuario_id`),
  CONSTRAINT `fk_mfa_codigos_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `intentos_login` (
  `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT,
  `clave` varchar(255) NOT NULL,
  `creado_en` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_intentos_clave_fecha` (`clave`, `creado_en`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- D15: identidad de la instancia (una sola fila).
CREATE TABLE IF NOT EXISTS `instalacion` (
  `id` tinyint(3) UNSIGNED NOT NULL DEFAULT 1,
  `instancia_id` varchar(10) NOT NULL,
  `version_app` varchar(20) NOT NULL,
  `folio_desde` int(10) UNSIGNED DEFAULT NULL,
  `folio_hasta` int(10) UNSIGNED DEFAULT NULL,
  `creada_en` datetime NOT NULL DEFAULT current_timestamp(),
  `actualizada_en` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_instalacion_unica` CHECK (`id` = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- FI: registro de migraciones aplicadas por el migrador.
CREATE TABLE IF NOT EXISTS `migraciones_aplicadas` (
  `nombre` varchar(100) NOT NULL,
  `sha256` char(64) NOT NULL,
  `aplicada_en` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- D1: descripción del rol Lector acorde a sus permisos.
UPDATE `roles` SET `descripcion` = 'Consulta de solicitudes y facturas, solo lectura'
WHERE `nombre` = 'Lector';

COMMIT;
```

Crear también:
- `migrations/005_auditoria_inmutable.sql` (se aplica **después** de `flask auditoria-sellar`, ver F3):

```sql
DELIMITER $$
CREATE TRIGGER IF NOT EXISTS `trg_auditoria_sin_update`
BEFORE UPDATE ON `auditoria` FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La auditoría es de solo inserción.';
END$$
CREATE TRIGGER IF NOT EXISTS `trg_auditoria_sin_delete`
BEFORE DELETE ON `auditoria` FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La auditoría es de solo inserción.';
END$$
DELIMITER ;
```

- `migrations/006_usuario_aplicacion.sql.example` (plantilla; la contraseña se reemplaza a mano y **no** se versiona el archivo real; agregar `migrations/*.local.sql` al `.gitignore`):

```sql
-- La app se conecta por TCP a 127.0.0.1 (DB_HOST): el usuario se crea para ese host,
-- no para '%', de modo que no pueda usarse desde otro equipo.
CREATE USER IF NOT EXISTS 'facturacion_app'@'127.0.0.1' IDENTIFIED BY '<CONTRASEÑA_LARGA_ALEATORIA>';
GRANT SELECT, INSERT ON `facturaciones_spa_mvp`.* TO 'facturacion_app'@'127.0.0.1';
-- UPDATE/DELETE tabla por tabla, nunca sobre auditoria:
GRANT UPDATE, DELETE ON `facturaciones_spa_mvp`.`usuarios` TO 'facturacion_app'@'127.0.0.1';
-- (repetir para: clientes, solicitudes, registros_xml, envios_correo, correos_entrantes,
--  facturas, mfa_codigos_recuperacion, intentos_login; instalacion y migraciones_aplicadas
--  solo SELECT para la app: las modifica el instalador/migrador con root)
FLUSH PRIVILEGES;

-- Usuario de respaldo (solo lectura y bloqueo de tablas para mysqldump):
CREATE USER IF NOT EXISTS 'facturacion_respaldo'@'127.0.0.1' IDENTIFIED BY '<OTRA_CONTRASEÑA>';
GRANT SELECT, LOCK TABLES, SHOW VIEW, TRIGGER, EVENT ON `facturaciones_spa_mvp`.* TO 'facturacion_respaldo'@'127.0.0.1';
FLUSH PRIVILEGES;
```

> Claude Code debe generar el `.example` con **todas** las tablas listadas explícitamente
> (consultando `SHOW TABLES` en la BD de prueba), sin usar el comodín para `UPDATE`/`DELETE`.

**Identidad ficticia (D26) – `migrations/007_dominio_ficticio.sql`:**
```sql
UPDATE `usuarios`
SET `email` = 'sistema.correo@facturaciones-spa.example'
WHERE `email` = 'sistema.correo@facturaciones.cl';
```
Además: `config.py` y `.env.example` → `SISTEMA_CORREO_EMAIL=sistema.correo@facturaciones-spa.example`; reemplazar `facturaciones.cl` por `facturaciones-spa.example` en pruebas, plantillas de correo y comentarios; `000_esquema_base.sql` nace con el dominio nuevo. Prueba `test_sin_dominios_reales_del_cliente` (no aparece `facturaciones.cl` en código, pruebas, plantillas ni migraciones posteriores a 003). Los datos de la BD de desarrollo del equipo (p. ej. `admin@facturaciones.cl`) se corrigen a mano con la misma regla; son locales y no se versionan.

**Esquema base para equipos nuevos:** crear `migrations/000_esquema_base.sql` con la estructura completa vigente **sin datos personales** (`mysqldump --no-data` de la BD de prueba con 001–003 aplicadas) más los catálogos (`roles`, `estados_solicitud`, `origenes_solicitud`) y el usuario técnico de 003. Verificar con una prueba que el archivo no contiene `INSERT INTO usuarios` distinto del usuario técnico, ni `clientes`, `solicitudes` o `auditoria`.

**Orden de migraciones nuevas:** 004 (seguridad) → 005 (auditoría inmutable, tras `auditoria-sellar`) → 006 (plantilla de usuarios) → 007 (dominio ficticio).

**Aplicación:** ejecutar 004 en BD de prueba y de desarrollo con
`C:\xampp\mysql\bin\mysql.exe -u root <bd> < migrations/004_seguridad.sql`. La 005 se aplica en F3. La 006 la aplica el equipo manualmente (ver §5).

**`app/models.py`:** agregar los nuevos campos al constructor de `User` con valores por defecto (`debe_cambiar_password=0`, `sesion_version=0`, `mfa_habilitado=0`, …) y a `_desde_fila` con `fila.get(...)`, para no romper `usuario_falso` en las pruebas.

**Pruebas:** `test/test_migraciones.py::test_migracion_004_es_reejecutable` (parsea el SQL y verifica `IF NOT EXISTS` en cada `ADD COLUMN`/`CREATE`), `test_plantilla_006_no_otorga_update_en_auditoria`.

**Commit:** `feat(bd): migraciones 004–006 para auditoría inmutable, MFA, contraseñas y usuario de aplicación`

---

### F3 – Auditoría inmutable, encadenada y completa

**Cierra:** A09, ASVS V7, 27002 5.33/8.15/8.17, Ley 21.459 (evidencia), RBAC y logs.

**`app/services/auditoria.py` (nuevo)** – mover aquí `registrar_evento` y dejar en `usuarios.py` una reexportación (`from .auditoria import registrar_evento`) para no romper importaciones.

```text
registrar_evento(connection, actor_id, accion, detalle, ip=None)
  1. detalle_txt = json.dumps(detalle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  2. creado_en = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
  3. SELECT hash FROM auditoria WHERE hash IS NOT NULL ORDER BY id DESC LIMIT 1 FOR UPDATE
     -> hash_anterior (o "0"*64 si no hay)
  4. hash = sha256("|".join([hash_anterior, str(actor_id or ""), accion, detalle_txt,
                             ip or "", creado_en.isoformat()]).encode("utf-8"))
  5. INSERT (usuario_id, accion, detalle, ip, creado_en, hash_anterior, hash)
```

- `verificar_cadena(connection)` → recorre por `id` y devuelve `{"ok": bool, "total": n, "primer_error_id": id|None}` recalculando con el **texto almacenado** de `detalle` y `creado_en` (formato ISO, sin zona).
- `sellar_historicos(connection)` → asigna `hash_anterior`/`hash` a filas con `hash IS NULL` en orden de `id` (solo antes de aplicar la migración 005).

**Comandos CLI (`app/cli/__init__.py`):**
- `flask --app run auditoria-sellar` (aborta si los triggers de 005 ya existen).
- `flask --app run auditoria-verificar` (código de salida 1 si la cadena está rota).

Secuencia: `auditoria-sellar` → aplicar `005_auditoria_inmutable.sql` → `auditoria-verificar`.

- `flask --app run auditoria-exportar --desde-id N [--salida carpeta]` (D2): genera `auditoria_<INSTALACION_ID>_<desde>-<hasta>.csv` y `…manifest.json` con `instancia_id`, rango de `id`, `hash_anterior` del primer evento, `hash` del último evento (**sello**), cantidad de eventos, SHA-256 del CSV y versión de la app. Registra `AUDITORIA_EXPORTADA`. Quien revise (docente, evaluador o responsable de la organización que adopte la plataforma) guarda el sello: la siguiente exportación debe comenzar con `hash_anterior` igual al sello anterior. Así, aunque alguien con control total del equipo recalculara la cadena local, no podría alterar lo ya sellado sin que se note (anclaje externo).
- `flask --app run auditoria-comprobar-sello --manifest ruta.json` (lo usa quien revisa, con la exportación siguiente): verifica continuidad, SHA-256 del CSV y que la cadena del CSV sea válida.

**Nuevos eventos** (todos con `registrar_evento`, conexión propia, sin bloquear la respuesta si la BD falla; en ese caso `current_app.logger.error`):

| Acción | Dónde | Detalle |
|---|---|---|
| `LOGIN_EXITOSO` | `auth/routes.py` tras `login_user` (o tras MFA) | `{"mfa": bool}` |
| `LOGIN_FALLIDO` | `auth/routes.py` | `{"email": <intentado>, "motivo": "credenciales"\|"mfa"}` (D10) |
| `LOGIN_BLOQUEADO` | `auth/routes.py` cuando `espera > 0` | `{"email", "segundos"}` |
| `LOGOUT` | `auth/routes.py::logout` | `{}` |
| `SESION_EXPIRADA` | `security.py::controlar_inactividad` | `{"motivo": "inactividad"\|"maxima"\|"version"}` |
| `ACCESO_DENEGADO` | `app/__init__.py` manejador 403 | `{"endpoint", "ruta", "metodo"}` |
| `PASSWORD_CAMBIADA`, `PASSWORD_RESTABLECIDA` | F4 | `{"usuario_afectado_id"}` |
| `MFA_ACTIVADO`, `MFA_RESTABLECIDO`, `MFA_CODIGO_RECUPERACION_USADO` | F5 | `{"usuario_afectado_id"}` |
| `DATOS_EXPORTADOS`, `DATOS_ANONIMIZADOS` | F9 | `{"tipo": "cliente"\|"usuario", "id"}` |
| `RETENCION_EJECUTADA` | F9 | `{"eml_eliminados", "intentos_eliminados"}` |
| `FACTURA_SOD_BLOQUEADA` | F7 | `{"solicitud_afectada_id"}` |
| `REAUTENTICACION` | F5 | `{"accion": "aprobar"\|"observar"\|"sii", "resultado": "ok"\|"fallida"}` |
| `INSTANCIA_INICIALIZADA`, `INSTANCIA_ACTUALIZADA`, `MIGRACION_APLICADA` | FI | `{"instancia_id", "version"}` / `{"nombre", "sha256"}` |

**Visor `/admin/auditoria`** (`app/admin/routes.py`, `templates/admin/auditoria.html`):
- Quitar la lista fija de acciones del `WHERE`; usar una constante `ACCIONES_AUDITORIA` (todas las existentes + las nuevas) como lista blanca para el filtro.
- Filtros GET: `accion`, `usuario_id`, `desde`, `hasta` (validados); paginación 50 por página con `LIMIT %s OFFSET %s`.
- Botón **Exportar CSV** (`/admin/auditoria.csv`, mismos filtros, máx. 10 000 filas, `Content-Disposition: attachment`, evento `AUDITORIA_EXPORTADA`). Neutralizar inyección de fórmulas: prefijar `'` a celdas que comienzan con `= + - @`.
- Indicador de integridad: resultado de `verificar_cadena` (cachear 60 s en `app.extensions`).

**Pruebas (`test/test_auditoria.py`):**
- `test_hash_encadenado_detecta_modificacion` (lista en memoria con conexión falsa).
- `test_hash_encadenado_detecta_eliminacion`.
- `test_login_exitoso_y_fallido_quedan_auditados` (monkeypatch de `registrar_evento`).
- `test_logout_queda_auditado`, `test_acceso_denegado_queda_auditado`.
- `test_bloqueo_de_login_queda_auditado`.
- `test_exportacion_csv_neutraliza_formulas`.
- `test_filtro_auditoria_rechaza_accion_desconocida`.
- `test_exportacion_sellada_y_continuidad` (dos exportaciones consecutivas encadenan; una fila alterada o faltante hace fallar `auditoria-comprobar-sello`).

**Commit:** `feat(auditoria): cadena de hashes, eventos de sesión y visor con filtros y exportación`

---

### F4 – Política de contraseñas, cambio, restablecimiento e invalidación de sesiones

**Cierra:** ASVS V2.1.x y V3.3, NIST 800-63B, 27002 5.17, A07.

**`app/services/contrasenas.py` (nuevo):**
- `validar_politica(password, *, email, nombre, hash_actual=None) -> list[str]` (errores):
  longitud 15–128 (contar caracteres, aceptar Unicode y espacios), no presente en la lista común (comparación en minúsculas), no contiene la parte local del correo ni palabras del nombre de ≥4 letras, no contiene `facturaciones`, distinta de la actual.
- Lista: `app/security_data/contrasenas_comunes.txt` (UTF-8, una por línea). Fuente sugerida: *SecLists – Passwords/Common-Credentials/10k-most-common.txt*. Si no hay red, generar una lista mínima de 500 entradas evidentes (patrones `123456…`, `password…`, `qwerty…`, nombres de meses y años, `facturacion…`) y registrar la limitación en la bitácora. Cargar una sola vez en memoria (`functools.lru_cache`).

**Invalidación de sesiones (`sesion_version`):**
- `User.get_id()` devuelve `f"{id}:{sesion_version}"`.
- `load_user` acepta `"id:version"`; si la versión no coincide con la de BD, devuelve `None` (sesión cerrada) y `controlar_inactividad` registra `SESION_EXPIRADA` motivo `version`. Aceptar también el formato antiguo `"id"` solo si `sesion_version == 0` (transición).
- Incrementar `sesion_version` al: cambiar o restablecer contraseña, cambiar rol, desactivar usuario, restablecer MFA, anonimizar usuario.
- Actualizar `test/conftest.py::login_como` para escribir `sesion["_user_id"] = usuario.get_id()` y que `usuario_falso` defina `sesion_version=0`, `debe_cambiar_password=0`, `mfa_habilitado=1`.

**Cambio de contraseña por el usuario:** `GET/POST /cuenta/password` (nuevo blueprint `cuenta_bp` en `app/cuenta/`), requiere sesión, pide contraseña actual, nueva y confirmación; usa `validar_politica`; actualiza `password_hash`, `password_actualizada_en = UTC_TIMESTAMP()`, `debe_cambiar_password = 0`, `sesion_version + 1`; audita; vuelve a autenticar la sesión actual (`session.clear()` + `login_user`) y redirige al panel. Limitar a 5 intentos fallidos de contraseña actual por 15 min (reutilizar el limitador).

**Restablecimiento por Administrador:** `POST /admin/usuarios/<id>/password` desde `usuario_editar.html`, con contraseña temporal escrita por el Administrador (nunca generada y mostrada en `flash`, porque la cookie de sesión de Flask es legible). Aplica `validar_politica`, marca `debe_cambiar_password = 1`, incrementa `sesion_version`, audita `PASSWORD_RESTABLECIDA`. Un Administrador no puede restablecer su propia contraseña por esta vía.

**Alta de usuarios:** `admin/routes.py::usuarios` usa `validar_politica` y crea con `debe_cambiar_password = 1`.

**Cambio forzado:** en `before_request` (después de `controlar_inactividad`): si `current_user.debe_cambiar_password` y el endpoint no está en `{"cuenta.cambiar_password", "auth.logout", "static", "privacidad"}`, redirigir a `/cuenta/password` con aviso.

**Menú:** enlace "Cambiar contraseña" para todos los roles en `base.html`.

**Pruebas (`test/test_contrasenas.py`, `test/test_cuenta.py`):**
- política: corta, larga, común, contiene correo, contiene nombre, válida, Unicode con espacios.
- `test_cambio_exige_password_actual`, `test_cambio_correcto_incrementa_sesion_version`.
- `test_sesion_con_version_antigua_se_cierra`.
- `test_usuario_con_cambio_pendiente_es_redirigido`.
- `test_admin_restablece_password_y_fuerza_cambio`, `test_admin_no_restablece_su_propia_password_por_admin`.
- `test_alta_usuario_aplica_politica`.

**Commit:** `feat(auth): política de contraseñas NIST, cambio, restablecimiento e invalidación de sesiones`

---

### F5 – MFA (TOTP) para Administrador

**Cierra:** NIST AAL2, ASVS V2.7/V2.8, 27002 8.2/8.5, A07.

**`app/services/mfa.py` (nuevo, solo biblioteca estándar + `cryptography`):**
- `generar_secreto()` → 20 bytes aleatorios en Base32 sin relleno.
- `cifrar(secreto)` / `descifrar(token)` con `Fernet(MFA_CLAVE_CIFRADO)`.
- `codigo_totp(secreto, paso)` → HMAC-SHA1, 6 dígitos, paso de 30 s (RFC 6238).
- `verificar(secreto, codigo, ultimo_paso, ahora=None) -> paso | None` → acepta ventana ±1 paso, rechaza `paso <= ultimo_paso` (anti reutilización), compara con `hmac.compare_digest`.
- `uri_aprovisionamiento(secreto, email)` → `otpauth://totp/Facturaciones:<email>?secret=…&issuer=Facturaciones&digits=6&period=30` (URL-encoded).
- `generar_codigos_recuperacion()` → 10 códigos `xxxx-xxxx-xxxx` (`secrets`), guardados con `generate_password_hash`; se muestran una sola vez en la respuesta de activación (renderizada, no en `flash`).

**Flujo de login (`auth/routes.py`):**
1. Contraseña válida → si el rol está en `MFA_ROLES_OBLIGATORIOS`:
   - con `mfa_habilitado = 1`: `session.clear()`; `session["mfa_pendiente"] = {"uid", "sv", "t"}`; redirigir a `GET/POST /login/mfa`.
   - sin MFA: iniciar sesión y forzar la activación (`before_request` redirige a `/cuenta/mfa` igual que el cambio forzado de contraseña).
2. `/login/mfa`: acepta código TOTP o de recuperación; máximo 5 intentos por `mfa_pendiente`; validez 5 min; si es correcto → `session.clear()`, `login_user`, actualizar `mfa_ultimo_paso`, auditar `LOGIN_EXITOSO {"mfa": true}`.
3. Activación `/cuenta/mfa`: muestra el secreto Base32 y la URI (sin bibliotecas de QR); exige un código válido para confirmar; guarda secreto cifrado, `mfa_habilitado = 1`, códigos de recuperación; audita `MFA_ACTIVADO`.
4. `POST /admin/usuarios/<id>/mfa/restablecer`: solo Administrador y no sobre sí mismo; borra secreto y códigos, `mfa_habilitado = 0`, `sesion_version + 1`; audita.

**Reautenticación reforzada (D2):** decorador `reautenticacion_required(accion)` para `factura_aprobar`, `factura_observar` y `factura_sii`: si `session["reauth"]` no existe o tiene más de `REAUTENTICACION_MINUTOS`, redirige a `GET/POST /cuenta/confirmar` (contraseña + código TOTP), y vuelve a la acción. Los formularios POST originales se reenvían desde la pantalla de confirmación con su token CSRF (no se pierden datos). Audita `REAUTENTICACION`. La marca de reautenticación se borra al usarse en `aprobar` (un uso por aprobación).

**Pruebas (`test/test_mfa.py`):**
- vector de prueba RFC 6238 (secreto ASCII `12345678901234567890`, T = 59 s → `287082` en 6 dígitos).
- `test_rechaza_codigo_reutilizado`, `test_acepta_ventana_mas_menos_uno`, `test_rechaza_fuera_de_ventana`.
- `test_admin_con_mfa_no_queda_autenticado_sin_codigo`.
- `test_admin_sin_mfa_es_redirigido_a_activacion`.
- `test_codigo_recuperacion_es_de_un_solo_uso`.
- `test_mfa_pendiente_expira`, `test_mfa_se_bloquea_tras_5_intentos`.
- `test_secreto_se_guarda_cifrado`.
- `test_aprobar_factura_exige_reautenticacion`, `test_reautenticacion_vence`, `test_reautenticacion_es_de_un_uso_para_aprobar`.

**Commit:** `feat(auth): MFA TOTP obligatorio para Administrador con códigos de recuperación`

---

### F6 – Limitador de intentos persistente

**Cierra:** A07, API4, NIST (limitación de intentos con varios procesos).

- `app/security.py`: `LimitadorIntentosBD` con la misma interfaz (`espera`, `registrar_fallo`, `limpiar`) sobre la tabla `intentos_login` (`creado_en` en UTC con microsegundos). Ante `pymysql.MySQLError`, usar el limitador en memoria como respaldo y registrar advertencia.
- `create_app`: `LimitadorIntentosBD` salvo `TESTING`, que mantiene el de memoria.
- Aplicar también a `/login/mfa` y a la contraseña actual en `/cuenta/password`.
- Limpieza de registros antiguos: en el comando de retención (F9).

**Pruebas:** `test_limitador_bd_bloquea_y_limpia` (conexión falsa), `test_limitador_bd_usa_memoria_si_falla_la_bd`.

**Commit:** `feat(seguridad): limitador de intentos persistente en base de datos`

---

### F7 – RBAC por permisos, rol Lector y segregación de funciones

**Cierra:** A01, API1/API5/API6, 27002 5.3/5.15/8.3, RBAC.

**`app/permisos.py` (nuevo):** mapa central (fuente única para rutas, servicios, menús y documentación):

| Permiso | Administrador | Emisor | Lector |
|---|---|---|---|
| `panel.ver` | ✅ | ✅ | ✅ |
| `cuenta.gestionar` (contraseña, MFA, mis datos) | ✅ | ✅ | ✅ |
| `solicitudes.ver_propias` | ✅ | ✅ | — |
| `solicitudes.ver_todas` | ✅ | — | ✅ (D1) |
| `solicitudes.crear`, `solicitudes.editar`, `solicitudes.xml`, `solicitudes.correo`, `factura.enviar_revision` | ✅ | ✅ (propias) | — |
| `factura.ver` | ✅ | ✅ (propias) | ✅ |
| `solicitudes.xml_descargar` | ✅ | ✅ (propias) | — |
| `solicitudes.cambiar_estado`, `factura.aprobar`, `factura.observar`, `factura.sii` | ✅ | — | — |
| `clientes.gestionar`, `usuarios.gestionar`, `auditoria.ver`, `correos.gestionar`, `datos.exportar`, `datos.anonimizar` | ✅ | — | — |

- `tiene_permiso(rol_nombre, permiso) -> bool` y decorador `permiso_required(*permisos)` (login + cuenta activa + algún permiso; si no, `abort(403)`).
- Reescribir `admin_required` y `solicitud_required` como envoltorios de `permiso_required` (sin cambiar su comportamiento para Administrador/Emisor) y reemplazar las comparaciones `role_name != "Administrador"` dispersas en rutas y servicios por `tiene_permiso(...)`.
- `obtener_solicitud_autorizada`, `construir_filtros` y listados: si no tiene `solicitudes.ver_todas`, filtrar por `emisor_id`.
- Rol Lector: acceso GET a listado, detalle y factura; plantillas ocultan formularios de acción cuando falta el permiso; todos los POST y descargas siguen devolviendo 403.
- Menú en `base.html` generado según permisos.

**Segregación de funciones (`app/services/facturas.py`):** en `aprobar_factura` y `observar_factura`, si `SEGREGACION_FUNCIONES` y (`solicitud["emisor_id"] == actor["id"]` o `factura_vigente["generada_por"] == actor["id"]`) → `ErrorFactura("Por segregación de funciones, otro Administrador debe validar esta factura.")` y evento `FACTURA_SOD_BLOQUEADA`. Mostrar el aviso en `solicitudes/factura.html`.
`segregacion_activa(cursor)`: `"1"` → siempre; `"0"` → nunca; `"auto"` → cuando `SELECT COUNT(*) FROM usuarios u JOIN roles r … WHERE r.nombre='Administrador' AND u.activo=1` ≥ 2. En todos los casos la aprobación exige la reautenticación reforzada de F5. Pruebas adicionales: `test_sod_auto_con_un_admin_permite_con_reautenticacion`, `test_sod_auto_con_dos_admins_bloquea_propia`.

**Documentación:** generar `docs/seguridad/MATRIZ_RBAC.md` desde `app/permisos.py` con el comando `flask --app run rbac-matriz` (evita que la documentación quede desactualizada).

**Pruebas (`test/test_permisos.py`, actualizar `test_rutas.py`):**
- Prueba parametrizada que recorre **todas** las reglas de `app.url_map` (excepto `static`, `auth.*`, `index`, `privacidad`) y verifica que sin sesión redirigen al login → evita rutas nuevas sin protección.
- Prueba parametrizada rol × endpoint con el código esperado (200/302/403/404) para cada fila de la matriz.
- Reemplazar `test_lector_no_accede_a_solicitudes` por `test_lector_ve_solicitudes_solo_lectura` y `test_lector_no_puede_ejecutar_acciones` (si se adopta la alternativa de D1, mantener la prueba original).
- `test_sod_impide_aprobar_factura_propia`, `test_sod_permite_aprobar_factura_de_correo`, `test_sod_desactivable`.
- `test_emisor_no_ve_solicitud_ajena` (404).

**Commit:** `feat(rbac): permisos centralizados, rol Lector de solo lectura y segregación de funciones`

---

### F8 – Autenticación de correo (SPF, DKIM, DMARC)

**Cierra:** SPF/DKIM/DMARC, API10, 27002 8.21.

**Entrante – `app/services/extraccion_correo.py`:**

```python
def verificacion_remitente(mensaje, authserv_id):
    """Devuelve "fallida", "aprobada" o "desconocida".

    Solo confía en la cabecera Authentication-Results agregada por el
    servidor receptor (authserv_id); ignora las que trae el remitente.
    """
    authserv_id = (authserv_id or "").strip().lower()
    if not authserv_id:
        return "desconocida"

    propia = next(
        (
            str(c).lower()
            for c in (mensaje.get_all("Authentication-Results") or [])
            if str(c).strip().lower().startswith(authserv_id)
        ),
        "",
    )
    if not propia:
        return "desconocida"

    dmarc_pasa = bool(re.search(r"\bdmarc=pass\b", propia))
    dmarc_falla = bool(re.search(r"\bdmarc=(fail|permerror|temperror)\b", propia))
    spf_falla = bool(re.search(r"\bspf=(fail|softfail)\b", propia))
    dkim_falla = bool(re.search(r"\bdkim=fail\b", propia))

    if dmarc_falla or spf_falla or (dkim_falla and not dmarc_pasa):
        return "fallida"
    if dmarc_pasa:
        return "aprobada"
    return "desconocida"
```

> Nota: con `spf=softfail` y `dmarc=pass` (DKIM alineado) el resultado es `fallida` por diseño
> conservador; el Administrador lo resuelve con "reprocesar" tras revisar el correo.

- Usar solo la **primera** cabecera que coincida con `authserv_id` (es la más reciente, agregada por el receptor).
- `correo_entrante.py::procesar_correo`: pasar `current_app.config["IMAP_AUTHSERV_ID"]`; agregar motivo de revisión si el resultado es `fallida`, o si es `desconocida` y `IMAP_EXIGIR_AUTENTICACION`. Guardar el resultado en `observaciones` del correo y mostrarlo en `admin/correos.html`.
- Actualizar `test/test_extraccion_correo.py` (la prueba actual usa `mx.ejemplo` sin `authserv_id`).

**Saliente – comando `flask --app run correo-dns [dominio]`** (usa `dnspython`, ya incluido):
- Dominio por defecto: el de `SMTP_FROM`.
- SPF: exactamente un TXT `v=spf1`; sin `+all`; advertir si termina en `?all`; advertir si supera 10 mecanismos con consulta DNS.
- DMARC: TXT en `_dmarc.<dominio>` con `v=DMARC1` y `p=`; advertir si `p=none`; recomendar `rua=`.
- DKIM: para cada selector de `CORREO_DKIM_SELECTORES`, existe TXT o CNAME en `<selector>._domainkey.<dominio>`.
- Salida tabular y código 1 si falta SPF, DMARC o algún DKIM configurado.
- Documentar en `docs/flujo_correo_factura.md` los registros que debe crear el equipo en el panel del proveedor SMTP y en su DNS.

**Pruebas (`test/test_autenticacion_correo.py`):**
- `test_ignora_cabecera_falsa_del_remitente` (cabecera `spf=pass` de otro `authserv-id` + ninguna propia → `desconocida`).
- `test_usa_cabecera_del_receptor` (`dmarc=pass` → `aprobada`; `dmarc=fail` → `fallida`; `spf=softfail` → `fallida`).
- `test_dkim_falla_y_dmarc_no_pasa_es_fallida`.
- `test_desconocida_va_a_revision_si_se_exige`.
- `test_correo_dns_detecta_spf_ausente_y_all_permisivo` (monkeypatch de `dns.resolver.resolve`).
- `test_correo_dns_detecta_dmarc_y_dkim`.

**Commit:** `fix(correo): verificación SPF/DKIM/DMARC confiable y comando de validación DNS`

---

### F9 – Ley 21.719 y Ley 21.459: transparencia, derechos y retención

**Cierra:** Ley 21.719 (transparencia, derechos, minimización, retención), Ley 21.459 (aviso de uso), 27002 5.34/8.10.

**Aviso de privacidad:** ruta pública `GET /privacidad` (endpoint `privacidad`) con `templates/privacidad.html`. Redactado a nombre de **Facturaciones SpA (empresa ficticia, proyecto académico)**, con marcadores `[COMPLETAR: …]` donde falte información: responsable (Facturaciones SpA) y contacto (`privacidad@facturaciones-spa.example`); datos tratados (usuarios, clientes, correos, IP); finalidades; base de licitud; destinatarios y encargados (proveedor SMTP, proveedor IMAP, alojamiento); transferencias internacionales; plazos (D7); derechos de acceso, rectificación, supresión, oposición, portabilidad y bloqueo, y cómo ejercerlos; medidas de seguridad; fecha de actualización. Enlazar desde `auth/login.html` y el pie de `base.html`.

**Aviso de uso autorizado (Ley 21.459):** en `auth/login.html`, texto breve: sistema de uso exclusivo de personal autorizado; los accesos se registran; el acceso no autorizado puede constituir delito conforme a la Ley N° 21.459.

**Derechos de los titulares:**
- `GET /cuenta/mis-datos` (todos los roles): JSON con los datos propios (sin `password_hash` ni secretos MFA); audita `DATOS_EXPORTADOS`.
- `GET /clientes/<id>/exportar` y `GET /admin/usuarios/<id>/exportar` (permiso `datos.exportar`): JSON; auditado.
- `POST /clientes/<id>/anonimizar` (permiso `datos.anonimizar`): solo si el cliente no tiene solicitudes; si las tiene, responder con mensaje de bloqueo por obligación tributaria (D7). Reemplaza `razon_social`, `direccion`, `giro`, `email_contacto` por valores neutros (`Anonimizado <id>`, `anonimizado+<id>@invalid`), `rut` por un marcador único que respete `varchar(12)` y la unicidad, `activo = 0`, `anonimizado_en = UTC_TIMESTAMP()`; auditado sin copiar los datos originales al detalle.
- `POST /admin/usuarios/<id>/anonimizar`: solo usuarios inactivos y distintos del actor; misma lógica sobre `nombre`, `email`, `rut`, `telefono`; `password_hash = '!'`; `sesion_version + 1`.
- Minimización en auditoría: desde esta fase, los eventos `*_EDITADO` y `*_CREADO` de clientes y usuarios registran los **nombres de campos** cambiados y, para `email`, `rut` y `telefono`, valores enmascarados (`a***@dominio.cl`, `12.***.***-5`). Implementar `enmascarar(campo, valor)` en `app/services/auditoria.py`.

**Retención:** comando `flask --app run datos-retencion [--simular]`:
- elimina archivos `.eml` y limpia `nombre_almacenado` de `correos_entrantes` con estado `PROCESADO` o `DESCARTADO` y antigüedad > `RETENCION_CORREOS_DIAS` (la fila se conserva con su `sha256` como evidencia);
- elimina filas de `intentos_login` > `RETENCION_INTENTOS_LOGIN_DIAS`;
- no toca auditoría, facturas, XML ni archivos SII;
- `--simular` solo informa; la ejecución real audita `RETENCION_EJECUTADA`.
Ajustar `_leer_eml`/`obtener_eml_autorizado` para responder "archivo eliminado por política de retención" cuando corresponda.

**Pruebas (`test/test_privacidad.py`):**
- `test_privacidad_es_publica_y_enlazada_desde_login`.
- `test_login_muestra_aviso_uso_autorizado`.
- `test_mis_datos_no_incluye_secretos`.
- `test_no_se_anonimiza_cliente_con_solicitudes`, `test_anonimizar_cliente_sin_solicitudes`.
- `test_no_se_anonimiza_usuario_activo_ni_a_si_mismo`.
- `test_enmascarar_correo_rut_telefono`.
- `test_retencion_simulada_no_elimina`, `test_retencion_respeta_estados_y_plazos`.

**Commit:** `feat(privacidad): aviso Ley 21.719, derechos de titulares, minimización y retención`

---

### F10 – Monitoreo, alertas y respaldo

**Cierra:** 27002 8.13/8.16, Ley 21.719 (detección de vulneraciones), A09.

**Alertas:** comando `flask --app run seguridad-alertas` que revisa las últimas 24 h de `auditoria`:
- `LOGIN_FALLIDO` + `LOGIN_BLOQUEADO` ≥ `ALERTA_UMBRAL_FALLOS_24H`;
- cualquier `ACCESO_DENEGADO` repetido ≥ 5 por usuario;
- `MFA_RESTABLECIDO`, `PASSWORD_RESTABLECIDA`, cambios de rol a Administrador;
- cadena de auditoría rota;
- correos con verificación `fallida`.
Si hay hallazgos, envía un resumen por SMTP a `NOTIFICAR_A` (o a los Administradores activos) con copia opcional a `CONTACTO_SEGURIDAD_EMAIL`, indicando `INSTALACION_ID` en el asunto; si el correo saliente está deshabilitado, solo imprime el resumen y lo muestra en el panel del Administrador, sin datos personales de clientes en el cuerpo; audita `ALERTA_SEGURIDAD_ENVIADA`. Código 0 siempre que el envío funcione; imprime el resumen.

**Respaldo:** `RAIZ/scripts/respaldo.py` (multiplataforma, FI.4) con envoltorio `RAIZ/scripts/windows/respaldo.ps1`:
- `mysqldump.exe --single-transaction --routines --triggers` con el usuario `facturacion_respaldo` usando `--defaults-extra-file` (archivo de credenciales fuera del repositorio, con permisos NTFS solo para la cuenta de la persona, `Administradores` y `SYSTEM`; ruta en parámetro); el nombre del respaldo incluye `INSTALACION_ID`; el `.zip` se cifra con contraseña (AES-256 vía 7-Zip si está instalado; si no, advertir y recomendar disco cifrado);
- comprime el volcado y las carpetas `CORREOS_FOLDER`, `XML_UPLOAD_FOLDER`, `SII_FOLDER` a `respaldos\AAAAMMDD_HHMM.zip`;
- genera `manifest.sha256` con el hash de cada archivo;
- elimina respaldos con más de 14 días;
- parámetro `-Destino2` opcional: copia el `.zip` y el manifiesto a un disco externo cifrado (BitLocker To Go) si está conectado; si no está, registra advertencia (regla 3-2-1: una copia fuera del equipo y desconectada, contra ransomware y robo);
- código de salida distinto de 0 ante error.
`RAIZ/scripts/restaurar_prueba.py` (y envoltorio `scripts/windows/restaurar_prueba.ps1`): restaura el último respaldo en `facturaciones_spa_mvp_restore`, verifica `manifest.sha256` y cuenta filas por tabla.

**Programación (opcional):** documentar en `docs/seguridad/POLITICA_RESPALDO.md` cómo programarlas con el Programador de tareas de Windows (`scripts/windows/instalar_tarea_servicio.ps1`) o con `cron`/`launchd` en Linux/macOS; sin programación, `seguridad-verificar` advierte si no hay respaldo reciente. Tareas: `correo-revisar` (5 min, ya existente), `seguridad-alertas` (diaria), `datos-retencion` (semanal), `respaldo.py` (diaria) y `restaurar_prueba.py` (mensual).

**Pruebas:** `test/test_alertas.py` (umbral, sin hallazgos no envía correo, cadena rota genera alerta). Para los scripts PowerShell: validación de sintaxis con `pwsh -NoProfile -Command "[ScriptBlock]::Create((Get-Content scripts/windows/respaldo.ps1 -Raw)) | Out-Null"` registrada en la bitácora.

**Commit:** `feat(operacion): alertas de seguridad, respaldo y prueba de restauración`

---

### F11 – Análisis estático y pruebas de seguridad de la aplicación

**Cierra:** A06, 27002 8.8/8.25/8.29, ASVS V14, API9. (La CI, Dependabot y dependencias con hashes están en **FR**.)

- `pyproject.toml` o `.bandit` con exclusión de `test/`.
- Corregir o justificar (`# nosec` con motivo) cada hallazgo de `bandit -r app -ll`; revisar y corregir alertas de CodeQL.
- Inventario de rutas: `flask --app run routes > docs/seguridad/INVENTARIO_RUTAS.txt` y agregar a la matriz RBAC el permiso de cada ruta.
- **Prueba dinámica local (DAST básico):** `test/test_dast_basico.py` con el cliente de pruebas: recorre todas las rutas GET sin sesión y con cada rol, envía cargas de XSS/SQLi/traversal típicas a parámetros de filtros y formularios, y verifica respuestas sin trazas, sin reflejo sin escapar y con códigos esperados.
- Prueba de humo del instalador en CI: `python scripts/instalar.py --simular --no-interactivo` en `windows-latest` y `ubuntu-latest`.

**Commit:** `test(seguridad): análisis estático, pruebas dinámicas básicas y humo del instalador`

---

### F12 – Documentación del SGSI y de cumplimiento

Crear en `docs/seguridad/` (Markdown, español, concisos, con fecha y responsable `[COMPLETAR]`):

| Archivo | Contenido mínimo |
|---|---|
| `ALCANCE_SGSI.md` | Alcance (aplicación instalada localmente, BD, archivos, correo, repositorio público y su CI), partes interesadas (autor, evaluadores, personas que instalan), exclusiones (cláusulas 9–10 fuera de alcance del MVP académico). |
| `POLITICA_SEGURIDAD.md` | Principios, roles y responsabilidades, revisión anual. |
| `MATRIZ_RIESGOS.md` | Tabla activo · amenaza · vulnerabilidad · probabilidad · impacto · control (C# / fase) · riesgo residual. Mínimo 15 riesgos (suplantación de correo, robo de sesión, fuerza bruta, IDOR, XXE, fuga de `.eml`, borrado de auditoría, pérdida de BD, dependencia vulnerable, uso indebido por Administrador, etc.). |
| `DECLARACION_APLICABILIDAD.md` | Controles 27002:2022 aplicables / no aplicables, justificación y referencia a la implementación. |
| `REGISTRO_TRATAMIENTOS.md` | **Plantilla** para quien adopte la plataforma: finalidad, base de licitud, categorías de datos y titulares, destinatarios, encargados (proveedor de correo), transferencias, plazo, medidas. Explicar que cada instalación local es un repositorio de datos bajo responsabilidad de quien la opera (D21). |
| `PROCEDIMIENTO_BRECHAS.md` | Detección (F10), contención (desconectar el equipo, revocar credenciales de correo, cambiar contraseñas), evaluación, registro, notificación a la Agencia y a titulares cuando corresponda, preservación de evidencia (Ley 21.459, exportación sellada), lecciones aprendidas. |
| `POLITICA_RETENCION.md` | D7 y marcas de tiempo (D6). |
| `POLITICA_RESPALDO.md` | F10. |
| `POLITICA_CONTRASENAS_MFA.md` | D3, D4, restablecimiento, recuperación. |
| `CIFRADO_EN_REPOSO.md` | D8: cómo activar y comprobar BitLocker (Windows), FileVault (macOS) y LUKS (Linux). |
| `MODELO_AMENAZAS.md` | Activos, actores (malware en el equipo, otra persona con acceso al equipo, sitio web malicioso abierto en el navegador, remitente de correo falsificado, dependencia comprometida, repositorio manipulado), superficies de ataque, controles (C#/fases) y riesgos residuales aceptados. |
| `GUIA_INSTALACION.md` | Guía para **cualquier persona** (lenguaje simple): requisitos, verificación de la descarga, `instalar.py`, primer ingreso, MFA, correo opcional, respaldo, actualización, desinstalación, qué hacer ante pérdida del equipo. Basada en §6. |
| `GUIA_OPERACION_FACTURACIONES_SPA.md` | Operación del cliente (D27): rol del Responsable de Seguridad; alta de persona/equipo (asignar buzón IMAP y credencial SMTP propios, instalación con `--perfil operacion`, acta, informe de cumplimiento); revisión semanal de exportaciones selladas (`auditoria-comprobar-sello`); versiones aprobadas; baja de persona/equipo y pérdida o robo; atención de derechos de titulares en todas las instancias; plantillas `plantillas/ACTA_HABILITACION_EQUIPO.md` y `plantillas/REGISTRO_INSTANCIAS.md` que **se llenan fuera del repositorio**. |
| `EVALUACION.md` (raíz) | FE.4. |
| `CONFIGURACION_GITHUB.md` | FR.5. |
| `SEGURIDAD_FISICA.md` | Recomendaciones: bloqueo de pantalla, contraseña de UEFI, custodia del disco de respaldo y de la clave de recuperación. |
| `MATRIZ_RBAC.md` | Generada en F7. |
| `INVENTARIO_RUTAS.txt` | Generado en F11. |

Actualizar `README.md` (sección "Seguridad") y `docs/flujo_correo_factura.md` (variables nuevas, DNS, comandos).

**Commit:** `docs(seguridad): SGSI, riesgos, aplicabilidad, tratamientos, brechas y políticas`

---

### FL – Operación local segura (servidor, red, XAMPP y Windows)

**Cierra:** 27002 7.x (seguridad física), 8.1 (equipos de usuario), 8.9, 8.13, 8.17, 8.20, 8.24; A02/A05; ASVS V9/V14; Ley 21.719 (deber de seguridad).
**Principio:** superficie de red cero. **Nada** de la plataforma escucha fuera de `127.0.0.1` (impuesto por la propia app, F1); el firewall y el endurecimiento del sistema son una **segunda capa opcional**, porque no se puede exigir a cualquier persona que ejecute scripts como administrador.

#### FL.1 Servidor de aplicación – `serve.py` (nuevo, en `APP_DIR`)

```python
"""Arranque para operación local en un solo equipo. No usar run.py fuera de desarrollo."""
import sys

from waitress import serve

from app import create_app

app = create_app()  # valida la configuración (F1) y aborta si es insegura

if app.config.get("APP_ENTORNO") != "operacion":
    sys.exit("serve.py es solo para APP_ENTORNO=operacion.")

if app.config.get("APP_HOST") != "127.0.0.1":
    sys.exit("APP_HOST debe ser 127.0.0.1: la plataforma no se expone a la red.")

serve(
    app,
    host=app.config["APP_HOST"],          # siempre 127.0.0.1
    port=int(app.config["APP_PUERTO"]),
    threads=int(app.config["WAITRESS_HILOS"]),
    ident=None,                           # no revelar el servidor en la cabecera Server
    clear_untrusted_proxy_headers=True,   # no hay proxy: ignorar X-Forwarded-*
    max_request_body_size=app.config["MAX_CONTENT_LENGTH"],
)
```

> Verificar los nombres de los parámetros (`ident`, `clear_untrusted_proxy_headers`,
> `max_request_body_size`) contra la documentación de la versión instalada de `waitress`.
> La doble comprobación de `APP_HOST` es intencional (defensa en profundidad).

Agregar `config.py` → `APP_HOST`, `APP_PUERTO`, `WAITRESS_HILOS` (F1) y prueba `test_serve_rechaza_desarrollo` (importando con `APP_ENTORNO=desarrollo`).

#### FL.2 Scripts opcionales de endurecimiento para Windows (`RAIZ/scripts/windows/`, PowerShell 5.1 compatible)

> Los scripts multiplataforma esenciales (`instalar.py`, `iniciar.py`, `actualizar.py`, `desinstalar.py`, `respaldo.py`) están en `RAIZ/scripts/` (FI). Los de esta tabla solo **suman** protección en Windows. Cada uno: revisa su propio SHA-256 contra `SHA256SUMS` de la versión publicada, muestra el plan de cambios, exige `-Aplicar`, crea copia de lo que modifica y tiene reversión.

Todos con `Set-StrictMode -Version Latest`, `$ErrorActionPreference = 'Stop'`, ayuda `<# .SYNOPSIS #>`, y **modo simulación por defecto** (solo muestran lo que harían) salvo los de solo lectura.

| Script | Función | Requiere admin |
|---|---|---|
| `iniciar.ps1` | Envoltorio de `python scripts/iniciar.py` para doble clic. | No |
| `instalar_tarea_servicio.ps1 -Usuario <cuenta> [-Aplicar]` | Crea la tarea programada "Facturacion - Servidor" **al iniciar sesión** de la cuenta estándar de la persona, reinicio ante falla (3 intentos, 1 min), sin "ejecutar con privilegios más altos". También registra las tareas de F10 (`correo-revisar`, `seguridad-alertas`, `datos-retencion`, `respaldo.ps1`, `restaurar_prueba.ps1`). | Sí |
| `endurecer_permisos.ps1 -Usuario <cuenta> [-Aplicar]` | `icacls`: quita herencia y deja **Control total** solo a `Administradores` y `SYSTEM`, y **Modificar** a la cuenta de la persona sobre `APP_DIR\.env`, carpetas de registros (`app\registros\*`, `CORREOS_FOLDER`, `SII_FOLDER`), `logs\`, `respaldos\` y el archivo de credenciales de respaldo. Lectura y ejecución para esa cuenta sobre el código (no Modificar: evita que un malware en la sesión altere el código). | Sí |
| `configurar_firewall.ps1 [-Aplicar]` | Reglas de entrada **bloquear** TCP 5000, 3306, 80, 443, 8080, 1025, 8025 (perfiles Dominio, Privado y Público), y bloqueo de entrada para `python.exe` del `venv`, `mysqld.exe` y `httpd.exe` de XAMPP. Nombres con prefijo `Facturacion -` para poder auditarlas y revertirlas. | Sí |
| `endurecer_xampp.ps1 [-RutaXampp C:\xampp] [-Aplicar]` | Respalda y modifica: `mysql\bin\my.ini` (`[mysqld]` → `bind-address=127.0.0.1`, `local-infile=0`, `skip-name-resolve`, `character-set-server=utf8mb4`, `default-time-zone='+00:00'`); `phpMyAdmin\config.inc.php` (`auth_type='cookie'`, sin contraseña escrita en el archivo, `blowfish_secret` aleatorio de 32 caracteres, `AllowNoPassword=false`, `AllowArbitraryServer=false`); verifica `apache\conf\extra\httpd-xampp.conf` con `Require local` para phpMyAdmin; `apache\conf\httpd.conf` con `Listen 127.0.0.1:80`. No cambia contraseñas (eso es manual, §6). | Sí |
| `verificar_host.ps1` | Solo lectura. Informe `CONTROL · OK/FALLA/ADVERTENCIA · DETALLE` (ver FL.4). Código 1 si hay FALLA. | Recomendado |
| `revertir_endurecimiento.ps1 [-Aplicar]` | Restaura las copias `*.bak-AAAAMMDD` de `my.ini`/`config.inc.php` y elimina las reglas `Facturacion -` del firewall. | Sí |

#### FL.3 Verificaciones del equipo (`verificar_host.ps1`)

| Control | Cómo se comprueba | Esperado |
|---|---|---|
| Puertos en escucha | `Get-NetTCPConnection -State Listen` para 5000, 3306, 80, 443, 8080 | 5000 y 3306 solo en `127.0.0.1`; 80 solo `127.0.0.1` o cerrado; 443 y 8080 cerrados |
| Firewall | `Get-NetFirewallProfile` y reglas `Facturacion -*` | Firewall activo en los 3 perfiles; todas las reglas presentes y habilitadas |
| Acceso remoto | `Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' fDenyTSConnections`; `Get-SmbShare` | Escritorio remoto deshabilitado (`1`); sin carpetas compartidas que incluyan `C:\Facturacion` |
| BitLocker | `Get-BitLockerVolume -MountPoint C:` (o `manage-bde -status`) | `ProtectionStatus = On` |
| Antimalware | `Get-MpComputerStatus` | Protección en tiempo real activa; firmas < 3 días |
| Actualizaciones | Servicio `wuauserv` no deshabilitado; último parche (`Get-HotFix`) < 45 días | OK / advertencia |
| Hora | `w32tm /query /status` | Sincronizada; desfase < 2 s |
| Cuenta de la persona | La cuenta que ejecuta la plataforma no pertenece a `Administradores` | OK |
| Identidad | `INSTALACION_ID` del `.env` igual al de la tabla `instalacion` (vía `flask seguridad-verificar`) | OK |
| Bloqueo de pantalla | Directiva de inactividad (`InactivityTimeoutSecs` ≤ 900) | OK / advertencia |
| Permisos NTFS | `Get-Acl` sobre `.env`, registros, `logs`, `respaldos` | Sin `Usuarios`, `Todos` ni `Usuarios autentificados` |
| XAMPP | `my.ini` con `bind-address=127.0.0.1` y `local-infile=0`; `config.inc.php` con `auth_type='cookie'`; módulos FileZilla/Mercury/Tomcat no en ejecución | OK |
| Respaldo | Último `.zip` en `respaldos\` < 26 h y su manifiesto válido | OK |
| Python | `venv` presente; `pip check` sin conflictos | OK |

#### FL.4 Otros ajustes de la aplicación para operación local

- **Cookies y otras apps locales:** las cookies no se aíslan por puerto. Documentar que no deben ejecutarse otras aplicaciones web en `127.0.0.1` del mismo equipo con el mismo navegador; opcionalmente usar `http://facturacion.localhost:5000` (agregarlo a `APP_HOSTS_CONFIABLES`) en navegadores que resuelven `*.localhost` a *loopback*.
- **Enlaces en correos:** `APP_BASE_URL` solo funciona en el equipo de facturación. Los avisos al Administrador deben indicarlo en el texto ("abrir desde el equipo de facturación") y no deben incluir datos de la factura más allá del identificador corto.
- **Rate limiting por IP:** todas las peticiones vienen de `127.0.0.1`; el límite por IP actúa como límite global y el límite por cuenta sigue siendo el principal. Mantenerlo y documentarlo.
- **Usuarios de Windows y de la app:** cada persona usa su propia cuenta de Windows y su propia cuenta de la aplicación; documentar que la sesión de la app se cierra al terminar (botón *Cerrar sesión*) y que el bloqueo de pantalla de Windows es obligatorio, porque todos comparten el mismo navegador/equipo.
- **Identidad en artefactos (D15, D20):** incluir `INSTALACION_ID` en: nombre del archivo SII descargado (`DTE_<INSTALACION_ID>_<public_id corto>_v<versión>.xml`) y comentario XML de `dte_sii.py`; cabecera `X-Facturacion-Instalacion` de todo correo enviado (`construir_mensaje`, lista blanca `X-*` existente); pie de las páginas para Administradores; nombre de respaldos y exportaciones. Pruebas: `test_archivo_sii_incluye_instancia`, `test_correo_lleva_cabecera_instancia`.
- **Perfil de navegador dedicado:** recomendar un perfil de navegador exclusivo para la plataforma (sin extensiones, sin guardar contraseñas), documentado en `GUIA_INSTALACION.md`.

**Pruebas:** `test_serve_rechaza_desarrollo`, `test_serve_rechaza_host_no_loopback`, validación de sintaxis de cada `.ps1` (como en F10) y prueba de `verificar_host.ps1` en modo simulación (`-Simular` que use datos de ejemplo de `scripts/fixtures/`).

**Commit:** `feat(despliegue): operación local en un solo equipo con waitress y scripts de endurecimiento`

---

### FE – Experiencia de evaluación (perfil `evaluacion`)

**Objetivo:** que cada evaluador, con **su propio `.env`** generado en su equipo, ejecute la plataforma de Facturaciones SpA completa —incluido el flujo de correo— en minutos, **sin cuentas reales, sin enviar nada a Internet y sin exponer su equipo**.
**Cierra:** A05 (configuración segura por defecto), 27002 8.31 (separación de entornos), Ley 21.719 (sin datos reales), y la demostración verificable de la matriz.

#### FE.1 Sandbox de correo local – `compose.evaluacion.yaml` (opcional, requiere Docker)

```yaml
services:
  mailpit:            # SMTP de captura + bandeja web para ver los avisos enviados
    image: axllent/mailpit@sha256:<DIGEST_FIJADO>
    ports: ["127.0.0.1:1025:1025", "127.0.0.1:8025:8025"]
  greenmail:          # SMTP+IMAP para simular el buzón de facturación entrante
    image: greenmail/standalone@sha256:<DIGEST_FIJADO>
    environment:
      GREENMAIL_OPTS: "-Dgreenmail.setup.test.smtp -Dgreenmail.setup.test.imap -Dgreenmail.hostname=0.0.0.0 -Dgreenmail.users=facturacion:<GENERADA>@facturaciones-spa.example"
    ports: ["127.0.0.1:3025:3025", "127.0.0.1:3143:3143"]
```

- Imágenes fijadas por *digest*; puertos publicados **solo en loopback**; la contraseña de GreenMail la genera `instalar.py` (no se versiona).
- Sin Docker: el perfil funciona con correo desactivado y la guía indica que el flujo de correo puede verse en las pruebas automatizadas (`test_correo_entrante.py`, `test_envio_integracion.py`).
- Prueba `test_compose_evaluacion_publica_solo_loopback` (parsea el YAML).

#### FE.2 Escenario de demostración de Facturaciones SpA – `flask demo-cargar --escenario facturaciones`

- Clientes ficticios (5) con dominios `*.example` y RUT ficticios con dígito verificador válido, rotulados "ficticio" en `razon_social`.
- Solicitudes en todos los estados (Pendiente, En revisión, En corrección, Aprobada, Rechazada), al menos una factura con dos versiones y cambios auditados, un XML de ejemplo y un archivo SII de ejemplo con advertencia de folio provisional.
- Usuarios: Administrador (creado por la persona en `instalacion-inicializar`), y de demo un segundo Administrador (para mostrar la segregación de funciones), un Emisor y un Lector; contraseñas aleatorias mostradas **una sola vez**; MFA obligatorio para los Administradores igual que en `operacion`.
- `flask demo-correos`: deposita en el sandbox (GreenMail) 4 correos de solicitud: uno válido de cliente registrado, uno de remitente desconocido, uno con datos incompletos y uno **con cabecera `Authentication-Results: spf=pass` falsificada** por el remitente, para evidenciar que se ignora (F8) y queda en revisión.
- `flask demo-borrar` elimina solo lo creado por la demo.

#### FE.3 Recorrido de seguridad guiado – `flask demo-seguridad`

Imprime (sin ejecutar ataques reales) una lista numerada de comprobaciones que el evaluador puede hacer en el navegador o la consola, con el resultado esperado y el control de la matriz que demuestra: acceso a solicitud ajena como Emisor (404, BOLA); aprobar como Emisor (403, BFLA); 5 contraseñas erróneas (429 y `LOGIN_BLOQUEADO`); aprobar la propia factura con dos Administradores (bloqueo por segregación); reautenticación reforzada; correo falsificado en revisión; `Host` no confiable (400); cabeceras de seguridad (`curl -I`); `UPDATE auditoria` rechazado por trigger; `auditoria-verificar`; `seguridad-verificar`. Cada ítem enlaza a la fila de `MATRIZ_CUMPLIMIENTO.md`.

#### FE.4 `EVALUACION.md` (raíz del repositorio)

Guía de una página para evaluadores: requisitos; "Instalación en 10 minutos" (`git clone` → `git checkout v1.0.0-entrega` → `python scripts/instalar.py --perfil evaluacion` → opcional `docker compose -f compose.evaluacion.yaml up -d` → `python scripts/iniciar.py`); dónde ver los correos (Mailpit en `http://127.0.0.1:8025`); el recorrido de FE.3; cómo reiniciar (`demo-borrar` / `desinstalar.py`); qué **no** hacer (no cargar datos reales, no cambiar `APP_HOST`); aclaración de que Facturaciones SpA es ficticia; enlace a `SECURITY.md`. Cada evaluador genera **su propio `.env`**: el repositorio nunca incluye uno.

**Pruebas:** `test_demo_escenario_completo` (estados, versiones y usuarios esperados), `test_demo_correos_incluye_cabecera_falsificada`, `test_franja_cliente_ficticio_en_evaluacion`, prueba de humo en CI: `instalar.py --perfil evaluacion --simular --no-interactivo`.

**Commit:** `feat(evaluacion): perfil de evaluación con escenario ficticio de Facturaciones SpA, sandbox de correo y recorrido de seguridad`

---

### FI – Instalación segura por cualquier persona y ciclo de vida

**Cierra:** 27002 5.9, 5.11, 7.14, 8.1, 8.8, 8.9, 8.19, 8.32; Ley 21.719 (D21); objetivo "quien clone el repositorio no corre riesgos".

#### FI.1 Migrador de base de datos – `flask --app run bd-migrar`

- Pide usuario y contraseña de **root** de MariaDB por consola (`click.prompt(..., hide_input=True)`); **nunca** los guarda ni los registra.
- Si la BD no existe: la crea (`utf8mb4_unicode_ci`) y aplica `000_esquema_base.sql`.
- Aplica en orden `migrations/NNN_*.sql` pendientes según `migraciones_aplicadas`; soporta `DELIMITER $$ … $$`; registra nombre y SHA-256; audita `MIGRACION_APLICADA`. Si cambió el SHA-256 de una migración ya aplicada, aborta.
- Ejecuta `auditoria-sellar` antes de `005` cuando corresponda.
- `--crear-usuarios`: crea `facturacion_app` y `facturacion_respaldo` @`127.0.0.1` con contraseñas aleatorias de 32 caracteres (`secrets.token_urlsafe`) y los permisos de `006`, y las escribe **solo** en `.env` y en el archivo de credenciales de respaldo.
- Si `root` no tiene contraseña, **se niega a continuar** y ofrece establecerla en ese momento (`ALTER USER 'root'@'localhost' IDENTIFIED BY …`, pidiéndola dos veces), además de eliminar usuarios anónimos y la BD `test`.

**Pruebas:** `test_separador_sql_respeta_delimiter`, `test_migrador_omite_aplicadas`, `test_migrador_aborta_si_cambia_hash`, `test_migrador_no_registra_password_root`, `test_migrador_exige_password_root`.

#### FI.2 Inicialización – `flask --app run instalacion-inicializar`

- Crea la fila de `instalacion` con el `INSTALACION_ID` del `.env` y `version_app` (`app/__init__.py::__version__`, nueva constante); se niega si ya existe.
- Crea el primer Administrador de forma interactiva (nombre, correo validado, contraseña con `validar_politica`); MFA obligatorio en el primer ingreso (F5). Sin RUT ni correos por defecto.
- `seed.py` queda como envoltorio que indica usar `instalacion-inicializar` y termina (elimina `admin@facturaciones.cl`, RUT `11111111-1` y la política de 12 caracteres).
- `create_app` (fuera de `desarrollo`): aborta si `instalacion` no existe o su ID difiere (D15).

**Pruebas:** `test_inicializacion_aplica_politica_password`, `test_app_aborta_si_instalacion_no_coincide`, `test_seed_py_ya_no_crea_usuarios`, `test_no_existen_credenciales_por_defecto` (busca en el repositorio correos/contraseñas de ejemplo en código ejecutable).

#### FI.3 Instalador multiplataforma – `RAIZ/scripts/instalar.py`

Solo biblioteca estándar (se ejecuta antes de crear el `venv`). Interactivo, idempotente, con `--perfil evaluacion|operacion` (por defecto `evaluacion`, el caso de los evaluadores), `--simular` y `--no-interactivo` (para CI). Registro en `logs/instalacion_AAAAMMDD_HHMM.log` **sin secretos**.

| Paso | Acción | Falla cerrada si… |
|---|---|---|
| 1 | Comprueba sistema (Windows 10/11, macOS, Linux), versión de Python (`.python-version`), Git y que **no** se ejecuta como administrador/root. | Python no soportado o ejecución como administrador. |
| 2 | Verifica el código: `git describe --tags --exact-match` en una etiqueta `v*`, `git status --porcelain` vacío; si las etiquetas están firmadas, `git verify-tag`; si se descargó el `.zip`, compara su SHA-256 con `SHA256SUMS` e indica cómo verificar la procedencia (`gh attestation verify <zip> -R <owner>/<repo>`). | Cambios locales o versión no publicada (permite continuar solo con `--permitir-desarrollo` y advertencia permanente). |
| 3 | Advierte si la carpeta está en un servicio de sincronización en la nube y si el disco no está cifrado (D8). | — (advertencias). |
| 4 | Crea `venv` e instala `pip install --require-hashes -r requirements.txt`; `pip check`. | Error de hash o de dependencias. |
| 5 | Crea `.env` desde `.env.example` con `SECRET_KEY` (`secrets.token_hex(32)`), `MFA_CLAVE_CIFRADO` (Fernet, generado con el Python del `venv`), `INSTALACION_ID` (`INST-` + `secrets.token_hex(4)`), `APP_ENTORNO` según `--perfil`, `APP_HOST=127.0.0.1`; correo **desactivado** (en `evaluacion`, ofrece activar el sandbox local de FE.1; en `operacion`, pide los datos del buzón y la credencial SMTP **propios** de la persona con `getpass`). Permisos del archivo: solo el usuario actual (Windows: `icacls` sin herencia, usuario actual + `SYSTEM` + `Administradores`; POSIX: `chmod 600`). Nunca imprime secretos. | `.env` ya existe (ofrece conservarlo; nunca lo sobrescribe sin confirmación y copia). |
| 6 | Detecta MariaDB en `127.0.0.1:3306`; si no responde, explica cómo instalar XAMPP o MariaDB (enlaces oficiales) o usar `compose.yaml` (MariaDB publicado en `127.0.0.1` con imagen fijada por *digest*). | No hay MariaDB local. |
| 7 | `flask bd-migrar --crear-usuarios` (FI.1). | Errores de migración o `root` sin contraseña. |
| 8 | `flask instalacion-inicializar` (FI.2). | — |
| 9 | `evaluacion`: ejecuta `flask demo-cargar --escenario facturaciones` y, si el sandbox está activo, `flask demo-correos`. `operacion`: no carga demo; recuerda enviar acta e informe al Responsable de Seguridad (D27). | — |
| 10 | Ejecuta `flask seguridad-verificar` y muestra el resumen con próximos pasos: abrir `http://127.0.0.1:5000`, activar MFA, configurar correo (opcional), respaldos, endurecimiento opcional de Windows. | FALLA en algún control obligatorio. |

`compose.yaml` (opcional, D14): servicio `mariadb` con imagen fijada por *digest*, `ports: ["127.0.0.1:3306:3306"]`, volumen nombrado, contraseña de `root` desde un archivo de secreto generado por el instalador (`secrets:`), sin otros servicios expuestos.

#### FI.4 Comandos de ciclo de vida (`RAIZ/scripts/`, multiplataforma)

| Script | Función |
|---|---|
| `iniciar.py` | Comprueba `.env`, MariaDB y ejecución sin privilegios; arranca `serve.py`; abre el navegador en `http://127.0.0.1:<puerto>`. |
| `respaldo.py` | Equivalente multiplataforma de `respaldo.ps1` (F10): `mysqldump` con `facturacion_respaldo`, archivos privados, manifiesto SHA-256, cifrado del `.zip` si 7-Zip está disponible, retención 14 días. |
| `actualizar.py --version vX.Y.Z` | Verifica que la versión existe y está firmada; respaldo; `git fetch --tags` + `checkout`; `pip install --require-hashes`; `flask bd-migrar`; actualiza `version_app`; `seguridad-verificar`. `--revertir` vuelve a la versión y respaldo anteriores. |
| `desinstalar.py` | Exportación final opcional (auditoría sellada + respaldo cifrado); recuerda revocar credenciales de correo; elimina tareas y reglas `Facturacion -*` si existen (pide elevación solo para eso); elimina BD (pide `root`), usuarios `facturacion_*`, `.env`, datos privados, `logs`, `respaldos` locales e `informes`, sobrescribiendo archivos antes de borrarlos; informa lo realizado. |

#### FI.5 Modo demostración (D22; detalle del escenario en FE.2)

- `flask demo-cargar`: 3 clientes y 5 solicitudes ficticias (`@example.com`, RUT ficticios), un Emisor y un Lector de demo con contraseñas aleatorias de 20 caracteres **mostradas una vez** en consola; `MODO_DEMO=1` en `instalacion`; franja visible "MODO DEMOSTRACIÓN – datos ficticios" en todas las páginas.
- `flask demo-borrar`: elimina solo lo creado por `demo-cargar` (marcado en `instalacion` y con evento de auditoría), deja `MODO_DEMO=0`.
- Pruebas: `test_demo_no_usa_dominios_reales`, `test_demo_borrar_solo_elimina_demo`, `test_franja_demo_visible`.

#### FI.6 Informe de seguridad local – `flask --app run informe-cumplimiento`

Ejecuta `seguridad-verificar` (y `scripts/windows/verificar_host.ps1` si existe y se está en Windows) y genera `informes/cumplimiento_<INSTALACION_ID>_<AAAAMMDD>.md/.json` con resultados por control, versión, fecha UTC, último sello de auditoría y SHA-256 del informe. Sin datos personales. Sirve como evidencia para el evaluador del Capstone o para una organización (`GUIA_ORGANIZACIONES.md`). `informes/` en `.gitignore`.

#### FI.7 Simulacro de "persona desconocida"

En equipos limpios (máquina virtual o **Windows Sandbox**, y una VM Linux), con una cuenta **estándar**:
1. Descargar la versión publicada desde GitHub, verificar `SHA256SUMS` y la atestación.
2. **Como evaluador:** ejecutar `instalar.py --perfil evaluacion` leyendo solo `EVALUACION.md`, completar el recorrido de FE.3 y verificar que nada sale a Internet (Mailpit recibe los avisos; ninguna conexión SMTP/IMAP externa).
3. **Como persona de Facturaciones SpA:** en otra VM, `instalar.py --perfil operacion` con credenciales de prueba de un proveedor real **de pruebas** del equipo; comprobar TLS y `correo-dns`.
4. Comprobar en ambos: `seguridad-verificar` sin FALLA; ningún puerto nuevo fuera de `127.0.0.1` (`netstat -ano` / `ss -ltnp`); no se crearon usuarios con contraseñas por defecto; el correo no envía nada; `demo-cargar` y `demo-borrar` funcionan; `desinstalar.py` deja el equipo limpio.
5. Copiar el `.env` de una instalación a otra → la app no arranca (D15).
Registrar resultados en la bitácora y en la matriz.

**Commit:** `feat(instalacion): instalador multiplataforma seguro por defecto, migrador, demo, actualización y desinstalación`

---

### F13 – Verificación integral y matriz actualizada

**Comando `flask --app run seguridad-verificar`** (`app/cli/verificacion.py`), con salida en tabla `CONTROL · RESULTADO · DETALLE` y código 1 si algún control obligatorio falla:

| Control | Verificación automática |
|---|---|
| Configuración | `validar_configuracion_operacion` para el perfil activo (si `APP_ENTORNO=desarrollo`, simula `evaluacion` y `operacion`) → lista de incumplimientos. |
| Ficción segura | En `evaluacion`: `MODO_DEMO=1`, correo solo *loopback*, todos los correos de clientes y usuarios de demo en `.example`. En cualquier perfil: no existe `facturaciones.cl` en la BD (D26). |
| Escucha de la app | `APP_HOST == "127.0.0.1"` y `TRUSTED_HOSTS` no vacío. |
| MariaDB local | `SHOW VARIABLES LIKE 'bind_address'` = `127.0.0.1`; `local_infile` = `OFF`; `CURRENT_USER()` con host `127.0.0.1`. |
| Instalación | `INSTALACION_ID` válido y coincide con `instalacion`; `version_app` = `__version__` y corresponde a una etiqueta publicada; todas las migraciones del repositorio en `migraciones_aplicadas`. |
| Privilegios | El proceso no corre como administrador/root. |
| MariaDB `root` | No acepta contraseña vacía. |
| Credenciales por defecto | No existen usuarios con contraseñas conocidas (hash comparado con una lista de contraseñas de ejemplo de la documentación). |
| Correo | Si está habilitado: TLS, credenciales presentes, `IMAP_AUTHSERV_ID` definido. |
| Recursos externos | CSP sin orígenes externos; plantillas sin URL `http(s)://` a CDN. |
| Disco cifrado / nube / respaldo | Advertencias de F1. |
| Equipo | Ejecuta `scripts/verificar_host.ps1` (si existe `powershell`) e incorpora su resultado; FALLA del host = FALLA del comando. |
| Usuario de BD | `SELECT CURRENT_USER()` ≠ `root@…`; `SHOW GRANTS` sin `UPDATE`/`DELETE` sobre `auditoria`. |
| Triggers | `information_schema.TRIGGERS` contiene `trg_auditoria_sin_update` y `trg_auditoria_sin_delete`. |
| Cadena de auditoría | `verificar_cadena` → OK. |
| Zona horaria | `SELECT @@session.time_zone` = `+00:00`. |
| MFA | Todos los Administradores activos con `mfa_habilitado = 1`. |
| Contraseñas pendientes | Lista de usuarios con `debe_cambiar_password = 1` (advertencia). |
| Rutas protegidas | Recorre `app.url_map` y confirma que cada vista no pública tiene `permiso_required` (atributo marcador en el decorador). |
| Cabeceras | Petición con `app.test_client()` a `/login`: CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Cache-Control: no-store`. |
| Correo saliente | Ejecuta la lógica de `correo-dns` si `SMTP_HOST` no es local (advertencia si no hay red). |
| Correo entrante | `IMAP_AUTHSERV_ID` definido si `IMAP_HOST` está definido. |
| Carpetas privadas | `XML_UPLOAD_FOLDER`, `CORREOS_FOLDER`, `SII_FOLDER` fuera de `app/static`. |
| Repositorio | `git check-ignore` confirma que `.env`, `*.eml`, `Registros_*`, `respaldos/`, `logs/` están ignorados. |
| Dependencias | Informa la última ejecución de `pip-audit` registrada en la bitácora (manual). |

**Pruebas:** `test/test_verificacion.py` con conexiones falsas para cada verificación (positivo y negativo).

**Matriz actualizada:** crear `docs/seguridad/MATRIZ_CUMPLIMIENTO.md` replicando las secciones de la matriz original (resumen por marco; ISO 27001; 27002; OWASP Top 10; API Top 10; ASVS; NIST; Ley 21.719; Ley 21.459; RBAC y auditoría; SPF/DKIM/DMARC) con columnas **Estado · Implementación (archivo:línea) · Cuándo · Evidencia (prueba o comando)**. Toda fila debe quedar en ✅, N/A justificado o ⚠️ con dependencia externa explícita (ver §5).

**Ejecución final (registrar salidas en la bitácora):**
1. `pytest` → todo en verde; anotar total de pruebas.
2. `bandit -r app -ll` → sin hallazgos sin justificar.
3. `pip-audit -r requirements.txt` → sin vulnerabilidades sin excepción documentada.
4. `flask --app run auditoria-verificar` → OK.
5. `flask --app run seguridad-verificar` → código 0 (advertencias de §5 permitidas).
6. `powershell -File ..\scripts\verificar_host.ps1` → sin FALLA (en el equipo de operación).
7. Desde **otro equipo** de la misma red: `Test-NetConnection <ip_equipo> -Port 5000`, `-Port 3306` y `-Port 80` deben fallar (`TcpTestSucceeded : False`). Si no hay otro equipo, documentarlo y apoyarse en la verificación de puertos de `verificar_host.ps1`.
8. Prueba manual guiada (anotar resultado): login Administrador con MFA; Emisor intenta abrir solicitud ajena (404) y aprobar factura (403); Lector solo lectura; 5 intentos fallidos → 429 y evento `LOGIN_BLOQUEADO`; cambio de contraseña cierra otras sesiones; `UPDATE auditoria …` en phpMyAdmin con el usuario de la app → error; correo con `Authentication-Results` falsificado → `REQUIERE_REVISION`.

**Commit:** `feat(seguridad): verificación integral y matriz de cumplimiento actualizada`

---

### FT – Estructura base reutilizable (después de la entrega)

**Se ejecuta solo cuando el autor lo indique, tras la evaluación**, en un **repositorio nuevo** creado desde la etiqueta `v1.0.0-entrega` (D28). Ningún control de seguridad se elimina ni se relaja.

1. **Congelar la entrega:** en el repositorio del Capstone, etiqueta firmada `v1.0.0-entrega`, *ruleset* que impide moverla y *Release* con `SHA256SUMS`, SBOM y atestación.
2. **Nuevo repositorio** (`<autor>/plataforma-facturacion-base` o el nombre que se elija): crear desde la etiqueta (sin el historial de desarrollo si así lo decide el autor), marcarlo como *Template repository* en GitHub y aplicar FR.5 completo.
3. **Marca configurable:** `app/marca.py` + variables `MARCA_NOMBRE` (por defecto `Mi Empresa`), `MARCA_DOMINIO` (por defecto `empresa.example`), `MARCA_LOGO` (archivo en `app/static/marca/`); reemplazar las ~40 apariciones de "Facturaciones SpA"/`facturaciones` en plantillas, asuntos de correo, comentarios del DTE y CLI por `{{ marca.nombre }}`/`current_app.config`. Nombre de BD por defecto `plataforma_facturacion`. Prueba `test_sin_marca_del_cliente` (no queda "Facturaciones SpA" fuera de `docs/historia/`).
4. **Asistente de marca:** `python scripts/nueva_marca.py` pide nombre, dominio y logo, actualiza `.env.example`, `EMPRESA_*` de ejemplo y textos de privacidad (con `[COMPLETAR]`).
5. **Perfiles:** `evaluacion` pasa a llamarse `demo` (alias aceptado); el escenario de demo se generaliza a una empresa ficticia neutra.
6. **Documentación:** `docs/PLANTILLA.md` (cómo iniciar un proyecto desde la plantilla, qué personalizar, qué controles **no** deben desactivarse), `GUIA_OPERACION_FACTURACIONES_SPA.md` → `GUIA_OPERACION_ORGANIZACION.md` genérica; la documentación del Capstone se archiva en `docs/historia/capstone/`.
7. **Licencia abierta** (D24) y `SECURITY.md` con el contacto de mantenimiento vigente.
8. **Verificación:** F13 completa en el nuevo repositorio, simulacro FI.7 con el perfil `demo` y `operacion`, y primera versión `v1.0.0` de la plantilla.

**Commit (en el nuevo repositorio):** `feat(plantilla): estructura base reutilizable con marca configurable`

---

## 4. Definición de terminado

- [ ] Fases F0, FR, F1–F12, FL, FE, FI y F13 con commit y entrada en la bitácora (FT queda fuera de esta definición: tiene su propia verificación).
- [ ] FR.1 sin secretos ni datos reales en archivos e historial (o hallazgos resueltos por el autor).
- [ ] `pytest`, `bandit`, `pip-audit`, `gitleaks` y `seguridad-verificar` en verde; CodeQL sin alertas abiertas de severidad alta.
- [ ] Simulacro FI.7 aprobado en Windows y Linux con cuenta estándar, en perfil `evaluacion` (solo con `EVALUACION.md`) y en perfil `operacion`.
- [ ] Ninguna referencia a `facturaciones.cl` ni a datos reales; franja de cliente ficticio visible en `evaluacion` (D26).
- [ ] Ninguna credencial por defecto, ningún puerto fuera de `127.0.0.1`, correo desactivado por defecto.
- [ ] `SECURITY.md`, `README.md`, `EVALUACION.md`, `GUIA_INSTALACION.md`, `GUIA_OPERACION_FACTURACIONES_SPA.md` y `MATRIZ_CUMPLIMIENTO.md` completos.
- [ ] Release `vX.Y.Z` de prueba generada por `release.yml` con `SHA256SUMS`, SBOM y atestación verificables.
- [ ] Informe final al autor con: resumen por marco, pruebas agregadas, comandos ejecutados y resultados, y acciones pendientes de §5.

---

## 5. Acciones manuales del autor del repositorio (fuera del alcance de Claude Code)

| Acción | Cuándo |
|---|---|
| Revisar D1–D28 (especialmente D2, D19, D22, D24, D26 y D28) | Antes de ejecutar |
| Corregir a mano en la BD de desarrollo del equipo los correos `@facturaciones.cl` (D26) | Durante F2 |
| Preparar la entrega: etiqueta firmada `v1.0.0-entrega`, *Release* verificable y enlace a `EVALUACION.md` en el README y en el informe del Capstone | Al cerrar F13 |
| Indicar a Claude Code cuándo ejecutar FT y con qué nombre de repositorio | Después de la evaluación |
| Si FR.1 encuentra secretos: **rotarlos primero** y decidir la reescritura del historial | Durante FR |
| Separar el desarrollo en un repositorio privado y eliminar ramas de trabajo del público (D19) | Antes de la primera versión |
| Aplicar la configuración de GitHub de FR.5 (2FA, *secret scanning*, *push protection*, Dependabot, CodeQL, *rulesets*, *private vulnerability reporting*, permisos de Actions) | Después de FR |
| Configurar la firma de commits y etiquetas, y publicar `v1.0.0` con `release.yml` | Después de F13 |
| Elegir la licencia (D24) según las reglas de la institución | Antes de publicar |
| Completar los `[COMPLETAR]` del aviso de privacidad y de la documentación | Antes de publicar |
| Validar con el docente plazos de retención y el alcance de la Ley 21.719 (vigencia legal 1-12-2026; existe un proyecto de postergación en trámite) | Antes de la entrega |

---

## 6. Guías de instalación

### 6.0 Guía rápida para evaluadores (perfil `evaluacion`)

1. Requisitos: Python (versión de `.python-version`), Git, MariaDB local (XAMPP solo con MySQL/MariaDB, o MariaDB oficial). Docker es opcional (sandbox de correo).
2. `git clone <repo>` → `git checkout v1.0.0-entrega` → `git verify-tag v1.0.0-entrega` (o verificar el `.zip` de la *Release* con `SHA256SUMS`).
3. Con una cuenta **estándar**: `python scripts/instalar.py --perfil evaluacion`. El instalador genera **su propio `.env`** con secretos únicos, pide definir la contraseña de `root` de MariaDB si está vacía, crea la BD y el primer Administrador, y carga el escenario ficticio de Facturaciones SpA.
4. Opcional: `docker compose -f compose.evaluacion.yaml up -d` y `flask --app run demo-correos` para probar el flujo de correo; los avisos se ven en `http://127.0.0.1:8025`.
5. `python scripts/iniciar.py` → `http://127.0.0.1:5000`; activar MFA en el primer ingreso.
6. `flask --app run demo-seguridad` muestra el recorrido de comprobaciones de seguridad.
7. Al terminar: `python scripts/desinstalar.py` (borra BD, `.env` y datos) y `docker compose -f compose.evaluacion.yaml down -v`.

### 6.A Guía para el personal de Facturaciones SpA (perfil `operacion`)

Igual que la guía general 6.B, con estas diferencias: instalar con `python scripts/instalar.py --perfil operacion`; antes de empezar, pedir al Responsable de Seguridad el buzón IMAP y la credencial SMTP **propios** y la versión aprobada; al terminar, enviar el informe de cumplimiento y el acta (`GUIA_OPERACION_FACTURACIONES_SPA.md`); exportar semanalmente la auditoría sellada. El endurecimiento de Windows (6.B.7) es **obligatorio** en este perfil por política del cliente.

### 6.B Guía general de instalación segura

> Base de `docs/seguridad/GUIA_INSTALACION.md` y del README. Escrita para quien clona el
> repositorio sin conocerlo (y base de la futura estructura reutilizable, FT). Windows es la plataforma principal; se indican equivalentes
> para macOS y Linux.

#### 6.B.1 Antes de instalar (recomendado, no obligatorio)

1. **Cifrado de disco:** BitLocker (Windows Pro: `manage-bde -status C:`), FileVault (macOS) o LUKS (Linux). Sin cifrado, quien robe el equipo puede leer los datos.
2. **Sistema actualizado** y antivirus activo.
3. **Cuenta estándar** (no administradora) para usar la plataforma; la de administrador solo para instalar programas.
4. **Bloqueo de pantalla** automático (≤ 10 min).
5. Ubicar la plataforma **fuera** de OneDrive, Dropbox, Google Drive o iCloud (p. ej. `C:\Facturacion`).

#### 6.B.2 Requisitos

- Python en la versión indicada en `.python-version` (desde python.org) y Git.
- MariaDB local: XAMPP (solo el módulo MySQL/MariaDB), MariaDB oficial, o Docker con `compose.yaml` del proyecto. En todos los casos solo en `127.0.0.1`.

#### 6.B.3 Descargar y verificar

1. Descargar la **última versión publicada** desde *Releases* (no la rama `main`).
2. Verificar la suma: `Get-FileHash .\<archivo>.zip -Algorithm SHA256` (macOS/Linux: `shasum -a 256`) y compararla con `SHA256SUMS`.
3. Opcional y recomendado: `gh attestation verify <archivo>.zip -R <owner>/<repo>`.
4. O clonar y situarse en la etiqueta: `git clone …` → `git checkout vX.Y.Z` → `git verify-tag vX.Y.Z`.

#### 6.B.4 Instalar

1. Si se usa XAMPP: iniciar **solo** MySQL/MariaDB en el panel; no iniciar Apache, FileZilla, Mercury ni Tomcat.
2. Con la cuenta **estándar**, en la carpeta del proyecto: `python scripts/instalar.py` (Windows: `py scripts\instalar.py`).
3. Seguir los pasos. Si `root` de MariaDB no tiene contraseña, el instalador pedirá definir una: guardarla en un gestor de contraseñas.
4. Opcional: cargar datos de demostración (ficticios).
5. Al final, el resumen de `seguridad-verificar` no debe mostrar **FALLA**. Las **ADVERTENCIAS** explican qué mejorar.

#### 6.B.5 Primer ingreso

1. `python scripts/iniciar.py` → se abre `http://127.0.0.1:5000`.
2. Ingresar con el Administrador creado, **activar MFA** (aplicación autenticadora) y guardar los códigos de recuperación fuera del equipo.
3. Si se cargó la demo: las contraseñas de los usuarios de demo se mostraron una sola vez en la consola.

#### 6.B.6 Correo (opcional)

1. Usar una cuenta **propia y dedicada** con contraseña de aplicación y MFA en el proveedor.
2. Completar SMTP/IMAP en `.env` (solo `starttls` o `ssl`), luego `CORREO_SALIENTE_HABILITADO=1` / `CORREO_ENTRANTE_HABILITADO=1`.
3. Probar: `flask --app run smtp-prueba <correo>`, `flask --app run imap-prueba`, `flask --app run correo-dns`; definir `IMAP_AUTHSERV_ID` según el original de un correo recibido.

#### 6.B.7 Endurecimiento opcional en Windows (como administrador)

En `scripts\windows\`, primero sin `-Aplicar` para revisar: `endurecer_xampp.ps1` (MariaDB solo `127.0.0.1`, `local-infile=0`, phpMyAdmin con login), `configurar_firewall.ps1` (bloquea entrada a 3306/5000/80/443/8080/1025/8025), `endurecer_permisos.ps1 -Usuario <cuenta>`, `instalar_tarea_servicio.ps1 -Usuario <cuenta>` (inicio automático al iniciar sesión), y `verificar_host.ps1`. Cada uno tiene reversión (`revertir_endurecimiento.ps1`).
macOS/Linux: `GUIA_INSTALACION.md` indica el equivalente (firewall del sistema, `bind-address` en `my.cnf`, `chmod 600 .env`).

#### 6.B.8 Uso y mantenimiento

| Frecuencia | Acción |
|---|---|
| Al terminar de trabajar | Cerrar sesión en la plataforma y bloquear el equipo. |
| Semanal | `python scripts/respaldo.py` a un disco externo cifrado; revisar `/admin/auditoria`. |
| Mensual | Probar la restauración; `flask informe-cumplimiento`; actualizar el sistema. |
| Nueva versión publicada | `python scripts/actualizar.py --version vX.Y.Z` (lee las notas de la versión, sobre todo los avisos de seguridad). |
| Antes de cargar datos reales | Leer `/privacidad` y `REGISTRO_TRATAMIENTOS.md`: quien instala es responsable de esos datos (D21). |

#### 6.B.9 Pérdida o robo del equipo

Revocar de inmediato las contraseñas de aplicación del correo, cambiar las contraseñas usadas en la plataforma si se reutilizaban, y seguir `PROCEDIMIENTO_BRECHAS.md` (evaluar si corresponde notificar según la Ley 21.719; el cifrado de disco es lo que normalmente evita que la pérdida sea una vulneración de datos).

#### 6.B.10 Desinstalar

`python scripts/desinstalar.py` (exportación final opcional, borrado de BD, secretos y datos). Revocar las credenciales de correo usadas.

#### 6.B.11 Qué no hacer

- No exponer la plataforma a la red ni a Internet (`APP_HOST=0.0.0.0`, *port forwarding*, túneles tipo ngrok, Escritorio remoto expuesto).
- No ejecutarla como administrador ni con `FLASK_DEBUG=1` / `run.py`.
- No instalar desde ramas, *forks* desconocidos o archivos `.zip` recibidos por chat: solo *Releases* verificadas del repositorio oficial.
- No publicar `.env`, respaldos, `.eml`, XML ni capturas con datos en *issues* o foros; las vulnerabilidades se reportan en privado (`SECURITY.md`).
- No copiar `.env` ni la BD entre equipos: cada instalación tiene secretos propios.
- No dejar Apache/phpMyAdmin encendido sin necesidad.
