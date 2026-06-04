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
    if ($value === '' || !preg_match('/^[A-Za-z0-9_.-]+$/', $value)) {
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

function heatmap_actor_name($name)
{
    $name = is_string($name) ? $name : '';
    $name = str_replace("\xE2\x80\xAE", '', $name);
    $name = trim($name);

    return $name === '' ? 'Unknown' : $name;
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
    $posX = intval($row['pos_x']);
    $posY = intval($row['pos_y']);

    if (!empty($config['flipx'])) {
        $posX *= -1;
    }
    if (!empty($config['flipy'])) {
        $posY *= -1;
    }

    $scale = floatval($config['scale'] ?? 1);
    if ($scale == 0.0) {
        $scale = 1.0;
    }

    return array(
        'x' => intval(($posX + intval($config['xoffset'] ?? 0)) / $scale),
        'y' => intval(($posY + intval($config['yoffset'] ?? 0)) / $scale),
    );
}

function heatmap_build_payload($game, $map, array $image, array $rows, array $config)
{
    $width = intval($image['width'] ?? 0);
    $height = intval($image['height'] ?? 0);
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

    return array(
        'game' => $game,
        'map' => $map,
        'image' => array(
            'url' => strval($image['url'] ?? ''),
            'width' => $width,
            'height' => $height,
        ),
        'points' => $points,
        'max' => max(1, $max),
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
            'config' => array(
                'xoffset' => intval($config['xoffset'] ?? 0),
                'yoffset' => intval($config['yoffset'] ?? 0),
                'flipx' => intval($config['flipx'] ?? 0),
                'flipy' => intval($config['flipy'] ?? 0),
                'rotate' => intval($config['rotate'] ?? 0),
                'scale' => floatval($config['scale'] ?? 1),
            ),
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
            hc.scale
        FROM hlstats_Games AS g
        INNER JOIN hlstats_Heatmap_Config AS hc ON hc.game = g.realgame
        WHERE g.code = :game AND hc.map = :map
        LIMIT 1'
    );
    $statement->execute(array('game' => $game, 'map' => $map));
    $row = $statement->fetch(PDO::FETCH_ASSOC);

    return $row ?: null;
}

function heatmap_fetch_rows(PDO $pdo, array $config, $limit = 10000)
{
    $options = array();
    if (is_array($limit)) {
        $options = $limit;
        $limit = intval($options['limit'] ?? 10000);
    }

    $limit = max(1, min(50000, intval($limit)));
    $days = max(1, intval($config['days'] ?? 30));
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
