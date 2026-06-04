<?php

declare(strict_types=1);

define('IN_HLSTATS', true);

require __DIR__ . '/config.php';
$includeRoot = preg_match('/^([A-Za-z]:)?[\/\\\\]/', INCLUDE_PATH)
    ? INCLUDE_PATH
    : __DIR__ . '/' . ltrim(INCLUDE_PATH, './');
require $includeRoot . '/heatmap_points.php';

$game = heatmap_clean_token($_GET['game'] ?? '');
$map = heatmap_clean_token($_GET['map'] ?? '');

if ($game === '' || $map === '') {
    http_response_code(400);
    exit;
}

try {
    $container = require __DIR__ . '/bootstrap.php';
    $config = heatmap_fetch_config($container->get('pdo'), $game, $map);
    if ($config === null) {
        http_response_code(404);
        exit;
    }

    $sourcePath = dirname(__DIR__) . '/heatmaps/src/' . $config['game'] . '/' . $map . '.jpg';
    if (!is_file($sourcePath)) {
        http_response_code(404);
        exit;
    }

    header('Content-Type: image/jpeg');
    header('Cache-Control: public, max-age=3600');
    readfile($sourcePath);
} catch (Throwable $exc) {
    http_response_code(500);
}
