CREATE TABLE IF NOT EXISTS `Proxy_Daemons` (
  `host` varchar(255) NOT NULL,
  `port` int unsigned NOT NULL,
  `curstate` varchar(16) NOT NULL DEFAULT 'n/a',
  `oldstate` varchar(16) NOT NULL DEFAULT 'n/a',
  `last_heartbeat` datetime DEFAULT NULL,
  `latency_ms` int unsigned DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`host`, `port`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
