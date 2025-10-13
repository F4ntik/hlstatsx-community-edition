-- Seed values that allow the Python proxy daemon to start and authenticate
-- local control commands.

INSERT INTO `hlstats_Options` (`keyname`, `value`, `opttype`) VALUES
  ('Proxy_Key', 'changeme', 2)
ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `opttype` = VALUES(`opttype`);

INSERT INTO `hlstats_Options` (`keyname`, `value`, `opttype`) VALUES
  ('Proxy_Daemons', '127.0.0.1:27900,127.0.0.1:27901', 2)
ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `opttype` = VALUES(`opttype`);

INSERT INTO `Proxy_Daemons` (`host`, `port`, `curstate`, `oldstate`)
VALUES
  ('127.0.0.1', 27900, 'n/a', 'n/a'),
  ('127.0.0.1', 27901, 'n/a', 'n/a')
ON DUPLICATE KEY UPDATE
  `curstate` = VALUES(`curstate`),
  `oldstate` = VALUES(`oldstate`);

ALTER USER 'hlstats'@'%' IDENTIFIED WITH mysql_native_password BY 'hlstats';
