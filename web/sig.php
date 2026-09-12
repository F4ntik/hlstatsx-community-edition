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

Originally idea for sig.php by Tankster
*/

foreach ($_SERVER as $key => $entry) {
	if ($key !== 'HTTP_COOKIE') {
		if (is_array($entry) || is_object($entry)) {
			$_SERVER[$key] = '';
			continue;
		}

		$entry = preg_replace('/<script\b[^>]*>.*?<\/script>/isu', '', (string) $entry);
		$entry = preg_replace('/[^\p{L}\p{N}.\-\/=:;_?#&~]/u', '', $entry);
  
		if ($key == 'PHP_SELF') {
			if ((strrchr($entry, '/') !== '/hlstats.php') &&
				(strrchr($entry, '/') !== '/show_graph.php') &&
				(strrchr($entry, '/') !== '/sig.php') &&
				(strrchr($entry, '/') !== '/sig2.php') &&
				(strrchr($entry, '/') !== '/index.php') &&
				(strrchr($entry, '/') !== '/status.php') &&
				(strrchr($entry, '/') !== '/top10.php') &&
				(strrchr($entry, '/') !== '/config.php') &&
				(strrchr($entry, '/') !== '/') &&
				($entry !== '')) {
				header('Location: http://'.$_SERVER['HTTP_HOST'].'/hlstats.php');    
				exit;
			}    
		}
		$_SERVER[$key] = $entry;
	}
}
  
define('IN_HLSTATS', true);

// Load database classes
require ('config.php');
require (INCLUDE_PATH . '/i18n.php');

session_start();
init_i18n();

header("Content-Type: image/png");

require (INCLUDE_PATH . '/class_db.php');
require (INCLUDE_PATH . '/functions.php');

$container = require ROOT_PATH . '/bootstrap.php';
$playerRepo = $container->get(\Repository\PlayerRepository::class);
$optionService = $container->get(\Service\OptionService::class);

$db_classname = 'DB_' . DB_TYPE;
if (class_exists($db_classname))
{
	$db = new $db_classname(DB_ADDR, DB_USER, DB_PASS, DB_NAME, DB_PCONNECT);
}
else
{
	error(localized_text('error.database_class_missing'));
}

$g_options = $optionService->getAllOptions();
if (empty($g_options)) {
	error(localized_text('error.options_missing'));
}

@error_reporting(E_ALL ^ E_NOTICE);

function imagecopymerge_alpha($dst_im, $src_im, $dst_x, $dst_y, $src_x, $src_y, $src_w, $src_h, $pct){
	$opacity=$pct;
	// getting the watermark width
	$w = imagesx($src_im);
	// getting the watermark height
	$h = imagesy($src_im);
	 
	// creating a cut resource
	$cut = imagecreatetruecolor($src_w, $src_h);
	// copying that section of the background to the cut
	imagecopy($cut, $dst_im, 0, 0, $dst_x, $dst_y, $src_w, $src_h);
	// inverting the opacity
	$opacity = 100 - $opacity;
	 
	// placing the watermark now
	imagecopy($cut, $src_im, 0, 0, $src_x, $src_y, $src_w, $src_h);
	imagecopymerge($dst_im, $cut, $dst_x, $dst_y, $src_x, $src_y, $src_w, $src_h, $opacity);
}

function sig_utf8_length($text)
{
	$text = (string) $text;
	if (function_exists('mb_strlen')) {
		return mb_strlen($text, 'UTF-8');
	}

	$characters = preg_split('//u', $text, -1, PREG_SPLIT_NO_EMPTY);
	return $characters === false ? strlen($text) : count($characters);
}

function sig_utf8_prefix($text, $length)
{
	$text = (string) $text;
	if (function_exists('mb_substr')) {
		return mb_substr($text, 0, $length, 'UTF-8');
	}

	$characters = preg_split('//u', $text, -1, PREG_SPLIT_NO_EMPTY);
	if ($characters === false) {
		return substr($text, 0, $length);
	}

	return implode('', array_slice($characters, 0, $length));
}

