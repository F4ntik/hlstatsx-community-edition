<?php

declare(strict_types=1);

define('IN_HLSTATS', true);
define('ROOT_PATH', dirname(__DIR__) . '/web');

require ROOT_PATH . '/includes/admin_security.php';

function assert_same($expected, $actual, string $message): void
{
    if ($expected !== $actual) {
        fwrite(STDERR, $message . PHP_EOL);
        fwrite(STDERR, 'Expected: ' . var_export($expected, true) . PHP_EOL);
        fwrite(STDERR, 'Actual: ' . var_export($actual, true) . PHP_EOL);
        exit(1);
    }
}

function assert_true($actual, string $message): void
{
    assert_same(true, $actual === true, $message);
}

function assert_false($actual, string $message): void
{
    assert_same(true, $actual === false, $message);
}

function assert_contains(string $needle, string $haystack, string $message): void
{
    assert_true(strpos($haystack, $needle) !== false, $message);
}

function source_between(string $source, string $start, string $end, string $message): string
{
    $startPosition = strpos($source, $start);
    $endPosition = $startPosition === false ? false : strpos($source, $end, $startPosition);
    assert_true($startPosition !== false && $endPosition !== false, $message);
    return substr($source, $startPosition, $endPosition - $startPosition);
}

function run_updater_runner_subprocess(string $runnerPath, string $workingDirectory, ?string $databaseVersion): array
{
    $environmentKey = 'HLSTATS_UPDATER_SMOKE_DBVERSION';
    $previousValue = getenv($environmentKey);
    if ($databaseVersion === null) {
        putenv($environmentKey);
    } else {
        putenv($environmentKey . '=' . $databaseVersion);
    }

    try {
        $process = proc_open(
            escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg($runnerPath),
            array(
                0 => array('pipe', 'r'),
                1 => array('pipe', 'w'),
                2 => array('pipe', 'w'),
            ),
            $pipes,
            $workingDirectory
        );
        if (!is_resource($process)) {
            throw new RuntimeException('could not start trusted updater runner smoke');
        }

        fclose($pipes[0]);
        $stdout = stream_get_contents($pipes[1]);
        $stderr = stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);

        return array(
            'exitCode' => proc_close($process),
            'stdout' => $stdout,
            'stderr' => $stderr,
        );
    } finally {
        if ($previousValue === false) {
            putenv($environmentKey);
        } else {
            putenv($environmentKey . '=' . $previousValue);
        }
    }
}

function remove_updater_runner_smoke_tree(string $path): void
{
    $resolvedPath = realpath($path);
    $tempPrefix = rtrim(str_replace('\\', '/', sys_get_temp_dir()), '/') . '/hlstats-updater-runner-smoke-';
    $normalizedPath = $resolvedPath === false ? '' : str_replace('\\', '/', $resolvedPath);
    if ($normalizedPath === '' || strpos($normalizedPath, $tempPrefix) !== 0) {
        throw new RuntimeException('refusing to remove an unexpected updater smoke path');
    }

    $iterator = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator($resolvedPath, FilesystemIterator::SKIP_DOTS),
        RecursiveIteratorIterator::CHILD_FIRST
    );
    foreach ($iterator as $entry) {
        if ($entry->isDir()) {
            rmdir($entry->getPathname());
        } else {
            unlink($entry->getPathname());
        }
    }
    rmdir($resolvedPath);
}

function t($key, $params = array(), $fallback = null)
{
    return $fallback === null ? $key : $fallback;
}

