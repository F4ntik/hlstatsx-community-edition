<?php

if (!defined('IN_HLSTATS')) {
    http_response_code(403);
    exit;
}

const HEATMAP_V2_SCHEMA = 2;
const HEATMAP_MAX_WINDOW_SECONDS = 315360000;
const HEATMAP_MAX_FLOORS = 8;
const HEATMAP_MEDIUMINT_MIN = -8388608;
const HEATMAP_MEDIUMINT_MAX = 8388607;
const HEATMAP_MYSQL_UNSIGNED_INT_MAX = 4294967295;
const HEATMAP_FLOOR_PARSER_SCHEMA = 1;
const HEATMAP_MAX_SOURCE_ROWS = 250000;
const HEATMAP_GRID_MAX_AXIS = 128;
const HEATMAP_MIN_FLOOR_Z_COVERAGE = 0.70;
const HEATMAP_MIN_PROJECTION_COVERAGE = 0.70;
const HEATMAP_SCENE_CACHE_SCHEMA = 2;
const HEATMAP_SCENE_BUCKET_VERSION = 1;
const HEATMAP_PAYLOAD_CACHE_MAX_AGE = 172800;
const HEATMAP_PAYLOAD_CACHE_PRUNE_LIMIT = 32;

function heatmap_explorer_mode(array $options): int
{
    if (!array_key_exists('HeatmapExplorerBeta', $options)) {
        return 0;
    }

    $value = $options['HeatmapExplorerBeta'];
    if (is_int($value) && $value >= 0 && $value <= 2) {
        return $value;
    }
    if (!is_string($value) || preg_match('/^[012]$/D', $value) !== 1) {
        return 0;
    }

    return intval($value);
}

function heatmap_cache_identity_value($value)
{
    if (!is_array($value)) {
        if (is_int($value) || is_string($value) || is_bool($value) || $value === null) {
            return $value;
        }
        if (is_float($value)) {
            return is_finite($value) ? $value : null;
        }

        return null;
    }

    if (array_is_list($value)) {
        return array_map('heatmap_cache_identity_value', $value);
    }

    $keys = array_keys($value);
    usort($keys, function ($left, $right): int {
        return strcmp(strval($left), strval($right));
    });
    $canonical = array();
    foreach ($keys as $key) {
        $canonical[strval($key)] = heatmap_cache_identity_value($value[$key]);
    }

    return $canonical;
}

function heatmap_scene_cache_key(array $query, array $config, array $image): string
{
    $identity = array(
        'cacheSchema' => HEATMAP_SCENE_CACHE_SCHEMA,
        'responseSchema' => HEATMAP_V2_SCHEMA,
        'bucketVersion' => $config['bucketVersion'] ?? HEATMAP_SCENE_BUCKET_VERSION,
        'query' => array(
            'schemaVersion' => $query['schemaVersion'] ?? HEATMAP_V2_SCHEMA,
            'game' => $query['game'] ?? '',
            'realgame' => $query['realgame'] ?? '',
            'map' => $query['map'] ?? '',
            'player' => $query['player'] ?? 0,
            'lens' => $query['lens'] ?? 'overview',
            'event' => $query['event'] ?? 'both',
            'channel' => $query['channel'] ?? ($query['event'] ?? 'both'),
            'from' => $query['from'] ?? 0,
            'to' => $query['to'] ?? 0,
            'floor' => $query['floor'] ?? 'all',
            'lang' => $query['lang'] ?? 'en',
            'normalization' => $query['normalization'] ?? ($config['normalization'] ?? 'none'),
        ),
        'config' => array(
            'code' => $config['code'] ?? '',
            'game' => $config['game'] ?? '',
            'realgame' => $config['realgame'] ?? '',
            'map' => $config['map'] ?? '',
            'projectionHash' => $config['projectionHash'] ?? ($config['projection_hash'] ?? ($config['configHash'] ?? '')),
            'floorConfigHash' => $config['floorConfigHash'] ?? ($config['floorHash'] ?? ($config['floor_hash'] ?? '')),
            'projection' => $config['projection'] ?? null,
            'floors' => $config['floors'] ?? null,
        ),
        'image' => array(
            'url' => $image['url'] ?? '',
            'width' => $image['width'] ?? 0,
            'height' => $image['height'] ?? 0,
            'sourceIdentity' => $image['sourceIdentity'] ?? ($image['sourceId'] ?? ($image['source'] ?? '')),
        ),
    );
    $encoded = json_encode(
        heatmap_cache_identity_value($identity),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION
    );

    return hash('sha256', is_string($encoded) ? $encoded : 'heatmap-invalid-cache-identity');
}

function heatmap_atomic_write_json(string $path, array $payload): bool
{
    try {
        $encoded = json_encode(
            $payload,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR
        );
    } catch (Throwable $exception) {
        return false;
    }
    if (!is_string($encoded)) {
        return false;
    }

    $directory = dirname($path);
    if (!is_dir($directory) && !@mkdir($directory, 0775, true) && !is_dir($directory)) {
        return false;
    }
    if (is_link($directory) || !is_writable($directory)) {
        return false;
    }

    $staging = null;
    $handle = null;
    try {
        for ($attempt = 0; $attempt < 8; $attempt++) {
            $candidate = $directory . DIRECTORY_SEPARATOR . '.heatmap-' . bin2hex(random_bytes(16)) . '.tmp';
            $candidateHandle = @fopen($candidate, 'x+b');
            if ($candidateHandle !== false) {
                $staging = $candidate;
                $handle = $candidateHandle;
                break;
            }
        }
        if (!is_resource($handle) || $staging === null || !@flock($handle, LOCK_EX)) {
            throw new RuntimeException('cache_stage_failed');
        }

        $length = strlen($encoded);
        $offset = 0;
        while ($offset < $length) {
            $written = @fwrite($handle, substr($encoded, $offset));
            if ($written === false || $written === 0) {
                throw new RuntimeException('cache_write_failed');
            }
            $offset += $written;
        }
        if (!@fflush($handle)) {
            throw new RuntimeException('cache_flush_failed');
        }
        if (!@fclose($handle)) {
            $handle = null;
            throw new RuntimeException('cache_close_failed');
        }
        $handle = null;
        if (!@rename($staging, $path)) {
            throw new RuntimeException('cache_rename_failed');
        }
        $staging = null;
        return true;
    } catch (Throwable $exception) {
        if (is_resource($handle)) {
            @fclose($handle);
        }
        if ($staging !== null) {
            @unlink($staging);
        }

        return false;
    }
}

function heatmap_scene_state_is_cacheable($state): bool
{
    return is_string($state) && in_array($state, array('ok', 'empty', 'insufficient_sample'), true);
}

function heatmap_prune_payload_cache(string $directory, int $now, int $limit = 32): int
{
    $limit = max(0, min(HEATMAP_PAYLOAD_CACHE_PRUNE_LIMIT, $limit));
    if ($limit === 0 || !is_dir($directory) || is_link($directory)) {
        return 0;
    }

    $cutoff = $now - HEATMAP_PAYLOAD_CACHE_MAX_AGE;
    $candidates = array();
    foreach (scandir($directory) ?: array() as $entry) {
        if ($entry === '.' || $entry === '..' || $entry[0] === '.'
            || strpos($entry, '.tmp') !== false || strpos($entry, '.stage') !== false
            || substr($entry, -5) !== '.json') {
            continue;
        }
        $path = $directory . DIRECTORY_SEPARATOR . $entry;
        if (is_link($path) || !is_file($path)) {
            continue;
        }
        $mtime = @filemtime($path);
        if ($mtime === false || $mtime >= $cutoff) {
            continue;
        }
        $candidates[] = array('path' => $path, 'name' => $entry, 'mtime' => intval($mtime));
    }
    usort($candidates, function (array $left, array $right): int {
        $mtimeCompare = $left['mtime'] <=> $right['mtime'];
        return $mtimeCompare !== 0 ? $mtimeCompare : strcmp($left['name'], $right['name']);
    });

    $deleted = 0;
    foreach (array_slice($candidates, 0, $limit) as $candidate) {
        if (@unlink($candidate['path'])) {
            $deleted++;
        }
    }

    return $deleted;
}

function heatmap_log_number($value, float $minimum, float $maximum, bool $fractional)
{
    if (is_string($value) && !is_numeric($value)) {
        $number = 0.0;
    } elseif (is_int($value) || is_float($value) || is_numeric($value)) {
        $number = floatval($value);
    } else {
        $number = 0.0;
    }
    if (!is_finite($number)) {
        $number = 0.0;
    }
    $number = min($maximum, max($minimum, $number));

    return $fractional ? $number : intval($number);
}

function heatmap_log_string($value, string $fallback = ''): string
{
    if (!is_string($value) || strlen($value) > 64
        || preg_match('/^[A-Za-z0-9_.:$-]*$/D', $value) !== 1) {
        return $fallback;
    }

    return $value;
}

