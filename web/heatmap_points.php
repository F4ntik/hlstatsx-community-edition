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

function heatmap_v2_emit(array $payload, int $status, array $metrics): void
{
    if (($metrics['operation'] ?? '') === 'inspect' || ($metrics['cache'] ?? '') === 'no-store') {
        header('Cache-Control: no-store');
        header('Pragma: no-cache');
    }
    $encoded = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    $encodingFailed = !is_string($encoded);
    if ($encodingFailed) {
        $status = 500;
        $encoded = '{"schemaVersion":2,"state":"unexpected_error","code":"internal_error"}';
        $metrics['state'] = 'unexpected_error';
        $metrics['fallbackReason'] = 'internal_error';
    }
    $metrics['rawPayloadBytes'] = strlen($encoded);
    $metrics['totalMs'] = (microtime(true) - floatval($metrics['_startedAt'] ?? microtime(true))) * 1000.0;
    unset($metrics['_startedAt']);
    if (!$encodingFailed) {
        $metrics['state'] = strval($payload['state'] ?? ($metrics['state'] ?? 'unknown'));
    }
    error_log('hlstats_heatmap ' . heatmap_request_log($metrics));

    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo $encoded;
}

function heatmap_v2_safe_error_code(Throwable $exception): string
{
    $allowed = array(
        'invalid_query',
        'invalid_window',
        'invalid_player',
        'invalid_event',
        'invalid_lens',
        'player_required',
        'difference_channel_required',
        'invalid_floor',
        'unknown_floor',
        'invalid_language',
        'invalid_inspect',
        'invalid_floor_config',
        'invalid_scene_query',
        'invalid_image',
    );
    $message = $exception->getMessage();
    return in_array($message, $allowed, true) ? $message : 'invalid_request';
}

function heatmap_v2_metrics(array $query, string $windowClass, string $cache, float $startedAt): array
{
    return array(
        '_startedAt' => $startedAt,
        'version' => 2,
        'operation' => 'scene',
        'game' => $query['game'] ?? '',
        'map' => $query['map'] ?? '',
        'windowClass' => $windowClass,
        'lens' => $query['lens'] ?? 'overview',
        'floor' => $query['floor'] ?? 'all',
        'rowsRead' => 0,
        'binsReturned' => 0,
        'rawPayloadBytes' => 0,
        'queryMs' => 0,
        'totalMs' => 0,
        'cache' => $cache,
        'xyCoverage' => 0,
        'zCoverage' => 0,
        'projectionCoverage' => 0,
        'state' => 'unknown',
        'fallbackReason' => '',
    );
}

function heatmap_v2_scene_metrics(array &$metrics, array $payload): void
{
    $summary = is_array($payload['summary'] ?? null) ? $payload['summary'] : array();
    $coverage = is_array($payload['coverage'] ?? null) ? $payload['coverage'] : array();
    $layers = is_array($payload['layers']['total'] ?? null) ? $payload['layers']['total'] : array();
    $metrics['rowsRead'] = $summary['rowsRead'] ?? 0;
    $metrics['binsReturned'] = count($layers);
    $metrics['xyCoverage'] = $coverage['xyCoverage'] ?? 0;
    $metrics['zCoverage'] = $coverage['zCoverage'] ?? 0;
    $metrics['projectionCoverage'] = $coverage['projectionCoverage'] ?? 0;
    $metrics['state'] = $payload['state'] ?? 'unknown';
    if ($metrics['state'] !== 'ok' && $metrics['state'] !== 'empty') {
        $metrics['fallbackReason'] = $metrics['state'];
    }
}

$isV2 = isset($_GET['v']) && is_string($_GET['v']) && $_GET['v'] === '2';
if (!$isV2) {
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
    } catch (Throwable $exception) {
        heatmap_json_response(array('error' => 'heatmap query failed'), 500);
    }
    exit;
}

$v2StartedAt = microtime(true);
$bootstrapStartedAt = $v2StartedAt;
$inspectRequested = array_key_exists('inspect', $_GET);
try {
    $container = require __DIR__ . '/bootstrap.php';
    $optionService = $container->get(\Service\OptionService::class);
    $g_options = $optionService->getAllOptions();
} catch (Throwable $exception) {
    $bootstrapMetrics = heatmap_v2_metrics(
        array(
            'game' => heatmap_clean_token($_GET['game'] ?? ''),
            'map' => heatmap_clean_token($_GET['map'] ?? ''),
        ),
        'default',
        $inspectRequested ? 'no-store' : 'error',
        $bootstrapStartedAt
    );
    if ($inspectRequested) {
        $bootstrapMetrics['operation'] = 'inspect';
    }
    heatmap_v2_emit(
        array('schemaVersion' => 2, 'state' => 'unexpected_error', 'code' => 'internal_error'),
        500,
        $bootstrapMetrics
    );
    exit;
}

$windowClass = array_key_exists('range', $_GET)
    ? 'preset'
    : (array_key_exists('from', $_GET) || array_key_exists('to', $_GET) ? 'custom' : 'default');
