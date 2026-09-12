<?php

if (!defined('IN_HLSTATS')) {
    http_response_code(403);
    exit;
}

require_once __DIR__ . '/heatmap_regions.php';
require_once __DIR__ . '/heatmap_surfaces.php';

const HEATMAP_V2_SCHEMA = 2;
const HEATMAP_MAX_WINDOW_SECONDS = 315360000;
const HEATMAP_MAX_FLOORS = 8;
const HEATMAP_MEDIUMINT_MIN = -8388608;
const HEATMAP_MEDIUMINT_MAX = 8388607;
const HEATMAP_MYSQL_UNSIGNED_INT_MAX = 4294967295;
const HEATMAP_FLOOR_PARSER_SCHEMA = 3;
const HEATMAP_MAX_SOURCE_ROWS = 250000;
const HEATMAP_INSPECT_MAX_ROWS = 101;
const HEATMAP_GRID_MAX_AXIS = 128;
const HEATMAP_MIN_FLOOR_Z_COVERAGE = 0.70;
const HEATMAP_MIN_PROJECTION_COVERAGE = 0.70;
const HEATMAP_SCENE_CACHE_SCHEMA = 5;
const HEATMAP_SCENE_BUCKET_VERSION = 1;
const HEATMAP_PAYLOAD_CACHE_MAX_AGE = 172800;
const HEATMAP_PAYLOAD_CACHE_PRUNE_LIMIT = 32;
const HEATMAP_EXACT_PREVIEW_LIMIT = 20000;

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

function heatmap_explorer_exact_flag(array $query, string $key): bool
{
    return array_key_exists($key, $query) && is_string($query[$key]) && $query[$key] === '1';
}

function heatmap_should_render_explorer(array $options, array $query): bool
{
    // `heatmap_legacy=1` wins whenever both flags are present.
    if (heatmap_explorer_exact_flag($query, 'heatmap_legacy')) {
        return false;
    }

    $mode = heatmap_explorer_mode($options);
    if ($mode === 1) {
        // Mode 1 is the explicit `heatmap_explorer=1` opt-in only.
        return heatmap_explorer_exact_flag($query, 'heatmap_explorer');
    }

    // Mode 0 stays legacy; mode 2 makes Explorer the default.
    return $mode === 2;
}

