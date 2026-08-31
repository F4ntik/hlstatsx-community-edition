const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('web/includes/js/heatmap.js', 'utf8');
const context = {
  console,
  module: {exports: {}},
  window: {addEvent() {}},
  SqueezeBox: {assign() {}},
  $$() { return []; },
  setupInlineHeatmaps() {},
};
vm.runInNewContext(source, context, {filename: 'heatmap.js'});

const projection = context.module.exports.HeatmapProjection;
assert.ok(projection, 'heatmap projection helpers should be exportable for smoke tests');
const adminPayload = context.module.exports.HeatmapAdminPayload;
assert.ok(adminPayload, 'heatmap admin payload helper should be exportable for smoke tests');
const original = {x: 17, y: -29};

for (let steps = 0; steps < 4; steps += 1) {
  const rotated = projection.rotate(original.x, original.y, steps);
  const restored = projection.unrotate(rotated.x, rotated.y, steps);
  assert.strictEqual(restored.x, original.x, `unrotate x should invert rotate(${steps})`);
  assert.strictEqual(restored.y, original.y, `unrotate y should invert rotate(${steps})`);

  let fourth = rotated;
  for (let index = 1; index < 4; index += 1) {
    fourth = projection.rotate(fourth.x, fourth.y, steps);
  }
  assert.strictEqual(fourth.x, original.x, `R^4 x should be identity for step ${steps}`);
  assert.strictEqual(fourth.y, original.y, `R^4 y should be identity for step ${steps}`);
}

