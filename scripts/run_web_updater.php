<?php
/* Run database migrations through the trusted command-line path only. */

if (PHP_SAPI !== 'cli') {
    fwrite(STDERR, "This updater can only run from the command line.\n");
    exit(1);
}

$repositoryRoot = dirname(__DIR__);
$webRoot = $repositoryRoot . DIRECTORY_SEPARATOR . 'web';
if (!is_file($webRoot . DIRECTORY_SEPARATOR . 'hlstats.php') && is_file('/var/www/html/hlstats.php')) {
    $webRoot = '/var/www/html';
}
$requiredPaths = array(
    $webRoot . DIRECTORY_SEPARATOR . 'hlstats.php',
    $webRoot . DIRECTORY_SEPARATOR . 'pages' . DIRECTORY_SEPARATOR . 'updater.php',
    $webRoot . DIRECTORY_SEPARATOR . 'updater' . DIRECTORY_SEPARATOR . '83.php',
    $repositoryRoot . DIRECTORY_SEPARATOR . 'sql' . DIRECTORY_SEPARATOR . 'migrations' . DIRECTORY_SEPARATOR . '2026_07_22_ftp_checkpoint.sql',
    $repositoryRoot . DIRECTORY_SEPARATOR . 'sql' . DIRECTORY_SEPARATOR . 'migrations' . DIRECTORY_SEPARATOR . '2026_07_22_0500.sql',
);

foreach ($requiredPaths as $path) {
    if (!file_exists($path)) {
        fwrite(STDERR, "Updater files are missing: $path\n");
        exit(1);
    }
}

if (($argv[1] ?? '') === '--check' && $argc === 2) {
    fwrite(STDOUT, "Trusted web updater entrypoint is available.\n");
    exit(0);
}

if ($argc !== 1) {
    fwrite(STDERR, "Usage: php scripts/run_web_updater.php [--check]\n");
    exit(1);
}

define('HLSTATS_TRUSTED_UPDATER', true);
$_GET = array('mode' => 'updater');
$_POST = array();
$_REQUEST = $_GET;
$_SERVER['HTTP_HOST'] = 'localhost';
$_SERVER['SERVER_NAME'] = 'localhost';
$_SERVER['SERVER_PORT'] = '80';
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['REQUEST_URI'] = '/hlstats.php?mode=updater';
$_SERVER['QUERY_STRING'] = 'mode=updater';
$_SERVER['SCRIPT_NAME'] = '/hlstats.php';
$_SERVER['PHP_SELF'] = '/hlstats.php';
chdir($webRoot);

$hlstatsTrustedUpdaterCompleted = false;
register_shutdown_function(static function () use (&$hlstatsTrustedUpdaterCompleted): void {
    // Legacy error handlers can call bare exit; exceptions cannot intercept it.
    if (!$hlstatsTrustedUpdaterCompleted) {
        fwrite(STDERR, "Trusted web updater stopped before verified completion.\n");
        exit(1);
    }
});

function trusted_web_updater_read_password_capacity($pdo): int
{
    $statement = $pdo->query("SHOW COLUMNS FROM `hlstats_Users` LIKE 'password'");
    if ($statement === false) {
        throw new RuntimeException('could not inspect administrator password storage');
    }

    $column = $statement->fetch(PDO::FETCH_ASSOC);
    $type = is_array($column) ? ($column['Type'] ?? null) : null;
    if (!is_string($type) || preg_match('/\Avarchar\(([1-9][0-9]*)\)\z/iD', $type, $matches) !== 1) {
        throw new RuntimeException('administrator password storage is incompatible');
    }

    return (int) $matches[1];
}

function trusted_web_updater_ensure_password_capacity($pdo): array
{
    $initialCapacity = trusted_web_updater_read_password_capacity($pdo);
    if ($initialCapacity >= 255) {
        return array('capacity' => $initialCapacity, 'repaired' => false);
    }

    $altered = $pdo->exec("ALTER TABLE `hlstats_Users` MODIFY COLUMN `password` varchar(255) NOT NULL default ''");
    if ($altered === false) {
        throw new RuntimeException('could not widen administrator password storage');
    }

    $capacity = trusted_web_updater_read_password_capacity($pdo);
    if ($capacity < 255) {
        throw new RuntimeException('administrator password storage remains too narrow after repair');
    }

    return array('capacity' => $capacity, 'repaired' => true, 'initialCapacity' => $initialCapacity);
}

try {
    require $webRoot . DIRECTORY_SEPARATOR . 'hlstats.php';
} catch (Throwable $exception) {
    fwrite(STDERR, "Trusted web updater failed: " . $exception->getMessage() . "\n");
    exit(1);
}

if (!isset($container) || !is_object($container) || !method_exists($container, 'get')) {
    fwrite(STDERR, "Trusted web updater failed: application bootstrap did not expose a database connection.\n");
    exit(1);
}

try {
    $pdo = $container->get('pdo');
    $statement = $pdo->prepare('SELECT `value` FROM hlstats_Options WHERE `keyname` = :keyname');
    if ($statement === false || $statement->execute(array('keyname' => 'dbversion')) !== true) {
        throw new RuntimeException('could not read the resulting database version');
    }
    $databaseVersion = $statement->fetchColumn();
} catch (Throwable $exception) {
    fwrite(STDERR, "Trusted web updater failed: " . $exception->getMessage() . "\n");
    exit(1);
}

if (!is_scalar($databaseVersion) || preg_match('/^[0-9]+$/', (string) $databaseVersion) !== 1 || (int) $databaseVersion < 83) {
    fwrite(STDERR, "Trusted web updater failed: database version did not reach 83.\n");
    exit(1);
}

$passwordStorage = null;
try {
    $passwordStorage = trusted_web_updater_ensure_password_capacity($pdo);
} catch (Throwable $exception) {
    fwrite(STDERR, "Trusted web updater failed: " . $exception->getMessage() . "\n");
    exit(1);
}

if ($passwordStorage['repaired']) {
    fwrite(
        STDOUT,
        "Trusted web updater widened administrator password storage from "
            . $passwordStorage['initialCapacity'] . " to " . $passwordStorage['capacity'] . ".\n"
    );
}

$hlstatsTrustedUpdaterCompleted = true;
fwrite(
    STDOUT,
    "Trusted web updater completed at database version " . $databaseVersion
        . " with administrator password capacity " . $passwordStorage['capacity'] . ".\n"
);
