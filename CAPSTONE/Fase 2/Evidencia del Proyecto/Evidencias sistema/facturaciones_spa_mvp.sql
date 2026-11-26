-- phpMyAdmin SQL Dump
-- version 5.2.3
-- https://www.phpmyadmin.net/
--
-- Servidor: 127.0.0.1
-- Tiempo de generación: 26-11-2026 a las 03:48:26
-- Versión del servidor: 10.11.16-MariaDB
-- Versión de PHP: 8.5.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de datos: `facturaciones_spa_mvp`
--

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `auditoria`
--

CREATE TABLE `auditoria` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `usuario_id` int(10) UNSIGNED DEFAULT NULL,
  `accion` varchar(40) NOT NULL,
  `detalle` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`detalle`)),
  `ip` varchar(45) DEFAULT NULL,
  `creado_en` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `clientes`
--

CREATE TABLE `clientes` (
  `id` int(10) UNSIGNED NOT NULL,
  `rut` varchar(12) NOT NULL,
  `razon_social` varchar(150) NOT NULL,
  `direccion` varchar(200) NOT NULL,
  `giro` varchar(150) NOT NULL,
  `email_contacto` varchar(150) NOT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT 1,
  `creado_en` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `correos_entrantes`
--

CREATE TABLE `correos_entrantes` (
  `id` int(10) UNSIGNED NOT NULL,
  `huella_message_id` char(64) NOT NULL,
  `message_id` varchar(255) NOT NULL,
  `remitente` varchar(150) NOT NULL,
  `asunto` varchar(200) NOT NULL,
  `fecha_correo` datetime DEFAULT NULL,
  `nombre_almacenado` char(36) NOT NULL,
  `tamano` int(10) UNSIGNED NOT NULL,
  `sha256` char(64) NOT NULL,
  `estado` enum('RECIBIDO','PROCESADO','REQUIERE_REVISION','DESCARTADO','ERROR') NOT NULL DEFAULT 'RECIBIDO',
  `cliente_id` int(10) UNSIGNED DEFAULT NULL,
  `solicitud_id` int(10) UNSIGNED DEFAULT NULL,
  `datos_extraidos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`datos_extraidos`)),
  `observaciones` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`observaciones`)),
  `intentos` tinyint(3) UNSIGNED NOT NULL DEFAULT 0,
  `recibido_en` datetime NOT NULL DEFAULT current_timestamp(),
  `procesado_en` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `envios_correo`
--

CREATE TABLE `envios_correo` (
  `id` bigint(20) UNSIGNED NOT NULL,
  `solicitud_id` int(10) UNSIGNED NOT NULL,
  `registro_xml_id` int(10) UNSIGNED DEFAULT NULL,
  `tipo` enum('XML_CLIENTE','NOTIFICACION_ADMIN') NOT NULL DEFAULT 'XML_CLIENTE',
  `enviado_por` int(10) UNSIGNED NOT NULL,
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
  `finalizado_en` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `estados_solicitud`
--

CREATE TABLE `estados_solicitud` (
  `id` tinyint(3) UNSIGNED NOT NULL,
  `nombre` varchar(30) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `facturas`
--

CREATE TABLE `facturas` (
  `id` int(10) UNSIGNED NOT NULL,
  `solicitud_id` int(10) UNSIGNED NOT NULL,
  `version` smallint(5) UNSIGNED NOT NULL,
  `estado` enum('EN_REVISION','OBSERVADA','APROBADA','RECHAZADA') NOT NULL DEFAULT 'EN_REVISION',
  `tipo_dte` smallint(5) UNSIGNED NOT NULL,
  `monto_neto` decimal(14,0) NOT NULL DEFAULT 0,
  `monto_exento` decimal(14,0) NOT NULL DEFAULT 0,
  `iva` decimal(14,0) NOT NULL DEFAULT 0,
  `monto_total` decimal(14,0) NOT NULL,
  `datos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`datos`)),
  `cambios` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`cambios`)),
  `huella` char(64) NOT NULL,
  `generada_por` int(10) UNSIGNED NOT NULL,
  `generada_en` datetime NOT NULL DEFAULT current_timestamp(),
  `revisada_por` int(10) UNSIGNED DEFAULT NULL,
  `revisada_en` datetime DEFAULT NULL,
  `observacion` varchar(500) DEFAULT NULL,
  `archivo_sii` char(36) DEFAULT NULL,
  `archivo_sii_sha256` char(64) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `origenes_solicitud`
--

