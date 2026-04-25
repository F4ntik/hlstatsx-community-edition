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
die(localized_direct_access_message());
    }

	if ($auth->userdata["acclevel"] < 80) {
        die(localized_access_denied_message());
	}

    $container = require ROOT_PATH . '/bootstrap.php';
    $gameRepo = $container->get(\Repository\GameRepository::class);
    $realgame = $gameRepo->getGameByCode($gamecode, 'realgame');

    function delete_server($server)
    {
    	global $db;
		$db->query("DELETE FROM `hlstats_Servers_Config` WHERE `serverId` = '" . $db->escape($server) . "';");
		$db->query("DELETE FROM `hlstats_server_load` WHERE `server_id`  = '" . $db->escape($server) . "'");
    }
	
	$edlist = new EditList("serverId", "hlstats_Servers", "server",true,true,"serversettings", 'delete_server');

	$edlist->columns[] = new EditListColumn("address", t('literal.ip_address'), 15, true, "ipaddress", "", 15);
	$edlist->columns[] = new EditListColumn("port", t('literal.port'), 5, true, "text", "27015", 5);
	$edlist->columns[] = new EditListColumn("name", t('literal.server_name'), 35, true, "text", "", 255);
	$edlist->columns[] = new EditListColumn("rcon_password", t('literal.rcon_password'), 10, false, "password", "", 128);
	$edlist->columns[] = new EditListColumn("publicaddress", t('literal.public_address'), 20, false, "text", "", 128);
	$edlist->columns[] = new EditListColumn("game", t('literal.game'), 20, true, "select", "hlstats_Games.name/code/realgame='".$realgame."'");
	$edlist->columns[] = new EditListColumn("sortorder", t('literal.sort_order'), 2, true, "text", "", 255);
	
	if ($_POST)
	{
		if ($edlist->update())
			message("success", t('admin.operation_successful'));
		else
			message("warning", $edlist->error());
	}
	
?>
<br /><br />

<?php

	$result = $db->query("
		SELECT
			serverId,
			address,
			port,
			name,
			sortorder,
			publicaddress,
			game,
			IF(rcon_password='','', '" . $db->escape(t('admin.editlist.password_encrypted')) . "') AS rcon_password
		FROM
			hlstats_Servers
		WHERE
			game='$gamecode'
		ORDER BY
			address ASC,
			port ASC
	");
	
	$edlist->draw($result, false);

?>

<table width="75%" border="0" cellspacing="0" cellpadding="0">
    <tr>
        <td align="center"><input type="submit" value="  <?php echo eHtml(t('ui.apply')); ?>  " class="submit"></td>
    </tr>
</table>

