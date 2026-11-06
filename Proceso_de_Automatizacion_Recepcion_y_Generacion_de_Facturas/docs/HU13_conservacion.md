# HU13 — Conservación y consulta histórica

Estado: pendiente de aprobación funcional.

## Alcance

Reutilizar el listado y los filtros de HU05 para consultar
solicitudes de períodos anteriores.

No incorporar un módulo independiente de archivo ni procesos
de migración o importación sin aprobación.

## Comportamiento técnico actual

Los filtros desde y hasta se aplican a la fecha de emisión
de la solicitud, con límites inclusivos.

Esto no establece una política de conservación.

## Decisiones pendientes

- Período de conservación.
- Fecha o evento desde el cual se calcula ese período.
- Confirmar si la consulta histórica debe utilizar fecha de
  emisión, fecha de creación u otra referencia.
- Alcance de los registros consultables por el perfil Lector.
- Disponibilidad de datos anteriores al inicio del sistema.
- Necesidad de migración o importación.
- Tratamiento de registros al finalizar el período aprobado.
- Responsable y fecha de aprobación de la política.

## Restricciones de implementación

No ampliar el decorador compartido de escritura para dar
acceso de lectura al Lector.

No introducir eliminación automática por antigüedad como
parte de esta historia sin aprobación expresa.

## Verificaciones pendientes

- Acceso del Administrador y del Lector según permisos aprobados.
- Consulta de solicitudes persistidas de períodos anteriores.
- Separación entre permisos de consulta y modificación.
- Comprobación de que la consulta no altera los datos.
- Evidencia del cumplimiento de la conservación aprobada.