<?php

declare(strict_types=1);

define('IN_HLSTATS', true);

require __DIR__ . '/config.php';
$includeRoot = preg_match('/^([A-Za-z]:)?[\/\\\\]/', INCLUDE_PATH)
    ? INCLUDE_PATH
    : __DIR__ . '/' . ltrim(INCLUDE_PATH, './');
require $includeRoot . '/functions.php';
require $includeRoot . '/heatmap_points.php';
require $includeRoot . '/heatmap_admin_transport.php';
const HEATMAP_ADMIN_MAX_IMAGE_BYTES = 20971520;
const HEATMAP_ADMIN_MAX_OVERVIEW_BYTES = 1048576;
const HEATMAP_ADMIN_MAX_IMAGE_DIMENSION = 8192;

final class HeatmapAdminException extends RuntimeException
{
    public int $httpStatus;
    public string $safeCode;

    public function __construct(string $safeCode, int $httpStatus)
    {
        parent::__construct($safeCode);
        $this->safeCode = $safeCode;
        $this->httpStatus = $httpStatus;
    }
}

function heatmap_admin_json(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
}

function heatmap_admin_language(array $request): string
{
    $language = strval($request['lang'] ?? ($_SESSION['lang'] ?? 'en'));
    return $language === 'ru' ? 'ru' : 'en';
}

function heatmap_admin_message(string $code, string $language): string
{
    $messages = array(
        'en' => array(
            'access_denied' => 'Administrator access is required.',
            'method_not_allowed' => 'This action requires POST.',
            'same_origin_required' => 'This request must come from this site.',
            'csrf_required' => 'Reload the calibration page and try again.',
            'invalid_request' => 'The calibration request is invalid.',
            'stale_config' => 'The calibration changed elsewhere. Reload it before saving.',
            'actor_required' => 'The authenticated administrator has no valid actor identity.',
            'image_missing' => 'A map image is required for preview.',
            'nothing_uploaded' => 'Choose a map image or overview file first.',
            'preview_failed' => 'The preview could not be prepared.',
            'save_failed' => 'The calibration was not saved.',
            'upload_failed' => 'The upload was not saved.',
            'saved' => 'Calibration saved.',
            'uploaded' => 'Upload saved.',
        ),
        'ru' => array(
            'access_denied' => 'Требуются права администратора.',
            'method_not_allowed' => 'Для этого действия нужен POST-запрос.',
            'same_origin_required' => 'Запрос должен быть отправлен с этого сайта.',
            'csrf_required' => 'Обновите страницу настройки и повторите попытку.',
            'invalid_request' => 'Некорректный запрос настройки.',
            'stale_config' => 'Настройка изменилась в другом месте. Загрузите её заново перед сохранением.',
            'actor_required' => 'У аутентифицированного администратора нет допустимого идентификатора.',
            'image_missing' => 'Для предпросмотра нужна карта изображения.',
            'nothing_uploaded' => 'Сначала выберите изображение карты или файл обзора.',
            'preview_failed' => 'Не удалось подготовить предпросмотр.',
            'save_failed' => 'Настройка не сохранена.',
            'upload_failed' => 'Загрузка не сохранена.',
            'saved' => 'Настройка сохранена.',
            'uploaded' => 'Загрузка сохранена.',
        ),
    );

    return $messages[$language][$code] ?? $messages[$language]['invalid_request'];
}
function heatmap_admin_result(string $code, string $language, array $extra = array()): array
{
    return array_replace(array(
        'ok' => true,
        'code' => $code,
        'message' => heatmap_admin_message($code, $language),
    ), $extra);
}

function heatmap_admin_require_access(): void
{
    if (empty($_SESSION['loggedin']) || intval($_SESSION['acclevel'] ?? 0) < 80) {
        throw new HeatmapAdminException('access_denied', 403);
    }
}