function heatmap_explorer_html($value): string
{
    return htmlspecialchars(strval($value), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function heatmap_explorer_label(string $key): string
{
    return t('heatmapExplorer.' . $key);
}

function heatmap_explorer_legacy_page_url(array $context): string
{
    $legacyPage = strval($context['legacyPage'] ?? '');
    if ($legacyPage === 'mapinfo') {
        $game = strval($context['game'] ?? '');
        $map = strval($context['map'] ?? '');
        if ($game === '' || $map === '') {
            return '';
        }
        return 'hlstats.php?mode=mapinfo&game=' . rawurlencode($game)
            . '&map=' . rawurlencode($map) . '&heatmap_legacy=1';
    }
    if ($legacyPage === 'playerinfo') {
        $player = strval($context['player'] ?? '');
        if (preg_match('/^[1-9][0-9]{0,9}$/D', $player) !== 1) {
            return '';
        }
        return 'hlstats.php?mode=playerinfo&player=' . rawurlencode($player)
            . '&heatmap_legacy=1';
    }
    return '';
}

function heatmap_explorer_v1_url(array $context): string
{
    $legacyPageUrl = heatmap_explorer_legacy_page_url($context);
    if ($legacyPageUrl !== '') {
        return $legacyPageUrl;
    }
    $endpoint = strval($context['endpoint'] ?? 'heatmap_points.php');
    $parts = parse_url($endpoint);
    $base = isset($parts['path']) && is_string($parts['path']) && $parts['path'] !== ''
        ? $parts['path']
        : 'heatmap_points.php';
    $query = array(
        'game' => strval($context['game'] ?? ''),
        'map' => strval($context['map'] ?? ''),
    );

    if (isset($parts['query']) && is_string($parts['query'])) {
        $endpointQuery = array();
        parse_str($parts['query'], $endpointQuery);
        if (is_array($endpointQuery)) {
            foreach (array('game', 'map', 'player', 'event') as $key) {
                if (isset($endpointQuery[$key]) && is_scalar($endpointQuery[$key])) {
                    $query[$key] = strval($endpointQuery[$key]);
                }
            }
        }
    }

    if (!isset($query['player']) && intval($context['player'] ?? 0) > 0) {
        $query['player'] = strval(intval($context['player']));
    }
    if (isset($query['player']) && preg_match('/^[1-9][0-9]{0,9}$/D', $query['player']) !== 1) {
        unset($query['player']);
    }
    if (isset($query['event']) && !in_array($query['event'], array('kills', 'deaths', 'both'), true)) {
        unset($query['event']);
    }

    $pairs = array();
    foreach (array('game', 'map', 'player', 'event') as $key) {
        $value = strval($query[$key] ?? '');
        if ($value === '') {
            continue;
        }
        $pairs[] = rawurlencode($key) . '=' . rawurlencode($value);
    }

    return $base . (count($pairs) > 0 ? '?' . implode('&', $pairs) : '');
}

function heatmap_render_explorer_workspace(array $context): string
{
    $context = array_merge(array(
        'game' => '',
        'map' => '',
        'player' => 0,
        'image' => '',
        'imageAlt' => '',
        'endpoint' => 'heatmap_points.php',
        'legacyPage' => '',
        'jpeg' => '',
        'lang' => 'en',
        'lenses' => array('overview'),
        'maps' => array(),
    ), $context);

    $game = heatmap_explorer_html($context['game']);
    $map = heatmap_explorer_html($context['map']);
    $player = max(0, intval($context['player']));
    $floorSheetId = 'heatmap-floor-sheet-' . $player;
    $inspectorSheetId = 'heatmap-inspector-sheet-' . $player;
    $image = heatmap_explorer_html($context['image']);
    $imageAlt = heatmap_explorer_html($context['imageAlt'] === '' ? $context['map'] : $context['imageAlt']);
    $endpoint = heatmap_explorer_html($context['endpoint']);
    $v1Url = heatmap_explorer_html(heatmap_explorer_v1_url($context));
    $jpeg = heatmap_explorer_html($context['jpeg']);
    $lang = $context['lang'] === 'ru' ? 'ru' : 'en';
    $lenses = is_array($context['lenses']) ? $context['lenses'] : array('overview');
    $hasMe = in_array('me', $lenses, true);
    $hasDifference = in_array('difference', $lenses, true);

    $mapOptions = '';
    $maps = is_array($context['maps']) ? $context['maps'] : array();
    if (count($maps) === 0) {
        $maps[] = array('map' => $context['map'], 'label' => $context['map']);
    }
    foreach ($maps as $mapOption) {
        if (!is_array($mapOption) || !isset($mapOption['map'])) {
            continue;
        }
        $mapValue = heatmap_explorer_html($mapOption['map']);
        $mapLabel = heatmap_explorer_html($mapOption['label'] ?? $mapOption['map']);
        $selected = strval($mapOption['map']) === strval($context['map']) ? ' selected="selected"' : '';
        $mapOptions .= '<option value="' . $mapValue . '"' . $selected . '>' . $mapLabel . '</option>';
    }

    $overviewPressed = 'true';
    $meControl = $hasMe
        ? '<button type="button" class="heatmap-explorer__control" data-heatmap-lens="me" aria-pressed="false">'
            . heatmap_explorer_html(heatmap_explorer_label('me')) . '</button>'
        : '';
    $differenceControl = $hasDifference
        ? '<button type="button" class="heatmap-explorer__control" data-heatmap-lens="difference" aria-pressed="false">'
            . heatmap_explorer_html(heatmap_explorer_label('difference')) . '</button>'
        : '';

    $html = '<section class="heatmap-explorer" data-heatmap-explorer="1"'
        . ' data-heatmap-map-style="color"'
        . ' data-heatmap-game="' . $game . '" data-heatmap-map="' . $map . '"'
        . ' data-heatmap-player="' . $player . '" data-heatmap-endpoint="' . $endpoint . '"'
        . ' data-heatmap-v1-url="' . $v1Url . '"'
        . ' data-heatmap-lang="' . $lang . '"'
        . ' data-heatmap-initial-lens="overview" data-heatmap-allow-me="' . ($hasMe ? '1' : '0') . '"'
        . ' data-heatmap-allow-difference="' . ($hasDifference ? '1' : '0') . '"'
        . ' data-heatmap-message-insufficient-sample="' . heatmap_explorer_html(heatmap_explorer_label('insufficient_sample')) . '"'
        . ' data-heatmap-message-missing-coordinates="' . heatmap_explorer_html(heatmap_explorer_label('missing_coordinates')) . '"'
        . ' data-heatmap-message-floors-unavailable="' . heatmap_explorer_html(heatmap_explorer_label('floors_unavailable')) . '"'
        . ' data-heatmap-message-weak-projection="' . heatmap_explorer_html(heatmap_explorer_label('weak_projection')) . '"'
        . ' data-heatmap-message-too-many-events="' . heatmap_explorer_html(heatmap_explorer_label('too_many_events')) . '"'
        . ' data-heatmap-message-range-custom="' . heatmap_explorer_html(heatmap_explorer_label('rangeCustom')) . '"'
        . ' data-heatmap-message-open-v1="' . heatmap_explorer_html(heatmap_explorer_label('openV1')) . '"'
        . ' data-heatmap-message-unavailable="' . heatmap_explorer_html(heatmap_explorer_label('unavailable')) . '">';
    $html .= '<header class="heatmap-explorer__header">';
    $html .= '<div><h2 data-heatmap-map-title="1">' . $map . '</h2>';
    $html .= '<p data-heatmap-period="1">' . heatmap_explorer_html(heatmap_explorer_label('loading')) . '</p></div>';
    $html .= '<label class="heatmap-explorer__map-label"' . (count($maps) <= 1 ? ' hidden="hidden"' : '') . '>' . heatmap_explorer_html(heatmap_explorer_label('map'));
    $html .= '<select data-heatmap-map-select="1">' . $mapOptions . '</select></label>';
    $html .= '<label class="heatmap-explorer__map-label">' . heatmap_explorer_html(heatmap_explorer_label('period'));
    $html .= '<select data-heatmap-range="1"><option value="7d">' . heatmap_explorer_html(heatmap_explorer_label('range7d')) . '</option>';
    $html .= '<option value="30d" selected="selected">' . heatmap_explorer_html(heatmap_explorer_label('range30d')) . '</option>';
    $html .= '<option value="90d">' . heatmap_explorer_html(heatmap_explorer_label('range90d')) . '</option>';
    $html .= '<option value="365d">' . heatmap_explorer_html(heatmap_explorer_label('range365d')) . '</option>';
    $html .= '<option value="custom">' . heatmap_explorer_html(heatmap_explorer_label('rangeCustom')) . '</option></select></label>';
    $html .= '<div class="heatmap-explorer__period-controls">';
    $html .= '<label class="heatmap-explorer__map-label">' . heatmap_explorer_html(heatmap_explorer_label('fromUtc'));
    $html .= '<input type="datetime-local" step="1" class="heatmap-explorer__input" data-heatmap-from="1" value="" /></label>';
    $html .= '<label class="heatmap-explorer__map-label">' . heatmap_explorer_html(heatmap_explorer_label('toUtc'));
    $html .= '<input type="datetime-local" step="1" class="heatmap-explorer__input" data-heatmap-to="1" value="" /></label>';
    $html .= '<button type="button" class="heatmap-explorer__control" data-heatmap-apply="1">'
        . heatmap_explorer_html(heatmap_explorer_label('apply')) . '</button></div>';
    $html .= '<button type="button" class="heatmap-explorer__sheet-toggle" data-heatmap-sheet-toggle="floors"'
        . ' aria-controls="' . $floorSheetId . '" aria-expanded="false">' . heatmap_explorer_html(heatmap_explorer_label('floor')) . '</button>';
    $html .= '<button type="button" class="heatmap-explorer__sheet-toggle" data-heatmap-sheet-toggle="inspector"'
        . ' aria-controls="' . $inspectorSheetId . '" aria-expanded="false">' . heatmap_explorer_html(heatmap_explorer_label('inspector')) . '</button>';
    $html .= '<fieldset class="heatmap-explorer__group"' . (!$hasMe && !$hasDifference ? ' hidden="hidden"' : '') . '><legend>' . heatmap_explorer_html(heatmap_explorer_label('lens')) . '</legend>';
    $html .= '<button type="button" class="heatmap-explorer__control is-selected" data-heatmap-lens="overview" aria-pressed="' . $overviewPressed . '">'
        . heatmap_explorer_html(heatmap_explorer_label('overview')) . '</button>' . $meControl . $differenceControl . '</fieldset>';
    $html .= '<fieldset class="heatmap-explorer__group"><legend>' . heatmap_explorer_html(heatmap_explorer_label('channel')) . '</legend>';
    $html .= '<button type="button" class="heatmap-explorer__control" data-heatmap-event="kills" aria-pressed="false">'
        . heatmap_explorer_html(heatmap_explorer_label('kills')) . '</button>';
    $html .= '<button type="button" class="heatmap-explorer__control" data-heatmap-event="deaths" aria-pressed="false">'
        . heatmap_explorer_html(heatmap_explorer_label('deaths')) . '</button>';
    $html .= '<button type="button" class="heatmap-explorer__control is-selected" data-heatmap-event="both" aria-pressed="true">'
        . heatmap_explorer_html(heatmap_explorer_label('both')) . '</button></fieldset>';
    $html .= '<fieldset class="heatmap-explorer__group" data-heatmap-display-controls="1"><legend>'
        . heatmap_explorer_html(heatmap_explorer_label('display')) . '</legend>';
    foreach (array('smooth', 'cells', 'points') as $mode) {
        $html .= '<button type="button" class="heatmap-explorer__control' . ($mode === 'smooth' ? ' is-selected' : '')
            . '" data-heatmap-display-option="' . $mode . '" aria-pressed="' . ($mode === 'smooth' ? 'true' : 'false') . '">'
            . heatmap_explorer_html(heatmap_explorer_label($mode)) . '</button>';
    }
    $html .= '</fieldset><fieldset class="heatmap-explorer__group"><legend>' . heatmap_explorer_html(heatmap_explorer_label('appearance')) . '</legend>';
    foreach (array('clear','soft') as $appearance) {
        $html .= '<button type="button" class="heatmap-explorer__control' . ($appearance === 'clear' ? ' is-selected' : '')
            . '" data-heatmap-appearance-option="' . $appearance . '" aria-pressed="' . ($appearance === 'clear' ? 'true' : 'false') . '">'
            . heatmap_explorer_html(heatmap_explorer_label($appearance)) . '</button>';
    }
    $html .= '</fieldset><span class="heatmap-explorer__legend" data-heatmap-legend="1"></span>';
    $html .= '<fieldset class="heatmap-explorer__group" data-heatmap-map-style-controls="1"><legend>'
        . heatmap_explorer_html(heatmap_explorer_label('mapStyle')) . '</legend>';
    $html .= '<button type="button" class="heatmap-explorer__control is-selected" data-heatmap-map-style-option="color" aria-pressed="true">'
        . heatmap_explorer_html(heatmap_explorer_label('color')) . '</button>';
    $html .= '<button type="button" class="heatmap-explorer__control" data-heatmap-map-style-option="mono" aria-pressed="false">'
        . heatmap_explorer_html(heatmap_explorer_label('mono')) . '</button>';
    $html .= '<button type="button" class="heatmap-explorer__control" data-heatmap-map-style-option="inverse" aria-pressed="false">'
        . heatmap_explorer_html(heatmap_explorer_label('inverse')) . '</button></fieldset></header>';
    $html .= '<aside id="' . $floorSheetId . '" class="heatmap-explorer__floors" data-heatmap-floor-sheet="1" aria-label="' . heatmap_explorer_html(heatmap_explorer_label('floor')) . '">';
    $html .= '<span class="heatmap-explorer__label">' . heatmap_explorer_html(heatmap_explorer_label('floor')) . '</span>';
    $html .= '<div data-heatmap-floor-options="1"><label><input type="radio" name="heatmap-floor-' . $player . '" value="all" data-heatmap-floor="all" checked="checked" />'
        . heatmap_explorer_html(heatmap_explorer_label('allFloors')) . '</label></div></aside>';
    $html .= '<main class="heatmap-explorer__stage-column">';
    $html .= '<div class="heatmap-explorer__scale"><span class="heatmap-explorer__scale-bar" aria-hidden="true"></span>'
        . '<span data-heatmap-scale-values="1"></span><button type="button" data-heatmap-scale-lock="1" aria-pressed="false">'
        . heatmap_explorer_html(heatmap_explorer_label('scaleLock')) . '</button></div>';
    $html .= '<div class="heatmap-explorer__interactive" data-heatmap-interactive="1">';
    $html .= '<div class="heatmap-explorer__stage" data-heatmap-stage="1" tabindex="0" aria-describedby="heatmap-summary-' . $player . '">';
    $html .= '<div data-heatmap-camera="1"><img data-heatmap-image="1" src="' . $image . '" alt="' . $imageAlt . '" />';
    $html .= '<canvas data-heatmap-canvas="1" aria-label="' . heatmap_explorer_html(heatmap_explorer_label('mapControls')) . '"></canvas></div></div></div>';
    $html .= '<div class="heatmap-explorer__controls" aria-label="' . heatmap_explorer_html(heatmap_explorer_label('mapControls')) . '">';
    $html .= '<button type="button" data-heatmap-zoom="in">+</button><button type="button" data-heatmap-zoom="out">−</button>';
    $html .= '<button type="button" data-heatmap-reset="1">' . heatmap_explorer_html(heatmap_explorer_label('reset')) . '</button>';
    $html .= '<button type="button" data-heatmap-pan="1" aria-pressed="false">' . heatmap_explorer_html(heatmap_explorer_label('pan')) . '</button>';
    $html .= '<a data-heatmap-share="1" href="">' . heatmap_explorer_html(heatmap_explorer_label('share')) . '</a></div>';
    $html .= '<div class="heatmap-explorer__static" data-heatmap-static="1"><a href="' . $jpeg . '" rel="boxed"><img src="' . $jpeg . '" alt="' . $imageAlt . '" /></a></div>';
    $html .= '<noscript><p>' . heatmap_explorer_html(heatmap_explorer_label('noscript')) . ' <a href="' . $jpeg . '">'
        . heatmap_explorer_html(heatmap_explorer_label('staticJpeg')) . '</a></p></noscript>';
    $html .= '<p class="heatmap-explorer__status" data-heatmap-status="1" role="status" aria-live="polite">'
        . heatmap_explorer_html(heatmap_explorer_label('loading')) . '</p>';
    $html .= '<p class="heatmap-explorer__alert" data-heatmap-alert="1" role="alert" hidden="hidden"></p>';
    $html .= '<p id="heatmap-summary-' . $player . '" class="heatmap-explorer__summary" data-heatmap-summary="1" hidden="hidden">'
        . heatmap_explorer_html(heatmap_explorer_label('loading')) . '</p></main>';
    $html .= '<aside id="' . $inspectorSheetId . '" class="heatmap-explorer__inspector" data-heatmap-inspector="1"><h3>'
        . heatmap_explorer_html(heatmap_explorer_label('inspector')) . '</h3><div data-heatmap-inspect-output="1">'
        . heatmap_explorer_html(heatmap_explorer_label('noCell')) . '</div></aside>';
    $html .= '<details class="heatmap-explorer__footer"><summary>' . heatmap_explorer_html(heatmap_explorer_label('details')) . '</summary>';
    $html .= '<p>' . heatmap_explorer_html(heatmap_explorer_label('populationNote')) . '</p>';
    $html .= '<p>' . heatmap_explorer_html(heatmap_explorer_label('alignmentUnverified')) . '</p>';
    $html .= '<span data-heatmap-window="1"></span><span data-heatmap-sample="1"></span>';
    $html .= '<span data-heatmap-coverage="1"></span><span data-heatmap-freshness="1"></span>';
    $html .= '<a data-heatmap-jpeg-link="1" href="' . $jpeg . '">' . heatmap_explorer_html(heatmap_explorer_label('staticJpeg')) . '</a></details>';
    $html .= '</section>';

    return $html;
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
        'geometry' => isset($query['geometry']) ? array('kind' => $query['geometry'], 'version' => 1) : null,
        'cacheSchema' => HEATMAP_SCENE_CACHE_SCHEMA,
        'surfaceIdentity' => heatmap_surface_identity($config, strval($query['map'] ?? '')),
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

function heatmap_admin_session_csrf_token(): string
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        throw new RuntimeException('admin_session_unavailable');
    }

    $token = $_SESSION['heatmap_admin_csrf'] ?? null;
    if (is_string($token) && preg_match('/^[a-f0-9]{64}$/D', $token) === 1) {
        return $token;
    }

    $token = bin2hex(random_bytes(32));
    $_SESSION['heatmap_admin_csrf'] = $token;
    return $token;
}

function heatmap_admin_preview_identity(array $config, array $image, array $query): string
{
    $queryIdentity = array(
        'game' => strval($query['game'] ?? ''),
        'map' => strval($query['map'] ?? ''),
        'from' => intval($query['from'] ?? 0),
        'to' => intval($query['to'] ?? 0),
        'event' => strval($query['event'] ?? ''),
        'floor' => strval($query['floor'] ?? ''),
    );
    $canonical = heatmap_admin_config_hash($config, $image) . "\n" . json_encode($queryIdentity, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    return hash('sha256', $canonical);
}

function heatmap_admin_issue_preview_token(array $config, array $image, array $query, int $now = null): string
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        throw new RuntimeException('admin_session_unavailable');
    }
    $now = $now ?? time();
    $token = bin2hex(random_bytes(32));
    $_SESSION['heatmap_admin_preview'] = array(
        'hash' => hash('sha256', $token),
        'identity' => heatmap_admin_preview_identity($config, $image, $query),
        'expires' => $now + 600,
    );
    return $token;
}

