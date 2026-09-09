<?php

declare(strict_types=1);

define('IN_HLSTATS', true);

require __DIR__ . '/config.php';
$includeRoot = preg_match('/^([A-Za-z]:)?[\/\\\\]/', INCLUDE_PATH)
    ? INCLUDE_PATH
    : __DIR__ . '/' . ltrim(INCLUDE_PATH, './');
require $includeRoot . '/functions.php';
require $includeRoot . '/heatmap_points.php';

$game = heatmap_clean_token($_GET['game'] ?? '');
$map = heatmap_clean_token($_GET['map'] ?? '');
$crop = intval($_GET['crop'] ?? 0) === 1;
$source = $_GET['source'] ?? 'heatmaps/src';

if ($game === '' || $map === '' || !is_string($source)
    || !in_array($source, array('heatmaps/src', 'hlstatsimg'), true)) {
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

    if ($source === 'hlstatsimg') {
        $fallback = getImage('/games/' . $game . '/maps/' . $map);
        if (!$fallback && !empty($config['realgame'])) {
            $fallback = getImage('/games/' . $config['realgame'] . '/maps/' . $map);
        }
        $sourcePath = is_array($fallback) ? strval($fallback['path'] ?? '') : '';
        $crop = false;
    } else {
        $sourcePath = dirname(__DIR__) . '/heatmaps/src/' . $config['game'] . '/' . $map . '.jpg';
        $floor = $_GET['floor'] ?? 'all';
        if (!is_string($floor)) throw new InvalidArgumentException('invalid_floor');
        $sourcePath = heatmap_floor_source_path($config, $map, $floor) ?? $sourcePath;
    }
    if ($sourcePath === '' || !is_file($sourcePath)) {
        http_response_code(404);
        exit;
    }

    $sourceSnapshot = heatmap_map_source_snapshot($sourcePath);
    $sourceWidth = $sourceSnapshot['width'];
    $sourceHeight = $sourceSnapshot['height'];
    $versionState = heatmap_map_request_version_state($_GET['v'] ?? '', $sourceSnapshot['sourceIdentity']);
    if ($versionState === 'stale') {
        header('Cache-Control: no-store');
        http_response_code(409);
        exit;
    }
    $cacheControl = $versionState === 'current'
        ? 'public, max-age=3600, immutable'
        : 'no-store';
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
        $image = imagecreatefromstring($sourceSnapshot['bytes']);
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
        header('Cache-Control: ' . $cacheControl);
        header('ETag: "' . $sourceSnapshot['sourceIdentity'] . '"');
        imagejpeg($cropped, null, 90);
        imagedestroy($cropped);
        imagedestroy($image);
        exit;
    }

    header('Content-Type: ' . $sourceSnapshot['mime']);
    header('Cache-Control: ' . $cacheControl);
    header('ETag: "' . $sourceSnapshot['sourceIdentity'] . '"');
    header('Content-Length: ' . strlen($sourceSnapshot['bytes']));
    echo $sourceSnapshot['bytes'];
} catch (Throwable $exc) {
    http_response_code(500);
}
