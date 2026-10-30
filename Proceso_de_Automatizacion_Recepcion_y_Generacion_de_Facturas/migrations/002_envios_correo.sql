-- =====================================================================
-- Migración 002: registro de auditoría de envíos SMTP
-- Base: facturaciones_spa_mvp (MariaDB 10.4 / XAMPP)
--
-- Cada intento de envío genera una fila. El ciclo de vida es:
--   EN_PROCESO -> ENVIADO | FALLIDO
-- adjunto_sha256 conserva la huella exacta del XML enviado, ya que
-- registros_xml se actualiza en sitio cuando se reemplaza el archivo.
-- =====================================================================

CREATE TABLE IF NOT EXISTS `envios_correo` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `solicitud_id` int(10) unsigned NOT NULL,
  `registro_xml_id` int(10) unsigned DEFAULT NULL,
  `enviado_por` int(10) unsigned NOT NULL,
  `destinatario` varchar(150) NOT NULL,
  `responder_a` varchar(150) DEFAULT NULL,
  `asunto` varchar(200) NOT NULL,
  `adjunto_nombre` varchar(255) DEFAULT NULL,
  `adjunto_sha256` char(64) DEFAULT NULL,
  `message_id` varchar(255) DEFAULT NULL,
  `smtp_host` varchar(150) NOT NULL,
  `estado` enum('EN_PROCESO','ENVIADO','FALLIDO') NOT NULL DEFAULT 'EN_PROCESO',
  `error_codigo` varchar(40) DEFAULT NULL,
  `error_detalle` varchar(500) DEFAULT NULL,
  `creado_en` datetime NOT NULL DEFAULT current_timestamp(),
  `finalizado_en` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_envios_solicitud` (`solicitud_id`, `creado_en`),
  KEY `idx_envios_estado` (`estado`),
  KEY `idx_envios_usuario` (`enviado_por`),
  KEY `idx_envios_xml` (`registro_xml_id`),
  CONSTRAINT `fk_envios_solicitud`
    FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`),
  CONSTRAINT `fk_envios_xml`
    FOREIGN KEY (`registro_xml_id`) REFERENCES `registros_xml` (`id`)
    ON DELETE SET NULL,
  CONSTRAINT `fk_envios_usuario`
    FOREIGN KEY (`enviado_por`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verificación
SHOW CREATE TABLE `envios_correo`;
