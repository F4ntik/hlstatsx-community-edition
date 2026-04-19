<?php
if (!defined('IN_HLSTATS')) {
    die('Do not access this file directly.');
}

define("DB_ADDR", 'mysql');
define("DB_USER", 'hlstats');
define("DB_PASS", 'hlstats');
define("DB_NAME", 'hlstatsx');
define("DB_TYPE", 'mysql');
define("DB_CHARSET", 'utf8mb4');
define("DB_COLLATE", 'utf8mb4_unicode_ci');
define("DB_PCONNECT", 0);
define("INCLUDE_PATH", './includes');
define("PAGE_PATH", './pages');
define("IMAGE_PATH", './hlstatsimg');
define("IMAGE_UPDATE_INTERVAL", 300);
define('GOOGLE_MAPS_API_KEY', "");
?>
