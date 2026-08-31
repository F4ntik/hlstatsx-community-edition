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
const explorerContext = {
  module: {exports: {}},
  window: {},
  btoa(value) { return Buffer.from(String(value), 'binary').toString('base64'); },
};
vm.runInNewContext(explorerSource, explorerContext, {filename: 'heatmap-explorer.js'});
const explorerApi = explorerContext.module.exports;
assert.deepStrictEqual(
  Object.keys(explorerApi).sort(),
  ['HeatmapExplorerCamera', 'HeatmapExplorerScene', 'HeatmapExplorerUrlState', 'HeatmapExplorerWorkspace', 'HeatmapGlRenderer'].sort(),
  'heatmap explorer should expose the workspace constructor alongside the frozen scene, camera, URL, and renderer APIs'
);
for (const name of Object.keys(explorerApi)) {
  assert.strictEqual(explorerContext.window[name], explorerApi[name], `${name} should attach to window`);
}

console.log('heatmap explorer export smoke ok');

const {
  HeatmapExplorerScene,
  HeatmapExplorerCamera,
  HeatmapExplorerUrlState,
  HeatmapExplorerWorkspace,
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
assert.deepStrictEqual(
  plain(validScene.coverage),
  {sourceRows: 8, candidate: 8, validXY: 8},
  'workspace summaries should use the validated server coverage instead of reconstructing it'
);
assert.deepStrictEqual(
  plain(validScene.summary),
  {rowsRead: 8, sourceRows: 8, personalSample: 5, otherSample: 3},
  'workspace summaries should use the validated server sample metadata'
);
assert.deepStrictEqual(
  plain(validScene.fallback),
  {
    v1: 'heatmap_points.php?game=cstrike&map=de_dust2',
    jpeg: './map-kill.jpg',
    thumbnail: './map-kill-thumb.jpg',
  },
  'fallback URLs must remain authoritative server data'
);
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
  const calls = {
    textures: [],
    texImages: [],
    shaderSources: [],
    draws: 0,
    programs: 0,
    buffers: 0,
    deleted: {shaders: [], programs: [], buffers: [], textures: []},
  };
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
    deleteShader(shader) { calls.deleted.shaders.push(shader.id); },
    createProgram() {
      if (options.createProgramFailure) return null;
      calls.programs += 1;
      return {id: ++nextId};
    },
    attachShader() {},
    linkProgram() {},
    getProgramParameter(program, parameter) { return !options.linkFailure && parameter === gl.LINK_STATUS; },
    getProgramInfoLog() { return 'driver link details'; },
    deleteProgram(program) { calls.deleted.programs.push(program.id); },
    createBuffer() {
      if (options.createBufferFailure) return null;
      calls.buffers += 1;
      return {id: ++nextId};
    },
    bindBuffer() {},
    bufferData() {},
    deleteBuffer(buffer) { calls.deleted.buffers.push(buffer.id); },
    createTexture() {
      if (options.createTextureFailure) return null;
      const texture = {id: ++nextId};
      calls.textures.push(texture);
      return texture;
    },
    bindTexture() {},
    texParameteri() {},
    texImage2D(...args) { calls.texImages.push(args); if (options.textureFailure) throw new Error('texture failure'); },
    deleteTexture(texture) { calls.deleted.textures.push(texture.id); },
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
    getExtension(name) { calls.extension = name; return options.extensionNull ? null : {}; },
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
assert.ok(Number.isFinite(dom.root.dispatches[0].detail.durationMs));
assert.strictEqual(
  dom.root.dispatches[0].detail.durationMs,
  dom.root.attributes['data-heatmap-render-ms'] * 1
);
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
assert.match(
  explorerSource,
  /vec2 sampleUv = vec2\(v_uv\.x, 1\.0 - v_uv\.y\)/,
  'fragment sampling should flip texture Y while preserving server row order'
);
const asymmetricPayload = explorerSceneFixture();
asymmetricPayload.query = Object.assign({}, asymmetricPayload.query, {lens: 'overview', event: 'kills'});
asymmetricPayload.grid = {
  bucketSize: 8,
  width: 1,
  height: 2,
  fields: ['cell', 'x', 'y', 'kills', 'deaths'],
};
asymmetricPayload.layers = {
  total: [['c0.0', 0, 0, 1, 0], ['c0.1', 0, 1, 9, 0]],
  me: [['c0.0', 0, 0, 0, 0], ['c0.1', 0, 1, 0, 0]],
  others: [['c0.0', 0, 0, 1, 0], ['c0.1', 0, 1, 9, 0]],
};
asymmetricPayload.comparison = {
  fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
  bins: [],
  personalSample: 0,
  otherSample: 10,
};
asymmetricPayload.summary = {rowsRead: 2, sourceRows: 2, personalSample: 0, otherSample: 10};
const asymmetricScene = new HeatmapExplorerScene(asymmetricPayload);
const asymmetricGl = fakeGl();
const asymmetricDom = makeDom(asymmetricGl);
const asymmetricRenderer = new HeatmapGlRenderer(
  asymmetricDom.root,
  asymmetricScene,
  {window: asymmetricDom.window}
);
asymmetricRenderer.mount();
assert.deepStrictEqual(
  Array.from(asymmetricGl.calls.texImages[0].at(-1)),
  [1, 9],
  'top-down server row order should reach the single texture unchanged'
);
asymmetricRenderer.destroy();
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

const extensionlessGl = fakeGl({extensionNull: true});
const extensionlessDom = makeDom(extensionlessGl);
const extensionlessRenderer = new HeatmapGlRenderer(
  extensionlessDom.root,
  validScene,
  {window: extensionlessDom.window}
);
extensionlessRenderer.mount();
assert.ok(extensionlessGl.calls.draws > 0, 'WebGL2 sampling should not require EXT_color_buffer_float');
assert.strictEqual(extensionlessDom.nodes.interactive.style.display, '');
assert.strictEqual(extensionlessDom.nodes.static.style.display, 'none');
extensionlessRenderer.destroy();

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

function deletedResources(gl) {
  return Object.fromEntries(
    Object.entries(gl.calls.deleted).map(([name, values]) => [
      name,
      values.slice().sort((left, right) => left - right),
    ])
  );
}

function assertResourceCleanup(options, expected, label) {
  const gl = fakeGl(options);
  const dom = makeDom(gl);
  const resourceRenderer = new HeatmapGlRenderer(dom.root, validScene, {window: dom.window});
  resourceRenderer.mount();
  assert.strictEqual(dom.root.attributes['data-heatmap-state'], 'static_fallback', label + ' should use static fallback');
  assert.deepStrictEqual(deletedResources(gl), expected, label + ' should delete every local allocation');
  resourceRenderer.destroy();
  assert.deepStrictEqual(
    deletedResources(gl),
    expected,
    label + ' cleanup should not double-delete transferred handles'
  );
}

assertResourceCleanup(
  {createProgramFailure: true},
  {shaders: [1, 2], programs: [], buffers: [], textures: []},
  'program allocation failure'
);
assertResourceCleanup(
  {linkFailure: true},
  {shaders: [1, 2], programs: [3], buffers: [], textures: []},
  'program link failure'
);
assertResourceCleanup(
  {createBufferFailure: true},
  {shaders: [1, 2], programs: [3], buffers: [], textures: []},
  'buffer allocation failure'
);
assertResourceCleanup(
  {createTextureFailure: true},
  {shaders: [1, 2], programs: [3], buffers: [4], textures: []},
  'texture allocation failure'
);

assert.strictEqual(/innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new\s+Function/.test(explorerSource), false, 'renderer source must not use unsafe HTML/eval APIs');
assert.match(explorerSource, /R32F/);
assert.match(explorerSource, /RED/);
assert.match(explorerSource, /CLAMP_TO_EDGE/);
assert.match(explorerSource, /for \(var offsetY = -1; offsetY <= 1; offsetY\+\+\)/);
assert.match(explorerSource, /amber|orange/i);
assert.match(explorerSource, /cyan|blue/i);
assert.match(explorerSource, /contour/i);

function workspaceElement(attributes = {}) {
  const listeners = Object.create(null);
  return {
    attributes: Object.assign({}, attributes),
    style: {},
    hidden: false,
    clientWidth: 320,
    clientHeight: 240,
    textContent: '',
    value: '',
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name]; },
    addEventListener(type, handler) { (listeners[type] || (listeners[type] = [])).push(handler); },
    removeEventListener(type, handler) {
      if (listeners[type]) listeners[type] = listeners[type].filter(candidate => candidate !== handler);
    },
  };
}

