<?php
// Prepared topology only. No BSP parsing or nearest-room snapping in requests.
function heatmap_surface_path(array $config, string $map): ?string
{
    if (($config['game'] ?? $config['realgame'] ?? '') !== 'cstrike'
        || preg_match('/^[A-Za-z0-9_-]{1,64}$/D', $map) !== 1) return null;
    return __DIR__ . '/../hlstatsimg/heatmap-surfaces/cstrike/' . $map . '.json';
}

function heatmap_surface_identity(array $config, string $map): string
{
    $path = heatmap_surface_path($config, $map);
    return $path && is_file($path) && filesize($path) <= 6500000 ? hash_file('sha256', $path) : 'absent';
}

function heatmap_surface_region_covers_cell(array $polygon, array $cell): bool
{
    foreach ($cell as $p) if (!heatmap_region_contains($polygon, $p[0], $p[1])) return false;
    $left = $cell[0][0]; $top = $cell[0][1]; $right = $cell[2][0]; $bottom = $cell[2][1];
    // A concave notch can enter a cell even when all corners are inside.
    // Reject any polygon boundary crossing the open cell interior.
    foreach ($polygon as $i => $a) {
        $b = $polygon[($i + 1) % count($polygon)]; $low = 0.0; $high = 1.0;
        for ($axis = 0; $axis < 2; $axis++) {
            $delta = $b[$axis] - $a[$axis];
            $min = $axis ? $top : $left; $max = $axis ? $bottom : $right;
            if ($delta == 0) {
                if ($a[$axis] < $min || $a[$axis] > $max) { $low = 1; $high = 0; break; }
            } else {
                $t1 = ($min - $a[$axis]) / $delta; $t2 = ($max - $a[$axis]) / $delta;
                $low = max($low, min($t1, $t2)); $high = min($high, max($t1, $t2));
            }
        }
        if ($low <= $high) {
            $t = ($low + $high) / 2;
            $x = $a[0] + ($b[0] - $a[0]) * $t; $y = $a[1] + ($b[1] - $a[1]) * $t;
            if ($x > $left && $x < $right && $y > $top && $y < $bottom) return false;
        }
    }
    return true;
}

function heatmap_surface_floor_allowed(float $z, float $x, float $y, array $floors, string $selected, float $halfX = 0, float $halfY = 0): bool
{
    if (!$floors) return $selected === 'all';
    $found = false;
    $cell = array(array($x-$halfX,$y-$halfY),array($x+$halfX,$y-$halfY),array($x+$halfX,$y+$halfY),array($x-$halfX,$y+$halfY));
    foreach ($floors as $floor) {
        if ($selected !== 'all' && $floor['id'] !== $selected) continue;
        // Use the same admissible origin interval as XYZ assignment, not a guessed single origin.
        if ($z + 80 < $floor['z_min'] || $z - 8 >= $floor['z_max']) continue;
        $found = true;
        if (!empty($floor['regions'])) {
            $covered = false;
            // Conservatively require one region to contain the whole cell. Corners
            // belonging to different regions must never bridge an excluded gap.
            foreach ($floor['regions'] as $polygon) if (heatmap_surface_region_covers_cell($polygon, $cell)) { $covered = true; break; }
            if (!$covered) return false;
        }
        foreach ($floor['blocked'] ?? array() as $polygon) {
            if (heatmap_regions_overlap(array($cell), array($polygon))) return false;
        }
    }
    // All-floor nodes outside configured bands retain ordinary unconfigured surfaces.
    return $selected === 'all' || $found;
}