CREATE TABLE `origenes_solicitud` (
  `id` tinyint(3) UNSIGNED NOT NULL,
  `nombre` varchar(30) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `recuperaciones_password`
--

CREATE TABLE `recuperaciones_password` (
  `id` int(10) UNSIGNED NOT NULL,
  `usuario_id` int(10) UNSIGNED NOT NULL,
  `estado` enum('PENDIENTE','ATENDIDA','DESCARTADA') NOT NULL DEFAULT 'PENDIENTE',
  `ip` varchar(45) DEFAULT NULL,
  `solicitada_en` datetime NOT NULL DEFAULT current_timestamp(),
  `atendida_por` int(10) UNSIGNED DEFAULT NULL,
  `atendida_en` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `registros_xml`
--

CREATE TABLE `registros_xml` (
  `id` int(10) UNSIGNED NOT NULL,
  `solicitud_id` int(10) UNSIGNED NOT NULL,
  `nombre_original` varchar(255) NOT NULL,
  `nombre_almacenado` char(36) NOT NULL,
  `tamano` int(10) UNSIGNED NOT NULL,
  `sha256` char(64) NOT NULL,
  `subido_por` int(10) UNSIGNED NOT NULL,
  `subido_en` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `roles`
--

CREATE TABLE `roles` (
  `id` smallint(5) UNSIGNED NOT NULL,
  `nombre` varchar(30) NOT NULL,
  `descripcion` varchar(150) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `solicitudes`
--

CREATE TABLE `solicitudes` (
  `id` int(10) UNSIGNED NOT NULL,
  `public_id` char(32) NOT NULL,
  `emisor_id` int(10) UNSIGNED NOT NULL,
  `cliente_id` int(10) UNSIGNED NOT NULL,
  `estado_id` tinyint(3) UNSIGNED NOT NULL,
  `origen_id` tinyint(3) UNSIGNED NOT NULL,
  `rut` varchar(12) NOT NULL,
  `nombre` varchar(150) NOT NULL,
  `direccion` varchar(200) NOT NULL,
  `giro` varchar(150) NOT NULL,
  `email_contacto_receptor` varchar(150) DEFAULT NULL,
  `concepto` varchar(500) NOT NULL,
  `nro_orden_compra` varchar(40) DEFAULT NULL,
  `fecha_emision` date NOT NULL,
  `monto_bruto` decimal(14,0) NOT NULL,
  `tipo_afectacion` enum('AFECTA','EXENTA') NOT NULL,
  `email_emisor` varchar(150) NOT NULL,
  `motivo_rechazo` varchar(300) DEFAULT NULL,
  `creado_en` datetime NOT NULL DEFAULT current_timestamp(),
  `actualizado_en` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `version` int(10) UNSIGNED NOT NULL DEFAULT 1,
  `clave_idempotencia` char(64) DEFAULT NULL,
  `huella_creacion` char(64) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `usuarios`
--

CREATE TABLE `usuarios` (
  `id` int(10) UNSIGNED NOT NULL,
  `rol_id` smallint(5) UNSIGNED NOT NULL,
  `rut` varchar(12) DEFAULT NULL,
  `nombre` varchar(120) NOT NULL,
  `email` varchar(150) NOT NULL,
  `telefono` varchar(20) DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `activo` tinyint(1) NOT NULL DEFAULT 1,
  `ultimo_login` datetime DEFAULT NULL,
  `creado_en` datetime NOT NULL DEFAULT current_timestamp(),
  `debe_cambiar_password` tinyint(1) NOT NULL DEFAULT 0,
  `password_actualizada_en` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Índices para tablas volcadas
--

--
-- Indices de la tabla `auditoria`
--
ALTER TABLE `auditoria`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_auditoria_usuario` (`usuario_id`),
  ADD KEY `idx_auditoria_fecha` (`creado_en`);

--
-- Indices de la tabla `clientes`
--
ALTER TABLE `clientes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_clientes_rut` (`rut`);

--
-- Indices de la tabla `correos_entrantes`
--
ALTER TABLE `correos_entrantes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_correos_huella` (`huella_message_id`),
  ADD KEY `idx_correos_estado` (`estado`,`recibido_en`),
  ADD KEY `idx_correos_solicitud` (`solicitud_id`),
  ADD KEY `idx_correos_cliente` (`cliente_id`);

--
-- Indices de la tabla `envios_correo`
--
ALTER TABLE `envios_correo`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_envios_solicitud` (`solicitud_id`,`creado_en`),
  ADD KEY `idx_envios_estado` (`estado`),
  ADD KEY `idx_envios_usuario` (`enviado_por`),
  ADD KEY `idx_envios_xml` (`registro_xml_id`),
  ADD KEY `idx_envios_tipo` (`tipo`);

--
-- Indices de la tabla `estados_solicitud`
--
ALTER TABLE `estados_solicitud`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nombre` (`nombre`);

--
-- Indices de la tabla `facturas`
--
ALTER TABLE `facturas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_facturas_solicitud_version` (`solicitud_id`,`version`),
  ADD KEY `idx_facturas_estado` (`estado`),
  ADD KEY `idx_facturas_generada_por` (`generada_por`),
  ADD KEY `idx_facturas_revisada_por` (`revisada_por`);

--
-- Indices de la tabla `origenes_solicitud`
--
ALTER TABLE `origenes_solicitud`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nombre` (`nombre`);

--
-- Indices de la tabla `recuperaciones_password`
--
ALTER TABLE `recuperaciones_password`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_recuperacion_estado` (`estado`,`usuario_id`),
  ADD KEY `idx_recuperacion_usuario` (`usuario_id`),
  ADD KEY `idx_recuperacion_atendida_por` (`atendida_por`);

--
-- Indices de la tabla `registros_xml`
--
ALTER TABLE `registros_xml`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_registros_xml_solicitud` (`solicitud_id`),
  ADD KEY `idx_registros_xml_subido_por` (`subido_por`);

--
-- Indices de la tabla `roles`
--
ALTER TABLE `roles`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `nombre` (`nombre`);

--
-- Indices de la tabla `solicitudes`
--
ALTER TABLE `solicitudes`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `public_id` (`public_id`),
  ADD UNIQUE KEY `uq_solicitud_emisor_idempotencia` (`emisor_id`,`clave_idempotencia`),
  ADD KEY `origen_id` (`origen_id`),
  ADD KEY `idx_solicitud_cliente` (`cliente_id`),
  ADD KEY `idx_solicitud_emisor` (`emisor_id`),
  ADD KEY `idx_solicitud_estado` (`estado_id`),
  ADD KEY `idx_solicitud_fecha` (`fecha_emision`);

--
-- Indices de la tabla `usuarios`
--
ALTER TABLE `usuarios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `email` (`email`),
  ADD UNIQUE KEY `rut` (`rut`),
  ADD KEY `fk_usuario_rol` (`rol_id`);

--
-- AUTO_INCREMENT de las tablas volcadas
--

--
-- AUTO_INCREMENT de la tabla `auditoria`
--
ALTER TABLE `auditoria`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `clientes`
--
ALTER TABLE `clientes`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `correos_entrantes`
--
ALTER TABLE `correos_entrantes`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `envios_correo`
--
ALTER TABLE `envios_correo`
  MODIFY `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `estados_solicitud`
--
ALTER TABLE `estados_solicitud`
  MODIFY `id` tinyint(3) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `facturas`
--
ALTER TABLE `facturas`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `origenes_solicitud`
--
ALTER TABLE `origenes_solicitud`
  MODIFY `id` tinyint(3) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `recuperaciones_password`
--
ALTER TABLE `recuperaciones_password`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `registros_xml`
--
ALTER TABLE `registros_xml`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `roles`
--
ALTER TABLE `roles`
  MODIFY `id` smallint(5) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `solicitudes`
--
ALTER TABLE `solicitudes`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- Restricciones para tablas volcadas
--

--
-- Filtros para la tabla `correos_entrantes`
--
ALTER TABLE `correos_entrantes`
  ADD CONSTRAINT `fk_correos_cliente` FOREIGN KEY (`cliente_id`) REFERENCES `clientes` (`id`),
  ADD CONSTRAINT `fk_correos_solicitud` FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`);

--
-- Filtros para la tabla `envios_correo`
--
ALTER TABLE `envios_correo`
  ADD CONSTRAINT `fk_envios_solicitud` FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`),
  ADD CONSTRAINT `fk_envios_usuario` FOREIGN KEY (`enviado_por`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `fk_envios_xml` FOREIGN KEY (`registro_xml_id`) REFERENCES `registros_xml` (`id`) ON DELETE SET NULL;

--
-- Filtros para la tabla `facturas`
--
ALTER TABLE `facturas`
  ADD CONSTRAINT `fk_facturas_generada_por` FOREIGN KEY (`generada_por`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `fk_facturas_revisada_por` FOREIGN KEY (`revisada_por`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `fk_facturas_solicitud` FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`);

--
-- Filtros para la tabla `recuperaciones_password`
--
ALTER TABLE `recuperaciones_password`
  ADD CONSTRAINT `fk_recuperacion_admin` FOREIGN KEY (`atendida_por`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `fk_recuperacion_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Filtros para la tabla `registros_xml`
--
ALTER TABLE `registros_xml`
  ADD CONSTRAINT `fk_registros_xml_solicitud` FOREIGN KEY (`solicitud_id`) REFERENCES `solicitudes` (`id`),
  ADD CONSTRAINT `fk_registros_xml_usuario` FOREIGN KEY (`subido_por`) REFERENCES `usuarios` (`id`);

--
-- Filtros para la tabla `solicitudes`
--
ALTER TABLE `solicitudes`
  ADD CONSTRAINT `solicitudes_ibfk_1` FOREIGN KEY (`emisor_id`) REFERENCES `usuarios` (`id`),
  ADD CONSTRAINT `solicitudes_ibfk_2` FOREIGN KEY (`cliente_id`) REFERENCES `clientes` (`id`),
  ADD CONSTRAINT `solicitudes_ibfk_3` FOREIGN KEY (`estado_id`) REFERENCES `estados_solicitud` (`id`),
  ADD CONSTRAINT `solicitudes_ibfk_4` FOREIGN KEY (`origen_id`) REFERENCES `origenes_solicitud` (`id`);

--
-- Filtros para la tabla `usuarios`
--
ALTER TABLE `usuarios`
  ADD CONSTRAINT `fk_usuario_rol` FOREIGN KEY (`rol_id`) REFERENCES `roles` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
