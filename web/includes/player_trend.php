<?php
/** Bounded presentation data for the interactive player history chart. */
if (!defined('IN_HLSTATS')) {
    exit;
}

function player_trend_rows(array $history): array
{
    $rows = array();
    foreach (array_slice($history, 0, 30) as $row) {
        $date = (string) ($row['date'] ?? '');
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/D', $date)
            || !is_numeric($row['skill'] ?? null) || !is_numeric($row['skill_change'] ?? null)) {
            continue;
        }
        $rows[] = array('date' => $date, 'rating' => (int) $row['skill'], 'change' => (int) $row['skill_change']);
    }
    usort($rows, static function ($a, $b) { return strcmp($a['date'], $b['date']); });
    return $rows;
}

function player_trend_render(?array $history, int $player, array $colors = array()): string
{
    $rows = player_trend_rows($history ?? array());
    $labels = array();
    foreach (array('rating', 'change', 'date', 'note', 'table', 'empty', 'error', 'help', 'legacy') as $key) {
        $labels[$key] = t('chart.' . $key);
    }
    $escape = static function ($text) { return htmlspecialchars((string) $text, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); };
    $payload = array('version' => 1, 'locale' => current_lang(), 'rows' => $rows, 'labels' => $labels);
    $html = '<section class="player-trend" data-player-trend="'
        . $escape(json_encode($payload, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT))
        . '" aria-label="' . $escape(t('literal.player_trend_graph')) . '">';
    $html .= '<p class="player-trend__note">' . $escape($labels['note']) . '</p>';
    if (!$rows) {
        $html .= '<p role="status">' . $escape($history === null ? $labels['error'] : $labels['empty']) . '</p>';
    } else {
        $html .= '<div class="player-trend__interactive" hidden></div>';
        $html .= '<details class="player-trend__data" open><summary>' . $escape($labels['table']) . '</summary>';
        $html .= '<table><thead><tr><th>' . $escape($labels['date']) . '</th><th>' . $escape($labels['rating'])
            . '</th><th>' . $escape($labels['change']) . '</th></tr></thead><tbody>';
        foreach ($rows as $row) {
            $html .= '<tr><td>' . $escape($row['date']) . '</td><td>' . $row['rating'] . '</td><td>'
                . ($row['change'] > 0 ? '+' : '') . $row['change'] . '</td></tr>';
        }
        $html .= '</tbody></table></details>';
    }
    $legacy = array('player' => $player);
    foreach (array('bgcolor', 'color') as $key) {
        if (isset($colors[$key])) $legacy[$key] = (string) $colors[$key];
    }
    $html .= '<a class="player-trend__legacy" href="trend_graph.php?' . $escape(http_build_query($legacy)) . '">'
        . $escape($labels['legacy']) . '</a></section>';
    return $html;
}