const identity = {game: 'cstrike', map: 'de_dust2'};
const controls = {overviewText: '', xoffset: '0', yoffset: '0', scale: '1', flipy: 0};
const plain = value => JSON.parse(JSON.stringify(value));
assert.deepStrictEqual(
  plain(adminPayload.build('preview', identity, controls, false)),
  {action: 'preview', game: 'cstrike', map: 'de_dust2'},
  'stored-config load should not send default controls that override DB projection'
);
assert.deepStrictEqual(
  plain(adminPayload.build('preview', identity, controls, true)),
  {action: 'preview', game: 'cstrike', map: 'de_dust2', overviewText: '', xoffset: '0', yoffset: '0', scale: '1', flipy: 0},
  'edit preview should send current controls'
);
assert.match(source, /bindClick\('\[data-heatmap-admin-load\]', requestStoredConfig\);/, 'Load button should request stored config');
assert.match(source, /mapSelect\.onchange = requestStoredConfig;/, 'map change should request stored config');
assert.match(source, /if \(activeMap\(\)\) \{\s*requestStoredConfig\(\);/, 'initial wizard load should request stored config');
assert.match(source, /bindClick\('\[data-heatmap-admin-preview\]', function\(\) \{ request\('preview'\); \}\);/, 'Preview button should send current controls');
assert.match(source, /request\('preview', token\);/, 'scheduled preview should send current controls');

console.log('heatmap JS projection smoke ok');

const explorerSource = fs.readFileSync('web/includes/js/heatmap-explorer.js', 'utf8');
const explorerContext = {module: {exports: {}}, window: {}};
vm.runInNewContext(explorerSource, explorerContext, {filename: 'heatmap-explorer.js'});
const explorerApi = explorerContext.module.exports;
assert.deepStrictEqual(
  Object.keys(explorerApi).sort(),
  ['HeatmapExplorerCamera', 'HeatmapExplorerScene', 'HeatmapExplorerUrlState', 'HeatmapGlRenderer'].sort(),
  'heatmap explorer should expose the four frozen constructors'
);
for (const name of Object.keys(explorerApi)) {
  assert.strictEqual(explorerContext.window[name], explorerApi[name], `${name} should attach to window`);
}

console.log('heatmap explorer export smoke ok');

const {
  HeatmapExplorerScene,
  HeatmapExplorerCamera,
  HeatmapExplorerUrlState,
  HeatmapGlRenderer,
} = explorerApi;

function explorerSceneFixture(overrides = {}) {
  const payload = {
    schemaVersion: 2,
    state: 'ok',
    query: {
      game: 'cstrike',
      map: 'de_dust2',
      player: 42,
      from: 1785456000,
      to: 1788048000,
      event: 'kills',
      lens: 'difference',
      floor: 'all',
      lang: 'en',
    },
    map: {
      game: 'cstrike',
      realgame: 'cstrike',
      name: 'de_dust2',
      image: {url: './map.jpg', width: 40, height: 30},
      projectionHash: 'a4dd45e46d84a12f',
      floorConfigHash: '97d170e1550eee4a',
    },
    floors: [],
    activeFloor: 'all',
    grid: {
      bucketSize: 8,
      width: 4,
      height: 3,
      fields: ['cell', 'x', 'y', 'kills', 'deaths'],
    },
    layers: {
      total: [
        ['c0.0', 0, 0, 5, 1],
        ['c2.0', 2, 0, 2, 3],
        ['c1.1', 1, 1, 0, 2],
        ['c3.2', 3, 2, 1, 0],
      ],
      me: [
        ['c0.0', 0, 0, 3, 1],
        ['c2.0', 2, 0, 1, 1],
        ['c1.1', 1, 1, 0, 1],
        ['c3.2', 3, 2, 1, 0],
      ],
      others: [
        ['c0.0', 0, 0, 2, 0],
        ['c2.0', 2, 0, 1, 2],
        ['c1.1', 1, 1, 0, 1],
        ['c3.2', 3, 2, 0, 0],
      ],
    },
    comparison: {
      fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
      bins: [
        ['c0.0', 0, 0, -0.0666666667, 0, 5],
        ['c2.0', 2, 0, -0.1333333333, 0, 2],
        ['c1.1', 1, 1, 0, 0, 0],
        ['c3.2', 3, 2, 0.2, 0, 1],
      ],
      personalSample: 5,
      otherSample: 3,
    },
    coverage: {sourceRows: 8, candidate: 8, validXY: 8},
    summary: {rowsRead: 8, sourceRows: 8, personalSample: 5, otherSample: 3},
    warnings: [],
    fallback: {
      v1: 'heatmap_points.php?game=cstrike&map=de_dust2',
      jpeg: './map-kill.jpg',
      thumbnail: './map-kill-thumb.jpg',
    },
  };
  return Object.assign(payload, overrides);
}

const validScene = new HeatmapExplorerScene(explorerSceneFixture());
const totalKills = validScene.dense('total', 'kills');
assert.strictEqual(Object.prototype.toString.call(totalKills.values), '[object Float32Array]', 'dense values should be Float32Array');
assert.strictEqual(totalKills.values.length, 12, 'dense values should cover the full grid');
assert.deepStrictEqual(Array.from(totalKills.values), [5, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
assert.deepStrictEqual(Array.from(totalKills.occupied, cell => cell.cell), ['c0.0', 'c2.0', 'c3.2']);
assert.strictEqual(totalKills.maxAbs, 5);
assert.strictEqual(totalKills.opacity[0], 1);
assert.strictEqual(totalKills.opacity[1], 0);
assert.deepStrictEqual(Array.from(validScene.dense('total', 'both').values), [6, 0, 5, 0, 0, 2, 0, 0, 0, 0, 0, 1]);
assert.deepStrictEqual(Array.from(validScene.dense('me', 'kills').values), [3, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
assert.deepStrictEqual(Array.from(validScene.dense('others', 'deaths').values), [0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0]);

const difference = validScene.dense('difference', 'kills');
assert.deepStrictEqual(Array.from(difference.values), [Math.fround(-0.0666666667), 0, Math.fround(-0.1333333333), 0, 0, 0, 0, 0, 0, 0, 0, Math.fround(0.2)]);
assert.strictEqual(difference.maxAbs, 0.2);
assert.strictEqual(difference.opacity[0], 1, 'three personal events should not be capped');
assert.strictEqual(difference.opacity[2], Math.fround(0.22), 'low-sample comparison should use the exact cap');
assert.strictEqual(difference.opacity[11], Math.fround(0.22));
assert.deepStrictEqual(Array.from(difference.occupied, cell => cell.cell), ['c0.0', 'c2.0', 'c3.2']);
assert.deepStrictEqual(plain(validScene.cellSummary('c0.0')), {
  cell: 'c0.0',
  gridX: 0,
  gridY: 0,
  total: {kills: 5, deaths: 1},
  me: {kills: 3, deaths: 1},
  others: {kills: 2, deaths: 0},
  comparison: {killDelta: -0.0666666667, deathDelta: 0, sample: 5},
});
assert.strictEqual(validScene.cellSummary('c1.1').total.kills, 0);
assert.strictEqual(validScene.cellSummary('c1.1').comparison.sample, 0);
assert.strictEqual(validScene.cellSummary('c9.9'), null);

const view = {left: 100, top: 50, width: 400, height: 300};
const pointerCell = validScene.cellFromPointer(500, 50, view, {zoom: 2, panX: -100, panY: -50});
assert.strictEqual(pointerCell.cell, 'c2.0', 'pointer mapping should account for shared pan and zoom');
assert.strictEqual(validScene.cellFromPointer(99, 50, view, {zoom: 1, panX: 0, panY: 0}), null);
assert.strictEqual(validScene.nextOccupied('c0.0', 'right', 'total', 'kills').cell, 'c2.0');
assert.strictEqual(validScene.nextOccupied('c3.2', 'up', 'total', 'kills').cell, 'c2.0');
assert.strictEqual(validScene.nextOccupied('c9.9', 'left', 'total', 'kills').cell, 'c0.0');
assert.strictEqual(validScene.nextOccupied('c9.9', 'right', 'total', 'kills').cell, 'c3.2');

function assertInvalidScene(mutator, message) {
  const payload = explorerSceneFixture();
  mutator(payload);
  assert.throws(() => new HeatmapExplorerScene(payload), error => {
    assert.strictEqual(error.message, 'invalid_scene', message);
    return true;
  }, message);
}

assertInvalidScene(payload => { payload.schemaVersion = 1; }, 'schema version should be strict');
assertInvalidScene(payload => { payload.state = 'error'; }, 'error state is not a scene');
assertInvalidScene(payload => { payload.query.map = 'de_nuke'; }, 'query/map identity should match');
assertInvalidScene(payload => { payload.map.image.width = 0; }, 'image dimensions should be positive');
assertInvalidScene(payload => { payload.grid.fields[0] = 'id'; }, 'grid fields should be exact');
assertInvalidScene(payload => { payload.layers.total[0] = ['c0.0', 0, 0, 5]; }, 'row length should be exact');
assertInvalidScene(payload => { payload.layers.total[0][0] = 'c1.0'; }, 'cell id should match coordinates');
assertInvalidScene(payload => { payload.layers.total[0][1] = 4; }, 'coordinates should be in grid');
assertInvalidScene(payload => { payload.layers.total[0][3] = 1.5; }, 'counts should be integers');
assertInvalidScene(payload => { payload.layers.total.push(['c0.0', 0, 0, 1, 0]); }, 'duplicate cells should be rejected');
assertInvalidScene(payload => { payload.layers.me[0][3] = 6; }, 'personal counts cannot exceed totals');
assertInvalidScene(payload => { payload.layers.others[0][3] = 1; }, 'others must equal total minus personal');
assertInvalidScene(payload => { payload.comparison.bins.push(['c0.0', 0, 0, 0, 0, 1]); }, 'comparison duplicates should be rejected');
assertInvalidScene(payload => { payload.comparison.bins[0][3] = NaN; }, 'deltas should be finite');
assertInvalidScene(payload => { payload.comparison.bins[0][5] = -1; }, 'samples should be nonnegative integers');
assertInvalidScene(payload => { payload.activeFloor = 'main'; }, 'active floor should match query floor');

const emptyScenePayload = explorerSceneFixture({
  state: 'empty',
  layers: {total: [], me: [], others: []},
  comparison: {
    fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
    bins: [],
    personalSample: 0,
    otherSample: 0,
  },
});
const emptyScene = new HeatmapExplorerScene(emptyScenePayload);
assert.strictEqual(emptyScene.dense('total', 'both').maxAbs, 0);
assert.strictEqual(emptyScene.dense('total', 'both').occupied.length, 0);

const camera = new HeatmapExplorerCamera({
  viewportWidth: 200,
  viewportHeight: 150,
  contentWidth: 400,
  contentHeight: 300,
});
assert.deepStrictEqual(plain(camera.state), {zoom: 1, panX: 0, panY: 0, reducedMotion: false});
camera.panBy(-50, -50);
assert.deepStrictEqual([camera.state.panX, camera.state.panY], [0, 0]);
camera.zoomAt(2, 100, 75);
assert.deepStrictEqual([camera.state.zoom, camera.state.panX, camera.state.panY], [2, -100, -75]);
camera.panBy(-1000, -1000);
assert.deepStrictEqual([camera.state.panX, camera.state.panY], [-600, -450]);
assert.strictEqual(camera.handleKey('Home'), true);
assert.deepStrictEqual([camera.state.zoom, camera.state.panX, camera.state.panY], [1, 0, 0]);
assert.strictEqual(camera.handleKey('ArrowRight'), false);
camera.zoomAt(2, 100, 75);
assert.strictEqual(camera.handleKey('ArrowRight'), true);
assert.strictEqual(camera.state.panX, -52);
assert.strictEqual(camera.handleKey('+'), true);
assert.strictEqual(camera.handleKey('='), true);
assert.strictEqual(camera.handleKey('-'), true);
assert.strictEqual(camera.handleKey('not-a-key'), false);
assert.match(camera.transform().css, /^translate3d\(-?\d+(?:\.\d+)?px, -?\d+(?:\.\d+)?px, 0\) scale\(/);
const reducedCamera = new HeatmapExplorerCamera({viewportWidth: 10, viewportHeight: 10, contentWidth: 20, contentHeight: 20, reducedMotion: true});
assert.strictEqual(reducedCamera.transform().animate, false);
reducedCamera.destroy();
reducedCamera.destroy();
camera.reset();
camera.setViewport(100, 100, 50, 50);
assert.deepStrictEqual([camera.state.panX, camera.state.panY], [0, 0]);

const parsedUrl = HeatmapExplorerUrlState.parse('?page=4&hm_range=30d&hm_lens=me&hm_event=kills&hm_floor=main&hm_cell=c2.1');
assert.deepStrictEqual(
  {range: parsedUrl.range, lens: parsedUrl.lens, event: parsedUrl.event, floor: parsedUrl.floor, cell: parsedUrl.cell},
  {range: '30d', lens: 'me', event: 'kills', floor: 'main', cell: 'c2.1'}
);
assert.strictEqual(
  HeatmapExplorerUrlState.serialize('?page=4&foo=a%20b', {
    range: '7d', lens: 'difference', event: 'deaths', floor: 'upper', cell: 'c3.2',
    player: 42, lang: 'ru', renderer: 'webgl', normalization: 'sqrt',
  }),
  '?hm_range=7d&hm_lens=difference&hm_event=deaths&hm_floor=upper&hm_cell=c3.2&page=4&foo=a%20b'
);
assert.strictEqual(
  HeatmapExplorerUrlState.serialize('?page=4', {from: 100, to: 200, event: 'both'}),
  '?hm_from=100&hm_to=200&hm_event=both&page=4'
);
function assertInvalidUrl(action, message) {
  assert.throws(action, error => {
    assert.strictEqual(error.message, 'invalid_heatmap_url_state', message);
    return true;
  }, message);
}
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_unknown=x'), 'unknown heatmap keys should fail');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_range=7d&hm_range=30d'), 'duplicate heatmap keys should fail');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_range=7D'), 'preset spelling should be strict');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_from=100'), 'custom windows need both bounds');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_from=200&hm_to=100'), 'custom windows need ordered bounds');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_lens=difference&hm_event=both'), 'difference both is invalid');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_floor=main!'), 'floor token should be bounded');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse('?hm_cell=c128.0'), 'cell should fit the grid contract');
assertInvalidUrl(() => HeatmapExplorerUrlState.parse({hm_range: '7d'}), 'object search should fail');
assertInvalidUrl(() => HeatmapExplorerUrlState.serialize('', {range: ['7d']}), 'array state values should fail');
assertInvalidUrl(() => HeatmapExplorerUrlState.serialize('', {lens: {value: 'me'}}), 'object state values should fail');

