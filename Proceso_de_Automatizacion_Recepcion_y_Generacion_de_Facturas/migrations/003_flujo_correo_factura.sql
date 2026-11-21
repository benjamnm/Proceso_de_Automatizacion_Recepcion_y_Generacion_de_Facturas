-- =====================================================================
-- Migración 003: flujo correo entrante -> factura -> validación -> SII
-- Base: facturaciones_spa_mvp (MariaDB 10.11 / XAMPP)
--
-- Agrega:
--   1. Estados "En corrección" y "Aprobada"; origen "Correo".
--   2. Usuario técnico del proceso automático (no puede iniciar sesión).
--   3. Tabla correos_entrantes: repositorio de correos de facturación.
--   4. Tabla facturas: una fila por versión de factura (v1, v2, ...).
--   5. envios_correo.tipo: distingue XML al cliente de avisos al Admin.
--
-- Es re-ejecutable (IF NOT EXISTS / INSERT IGNORE).
-- Ejecutar en phpMyAdmin > facturaciones_spa_mvp > SQL.
-- Respalde antes: Exportar > Rápido > SQL.
-- =====================================================================

START TRANSACTION;

-- 1) Catálogos ---------------------------------------------------------
INSERT IGNORE INTO `estados_solicitud` (`nombre`) VALUES
  ('En corrección'),
  ('Aprobada');

INSERT IGNORE INTO `origenes_solicitud` (`nombre`) VALUES
  ('Correo');

-- 2) Usuario técnico ---------------------------------------------------
-- password_hash '!' no corresponde a ningún hash válido: el login
-- siempre falla. activo = 0 lo excluye además de Flask-Login.
-- Si cambia el correo, actualice SISTEMA_CORREO_EMAIL en .env.
INSERT INTO `usuarios` (`rol_id`, `nombre`, `email`, `password_hash`, `activo`)
SELECT r.`id`, 'Sistema - Correo entrante',
       'sistema.correo@facturaciones.cl', '!', 0
FROM `roles` AS r
WHERE r.`nombre` = 'Emisor'
  AND NOT EXISTS (
      SELECT 1 FROM `usuarios`
      WHERE `email` = 'sistema.correo@facturaciones.cl'
  );

COMMIT;

-- 3) Repositorio de correos entrantes ---------------------------------
-- Ciclo de vida:
--   RECIBIDO -> PROCESADO          (se creó solicitud + factura v1)
--            -> REQUIERE_REVISION  (faltan datos o remitente desconocido)
--            -> ERROR              (falla técnica; se puede reprocesar)
--   REQUIERE_REVISION | ERROR -> RECIBIDO (reprocesar) | DESCARTADO
CREATE TABLE IF NOT EXISTS `correos_entrantes` (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `huella_message_id` char(64) NOT NULL,
  `message_id` varchar(255) NOT NULL,
  `remitente` varchar(150) NOT NULL,
  `asunto` varchar(200) NOT NULL,
  `fecha_correo` datetime DEFAULT NULL,
  `nombre_almacenado` char(36) NOT NULL,
  `tamano` int(10) UNSIGNED NOT NULL,
  `sha256` char(64) NOT NULL,
  `estado` enum('RECIBIDO','PROCESADO','REQUIERE_REVISION','DESCARTADO','ERROR')
      NOT NULL DEFAULT 'RECIBIDO',
  `cliente_id` int(10) UNSIGNED DEFAULT NULL,
  `solicitud_id` int(10) UNSIGNED DEFAULT NULL,
  `datos_extraidos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
      DEFAULT NULL CHECK (json_valid(`datos_extraidos`)),
  `observaciones` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
      DEFAULT NULL CHECK (json_valid(`observaciones`)),
  `intentos` tinyint(3) UNSIGNED NOT NULL DEFAULT 0,
  `recibido_en` datetime NOT NULL DEFAULT current_timestamp(),
  `procesado_en` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_correos_huella` (`huella_message_id`),
  KEY `idx_correos_estado` (`estado`, `recibido_en`),
  KEY `idx_correos_solicitud` (`solicitud_id`),
  KEY `idx_correos_cliente` (`cliente_id`),
  CONSTRAINT `fk_correos_solicitud`
    FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`),
  CONSTRAINT `fk_correos_cliente`
    FOREIGN KEY (`cliente_id`) REFERENCES `clientes` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) Versiones de factura ---------------------------------------------
-- Cada envío a revisión crea una versión nueva e inmutable.
-- "datos" es la foto completa; "cambios" es la diferencia con la
-- versión anterior (NULL en la v1).
CREATE TABLE IF NOT EXISTS `facturas` (
  `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `solicitud_id` int(10) UNSIGNED NOT NULL,
  `version` smallint(5) UNSIGNED NOT NULL,
  `estado` enum('EN_REVISION','OBSERVADA','APROBADA','RECHAZADA')
      NOT NULL DEFAULT 'EN_REVISION',
  `tipo_dte` smallint(5) UNSIGNED NOT NULL,
  `monto_neto` decimal(14,0) NOT NULL DEFAULT 0,
  `monto_exento` decimal(14,0) NOT NULL DEFAULT 0,
  `iva` decimal(14,0) NOT NULL DEFAULT 0,
  `monto_total` decimal(14,0) NOT NULL,
  `datos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
      NOT NULL CHECK (json_valid(`datos`)),
  `cambios` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin
      DEFAULT NULL CHECK (json_valid(`cambios`)),
  `huella` char(64) NOT NULL,
  `generada_por` int(10) UNSIGNED NOT NULL,
  `generada_en` datetime NOT NULL DEFAULT current_timestamp(),
  `revisada_por` int(10) UNSIGNED DEFAULT NULL,
  `revisada_en` datetime DEFAULT NULL,
  `observacion` varchar(500) DEFAULT NULL,
  `archivo_sii` char(36) DEFAULT NULL,
  `archivo_sii_sha256` char(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_facturas_solicitud_version` (`solicitud_id`, `version`),
  KEY `idx_facturas_estado` (`estado`),
  KEY `idx_facturas_generada_por` (`generada_por`),
  KEY `idx_facturas_revisada_por` (`revisada_por`),
  CONSTRAINT `fk_facturas_solicitud`
    FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`),
  CONSTRAINT `fk_facturas_generada_por`
    FOREIGN KEY (`generada_por`) REFERENCES `usuarios` (`id`),
  CONSTRAINT `fk_facturas_revisada_por`
    FOREIGN KEY (`revisada_por`) REFERENCES `usuarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) Tipo de envío -----------------------------------------------------
ALTER TABLE `envios_correo`
  ADD COLUMN IF NOT EXISTS `tipo`
      enum('XML_CLIENTE','NOTIFICACION_ADMIN')
      NOT NULL DEFAULT 'XML_CLIENTE' AFTER `registro_xml_id`,
  ADD KEY IF NOT EXISTS `idx_envios_tipo` (`tipo`);

-- Verificación ---------------------------------------------------------
SELECT * FROM `estados_solicitud` ORDER BY `id`;
SELECT * FROM `origenes_solicitud` ORDER BY `id`;
SELECT `id`, `nombre`, `email`, `activo` FROM `usuarios`
WHERE `email` = 'sistema.correo@facturaciones.cl';
SHOW CREATE TABLE `correos_entrantes`;
SHOW CREATE TABLE `facturas`;
SHOW COLUMNS FROM `envios_correo` LIKE 'tipo';