function heatmap_surface_load(array $config, array $image, string $map, string $floor): array
{
    $result = array('state' => 'missing_asset', 'asset' => null, 'rows' => array(),
        'allowedData' => '', 'diagnostics' => array('candidate' => 0, 'assigned' => 0,
        'missingZ' => 0, 'ambiguous' => 0, 'offSurface' => 0, 'excluded' => 0));
    $path = heatmap_surface_path($config, $map);
    if (!$path || !is_file($path)) return $result;
    $result['state'] = 'invalid_asset';
    if (filesize($path) > 6500000) return $result;
    $json = file_get_contents($path);
    $a = json_decode($json, true, 32);
    if (!is_array($a) || ($a['schemaVersion'] ?? null) !== 1 || ($a['map'] ?? null) !== $map) return $result;
    $n = $a['nodeCount'] ?? null; $e = $a['edgeCount'] ?? null;
    $w = $a['grid']['width'] ?? null; $h = $a['grid']['height'] ?? null;
    if (!is_int($n) || $n < 1 || $n > 196608 || !is_int($e) || $e < 0 || $e > 393216
        || !is_int($w) || !is_int($h) || $w < 1 || $w > 512 || $h < 1 || $h > 384) return $result;
    foreach (array('pixelData' => $n * 4, 'heightData' => $n * 4, 'edgeData' => $e * 8) as $key => $length) {
        if (!is_string($a[$key] ?? null) || strlen($a[$key]) !== 4 * intval(ceil($length / 3))) return $result;
        $decoded = base64_decode($a[$key], true);
        if ($decoded === false || strlen($decoded) !== $length) return $result;
        if ($key !== 'edgeData') $a[$key] = $decoded;
    }
    $result['state'] = 'identity_mismatch';
    $source = heatmap_floor_source_path($config, $map, $floor) ?? heatmap_source_path($config, $map);
    if (!is_file($source) || ($image['source'] ?? '') !== 'heatmaps/src'
        || ($a['image']['width'] ?? 0) !== $image['width'] || ($a['image']['height'] ?? 0) !== $image['height']
        || ($a['image']['sha256'] ?? '') !== hash_file('sha256', $source)) return $result;
    $projection = heatmap_projection_config($config);
    foreach (array('xoffset','yoffset','flipx','flipy','rotate','scale','cropx1','cropy1','cropx2','cropy2') as $key) {
        // MySQL FLOAT serializes seeded 5.333333... as 5.33333. This tolerance is
        // about 0.001 image pixels across a native 1024-pixel overview.
        $tolerance = $key === 'scale' ? max(0.000001, abs($projection[$key]) * 0.000001) : 0;
        if (!isset($a['projection'][$key]) || !(is_numeric($a['projection'][$key]) || (in_array($key, array('flipx','flipy'), true) && is_bool($a['projection'][$key])))
            || abs(floatval($a['projection'][$key]) - $projection[$key]) > $tolerance) return $result;
    }
    $pixels = array_values(unpack('V*', $a['pixelData']));
    $heights = array_values(unpack('g*', $a['heightData']));
    $byPixel = array(); $allowed = ''; $lastPixel = -1; $lastZ = -INF; $stackSize = 0;
    for ($i = 0; $i < $n; $i++) {
        $pixel = $pixels[$i]; $z = $heights[$i];
        if ($pixel >= $w * $h || !is_finite($z) || abs($z) > 8388608
            || $pixel < $lastPixel || ($pixel === $lastPixel && $z <= $lastZ)) { $result['state'] = 'invalid_asset'; return $result; }
        $stackSize = $pixel === $lastPixel ? $stackSize + 1 : 1;
        $lastPixel = $pixel; $lastZ = $z;
        if (!isset($byPixel[$pixel])) $byPixel[$pixel] = $i;
        if ($stackSize > 16) { $result['state'] = 'invalid_asset'; return $result; }
        if (empty($config['floors'])) { $allowed .= "\1"; continue; }
        $p = heatmap_unrotate_point(($pixel % $w + 0.5) * $image['width'] / $w + $projection['cropx1'],
            (intdiv($pixel, $w) + 0.5) * $image['height'] / $h + $projection['cropy1'], $projection['rotate']);
        $x = ($p['x'] * $projection['scale'] - $projection['xoffset']) * ($projection['flipx'] ? -1 : 1);
        $y = ($p['y'] * $projection['scale'] - $projection['yoffset']) * ($projection['flipy'] ? -1 : 1);
        $halfX = $image['width'] / $w * $projection['scale'] / 2;
        $halfY = $image['height'] / $h * $projection['scale'] / 2;
        if ($projection['rotate'] % 2) { $swap = $halfX; $halfX = $halfY; $halfY = $swap; }
        $allowed .= heatmap_surface_floor_allowed($z, $x, $y, $config['floors'], $floor, $halfX, $halfY) ? "\1" : "\0";
    }
    $result['state'] = 'ready';
    $result['asset'] = array('url' => 'hlstatsimg/heatmap-surfaces/cstrike/' . $map . '.json',
        'sha256' => hash('sha256', $json), 'grid' => array('width' => $w, 'height' => $h), 'nodeCount' => $n, 'edgeCount' => $e);
    $result['allowedData'] = base64_encode($allowed);
    $result['_allowed'] = $allowed; $result['_starts'] = $byPixel;
    $result['_pixels'] = $a['pixelData']; $result['_heights'] = $a['heightData'];
    return $result;
}