function workspaceRoot(attributes) {
  const root = workspaceElement(attributes);
  root.querySelector = () => null;
  root.querySelectorAll = () => [];
  return root;
}

function mountedWorkspaceRoot(attributes, nodes) {
  const root = workspaceRoot(attributes);
  root.querySelector = selector => nodes[selector] || null;
  return root;
}

const workspaceMessages = {
  loading: 'Loading', loaded: 'Loaded', failed: 'Failed', invalidUrl: 'Invalid URL',
  retry: 'Retry', fallback: 'Fallback', differenceBothCorrected: 'Kills selected',
  period: 'Period', sample: 'Sample', xyCoverage: 'XY', zCoverage: 'Z',
  projectionCoverage: 'Projection', coverage: 'Coverage', freshness: 'Freshness',
  empty: 'Empty', pinned: 'Pinned', unpinned: 'Unpinned', noCell: 'No cell',
  inspect: 'Inspect', kills: 'Kills', deaths: 'Deaths', pan: 'Pan', navigation: 'Navigation',
};
const workspaceState = new HeatmapExplorerWorkspace(
  workspaceRoot({
    'data-heatmap-game': 'cstrike',
    'data-heatmap-map': 'de_dust2',
    'data-heatmap-player': '42',
    'data-heatmap-endpoint': 'heatmap_points.php?legacy=1',
    'data-heatmap-lang': 'ru',
    'data-heatmap-allow-me': '1',
    'data-heatmap-allow-difference': '1',
  }),
  {search: '?page=4&hm_range=7d&hm_lens=difference&hm_event=kills&hm_floor=all', messages: workspaceMessages}
);
assert.strictEqual(
  workspaceState.sceneUrl(),
  'heatmap_points.php?v=2&game=cstrike&map=de_dust2&player=42&range=7d&event=kills&lens=difference&floor=all&lang=ru',
  'scene requests should contain only the strict v2 allowlist in a stable order'
);
assert.strictEqual(workspaceState._message('static_fallback'), 'Fallback', 'renderer fallback states should use the localized Explorer fallback message');
workspaceState.state.event = 'both';
workspaceState._normalizeSelection(true);
assert.strictEqual(workspaceState.state.event, 'kills', 'difference plus both should correct to kills');
workspaceState._scene = validScene;
workspaceState.state.focusedCell = 'c0.0';
let navigationPrevented = false;
workspaceState._handleStageKey({key: 'ArrowRight', preventDefault() { navigationPrevented = true; }});
assert.strictEqual(workspaceState.state.focusedCell, 'c2.0', 'navigation-mode arrows should select the nearest occupied cell');
assert.strictEqual(navigationPrevented, true);
workspaceState._handleStageKey({key: 'Enter', preventDefault() {}});
assert.strictEqual(workspaceState.state.cell, 'c2.0', 'Enter should pin the selected cell');
assert.doesNotMatch(workspaceState.sceneUrl(), /inspect=/, 'scene URLs must stay distinct from inspect requests');
assert.match(workspaceState.inspectUrl(), /&inspect=c2.0$/, 'pinning should prepare a strict v2 inspect=cX.Y request');
workspaceState._handleStageKey({key: 'Escape', preventDefault() {}});
assert.strictEqual(workspaceState.state.cell, null, 'Escape should clear the pinned cell');
workspaceState._camera = new HeatmapExplorerCamera({viewportWidth: 200, viewportHeight: 150, contentWidth: 400, contentHeight: 300});
workspaceState._camera.zoomAt(2, 100, 75);
workspaceState._renderer = {setCamera() {}};
workspaceState._panMode = true;
const panBefore = workspaceState._camera.state.panX;
workspaceState._handleStageKey({key: 'ArrowRight', preventDefault() {}});
assert.notStrictEqual(workspaceState._camera.state.panX, panBefore, 'Pan mode should give arrow keys to the camera instead of cell navigation');

