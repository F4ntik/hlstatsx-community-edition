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
?>

&nbsp;&nbsp;&nbsp;&nbsp;<img src="<?php echo IMAGE_PATH; ?>/downarrow.gif" width=9 height=6 class="imageformat"><b>&nbsp;<?php echo $task->title; ?></b><p>

<?php

function check_writable() {

	$ok = '';
	$f = IMAGE_PATH."/games/";
	if (!is_writable($f)) 
		$ok .= '<li>' . t('admin.task.tools_settings_copy.error.write_permission', array('path' => eHtml($f))) . '</li>';
	
	if ($ok != '') {
		echo '<strong>' . eHtml(t('ui.error')) . ":</strong><br><ul>";
		echo $ok;
		echo '</ul><br>' . eHtml(t('admin.task.tools_settings_copy.error.correct_before_continuing'));
		die();
	}
	return true; 
}

function getTableFields($table,$auto_increment) {
   // get a field array of specified table
   global $db;

   $db->query("SHOW COLUMNS FROM $table;");
   $res = array();
   while ($r=$db->fetch_array())
   {  
      if ((!$auto_increment) && ($r['Extra']=='auto_increment'))
      {  
         continue;
      }
      else
      {  
         array_push($res,$r['Field']);
      }
   }
   return $res;
}

function copySettings($table,$game1,$game2) {
	global $db;
	
	$db->query("SELECT game FROM $table WHERE game='$game2' LIMIT 1;");
	if ($db->num_rows()!=0)
		$ret = t('admin.task.tools_settings_copy.progress.target_gametype_exists');
	else {
		$db->query("SELECT count(game) AS cnt FROM $table WHERE game='$game1';");
		$r = $db->fetch_array();
		if ($r['cnt']==0)
			$ret = t('admin.task.tools_settings_copy.progress.no_source_data');
		else {
			$ret = t('admin.task.tools_settings_copy.progress.entries_copied', array('count' => $r['cnt']));
			$fields = '';
			$ignoreFields = array('game','id','d_winner_id','d_winner_count','g_winner_id','g_winner_count','count','picked','kills','deaths','headshots');
			foreach (getTableFields($table,0) AS $field) {
				if (!in_array($field, $ignoreFields)) {
					if ($fields!='')
						$fields .= ', ';
					$fields .= $field;
				}
			}
			$SQL = "INSERT INTO $table ($fields,game) SELECT $fields,'$game2' FROM $table WHERE game='$game1';";
			$db->query($SQL);
		}
	}  
	return $ret."</li>";
}

function mkdir_recursive($pathname) {
	is_dir(dirname($pathname)) || mkdir_recursive(dirname($pathname));
	return is_dir($pathname) || @mkdir($pathname);
}

function copyFile($source,$dest) {
	if ($source != '') {
		$source = IMAGE_PATH."/games/$source";
		$dest = IMAGE_PATH."/games/$dest";
		
		if (!is_file($source))
			$ret = t(
                'admin.task.tools_settings_copy.progress.file_not_found',
                array(
                    'source' => eHtml($source),
                    'dest' => eHtml($dest),
                )
            );
		else {
			mkdir_recursive(dirname($dest));
			if (!copy($source,$dest))
				$status = t('admin.tools_reset.status.error');
			else
				$status = t('admin.tools_reset.status.ok');
			$ret = t(
                'admin.task.tools_settings_copy.progress.copy_file',
                array(
                    'source' => eHtml($source),
                    'dest' => eHtml($dest),
                    'status' => eHtml($status),
                )
            );
		}
		return $ret . '</li>';
	}
	return '';
}

