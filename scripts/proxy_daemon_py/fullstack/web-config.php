<?php
if (!defined('IN_HLSTATS')) {
    die('Do not access this file directly.');
}

error_reporting(E_ALL & ~E_DEPRECATED & ~E_USER_DEPRECATED);

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

// Add a chat delay to prevent real-time tracking and provide information that can help in-game.
// Only allowed from 1 minute to CHAT_DELAY_MAX_TIME, other values disable this.
// Disabled by default.
define('CHAT_DELAY_TIME', 0);
define('CHAT_DELAY_MAX_TIME', 20);

define('ROOT_PATH', __DIR__);

// Maximum storage time for player trend image cache (in seconds).
// Default value: 604800 seconds = 7 days.
define('TREND_CACHE_STORAGE_TIME', 604800);

// The probability of triggering the code to clear the cache of player trend images
// so as not to overload the disk every time you visit the site
// (specified as a percentage from 1 to 100).
define('TREND_CACHE_PROBABILITY', 10); // 10 %

// The largest number of images in the trend cache for 1 player,
// any images above this number will be deleted.
define('TREND_CACHE_MAX_FILES_PER_PLAYER', 5);
?>
