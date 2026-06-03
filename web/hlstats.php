<?php
/*
HLstatsX Community Edition - Real-time player and clan rankings and statistics
Copyleft (L) 2008-20XX Nicholas Hastings (nshastings@gmail.com)
http://www.hlxcommunity.com

HLstatsX Community Edition is a continuation of 
ELstatsNEO - Real-time player and clan rankings and statistics
Copyleft (L) 2008-20XX Malte Bayer (steam@neo-soft.org)
http://ovrsized.neo-soft.org/

ELstatsNEO is an very improved & enhanced - so called Ultra-Humongus Edition of HLstatsX
HLstatsX - Real-time player and clan rankings and statistics for Half-Life 2
http://www.hlstatsx.com/
Copyright (C) 2005-2007 Tobias Oetzel (Tobi@hlstatsx.com)

HLstatsX is an enhanced version of HLstats made by Simon Garner
HLstats - Real-time player and clan rankings and statistics for Half-Life
http://sourceforge.net/projects/hlstats/
Copyright (C) 2001  Simon Garner
            
This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

For support and installation notes visit http://www.hlxcommunity.com
*/

define('IN_HLSTATS', true);
require('config.php');
require(INCLUDE_PATH . '/i18n.php');

define('TITLE_IMAGE', IMAGE_PATH . "/downarrow.gif");

session_start();
init_i18n();

if (!empty($_GET['logout']) && $_GET['logout'] == '1') {
	unset($_SESSION['loggedin']);
	header('Location: ' . lang_url(current_lang(), array('logout', '_smoke')));
	die;
}

$historical_cache = 0;
if (defined('HISTORICAL_CACHE'))
{
	$historical_cache = constant('HISTORICAL_CACHE');
}

if ($historical_cache == 1)
{
	$cacheRequest = $_GET + $_POST;
	$cacheTarget = i18n_historical_cache_target($cacheRequest, current_lang());
	$cachetarget = $cacheTarget['path'];

	@mkdir("cache/{$cacheTarget['dir1']}");
	@mkdir("cache/{$cacheTarget['dir1']}/{$cacheTarget['dir2']}");

	if (file_exists($cachetarget))
	{
		file_put_contents("cache/cachehit", $cachetarget . "\n", FILE_APPEND);
		echo file_get_contents($cachetarget);
		die;
	}
}

// Several stuff added by Malte Bayer
global $scripttime, $siteurlneo;
$scripttime = microtime(true);
$siteurlneo='http://'.$_SERVER['HTTP_HOST'].substr($_SERVER['PHP_SELF'],0,strpos($_SERVER['PHP_SELF'],strrchr($_SERVER['PHP_SELF'],'/'))+1);
$siteurlneo=str_replace('\\','/',$siteurlneo);

// Several Stuff end

foreach ($_SERVER as $key => $entry) {
	if ($key !== 'HTTP_COOKIE') {
		if (is_array($entry) || is_object($entry)) {
			$_SERVER[$key] = '';
			continue;
		}

		$entry = preg_replace('/<script\b[^>]*>.*?<\/script>/isu', '', (string) $entry);
		$entry = preg_replace('/[^\p{L}\p{N}.\-\/=:;_?#&~]/u', '', $entry);
  
		if ($key == "PHP_SELF") {
			if ((strrchr($entry, '/') !== '/hlstats.php') &&
				(strrchr($entry, '/') !== '/ingame.php') &&
				(strrchr($entry, '/') !== '/show_graph.php') &&
				(strrchr($entry, '/') !== '/sig.php') &&
				(strrchr($entry, '/') !== '/sig2.php') &&
				(strrchr($entry, '/') !== '/index.php') &&
				(strrchr($entry, '/') !== '/status.php') &&
				(strrchr($entry, '/') !== '/top10.php') &&
				(strrchr($entry, '/') !== '/config.php') &&
				(strrchr($entry, '/') !== '/') &&
				($entry !== '')) {
				header("Location: http://$siteurlneo/hlstats.php");    
				exit;
			}    
		}
		$_SERVER[$key] = $entry;
	}
}

@header('Content-Type: text/html; charset=utf-8');

