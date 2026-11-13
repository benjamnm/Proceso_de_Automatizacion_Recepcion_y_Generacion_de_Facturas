# Evidencia de regresión automatizada — integración v2 en QA

## Identificación y procedencia

- Proyecto: Automatización de recepción y generación de facturas.
- Fecha de las ejecuciones: 11 de noviembre de 2026, hora local -03.
- Fecha de consolidación documental: 12 de noviembre de 2026.
- Herramienta: pytest 9.1.1; Python 3.15.2; Windows; pluggy 1.7.0.
- Directorio ejecutado: `Proceso_de_Automatizacion_Recepcion_y_Generacion_de_Facturas/test/`.
- Fuente: salidas de consola y ubicaciones de reportes compartidas por el ejecutor en la conversación de QA. Este informe es una transcripción consolidada, no una ejecución nueva.
- Autoría y revisión: consolidación asistida por IA; resultados reportados por el usuario. No existe acta de aceptación del producto asociada a este informe.

## Versión evaluada

Las ejecuciones se realizaron durante una integración local sin commit: HEAD de QA `ad3ab385801f484bc8df252d0e92ddb794a275e5`, integrando v2 `1d84f9d11c3f19f71ace5fef604cace26f713e4a`, con resolución local de conflictos y posteriores ajustes de pruebas HU01/HU06.

El historial posterior contiene el merge `be106bc` y el commit de limpieza `bf475f46ed074740139b6cf1f6ab285bf64a08c5`. Estos identifican la evolución posterior del repositorio; no constituyen evidencia de una nueva ejecución sobre esos commits ni prueban identidad byte a byte con el árbol local evaluado.

## Objetivo y alcance

Comprobar mediante la suite pytest que la integración del flujo v2 y la resolución de conflictos no introducen fallos inesperados en las verificaciones automatizadas existentes y nuevas. La suite combina pruebas de validaciones, servicios, rutas, permisos, correo, facturas y seguridad. Incluye dobles de prueba y no acredita por sí sola integración real con MariaDB o servicios externos. Los casos parametrizados cuentan como pruebas recopiladas, no como historias de usuario diferentes.

## Resultado vigente reportado

| Recopiladas | Aprobadas | Fallidas | Xfailed | Duración | Salida |
|---:|---:|---:|---:|---:|---:|
| 364 | 362 | 0 | 2 | 23,54 s | 0 |

Resultado: regresión automatizada sin fallos inesperados, con dos brechas conocidas. No equivale a aceptación completa del producto.

El historial de ocho ejecuciones se conserva en [ejecuciones.csv](ejecuciones.csv). No se suman ejecuciones repetidas para calcular cobertura.

## Incidencias encontradas y ajustes

### HU01 — expectativas HTTP

La regresión inicial mostró cinco fallos: las pruebas esperaban HTTP 200 al rechazar credenciales, pero v2 devolvía explícitamente HTTP 401. El comportamiento también estaba previsto en las pruebas de seguridad de v2. Se actualizaron únicamente esas expectativas de código en dos funciones de prueba, conservando las verificaciones de mensaje genérico, ausencia de sesión y ausencia de registro de login. Reprueba HU01 + seguridad: 22 aprobadas. No se modificó el código de autenticación para obtener ese resultado.

### HU06 — separación del flujo de factura

Ocho pruebas antiguas se detenían por intentar cambios directos reservados al flujo de factura. Se adaptaron las pruebas de cambio directo a `Rechazada` con motivo; se conservaron verificaciones de autorización, versión, auditoría, reversión y fila afectada; se probó el rechazo desde estado final y se añadieron cuatro variantes de destinos no admitidos. Reprueba HU06: 14 aprobadas. No se eliminó la guarda del servicio.

El bloque `test_facturas.py` + `test_rutas_factura.py` registró 46 aprobadas. Esto no demuestra por sí solo equivalencia completa entre contratos antiguos/nuevos ni aceptación funcional de todos los cambios de estados.

## Brechas conocidas no aprobadas

1. HU12.2: `test_consulta_aplica_filtro_parametrizado_por_solicitud`. La ruta no aplica el filtro parametrizado por solicitud.
2. HU13: `test_lector_puede_acceder_a_consulta_historica`. El decorador rechaza al Lector; se requiere permiso de lectura separado y alcance definido.

Un `xfail` no acredita cumplimiento del requisito. No se ocultan ni se convierten estas brechas en aprobaciones.

## Evidencias originales y trazabilidad

El ejecutor reportó generación de JUnit XML y conservación local de consola, metadatos y códigos de salida en carpetas `QA-Evidencias`. La carpeta final identificada es `Integracion-v2-Regresion-Reprueba-20261111-231448`; su reporte es `regresion-junit.xml`. Los nombres de carpeta por ejecución figuran en el CSV.

Estado documental: los XML, logs y metadatos locales originales todavía no están incluidos en este directorio ni han sido inspeccionados directamente para esta publicación. Este informe no los sustituye ni afirma haber verificado sus hashes o su integridad. Incorporarlos después requiere revisión de contenido sensible y conservar los originales privados.

## Exclusiones y límites

- No hay ejecución Selenium, Lighthouse, JMeter o BrowserStack acreditada por este informe.
- No se acredita recepción o envío real de correo, emisión tributaria SII, restauración de respaldo ni persistencia/concurrencia real por estas cifras pytest.
- No se incluyen pruebas manuales posteriores ni se certifica la existencia de sus capturas.
- No publicar respaldos SQL, archivos .env, credenciales, cookies, correos, XML/DTE de clientes o datos personales.

## Siguientes verificaciones

1. Incorporar los reportes originales revisados y saneados.
2. Vincular las brechas a incidencias reales, sin inventar identificadores Jira.
3. Ejecutar Selenium para acceso, permisos y flujos estables con datos controlados.
4. Auditar páginas mediante Lighthouse y ejecutar carga JMeter con escenarios/criterios autorizados.
