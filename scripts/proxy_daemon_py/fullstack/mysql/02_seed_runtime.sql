UPDATE `hlstats_Options`
SET `value` = 'pythonproxysecret'
WHERE `keyname` = 'Proxy_Key';

UPDATE `hlstats_Options`
SET `value` = 'hlstats-worker:28000'
WHERE `keyname` = 'Proxy_Daemons';

INSERT INTO `Proxy_Daemons` (`host`, `port`, `curstate`, `oldstate`)
VALUES ('hlstats-worker', 28000, 'n/a', 'n/a')
ON DUPLICATE KEY UPDATE
  `curstate` = VALUES(`curstate`),
  `oldstate` = VALUES(`oldstate`);

INSERT INTO `hlstats_Servers` (
  `serverId`, `address`, `port`, `name`, `game`, `publicaddress`, `act_players`, `max_players`, `act_map`
)
VALUES (
  1, '127.0.0.1', 27015, 'Local Python Server', 'css', '127.0.0.1:27015', 0, 32, 'de_dust2'
)
ON DUPLICATE KEY UPDATE
  `address` = VALUES(`address`),
  `port` = VALUES(`port`),
  `name` = VALUES(`name`),
  `game` = VALUES(`game`),
  `publicaddress` = VALUES(`publicaddress`),
  `act_map` = VALUES(`act_map`);