function scanCopyFiles($source,$dest) {
	global $files;
	$sourcePath = IMAGE_PATH.'/games/'.$source;
	if (!is_dir($sourcePath)) {
		return;
	}
	$d = dir($sourcePath);

	if ($d !== false) {
		while (($entry=$d->read()) !== false) {
			if (is_file(IMAGE_PATH.'/games/'.$source.'/'.$entry) && ($entry != '.') && ($entry != '..'))
				$files[] = array($source.'/'.$entry,$dest.'/'.$entry);
			if (is_dir(IMAGE_PATH.'/games/'.$source.'/'.$entry) && ($entry != '.') && ($entry != '..'))
				scanCopyFiles($source.'/'.$entry,$dest.'/'.$entry); 
		}
		$d->close();
	}
}

	if (isset($_POST['confirm'])) {
		$game1 = '';
		if (isset($_POST['game1']))
			if ($_POST['game1']!='')
				$game1 = $_POST['game1'];
		
		$game2 = '';
		if (isset($_POST['game2']))
			if ($_POST['game2']!='')
				$game2 = $_POST['game2'];
		
		$game2name = '';
		if (isset($_POST['game2name']))
			if ($_POST['game2name']!='')
				$game2name = $_POST['game2name'];
		
		echo '<ul><br />';
		check_writable();
		$game1 = valid_request($game1, false);
		$game2 = valid_request($game2, false);
		$game2name = valid_request($game2name, false);
		echo '<li>' . t('admin.task.tools_settings_copy.progress.copy_table', array('table' => eHtml('hlstats_Games'))) . ' ';
		$db->query("SELECT code FROM hlstats_Games WHERE code='$game2' LIMIT 1;");
		if ($db->num_rows()!=0) {
			echo '</ul><br /><br /><br />';
			echo '<b>' . eHtml(t('admin.task.tools_settings_copy.progress.target_gametype_exists')) . '</b><br /><br />';
		} else {
			$db->query("INSERT INTO hlstats_Games (code,name,hidden,realgame) SELECT '$game2', '$game2name', '0', realgame FROM hlstats_Games WHERE code='$game1'");
			echo eHtml(t('admin.tools_reset.status.ok')) . '</li>';
			
			$dbtables = array();
			array_push($dbtables,
				'hlstats_Actions',
				'hlstats_Awards',
				'hlstats_Ribbons',
				'hlstats_Ranks',
				'hlstats_Roles',
				'hlstats_Teams',
				'hlstats_Weapons'
				);

			foreach ($dbtables as $dbt) {
				echo '<li>' . t('admin.task.tools_settings_copy.progress.copy_table', array('table' => eHtml($dbt))) . ' ';
				echo copySettings($dbt,$game1,$game2);
			}

			echo '</ul><br /><br /><br />';	
			echo '<ul>';
				
			$files = array();

			scanCopyFiles("$game1/","$game2/");

			foreach ($files as $f) {
				echo '<li>';
				echo copyFile($f[0],$f[1]);
			}
			echo '</ul><br /><br /><br />';
			echo eHtml(t('admin.tools_reset.done')) . '<br /><br />';
		}
	} else {
		$result = $db->query("SELECT code, name FROM hlstats_Games ORDER BY code;");
		unset($games);
		$games[] = '<option value="" selected="selected">' . eHtml(t('admin.please_select')) . '</option>';
		while ($rowdata = $db->fetch_row($result))
		{
			$gameCode = eHtml($rowdata[0]);
			$gameName = eHtml($rowdata[1]);
			$games[] = '<option value="' . $gameCode . '">' . $gameCode . ' - ' . $gameName . '</option>';
		}

?>

<form method="post">
<table width="60%" align="center" border="0" cellspacing="0" cellpadding="0" class="border">

<tr>
	<td>
		<table width="100%" border="0" cellspacing="1" cellpadding="10">
		
		<tr class="bg1">
			<td class="fNormal" style="text-align:center;">

<?php echo eHtml(t('admin.task.tools_settings_copy.intro')); ?><br>
<?php echo eHtml(t('admin.task.tools_settings_copy.images_notice')); ?><p>

<input type="hidden" name="confirm" value="1" />
 <?php echo eHtml(t('admin.task.tools_settings_copy.field.existing_gametype')); ?>: 
 <select Name="game1">
 <?php foreach ($games as $g) echo $g; ?>
 </select><br />
 <?php echo eHtml(t('admin.task.tools_settings_copy.field.new_gametype_code')); ?>: 
 <input type="text" size="10" value="<?php echo eHtml(t('admin.task.tools_settings_copy.default_game_code')); ?>" name="game2"><br />
 <?php echo eHtml(t('admin.task.tools_settings_copy.field.new_gametype_name')); ?>: 
 <input type="text" size="26" value="<?php echo eHtml(t('admin.task.tools_settings_copy.default_game_name')); ?>" name="game2name"><br />
 <input type="submit" value="  <?php echo eHtml(t('admin.task.tools_settings_copy.submit_button')); ?> " />
</td>
		</tr>
		</table></td>
</tr>

</table>
</form>
<?php
	}
?>