function valid_request($value, $numeric = false)
{
    return $numeric ? (string) (int) $value : htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

final class AdminSecurityFakeDb
{
    public array $user;
    public int $writeQueries = 0;
    private $lastResult = false;

    public function __construct(array $user)
    {
        $this->user = $user;
    }

    public function escape($value): string
    {
        return addslashes((string) $value);
    }

    public function query($query, $showError = true)
    {
        if (preg_match('/^\\s*SELECT\\b/i', (string) $query) === 1) {
            $this->lastResult = 'user';
            return 'user';
        }

        if (preg_match('/^\\s*UPDATE\\s+hlstats_Users\\b/i', (string) $query) === 1) {
            if (preg_match("/SET\\s+password\\s*=\\s*'((?:\\\\.|[^'])*)'/is", (string) $query, $matches) !== 1) {
                return false;
            }
            $this->user['password'] = stripslashes($matches[1]);
            $this->writeQueries++;
            return true;
        }

        return false;
    }

    public function num_rows($result): int
    {
        return $result === 'user' ? 1 : 0;
    }

    public function fetch_array($result): array
    {
        return $this->user;
    }

    public function free_result($result): void
    {
    }
}

function exercise_admin_dispatcher_gate(string $method, $csrfToken, bool $loginRequestConsumed, callable $mutation): int
{
    if (admin_csrf_rejection_required($method, $csrfToken, $loginRequestConsumed)) {
        return 403;
    }

    $mutation();
    return 200;
}

$adminSource = file_get_contents(ROOT_PATH . '/pages/admin.php');
$heatmapSource = file_get_contents(ROOT_PATH . '/heatmap_admin.php');
$hlstatsSource = file_get_contents(ROOT_PATH . '/hlstats.php');
$updaterSource = file_get_contents(ROOT_PATH . '/pages/updater.php');
$installSource = file_get_contents(dirname(ROOT_PATH) . '/sql/install.sql');
$updaterRunnerSource = file_get_contents(dirname(ROOT_PATH) . '/scripts/run_web_updater.php');
assert_true(is_string($adminSource) && is_string($heatmapSource) && is_string($hlstatsSource), 'security sources should be readable');

$authSource = source_between($adminSource, 'class Auth', 'class AdminTask', 'Auth class should be extractable for its request lifecycle test');
eval($authSource);
$heatmapSessionSource = source_between($heatmapSource, 'function heatmap_admin_session_matches_user', 'function heatmap_admin_current_user', 'heatmap session boundary should be extractable');
eval($heatmapSessionSource);

$csrfGatePosition = strpos($adminSource, 'admin_csrf_rejection_required(');
$pageHeaderPosition = strpos($adminSource, 'pageHeader(');
$taskIncludePosition = strpos($adminSource, 'include (PAGE_PATH . "/admintasks/$code.php");');
assert_true(
    $csrfGatePosition !== false && $pageHeaderPosition !== false && $taskIncludePosition !== false
        && $csrfGatePosition < $pageHeaderPosition && $csrfGatePosition < $taskIncludePosition,
    'the CSRF rejection must be decided before page output or task inclusion'
);
assert_contains("new AdminTask(t('admin.task.tools_reset.title'), 100", $adminSource, 'primary reset task must require level 100');
assert_contains("new AdminTask(t('admin.task.tools_reset_2.title'), 100", $adminSource, 'secondary reset task must require level 100');
assert_true(admin_task_access_allowed(100, 100), 'level 100 should pass a level 100 task');
assert_false(admin_task_access_allowed(80, 100), 'level 80 should not pass a level 100 task');

foreach (array('tools_reset.php', 'tools_reset_2.php', 'tools_resetdbcollations.php') as $resetFile) {
    $resetSource = file_get_contents(ROOT_PATH . '/pages/admintasks/' . $resetFile);
    assert_true(is_string($resetSource), $resetFile . ' should be readable');
    assert_true(preg_match('/acclevel[\'\"]\\]\\s*<\\s*100/', $resetSource) === 1, $resetFile . ' must retain a local level 100 guard');
    assert_contains('admin_csrf_field();', $resetSource, $resetFile . ' must render a CSRF token');
}

foreach (array(
    'pages/adminauth.php',
    'pages/admin.php',
    'pages/header.php',
    'pages/admintasks/tools_optimize.php',
    'pages/admintasks/tools_runtimecontrol.php',
    'pages/admintasks/tools_settings_copy.php',
    'pages/admintasks/tools_synchronize.php',
    'pages/admintasks/tools_editdetails_player.php',
    'pages/admintasks/tools_editdetails_clan.php',
) as $formFile) {
    $formSource = file_get_contents(ROOT_PATH . '/' . $formFile);
    assert_true(is_string($formSource), $formFile . ' should be readable');
    assert_contains('admin_csrf_field', $formSource, $formFile . ' must render a CSRF token');
}

assert_contains('($_SERVER[\'REQUEST_METHOD\'] ?? \'\') !== \'POST\' || !isset($_POST[\'confirm\'])', file_get_contents(ROOT_PATH . '/pages/admintasks/tools_optimize.php'), 'GET optimize requests must only show confirmation');
assert_contains('DROP TEMPORARY TABLE IF EXISTS hlstats_AdminEventHistory', file_get_contents(ROOT_PATH . '/pages/admintasks/tools_adminevents.php'), 'the GET event-history report must not drop a persistent table');
assert_contains("PHP_SAPI !== 'cli' || !defined('HLSTATS_TRUSTED_UPDATER')", $hlstatsSource, 'the public dispatcher must reject updater requests');
assert_contains("PHP_SAPI !== 'cli' || !defined('HLSTATS_TRUSTED_UPDATER')", $updaterSource, 'the updater page must independently require the trusted CLI route');
$databaseBootstrapPosition = strpos($hlstatsSource, '$db = new $db_classname');
$publicSessionValidationPosition = strpos($hlstatsSource, 'admin_auth_session_validate_current_user($db);');
$modeDispatchPosition = strpos($hlstatsSource, '$valid_modes = array(');
assert_true(
    $databaseBootstrapPosition !== false
        && $publicSessionValidationPosition !== false
        && $modeDispatchPosition !== false
        && $databaseBootstrapPosition < $publicSessionValidationPosition
        && $publicSessionValidationPosition < $modeDispatchPosition,
    'the public dispatcher must validate an authenticated session after database bootstrap and before route dispatch'
);
assert_contains('admin_auth_session_validate_current_user($db)', $authSource, 'the admin route must reuse the shared database-backed session validation');
assert_contains('`password` varchar(255)', $installSource, 'new installs must reserve full modern password storage');
$updater83Source = file_get_contents(ROOT_PATH . '/updater/83.php');
assert_contains('MODIFY COLUMN password varchar(255)', $updater83Source, 'the explicit updater must widen old password storage');
assert_contains('throw new RuntimeException', $updater83Source, 'the explicit updater must fail with a nonzero CLI status when a database write fails');
assert_contains("is_file('/var/www/html/hlstats.php')", $updaterRunnerSource, 'the updater runner must support the Docker web-root layout');
assert_contains('$_SERVER[\'PHP_SELF\'] = \'/hlstats.php\';', $updaterRunnerSource, 'the updater runner must use the canonical dispatcher path');
assert_contains('$_SERVER[\'HTTP_HOST\'] = \'localhost\';', $updaterRunnerSource, 'the updater runner must supply a trusted CLI host context');
assert_contains('database version did not reach 83', $updaterRunnerSource, 'the updater runner must verify migration completion');

$enCatalog = require ROOT_PATH . '/lang/en.php';
$ruCatalog = require ROOT_PATH . '/lang/ru.php';
foreach (array('admin.csrf_invalid', 'admin.password_upgrade_failed', 'admin.password_storage_upgrade_required', 'updater.cli_only') as $key) {
    assert_true(isset($enCatalog['messages'][$key]) && $enCatalog['messages'][$key] !== '', 'English should contain ' . $key);
    assert_true(isset($ruCatalog['messages'][$key]) && $ruCatalog['messages'][$key] !== '', 'Russian should contain ' . $key);
}

if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}

