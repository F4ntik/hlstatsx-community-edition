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

if (!defined('IN_HLSTATS')) {
	http_response_code(403);
	exit;
}

function localized_interpolate($text, array $params = array())
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

function localized_text($key, $fallback = null, array $params = array())
{
	if (function_exists('t')) {
		return t($key, $params, $fallback);
	}

	$text = ($fallback !== null) ? $fallback : $key;
	return localized_interpolate($text, $params);
}

function localized_direct_access_message()
{
	return localized_text('admin.direct_access');
}

function localized_access_denied_message()
{
	return localized_text('admin.access_denied');
}

function localized_invalid_or_no_game_message()
{
	return localized_text('error.invalid_or_no_game_specified');
}

function localized_template_missing_message($template)
{
	return localized_text(
		'error.template_missing',
		null,
		array('template' => $template)
	);
}

function localized_required_php_function_unavailable_message($functionName)
{
	return localized_text(
		'error.required_php_function_unavailable',
		null,
		array('function' => $functionName)
	);
}

function checkValidGame(string $gameStr, array $allowedGames, ?string &$retError) : bool
{
	// Not object and array
	if (!is_string($gameStr)) {
		$retError = localized_text('error.invalid_game_parameter');
		return false;
	}

	$gameStr = trim($gameStr);
	if ($gameStr === '') {
		$retError = localized_text('error.game_parameter_missing');
		return false;
	}

	// Path traversal and XSS fixes
	if (!preg_match('/^[a-zA-Z0-9_]+$/', $gameStr)) {
		$retError = localized_text('error.invalid_game_code');
		return false;
	}

	if (!is_array($allowedGames) || empty($allowedGames)) {
		$retError = localized_text('error.allowed_games_unavailable');
		return false;
	}

	if (!in_array($gameStr, $allowedGames, true)) {
		$retError = localized_text('error.game_not_allowed');
		return false;
	}

	return true;
}

function buildSearchSqlSafe($db, $search)
{
	$search = trim($search);
	if ($search === '') {
		return "";
	}

	$len = mb_strlen($search, 'UTF-8');
	$like_filter = $db->escape(addcslashes($search, '%_'));
	$match_filter = $db->escape($search);

	// 'MATCH' - doesn't work for text shorter than 4 characters. Fixed without editing the mysql cfg.
	if ($len <= 3) {
		if ($len == 1) {
			return " AND hlstats_Events_Chat.message LIKE '%{$like_filter}%'";
		}

		return " AND (
			hlstats_Events_Chat.message = '{$like_filter}'
			OR hlstats_Events_Chat.message LIKE '{$like_filter} %'
			OR hlstats_Events_Chat.message LIKE '% {$like_filter}'
			OR hlstats_Events_Chat.message LIKE '% {$like_filter} %'
		)";
	}

	return " AND MATCH (hlstats_Events_Chat.message) AGAINST ('{$match_filter}' IN BOOLEAN MODE)";
}

// Support for legacy code, it used array $_REQUEST, for _GET, and _POST?
// Filter arrays
function getChatFilterParam()
{
	$retFilter = '';

	$postFilter = filter_input(INPUT_POST, 'filter', FILTER_UNSAFE_RAW);
	$getFilter = filter_input(INPUT_GET, 'filter', FILTER_UNSAFE_RAW);

	if ($postFilter !== null && $postFilter !== false) {
		$retFilter = $postFilter;
	} elseif ($getFilter !== null && $getFilter !== false) {
		$retFilter = $getFilter;
	}

	$retFilter = (string)$retFilter;
	return trim($retFilter);
}

function eHtml($str)
{
    return htmlspecialchars($str, ENT_QUOTES | ENT_HTML5, 'UTF-8');
}