function heatmap_request_log(array $metrics): string
{
    $payload = array(
        'version' => heatmap_log_number($metrics['version'] ?? 2, 0, 99, false),
        'operation' => heatmap_log_string($metrics['operation'] ?? 'scene', 'scene'),
        'game' => heatmap_log_string($metrics['game'] ?? ''),
        'map' => heatmap_log_string($metrics['map'] ?? ''),
        'windowClass' => heatmap_log_string($metrics['windowClass'] ?? 'default', 'default'),
        'lens' => heatmap_log_string($metrics['lens'] ?? 'overview', 'overview'),
        'floor' => heatmap_log_string($metrics['floor'] ?? 'all', 'all'),
        'rowsRead' => heatmap_log_number($metrics['rowsRead'] ?? 0, 0, 1000000000, false),
        'binsReturned' => heatmap_log_number($metrics['binsReturned'] ?? 0, 0, 1000000000, false),
        'rawPayloadBytes' => heatmap_log_number($metrics['rawPayloadBytes'] ?? 0, 0, 1000000000, false),
        'queryMs' => heatmap_log_number($metrics['queryMs'] ?? 0, 0, 86400000, true),
        'totalMs' => heatmap_log_number($metrics['totalMs'] ?? 0, 0, 86400000, true),
        'cache' => heatmap_log_string($metrics['cache'] ?? 'miss', 'miss'),
        'xyCoverage' => heatmap_log_number($metrics['xyCoverage'] ?? 0, 0, 1, true),
        'zCoverage' => heatmap_log_number($metrics['zCoverage'] ?? 0, 0, 1, true),
        'projectionCoverage' => heatmap_log_number($metrics['projectionCoverage'] ?? 0, 0, 1, true),
        'state' => heatmap_log_string($metrics['state'] ?? 'unknown', 'unknown'),
        'fallbackReason' => heatmap_log_string($metrics['fallbackReason'] ?? ''),
    );

    $encoded = json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    return is_string($encoded) ? $encoded : '{}';
}

function heatmap_clean_token($value)
{
    if (!is_string($value)) {
        return '';
    }

    $value = trim($value);
    if ($value === '' || !preg_match('/^[A-Za-z0-9_.\-$]+$/', $value)) {
        return '';
    }

    return $value;
}

function heatmap_clean_event($value)
{
    $value = is_string($value) ? strtolower(trim($value)) : '';
    if ($value === 'kill') {
        return 'kills';
    }
    if ($value === 'death') {
        return 'deaths';
    }
    if ($value === 'deaths' || $value === 'both') {
        return $value;
    }

    return 'kills';
}

function heatmap_parse_canonical_integer($value, $errorCode)
{
    if (!is_string($value) || preg_match('/^(?:0|-?[1-9][0-9]*)$/D', $value) !== 1) {
        throw new InvalidArgumentException($errorCode);
    }

    $parsed = filter_var($value, FILTER_VALIDATE_INT);
    if ($parsed === false) {
        throw new InvalidArgumentException($errorCode);
    }

    return intval($parsed);
}

function heatmap_try_canonical_integer($value)
{
    if (is_int($value)) {
        return $value;
    }
    if (!is_string($value) || preg_match('/^(?:0|-?[1-9][0-9]*)$/D', $value) !== 1) {
        return null;
    }

    $parsed = filter_var($value, FILTER_VALIDATE_INT);
    return $parsed === false ? null : intval($parsed);
}

function heatmap_v2_token($value)
{
    if (!is_string($value) || $value === '' || strlen($value) > 64 || heatmap_clean_token($value) !== $value) {
        throw new InvalidArgumentException('invalid_query');
    }

    return $value;
}

function heatmap_floor_id_is_valid($value)
{
    return is_string($value) && preg_match('/^[A-Za-z][A-Za-z0-9_-]{0,31}$/D', $value) === 1;
}

function heatmap_parse_v2_query(array $input, int $now): array
{
    $allowed = array_flip(array(
        'v',
        'game',
        'map',
        'player',
        'range',
        'from',
        'to',
        'event',
        'lens',
        'floor',
        'lang',
        'inspect',
    ));
    foreach ($input as $key => $value) {
        if (!is_string($key) || !isset($allowed[$key]) || !is_string($value)) {
            throw new InvalidArgumentException('invalid_query');
        }
    }

    if (!isset($input['v']) || $input['v'] !== '2'
        || !isset($input['game']) || !isset($input['map'])) {
        throw new InvalidArgumentException('invalid_query');
    }

    $game = heatmap_v2_token($input['game']);
    $map = heatmap_v2_token($input['map']);
    $hasRange = array_key_exists('range', $input);
    $hasFrom = array_key_exists('from', $input);
    $hasTo = array_key_exists('to', $input);
    if (($hasRange && ($hasFrom || $hasTo)) || $hasFrom !== $hasTo) {
        throw new InvalidArgumentException('invalid_window');
    }

    if ($hasRange) {
        $durations = array(
            '7d' => 604800,
            '30d' => 2592000,
            '90d' => 7776000,
            '365d' => 31536000,
        );
        if (!isset($durations[$input['range']])) {
            throw new InvalidArgumentException('invalid_window');
        }
        $to = intdiv($now, 900) * 900;
        $from = $to - $durations[$input['range']];
    } elseif ($hasFrom) {
        $from = heatmap_parse_canonical_integer($input['from'], 'invalid_window');
        $to = heatmap_parse_canonical_integer($input['to'], 'invalid_window');
        if ($from >= $to
            || ($to - $from) > HEATMAP_MAX_WINDOW_SECONDS
            || $to > $now + 300) {
            throw new InvalidArgumentException('invalid_window');
        }
    } else {
        $to = intdiv($now, 900) * 900;
        $from = $to - 2592000;
    }

    $player = 0;
    if (array_key_exists('player', $input)) {
        $player = heatmap_parse_canonical_integer($input['player'], 'invalid_player');
        if ($player <= 0 || $player > HEATMAP_MYSQL_UNSIGNED_INT_MAX) {
            throw new InvalidArgumentException('invalid_player');
        }
    }

    $event = $input['event'] ?? 'both';
    if (!in_array($event, array('kills', 'deaths', 'both'), true)) {
        throw new InvalidArgumentException('invalid_event');
    }
    $lens = $input['lens'] ?? 'overview';
    if (!in_array($lens, array('overview', 'me', 'difference'), true)) {
        throw new InvalidArgumentException('invalid_lens');
    }
    if (($lens === 'me' || $lens === 'difference') && $player <= 0) {
        throw new InvalidArgumentException('player_required');
    }
    if ($lens === 'difference' && $event === 'both') {
        throw new InvalidArgumentException('difference_channel_required');
    }

    $floor = $input['floor'] ?? 'all';
    if ($floor !== 'all' && !heatmap_floor_id_is_valid($floor)) {
        throw new InvalidArgumentException('invalid_floor');
    }
    $lang = $input['lang'] ?? 'en';
    if ($lang !== 'en' && $lang !== 'ru') {
        throw new InvalidArgumentException('invalid_language');
    }

    $query = array(
        'game' => $game,
        'map' => $map,
        'player' => $player,
        'from' => $from,
        'to' => $to,
        'event' => $event,
        'lens' => $lens,
        'floor' => $floor,
        'lang' => $lang,
    );
    if (array_key_exists('inspect', $input)) {
        $inspect = $input['inspect'];
        if (preg_match('/^c(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$/D', $inspect) !== 1) {
            throw new InvalidArgumentException('invalid_inspect');
        }
        $query['inspect'] = $inspect;
    }

    return $query;
}

function heatmap_parse_floor_config($json): array
{
    if ($json === null) {
        return array();
    }
    if (!is_string($json)) {
        throw new InvalidArgumentException('invalid_floor_config');
    }

    $json = trim($json);
    if ($json === '') {
        return array();
    }
    if ($json[0] !== '[') {
        throw new InvalidArgumentException('invalid_floor_config');
    }

    try {
        $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
    } catch (JsonException $exception) {
        throw new InvalidArgumentException('invalid_floor_config');
    }
    if (!is_array($decoded) || !array_is_list($decoded) || count($decoded) > HEATMAP_MAX_FLOORS) {
        throw new InvalidArgumentException('invalid_floor_config');
    }

    $expectedKeys = array('id', 'label_en', 'label_ru', 'z_max', 'z_min');
    sort($expectedKeys, SORT_STRING);
    $floors = array();
    $seenIds = array();
    foreach ($decoded as $floor) {
        if (!is_array($floor)) {
            throw new InvalidArgumentException('invalid_floor_config');
        }
        $keys = array_keys($floor);
        sort($keys, SORT_STRING);
        if ($keys !== $expectedKeys) {
            throw new InvalidArgumentException('invalid_floor_config');
        }

        $id = $floor['id'];
        $labelEn = $floor['label_en'];
        $labelRu = $floor['label_ru'];
        if (!heatmap_floor_id_is_valid($id) || isset($seenIds[$id])
            || !is_string($labelEn) || !is_string($labelRu)) {
            throw new InvalidArgumentException('invalid_floor_config');
        }
        foreach (array($labelEn, $labelRu) as $label) {
            if ($label === '' || preg_match('/^\s|\s$/u', $label) === 1
                || preg_match('//u', $label) !== 1
                || preg_match('/\p{Cc}|\p{Cf}/u', $label) === 1) {
                throw new InvalidArgumentException('invalid_floor_config');
            }
            $codePointCount = preg_match_all('/./u', $label, $matches);
            if ($codePointCount === false || $codePointCount < 1 || $codePointCount > 64) {
                throw new InvalidArgumentException('invalid_floor_config');
            }
        }

        $zMin = $floor['z_min'];
        $zMax = $floor['z_max'];
        if (!is_int($zMin) || !is_int($zMax)
            || $zMin < HEATMAP_MEDIUMINT_MIN || $zMin > HEATMAP_MEDIUMINT_MAX
            || $zMax < HEATMAP_MEDIUMINT_MIN || $zMax > HEATMAP_MEDIUMINT_MAX
            || $zMin >= $zMax) {
            throw new InvalidArgumentException('invalid_floor_config');
        }

        $seenIds[$id] = true;
        $floors[] = array(
            'id' => $id,
            'label_en' => $labelEn,
            'label_ru' => $labelRu,
            'z_min' => $zMin,
            'z_max' => $zMax,
        );
    }

    usort($floors, function ($left, $right) {
        $zCompare = $left['z_min'] <=> $right['z_min'];
        return $zCompare !== 0 ? $zCompare : strcmp($left['id'], $right['id']);
    });
    $previousMax = null;
    foreach ($floors as $floor) {
        if ($previousMax !== null && $floor['z_min'] < $previousMax) {
            throw new InvalidArgumentException('invalid_floor_config');
        }
        $previousMax = $floor['z_max'];
    }

    return $floors;
}