function makeDom(gl) {
  const listenerMap = () => Object.create(null);
  function element(attributes = {}) {
    const listeners = listenerMap();
    const node = {
      attributes: Object.assign({}, attributes),
      style: {},
      hidden: false,
      clientWidth: 320,
      clientHeight: 240,
      width: 0,
      height: 0,
      textContent: '',
      listeners,
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name]; },
      addEventListener(type, handler) { (listeners[type] || (listeners[type] = [])).push(handler); },
      removeEventListener(type, handler) {
        if (!listeners[type]) return;
        listeners[type] = listeners[type].filter(candidate => candidate !== handler);
      },
      dispatchEvent(event) {
        (listeners[event.type] || []).slice().forEach(handler => handler(event));
        return true;
      },
      getContext() { return gl; },
    };
    return node;
  }
  const nodes = {
    interactive: element(),
    stage: element(),
    camera: element(),
    image: element(),
    canvas: element(),
    static: element(),
    status: element(),
  };
  nodes.stage.clientWidth = 320;
  nodes.stage.clientHeight = 240;
  nodes.canvas.getBoundingClientRect = () => ({left: 0, top: 0, width: 320, height: 240});
  const selectors = {
    '[data-heatmap-interactive]': nodes.interactive,
    '[data-heatmap-stage]': nodes.stage,
    '[data-heatmap-camera]': nodes.camera,
    '[data-heatmap-image]': nodes.image,
    '[data-heatmap-canvas]': nodes.canvas,
    '[data-heatmap-static]': nodes.static,
    '[data-heatmap-status]': nodes.status,
  };
  const root = element();
  root.querySelector = selector => selectors[selector] || null;
  root.dispatches = [];
  root.dispatchEvent = event => { root.dispatches.push(event); return true; };
  const windowListeners = listenerMap();
  const window = {
    devicePixelRatio: 3,
    listeners: windowListeners,
    addEventListener(type, handler) { (windowListeners[type] || (windowListeners[type] = [])).push(handler); },
    removeEventListener(type, handler) {
      if (!windowListeners[type]) return;
      windowListeners[type] = windowListeners[type].filter(candidate => candidate !== handler);
    },
    CustomEvent: function CustomEvent(type, init) { this.type = type; this.detail = init && init.detail; },
  };
  return {root, nodes, window};
}

