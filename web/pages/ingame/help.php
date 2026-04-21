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

    $server_id = 1;
	if (isset($_GET['server_id']) && is_numeric($_GET['server_id'])) {
		$server_id = valid_request($_GET['server_id'], true);
	}

	$helpText = array(
		'commands_display_ingame' => t('help.ingame.commands_display_ingame', array(), 'Commands display the results ingame'),
		'current_position' => t('help.ingame.current_position', array(), 'Current position'),
		'total_player_statistics' => t('help.ingame.total_player_statistics', array(), 'Total player statistics'),
		'current_session_statistics' => t('help.ingame.current_session_statistics', array(), 'Current session statistics'),
		'players_ahead_in_ranking' => t('help.ingame.players_ahead_in_ranking', array(), 'Players ahead in the ranking.'),
		'commands_display_window' => t('help.ingame.commands_display_window', array(), 'Commands display the results in window'),
		'statistics_all_servers' => t('help.ingame.statistics_all_servers', array(), 'Statistics from all servers'),
		'current_server_status' => t('help.ingame.current_server_status', array(), 'Current server status'),
		'participating_servers_list' => t('help.ingame.participating_servers_list', array(), 'List of all participating servers'),
		'top_players' => t('help.ingame.top_players', array(), 'Top-Players'),
		'clan_ranking' => t('help.ingame.clan_ranking', array(), 'Clan ranking'),
		'banned_players' => t('help.ingame.banned_players', array(), 'Banned players'),
		'statistic_summary' => t('help.ingame.statistic_summary', array(), 'Statistic summary'),
		'weapons_usage' => t('help.ingame.weapons_usage', array(), 'Weapons usage'),
		'weapons_accuracy' => t('literal.weapon_accuracy', array(), 'Weapons accuracy'),
		'targets_hit_positions' => t('help.ingame.targets_hit_positions', array(), 'Targets hit positions'),
		'kill_statistics' => t('help.ingame.kill_statistics', array(), 'Kill statistics (5 or more kills)'),
		'server_actions_summary' => t('help.ingame.server_actions_summary', array(), 'Server actions summary'),
		'help_screen' => t('help.ingame.help_screen', array(), 'Help screen'),
		'commands_set_user_options' => t('help.ingame.commands_set_user_options', array(), 'Commands to set your user options'),
		'auto_command_event' => t('help.ingame.auto_command_event', array(), 'Auto-Command on specific event (on death, roundstart, roundend)'),
		'toggle_console_events' => t('help.ingame.toggle_console_events', array(), 'Enable or disable displaying console events.'),
		'toggle_global_chat_events' => t('help.ingame.toggle_global_chat_events', array(), 'Enable or disable the displaying of global chat events(if enabled).'),
		'set_player_info' => t('help.ingame.set_player_info', array(), '(Type in chat, not console) Sets your player info.'),
		'hide_from_rankings' => t('help.ingame.hide_from_rankings', array(), '(Type in chat, not console) Makes you invisible on player rankings, unranked.'),
	);

