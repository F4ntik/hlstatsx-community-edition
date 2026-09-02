<?php

declare(strict_types=1);

define('IN_HLSTATS', true);
define('ROOT_PATH', dirname(__DIR__) . '/web');

require ROOT_PATH . '/includes/i18n.php';

function assert_same($expected, $actual, string $message): void
{
    if ($expected !== $actual) {
        fwrite(STDERR, $message . PHP_EOL);
        fwrite(STDERR, 'Expected: ' . var_export($expected, true) . PHP_EOL);
        fwrite(STDERR, 'Actual: ' . var_export($actual, true) . PHP_EOL);
        exit(1);
    }
}

$available = array(
    'en' => array('code' => 'en', 'label' => 'English'),
    'ru' => array('code' => 'ru', 'label' => 'Russian'),
);

assert_same('ru', i18n_normalize_lang(' RU '), 'language normalization lowercases valid codes');
assert_same('', i18n_normalize_lang('../ru'), 'language normalization rejects path-ish input');
assert_same('', i18n_normalize_lang('ru.php'), 'language normalization rejects punctuation');

$enCatalog = i18n_load_catalog('en');
$ruCatalog = i18n_load_catalog('ru');
foreach (array(
    'admin.task.heatmaps.landmarks',
    'admin.task.heatmaps.tolerance',
    'admin.task.heatmaps.world_x',
    'admin.task.heatmaps.world_y',
    'admin.task.heatmaps.pixel_x',
    'admin.task.heatmaps.pixel_y',
    'admin.task.heatmaps.holdout',
    'admin.task.heatmaps.landmarks_required',
    'admin.task.heatmaps.registration_accepted',
	'admin.task.heatmaps.anchor_count',
	'admin.task.heatmaps.holdout_count',
	'admin.task.heatmaps.residual',
	'admin.task.heatmaps.candidate_refused',
	'admin.task.heatmaps.preview_required',
	'admin.task.heatmaps.asset_mismatch',
	'admin.task.heatmaps.registration_coverage',
	'admin.task.heatmaps.apply_candidate',
) as $key) {
    assert_same(true, isset($enCatalog['messages'][$key]) && $enCatalog['messages'][$key] !== '', 'English calibration copy should include ' . $key);
    assert_same(true, isset($ruCatalog['messages'][$key]) && $ruCatalog['messages'][$key] !== '', 'Russian calibration copy should include ' . $key);
}

assert_same(
    'ru',
    i18n_resolve_request_lang(array('lang' => 'ru'), array('lang' => 'en'), array('lang' => 'en'), $available),
    'GET lang should win over cookie and session'
);
assert_same(
    'ru',
    i18n_resolve_request_lang(array('lang' => '../ru'), array('lang' => 'ru'), array('lang' => 'en'), $available),
    'invalid GET lang should fall back to cookie'
);
assert_same(
    'ru',
    i18n_resolve_request_lang(array('lang' => 'ru.php'), array('lang' => 'missing'), array('lang' => 'ru'), $available),
    'invalid GET and cookie langs should fall back to session'
);
assert_same(
    'en',
    i18n_resolve_request_lang(array('lang' => '../ru'), array('lang' => 'missing'), array('lang' => 'also-missing'), $available),
    'invalid request languages should fall back to default'
);

$params = array('mode' => 'players', 'game' => 'cstrike', 'lang' => 'en', 'logout' => '1');
$url = i18n_build_lang_url('ru', $params, 'hlstats.php', array('logout'));
assert_same('hlstats.php?mode=players&game=cstrike&lang=ru', $url, 'lang URL should preserve params and exclude logout');
assert_same('en', $params['lang'], 'lang URL should not mutate source params');
assert_same('1', $params['logout'], 'lang URL should not mutate excluded source params');

$request = array('mode' => 'players', 'game' => 'cstrike', 'lang' => 'en');
$enCache = i18n_historical_cache_target($request, 'en');
$ruCache = i18n_historical_cache_target($request, 'ru');
assert_same(true, $enCache['key'] !== $ruCache['key'], 'historical cache key should include language');
assert_same(true, $enCache['path'] !== $ruCache['path'], 'historical cache path should include language');
assert_same('en', $request['lang'], 'historical cache helper should not mutate source request');

echo "web i18n smoke ok\n";