// do not report NOTICE warnings
@error_reporting(E_ALL ^ E_NOTICE);

////
//// Initialisation
////

define('PAGE', 'HLSTATS');

///
/// Classes
///

// Load required files
require(INCLUDE_PATH . '/class_db.php');
require(INCLUDE_PATH . '/class_table.php');
require(INCLUDE_PATH . '/functions.php');

$db_classname = 'DB_' . DB_TYPE;
if ( class_exists($db_classname) )
{
	$db = new $db_classname(DB_ADDR, DB_USER, DB_PASS, DB_NAME, DB_PCONNECT);
}
else
{
	error('Database class does not exist.  Please check your config.php file for DB_TYPE');
}

$container = require ROOT_PATH . '/bootstrap.php';
$optionService = $container->get(\Service\OptionService::class);

$g_options = $optionService->getAllOptions();
if (empty($g_options)) {
	error('Warning: Could not find any options in the database. Check HLStats configuration.');
}

$cacheCleaner = $container->get(\Cache\CacheCleaner::class);
$deleteFiles = $cacheCleaner->cleanOldTrendCache(
	null,
	TREND_CACHE_STORAGE_TIME,
	TREND_CACHE_MAX_FILES_PER_PLAYER
);

////
//// Main
////

$game = valid_request(isset($_GET['game']) ? $_GET['game'] : '', false);

$realgame = $_SESSION['realgame'] ?? null;

if (!$game)
{
	$game = isset($_SESSION['game'])?$_SESSION['game']:'';
}
else
{
	if (isset($_SESSION['game']) && $_SESSION['game'] !== $game) {
		unset($_SESSION['realgame']);
		$realgame = null;
	}
	$_SESSION['game'] = $game;
}

if (!$realgame && $game)
{
	$gameRepo = $container->get(\Repository\GameRepository::class);
	$realgame = $gameRepo->getGameByCode($game, 'realgame');

	$_SESSION['realgame'] = $realgame;
}

$mode = isset($_GET['mode']) ? $_GET['mode'] : '';

$valid_modes = array(
	'players',
	'clans',
	'weapons',
	'roles',
	'rolesinfo',
	'maps',
	'actions',
	'claninfo',
	'playerinfo',
	'weaponinfo',
	'mapinfo',
	'actioninfo',
	'playerhistory',
	'playersessions',
	'playerawards',
	'search',
	'admin',
	'help',
	'bans',
	'servers',
	'chathistory',
	'ranks',
	'rankinfo',
	'ribbons',
	'ribboninfo',
	'chat',
	'globalawards',
	'awards',
	'dailyawardinfo',
	'countryclans',
	'countryclansinfo',
	'teamspeak',
	'ventrilo',
	'updater',
	'profile'
);
   
if (file_exists('./updater') && $mode != 'updater')
{
	pageHeader(array(t('ui.updater.notice_title')), array(t('ui.updater.notice_title') => ''));
	echo "<div class=\"warning\">\n" . 
	"<span class=\"warning-heading\"><img src=\"".IMAGE_PATH."/warning.gif\" alt=\"".eHtml(t('ui.warning'))."\"> " . eHtml(t('ui.warning')) . ":</span><br />\n" .
	"<span class=\"warning-text\">" . eHtml(t('ui.updater.detected')) . "<br />" .
	eHtml(t('ui.updater.perform')) . " <strong><a href=\"{$g_options['scripturl']}?mode=updater\">" . eHtml(t('ui.updater.link')) . "</a></strong>.<br /><br />" .
	"<strong>" . eHtml(t('ui.updater.cleanup')) . "</strong></span>\n</div>";
	pageFooter();
	die();
}
   
if ( !in_array($mode, $valid_modes) )
{
	$mode = 'contents';
}

if ( file_exists(PAGE_PATH . "/$mode.php") )
{
	@include(PAGE_PATH . "/$mode.php");
	pageFooter();
}
else
{
	header('HTTP/1.1 404 File Not Found', false, 404);
	error('Unable to find ' . PAGE_PATH . "/$mode.php");
	pageFooter();
}

?>


