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

    $sourcePath = dirname(__DIR__) . '/heatmaps/src/' . $config['game'] . '/' . $map . '.jpg';
    if (is_file($sourcePath)) {
        $sourceSize = getimagesize($sourcePath);
        $image = array(
            'url' => 'heatmap_map.php?game=' . rawurlencode($game) . '&map=' . rawurlencode($map),
            'width' => intval($sourceSize[0] ?? 0),
            'height' => intval($sourceSize[1] ?? 0),
        );
    } else {
        $image = getImage('/games/' . $game . '/maps/' . $map);
        if (!$image && !empty($config['realgame'])) {
            $image = getImage('/games/' . $config['realgame'] . '/maps/' . $map);
        }
    }

    if (!$image) {
        heatmap_json_response(array('error' => 'map image not found'), 404);
        exit;
    }

    $rows = heatmap_fetch_rows($pdo, $config, array(
        'playerId' => $playerId,
        'event' => $event,
    ));
    $payload = heatmap_build_payload($game, $map, $image, $rows, $config);
    $payload['scope'] = array(
        'playerId' => $playerId,
        'event' => $playerId > 0 ? $event : 'global',
    );
    heatmap_json_response($payload);
} catch (Throwable $exc) {
    heatmap_json_response(array('error' => 'heatmap query failed'), 500);
}