function heatmap_admin_request(): array
{
    $payload = array();
    $contentType = strtolower(strval($_SERVER['CONTENT_TYPE'] ?? ''));
    $raw = strpos($contentType, 'application/json') === 0 ? file_get_contents('php://input') : '';
    if (is_string($raw) && trim($raw) !== '') {
        try {
            $decoded = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        } catch (JsonException $exception) {
            throw new HeatmapAdminException('invalid_request', 400);
        }
        if (!is_array($decoded)) {
            throw new HeatmapAdminException('invalid_request', 400);
        }
        $payload = $decoded;
    }

    if (strtoupper(strval($_SERVER['REQUEST_METHOD'] ?? 'GET')) === 'POST') {
        return array_replace($payload, $_POST);
    }

    return array_replace($payload, $_GET);
}

function heatmap_admin_same_origin(): bool
{
    $expectedHost = strtolower(trim(strval($_SERVER['HTTP_HOST'] ?? '')));
    if ($expectedHost === ''
        || preg_match('/^(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::[0-9]{1,5})?$/Di', $expectedHost) !== 1) {
        return false;
    }
    $expectedScheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $sawTrustedHeader = false;
    foreach (array('HTTP_ORIGIN', 'HTTP_REFERER') as $header) {
        $value = trim(strval($_SERVER[$header] ?? ''));
        if ($value === '') {
            continue;
        }
        $parts = parse_url($value);
        if (!is_array($parts)
            || !isset($parts['scheme'], $parts['host'])
            || !is_string($parts['scheme'])
            || !is_string($parts['host'])) {
            return false;
        }
        $scheme = strtolower($parts['scheme']);
        $host = strtolower($parts['host']);
        $port = isset($parts['port']) ? ':' . intval($parts['port']) : '';
        if (($scheme !== 'http' && $scheme !== 'https')
            || $scheme !== $expectedScheme
            || !hash_equals($expectedHost, $host . $port)) {
            return false;
        }
        $sawTrustedHeader = true;
    }

    return $sawTrustedHeader;
}

function heatmap_admin_require_mutation_allowed(string $action): void
{
    if (!in_array($action, array('save', 'upload'), true)) {
        return;
    }
    if (strtoupper(strval($_SERVER['REQUEST_METHOD'] ?? 'GET')) !== 'POST') {
        throw new HeatmapAdminException('method_not_allowed', 405);
    }
    if (!heatmap_admin_same_origin()) {
        throw new HeatmapAdminException('same_origin_required', 403);
    }
    $provided = strval($_SERVER['HTTP_X_HLX_CSRF'] ?? '');
    $expected = heatmap_admin_session_csrf_token();
    if ($provided === '' || !hash_equals($expected, $provided)) {
        throw new HeatmapAdminException('csrf_required', 403);
    }
}

function heatmap_admin_identify_request(array $request): array
{
    $game = heatmap_clean_token($request['game'] ?? '');
    $map = heatmap_clean_token($request['map'] ?? '');
    if ($game === '' || $map === '') {
        throw new HeatmapAdminException('invalid_request', 400);
    }

    return array($game, $map);
}

function heatmap_admin_config(PDO $pdo, string $game, string $map): ?array
{
    $config = heatmap_fetch_config($pdo, $game, $map);
    return $config ?? heatmap_default_config($pdo, $game, $map);
}

function heatmap_admin_actor_id(PDO $pdo): int
{
    $username = $_SESSION['username'] ?? null;
    $password = $_SESSION['password'] ?? null;
    if (!is_string($username) || $username === '' || strlen($username) > 16
        || !is_string($password) || $password === '') {
        return 0;
    }

    $statement = $pdo->prepare(
        'SELECT password, acclevel, playerId FROM hlstats_Users WHERE username = :username LIMIT 1'
    );
    $statement->execute(array('username' => $username));
    $row = $statement->fetch(PDO::FETCH_ASSOC);
    if (!is_array($row)
        || intval($row['acclevel'] ?? 0) < 80
        || !is_string($row['password'] ?? null)
        || !hash_equals($row['password'], md5($password))) {
        return 0;
    }

    $actorId = filter_var($row['playerId'] ?? null, FILTER_VALIDATE_INT);
    return $actorId !== false && $actorId > 0 ? intval($actorId) : 0;
}

