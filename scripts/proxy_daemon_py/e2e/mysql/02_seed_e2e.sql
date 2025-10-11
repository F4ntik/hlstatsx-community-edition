-- Override daemon hostnames for the docker-compose sandbox.
UPDATE `hlstats_Options`
SET `value` = 'mock-daemon-a:27900,mock-daemon-b:27901'
WHERE `keyname` = 'Proxy_Daemons';

INSERT INTO `Proxy_Daemons` (`host`, `port`, `curstate`, `oldstate`)
VALUES
  ('mock-daemon-a', 27900, 'n/a', 'n/a'),
  ('mock-daemon-b', 27901, 'n/a', 'n/a')
ON DUPLICATE KEY UPDATE
  `host` = VALUES(`host`),
  `port` = VALUES(`port`),
  `curstate` = VALUES(`curstate`),
  `oldstate` = VALUES(`oldstate`);