function translate_ui_literal_key($text)
{
	if (!is_string($text) || $text === '') {
		return null;
	}

	if (strpos($text, '.') !== false) {
		return $text;
	}

	static $map = array(
		'Name' => 'literal.name',
		'Username' => 'admin.username',
		'Password' => 'admin.password',
		'Players' => 'literal.players',
		'Player' => 'literal.player',
		'Clans' => 'literal.clans',
		'Clan' => 'literal.clan',
		'Servers' => 'literal.servers',
		'Chat' => 'literal.chat',
		'Countries' => 'literal.countries',
		'Awards' => 'literal.awards',
		'Actions' => 'literal.actions',
		'Weapons' => 'literal.weapons',
		'Maps' => 'literal.maps',
		'Roles' => 'literal.roles',
		'Ribbons' => 'literal.ribbons',
		'Ranks' => 'literal.ranks',
		'Player Action' => 'literal.player_action',
		'PlyrPlyr Action' => 'literal.plyrplyr_action',
		'Team Action' => 'literal.team_action',
		'World Action' => 'literal.world_action',
		'Action' => 'literal.action',
		'Weapon' => 'literal.weapon',
		'Team' => 'literal.team',
		'Role' => 'literal.role',
		'Server' => 'literal.server',
		'Server ID' => 'literal.server_id',
		'Server parameter name' => 'literal.server_parameter_name',
		'Parameter value' => 'literal.parameter_value',
		'Address' => 'literal.address',
		'Connection Time' => 'literal.connection_time',
		'Map Name' => 'literal.map_name',
		'Map' => 'literal.map',
		'Game Code' => 'literal.game_code',
		'Display Name' => 'literal.display_name',
		'Hide Game' => 'literal.hide_game',
		'Played' => 'literal.played',
		'Statistics Summary' => 'literal.statistics_summary',
		'Clan Profile Stats Summary' => 'literal.clan_profile_stats_summary',
		'Number Of Members' => 'literal.number_of_members',
		'Avg. Member Points' => 'literal.avg_member_points',
		'Top Player' => 'literal.top_player',
		'Top Clan' => 'literal.top_clan',
		'Rank' => 'literal.rank',
		'Points' => 'literal.points',
		'Activity' => 'literal.activity',
		'Kills' => 'literal.kills',
		'Deaths' => 'literal.deaths',
		'Headshots' => 'literal.headshots',
		'No Players' => 'literal.no_players',
		'Unknown' => 'literal.unknown',
		'Unknown team' => 'literal.unknown_team',
		'Unknown Country' => 'status.unknown_country',
		'Damage per Hit' => 'literal.damage_per_hit',
		'Shots per Kill' => 'literal.shots_per_kill',
		'Kills per Death' => 'literal.kills_per_death',
		'Player Locations' => 'literal.player_locations',
		'Clan Kills' => 'literal.clan_kills',
		'Modifier' => 'literal.modifier',
		'Shots' => 'literal.shots',
		'Hits' => 'literal.hits',
		'Damage' => 'literal.damage',
		'Head' => 'literal.head',
		'Chest' => 'literal.chest',
		'Stomach' => 'literal.stomach',
		'Left Arm' => 'literal.left_arm',
		'Right Arm' => 'literal.right_arm',
		'Left Leg' => 'literal.left_leg',
		'Right Leg' => 'literal.right_leg',
		'L. Arm' => 'literal.left_arm',
		'R. Arm' => 'literal.right_arm',
		'L. Leg' => 'literal.left_leg',
		'R. Leg' => 'literal.right_leg',
		'Left' => 'literal.left',
		'Middle' => 'literal.middle',
		'Right' => 'literal.right',
		'HeatMap' => 'literal.heatmap',
		'Earned' => 'literal.earned',
		'Earned Against' => 'literal.earned_against',
		'Achieved' => 'literal.achieved',
		'Times Victimized' => 'literal.times_victimized',
		'Reward' => 'literal.reward',
		'Picked' => 'literal.picked',
		'Joined' => 'literal.joined',
		'Accuracy' => 'literal.accuracy',
		'Weapon Accuracy' => 'literal.weapon_accuracy',
		'Suicides' => 'literal.suicides',
		'Victim' => 'literal.victim',
		'Playername' => 'literal.player',
		'Clanname' => 'admin.clan_name',
		'Perc. Kills' => 'literal.percent_kills',
		'Perc. Headshots' => 'literal.percent_headshots',
		'Skill Bonus' => 'literal.skill_bonus',
		'Skill Bonus Total' => 'literal.skill_bonus_total',
		'Headshots per Kill' => 'literal.headshots_per_kill',
		'Teammate Kills' => 'literal.teammate_kills',
		'Longest Kill Streak' => 'literal.longest_kill_streak',
		'Longest Death Streak' => 'literal.longest_death_streak',
		'Total Kills' => 'literal.total_kills',
		'Total Deaths' => 'literal.total_deaths',
		'Home Page' => 'literal.home_page',
		'Server offline' => 'literal.server_offline',
		'Profile' => 'admin.profile',
		'Real Name' => 'literal.real_name',
		'E-mail Address' => 'literal.email_address',
		'Homepage URL' => 'admin.homepage_url',
		'Country Flag' => 'admin.country_flag',
		'Hide Ranking' => 'admin.hide_ranking',
		'Force Default Avatar Image (note that this overrides images in hlstatsimg/avatars)' => 'admin.force_default_avatar',
		'Clan Name' => 'admin.clan_name',
		'Map Region' => 'admin.map_region',
		'1 = Hide from clan list' => 'admin.hide_from_clan_list',
		'IP Address' => 'search.ip_address',
		'Aliases' => 'literal.aliases',
		'Last Use' => 'literal.last_use',
		'Last Used' => 'literal.last_use',
		'Total Connection Time' => 'literal.total_connection_time',
		'Hidden' => 'literal.hidden',
		'Banned' => 'literal.banned',
		'In good standing' => 'literal.in_good_standing',
		'Not active' => 'literal.not_active',
		'Members' => 'literal.members',
		'(None)' => 'literal.none',
		'(Not specified.)' => 'literal.not_specified',
		'Time' => 'literal.time_label',
		'Skill' => 'literal.skill_label',
		'Hpk' => 'literal.hpk_cap',
		'Kpd' => 'literal.kpd_cap',
		'K:D' => 'literal.kpd_cap',
		'Game' => 'ui.game',
		'Games' => 'ui.games',
		'Yes' => 'literal.yes',
		'No' => 'literal.no',
		'Team Bonus' => 'playerhistory.type.team_bonus',
		'Connect' => 'playerhistory.type.connect',
		'Disconnect' => 'playerhistory.type.disconnect',
		'Entry' => 'playerhistory.type.entry',
		'Kill' => 'playerhistory.type.kill',
		'Death' => 'playerhistory.type.death',
		'Team Kill' => 'playerhistory.type.team_kill',
		'Friendly Fire' => 'playerhistory.type.friendly_fire',
		'Role' => 'playerhistory.type.role',
		'Name' => 'playerhistory.type.name',
		'Suicide' => 'playerhistory.type.suicide',
		'Authorization Required' => 'admin.auth_required',
		'Access denied!' => 'admin.access_denied',
		'Operation successful.' => 'admin.operation_successful',
		'Profile updated successfully.' => 'admin.profile_updated',
		'No help text available' => 'admin.no_help_text',
		'Server IP Address' => 'admin.server_ip_address',
		'Server Port' => 'admin.server_port',
		'Server Name' => 'literal.server_name',
		'Rcon Password' => 'admin.rcon_password',
		'Public Address' => 'admin.public_address',
		'Admin Mod' => 'admin.admin_mod',
		'PLEASE SELECT' => 'admin.please_select',
	);

	return $map[$text] ?? null;
}

