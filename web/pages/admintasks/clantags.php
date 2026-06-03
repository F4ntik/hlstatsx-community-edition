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

	$edlist = new EditList("id", "hlstats_ClanTags", "clan", false);
	$edlist->columns[] = new EditListColumn("pattern", t('admin.task.clantags.column.pattern'), 40, true, "text", "", 64);
	$edlist->columns[] = new EditListColumn(
		"position",
		t('admin.task.clantags.column.match_position'),
		0,
		true,
		"select",
		"EITHER/" . t('admin.task.clantags.match_position.either') .
		";START/" . t('admin.task.clantags.match_position.start_only') .
		";END/" . t('admin.task.clantags.match_position.end_only')
	);
	
	if ($_POST)
	{
		if ($edlist->update())
			message("success", t('admin.operation_successful'));
		else
			message("warning", $edlist->error());
	}
	
?>

<?php echo t('admin.task.clantags.intro'); ?><p>

<?php echo t('admin.task.clantags.special_characters'); ?><p>

<table border=0 cellspacing=0 cellpadding=4>

<tr class="head">
	<td class="fSmall"><?php echo eHtml(t('admin.task.clantags.table.character')); ?></td>
	<td class="fSmall"><?php echo eHtml(t('admin.task.clantags.table.description')); ?></td>
</tr>

<tr>
	<td class="fNormal"><tt>A</tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.pattern.required_character')); ?></td>
</tr>

<tr>
	<td class="fNormal"><tt>X</tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.pattern.optional_character')); ?></td>
</tr>

<tr>
	<td class="fNormal"><tt>a</tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.pattern.literal_a')); ?></td>
</tr>

<tr>
	<td class="fNormal"><tt>x</tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.pattern.literal_x')); ?></td>
</tr>

</table><p>

<?php echo t('admin.task.clantags.example_patterns'); ?><p>

<table border=0 cellspacing=0 cellpadding=4>

<tr class="head">
	<td class="fSmall"><?php echo eHtml(t('admin.task.clantags.table.pattern')); ?></td>
	<td class="fSmall"><?php echo eHtml(t('admin.task.clantags.table.description')); ?></td>
	<td class="fSmall"><?php echo eHtml(t('admin.task.clantags.table.example')); ?></td>
</tr>

<tr>
	<td class="fNormal"><tt>[AXXXXX]</tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.example.square_brackets')); ?></td>
	<td class="fNormal"><tt>[ZOOM]Player</tt></td>
</tr>

<tr>
	<td class="fNormal"><tt>{AAXX}</tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.example.curly_braces')); ?></td>
	<td class="fNormal"><tt>{S3G}Player</tt></td>
</tr>

<tr>
	<td class="fNormal"><tt>rex>></tt></td>
	<td class="fNormal"><?php echo eHtml(t('admin.task.clantags.example.rex')); ?></td>
	<td class="fNormal"><tt>REX>>Tyranno</tt></td>
</tr>

</table><p>

<?php echo t('admin.task.clantags.warning_generic_patterns'); ?><p>

<?php echo t('admin.task.clantags.match_position_help'); ?><p>

<?php
	
	$result = $db->query("
		SELECT
			id,
			pattern,
			position
		FROM
			hlstats_ClanTags
		ORDER BY
			id
	");
	
	$edlist->draw($result);
?>

<table width="75%" border=0 cellspacing=0 cellpadding=0>
<tr>
	<td align="center"><input type="submit" value="  <?php echo eHtml(t('ui.apply')); ?>  " class="submit"></td>
</tr>
</table>