function heatmap_surface_accumulate(array &$scene, array $z, float $x, float $y, string $channel, bool $personal): void
{
    $s =& $scene['surfaces'];
    if ($s['state'] !== 'ready') return;
    $s['diagnostics']['candidate']++;
    if ($z['status'] !== 'valid') { $s['diagnostics']['missingZ']++; return; }
    $g = $s['asset']['grid'];
    $pixel = intval(floor($y * $g['height'] / $scene['image']['height'])) * $g['width']
        + intval(floor($x * $g['width'] / $scene['image']['width']));
    $matches = array();
    for ($node = $s['_starts'][$pixel] ?? $s['asset']['nodeCount']; $node < $s['asset']['nodeCount']; $node++) {
        if (unpack('V', $s['_pixels'], $node * 4)[1] !== $pixel) break;
        $delta = $z['value'] - unpack('g', $s['_heights'], $node * 4)[1];
        if ($delta >= -8 && $delta <= 80) $matches[] = $node;
    }
    if (count($matches) !== 1) { $s['diagnostics'][count($matches) ? 'ambiguous' : 'offSurface']++; return; }
    $node = $matches[0];
    if ($s['_allowed'][$node] === "\0") { $s['diagnostics']['excluded']++; return; }
    if (!isset($s['rows'][$node])) $s['rows'][$node] = array($node, 0, 0, 0, 0);
    $column = $channel === 'kills' ? 1 : 2;
    $s['rows'][$node][$column]++;
    if ($personal) $s['rows'][$node][$column + 2]++;
    $s['diagnostics']['assigned']++;
}

function heatmap_surface_finalize(array $s, bool $overflow, string $lens = 'overview', int $personalCandidate = 0): array
{
    if ($s['state'] === 'ready' && ($overflow || ($s['diagnostics']['candidate'] > 0
        && $s['diagnostics']['assigned'] / $s['diagnostics']['candidate'] < 0.70))) $s['state'] = 'low_coverage';
    if ($s['state'] === 'ready' && ($lens === 'me' || $lens === 'difference')) {
        $personalAssigned = 0;
        foreach ($s['rows'] as $row) $personalAssigned += $row[3] + $row[4];
        $otherCandidate = $s['diagnostics']['candidate'] - $personalCandidate;
        $otherAssigned = $s['diagnostics']['assigned'] - $personalAssigned;
        if (($personalCandidate > 0 && $personalAssigned / $personalCandidate < 0.70)
            || ($lens === 'difference' && $otherCandidate > 0 && $otherAssigned / $otherCandidate < 0.70)) $s['state'] = 'low_coverage';
    }
    ksort($s['rows'], SORT_NUMERIC);
    return array('version' => 1, 'state' => $s['state'], 'asset' => $s['asset'],
        'fields' => array('node','kills','deaths','meKills','meDeaths'),
        'rows' => $overflow ? array() : array_values($s['rows']), 'allowedData' => $s['allowedData'], 'diagnostics' => $s['diagnostics']);
}
