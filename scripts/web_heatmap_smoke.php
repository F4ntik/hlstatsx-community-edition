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

function assert_true($actual, string $message): void
{
    assert_same(true, $actual === true, $message);
}

function assert_contains(string $needle, string $haystack, string $message): void
{
    assert_true(strpos($haystack, $needle) !== false, $message);
}

function assert_throws(string $expectedCode, callable $callback, string $message): void
{
    try {
        $callback();
    } catch (InvalidArgumentException $exception) {
        assert_same($expectedCode, $exception->getMessage(), $message);
        return;
    } catch (Throwable $exception) {
        fwrite(STDERR, $message . PHP_EOL);
        fwrite(STDERR, 'Expected InvalidArgumentException, got ' . get_class($exception) . PHP_EOL);
        exit(1);
    }

    fwrite(STDERR, $message . PHP_EOL);
    fwrite(STDERR, 'Expected InvalidArgumentException with code: ' . $expectedCode . PHP_EOL);
    exit(1);
}

function v2_query_input(array $overrides = array()): array
{
    return array_merge(array(
        'v' => '2',
        'game' => 'cstrike',
        'map' => 'de_dust2',
    ), $overrides);
}

function floor_fixture($id = 'ground', $zMin = 0, $zMax = 10, $labelEn = 'Ground', $labelRu = 'Зал'): array
{
    return array(
        'id' => $id,
        'label_en' => $labelEn,
        'label_ru' => $labelRu,
        'z_min' => $zMin,
        'z_max' => $zMax,
    );
}

