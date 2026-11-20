-- =====================================================================
-- Migración 005: gestión y recuperación de contraseñas
-- Base: facturaciones_spa_mvp (MariaDB 10.11 / XAMPP)
--
-- Agrega:
--   1. usuarios.debe_cambiar_password: obliga a cambiar la contraseña en
--      el próximo inicio de sesión (contraseña temporal del Administrador).
--   2. usuarios.password_actualizada_en: fecha del último cambio.
--   3. Tabla recuperaciones_password: solicitudes "¿Olvidó su contraseña?"
--      que el Administrador atiende (restablece) o descarta.
--
-- Es re-ejecutable (IF NOT EXISTS).
-- Ejecutar en phpMyAdmin > facturaciones_spa_mvp > SQL.
-- Respalde antes: Exportar > Rápido > SQL.
-- =====================================================================

-- 1) y 2) Columnas en usuarios -----------------------------------------
ALTER TABLE `usuarios`
  ADD COLUMN IF NOT EXISTS `debe_cambiar_password` tinyint(1) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS `password_actualizada_en` datetime NULL DEFAULT NULL;

-- 3) Solicitudes de recuperación ---------------------------------------
CREATE TABLE IF NOT EXISTS `recuperaciones_password` (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `usuario_id` int(10) UNSIGNED NOT NULL,
  `estado` enum('PENDIENTE','ATENDIDA','DESCARTADA') NOT NULL DEFAULT 'PENDIENTE',
  `ip` varchar(45) DEFAULT NULL,
  `solicitada_en` datetime NOT NULL DEFAULT current_timestamp(),
  `atendida_por` int(10) UNSIGNED DEFAULT NULL,
  `atendida_en` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_recuperacion_estado` (`estado`, `usuario_id`),
  KEY `idx_recuperacion_usuario` (`usuario_id`),
  KEY `idx_recuperacion_atendida_por` (`atendida_por`),
  CONSTRAINT `fk_recuperacion_usuario`
    FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`),
  CONSTRAINT `fk_recuperacion_admin`
    FOREIGN KEY (`atendida_por`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verificación ---------------------------------------------------------
SHOW COLUMNS FROM `usuarios` LIKE '%password%';
SHOW CREATE TABLE `recuperaciones_password`;
