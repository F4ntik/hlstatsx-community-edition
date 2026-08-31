<?php
    if ( !defined('IN_UPDATER') )
    {
        die('Do not access this file directly.');
    }

    $dbversion = 81;
    $version = "1.7.0";

    $columnResult = $db->query("SHOW COLUMNS FROM hlstats_Heatmap_Config LIKE 'floors_json'");
    if (!$db->fetch_row($columnResult))
    {
        $db->query("ALTER TABLE `hlstats_Heatmap_Config` ADD `floors_json` TEXT NULL AFTER `cropy2`");
    }

    $tableResult = $db->query("SHOW TABLE STATUS LIKE 'hlstats_Heatmap_Config'");
    $tableStatus = $db->fetch_array($tableResult);
    if ($tableStatus && strtolower($tableStatus['Engine']) !== 'innodb')
    {
        $db->query("ALTER TABLE `hlstats_Heatmap_Config` ENGINE=InnoDB");
    }

    $db->query("
        INSERT IGNORE INTO `hlstats_Options` (`keyname`, `value`, `opttype`) VALUES
        ('HeatmapExplorerBeta', '0', 2)
    ");
    $db->query("
        INSERT IGNORE INTO `hlstats_Options_Choices` (`keyname`, `value`, `text`, `isDefault`) VALUES
        ('HeatmapExplorerBeta', '0', 'Off', 1),
        ('HeatmapExplorerBeta', '1', 'Opt-in', 0),
        ('HeatmapExplorerBeta', '2', 'Default', 0)
    ");

    // Perform database schema update notification
    print "Updating database and verion schema numbers.<br />";
    $db->query("UPDATE hlstats_Options SET `value` = '$version' WHERE `keyname` = 'version'");
    $db->query("UPDATE hlstats_Options SET `value` = '$dbversion' WHERE `keyname` = 'dbversion'");
?>