function WorkspaceRenderer() {}
WorkspaceRenderer.prototype.mount = function () {};
WorkspaceRenderer.prototype.destroy = function () {};
WorkspaceRenderer.prototype.setCamera = function () {};
const imageNode = workspaceElement({src: './client.jpg', alt: 'client map'});
const staticLinkNode = workspaceElement({href: './client-kill.jpg'});
const staticImageNode = workspaceElement({src: './client-kill.jpg', alt: 'client map'});
const shareNode = workspaceElement();
const workspaceRootForScene = workspaceRoot({
  'data-heatmap-game': 'cstrike',
  'data-heatmap-map': 'de_dust2',
  'data-heatmap-player': '42',
  'data-heatmap-endpoint': 'heatmap_points.php',
  'data-heatmap-lang': 'en',
  'data-heatmap-allow-me': '1',
  'data-heatmap-allow-difference': '1',
});
const historyWrites = [];
const workspaceForScene = new HeatmapExplorerWorkspace(workspaceRootForScene, {
  search: '?page=4',
  messages: workspaceMessages,
  Renderer: WorkspaceRenderer,
  window: {
    location: {search: '?page=4', pathname: '/hlstats.php'},
    history: {replaceState(_state, _title, href) { historyWrites.push(href); }},
  },
});
workspaceForScene._nodes = {
  interactive: workspaceElement(), stage: workspaceElement(), image: imageNode, canvas: workspaceElement(),
  static: workspaceElement(), staticLink: staticLinkNode, staticImage: staticImageNode, jpegLink: workspaceElement(),
  status: workspaceElement(), alert: workspaceElement(), summary: workspaceElement(), period: workspaceElement(),
  window: workspaceElement(), sample: workspaceElement(), coverage: workspaceElement(), freshness: workspaceElement(),
  inspectOutput: workspaceElement(), mapTitle: workspaceElement(), mapSelect: workspaceElement(),
  zoomIn: workspaceElement(), zoomOut: workspaceElement(), reset: workspaceElement(), pan: workspaceElement(), share: shareNode,
};
workspaceForScene._applyScene(validScene, 'map');
assert.strictEqual(imageNode.attributes.src, './map.jpg', 'server-validated map image URL should replace client assumptions');
assert.strictEqual(imageNode.attributes.alt, 'de_dust2', 'server map identity should update image alt text together with the image');
assert.strictEqual(staticLinkNode.attributes.href, './map-kill.jpg', 'server fallback JPEG should update with the scene');
assert.strictEqual(workspaceForScene._nodes.mapSelect.value, 'de_dust2', 'server map identity should keep the map control synchronized');
assert.match(workspaceForScene._nodes.summary.textContent, /Period: 1785456000–1788048000 UTC/, 'every scene query should refresh a textual summary');
assert.match(workspaceForScene._nodes.status.textContent, /Loaded: Coverage/, 'the live status should communicate completed coverage, not only a generic loaded state');
assert.strictEqual(workspaceForScene.state.lens, 'difference', 'authoritative scene state should keep the share lens synchronized');
assert.strictEqual(workspaceForScene.state.event, 'kills', 'authoritative scene state should keep the share channel synchronized');
assert.match(shareNode.attributes.href, /hm_lens=difference/);
assert.match(shareNode.attributes.href, /hm_event=kills/);
assert.deepStrictEqual(historyWrites.at(-1), shareNode.attributes.href, 'share URL and history should update together');

