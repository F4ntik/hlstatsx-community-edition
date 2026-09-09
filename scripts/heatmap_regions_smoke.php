<?php
define('IN_HLSTATS', true);
require __DIR__ . '/../web/includes/heatmap_points.php';
function check_region($ok, $message) { if (!$ok) throw new RuntimeException($message); }
$left = array(array(0,0),array(10,0),array(10,10),array(0,10));
$right = array(array(20,0),array(30,0),array(30,10),array(20,10));
$floor = array('id'=>'a','label_en'=>'A','label_ru'=>'А','z_min'=>0,'z_max'=>100,'regions'=>array($left));
$other = array_replace($floor, array('id'=>'b','regions'=>array($right)));
$parsed = heatmap_parse_floor_array(array($floor, $other));
check_region(count($parsed) === 2, 'disjoint same-height regions allowed');
foreach (array(array(0,0),array(10,10),array(5,5)) as $p) check_region(heatmap_assign_floor(20,$parsed,$p[0],$p[1]) === 'a','boundary included');
check_region(heatmap_assign_floor(20,$parsed,25,5) === 'b','second region');
check_region(heatmap_assign_floor(20,$parsed,15,5) === null,'gap unassigned');
check_region(heatmap_assign_floor(100,$parsed,5,5) === null,'upper Z exclusive');
$wall = array(array(4,0),array(6,0),array(6,10),array(4,10));
$walled = heatmap_parse_floor_array(array(array_replace($floor,array('blocked'=>array($wall)))));
check_region(heatmap_assign_floor(20,$walled,4,5) === null,'wall boundary excluded');
check_region(heatmap_assign_floor(20,$walled,5,5) === null,'wall interior excluded');
check_region(heatmap_assign_floor(20,$walled,3,5) === 'a','beside wall retained');
check_region(heatmap_parse_floor_config(heatmap_floor_config_json($walled)) === $walled,'walls survive saved settings');
$scene = array('floors'=>array($floor),'floorCounts'=>array('a'=>10),'validXY'=>100,'validZ'=>100,'query'=>array('lang'=>'en'),'config'=>array('scale'=>1,'xoffset'=>0,'yoffset'=>0,'flipx'=>0,'flipy'=>0,'rotate'=>0));
check_region(heatmap_scene_floor_metadata($scene,0.1)[0]['available'], 'a small region is not low Z coverage');
$scene['validZ'] = 10;
check_region(!heatmap_scene_floor_metadata($scene,0.1)[0]['available'], 'missing Z still blocks a region');
$bad = array(
    array(array(0,0),array(10,10),array(0,10),array(10,0)),
    array(array(0,0),array(1,1),array(2,2)),
    array(array(0,0),array(10,0),array(0,0)),
);
foreach ($bad as $polygon) {
    try { heatmap_validate_regions(array($polygon)); throw new RuntimeException('accepted invalid polygon'); }
    catch (InvalidArgumentException $expected) {}
}
try { heatmap_parse_floor_array(array($floor,array_replace($other,array('regions'=>array($left))))); throw new RuntimeException('accepted ambiguous floors'); }
catch (InvalidArgumentException $expected) {}
// Verify the inspector predicate against PHP membership using the real database.
if (isset($argv[1])) {
    require $argv[1] . '/config.php';
    $container = require $argv[1] . '/bootstrap.php'; $pdo = $container->get('pdo');
    $statement = $pdo->prepare('SELECT (' . heatmap_regions_sql(array($left),'hef.pos_x','hef.pos_y') . ' AND NOT ' . heatmap_regions_sql(array($wall),'hef.pos_x','hef.pos_y') . ') FROM (SELECT :x AS pos_x,:y AS pos_y) AS hef');
    for ($x=-1;$x<=11;$x++) for ($y=-1;$y<=11;$y++) {
        $statement->execute(array('x'=>$x,'y'=>$y));
        check_region((bool)$statement->fetchColumn() === (heatmap_assign_floor(20,$walled,$x,$y) === 'a'), 'wall SQL/PHP parity');
    }
    foreach (array($left, array(array(-5,0),array(12,3),array(4,12),array(2,5))) as $polygon) {
        $sql = 'SELECT ' . heatmap_regions_sql(array($polygon),'hef.pos_x','hef.pos_y') . ' AS member FROM (SELECT :x AS pos_x,:y AS pos_y) AS hef';
        $statement = $pdo->prepare($sql);
        for ($x=-6;$x<=13;$x++) for($y=-1;$y<=13;$y++) {
            $statement->execute(array('x'=>$x,'y'=>$y));
            check_region((bool)$statement->fetchColumn() === heatmap_region_contains($polygon,$x,$y),"SQL/PHP mismatch at $x,$y");
        }
    }
}
echo "heatmap regions smoke ok\n";
