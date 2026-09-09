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
const scene = {map:{name:'de_dust2',projectionHash:'a',image:{width:1280,height:1024}},activeFloor:'all',query:{player:0,lens:'overview',event:'kills'}};
const workspace = {lang:'en',root:{querySelector:()=>null,setAttribute:()=>{}},_message:k=>k};
const maximum = (s,n,mode='smooth') => api.HeatmapExplorerWorkspace.prototype._scaleMaximum.call(workspace,s,n,mode);
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