function translate_ui_literal($text)
{
	if (!is_string($text) || $text === '') {
		return $text;
	}

	$key = translate_ui_literal_key($text);
	if ($key === null) {
		return $text;
	}

	return t($key, array(), $text);
}

function playerinfo_cstrike_action_label($code, $description, $game)
{
	if (strtolower((string) $game) !== 'cstrike') {
		return $description;
	}

	static $map = array(
		"Begin_Bomb_Defuse_Without_Kit\0Start Defusing the Bomb Without a Defuse Kit" => 'player_action.defuse_without_kit',
		"Begin_Bomb_Defuse_With_Kit\0Start Defusing the Bomb With a Defuse Kit" => 'player_action.defuse_with_kit',
		"Assassinated_The_VIP\0Assassinate the VIP" => 'player_action.assassinate_vip',
		"Planted_The_Bomb\0Plant the Bomb" => 'player_action.plant_bomb',
		"Defused_The_Bomb\0Defuse the Bomb" => 'player_action.defuse_bomb',
		"Touched_A_Hostage\0Touch a Hostage" => 'player_action.touch_hostage',
		"Rescued_A_Hostage\0Rescue a Hostage" => 'player_action.rescue_hostage',
		"Killed_A_Hostage\0Kill a Hostage" => 'player_action.kill_hostage',
		"Became_VIP\0Become the VIP" => 'player_action.become_vip',
		"Spawned_With_The_Bomb\0Spawn with the Bomb" => 'player_action.spawn_with_bomb',
		"Got_The_Bomb\0Pick up the Bomb" => 'player_action.pick_up_bomb',
		"Dropped_The_Bomb\0Drop the Bomb" => 'player_action.drop_bomb',
		"CTs_Win\0All Terrorists eliminated" => 'player_action.all_terrorists_eliminated',
		"Terrorists_Win\0All Counter-Terrorists eliminated" => 'player_action.all_counter_terrorists_eliminated',
		"All_Hostages_Rescued\0Counter-Terrorists rescued all the hostages" => 'player_action.counter_terrorists_rescued_hostages',
		"Target_Bombed\0Terrorists bombed the target" => 'player_action.terrorists_bombed_target',
		"VIP_Assassinated\0Terrorists assassinated the VIP" => 'player_action.terrorists_assassinated_vip',
		"Bomb_Defused\0Counter-Terrorists defused the bomb" => 'player_action.counter_terrorists_defused_bomb',
		"VIP_Escaped\0VIP escaped" => 'player_action.vip_escaped',
		"kill_streak_2\0Double Kill (2 kills)" => 'player_action.double_kill',
		"kill_streak_3\0Triple Kill (3 kills)" => 'player_action.triple_kill',
		"kill_streak_4\0Domination (4 kills)" => 'player_action.domination',
		"kill_streak_5\0Rampage (5 kills)" => 'player_action.rampage',
		"kill_streak_6\0Mega Kill (6 kills)" => 'player_action.mega_kill',
		"kill_streak_7\0Ownage (7 kills)" => 'player_action.ownage',
		"kill_streak_8\0Ultra Kill (8 kills)" => 'player_action.ultra_kill',
		"kill_streak_9\0Killing Spree (9 kills)" => 'player_action.killing_spree',
		"kill_streak_10\0Monster Kill (10 kills)" => 'player_action.monster_kill',
		"kill_streak_11\0Unstoppable (11 kills)" => 'player_action.unstoppable',
		"kill_streak_12\0God Like (12+ kills)" => 'player_action.god_like',
		"headshot\0Headshot" => 'player_action.headshot',
		"headshot\0Headshot Kill" => 'player_action.headshot',
	);

	$key = $map[(string) $code . "\0" . (string) $description] ?? null;
	return $key === null ? $description : t($key, array(), $description);
}

