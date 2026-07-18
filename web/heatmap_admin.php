<?php

declare(strict_types=1);

define('IN_HLSTATS', true);

require __DIR__ . '/config.php';
$includeRoot = preg_match('/^([A-Za-z]:)?[\/\\\\]/', INCLUDE_PATH)
    ? INCLUDE_PATH
    : __DIR__ . '/' . ltrim(INCLUDE_PATH, './');
require $includeRoot . '/functions.php';
require $includeRoot . '/heatmap_points.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}

function heatmap_admin_json($payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
}

function heatmap_admin_require_access(): void
{
    if (empty($_SESSION['loggedin']) || intval($_SESSION['acclevel'] ?? 0) < 80) {
        heatmap_admin_json(array('error' => 'access denied'), 403);
        exit;
    }
}

function heatmap_admin_request(): array
{
    $payload = array();
    $raw = file_get_contents('php://input');
    if (is_string($raw) && trim($raw) !== '') {
        $decoded = json_decode($raw, true);
        if (is_array($decoded)) {
            $payload = $decoded;
        }
    }

    return array_replace($payload, $_POST, $_GET);
}

function heatmap_admin_same_origin(): bool
{
    $expectedHost = strval($_SERVER['HTTP_HOST'] ?? '');
    if ($expectedHost === '') {
        return true;
    }
    $expectedScheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    foreach (array('HTTP_ORIGIN', 'HTTP_REFERER') as $header) {
        $value = strval($_SERVER[$header] ?? '');
        if ($value === '') {
            continue;
        }
        $parts = parse_url($value);
        $host = strval($parts['host'] ?? '');
        $port = isset($parts['port']) ? ':' . intval($parts['port']) : '';
        $scheme = strval($parts['scheme'] ?? '');
        if ($scheme !== $expectedScheme || ($host . $port) !== $expectedHost) {
            return false;
        }
    }

    return true;
}

function heatmap_admin_require_mutation_allowed(string $action): void
{
    if (!in_array($action, array('save', 'upload', 'regenerate'), true)) {
        return;
    }
    if (strtoupper(strval($_SERVER['REQUEST_METHOD'] ?? 'GET')) !== 'POST') {
        heatmap_admin_json(array('error' => 'method not allowed'), 405);
        exit;
    }
    if (!heatmap_admin_same_origin()) {
        heatmap_admin_json(array('error' => 'same-origin request required'), 403);
        exit;
    }
}

function heatmap_admin_config(PDO $pdo, string $game, string $map): ?array
{
    $config = heatmap_fetch_config($pdo, $game, $map);
    if ($config !== null) {
        return $config;
    }

    return heatmap_default_config($pdo, $game, $map);
}

function heatmap_admin_preview(PDO $pdo, array $request, bool $save): void
{
    $game = heatmap_clean_token($request['game'] ?? '');
    $map = heatmap_clean_token($request['map'] ?? '');
    if ($game === '' || $map === '') {
        heatmap_admin_json(array('error' => 'invalid game or map'), 400);
        return;
    }

    $config = heatmap_admin_config($pdo, $game, $map);
    if ($config === null) {
        heatmap_admin_json(array('error' => 'game not found'), 404);
        return;
    }

    $config = heatmap_merge_config_override($config, $request);
    if (!empty($request['overviewText'])) {
        $config = heatmap_parse_overview(strval($request['overviewText']), $config);
    }
    $config['map'] = $map;

    $image = heatmap_image_metadata($game, $map, $config);
    if (!$image) {
        heatmap_admin_json(array('error' => 'map image not found'), 404);
        return;
    }

    $config = heatmap_normalize_crop(
        $config,
        intval($image['sourceWidth'] ?? $image['width'] ?? 0),
        intval($image['sourceHeight'] ?? $image['height'] ?? 0)
    );
    $image = heatmap_image_metadata($game, $map, $config);

    if ($save) {
        heatmap_save_config($pdo, $config);
        heatmap_clear_payload_cache($game, $map);
    }

    $rows = heatmap_fetch_rows($pdo, $config, array(
        'playerId' => max(0, intval($request['playerId'] ?? 0)),
        'event' => heatmap_clean_event($request['event'] ?? 'kills'),
        'days' => max(1, min(3650, intval($request['days'] ?? ($config['days'] ?? 30)))),
        'limit' => max(1, min(50000, intval($request['limit'] ?? 10000))),
    ));
    $payload = heatmap_build_payload($game, $map, $image, $rows, $config, array(
        'renderer' => heatmap_clean_renderer_mode($request['renderer'] ?? 'thermal'),
        'normalization' => heatmap_clean_normalization($request['normalization'] ?? 'sqrt'),
    ));
    $payload['saved'] = $save;
    $payload['cache'] = array('invalidated' => $save);
    heatmap_admin_json($payload);
}