function sig_ascii_text($text)
{
	$text = (string) $text;
	if (function_exists('iconv')) {
		$converted = @iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $text);
		if ($converted !== false) {
			$text = $converted;
		}
	}

	$ascii = preg_replace('/[^\x20-\x7E]/', '?', $text);
	return $ascii === null ? '' : $ascii;
}

function sig_ttf_width($font, $size, $text)
{
	$box = imagettfbbox($size, 0, $font, (string) $text);
	return $box === false ? 0 : abs($box[2] - $box[0]);
}

function sig_fit_ttf_text($font, $size, $text, $max_width)
{
	$text = (string) $text;
	if ($max_width <= 0 || sig_ttf_width($font, $size, $text) <= $max_width) {
		return $max_width <= 0 ? '' : $text;
	}

	$ellipsis = '...';
	$length = sig_utf8_length($text);
	while ($length > 0) {
		$candidate = sig_utf8_prefix($text, $length) . $ellipsis;
		if (sig_ttf_width($font, $size, $candidate) <= $max_width) {
			return $candidate;
		}
		$length--;
	}

	return sig_ttf_width($font, $size, $ellipsis) <= $max_width ? $ellipsis : '';
}

function sig_draw_ttf_fit($image, $font, $text, $x, $baseline, $color, $size, $min_size, $max_width)
{
	$draw_size = (float) $size;
	$min_size = (float) $min_size;
	while ($draw_size > $min_size && sig_ttf_width($font, $draw_size, $text) > $max_width) {
		$draw_size -= 0.25;
	}

	$fitted = sig_fit_ttf_text($font, $draw_size, $text, $max_width);
	if ($fitted === '') {
		return 0;
	}

	$box = imagettftext($image, $draw_size, 0, $x, $baseline, $color, $font, $fitted);
	return $box === false ? 0 : abs($box[2] - $box[0]);
}

function sig_fit_bitmap_text($font, $text, $max_width)
{
	$text = sig_ascii_text($text);
	$char_width = imagefontwidth($font);
	$max_chars = $char_width > 0 ? (int) floor($max_width / $char_width) : 0;
	if ($max_chars <= 0) {
		return '';
	}
	if (strlen($text) <= $max_chars) {
		return $text;
	}
	if ($max_chars <= 3) {
		return substr($text, 0, $max_chars);
	}

	return substr($text, 0, $max_chars - 3) . '...';
}