$g_options = array('dbversion' => 83);
$specialPassword = "Sp&c!al <pass> ' \" ; = Ё";
$modernHash = admin_password_hash_for_storage($specialPassword, $g_options);
assert_true(is_string($modernHash), 'modern storage should accept special-character passwords');
assert_true(admin_password_verify_value($specialPassword, $modernHash), 'modern password verification should preserve opaque special characters');

$db = new AdminSecurityFakeDb(array(
    'username' => 'admin',
    'password' => $modernHash,
    'acclevel' => 100,
    'playerId' => 0,
));
$_SESSION = array();
$_SESSION['heatmap_admin_preview'] = 'stale-preview';
$originalSessionId = session_id();
$_SERVER = array('REQUEST_METHOD' => 'POST');
$_POST = array(
    'authusername' => 'admin',
    'authpassword' => $specialPassword,
    'csrf_token' => admin_csrf_token(),
    'task' => 'tools_reset',
    'confirm' => '1',
);
$auth = new Auth();
assert_true($auth->ok, 'the actual Auth constructor should accept a special-character password');
assert_true($auth->loginRequestConsumed, 'a successful Auth POST must be consumed before task dispatch');
assert_same(array(), $_POST, 'a successful login must clear the request payload before dispatch');
assert_true(session_id() !== $originalSessionId, 'a successful login must rotate the session identifier');
assert_false(isset($_SESSION['password']), 'the session must not retain a plaintext password');
assert_false(isset($_SESSION['heatmap_admin_preview']), 'a successful login must discard any prior admin preview capability');
assert_true(admin_auth_session_is_current('admin', $db->user['password']), 'the fresh session should match the persisted password fingerprint');
assert_true(is_array(admin_auth_session_validate_current_user($db)), 'the public dispatcher should accept a current database-backed session');
assert_same(100, $_SESSION['acclevel'], 'database-backed validation should retain the current access level');

