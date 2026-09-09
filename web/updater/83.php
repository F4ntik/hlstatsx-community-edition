<?php
if (!defined('IN_UPDATER')) {
    die('Do not access this file directly.');
}

$dbversion = 83;
$version = '1.7.0';

print "Widening administrator password storage.<br />";
if (!$db->query("ALTER TABLE hlstats_Users MODIFY COLUMN password varchar(255) NOT NULL default ''", false)) {
    die('Could not widen administrator password storage.');
}

print "Updating database and version schema numbers.<br />";
$db->query("UPDATE hlstats_Options SET `value` = '$version' WHERE `keyname` = 'version'");
$db->query("UPDATE hlstats_Options SET `value` = '$dbversion' WHERE `keyname` = 'dbversion'");
?>
