'use strict';
const assert = require('assert');
const fs = require('fs');
const crypto = require('crypto');
const {performance} = require('perf_hooks');
const api = require('../web/includes/js/heatmap-explorer.js');
const base64 = array => Buffer.from(array.buffer).toString('base64');
function fixture(pixels=[0,1,2,3], heights=[0,0,0,0], edges=[0,1,2,3], width=4,height=1) {
  const a={schemaVersion:1,map:'test',bspSha256:'a'.repeat(64),image:{width,height,sha256:'b'.repeat(64)},
    projection:{xoffset:0,yoffset:0,scale:1,flipx:0,flipy:0,rotate:0,cropx1:0,cropx2:0,cropy1:0,cropy2:0},grid:{width,height},
    nodeCount:pixels.length,edgeCount:edges.length/2,pixelData:base64(new Uint32Array(pixels)),heightData:base64(new Float32Array(heights)),edgeData:base64(new Uint32Array(edges))};
  const text=JSON.stringify(a), descriptor={url:'hlstatsimg/heatmap-surfaces/cstrike/test.json',sha256:crypto.createHash('sha256').update(text).digest('hex'),grid:a.grid,nodeCount:a.nodeCount,edgeCount:a.edgeCount};
  return {a,text,descriptor,graph:new api.HeatmapSurfaceGraph(a,descriptor)};
}
function scene(graph, rows, allowed) {
  return {map:{image:graph.image},floors:[],activeFloor:'all',summary:{personalSample:10,otherSample:20},
    surfaces:{rows,allowed:allowed||new Uint8Array(graph.pixels.length).fill(1)}};
}
function near(a,b) { assert(Math.abs(a-b)<1e-4*Math.max(1,Math.abs(b)),`${a} != ${b}`); }
async function main() {
  const f=fixture(), s=scene(f.graph,[[1,100,0,10,0]]), field=f.graph.field(s,'total','kills');
  near(field.values[0]+field.values[2],100); assert.strictEqual(field.values[4],0); assert.strictEqual(field.values[6],0);
  const more=f.graph.field(scene(f.graph,[[1,1000,0,100,0]]),'total','kills'); near(more.maxAbs,field.maxAbs*10);
  const stacked=fixture([0,0,1,1],[0,100,0,100],[0,2,1,3],2);
  const stackedField=stacked.graph.field(scene(stacked.graph,[[0,100,0,0,0],[1,40,0,0,0]]),'total','kills');
  near(stackedField.values[0]+stackedField.values[2],100);
  const excluded=stacked.graph.field(scene(stacked.graph,[[0,100,0,0,0],[1,40,0,0,0]],new Uint8Array([0,1,0,1])),'total','kills');
  near(excluded.values[0]+excluded.values[2],40);
  const signed=f.graph.field(scene(f.graph,[[0,10,0,10,0],[3,20,0,0,0]]),'difference','kills');
  assert(signed.values[0]>0 && signed.values[7]>0); near(signed.opacity[3],0.22);
  const bad=JSON.parse(f.text); bad.edgeData=base64(new Uint32Array([0,1,0,1])); assert.throws(()=>new api.HeatmapSurfaceGraph(bad,f.descriptor));
  bad.edgeData=base64(new Uint32Array([0,2,2,3])); assert.throws(()=>new api.HeatmapSurfaceGraph(bad,f.descriptor));
  bad.pixelData='A'.repeat(20000000); assert.throws(()=>new api.HeatmapSurfaceGraph(bad,f.descriptor));
  let calls=0;
  const fetcher=async()=>{calls++;return {ok:true,text:async()=>f.text};};
  const [one,two]=await Promise.all([api.loadSurfaceGraph(fetcher,crypto.webcrypto,f.descriptor),api.loadSurfaceGraph(fetcher,crypto.webcrypto,f.descriptor)]);
  assert.strictEqual(calls,1); assert.strictEqual(one,two);
  await assert.rejects(api.loadSurfaceGraph(fetcher,crypto.webcrypto,{...f.descriptor,sha256:'f'.repeat(64)}));
  // A previous geometry download finishing late must never apply its old scene.
  let release, applied=[];
  const slow=fixture([0,1],[0,0],[0,1],2); slow.descriptor.sha256=crypto.createHash('sha256').update(slow.text).digest('hex');
  const older={state:'ok',map:{image:slow.a.image},surfaces:{state:'ready',asset:slow.descriptor}};
  const newer={state:'ok',map:{image:slow.a.image},surfaces:null};
  const workspace=Object.create(api.HeatmapExplorerWorkspace.prototype);
  Object.assign(workspace,{window:{crypto:crypto.webcrypto},_sceneGeneration:0,_geometryGeneration:0,_inspectGeneration:0,
    Scene:function(p){return p;},_setStatus(){},_clearAlert(){},_showAlert(){},_showFailureActions(){},_applyScene(p){applied.push(p);},
    fetch:async url=>url==='old'?{json:async()=>older}:url==='new'?{json:async()=>newer}:{text:()=>new Promise(resolve=>{release=()=>resolve(slow.text);})}});
  const pending=workspace._loadScene('old','old');
  while(!release) await new Promise(resolve=>setImmediate(resolve));
  assert(await workspace._loadScene('new','new')); release(); assert.strictEqual(await pending,false); assert.deepStrictEqual(applied,[newer]);
  // Demonstrate why blur then clip cannot enforce a wall between two valid cells.
  const seed=new Float32Array([0,100,0,0]);
  const post=api.gaussianSmooth(seed,4,1,api.gaussianKernel1d(1.25,4));
  assert(post[2]>0 && field.values[4]===0);
  const manifest=JSON.parse(fs.readFileSync('web/hlstatsimg/heatmap-surfaces/cstrike/manifest.json','utf8'));
  assert.strictEqual(Object.keys(manifest).length,25);
  for(const [map,entry] of Object.entries(manifest)) {
    assert.strictEqual(entry.file,map+'.json');
    const text=fs.readFileSync('web/hlstatsimg/heatmap-surfaces/cstrike/'+entry.file,'utf8'),asset=JSON.parse(text);
    assert.strictEqual(crypto.createHash('sha256').update(text).digest('hex'),entry.sha256);
    new api.HeatmapSurfaceGraph(asset,{url:'hlstatsimg/heatmap-surfaces/cstrike/'+entry.file,grid:asset.grid,nodeCount:entry.nodeCount,edgeCount:entry.edgeCount});
  }
  const wallProbe={postBlurMask:post[2],topology:field.values[4]};
  console.log(JSON.stringify({tests:'PASS',preparedMaps:25,wallProbe},null,2));
  if(process.argv.includes('--benchmark')) benchmark(wallProbe);
}
function benchmark(wallProbe) {
  const output=[];
  for(const map of ['de_dust2','as_oilrig']) {
    const path=`web/hlstatsimg/heatmap-surfaces/cstrike/${map}.json`;
    if(!fs.existsSync(path)) continue;
    const text=fs.readFileSync(path,'utf8'),a=JSON.parse(text);
    const desc={url:`hlstatsimg/heatmap-surfaces/cstrike/${map}.json`,sha256:crypto.createHash('sha256').update(text).digest('hex'),grid:a.grid,nodeCount:a.nodeCount,edgeCount:a.edgeCount};
    const begin=performance.now(), graph=new api.HeatmapSurfaceGraph(a,desc),decodeMs=performance.now()-begin;
    for(const appearance of ['clear','soft']) for(const channel of ['kills','both'])
    for(const pattern of ['distributed','dense']) for(const totalWeight of [1000,100000,1000000]) {
      const occupied=Math.min(pattern==='distributed'?1000:a.nodeCount,totalWeight);
      const rows=Array.from({length:occupied},(_,i)=>[Math.floor(i*a.nodeCount/occupied),Math.floor(totalWeight/occupied)+(i<totalWeight%occupied?1:0),0,0,0]);
      if(channel==='both') rows.forEach((row,i)=>{ row[2]=Math.floor((row[1]+i%2)/2); row[1]-=row[2]; });
      const s=scene(graph,rows); let start=performance.now(), field=graph.field(s,'total',channel,appearance),fieldMs=performance.now()-start;
      const cached={field}; start=performance.now(); let check=0; for(let i=0;i<1000;i++) check+=cached.field.maxAbs;
      const cacheLookupMs=(performance.now()-start)/1000;
      const seed=new Float32Array(a.grid.width*a.grid.height); for(const r of rows) seed[graph.pixels[r[0]]]+=r[1];
      start=performance.now(); api.gaussianSmooth(seed,a.grid.width,a.grid.height,api.gaussianKernel1d(1.25,4)); const gaussianMs=performance.now()-start;
      output.push({map,appearance,channel,nodes:a.nodeCount,edges:a.edgeCount,pattern,occupied,totalWeight,decodeMs:+decodeMs.toFixed(2),fieldMs:+fieldMs.toFixed(2),cacheLookupMs:+cacheLookupMs.toFixed(6),gaussianMs:+gaussianMs.toFixed(2),maxAbs:field.maxAbs});
      assert(check>=0);
    }
  }
  const report={benchmark:output,wallProbe,notes:'Integer aggregated count weights, not database row throughput or browser FPS. Clear 8 steps; Soft 24 steps; alpha .18 for both. Both splits total weight across kill/death channels. Cached lookup excludes actual WebGL redraw. Gaussian is unconstrained blur reference.'};
  console.log(JSON.stringify(report,null,2));
  const out=process.argv.indexOf('--output'); if(out>=0) fs.writeFileSync(process.argv[out+1],JSON.stringify(report,null,2)+'\n');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