const noFetchNodes = {
  '[data-heatmap-interactive]': workspaceElement(),
  '[data-heatmap-stage]': workspaceElement(),
  '[data-heatmap-image]': workspaceElement(),
  '[data-heatmap-canvas]': workspaceElement(),
  '[data-heatmap-static]': workspaceElement(),
  '[data-heatmap-status]': workspaceElement(),
  '[data-heatmap-alert]': workspaceElement(),
  '[data-heatmap-summary]': workspaceElement(),
};
const noFetchWorkspace = new HeatmapExplorerWorkspace(
  mountedWorkspaceRoot({
    'data-heatmap-game': 'cstrike', 'data-heatmap-map': 'de_dust2',
    'data-heatmap-player': '0', 'data-heatmap-endpoint': 'heatmap_points.php',
  }, noFetchNodes),
  {messages: workspaceMessages}
);
noFetchWorkspace.mount();
assert.strictEqual(noFetchNodes['[data-heatmap-status]'].textContent, 'Fallback', 'no-fetch environments should immediately expose the usable static fallback');
assert.strictEqual(noFetchNodes['[data-heatmap-interactive]'].style.display, 'none');

function workspaceEventElement(attributes = {}) {
  const node = workspaceElement(attributes);
  const listeners = Object.create(null);
  node.addEventListener = function (type, handler) {
    (listeners[type] || (listeners[type] = [])).push(handler);
  };
  node.removeEventListener = function (type, handler) {
    if (listeners[type]) listeners[type] = listeners[type].filter(candidate => candidate !== handler);
  };
  node.dispatch = function (type, details = {}) {
    const event = Object.assign({type, currentTarget: node, target: node, preventDefault() {}}, details);
    (listeners[type] || []).slice().forEach(handler => handler(event));
  };
  return node;
}

