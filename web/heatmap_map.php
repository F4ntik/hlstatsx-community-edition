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
$crop = intval($_GET['crop'] ?? 0) === 1;

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

    $sourceSize = getimagesize($sourcePath);
    $sourceWidth = intval($sourceSize[0] ?? 0);
    $sourceHeight = intval($sourceSize[1] ?? 0);
    if ($sourceWidth <= 0 || $sourceHeight <= 0) {
        http_response_code(500);
        exit;
    }
    $cropConfig = array(
        'cropx1' => isset($_GET['cropx1']) ? intval($_GET['cropx1']) : intval($config['cropx1'] ?? 0),
        'cropy1' => isset($_GET['cropy1']) ? intval($_GET['cropy1']) : intval($config['cropy1'] ?? 0),
        'cropx2' => isset($_GET['cropx2']) ? intval($_GET['cropx2']) : intval($config['cropx2'] ?? 0),
        'cropy2' => isset($_GET['cropy2']) ? intval($_GET['cropy2']) : intval($config['cropy2'] ?? 0),
    );
    $cropConfig = heatmap_normalize_crop($cropConfig, $sourceWidth, $sourceHeight);

    if ($crop && heatmap_has_crop($cropConfig)) {
        if (!function_exists('imagecreatefromjpeg')) {
            http_response_code(500);
            exit;
        }
        $image = imagecreatefromjpeg($sourcePath);
        if (!$image) {
            http_response_code(500);
            exit;
        }
        $cropped = imagecreatetruecolor($cropConfig['cropx2'], $cropConfig['cropy2']);
        imagecopy(
            $cropped,
            $image,
            0,
            0,
            $cropConfig['cropx1'],
            $cropConfig['cropy1'],
            $cropConfig['cropx2'],
            $cropConfig['cropy2']
        );
        header('Content-Type: image/jpeg');
        header('Cache-Control: public, max-age=3600');
        imagejpeg($cropped, null, 90);
        imagedestroy($cropped);
        imagedestroy($image);
        exit;
    }

    header('Content-Type: image/jpeg');
    header('Cache-Control: public, max-age=3600');
    readfile($sourcePath);
} catch (Throwable $exc) {
    http_response_code(500);
}
