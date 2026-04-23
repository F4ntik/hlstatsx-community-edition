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
        die(t('admin.direct_access'));
    }
	 
	if ($auth->userdata["acclevel"] < 80) {
        die(t('admin.access_denied'));
	}
	
    function delete_game($game)
    {
    	global $db;
		
		$srvtables = array(
			"hlstats_Events_Admin",
			"hlstats_Events_ChangeName",
			"hlstats_Events_ChangeRole",
			"hlstats_Events_ChangeTeam",
			"hlstats_Events_Chat",
			"hlstats_Events_Connects",
			"hlstats_Events_Disconnects",
			"hlstats_Events_Entries",
			"hlstats_Events_Frags",
			"hlstats_Events_Latency",
			"hlstats_Events_PlayerActions",
			"hlstats_Events_PlayerPlayerActions",
			"hlstats_Events_Rcon",
			"hlstats_Events_Statsme",
			"hlstats_Events_Statsme2",
			"hlstats_Events_StatsmeLatency",
			"hlstats_Events_StatsmeTime",
			"hlstats_Events_Suicides",
			"hlstats_Events_TeamBonuses",
			"hlstats_Events_Teamkills",
			"hlstats_Servers_Config"
		);
		$pltables = array(
			"hlstats_PlayerNames"
		);
		$dbtables = array(
			"hlstats_Actions",
			"hlstats_Awards",
			"hlstats_Ribbons",
			"hlstats_Roles",
			"hlstats_Teams",
			"hlstats_Weapons",
			"hlstats_Ranks",
			"hlstats_Maps_Counts",
			"hlstats_Servers",
			"hlstats_Players_History",
			"hlstats_Players_Awards",
			"hlstats_Players_Ribbons",
			"hlstats_PlayerUniqueIds",
			"hlstats_Players",
			"hlstats_Clans",
			"hlstats_Trend"
		);
		
		$resultServers = $db->query("SELECT serverId FROM hlstats_Servers WHERE game = '$game'");
		if ($db->num_rows($resultServers) > 0)
		{
			$serverlist = "(";
			while ($server = $db->fetch_row($resultServers))
			{
				$serverlist .= $server[0].',';
			}
			$serverlist = preg_replace('/,$/', ')',$serverlist);
			foreach ($srvtables as $srvt)
			{
				echo "<li>$srvt ... ";
				$db->query("DELETE FROM $srvt WHERE serverId IN $serverlist");
				echo t('admin.tools_reset.status.ok') . "</li>\n";
			}
			echo "<li>hlstats_server_load ... ";
			$db->query("DELETE FROM hlstats_server_load WHERE server_id IN $serverlist");
			echo t('admin.tools_reset.status.ok') . "</li>\n";
		}
		
		$resultPlayers = $db->query("SELECT playerId FROM hlstats_Players WHERE game = '$game'");
		if ($db->num_rows($resultPlayers) > 0)
		{
			$playerlist = "(";
			while ($player = $db->fetch_row($resultPlayers))
			{
				$playerlist .= $player[0].',';
			}
			$playerlist = preg_replace('/,$/', ')',$playerlist);
			foreach ($pltables as $plt)
			{
				echo "<li>$plt ... ";
				$db->query("DELETE FROM $plt WHERE playerId IN $playerlist");
				echo t('admin.tools_reset.status.ok') . "</li>\n";
			}
		}
		
		foreach ($dbtables as $dbt)
		{
			echo "<li>$dbt ... ";
			echo removeGameSettings($dbt, $game);
		}

		echo "<li>hlstats_Games ...";
		$db->query("DELETE FROM hlstats_Games WHERE code='$game'");
		echo t('admin.tools_reset.status.ok') . "\n";
		echo "</ul><p>\n";
		echo t('admin.games.delete.done') . "<p>";
    }
	
	function removeGameSettings($table, $game) {
		global $db;
		$db->query("SELECT COUNT(game) AS cnt FROM $table WHERE game='$game';");
		$r = $db->fetch_array();
		if ($r['cnt'] == 0)
		{
			$ret = t('admin.games.delete.no_data');
		}
		else
		{
			$ret = t('admin.games.delete.entries_deleted', array('count' => $r['cnt']));
			$SQL = "DELETE FROM $table WHERE game='$game';";
			$db->query($SQL);
		}
		return $ret."\n";
	}
	
	$edlist = new EditList("code", "hlstats_Games", "game", false, false, "", 'delete_game');
	$edlist->columns[] = new EditListColumn("code", t('admin.games.field.game_code'), 10, true, "readonly", "", 16);
	$edlist->columns[] = new EditListColumn("name", t('admin.games.field.display_name'), 30, true, "text", "", 128);
	$edlist->columns[] = new EditListColumn("realgame", t('admin.field.game'), 50, true, "select", "hlstats_Games_Supported.name/code/", 128);
	$edlist->columns[] = new EditListColumn("hidden", "<center>" . t('admin.games.field.hide_game') . "</center>", 0, false, "checkbox");
	
	
	if ($_POST)
	{
		if ($edlist->update())
			message("success", t('admin.operation_successful'));
		else
			message("warning", $edlist->error());
	}
	
?>

<?php echo t('admin.games.help_html'); ?>

<?php
	
	$result = $db->query("
		SELECT
			code,
			name,
			realgame,
			hidden
		FROM
			hlstats_Games
		ORDER BY
			code ASC
	");
	
	$edlist->draw($result, false);
?>

<table style="width:75%;border:0;" cellspacing="0" cellpadding="0">
<tr>
	<td align="center"><input type="submit" value="  <?php echo t('ui.apply'); ?>  " class="submit"></td>
</tr>
</table>