function fakeGl(options = {}) {
  let nextId = 0;
  const calls = {textures: [], texImages: [], shaderSources: [], draws: 0, programs: 0, buffers: 0};
  const gl = {
    VERTEX_SHADER: 35633, FRAGMENT_SHADER: 35632, COMPILE_STATUS: 35713, LINK_STATUS: 35714,
    ARRAY_BUFFER: 34962, STATIC_DRAW: 35044, FLOAT: 5126, TEXTURE_2D: 3553,
    TEXTURE_MIN_FILTER: 10241, TEXTURE_MAG_FILTER: 10240, TEXTURE_WRAP_S: 10242,
    TEXTURE_WRAP_T: 10243, NEAREST: 9728, CLAMP_TO_EDGE: 33071, R32F: 33326,
    RED: 6403, TRIANGLE_STRIP: 5, COLOR_BUFFER_BIT: 16384, NO_ERROR: 0,
    createShader(type) { return {id: ++nextId, type}; },
    shaderSource(shader, source) { shader.source = source; calls.shaderSources.push(source); },
    compileShader() {},
    getShaderParameter(shader, parameter) { return !options.compileFailure && parameter === gl.COMPILE_STATUS; },
    getShaderInfoLog() { return 'driver shader details'; },
    deleteShader() {},
    createProgram() { calls.programs += 1; return {id: ++nextId}; },
    attachShader() {},
    linkProgram() {},
    getProgramParameter(program, parameter) { return !options.linkFailure && parameter === gl.LINK_STATUS; },
    getProgramInfoLog() { return 'driver link details'; },
    deleteProgram() {},
    createBuffer() { calls.buffers += 1; return {id: ++nextId}; },
    bindBuffer() {},
    bufferData() {},
    deleteBuffer() {},
    createTexture() { const texture = {id: ++nextId}; calls.textures.push(texture); return texture; },
    bindTexture() {},
    texParameteri() {},
    texImage2D(...args) { calls.texImages.push(args); if (options.textureFailure) throw new Error('texture failure'); },
    deleteTexture() {},
    useProgram() {},
    getAttribLocation() { return 0; },
    enableVertexAttribArray() {},
    vertexAttribPointer() {},
    getUniformLocation(_program, name) { return {name}; },
    uniform1f() {},
    uniform1i() {},
    uniform2f() {},
    activeTexture() {},
    drawArrays() { calls.draws += 1; if (options.drawFailure) throw new Error('draw failure'); },
    viewport() {},
    clearColor() {},
    clear() {},
    getError() { return options.errorCode || 0; },
    getExtension(name) { calls.extension = name; return {}; },
  };
  gl.calls = calls;
  return gl;
}

