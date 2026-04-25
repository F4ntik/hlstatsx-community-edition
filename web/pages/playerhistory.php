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

    // Player History
	$player = valid_request(intval($_GET['player']), true) or error(t('literal.no_player_id'));

	$db->query("
		SELECT
			hlstats_Players.lastName,
			hlstats_Players.game
		FROM
			hlstats_Players
		WHERE
			hlstats_Players.playerId = $player
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
		array ($gamename, t('literal.event_history'), $pl_name),
		array
		(
			$gamename=>$g_options['scripturl'] . "?game=$game",
			t('literal.player_rankings')=>$g_options['scripturl'] . "?mode=players&game=$game",
			t('literal.player_details')=>$g_options['scripturl'] . "?mode=playerinfo&player=$player",
			t('literal.event_history')=>''
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
				'width=20'
			),
			new TableColumn
			(
				'eventType',
				t('literal.type'),
				'width=10&align=center'
			),
			new TableColumn
			(
				'eventDesc',
				t('literal.description'),
				'width=40&sort=no&append=.&embedlink=yes'
			),
			new TableColumn
			(
				'serverName',
				t('literal.server'),
				'width=20'
			),
			new TableColumn
			(
				'map',
				t('literal.map'),
				'width=10'
			)
		),
		'eventTime',
		'eventTime',
		'eventType',
		false,
		50,
		'page',
		'sort',
		'sortorder'
	);
	$surl = $g_options['scripturl'];
