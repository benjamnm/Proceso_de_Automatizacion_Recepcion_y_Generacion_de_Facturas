-- =====================================================================
-- Migración 001: elimina la columna sin uso solicitudes.creado_por
-- Base: facturaciones_spa_mvp (MariaDB 10.4 / XAMPP)
--
-- Contexto: la idempotencia se controla con
--   uq_solicitud_emisor_idempotencia (emisor_id, clave_idempotencia).
-- La columna creado_por y su índice uq_solicitud_creador_clave no se
-- usan en el código (verificado en app/).
--
-- Ejecutar en phpMyAdmin > facturaciones_spa_mvp > SQL.
-- Respalde antes: Exportar > Rápido > SQL.
-- =====================================================================

-- 1) Verificación previa: debe devolver 0. Si no, NO continúe.
SELECT COUNT(*) AS filas_con_creado_por
FROM solicitudes
WHERE creado_por IS NOT NULL;

-- 2) Limpieza
ALTER TABLE solicitudes
    DROP INDEX uq_solicitud_creador_clave,
    DROP COLUMN creado_por;
