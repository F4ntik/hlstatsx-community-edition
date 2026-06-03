<?php

if (!defined('IN_HLSTATS')) {
    http_response_code(403);
    exit;
}

function i18n_lang_dir()
{
    return ROOT_PATH . '/lang';
}

function i18n_normalize_lang($lang)
{
    $lang = strtolower(trim((string) $lang));
    if ($lang === '') {
        return '';
    }
    if (!preg_match('/^[a-z0-9_-]+$/', $lang)) {
        return '';
    }

    return $lang;
}

function i18n_load_catalog($code)
{
    static $catalogs = array();

    $code = i18n_normalize_lang($code);
    if ($code === '') {
        return null;
    }

    if (isset($catalogs[$code])) {
        return $catalogs[$code];
    }

    $file = i18n_lang_dir() . "/$code.php";
    if (!file_exists($file)) {
        return null;
    }

    $catalog = require $file;
    if (!is_array($catalog)) {
        return null;
    }

    $catalog['meta'] = isset($catalog['meta']) && is_array($catalog['meta']) ? $catalog['meta'] : array();
    $catalog['messages'] = isset($catalog['messages']) && is_array($catalog['messages']) ? $catalog['messages'] : array();
    $catalog['meta']['code'] = $code;
    $catalog['meta']['label'] = $catalog['meta']['label'] ?? strtoupper($code);

    $catalogs[$code] = $catalog;

    return $catalog;
}

function i18n_resolve_request_lang(array $query, array $cookies, array $session, ?array $available = null, $defaultLang = 'en')
{
    $available = $available ?? available_langs();
    $defaultLang = i18n_normalize_lang($defaultLang);
    if ($defaultLang === '' || !isset($available[$defaultLang])) {
        $defaultLang = 'en';
    }

    $candidates = array(
        $query['lang'] ?? null,
        $cookies['lang'] ?? null,
        $session['lang'] ?? null,
    );
    foreach ($candidates as $candidate) {
        $candidate = i18n_normalize_lang($candidate);
        if ($candidate !== '' && isset($available[$candidate])) {
            return $candidate;
        }
    }

    return $defaultLang;
}

function available_langs()
{
    static $available = null;

    if ($available !== null) {
        return $available;
    }

    $available = array();
    foreach (glob(i18n_lang_dir() . '/*.php') ?: array() as $file) {
        $code = basename($file, '.php');
        $catalog = i18n_load_catalog($code);
        if ($catalog) {
            $available[$code] = $catalog['meta'];
        }
    }

    if (!isset($available['en'])) {
        $available['en'] = array('code' => 'en', 'label' => 'English');
    }

    uksort($available, function ($left, $right) {
        if ($left === 'en') {
            return -1;
        }

        if ($right === 'en') {
            return 1;
        }

        return strcmp($left, $right);
    });

    return $available;
}

function init_i18n()
{
    $available = available_langs();
    $defaultLang = 'en';
    $requested = i18n_resolve_request_lang($_GET, $_COOKIE, $_SESSION ?? array(), $available, $defaultLang);

    $GLOBALS['i18n_default_lang'] = $defaultLang;
    $GLOBALS['i18n_current_lang'] = $requested;
    $GLOBALS['i18n_available_langs'] = $available;

    $enCatalog = i18n_load_catalog($defaultLang);
    $currentCatalog = i18n_load_catalog($requested);

    $GLOBALS['i18n_en_messages'] = $enCatalog['messages'] ?? array();
    $GLOBALS['i18n_current_messages'] = $currentCatalog['messages'] ?? array();

    if (session_status() === PHP_SESSION_ACTIVE) {
        $_SESSION['lang'] = $requested;
    }

    @setcookie('lang', $requested, time() + 60 * 60 * 24 * 30, '/');
}

function current_lang()
{
    return $GLOBALS['i18n_current_lang'] ?? 'en';
}

function i18n_interpolate($text, array $params = array())
{
    if (!$params) {
        return $text;
    }

    $replacements = array();
    foreach ($params as $key => $value) {
        $replacements[':' . $key] = $value;
        $replacements['{' . $key . '}'] = $value;
    }

    return strtr($text, $replacements);
}

function t($key, $params = array(), $fallback = null)
{
    $messages = $GLOBALS['i18n_current_messages'] ?? array();
    $enMessages = $GLOBALS['i18n_en_messages'] ?? array();

    if (isset($messages[$key]) && $messages[$key] !== '') {
        $text = $messages[$key];
    } elseif (isset($enMessages[$key]) && $enMessages[$key] !== '') {
        $text = $enMessages[$key];
    } elseif ($fallback !== null) {
        $text = $fallback;
    } else {
        $text = $key;
    }

    return i18n_interpolate($text, (array) $params);
}

function i18n_build_lang_url($code, array $params, $base, $exclude = array())
{
    $normalizedCode = i18n_normalize_lang($code);
    if ($normalizedCode !== '') {
        $params['lang'] = $normalizedCode;
    } else {
        unset($params['lang']);
    }
    foreach ((array) $exclude as $param) {
        unset($params[$param]);
    }
    $query = http_build_query($params);

    return $query === '' ? $base : $base . '?' . $query;
}

function lang_url($code, $exclude = array())
{
    global $g_options;

    $base = $g_options['scripturl'] ?? ($_SERVER['PHP_SELF'] ?? 'hlstats.php');

    return i18n_build_lang_url($code, $_GET, $base, $exclude);
}

function i18n_historical_cache_target(array $request, $lang, $cacheRoot = 'cache')
{
    $request['lang'] = i18n_normalize_lang($lang) ?: 'en';
    ksort($request);

    $rawmd5 = md5(http_build_query($request));
    $dir1 = substr($rawmd5, 0, 1);
    $dir2 = substr($rawmd5, 1, 1);

    return array(
        'key' => $rawmd5,
        'dir1' => $dir1,
        'dir2' => $dir2,
        'path' => sprintf('%s/%s/%s/%s', rtrim($cacheRoot, '/'), $dir1, $dir2, $rawmd5),
    );
}

