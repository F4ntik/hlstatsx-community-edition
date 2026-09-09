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
chdir($webRoot);
require $webRoot . DIRECTORY_SEPARATOR . 'hlstats.php';
