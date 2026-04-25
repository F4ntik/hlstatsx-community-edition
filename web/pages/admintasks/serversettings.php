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

    function setdefaults($key)
    {
        global $db;
        // get default values
        $db->query("DELETE FROM hlstats_Servers_Config WHERE serverId=$key;");
        $db->query("INSERT INTO hlstats_Servers_Config (serverId, parameter, value) SELECT $key,parameter,value FROM hlstats_Servers_Config_Default");
        // get server ip and port
        $db->query("SELECT CONCAT(address, ':', port) AS addr FROM hlstats_Servers WHERE serverId=$key;");
        $r = $db->fetch_array();
    }
	
	if (isset($_GET['key'])) {
		$key = valid_request(intval($_GET['key']),true);
	} else {
		if (isset($_POST['key'])) {
			$key = valid_request(intval($_POST['key']),true);
		} else {
			$key = 0;
		}
	}
	
	if ($key == 0) {
		die(t('admin.task.serversettings.server_id_not_set'));
	}
	
	if (isset($_POST['sourceId'])) {
		$sourceId = valid_request(intval($_POST['sourceId']),true);
	} else {
		$sourceId = 0;
	}
	
?>
	
	<table id="startsettings" width="60%" align="center" border=0 cellspacing=0 cellpadding=0 class="border">
<tr>
    <td>
        <table width="100%" border=0 cellspacing=1 cellpadding=10>
        
        <tr bgcolor="#FF0000">
            <td class="fNormal" style="color: #FFF; font-weight: bold; font-size: medium;" align="center">
				<?php
				$reloadLink = '<a href="' . $g_options['scripturl'] . '?mode=admin&amp;task=tools_perlcontrol">' . eHtml(t('admin.task.serversettings.reload')) . '</a>';
				echo t('admin.task.serversettings.runtime_notice', array('reload_link' => $reloadLink));
				?>
			</td>
        </tr>
        
        </table></td>
</tr>
</table>
<br>
<?php
	// get available help texts
	$db->query("SELECT parameter,description FROM hlstats_Servers_Config_Default");
	$helptexts = array();
	while ($r = $db->fetch_array()) {
		$helptexts[strtolower($r['parameter'])] = t(
			'admin.task.serversettings.parameter_help',
			array('parameter' => $r['parameter']),
			'Runtime parameter: :parameter'
		);
	}
	
	$edlist = new EditList('serverConfigId', 'hlstats_Servers_Config','', false);
	
	$footerscript = $edlist->setHelp('helpdiv','parameter',$helptexts);

	$edlist->columns[] = new EditListColumn('serverId', t('literal.server_id'), 0, true, 'hidden', $key);
	$edlist->columns[] = new EditListColumn('parameter', t('literal.server_parameter_name'), 30, true, 'readonly', '', 50);
	$edlist->columns[] = new EditListColumn('value', t('literal.parameter_value'), 60, false, 'text', '', 128);
	
	if ($_POST)
	if ($_POST['setdefaults']=='defaults') {
		setdefaults($key);
	} else 
		if ($_POST['sourceId']!='0') {
			// copy server settings from another server
			$db->query("DELETE FROM hlstats_Servers_Config WHERE serverId=$key");
			$db->query("INSERT INTO hlstats_Servers_Config (serverId, parameter, value) SELECT $key,parameter,value FROM hlstats_Servers_Config WHERE serverId=$sourceId");
			// get server ip and port
			$db->query("SELECT CONCAT(address, ':', port) AS addr FROM hlstats_Servers WHERE serverId=$key;");
			$r = $db->fetch_array();
		} else {
			if ($edlist->update())
				message('success', t('admin.operation_successful'));
			else
				message('warning', $edlist->error());
		}
	
?>
<?php echo eHtml(t('admin.task.serversettings.runtime_parameters_intro')); ?><br>

<?php

	$result = $db->query("
		SELECT
			*
		FROM
			hlstats_Servers_Config
		WHERE
			serverId=$key
		ORDER BY
			parameter ASC
	");
	if ($db->num_rows($result) == 0) {
		setdefaults($key);
		$result = $db->query("
			SELECT
				*
			FROM
				hlstats_Servers_Config
			WHERE
				serverId=$key
			ORDER BY
				parameter ASC
		");
	}
	
	$edlist->draw($result);

	// get all other server id's
	$sourceIds = '';
	$db->query("SELECT CONCAT(name,' (',address,':',port,')') AS name, serverId FROM hlstats_Servers WHERE serverId<>$key ORDER BY name, address, port");
	while ($r = $db->fetch_array())
		$sourceIds .= '<OPTION VALUE="'.$r['serverId'].'">'.$r['name'];
   
?>

<INPUT TYPE="hidden" NAME="key" VALUE="<?php echo $key ?>">

<table width="75%" border=0 cellspacing=0 cellpadding=0>
<tr>
	<td align="center">
	<INPUT TYPE="checkbox" NAME="setdefaults" VALUE="defaults"> <?php echo eHtml(t('admin.task.serversettings.reset_defaults')); ?><br>
	<?php echo eHtml(t('admin.task.serversettings.copy_from_existing')); ?> 
  <SELECT NAME="sourceId">
	 <OPTION VALUE="0"><?php echo eHtml(t('admin.task.serversettings.select_server')); ?>
	 <?php echo $sourceIds; ?>
	</SELECT><br> 
	 
  <input type="submit" value="  <?php echo eHtml(t('ui.apply')); ?>  " class="submit"></td>
</tr>
</table>