// This would be better done with a UNION query, I think, but MySQL doesn't
// support them yet. (NOTE you need MySQL 3.23 for temporary table support.)
	$db->query("DROP TABLE IF EXISTS hlstats_EventHistory");

	$sql_create_temp_table = "
		CREATE TEMPORARY TABLE hlstats_EventHistory
		(
			eventType VARCHAR(32) NOT NULL,
			eventTime DATETIME NOT NULL,
			eventDesc VARCHAR(255) NOT NULL,
			serverName VARCHAR(255) NOT NULL,
			map VARCHAR(64) NOT NULL
		) DEFAULT CHARSET=" . DB_CHARSET . " DEFAULT COLLATE=" . DB_COLLATE . ";
	";

	$db->query($sql_create_temp_table);

	function insertEvents ($table, $select)
	{
		global $db;
		$select = str_replace("<table>", "hlstats_Events_$table", $select);
		$db->query
		("
			INSERT INTO
				hlstats_EventHistory
				(
					eventType,
					eventTime,
					eventDesc,
					serverName,
					map
				)
			$select
		");
	}
	insertEvents
	('TeamBonuses', "
		SELECT
			'i18n:playerhistory.type.team_bonus',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.team_bonus|bonus=', bonus,
				'|action=', IFNULL(hlstats_Actions.description, 'i18n:literal.unknown')
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Actions
		ON
			<table>.actionId = hlstats_Actions.id
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
		AND
			hlstats_Actions.game = '$game'
	");
	if ($g_options["Mode"] == "LAN")
	{
		$uqIdStr = "IP Address:";
	}
	else
	{
		$uqIdStr = "Unique ID:";
	}
	insertEvents
	('Connects', "
		SELECT
			'i18n:playerhistory.type.connect',
			<table>.eventTime,
			'i18n:playerhistory.desc.connect',
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
	");
	insertEvents
	('Disconnects', "
		SELECT
			'i18n:playerhistory.type.disconnect',
			<table>.eventTime,
			'i18n:playerhistory.desc.disconnect',
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
	");
	insertEvents
	('Entries', "
		SELECT
			'i18n:playerhistory.type.entry',
			<table>.eventTime,
			'i18n:playerhistory.desc.entry',
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
	");
	insertEvents
	('Frags', "
		SELECT
			'i18n:playerhistory.type.kill',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.kill|victim_url=', '$surl?mode=playerinfo&player=', victimId,
				'|victim_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown'),
				'|weapon=', weapon
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Players
		ON
			hlstats_Players.playerId = <table>.victimId
		WHERE
			<table>.killerId = $player
			AND <table>.headshot = 0
	");
	insertEvents
	('Frags', "
		SELECT
			'i18n:playerhistory.type.kill',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.kill_headshot|victim_url=', '$surl?mode=playerinfo&player=', victimId,
				'|victim_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown'),
				'|weapon=', weapon
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Players
		ON
			hlstats_Players.playerId = <table>.victimId
		WHERE
			<table>.killerId = $player
			AND <table>.headshot = 1
	");
	insertEvents
	('Frags', "
		SELECT
			'i18n:playerhistory.type.death',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.death|killer_url=', '$surl?mode=playerinfo&player=', killerId,
				'|killer_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown'),
				'|weapon=', weapon
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Players
		ON
			hlstats_Players.playerId = <table>.killerId
		WHERE
			<table>.victimId = $player
	");
	insertEvents
	('Teamkills', "
		SELECT
			'i18n:playerhistory.type.team_kill',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.team_kill|victim_url=', '$surl?mode=playerinfo&player=', victimId,
				'|victim_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown'),
				'|weapon=', weapon
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Players
		ON
			hlstats_Players.playerId = <table>.victimId
		WHERE
			<table>.killerId = $player
	");
	insertEvents
	('Teamkills', "
		SELECT
			'i18n:playerhistory.type.friendly_fire',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.friendly_fire|killer_url=', '$surl?mode=playerinfo&player=', killerId,
				'|killer_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown'),
				'|weapon=', weapon
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Players
		ON
			hlstats_Players.playerId = <table>.killerId
		WHERE
			<table>.victimId = $player
	");
	insertEvents
	('ChangeRole', "
		SELECT
			'i18n:playerhistory.type.role',
			<table>.eventTime,
			CONCAT('i18n:playerhistory.desc.change_role|role=', role),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
	");
	insertEvents
	('ChangeName', "
		SELECT
			'i18n:playerhistory.type.name',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.change_name|old_name=', oldName,
				'|new_name=', newName
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
	");
	insertEvents
	('PlayerActions', "
		SELECT
			'Action',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.player_action|bonus=', bonus,
				'|action=', IFNULL(hlstats_Actions.description, 'i18n:literal.unknown')
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Actions
		ON
			hlstats_Actions.id = <table>.actionId
		WHERE
			<table>.playerId = $player
		AND
			hlstats_Actions.game = '$game'
	");
	insertEvents
	('PlayerPlayerActions', "
		SELECT
			'Action',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.player_action_against|bonus=', bonus,
				'|action=', IFNULL(hlstats_Actions.description, 'i18n:literal.unknown'),
				'|victim_url=', '$surl?mode=playerinfo&player=', victimId,
				'|victim_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown')
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Actions
		ON
			hlstats_Actions.id = <table>.actionId
		LEFT JOIN hlstats_Players ON
			hlstats_Players.playerId = <table>.victimId
		WHERE
			<table>.playerId = $player
		AND
			hlstats_Actions.game = '$game'
	");
	insertEvents
	('PlayerPlayerActions', "
		SELECT
			'Action',
			<table>.eventTime,
			CONCAT(
				'i18n:playerhistory.desc.player_action_against_me|player_url=', '$surl?mode=playerinfo&player=', <table>.playerId,
				'|player_name=', IFNULL(hlstats_Players.lastName, 'i18n:literal.unknown'),
				'|action=', IFNULL(hlstats_Actions.description, 'i18n:literal.unknown')
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Actions
		ON
			hlstats_Actions.id = <table>.actionId
		LEFT JOIN
			hlstats_Players
		ON
			hlstats_Players.playerId = <table>.playerId
		WHERE
			<table>.victimId = $player
		AND
			hlstats_Actions.game = '$game'
	");
	insertEvents
	('Suicides', "
		SELECT
			'i18n:playerhistory.type.suicide',
			<table>.eventTime,
			CONCAT('i18n:playerhistory.desc.suicide|weapon=', weapon),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		WHERE
			<table>.playerId = $player
	");
	insertEvents
	('ChangeTeam', "
		SELECT
			'Team',
			<table>.eventTime,
			IF(
				hlstats_Teams.name IS NULL,
				CONCAT('i18n:playerhistory.desc.change_team|team=', team),
				CONCAT('i18n:playerhistory.desc.change_team_named|team=', team, '|team_name=', hlstats_Teams.name)
			),
			IFNULL(hlstats_Servers.name, 'i18n:literal.unknown'),
			<table>.map
		FROM
			<table>
		LEFT JOIN
			hlstats_Servers
		ON
			hlstats_Servers.serverId = <table>.serverId
		LEFT JOIN
			hlstats_Teams
		ON
			hlstats_Teams.code = <table>.team
		WHERE
			<table>.playerId = $player
		AND
			hlstats_Teams.game = '$game'
	");
	$result = $db->query
	("
		SELECT
			hlstats_EventHistory.eventTime,
			hlstats_EventHistory.eventType,
			hlstats_EventHistory.eventDesc,
			hlstats_EventHistory.serverName,
			hlstats_EventHistory.map
		FROM
			hlstats_EventHistory
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
			hlstats_EventHistory
	");
	list($numitems) = $db->fetch_row($resultCount);
?>

<div class="block">
<?php
	printSectionTitle(t('literal.player_event_history', array('days' => $g_options['DeleteDays'])));
	if ($numitems > 0)
	{
		$table->draw($result, $numitems, 95);
	}
?><br /><br />
	<div class="subblock">
		<div style="float:right;">
			<?php echo eHtml(t('literal.go_to')); ?>: <a href="<?php echo $g_options['scripturl'] . "?mode=playerinfo&amp;player=$player"; ?>"><?php echo t('literal.player_statistics_link', array('player' => $pl_name)); ?></a>
		</div>
	</div>
</div>
