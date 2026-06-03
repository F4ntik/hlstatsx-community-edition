<?php

	if (!defined('IN_HLSTATS')) {
		die(localized_direct_access_message());
	}
	
	if (!file_exists("./updater")) {
		die(t('updater.directory_missing'));
	}
	
	define('IN_UPDATER', true);
	
	pageHeader
	(
		array ($gamename, t('updater.title'))
	);
	echo "<div class=\"warning\">\n" .
	"<span id=\"warning-header\"><strong>" . eHtml(t('updater.log_title')) . "</span></strong><br /><br />\n";
	// Check version since updater wasn't implemented until version 1.6.2
	$versioncomp = version_compare($g_options['version'], '1.6.1');
	
	if ($versioncomp === -1)
	{
		// not yet at 1.6.1
		echo eHtml(t('updater.upgrade_blocked', array('version' => $g_options['version']))) . "\n";
	}
	else if ($versioncomp === 0)
	{
		// at 1.6.1, up to 1.6.2
		include ("./updater/update161-162.php");		
	}
	else
	{
		// at 1.6.2 or higher, can update normally
		echo eHtml(t('updater.current_db_version', array('version' => $g_options['dbversion']))) . "<br />\n";
		$i = $g_options['dbversion']+1;
		
		while (file_exists ("./updater/$i.php"))
		{
			echo "<br /><em>" . eHtml(t('updater.running_update', array('version' => $i))) . "</em><br />\n";
			include ("./updater/$i.php");
			
			echo "<em>" . eHtml(t('updater.update_complete', array('version' => $i))) . "</em><br />";
			$i++;
			
		}
		
		if ($i == $g_options['dbversion']+1)
		{
			echo "<strong>" . eHtml(t('updater.already_up_to_date', array('version' => $g_options['dbversion']))) . "</strong>\n";
		}
		else
		{
			echo "<br /><strong>" . eHtml(t('updater.updated_to_version', array('version' => ($i - 1)))) . "</strong>\n";
		}
	}
	
	echo "<br /><br /><img src=\"".IMAGE_PATH."/warning.gif\" alt=\"" . eHtml(t('ui.warning')) . "\"> <span class=\"warning-header\">" . t('updater.cleanup_notice') . "</span>\n</div>\n";
?>
