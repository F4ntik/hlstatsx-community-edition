<?php
/*
 * Shared security primitives for the classic administrator pages.
 *
 * Keep this file independent from the page renderer so the session and
 * password boundaries can be exercised without a database-backed request.
 */

if (!defined('HLSTATS_ADMIN_PASSWORD_DB_VERSION')) {
    define('HLSTATS_ADMIN_PASSWORD_DB_VERSION', 83);
}

function admin_request_scalar_string($value)
{
    return is_string($value) ? $value : '';
}

function admin_password_uses_legacy_md5($storedPassword)
{
    return is_string($storedPassword)
        && preg_match('/\A[0-9a-f]{32}\z/iD', $storedPassword) === 1;
}

function admin_password_verify_value($password, $storedPassword)
{
    if (!is_string($password) || !is_string($storedPassword)) {
        return false;
    }

    if (admin_password_uses_legacy_md5($storedPassword)) {
        return hash_equals(strtolower($storedPassword), md5($password));
    }

    return password_verify($password, $storedPassword);
}

function admin_password_needs_upgrade($storedPassword)
{
    if (admin_password_uses_legacy_md5($storedPassword)) {
        return true;
    }

    if (!is_string($storedPassword)) {
        return false;
    }

    $info = password_get_info($storedPassword);
    return !empty($info['algo']) && password_needs_rehash($storedPassword, PASSWORD_DEFAULT);
}

function admin_password_storage_is_ready($options)
{
    return is_array($options)
        && isset($options['dbversion'])
        && (int) $options['dbversion'] >= HLSTATS_ADMIN_PASSWORD_DB_VERSION;
}

function admin_password_hash_for_storage($password, $options)
{
    if (!is_string($password) || strlen($password) > 72 || !admin_password_storage_is_ready($options)) {
        return false;
    }

    $hash = password_hash($password, PASSWORD_DEFAULT);
    return is_string($hash) && strlen($hash) <= 255 ? $hash : false;
}

function admin_password_fingerprint($storedPassword)
{
    return is_string($storedPassword) ? hash('sha256', $storedPassword) : '';
}

function admin_auth_session_start($username, $storedPassword, $accessLevel)
{
    if (session_status() !== PHP_SESSION_ACTIVE
        || !is_string($username)
        || !is_string($storedPassword)
        || !session_regenerate_id(true)) {
        return false;
    }

    unset(
        $_SESSION['password'],
        $_SESSION['authpassword'],
        $_SESSION['authsavepass'],
        $_SESSION['admin_csrf'],
        $_SESSION['heatmap_admin_csrf'],
        $_SESSION['heatmap_admin_preview']
    );

    $_SESSION['loggedin'] = 1;
    $_SESSION['username'] = $username;
    $_SESSION['authsessionStart'] = time();
    $_SESSION['acclevel'] = (int) $accessLevel;
    $_SESSION['auth_password_fingerprint'] = admin_password_fingerprint($storedPassword);

    return true;
}

function admin_auth_session_is_current($username, $storedPassword, $now = null)
{
    if (session_status() !== PHP_SESSION_ACTIVE || !is_string($username) || !is_string($storedPassword)) {
        return false;
    }

    $now = $now === null ? time() : (int) $now;
    $sessionUsername = $_SESSION['username'] ?? null;
    $sessionStarted = (int) ($_SESSION['authsessionStart'] ?? 0);
    $fingerprint = $_SESSION['auth_password_fingerprint'] ?? null;

    if (empty($_SESSION['loggedin'])
        || !is_string($sessionUsername)
        || !hash_equals($username, $sessionUsername)
        || $sessionStarted < 1
        || $sessionStarted > $now + 60
        || $sessionStarted <= $now - 3600
        || !is_string($fingerprint)) {
        return false;
    }

    return hash_equals(admin_password_fingerprint($storedPassword), $fingerprint);
}

function admin_auth_session_validate_current_user($db)
{
    if (session_status() !== PHP_SESSION_ACTIVE || empty($_SESSION['loggedin'])) {
        return false;
    }

    $username = admin_request_scalar_string($_SESSION['username'] ?? null);
    if ($username === '') {
        admin_auth_session_revoke();
        return false;
    }

    $escapedUsername = $db->escape($username);
    $result = $db->query(
        "SELECT password, acclevel FROM hlstats_Users WHERE username = '$escapedUsername' LIMIT 1",
        false
    );
    if (!$result || $db->num_rows($result) != 1) {
        if ($result) {
            $db->free_result($result);
        }
        admin_auth_session_revoke();
        return false;
    }

    $user = $db->fetch_array($result);
    $db->free_result($result);
    if (!is_array($user)
        || !is_string($user['password'] ?? null)
        || !admin_auth_session_is_current($username, $user['password'])) {
        admin_auth_session_revoke();
        return false;
    }

    $_SESSION['acclevel'] = (int) ($user['acclevel'] ?? 0);
    return $user;
}

function admin_auth_session_revoke()
{
    unset(
        $_SESSION['loggedin'],
        $_SESSION['username'],
        $_SESSION['password'],
        $_SESSION['authpassword'],
        $_SESSION['authsavepass'],
        $_SESSION['authsessionStart'],
        $_SESSION['acclevel'],
        $_SESSION['auth_password_fingerprint'],
        $_SESSION['admin_csrf'],
        $_SESSION['heatmap_admin_csrf'],
        $_SESSION['heatmap_admin_preview']
    );

    if (session_status() === PHP_SESSION_ACTIVE && !headers_sent()) {
        session_regenerate_id(true);
    }
}

function admin_csrf_token()
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        throw new RuntimeException('admin_session_unavailable');
    }

    $token = $_SESSION['admin_csrf'] ?? null;
    if (is_string($token) && preg_match('/\A[a-f0-9]{64}\z/D', $token) === 1) {
        return $token;
    }

    $token = bin2hex(random_bytes(32));
    $_SESSION['admin_csrf'] = $token;
    return $token;
}

function admin_csrf_is_valid($providedToken)
{
    return is_string($providedToken) && hash_equals(admin_csrf_token(), $providedToken);
}

function admin_csrf_rejection_required($requestMethod, $providedToken, $loginRequestConsumed = false)
{
    return !$loginRequestConsumed
        && $requestMethod === 'POST'
        && !admin_csrf_is_valid($providedToken);
}

function admin_csrf_field()
{
    return '<input type="hidden" name="csrf_token" value="'
        . htmlspecialchars(admin_csrf_token(), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')
        . '" />';
}

function admin_task_access_allowed($accessLevel, $requiredAccessLevel)
{
    return (int) $accessLevel >= (int) $requiredAccessLevel;
}
