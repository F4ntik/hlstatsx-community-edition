<?php
require '/heatmaps/config.inc.php';
require '/heatmaps/heatmap.class.php';

$heat = new Heatmap();
$heat->init();
$heat->generate('cstrike', 'de_dust2', 'kill');
