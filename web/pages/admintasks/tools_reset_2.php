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
?>

&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width=9 height=6 class="imageformat"><b>&nbsp;<?php echo $task->title; ?></b><p>

<?php
    if (isset($_POST['confirm'])) {
		
		echo "<ul>\n";

      $dbt = t('admin.task.tools_reset_2.progress.delete_inactive_players');
			echo '<li>' . eHtml($dbt) . ' ';
			$minTimestamp = date("U")-(3600*24*30);
			$SQL = "DELETE FROM hlstats_Players WHERE last_event<$minTimestamp;";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n"; 

      $dbt = t('admin.task.tools_reset_2.progress.delete_empty_clans');
			echo '<li>' . eHtml($dbt) . ' ';
			$SQL = "DELETE FROM hlstats_Clans USING hlstats_Clans LEFT JOIN hlstats_Players ON (clan=clanId) WHERE isnull(clan);";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n"; 
    
      $dbt = t('admin.task.tools_reset_2.progress.delete_inactive_names');
			echo '<li>' . eHtml($dbt) . ' ';
			$SQL = "DELETE FROM hlstats_PlayerNames USING hlstats_PlayerNames LEFT JOIN hlstats_Players ON (hlstats_PlayerNames.playerId=hlstats_Players.playerId) WHERE isnull(hlstats_Players.playerId);";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n"; 

      $dbt = t('admin.task.tools_reset_2.progress.delete_inactive_uniqueids');
			echo '<li>' . eHtml($dbt) . ' ';
			$SQL = "DELETE FROM hlstats_PlayerUniqueIds USING hlstats_PlayerUniqueIds LEFT JOIN hlstats_Players ON (hlstats_PlayerUniqueIds.playerId=hlstats_Players.playerId) WHERE isnull(hlstats_Players.playerId);";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n"; 

      $dbt = t('admin.task.tools_reset_2.progress.delete_inactive_awards');
			echo '<li>' . eHtml($dbt) . ' ';
			$SQL = "DELETE FROM hlstats_Players_Awards USING hlstats_Players_Awards LEFT JOIN hlstats_Players ON (hlstats_Players_Awards.playerId=hlstats_Players.playerId) WHERE isnull(hlstats_Players.playerId);";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n"; 
	  
	  $dbt = t('admin.task.tools_reset_2.progress.delete_inactive_ribbons');
			echo '<li>' . eHtml($dbt) . ' ';
			$SQL = "DELETE FROM hlstats_Players_Ribbons USING hlstats_Players_Ribbons LEFT JOIN hlstats_Players ON (hlstats_Players_Ribbons.playerId=hlstats_Players.playerId) WHERE isnull(hlstats_Players.playerId);";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n";

      $dbt = t('admin.task.tools_reset_2.progress.delete_inactive_history');
			echo '<li>' . eHtml($dbt) . ' ';
			$SQL = "DELETE FROM hlstats_Players_History USING hlstats_Players_History LEFT JOIN hlstats_Players ON (hlstats_Players_History.playerId=hlstats_Players.playerId) WHERE isnull(hlstats_Players.playerId);";
			if ($db->query($SQL)) echo eHtml(t('admin.tools_reset.status.ok')) . "\n"; else echo eHtml(t('admin.tools_reset.status.error')) . "\n"; 


//      $dbt = "Resetting Players count for all servers";
//			echo "<li>$dbt ... ";
//			$SQL = "UPDATE hlstats_Servers SET players=0;";
//			if ($db->query($SQL)) echo "OK\n"; else echo "ERROR\n"; 
		
		echo "</ul>\n";
		
		echo eHtml(t('admin.tools_reset.done')) . "<p>";
	}
	else
	{
?>

<form method="POST">
<?php echo admin_csrf_field(); ?>
<table width="60%" align="center" border=0 cellspacing=0 cellpadding=0 class="border">

<tr>
	<td>
		<table width="100%" border=0 cellspacing=1 cellpadding=10>
		
		<tr class="bg1">
			<td class="fNormal"><?php
$stopDaemonLink = '<a href="' . $g_options['scripturl'] . '?mode=admin&amp;task=tools_runtimecontrol">' . eHtml(t('admin.tools_reset.stop_daemon')) . '</a>';
echo eHtml(t('admin.task.tools_reset_2.confirmation'));
?><p>

<b><?php echo eHtml(t('admin.tools_reset.note_label')); ?></b>: <?php echo t('admin.tools_reset.daemon_notice', array('link' => $stopDaemonLink)); ?><p>

<input type="hidden" name="confirm" value="1">
<center><input type="submit" value="  <?php echo eHtml(t('admin.task.tools_reset_2.reset_button')); ?>  "></center>
</td>
		</tr>
		
		</table></td>
</tr>

</table>
</form>
<?php
	}
?>