function playerinfo_cstrike_team_label($name, $game)
{
	if (strtolower((string) $game) !== 'cstrike') {
		return $name;
	}

	static $map = array(
		'Counter-Terrorist' => 'player_team.counter_terrorist',
		'Counter-Terrorists' => 'player_team.counter_terrorists',
		'CT' => 'player_team.counter_terrorists',
		'Terrorist' => 'player_team.terrorist',
		'Terrorists' => 'player_team.terrorists',
		'TERRORIST' => 'player_team.terrorists',
	);

	$key = $map[(string) $name] ?? null;
	return $key === null ? $name : t($key, array(), $name);
}

function localized_render_text($text)
{
	if (!is_string($text) || $text === '') {
		return $text;
	}

	if (strpos($text, 'i18n:') !== 0) {
		return translate_ui_literal($text);
	}

	$payload = substr($text, 5);
	$parts = explode('|', $payload);
	$key = array_shift($parts);
	$params = array();

	foreach ($parts as $part) {
		$separator = strpos($part, '=');
		if ($separator === false) {
			continue;
		}

		$name = substr($part, 0, $separator);
		$value = substr($part, $separator + 1);
		$params[$name] = localized_render_text(rawurldecode($value));
	}

	return t($key, $params, $key);
}

function localized_no_such_game_message($game)
{
	return localized_text('literal.no_such_game_named', null, array('game' => $game));
}

