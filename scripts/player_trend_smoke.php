<?php
define('IN_HLSTATS', true);
define('ROOT_PATH', __DIR__ . '/../web');
require __DIR__ . '/../web/includes/i18n.php';
require __DIR__ . '/../web/includes/player_trend.php';
function check_trend($condition, $message) {
    if (!$condition) throw new RuntimeException($message);
}
$_GET['lang'] = 'ru';
init_i18n();
$history = array(
    array('date' => '2026-01-02', 'skill' => 1039, 'skill_change' => -39),
    array('date' => '2024-01-06', 'skill' => 2473, 'skill_change' => 971),
    array('date' => '2024-01-05', 'skill' => 1502, 'skill_change' => 463),
);
$rows = player_trend_rows($history);
check_trend(array_column($rows, 'date') === array('2024-01-05', '2024-01-06', '2026-01-02'), 'Full calendar dates stay chronological across years');
check_trend($rows[2]['change'] === -39 && $rows[1]['rating'] === 2473, 'Signed changes and raw rating preserved');
check_trend(count($rows) === 3, 'Missing days are not synthesized');
check_trend(count(player_trend_rows(array_fill(0, 40, $history[0]))) === 30, 'Payload bounded to 30 rows');
check_trend(player_trend_rows(array(array('date' => '<script>', 'skill' => 1, 'skill_change' => 2))) === array(), 'Invalid date cannot enter the payload');
$html = player_trend_render($history, 187);
check_trend(strpos($html, '<details class="player-trend__data" open>') !== false, 'Table available without JavaScript');
preg_match('/data-player-trend="([^"]*)"/', $html, $match);
$payload = json_decode(html_entity_decode($match[1], ENT_QUOTES, 'UTF-8'), true);
check_trend($payload['rows'] === $rows && $payload['locale'] === 'ru', 'HTML-escaped payload round-trips exactly');
check_trend(strpos(player_trend_render(array(), 187), t('chart.empty')) !== false, 'Empty history has a clear message');
check_trend(strpos(player_trend_render(null, 187), t('chart.error')) !== false, 'Query failure differs from empty history');
check_trend(strpos(player_trend_render($history, 187, array('bgcolor' => '123456', 'color' => 'abcdef')), 'bgcolor=123456&amp;color=abcdef') !== false, 'Classic image preserves configured colors');
echo "player_trend_smoke: OK\n";
