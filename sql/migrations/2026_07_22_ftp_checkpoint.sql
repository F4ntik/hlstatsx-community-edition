-- P1 FTP durable checkpoint.
--
-- Apply this migration before running hlstats_ftp_py without
-- --legacy-file-marker.  InnoDB is required: the FTP runner advances this
-- cursor in the same MySQL transaction as a committed log file/import tail.
-- This creates only the new cursor table. Default durable mode separately
-- refuses a legacy schema whose importer write tables are not already InnoDB.

CREATE TABLE IF NOT EXISTS `hlstats_FTP_Checkpoints` (
  `source_key` char(64) NOT NULL,
  `checkpoint_mtime_us` bigint unsigned NOT NULL,
  `checkpoint_name` varchar(255) DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`source_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
