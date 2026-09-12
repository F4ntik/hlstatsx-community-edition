<?php
define('IN_HLSTATS', true);
require_once __DIR__ . '/../web/includes/heatmap_points.php';
function surface_check($value, string $label): void { if (!$value) throw new RuntimeException($label); }
$asset = json_decode(file_get_contents(__DIR__ . '/../web/hlstatsimg/heatmap-surfaces/cstrike/de_dust2.json'), true);
$config = array_merge($asset['projection'], array('game'=>'cstrike','map'=>'de_dust2','floors'=>array()));
$image = array('source'=>'heatmaps/src','width'=>1024,'height'=>768);
$loaded = heatmap_surface_load($config, $image, 'de_dust2', 'all');
surface_check($loaded['state'] === 'ready', 'real asset identity: ' . $loaded['state']);
$rounded = $config; $rounded['scale'] = 5.33333;
surface_check(heatmap_surface_load($rounded,$image,'de_dust2','all')['state'] === 'ready','SQL FLOAT round trip');
$rounded['scale'] = 5.334;
surface_check(heatmap_surface_load($rounded,$image,'de_dust2','all')['state'] === 'identity_mismatch','meaningful scale change');
$changed = $config; $changed['xoffset']++;
surface_check(heatmap_surface_load($changed,$image,'de_dust2','all')['state'] === 'identity_mismatch','projection mismatch');
$changed = $image; $changed['width']++;
surface_check(heatmap_surface_load($config,$changed,'de_dust2','all')['state'] === 'identity_mismatch','image mismatch');
surface_check(heatmap_surface_load($config,$image,'missing_test','all')['state'] === 'missing_asset','missing fallback');
surface_check(heatmap_surface_path($config,'../de_dust2') === null,'path traversal');
$floor = array('id'=>'upper','z_min'=>40,'z_max'=>100);
surface_check(heatmap_surface_floor_allowed(0.0,0,0,array($floor),'upper'),'float ground + event band overlap');
surface_check(!heatmap_surface_floor_allowed(200.0,0,0,array($floor),'upper'),'excluded height');
$floor['blocked'] = array(array(array(-1,-10),array(1,-10),array(1,10),array(-1,10)));
surface_check(!heatmap_surface_floor_allowed(0.0,0,0,array($floor),'all',2,2),'all floors blocked wall');
surface_check(!heatmap_surface_floor_allowed(0.0,2,0,array($floor),'all',2,2),'thin wall touches cell');
$regionsFloor = array('id'=>'main','z_min'=>0,'z_max'=>100,'regions'=>array(
    array(array(-1,-1),array(2,-1),array(2,11),array(-1,11)),
    array(array(3,-1),array(11,-1),array(11,11),array(3,11))));
surface_check(!heatmap_surface_floor_allowed(0.0,5,5,array($regionsFloor),'all',5,5),'region union does not bridge thin excluded gap');
$regionsFloor['regions'] = array(array(array(-1,-1),array(2,-1),array(2,8),array(3,8),array(3,-1),array(11,-1),array(11,11),array(-1,11)));
surface_check(!heatmap_surface_floor_allowed(0.0,5,5,array($regionsFloor),'main',5,5),'concave region notch excludes intersecting cell');
$regionsFloor['regions'] = array(array(array(0,0),array(10,0),array(10,10),array(0,10)));
surface_check(heatmap_surface_floor_allowed(0.0,5,5,array($regionsFloor),'main',5,5),'boundary-aligned contained cell remains allowed');
$s = array('image'=>array('width'=>2,'height'=>1),'surfaces'=>array('state'=>'ready',
    'asset'=>array('grid'=>array('width'=>2,'height'=>1),'nodeCount'=>3,'edgeCount'=>0),
    'allowedData'=>base64_encode("\1\1\1"),'_allowed'=>"\1\1\1",'_starts'=>array(0=>0,1=>2),
    '_pixels'=>pack('V*',0,0,1),'_heights'=>pack('g*',0,100,0),'rows'=>array(),
    'diagnostics'=>array('candidate'=>0,'assigned'=>0,'missingZ'=>0,'ambiguous'=>0,'offSurface'=>0,'excluded'=>0)));
