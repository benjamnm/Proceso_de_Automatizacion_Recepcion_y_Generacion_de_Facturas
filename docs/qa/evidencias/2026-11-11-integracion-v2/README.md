# Matriz integral de pruebas QA

Esta matriz complementa, no reemplaza, el historial `2026-11-11-integracion-v2/ejecuciones.csv` ni su informe. Es una consolidacion asistida de resultados reportados y trabajo planificado; no es una nueva ejecucion ni una certificacion de cobertura completa de Fase 2.

## Lectura y conteo

- A01-A25: 25 modulos de la suite pytest. El desglose se reconstruye de las salidas compartidas y las repruebas HU01/HU06. Suma: 362 aprobadas, cero fallidas y dos xfailed; 364 pruebas recopiladas en R08, 23.54 segundos, salida 0.
- A26: archivo sin extension py inventariado; no se cuenta en R08.
- M01: smoke manual aprobado por confirmacion del ejecutor; capturas no aportadas. No acredita Selenium ni aislamiento completo por perfil.
- D01 y B01: verificaciones de ambiente/preparacion, no casos funcionales adicionales. El respaldo esta exportado, no restaurado ni probado recuperable.
- P01-P10: bloques de trabajo pendientes o condicionados. No cuentan como pruebas aprobadas, no son diez requisitos nuevos y no se suman a las 364.
- Campos numericos vacios: no aplican o no existe ejecucion. No significan cero pruebas fallidas de un bloque no ejecutado.
- No sumar R01-R08 ni repetir conteos entre la matriz y el historial como cobertura adicional.

## Version y evidencia

R08 se ejecuto el 11/11/2026 sobre el arbol local de integracion sin commit: HEAD ad3ab385801f484bc8df252d0e92ddb794a275e5, integrando 1d84f9d11c3f19f71ace5fef604cace26f713e4a, con resoluciones y ajustes locales. El merge posterior be106bc no constituye una nueva ejecucion.

Los XML originales y logs locales no se han incorporado ni inspeccionado directamente. Los estados reflejan reportes del ejecutor. Para una fila por cada una de las 364 pruebas parametrizadas, se debe incorporar y procesar el JUnit original; no inventar identificadores, duraciones individuales o resultados por parametro.

La matriz no contiene las precondiciones, datos y pasos completos de cada caso individual: ese detalle corresponde al catalogo de casos y su trazabilidad con RF/RNF/HU, cuya revision documental integra sigue pendiente. Los nombres de archivo no demuestran por si solos el nivel real ni el uso de servicios externos.

## Brechas y seguridad

HU12.2 y HU13 permanecen abiertas; xfail no equivale a aprobado. Revisar equivalencia funcional de las pruebas adaptadas antes de aceptar el alcance de negocio.

Se acordo utilizar facturaciones_spa_mvp; no se ha demostrado aislamiento productivo. Las pruebas mutantes requieren datos controlados, identificadores y limpieza limitada. La carga JMeter requiere autorizacion especifica. No subir respaldos SQL, .env, contrasenas, cookies, correos o documentos sensibles. Cualquier evidencia original publicada debe revisarse y sanearse sin alterar su significado; conservar originales privados.

## Uso

Consultar `matriz-integral.csv` junto al informe e historial existentes. Vincular cada bloque pendiente a criterios reales antes de expandirlo en casos. Registrar fecha, commit, ambiente, resultado y evidencia por cada nueva ejecucion, conservando intentos previos.