function localized_no_such_player_message($player)
{
	return localized_text('literal.no_such_player', null, array('player' => $player));
}

function localized_no_such_country_message($country)
{
	return localized_text('literal.no_such_country', null, array('country' => $country));
}

function localized_no_such_clan_message($clan)
{
	return localized_text('literal.no_such_clan', null, array('clan' => $clan));
}

function localized_no_players_matching_uniqueid_message($uniqueid)
{
	return localized_text('literal.no_players_matching_uniqueid', null, array('uniqueid' => $uniqueid));
}

function format_compact_duration($seconds)
{
	$seconds = max(0, (int) round($seconds));

	$days = intdiv($seconds, 86400);
	$seconds %= 86400;
	$hours = intdiv($seconds, 3600);
	$seconds %= 3600;
	$minutes = intdiv($seconds, 60);
	$seconds %= 60;

	return sprintf(
		'%d%s&nbsp;%02d%s&nbsp;%02d%s&nbsp;%02d%s',
		$days,
		t('time.compact.d'),
		$hours,
		t('time.compact.h'),
		$minutes,
		t('time.compact.m'),
		$seconds,
		t('time.compact.s')
	);
}

function format_short_duration($time)
{
	$time = max(0, (int) round($time));
	$hours = intdiv($time, 3600);
	$minutes = intdiv($time % 3600, 60);
	$seconds = $time % 60;

	if ($hours > 0) {
		return $hours . t('time.compact.h') . ' ' . $minutes . t('time.compact.m') . ' ' . $seconds . t('time.compact.s');
	}

	if ($minutes > 0) {
		return $minutes . t('time.compact.m') . ' ' . $seconds . t('time.compact.s');
	}

	return $seconds . t('time.compact.s');
}

// Test if flags exists
/**
 * getFlag()
 * 
 * @param string $flag
 * @param string $type
 * @return string Either the flag or default flag if none exists
 */
function getFlag($flag, $type='url')
{
	$image = getImage('/flags/'.strtolower($flag));
	if ($image)
		return $image[$type];
	else
		return IMAGE_PATH.'/flags/0.gif';
}

/**
 * valid_request()
 * 
 * @param string $str
 * @param boolean $numeric
 * @return mixed request
 */