function f_num($number) {
	if (($number >= 10) &&($number < 20))
		return $number.'th';
	else {
		switch ($number % 10) {
			case 1:
				return $number.'st';
				break;
			case 2:
				return $number.'nd';
				break;
			case 3:
				return $number.'rd';
				break;
			default:
				return $number.'th';
				break;
		}
	}
}

	$player_id = 0;
	$realgame = '';
	if (isset($_GET['player_id'])) {
		$player_id = valid_request($_GET['player_id'], true);
	} elseif (isset($_GET['steam_id']) && isset($_GET['game'])) {
		$steam_id = valid_request($_GET['steam_id'], false);
		$steam_id = preg_replace('/^STEAM_\d+?\:/i','',$steam_id);
		$game = valid_request($_GET['game'], false);

		$steam_id_escaped=$db->escape($steam_id);
		$game_escaped=$db->escape($game);
		
		// Obtain realgame from hlstats_Games
		$db->query("
			SELECT
				realgame
			FROM
				hlstats_Games
			WHERE
				code = '$game_escaped'
		");
		$realgame = $db->fetch_row();
		
		// Obtain player_id from the steam_id and game code
		$db->query("
			SELECT
				playerId
			FROM
				hlstats_PlayerUniqueIds
			WHERE
				uniqueId = '{$steam_id_escaped}' AND
				game = '{$game_escaped}'
		");
		
		if ($db->num_rows() != 1)
		error(localized_no_such_player_message($player));
		list($player_id) = $db->fetch_row();
	}
	
	$show_flags = $g_options['countrydata'];
	if (isset($_GET['show_flags']) && is_numeric($_GET['show_flags'])) {
		$show_flags = valid_request($_GET['show_flags'], true);
	}

	$signature_cache_request = $_GET;
	$signature_cache_request['lang'] = current_lang();
	$signature_cache_request['_signature_renderer'] = 'utf8-ttf-v2';
	ksort($signature_cache_request);
	$signature_cache_path = IMAGE_PATH . '/progress/sig_' . md5(http_build_query($signature_cache_request)) . '.png';

	if (is_file($signature_cache_path)) {
		$file_timestamp = @filemtime($signature_cache_path);
		if ($file_timestamp + IMAGE_UPDATE_INTERVAL > time()) {
			if (isset($_SERVER['HTTP_IF_MODIFIED_SINCE'])) {
				$browser_timestamp = strtotime($_SERVER['HTTP_IF_MODIFIED_SINCE']);
				if ($browser_timestamp !== false && $browser_timestamp >= $file_timestamp) {
					header('HTTP/1.0 304 Not Modified');
					exit; 
				}
			}

			$mod_date = date('D, d M Y H:i:s \G\M\T', $file_timestamp);
			header('Last-Modified:'.$mod_date);
			header('Content-Length: ' . filesize($signature_cache_path));
			readfile($signature_cache_path);
			exit;
		}  
	}

	////
	//// Main
	////

if (isset($_GET['color']) && is_string($_GET['color'])) {
	$color = hex2rgb(valid_request($_GET['color'], false));
}

if (isset($_GET['caption_color']) && is_string($_GET['caption_color'])) {
	$caption_color = hex2rgb(valid_request($_GET['caption_color'], false));
}

if (isset($_GET['link_color']) && is_string($_GET['link_color'])) {
	$link_color = hex2rgb(valid_request($_GET['link_color'], false));
}

if ($player_id > 0) {
	$db->query("
		SELECT
			playerId, 
			game, 
			FROM_UNIXTIME((last_event), '%Y-%m-%d %H:%i') as lastevent,
			connection_time,
			last_skill_change,
                        unhex(replace(hex(lastName), 'E280AE', '')) as lastName,
			country,
			flag,
			kills, 
			deaths, 
			suicides, 
			skill, 
			shots, 
			hits, 
			headshots, IFNULL(ROUND(headshots/kills * 100), '-') AS hpk, 
			IFNULL(kills/deaths, '-') AS kpd, 
			IFNULL(ROUND((hits / shots * 100), 1), 0.0) AS acc, 
			activity, 
			hideranking
		FROM 
			hlstats_Players
		WHERE 
			playerId='$player_id'
	");
	if ($db->num_rows() != 1)
		error(localized_no_such_player_message($player));

	$playerdata = $db->fetch_array();
	$db->free_result();

	$pl_name = (string) $playerdata['lastName'];

	$db->query("
		SELECT
			COUNT(*) as count
		FROM
			hlstats_Players
		WHERE
			game='".$playerdata['game']."'");
	$pl_count = $db->fetch_array();
	$db->free_result();

	$rank = t('literal.unknown');

	if ($playerdata['activity'] > 0 && $playerdata['hideranking'] == 0) {
		$plGame = $playerdata['game'];
		$rankType = $g_options['rankingtype'];
		$plValue = $playerdata[$rankType];
		$plKills = $playerdata['kills'];
		$playerDeaths = $playerdata['deaths'];

		$rank = $playerRepo->getPlayerRank($plGame, $rankType, $plValue, $plKills, $playerDeaths);

		if (is_null($rank)) {
			$rank = t('literal.unknown');
		}
	} else {
		if ($playerdata['hideranking'] == 1) {
			$rank = t('literal.hidden');
		} elseif ($playerdata['hideranking'] == 2) {
			$rank = 'Banned';
		} else {
			$rank = 'Not active';
		}
	}

	if ($playerdata['activity'] == -1)
		$playerdata['activity'] = 0;

	$skill_change = '0';
	if ($playerdata['last_skill_change'] > 0)
		$skill_change = $playerdata['last_skill_change'];
	else if ($playerdata['last_skill_change'] < 0)
		$skill_change = $playerdata['last_skill_change'];  
	
	$background = 'random';
	if (isset($_GET['background']) && ((($_GET['background'] > 0) && ($_GET['background'] < 12)) || ($_GET['background']=='random'))) {
		$background = valid_request($_GET['background'], false);
	}

	if ($background == 'random') {
		$background = rand(1, 11);
	}

	$hlx_sig_image = getImage('/games/'.$playerdata['game'].'/sig/'.$background);
	if ($hlx_sig_image)
	{
		$hlx_sig = $hlx_sig_image['path'];
	}
	elseif ($hlx_sig_image = getImage('/games/'.$realgame.'/sig/'.$background))
	{
		$hlx_sig = $hlx_sig_image['path'];
	}
	else
	{
		$hlx_sig = IMAGE_PATH."/sig/$background.png";
	}

	switch ($background) {
		case 1:		$caption_color = array('red' => 0, 'green' => 0, 'blue' => 255);
					$link_color = array('red' => 0, 'green' => 0, 'blue' => 255);
					$color = array('red' => 0, 'green' => 0, 'blue' => 0);
					break;
		case 2:		$caption_color = array('red' => 147, 'green' => 23, 'blue' => 18);
					$link_color = array('red' => 147, 'green' => 23, 'blue' => 18);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 3:		$caption_color = array('red' => 150, 'green' => 180, 'blue' => 99);
					$link_color = array('red' => 150, 'green' => 180, 'blue' => 99);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 4:		$caption_color = array('red' => 255, 'green' => 203, 'blue' => 4);
					$link_color = array('red' => 255, 'green' => 203, 'blue' => 4);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 5:		$caption_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$link_color = array('red' => 0, 'green' => 102, 'blue' => 204);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 6:		$caption_color = array('red' => 0, 'green' => 0, 'blue' => 0);
					$link_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 7:		$caption_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$link_color = array('red' => 100, 'green' => 100, 'blue' => 100);
					$color = array('red' => 0, 'green' => 0, 'blue' => 0);
					break;
		case 8:		$caption_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$link_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 9:		$caption_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$link_color = array('red' => 0, 'green' => 0, 'blue' => 0);
					$color = array('red' => 0, 'green' => 0, 'blue' => 0);
					break;
		case 10:		$caption_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$link_color = array('red' => 255, 'green' => 255, 'blue' => 255);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		case 11:		$caption_color = array('red' => 150, 'green' => 180, 'blue' => 99);
					$link_color = array('red' => 150, 'green' => 180, 'blue' => 99);
					$color = array('red' => 255, 'green' => 255, 'blue' => 255);
					break;
		default:		$caption_color = array('red' => 0, 'green' => 0, 'blue' => 255);
					$link_color = array('red' => 0, 'green' => 155, 'blue' => 0);
					$color = array('red' => 0, 'green' => 0, 'blue' => 0);
					break;
}

	$image			= imagecreatetruecolor(400, 75);

        imagealphablending($image, false);
        imagesavealpha($image, true);

	$white			= imagecolorallocate($image, 255, 255, 255); 
	$bgray			= imagecolorallocate($image, 192, 192, 192); 
	$yellow		= imagecolorallocate($image, 255, 255,   0); 
	$black			= imagecolorallocate($image,   0,   0,   0); 
	$red			= imagecolorallocate($image, 255,   0,   0); 
	$green			= imagecolorallocate($image,   0, 155,   0); 
	$blue			= imagecolorallocate($image,   0,   0, 255); 
	$grey_shade		= imagecolorallocate($image, 204, 204, 204); 
	$font_color		= imagecolorallocate($image, $color['red'], $color['green'], $color['blue']);
	$caption_color	= imagecolorallocate($image, $caption_color['red'], $caption_color['green'], $caption_color['blue']);
	$link_color		= imagecolorallocate($image, $link_color['red'], $link_color['green'], $link_color['blue']);
	//$font_colorb		= imagecolorallocate($image, $colorb['red'], $colorb['green'], $colorb['blue']);
	//$caption_colorb	= imagecolorallocate($image, $caption_colorb['red'], $caption_colorb['green'], $caption_colorb['blue']);
	//$link_colorb		= imagecolorallocate($image, $link_colorb['red'], $link_colorb['green'], $link_colorb['blue']);


	$background_img = imagecreatefrompng($hlx_sig);



	if ($background_img) {
		imagecopy($image, $background_img, 0, 0, 0, 0, 400, 75);
		imagedestroy($background_img);
	}   

	if ($background == 0)
		imagerectangle($image, 0, 0, 400, 75, $bgray);

	if ($show_flags > 0)  {
		$flag = imagecreatefromgif(getFlag($playerdata['flag'], 'path'));
		if ($flag) {
			imagecopy($image, $flag, 8, 4, 0, 0, 18, 12); 
			imagedestroy($flag);
		}
	}
        imagealphablending($image, true);
	$timestamp   = max(0, (int) $playerdata['connection_time']);
	$hours       = intdiv($timestamp, 3600);
	if ($hours < 10)
		$hours = '0'.$hours; 
	$min         = intdiv($timestamp % 3600, 60);
	if ($min < 10)
		$min = '0'.$min; 
	$sec         = $timestamp % 60;
	if ($sec < 10)
		$sec = '0'.$sec; 
	$con_time = $hours.':'.$min.':'.$sec;

	if ($playerdata['last_skill_change'] == '')
		$playerdata['last_skill_change'] = 0;
	if ($playerdata['last_skill_change'] == 0)
		$trend_image_name = IMAGE_PATH.'/t1.gif';
	elseif ($playerdata['last_skill_change'] > 0)
		$trend_image_name = IMAGE_PATH.'/t0.gif';
	elseif ($playerdata['last_skill_change'] < 0)
		$trend_image_name = IMAGE_PATH.'/t2.gif';
	$trend = imagecreatefromgif($trend_image_name);
    
	$signature_font = ROOT_PATH . '/hlstatsimg/sig/font/DejaVuSans.ttf';
	$signature_ttf = function_exists('imagettftext')
		&& function_exists('imagettfbbox')
		&& is_file($signature_font);
	$rank_value = is_numeric($rank) ? number_format($rank) : (string) $rank;

	if ($signature_ttf) {
		$position_label = localized_text('sig.position', 'Position ');
		$ranktext = localized_text('sig.of_players_with_skill', 'of {count} players with {skill} (', array('count' => $pl_count['count'], 'skill' => $playerdata['skill']));
		$points_text = localized_text('sig.points_delta', '{points}) points', array('points' => $skill_change));
		$frags_line = localized_text('sig.frags_line', 'Frags: {kills} / {deaths}, K/D {kpd}, HS {headshots} ({hpk}%)', array('kills' => $playerdata['kills'], 'deaths' => $playerdata['deaths'], 'kpd' => $playerdata['kpd'], 'headshots' => $playerdata['headshots'], 'hpk' => $playerdata['hpk']));
		$activity_line = localized_text('sig.activity_line', 'Activity: {activity}%, last: {lastevent}, time: {hours}', array('lastevent' => $playerdata['lastevent'], 'activity' => $playerdata['activity'], 'hours' => $con_time));
		$statistics_label = localized_text('sig.statistics', 'Statistics: ');

		sig_draw_ttf_fit($image, $signature_font, $pl_name, 30, 16, $caption_color, 10, 8, 235);
	} else {
		// GD's bitmap fonts cannot render UTF-8. Keep this path ASCII-only.
		$position_label = 'Position ';
		$ranktext = 'of ' . $pl_count['count'] . ' with ' . $playerdata['skill'] . ' (';
		$points_text = $skill_change . ') points';
		$frags_line = 'Frags: ' . $playerdata['kills'] . ' / ' . $playerdata['deaths'] . ', K/D ' . $playerdata['kpd'] . ', HS ' . $playerdata['headshots'] . ' (' . $playerdata['hpk'] . '%)';
		$activity_line = 'Activity: ' . $playerdata['activity'] . '%, last: ' . $playerdata['lastevent'] . ', time: ' . $con_time;
		$statistics_label = 'Stats: ';

		imagestring($image, 4, 30, 3, sig_fit_bitmap_text(4, $pl_name, 360), $caption_color);
	}

	$position_prefix = $position_label . $rank_value . ' ' . $ranktext;
	$has_trend = $trend !== false;
	if ($signature_ttf) {
		$body_size = 7.2;
		$line_right = 390;
		$tail_width = sig_ttf_width($signature_font, $body_size, $points_text);
		$prefix_max = max(1, $line_right - 15 - $tail_width - ($has_trend ? 12 : 4));
		$prefix = sig_fit_ttf_text($signature_font, $body_size, $position_prefix, $prefix_max);
		$prefix_width = sig_draw_ttf_fit($image, $signature_font, $prefix, 15, 26, $font_color, $body_size, 6.2, $prefix_max);
		$next_x = 15 + $prefix_width + 3;
		if ($has_trend) {
			imagecopy($image, $trend, $next_x, 20, 0, 0, 7, 7);
			$next_x += 10;
		}
		sig_draw_ttf_fit($image, $signature_font, $points_text, $next_x, 26, $font_color, $body_size, 6.2, max(1, $line_right - $next_x));
		if ($has_trend) {
			imagedestroy($trend);
		}

		sig_draw_ttf_fit($image, $signature_font, $frags_line, 15, 38, $font_color, $body_size, 6.2, 375);
		sig_draw_ttf_fit($image, $signature_font, $activity_line, 15, 49, $font_color, $body_size, 6.2, 375);

		$watermark_text = 'HLstatsX PY';
		$watermark_size = 7;
		$watermark_width = sig_ttf_width($signature_font, $watermark_size, $watermark_text);
		$watermark_x = max(300, 390 - $watermark_width);
		$stats_label_width = sig_draw_ttf_fit($image, $signature_font, $statistics_label, 15, 60, $font_color, $body_size, 6.2, max(1, $watermark_x - 23));
		$stats_url_x = 15 + $stats_label_width + 4;
		sig_draw_ttf_fit($image, $signature_font, (string) $g_options['siteurl'], $stats_url_x, 60, $link_color, $body_size, 6.2, max(1, $watermark_x - 8 - $stats_url_x));
		sig_draw_ttf_fit($image, $signature_font, $watermark_text, $watermark_x, 71, $link_color, $watermark_size, $watermark_size, $watermark_width);
	} else {
		$bitmap_font = 2;
		$position_width = imagefontwidth($bitmap_font);
		$tail_width = $position_width * strlen(sig_ascii_text($points_text));
		$prefix_max = max(1, 375 - $tail_width - ($has_trend ? 12 : 4));
		$prefix = sig_fit_bitmap_text($bitmap_font, $position_prefix, $prefix_max);
		imagestring($image, $bitmap_font, 15, 22, $prefix, $font_color);
		$next_x = 15 + $position_width * strlen($prefix) + 3;
		if ($has_trend) {
			imagecopy($image, $trend, $next_x, 26, 0, 0, 7, 7);
			$next_x += 10;
		}
		$points = sig_fit_bitmap_text($bitmap_font, $points_text, 390 - $next_x);
		imagestring($image, $bitmap_font, $next_x, 22, $points, $font_color);
		if ($has_trend) {
			imagedestroy($trend);
		}

		imagestring($image, $bitmap_font, 15, 34, sig_fit_bitmap_text($bitmap_font, $frags_line, 375), $font_color);
		imagestring($image, $bitmap_font, 15, 45, sig_fit_bitmap_text($bitmap_font, $activity_line, 375), $font_color);

		$watermark_text = sig_ascii_text('HLstatsX PY');
		$watermark_width = imagefontwidth($bitmap_font) * strlen($watermark_text);
		$watermark_x = max(300, 390 - $watermark_width);
		$stats_label_width = imagefontwidth($bitmap_font) * strlen(sig_ascii_text($statistics_label));
		imagestring($image, $bitmap_font, 15, 56, sig_fit_bitmap_text($bitmap_font, $statistics_label, $watermark_x - 15), $font_color);
		$stats_url_x = 15 + $stats_label_width + 4;
		imagestring($image, $bitmap_font, $stats_url_x, 56, sig_fit_bitmap_text($bitmap_font, $g_options['siteurl'], $watermark_x - 8 - $stats_url_x), $link_color);
		imagestring($image, $bitmap_font, $watermark_x, 62, sig_fit_bitmap_text($bitmap_font, $watermark_text, 390 - $watermark_x), $link_color);
	}
	
	$mod_date = date('D, d M Y H:i:s \G\M\T', time());
	Header('Last-Modified:'.$mod_date);

	imagepng($image);
	imagedestroy($image);

}   
?>
