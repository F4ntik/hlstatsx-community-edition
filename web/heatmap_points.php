<?php

declare(strict_types=1);

define('IN_HLSTATS', true);

require __DIR__ . '/config.php';
$includeRoot = preg_match('/^([A-Za-z]:)?[\/\\\\]/', INCLUDE_PATH)
    ? INCLUDE_PATH
    : __DIR__ . '/' . ltrim(INCLUDE_PATH, './');
require $includeRoot . '/functions.php';
require $includeRoot . '/heatmap_points.php';

function heatmap_json_response($payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
}

$game = heatmap_clean_token($_GET['game'] ?? '');
$map = heatmap_clean_token($_GET['map'] ?? '');
$playerId = max(0, intval($_GET['player'] ?? 0));
$event = heatmap_clean_event($_GET['event'] ?? 'kills');
$renderer = heatmap_clean_renderer_mode($_GET['renderer'] ?? 'thermal');
$normalization = heatmap_clean_normalization($_GET['normalization'] ?? 'sqrt');
$days = isset($_GET['days']) ? max(1, min(3650, intval($_GET['days']))) : 0;
$limit = max(1, min(50000, intval($_GET['limit'] ?? 10000)));

if ($game === '' || $map === '') {
    heatmap_json_response(array('error' => 'invalid game or map'), 400);
    exit;
}

try {
    $container = require __DIR__ . '/bootstrap.php';
    $pdo = $container->get('pdo');
    $config = heatmap_fetch_config($pdo, $game, $map);

    if ($config === null) {
        heatmap_json_response(array('error' => 'heatmap config not found'), 404);
        exit;
    }

    $image = heatmap_image_metadata($game, $map, $config);
    if (!$image) {
        heatmap_json_response(array('error' => 'map image not found'), 404);
        exit;
    }

    $scope = array(
        'playerId' => $playerId,
        'event' => $playerId > 0 ? $event : 'global',
        'days' => $days > 0 ? $days : intval($config['days'] ?? 30),
        'limit' => $limit,
    );
    $cacheKey = heatmap_cache_key(array(
        'game' => $game,
        'map' => $map,
        'scope' => $scope,
        'renderer' => $renderer,
        'normalization' => $normalization,
        'configHash' => heatmap_config_hash($config, $image),
    ));
    $cached = heatmap_read_payload_cache($cacheKey);
    if ($cached !== null) {
        $cached['cache'] = array('status' => 'hit', 'key' => $cacheKey);
        heatmap_json_response($cached);
        exit;
    }

    $rows = heatmap_fetch_rows($pdo, $config, array(
        'playerId' => $playerId,
        'event' => $event,
        'days' => $scope['days'],
        'limit' => $limit,
    ));
    $payload = heatmap_build_payload($game, $map, $image, $rows, $config, array(
        'renderer' => $renderer,
        'normalization' => $normalization,
    ));
    $payload['scope'] = $scope;
    $payload['cache'] = array('status' => 'miss', 'key' => $cacheKey);
    heatmap_write_payload_cache($cacheKey, $payload);
    heatmap_json_response($payload);
} catch (Throwable $exc) {
    heatmap_json_response(array('error' => 'heatmap query failed'), 500);
}