function heatmap_admin_preview_token_is_valid(string $token, array $config, array $image, array $query, int $now = null): bool
{
    $record = $_SESSION['heatmap_admin_preview'] ?? null;
    $now = $now ?? time();
    if (!is_array($record) || $now > intval($record['expires'] ?? 0)) {
        unset($_SESSION['heatmap_admin_preview']);
        return false;
    }
    return preg_match('/^[a-f0-9]{64}$/D', $token) === 1
        && is_string($record['hash'] ?? null)
        && is_string($record['identity'] ?? null)
        && hash_equals($record['hash'], hash('sha256', $token))
        && hash_equals($record['identity'], heatmap_admin_preview_identity($config, $image, $query));
}

function heatmap_admin_preview_token_consume(string $token, array $config, array $image, array $query, int $now = null): bool
{
    $valid = heatmap_admin_preview_token_is_valid($token, $config, $image, $query, $now);
    unset($_SESSION['heatmap_admin_preview']);
    return $valid;
}

function heatmap_admin_landmark_evidence(array $landmarks, array $config, $tolerance): array
{
    $tolerance = is_numeric($tolerance) && is_finite(floatval($tolerance))
        ? max(1.0, min(10.0, floatval($tolerance)))
        : 10.0;
    if (count($landmarks) > 64) {
        return array('ok' => false, 'reason' => 'invalid_landmarks', 'residuals' => array());
    }
    $calibration = array();
    $holdouts = array();
    $residuals = array();
    $labels = array();
    $worldPoints = array();
    $pixelPoints = array();
    $anchorPoints = array();
    foreach ($landmarks as $index => $landmark) {
        if (!is_array($landmark)) {
            return array('ok' => false, 'reason' => 'invalid_landmarks', 'residuals' => array());
        }
        foreach (array('worldX', 'worldY', 'pixelX', 'pixelY') as $field) {
            if (!array_key_exists($field, $landmark) || !is_numeric($landmark[$field]) || !is_finite(floatval($landmark[$field]))) {
                return array('ok' => false, 'reason' => 'invalid_landmarks', 'residuals' => array());
            }
        }
        $label = is_string($landmark['label'] ?? null) ? trim($landmark['label']) : '';
        $worldKey = intval($landmark['worldX']) . ':' . intval($landmark['worldY']);
        $pixelKey = floatval($landmark['pixelX']) . ':' . floatval($landmark['pixelY']);
        if ($label === '' || strlen($label) > 120 || isset($labels[strtolower($label)]) || isset($worldPoints[$worldKey]) || isset($pixelPoints[$pixelKey])) {
            return array('ok' => false, 'reason' => 'invalid_landmarks', 'residuals' => array());
        }
        $labels[strtolower($label)] = true; $worldPoints[$worldKey] = true; $pixelPoints[$pixelKey] = true;
        $projected = heatmap_transform_point(array(
            'pos_x' => intval($landmark['worldX']),
            'pos_y' => intval($landmark['worldY']),
        ), $config);
        $residual = hypot(floatval($projected['x']) - floatval($landmark['pixelX']), floatval($projected['y']) - floatval($landmark['pixelY']));
        $entry = array('index' => intval($index), 'residual' => $residual, 'holdout' => !empty($landmark['holdout']));
        $residuals[] = $entry;
        if ($entry['holdout']) {
            $holdouts[] = $entry;
        } else {
            $calibration[] = $entry;
            if ($residual <= $tolerance) $anchorPoints[] = $landmark;
        }
    }
    if (count($calibration) < 4 || count($holdouts) < 2) {
        return array('ok' => false, 'reason' => 'landmarks_required', 'residuals' => $residuals);
    }
    // Independent server-side rank check: repeated or almost collinear anchors cannot certify a map.
    foreach (array(array('worldX', 'worldY'), array('pixelX', 'pixelY')) as $axes) {
        $maxArea = 0.0; $span = 0.0;
        foreach ($anchorPoints as $a) foreach ($anchorPoints as $b) {
            $dx = floatval($b[$axes[0]]) - floatval($a[$axes[0]]);
            $dy = floatval($b[$axes[1]]) - floatval($a[$axes[1]]);
            $span = max($span, $dx * $dx + $dy * $dy);
            foreach ($anchorPoints as $c) $maxArea = max($maxArea, abs($dx * (floatval($c[$axes[1]]) - floatval($a[$axes[1]])) - $dy * (floatval($c[$axes[0]]) - floatval($a[$axes[0]]))));
        }
        if ($span <= 0 || $maxArea / $span < 0.01 || ($axes[0] === 'pixelX' && $span <= 4 * $tolerance * $tolerance)) return array('ok' => false, 'reason' => 'invalid_landmarks', 'residuals' => $residuals);
    }
    $calibrationValues = array_map(function (array $entry): float { return $entry['residual']; }, $calibration);
    sort($calibrationValues, SORT_NUMERIC);
    $middle = intdiv(count($calibrationValues), 2);
    $median = count($calibrationValues) % 2 === 1
        ? $calibrationValues[$middle]
        : ($calibrationValues[$middle - 1] + $calibrationValues[$middle]) / 2.0;
    $outlierThreshold = max($tolerance, $median * 3.0);
    $calibrationAccepted = count(array_filter($calibration, function (array $entry) use ($tolerance): bool {
        return $entry['residual'] <= $tolerance;
    }));
    $allHoldoutsAccepted = count(array_filter($holdouts, function (array $entry) use ($tolerance): bool {
        return $entry['residual'] <= $tolerance;
    })) === count($holdouts);
    $maximumResidual = 0.0;
    foreach ($residuals as $entry) {
        $maximumResidual = max($maximumResidual, $entry['residual']);
    }
    return array(
        'ok' => $calibrationAccepted >= 4 && $allHoldoutsAccepted,
        'reason' => $calibrationAccepted >= 4 && $allHoldoutsAccepted ? '' : 'candidate_refused',
        'residuals' => $residuals,
        'inliers' => array_values(array_map(function (array $entry): int { return $entry['index']; }, array_filter($calibration, function (array $entry) use ($outlierThreshold): bool {
            return $entry['residual'] <= $outlierThreshold;
        }))),
        'holdouts' => array_values(array_map(function (array $entry): int { return $entry['index']; }, $holdouts)),
        'maximumResidual' => $maximumResidual,
        'tolerance' => $tolerance,
    );
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
        'geometry',
    ));
    foreach ($input as $key => $value) {
        if (!is_string($key) || !isset($allowed[$key]) || !is_string($value)) {
            throw new InvalidArgumentException('invalid_query');
        }
    }
    if (isset($input['geometry']) && ($input['geometry'] !== 'points' || isset($input['inspect']))) {
        throw new InvalidArgumentException('invalid_query');
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
    if (isset($input['geometry'])) {
        $query['geometry'] = 'points';
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
        if (array_diff($expectedKeys, $keys) || array_diff($keys, array_merge($expectedKeys, array('regions', 'blocked', 'image')))) {
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
        if (array_key_exists('regions', $floor)) $floors[count($floors) - 1]['regions'] = heatmap_validate_regions($floor['regions']);
        if (array_key_exists('blocked', $floor)) $floors[count($floors) - 1]['blocked'] = heatmap_validate_regions($floor['blocked']);
        if (array_key_exists('image', $floor)) {
            if (!is_bool($floor['image'])) throw new InvalidArgumentException('invalid_floor_config');
            $floors[count($floors) - 1]['image'] = $floor['image'];
        }
    }

    usort($floors, function ($left, $right) {
        $zCompare = $left['z_min'] <=> $right['z_min'];
        return $zCompare !== 0 ? $zCompare : strcmp($left['id'], $right['id']);
    });
    foreach ($floors as $i => $floor) foreach (array_slice($floors, $i + 1) as $other) {
        if ($floor['z_min'] < $other['z_max'] && $other['z_min'] < $floor['z_max']
            && heatmap_regions_overlap($floor['regions'] ?? array(), $other['regions'] ?? array())) throw new InvalidArgumentException('invalid_floor_config');
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

function heatmap_assign_floor($z, array $floors, $x = null, $y = null): ?string
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
        if ($z >= $floor['z_min'] && $z < $floor['z_max'] && heatmap_regions_contains($floor['regions'] ?? array(), $x, $y)
            && (empty($floor['blocked']) || !heatmap_regions_contains($floor['blocked'], $x, $y))) {
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
    $options = is_array($state['options'] ?? null) ? $state['options'] : array();
    $exactLimit = heatmap_try_canonical_integer($options['exactLimit'] ?? HEATMAP_EXACT_PREVIEW_LIMIT);
    $exactLimit = $exactLimit === null
        ? HEATMAP_EXACT_PREVIEW_LIMIT
        : max(1, min(HEATMAP_EXACT_PREVIEW_LIMIT, $exactLimit));
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
        'zHistogram' => array(),
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
    $state['_scene']['surfaces'] = heatmap_surface_load($config, $state['image'], $context['map'], $floor);
    if (($options['exact'] ?? false) === true) {
        $state['_scene']['exact'] = array(
            'limit' => $exactLimit,
            'overflow' => false,
            'points' => array(),
        );
    }
    if (($options['geometry'] ?? '') === 'points') {
        $state['_scene']['geometry'] = array('points' => array(), 'overflow' => false);
    }
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

function heatmap_scene_add_exact_point(array &$scene, array $row, array $projected, string $channel, string $participant): void
{
    if (!isset($scene['exact'])) {
        return;
    }
    if ($scene['exact']['overflow']) {
        return;
    }
    if (count($scene['exact']['points']) >= $scene['exact']['limit']) {
        $scene['exact']['points'] = array();
        $scene['exact']['overflow'] = true;
        return;
    }
    $scene['exact']['points'][] = array(
        (int) $row[$participant . 'X'], (int) $row[$participant . 'Y'], (int) $row[$participant . 'Z'],
        (int) $projected['x'], (int) $projected['y'],
        $channel, $participant, (bool) $projected['in_bounds'],
    );
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
    if ($z['status'] === 'valid') {
        $bucket = intval(floor(floatval($z['value']) / 32.0)) * 32;
        if (!isset($scene['zHistogram'][$bucket])) {
            $scene['zHistogram'][$bucket] = 0;
        }
        $scene['zHistogram'][$bucket]++;
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
            $assignedFloor = heatmap_assign_floor($z['value'], $scene['floors'], $x['value'], $y['value']);
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
    $inBounds = $projectedX >= 0 && $projectedY >= 0
        && $projectedX < $scene['image']['width'] && $projectedY < $scene['image']['height'];
    heatmap_scene_add_exact_point($scene, array(
        $participant . 'X' => $x['value'],
        $participant . 'Y' => $y['value'],
        $participant . 'Z' => $z['value'],
    ), array('x' => $projectedX, 'y' => $projectedY, 'in_bounds' => $inBounds), $channel, $participant);
    if (!$inBounds) {
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
    heatmap_surface_accumulate($scene, $z, $projectedX, $projectedY, $channel, $scene['query']['player'] > 0 && $participantId === $scene['query']['player']);
    if (isset($scene['geometry']) && !$scene['geometry']['overflow']) {
        $personal = $scene['query']['player'] > 0 && $participantId === $scene['query']['player'];
        if ($scene['query']['lens'] === 'me' && !$personal) {
            return;
        }
        $key = $projectedY . '.' . $projectedX;
        if (!isset($scene['geometry']['points'][$key])) {
            if (count($scene['geometry']['points']) >= 20000) {
                $scene['geometry'] = array('points' => array(), 'overflow' => true);
                return;
            }
            $scene['geometry']['points'][$key] = array(intval($projectedX), intval($projectedY), 0, 0);
        }
        $index = $scene['query']['lens'] === 'difference' ? ($personal ? 2 : 3) : ($channel === 'kills' ? 2 : 3);
        $scene['geometry']['points'][$key][$index]++;
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
        if (isset($scene['exact'])) {
            $scene['exact']['points'] = array();
            $scene['exact']['overflow'] = true;
        }
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
            // A bounded region intentionally excludes the rest of the map; its
            // availability depends on recorded Z, not whole-map assignment.
            'available' => (!empty($floor['regions']) || !empty($floor['blocked'])
                ? ($scene['validXY'] > 0 ? $scene['validZ'] / $scene['validXY'] : 0)
                : $zCoverage) >= HEATMAP_MIN_FLOOR_Z_COVERAGE && $count > 0,
        );
        foreach (array('regions', 'blocked') as $kind) if (!empty($floor[$kind])) {
            $metadata[count($metadata) - 1][$kind] = array_map(function ($polygon) use ($scene) {
                return array_map(function ($p) use ($scene) {
                    $point = heatmap_transform_point(array('pos_x' => $p[0], 'pos_y' => $p[1]), $scene['config']);
                    return array(intval($point['x']), intval($point['y']));
                }, $polygon);
            }, $floor[$kind]);
        }
    }

    return $metadata;
}

function heatmap_scene_floor_config_hash(array $floors): string
{
    $encoded = json_encode($floors, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    return substr(sha1(is_string($encoded) ? $encoded : '[]'), 0, 16);
}

function heatmap_scene_z_histogram_rows(array $histogram): array
{
    $rows = array();
    foreach ($histogram as $z => $count) {
        if (!is_numeric($z) || intval($count) <= 0) {
            continue;
        }
        $rows[] = array('z' => intval($z), 'count' => intval($count));
    }
    usort($rows, function ($left, $right) {
        return $left['z'] <=> $right['z'];
    });

    return $rows;
}

function heatmap_suggest_floor_bands(array $histogramRows): array
{
    $rows = array();
    foreach ($histogramRows as $row) {
        if (!is_array($row) || !isset($row['z'], $row['count']) || intval($row['count']) <= 0) {
            continue;
        }
        $z = intval($row['z']);
        if ($z < HEATMAP_MEDIUMINT_MIN || $z > HEATMAP_MEDIUMINT_MAX - 31) {
            continue;
        }
        $rows[$z] = true;
    }
    $starts = array_keys($rows);
    sort($starts, SORT_NUMERIC);
    if (!$starts) {
        return array();
    }

    $bands = array();
    $start = intval($starts[0]);
    $end = $start + 32;
    foreach (array_slice($starts, 1) as $next) {
        $next = intval($next);
        $gap = $next - $end;
        if ($gap >= 128 && count($bands) < HEATMAP_MAX_FLOORS - 1) {
            $bands[] = array('z_min' => $start, 'z_max' => $end);
            $start = $next;
        }
        $end = max($end, $next + 32);
    }
    $bands[] = array('z_min' => $start, 'z_max' => $end);

    $suggestions = array();
    foreach ($bands as $index => $band) {
        $number = $index + 1;
        $suggestions[] = array(
            'id' => 'floor' . $number,
            'label_en' => 'Floor ' . $number,
            'label_ru' => 'Уровень ' . $number,
            'z_min' => intval($band['z_min']),
            'z_max' => intval($band['z_max']),
        );
    }

    return heatmap_parse_floor_array($suggestions);
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
        $comparison['personalSample'] = 0;
        $comparison['otherSample'] = 0;
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

    $response = array(
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
            'zHistogram' => heatmap_scene_z_histogram_rows($scene['zHistogram']),
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
    $surfacePersonalCandidate = 0;
    foreach ($scene['meBins'] as $bin) $surfacePersonalCandidate += $bin['kills'] + $bin['deaths'];
    $response['surfaces'] = heatmap_surface_finalize($scene['surfaces'], $scene['overflow'], $scene['query']['lens'], $surfacePersonalCandidate);
    if (isset($scene['exact'])) {
        $response['exact'] = array(
            'fields' => array('x', 'y', 'z', 'projectedX', 'projectedY', 'channel', 'participant', 'inBounds'),
            'points' => $scene['exact']['points'],
            'overflow' => $scene['exact']['overflow'],
        );
    }
    if (isset($scene['geometry'])) {
        $geometryState = $scene['geometry']['overflow'] ? 'too_many_points' : $stateName;
        $points = in_array($geometryState, array('ok', 'empty'), true) ? array_values($scene['geometry']['points']) : array();
        usort($points, function (array $a, array $b): int { return ($a[1] <=> $b[1]) ?: ($a[0] <=> $b[0]); });
        return array(
            'schemaVersion' => 2, 'operation' => 'geometry', 'version' => 1, 'kind' => 'points',
            'state' => $geometryState, 'query' => $response['query'], 'map' => $response['map'],
            'fields' => $scene['query']['lens'] === 'difference' ? array('x', 'y', 'personal', 'others') : array('x', 'y', 'kills', 'deaths'),
            'points' => $points,
            'summary' => array('positions' => count($points), 'sourceRows' => $scene['sourceRows'],
                'personalSample' => $comparison['personalSample'], 'otherSample' => $comparison['otherSample']),
        );
    }

    return $response;
}

function heatmap_build_scene(PDO $pdo, array $query, array $config, array $image, array $options = array()): array
{
    $descriptor = heatmap_build_scene_sql($query, $config);
    $state = array('query' => $query, 'config' => $config, 'image' => $image, 'options' => $options);
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

function heatmap_inspect_grid(array $grid): array
{
    foreach (array('bucketSize', 'width', 'height', 'imageWidth', 'imageHeight') as $field) {
        if (!array_key_exists($field, $grid) || !is_int($grid[$field])) {
            throw new InvalidArgumentException('invalid_inspect');
        }
    }
    if ($grid['bucketSize'] <= 0 || $grid['width'] <= 0 || $grid['height'] <= 0
        || $grid['width'] > HEATMAP_GRID_MAX_AXIS || $grid['height'] > HEATMAP_GRID_MAX_AXIS
        || $grid['imageWidth'] <= 0 || $grid['imageHeight'] <= 0
        || $grid['bucketSize'] > intdiv(PHP_INT_MAX, HEATMAP_GRID_MAX_AXIS + 1)) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    return array(
        'bucketSize' => $grid['bucketSize'],
        'width' => $grid['width'],
        'height' => $grid['height'],
        'imageWidth' => $grid['imageWidth'],
        'imageHeight' => $grid['imageHeight'],
    );
}

function heatmap_parse_cell_id(string $cellId, array $grid): array
{
    $grid = heatmap_inspect_grid($grid);
    if (preg_match('/^c(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$/D', $cellId) !== 1) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    $parts = explode('.', substr($cellId, 1));
    $gridX = heatmap_try_canonical_integer($parts[0] ?? null);
    $gridY = heatmap_try_canonical_integer($parts[1] ?? null);
    if ($gridX === null || $gridY === null || $gridX < 0 || $gridX >= $grid['width']
        || $gridY < 0 || $gridY >= $grid['height'] || $gridX > 127 || $gridY > 127) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    $xMin = $gridX * $grid['bucketSize'];
    $yMin = $gridY * $grid['bucketSize'];
    $xMax = min($grid['imageWidth'], ($gridX + 1) * $grid['bucketSize']);
    $yMax = min($grid['imageHeight'], ($gridY + 1) * $grid['bucketSize']);
    if (!is_int($xMin) || !is_int($xMax) || !is_int($yMin) || !is_int($yMax)
        || $xMin >= $xMax || $yMin >= $yMax) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    return array(
        'id' => $cellId,
        'gridX' => $gridX,
        'gridY' => $gridY,
        'projectedBounds' => array(
            'xMin' => $xMin,
            'xMax' => $xMax,
            'yMin' => $yMin,
            'yMax' => $yMax,
        ),
    );
}

function heatmap_inspect_negated_interval(int $min, int $max): array
{
    if ($min >= $max) {
        throw new InvalidArgumentException('invalid_inspect');
    }
    $negatedMin = 0 - $max + 1;
    $negatedMax = 0 - $min + 1;
    if (!is_int($negatedMin) || !is_int($negatedMax) || $negatedMin >= $negatedMax) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    return array($negatedMin, $negatedMax);
}

function heatmap_inspect_inverse_rotation(array $projected, int $rotate): array
{
    $xMin = $projected['xMin'];
    $xMax = $projected['xMax'];
    $yMin = $projected['yMin'];
    $yMax = $projected['yMax'];
    $rotate = heatmap_rotation_steps($rotate);
    if ($rotate === 1) {
        $xInterval = array($yMin, $yMax);
        $yInterval = heatmap_inspect_negated_interval($xMin, $xMax);
    } elseif ($rotate === 2) {
        $xInterval = heatmap_inspect_negated_interval($xMin, $xMax);
        $yInterval = heatmap_inspect_negated_interval($yMin, $yMax);
    } elseif ($rotate === 3) {
        $xInterval = heatmap_inspect_negated_interval($yMin, $yMax);
        $yInterval = array($xMin, $xMax);
    } else {
        $xInterval = array($xMin, $xMax);
        $yInterval = array($yMin, $yMax);
    }

    return array('x' => $xInterval, 'y' => $yInterval);
}

function heatmap_inspect_truncated_value(int $value, int $offset, float $scale): int
{
    $quotient = (floatval($value) + floatval($offset)) / $scale;
    if ($quotient === INF || $quotient >= floatval(PHP_INT_MAX)) {
        return PHP_INT_MAX;
    }
    if ($quotient === -INF || $quotient <= floatval(PHP_INT_MIN)) {
        return PHP_INT_MIN;
    }

    return intval($quotient);
}

function heatmap_inspect_first_value_at_least(
    int $domainMin,
    int $domainMax,
    int $target,
    int $offset,
    float $scale
): int {
    $low = $domainMin;
    $high = $domainMax + 1;
    while ($low < $high) {
        $middle = $low + intdiv($high - $low, 2);
        if (heatmap_inspect_truncated_value($middle, $offset, $scale) >= $target) {
            $high = $middle;
        } else {
            $low = $middle + 1;
        }
    }

    return $low;
}

function heatmap_inspect_axis_preimage(int $min, int $max, int $offset, float $scale, bool $flip): ?array
{
    if ($min >= $max || !is_finite($scale) || $scale <= 0.0) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    $domainMin = $flip ? -HEATMAP_MEDIUMINT_MAX : HEATMAP_MEDIUMINT_MIN;
    $domainMax = $flip ? -HEATMAP_MEDIUMINT_MIN : HEATMAP_MEDIUMINT_MAX;
    $firstAtMin = heatmap_inspect_first_value_at_least($domainMin, $domainMax, $min, $offset, $scale);
    $firstAtMax = heatmap_inspect_first_value_at_least($domainMin, $domainMax, $max, $offset, $scale);
    $afterMin = max($domainMin, $firstAtMin);
    $afterMax = min($domainMax, $firstAtMax - 1);
    if ($afterMin > $afterMax) {
        return null;
    }

    if ($flip) {
        return array(0 - $afterMax, 0 - $afterMin);
    }

    return array($afterMin, $afterMax);
}

function heatmap_inspect_projection_config(array $config): array
{
    $config = heatmap_normalize_crop($config);
    $scale = heatmap_scale($config['scale'] ?? 1);
    if (!is_finite($scale) || $scale <= 0.0) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    return array(
        'xoffset' => intval($config['xoffset'] ?? 0),
        'yoffset' => intval($config['yoffset'] ?? 0),
        'flipx' => heatmap_bool($config['flipx'] ?? 0) === 1,
        'flipy' => heatmap_bool($config['flipy'] ?? 0) === 1,
        'rotate' => heatmap_rotation_steps($config['rotate'] ?? 0),
        'scale' => $scale,
        'cropx1' => intval($config['cropx1'] ?? 0),
        'cropy1' => intval($config['cropy1'] ?? 0),
    );
}

function heatmap_unproject_cell_bounds(array $cell, array $grid, array $config): array
{
    $grid = heatmap_inspect_grid($grid);
    if (!isset($cell['id']) || !is_string($cell['id'])) {
        throw new InvalidArgumentException('invalid_inspect');
    }
    $canonicalCell = heatmap_parse_cell_id($cell['id'], $grid);
    foreach (array('gridX', 'gridY') as $field) {
        if (array_key_exists($field, $cell) && $cell[$field] !== $canonicalCell[$field]) {
            throw new InvalidArgumentException('invalid_inspect');
        }
    }
    if (array_key_exists('projectedBounds', $cell)
        && $cell['projectedBounds'] !== $canonicalCell['projectedBounds']) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    $projection = heatmap_inspect_projection_config($config);
    $projected = $canonicalCell['projectedBounds'];
    $projectedWithCrop = array(
        'xMin' => $projected['xMin'] + $projection['cropx1'],
        'xMax' => $projected['xMax'] + $projection['cropx1'],
        'yMin' => $projected['yMin'] + $projection['cropy1'],
        'yMax' => $projected['yMax'] + $projection['cropy1'],
    );
    foreach ($projectedWithCrop as $value) {
        if (!is_int($value)) {
            throw new InvalidArgumentException('invalid_inspect');
        }
    }
    $inverse = heatmap_inspect_inverse_rotation($projectedWithCrop, $projection['rotate']);
    $rawX = heatmap_inspect_axis_preimage(
        $inverse['x'][0],
        $inverse['x'][1],
        $projection['xoffset'],
        $projection['scale'],
        $projection['flipx']
    );
    $rawY = heatmap_inspect_axis_preimage(
        $inverse['y'][0],
        $inverse['y'][1],
        $projection['yoffset'],
        $projection['scale'],
        $projection['flipy']
    );
    if ($rawX === null || $rawY === null) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    return array(
        'xMin' => max(HEATMAP_MEDIUMINT_MIN, min(HEATMAP_MEDIUMINT_MAX, $rawX[0])),
        'xMax' => max(HEATMAP_MEDIUMINT_MIN, min(HEATMAP_MEDIUMINT_MAX, $rawX[1])),
        'yMin' => max(HEATMAP_MEDIUMINT_MIN, min(HEATMAP_MEDIUMINT_MAX, $rawY[0])),
        'yMax' => max(HEATMAP_MEDIUMINT_MIN, min(HEATMAP_MEDIUMINT_MAX, $rawY[1])),
        'projectedBounds' => $projected,
    );
}

function heatmap_inspect_raw_bounds(array $bounds): array
{
    if (isset($bounds['rawBounds']) && is_array($bounds['rawBounds'])) {
        $bounds = $bounds['rawBounds'] + $bounds;
    }
    foreach (array('xMin', 'xMax', 'yMin', 'yMax') as $field) {
        if (!array_key_exists($field, $bounds) || !is_int($bounds[$field])) {
            throw new InvalidArgumentException('invalid_inspect');
        }
    }
    if ($bounds['xMin'] > $bounds['xMax'] || $bounds['yMin'] > $bounds['yMax']
        || $bounds['xMin'] < HEATMAP_MEDIUMINT_MIN || $bounds['xMax'] > HEATMAP_MEDIUMINT_MAX
        || $bounds['yMin'] < HEATMAP_MEDIUMINT_MIN || $bounds['yMax'] > HEATMAP_MEDIUMINT_MAX) {
        throw new InvalidArgumentException('invalid_inspect');
    }

    return array(
        'xMin' => $bounds['xMin'],
        'xMax' => $bounds['xMax'],
        'yMin' => $bounds['yMin'],
        'yMax' => $bounds['yMax'],
    );
}

function heatmap_inspect_sql_context(array $query, array $config, array $bounds): array
{
    $context = heatmap_scene_sql_context($query, $config);
    $player = heatmap_scene_player_id($query['player'] ?? 0);
    $event = $query['event'] ?? 'both';
    $lens = $query['lens'] ?? 'overview';
    if ($player === null || !in_array($event, array('kills', 'deaths', 'both'), true)
        || !in_array($lens, array('overview', 'me', 'difference'), true)
        || (($lens === 'me' || $lens === 'difference') && $player <= 0)
        || ($lens === 'difference' && $event === 'both')) {
        throw new InvalidArgumentException('invalid_scene_query');
    }
    $floors = heatmap_config_floors($config);
    $floor = $query['floor'] ?? 'all';
    if (!is_string($floor)) {
        throw new InvalidArgumentException('invalid_scene_query');
    }
    heatmap_validate_requested_floor($floor, $floors);
    $rawBounds = heatmap_inspect_raw_bounds($bounds);
    $floorBounds = null;
    if ($floor !== 'all') {
        foreach ($floors as $configuredFloor) {
            if ($configuredFloor['id'] === $floor) {
                $floorBounds = array('zMin' => $configuredFloor['z_min'], 'zMax' => $configuredFloor['z_max'], 'regions' => $configuredFloor['regions'] ?? array(), 'blocked' => $configuredFloor['blocked'] ?? array());
                break;
            }
        }
        if ($floorBounds === null) {
            throw new InvalidArgumentException('unknown_floor');
        }
    }

    return array(
        'context' => $context,
        'player' => $player,
        'event' => $event,
        'lens' => $lens,
        'rawBounds' => $rawBounds,
        'floorBounds' => $floorBounds,
    );
}

function heatmap_build_inspect_sql(array $query, array $config, array $bounds): array
{
    $context = heatmap_inspect_sql_context($query, $config, $bounds);
    $branches = array();
    $params = array();
    $branchIndex = 0;
    $channels = $context['event'] === 'both' ? array('kills', 'deaths') : array($context['event']);
    $sources = array(
        array('table' => 'hlstats_Events_Frags', 'prefix' => 'frags', 'teamkill' => 0),
        array('table' => 'hlstats_Events_Teamkills', 'prefix' => 'teamkills', 'teamkill' => 1),
    );
    foreach ($channels as $channel) {
        $participant = $channel === 'kills' ? 'attacker' : 'victim';
        $xColumn = $channel === 'kills' ? 'pos_x' : 'pos_victim_x';
        $yColumn = $channel === 'kills' ? 'pos_y' : 'pos_victim_y';
        $zColumn = $channel === 'kills' ? 'pos_z' : 'pos_victim_z';
        foreach ($sources as $source) {
            $prefix = $source['prefix'] . '_' . $channel;
            $playerJoinAlias = $participant === 'attacker' ? 'killer_player' : 'victim_player';
            $playerPredicate = '';
            if ($context['lens'] === 'me') {
                $playerPredicate = '                AND ' . $playerJoinAlias . '.playerId = :' . $prefix . '_player';
                $params[$prefix . '_player'] = $context['player'];
            }
            $floorPredicate = '';
            if ($context['floorBounds'] !== null) {
                $floorPredicate = '                AND hef.' . $zColumn . ' >= :' . $prefix . '_z_min' . "\n"
                    . '                AND hef.' . $zColumn . ' < :' . $prefix . '_z_max' . "\n";
                $params[$prefix . '_z_min'] = $context['floorBounds']['zMin'];
                $params[$prefix . '_z_max'] = $context['floorBounds']['zMax'];
                if ($context['floorBounds']['regions']) {
                    $floorPredicate .= '                AND ' . heatmap_regions_sql($context['floorBounds']['regions'], 'hef.' . $xColumn, 'hef.' . $yColumn) . "\n";
                }
                if (!empty($context['floorBounds']['blocked'])) {
                    $floorPredicate .= '                AND NOT ' . heatmap_regions_sql($context['floorBounds']['blocked'], 'hef.' . $xColumn, 'hef.' . $yColumn) . "\n";
                }
            }
            $branchLines = array(
                '            SELECT',
                '                hef.eventTime AS eventTime,',
                "                '" . ($channel === 'kills' ? 'kill' : 'death') . "' AS event,",
                '                COALESCE(killer_player.playerId, 0) AS killerId,',
                "                COALESCE(killer_player.lastName, '') AS killerName,",
                '                COALESCE(victim_player.playerId, 0) AS victimId,',
                "                COALESCE(victim_player.lastName, '') AS victimName,",
                '                hef.weapon AS weapon,',
                $channel === 'kills' && $source['teamkill'] === 0
                    ? '                hef.headshot AS headshot,'
                    : '                0 AS headshot,',
                '                ' . $source['teamkill'] . ' AS teamkill,',
                '                hef.id AS eventId,',
                '                ' . $branchIndex . ' AS sourceOrder',
                '            FROM ' . $source['table'] . ' AS hef',
                '            INNER JOIN hlstats_Servers AS hs ON hs.serverId = hef.serverId',
                '            LEFT JOIN hlstats_Players AS killer_player',
                '                ON killer_player.playerId = hef.killerId',
                '                AND killer_player.hideranking = 0',
                '            LEFT JOIN hlstats_Players AS victim_player',
                '                ON victim_player.playerId = hef.victimId',
                '                AND victim_player.hideranking = 0',
                '            WHERE hef.map = :' . $prefix . '_map',
                '                AND hs.game = :' . $prefix . '_game',
                '                AND hef.eventTime >= FROM_UNIXTIME(:' . $prefix . '_from)',
                '                AND hef.eventTime < FROM_UNIXTIME(:' . $prefix . '_to)',
                '                AND hef.' . $xColumn . ' >= :' . $prefix . '_x_min',
                '                AND hef.' . $xColumn . ' <= :' . $prefix . '_x_max',
                '                AND hef.' . $yColumn . ' >= :' . $prefix . '_y_min',
                '                AND hef.' . $yColumn . ' <= :' . $prefix . '_y_max',
            );
            $branch = implode("\n", $branchLines) . "\n" . $floorPredicate . $playerPredicate;
            $branches[] = rtrim($branch);
            $params[$prefix . '_map'] = $context['context']['map'];
            $params[$prefix . '_game'] = $context['context']['game'];
            $params[$prefix . '_from'] = $context['context']['from'];
            $params[$prefix . '_to'] = $context['context']['to'];
            $params[$prefix . '_x_min'] = $context['rawBounds']['xMin'];
            $params[$prefix . '_x_max'] = $context['rawBounds']['xMax'];
            $params[$prefix . '_y_min'] = $context['rawBounds']['yMin'];
            $params[$prefix . '_y_max'] = $context['rawBounds']['yMax'];
            $branchIndex++;
        }
    }
    if (!$branches) {
        throw new InvalidArgumentException('invalid_scene_query');
    }

    $sql = implode("\n", array(
        'SELECT',
        '    inspect_events.eventTime,',
        '    inspect_events.event,',
        '    inspect_events.killerId,',
        '    inspect_events.killerName,',
        '    inspect_events.victimId,',
        '    inspect_events.victimName,',
        '    inspect_events.weapon,',
        '    inspect_events.headshot,',
        '    inspect_events.teamkill',
        'FROM (',
        implode("\n            UNION ALL\n", $branches),
        ') AS inspect_events',
        'ORDER BY eventTime DESC, eventId DESC, sourceOrder ASC',
        'LIMIT ' . HEATMAP_INSPECT_MAX_ROWS,
    ));

    return array('sql' => $sql, 'params' => $params, 'limit' => HEATMAP_INSPECT_MAX_ROWS);
}

function heatmap_inspect_event_time($value): string
{
    if ($value instanceof DateTimeInterface) {
        return $value->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\\TH:i:s\\Z');
    }
    if (!is_string($value) && !is_int($value) && !is_float($value)) {
        return '';
    }
    try {
        $date = new DateTimeImmutable(strval($value), new DateTimeZone('UTC'));
    } catch (Throwable $exception) {
        return '';
    }

    return $date->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\\TH:i:s\\Z');
}

function heatmap_inspect_public_player_id($value): int
{
    $playerId = heatmap_try_canonical_integer($value);
    return $playerId !== null && $playerId > 0 && $playerId <= HEATMAP_MYSQL_UNSIGNED_INT_MAX ? $playerId : 0;
}

function heatmap_inspect_weapon($value): string
{
    if (!is_string($value)) {
        return '';
    }
    $value = trim($value);
    return strlen($value) <= 64 && preg_match('/^[A-Za-z0-9_.:$-]*$/D', $value) === 1 ? $value : '';
}

function heatmap_inspect_aggregates(array $rows): array
{
    $weaponCounts = array();
    $killerIds = array();
    $victimIds = array();
    $participantIds = array();
    foreach ($rows as $row) {
        $weapon = strval($row['weapon'] ?? '');
        if ($weapon !== '') {
            $weaponCounts[$weapon] = intval($weaponCounts[$weapon] ?? 0) + 1;
        }
        $killerId = intval($row['killer']['id'] ?? 0);
        if ($killerId > 0) {
            $killerIds[$killerId] = true;
            $participantIds[$killerId] = true;
        }
        $victimId = intval($row['victim']['id'] ?? 0);
        if ($victimId > 0) {
            $victimIds[$victimId] = true;
            $participantIds[$victimId] = true;
        }
    }

    $topWeapons = array();
    foreach ($weaponCounts as $weapon => $count) {
        $topWeapons[] = array('weapon' => strval($weapon), 'count' => $count);
    }
    usort($topWeapons, function (array $left, array $right): int {
        $countCompare = intval($right['count']) <=> intval($left['count']);
        return $countCompare !== 0 ? $countCompare : strcmp($left['weapon'], $right['weapon']);
    });

    return array(
        'scope' => 'returned_rows',
        'sampleRows' => count($rows),
        'topWeapons' => array_slice($topWeapons, 0, 5),
        'participantCounts' => array(
            'unique' => count($participantIds),
            'killers' => count($killerIds),
            'victims' => count($victimIds),
        ),
    );
}

function heatmap_build_inspect_payload(array $rows, bool $truncated): array
{
    $payloadRows = array();
    foreach (array_slice($rows, 0, 100) as $row) {
        $event = strtolower(trim(strval($row['event'] ?? '')));
        $event = $event === 'death' || $event === 'deaths' ? 'death' : 'kill';
        $payloadRows[] = array(
            'eventTime' => heatmap_inspect_event_time($row['eventTime'] ?? null),
            'event' => $event,
            'killer' => array(
                'id' => heatmap_inspect_public_player_id($row['killerId'] ?? null),
                'name' => heatmap_actor_name($row['killerName'] ?? ''),
            ),
            'victim' => array(
                'id' => heatmap_inspect_public_player_id($row['victimId'] ?? null),
                'name' => heatmap_actor_name($row['victimName'] ?? ''),
            ),
            'weapon' => heatmap_inspect_weapon($row['weapon'] ?? null),
            'headshot' => intval($row['headshot'] ?? 0) !== 0,
            'teamkill' => intval($row['teamkill'] ?? 0) !== 0,
        );
    }

    return array(
        'schemaVersion' => HEATMAP_V2_SCHEMA,
        'operation' => 'inspect',
        'state' => 'ok',
        'rows' => $payloadRows,
        'aggregates' => heatmap_inspect_aggregates($payloadRows),
        'truncated' => $truncated,
        'warnings' => array(),
    );
}

function heatmap_inspect_context(array $query, array $config, array $image): array
{
    $state = array('query' => $query, 'config' => $config, 'image' => $image);
    heatmap_scene_prepare_state($state);
    $scene = $state['_scene'];
    return array(
        'query' => $scene['query'],
        'config' => $scene['config'],
        'image' => $scene['image'],
        'grid' => array(
            'bucketSize' => $scene['bucketSize'],
            'width' => $scene['gridWidth'],
            'height' => $scene['gridHeight'],
            'imageWidth' => $scene['image']['width'],
            'imageHeight' => $scene['image']['height'],
        ),
    );
}

function heatmap_fetch_inspect_rows(PDO $pdo, array $descriptor): array
{
    if (!isset($descriptor['sql'], $descriptor['params']) || !is_string($descriptor['sql'])
        || !is_array($descriptor['params'])) {
        throw new InvalidArgumentException('invalid_inspect');
    }
    $statement = $pdo->prepare($descriptor['sql']);
    if (!$statement instanceof PDOStatement) {
        throw new RuntimeException('inspect_statement_unavailable');
    }
    $rows = array();
    try {
        $statement->execute($descriptor['params']);
        while (count($rows) < HEATMAP_INSPECT_MAX_ROWS
            && ($row = $statement->fetch(PDO::FETCH_ASSOC)) !== false) {
            $rows[] = $row;
        }
    } finally {
        $statement->closeCursor();
    }

    return $rows;
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

    if ($name !== '') {
        return $name;
    }

    return function_exists('localized_text')
        ? localized_text('literal.unknown', 'Unknown')
        : 'Unknown';
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

function heatmap_cache_subdirectory(string $name): ?string
{
    if ($name !== 'locks') {
        return null;
    }

    $directory = heatmap_cache_dir() . DIRECTORY_SEPARATOR . $name;
    if (!is_dir($directory) && !@mkdir($directory, 0700, true)) {
        return null;
    }
    if (is_link($directory) || !is_dir($directory) || !is_writable($directory)) {
        return null;
    }

    @chmod($directory, 0700);
    return $directory;
}

function heatmap_admin_map_lock_path(string $game, string $map): string
{
    $game = heatmap_clean_token($game);
    $map = heatmap_clean_token($map);
    $directory = heatmap_cache_subdirectory('locks');
    if ($game === '' || $map === '' || $directory === null) {
        throw new RuntimeException('admin_lock_unavailable');
    }

    return $directory . DIRECTORY_SEPARATOR . hash('sha256', $game . "\0" . $map) . '.lock';
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
    $sourceIdentity = strval($image['sourceIdentity'] ?? '');
    if ($sourceIdentity === '' && is_file($sourcePath)) {
        $sourceIdentity = heatmap_map_source_identity($sourcePath);
    }
    $payload = array(
        'projection' => $projection,
        'floorParserSchema' => HEATMAP_FLOOR_PARSER_SCHEMA,
        'floors' => $projection['floors'],
        'days' => intval($config['days'] ?? 30),
        'brush' => strval($config['brush'] ?? 'small'),
        'imageMtime' => is_file($sourcePath) ? filemtime($sourcePath) : 0,
        'imageIdentity' => $sourceIdentity,
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

function heatmap_map_source_identity(string $path): string
{
    clearstatcache(true, $path);
    if (!is_file($path)) {
        return '';
    }

    $digest = hash_file('sha256', $path);
    if (!is_string($digest) || preg_match('/^[a-f0-9]{64}$/D', $digest) !== 1) {
        throw new RuntimeException('map_asset_unreadable');
    }

    return $digest;
}

function heatmap_map_source_snapshot(string $path): array
{
    clearstatcache(true, $path);
    $bytes = @file_get_contents($path);
    if (!is_string($bytes)) {
        throw new RuntimeException('map_asset_unreadable');
    }
    $size = @getimagesizefromstring($bytes);
    if (!is_array($size) || intval($size[0] ?? 0) <= 0 || intval($size[1] ?? 0) <= 0) {
        throw new RuntimeException('map_asset_unreadable');
    }

    return array(
        'bytes' => $bytes,
        'width' => intval($size[0]),
        'height' => intval($size[1]),
        'mime' => is_string($size['mime'] ?? null) ? $size['mime'] : 'application/octet-stream',
        'sourceIdentity' => hash('sha256', $bytes),
    );
}

function heatmap_map_request_version_state($requested, string $sourceIdentity): string
{
    $requested = is_string($requested) ? $requested : '';
    if (preg_match('/^[a-f0-9]{64}$/D', $requested) !== 1) {
        return 'unversioned';
    }

    return hash_equals($sourceIdentity, $requested) ? 'current' : 'stale';
}

function heatmap_version_fallback_image(array $image, string $game, string $map): array
{
    $snapshot = heatmap_map_source_snapshot(strval($image['path'] ?? ''));
    $sourceIdentity = $snapshot['sourceIdentity'];
    $game = heatmap_clean_token($game);
    $map = heatmap_clean_token($map);
    if ($game === '' || $map === '') {
        throw new InvalidArgumentException('invalid_image');
    }
    $image['url'] = 'heatmap_map.php?game=' . rawurlencode($game)
        . '&map=' . rawurlencode($map)
        . '&source=hlstatsimg&v=' . $sourceIdentity;
    $image['width'] = $snapshot['width'];
    $image['height'] = $snapshot['height'];
    $image['sourceIdentity'] = $sourceIdentity;

    return $image;
}

function heatmap_admin_file_identity(string $path): array
{
    clearstatcache(true, $path);
    if (is_link($path) || !is_file($path)) {
        return array('state' => 'missing');
    }

    $digest = hash_file('sha256', $path);
    if (!is_string($digest) || $digest === '') {
        throw new RuntimeException('admin_asset_unreadable');
    }
    clearstatcache(true, $path);

    return array(
        'state' => 'present',
        'sha256' => $digest,
        'bytes' => max(0, intval(filesize($path))),
    );
}

function heatmap_overview_path(array $config, string $map): string
{
    $game = heatmap_clean_token($config['game'] ?? '');
    $map = heatmap_clean_token($map);
    if ($game === '' || $map === '') {
        throw new InvalidArgumentException('invalid_overview_target');
    }

    return dirname(__DIR__, 2) . '/heatmaps/overviews/' . $game . '/' . $map . '.txt';
}

function heatmap_admin_config_hash(array $config, array $image = null): string
{
    $map = heatmap_clean_token($config['map'] ?? '');
    if ($map === '') {
        throw new InvalidArgumentException('invalid_config_hash');
    }
    $image = $image ?? heatmap_image_metadata($config['code'] ?? $config['game'] ?? '', $map, $config);
    $sourceWidth = intval($image['sourceWidth'] ?? $image['width'] ?? 0);
    $sourceHeight = intval($image['sourceHeight'] ?? $image['height'] ?? 0);
    $config = heatmap_normalize_crop($config, $sourceWidth, $sourceHeight);
    $sourcePath = heatmap_source_path($config, $map);
    $imagePath = strval($image['path'] ?? '');
    if ($imagePath === '') {
        $imagePath = $sourcePath;
    }
    $payload = array(
        'schema' => 1,
        'projection' => heatmap_projection_config($config),
        'image' => heatmap_admin_file_identity($imagePath),
        'overview' => heatmap_admin_file_identity(heatmap_overview_path($config, $map)),
    );
    foreach (heatmap_config_floors($config) as $floor) {
        if (!empty($floor['image'])) $payload['floorImages'][$floor['id']] = heatmap_admin_file_identity(heatmap_source_path($config, $map . '--' . $floor['id']));
    }
    $encoded = json_encode(
        heatmap_cache_identity_value($payload),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION
    );
    if (!is_string($encoded)) {
        throw new RuntimeException('admin_hash_unavailable');
    }

    return hash('sha256', $encoded);
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

function heatmap_validate_base_image_dimensions(array $config, string $map, int $width, int $height): void
{
    foreach (heatmap_config_floors($config) as $floor) {
        if (empty($floor['image'])) continue;
        $path = heatmap_source_path($config, $map . '--' . $floor['id']);
        $layer = heatmap_map_source_snapshot($path);
        if ($layer['width'] !== $width || $layer['height'] !== $height) {
            throw new InvalidArgumentException('floor_image_size');
        }
    }
}

function heatmap_floor_source_path(array $config, string $map, string $floor): ?string
{
    if ($floor === 'all') return null;
    $floors = heatmap_config_floors($config);
    heatmap_validate_requested_floor($floor, $floors);
    foreach ($floors as $item) {
        if ($item['id'] === $floor && !empty($item['image'])) {
            $path = heatmap_source_path($config, $map . '--' . $floor);
            if (!is_file($path)) throw new InvalidArgumentException('invalid_image');
            $base = heatmap_map_source_snapshot(heatmap_source_path($config, $map));
            $layer = heatmap_map_source_snapshot($path);
            if ($base['width'] !== $layer['width'] || $base['height'] !== $layer['height']) throw new InvalidArgumentException('invalid_image');
            return $path;
        }
    }
    return null;
}

function heatmap_image_metadata($game, $map, array $config, string $floor = 'all')
{
    $floorPath = heatmap_floor_source_path($config, $map, $floor);
    $sourcePath = $floorPath ?? heatmap_source_path($config, $map);
    if (is_file($sourcePath)) {
        $sourceSnapshot = heatmap_map_source_snapshot($sourcePath);
        $sourceIdentity = $sourceSnapshot['sourceIdentity'];
        $config = heatmap_normalize_crop($config, $sourceSnapshot['width'], $sourceSnapshot['height']);
        $base = array(
            'url' => 'heatmap_map.php?game=' . rawurlencode($game) . '&map=' . rawurlencode($map),
            'width' => $sourceSnapshot['width'],
            'height' => $sourceSnapshot['height'],
            'sourceWidth' => $sourceSnapshot['width'],
            'sourceHeight' => $sourceSnapshot['height'],
            'source' => 'heatmaps/src',
            'sourceIdentity' => $sourceIdentity,
        );
        if ($floorPath !== null) $base['url'] .= '&floor=' . rawurlencode($floor);
        if (heatmap_has_crop($config)) {
            $base['url'] .= '&crop=1'
                . '&cropx1=' . intval($config['cropx1'])
                . '&cropy1=' . intval($config['cropy1'])
                . '&cropx2=' . intval($config['cropx2'])
                . '&cropy2=' . intval($config['cropy2'])
                . '&v=' . $sourceIdentity;
            list($base['width'], $base['height']) = heatmap_projected_image_size($base, $config);
            $base['crop'] = array(
                'x' => intval($config['cropx1']),
                'y' => intval($config['cropy1']),
                'width' => intval($config['cropx2']),
                'height' => intval($config['cropy2']),
            );
        } else {
            $base['url'] .= '&v=' . $sourceIdentity;
        }
        return $base;
    }

    $image = getImage('/games/' . $game . '/maps/' . $map);
    if (!$image && !empty($config['realgame'])) {
        $image = getImage('/games/' . $config['realgame'] . '/maps/' . $map);
    }
    if ($image) {
        $image = heatmap_version_fallback_image($image, $game, $map);
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

function heatmap_fetch_config_for_update(PDO $pdo, $game, $map): ?array
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
        LIMIT 1 FOR UPDATE'
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
            'rotate' => 0,
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
        throw new InvalidArgumentException('GoldSrc TXT requires native image registration; use scripts/heatmap_bsp_registration.py and preview the resulting projection with landmarks.');
    }

    throw new InvalidArgumentException('overview file did not contain supported projection fields');
}