function heatmap_parse_floor_array(array $floors): array
{
    $json = json_encode($floors, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
    if (!is_string($json)) {
        throw new InvalidArgumentException('invalid_floor_config');
    }

    return heatmap_parse_floor_config($json);
}

function heatmap_config_floors(array $config): array
{
    if (array_key_exists('floors', $config)) {
        if (!is_array($config['floors'])) {
            throw new InvalidArgumentException('invalid_floor_config');
        }

        return heatmap_parse_floor_array($config['floors']);
    }

    return heatmap_parse_floor_config($config['floors_json'] ?? null);
}

function heatmap_floor_config_json(array $floors): string
{
    $floors = heatmap_parse_floor_array($floors);
    $json = json_encode($floors, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    if (!is_string($json)) {
        throw new InvalidArgumentException('invalid_floor_config');
    }

    return $json;
}

function heatmap_assign_floor($z, array $floors): ?string
{
    $z = heatmap_try_canonical_integer($z);
    if ($z === null || $z < HEATMAP_MEDIUMINT_MIN || $z > HEATMAP_MEDIUMINT_MAX) {
        return null;
    }

    foreach ($floors as $floor) {
        if (!is_array($floor) || !isset($floor['id'], $floor['z_min'], $floor['z_max'])
            || !heatmap_floor_id_is_valid($floor['id'])
            || !is_int($floor['z_min']) || !is_int($floor['z_max'])) {
            return null;
        }
        if ($z >= $floor['z_min'] && $z < $floor['z_max']) {
            return $floor['id'];
        }
    }

    return null;
}

function heatmap_validate_requested_floor(string $floor, array $floors): string
{
    if ($floor === 'all') {
        return 'all';
    }
    foreach ($floors as $configuredFloor) {
        if (is_array($configuredFloor) && isset($configuredFloor['id'])
            && is_string($configuredFloor['id']) && $configuredFloor['id'] === $floor) {
            return $floor;
        }
    }

    throw new InvalidArgumentException('unknown_floor');
}

function heatmap_scene_sql_context(array $query, array $config): array
{
    $map = heatmap_v2_token($query['map'] ?? '');
    $game = heatmap_v2_token($config['code'] ?? ($query['game'] ?? ''));
    $from = heatmap_try_canonical_integer($query['from'] ?? null);
    $to = heatmap_try_canonical_integer($query['to'] ?? null);
    if ($from === null || $to === null || $from >= $to) {
        throw new InvalidArgumentException('invalid_scene_query');
    }

    return array(
        'map' => $map,
        'game' => $game,
        'from' => $from,
        'to' => $to,
    );
}

function heatmap_build_scene_sql(array $query, array $config): array
{
    $context = heatmap_scene_sql_context($query, $config);
    $limit = HEATMAP_MAX_SOURCE_ROWS + 1;
    $sql = '
        SELECT
            scene_events.eventId,
            scene_events.eventTime,
            scene_events.killerId,
            scene_events.victimId,
            scene_events.weapon,
            scene_events.headshot,
            scene_events.teamkill,
            scene_events.attackerX,
            scene_events.attackerY,
            scene_events.attackerZ,
            scene_events.victimX,
            scene_events.victimY,
            scene_events.victimZ
        FROM (
            SELECT
                hef.id AS eventId,
                hef.eventTime AS eventTime,
                hef.killerId AS killerId,
                hef.victimId AS victimId,
                hef.weapon AS weapon,
                hef.headshot AS headshot,
                0 AS teamkill,
                hef.pos_x AS attackerX,
                hef.pos_y AS attackerY,
                hef.pos_z AS attackerZ,
                hef.pos_victim_x AS victimX,
                hef.pos_victim_y AS victimY,
                hef.pos_victim_z AS victimZ
            FROM hlstats_Events_Frags AS hef
            INNER JOIN hlstats_Servers AS hs ON hs.serverId = hef.serverId
            WHERE hef.map = :frags_map
                AND hs.game = :frags_game
                AND hef.eventTime >= FROM_UNIXTIME(:frags_from)
                AND hef.eventTime < FROM_UNIXTIME(:frags_to)
            UNION ALL
            SELECT
                hef.id AS eventId,
                hef.eventTime AS eventTime,
                hef.killerId AS killerId,
                hef.victimId AS victimId,
                hef.weapon AS weapon,
                0 AS headshot,
                1 AS teamkill,
                hef.pos_x AS attackerX,
                hef.pos_y AS attackerY,
                hef.pos_z AS attackerZ,
                hef.pos_victim_x AS victimX,
                hef.pos_victim_y AS victimY,
                hef.pos_victim_z AS victimZ
            FROM hlstats_Events_Teamkills AS hef
            INNER JOIN hlstats_Servers AS hs ON hs.serverId = hef.serverId
            WHERE hef.map = :teamkills_map
                AND hs.game = :teamkills_game
                AND hef.eventTime >= FROM_UNIXTIME(:teamkills_from)
                AND hef.eventTime < FROM_UNIXTIME(:teamkills_to)
        ) AS scene_events
        LIMIT ' . $limit;
    $params = array(
        'frags_map' => $context['map'],
        'frags_game' => $context['game'],
        'frags_from' => $context['from'],
        'frags_to' => $context['to'],
        'teamkills_map' => $context['map'],
        'teamkills_game' => $context['game'],
        'teamkills_from' => $context['from'],
        'teamkills_to' => $context['to'],
    );

    return array(
        'sql' => $sql,
        'params' => $params,
        'limit' => $limit,
        'suicides' => array(
            'sql' => '
                SELECT COUNT(*) AS excludedSuicides
                FROM hlstats_Events_Suicides AS hes
                INNER JOIN hlstats_Servers AS hs ON hs.serverId = hes.serverId
                WHERE hes.map = :suicides_map
                    AND hs.game = :suicides_game
                    AND hes.eventTime >= FROM_UNIXTIME(:suicides_from)
                    AND hes.eventTime < FROM_UNIXTIME(:suicides_to)',
            'params' => array(
                'suicides_map' => $context['map'],
                'suicides_game' => $context['game'],
                'suicides_from' => $context['from'],
                'suicides_to' => $context['to'],
            ),
        ),
    );
}

function heatmap_scene_bucket_size(int $width, int $height): int
{
    if ($width <= 0 || $height <= 0) {
        throw new InvalidArgumentException('invalid_image');
    }

    return max(4, intval(ceil(max($width, $height) / HEATMAP_GRID_MAX_AXIS)));
}

function heatmap_scene_dimension($value): int
{
    $dimension = heatmap_try_canonical_integer($value);
    if ($dimension === null || $dimension <= 0) {
        throw new InvalidArgumentException('invalid_image');
    }

    return $dimension;
}

function heatmap_scene_player_id($value): ?int
{
    $playerId = heatmap_try_canonical_integer($value);
    if ($playerId === null || $playerId < 0 || $playerId > HEATMAP_MYSQL_UNSIGNED_INT_MAX) {
        return null;
    }

    return $playerId;
}

function heatmap_scene_count($value): int
{
    $count = heatmap_try_canonical_integer($value);
    return $count === null || $count < 0 ? 0 : $count;
}

function heatmap_scene_coordinate($value): array
{
    if ($value === null) {
        return array('status' => 'missing', 'value' => null);
    }

    $coordinate = heatmap_try_canonical_integer($value);
    if ($coordinate === null || $coordinate < HEATMAP_MEDIUMINT_MIN || $coordinate > HEATMAP_MEDIUMINT_MAX) {
        return array('status' => 'malformed', 'value' => null);
    }

    return array('status' => 'valid', 'value' => $coordinate);
}

function heatmap_scene_prepare_state(array &$state): void
{
    if (($state['_sceneReady'] ?? false) === true) {
        return;
    }
    if (!isset($state['query']) || !is_array($state['query'])
        || !isset($state['config']) || !is_array($state['config'])
        || !isset($state['image']) || !is_array($state['image'])) {
        throw new InvalidArgumentException('invalid_scene_state');
    }

    $query = $state['query'];
    $config = $state['config'];
    $context = heatmap_scene_sql_context($query, $config);
    $player = heatmap_scene_player_id($query['player'] ?? 0);
    $event = $query['event'] ?? 'both';
    $lens = $query['lens'] ?? 'overview';
    $floor = $query['floor'] ?? 'all';
    $lang = $query['lang'] ?? 'en';
    if ($player === null || !in_array($event, array('kills', 'deaths', 'both'), true)
        || !in_array($lens, array('overview', 'me', 'difference'), true)
        || !is_string($floor) || !is_string($lang) || ($lang !== 'en' && $lang !== 'ru')
        || (($lens === 'me' || $lens === 'difference') && $player <= 0)
        || ($lens === 'difference' && $event === 'both')) {
        throw new InvalidArgumentException('invalid_scene_query');
    }

    $floors = heatmap_config_floors($config);
    $floor = heatmap_validate_requested_floor($floor, $floors);
    $baseWidth = heatmap_scene_dimension($state['image']['sourceWidth'] ?? $state['image']['width'] ?? null);
    $baseHeight = heatmap_scene_dimension($state['image']['sourceHeight'] ?? $state['image']['height'] ?? null);
    $config = heatmap_normalize_crop($config, $baseWidth, $baseHeight);
    if (strval($state['image']['source'] ?? '') !== 'heatmaps/src') {
        $config['cropx1'] = 0;
        $config['cropy1'] = 0;
        $config['cropx2'] = 0;
        $config['cropy2'] = 0;
    }
    $config['floors'] = $floors;
    $width = heatmap_scene_dimension($state['image']['width'] ?? null);
    $height = heatmap_scene_dimension($state['image']['height'] ?? null);
    $bucketSize = heatmap_scene_bucket_size($width, $height);
    $floorCounts = array();
    foreach ($floors as $configuredFloor) {
        $floorCounts[$configuredFloor['id']] = 0;
    }

    $state['_sceneReady'] = true;
    $state['_scene'] = array(
        'query' => array(
            'game' => heatmap_v2_token($query['game'] ?? $context['game']),
            'map' => $context['map'],
            'player' => $player,
            'from' => $context['from'],
            'to' => $context['to'],
            'event' => $event,
            'lens' => $lens,
            'floor' => $floor,
            'lang' => $lang,
        ),
        'config' => $config,
        'image' => array(
            'url' => is_string($state['image']['url'] ?? null) ? $state['image']['url'] : '',
            'width' => $width,
            'height' => $height,
        ),
        'floors' => $floors,
        'floorCounts' => $floorCounts,
        'bucketSize' => $bucketSize,
        'gridWidth' => intval(ceil($width / $bucketSize)),
        'gridHeight' => intval(ceil($height / $bucketSize)),
        'rowsRead' => 0,
        'sourceRows' => 0,
        'candidate' => 0,
        'validXY' => 0,
        'validZ' => 0,
        'missingCoordinates' => 0,
        'malformedCoordinates' => 0,
        'assigned' => 0,
        'unassigned' => 0,
        'projected' => 0,
        'inBounds' => 0,
        'outOfBounds' => 0,
        'overflow' => false,
        'totalBins' => array(),
        'meBins' => array(),
    );
}

function heatmap_scene_add_bin(array &$bins, string $cellId, int $gridX, int $gridY, string $channel): void
{
    if (!isset($bins[$cellId])) {
        $bins[$cellId] = array(
            'cell' => $cellId,
            'x' => $gridX,
            'y' => $gridY,
            'kills' => 0,
            'deaths' => 0,
        );
    }
    $bins[$cellId][$channel]++;
}

function heatmap_scene_accumulate_contribution(array &$scene, array $row, string $channel, string $participant): void
{
    $scene['candidate']++;
    $x = heatmap_scene_coordinate($row[$participant . 'X'] ?? null);
    $y = heatmap_scene_coordinate($row[$participant . 'Y'] ?? null);
    $z = heatmap_scene_coordinate($row[$participant . 'Z'] ?? null);
    $coordinates = array($x, $y, $z);
    $hasMissing = false;
    $hasMalformed = false;
    foreach ($coordinates as $coordinate) {
        $hasMissing = $hasMissing || $coordinate['status'] === 'missing';
        $hasMalformed = $hasMalformed || $coordinate['status'] === 'malformed';
    }
    if ($hasMissing) {
        $scene['missingCoordinates']++;
    }
    if ($hasMalformed) {
        $scene['malformedCoordinates']++;
    }
    if ($x['status'] !== 'valid' || $y['status'] !== 'valid') {
        return;
    }

    $scene['validXY']++;
    $assignedFloor = null;
    if ($z['status'] === 'valid') {
        $scene['validZ']++;
        if ($scene['floors']) {
            $assignedFloor = heatmap_assign_floor($z['value'], $scene['floors']);
            if ($assignedFloor === null) {
                $scene['unassigned']++;
            } else {
                $scene['assigned']++;
                $scene['floorCounts'][$assignedFloor]++;
            }
        }
    }
    if ($scene['query']['floor'] !== 'all' && $assignedFloor !== $scene['query']['floor']) {
        return;
    }

    $scene['projected']++;
    $point = heatmap_transform_point(array('pos_x' => $x['value'], 'pos_y' => $y['value']), $scene['config']);
    $projectedX = $point['x'];
    $projectedY = $point['y'];
    if ($projectedX < 0 || $projectedY < 0
        || $projectedX >= $scene['image']['width'] || $projectedY >= $scene['image']['height']) {
        $scene['outOfBounds']++;
        return;
    }

    $scene['inBounds']++;
    $gridX = intval(floor($projectedX / $scene['bucketSize']));
    $gridY = intval(floor($projectedY / $scene['bucketSize']));
    $cellId = 'c' . $gridX . '.' . $gridY;
    heatmap_scene_add_bin($scene['totalBins'], $cellId, $gridX, $gridY, $channel);
    $participantId = heatmap_scene_player_id($row[$participant === 'attacker' ? 'killerId' : 'victimId'] ?? null);
    if ($scene['query']['player'] > 0 && $participantId === $scene['query']['player']) {
        heatmap_scene_add_bin($scene['meBins'], $cellId, $gridX, $gridY, $channel);
    }
}

function heatmap_accumulate_scene_row(array &$state, array $row): void
{
    heatmap_scene_prepare_state($state);
    $scene =& $state['_scene'];
    $scene['rowsRead']++;
    if ($scene['rowsRead'] > HEATMAP_MAX_SOURCE_ROWS) {
        $scene['overflow'] = true;
        $scene['totalBins'] = array();
        $scene['meBins'] = array();
        return;
    }

    $scene['sourceRows']++;
    if ($scene['query']['event'] === 'kills' || $scene['query']['event'] === 'both') {
        heatmap_scene_accumulate_contribution($scene, $row, 'kills', 'attacker');
    }
    if ($scene['query']['event'] === 'deaths' || $scene['query']['event'] === 'both') {
        heatmap_scene_accumulate_contribution($scene, $row, 'deaths', 'victim');
    }
}

function heatmap_scene_layer_rows(array $bins): array
{
    $rows = array_values($bins);
    usort($rows, function ($left, $right) {
        $yCompare = $left['y'] <=> $right['y'];
        return $yCompare !== 0 ? $yCompare : ($left['x'] <=> $right['x']);
    });

    return array_map(function ($bin) {
        return array($bin['cell'], $bin['x'], $bin['y'], $bin['kills'], $bin['deaths']);
    }, $rows);
}

function heatmap_scene_layers(array $scene): array
{
    $totalBins = $scene['totalBins'];
    $meBins = array();
    $othersBins = array();
    foreach ($totalBins as $cellId => $total) {
        $me = $scene['meBins'][$cellId] ?? array(
            'cell' => $total['cell'],
            'x' => $total['x'],
            'y' => $total['y'],
            'kills' => 0,
            'deaths' => 0,
        );
        $meBins[$cellId] = $me;
        $othersBins[$cellId] = array(
            'cell' => $total['cell'],
            'x' => $total['x'],
            'y' => $total['y'],
            'kills' => max(0, $total['kills'] - $me['kills']),
            'deaths' => max(0, $total['deaths'] - $me['deaths']),
        );
    }

    return array(
        'total' => heatmap_scene_layer_rows($totalBins),
        'me' => heatmap_scene_layer_rows($meBins),
        'others' => heatmap_scene_layer_rows($othersBins),
    );
}

function heatmap_scene_comparison(array $layers, array $scene): array
{
    $comparison = array(
        'fields' => array('cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'),
        'bins' => array(),
        'personalSample' => 0,
        'otherSample' => 0,
    );
    if ($scene['query']['event'] !== 'kills' && $scene['query']['event'] !== 'deaths') {
        return $comparison;
    }

    $valueIndex = $scene['query']['event'] === 'kills' ? 3 : 4;
    foreach ($layers['me'] as $row) {
        $comparison['personalSample'] += $row[$valueIndex];
    }
    foreach ($layers['others'] as $row) {
        $comparison['otherSample'] += $row[$valueIndex];
    }
    if ($scene['query']['lens'] !== 'difference') {
        return $comparison;
    }

    foreach ($layers['total'] as $index => $row) {
        $me = $layers['me'][$index][$valueIndex];
        $others = $layers['others'][$index][$valueIndex];
        $delta = ($me / max(1, $comparison['personalSample']))
            - ($others / max(1, $comparison['otherSample']));
        $comparison['bins'][] = array(
            $row[0],
            $row[1],
            $row[2],
            $scene['query']['event'] === 'kills' ? $delta : 0.0,
            $scene['query']['event'] === 'deaths' ? $delta : 0.0,
            $me + $others,
        );
    }

    return $comparison;
}

function heatmap_scene_floor_metadata(array $scene, float $zCoverage): array
{
    $metadata = array();
    foreach ($scene['floors'] as $floor) {
        $count = $scene['floorCounts'][$floor['id']] ?? 0;
        $metadata[] = array(
            'id' => $floor['id'],
            'label' => $scene['query']['lang'] === 'ru' ? $floor['label_ru'] : $floor['label_en'],
            'count' => $count,
            'available' => $zCoverage >= HEATMAP_MIN_FLOOR_Z_COVERAGE && $count > 0,
        );
    }

    return $metadata;
}

function heatmap_scene_floor_config_hash(array $floors): string
{
    $encoded = json_encode($floors, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    return substr(sha1(is_string($encoded) ? $encoded : '[]'), 0, 16);
}

function heatmap_finalize_scene(array $state): array
{
    heatmap_scene_prepare_state($state);
    $scene = $state['_scene'];
    $zCoverage = !$scene['floors']
        ? 1.0
        : ($scene['validXY'] > 0 ? floatval($scene['assigned']) / floatval($scene['validXY']) : 0.0);
    $projectionCoverage = $scene['projected'] > 0
        ? floatval($scene['inBounds']) / floatval($scene['projected'])
        : 0.0;
    $xyCoverage = $scene['candidate'] > 0
        ? floatval($scene['validXY']) / floatval($scene['candidate'])
        : 0.0;
    $floors = heatmap_scene_floor_metadata($scene, $zCoverage);
    $activeFloorAvailable = $scene['query']['floor'] === 'all';
    foreach ($floors as $floor) {
        if ($floor['id'] === $scene['query']['floor']) {
            $activeFloorAvailable = $floor['available'];
            break;
        }
    }
    $layers = heatmap_scene_layers($scene);
    $comparison = heatmap_scene_comparison($layers, $scene);
    if ($scene['overflow']) {
        $stateName = 'too_many_events';
    } elseif ($scene['sourceRows'] === 0) {
        $stateName = 'empty';
    } elseif ($scene['validXY'] === 0) {
        $stateName = 'missing_coordinates';
    } elseif ($scene['query']['floor'] !== 'all' && !$activeFloorAvailable) {
        $stateName = 'floors_unavailable';
    } elseif ($scene['projected'] > 0 && $projectionCoverage < HEATMAP_MIN_PROJECTION_COVERAGE) {
        $stateName = 'weak_projection';
    } elseif ($scene['query']['lens'] === 'difference' && $comparison['personalSample'] < 3) {
        $stateName = 'insufficient_sample';
    } else {
        $stateName = 'ok';
    }
    if (in_array($stateName, array('too_many_events', 'missing_coordinates', 'floors_unavailable', 'weak_projection'), true)) {
        $layers = array('total' => array(), 'me' => array(), 'others' => array());
        $comparison['bins'] = array();
    } elseif ($stateName === 'insufficient_sample') {
        $comparison['bins'] = array();
    }
    $warnings = array();
    if ($stateName === 'ok') {
        if ($scene['missingCoordinates'] > 0) {
            $warnings[] = 'missing_coordinates';
        }
        if ($scene['malformedCoordinates'] > 0) {
            $warnings[] = 'malformed_coordinates';
        }
        if ($scene['unassigned'] > 0) {
            $warnings[] = 'unassigned_floor';
        }
        if ($scene['outOfBounds'] > 0) {
            $warnings[] = 'out_of_bounds';
        }
    }
    $game = rawurlencode($scene['query']['game']);
    $map = rawurlencode($scene['query']['map']);
    $excludedSuicides = heatmap_scene_count($state['excludedSuicides'] ?? 0);

    return array(
        'schemaVersion' => HEATMAP_V2_SCHEMA,
        'state' => $stateName,
        'query' => $scene['query'],
        'map' => array(
            'game' => $scene['query']['game'],
            'realgame' => strval($scene['config']['game'] ?? ($scene['config']['realgame'] ?? $scene['query']['game'])),
            'name' => $scene['query']['map'],
            'image' => $scene['image'],
            'projectionHash' => heatmap_config_hash($scene['config'], $scene['image']),
            'floorConfigHash' => heatmap_scene_floor_config_hash($scene['floors']),
        ),
        'floors' => $floors,
        'activeFloor' => $scene['query']['floor'],
        'grid' => array(
            'bucketSize' => $scene['bucketSize'],
            'width' => $scene['gridWidth'],
            'height' => $scene['gridHeight'],
            'fields' => array('cell', 'x', 'y', 'kills', 'deaths'),
        ),
        'layers' => $layers,
        'comparison' => $comparison,
        'coverage' => array(
            'sourceRows' => $scene['sourceRows'],
            'candidate' => $scene['candidate'],
            'validXY' => $scene['validXY'],
            'validZ' => $scene['validZ'],
            'missingCoordinates' => $scene['missingCoordinates'],
            'malformedCoordinates' => $scene['malformedCoordinates'],
            'assigned' => $scene['assigned'],
            'unassigned' => $scene['unassigned'],
            'xyCoverage' => $xyCoverage,
            'zCoverage' => $zCoverage,
            'projected' => $scene['projected'],
            'inBounds' => $scene['inBounds'],
            'outOfBounds' => $scene['outOfBounds'],
            'projectionCoverage' => $projectionCoverage,
        ),
        'summary' => array(
            'rowsRead' => $scene['rowsRead'],
            'sourceRows' => $scene['sourceRows'],
            'candidate' => $scene['candidate'],
            'excludedSuicides' => $excludedSuicides,
            'personalSample' => $comparison['personalSample'],
            'otherSample' => $comparison['otherSample'],
        ),
        'warnings' => $warnings,
        'fallback' => array(
            'v1' => 'heatmap_points.php?game=' . $game . '&map=' . $map,
            'jpeg' => './hlstatsimg/games/' . $game . '/heatmaps/' . $map . '-kill.jpg',
            'thumbnail' => './hlstatsimg/games/' . $game . '/heatmaps/' . $map . '-kill-thumb.jpg',
        ),
    );
}

function heatmap_build_scene(PDO $pdo, array $query, array $config, array $image): array
{
    $descriptor = heatmap_build_scene_sql($query, $config);
    $state = array('query' => $query, 'config' => $config, 'image' => $image);
    $bufferedAttribute = defined('PDO::MYSQL_ATTR_USE_BUFFERED_QUERY')
        ? constant('PDO::MYSQL_ATTR_USE_BUFFERED_QUERY')
        : null;
    if ($bufferedAttribute === null) {
        throw new RuntimeException('mysql_buffering_unavailable');
    }

    $previousBuffered = true;
    try {
        $previousBuffered = $pdo->getAttribute($bufferedAttribute);
    } catch (Throwable $exception) {
        $previousBuffered = true;
    }
    $statement = null;
    $bufferingChanged = false;
    try {
        if (!$pdo->setAttribute($bufferedAttribute, false)) {
            throw new RuntimeException('mysql_buffering_unavailable');
        }
        $bufferingChanged = true;
        $statement = $pdo->prepare($descriptor['sql']);
        if (!$statement instanceof PDOStatement) {
            throw new RuntimeException('scene_statement_unavailable');
        }
        $statement->execute($descriptor['params']);
        while (($row = $statement->fetch(PDO::FETCH_ASSOC)) !== false) {
            heatmap_accumulate_scene_row($state, $row);
        }
    } finally {
        if ($statement instanceof PDOStatement) {
            $statement->closeCursor();
        }
        if ($bufferingChanged) {
            $pdo->setAttribute($bufferedAttribute, $previousBuffered);
        }
    }

    $suicideStatement = $pdo->prepare($descriptor['suicides']['sql']);
    if (!$suicideStatement instanceof PDOStatement) {
        throw new RuntimeException('scene_statement_unavailable');
    }
    try {
        $suicideStatement->execute($descriptor['suicides']['params']);
        $state['excludedSuicides'] = heatmap_scene_count($suicideStatement->fetchColumn());
    } finally {
        $suicideStatement->closeCursor();
    }

    return heatmap_finalize_scene($state);
}

function heatmap_clean_renderer_mode($value)
{
    $value = is_string($value) ? strtolower(trim($value)) : '';
    return $value === 'semantic' ? 'semantic' : 'thermal';
}

function heatmap_clean_normalization($value)
{
    $value = is_string($value) ? strtolower(trim($value)) : '';
    if ($value === 'linear' || $value === 'log') {
        return $value;
    }

    return 'sqrt';
}

function heatmap_actor_name($name)
{
    $name = is_string($name) ? $name : '';
    $name = str_replace("\xE2\x80\xAE", '', $name);
    $name = trim($name);

    return $name === '' ? localized_text('literal.unknown', 'Unknown') : $name;
}

function heatmap_bool($value)
{
    return intval($value) ? 1 : 0;
}

function heatmap_rotation_steps($value)
{
    $steps = intval($value) % 4;
    return $steps < 0 ? $steps + 4 : $steps;
}

function heatmap_rotate_point($x, $y, $steps)
{
    $steps = heatmap_rotation_steps($steps);
    if ($steps === 1) {
        return array('x' => -$y, 'y' => $x);
    }
    if ($steps === 2) {
        return array('x' => -$x, 'y' => -$y);
    }
    if ($steps === 3) {
        return array('x' => $y, 'y' => -$x);
    }

    return array('x' => $x, 'y' => $y);
}

function heatmap_unrotate_point($x, $y, $steps)
{
    return heatmap_rotate_point($x, $y, 4 - heatmap_rotation_steps($steps));
}

function heatmap_scale($value)
{
    $scale = floatval($value);
    return $scale <= 0.0 || !is_finite($scale) ? 1.0 : $scale;
}

function heatmap_normalize_crop(array $config, $imageWidth = null, $imageHeight = null)
{
    $width = $imageWidth === null ? 0 : max(0, intval($imageWidth));
    $height = $imageHeight === null ? 0 : max(0, intval($imageHeight));
    $x1 = max(0, intval($config['cropx1'] ?? 0));
    $y1 = max(0, intval($config['cropy1'] ?? 0));
    $x2 = max(0, intval($config['cropx2'] ?? 0));
    $y2 = max(0, intval($config['cropy2'] ?? 0));

    if ($x2 <= 0 || $y2 <= 0) {
        $x1 = 0;
        $y1 = 0;
        $x2 = 0;
        $y2 = 0;
    } elseif ($width > 0 && $height > 0) {
        $x1 = min($width - 1, $x1);
        $y1 = min($height - 1, $y1);
        $x2 = min($width - $x1, $x2);
        $y2 = min($height - $y1, $y2);
        if ($x2 <= 0 || $y2 <= 0) {
            $x1 = 0;
            $y1 = 0;
            $x2 = 0;
            $y2 = 0;
        }
    }

    $config['cropx1'] = $x1;
    $config['cropy1'] = $y1;
    $config['cropx2'] = $x2;
    $config['cropy2'] = $y2;
    return $config;
}

function heatmap_projection_config(array $config)
{
    $floors = heatmap_config_floors($config);

    return array(
        'xoffset' => intval($config['xoffset'] ?? 0),
        'yoffset' => intval($config['yoffset'] ?? 0),
        'flipx' => heatmap_bool($config['flipx'] ?? 0),
        'flipy' => heatmap_bool($config['flipy'] ?? 0),
        'rotate' => heatmap_rotation_steps($config['rotate'] ?? 0),
        'scale' => heatmap_scale($config['scale'] ?? 1),
        'cropx1' => intval($config['cropx1'] ?? 0),
        'cropy1' => intval($config['cropy1'] ?? 0),
        'cropx2' => intval($config['cropx2'] ?? 0),
        'cropy2' => intval($config['cropy2'] ?? 0),
        'floors' => $floors,
        'floorParserSchema' => HEATMAP_FLOOR_PARSER_SCHEMA,
    );
}

function heatmap_has_crop(array $config)
{
    return intval($config['cropx2'] ?? 0) > 0 && intval($config['cropy2'] ?? 0) > 0;
}

function heatmap_projected_image_size(array $baseImage, array $config)
{
    if (heatmap_has_crop($config)) {
        return array(intval($config['cropx2']), intval($config['cropy2']));
    }

    return array(intval($baseImage['width'] ?? 0), intval($baseImage['height'] ?? 0));
}

function heatmap_source_path(array $config, $map)
{
    return dirname(__DIR__, 2) . '/heatmaps/src/' . heatmap_clean_token($config['game'] ?? '') . '/' . heatmap_clean_token($map) . '.jpg';
}

function heatmap_cache_dir()
{
    return dirname(__DIR__) . '/cache/heatmaps';
}

function heatmap_cache_key(array $parts)
{
    return sha1(json_encode($parts, JSON_UNESCAPED_SLASHES));
}

function heatmap_cache_path($key, ?string $directory = null)
{
    $directory = $directory ?? heatmap_cache_dir();
    return $directory . '/' . preg_replace('/[^a-f0-9]/', '', $key) . '.json';
}

function heatmap_read_payload_cache($key, ?string $directory = null)
{
    $path = heatmap_cache_path($key, $directory);
    if (is_link($path) || !is_file($path)) {
        return null;
    }

    $payload = json_decode((string) file_get_contents($path), true);
    return is_array($payload) ? $payload : null;
}

function heatmap_read_complete_payload_cache($key, ?string $directory = null): ?array
{
    $payload = heatmap_read_payload_cache($key, $directory);
    if (!is_array($payload)
        || !is_int($payload['schemaVersion'] ?? null)
        || $payload['schemaVersion'] !== HEATMAP_V2_SCHEMA
        || !heatmap_scene_state_is_cacheable($payload['state'] ?? null)) {
        return null;
    }
    foreach (array('query', 'map', 'floors', 'grid', 'layers', 'comparison', 'coverage', 'summary', 'warnings', 'fallback') as $field) {
        if (!array_key_exists($field, $payload) || !is_array($payload[$field])) {
            return null;
        }
    }
    if (!is_array($payload['grid']['fields'] ?? null)
        || !is_array($payload['layers']['total'] ?? null)
        || !is_array($payload['layers']['me'] ?? null)
        || !is_array($payload['layers']['others'] ?? null)
        || !is_array($payload['comparison']['bins'] ?? null)) {
        return null;
    }

    return $payload;
}

function heatmap_write_payload_cache($key, array $payload)
{
    $dir = heatmap_cache_dir();
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    if (!is_dir($dir) || !is_writable($dir)) {
        return false;
    }

    $written = heatmap_atomic_write_json(heatmap_cache_path($key), $payload);
    if ($written) {
        heatmap_prune_payload_cache($dir, time());
    }

    return $written;
}

function heatmap_clear_payload_cache($game = '', $map = '', ?string $directory = null)
{
    $dir = $directory ?? heatmap_cache_dir();
    if (!is_dir($dir)) {
        return 0;
    }

    $deleted = 0;
    foreach (scandir($dir) ?: array() as $entry) {
        if ($entry === '.' || $entry === '..' || $entry[0] === '.'
            || substr($entry, -5) !== '.json') {
            continue;
        }
        $file = $dir . DIRECTORY_SEPARATOR . $entry;
        if (is_link($file) || !is_file($file)) {
            continue;
        }
        $payload = json_decode((string) @file_get_contents($file), true);
        if (!is_array($payload)) {
            continue;
        }
        if ($game !== '' || $map !== '') {
            $query = is_array($payload['query'] ?? null) ? $payload['query'] : array();
            $mapPayload = is_array($payload['map'] ?? null) ? $payload['map'] : array();
            $publicGame = is_string($payload['game'] ?? null)
                ? $payload['game']
                : (is_string($query['game'] ?? null)
                    ? $query['game']
                    : (is_string($mapPayload['game'] ?? null) ? $mapPayload['game'] : ''));
            $realGame = is_string($mapPayload['realgame'] ?? null) ? $mapPayload['realgame'] : '';
            $payloadMap = is_string($payload['map'] ?? null)
                ? $payload['map']
                : (is_string($query['map'] ?? null)
                    ? $query['map']
                    : (is_string($mapPayload['name'] ?? null) ? $mapPayload['name'] : ''));
            if ($game !== '' && $publicGame !== $game && $realGame !== $game) {
                continue;
            }
            if ($map !== '' && $payloadMap !== $map) {
                continue;
            }
        }
        if (@unlink($file)) {
            $deleted++;
        }
    }

    return $deleted;
}

function heatmap_config_hash(array $config, array $image = null)
{
    $projection = heatmap_projection_config($config);
    $sourcePath = heatmap_source_path($config, $config['map'] ?? '');
    $payload = array(
        'projection' => $projection,
        'floorParserSchema' => HEATMAP_FLOOR_PARSER_SCHEMA,
        'floors' => $projection['floors'],
        'days' => intval($config['days'] ?? 30),
        'brush' => strval($config['brush'] ?? 'small'),
        'imageMtime' => is_file($sourcePath) ? filemtime($sourcePath) : 0,
    );
    if ($image) {
        $payload['image'] = array(
            'url' => strval($image['url'] ?? ''),
            'width' => intval($image['width'] ?? 0),
            'height' => intval($image['height'] ?? 0),
        );
    }

    return substr(sha1(json_encode($payload, JSON_UNESCAPED_SLASHES)), 0, 16);
}

function heatmap_add_actor(array &$bucket, $group, $id, $name)
{
    $id = intval($id);
    if ($id <= 0) {
        return;
    }

    if (!isset($bucket[$group])) {
        $bucket[$group] = array();
    }
    if (!isset($bucket[$group][$id])) {
        $bucket[$group][$id] = array(
            'id' => $id,
            'name' => heatmap_actor_name($name),
            'count' => 0,
        );
    }
    $bucket[$group][$id]['count']++;
}

function heatmap_top_actors(array $actors, $limit = 5)
{
    usort($actors, function ($left, $right) {
        $countCompare = intval($right['count']) <=> intval($left['count']);
        if ($countCompare !== 0) {
            return $countCompare;
        }

        return strcmp(strval($left['name']), strval($right['name']));
    });

    return array_slice($actors, 0, max(1, intval($limit)));
}

function heatmap_transform_point(array $row, array $config)
{
    $projection = heatmap_projection_config(heatmap_normalize_crop($config));
    $posX = intval($row['pos_x']);
    $posY = intval($row['pos_y']);

    if ($projection['flipx']) {
        $posX *= -1;
    }
    if ($projection['flipy']) {
        $posY *= -1;
    }

    $x = intval(($posX + $projection['xoffset']) / $projection['scale']);
    $y = intval(($posY + $projection['yoffset']) / $projection['scale']);
    $rotated = heatmap_rotate_point($x, $y, $projection['rotate']);
    $x = $rotated['x'];
    $y = $rotated['y'];
    if (heatmap_has_crop($projection)) {
        $x -= $projection['cropx1'];
        $y -= $projection['cropy1'];
    }

    return array('x' => $x, 'y' => $y);
}

function heatmap_image_metadata($game, $map, array $config)
{
    $sourcePath = heatmap_source_path($config, $map);
    if (is_file($sourcePath)) {
        $sourceSize = getimagesize($sourcePath);
        $config = heatmap_normalize_crop($config, intval($sourceSize[0] ?? 0), intval($sourceSize[1] ?? 0));
        $base = array(
            'url' => 'heatmap_map.php?game=' . rawurlencode($game) . '&map=' . rawurlencode($map),
            'width' => intval($sourceSize[0] ?? 0),
            'height' => intval($sourceSize[1] ?? 0),
            'sourceWidth' => intval($sourceSize[0] ?? 0),
            'sourceHeight' => intval($sourceSize[1] ?? 0),
            'source' => 'heatmaps/src',
        );
        if (heatmap_has_crop($config)) {
            $base['url'] .= '&crop=1'
                . '&cropx1=' . intval($config['cropx1'])
                . '&cropy1=' . intval($config['cropy1'])
                . '&cropx2=' . intval($config['cropx2'])
                . '&cropy2=' . intval($config['cropy2'])
                . '&v=' . (is_file($sourcePath) ? intval(filemtime($sourcePath)) : 0);
            list($base['width'], $base['height']) = heatmap_projected_image_size($base, $config);
            $base['crop'] = array(
                'x' => intval($config['cropx1']),
                'y' => intval($config['cropy1']),
                'width' => intval($config['cropx2']),
                'height' => intval($config['cropy2']),
            );
        } else {
            $base['url'] .= '&v=' . (is_file($sourcePath) ? intval(filemtime($sourcePath)) : 0);
        }
        return $base;
    }

    $image = getImage('/games/' . $game . '/maps/' . $map);
    if (!$image && !empty($config['realgame'])) {
        $image = getImage('/games/' . $config['realgame'] . '/maps/' . $map);
    }
    if ($image) {
        $image['source'] = 'hlstatsimg';
        $image['crop'] = null;
    }

    return $image ?: null;
}

function heatmap_build_payload($game, $map, array $image, array $rows, array $config, array $options = array())
{
    $baseWidth = intval($image['sourceWidth'] ?? $image['width'] ?? 0);
    $baseHeight = intval($image['sourceHeight'] ?? $image['height'] ?? 0);
    $config = heatmap_normalize_crop($config, $baseWidth, $baseHeight);
    if (strval($image['source'] ?? '') !== 'heatmaps/src') {
        $config['cropx1'] = 0;
        $config['cropy1'] = 0;
        $config['cropx2'] = 0;
        $config['cropy2'] = 0;
    }
    $width = intval($image['width'] ?? $baseWidth);
    $height = intval($image['height'] ?? $baseHeight);
    $payloadCrop = null;
    if (strval($image['source'] ?? '') === 'heatmaps/src' && heatmap_has_crop($config)) {
        list($width, $height) = heatmap_projected_image_size(
            array('width' => $baseWidth, 'height' => $baseHeight),
            $config
        );
        $payloadCrop = array(
            'x' => intval($config['cropx1']),
            'y' => intval($config['cropy1']),
            'width' => intval($config['cropx2']),
            'height' => intval($config['cropy2']),
        );
    }
    $buckets = array();
    $minX = null;
    $maxX = null;
    $minY = null;
    $maxY = null;
    $rawMinX = null;
    $rawMaxX = null;
    $rawMinY = null;
    $rawMaxY = null;
    $inBounds = 0;
    $outOfBounds = 0;

    foreach ($rows as $row) {
        $rawX = intval($row['pos_x']);
        $rawY = intval($row['pos_y']);
        $rawMinX = ($rawMinX === null) ? $rawX : min($rawMinX, $rawX);
        $rawMaxX = ($rawMaxX === null) ? $rawX : max($rawMaxX, $rawX);
        $rawMinY = ($rawMinY === null) ? $rawY : min($rawMinY, $rawY);
        $rawMaxY = ($rawMaxY === null) ? $rawY : max($rawMaxY, $rawY);

        $point = heatmap_transform_point($row, $config);
        $x = $point['x'];
        $y = $point['y'];

        $minX = ($minX === null) ? $x : min($minX, $x);
        $maxX = ($maxX === null) ? $x : max($maxX, $x);
        $minY = ($minY === null) ? $y : min($minY, $y);
        $maxY = ($maxY === null) ? $y : max($maxY, $y);

        if ($width <= 0 || $height <= 0 || $x < 0 || $y < 0 || $x >= $width || $y >= $height) {
            $outOfBounds++;
            continue;
        }

        $inBounds++;
        $key = $x . ':' . $y;
        if (!isset($buckets[$key])) {
            $buckets[$key] = array(
                'x' => $x,
                'y' => $y,
                'value' => 0,
                'killValue' => 0,
                'deathValue' => 0,
                '_killers' => array(),
                '_victims' => array(),
                '_players' => array(),
            );
        }
        $buckets[$key]['value'] += intval($row['value'] ?? 1);
        $eventType = heatmap_clean_event($row['heatmapEvent'] ?? 'kills');
        if ($eventType === 'deaths') {
            $buckets[$key]['deathValue'] += intval($row['value'] ?? 1);
        } else {
            $buckets[$key]['killValue'] += intval($row['value'] ?? 1);
        }
        heatmap_add_actor($buckets[$key], '_killers', $row['killerId'] ?? 0, $row['killerName'] ?? '');
        heatmap_add_actor($buckets[$key], '_victims', $row['victimId'] ?? 0, $row['victimName'] ?? '');
        heatmap_add_actor($buckets[$key], '_players', $row['killerId'] ?? 0, $row['killerName'] ?? '');
        heatmap_add_actor($buckets[$key], '_players', $row['victimId'] ?? 0, $row['victimName'] ?? '');
    }

    $points = array();
    foreach ($buckets as $bucket) {
        $bucket['topKillers'] = heatmap_top_actors(array_values($bucket['_killers']));
        $bucket['topVictims'] = heatmap_top_actors(array_values($bucket['_victims']));
        $bucket['topPlayers'] = heatmap_top_actors(array_values($bucket['_players']));
        unset($bucket['_killers'], $bucket['_victims'], $bucket['_players']);
        $points[] = $bucket;
    }
    $max = 0;
    foreach ($points as $point) {
        $max = max($max, intval($point['value']));
    }
    $inBoundsRatio = count($rows) > 0 ? $inBounds / count($rows) : 0;
    $renderer = heatmap_clean_renderer_mode($options['renderer'] ?? 'thermal');
    $normalization = heatmap_clean_normalization($options['normalization'] ?? 'sqrt');

    return array(
        'game' => $game,
        'map' => $map,
        'image' => array(
            'url' => strval($image['url'] ?? ''),
            'width' => $width,
            'height' => $height,
            'source' => strval($image['source'] ?? ''),
            'crop' => $payloadCrop,
        ),
        'points' => $points,
        'max' => max(1, $max),
        'renderer' => array(
            'mode' => $renderer,
            'normalization' => $normalization,
            'alpha' => array('min' => 0.05, 'max' => 0.82),
        ),
        'projection' => heatmap_projection_config($config),
        'configHash' => heatmap_config_hash($config, $image),
        'diagnostics' => array(
            'queried' => count($rows),
            'inBounds' => $inBounds,
            'outOfBounds' => $outOfBounds,
            'inBoundsRatio' => $inBoundsRatio,
            'manualRequired' => count($rows) > 0 && $inBoundsRatio < 0.8,
            'minX' => $minX,
            'maxX' => $maxX,
            'minY' => $minY,
            'maxY' => $maxY,
            'raw' => array(
                'minX' => $rawMinX,
                'maxX' => $rawMaxX,
                'minY' => $rawMinY,
                'maxY' => $rawMaxY,
            ),
            'transformed' => array(
                'minX' => $minX,
                'maxX' => $maxX,
                'minY' => $minY,
                'maxY' => $maxY,
            ),
            'image' => array(
                'width' => $width,
                'height' => $height,
            ),
            'config' => heatmap_projection_config($config),
        ),
    );
}

function heatmap_fetch_config(PDO $pdo, $game, $map)
{
    $statement = $pdo->prepare(
        'SELECT
            g.code,
            g.realgame,
            hc.map,
            hc.game,
            hc.xoffset,
            hc.yoffset,
            hc.flipx,
            hc.flipy,
            hc.rotate,
            hc.days,
            hc.brush,
            hc.scale,
            hc.font,
            hc.thumbw,
            hc.thumbh,
            hc.cropx1,
            hc.cropy1,
            hc.cropx2,
            hc.cropy2,
            hc.floors_json
        FROM hlstats_Games AS g
        INNER JOIN hlstats_Heatmap_Config AS hc ON hc.game = g.realgame
        WHERE g.code = :game AND hc.map = :map
        LIMIT 1'
    );
    $statement->execute(array('game' => $game, 'map' => $map));
    $row = $statement->fetch(PDO::FETCH_ASSOC);

    if (!$row) {
        return null;
    }

    $row['floors'] = heatmap_parse_floor_config($row['floors_json'] ?? null);
    $row['floors_json'] = heatmap_floor_config_json($row['floors']);
    return $row;
}

function heatmap_default_config(PDO $pdo, $game, $map)
{
    $statement = $pdo->prepare('SELECT code, realgame FROM hlstats_Games WHERE code = :game LIMIT 1');
    $statement->execute(array('game' => $game));
    $row = $statement->fetch(PDO::FETCH_ASSOC);
    if (!$row) {
        return null;
    }

    return array(
        'code' => $row['code'],
        'realgame' => $row['realgame'],
        'map' => $map,
        'game' => $row['realgame'],
        'xoffset' => 0,
        'yoffset' => 0,
        'flipx' => 0,
        'flipy' => 1,
        'rotate' => 0,
        'days' => 30,
        'brush' => 'small',
        'scale' => 1,
        'font' => 10,
        'thumbw' => 0.170312,
        'thumbh' => 0.170312,
        'cropx1' => 0,
        'cropy1' => 0,
        'cropx2' => 0,
        'cropy2' => 0,
        'floors' => array(),
        'floors_json' => '[]',
    );
}

function heatmap_merge_config_override(array $config, array $values)
{
    foreach (array('xoffset', 'yoffset', 'cropx1', 'cropy1', 'cropx2', 'cropy2', 'days', 'font') as $field) {
        if (isset($values[$field]) && $values[$field] !== '') {
            $config[$field] = intval($values[$field]);
        }
    }
    foreach (array('flipx', 'flipy') as $field) {
        if (isset($values[$field]) && $values[$field] !== '') {
            $config[$field] = heatmap_bool($values[$field]);
        }
    }
    if (isset($values['rotate']) && $values['rotate'] !== '') {
        $config['rotate'] = heatmap_rotation_steps($values['rotate']);
    }
    foreach (array('scale', 'thumbw', 'thumbh') as $field) {
        if (isset($values[$field]) && $values[$field] !== '') {
            $config[$field] = floatval($values[$field]);
        }
    }
    if (isset($values['brush']) && preg_match('/^[A-Za-z0-9_-]{1,16}$/', strval($values['brush']))) {
        $config['brush'] = strval($values['brush']);
    }
    if (array_key_exists('floors_json', $values)) {
        $floors = heatmap_parse_floor_config($values['floors_json']);
    } elseif (array_key_exists('floors', $values)) {
        if (!is_array($values['floors'])) {
            throw new InvalidArgumentException('invalid_floor_config');
        }
        $floors = heatmap_parse_floor_array($values['floors']);
    } else {
        $floors = heatmap_config_floors($config);
    }
    $config['floors'] = $floors;
    $config['floors_json'] = heatmap_floor_config_json($floors);
    $config['scale'] = heatmap_scale($config['scale'] ?? 1);
    $config['days'] = max(1, min(3650, intval($config['days'] ?? 30)));
    $config = heatmap_normalize_crop($config);

    return $config;
}

function heatmap_save_config(PDO $pdo, array $config)
{
    $config = heatmap_normalize_crop($config);
    $config['floors'] = heatmap_config_floors($config);
    $config['floors_json'] = heatmap_floor_config_json($config['floors']);
    $statement = $pdo->prepare(
        'INSERT INTO hlstats_Heatmap_Config
            (map, game, xoffset, yoffset, flipx, flipy, rotate, days, brush, scale, font, thumbw, thumbh, cropx1, cropy1, cropx2, cropy2, floors_json)
        VALUES
            (:map, :game, :xoffset, :yoffset, :flipx, :flipy, :rotate, :days, :brush, :scale, :font, :thumbw, :thumbh, :cropx1, :cropy1, :cropx2, :cropy2, :floors_json)
        ON DUPLICATE KEY UPDATE
            xoffset = VALUES(xoffset),
            yoffset = VALUES(yoffset),
            flipx = VALUES(flipx),
            flipy = VALUES(flipy),
            rotate = VALUES(rotate),
            days = VALUES(days),
            brush = VALUES(brush),
            scale = VALUES(scale),
            font = VALUES(font),
            thumbw = VALUES(thumbw),
            thumbh = VALUES(thumbh),
            cropx1 = VALUES(cropx1),
            cropy1 = VALUES(cropy1),
            cropx2 = VALUES(cropx2),
            cropy2 = VALUES(cropy2),
            floors_json = VALUES(floors_json)'
    );
    return $statement->execute(array(
        'map' => $config['map'],
        'game' => $config['game'],
        'xoffset' => intval($config['xoffset']),
        'yoffset' => intval($config['yoffset']),
        'flipx' => heatmap_bool($config['flipx']),
        'flipy' => heatmap_bool($config['flipy']),
        'rotate' => heatmap_rotation_steps($config['rotate']),
        'days' => max(1, intval($config['days'])),
        'brush' => strval($config['brush'] ?? 'small'),
        'scale' => heatmap_scale($config['scale']),
        'font' => intval($config['font'] ?? 10),
        'thumbw' => floatval($config['thumbw'] ?? 0.170312),
        'thumbh' => floatval($config['thumbh'] ?? 0.170312),
        'cropx1' => intval($config['cropx1'] ?? 0),
        'cropy1' => intval($config['cropy1'] ?? 0),
        'cropx2' => intval($config['cropx2'] ?? 0),
        'cropy2' => intval($config['cropy2'] ?? 0),
        'floors_json' => $config['floors_json'],
    ));
}

function heatmap_fetch_rows(PDO $pdo, array $config, $limit = 10000)
{
    $options = array();
    if (is_array($limit)) {
        $options = $limit;
        $limit = intval($options['limit'] ?? 10000);
    }

    $limit = max(1, min(50000, intval($limit)));
    $days = max(1, intval($options['days'] ?? ($config['days'] ?? 30)));
    $boundary = time() - (60 * 60 * 24 * $days);
    $playerId = max(0, intval($options['playerId'] ?? 0));
    $event = heatmap_clean_event($options['event'] ?? 'kills');
    $queryParts = array();
    $params = array();

    $addPart = function ($table, $prefix, $coordinateMode, $playerClause) use (&$queryParts, &$params, $config, $boundary, $limit) {
        $xExpression = $coordinateMode === 'victim' ? 'hef.pos_victim_x' : 'hef.pos_x';
        $yExpression = $coordinateMode === 'victim' ? 'hef.pos_victim_y' : 'hef.pos_y';
        $heatmapEvent = $coordinateMode === 'victim' ? "'deaths'" : "'kills'";
        $coordinateWhere = $coordinateMode === 'victim'
            ? '(hef.pos_victim_x IS NOT NULL AND hef.pos_victim_y IS NOT NULL)'
            : '(hef.pos_x IS NOT NULL AND hef.pos_y IS NOT NULL)';

        $queryParts[] = '
        (
            SELECT
                ' . $xExpression . ' AS pos_x,
                ' . $yExpression . ' AS pos_y,
                1 AS value,
                ' . $heatmapEvent . ' AS heatmapEvent,
                hef.killerId,
                kp.lastName AS killerName,
                hef.victimId,
                vp.lastName AS victimName
            FROM ' . $table . ' AS hef
            INNER JOIN hlstats_Servers AS hs ON hs.serverId = hef.serverId
            LEFT JOIN hlstats_Players AS kp ON kp.playerId = hef.killerId
            LEFT JOIN hlstats_Players AS vp ON vp.playerId = hef.victimId
            WHERE hef.map = :' . $prefix . '_map
                AND hs.game = :' . $prefix . '_game
                AND ' . $coordinateWhere . '
                AND hef.eventTime >= FROM_UNIXTIME(:' . $prefix . '_boundary)
                ' . $playerClause . '
            LIMIT ' . $limit . '
        )';
        $params[$prefix . '_map'] = $config['map'];
        $params[$prefix . '_game'] = $config['code'];
        $params[$prefix . '_boundary'] = $boundary;
    };

    if ($playerId > 0) {
        if ($event === 'kills' || $event === 'both') {
            $addPart('hlstats_Events_Frags', 'frag_kills', 'killer', 'AND hef.killerId = :frag_kills_player');
            $params['frag_kills_player'] = $playerId;
            $addPart('hlstats_Events_Teamkills', 'teamkill_kills', 'killer', 'AND hef.killerId = :teamkill_kills_player');
            $params['teamkill_kills_player'] = $playerId;
        }
        if ($event === 'deaths' || $event === 'both') {
            $addPart('hlstats_Events_Frags', 'frag_deaths', 'victim', 'AND hef.victimId = :frag_deaths_player');
            $params['frag_deaths_player'] = $playerId;
            $addPart('hlstats_Events_Teamkills', 'teamkill_deaths', 'victim', 'AND hef.victimId = :teamkill_deaths_player');
            $params['teamkill_deaths_player'] = $playerId;
        }
    } else {
        $addPart('hlstats_Events_Frags', 'frag', 'killer', '');
        $addPart('hlstats_Events_Teamkills', 'teamkill', 'killer', '');
    }

    if (!$queryParts) {
        return array();
    }

    $statement = $pdo->prepare(implode(' UNION ALL ', $queryParts));
    $statement->execute($params);

    return $statement->fetchAll(PDO::FETCH_ASSOC);
}

function heatmap_fetch_games(PDO $pdo)
{
    $statement = $pdo->query('SELECT code, name, realgame FROM hlstats_Games ORDER BY name ASC, code ASC');
    return $statement->fetchAll(PDO::FETCH_ASSOC);
}

function heatmap_fetch_known_maps(PDO $pdo, $game)
{
    $statement = $pdo->prepare(
        'SELECT map FROM (
            SELECT DISTINCT hef.map, 0 AS priority FROM hlstats_Events_Frags hef
            INNER JOIN hlstats_Servers hs ON hs.serverId = hef.serverId
            INNER JOIN hlstats_Games g ON g.code = hs.game
            INNER JOIN hlstats_Heatmap_Config hc ON hc.game = g.realgame AND hc.map = hef.map
            WHERE hs.game = :game_ready AND hef.map <> ""
            UNION ALL
            SELECT hc.map, 1 AS priority FROM hlstats_Heatmap_Config hc
            INNER JOIN hlstats_Games g ON g.realgame = hc.game
            WHERE g.code = :game_config
            UNION ALL
            SELECT DISTINCT hef.map, 2 AS priority FROM hlstats_Events_Frags hef
            INNER JOIN hlstats_Servers hs ON hs.serverId = hef.serverId
            WHERE hs.game = :game_events AND hef.map <> ""
        ) maps
        GROUP BY map
        ORDER BY MIN(priority) ASC, map ASC
        LIMIT 300'
    );
    $statement->execute(array('game_ready' => $game, 'game_config' => $game, 'game_events' => $game));
    return $statement->fetchAll(PDO::FETCH_COLUMN);
}

function heatmap_parse_overview($content, array $config)
{
    $content = strval($content);
    $sourcePairs = array();
    if (preg_match_all('/"(?P<key>[^"]+)"\s+"?(?P<value>[^"\r\n]+)"?/i', $content, $matches, PREG_SET_ORDER)) {
        foreach ($matches as $match) {
            $sourcePairs[strtolower(trim($match['key']))] = trim($match['value']);
        }
    }
    if (isset($sourcePairs['pos_x'], $sourcePairs['pos_y'], $sourcePairs['scale'])) {
        return heatmap_merge_config_override($config, array(
            'xoffset' => round(-floatval($sourcePairs['pos_x'])),
            'yoffset' => round(floatval($sourcePairs['pos_y'])),
            'scale' => floatval($sourcePairs['scale']),
            'flipx' => 0,
            'flipy' => 1,
            'rotate' => (isset($sourcePairs['rotate']) && !in_array(strtolower($sourcePairs['rotate']), array('0', 'false'), true)) ? 1 : 0,
        ));
    }

    $gold = array();
    if (preg_match('/^\s*ZOOM\s+([-0-9.]+)/mi', $content, $match)) {
        $gold['scale'] = floatval($match[1]);
    }
    if (preg_match('/^\s*ORIGIN\s+([-0-9.]+)\s+([-0-9.]+)/mi', $content, $match)) {
        $gold['xoffset'] = round(-floatval($match[1]));
        $gold['yoffset'] = round(floatval($match[2]));
    }
    if (preg_match('/^\s*ROTATED\s+([^\r\n]+)/mi', $content, $match)) {
        $gold['rotate'] = !in_array(strtolower(trim($match[1])), array('0', 'false'), true) ? 1 : 0;
    }
    if (isset($gold['xoffset'], $gold['yoffset'], $gold['scale'])) {
        $gold['flipx'] = 0;
        $gold['flipy'] = 1;
        return heatmap_merge_config_override($config, $gold);
    }

    throw new InvalidArgumentException('overview file did not contain supported projection fields');
}