$initialMetrics = heatmap_v2_metrics(
    array(
        'game' => heatmap_clean_token($_GET['game'] ?? ''),
        'map' => heatmap_clean_token($_GET['map'] ?? ''),
    ),
    $windowClass,
    'miss',
    $v2StartedAt
);
if ($inspectRequested) {
    $initialMetrics['operation'] = 'inspect';
    $initialMetrics['cache'] = 'no-store';
}

if (heatmap_explorer_mode($g_options) === 0) {
    $initialMetrics['cache'] = $inspectRequested ? 'no-store' : 'disabled';
    $initialMetrics['state'] = 'explorer_disabled';
    $initialMetrics['fallbackReason'] = 'explorer_disabled';
    heatmap_v2_emit(
        array('schemaVersion' => 2, 'state' => 'explorer_disabled'),
        404,
        $initialMetrics
    );
    exit;
}

try {
    $query = heatmap_parse_v2_query($_GET, time());
    $isInspect = array_key_exists('inspect', $query);
    $metrics = heatmap_v2_metrics($query, $windowClass, $isInspect ? 'no-store' : 'miss', $v2StartedAt);
    $metrics['operation'] = $isInspect ? 'inspect' : 'scene';

    $pdo = $container->get('pdo');
    $config = heatmap_fetch_config($pdo, $query['game'], $query['map']);
    if ($config === null) {
        $metrics['state'] = 'not_found';
        $metrics['fallbackReason'] = 'config_not_found';
        heatmap_v2_emit(
            array('schemaVersion' => 2, 'state' => 'not_found', 'code' => 'config_not_found'),
            404,
            $metrics
        );
        exit;
    }

    $image = heatmap_image_metadata($query['game'], $query['map'], $config);
    if (!$image) {
        $metrics['state'] = 'not_found';
        $metrics['fallbackReason'] = 'image_not_found';
        heatmap_v2_emit(
            array('schemaVersion' => 2, 'state' => 'not_found', 'code' => 'image_not_found'),
            404,
            $metrics
        );
        exit;
    }

    $floors = heatmap_config_floors($config);
    heatmap_validate_requested_floor($query['floor'], $floors);
    if ($isInspect) {
        $inspectStartedAt = microtime(true);
        $inspectContext = heatmap_inspect_context($query, $config, $image);
        $cell = heatmap_parse_cell_id($query['inspect'], $inspectContext['grid']);
        $bounds = heatmap_unproject_cell_bounds($cell, $inspectContext['grid'], $inspectContext['config']);
        $descriptor = heatmap_build_inspect_sql($inspectContext['query'], $inspectContext['config'], $bounds);
        $rows = heatmap_fetch_inspect_rows($pdo, $descriptor);
        $metrics['queryMs'] = (microtime(true) - $inspectStartedAt) * 1000.0;
        $metrics['rowsRead'] = count($rows);
        $metrics['binsReturned'] = 0;
        $metrics['cache'] = 'no-store';
        $payload = heatmap_build_inspect_payload($rows, count($rows) > 100);
        $payload['query'] = $inspectContext['query'];
        $payload['cell'] = array(
            'id' => $cell['id'],
            'gridX' => $cell['gridX'],
            'gridY' => $cell['gridY'],
            'projectedBounds' => $bounds['projectedBounds'],
        );
        heatmap_v2_emit($payload, 200, $metrics);
        exit;
    }
    $cacheConfig = $config;
    $cacheConfig['projectionHash'] = heatmap_config_hash($config, $image);
    $cacheConfig['floorConfigHash'] = heatmap_scene_floor_config_hash($floors);
    $cacheKey = heatmap_scene_cache_key($query, $cacheConfig, $image);
    $cached = heatmap_read_complete_payload_cache($cacheKey);
    if ($cached !== null) {
        $metrics['cache'] = 'hit';
        heatmap_v2_scene_metrics($metrics, $cached);
        heatmap_v2_emit($cached, 200, $metrics);
        exit;
    }

    $queryStartedAt = microtime(true);
    $scene = heatmap_build_scene($pdo, $query, $config, $image);
    $metrics['queryMs'] = (microtime(true) - $queryStartedAt) * 1000.0;
    heatmap_v2_scene_metrics($metrics, $scene);
    $status = ($scene['state'] ?? '') === 'too_many_events' ? 422 : 200;
    if (heatmap_scene_state_is_cacheable($scene['state'] ?? null)) {
        heatmap_write_payload_cache($cacheKey, $scene);
    } else {
        $metrics['cache'] = 'bypass';
    }
    heatmap_v2_emit($scene, $status, $metrics);
} catch (InvalidArgumentException $exception) {
    $code = heatmap_v2_safe_error_code($exception);
    $initialMetrics['state'] = 'rejected';
    $initialMetrics['fallbackReason'] = $code;
    heatmap_v2_emit(
        array('schemaVersion' => 2, 'state' => 'rejected', 'code' => $code),
        400,
        $initialMetrics
    );
} catch (Throwable $exception) {
    $initialMetrics['state'] = 'unexpected_error';
    $initialMetrics['fallbackReason'] = 'internal_error';
    heatmap_v2_emit(
        array('schemaVersion' => 2, 'state' => 'unexpected_error', 'code' => 'internal_error'),
        500,
        $initialMetrics
    );
}
