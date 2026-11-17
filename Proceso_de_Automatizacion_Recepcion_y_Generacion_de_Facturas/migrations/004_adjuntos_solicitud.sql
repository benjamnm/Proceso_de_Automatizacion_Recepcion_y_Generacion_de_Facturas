-- =====================================================================
-- Migración 004: documentos adjuntos a la solicitud
-- Base: facturaciones_spa_mvp (MariaDB 10.11 / XAMPP)
--
-- Agrega:
--   1. Tabla adjuntos_solicitud: PDF, PNG o JPEG adjuntos al crear una
--      solicitud (máximo 3 de 5 MB). El archivo se guarda en disco, fuera
--      de /static, con nombre aleatorio; aquí solo van sus metadatos.
--   2. (Opcional) Índice que acelera la "Actividad reciente" del Emisor.
--
-- Es re-ejecutable (IF NOT EXISTS).
-- Ejecutar en phpMyAdmin > facturaciones_spa_mvp > SQL.
-- Respalde antes: Exportar > Rápido > SQL.
-- =====================================================================

-- 1) Adjuntos ----------------------------------------------------------
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

-- 2) Opcional (panel): acelera la actividad reciente del Emisor --------
ALTER TABLE `solicitudes`
  ADD KEY IF NOT EXISTS `idx_solicitud_emisor_actualizado`
    (`emisor_id`, `actualizado_en`);

-- Verificación ---------------------------------------------------------
SHOW CREATE TABLE `adjuntos_solicitud`;
