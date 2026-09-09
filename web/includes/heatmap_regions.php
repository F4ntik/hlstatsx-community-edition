<?php

// Optional world-space floor outlines. No event coordinates are exported here.
function heatmap_region_cross(array $a, array $b, array $p)
{
    return ($b[0] - $a[0]) * ($p[1] - $a[1]) - ($b[1] - $a[1]) * ($p[0] - $a[0]);
}

function heatmap_region_on_edge(array $a, array $b, array $p): bool
{
    return heatmap_region_cross($a, $b, $p) == 0
        && $p[0] >= min($a[0], $b[0]) && $p[0] <= max($a[0], $b[0])
        && $p[1] >= min($a[1], $b[1]) && $p[1] <= max($a[1], $b[1]);
}

function heatmap_region_edges_intersect(array $a, array $b, array $c, array $d): bool
{
    $abC = heatmap_region_cross($a, $b, $c); $abD = heatmap_region_cross($a, $b, $d);
    $cdA = heatmap_region_cross($c, $d, $a); $cdB = heatmap_region_cross($c, $d, $b);
    return (($abC > 0 && $abD < 0 || $abC < 0 && $abD > 0)
        && ($cdA > 0 && $cdB < 0 || $cdA < 0 && $cdB > 0))
        || heatmap_region_on_edge($a, $b, $c) || heatmap_region_on_edge($a, $b, $d)
        || heatmap_region_on_edge($c, $d, $a) || heatmap_region_on_edge($c, $d, $b);
}

function heatmap_region_contains(array $polygon, $x, $y): bool
{
    $inside = false; $p = array($x, $y); $count = count($polygon);
    for ($i = 0, $j = $count - 1; $i < $count; $j = $i++) {
        $a = $polygon[$j]; $b = $polygon[$i];
        if (heatmap_region_on_edge($a, $b, $p)) return true;
        if (($a[1] > $y) !== ($b[1] > $y)
            && $x < ($b[0] - $a[0]) * ($y - $a[1]) / ($b[1] - $a[1]) + $a[0]) $inside = !$inside;
    }
    return $inside;
}

function heatmap_regions_contains(array $regions, $x, $y): bool
{
    if (!$regions) return true;
    if ($x === null || $y === null) return false;
    foreach ($regions as $polygon) if (heatmap_region_contains($polygon, $x, $y)) return true;
    return false;
}

function heatmap_validate_regions($regions): array
{
    if (!is_array($regions) || !array_is_list($regions) || count($regions) > 8) throw new InvalidArgumentException('invalid_floor_config');
    foreach ($regions as $polygon) {
        if (!is_array($polygon) || !array_is_list($polygon) || count($polygon) < 3 || count($polygon) > 32) throw new InvalidArgumentException('invalid_floor_config');
        $seen = array(); $area = 0; $n = count($polygon);
        foreach ($polygon as $p) {
            if (!is_array($p) || !array_is_list($p) || count($p) !== 2) throw new InvalidArgumentException('invalid_floor_config');
            foreach ($p as $v) if (!is_int($v) || $v < -8388608 || $v > 8388607) throw new InvalidArgumentException('invalid_floor_config');
            $key = $p[0] . ':' . $p[1];
            if (isset($seen[$key])) throw new InvalidArgumentException('invalid_floor_config');
            $seen[$key] = true;
        }
        for ($i = 0; $i < $n; $i++) {
            $a = $polygon[$i]; $b = $polygon[($i + 1) % $n];
            $area += $a[0] * $b[1] - $b[0] * $a[1];
            for ($j = $i + 1; $j < $n; $j++) {
                if ($j === $i + 1 || $i === 0 && $j === $n - 1) continue;
                if (heatmap_region_edges_intersect($a, $b, $polygon[$j], $polygon[($j + 1) % $n])) throw new InvalidArgumentException('invalid_floor_config');
            }
        }
        if (abs($area) < 2) throw new InvalidArgumentException('invalid_floor_config');
    }
    return $regions;
}

function heatmap_regions_overlap(array $left, array $right): bool
{
    if (!$left || !$right) return true;
    foreach ($left as $a) foreach ($right as $b) {
        if (heatmap_region_contains($a, $b[0][0], $b[0][1]) || heatmap_region_contains($b, $a[0][0], $a[0][1])) return true;
        for ($i = 0; $i < count($a); $i++) for ($j = 0; $j < count($b); $j++) {
            if (heatmap_region_edges_intersect($a[$i], $a[($i + 1) % count($a)], $b[$j], $b[($j + 1) % count($b)])) return true;
        }
    }
    return false;
}

function heatmap_regions_sql(array $regions, string $x, string $y): string
{
    // Only validated integer vertices and internally chosen column names enter SQL.
    heatmap_validate_regions($regions);
    if (!preg_match('/^hef\.pos_(victim_)?[xy]$/D', $x) || !preg_match('/^hef\.pos_(victim_)?[xy]$/D', $y)) throw new InvalidArgumentException('invalid_floor_config');
    $parts = array();
    foreach ($regions as $polygon) {
        $edges = array(); $crossings = array(); $n = count($polygon);
        for ($i = 0; $i < $n; $i++) {
            list($ax, $ay) = $polygon[$i]; list($bx, $by) = $polygon[($i + 1) % $n];
            $dx = $bx - $ax; $dy = $by - $ay;
            $edges[] = "(($dx)*($y-($ay))=($dy)*($x-($ax)) AND $x BETWEEN " . min($ax, $bx) . ' AND ' . max($ax, $bx) . " AND $y BETWEEN " . min($ay, $by) . ' AND ' . max($ay, $by) . ')';
            if ($dy !== 0) $crossings[] = "((($ay)>$y)<>(($by)>$y) AND $x < ($dx)*($y-($ay))/($dy)+($ax))";
        }
        $parts[] = '(' . implode(' OR ', $edges) . ' OR MOD((' . implode('+', $crossings) . '),2)=1)';
    }
    return $parts ? '(' . implode(' OR ', $parts) . ')' : '1=1';
}