function heatmap_admin_upload(PDO $pdo, array $request): void
{
    $game = heatmap_clean_token($request['game'] ?? '');
    $map = heatmap_clean_token($request['map'] ?? '');
    if ($game === '' || $map === '') {
        heatmap_admin_json(array('error' => 'invalid game or map'), 400);
        return;
    }

    $config = heatmap_admin_config($pdo, $game, $map);
    if ($config === null) {
        heatmap_admin_json(array('error' => 'game not found'), 404);
        return;
    }

    $result = array('uploaded' => array());
    if (!empty($_FILES['mapImage']['tmp_name'])) {
        if (intval($_FILES['mapImage']['error'] ?? UPLOAD_ERR_OK) !== UPLOAD_ERR_OK) {
            heatmap_admin_json(array('error' => 'map image upload failed'), 400);
            return;
        }
        if (intval($_FILES['mapImage']['size'] ?? 0) > 20 * 1024 * 1024) {
            heatmap_admin_json(array('error' => 'map image is too large'), 400);
            return;
        }
        $tmp = $_FILES['mapImage']['tmp_name'];
        $size = @getimagesize($tmp);
        if (!$size || intval($size[2] ?? 0) !== IMAGETYPE_JPEG) {
            heatmap_admin_json(array('error' => 'map image must be a JPEG'), 400);
            return;
        }
        $dir = dirname(__DIR__) . '/heatmaps/src/' . $config['game'];
        if (!is_dir($dir)) {
            @mkdir($dir, 0775, true);
        }
        $target = $dir . '/' . $map . '.jpg';
        if (!move_uploaded_file($tmp, $target)) {
            heatmap_admin_json(array('error' => 'failed to save map image'), 500);
            return;
        }
        $result['uploaded']['mapImage'] = basename($target);
    }

    $overviewText = '';
    if (!empty($_FILES['overviewFile']['tmp_name'])) {
        if (intval($_FILES['overviewFile']['error'] ?? UPLOAD_ERR_OK) !== UPLOAD_ERR_OK) {
            heatmap_admin_json(array('error' => 'overview upload failed'), 400);
            return;
        }
        if (intval($_FILES['overviewFile']['size'] ?? 0) > 1024 * 1024) {
            heatmap_admin_json(array('error' => 'overview file is too large'), 400);
            return;
        }
        $overviewText = (string) file_get_contents($_FILES['overviewFile']['tmp_name']);
    } elseif (!empty($request['overviewText'])) {
        $overviewText = strval($request['overviewText']);
    }
    if (strlen($overviewText) > 1024 * 1024) {
        heatmap_admin_json(array('error' => 'overview text is too large'), 400);
        return;
    }
    if ($overviewText !== '') {
        $config = heatmap_parse_overview($overviewText, $config);
        $dir = dirname(__DIR__) . '/heatmaps/overviews/' . $config['game'];
        if (!is_dir($dir)) {
            @mkdir($dir, 0775, true);
        }
        file_put_contents($dir . '/' . $map . '.txt', $overviewText);
        $result['uploaded']['overview'] = $map . '.txt';
        $result['projection'] = heatmap_projection_config($config);
    }

    heatmap_clear_payload_cache($game, $map);
    heatmap_admin_json($result);
}

function heatmap_admin_regenerate(array $request): void
{
    $game = heatmap_clean_token($request['game'] ?? '');
    $map = heatmap_clean_token($request['map'] ?? '');
    if ($game === '' || $map === '') {
        heatmap_admin_json(array('error' => 'invalid game or map'), 400);
        return;
    }

    $root = dirname(__DIR__);
    $webRoot = is_dir($root . '/web') ? $root . '/web' : __DIR__;
    $scripts = $root . '/scripts';
    $python = getenv('PYTHON') ?: (DIRECTORY_SEPARATOR === '\\' ? 'python' : 'python3');
    $baseCommand = escapeshellarg($python)
        . ' -m hlstats_py.heatmaps'
        . ' --configfile ' . escapeshellarg($scripts . '/hlstats.conf')
        . ' --web-root ' . escapeshellarg($webRoot)
        . ' --heatmaps-root ' . escapeshellarg($root . '/heatmaps')
        . ' --game ' . escapeshellarg($game)
        . ' --map ' . escapeshellarg($map)
        . ' --disablecache';
    $command = DIRECTORY_SEPARATOR === '\\'
        ? 'set "PYTHONPATH=' . str_replace('"', '', $scripts) . '" && ' . $baseCommand
        : 'PYTHONPATH=' . escapeshellarg($scripts) . ' ' . $baseCommand;

    $descriptors = array(
        1 => array('pipe', 'w'),
        2 => array('pipe', 'w'),
    );
    $process = @proc_open($command, $descriptors, $pipes, $root);
    if (!is_resource($process)) {
        heatmap_admin_json(array('error' => 'failed to start heatmap generator', 'command' => $command), 500);
        return;
    }

    $stdout = stream_get_contents($pipes[1]);
    $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[1]);
    fclose($pipes[2]);
    $exitCode = proc_close($process);
    heatmap_clear_payload_cache($game, $map);

    heatmap_admin_json(array(
        'ok' => $exitCode === 0,
        'exitCode' => $exitCode,
        'stdout' => $stdout,
        'stderr' => $stderr,
        'command' => $command,
    ), $exitCode === 0 ? 200 : 500);
}

heatmap_admin_require_access();

try {
    $container = require __DIR__ . '/bootstrap.php';
    $pdo = $container->get('pdo');
    $request = heatmap_admin_request();
    $action = strtolower(strval($request['action'] ?? 'preview'));
    heatmap_admin_require_mutation_allowed($action);

    if ($action === 'games') {
        heatmap_admin_json(array('games' => heatmap_fetch_games($pdo)));
    } elseif ($action === 'maps') {
        $game = heatmap_clean_token($request['game'] ?? '');
        heatmap_admin_json(array('maps' => $game === '' ? array() : heatmap_fetch_known_maps($pdo, $game)));
    } elseif ($action === 'save') {
        heatmap_admin_preview($pdo, $request, true);
    } elseif ($action === 'upload') {
        heatmap_admin_upload($pdo, $request);
    } elseif ($action === 'regenerate') {
        heatmap_admin_regenerate($request);
    } else {
        heatmap_admin_preview($pdo, $request, false);
    }
} catch (Throwable $exc) {
    heatmap_admin_json(array('error' => 'heatmap admin request failed', 'detail' => $exc->getMessage()), 500);
}