function heatmap_admin_require_actor(PDO $pdo): int
{
    $actorId = heatmap_admin_actor_id($pdo);
    if ($actorId <= 0) {
        throw new HeatmapAdminException('actor_required', 403);
    }

    return $actorId;
}

function heatmap_admin_log($logger, int $actorId, string $game, string $map, string $oldHash, string $newHash, bool $success): void
{
    if ($actorId <= 0 || !is_object($logger) || !method_exists($logger, 'warning')) {
        return;
    }
    $logger->warning(sprintf(
        'heatmap_admin actor=%d target=%s/%s old=%s new=%s success=%s',
        $actorId,
        $game,
        $map,
        $oldHash,
        $newHash,
        $success ? '1' : '0'
    ));
}

function heatmap_admin_open_map_lock(string $game, string $map)
{
    $path = heatmap_admin_map_lock_path($game, $map);
    $handle = @fopen($path, 'c');
    if (!is_resource($handle)) {
        throw new HeatmapAdminException('save_failed', 500);
    }
    @chmod($path, 0600);
    if (!flock($handle, LOCK_EX)) {
        fclose($handle);
        throw new HeatmapAdminException('save_failed', 500);
    }

    return $handle;
}

function heatmap_admin_release_map_lock($handle): void
{
    if (is_resource($handle)) {
        flock($handle, LOCK_UN);
        fclose($handle);
    }
}

function heatmap_admin_require_config_hash(array $request, string $currentHash): void
{
    $provided = strval($request['configHash'] ?? '');
    if (preg_match('/^[a-f0-9]{64}$/D', $provided) !== 1 || !hash_equals($currentHash, $provided)) {
        throw new HeatmapAdminException('stale_config', 409);
    }
}

function heatmap_admin_invalidate_alias_payload_caches(string $game, string $map, array $config): void
{
    $map = heatmap_clean_token($map);
    if ($map === '') {
        return;
    }

    $games = array();
    foreach (array($game, $config['game'] ?? '', $config['realgame'] ?? '') as $candidate) {
        $candidate = heatmap_clean_token($candidate);
        if ($candidate !== '') {
            $games[$candidate] = true;
        }
    }
    foreach (array_keys($games) as $cacheGame) {
        heatmap_clear_payload_cache($cacheGame, $map);
    }
}

function heatmap_admin_locked_config(PDO $pdo, string $game, string $map): array
{
    $config = heatmap_fetch_config_for_update($pdo, $game, $map);
    if ($config !== null) {
        return $config;
    }

    $config = heatmap_default_config($pdo, $game, $map);
    if ($config === null || !heatmap_save_config($pdo, $config)) {
        throw new HeatmapAdminException('save_failed', 500);
    }
    $config = heatmap_fetch_config_for_update($pdo, $game, $map);
    if ($config === null) {
        throw new HeatmapAdminException('save_failed', 500);
    }

    return $config;
}

function heatmap_admin_bounded_overview($value): string
{
    if (!is_string($value) || strlen($value) > HEATMAP_ADMIN_MAX_OVERVIEW_BYTES || strpos($value, "\0") !== false) {
        throw new HeatmapAdminException('invalid_request', 400);
    }

    return $value;
}