function workspaceHarness(search = '?page=4') {
  const nodes = {
    interactive: workspaceEventElement(),
    stage: workspaceEventElement(),
    image: workspaceEventElement(),
    canvas: workspaceEventElement(),
    static: workspaceEventElement(),
    status: workspaceEventElement(),
    alert: workspaceEventElement(),
    summary: workspaceEventElement(),
    inspectOutput: workspaceEventElement(),
    zoomIn: workspaceEventElement(),
    zoomOut: workspaceEventElement(),
  };
  const selectors = {
    '[data-heatmap-interactive]': nodes.interactive,
    '[data-heatmap-stage]': nodes.stage,
    '[data-heatmap-image]': nodes.image,
    '[data-heatmap-canvas]': nodes.canvas,
    '[data-heatmap-static]': nodes.static,
    '[data-heatmap-status]': nodes.status,
    '[data-heatmap-alert]': nodes.alert,
    '[data-heatmap-summary]': nodes.summary,
    '[data-heatmap-inspect-output]': nodes.inspectOutput,
    '[data-heatmap-zoom="in"]': nodes.zoomIn,
    '[data-heatmap-zoom="out"]': nodes.zoomOut,
  };
  const root = workspaceEventElement({
    'data-heatmap-game': 'cstrike',
    'data-heatmap-map': 'de_dust2',
    'data-heatmap-player': '42',
    'data-heatmap-endpoint': 'heatmap_points.php',
    'data-heatmap-lang': 'en',
    'data-heatmap-allow-me': '1',
    'data-heatmap-allow-difference': '1',
  });
  root.querySelector = selector => selectors[selector] || null;
  root.querySelectorAll = () => [];
  return {
    root,
    nodes,
    window: {
      location: {search, pathname: '/hlstats.php'},
      history: {replaceState() {}},
    },
  };
}

function deferredTransport() {
  const requests = [];
  return {
    requests,
    fetch(url) {
      let resolve;
      let reject;
      const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
      });
      requests.push({url, resolve, reject, promise});
      return promise;
    },
  };
}