function valid_request($str, $numeric = false)
{
	if ($str === null) {
		$str = '';
	}

	if (is_array($str) || is_object($str)) {
		return $numeric ? -1 : '';
	}

	$str = (string) $str;
	$str = preg_replace('/<script\b[^>]*>.*?<\/script>/isu', '', $str);
	$str = preg_replace('/[\x00-\x1F\x7F]/u', '', $str);
	$str = preg_replace('/[^\p{L}\p{N}\[\]*.,=()!"$%&^`?\'":;#+~_\-|<>\/\\\\@{}\s]/u', '', $str);

	if (!$numeric) {
		return htmlspecialchars($str, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
	}

	if (is_numeric($str)) {
		return intval($str);
	}

	return -1;
}

/**
 * timestamp_to_str()
 * 
 * @param integer $timestamp
 * @return string Formatted Timestamp
 */
function timestamp_to_str($seconds)
{
    // We allow passing an empty parameter, for output in html
	if (empty($seconds)) {
		return t('time.zero');
	}

    // If something other than int or float is passed here, then return 'Undefined'
	if (!is_numeric($seconds)) {
		return t('ui.undefined');
	}

	return format_compact_duration($seconds);
}

/**
 * error()
 * Formats and outputs the given error message. Optionally terminates script
 * processing.
 * 
 * @param mixed $message
 * @param bool $exit
 * @return void
 */
function error(string $message, bool $exit = true) : void
{
    $html = '<table style="border:1px solid red;padding:1em;margin:1em;background:#fee;">';

    $html .= '<thead style="text-align:center; color:#673636;">';
    $html .= '<tr>';
    $html .= '<td class="errorhead">' . eHtml(t('ui.error')) . '</td>';
    $html .= '</tr>';
    $html .= '</thead>';

    $html .= '<tbody>';
    $html .= '<tr>';
    $html .= '<td class="errortext">' . nl2br(eHtml($message), false) . '</td>';
    $html .= '</tr>';
    $html .= '</tbody>';

    $html .= '</table>';

    echo $html;

    if ($exit) {
        exit;
    }
}

//
// string makeQueryString (string key, string value, [array notkeys])
//
// Generates an HTTP GET query string from the current HTTP GET variables,
// plus the given 'key' and 'value' pair. Any current HTTP GET variables
// whose keys appear in the 'notkeys' array, or are the same as 'key', will
// be excluded from the returned query string.
//

/**
 * makeQueryString()
 * 
 * @param mixed $key
 * @param mixed $value
 * @param mixed $notkeys
 * @return
 */
function makeQueryString($key, $value, $notkeys = array())
{
	$params = $_GET;
	$params[$key] = $value;

	// We remove disabled keys (for example, "page" when changing sorting)
	foreach ($notkeys as $remove) {
		unset($params[$remove]);
	}

	// Building a query string
	return http_build_query($params);
}

//
// void pageHeader (array title, array location)
//
// Prints the page heading.
//

/**
 * pageHeader()
 * 
 * @param mixed $title
 * @param mixed $location
 * @return
 */
function pageHeader($title = '', $location = '')
{
	global $db, $g_options;
	if ( defined('PAGE') && PAGE == 'HLSTATS' )
		include (PAGE_PATH . '/header.php');
	elseif ( defined('PAGE') && PAGE == 'INGAME' )
		include (PAGE_PATH . '/ingame/header.php');
}


//
// void pageFooter (void)
//
// Prints the page footer.
//

/**
 * pageFooter()
 * 
 * @return
 */
function pageFooter()
{
	global $g_options;
	if ( defined('PAGE') && PAGE == 'HLSTATS' )
		include (PAGE_PATH . '/footer.php');
	elseif ( defined('PAGE') && PAGE == 'INGAME' )
		include (PAGE_PATH . '/ingame/footer.php');
}

/**
 * getSortArrow()
 * 
 * @param mixed $sort
 * @param mixed $sortorder
 * @param mixed $name
 * @param mixed $longname
 * @param string $var_sort
 * @param string $var_sortorder
 * @param string $sorthash
 * @return string Returns the code for a sort arrow <IMG> tag.
 */
function getSortArrow($sort, $sortorder, $name, $longname, $var_sort = 'sort', $var_sortorder =
	'sortorder', $sorthash = '', $ajax = false)
{
	global $g_options;

	if ($sortorder == 'asc')
	{
		$sortimg = 'sort-ascending.gif';
		$othersortorder = 'desc';
	}
	else
	{
		$sortimg = 'sort-descending.gif';
		$othersortorder = 'asc';
	}
	
	$sortUrl = $g_options['scripturl'] . '?' . makeQueryString($var_sort, $name, array($var_sortorder));

	if ($sort == $name)
	{
		$sortUrl .= "&$var_sortorder=$othersortorder";
		$jsarrow = "'" . $var_sortorder . "': '" . $othersortorder . "'";
	}
	else
	{
		$sortUrl .= "&$var_sortorder=$sortorder";
		$jsarrow = "'" . $var_sortorder . "': '" . $sortorder . "'";
	}

	if ($sorthash)
	{
		$sortUrl .= "#$sorthash";
	}

	$arrowstring = '<a href="' . eHtml($sortUrl) . '"';

	$arrowstring .= ' class="head"';
	
	if ( $ajax )
	{
		$arrowstring .= " onclick=\"Tabs.refreshTab({'$var_sort': '$name', $jsarrow}); return false;\"";
	}
	
	$arrowstring .= ' title="' . eHtml(t('ui.change_sort_order')) . '">' . eHtml(translate_ui_literal($longname)) . '</a>';

	if ($sort == $name)
	{
		$arrowstring .= '&nbsp;<img src="' . IMAGE_PATH . "/$sortimg\"" .
			" style=\"padding-left:4px;padding-right:4px;\" alt=\"$sortimg\" />";
	}


	return $arrowstring;
}

/**
 * getSelect()
 * Returns the HTML for a SELECT box, generated using the 'values' array.
 * Each key in the array should be a OPTION VALUE, while each value in the
 * array should be a corresponding descriptive name for the OPTION.
 * 
 * @param mixed $name
 * @param mixed $values
 * @param string $currentvalue
 * @return The 'currentvalue' will be given the SELECTED attribute.
 */
function getSelect($name, $values, $currentvalue = '')
{
	$select = "<select name=\"$name\" style=\"width:300px;\">\n";

	$gotcval = false;

	foreach ($values as $k => $v)
	{
		$select .= "\t<option value=\"$k\"";

		if ($k == $currentvalue)
		{
			$select .= ' selected="selected"';
			$gotcval = true;
		}

		$select .= ">$v</option>\n";
	}

	if ($currentvalue && !$gotcval)
	{
		$select .= "\t<option value=\"$currentvalue\" selected=\"selected\">$currentvalue</option>\n";
	}

	$select .= '</select>';

	return $select;
}

/**
 * getLink()
 * 
 * @param mixed $url
 * @param integer $maxlength
 * @param string $type
 * @param string $target
 * @return
 */
 
function getLink($url, $type = 'http://', $target = '_blank')
{
	$urld=parse_url($url);

	if(!isset($urld['scheme']) && (!isset($urld['host']) && isset($urld['path'])))
	{
			$urld['scheme']=str_replace('://', '', $type);
			$urld['host']=$urld['path'];
			unset($urld['path']);
	}

	if($urld['scheme']!='http' && $urld['scheme']!='https')
	{
			return localized_text('error.invalid_url');
	}

	if(!isset($urld['path']))
	{
			$urld['path']='';
	}

	if(!isset($urld['query']))
	{
			$urld['query']='';
	}
	else
	{
			$urld['query']='?' . urlencode($urld['query']);
	}

	if(!isset($urld['fragment']))
	{
			$urld['fragment']='';
	}
	else
	{
			$urld['fragment']='#' . urlencode($urld['fragment']);
	}

	$uri=sprintf("%s%s%s", $urld['path'], $urld['query'], $urld['fragment']);
	$host_uri=$urld['host'] . $uri;
	return sprintf('<a href="%s://%s%s" target="%s">%s</a>',$urld['scheme'], $urld['host'], $uri, $target, htmlspecialchars($host_uri, ENT_COMPAT));
}

/**
 * Generate a safe mailto link for an email address.
 * Validates the email, trims it, blocks dangerous characters,
 * converts to lowercase, and safely truncates display text.
 *
 * Note: does not support ASCII characters.
 *
 * @param string|null $email The email address to link
 * @param int $maxLength Maximum length of the displayed email
 * @return string HTML link or empty string if invalid
 */
function getEmailLink(?string $email, int $maxLength = 40) : string
{
	// 1. Return empty string if email is null or empty
	if (!$email) {
		return '';
	}

	// 2. Remove leading/trailing whitespace
	$email = trim($email);

	// 3. Validate email format using PHP filter
	if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
		return '';
	}

	// 4. Block dangerous characters for mailto and HTML
	// Disallow: double/single quotes, <, >, ?, and whitespace
	if (preg_match('/[?"\'<>\s]/', $email)) {
		return '';
	}

	// 5. Normalize email to lowercase for consistent display
	$email = mb_strtolower($email, 'UTF-8');

	// 6. Trim the email for display if it exceeds max length
	// mb_strimwidth ensures multibyte safe truncation
	$display = mb_strimwidth($email, 0, $maxLength, '...', 'UTF-8');

	// 7. Construct the mailto URL
	$url = 'mailto:' . $email;

	// 8. Return safe HTML link
	// eHtml should escape HTML special characters to prevent XSS
	return sprintf('<a href="%s">%s</a>', eHtml($url), eHtml($display));
}