function heatmap_admin_preview_query(array $request, array $config, string $game, string $map): array
{
    $now = time();
    $to = intdiv($now, 900) * 900;
    $from = $to - min(3650, max(1, intval($config['days'] ?? 30))) * 86400;
    if (array_key_exists('diagnosticFrom', $request) || array_key_exists('diagnosticTo', $request)) {
        $requestedFrom = heatmap_try_canonical_integer($request['diagnosticFrom'] ?? null);
        $requestedTo = heatmap_try_canonical_integer($request['diagnosticTo'] ?? null);
        if ($requestedFrom === null || $requestedTo === null) {
            throw new HeatmapAdminException('invalid_request', 400);
        }
        $from = $requestedFrom;
        $to = $requestedTo;
    }
    $rawFloor = $request['floor'] ?? 'all';
    $floor = is_string($rawFloor) ? $rawFloor : '';
    if ($floor !== 'all' && !heatmap_floor_id_is_valid($floor)) {
        throw new HeatmapAdminException('invalid_request', 400);
    }
    $event = heatmap_clean_event($request['event'] ?? 'both');
    if ($event !== 'kills' && $event !== 'deaths' && $event !== 'both') {
        throw new HeatmapAdminException('invalid_request', 400);
    }

    try {
        return heatmap_parse_v2_query(array(
            'v' => '2',
            'game' => $game,
            'map' => $map,
            'from' => strval($from),
            'to' => strval($to),
            'event' => $event,
            'lens' => 'overview',
            'floor' => $floor,
            'lang' => heatmap_admin_language($request),
        ), $now);
    } catch (InvalidArgumentException $exception) {
        throw new HeatmapAdminException('invalid_request', 400);
    }
}

function heatmap_admin_scene_points(array $scene): array
{
    $points = array();
    $max = 1;
    $bucketSize = max(1, intval($scene['grid']['bucketSize'] ?? 1));
    foreach ($scene['layers']['total'] ?? array() as $row) {
        if (!is_array($row) || count($row) < 5) {
            continue;
        }
        $value = max(0, intval($row[3]) + intval($row[4]));
        if ($value <= 0) {
            continue;
        }
        $max = max($max, $value);
        $points[] = array(
            'x' => intval($row[1]) * $bucketSize + intdiv($bucketSize, 2),
            'y' => intval($row[2]) * $bucketSize + intdiv($bucketSize, 2),
            'value' => $value,
        );
    }

    return array('points' => $points, 'max' => $max);
}

function heatmap_admin_preview_payload(PDO $pdo, array $request, array $storedConfig, string $game, string $map): array
{
    try {
        $config = heatmap_merge_config_override($storedConfig, $request);
    } catch (InvalidArgumentException $exception) {
        throw new HeatmapAdminException('invalid_request', 400);
    }
    if (array_key_exists('overviewText', $request) && strval($request['overviewText']) !== '') {
        try {
            $config = heatmap_parse_overview(heatmap_admin_bounded_overview($request['overviewText']), $config);
        } catch (InvalidArgumentException $exception) {
            throw new HeatmapAdminException('invalid_request', 400);
        }
    }
    $config['map'] = $map;
    $image = heatmap_image_metadata($game, $map, $config);
    if (!is_array($image)) {
        throw new HeatmapAdminException('image_missing', 404);
    }

    try {
        $scene = heatmap_build_scene($pdo, heatmap_admin_preview_query($request, $config, $game, $map), $config, $image);
    } catch (HeatmapAdminException $exception) {
        throw $exception;
    } catch (InvalidArgumentException $exception) {
        throw new HeatmapAdminException('invalid_request', 400);
    } catch (Throwable $exception) {
        throw new HeatmapAdminException('preview_failed', 500);
    }
    $renderImage = is_array($scene['map']['image'] ?? null) ? $scene['map']['image'] : array();
    unset($renderImage['path']);
    $scene['map']['image'] = $renderImage;
    $scene['image'] = $renderImage;
    $scene['projection'] = heatmap_projection_config($config);
    $scene['renderer'] = array(
        'mode' => heatmap_clean_renderer_mode($request['renderer'] ?? 'thermal'),
        'normalization' => heatmap_clean_normalization($request['normalization'] ?? 'sqrt'),
        'alpha' => array('min' => 0.05, 'max' => 0.82),
    );
    $renderPoints = heatmap_admin_scene_points($scene);
    $scene['points'] = $renderPoints['points'];
    $scene['max'] = $renderPoints['max'];
    $coverage = is_array($scene['coverage'] ?? null) ? $scene['coverage'] : array();
    $scene['diagnostics'] = array_replace($coverage, array(
        'queried' => intval($coverage['sourceRows'] ?? 0),
        'manualRequired' => floatval($coverage['projectionCoverage'] ?? 0.0) < HEATMAP_MIN_PROJECTION_COVERAGE,
    ));
    $scene['suggestedFloors'] = heatmap_suggest_floor_bands($coverage['zHistogram'] ?? array());
    $scene['configHash'] = heatmap_admin_config_hash($storedConfig, heatmap_image_metadata($game, $map, $storedConfig));
    return $scene;
}