?>
	<strong>&nbsp;<a href="http://www.hlxcommunity.com">HLstatsX Community Edition</a> <?php echo $g_options['version']; ?></strong><br /><br />
	<table style="width:100%;border:0;padding:1px;border-spacing:0;">
		<tr class="data-table-head">
			<td class="fSmall data-table" colspan="3">&nbsp;<?php echo eHtml($helpText['commands_display_ingame']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">rank [skill, points, place (to all)]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['current_position']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">kpd [kdratio, kdeath (to all)]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['total_player_statistics']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">session [session_data (to all)]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['current_session_statistics']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">next</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['players_ahead_in_ranking']); ?></td>
		</tr>
		<tr class="data-table-head">
			<td class="fSmall data-table" colspan="3">&nbsp;<?php echo eHtml($helpText['commands_display_window']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">load</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['statistics_all_servers']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">status</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['current_server_status']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">servers</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['participating_servers_list']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">top20 [top5, top10]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['top_players']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">clans</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['clan_ranking']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">cheaters</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['banned_players']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">statsme</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['statistic_summary']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">weapons [weapon]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['weapons_usage']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">accuracy</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['weapons_accuracy']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">targets [target]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['targets_hit_positions']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">kills [kill, player_kills]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['kill_statistics']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">actions [action]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['server_actions_summary']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">help [cmd, cmds, commands]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['help_screen']); ?></td>
		</tr>
		<tr class="data-table-head">
			<td class="fSmall data-table" colspan="3">&nbsp;<?php echo eHtml($helpText['commands_set_user_options']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">hlx_auto clear|start|end|kill command</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['auto_command_event']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">hlx_display 0|1</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['toggle_console_events']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">hlx_chat 0|1</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['toggle_global_chat_events']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">/hlx_set realname|email|homepage [value]</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['set_player_info']); ?></td>
		</tr>
		<tr class="bg1">
			<td class="fNormal">/hlx_hideranking</td>
			<td class="fNormal">=</td>
			<td class="fNormal"><?php echo eHtml($helpText['hide_from_rankings']); ?></td>
		</tr>
    </table>
    <table class="data-table">
		<tr class="data-table-head">
			<td style="width:55%;" class="fSmall">&nbsp;<?php echo eHtml(t('literal.participating_servers')); ?></td>
			<td style="width:23%;" class="fSmall">&nbsp;<?php echo eHtml(t('literal.address')); ?></td>
			<td style="width:6%;text-align:center" class="fSmall">&nbsp;<?php echo eHtml(t('literal.map')); ?></td>
			<td style="width:6%;text-align:center" class="fSmall">&nbsp;<?php echo eHtml(t('literal.played')); ?></td>
			<td style="width:10%;text-align:center" class="fSmall">&nbsp;<?php echo eHtml(t('literal.players')); ?></td>
		</tr>
        
<?php
	$query= "
		SELECT
			serverId,
			name,
			IF(publicaddress != '',
				publicaddress,
				concat(address, ':', port)
			) AS addr,
			kills,
			headshots,              
			act_players,                                
			max_players,
			act_map,
			map_started,
			map_ct_wins,
			map_ts_wins                 
		FROM
			hlstats_Servers
		WHERE
			game='$game'
		ORDER BY
			serverId
	";
	$db->query($query);
	$this_server = array();
	$servers = array();
	while ($rowdata = $db->fetch_array()) {
		$servers[] = $rowdata;
		if ($rowdata['serverId'] == $server_id)
			$this_server = $rowdata;
	}
          
	$i=0;
	for ($i=0; $i<count($servers); $i++)
	{
		$rowdata = $servers[$i]; 
		$server_id = $rowdata['serverId'];    
		$c = ($i % 2) + 1;
		$addr = $rowdata["addr"];
		$kills     = $rowdata['kills'];
		$headshots = $rowdata['headshots'];
		$player_string = $rowdata['act_players']."/".$rowdata['max_players'];
		$map_ct_wins = $rowdata['map_ct_wins'];
		$map_ts_wins = $rowdata['map_ts_wins'];
?>
		<tr class="bg<?php echo $c; ?>">
			<td class="fSmall"><?php
				echo '<strong>'.$rowdata['name'].'</strong>';
			?></td>
			<td class="fSmall"><?php
				echo $addr;
			?></td>
			<td style="text-align:center;" class="fSmall"><?php 
				echo $rowdata['act_map'];
			?></td>
			<td style="text-align:center;" class="fSmall"><?php
				$stamp = time()-$rowdata['map_started'];
				$hours = sprintf('%02d', floor($stamp / 3600));
				$min   = sprintf('%02d', floor(($stamp % 3600) / 60));
				$sec   = sprintf('%02d', floor($stamp % 60)); 
				echo "$hours:$min:$sec";
			?></td>
			<td style="text-align:center;" class="fSmall"><?php
				echo $player_string;
			?></td>
		</tr>
<?php } ?>
    </table>
