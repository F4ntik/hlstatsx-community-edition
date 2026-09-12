'use strict';
const assert = require('assert');
const fs = require('fs');
const api = require('../web/includes/js/heatmap-explorer.js');
const vm = require('vm');
const adminContext = {module:{exports:{}},window:{addEvent:()=>{}},console};
vm.runInNewContext(fs.readFileSync(__dirname+'/../web/includes/js/heatmap.js','utf8'),adminContext);
const admin = adminContext.module.exports;
for (const seconds of [0,1736115901,1767651900,1788813000]) assert.strictEqual(api.utcInputSeconds(api.utcInputValue(seconds)),seconds);
for (const value of ['2026-02-30T12:00','2026-09-08T24:00','2026-09-08','1788813000','2026-09-08T12:00+03:00']) assert.throws(()=>api.utcInputSeconds(value));
assert.strictEqual(api.utcInputSeconds('2026-03-29T02:30'),Date.UTC(2026,2,29,2,30)/1000,'UTC unaffected by local DST');
const input = new Float32Array([4,0,0,0,0,0,0]);
const mask = new Uint8Array([1,1,0,1,1,1,1]);
const field = api.gaussianSmooth(input,7,1,api.gaussianKernel1d(1.25,4),mask);
assert(field[1]>0); assert.strictEqual(field[2],0); assert.strictEqual(field[3],0,'no smoothing across a masked gap');
assert.deepStrictEqual(Array.from(input),[4,0,0,0,0,0,0],'raw data immutable');
assert(api.regionContains([[0,0],[10,0],[10,10],[0,10]],0,5));
assert(!api.regionContains([[0,0],[10,0],[10,10],[0,10]],11,5));
const wallScene={floors:[{id:'a',blocked:[[[21,0],[22,0],[22,10],[21,10]]]}],activeFloor:'a',grid:{width:7,height:1,bucketSize:10},cellSummary:()=>null};
const wallMask=api.regionGridMask(wallScene);
assert.deepStrictEqual(Array.from(wallMask),[1,1,0,1,1,1,1],'thin wall intersects bucket even without its center');
const wallField=api.gaussianSmooth(input,7,1,api.gaussianKernel1d(1.25,4),wallMask);
assert.strictEqual(wallField[3],0,'thin wall stops cross-wall smoothing');
const dual = api.presentationField({values:new Float32Array([1,0,5]),secondaryValues:new Float32Array([0,2,5])},3,1,false,false,null,'clear');
assert.deepStrictEqual(Array.from(dual.values),[1,0,0,2,5,5],'Both retains independent kill/death weights, including overlap');
assert.strictEqual(dual.maxAbs,5,'Both shares a channel-count scale instead of summing overlap');
const graph=Object.create(api.HeatmapSurfaceGraph.prototype);
Object.assign(graph,{grid:{width:21,height:1},image:{width:21,height:1},pixels:Uint32Array.from({length:21},(_,i)=>i),edges:Uint32Array.from({length:40},(_,i)=>Math.floor(i/2)+(i%2))});
const graphScene={map:{image:graph.image},floors:[],activeFloor:'all',summary:{personalSample:1,otherSample:1},surfaces:{allowed:new Uint8Array(21).fill(1),rows:[[10,1,0,1,0],[20,0,1,0,0]]}};
const compact=graph.field(graphScene,'total','kills','clear'),soft=graph.field(graphScene,'total','kills','soft'),both=graph.field(graphScene,'total','both','clear');
assert(compact.maxAbs>soft.maxAbs,'compact spread concentrates isolated event');
assert(compact.values[0]<soft.values[0],'intermediate compact spread has a weaker distant fringe than Soft');
assert(soft.values[0]>0,'soft option retains broader spread');
assert(both.values[20]>0 && both.values[41]>0 && both.values[1]===0,'Both keeps channels separate through topology diffusion');
assert.deepStrictEqual(Array.from(graph.field(graphScene,'difference','kills','clear').values),Array.from(graph.field(graphScene,'difference','kills','soft').values),'Difference presentation is unchanged by appearance preference');
const plane=Object.create(api.HeatmapSurfaceGraph.prototype),planeEdges=[];
for(let y=0;y<21;y++)for(let x=0;x<21;x++){const n=y*21+x;if(x<20)planeEdges.push(n,n+1);if(y<20)planeEdges.push(n,n+21);}
Object.assign(plane,{grid:{width:21,height:21},image:{width:21,height:21},pixels:Uint32Array.from({length:441},(_,i)=>i),edges:Uint32Array.from(planeEdges)});
const single=plane.field({...graphScene,map:{image:plane.image},surfaces:{allowed:new Uint8Array(441).fill(1),rows:[[220,1,0,0,0]]}},'total','kills','clear');
for(let offset=0;offset<8;offset++)assert(single.values[(220+offset)*2]>=single.values[(221+offset)*2],'compact isolated spot has no alternating brighter parity rings');
const scene = {map:{name:'de_dust2',projectionHash:'a',image:{width:1280,height:1024}},activeFloor:'all',query:{player:0,lens:'overview',event:'kills'}};
const workspace = {lang:'en',root:{querySelector:()=>null,setAttribute:()=>{}},_message:k=>k};
const maximum = (s,n,mode='smooth') => api.HeatmapExplorerWorkspace.prototype._scaleMaximum.call(workspace,s,n,mode);
for (const lang of ['ru','en']) {
    const w=Object.create(api.HeatmapExplorerWorkspace.prototype);
    Object.assign(w,{lang,_message:k=>k,_nodes:{status:{textContent:''}}});
    w._setCoverageStatus({state:'ok',query:{lens:'difference'},summary:{sourceRows:175,personalSample:5,otherSample:170},
      coverage:{xyCoverage:1},surfaces:{state:'low_coverage',diagnostics:{assigned:166,candidate:175}}});
    assert(!w._nodes.status.textContent.includes('166/175'),'overall assignment must not obscure missing selected population');
    assert(w._nodes.status.textContent.includes(lang==='ru'?'недостаточно точек с надёжной привязкой':'too few reliably located positions'));
}
assert.strictEqual(maximum(scene,12),12);
workspace._scaleReference=workspace._scaleCurrent;
assert.strictEqual(maximum({...scene,query:{...scene.query,from:123,to:456}},2),12,'same metric period retains denominator');
assert.strictEqual(maximum({...scene,query:{...scene.query,event:'deaths'}},2),2,'channel releases lock');
workspace._scaleReference=workspace._scaleCurrent;
assert.strictEqual(maximum(scene,4,'cells'),4,'view releases lock');
for (const mode of ['cells','points']) {
    const w = Object.create(api.HeatmapExplorerWorkspace.prototype);
    let renderOptions;
    Object.assign(w,{lang:'en',root:workspace.root,_message:k=>k,_displayMode:mode,_nodes:{stage:{clientWidth:800,clientHeight:640,style:{}},image:{}},Renderer:function(root,s,options){
        renderOptions=options;
        this.mount=()=>options.scaleMaximum(1,'smooth');
        this.setDisplayMode=m=>options.scaleMaximum(2,m);
    }});
    w._scaleMaximum(scene,12,mode);w._scaleReference=w._scaleCurrent;
    w._createRenderer(scene);
    assert(w._scaleReference, mode+' lock survives interim mount frames');
    assert.strictEqual(renderOptions.scaleMaximum(3,mode),12);
}
const report=fs.readFileSync(__dirname+'/../docs/audits/modern-heatmap-explorer/bsp-registration-20260907/registration-report.json','utf8');
assert(Math.abs(admin.HeatmapRegistrationReport.parse(report).config.scale-5.078819835144061)<1e-12,'import preserves scale precision');
for (const mutate of [r=>r.candidate_config.scale=0,r=>r.candidate_config.flipx='1',r=>r.candidate_config.xoffset='alert(1)',r=>r.candidate_config.rotate=8,r=>r.served_size=[0,10]]) {
    const r=JSON.parse(report);mutate(r);assert.throws(()=>admin.HeatmapRegistrationReport.parse(JSON.stringify(r)));
}
console.log('heatmap presentation smoke ok');