function heatmap_admin_preview(PDO $pdo, array $request): void
{
    list($game, $map) = heatmap_admin_identify_request($request);
    $config = heatmap_admin_config($pdo, $game, $map);
    if ($config === null) {
        throw new HeatmapAdminException('invalid_request', 404);
    }
    heatmap_admin_json(heatmap_admin_preview_payload($pdo, $request, $config, $game, $map));
}

function heatmap_admin_save(PDO $pdo, $logger, array $request): void
{
    list($game, $map) = heatmap_admin_identify_request($request);
    $language = heatmap_admin_language($request);
    $actorId = heatmap_admin_require_actor($pdo);
    $lock = null;
    $oldHash = '';
    $newHash = '';
    $success = false;
    $status = 500;
    $response = array();
    try {
        $lock = heatmap_admin_open_map_lock($game, $map);
        if (!$pdo->beginTransaction()) {
            throw new HeatmapAdminException('save_failed', 500);
        }
        $storedConfig = heatmap_admin_locked_config($pdo, $game, $map);
        $storedImage = heatmap_image_metadata($game, $map, $storedConfig);
        $oldHash = heatmap_admin_config_hash($storedConfig, $storedImage);
        heatmap_admin_require_config_hash($request, $oldHash);
        try {
            $nextConfig = heatmap_merge_config_override($storedConfig, $request);
        } catch (InvalidArgumentException $exception) {
            throw new HeatmapAdminException('invalid_request', 400);
        }
        if (array_key_exists('overviewText', $request) && strval($request['overviewText']) !== '') {
            $nextConfig = heatmap_parse_overview(heatmap_admin_bounded_overview($request['overviewText']), $nextConfig);
        }
        $nextConfig['map'] = $map;
        if (!heatmap_save_config($pdo, $nextConfig)) {
            throw new HeatmapAdminException('save_failed', 500);
        }
        $readback = heatmap_fetch_config_for_update($pdo, $game, $map);
        if ($readback === null) {
            throw new HeatmapAdminException('save_failed', 500);
        }
        $readbackImage = heatmap_image_metadata($game, $map, $readback);
        $expectedHash = heatmap_admin_config_hash($nextConfig, heatmap_image_metadata($game, $map, $nextConfig));
        $newHash = heatmap_admin_config_hash($readback, $readbackImage);
        if (!hash_equals($expectedHash, $newHash)) {
            throw new HeatmapAdminException('save_failed', 500);
        }
        if (!$pdo->commit()) {
            throw new HeatmapAdminException('save_failed', 500);
        }
        heatmap_admin_invalidate_alias_payload_caches($game, $map, $readback);
        $success = true;
        $status = 200;
        $response = heatmap_admin_result('saved', $language, array(
            'configHash' => $newHash,
            'projection' => heatmap_projection_config($readback),
            'floors' => heatmap_config_floors($readback),
        ));
    } catch (HeatmapAdminException $exception) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        $status = $exception->httpStatus;
        $response = array('ok' => false, 'code' => $exception->safeCode, 'message' => heatmap_admin_message($exception->safeCode, $language));
    } catch (Throwable $exception) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        $response = array('ok' => false, 'code' => 'save_failed', 'message' => heatmap_admin_message('save_failed', $language));
    } finally {
        heatmap_admin_release_map_lock($lock);
        heatmap_admin_log($logger, $actorId, $game, $map, $oldHash, $newHash, $success);
    }

    heatmap_admin_json($response, $status);
}

