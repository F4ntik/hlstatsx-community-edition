<?php
    if ( !defined('IN_UPDATER') )
    {
        die('Do not access this file directly.');
    }

    $dbversion = 82;
    $version = "1.7.0";

    $indexResult = $db->query("SHOW INDEX FROM hlstats_Events_Teamkills WHERE Key_name = 'mapEventTime'", 0, 1);
    $indexRows = $db->calc_rows($indexResult);
    if ($indexRows < 1)
    {
        print "Adding heatmap Teamkills index.<br />";
        $db->query("ALTER TABLE hlstats_Events_Teamkills ADD KEY `mapEventTime` (`map`, `eventTime`)");
    }

    // Perform database schema update notification
    print "Updating database and verion schema numbers.<br />";
    $db->query("UPDATE hlstats_Options SET `value` = '$version' WHERE `keyname` = 'version'");
    $db->query("UPDATE hlstats_Options SET `value` = '$dbversion' WHERE `keyname` = 'dbversion'");
?>