/**
 * getImage()
 * 
 * @param string $filename
 * @return mixed Either the image if exists, or false otherwise
 */
function getImage($filename)
{
	preg_match('/^(.*\/)(.+)$/', $filename, $matches);
	$relpath = $matches[1];
	$realfilename = $matches[2];
	
	$path = IMAGE_PATH . $filename;
	$url = IMAGE_PATH . $relpath . rawurlencode($realfilename);

	// check if image exists
	if (file_exists($path . '.png'))
	{
		$ext = 'png';
	} elseif (file_exists($path . '.gif'))
	{
		$ext = 'gif';
	} elseif (file_exists($path . '.jpg'))
	{
		$ext = 'jpg';
	}
	else
	{
		$ext = '';
	}

	if ($ext)
	{
		$size = getImageSize("$path.$ext");

		return array('url' => "$url.$ext", 'path' => "$path.$ext", 'width' => $size[0], 'height' => $size[1],
			'size' => $size[3]);
	}

    return false;
}

function printSectionTitle($title, $echo = true)
{
	$html = '<span class="fHeading">';
	$html .= '&nbsp;<img src="' . TITLE_IMAGE . '" alt="">';
	$html .= '&nbsp;' . eHtml($title);
	$html .= '</span>';
	$html .= '<br><br>';

	if (!$echo) {
		return $html;
	}

	echo $html;
}

/**
 * Convert hex color to RGB array.
 *
 * @param string $hexVal Color in hex format (e.g. "FF00CC" or "#FF00CC").
 * @return array{red: int, green: int, blue: int}|null Associative array or null on failure.
 */
function tryHexToRgb($hexVal = '') : ?array
{
	$hexVal = ltrim($hexVal, '#');

	if (!preg_match('/^[0-9A-F]{6}$/i', $hexVal)) {
		return null;
	}

	$parts = str_split($hexVal, 2);
	$rgb = array_map('hexdec', $parts);

	return [
		'red'   => $rgb[0],
		'green' => $rgb[1],
		'blue'  => $rgb[2],
	];
}

// Deprecated function
function hex2rgb($hexVal = '')
{
	$hexVal = preg_replace('[^a-fA-F0-9]', '', $hexVal);
	if (strlen($hexVal) != 6)
	{
		return 'ERR: Incorrect colorcode, expecting 6 chars (a-f, 0-9)';
	}
	$arrTmp = explode(' ', chunk_split($hexVal, 2, ' '));
	$arrTmp = array_map('hexdec', $arrTmp);
	return array('red' => $arrTmp[0], 'green' => $arrTmp[1], 'blue' => $arrTmp[2]);
}