function heatmap_admin_asset_directory(string $kind, array $config): string
{
    if ($kind !== 'src' && $kind !== 'overviews') {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    $game = heatmap_clean_token($config['game'] ?? '');
    if ($game === '') {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    $directory = dirname(__DIR__) . '/heatmaps/' . $kind . '/' . $game;
    if (!is_dir($directory) && !@mkdir($directory, 0750, true)) {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    if (is_link($directory) || !is_dir($directory) || !is_writable($directory)) {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    @chmod($directory, 0750);
    return $directory;
}

function heatmap_admin_stage_path(string $directory, string $targetName, string $type): string
{
    if (heatmap_clean_token(pathinfo($targetName, PATHINFO_FILENAME)) === ''
        || !in_array($type, array('stage', 'rollback'), true)) {
        throw new HeatmapAdminException('upload_failed', 500);
    }

    return $directory . DIRECTORY_SEPARATOR . '.' . $targetName . '.hlx-' . $type . '-' . bin2hex(random_bytes(16));
}

function heatmap_admin_validate_map_image(array $upload): void
{
    $tmpName = $upload['tmp_name'] ?? null;
    $bytes = is_string($tmpName) && is_uploaded_file($tmpName) ? @filesize($tmpName) : false;
    if (intval($upload['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK
        || !is_string($tmpName)
        || !is_uploaded_file($tmpName)
        || !is_int($bytes)
        || $bytes <= 0
        || $bytes > HEATMAP_ADMIN_MAX_IMAGE_BYTES) {
        throw new HeatmapAdminException('invalid_request', 400);
    }
    $size = @getimagesize($tmpName);
    if (!is_array($size)
        || intval($size[2] ?? 0) !== IMAGETYPE_JPEG
        || intval($size[0] ?? 0) <= 0
        || intval($size[1] ?? 0) <= 0
        || intval($size[0] ?? 0) > HEATMAP_ADMIN_MAX_IMAGE_DIMENSION
        || intval($size[1] ?? 0) > HEATMAP_ADMIN_MAX_IMAGE_DIMENSION) {
        throw new HeatmapAdminException('invalid_request', 400);
    }
}

function heatmap_admin_stage_uploaded_file(string $directory, string $targetName, array $upload, string $kind): array
{
    $stage = heatmap_admin_stage_path($directory, $targetName, 'stage');
    if (!move_uploaded_file($upload['tmp_name'], $stage)) {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    @chmod($stage, 0600);
    return array(
        'kind' => $kind,
        'target' => $directory . DIRECTORY_SEPARATOR . $targetName,
        'stage' => $stage,
        'expected' => heatmap_admin_file_identity($stage),
        'backup' => null,
        'installed' => false,
        'restoreFailed' => false,
    );
}

function heatmap_admin_stage_text_file(string $directory, string $targetName, string $contents, string $kind): array
{
    $stage = heatmap_admin_stage_path($directory, $targetName, 'stage');
    if (file_put_contents($stage, $contents, LOCK_EX) === false) {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    @chmod($stage, 0600);
    return array(
        'kind' => $kind,
        'target' => $directory . DIRECTORY_SEPARATOR . $targetName,
        'stage' => $stage,
        'expected' => heatmap_admin_file_identity($stage),
        'backup' => null,
        'installed' => false,
        'restoreFailed' => false,
    );
}

function heatmap_admin_verify_installed_asset(array $artifact): void
{
    $actual = heatmap_admin_file_identity($artifact['target']);
    if (!hash_equals(strval($artifact['expected']['sha256'] ?? ''), strval($actual['sha256'] ?? ''))
        || intval($artifact['expected']['bytes'] ?? -1) !== intval($actual['bytes'] ?? -2)) {
        throw new HeatmapAdminException('upload_failed', 500);
    }
    if ($artifact['kind'] === 'mapImage') {
        $size = @getimagesize($artifact['target']);
        if (!is_array($size)
            || intval($size[2] ?? 0) !== IMAGETYPE_JPEG
            || intval($size[0] ?? 0) > HEATMAP_ADMIN_MAX_IMAGE_DIMENSION
            || intval($size[1] ?? 0) > HEATMAP_ADMIN_MAX_IMAGE_DIMENSION) {
            throw new HeatmapAdminException('upload_failed', 500);
        }
    }
}

function heatmap_admin_restore_artifacts(array &$artifacts): void
{
    foreach (array_reverse($artifacts, true) as $index => $artifact) {
        $target = $artifact['target'];
        $backup = $artifact['backup'];
        if (is_link($target)) {
            $artifacts[$index]['restoreFailed'] = true;
            continue;
        }
        if (!empty($artifact['installed']) && is_file($target) && !@unlink($target)) {
            $artifacts[$index]['restoreFailed'] = true;
            continue;
        }
        if (is_string($backup) && is_file($backup) && !is_link($backup)) {
            if (@rename($backup, $target)) {
                $artifacts[$index]['backup'] = null;
            } else {
                $artifacts[$index]['restoreFailed'] = true;
            }
        }
    }
}

function heatmap_admin_clean_artifacts(array $artifacts): void
{
    foreach ($artifacts as $artifact) {
        $stage = $artifact['stage'] ?? null;
        if (is_string($stage) && is_file($stage) && !is_link($stage)) {
            @unlink($stage);
        }
        $backup = $artifact['backup'] ?? null;
        if (empty($artifact['restoreFailed'])
            && is_string($backup) && is_file($backup) && !is_link($backup)) {
            @unlink($backup);
        }
    }
}

function heatmap_admin_install_artifacts(array &$artifacts): void
{
    foreach ($artifacts as $index => $artifact) {
        $target = $artifact['target'];
        if (is_link($target)) {
            throw new HeatmapAdminException('upload_failed', 500);
        }
        if (is_file($target)) {
            $backup = heatmap_admin_stage_path(dirname($target), basename($target), 'rollback');
            if (!@rename($target, $backup)) {
                throw new HeatmapAdminException('upload_failed', 500);
            }
            @chmod($backup, 0600);
            $artifacts[$index]['backup'] = $backup;
        }
        if (!@rename($artifact['stage'], $target)) {
            throw new HeatmapAdminException('upload_failed', 500);
        }
        $artifacts[$index]['stage'] = null;
        $artifacts[$index]['installed'] = true;
    }
    foreach ($artifacts as $artifact) {
        heatmap_admin_verify_installed_asset($artifact);
    }
}

function heatmap_admin_upload(PDO $pdo, $logger, array $request): void
{
    list($game, $map) = heatmap_admin_identify_request($request);
    $language = heatmap_admin_language($request);
    $actorId = heatmap_admin_require_actor($pdo);
    $lock = null;
    $artifacts = array();
    $oldHash = '';
    $newHash = '';
    $success = false;
    $status = 500;
    $response = array();
    try {
        $lock = heatmap_admin_open_map_lock($game, $map);
        if (!$pdo->beginTransaction()) {
            throw new HeatmapAdminException('upload_failed', 500);
        }
        $config = heatmap_fetch_config_for_update($pdo, $game, $map);
        if ($config === null) {
            $config = heatmap_default_config($pdo, $game, $map);
        }
        if ($config === null) {
            throw new HeatmapAdminException('invalid_request', 404);
        }
        $oldHash = heatmap_admin_config_hash($config, heatmap_image_metadata($game, $map, $config));
        heatmap_admin_require_config_hash($request, $oldHash);
        if (!empty($_FILES['mapImage']['tmp_name'])) {
            heatmap_admin_validate_map_image($_FILES['mapImage']);
            $artifacts[] = heatmap_admin_stage_uploaded_file(
                heatmap_admin_asset_directory('src', $config),
                $map . '.jpg',
                $_FILES['mapImage'],
                'mapImage'
            );
        }
        $overview = '';
        if (!empty($_FILES['overviewFile']['tmp_name'])) {
            $upload = $_FILES['overviewFile'];
            $overviewTempName = $upload['tmp_name'] ?? null;
            $overviewBytes = is_string($overviewTempName) && is_uploaded_file($overviewTempName)
                ? @filesize($overviewTempName)
                : false;
            if (intval($upload['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK
                || !is_string($overviewTempName)
                || !is_uploaded_file($overviewTempName)
                || !is_int($overviewBytes)
                || $overviewBytes < 0
                || $overviewBytes > HEATMAP_ADMIN_MAX_OVERVIEW_BYTES) {
                throw new HeatmapAdminException('invalid_request', 400);
            }
            $contents = file_get_contents($overviewTempName);
            if (!is_string($contents)) {
                throw new HeatmapAdminException('upload_failed', 500);
            }
            $overview = heatmap_admin_bounded_overview($contents);
        } elseif (array_key_exists('overviewText', $request) && strval($request['overviewText']) !== '') {
            $overview = heatmap_admin_bounded_overview($request['overviewText']);
        }
        if ($overview !== '') {
            $artifacts[] = heatmap_admin_stage_text_file(
                heatmap_admin_asset_directory('overviews', $config),
                $map . '.txt',
                $overview,
                'overview'
            );
        }
        if (!$artifacts) {
            throw new HeatmapAdminException('nothing_uploaded', 400);
        }
        heatmap_admin_install_artifacts($artifacts);
        $newHash = heatmap_admin_config_hash($config, heatmap_image_metadata($game, $map, $config));
        if (!$pdo->commit()) {
            throw new HeatmapAdminException('upload_failed', 500);
        }
        heatmap_admin_invalidate_alias_payload_caches($game, $map, $config);
        $success = true;
        $status = 200;
        $response = heatmap_admin_result('uploaded', $language, array(
            'configHash' => $newHash,
            'projection' => heatmap_projection_config($config),
        ));
    } catch (HeatmapAdminException $exception) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        heatmap_admin_restore_artifacts($artifacts);
        $status = $exception->httpStatus;
        $response = array('ok' => false, 'code' => $exception->safeCode, 'message' => heatmap_admin_message($exception->safeCode, $language));
    } catch (Throwable $exception) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        heatmap_admin_restore_artifacts($artifacts);
        $response = array('ok' => false, 'code' => 'upload_failed', 'message' => heatmap_admin_message('upload_failed', $language));
    } finally {
        heatmap_admin_clean_artifacts($artifacts);
        heatmap_admin_release_map_lock($lock);
        heatmap_admin_log($logger, $actorId, $game, $map, $oldHash, $newHash, $success);
    }

    heatmap_admin_json($response, $status);
}

if (heatmap_admin_reject_oversize_post($_SERVER)) {
    exit;
}
if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}

try {
    heatmap_admin_require_access();
    $container = require __DIR__ . '/bootstrap.php';
    $pdo = $container->get('pdo');
    $logger = $container->get('logger');
    $request = heatmap_admin_request();
    $action = strtolower(strval($request['action'] ?? 'preview'));
    heatmap_admin_require_mutation_allowed($action);

    if ($action === 'games') {
        heatmap_admin_json(array('ok' => true, 'games' => heatmap_fetch_games($pdo)));
    } elseif ($action === 'maps') {
        $game = heatmap_clean_token($request['game'] ?? '');
        heatmap_admin_json(array('ok' => true, 'maps' => $game === '' ? array() : heatmap_fetch_known_maps($pdo, $game)));
    } elseif ($action === 'save') {
        heatmap_admin_save($pdo, $logger, $request);
    } elseif ($action === 'upload') {
        heatmap_admin_upload($pdo, $logger, $request);
    } elseif ($action === 'preview') {
        heatmap_admin_preview($pdo, $request);
    } else {
        throw new HeatmapAdminException('invalid_request', 400);
    }
} catch (HeatmapAdminException $exception) {
    $language = heatmap_admin_language(isset($request) && is_array($request) ? $request : array());
    heatmap_admin_json(array('ok' => false, 'code' => $exception->safeCode, 'message' => heatmap_admin_message($exception->safeCode, $language)), $exception->httpStatus);
} catch (Throwable $exception) {
    $language = heatmap_admin_language(isset($request) && is_array($request) ? $request : array());
    heatmap_admin_json(array('ok' => false, 'code' => 'preview_failed', 'message' => heatmap_admin_message('preview_failed', $language)), 500);
}