for($i=0;$i<10;$i++) heatmap_surface_accumulate($s,array('status'=>'valid','value'=>36),0,0,'kills',true);
heatmap_surface_accumulate($s,array('status'=>'valid','value'=>136),0,0,'deaths',false);
heatmap_surface_accumulate($s,array('status'=>'missing','value'=>null),0,0,'kills',false);
heatmap_surface_accumulate($s,array('status'=>'valid','value'=>500),0,0,'kills',false);
surface_check($s['surfaces']['rows'][0] === array(0,10,0,10,0),'counted personal kill weight');
surface_check($s['surfaces']['rows'][1] === array(1,0,1,0,0),'stacked death surface');
surface_check($s['surfaces']['diagnostics']['missingZ']===1 && $s['surfaces']['diagnostics']['offSurface']===1,'explicit exclusions');
$s['surfaces']['_heights'] = pack('g*',0,40,0);
heatmap_surface_accumulate($s,array('status'=>'valid','value'=>60),0,0,'kills',false);
surface_check($s['surfaces']['diagnostics']['ambiguous']===1,'no ambiguous snap');
$s['surfaces']['_allowed'][2]="\0";
heatmap_surface_accumulate($s,array('status'=>'valid','value'=>36),1,0,'kills',false);
surface_check($s['surfaces']['diagnostics']['excluded']===1,'excluded floor count');
$final=heatmap_surface_finalize($s['surfaces'],false);
surface_check($final['state']==='ready','coverage 11/15 passes');
for($i=0;$i<5;$i++) heatmap_surface_accumulate($s,array('status'=>'missing','value'=>null),1,0,'kills',false);
surface_check(heatmap_surface_finalize($s['surfaces'],false)['state']==='low_coverage','low coverage visible fallback');
$overflow=heatmap_surface_finalize($s['surfaces'],true);
surface_check($overflow['rows']===array() && $overflow['state']==='low_coverage','overflow no partial surface rendering');
$cohort = $loaded;
$cohort['rows'] = array(array(0,100,0,0,0));
$cohort['diagnostics'] = array('candidate'=>110,'assigned'=>100,'missingZ'=>10,'ambiguous'=>0,'offSurface'=>0,'excluded'=>0);
surface_check(heatmap_surface_finalize($cohort,false)['state']==='ready','global cohort coverage ready');
surface_check(heatmap_surface_finalize($cohort,false,'me',10)['state']==='low_coverage','personal missingZ does not render blank heat');
surface_check(heatmap_surface_finalize($cohort,false,'difference',10)['state']==='low_coverage','difference requires personal coverage');
$cohort['rows'][0][3] = 100;
surface_check(heatmap_surface_finalize($cohort,false,'difference',100)['state']==='low_coverage','difference requires other population coverage');
$manifest=json_decode(file_get_contents(__DIR__.'/../web/hlstatsimg/heatmap-surfaces/cstrike/manifest.json'),true);
surface_check(count($manifest)===25,'all25 manifest');
foreach($manifest as $map=>$entry) {
    $a=json_decode(file_get_contents(__DIR__.'/../web/hlstatsimg/heatmap-surfaces/cstrike/'.$entry['file']),true);
    $c=array_merge($a['projection'],array('game'=>'cstrike','map'=>$map,'floors'=>array()));
    $im=array('source'=>'heatmaps/src','width'=>$a['image']['width'],'height'=>$a['image']['height']);
    surface_check(heatmap_surface_load($c,$im,$map,'all')['state']==='ready','all25 PHP loader: '.$map);
}
echo "heatmap surfaces PHP smoke ok (25 prepared maps)\n";