const goodGl = fakeGl();
const dom = makeDom(goodGl);
let nowValue = 100;
const rendererStates = [];
const renderer = new HeatmapGlRenderer(dom.root, validScene, {
  document: {},
  window: dom.window,
  now: () => { nowValue += 5; return nowValue; },
  message: code => `<${code}>`,
  onState: code => rendererStates.push(code),
});
renderer.mount();
assert.strictEqual(goodGl.calls.textures.length, 1, 'renderer should create one texture');
assert.strictEqual(goodGl.calls.buffers, 1, 'renderer should create one full-quad buffer');
assert.strictEqual(goodGl.calls.programs, 1, 'renderer should create one program');
assert.strictEqual(goodGl.calls.texImages.length, 1, 'initial render should upload one dense texture');
assert.strictEqual(dom.nodes.canvas.width, 640, 'resize should cap device pixel ratio at two');
assert.strictEqual(dom.root.attributes['data-heatmap-render-ms'] !== undefined, true);
assert.strictEqual(dom.root.dispatches.length, 1);
assert.ok(Number.isFinite(dom.root.attributes['data-heatmap-render-ms'] * 1));
assert.strictEqual(rendererStates.length, 0);
renderer.render({layer: 'difference', channel: 'kills'});
const uploaded = goodGl.calls.texImages[goodGl.calls.texImages.length - 1].at(-1);
assert.strictEqual(Object.prototype.toString.call(uploaded), '[object Float32Array]', 'difference upload should remain one Float32Array');
assert.strictEqual(uploaded[2], Math.fround(Math.fround(-0.1333333333) * Math.fround(0.22)));
assert.strictEqual(goodGl.calls.textures.length, 1);
renderer.render({layer: 'difference', channel: 'kills'});
assert.strictEqual(dom.root.dispatches.length, 1, 'ready should fire only once per mount');
const sharedCamera = {transform: () => ({css: 'translate3d(-8px,0,0) scale(2)', animate: false})};
renderer.setCamera(sharedCamera);
assert.strictEqual(dom.nodes.camera.style.transform, 'translate3d(-8px,0,0) scale(2)');
assert.strictEqual(dom.nodes.image.style.transform, undefined);
assert.strictEqual(dom.nodes.canvas.style.transform, undefined);
let prevented = false;
dom.nodes.canvas.dispatchEvent({type: 'webglcontextlost', preventDefault() { prevented = true; }});
assert.strictEqual(prevented, true);
assert.strictEqual(dom.root.attributes['data-heatmap-state'], 'context_lost');
assert.notStrictEqual(dom.nodes.static.style.display, 'none');
dom.nodes.canvas.dispatchEvent({type: 'webglcontextrestored'});
assert.ok(goodGl.calls.programs >= 2, 'context restore should rebuild resources');
renderer.destroy();
renderer.destroy();
assert.strictEqual((dom.nodes.canvas.listeners.webglcontextlost || []).length, 0);
assert.strictEqual((dom.nodes.canvas.listeners.webglcontextrestored || []).length, 0);
assert.strictEqual((dom.window.listeners.resize || []).length, 0);

