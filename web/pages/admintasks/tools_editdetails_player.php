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
	
	$id = -1;
	if (isset($_GET['id']) && is_numeric($_GET['id'])) {
		$id = valid_request($_GET['id'], true);
	}
?>

&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" class="imageformat" alt="" /><b>&nbsp;<a href="<?php echo $g_options['scripturl']; ?>?mode=admin&amp;task=tools_editdetails"><?php echo eHtml(t('admin.edit_player_or_clan_details')); ?></a></b><br />

<img src="<?php echo IMAGE_PATH; ?>/spacer.gif" width="1" height="8" border="0" alt=""><br />
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width="9" height="6" class="imageformat" alt="" /><b>&nbsp;<?php echo eHtml(t('admin.edit_player_number', array('id' => $id))); ?></b><br /><br />

<form method="post" action="<?php echo $g_options['scripturl'] . "?mode=admin&amp;task=$selTask&amp;id=$id&amp;" . strip_tags(SID); ?>">
<?php

  // get available country flag files
	$result = $db->query("SELECT `flag`,`name` FROM hlstats_Countries ORDER BY `name`");
    while ($rowdata = $db->fetch_row($result))
    {
        $flagselect.=";".$rowdata[0]."/".$rowdata[1];
    }
	$flagselect.=";";

	$proppage = new PropertyPage("hlstats_Players", "playerId", $id, array(
		new PropertyPage_Group(t('admin.profile'), array(
			new PropertyPage_Property("fullName", t('literal.real_name'), "text"),
			new PropertyPage_Property("email", t('literal.email_address'), "text"),
			new PropertyPage_Property("homepage", t('admin.homepage_url'), "text"),
			new PropertyPage_Property("flag", t('admin.country_flag'), "select",$flagselect),
			new PropertyPage_Property("skill", t('literal.points'), "text"),
			new PropertyPage_Property("kills", t('literal.kills'), "text"),
			new PropertyPage_Property("deaths", t('literal.deaths'), "text"),
			new PropertyPage_Property("headshots", t('literal.headshots'), "text"),
			new PropertyPage_Property("suicides", t('literal.suicides'), "text"),
			new PropertyPage_Property("hideranking", t('admin.hide_ranking'), "select", "0/" . t('literal.no') . ";1/" . t('literal.yes') . ";2/" . t('admin.flag_as_banned') . ";3/" . t('admin.inactive_automatic') . ";"),
			new PropertyPage_Property("blockavatar", t('admin.force_default_avatar'), "select", "0/" . t('literal.no') . ";1/" . t('literal.yes') . ";"),
		))
	));
	
	if (isset($_POST['fullName']))
	{
		$proppage->update();
		message("success", t('admin.profile_updated'));
	}
	$playerId = $db->escape($id);
	$result = $db->query("
		SELECT
			*
		FROM
			hlstats_Players
		WHERE
			playerId='$playerId'
	");
	if ($db->num_rows() < 1) die(t('admin.no_player_exists', array('id' => $id)));
	
	$data = $db->fetch_array($result);
	
	echo '<span class="fTitle">';
	echo $data['lastName'];
	echo '</span>';
	
	echo '<span class="fNormal">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
		. '<a href="' . $g_options['scripturl'] . "?mode=playerinfo&amp;player=$id&amp;" . strip_tags(SID) . '">'
		. '(' . eHtml(t('admin.view_player_details')) . ')</a></span>';
?><br /><br />

<table width="60%" align="center" border="0" cellspacing="0" cellpadding="0">
<tr>
	<td class="fNormal"><?php
		$proppage->draw($data);
?>
	<center><input type="submit" value="  <?php echo eHtml(t('ui.apply')); ?>  " class="submit" /></center></td>
</tr>
</table>
</form>

<?php
	$tblIps = new Table
	(
		array
		(
			new TableColumn
			(
				'ipAddress',
				t('search.ip_address'),
				'width=40'
			),
			new TableColumn
			(
				'eventTime',
				t('literal.last_use'),
				'width=60'
			)
		),
		'ipAddress',
		'eventTime',
		'eventTime'
	);
	$result = $db->query
	("
		SELECT
			ipAddress,
			eventTime
		FROM
			hlstats_Events_Connects
		WHERE
			playerId = $playerId
		GROUP BY
			ipAddress
		ORDER BY
			eventTime DESC
	");
?>
<div class="block">
<?php
	printSectionTitle(t('admin.player_ip_addresses'));
	$tblIps->draw($result, 50, 50);
?>
</div><br /><br />
