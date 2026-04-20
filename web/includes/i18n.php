<?php

if (!defined('IN_HLSTATS')) {
    die('Do not access this file directly.');
}

function i18n_lang_dir()
{
    return ROOT_PATH . '/lang';
}

function i18n_normalize_lang($lang)
{
    $lang = strtolower(trim((string) $lang));
    $lang = preg_replace('/[^a-z0-9_-]/', '', $lang);

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
    $requested = null;

    if (!empty($_GET['lang'])) {
        $requested = $_GET['lang'];
    } elseif (!empty($_COOKIE['lang'])) {
        $requested = $_COOKIE['lang'];
    } elseif (isset($_SESSION['lang'])) {
        $requested = $_SESSION['lang'];
    }

    $requested = i18n_normalize_lang($requested);
    if ($requested === '' || !isset($available[$requested])) {
        $requested = $defaultLang;
    }

    $GLOBALS['i18n_default_lang'] = $defaultLang;
    $GLOBALS['i18n_current_lang'] = $requested;
    $GLOBALS['i18n_available_langs'] = $available;

    $enCatalog = i18n_load_catalog($defaultLang);
    $currentCatalog = i18n_load_catalog($requested);

    $GLOBALS['i18n_en_messages'] = $enCatalog['messages'] ?? array();
    $GLOBALS['i18n_current_messages'] = $currentCatalog['messages'] ?? array();
    $GLOBALS['i18n_literal_map'] = null;

    $_GET['lang'] = $requested;
    $_REQUEST['lang'] = $requested;
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

function lang_url($code)
{
    global $g_options;

    $params = $_GET;
    $params['lang'] = i18n_normalize_lang($code);
    $base = $g_options['scripturl'] ?? ($_SERVER['PHP_SELF'] ?? 'hlstats.php');

    return $base . '?' . http_build_query($params);
}

function i18n_literal_map()
{
    if (isset($GLOBALS['i18n_literal_map']) && is_array($GLOBALS['i18n_literal_map'])) {
        return $GLOBALS['i18n_literal_map'];
    }

    $map = array();
    $source = $GLOBALS['i18n_en_messages'] ?? array();
    $target = $GLOBALS['i18n_current_messages'] ?? array();

    foreach ($source as $key => $sourceText) {
        if (!is_string($sourceText) || $sourceText === '') {
            continue;
        }

        $targetText = $target[$key] ?? $sourceText;
        if (!is_string($targetText) || $targetText === '' || $targetText === $sourceText) {
            continue;
        }

        $map[$sourceText] = $targetText;
    }

    uksort($map, function ($left, $right) {
        return strlen($right) <=> strlen($left);
    });

    $GLOBALS['i18n_literal_map'] = $map;

    return $map;
}

function i18n_translate_literal_value($value, array $map)
{
    if (!is_string($value) || $value === '') {
        return $value;
    }

    $trimmed = trim($value);
    if ($trimmed === '' || !isset($map[$trimmed])) {
        return $value;
    }

    preg_match('/^\s*/u', $value, $leading);
    preg_match('/\s*$/u', $value, $trailing);

    return $leading[0] . $map[$trimmed] . $trailing[0];
}

function i18n_translate_dom_node($node, array $map)
{
    if ($node instanceof DOMText) {
        $node->nodeValue = i18n_translate_literal_value($node->nodeValue, $map);
        return;
    }

    if ($node instanceof DOMElement) {
        $attrs = array('alt', 'title', 'placeholder', 'aria-label');

        if ($node->tagName === 'input') {
            $type = strtolower((string) $node->getAttribute('type'));
            if (!in_array($type, array('hidden', 'checkbox', 'radio'), true)) {
                $attrs[] = 'value';
            }
        }

        foreach ($attrs as $attr) {
            if ($node->hasAttribute($attr)) {
                $node->setAttribute($attr, i18n_translate_literal_value($node->getAttribute($attr), $map));
            }
        }
    }

    if (!$node->hasChildNodes()) {
        return;
    }

    foreach ($node->childNodes as $childNode) {
        i18n_translate_dom_node($childNode, $map);
    }
}

function i18n_translate_output_dom($html, array $map)
{
    if (!class_exists('DOMDocument')) {
        return null;
    }

    $dom = new DOMDocument('1.0', 'UTF-8');
    $previous = libxml_use_internal_errors(true);
    $flags = 0;

    if (defined('LIBXML_HTML_NOIMPLIED')) {
        $flags |= LIBXML_HTML_NOIMPLIED;
    }

    if (defined('LIBXML_HTML_NODEFDTD')) {
        $flags |= LIBXML_HTML_NODEFDTD;
    }

    $loaded = $dom->loadHTML('<?xml encoding="utf-8" ?>' . $html, $flags);
    if (!$loaded) {
        libxml_clear_errors();
        libxml_use_internal_errors($previous);
        return null;
    }

    if ($dom->documentElement) {
        i18n_translate_dom_node($dom->documentElement, $map);
    }

    $translated = $dom->saveHTML();
    $translated = preg_replace('/^<\?xml.+?\?>/u', '', $translated);

    libxml_clear_errors();
    libxml_use_internal_errors($previous);

    return $translated;
}

function i18n_translate_output_strtr($html, array $map)
{
    $replacements = array(
        '/(\d+)h (\d+)m (\d+)s/u' => '$1' . t('time.compact.h') . ' $2' . t('time.compact.m') . ' $3' . t('time.compact.s'),
        '/(\d+)m (\d+)s/u' => '$1' . t('time.compact.m') . ' $2' . t('time.compact.s'),
        '/(\d+)s/u' => '$1' . t('time.compact.s'),
    );

    foreach ($replacements as $pattern => $replacement) {
        $html = preg_replace($pattern, $replacement, $html);
    }

    return $html;
}

function translate_output_html($html)
{
    if (current_lang() === ($GLOBALS['i18n_default_lang'] ?? 'en')) {
        return $html;
    }

    $map = i18n_literal_map();
    if (!$map) {
        return $html;
    }

    $translated = i18n_translate_output_dom($html, $map);
    if ($translated === null) {
        $translated = $html;
    }

    return i18n_translate_output_strtr($translated, $map);
}