$writesBeforeCsrfReject = $db->writeQueries;
$rejectedStatus = exercise_admin_dispatcher_gate('POST', 'not-a-valid-token', false, function () use ($db): void {
    $db->query("UPDATE hlstats_Users SET password = 'should-not-run'");
});
assert_same(403, $rejectedStatus, 'a bad CSRF token must produce a rejection before mutation');
assert_same($writesBeforeCsrfReject, $db->writeQueries, 'a bad CSRF token must not reach a database write');
assert_same(200, exercise_admin_dispatcher_gate('POST', 'not-a-valid-token', true, static function (): void {}), 'a consumed login POST must not be rejected again by the dispatcher');

assert_false(
    admin_password_verify_value('QNKCDZO', md5('240610708')),
    'legacy MD5 verification must reject the loose-comparison magic-hash pair'
);

admin_auth_session_revoke();
$_SESSION = array();
$db->user['password'] = md5($specialPassword);
$legacySessionId = session_id();
$_SERVER = array('REQUEST_METHOD' => 'POST');
$_POST = array(
    'authusername' => 'admin',
    'authpassword' => $specialPassword,
    'csrf_token' => admin_csrf_token(),
);
$legacyAuth = new Auth();
assert_true($legacyAuth->ok, 'a legacy MD5 account should authenticate once with the correct password');
assert_false(admin_password_uses_legacy_md5($db->user['password']), 'a successful legacy login must upgrade the stored password');
assert_true(admin_password_verify_value($specialPassword, $db->user['password']), 'the upgraded password must keep the original opaque value');
assert_true(session_id() !== $legacySessionId, 'legacy login upgrade must still rotate the session identifier');
assert_true(admin_auth_session_is_current('admin', $db->user['password']), 'the upgraded account should create a valid current session');

$readOnlyHeatmapUser = array('password' => $db->user['password'], 'acclevel' => 80, 'playerId' => 0);
assert_true(
    heatmap_admin_session_matches_user('admin', $readOnlyHeatmapUser),
    'a current password-free session must allow read-only heatmap access without a player binding'
);
assert_false(
    heatmap_admin_session_matches_user('admin', array('password' => admin_password_hash_for_storage('changed password', $g_options))),
    'a password change must invalidate the heatmap session boundary'
);
assert_contains('heatmap_admin_require_access($pdo);', $heatmapSource, 'all heatmap actions must perform a fresh session check after opening the database');
assert_contains('admin_auth_session_revoke();', $heatmapSource, 'invalid heatmap sessions must be revoked');
assert_false(strpos(source_between($heatmapSource, 'function heatmap_admin_actor_id', 'function heatmap_admin_require_actor', 'actor function should be extractable'), '$_SESSION[\'password\']') !== false, 'heatmap actor resolution must not use a plaintext session password');

