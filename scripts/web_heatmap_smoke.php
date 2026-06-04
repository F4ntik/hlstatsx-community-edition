<?php

declare(strict_types=1);

define('IN_HLSTATS', true);
define('ROOT_PATH', dirname(__DIR__) . '/web');

require ROOT_PATH . '/includes/heatmap_points.php';

function assert_same($expected, $actual, string $message): void
{
    if ($expected !== $actual) {
        fwrite(STDERR, $message . PHP_EOL);
        fwrite(STDERR, 'Expected: ' . var_export($expected, true) . PHP_EOL);
        fwrite(STDERR, 'Actual: ' . var_export($actual, true) . PHP_EOL);
        exit(1);
    }
}

assert_same('de_dust2', heatmap_clean_token('de_dust2'), 'valid map token should pass');
assert_same('', heatmap_clean_token('../de_dust2'), 'path-ish map token should be rejected');
assert_same('kills', heatmap_clean_event('kills'), 'valid heatmap event should pass');
assert_same('kills', heatmap_clean_event('bad'), 'invalid heatmap event should fall back to kills');

$config = array(
    'xoffset' => 32,
    'yoffset' => 64,
    'flipx' => 1,
    'flipy' => 0,
    'scale' => 2,
);

$point = heatmap_transform_point(array('pos_x' => 12, 'pos_y' => 20), $config);
assert_same(10, $point['x'], 'x transform should apply flip, offset, and scale');
assert_same(42, $point['y'], 'y transform should apply offset and scale');

$rotated = heatmap_transform_point(
    array('pos_x' => 10, 'pos_y' => 20),
    array('xoffset' => 0, 'yoffset' => 0, 'flipx' => 0, 'flipy' => 0, 'scale' => 1, 'rotate' => 1, 'cropx1' => 5, 'cropy1' => 7, 'cropx2' => 200, 'cropy2' => 200)
);
assert_same(15, $rotated['x'], 'x transform should rotate before crop');
assert_same(3, $rotated['y'], 'y transform should rotate before crop');

$payload = heatmap_build_payload(
    'cstrike',
    'de_dust2',
    array('url' => './hlstatsimg/games/cstrike/maps/de_dust2.jpg', 'width' => 1280, 'height' => 1024),
    array(
        array('pos_x' => 0, 'pos_y' => 0, 'value' => 1, 'heatmapEvent' => 'kills', 'killerId' => 10, 'killerName' => 'Alpha', 'victimId' => 20, 'victimName' => 'Beta'),
        array('pos_x' => 0, 'pos_y' => 0, 'value' => 1, 'heatmapEvent' => 'deaths', 'killerId' => 10, 'killerName' => 'Alpha', 'victimId' => 30, 'victimName' => 'Gamma'),
        array('pos_x' => 5000, 'pos_y' => 5000, 'value' => 1),
    ),
    array(
        'xoffset' => 32,
        'yoffset' => 32,
        'flipx' => 0,
        'flipy' => 0,
        'scale' => 1,
    )
);

assert_same('cstrike', $payload['game'], 'payload should include game');
assert_same('de_dust2', $payload['map'], 'payload should include map');
assert_same(1, count($payload['points']), 'payload should drop transformed out-of-bounds points');
assert_same(32, $payload['points'][0]['x'], 'payload point should include transformed x');
assert_same(32, $payload['points'][0]['y'], 'payload point should include transformed y');
assert_same(2, $payload['points'][0]['value'], 'payload bucket should sum duplicate transformed points');
assert_same(1, $payload['points'][0]['killValue'], 'payload bucket should include kill channel intensity');
assert_same(1, $payload['points'][0]['deathValue'], 'payload bucket should include death channel intensity');
assert_same(2, $payload['max'], 'payload max should reflect point intensity');
assert_same(10, $payload['points'][0]['topKillers'][0]['id'], 'payload bucket should include top killer id');
assert_same('Alpha', $payload['points'][0]['topKillers'][0]['name'], 'payload bucket should include top killer name');
assert_same(2, $payload['points'][0]['topKillers'][0]['count'], 'payload bucket should aggregate top killer count');
assert_same(20, $payload['points'][0]['topVictims'][0]['id'], 'payload bucket should include top victim id');
assert_same(2, count($payload['points'][0]['topVictims']), 'payload bucket should keep multiple victims');
assert_same(3, $payload['diagnostics']['queried'], 'payload diagnostics should include queried count');
assert_same(1, $payload['diagnostics']['outOfBounds'], 'payload diagnostics should include out-of-bounds count');
assert_same(0, $payload['diagnostics']['raw']['minX'], 'payload diagnostics should include raw min x');
assert_same(5000, $payload['diagnostics']['raw']['maxX'], 'payload diagnostics should include raw max x');
assert_same(32, $payload['diagnostics']['transformed']['minX'], 'payload diagnostics should include transformed min x');
assert_same(5032, $payload['diagnostics']['transformed']['maxX'], 'payload diagnostics should include transformed max x');
assert_same(2 / 3, $payload['diagnostics']['inBoundsRatio'], 'payload diagnostics should include in-bounds ratio');
assert_same(true, $payload['diagnostics']['manualRequired'], 'payload diagnostics should mark weak projection');
assert_same(32, $payload['diagnostics']['config']['xoffset'], 'payload diagnostics should include config xoffset');
assert_same(1280, $payload['diagnostics']['image']['width'], 'payload diagnostics should include image width');
assert_same('thermal', $payload['renderer']['mode'], 'payload renderer should default to thermal');
assert_same('sqrt', $payload['renderer']['normalization'], 'payload normalization should default to sqrt');
assert_same(16, strlen($payload['configHash']), 'payload should include compact config hash');

$semanticPayload = heatmap_build_payload(
    'cstrike',
    'de_dust2',
    array('url' => './hlstatsimg/games/cstrike/maps/de_dust2.jpg', 'width' => 1280, 'height' => 1024),
    array(),
    array('xoffset' => 0, 'yoffset' => 0, 'scale' => 1),
    array('renderer' => 'semantic', 'normalization' => 'log')
);
assert_same('semantic', $semanticPayload['renderer']['mode'], 'payload should accept semantic renderer');
assert_same('log', $semanticPayload['renderer']['normalization'], 'payload should accept log normalization');

$overviewConfig = heatmap_parse_overview(
    '"pos_x" "-1200"' . "\n" . '"pos_y" "2400"' . "\n" . '"scale" "4"' . "\n" . '"rotate" "1"',
    array('xoffset' => 0, 'yoffset' => 0, 'scale' => 1, 'flipx' => 0, 'flipy' => 0, 'rotate' => 0)
);
assert_same(1200, $overviewConfig['xoffset'], 'source overview should seed xoffset');
assert_same(2400, $overviewConfig['yoffset'], 'source overview should seed yoffset');
assert_same(1, $overviewConfig['rotate'], 'source overview should seed rotate');

echo "web heatmap smoke ok\n";
