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

	$edlist = new EditList("ribbonId", "hlstats_Ribbons", "game", false);
	$edlist->columns[] = new EditListColumn("game", t('admin.field.game'), 0, true, "hidden", $gamecode);
//	$edlist->columns[] = new EditListColumn("ribbonId", "Ribbon", 0, true, "select", "hlstats_Ribbons.ribbonName/ribbonId/game='$gamecode'");
	$edlist->columns[] = new EditListColumn("ribbonName", t('admin.field.ribbon'), 30, false, "text", "name", 64);
	$edlist->columns[] = new EditListColumn("image", t('admin.field.image_file'), 30, false, "text", "name.png", 64);
	$edlist->columns[] = new EditListColumn("awardCode", t('admin.field.trigger_award'), 0, false, "select", "hlstats_Awards.name/code/game='$gamecode'");
	$edlist->columns[] = new EditListColumn("awardCount", t('admin.field.awards_needed'), 10, true, "text", "0", 64);
	$edlist->columns[] = new EditListColumn("special", t('admin.field.special_logic'), 10, false, "text", "0", 64);

	if ($_POST) {
		if ($edlist->update())
			message("success", t('admin.operation_successful'));
		else
			message("warning", $edlist->error());
	}
	
?>

<?php echo t('admin.help.ribbons_special_logic'); ?>

<?php
	
	$result = $db->query("
		SELECT
			ribbonId,
			game,
			awardCode,
			awardCount,
			image,
			ribbonName,
			special
		FROM
			hlstats_Ribbons
		WHERE
			game='$gamecode'
		ORDER BY
			awardCount,awardCode
	");
	
	$edlist->draw($result);
?>

<table width="75%" border=0 cellspacing=0 cellpadding=0>
<tr>
	<td align="center"><input type="submit" value="  <?php echo t('ui.apply'); ?>  " class="submit"></td>
</tr>
</table>