$changedPasswordHash = admin_password_hash_for_storage('changed password', $g_options);
assert_true(is_string($changedPasswordHash), 'the changed-password regression needs a valid stored hash');
$db->user['password'] = $changedPasswordHash;
assert_false(admin_auth_session_validate_current_user($db), 'a changed database password must revoke public-route access');
assert_false(isset($_SESSION['loggedin']) || isset($_SESSION['acclevel']), 'a changed database password must clear cached public-route authorization');

assert_true(admin_auth_session_start('admin', $db->user['password'], 100), 'the expiry regression should start a fresh session');
$_SESSION['authsessionStart'] = time() - 3600;
assert_false(admin_auth_session_validate_current_user($db), 'an expired session must revoke public-route access');
assert_false(isset($_SESSION['loggedin']) || isset($_SESSION['acclevel']), 'an expired session must clear cached public-route authorization');

assert_true(admin_auth_session_start('admin', $db->user['password'], 100), 'the downgrade regression should start a fresh session');
$db->user['acclevel'] = 20;
assert_true(is_array(admin_auth_session_validate_current_user($db)), 'a current session should refresh its database user record');
assert_same(20, $_SESSION['acclevel'], 'a database privilege downgrade must replace the cached access level');
assert_false(isset($_SESSION['loggedin']) && $_SESSION['acclevel'] >= 80, 'a downgraded user must lose public IP-search authorization');

$_SESSION['authsessionStart'] = time() - 3600;
assert_false(admin_auth_session_is_current('admin', $db->user['password']), 'stale sessions must fail closed');
$_SESSION['authsessionStart'] = time();
assert_false(
    admin_auth_session_is_current('admin', admin_password_hash_for_storage('changed password', $g_options)),
    'a changed persisted password must revoke the old session fingerprint'
);
admin_auth_session_revoke();
assert_false(isset($_SESSION['loggedin']) || isset($_SESSION['auth_password_fingerprint']) || isset($_SESSION['password']) || isset($_SESSION['heatmap_admin_preview']), 'logout/revocation must remove authentication state and preview remnants');