function floor_fixture_json(array $floors): string
{
    $json = json_encode($floors, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
    assert_true($json !== false, 'floor fixture should encode to JSON');
    return $json;
}

function smoke_temp_directory(string $suffix): string
{
    $directory = sys_get_temp_dir() . '/hlstats-' . $suffix . '-' . bin2hex(random_bytes(8));
    assert_true(mkdir($directory, 0700, true), 'temporary directory should be created');
    return $directory;
}

function smoke_remove_directory(string $directory): void
{
    if (!is_dir($directory)) {
        return;
    }
    foreach (scandir($directory) ?: array() as $entry) {
        if ($entry === '.' || $entry === '..') {
            continue;
        }
        $path = $directory . DIRECTORY_SEPARATOR . $entry;
        if (is_dir($path) && !is_link($path)) {
            smoke_remove_directory($path);
        } else {
            @unlink($path);
        }
    }
    @rmdir($directory);
}

$explorerModeCases = array(
    array('input' => array(), 'mode' => 0),
    array('input' => array('HeatmapExplorerBeta' => 0), 'mode' => 0),
    array('input' => array('HeatmapExplorerBeta' => 1), 'mode' => 1),
    array('input' => array('HeatmapExplorerBeta' => 2), 'mode' => 2),
    array('input' => array('HeatmapExplorerBeta' => '0'), 'mode' => 0),
    array('input' => array('HeatmapExplorerBeta' => '1'), 'mode' => 1),
    array('input' => array('HeatmapExplorerBeta' => '2'), 'mode' => 2),
);
foreach ($explorerModeCases as $case) {
    assert_same($case['mode'], heatmap_explorer_mode($case['input']), 'explorer mode should accept only canonical 0/1/2 values');
}
foreach (array(false, true, '', ' ', '01', '1.0', '1e0', -1, 3, 1.5, array(1), new stdClass()) as $invalidMode) {
    assert_same(0, heatmap_explorer_mode(array('HeatmapExplorerBeta' => $invalidMode)), 'invalid explorer mode should fail closed');
}

$sceneKeyQuery = array(
    'game' => 'cstrike',
    'map' => 'de_dust2',
    'player' => 42,
    'lens' => 'overview',
    'event' => 'kills',
    'channel' => 'kills',
    'from' => 1700000000,
    'to' => 1700003600,
    'floor' => 'all',
    'lang' => 'en',
    'normalization' => 'sqrt',
);
$sceneKeyConfig = array(
    'code' => 'cstrike',
    'game' => 'cstrike',
    'realgame' => 'cstrike',
    'map' => 'de_dust2',
    'projectionHash' => 'projection-a',
    'floorConfigHash' => 'floor-a',
);
$sceneKeyImage = array(
    'url' => './hlstatsimg/games/cstrike/maps/de_dust2.jpg',
    'width' => 1024,
    'height' => 768,
    'source' => 'hlstatsimg',
    'sourceIdentity' => 'asset-a',
);
$sceneKey = heatmap_scene_cache_key($sceneKeyQuery, $sceneKeyConfig, $sceneKeyImage);
assert_true(preg_match('/^[a-f0-9]{64}$/D', $sceneKey) === 1, 'scene cache key should be a stable SHA-256 token');
$sceneKeyDimensions = array(
    array('query', 'schemaVersion', 3),
    array('query', 'game', 'arena'),
    array('query', 'realgame', 'arena-real'),
    array('query', 'map', 'de_nuke'),
    array('query', 'player', 84),
    array('query', 'lens', 'me'),
    array('query', 'event', 'deaths'),
    array('query', 'channel', 'deaths'),
    array('query', 'from', 1700000001),
    array('query', 'to', 1700003601),
    array('query', 'floor', 'upper'),
    array('query', 'lang', 'ru'),
    array('query', 'normalization', 'linear'),
    array('config', 'realgame', 'cstrike-real'),
    array('config', 'bucketVersion', 2),
    array('config', 'projectionHash', 'projection-b'),
    array('config', 'floorConfigHash', 'floor-b'),
    array('image', 'url', './map-b.jpg'),
    array('image', 'width', 2048),
    array('image', 'height', 2048),
    array('image', 'sourceIdentity', 'asset-b'),
);
foreach ($sceneKeyDimensions as $dimension) {
    $query = $sceneKeyQuery;
    $config = $sceneKeyConfig;
    $image = $sceneKeyImage;
    if ($dimension[0] === 'query') {
        $query[$dimension[1]] = $dimension[2];
    } elseif ($dimension[0] === 'config') {
        $config[$dimension[1]] = $dimension[2];
    } else {
        $image[$dimension[1]] = $dimension[2];
    }
    assert_true(
        $sceneKey !== heatmap_scene_cache_key($query, $config, $image),
        'scene cache key should include ' . $dimension[0] . '.' . $dimension[1]
    );
}
$reorderedQuery = array_reverse($sceneKeyQuery, true);
$reorderedConfig = array_reverse($sceneKeyConfig, true);
$reorderedImage = array_reverse($sceneKeyImage, true);
assert_same(
    $sceneKey,
    heatmap_scene_cache_key($reorderedQuery, $reorderedConfig, $reorderedImage),
    'scene cache key should be independent of associative insertion order'
);

$atomicDirectory = smoke_temp_directory('atomic');
$atomicPath = $atomicDirectory . '/scene.json';
assert_same(true, heatmap_atomic_write_json($atomicPath, array('state' => 'ok', 'version' => 1)), 'atomic writer should publish a complete JSON file');
$previousAtomicJson = file_get_contents($atomicPath);
assert_true(is_string($previousAtomicJson), 'atomic writer fixture should be readable');
$resource = fopen($atomicDirectory . '/resource', 'wb');
assert_true(is_resource($resource), 'atomic writer failure fixture should open a resource');
assert_same(false, heatmap_atomic_write_json($atomicPath, array('unsupported' => $resource)), 'JSON encoding failure should be reported');
fclose($resource);
assert_same($previousAtomicJson, file_get_contents($atomicPath), 'JSON encoding failure should preserve the previous complete file');
$renameFailurePath = $atomicPath . '/';
assert_same(false, heatmap_atomic_write_json($renameFailurePath, array('state' => 'replacement')), 'staging/rename failure should be reported');
assert_same($previousAtomicJson, file_get_contents($atomicPath), 'staging/rename failure should preserve the previous complete file');
smoke_remove_directory($atomicDirectory);

$cacheableStates = array('ok', 'empty', 'insufficient_sample');
foreach (array('ok', 'empty', 'insufficient_sample') as $state) {
    assert_same(true, heatmap_scene_state_is_cacheable($state), 'complete scene state should be cacheable: ' . $state);
}
foreach (array('missing_coordinates', 'floors_unavailable', 'weak_projection', 'too_many_events', 'explorer_disabled', 'rejected', 'unexpected_error', 'truncated', 'inspect') as $state) {
    assert_same(false, heatmap_scene_state_is_cacheable($state), 'non-complete scene state should not be cacheable: ' . $state);
}
assert_same($cacheableStates, array_values(array_filter(
    array('ok', 'empty', 'insufficient_sample', 'missing_coordinates'),
    'heatmap_scene_state_is_cacheable'
)), 'cacheable state allowlist should remain exact');

$pruneDirectory = smoke_temp_directory('prune');
$pruneNow = 2000000000;
$pruneCutoff = $pruneNow - 172800;
file_put_contents($pruneDirectory . '/old-a.json', '{}');
file_put_contents($pruneDirectory . '/old-b.json', '{}');
file_put_contents($pruneDirectory . '/boundary.json', '{}');
file_put_contents($pruneDirectory . '/new.json', '{}');
file_put_contents($pruneDirectory . '/not-json.txt', '{}');
file_put_contents($pruneDirectory . '/stage.tmp', '{}');
mkdir($pruneDirectory . '/nested', 0700, true);
file_put_contents($pruneDirectory . '/nested/nested.json', '{}');
touch($pruneDirectory . '/old-a.json', $pruneCutoff - 2);
touch($pruneDirectory . '/old-b.json', $pruneCutoff - 1);
touch($pruneDirectory . '/boundary.json', $pruneCutoff);
touch($pruneDirectory . '/new.json', $pruneNow);
assert_same(1, heatmap_prune_payload_cache($pruneDirectory, $pruneNow, 1), 'pruner should honor the bounded delete limit and oldest order');
assert_true(!is_file($pruneDirectory . '/old-a.json'), 'pruner should delete the oldest eligible direct JSON');
assert_true(is_file($pruneDirectory . '/old-b.json'), 'pruner should retain eligible JSON beyond the limit');
assert_true(is_file($pruneDirectory . '/boundary.json'), 'pruner should retain the exact 48-hour age boundary');
assert_true(is_file($pruneDirectory . '/not-json.txt'), 'pruner should ignore non-JSON entries');
assert_true(is_file($pruneDirectory . '/stage.tmp'), 'pruner should ignore staging entries');
assert_true(is_file($pruneDirectory . '/nested/nested.json'), 'pruner should never recurse into subdirectories');
for ($index = 0; $index < 40; $index++) {
    $path = $pruneDirectory . '/bulk-' . $index . '.json';
    file_put_contents($path, '{}');
    touch($path, $pruneCutoff - 100 - $index);
}
assert_same(32, heatmap_prune_payload_cache($pruneDirectory, $pruneNow, 999), 'pruner should cap one pass at 32 files');
if (function_exists('symlink')) {
    $symlinkTarget = $pruneDirectory . '/symlink-target.json';
    $symlinkPath = $pruneDirectory . '/symlink.json';
    file_put_contents($symlinkTarget, '{}');
    touch($symlinkTarget, $pruneCutoff - 10);
    if (@symlink($symlinkTarget, $symlinkPath)) {
        heatmap_prune_payload_cache($pruneDirectory, $pruneNow, 1);
        assert_true(is_link($symlinkPath), 'pruner should ignore symlink entries');
        assert_true(is_file($symlinkTarget), 'pruner should not delete a symlink target');
        @unlink($symlinkPath);
    }
}
smoke_remove_directory($pruneDirectory);

$logFields = array(
    'version' => 2,
    'operation' => 'scene',
    'game' => 'cstrike',
    'map' => 'de_dust2',
    'windowClass' => 'preset',
    'lens' => 'overview',
    'floor' => 'all',
    'rowsRead' => 12,
    'binsReturned' => 4,
    'rawPayloadBytes' => 512,
    'queryMs' => 12.5,
    'totalMs' => INF,
    'cache' => 'miss',
    'xyCoverage' => 0.75,
    'zCoverage' => NAN,
    'projectionCoverage' => 1.5,
    'state' => 'ok',
    'fallbackReason' => '',
    'playerId' => 42,
    'ip' => '198.51.100.1',
    'sql' => 'SELECT secret',
);
$logJson = heatmap_request_log($logFields);
$logPayload = json_decode($logJson, true);
assert_true(is_array($logPayload), 'request log should be valid JSON');
assert_same(
    array('version', 'operation', 'game', 'map', 'windowClass', 'lens', 'floor', 'rowsRead', 'binsReturned', 'rawPayloadBytes', 'queryMs', 'totalMs', 'cache', 'xyCoverage', 'zCoverage', 'projectionCoverage', 'state', 'fallbackReason'),
    array_keys($logPayload),
    'request log should emit only the stable allowlist in order'
);
assert_true(strpos($logJson, '198.51.100.1') === false, 'request log should not expose IP values');
assert_true(strpos($logJson, 'SELECT') === false, 'request log should not expose SQL values');
assert_true(is_finite(floatval($logPayload['totalMs'])), 'request log should normalize non-finite numbers');
assert_true(floatval($logPayload['projectionCoverage']) <= 1.0, 'request log should bound coverage values');

$routeSource = file_get_contents(ROOT_PATH . '/heatmap_points.php');
assert_true($routeSource !== false, 'heatmap route should be readable');
assert_contains("\$container = require __DIR__ . '/bootstrap.php';", $routeSource, 'route should bootstrap before selecting v1 or v2');
assert_contains('OptionService::class', $routeSource, 'route should load options before selecting v1 or v2');
assert_contains("\$_GET['v'] !== '2'", $routeSource, 'route should split only on exact v=2');
assert_contains('explorer_disabled', $routeSource, 'disabled v2 mode should publish the stable disabled state');
assert_contains('heatmap_build_scene(', $routeSource, 'v2 route should delegate scene construction to the Task 4 builder');
assert_contains('heatmap_atomic_write_json', $routeSource . file_get_contents(ROOT_PATH . '/includes/heatmap_points.php'), 'route path should use the atomic cache writer');
assert_true(substr_count($routeSource, 'heatmap_v2_emit(') >= 2, 'v2 responses should pass through one encode/log emission helper');

$heatmapIncludeSource = file_get_contents(ROOT_PATH . '/includes/heatmap_points.php');
assert_true($heatmapIncludeSource !== false, 'heatmap include should be readable');
assert_true(strpos($heatmapIncludeSource, 'COALESCE(hef.pos_victim_x') === false, 'v1 death SQL should never fall back to attacker X');
assert_true(strpos($heatmapIncludeSource, 'COALESCE(hef.pos_victim_y') === false, 'v1 death SQL should never fall back to attacker Y');
assert_contains("hef.pos_victim_x IS NOT NULL AND hef.pos_victim_y IS NOT NULL", $heatmapIncludeSource, 'v1 death SQL should require victim XY');

$installSql = file_get_contents(dirname(__DIR__) . '/sql/install.sql');
assert_true($installSql !== false, 'installer SQL should be readable');
assert_contains('SET @DBVERSION="81";', $installSql, 'fresh install should set dbversion 81');
assert_true(
    preg_match(
        "/`cropy2` int\\(11\\) NOT NULL default '0',\\s+`floors_json` TEXT NULL,/",
        $installSql
    ) === 1,
    'fresh heatmap config should place nullable floors_json after cropy2'
);
assert_true(
    preg_match(
        '/CREATE TABLE IF NOT EXISTS `hlstats_Heatmap_Config` \\(.*?\\) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4/s',
        $installSql
    ) === 1,
    'fresh heatmap config should use InnoDB'
);
assert_contains("('HeatmapExplorerBeta', '0',2)", $installSql, 'fresh options should include the beta rollout flag');
assert_same(4, substr_count($installSql, 'HeatmapExplorerBeta'), 'fresh install should define one beta flag and three choices');
foreach (array(
    "('HeatmapExplorerBeta', '0', 'Off', 1)",
    "('HeatmapExplorerBeta', '1', 'Opt-in', 0)",
    "('HeatmapExplorerBeta', '2', 'Default', 0)",
) as $choice) {
    assert_contains($choice, $installSql, 'fresh install should define the expected beta choice');
}

$updater80Path = ROOT_PATH . '/updater/80.php';
assert_true(is_file($updater80Path), 'updater 80 bridge should exist');
$updater80 = file_get_contents($updater80Path);
assert_true($updater80 !== false, 'updater 80 bridge should be readable');
assert_contains("defined('IN_UPDATER')", $updater80, 'updater 80 should guard direct access');
assert_contains('$dbversion = 80;', $updater80, 'updater 80 should set dbversion 80');
assert_contains('$version = "1.7.0";', $updater80, 'updater 80 should set product version 1.7.0');
assert_same(2, substr_count($updater80, '$db->query('), 'updater 80 should update only version state');
assert_contains("`keyname` = 'version'", $updater80, 'updater 80 should update product version');
assert_contains("`keyname` = 'dbversion'", $updater80, 'updater 80 should update dbversion');
assert_true(strpos($updater80, 'ALTER TABLE') === false, 'updater 80 should remain a schema no-op');
assert_true(strpos($updater80, 'INSERT ') === false, 'updater 80 should not add data');

$updater81Path = ROOT_PATH . '/updater/81.php';
assert_true(is_file($updater81Path), 'updater 81 migration should exist');
$updater81 = file_get_contents($updater81Path);
assert_true($updater81 !== false, 'updater 81 migration should be readable');
assert_contains("defined('IN_UPDATER')", $updater81, 'updater 81 should guard direct access');
assert_contains('$dbversion = 81;', $updater81, 'updater 81 should set dbversion 81');
assert_contains('$version = "1.7.0";', $updater81, 'updater 81 should set product version 1.7.0');

$columnCheck = strpos($updater81, "SHOW COLUMNS FROM hlstats_Heatmap_Config LIKE 'floors_json'");
$columnAdd = strpos($updater81, 'ALTER TABLE `hlstats_Heatmap_Config` ADD `floors_json` TEXT NULL AFTER `cropy2`');
assert_true(
    $columnCheck !== false
        && $columnAdd !== false
        && $columnCheck < $columnAdd
        && strpos($updater81, '$db->fetch_row(', $columnCheck) !== false,
    'updater 81 should check for floors_json before adding it'
);

$tableCheck = strpos($updater81, "SHOW TABLE STATUS LIKE 'hlstats_Heatmap_Config'");
$engineCheck = strpos($updater81, '$tableStatus[\'Engine\']');
$engineConvert = strpos($updater81, 'ALTER TABLE `hlstats_Heatmap_Config` ENGINE=InnoDB');
assert_true(
    $tableCheck !== false
        && $engineCheck !== false
        && $engineConvert !== false
        && $tableCheck < $engineCheck
        && $engineCheck < $engineConvert,
    'updater 81 should inspect the associative table engine before conversion'
);
assert_contains('$db->fetch_array(', $updater81, 'updater 81 should use the existing associative database API');
assert_contains('if ($tableStatus &&', $updater81, 'updater 81 should only convert an existing non-InnoDB table');
assert_contains("!== 'innodb'", $updater81, 'updater 81 should leave InnoDB untouched');

$optionInsert = strpos($updater81, 'INSERT IGNORE INTO `hlstats_Options`');
$choiceInsert = strpos($updater81, 'INSERT IGNORE INTO `hlstats_Options_Choices`');
$versionUpdate = strpos($updater81, "`keyname` = 'version'");
$dbversionUpdate = strpos($updater81, "`keyname` = 'dbversion'");
assert_true(
    $optionInsert !== false
        && $choiceInsert !== false
        && $versionUpdate !== false
        && $dbversionUpdate !== false
        && $optionInsert < $choiceInsert
        && $choiceInsert < $versionUpdate
        && $versionUpdate < $dbversionUpdate
        && strrpos($updater81, '$db->query(') < $dbversionUpdate,
    'updater 81 should finish with dbversion after schema and rollout data'
);
assert_contains("('HeatmapExplorerBeta', '0', 2)", $updater81, 'updater 81 should insert the beta rollout flag idempotently');
foreach (array(
    "('HeatmapExplorerBeta', '0', 'Off', 1)",
    "('HeatmapExplorerBeta', '1', 'Opt-in', 0)",
    "('HeatmapExplorerBeta', '2', 'Default', 0)",
) as $choice) {
    assert_contains($choice, $updater81, 'updater 81 should insert each beta choice idempotently');
}

assert_same('de_dust2', heatmap_clean_token('de_dust2'), 'valid map token should pass');
assert_same('$2000$', heatmap_clean_token('$2000$'), 'dollar map token should pass');
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
assert_same(1.0, heatmap_scale(0), 'zero scale should use the safe default');
assert_same(1.0, heatmap_scale(-2), 'negative scale should use the safe default');

$rotated = heatmap_transform_point(
    array('pos_x' => 10, 'pos_y' => 20),
    array('xoffset' => 0, 'yoffset' => 0, 'flipx' => 0, 'flipy' => 0, 'scale' => 1, 'rotate' => 1, 'cropx1' => 5, 'cropy1' => 7, 'cropx2' => 200, 'cropy2' => 200)
);
assert_same(-25, $rotated['x'], 'x transform should rotate before crop');
assert_same(3, $rotated['y'], 'y transform should rotate before crop');

$halfTurn = heatmap_transform_point(
    array('pos_x' => 10, 'pos_y' => 20),
    array('xoffset' => 0, 'yoffset' => 0, 'flipx' => 0, 'flipy' => 0, 'scale' => 1, 'rotate' => 2)
);
assert_same(-10, $halfTurn['x'], 'x transform should support 180 degree rotation');
assert_same(-20, $halfTurn['y'], 'y transform should support 180 degree rotation');

$threeQuarterTurn = heatmap_transform_point(
    array('pos_x' => 10, 'pos_y' => 20),
    array('xoffset' => 0, 'yoffset' => 0, 'flipx' => 0, 'flipy' => 0, 'scale' => 1, 'rotate' => 3)
);
assert_same(20, $threeQuarterTurn['x'], 'x transform should support 270 degree rotation');
assert_same(-10, $threeQuarterTurn['y'], 'y transform should support 270 degree rotation');

$rotatedPoint = array('x' => 17, 'y' => -29);
for ($steps = 0; $steps < 4; $steps++) {
    $once = heatmap_rotate_point($rotatedPoint['x'], $rotatedPoint['y'], $steps);
    $inverse = heatmap_unrotate_point($once['x'], $once['y'], $steps);
    assert_same($rotatedPoint, $inverse, 'rotate/unrotate should be inverse for every quarter turn');
    $four = $once;
    for ($i = 1; $i < 4; $i++) {
        $four = heatmap_rotate_point($four['x'], $four['y'], $steps);
    }
    assert_same($rotatedPoint, $four, 'four repeated rotations should return to the original point');
}

$normalizedCrop = heatmap_normalize_crop(
    array('cropx1' => 90, 'cropy1' => -5, 'cropx2' => 50, 'cropy2' => 100),
    100,
    80
);
assert_same(90, $normalizedCrop['cropx1'], 'crop origin should be clamped to image width');
assert_same(0, $normalizedCrop['cropy1'], 'crop origin should be clamped to image height');
assert_same(10, $normalizedCrop['cropx2'], 'crop width should be clamped to image bounds');
assert_same(80, $normalizedCrop['cropy2'], 'crop height should be clamped to image bounds');

$cropPayload = heatmap_build_payload(
    'cstrike',
    'de_dust2',
    array('url' => 'heatmap_map.php', 'width' => 100, 'height' => 80, 'sourceWidth' => 100, 'sourceHeight' => 80, 'source' => 'heatmaps/src'),
    array(
        array('pos_x' => 95, 'pos_y' => 10, 'value' => 1),
        array('pos_x' => 50, 'pos_y' => 10, 'value' => 1),
    ),
    array('xoffset' => 0, 'yoffset' => 0, 'scale' => 1, 'cropx1' => 90, 'cropy1' => 0, 'cropx2' => 50, 'cropy2' => 80)
);
assert_same(10, $cropPayload['image']['width'], 'payload image width should match normalized crop');
assert_same(array('x' => 90, 'y' => 0, 'width' => 10, 'height' => 80), $cropPayload['image']['crop'], 'payload crop should match normalized crop');
assert_same(1, count($cropPayload['points']), 'payload should use the effective cropped canvas');
assert_same(5, $cropPayload['points'][0]['x'], 'payload point should subtract crop origin');

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

$projection = heatmap_projection_config(array('rotate' => 7));
assert_same(3, $projection['rotate'], 'projection config should normalize rotate to quarter turns');

$queryNow = 1700000123;
$presetCases = array(
    array('range' => '7d', 'from' => 1699395300, 'to' => 1700000100),
    array('range' => '30d', 'from' => 1697408100, 'to' => 1700000100),
    array('range' => '90d', 'from' => 1692224100, 'to' => 1700000100),
    array('range' => '365d', 'from' => 1668464100, 'to' => 1700000100),
);
foreach ($presetCases as $case) {
    $query = heatmap_parse_v2_query(v2_query_input(array('range' => $case['range'])), $queryNow);
    assert_same($case['from'], $query['from'], 'preset should use the documented start boundary: ' . $case['range']);
    assert_same($case['to'], $query['to'], 'preset should align end to a 15-minute boundary: ' . $case['range']);
}

$defaultQuery = heatmap_parse_v2_query(v2_query_input(), $queryNow);
assert_same('cstrike', $defaultQuery['game'], 'v2 query should preserve the game token');
assert_same('de_dust2', $defaultQuery['map'], 'v2 query should preserve the map token');
assert_same(0, $defaultQuery['player'], 'v2 query should default player to zero');
assert_same(1697408100, $defaultQuery['from'], 'v2 query should default to the 30-day start');
assert_same(1700000100, $defaultQuery['to'], 'v2 query should default to the aligned end');
assert_same('both', $defaultQuery['event'], 'v2 query should default to both channels');
assert_same('overview', $defaultQuery['lens'], 'v2 query should default to overview lens');
assert_same('all', $defaultQuery['floor'], 'v2 query should default to all floors');
assert_same('en', $defaultQuery['lang'], 'v2 query should default to English');
assert_true(!array_key_exists('inspect', $defaultQuery), 'v2 query should omit inspect when none was requested');
assert_same(
    $defaultQuery,
    heatmap_parse_v2_query(v2_query_input(), $queryNow),
    'v2 query should be deterministic for an injected historical now'
);
$maximumPublicPlayerQuery = heatmap_parse_v2_query(
    v2_query_input(array('player' => '4294967295', 'lens' => 'me')),
    $queryNow
);
assert_same(4294967295, $maximumPublicPlayerQuery['player'], 'maximum MySQL unsigned player id should remain valid');

$customQuery = heatmap_parse_v2_query(
    v2_query_input(array('from' => '1699990000', 'to' => '1700000001')),
    $queryNow
);
assert_same(1699990000, $customQuery['from'], 'custom window should keep its exact inclusive start');
assert_same(1700000001, $customQuery['to'], 'custom window should keep its exact exclusive end');

$maximumWindow = heatmap_parse_v2_query(
    v2_query_input(array('from' => '1384640400', 'to' => '1700000400')),
    $queryNow
);
assert_same(1384640400, $maximumWindow['from'], 'the exact 3650-day custom window should be accepted');
assert_same(1700000400, $maximumWindow['to'], 'the exact 3650-day custom window should retain its end');

$v2InvalidCases = array(
    array('name' => 'v2 version is required', 'input' => array('game' => 'cstrike', 'map' => 'de_dust2'), 'code' => 'invalid_query'),
    array('name' => 'v2 version must be canonical', 'input' => v2_query_input(array('v' => '02')), 'code' => 'invalid_query'),
    array('name' => 'game token cannot be empty', 'input' => v2_query_input(array('game' => '')), 'code' => 'invalid_query'),
    array('name' => 'map token cannot be empty', 'input' => v2_query_input(array('map' => '')), 'code' => 'invalid_query'),
    array('name' => 'game token must be bounded and safe', 'input' => v2_query_input(array('game' => '../cstrike')), 'code' => 'invalid_query'),
    array('name' => 'map token must be bounded', 'input' => v2_query_input(array('map' => str_repeat('a', 65))), 'code' => 'invalid_query'),
    array('name' => 'unknown query key is rejected', 'input' => v2_query_input(array('sort' => 'eventTime')), 'code' => 'invalid_query'),
    array('name' => 'array query value is rejected', 'input' => v2_query_input(array('player' => array('1'))), 'code' => 'invalid_query'),
    array('name' => 'object query value is rejected', 'input' => v2_query_input(array('map' => new stdClass())), 'code' => 'invalid_query'),
    array('name' => 'range and custom window cannot mix', 'input' => v2_query_input(array('range' => '30d', 'from' => '1699990000', 'to' => '1700000001')), 'code' => 'invalid_window'),
    array('name' => 'custom window requires both bounds', 'input' => v2_query_input(array('from' => '1699990000')), 'code' => 'invalid_window'),
    array('name' => 'custom window rejects a lone end bound', 'input' => v2_query_input(array('to' => '1700000001')), 'code' => 'invalid_window'),
    array('name' => 'custom window must be half-open with increasing bounds', 'input' => v2_query_input(array('from' => '1700000001', 'to' => '1700000001')), 'code' => 'invalid_window'),
    array('name' => 'custom window rejects a reversed interval', 'input' => v2_query_input(array('from' => '1700000002', 'to' => '1700000001')), 'code' => 'invalid_window'),
    array('name' => 'custom window cannot exceed 3650 days', 'input' => v2_query_input(array('from' => '1384640399', 'to' => '1700000400')), 'code' => 'invalid_window'),
    array('name' => 'custom window cannot end more than five minutes in the future', 'input' => v2_query_input(array('from' => '1700000000', 'to' => '1700000424')), 'code' => 'invalid_window'),
    array('name' => 'custom window integers must be canonical', 'input' => v2_query_input(array('from' => '01699990000', 'to' => '1700000001')), 'code' => 'invalid_window'),
    array('name' => 'explicit zero player is rejected', 'input' => v2_query_input(array('player' => '0')), 'code' => 'invalid_player'),
    array('name' => 'player integer cannot have a leading zero', 'input' => v2_query_input(array('player' => '01')), 'code' => 'invalid_player'),
    array('name' => 'player cannot exceed MySQL unsigned int', 'input' => v2_query_input(array('player' => '4294967296')), 'code' => 'invalid_player'),
    array('name' => 'PHP integer maximum is not a public player id', 'input' => v2_query_input(array('player' => strval(PHP_INT_MAX))), 'code' => 'invalid_player'),
    array('name' => 'me lens needs a player', 'input' => v2_query_input(array('lens' => 'me')), 'code' => 'player_required'),
    array('name' => 'difference lens needs a player', 'input' => v2_query_input(array('lens' => 'difference', 'event' => 'kills')), 'code' => 'player_required'),
    array('name' => 'difference lens cannot combine channels', 'input' => v2_query_input(array('player' => '4', 'lens' => 'difference', 'event' => 'both')), 'code' => 'difference_channel_required'),
    array('name' => 'event must be one published channel', 'input' => v2_query_input(array('event' => 'kill')), 'code' => 'invalid_event'),
    array('name' => 'lens must be published', 'input' => v2_query_input(array('lens' => 'team')), 'code' => 'invalid_lens'),
    array('name' => 'language must be supported', 'input' => v2_query_input(array('lang' => 'de')), 'code' => 'invalid_language'),
    array('name' => 'floor identifier must be safe', 'input' => v2_query_input(array('floor' => 'upper floor')), 'code' => 'invalid_floor'),
    array('name' => 'inspect must use a nonnegative grid cell id', 'input' => v2_query_input(array('inspect' => 'c-1.0')), 'code' => 'invalid_inspect'),
    array('name' => 'inspect coordinates must be canonical', 'input' => v2_query_input(array('inspect' => 'c01.0')), 'code' => 'invalid_inspect'),
);
foreach ($v2InvalidCases as $case) {
    assert_throws($case['code'], function () use ($case, $queryNow): void {
        heatmap_parse_v2_query($case['input'], $queryNow);
    }, 'v2 query should reject ' . $case['name']);
}

$inspectQuery = heatmap_parse_v2_query(v2_query_input(array('inspect' => 'c0.12')), $queryNow);
assert_same('c0.12', $inspectQuery['inspect'], 'v2 query should retain a syntactically valid inspect cell id');

foreach (array(null, '', '   ', '[]') as $emptyFloorsJson) {
    assert_same(array(), heatmap_parse_floor_config($emptyFloorsJson), 'empty floor metadata should represent the all-floors map');
}

$canonicalFloors = array(
    floor_fixture('basement', -10, 0, 'Basement', 'Подвал'),
    floor_fixture('ground', 0, 10, 'Ground', 'Зал'),
    floor_fixture('upper', 10, 20, 'Upper', 'Верх'),
);
$unorderedFloorsJson = floor_fixture_json(array(
    $canonicalFloors[2],
    $canonicalFloors[0],
    $canonicalFloors[1],
));
assert_same(
    $canonicalFloors,
    heatmap_parse_floor_config($unorderedFloorsJson),
    'floor metadata should sort non-overlapping adjacent bands canonically'
);

$eightFloors = array();
for ($index = 0; $index < 8; $index++) {
    $eightFloors[] = floor_fixture('f' . $index, $index * 10, ($index + 1) * 10, 'Floor ' . $index, 'Этаж ' . $index);
}
assert_same(8, count(heatmap_parse_floor_config(floor_fixture_json($eightFloors))), 'floor metadata should allow exactly eight bands');
$nineFloors = $eightFloors;
$nineFloors[] = floor_fixture('f8', 80, 90, 'Floor 8', 'Этаж 8');

$floorInvalidCases = array(
    array('name' => 'JSON null is not a floor list', 'json' => 'null'),
    array('name' => 'malformed JSON', 'json' => '[{'),
    array('name' => 'root object instead of list', 'json' => floor_fixture_json(floor_fixture())),
    array('name' => 'more than eight bands', 'json' => floor_fixture_json($nineFloors)),
    array('name' => 'invalid id', 'json' => floor_fixture_json(array(floor_fixture('1ground')))),
    array('name' => 'missing required label', 'json' => floor_fixture_json(array(array(
        'id' => 'ground',
        'label_en' => 'Ground',
        'z_min' => 0,
        'z_max' => 10,
    )))),
    array('name' => 'untrimmed label', 'json' => floor_fixture_json(array(floor_fixture('ground', 0, 10, ' Ground ')))),
    array('name' => 'too long label', 'json' => floor_fixture_json(array(floor_fixture('ground', 0, 10, str_repeat('x', 65))))),
    array('name' => 'invalid UTF-8 label', 'json' => "[{\"id\":\"ground\",\"label_en\":\"\xC3\x28\",\"label_ru\":\"Зал\",\"z_min\":0,\"z_max\":10}]"),
    array('name' => 'control character label', 'json' => '[{"id":"ground","label_en":"Ground\\u0001","label_ru":"Зал","z_min":0,"z_max":10}]'),
    array('name' => 'right-to-left override format control label', 'json' => '[{"id":"ground","label_en":"Ground\\u202E","label_ru":"Зал","z_min":0,"z_max":10}]'),
    array('name' => 'left-to-right isolate format control label', 'json' => '[{"id":"ground","label_en":"Ground","label_ru":"Зал\\u2066","z_min":0,"z_max":10}]'),
    array('name' => 'unknown floor field', 'json' => floor_fixture_json(array(array_merge(floor_fixture(), array('image' => 'client.png'))))),
    array('name' => 'duplicate id', 'json' => floor_fixture_json(array(floor_fixture('ground', 0, 10), floor_fixture('ground', 10, 20)))),
    array('name' => 'string z bound', 'json' => floor_fixture_json(array(floor_fixture('ground', '0', 10)))),
    array('name' => 'float z bound', 'json' => floor_fixture_json(array(floor_fixture('ground', 0.0, 10)))),
    array('name' => 'boolean z bound', 'json' => floor_fixture_json(array(floor_fixture('ground', true, 10)))),
    array('name' => 'null z bound', 'json' => floor_fixture_json(array(floor_fixture('ground', null, 10)))),
    array('name' => 'out of range low z bound', 'json' => floor_fixture_json(array(floor_fixture('ground', -8388609, 10)))),
    array('name' => 'out of range high z bound', 'json' => floor_fixture_json(array(floor_fixture('ground', 0, 8388608)))),
    array('name' => 'empty z interval', 'json' => floor_fixture_json(array(floor_fixture('ground', 0, 0)))),
    array('name' => 'reversed z interval', 'json' => floor_fixture_json(array(floor_fixture('ground', 10, 0)))),
    array('name' => 'overlapping bands', 'json' => floor_fixture_json(array(floor_fixture('lower', 0, 10), floor_fixture('upper', 9, 20)))),
);
foreach ($floorInvalidCases as $case) {
    assert_throws('invalid_floor_config', function () use ($case): void {
        heatmap_parse_floor_config($case['json']);
    }, 'floor parser should reject ' . $case['name']);
}

$floorAssignmentCases = array(
    array('z' => -10, 'floor' => 'basement'),
    array('z' => -1, 'floor' => 'basement'),
    array('z' => '0', 'floor' => 'ground'),
    array('z' => 9, 'floor' => 'ground'),
    array('z' => 10, 'floor' => 'upper'),
    array('z' => 19, 'floor' => 'upper'),
    array('z' => 20, 'floor' => null),
    array('z' => null, 'floor' => null),
    array('z' => 'xy-only', 'floor' => null),
    array('z' => 1.5, 'floor' => null),
    array('z' => 8388608, 'floor' => null),
);
foreach ($floorAssignmentCases as $case) {
    assert_same(
        $case['floor'],
        heatmap_assign_floor($case['z'], $canonicalFloors),
        'floor assignment should use exact half-open Z bands'
    );
}
assert_same('all', heatmap_validate_requested_floor('all', $canonicalFloors), 'all should remain valid for any floor configuration');
assert_same('ground', heatmap_validate_requested_floor('ground', $canonicalFloors), 'configured floor id should remain valid');
assert_throws('unknown_floor', function () use ($canonicalFloors): void {
    heatmap_validate_requested_floor('roof', $canonicalFloors);
}, 'unconfigured floor id should fail closed');

$floorConfig = array(
    'game' => 'cstrike',
    'map' => 'de_dust2',
    'xoffset' => 0,
    'yoffset' => 0,
    'scale' => 1,
    'floors_json' => $unorderedFloorsJson,
);
$mergedFloorConfig = heatmap_merge_config_override($floorConfig, array());
$canonicalFloorsJson = '[{"id":"basement","label_en":"Basement","label_ru":"Подвал","z_min":-10,"z_max":0},{"id":"ground","label_en":"Ground","label_ru":"Зал","z_min":0,"z_max":10},{"id":"upper","label_en":"Upper","label_ru":"Верх","z_min":10,"z_max":20}]';
assert_same($canonicalFloors, $mergedFloorConfig['floors'], 'config merge should expose parsed canonical floors');
assert_same($canonicalFloorsJson, $mergedFloorConfig['floors_json'], 'config merge should store deterministic canonical floor JSON');
$roundTrippedConfig = heatmap_merge_config_override($mergedFloorConfig, array('floors_json' => $mergedFloorConfig['floors_json']));
assert_same($mergedFloorConfig['floors'], $roundTrippedConfig['floors'], 'floor config should round trip through merge');
assert_same($mergedFloorConfig['floors_json'], $roundTrippedConfig['floors_json'], 'floor JSON should round trip without formatting drift');
assert_same($canonicalFloors, heatmap_projection_config($roundTrippedConfig)['floors'], 'projection config should retain canonical floors');
assert_same(
    heatmap_config_hash($mergedFloorConfig),
    heatmap_config_hash($roundTrippedConfig),
    'equivalent floor configs should share a cache identity'
);
$changedFloorConfig = heatmap_merge_config_override(
    array('game' => 'cstrike', 'map' => 'de_dust2', 'floors_json' => '[]'),
    array('floors_json' => floor_fixture_json(array(floor_fixture('ground', 0, 11))))
);
assert_true(
    heatmap_config_hash($mergedFloorConfig) !== heatmap_config_hash($changedFloorConfig),
    'floor changes should invalidate the config hash'
);
assert_throws('invalid_floor_config', function () use ($floorConfig): void {
    heatmap_merge_config_override($floorConfig, array('floors' => array(floor_fixture('ground', 0.0, 10))));
}, 'config merge should retain native float Z type violations');
assert_throws('invalid_floor_config', function () use ($floorConfig): void {
    heatmap_merge_config_override($floorConfig, array('floors_json' => '{"not":"a list"}'));
}, 'config merge should fail closed for invalid floor storage');

function scene_query(array $overrides = array()): array
{
    return array_merge(array(
        'game' => 'cstrike',
        'map' => 'de_dust2',
        'player' => 42,
        'from' => 1700000000,
        'to' => 1700003600,
        'event' => 'both',
        'lens' => 'overview',
        'floor' => 'all',
        'lang' => 'en',
    ), $overrides);
}

function scene_config(array $overrides = array()): array
{
    return array_merge(array(
        'code' => 'cstrike',
        'game' => 'cstrike',
        'realgame' => 'cstrike',
        'map' => 'de_dust2',
        'xoffset' => 0,
        'yoffset' => 0,
        'flipx' => 0,
        'flipy' => 0,
        'rotate' => 0,
        'scale' => 1,
        'cropx1' => 0,
        'cropy1' => 0,
        'cropx2' => 0,
        'cropy2' => 0,
        'floors' => array(
            floor_fixture('lower', 0, 10, 'Lower', 'Lower'),
            floor_fixture('upper', 10, 20, 'Upper', 'Upper'),
        ),
    ), $overrides);
}

function scene_image(array $overrides = array()): array
{
    return array_merge(array(
        'url' => './hlstatsimg/games/cstrike/maps/de_dust2.jpg',
        'width' => 128,
        'height' => 128,
    ), $overrides);
}

function scene_row(array $overrides = array()): array
{
    return array_merge(array(
        'eventId' => '1',
        'eventTime' => '2026-01-01 00:00:00',
        'killerId' => '42',
        'victimId' => '84',
        'weapon' => 'ak47',
        'headshot' => '0',
        'teamkill' => '0',
        'attackerX' => '8',
        'attackerY' => '8',
        'attackerZ' => '5',
        'victimX' => '12',
        'victimY' => '4',
        'victimZ' => '15',
    ), $overrides);
}

function scene_payload(array $rows, array $query = array(), array $config = array(), array $image = array()): array
{
    $state = array(
        'query' => scene_query($query),
        'config' => scene_config($config),
        'image' => scene_image($image),
        'excludedSuicides' => 2,
    );
    foreach ($rows as $row) {
        heatmap_accumulate_scene_row($state, $row);
    }

    return heatmap_finalize_scene($state);
}

function scene_layer_row(array $rows, string $cell): array
{
    foreach ($rows as $row) {
        if ($row[0] === $cell) {
            return $row;
        }
    }

    fwrite(STDERR, 'missing expected scene cell: ' . $cell . PHP_EOL);
    exit(1);
}

function assert_float_close(float $expected, float $actual, string $message): void
{
    assert_true(abs($expected - $actual) < 0.000000001, $message);
}

$sceneSql = heatmap_build_scene_sql(scene_query(), scene_config());
assert_same(250001, $sceneSql['limit'], 'scene SQL should retain exactly one overflow sentinel');
assert_same(1, substr_count($sceneSql['sql'], 'UNION ALL'), 'scene SQL should union Frags and Teamkills exactly once');
assert_same(1, substr_count($sceneSql['sql'], 'hlstats_Events_Frags'), 'scene SQL should select Frags exactly once');
assert_same(1, substr_count($sceneSql['sql'], 'hlstats_Events_Teamkills'), 'scene SQL should select Teamkills exactly once');
assert_contains('hef.map = :frags_map', $sceneSql['sql'], 'Frags branch should filter the exact map');
assert_contains('hs.game = :frags_game', $sceneSql['sql'], 'Frags branch should filter the exact server game');
assert_contains('hef.eventTime >= FROM_UNIXTIME(:frags_from)', $sceneSql['sql'], 'Frags branch should retain the half-open lower time boundary');
assert_contains('hef.eventTime < FROM_UNIXTIME(:frags_to)', $sceneSql['sql'], 'Frags branch should retain the half-open upper time boundary');
assert_contains('hef.eventTime >= FROM_UNIXTIME(:teamkills_from)', $sceneSql['sql'], 'Teamkills branch should use branch-specific lower-bound parameters');
assert_contains('hef.eventTime < FROM_UNIXTIME(:teamkills_to)', $sceneSql['sql'], 'Teamkills branch should use branch-specific upper-bound parameters');
assert_true(strpos($sceneSql['sql'], 'COALESCE(') === false, 'scene SQL should never substitute attacker coordinates for a victim');
assert_true(strpos($sceneSql['sql'], 'killerId = :') === false, 'scene SQL should not pre-filter the personal kill lens');
assert_true(strpos($sceneSql['sql'], 'victimId = :') === false, 'scene SQL should not pre-filter the personal death lens');
assert_same(array(
    'frags_map' => 'de_dust2',
    'frags_game' => 'cstrike',
    'frags_from' => 1700000000,
    'frags_to' => 1700003600,
    'teamkills_map' => 'de_dust2',
    'teamkills_game' => 'cstrike',
    'teamkills_from' => 1700000000,
    'teamkills_to' => 1700003600,
), $sceneSql['params'], 'scene SQL should expose every branch-specific bind parameter');
assert_same(array(
    'suicides_map' => 'de_dust2',
    'suicides_game' => 'cstrike',
    'suicides_from' => 1700000000,
    'suicides_to' => 1700003600,
), $sceneSql['suicides']['params'], 'suicide count should retain its own complete map/game/window bindings');
assert_contains('COUNT(*) AS excludedSuicides', $sceneSql['suicides']['sql'], 'suicide count should be a separate aggregate query');
assert_contains('hlstats_Events_Suicides', $sceneSql['suicides']['sql'], 'suicide count should query the suicide source table');
assert_true(strpos($sceneSql['suicides']['sql'], 'playerId = :') === false, 'suicide count should be independent of the player lens');

$bucketCases = array(
    array('width' => 1, 'height' => 1, 'bucket' => 4),
    array('width' => 512, 'height' => 128, 'bucket' => 4),
    array('width' => 4096, 'height' => 2048, 'bucket' => 32),
);
foreach ($bucketCases as $case) {
    assert_same(
        $case['bucket'],
        heatmap_scene_bucket_size($case['width'], $case['height']),
        'scene bucket size should stay bounded for ' . $case['width'] . 'x' . $case['height']
    );
}
assert_throws('invalid_image', function (): void {
    heatmap_scene_bucket_size(0, 128);
}, 'scene bucket builder should reject a non-positive image width');

$bothPayload = scene_payload(array(scene_row(array('headshot' => '1', 'teamkill' => '1'))));
assert_same('ok', $bothPayload['state'], 'one well-formed combat row should build an ok scene');
assert_same(2, $bothPayload['summary']['excludedSuicides'], 'scene summary should retain separately counted suicides');
assert_same(4, $bothPayload['grid']['bucketSize'], 'small scene images should use the minimum bucket size');
assert_same(array('cell', 'x', 'y', 'kills', 'deaths'), $bothPayload['grid']['fields'], 'scene grids should expose stable compact layer fields');
assert_same(
    array(
        array('c3.1', 3, 1, 0, 1),
        array('c2.2', 2, 2, 1, 0),
    ),
    $bothPayload['layers']['total'],
    'one combat row should contribute independently to victim deaths and attacker kills'
);
assert_same(array('c2.2', 2, 2, 1, 0), scene_layer_row($bothPayload['layers']['me'], 'c2.2'), 'personal kills should match killerId only');
assert_same(array('c3.1', 3, 1, 0, 1), scene_layer_row($bothPayload['layers']['others'], 'c3.1'), 'others should retain compatible victim deaths');
assert_same(1, $bothPayload['coverage']['sourceRows'], 'source row coverage should count one combat event');
assert_same(2, $bothPayload['coverage']['candidate'], 'both channels should create two candidate contributions from one combat event');
assert_same(2, $bothPayload['coverage']['validXY'], 'both participant coordinates should independently count as valid XY');
assert_same(2, $bothPayload['coverage']['assigned'], 'both participant coordinates should independently assign a floor');
assert_same(1.0, $bothPayload['coverage']['zCoverage'], 'fully assigned floor data should have complete Z coverage');
assert_same(array('id', 'label', 'count', 'available'), array_keys($bothPayload['floors'][0]), 'floor metadata should never expose an asset token');
assert_same('./hlstatsimg/games/cstrike/maps/de_dust2.jpg', $bothPayload['map']['image']['url'], 'all floors should share the validated map image');

$deathPayload = scene_payload(array(scene_row(array(
    'killerId' => '7',
    'victimId' => '42',
    'attackerX' => '4',
    'attackerY' => '4',
    'attackerZ' => '5',
    'victimX' => '20',
    'victimY' => '12',
    'victimZ' => '5',
))), scene_query(array('event' => 'deaths', 'lens' => 'me')));
assert_same(array('c5.3', 5, 3, 0, 1), $deathPayload['layers']['me'][0], 'personal deaths should use victimId and victim coordinates only');

$floorProjectionPayload = scene_payload(
    array(scene_row(array('attackerX' => '8', 'attackerY' => '8', 'attackerZ' => '5'))),
    scene_query(array('event' => 'kills', 'floor' => 'lower')),
    scene_config(array('xoffset' => 20))
);
assert_same('ok', $floorProjectionPayload['state'], 'raw Z should assign a requested floor before XY projection');
assert_same(array('c7.2', 7, 2, 1, 0), $floorProjectionPayload['layers']['total'][0], 'projection should run after floor selection');
assert_same(1, $floorProjectionPayload['floors'][0]['count'], 'floor metadata should count requested-channel contributions');
assert_same(true, $floorProjectionPayload['floors'][0]['available'], 'a covered populated floor should be available');

$allFloorPayload = scene_payload(
    array(scene_row(array('attackerZ' => null))),
    scene_query(array('event' => 'kills', 'floor' => 'all'))
);
assert_same('ok', $allFloorPayload['state'], 'the all-floor view should retain valid XY without Z');
assert_same(1, count($allFloorPayload['layers']['total']), 'the all-floor view should retain XY-only contributions');
assert_same(1, $allFloorPayload['coverage']['missingCoordinates'], 'missing Z should remain a per-contribution diagnostic');
assert_same(0.0, $allFloorPayload['coverage']['zCoverage'], 'floor-enabled maps should report incomplete Z coverage without an assignment');

$lowFloorCoveragePayload = scene_payload(array(
    scene_row(array('attackerZ' => '5')),
    scene_row(array('eventId' => '2', 'attackerX' => '12', 'attackerZ' => null)),
), scene_query(array('event' => 'kills', 'floor' => 'lower')));
assert_same('floors_unavailable', $lowFloorCoveragePayload['state'], 'a selected floor should fail closed below global Z coverage');
assert_same(array(), $lowFloorCoveragePayload['layers']['total'], 'unavailable floors should not expose partial bins');

$diagnosticPayload = scene_payload(array(
    scene_row(array('eventId' => '1', 'attackerX' => '8', 'attackerY' => '8', 'attackerZ' => '5')),
    scene_row(array('eventId' => '2', 'attackerX' => null, 'attackerY' => '8', 'attackerZ' => '5')),
    scene_row(array('eventId' => '3', 'attackerX' => 'not-an-integer', 'attackerY' => '8', 'attackerZ' => '5')),
    scene_row(array('eventId' => '4', 'attackerX' => '130', 'attackerY' => '8', 'attackerZ' => '25')),
), scene_query(array('event' => 'kills')));
assert_same('weak_projection', $diagnosticPayload['state'], 'active-floor projection below 70 percent should fail closed');
assert_same(4, $diagnosticPayload['coverage']['sourceRows'], 'coverage should retain fetched source-row count');
assert_same(4, $diagnosticPayload['coverage']['candidate'], 'coverage should count requested-channel candidates before coordinate validation');
assert_same(2, $diagnosticPayload['coverage']['validXY'], 'coverage should retain only canonical MEDIUMINT XY candidates');
assert_same(2, $diagnosticPayload['coverage']['validZ'], 'coverage should distinguish valid raw Z from unassigned Z');
assert_same(1, $diagnosticPayload['coverage']['missingCoordinates'], 'coverage should count null coordinates without coercion');
assert_same(1, $diagnosticPayload['coverage']['malformedCoordinates'], 'coverage should count malformed coordinates without coercion');
assert_same(1, $diagnosticPayload['coverage']['assigned'], 'coverage should count floor assignments from raw Z');
assert_same(1, $diagnosticPayload['coverage']['unassigned'], 'coverage should count valid raw Z outside every floor band');
assert_same(2, $diagnosticPayload['coverage']['projected'], 'coverage should project only valid XY contributions in the active floor');
assert_same(1, $diagnosticPayload['coverage']['inBounds'], 'coverage should count bounded projected contributions');
assert_same(1, $diagnosticPayload['coverage']['outOfBounds'], 'coverage should count projected but out-of-bounds contributions');
assert_same(array(), $diagnosticPayload['layers']['total'], 'weak projection should not expose biased partial bins');

$missingCoordinatesPayload = scene_payload(array(scene_row(array('attackerX' => null, 'attackerY' => null))), scene_query(array('event' => 'kills')));
assert_same('missing_coordinates', $missingCoordinatesPayload['state'], 'combat rows without requested-channel XY should expose the coordinate state');
assert_same(array(), $missingCoordinatesPayload['layers']['total'], 'missing coordinate scenes should not expose partial bins');
$emptyPayload = scene_payload(array(), scene_query(array('event' => 'kills')));
assert_same('empty', $emptyPayload['state'], 'zero combat rows should expose the empty state');

$orderedRows = array(
    scene_row(array('eventId' => '1', 'attackerX' => '12', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '2', 'attackerX' => '4', 'attackerY' => '8', 'attackerZ' => '5')),
);
$orderedPayload = scene_payload($orderedRows, scene_query(array('event' => 'kills')));
$reversedPayload = scene_payload(array_reverse($orderedRows), scene_query(array('event' => 'kills')));
assert_same($orderedPayload['layers'], $reversedPayload['layers'], 'scene layer aggregation should not depend on SQL row order');
assert_same(
    array(
        array('c3.1', 3, 1, 1, 0),
        array('c1.2', 1, 2, 1, 0),
    ),
    $orderedPayload['layers']['total'],
    'scene cells should sort deterministically by gridY then gridX'
);

$largeScenePayload = scene_payload(
    array(scene_row(array('attackerX' => '4095', 'attackerY' => '2047', 'attackerZ' => '5'))),
    scene_query(array('event' => 'kills')),
    scene_config(),
    scene_image(array('width' => 4096, 'height' => 2048))
);
assert_same(32, $largeScenePayload['grid']['bucketSize'], '4096-pixel images should use a 32-pixel grid bucket');
assert_same(128, $largeScenePayload['grid']['width'], '4096-pixel images should cap the horizontal grid axis at 128');
assert_same(64, $largeScenePayload['grid']['height'], '2048-pixel images should retain the bounded vertical grid axis');

$sourceCropConfig = scene_config(array(
    'cropx1' => 100,
    'cropy1' => 50,
    'cropx2' => 128,
    'cropy2' => 128,
));
$sourceCropRow = scene_row(array('attackerX' => '104', 'attackerY' => '56', 'attackerZ' => '5'));
$sourceCropCases = array(
    array(
        'name' => 'hlstatsimg keeps full-image scene coordinates',
        'image' => scene_image(array('source' => 'hlstatsimg', 'width' => 256, 'height' => 256)),
        'cell' => array('c26.14', 26, 14, 1, 0),
    ),
    array(
        'name' => 'heatmaps source applies its configured crop',
        'image' => scene_image(array(
            'source' => 'heatmaps/src',
            'sourceWidth' => 256,
            'sourceHeight' => 256,
            'width' => 128,
            'height' => 128,
        )),
        'cell' => array('c1.1', 1, 1, 1, 0),
    ),
);
foreach ($sourceCropCases as $case) {
    $payload = scene_payload(
        array($sourceCropRow),
        scene_query(array('event' => 'kills')),
        $sourceCropConfig,
        $case['image']
    );
    assert_same('ok', $payload['state'], 'source-specific crop fixture should produce an ok scene: ' . $case['name']);
    assert_same($case['cell'], $payload['layers']['total'][0], 'scene crop behavior should mirror v1: ' . $case['name']);
}

$comparisonRows = array(
    scene_row(array('eventId' => '1', 'killerId' => '42', 'attackerX' => '4', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '2', 'killerId' => '42', 'attackerX' => '4', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '3', 'killerId' => '7', 'attackerX' => '4', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '4', 'killerId' => '42', 'attackerX' => '8', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '5', 'killerId' => '8', 'attackerX' => '8', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '6', 'killerId' => '9', 'attackerX' => '8', 'attackerY' => '4', 'attackerZ' => '5')),
    scene_row(array('eventId' => '7', 'killerId' => '10', 'attackerX' => '8', 'attackerY' => '4', 'attackerZ' => '5')),
);
$comparisonPayload = scene_payload($comparisonRows, scene_query(array('event' => 'kills', 'lens' => 'difference')));
assert_same('ok', $comparisonPayload['state'], 'three personal kills should satisfy the comparison sample floor');
assert_same(array('cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'), $comparisonPayload['comparison']['fields'], 'comparison should retain the canonical six-field scene shape');
assert_same(3, $comparisonPayload['comparison']['personalSample'], 'comparison should expose the complete in-bounds personal sample');
assert_same(4, $comparisonPayload['comparison']['otherSample'], 'comparison should expose the complete compatible other sample');
assert_float_close(5 / 12, $comparisonPayload['comparison']['bins'][0][3], 'comparison should use per-layer kill density shares');
assert_same(0.0, $comparisonPayload['comparison']['bins'][0][4], 'kill comparisons should leave the death delta column neutral');
assert_same(3, $comparisonPayload['comparison']['bins'][0][5], 'comparison samples should sum compatible me and other counts per cell');
assert_float_close(-5 / 12, $comparisonPayload['comparison']['bins'][1][3], 'comparison should retain negative density deltas for other-heavy cells');

$insufficientPayload = scene_payload(array_slice($comparisonRows, 0, 3), scene_query(array('event' => 'kills', 'lens' => 'difference')));
assert_same('insufficient_sample', $insufficientPayload['state'], 'comparison scenes below three personal events should be terminal but complete');
assert_true(count($insufficientPayload['layers']['total']) > 0, 'insufficient comparison scenes should retain count layers');
assert_same(array(), $insufficientPayload['comparison']['bins'], 'insufficient comparison scenes should not expose unstable comparison bins');

$overflowState = array(
    'query' => scene_query(array('event' => 'kills')),
    'config' => scene_config(),
    'image' => scene_image(),
);
for ($rowIndex = 0; $rowIndex <= HEATMAP_MAX_SOURCE_ROWS; $rowIndex++) {
    heatmap_accumulate_scene_row($overflowState, scene_row(array('eventId' => strval($rowIndex + 1))));
}
$overflowPayload = heatmap_finalize_scene($overflowState);
assert_same('too_many_events', $overflowPayload['state'], 'the 250001st fetched row should produce the explicit source budget state');
assert_same(250001, $overflowPayload['summary']['rowsRead'], 'the overflow sentinel should be recorded only as a row observation');
assert_same(250000, $overflowPayload['coverage']['sourceRows'], 'coverage should exclude the overflow sentinel from source rows');
assert_same(array(), $overflowPayload['layers']['total'], 'overflow scenes should discard every accumulated bin');
assert_same(array(), $overflowPayload['comparison']['bins'], 'overflow scenes should not expose comparison bins');

echo "web heatmap smoke ok\n";
