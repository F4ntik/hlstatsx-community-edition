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

	if ($auth->userdata['acclevel'] < 80) {
        die(localized_access_denied_message());
	}

	$edlist = new EditList('serverId', 'hlstats_Servers_VoiceComm', '', false);
	$edlist->columns[] = new EditListColumn('name', t('literal.server_name'), 45, true, 'text', '', 64);
	$edlist->columns[] = new EditListColumn('addr', t('literal.server_ip_or_hostname'), 20, true, 'text', '', 64);
	$edlist->columns[] = new EditListColumn('password', t('literal.password'), 20, false, 'text', '', 64);
	$edlist->columns[] = new EditListColumn('UDPPort', t('literal.udp_port_teamspeak_only'), 6, false, 'text', '8767', 64);
	$edlist->columns[] = new EditListColumn('queryPort', t('literal.query_port_or_connect_port'), 6, true, 'text', '51234', 64);
	$edlist->columns[] = new EditListColumn('descr', t('literal.notes'), 40, false, 'text', '', 64);
	$edlist->columns[] = new EditListColumn('serverType', t('literal.server_type'), 20, true, 'select', '0/Teamspeak;1/Ventrilo');
	
	if ($_POST) {
		if ($edlist->update())
			message('success', t('admin.operation_successful'));
		else
			message('warning', $edlist->error());
	}
	
?>

<?php
	
	$result = $db->query("
		SELECT
			serverId,
			name,
			addr,
			password,
			UDPPort,
			queryPort,
			descr,
			serverType
		FROM
			hlstats_Servers_VoiceComm
		ORDER BY
			serverType,
			name
	");
	
	$edlist->draw($result);
?>

<table width="75%" border="0" cellspacing="0" cellpadding="0">
<tr>
	<td align="center"><input type="submit" value="  <?php echo eHtml(t('ui.apply')); ?>  " class="submit"></td>
</tr>
</table>

