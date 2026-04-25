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

	if (isset($_POST['confirm'])){
		$convert_to = DB_COLLATE;
		$character_set = DB_CHARSET;

		if ($_POST['printonly'] > 0) {
			echo '<strong>' . eHtml(t('admin.task.tools_resetdbcollations.print_header')) . '</strong><br><br>';
			echo "ALTER DATABASE `".DB_NAME."` DEFAULT CHARACTER SET $character_set COLLATE $convert_to;<br>";

			$rs_tables = $db->query('SHOW TABLES') or die("DB:> Cannot SHOW TABLES");

			while ($row_tables = $db->fetch_row($rs_tables))
			{
				$table = $db->escape($row_tables[0]);

				echo "ALTER TABLE `$table` CONVERT TO CHARACTER SET $character_set COLLATE $convert_to;<br>";

				$rs = $db->query("SHOW FULL FIELDS FROM `$table` WHERE collation is not null AND collation <> '{$convert_to}'") or die ("DB:> Cannot SHOW FULL FIELDS");

				while ($row = mysqli_fetch_assoc($rs))
				{
					if ($row['Collation'] == '')
						continue;
					if ( strtolower($row['Null']) == 'yes' )
						$nullable = ' NULL ';
					else
						$nullable = ' NOT NULL';
					if ( $row['Default'] === NULL && $nullable == ' NOT NULL' )
						$default = " DEFAULT ''";
					else if ( $row['Default'] === NULL )
						$default = ' DEFAULT NULL';
					else if ($row['Default']!='')
						$default = " DEFAULT '".$db->escape($row['Default'])."'";
					else
						$default = '';
					
					$field = $db->escape($row['Field']);
					echo "ALTER TABLE `$table` CHANGE `$field` `$field` $row[Type] CHARACTER SET $character_set COLLATE $convert_to $nullable $default;<br>";
				}
			}
		} else {
			echo eHtml(t('admin.task.tools_resetdbcollations.progress.start', array('charset' => $character_set))) . "<ul>\n";
			set_time_limit(0);
			echo '<li>' . eHtml(t('admin.task.tools_resetdbcollations.progress.change_database', array('db_name' => DB_NAME)));
			$db->query("ALTER DATABASE `".DB_NAME."` DEFAULT CHARACTER SET $character_set COLLATE $convert_to;") or die("DB:> Cannot ALTER DATABASE");
			echo eHtml(t('admin.tools_reset.status.ok'));
			$rs_tables = $db->query('SHOW TABLES') or die("DB:> Cannot SHOW TABLES");
			while ($row_tables = $db->fetch_row($rs_tables))
			{
				$table = $db->escape($row_tables[0]);

				echo '<li>' . eHtml(t('admin.task.tools_resetdbcollations.progress.convert_table', array('table' => $table)));

				$db->query("ALTER TABLE `$table` CONVERT TO CHARACTER SET $character_set COLLATE $convert_to;");

				echo eHtml(t('admin.tools_reset.status.ok'));

				$rs = $db->query("SHOW FULL FIELDS FROM `$table` WHERE collation is not null AND collation <> '{$convert_to}'") or die("DB:> Cannot SHOW FULL FIELDS");

				while ($row=mysqli_fetch_assoc($rs))
				{
					if ($row['Collation'] == '')
						continue;
					if ( strtolower($row['Null']) == 'yes' )
						$nullable = ' NULL ';
					else
						$nullable = ' NOT NULL';
					if ( $row['Default'] === NULL && $nullable == ' NOT NULL' )
						$default = " DEFAULT ''";
					else if ( $row['Default'] === NULL )
						$default = ' DEFAULT NULL';
					else if ($row['Default']!='')
						$default = " DEFAULT '".$db->escape($row['Default'])."'";
					else
						$default = '';
					
					$field = $db->escape($row['Field']);
					echo '<li>' . eHtml(t('admin.task.tools_resetdbcollations.progress.convert_column', array('table' => $table, 'field' => $field)));
					$db->query("ALTER TABLE `$table` CHANGE `$field` `$field` $row[Type] CHARACTER SET $character_set COLLATE $convert_to $nullable $default;");
					echo eHtml(t('admin.tools_reset.status.ok'));
				}
			}
			echo '</ul>';
			
			echo eHtml(t('admin.tools_reset.done')) . "<p>";
		}
		
    } else {
        
?>        

<form method="POST">
<table width="60%" align="center" border=0 cellspacing=0 cellpadding=0 class="border">

<tr>
    <td>
        <table width="100%" border=0 cellspacing=1 cellpadding=10>
        
        <tr class="bg1">
            <td class="fNormal">

<?php echo eHtml(t('admin.task.tools_resetdbcollations.intro')); ?><br><br>
<?php echo eHtml(t('admin.task.tools_resetdbcollations.backup_notice')); ?><br><br><br>



<input type="hidden" name="confirm" value="1">
<input type="radio" name="printonly" value="0" checked> <?php echo eHtml(t('admin.task.tools_resetdbcollations.run_commands')); ?><br>
<input type="radio" name="printonly" value="1"> <?php echo eHtml(t('admin.task.tools_resetdbcollations.print_commands')); ?><br>
<center><input type="submit" value="<?php echo eHtml(t('admin.task.tools_resetdbcollations.submit_button')); ?>"></center>
</td>
        </tr>
        
        </table></td>
</tr>

</table>
</form>

<?php
    }
?>    
    
