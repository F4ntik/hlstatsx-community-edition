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

	if ($auth->userdata["acclevel"] < 100) {
        die(localized_access_denied_message());
	}
	
	$edlist = new EditList("id", "hlstats_HostGroups", "server", false);
	$edlist->columns[] = new EditListColumn("pattern", t('admin.task.hostgroups.column.host_pattern'), 30, true, "text", "", 128);
	$edlist->columns[] = new EditListColumn("name", t('admin.task.hostgroups.column.group_name'), 30, true, "text", "", 128);
	
	if ($_POST)
	{
		if ($edlist->update())
			message("success", t('admin.operation_successful'));
		else
			message("warning", $edlist->error());
	}
	
?>
<?php echo t('admin.task.hostgroups.intro'); ?><p>

<?php echo t('admin.task.hostgroups.pattern_help'); ?><p>

<?php echo t('admin.task.hostgroups.ordering_help'); ?><p>

<?php
	$regroupCommand = '<code>python -m hlstats_resolve_py.cli --configfile /path/to/hlstats.conf --regroup</code>';
	echo t('admin.task.hostgroups.regroup_note', array('command' => $regroupCommand));
?><p>
<?php $result = $db->query("
		SELECT
			id,
			pattern,
			name,
			LENGTH(pattern) AS patternlength
		FROM
			hlstats_HostGroups
		ORDER BY
			patternlength DESC,
			pattern ASC
	");
	
	$edlist->draw($result);
?>

<table width="75%" border=0 cellspacing=0 cellpadding=0>
<tr>
	<td align="center"><input type="submit" value="  <?php echo eHtml(t('ui.apply')); ?>  " class="submit"></td>
</tr>
</table>