const emptyGl = fakeGl();
const emptyDom = makeDom(emptyGl);
const emptyRenderer = new HeatmapGlRenderer(emptyDom.root, emptyScene, {
  window: emptyDom.window,
  now: () => 200,
  message: code => `[${code}]`,
});
emptyRenderer.mount();
assert.strictEqual(emptyDom.root.attributes['data-heatmap-render-ms'], undefined, 'empty frame should not be ready');
assert.strictEqual(emptyDom.root.dispatches.length, 0);
emptyRenderer.destroy();

const failedGl = fakeGl({compileFailure: true});
const failedDom = makeDom(failedGl);
const failedStates = [];
const failedRenderer = new HeatmapGlRenderer(failedDom.root, validScene, {
  window: failedDom.window,
  message: code => `<${code}>`,
  onState: code => failedStates.push(code),
});
failedRenderer.mount();
assert.strictEqual(failedDom.root.attributes['data-heatmap-state'], 'static_fallback');
assert.strictEqual(failedStates[0], 'static_fallback');
assert.strictEqual(failedDom.nodes.interactive.style.display, 'none');
assert.strictEqual(failedDom.nodes.static.style.display, '');
assert.strictEqual(failedDom.nodes.status.textContent, '<static_fallback>');
assert.strictEqual(failedDom.nodes.status.textContent.includes('driver'), false);
failedRenderer.destroy();

assert.strictEqual(/innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new\s+Function/.test(explorerSource), false, 'renderer source must not use unsafe HTML/eval APIs');
assert.match(explorerSource, /R32F/);
assert.match(explorerSource, /RED/);
assert.match(explorerSource, /CLAMP_TO_EDGE/);
assert.match(explorerSource, /for \(var offsetY = -1; offsetY <= 1; offsetY\+\+\)/);
assert.match(explorerSource, /amber|orange/i);
assert.match(explorerSource, /cyan|blue/i);
assert.match(explorerSource, /contour/i);

console.log('heatmap explorer contract smoke ok');
