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
        die('Do not access this file directly.');
    }

    // Player History -> Sessions & Skill change
	$player = valid_request(intval($_GET["player"]), true) or error(t('literal.no_player_id'));

	$db->query("
		SELECT
			hlstats_Players.lastName,
			hlstats_Players.game
		FROM
			hlstats_Players
		WHERE
			playerId = $player
	");

	if ($db->num_rows() != 1) {
	error(localized_no_such_player_message($player));
	}

	$playerdata = $db->fetch_array();
	$pl_name = $playerdata['lastName'];

    if (strlen($pl_name) > 10) {
		$pl_shortname = substr($pl_name, 0, 8) . '...';
	} else {
		$pl_shortname = $pl_name;
	}

	$pl_name = htmlspecialchars($pl_name, ENT_COMPAT);
	$pl_shortname = htmlspecialchars($pl_shortname, ENT_COMPAT);
	$game = $playerdata['game'];

    $db->query("
		SELECT
			hlstats_Games.name
		FROM
			hlstats_Games
		WHERE
			hlstats_Games.code = '$game'
	");

	if ($db->num_rows() != 1) {
		$gamename = ucfirst($game);
	} else {
		list($gamename) = $db->fetch_row();
	}

	pageHeader
	(
		array ($gamename, t('literal.session_history'), $pl_name),
		array
		(
			$gamename => $g_options['scripturl']."?game=$game",
			t('literal.player_rankings') => $g_options['scripturl']."?mode=players&game=$game",
			t('literal.player_details') => $g_options['scripturl']."?mode=playerinfo&player=$player",
			t('literal.session_history') => ''
		),
		$playername = ""
	);
	flush();
	$table = new Table
	(
		array
		(
			new TableColumn
			(
				'eventTime',
				t('literal.date'),
				'width=11'
			),
			new TableColumn
			(
				'skill_change',
				t('literal.skill_change'),
				'width=10&align=right&skill_change=1'
			),
			new TableColumn
			(
				'skill',
				t('literal.points'),
				'width=10&align=right'
			),
			new TableColumn
			(
				'connection_time',
				t('literal.time_label'),
				'width=13&align=right&type=timestamp'
			),
			new TableColumn
			(
				'kills',
				t('literal.kills'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'deaths',
				t('literal.deaths'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'kpd',
				t('literal.kpd_cap'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'headshots',
				t('literal.headshots_short'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'hpk',
				t('literal.hpk_cap'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'suicides',
				t('literal.suicides'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'teamkills',
				t('literal.teamkills_short'),
				'width=7&align=right'
			),
			new TableColumn
			(
				'kill_streak',
				t('literal.kill_streak_short'),
				'width=7&align=right'
			),
		),
		'eventTime',
		'eventTime',
		'skill_change',
		false,
		50,
		'page',
		'sort',
		'sortorder'
	);
	$surl = $g_options['scripturl'];
	$result = $db->query
	("
		SELECT
			hlstats_Players_History.eventTime,
			hlstats_Players_History.skill_change,
			hlstats_Players_History.skill,
			hlstats_Players_History.kills,
			hlstats_Players_History.deaths,
			hlstats_Players_History.headshots,
			hlstats_Players_History.suicides,
			hlstats_Players_History.connection_time,
			ROUND(hlstats_Players_History.kills/(IF(hlstats_Players_History.deaths = 0, 1, hlstats_Players_History.deaths)), 2) AS kpd,
			ROUND(hlstats_Players_History.headshots/(IF(hlstats_Players_History.kills = 0, 1, hlstats_Players_History.kills)), 2) AS hpk,
			hlstats_Players_History.teamkills,
			hlstats_Players_History.kill_streak,
			hlstats_Players_History.death_streak,
			hlstats_Players_History.skill_change AS last_skill_change
		FROM
			hlstats_Players_History
		WHERE
			hlstats_Players_History.playerId = $player
		ORDER BY
			$table->sort $table->sortorder,
			$table->sort2 $table->sortorder
		LIMIT
			$table->startitem,
			$table->numperpage
	");
	$resultCount = $db->query
	("
		SELECT
			COUNT(*)
		FROM
			hlstats_Players_History
		WHERE
			hlstats_Players_History.playerId = $player
	");
	list($numitems) = $db->fetch_row($resultCount);
?>

<div class="block">
<?php
	printSectionTitle(t('literal.player_session_history'));
	if ($numitems > 0)
	{
		$table->draw($result, $numitems, 95);
	}
?><br /><br />
	<div class="subblock">
		<div style="float:left;">
			<?php echo t('literal.generated_last_days', array('days' => $g_options['DeleteDays'])); ?>
		</div>
		<div style="float:right;">
<?php 
	$db->query
	("
		SELECT
			hlstats_Players.lastName
		FROM
			hlstats_Players
		WHERE
			hlstats_Players.playerId = '$player'
	");
	list($lastName) = $db->fetch_row();
?>
			<?php echo eHtml(t('literal.go_to')); ?>: <a href="<?php echo $g_options['scripturl'] . "?mode=playerinfo&amp;player=$player"; ?>"><?php echo t('literal.player_statistics_link', array('player' => eHtml($lastName))); ?></a>
		</div>
	</div>
</div>