function jsonResponse(payload) {
  return {ok: true, json() { return Promise.resolve(payload); }};
}

function sceneForMap(map) {
  const payload = explorerSceneFixture();
  payload.query.map = map;
  payload.map.name = map;
  payload.map.image = {url: './' + map + '.jpg', width: 40, height: 30};
  payload.fallback = {
    v1: 'heatmap_points.php?game=cstrike&map=' + map,
    jpeg: './' + map + '-kill.jpg',
    thumbnail: './' + map + '-kill-thumb.jpg',
  };
  return payload;
}

function inspectPayload() {
  return {
    schemaVersion: 2,
    operation: 'inspect',
    state: 'ok',
    rows: [{
      eventTime: '2026-08-31T12:00:00Z',
      event: 'kill',
      killer: {id: 42, name: 'Alice'},
      victim: {id: 7, name: 'Bob'},
      weapon: 'ak47',
      headshot: true,
      teamkill: false,
    }],
    truncated: false,
    warnings: [],
  };
}

async function settleWorkspace() {
  for (let turn = 0; turn < 6; turn += 1) await Promise.resolve();
}

async function assertSeparateInspectAndDeepLinkFlow() {
  const deepLink = workspaceHarness('?page=4&hm_cell=c2.0');
  const deepLinkTransport = deferredTransport();
  const deepLinkWorkspace = new HeatmapExplorerWorkspace(deepLink.root, {
    window: deepLink.window,
    fetch: deepLinkTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  deepLinkWorkspace.mount();
  await settleWorkspace();
  assert.strictEqual(deepLinkTransport.requests.length, 1, 'a deep-linked cell should start with one scene request');
  assert.doesNotMatch(deepLinkTransport.requests[0].url, /inspect=/, 'the initial scene request must not be replaced by inspect');
  deepLinkTransport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();
  assert.strictEqual(deepLinkWorkspace._scene.map.name, 'de_dust2', 'deep-link loading must retain the validated scene before inspect');
  assert.strictEqual(deepLinkTransport.requests.length, 2, 'deep-linked cell should issue a separate inspect request after scene load');
  assert.match(deepLinkTransport.requests[1].url, /&inspect=c2.0$/, 'the follow-up request must target the pinned cell');
  deepLinkTransport.requests[1].resolve(jsonResponse(inspectPayload()));
  await settleWorkspace();
  assert.match(deepLink.nodes.inspectOutput.textContent, /Alice.*ak47/, 'validated inspect rows should render in the inspector');

  const pinned = workspaceHarness();
  const pinnedTransport = deferredTransport();
  const pinnedWorkspace = new HeatmapExplorerWorkspace(pinned.root, {
    window: pinned.window,
    fetch: pinnedTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  pinnedWorkspace.mount();
  await settleWorkspace();
  pinnedTransport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();
  const retainedScene = pinnedWorkspace._scene;
  const retainedRenderer = pinnedWorkspace._renderer;
  pinnedWorkspace.pin('c2.0');
  await settleWorkspace();
  assert.strictEqual(pinnedTransport.requests.length, 2, 'pinning after scene load should issue inspect without a second scene reload');
  pinnedTransport.requests[1].resolve(jsonResponse(inspectPayload()));
  await settleWorkspace();
  assert.strictEqual(pinnedWorkspace._scene, retainedScene, 'inspect success must retain the existing scene instance');
  assert.strictEqual(pinnedWorkspace._renderer, retainedRenderer, 'inspect success must not recreate the scene renderer');
  assert.match(pinned.nodes.inspectOutput.textContent, /Alice.*ak47/, 'pinning should render the inspect payload instead of treating it as a scene');
}

async function assertLatestSceneRequestWins() {
  const success = workspaceHarness();
  const successTransport = deferredTransport();
  const successWorkspace = new HeatmapExplorerWorkspace(success.root, {
    window: success.window,
    fetch: successTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  successWorkspace.mount();
  await settleWorkspace();
  successWorkspace._setState({map: 'de_nuke', floor: 'all', cell: null}, 'map');
  await settleWorkspace();
  assert.strictEqual(successTransport.requests.length, 2, 'a newer selection while loading must start the newest request');
  const oldestSuccess = successTransport.requests[0];
  const newestSuccess = successTransport.requests[1];
  assert.match(newestSuccess.url, /map=de_nuke/, 'the newest queued request must contain the current selection');
  newestSuccess.resolve(jsonResponse(sceneForMap('de_nuke')));
  await settleWorkspace();
  assert.strictEqual(success.nodes.image.attributes.src, './de_nuke.jpg', 'the newest scene success must own the rendered image');
  oldestSuccess.resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();
  assert.strictEqual(successWorkspace.state.map, 'de_nuke', 'inverse-order stale scene success must not restore an older map selection');
  assert.strictEqual(success.nodes.image.attributes.src, './de_nuke.jpg', 'inverse-order stale success must not overwrite the newest rendered image');

  const failure = workspaceHarness();
  const failureTransport = deferredTransport();
  const failureWorkspace = new HeatmapExplorerWorkspace(failure.root, {
    window: failure.window,
    fetch: failureTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  failureWorkspace.mount();
  await settleWorkspace();
  failureWorkspace._setState({map: 'de_nuke', floor: 'all', cell: null}, 'map');
  await settleWorkspace();
  assert.strictEqual(failureTransport.requests.length, 2, 'the newest selection must survive while the older request is pending');
  const oldestFailure = failureTransport.requests[0];
  const newestFailure = failureTransport.requests[1];
  newestFailure.resolve(jsonResponse(sceneForMap('de_nuke')));
  await settleWorkspace();
  assert.strictEqual(failure.nodes.image.attributes.src, './de_nuke.jpg', 'the request after a stale failure must still render the newest scene');
  oldestFailure.reject(new Error('stale failure'));
  await settleWorkspace();
  assert.strictEqual(failureWorkspace.state.map, 'de_nuke', 'inverse-order stale scene failure must not restore an older selection');
  assert.strictEqual(failure.nodes.image.attributes.src, './de_nuke.jpg', 'inverse-order stale failure must not overwrite the newest image');
  assert.notStrictEqual(failure.nodes.status.textContent, 'Failed', 'inverse-order stale failure must not replace the newest loaded state');
}

function assertZoomUsesReversibleFactors() {
  const zoom = workspaceHarness();
  const zoomWorkspace = new HeatmapExplorerWorkspace(zoom.root, {messages: workspaceMessages});
  zoomWorkspace._nodes = {
    floors: null, mapSelect: null, range: null, reset: null, pan: null, stage: null, canvas: null,
    zoomIn: zoom.nodes.zoomIn, zoomOut: zoom.nodes.zoomOut,
  };
  const cameraForControls = new HeatmapExplorerCamera({
    viewportWidth: 200,
    viewportHeight: 150,
    contentWidth: 400,
    contentHeight: 300,
  });
  const observedFactors = [];
  const originalZoomAt = cameraForControls.zoomAt;
  cameraForControls.zoomAt = function (factor, x, y) {
    observedFactors.push(factor);
    return originalZoomAt.call(this, factor, x, y);
  };
  zoomWorkspace._camera = cameraForControls;
  zoomWorkspace._renderer = {setCamera() {}};
  zoomWorkspace._bindEvents();
  zoom.nodes.zoomIn.dispatch('click');
  zoom.nodes.zoomOut.dispatch('click');
  assert.deepStrictEqual(observedFactors, [1.25, 0.8], 'zoom controls must pass stable inverse factors, never the current absolute zoom');
  assert.strictEqual(cameraForControls.state.zoom, 1, 'zoom in followed by zoom out must return to the prior zoom level');
}

(async function runFixRoundOneRegressions() {
  await assertSeparateInspectAndDeepLinkFlow();
  await assertLatestSceneRequestWins();
  assertZoomUsesReversibleFactors();
  console.log('heatmap explorer contract smoke ok');
}()).catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