$updaterSmokeRoot = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'hlstats-updater-runner-smoke-' . bin2hex(random_bytes(8));
try {
    assert_true(mkdir($updaterSmokeRoot . '/scripts', 0700, true), 'updater runner smoke scripts directory should be created');
    assert_true(mkdir($updaterSmokeRoot . '/web/pages', 0700, true), 'updater runner smoke pages directory should be created');
    assert_true(mkdir($updaterSmokeRoot . '/web/updater', 0700, true), 'updater runner smoke updater directory should be created');
    assert_true(mkdir($updaterSmokeRoot . '/sql/migrations', 0700, true), 'updater runner smoke migrations directory should be created');
    assert_true(copy(dirname(ROOT_PATH) . '/scripts/run_web_updater.php', $updaterSmokeRoot . '/scripts/run_web_updater.php'), 'updater runner smoke should execute the checked-in runner');
    assert_true(file_put_contents($updaterSmokeRoot . '/web/pages/updater.php', "<?php\n") !== false, 'updater runner smoke updater page should be created');
    assert_true(file_put_contents($updaterSmokeRoot . '/web/updater/83.php', "<?php\n") !== false, 'updater runner smoke migration should be created');
    assert_true(file_put_contents($updaterSmokeRoot . '/sql/migrations/2026_07_22_ftp_checkpoint.sql', "-- smoke\n") !== false, 'updater runner smoke checkpoint should be created');
    assert_true(file_put_contents($updaterSmokeRoot . '/sql/migrations/2026_07_22_0500.sql', "-- smoke\n") !== false, 'updater runner smoke runtime migration should be created');
    assert_true(file_put_contents($updaterSmokeRoot . '/web/hlstats.php', <<<'PHP'
<?php
$expectedServer = array(
    'HTTP_HOST' => 'localhost',
    'REQUEST_METHOD' => 'GET',
    'REQUEST_URI' => '/hlstats.php?mode=updater',
    'QUERY_STRING' => 'mode=updater',
    'SCRIPT_NAME' => '/hlstats.php',
    'PHP_SELF' => '/hlstats.php',
);
foreach ($expectedServer as $key => $value) {
    if (($_SERVER[$key] ?? null) !== $value) {
        fwrite(STDERR, "invalid trusted updater request context: $key\n");
        exit(71);
    }
}
if (($_GET['mode'] ?? null) !== 'updater' || $_POST !== array() || $_REQUEST !== $_GET) {
    fwrite(STDERR, "invalid trusted updater request payload\n");
    exit(72);
}

final class UpdaterRunnerSmokeStatement
{
    private string $databaseVersion;

    public function __construct(string $databaseVersion)
    {
        $this->databaseVersion = $databaseVersion;
    }

    public function execute(array $parameters): bool
    {
        return ($parameters['keyname'] ?? null) === 'dbversion';
    }

    public function fetchColumn(): string
    {
        return $this->databaseVersion;
    }
}

final class UpdaterRunnerSmokePdo
{
    public function prepare(string $query): UpdaterRunnerSmokeStatement
    {
        if (strpos($query, 'hlstats_Options') === false) {
            throw new RuntimeException('unexpected updater completion query');
        }
        $databaseVersion = getenv('HLSTATS_UPDATER_SMOKE_DBVERSION');
        return new UpdaterRunnerSmokeStatement($databaseVersion === false || $databaseVersion === '' ? '83' : $databaseVersion);
    }
}

final class UpdaterRunnerSmokeContainer
{
    public function get(string $service)
    {
        if ($service !== 'pdo') {
            throw new RuntimeException('unexpected updater service');
        }
        return new UpdaterRunnerSmokePdo();
    }
}

$container = new UpdaterRunnerSmokeContainer();
PHP
    ) !== false, 'updater runner smoke dispatcher should be created');

    $successfulRun = run_updater_runner_subprocess($updaterSmokeRoot . '/scripts/run_web_updater.php', $updaterSmokeRoot, null);
    assert_same(0, $successfulRun['exitCode'], 'trusted updater runner must reach the canonical dispatcher route');
    assert_same('', $successfulRun['stderr'], 'trusted updater runner must not emit bootstrap warnings');
    assert_contains('Trusted web updater completed at database version 83.', $successfulRun['stdout'], 'trusted updater runner must report a verified completion');

    $staleRun = run_updater_runner_subprocess($updaterSmokeRoot . '/scripts/run_web_updater.php', $updaterSmokeRoot, '82');
    assert_true($staleRun['exitCode'] !== 0, 'trusted updater runner must fail when the migration remains incomplete');
    assert_contains('database version did not reach 83', $staleRun['stderr'], 'trusted updater runner must explain an incomplete migration');

    assert_true(file_put_contents($updaterSmokeRoot . '/web/hlstats.php', "<?php exit;\n") !== false, 'early-exit dispatcher should be created');
    $earlyExitRun = run_updater_runner_subprocess($updaterSmokeRoot . '/scripts/run_web_updater.php', $updaterSmokeRoot, null);
    assert_same(1, $earlyExitRun['exitCode'], 'legacy bare exit must not report updater success');
    assert_contains('stopped before verified completion', $earlyExitRun['stderr'], 'early exit must explain missing completion');
} finally {
    if (is_dir($updaterSmokeRoot)) {
        remove_updater_runner_smoke_tree($updaterSmokeRoot);
    }
}

echo "web admin security smoke ok\n";
