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

	$edlist = new EditList("id", "hlstats_Actions", "game", false);
	$edlist->columns[] = new EditListColumn("game", t('admin.field.game'), 0, true, "hidden", $gamecode);
	$edlist->columns[] = new EditListColumn("code", t('admin.field.action_code'), 15, true, "text", "", 64);
	$edlist->columns[] = new EditListColumn("for_PlayerActions", t('literal.player_action'), 0, false, "checkbox");
	$edlist->columns[] = new EditListColumn("for_PlayerPlayerActions", t('literal.plyrplyr_action'), 0, false, "checkbox");
	$edlist->columns[] = new EditListColumn("for_TeamActions", t('literal.team_action'), 0, false, "checkbox");
	$edlist->columns[] = new EditListColumn("for_WorldActions", t('literal.world_action'), 0, false, "checkbox");
	$edlist->columns[] = new EditListColumn("reward_player", t('literal.player_reward'), 4, false, "text", "0");
	$edlist->columns[] = new EditListColumn("reward_team", t('literal.team_reward'), 4, false, "text", "0");
	$edlist->columns[] = new EditListColumn("team", t('literal.team'), 0, false, "select", "hlstats_Teams.name/code/game='$gamecode'");
	$edlist->columns[] = new EditListColumn("description", t('admin.field.action_description'), 23, true, "text", "", 128);

	if ($_POST)
	{
		if ($edlist->update())
			message("success", t('admin.operation_successful'));
		else
			message("warning", $edlist->error());
	}
	
?>

<?php echo t('admin.help.actions_map_specific'); ?>

<?php
	
	$result = $db->query("
		SELECT
			id,
			code,
			reward_player,
			reward_team,
			team,
			description,
			for_PlayerActions,
			for_PlayerPlayerActions,
			for_TeamActions,
			for_WorldActions
		FROM
			hlstats_Actions
		WHERE
			game='$gamecode'
		ORDER BY
			code ASC
	");
	
	$edlist->draw($result);
?>

<table width="75%" border=0 cellspacing=0 cellpadding=0>
<tr>
	<td align="center"><input type="submit" value="  <?php echo t('ui.apply'); ?>  " class="submit"></td>
</tr>
</table>

