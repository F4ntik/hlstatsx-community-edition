<?php

if (!defined('IN_HLSTATS')) {
    http_response_code(403);
    exit;
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

function heatmap_cache_path($key)
{
    return heatmap_cache_dir() . '/' . preg_replace('/[^a-f0-9]/', '', $key) . '.json';
}

function heatmap_read_payload_cache($key)
{
    $path = heatmap_cache_path($key);
    if (!is_file($path)) {
        return null;
    }

    $payload = json_decode((string) file_get_contents($path), true);
    return is_array($payload) ? $payload : null;
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

    return file_put_contents(heatmap_cache_path($key), json_encode($payload, JSON_UNESCAPED_SLASHES)) !== false;
}

function heatmap_clear_payload_cache($game = '', $map = '')
{
    $dir = heatmap_cache_dir();
    if (!is_dir($dir)) {
        return 0;
    }

    $deleted = 0;
    foreach (glob($dir . '/*.json') as $file) {
        if ($game !== '' || $map !== '') {
            $payload = json_decode((string) @file_get_contents($file), true);
            if (!is_array($payload)) {
                continue;
            }
            if ($game !== '' && strval($payload['game'] ?? '') !== $game) {
                continue;
            }
            if ($map !== '' && strval($payload['map'] ?? '') !== $map) {
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
            hc.cropy2
        FROM hlstats_Games AS g
        INNER JOIN hlstats_Heatmap_Config AS hc ON hc.game = g.realgame
        WHERE g.code = :game AND hc.map = :map
        LIMIT 1'
    );
    $statement->execute(array('game' => $game, 'map' => $map));
    $row = $statement->fetch(PDO::FETCH_ASSOC);

    return $row ?: null;
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
    $config['scale'] = heatmap_scale($config['scale'] ?? 1);
    $config['days'] = max(1, min(3650, intval($config['days'] ?? 30)));
    $config = heatmap_normalize_crop($config);

    return $config;
}

function heatmap_save_config(PDO $pdo, array $config)
{
    $config = heatmap_normalize_crop($config);
    $statement = $pdo->prepare(
        'INSERT INTO hlstats_Heatmap_Config
            (map, game, xoffset, yoffset, flipx, flipy, rotate, days, brush, scale, font, thumbw, thumbh, cropx1, cropy1, cropx2, cropy2)
        VALUES
            (:map, :game, :xoffset, :yoffset, :flipx, :flipy, :rotate, :days, :brush, :scale, :font, :thumbw, :thumbh, :cropx1, :cropy1, :cropx2, :cropy2)
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
            cropy2 = VALUES(cropy2)'
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
        $xExpression = $coordinateMode === 'victim' ? 'COALESCE(hef.pos_victim_x, hef.pos_x)' : 'hef.pos_x';
        $yExpression = $coordinateMode === 'victim' ? 'COALESCE(hef.pos_victim_y, hef.pos_y)' : 'hef.pos_y';
        $heatmapEvent = $coordinateMode === 'victim' ? "'deaths'" : "'kills'";
        $coordinateWhere = $coordinateMode === 'victim'
            ? '((hef.pos_victim_x IS NOT NULL AND hef.pos_victim_y IS NOT NULL) OR (hef.pos_x IS NOT NULL AND hef.pos_y IS NOT NULL))'
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
