-- Minimal schema required for running the Python proxy daemon locally.
--
-- The script intentionally re-creates only the tables that the daemon reads
-- during startup.  Full HLstatsX installations should rely on the canonical
-- schema from sql/install.sql instead.

DROP TABLE IF EXISTS `hlstats_Options`;
CREATE TABLE IF NOT EXISTS `hlstats_Options` (
  `keyname` varchar(32) NOT NULL DEFAULT '',
  `value` varchar(128) NOT NULL DEFAULT '',
  `opttype` TINYINT NOT NULL DEFAULT '1',
  PRIMARY KEY (`keyname`),
  INDEX (`opttype`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `Proxy_Daemons`;
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
