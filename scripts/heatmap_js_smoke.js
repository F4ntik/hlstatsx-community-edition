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
const plain = value => JSON.parse(JSON.stringify(value));
const adminPayload = context.module.exports.HeatmapAdminPayload;
assert.ok(adminPayload, 'heatmap admin payload helper should be exportable for smoke tests');
const adminGeometry = context.module.exports.HeatmapAdminGeometry;
assert.ok(adminGeometry, 'heatmap admin geometry helpers should be exportable for responsive calibration drags');
const landmarkSolver = context.module.exports.HeatmapLandmarkSolver;
assert.ok(landmarkSolver, 'landmark similarity solver should be exportable for calibration checks');
assert.strictEqual(typeof landmarkSolver.project, 'function', 'solver should expose the authoritative persisted-projection round trip');
const landmarkAnchors = [
  {worldX: 0, worldY: 0, pixelX: 100, pixelY: 50},
  {worldX: 100, worldY: 0, pixelX: 150, pixelY: 50},
  {worldX: 0, worldY: 100, pixelX: 100, pixelY: 0},
  {worldX: 100, worldY: 100, pixelX: 150, pixelY: 0},
  {worldX: 50, worldY: 150, pixelX: 125, pixelY: -25, holdout: true},
  {worldX: 150, worldY: 50, pixelX: 175, pixelY: 25, holdout: true}
];
const landmarkResult = landmarkSolver.solve(landmarkAnchors, {minimumAnchors: 4, outlierPixels: 10});
assert.strictEqual(landmarkResult.ok, true, 'solver should accept a six-point similarity mapping');
assert.strictEqual(landmarkResult.rotate, 0, 'solver should recover the unrotated orientation');
assert.strictEqual(landmarkResult.flipX, false, 'solver should use the canonical reflection representation');
assert.strictEqual(landmarkResult.flipY, true, 'solver should recover the Y reflection');
assert.ok(Math.abs(landmarkResult.scale - 2) < 1e-6, 'solver should recover the known uniform scale');
assert.ok(landmarkResult.rmse < 0.001, 'solver should preserve exact holdout geometry');
assert.strictEqual(landmarkResult.inliers.length, 6, 'solver should retain all clean landmarks');
assert.deepStrictEqual(
  plain(landmarkSolver.project({worldX: 100, worldY: 50}, landmarkResult)),
  {x: 150, y: 25},
  'solver candidate should round-trip through persisted projection fields'
);
const croppedRotationConfig = {xoffset: 200, yoffset: -300, scale: 2, flipX: false, flipY: true, rotate: 1, cropX: 30, cropY: 40};
const croppedRotationAnchors = [
  {worldX: 0, worldY: 0}, {worldX: 100, worldY: 0}, {worldX: 0, worldY: 100}, {worldX: 100, worldY: 100},
  {worldX: 50, worldY: 150, holdout: true}, {worldX: 150, worldY: 50, holdout: true}
].map(anchor => {
  const point = landmarkSolver.project(anchor, croppedRotationConfig);
  return Object.assign({}, anchor, {pixelX: point.x, pixelY: point.y});
});
const croppedRotationResult = landmarkSolver.solve(croppedRotationAnchors, {minimumAnchors: 4, outlierPixels: 1, cropX: 30, cropY: 40});
assert.strictEqual(croppedRotationResult.ok, true, 'solver should recover an authoritative rotated and cropped projection');
assert.deepStrictEqual(
  plain(landmarkSolver.project({worldX: 150, worldY: 50}, croppedRotationResult)),
  plain(landmarkSolver.project({worldX: 150, worldY: 50}, croppedRotationConfig)),
  'rotated/cropped candidate must preserve the authoritative landmark pixel'
);
for (let rotation = 0; rotation < 4; rotation += 1) {
  const rotatedAnchors = landmarkAnchors.map(anchor => {
    const point = landmarkSolver.project(anchor, {xoffset: 200, yoffset: 100, scale: 2, flipX: false, flipY: true, rotate: rotation, cropX: 0, cropY: 0});
    return Object.assign({}, anchor, {pixelX: point.x, pixelY: point.y});
  });
  const rotatedResult = landmarkSolver.solve(rotatedAnchors, {minimumAnchors: 4, outlierPixels: 10});
  assert.strictEqual(rotatedResult.ok, true, `solver should accept reflected rotation ${rotation}`);
  assert.strictEqual(rotatedResult.rotate, rotation, `solver should recover rotation ${rotation}`);
  assert.strictEqual(rotatedResult.flipY, true, `solver should recover reflection for rotation ${rotation}`);
}
const landmarkOutlier = landmarkAnchors.concat([{worldX: 220, worldY: 140, pixelX: -500, pixelY: 900}]);
const landmarkOutlierResult = landmarkSolver.solve(landmarkOutlier, {minimumAnchors: 4, outlierPixels: 10});
assert.strictEqual(landmarkOutlierResult.ok, true, 'solver should reject one gross calibration outlier');
assert.strictEqual(landmarkOutlierResult.inliers.length, 6, 'solver should retain at least four calibration anchors and both holdouts');
assert.strictEqual(landmarkSolver.solve(landmarkAnchors.slice(0, 3), {minimumAnchors: 4, outlierPixels: 10}).ok, false, 'solver should reject fewer than four calibration anchors');
assert.strictEqual(landmarkSolver.solve(landmarkAnchors.slice(0, 4), {minimumAnchors: 4, outlierPixels: 10}).ok, false, 'solver should reject candidates without two holdouts');
const collinearAnchors = landmarkAnchors.map(anchor => Object.assign({}, anchor, {
  worldY: anchor.worldX * 2,
  pixelX: 100 + anchor.worldX,
  pixelY: 50 + anchor.worldX * 2
}));
assert.strictEqual(landmarkSolver.solve(collinearAnchors, {minimumAnchors: 4, outlierPixels: 10}).ok, false, 'solver should reject collinear landmarks');
assert.strictEqual(landmarkSolver.solve(landmarkAnchors.concat([{worldX: NaN, worldY: 0, pixelX: 0, pixelY: 0}]), {minimumAnchors: 4, outlierPixels: 10}).ok, false, 'solver should reject non-finite landmarks');
const anisotropicAnchors = landmarkAnchors.map(anchor => Object.assign({}, anchor, {pixelX: 100 + anchor.worldX, pixelY: 50 - anchor.worldY * 0.25}));
assert.strictEqual(landmarkSolver.solve(anisotropicAnchors, {minimumAnchors: 4, outlierPixels: 10}).ok, false, 'solver should reject anisotropic residual growth');
const asymmetricHoldouts = landmarkAnchors.map(anchor => Object.assign({}, anchor));
asymmetricHoldouts[5].pixelX += 14;
const asymmetricHoldoutResult = landmarkSolver.solve(asymmetricHoldouts, {minimumAnchors: 4, outlierPixels: 10});
assert.strictEqual(asymmetricHoldoutResult.ok, false, 'each mandatory holdout must stay within tolerance, not just aggregate RMSE');
assert.ok(asymmetricHoldoutResult.maximumResidual >= 14, 'maximum residual should include every mandatory holdout');
assert.deepStrictEqual(
  Array.from(adminGeometry.offsetDelta(10, 20, {width: 640, height: 512}, 1280, 1024, 4, 0)),
  [80, 160],
  'responsive drag should convert CSS movement into native canvas offsets'
);
assert.deepStrictEqual(
  Array.from(adminGeometry.offsetDelta(10, 20, {width: 640, height: 512}, 1280, 1024, 4, 1)),
  [160, -80],
  'responsive drag should unrotate native canvas offsets before updating calibration'
);
assert.deepStrictEqual(
  Array.from(adminGeometry.canvasDelta(10, 20, {width: 1280, height: 1024}, 1280, 1024)),
  [10, 20],
  'native-size display should preserve the client drag delta'
);
assert.deepStrictEqual(
  Array.from(adminGeometry.canvasDelta(10, 20, {width: 640, height: 2048}, 1280, 1024)),
  [20, 10],
  'responsive drag should preserve independent horizontal and vertical scale factors'
);
assert.deepStrictEqual(
  Array.from(adminGeometry.canvasDelta(10, 20, {width: 0, height: 0}, 1280, 1024)),
  [12800, 20480],
  'zero display rectangle dimensions should stay finite for a safe drag result'
);
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
assert.deepStrictEqual(
  plain(adminPayload.build('save', identity, controls, true, 'a'.repeat(64), 'b'.repeat(64))),
	{action: 'save', game: 'cstrike', map: 'de_dust2', overviewText: '', xoffset: '0', yoffset: '0', scale: '1', flipy: 0, configHash: 'a'.repeat(64), previewToken: 'b'.repeat(64)},
  'save should carry the last server-issued configuration hash'
);
assert.match(source, /'X-HLX-CSRF'/, 'admin mutations should carry the session-bound CSRF header');
assert.doesNotMatch(source, /innerHTML/, 'untrusted heatmap payloads must be rendered with DOM text nodes');
assert.doesNotMatch(source, /data-heatmap-admin-regenerate/, 'the browser must not expose server-side regeneration');
assert.match(source, /bindClick\('\[data-heatmap-admin-load\]', requestStoredConfig\);/, 'Load button should request stored config');
assert.match(source, /mapSelect\.onchange = function\(\) \{ invalidatePreviewToken\(\); requestStoredConfig\(\); \};/, 'map change should invalidate authorization before requesting stored config');
assert.match(source, /fields\[fieldIndex\]\.oninput = schedulePreview;/, 'new floor-row inputs should invalidate projection authorization');
assert.match(source, /if \(error && error\.code === 'preview_required'\) \{\s*invalidatePreviewToken\(\);/, 'preview-required responses should clear the local authorization token');
assert.match(source, /if \(activeMap\(\)\) \{\s*requestStoredConfig\(\);/, 'initial wizard load should request stored config');
assert.match(source, /bindClick\('\[data-heatmap-admin-preview\]', function\(\) \{ request\('preview'\); \}\);/, 'Preview button should send current controls');
assert.match(source, /request\('preview', token\);/, 'scheduled preview should send current controls');

console.log('heatmap JS projection smoke ok');

const tabsSource = fs.readFileSync('web/includes/js/tabs.js', 'utf8');
function tabsUpdateTabHarness(html, options = {}) {
  const events = [];
  let documentScans = 0;
  const mountCalls = [];
  const container = {children: []};
  const loading = {
    destroyed: false,
    destroy() {
      this.destroyed = true;
      events.push('destroyLoading');
    },
  };
  function FakeElement(tag) {
    return {
      tag,
      html: '',
      containsExplorer: false,
      set(name, value) {
        if (name === 'html') {
          this.html = String(value);
          this.containsExplorer = /data-heatmap-explorer=(["'])1\1/.test(this.html);
          events.push('setHtml');
        }
        return this;
      },
      injectInside(parent) {
        parent.children.push(this);
        events.push('injectInside');
        return this;
      },
      getElement(selector) {
        events.push(`getElement:${selector}`);
        if (selector === '[data-heatmap-explorer="1"]' && this.containsExplorer) {
          return {nodeType: 1};
        }
        return null;
      },
    };
  }
  const tabsWindow = {
    HeatmapExplorerWorkspace: {
      mountAll(root, mountOptions) {
        events.push('mountAll');
        mountCalls.push({root, mountOptions});
      },
    },
  };
  const tabsContext = {
    console,
    window: tabsWindow,
    document: {
      querySelectorAll() {
        documentScans += 1;
        return [];
      },
    },
    Options: function Options() {},
    Class: function Class(definition) {
      function Klass() {}
      Object.assign(Klass.prototype, definition);
      return Klass;
    },
    Element: FakeElement,
    $: value => value,
  };
  vm.runInNewContext(tabsSource, tabsContext, {filename: 'tabs.js'});
  const responseText = new String(html);
  responseText.stripScripts = flag => {
    events.push(`stripScripts:${flag}`);
    return String(responseText).replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  };
  const instance = {
    loading,
    elements: [],
    currentRequest: {options: {currentTab: options.currentTab ?? 1}},
    container,
  };
  tabsContext.Tabs.prototype.updateTab.call(instance, responseText);
  return {
    container,
    currentTab: options.currentTab ?? 1,
    documentScans,
    events,
    instance,
    mountCalls,
    tabsWindow,
  };
}

const ajaxExplorerTab = tabsUpdateTabHarness(
  '<div class="tab-pane"><div data-heatmap-explorer="1"></div><script>window.__ajaxInline = true;</script></div>'
);
assert.strictEqual(ajaxExplorerTab.instance.loading.destroyed, true, 'Tabs.updateTab should remove the loading placeholder before mounting AJAX content');
assert.strictEqual(ajaxExplorerTab.container.children.length, 1, 'Tabs.updateTab should inject exactly one wrapper for the AJAX response');
assert.strictEqual(ajaxExplorerTab.instance.elements[ajaxExplorerTab.currentTab], ajaxExplorerTab.container.children[0], 'Tabs.updateTab should cache the newly injected wrapper for the current tab');
assert.ok(
  ajaxExplorerTab.events.indexOf('injectInside') < ajaxExplorerTab.events.indexOf('stripScripts:true'),
  'Tabs.updateTab should keep the existing AJAX insertion-before-stripScripts order'
);
assert.ok(
  ajaxExplorerTab.events.indexOf('stripScripts:true') < ajaxExplorerTab.events.indexOf('mountAll'),
  'Tabs.updateTab should mount the explorer only after inline scripts stay on the stripScripts(true) path'
);
assert.strictEqual(ajaxExplorerTab.mountCalls.length, 1, 'Tabs.updateTab should mount exactly once when the AJAX subtree contains an explorer root');
assert.strictEqual(ajaxExplorerTab.mountCalls[0].root, ajaxExplorerTab.container.children[0], 'Tabs.updateTab should mount on the newly inserted wrapper, not on the whole document');
assert.strictEqual(ajaxExplorerTab.mountCalls[0].mountOptions.window, ajaxExplorerTab.tabsWindow, 'Tabs.updateTab should pass the live window object through to mountAll');
assert.strictEqual(ajaxExplorerTab.documentScans, 0, 'Tabs.updateTab should not rescan the whole document after AJAX insertion');
assert.strictEqual(ajaxExplorerTab.instance.currentRequest, false, 'Tabs.updateTab should clear currentRequest after a successful AJAX update');

const ajaxPlainTab = tabsUpdateTabHarness(
  '<div class="tab-pane"><p>Plain AJAX content</p><script>window.__ajaxPlain = true;</script></div>'
);
assert.deepStrictEqual(ajaxPlainTab.mountCalls, [], 'Tabs.updateTab should not call explorer mountAll for plain non-explorer AJAX HTML');
assert.ok(
  ajaxPlainTab.events.includes('stripScripts:true'),
  'Tabs.updateTab should keep the existing inline script execution path for plain AJAX HTML'
);
assert.strictEqual(ajaxPlainTab.instance.currentRequest, false, 'Tabs.updateTab should still clear currentRequest for plain AJAX HTML');

console.log('tabs JS contract smoke ok');

const explorerSource = fs.readFileSync('web/includes/js/heatmap-explorer.js', 'utf8');
const cssSource = fs.readFileSync('web/hlstats.css', 'utf8');
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
    coverage: {
      sourceRows: 8,
      candidate: 8,
      validXY: 8,
      validZ: 8,
      zHistogram: [{z: 0, count: 8}],
      missingCoordinates: 0,
      malformedCoordinates: 0,
      assigned: 8,
      unassigned: 0,
      xyCoverage: 1,
      zCoverage: 1,
      projected: 8,
      inBounds: 8,
      outOfBounds: 0,
      projectionCoverage: 1,
    },
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
  {
    sourceRows: 8,
    candidate: 8,
    validXY: 8,
    validZ: 8,
    zHistogram: [{z: 0, count: 8}],
    missingCoordinates: 0,
    malformedCoordinates: 0,
    assigned: 8,
    unassigned: 0,
    xyCoverage: 1,
    zCoverage: 1,
    projected: 8,
    inBounds: 8,
    outOfBounds: 0,
    projectionCoverage: 1,
  },
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
assert.doesNotThrow(
  () => new HeatmapExplorerScene(explorerSceneFixture({
    coverage: Object.assign({}, explorerSceneFixture().coverage, {
      zHistogram: [{z: -64, count: 1}, {z: 32, count: 2}],
    }),
  })),
  'coverage should accept the authoritative zHistogram row shape'
);
assertInvalidScene(payload => { payload.coverage.zHistogram = [{z: '-64', count: 1}]; }, 'zHistogram z buckets should stay numeric');
assertInvalidScene(payload => { payload.coverage.zHistogram = [{z: -64, count: -1}]; }, 'zHistogram counts should stay nonnegative');
assertInvalidScene(payload => { payload.coverage.zHistogram = [{z: -64, count: 1, extra: 2}]; }, 'zHistogram rows should stay strict two-field objects');

function blockedSceneFixture(state, overrides = {}) {
  const payload = explorerSceneFixture({
    state,
    layers: {total: [], me: [], others: []},
    comparison: {
      fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
      bins: [],
      personalSample: 0,
      otherSample: 0,
    },
  });
  if (state === 'floors_unavailable') {
    payload.query = Object.assign({}, payload.query, {floor: 'upper'});
    payload.activeFloor = 'upper';
    payload.floors = [
      {id: 'main', label: 'Main', count: 3, available: true},
      {id: 'upper', label: 'Upper', count: 1, available: false},
    ];
  }
  return Object.assign(payload, overrides);
}

for (const state of ['missing_coordinates', 'floors_unavailable', 'weak_projection', 'too_many_events']) {
  assert.doesNotThrow(
    () => new HeatmapExplorerScene(blockedSceneFixture(state)),
    `scene state ${state} should remain a valid explicit terminal payload`
  );
}

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
const insufficientScene = new HeatmapExplorerScene(explorerSceneFixture({
  state: 'insufficient_sample',
  query: Object.assign({}, explorerSceneFixture().query, {lens: 'difference', event: 'kills'}),
  layers: {
    total: [['c0.0', 0, 0, 5, 0]],
    me: [['c0.0', 0, 0, 2, 0]],
    others: [['c0.0', 0, 0, 3, 0]],
  },
  comparison: {
    fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
    bins: [],
    personalSample: 2,
    otherSample: 3,
  },
}));
assert.strictEqual(insufficientScene.state, 'insufficient_sample');

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

function parseAspectRatioValue(value) {
  const match = /^([0-9]+(?:\.[0-9]+)?)\s*\/\s*([0-9]+(?:\.[0-9]+)?)$/.exec(String(value || ''));
  if (!match) {
    return null;
  }
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return {width, height};
}

function makeDom(gl) {
  const listenerMap = () => Object.create(null);
  function element(attributes = {}) {
    const listeners = listenerMap();
    let clientWidth = 320;
    let clientHeight = 240;
    const node = {
      attributes: Object.assign({}, attributes),
      style: {},
      hidden: false,
      width: 0,
      height: 0,
      textContent: '',
      captures: [],
      contextCalls: [],
      releasedCaptures: [],
      listeners,
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name]; },
      removeAttribute(name) { delete this.attributes[name]; },
      addEventListener(type, handler) { (listeners[type] || (listeners[type] = [])).push(handler); },
      removeEventListener(type, handler) {
        if (!listeners[type]) return;
        listeners[type] = listeners[type].filter(candidate => candidate !== handler);
      },
      setPointerCapture(pointerId) { this.captures.push(pointerId); },
      releasePointerCapture(pointerId) { this.releasedCaptures.push(pointerId); },
      dispatchEvent(event) {
        (listeners[event.type] || []).slice().forEach(handler => handler(event));
        return true;
      },
      getContext(type, attrs) {
        node.contextCalls.push({
          type,
          attrs: attrs ? Object.assign({}, attrs) : attrs,
        });
        return gl;
      },
    };
    Object.defineProperty(node, 'clientWidth', {
      enumerable: true,
      get() { return clientWidth; },
      set(value) { clientWidth = value; },
    });
    Object.defineProperty(node, 'clientHeight', {
      enumerable: true,
      get() {
        const aspect = parseAspectRatioValue(node.style && node.style.aspectRatio);
        if (aspect && node.attributes['data-heatmap-sized'] === '1') {
          return Math.round(clientWidth * aspect.height / aspect.width);
        }
        return clientHeight;
      },
      set(value) { clientHeight = value; },
    });
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
  let textureCreates = 0;
  const calls = {
    textures: [],
    texImages: [],
    shaderSources: [],
    draws: 0,
    programs: 0,
    buffers: 0,
    activeTextures: [],
    boundTextures: [],
    uniform1f: [],
    uniform1i: [],
    uniform2f: [],
    viewports: [],
    deleted: {shaders: [], programs: [], buffers: [], textures: []},
  };
  const gl = {
    VERTEX_SHADER: 35633, FRAGMENT_SHADER: 35632, COMPILE_STATUS: 35713, LINK_STATUS: 35714,
    ARRAY_BUFFER: 34962, STATIC_DRAW: 35044, FLOAT: 5126, TEXTURE_2D: 3553,
    TEXTURE_MIN_FILTER: 10241, TEXTURE_MAG_FILTER: 10240, TEXTURE_WRAP_S: 10242,
    TEXTURE_WRAP_T: 10243, TEXTURE0: 33984, TEXTURE1: 33985,
    NEAREST: 9728, CLAMP_TO_EDGE: 33071, R32F: 33326,
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
      textureCreates += 1;
      if (options.createTextureFailure || options.createTextureFailureAt === textureCreates) return null;
      const texture = {id: ++nextId};
      calls.textures.push(texture);
      return texture;
    },
    bindTexture(target, texture) {
      calls.boundTextures.push({
        activeTexture: calls.activeTextures.length > 0 ? calls.activeTextures[calls.activeTextures.length - 1] : gl.TEXTURE0,
        target,
        texture: texture ? texture.id : null,
      });
    },
    texParameteri() {},
    texImage2D(...args) { calls.texImages.push(args); if (options.textureFailure) throw new Error('texture failure'); },
    deleteTexture(texture) { calls.deleted.textures.push(texture.id); },
    useProgram() {},
    getAttribLocation() { return 0; },
    enableVertexAttribArray() {},
    vertexAttribPointer() {},
    getUniformLocation(_program, name) { return {name}; },
    uniform1f(location, value) { calls.uniform1f.push({name: location ? location.name : null, value}); },
    uniform1i(location, value) { calls.uniform1i.push({name: location ? location.name : null, value}); },
    uniform2f(location, x, y) { calls.uniform2f.push({name: location ? location.name : null, value: [x, y]}); },
    activeTexture(value) { calls.activeTextures.push(value); },
    drawArrays() { calls.draws += 1; if (options.drawFailure) throw new Error('draw failure'); },
    viewport(x, y, width, height) { calls.viewports.push([x, y, width, height]); },
    clearColor() {},
    clear() {},
    getError() { return options.errorCode || 0; },
    getExtension(name) { calls.extension = name; return options.extensionNull ? null : {}; },
  };
  gl.calls = calls;
  return gl;
}

function fragmentShaderSource(gl) {
  const fragment = gl.calls.shaderSources.find(source => source.includes('differenceBlueNeutralAmber'));
  assert.ok(fragment, 'renderer should compile and retain the fragment shader source');
  return fragment;
}

function clampGridIndex(value, limit) {
  return Math.max(0, Math.min(limit - 1, value));
}

function kernelAverage(upload, width, height, gridX, gridY) {
  let sum = 0;
  for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
    for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
      const sampleX = clampGridIndex(gridX + offsetX, width);
      const sampleY = clampGridIndex(gridY + offsetY, height);
      sum += upload[sampleY * width + sampleX];
    }
  }
  return sum / 9;
}

function normalizedAmount(value, maxAbs) {
  return Math.max(0, Math.min(1, Math.abs(value) / Math.max(maxAbs, 0.000001)));
}

function sqrtNormalizedAmount(value, maxAbs) {
  return Math.sqrt(normalizedAmount(value, maxAbs));
}

function differenceHue(value) {
  return value < 0 ? -1 : (value > 0 ? 1 : 0);
}

function differencePresentationAlpha(value, maxAbs, confidence) {
  if (value === 0) {
    return 0;
  }
  return Math.max(sqrtNormalizedAmount(value, maxAbs) * confidence, 0.22);
}

function kernelDisplayMax(upload, width, height) {
  let maxAbs = 0;
  for (let gridY = 0; gridY < height; gridY += 1) {
    for (let gridX = 0; gridX < width; gridX += 1) {
      maxAbs = Math.max(maxAbs, Math.abs(kernelAverage(upload, width, height, gridX, gridY)));
    }
  }
  return maxAbs;
}

function assertSparseDisplayNormalization() {
  const width = 7;
  const height = 3;
  const sparseUpload = new Float32Array(width * height);
  sparseUpload[1 * width + 1] = 1;
  sparseUpload[1 * width + 4] = 3;
  sparseUpload[1 * width + 5] = 12;
  const rawMaxAbs = 12;
  const singletonAverage = kernelAverage(sparseUpload, width, height, 1, 1);
  const peakAverage = kernelAverage(sparseUpload, width, height, 5, 1);
  const displayMax = kernelDisplayMax(sparseUpload, width, height);
  const legacySingletonAlpha = normalizedAmount(singletonAverage, rawMaxAbs);
  const legacyPeakAlpha = normalizedAmount(peakAverage, rawMaxAbs);
  const legibilityThreshold = 0.2;

  assert.ok(Math.abs(singletonAverage - (1 / 9)) < 1e-7, 'sparse singleton should keep one occupied texel in the clamped 3x3 average');
  assert.ok(Math.abs(peakAverage - (15 / 9)) < 1e-7, 'sparse peak should include the documented 12+3 neighborhood sum');
  assert.ok(Math.abs(displayMax - (15 / 9)) < 1e-7, 'display max should be the maximum clamped 3x3 average');
  assert.ok(Math.abs(legacySingletonAlpha - (1 / 108)) < 1e-12, 'legacy sparse singleton alpha should be 0.009259...');
  assert.ok(Math.abs(legacyPeakAlpha - (15 / 108)) < 1e-12, 'legacy sparse peak alpha should be 0.138889...');
  assert.ok(legacySingletonAlpha < legibilityThreshold, 'legacy singleton must fail the legibility predicate');
  assert.ok(legacyPeakAlpha < legibilityThreshold, 'legacy peak must fail the legibility predicate');

  const sparsePayload = explorerSceneFixture({
    query: Object.assign({}, explorerSceneFixture().query, {lens: 'overview', event: 'kills'}),
    grid: {
      bucketSize: 8,
      width,
      height,
      fields: ['cell', 'x', 'y', 'kills', 'deaths'],
    },
    layers: {
      total: [['c1.1', 1, 1, 1, 2], ['c4.1', 4, 1, 3, 6], ['c5.1', 5, 1, 12, 8]],
      me: [['c1.1', 1, 1, 0, 0], ['c4.1', 4, 1, 0, 0], ['c5.1', 5, 1, 0, 0]],
      others: [['c1.1', 1, 1, 1, 2], ['c4.1', 4, 1, 3, 6], ['c5.1', 5, 1, 12, 8]],
    },
    comparison: {
      fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
      bins: [],
      personalSample: 0,
      otherSample: 16,
    },
    summary: {rowsRead: 3, sourceRows: 3, personalSample: 0, otherSample: 16},
  });
  const sparseScene = new HeatmapExplorerScene(sparsePayload);
  const sparseDense = sparseScene.dense('total', 'kills');
  assert.strictEqual(sparseDense.maxAbs, rawMaxAbs, 'dense raw max must remain the unblurred maximum');
  const sparseGl = fakeGl();
  const sparseDom = makeDom(sparseGl);
  const sparseRenderer = new HeatmapGlRenderer(sparseDom.root, sparseScene, {window: sparseDom.window});
  sparseRenderer.mount();
  assert.ok(sparseGl.calls.draws > 0, 'legacy renderer could call drawArrays even when sparse data was illegible');
  const displayMaxUniform = sparseGl.calls.uniform1f.find(call => call.name === 'u_displayMax');
  assert.ok(displayMaxUniform, 'ordinary rendering must pass a separate post-convolution display max');
  assert.ok(Math.abs(displayMaxUniform.value - displayMax) < 1e-7, 'display max uniform should match the clamped 3x3 model');
  assert.ok(Math.abs(sqrtNormalizedAmount(singletonAverage, displayMax) - 0.2581988897) < 1e-7, 'sparse singleton should use sqrt(1/15) presentation intensity');
  assert.strictEqual(sqrtNormalizedAmount(peakAverage, displayMax), 1, 'sparse peak should remain full presentation intensity');
  const sparseDeathDense = sparseScene.dense('total', 'deaths');
  const deathDisplayMax = kernelDisplayMax(sparseDeathDense.values, width, height);
  sparseRenderer.render({layer: 'total', channel: 'deaths'});
  const deathDisplayMaxUniform = sparseGl.calls.uniform1f
    .slice().reverse().find(call => call.name === 'u_displayMax');
  assert.ok(deathDisplayMax > 0 && deathDisplayMax <= sparseDeathDense.maxAbs, 'deaths should retain a bounded post-convolution display range');
  assert.ok(deathDisplayMaxUniform, 'deaths rendering must pass its own post-convolution display max');
  assert.ok(Math.abs(deathDisplayMaxUniform.value - deathDisplayMax) < 1e-7, 'deaths display max uniform should match its clamped 3x3 model');
  const sparseFragment = fragmentShaderSource(sparseGl);
  assert.match(sparseFragment, /sqrt\(/, 'sparse ordinary rendering must apply sqrt presentation scaling');
  sparseRenderer.destroy();
}

assertSparseDisplayNormalization();

function cssAtRuleBlock(source, marker) {
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `missing CSS block: ${marker}`);
  const open = source.indexOf('{', start + marker.length);
  assert.ok(open >= 0, `missing CSS block opener: ${marker}`);
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') {
      depth += 1;
    } else if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return {
          full: source.slice(start, index + 1),
          body: source.slice(open + 1, index),
        };
      }
    }
  }
  throw new Error(`unterminated CSS block: ${marker}`);
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
assert.deepStrictEqual(
  dom.nodes.canvas.contextCalls,
  [{type: 'webgl2', attrs: {alpha: true, antialias: false, premultipliedAlpha: false}}],
  'renderer should request a straight-alpha WebGL2 context without antialiasing'
);
assert.strictEqual(goodGl.calls.textures.length, 2, 'renderer should create separate density and opacity textures');
assert.strictEqual(goodGl.calls.buffers, 1, 'renderer should create one full-quad buffer');
assert.strictEqual(goodGl.calls.programs, 1, 'renderer should create one program');
assert.strictEqual(goodGl.calls.texImages.length, 2, 'initial render should upload density and opacity textures');
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
const initialDensityUpload = goodGl.calls.texImages[0].at(-1);
const initialOpacityUpload = goodGl.calls.texImages[1].at(-1);
assert.strictEqual(initialDensityUpload[2], Math.fround(-0.1333333333), 'difference density uploads should preserve raw signed values');
assert.strictEqual(initialOpacityUpload[2], Math.fround(0.22), 'difference opacity uploads should carry low-sample confidence separately');
assert.deepStrictEqual(
  goodGl.calls.uniform1i
    .filter(call => call.name === 'u_density' || call.name === 'u_opacity')
    .slice(-2),
  [{name: 'u_density', value: 0}, {name: 'u_opacity', value: 1}],
  'difference rendering should bind density and opacity samplers to separate texture units'
);
renderer.render({layer: 'difference', channel: 'kills'});
const rerenderDensityUpload = goodGl.calls.texImages[goodGl.calls.texImages.length - 2].at(-1);
const rerenderOpacityUpload = goodGl.calls.texImages[goodGl.calls.texImages.length - 1].at(-1);
assert.strictEqual(Object.prototype.toString.call(rerenderDensityUpload), '[object Float32Array]', 'difference density upload should remain Float32Array');
assert.strictEqual(Object.prototype.toString.call(rerenderOpacityUpload), '[object Float32Array]', 'difference opacity upload should remain Float32Array');
assert.strictEqual(rerenderDensityUpload[2], Math.fround(-0.1333333333));
assert.strictEqual(rerenderOpacityUpload[2], Math.fround(0.22));
assert.strictEqual(goodGl.calls.textures.length, 2);
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
const differenceFragment = fragmentShaderSource(goodGl);
assert.match(
  differenceFragment,
  /uniform sampler2D u_opacity;/,
  'difference rendering should sample a dedicated opacity texture'
);
assert.match(
  differenceFragment,
  /float center = texture\(u_density, sampleUv\)\.r;/,
  'difference rendering should sample the center texel directly'
);
assert.match(
  differenceFragment,
  /float value = u_palette == 2 \? center : sum \/ 9\.0;/,
  'difference palette should bypass the shared 3x3 smoothing while total\/me\/others keep it'
);
assert.match(
  differenceFragment,
  /float rawMaxAbs = max\(u_maxAbs, 0\.000001\);/,
  'difference normalization should retain the raw signed maximum separately'
);
assert.match(
  differenceFragment,
  /sqrt\(clamp\(abs\(center\) \/ rawMaxAbs, 0\.0, 1\.0\)\)/,
  'difference alpha should use sqrt presentation scaling on the signed center sample'
);
assert.match(
  differenceFragment,
  /float differenceHue = center < 0\.0 \? -1\.0 : \(center > 0\.0 \? 1\.0 : 0\.0\);/,
  'difference hue should use the full signed palette endpoints while alpha carries magnitude'
);
assert.match(
  differenceFragment,
  /float alpha = u_palette == 2\n\s+\? \(center == 0\.0 \? 0\.0 : max\(amount \* confidence, 0\.22\)\)\n\s+: amount \* confidence;/,
  'difference alpha should floor occupied pixels after confidence while preserving confidence multiplication'
);
assert.match(
  differenceFragment,
  /differenceBlueNeutralAmber\(differenceHue\)/,
  'difference palette should receive the signed endpoint rather than the near-neutral raw ratio'
);
assert.strictEqual(differencePresentationAlpha(0, 1, 1), 0, 'zero difference should remain transparent');
assert.strictEqual(differencePresentationAlpha(0.01, 1, 1), 0.22, 'tiny high-confidence difference should meet the alpha floor');
assert.strictEqual(differencePresentationAlpha(-0.01, 1, 0.22), 0.22, 'tiny low-confidence difference should remain visibly muted at the floor');
assert.strictEqual(differencePresentationAlpha(0.25, 1, 0.22), 0.22, 'low-confidence difference should retain its muted cap');
assert.strictEqual(differencePresentationAlpha(0.25, 1, 1), 0.5, 'high-confidence difference alpha should retain sqrt magnitude growth');
assert.ok(differencePresentationAlpha(0.25, 1, 1) > 0.22, 'difference alpha should grow above the floor with magnitude');
assert.strictEqual(differenceHue(0), 0, 'zero difference should keep the neutral hue but remain transparent');
assert.strictEqual(differenceHue(0.01), 1, 'positive difference should use the full warm endpoint');
assert.strictEqual(differenceHue(-0.01), -1, 'negative difference should use the full cool endpoint');
assert.match(
  differenceFragment,
  /float confidence = u_palette == 2 \? clamp\(texture\(u_opacity, sampleUv\)\.r, 0\.0, 1\.0\) : 1\.0;/,
  'difference alpha should come from the dedicated opacity texture while non-difference layers remain fully opaque'
);
assert.match(
  differenceFragment,
  /outputColor = vec4\(mix\(color, vec3\(1\.0\), contour\), alpha\);/,
  'difference alpha should combine normalized amount with confidence'
);
const signedDifferencePayload = explorerSceneFixture({
  grid: {
    bucketSize: 8,
    width: 3,
    height: 3,
    fields: ['cell', 'x', 'y', 'kills', 'deaths'],
  },
  layers: {
    total: [['c0.1', 0, 1, 3, 0], ['c1.1', 1, 1, 4, 0], ['c2.1', 2, 1, 3, 0]],
    me: [['c0.1', 0, 1, 3, 0], ['c1.1', 1, 1, 4, 0], ['c2.1', 2, 1, 3, 0]],
    others: [['c0.1', 0, 1, 0, 0], ['c1.1', 1, 1, 0, 0], ['c2.1', 2, 1, 0, 0]],
  },
  comparison: {
    fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
    bins: [['c0.1', 0, 1, -0.8, 0, 3], ['c1.1', 1, 1, 0.8, 0, 4], ['c2.1', 2, 1, -0.8, 0, 3]],
    personalSample: 10,
    otherSample: 0,
  },
  summary: {rowsRead: 3, sourceRows: 3, personalSample: 10, otherSample: 0},
});
const signedDifferenceScene = new HeatmapExplorerScene(signedDifferencePayload);
const signedDifferenceGl = fakeGl();
const signedDifferenceDom = makeDom(signedDifferenceGl);
const signedDifferenceRenderer = new HeatmapGlRenderer(signedDifferenceDom.root, signedDifferenceScene, {
  window: signedDifferenceDom.window,
});
signedDifferenceRenderer.mount();
const signedDifferenceUpload = signedDifferenceGl.calls.texImages[signedDifferenceGl.calls.texImages.length - 2].at(-1);
const signedDifferenceDense = signedDifferenceScene.dense('difference', 'kills');
const signedCenter = signedDifferenceUpload[4];
const signedSmoothed = kernelAverage(signedDifferenceUpload, 3, 3, 1, 1);
assert.ok(signedCenter > 0, 'signed difference center texel should remain positive before shader sampling');
assert.ok(signedSmoothed < 0, 'the legacy shared 3x3 average would flip adjacent opposite-sign deltas negative');
assert.ok(
  normalizedAmount(signedCenter, signedDifferenceDense.maxAbs) > normalizedAmount(signedSmoothed, signedDifferenceDense.maxAbs),
  'difference center sampling should preserve stronger signed intensity than the shared 3x3 smoothing path'
);
signedDifferenceRenderer.destroy();

const sparseDifferencePayload = explorerSceneFixture({
  grid: {
    bucketSize: 8,
    width: 3,
    height: 3,
    fields: ['cell', 'x', 'y', 'kills', 'deaths'],
  },
  layers: {
    total: [['c0.1', 0, 1, 2, 0], ['c1.1', 1, 1, 2, 0], ['c2.1', 2, 1, 2, 0]],
    me: [['c0.1', 0, 1, 2, 0], ['c1.1', 1, 1, 2, 0], ['c2.1', 2, 1, 2, 0]],
    others: [['c0.1', 0, 1, 0, 0], ['c1.1', 1, 1, 0, 0], ['c2.1', 2, 1, 0, 0]],
  },
  comparison: {
    fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
    bins: [['c0.1', 0, 1, 0, 0, 2], ['c1.1', 1, 1, 0.2, 0, 2], ['c2.1', 2, 1, 0, 0, 2]],
    personalSample: 6,
    otherSample: 0,
  },
  summary: {rowsRead: 3, sourceRows: 3, personalSample: 6, otherSample: 0},
});
const sparseDifferenceScene = new HeatmapExplorerScene(sparseDifferencePayload);
const sparseDifferenceGl = fakeGl();
const sparseDifferenceDom = makeDom(sparseDifferenceGl);
const sparseDifferenceRenderer = new HeatmapGlRenderer(sparseDifferenceDom.root, sparseDifferenceScene, {
  window: sparseDifferenceDom.window,
});
sparseDifferenceRenderer.mount();
const sparseDifferenceUpload = sparseDifferenceGl.calls.texImages[sparseDifferenceGl.calls.texImages.length - 2].at(-1);
const sparseDifferenceOpacityUpload = sparseDifferenceGl.calls.texImages[sparseDifferenceGl.calls.texImages.length - 1].at(-1);
const sparseDifferenceDense = sparseDifferenceScene.dense('difference', 'kills');
const sparseCenter = sparseDifferenceUpload[4];
const sparseSmoothed = kernelAverage(sparseDifferenceUpload, 3, 3, 1, 1);
assert.ok(Math.abs(sparseCenter - Math.fround(0.2)) < 1e-6, 'difference density upload should preserve the sparse signed delta before confidence is applied');
assert.ok(Math.abs(sparseDifferenceOpacityUpload[4] - Math.fround(0.22)) < 1e-6, 'difference opacity upload should preserve the existing low-sample opacity cap');
assert.ok(
  normalizedAmount(sparseCenter, sparseDifferenceDense.maxAbs) > normalizedAmount(sparseSmoothed, sparseDifferenceDense.maxAbs),
  'difference center sampling should keep isolated sparse deltas visible instead of forcing them through the shared 3x3 average'
);
sparseDifferenceRenderer.destroy();

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
const stateBeforeContextLoss = 'scene_ready';
const statusBeforeContextLoss = 'Loaded: Coverage 100%';
const drawsBeforeContextLoss = goodGl.calls.draws;
const selectionBeforeContextLoss = Object.assign({}, renderer._selection);
dom.root.setAttribute('data-heatmap-state', stateBeforeContextLoss);
dom.nodes.status.textContent = statusBeforeContextLoss;
dom.nodes.canvas.dispatchEvent({type: 'webglcontextlost', preventDefault() { prevented = true; }});
assert.strictEqual(prevented, true);
assert.strictEqual(dom.root.attributes['data-heatmap-state'], 'context_lost');
assert.strictEqual(dom.nodes.status.textContent, '<context_lost>');
assert.notStrictEqual(dom.nodes.static.style.display, 'none');
assert.deepStrictEqual(
  deletedResources(goodGl).textures,
  goodGl.calls.textures.slice(0, 2).map(texture => texture.id),
  'context loss should release both density and opacity textures before restore'
);
dom.nodes.canvas.dispatchEvent({type: 'webglcontextrestored'});
assert.ok(goodGl.calls.programs >= 2, 'context restore should rebuild resources');
assert.strictEqual(goodGl.calls.textures.length, 4, 'context restore should rebuild both density and opacity textures');
assert.strictEqual(dom.nodes.canvas.contextCalls.length, 1, 'context restore should reuse the original WebGL2 context instead of calling getContext again');
assert.strictEqual(dom.root.attributes['data-heatmap-state'], stateBeforeContextLoss, 'successful context restore should clear the transient context-loss state');
assert.strictEqual(dom.nodes.status.textContent, statusBeforeContextLoss, 'successful context restore should restore the pre-loss status text');
assert.ok(goodGl.calls.draws > drawsBeforeContextLoss, 'successful context restore should redraw the preserved scene');
assert.strictEqual(renderer._selection.layer, selectionBeforeContextLoss.layer, 'successful context restore should preserve the active layer');
assert.strictEqual(renderer._selection.channel, selectionBeforeContextLoss.channel, 'successful context restore should preserve the active channel');
renderer.destroy();
renderer.destroy();
assert.strictEqual((dom.nodes.canvas.listeners.webglcontextlost || []).length, 0);
assert.strictEqual((dom.nodes.canvas.listeners.webglcontextrestored || []).length, 0);
assert.strictEqual((dom.window.listeners.resize || []).length, 0);
assert.deepStrictEqual(
  deletedResources(goodGl).textures,
  goodGl.calls.textures.map(texture => texture.id),
  'destroy should release both original and restored density/opacity textures exactly once'
);

const restoreFailureGl = fakeGl({createTextureFailureAt: 3});
const restoreFailureDom = makeDom(restoreFailureGl);
const restoreFailureRenderer = new HeatmapGlRenderer(restoreFailureDom.root, validScene, {
  window: restoreFailureDom.window,
  message: code => `<${code}>`,
});
restoreFailureRenderer.mount();
restoreFailureDom.nodes.status.textContent = 'Loaded: Coverage 100%';
restoreFailureDom.nodes.canvas.dispatchEvent({type: 'webglcontextlost', preventDefault() {}});
restoreFailureDom.nodes.canvas.dispatchEvent({type: 'webglcontextrestored'});
assert.strictEqual(restoreFailureDom.root.attributes['data-heatmap-state'], 'static_fallback', 'failed context restore should retain the static fallback state');
assert.strictEqual(restoreFailureDom.nodes.status.textContent, '<static_fallback>', 'failed context restore should keep the localized static fallback status');
assert.strictEqual(restoreFailureDom.nodes.interactive.style.display, 'none', 'failed context restore should hide the unusable interactive canvas');
assert.strictEqual(restoreFailureDom.nodes.static.style.display, '', 'failed context restore should keep the JPEG fallback visible');
restoreFailureRenderer.destroy();

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
  'first texture allocation failure'
);
assertResourceCleanup(
  {createTextureFailureAt: 2},
  {shaders: [1, 2], programs: [3], buffers: [4], textures: [5]},
  'second texture allocation failure'
);

assert.strictEqual(/innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new\s+Function/.test(explorerSource), false, 'renderer source must not use unsafe HTML/eval APIs');
assert.match(explorerSource, /R32F/);
assert.match(explorerSource, /RED/);
assert.match(explorerSource, /CLAMP_TO_EDGE/);
assert.match(explorerSource, /for \(var offsetY = -1; offsetY <= 1; offsetY\+\+\)/);
assert.match(explorerSource, /amber|orange/i);
assert.match(explorerSource, /cyan|blue/i);
assert.match(explorerSource, /contour/i);
assert.doesNotMatch(explorerSource, /pointerPan:\s*false/, 'workspace should not hard-code pointer pan off');
assert.match(explorerSource, /consumeSuppressedClick/, 'renderer should expose drag-based click suppression');
assert.match(explorerSource, /data-heatmap-pan-active/, 'workspace should expose a scoped pan-active hook');
assert.match(explorerSource, /data-heatmap-v1-url/, 'workspace should expose a trustworthy legacy route hook');
assert.match(cssSource, /touch-action:\s*none/, 'pan mode should explicitly disable touch scrolling only while active');
assert.match(
  cssSource,
  /\.heatmap-explorer__stage\s*\{[\s\S]*?min-height:\s*360px;/,
  'desktop placeholder stage should remain 360px before authoritative sizing'
);
assert.match(cssSource, /\.heatmap-explorer__stage\[data-heatmap-sized="1"\]/, 'sized stages should have an explicit aspect-driven CSS contract');
assert.match(
  cssSource,
  /\.heatmap-explorer__stage\[data-heatmap-sized="1"\]\s*\{[\s\S]*?min-height:\s*0;/,
  'sized stages should intentionally drop placeholder min-height once authoritative aspect sizing is known'
);
assert.match(
  cssSource,
  /@media \(max-width: 540px\)\s*\{[\s\S]*?\.heatmap-explorer__header,[\s\S]*?\.heatmap-explorer__period-controls\s*\{[\s\S]*?flex-direction:\s*column;/,
  'phone layout reflow should remain scoped to narrow viewports only'
);
assert.match(
  cssSource,
  /@media \(max-width: 540px\)\s*\{[\s\S]*?\.heatmap-explorer__stage:not\(\[data-heatmap-sized="1"\]\)\s*\{[\s\S]*?min-height:\s*320px;/,
  'mobile placeholder stage should use 320px only while the stage is still unsized'
);
assert.match(
  cssSource,
  /@media \(max-width: 540px\), \(hover: none\) and \(pointer: coarse\)\s*\{/,
  'Explorer mobile rules should activate on narrow viewports and coarse-pointer touch layouts'
);
assert.match(
  cssSource,
  /@media \(max-width: 540px\), \(hover: none\) and \(pointer: coarse\)\s*\{[\s\S]*?\.heatmap-explorer select,[\s\S]*?\.heatmap-explorer button,[\s\S]*?\.heatmap-explorer a,[\s\S]*?\.heatmap-explorer__map-label,[\s\S]*?\.heatmap-explorer__floors label,[\s\S]*?\.heatmap-explorer__input\s*\{[\s\S]*?min-height:\s*44px;/,
  'mobile hit-area rules should cover select, button, links, map labels, floor labels, and explorer inputs'
);
assert.doesNotMatch(
  cssSource,
  /@media \(max-width: 540px\), \(hover: none\) and \(pointer: coarse\)\s*\{[\s\S]*?\.heatmap-explorer__header,[\s\S]*?\.heatmap-explorer__period-controls\s*\{[\s\S]*?flex-direction:\s*column;/,
  'wide coarse tablets must not inherit narrow phone layout reflow from the hit-target media block'
);
assert.doesNotMatch(
  cssSource,
  /@media \(max-width: 540px\), \(hover: none\) and \(pointer: coarse\)\s*\{[\s\S]*?\.heatmap-explorer__stage\s*\{[\s\S]*?min-height:\s*320px;/,
  'mobile 320px placeholder must not reapply to sized stages and reintroduce aspect drift'
);
assert.doesNotMatch(
  cssSource,
  /@media \(max-width: 540px\), \(hover: none\) and \(pointer: coarse\)\s*\{[\s\S]*?\.heatmap-explorer__stage:not\(\[data-heatmap-sized="1"\]\)\s*\{[\s\S]*?min-height:\s*320px;/,
  'wide coarse tablets must not inherit the narrow placeholder stage height from the hit-target media block'
);
assert.doesNotMatch(cssSource, /min-height:\s*620px/, 'desktop stages should no longer be pinned to 620px after sizing');
assert.match(cssSource, /min-height:\s*44px/, 'mobile 44px tap-target rules should remain intact');
assert.doesNotMatch(
  cssSource,
  /@media \(max-width: 540px\), \(hover: none\) and \(pointer: coarse\)\s*\{[\s\S]*?input\[type=(?:'|")radio(?:'|")\][\s\S]*?min-height:\s*44px;/,
  'mobile floor radio hit-area auditing should enlarge the label target without forcing the radio glyph itself to 44px'
);
const touchTargetBlock = cssAtRuleBlock(cssSource, '@media (max-width: 540px), (hover: none) and (pointer: coarse)');
const narrowPhoneBlock = cssAtRuleBlock(cssSource, '@media (max-width: 540px)');
assert.match(
  touchTargetBlock.body,
  /\.heatmap-explorer \[data-heatmap-zoom="in"\],[\s\S]*?\.heatmap-explorer \[data-heatmap-zoom="out"\][\s\S]*?min-width:\s*44px;/,
  'touch-target media should give zoom controls a 44px minimum width'
);
assert.doesNotMatch(
  narrowPhoneBlock.body,
  /\[data-heatmap-zoom="in"\][\s\S]*?min-width:\s*44px;/,
  'narrow-phone layout block should not set zoom min-width directly'
);
assert.doesNotMatch(
  cssSource.replace(touchTargetBlock.full, ''),
  /\[data-heatmap-zoom="in"\][\s\S]*?min-width:\s*44px;| \[data-heatmap-zoom="out"\][\s\S]*?min-width:\s*44px;/,
  'zoom target min-width should stay scoped to the touch-target media block, not global CSS'
);

function workspaceElement(attributes = {}) {
  const listeners = Object.create(null);
  const classes = new Set();
  let clientWidth = 320;
  let clientHeight = 240;
  const node = {
    attributes: Object.assign({}, attributes),
    style: {},
    hidden: false,
    textContent: '',
    value: '',
    children: [],
    disabled: false,
    checked: false,
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, force) {
        if (force === undefined) {
          if (classes.has(name)) {
            classes.delete(name);
            return false;
          }
          classes.add(name);
          return true;
        }
        if (force) {
          classes.add(name);
          return true;
        }
        classes.delete(name);
        return false;
      },
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name]; },
    addEventListener(type, handler) { (listeners[type] || (listeners[type] = [])).push(handler); },
    removeEventListener(type, handler) {
      if (listeners[type]) listeners[type] = listeners[type].filter(candidate => candidate !== handler);
    },
    appendChild(child) {
      this.children.push(child);
      if (child && typeof child.textContent === 'string' && child.nodeType === 3) {
        this.textContent += child.textContent;
      }
      return child;
    },
    removeChild(child) {
      const index = this.children.indexOf(child);
      if (index >= 0) {
        this.children.splice(index, 1);
      }
      if (child && typeof child.textContent === 'string' && child.nodeType === 3) {
        this.textContent = this.children
          .filter(candidate => candidate && candidate.nodeType === 3 && typeof candidate.textContent === 'string')
          .map(candidate => candidate.textContent)
          .join('');
      }
      return child;
    },
  };
  Object.defineProperty(node, 'clientWidth', {
    enumerable: true,
    get() { return clientWidth; },
    set(value) { clientWidth = value; },
  });
  Object.defineProperty(node, 'clientHeight', {
    enumerable: true,
    get() {
      const aspect = parseAspectRatioValue(node.style && node.style.aspectRatio);
      if (aspect && node.attributes['data-heatmap-sized'] === '1') {
        return Math.round(clientWidth * aspect.height / aspect.width);
      }
      return clientHeight;
    },
    set(value) { clientHeight = value; },
  });
  Object.defineProperty(node, 'firstChild', {
    enumerable: true,
    get() {
      return node.children.length > 0 ? node.children[0] : null;
    },
  });
  return node;
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
  allFloors: 'All floors',
  empty: 'Empty', pinned: 'Pinned', unpinned: 'Unpinned', noCell: 'No cell',
  inspect: 'Inspect', inspectSample: 'Returned events', topWeapons: 'Top weapons',
  participants: 'Participants', killers: 'killers', victims: 'victims', truncated: 'truncated',
  headshot: 'headshot', teamkill: 'teamkill', kills: 'Kills', deaths: 'Deaths', pan: 'Pan', navigation: 'Navigation',
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
WorkspaceRenderer.prototype.consumeSuppressedClick = function () { return false; };
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
const noFetchRoot = mountedWorkspaceRoot({
  'data-heatmap-game': 'cstrike', 'data-heatmap-map': 'de_dust2',
  'data-heatmap-player': '0', 'data-heatmap-endpoint': 'heatmap_points.php',
}, noFetchNodes);
const noFetchWorkspace = new HeatmapExplorerWorkspace(
  noFetchRoot,
  {messages: workspaceMessages}
);
noFetchWorkspace.mount();
assert.strictEqual(noFetchNodes['[data-heatmap-status]'].textContent, 'Fallback', 'no-fetch environments should immediately expose the usable static fallback');
assert.strictEqual(noFetchNodes['[data-heatmap-interactive]'].style.display, 'none');
assert.strictEqual(noFetchRoot.attributes['data-heatmap-state'], 'static_fallback', 'no-fetch mounts should publish static fallback state so map-style controls are hidden with the JPEG');

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

function explorerMessageAttributes() {
  return {
    'data-heatmap-message-insufficient-sample': 'Need at least three personal events',
    'data-heatmap-message-missing-coordinates': 'Coordinates are missing for this view',
    'data-heatmap-message-floors-unavailable': 'Selected floor is unavailable for this view',
    'data-heatmap-message-weak-projection': 'Projection is too weak for Explorer rendering',
    'data-heatmap-message-too-many-events': 'Too many events matched this view',
    'data-heatmap-message-range-custom': 'Custom UTC window',
    'data-heatmap-message-open-v1': 'Open legacy view',
    'data-heatmap-message-unavailable': 'Unavailable',
  };
}

function workspaceDocument() {
  const document = {
    activeElement: null,
    createElement(tagName) {
      const node = workspaceEventElement();
      node.tagName = String(tagName).toUpperCase();
      node.focusCalls = 0;
      node.focus = function () {
        node.focusCalls += 1;
        document.activeElement = node;
      };
      return node;
    },
    createTextNode(text) {
      return {nodeType: 3, textContent: String(text)};
    },
  };
  return document;
}

function richWorkspaceHarness(search = '?page=4', rootAttributes = {}) {
  const nodes = {
    interactive: workspaceEventElement(),
    stage: workspaceEventElement(),
    camera: workspaceEventElement(),
    image: workspaceEventElement({src: './client.jpg', alt: 'client map'}),
    canvas: workspaceEventElement(),
    static: workspaceEventElement(),
    staticLink: workspaceEventElement({href: './client-kill.jpg'}),
    staticImage: workspaceEventElement({src: './client-kill.jpg', alt: 'client map'}),
    status: workspaceEventElement(),
    alert: workspaceEventElement(),
    summary: workspaceEventElement(),
    period: workspaceEventElement(),
    window: workspaceEventElement(),
    sample: workspaceEventElement(),
    coverage: workspaceEventElement(),
    freshness: workspaceEventElement(),
    inspectOutput: workspaceEventElement(),
    floors: workspaceEventElement(),
    floorOptions: workspaceEventElement(),
    inspector: workspaceEventElement(),
    mapTitle: workspaceEventElement(),
    mapSelect: workspaceEventElement(),
    range: workspaceEventElement(),
    from: workspaceEventElement(),
    to: workspaceEventElement(),
    apply: workspaceEventElement(),
    zoomIn: workspaceEventElement(),
    zoomOut: workspaceEventElement(),
    reset: workspaceEventElement(),
    pan: workspaceEventElement(),
    share: workspaceEventElement(),
    mapStyleColor: workspaceEventElement({'data-heatmap-map-style-option': 'color', 'aria-pressed': 'true'}),
    mapStyleMono: workspaceEventElement({'data-heatmap-map-style-option': 'mono', 'aria-pressed': 'false'}),
    mapStyleInvalid: workspaceEventElement({'data-heatmap-map-style-option': 'invalid', 'aria-pressed': 'false'}),
  };
  nodes.range.value = '30d';
  nodes.mapSelect.value = 'de_dust2';
  nodes.canvas.getBoundingClientRect = () => ({left: 100, top: 50, width: 400, height: 300});
  nodes.static.appendChild(nodes.staticLink);
  nodes.staticLink.appendChild(nodes.staticImage);

  const selectors = {
    '[data-heatmap-interactive]': nodes.interactive,
    '[data-heatmap-stage]': nodes.stage,
    '[data-heatmap-camera]': nodes.camera,
    '[data-heatmap-image]': nodes.image,
    '[data-heatmap-canvas]': nodes.canvas,
    '[data-heatmap-static]': nodes.static,
    '[data-heatmap-static] a': nodes.staticLink,
    '[data-heatmap-static] img': nodes.staticImage,
    '[data-heatmap-status]': nodes.status,
    '[data-heatmap-alert]': nodes.alert,
    '[data-heatmap-summary]': nodes.summary,
    '[data-heatmap-period]': nodes.period,
    '[data-heatmap-window]': nodes.window,
    '[data-heatmap-sample]': nodes.sample,
    '[data-heatmap-coverage]': nodes.coverage,
    '[data-heatmap-freshness]': nodes.freshness,
    '[data-heatmap-inspect-output]': nodes.inspectOutput,
    '[data-heatmap-floor-sheet]': nodes.floors,
    '[data-heatmap-floor-options]': nodes.floorOptions,
    '[data-heatmap-inspector]': nodes.inspector,
    '[data-heatmap-map-title]': nodes.mapTitle,
    '[data-heatmap-map-select]': nodes.mapSelect,
    '[data-heatmap-range]': nodes.range,
    '[data-heatmap-from]': nodes.from,
    '[data-heatmap-to]': nodes.to,
    '[data-heatmap-apply]': nodes.apply,
    '[data-heatmap-zoom="in"]': nodes.zoomIn,
    '[data-heatmap-zoom="out"]': nodes.zoomOut,
    '[data-heatmap-reset]': nodes.reset,
    '[data-heatmap-pan]': nodes.pan,
    '[data-heatmap-share]': nodes.share,
  };

  const historyWrites = [];
  const root = workspaceEventElement(Object.assign({
    'data-heatmap-game': 'cstrike',
    'data-heatmap-map': 'de_dust2',
    'data-heatmap-player': '42',
    'data-heatmap-endpoint': 'heatmap_points.php',
    'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2',
    'data-heatmap-lang': 'en',
    'data-heatmap-allow-me': '1',
    'data-heatmap-allow-difference': '1',
  }, explorerMessageAttributes(), rootAttributes));
  root.querySelector = selector => selectors[selector] || null;
  root.querySelectorAll = selector => {
    if (selector === '[data-heatmap-floor]') {
      return nodes.floorOptions.children
        .flatMap(child => Array.isArray(child.children) ? child.children : [])
        .filter(child => child && typeof child.getAttribute === 'function'
          && child.getAttribute('data-heatmap-floor'));
    }
    if (selector === '[data-heatmap-map-style-option]') {
      return [nodes.mapStyleColor, nodes.mapStyleMono, nodes.mapStyleInvalid];
    }
    return [];
  };
  return {
    root,
    nodes,
    document: workspaceDocument(),
    historyWrites,
    window: {
      location: {search, pathname: '/hlstats.php'},
      history: {replaceState(_state, _title, href) { historyWrites.push(href); }},
    },
  };
}

function workspaceNodeBag(nodes) {
  return {
    interactive: nodes.interactive,
    stage: nodes.stage,
    camera: nodes.camera,
    image: nodes.image,
    canvas: nodes.canvas,
    static: nodes.static,
    staticLink: nodes.staticLink,
    staticImage: nodes.staticImage,
    jpegLink: nodes.share,
    status: nodes.status,
    alert: nodes.alert,
    summary: nodes.summary,
    period: nodes.period,
    window: nodes.window,
    sample: nodes.sample,
    coverage: nodes.coverage,
    freshness: nodes.freshness,
    inspectOutput: nodes.inspectOutput,
    floors: nodes.floors,
    floorOptions: nodes.floorOptions,
    inspector: nodes.inspector,
    mapTitle: nodes.mapTitle,
    mapSelect: nodes.mapSelect,
    range: nodes.range,
    from: nodes.from,
    to: nodes.to,
    apply: nodes.apply,
    zoomIn: nodes.zoomIn,
    zoomOut: nodes.zoomOut,
    reset: nodes.reset,
    pan: nodes.pan,
    share: nodes.share,
  };
}

function mountedWorkspace(search = '?page=4', fetchImpl = null, options = {}) {
  const harness = richWorkspaceHarness(search, options.rootAttributes);
  const workspace = new HeatmapExplorerWorkspace(harness.root, Object.assign({
    window: harness.window,
    fetch: fetchImpl,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  }, options.workspaceOptions || {}));
  workspace.document = harness.document;
  workspace._nodes = workspaceNodeBag(harness.nodes);
  workspace._mounted = true;
  return {harness, workspace};
}

function assertWorkspaceUsesCanonicalCoverageRatios() {
  const {harness, workspace} = mountedWorkspace();
  const payload = explorerSceneFixture();
  payload.coverage = Object.assign({}, payload.coverage, {
    candidate: 16,
    validXY: 8,
    validZ: 5,
    assigned: 5,
    unassigned: 3,
    xyCoverage: 0.5,
    zCoverage: 0.625,
    projected: 8,
    inBounds: 6,
    outOfBounds: 2,
    projectionCoverage: 0.75,
  });
  const scene = new HeatmapExplorerScene(payload);

  workspace._updateSceneText(scene);
  workspace._setCoverageStatus(scene);

  assert.match(harness.nodes.summary.textContent, /XY: 50%/, 'summary should use the canonical XY coverage ratio');
  assert.match(
    harness.nodes.coverage.textContent,
    /Coverage: XY 50%; Z 63%; Projection 75%/,
    'footer should use the canonical server coverage ratios when one source row yields multiple candidates'
  );
  assert.strictEqual(
    harness.nodes.status.textContent,
    'Loaded: Coverage 50%',
    'loaded status should use the canonical XY coverage ratio'
  );
}

assertWorkspaceUsesCanonicalCoverageRatios();

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

function httpJsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json() { return Promise.resolve(payload); },
  };
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

function sceneWithState(state, overrides = {}) {
  return explorerSceneFixture(Object.assign({
    state,
    query: {
      game: 'cstrike',
      map: 'de_dust2',
      player: 42,
      from: 1785456000,
      to: 1788048000,
      event: 'both',
      lens: 'overview',
      floor: 'all',
      lang: 'en',
    },
    layers: {total: [], me: [], others: []},
    comparison: {
      fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
      bins: [],
      personalSample: 0,
      otherSample: 0,
    },
    coverage: {
      sourceRows: 0,
      candidate: 0,
      validXY: 0,
      validZ: 0,
      zHistogram: [],
      missingCoordinates: 0,
      malformedCoordinates: 0,
      assigned: 0,
      unassigned: 0,
      xyCoverage: 0,
      zCoverage: 0,
      projected: 0,
      inBounds: 0,
      outOfBounds: 0,
      projectionCoverage: 0,
    },
    summary: {
      rowsRead: 0,
      sourceRows: 0,
      personalSample: 0,
      otherSample: 0,
    },
  }, overrides));
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
    aggregates: {
      scope: 'returned_rows',
      sampleRows: 1,
      topWeapons: [{weapon: 'ak47', count: 1}],
      participantCounts: {unique: 2, killers: 1, victims: 1},
    },
    truncated: false,
    warnings: [],
  };
}

function overviewSceneForWindow(from, to, overrides = {}) {
  return explorerSceneFixture(Object.assign({
    query: {
      game: 'cstrike',
      map: 'de_dust2',
      player: 42,
      from,
      to,
      event: 'both',
      lens: 'overview',
      floor: 'all',
      lang: 'en',
    },
    layers: {
      total: [['c0.0', 0, 0, 5, 1]],
      me: [['c0.0', 0, 0, 3, 1]],
      others: [['c0.0', 0, 0, 2, 0]],
    },
    comparison: {
      fields: ['cell', 'x', 'y', 'killDelta', 'deathDelta', 'sample'],
      bins: [],
      personalSample: 0,
      otherSample: 0,
    },
  }, overrides));
}

function floorSceneForFocus(activeFloor, upperAvailable) {
  const overrides = {
    query: {
      game: 'cstrike',
      map: 'de_dust2',
      player: 42,
      from: 1785456000,
      to: 1788048000,
      event: 'kills',
      lens: 'difference',
      floor: activeFloor,
      lang: 'en',
    },
    floors: [{
      id: 'upper',
      label: 'Upper',
      count: upperAvailable ? 4 : 0,
      available: upperAvailable,
    }],
    activeFloor,
  };
  return upperAvailable
    ? explorerSceneFixture(overrides)
    : sceneWithState('floors_unavailable', overrides);
}

function renderedFloorControl(harness, id) {
  return harness.root.querySelectorAll('[data-heatmap-floor]').find(control =>
    control.getAttribute('data-heatmap-floor') === id
  );
}

function floorFocusWorkspace() {
  const transport = deferredTransport();
  const harness = richWorkspaceHarness();
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  return {transport, harness, workspace};
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
  assert.match(deepLink.nodes.inspectOutput.textContent, /Top weapons: ak47 × 1/, 'inspect should render top weapons from the bounded server sample');
  assert.match(deepLink.nodes.inspectOutput.textContent, /Participants: 2 \(killers 1, victims 1\)/, 'inspect should render unique participant counts');
  assert.match(deepLink.nodes.inspectOutput.textContent, /Returned events: 1/, 'inspect should label the aggregate sample size');

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

async function assertClearedInspectCannotRetry() {
  const retry = workspaceHarness();
  const retryTransport = deferredTransport();
  const retryWorkspace = new HeatmapExplorerWorkspace(retry.root, {
    window: retry.window,
    fetch: retryTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  retryWorkspace.mount();
  await settleWorkspace();
  retryTransport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();
  retryWorkspace.pin('c2.0');
  await settleWorkspace();
  retryTransport.requests[1].reject(new Error('inspect failed'));
  await settleWorkspace();
  const retainedScene = retryWorkspace._scene;
  retryWorkspace.clearPin();
  const requestCount = retryTransport.requests.length;
  let retryResult = null;
  retryWorkspace.retry().then(result => { retryResult = result; });
  await settleWorkspace();
  assert.strictEqual(retryTransport.requests.length, requestCount, 'retry after clearPin must not start a stale inspect fetch');
  assert.strictEqual(retryWorkspace._scene, retainedScene, 'retry after clearPin must retain the current scene');
  assert.strictEqual(retryWorkspace.state.cell, null, 'retry after clearPin must keep the cell unpinned');
  assert.notStrictEqual(retry.nodes.status.textContent, 'Loading', 'retry after clearPin must not leave the status loading');
  assert.strictEqual(retryResult, false, 'retry after clearPin must resolve without requesting inspect');
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

async function assertStaleMapImageRecoversOnceThenFallsBack() {
  const harness = richWorkspaceHarness();
  const transport = deferredTransport();
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  workspace.mount();
  await settleWorkspace();
  const sceneA = sceneForMap('de_dust2');
  sceneA.map.image.url = 'heatmap_map.php?game=cstrike&map=de_dust2&v=' + 'a'.repeat(64);
  transport.requests[0].resolve(jsonResponse(sceneA));
  await settleWorkspace();

  harness.nodes.image.dispatch('error');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 2, 'a stale base-map response should trigger one fresh scene request');
  const sceneB = sceneForMap('de_dust2');
  sceneB.map.image.url = 'heatmap_map.php?game=cstrike&map=de_dust2&v=' + 'b'.repeat(64);
  transport.requests[1].resolve(jsonResponse(sceneB));
  await settleWorkspace();
  assert.strictEqual(harness.nodes.image.attributes.src, sceneB.map.image.url, 'the bounded recovery should install the replacement content URL');

  harness.nodes.image.dispatch('error');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 2, 'a second base-map error before load must not loop scene requests');
  assert.strictEqual(harness.root.attributes['data-heatmap-state'], 'static_fallback', 'failed replacement loading should expose the static JPEG fallback');
  assert.strictEqual(harness.nodes.alert.hidden, false, 'failed replacement loading should keep recovery actions visible');
  assert.ok(harness.nodes.alert.children.length > 0, 'failed replacement loading should expose retry and legacy actions');
}

async function assertSupersededMapRecoveryCannotHideNewestScene() {
  const harness = richWorkspaceHarness();
  const transport = deferredTransport();
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  workspace.mount();
  await settleWorkspace();
  transport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();

  harness.nodes.image.dispatch('error');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 2, 'image recovery should start one scene refresh');
  const staleRecovery = transport.requests[1];
  workspace._setState({map: 'de_nuke', floor: 'all', cell: null}, 'map');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 3, 'a user map choice should supersede the pending recovery');
  transport.requests[2].resolve(jsonResponse(sceneForMap('de_nuke')));
  await settleWorkspace();
  staleRecovery.resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();

  assert.strictEqual(workspace.state.map, 'de_nuke', 'the newest user-selected scene should remain authoritative');
  assert.strictEqual(harness.nodes.image.attributes.src, './de_nuke.jpg', 'a stale recovery must not replace the newest image');
  assert.notStrictEqual(harness.root.attributes['data-heatmap-state'], 'static_fallback', 'a stale recovery failure must not hide a valid newer Explorer');
  assert.notStrictEqual(harness.nodes.interactive.style.display, 'none', 'the valid newer interactive view should remain visible');
}

async function assertMapStyleStaysInstanceLocalAndDoesNotReload() {
  const transport = deferredTransport();
  const harness = richWorkspaceHarness();
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  workspace.mount();
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 1, 'mount should load one initial scene before style changes are exercised');
  transport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();

  const colorButton = harness.nodes.mapStyleColor;
  const monoButton = harness.nodes.mapStyleMono;
  const invalidButton = harness.nodes.mapStyleInvalid;
  const requestsBeforeStyleChange = transport.requests.length;
  const historyWritesBeforeStyleChange = harness.historyWrites.length;
  const searchBeforeStyleChange = harness.window.location.search;
  const stateBeforeStyleChange = plain(workspace.state);
  workspace._setState = function () {
    throw new Error('map style controls must not mutate workspace state');
  };
  workspace._loadScene = function () {
    throw new Error('map style controls must not reload the scene');
  };
  workspace._writeUrl = function () {
    throw new Error('map style controls must not write the URL');
  };
  workspace._renderer = new Proxy({}, {
    get() {
      throw new Error('map style controls must not invoke renderer methods');
    },
  });

  monoButton.dispatch('click', {currentTarget: monoButton});
  assert.strictEqual(harness.root.getAttribute('data-heatmap-map-style'), 'mono');
  assert.strictEqual(monoButton.getAttribute('aria-pressed'), 'true');
  assert.strictEqual(colorButton.getAttribute('aria-pressed'), 'false');
  assert.strictEqual(monoButton.classList.contains('is-selected'), true);
  assert.strictEqual(colorButton.classList.contains('is-selected'), false);
  assert.strictEqual(transport.requests.length, requestsBeforeStyleChange);
  assert.strictEqual(harness.historyWrites.length, historyWritesBeforeStyleChange);
  assert.strictEqual(harness.window.location.search, searchBeforeStyleChange);
  assert.deepStrictEqual(plain(workspace.state), stateBeforeStyleChange);

  colorButton.dispatch('click', {currentTarget: colorButton});
  assert.strictEqual(harness.root.getAttribute('data-heatmap-map-style'), 'color');
  assert.strictEqual(colorButton.getAttribute('aria-pressed'), 'true');
  assert.strictEqual(monoButton.getAttribute('aria-pressed'), 'false');
  assert.strictEqual(colorButton.classList.contains('is-selected'), true);
  assert.strictEqual(monoButton.classList.contains('is-selected'), false);

  invalidButton.dispatch('click', {currentTarget: invalidButton});
  assert.strictEqual(harness.root.getAttribute('data-heatmap-map-style'), 'color');
  assert.strictEqual(invalidButton.getAttribute('aria-pressed'), 'false');
  assert.strictEqual(transport.requests.length, requestsBeforeStyleChange);
  assert.strictEqual(harness.historyWrites.length, historyWritesBeforeStyleChange);
  assert.strictEqual(harness.window.location.search, searchBeforeStyleChange);
  assert.deepStrictEqual(plain(workspace.state), stateBeforeStyleChange);

  const nextTransport = deferredTransport();
  const nextHarness = richWorkspaceHarness();
  const nextWorkspace = new HeatmapExplorerWorkspace(nextHarness.root, {
    window: nextHarness.window,
    document: nextHarness.document,
    fetch: nextTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  nextWorkspace.mount();
  await settleWorkspace();
  assert.strictEqual(nextHarness.root.getAttribute('data-heatmap-map-style'), 'color');
  assert.strictEqual(nextHarness.nodes.mapStyleColor.getAttribute('aria-pressed'), 'true');
  assert.strictEqual(nextHarness.nodes.mapStyleMono.getAttribute('aria-pressed'), 'false');
}

function assertMapStyleCssStaysScoped() {
  assert.match(
    cssSource,
    /\.heatmap-explorer \[data-heatmap-image\]\s*\{[\s\S]*?position:\s*relative;[\s\S]*?z-index:\s*0;[\s\S]*?transition:\s*filter 120ms ease;[\s\S]*?\}/,
    'the decorative grade should start on the map image below the canvas'
  );
  assert.match(
    cssSource,
    /\.heatmap-explorer \[data-heatmap-camera\]::after\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?z-index:\s*1;[\s\S]*?pointer-events:\s*none;[\s\S]*?mix-blend-mode:\s*soft-light;[\s\S]*?\}/,
    'the camera pseudo-element should add a non-interactive decorative grade below the canvas'
  );
  assert.match(
    cssSource,
    /\.heatmap-explorer \[data-heatmap-canvas\]\s*\{[\s\S]*?z-index:\s*2;[\s\S]*?\}/,
    'the semantic WebGL canvas should remain above the decorative grade'
  );
  assert.match(
    cssSource,
    /\.heatmap-explorer\[data-heatmap-map-style="color"\] \[data-heatmap-image\]\s*\{[\s\S]*?filter:\s*sepia\(0\.22\) saturate\(1\.14\) hue-rotate\(346deg\) contrast\(1\.03\) brightness\(0\.94\);[\s\S]*?\}/,
    'color mode should grade only the dynamic map image'
  );
  assert.match(
    cssSource,
    /\.heatmap-explorer\[data-heatmap-map-style="mono"\] \[data-heatmap-image\]\s*\{[\s\S]*?filter:\s*grayscale\(1\) contrast\(1\.05\) brightness\(0\.94\);[\s\S]*?\}/,
    'mono mode should grade only the dynamic map image'
  );
  assert.match(
    cssSource,
    /\.heatmap-explorer\[data-heatmap-state="static_fallback"\] \[data-heatmap-map-style-controls\],[\s\S]*?\.heatmap-explorer\[data-heatmap-state="context_lost"\] \[data-heatmap-map-style-controls\]\s*\{\s*display:\s*none;/,
    'style controls should hide when the explorer is unavailable'
  );
  assert.match(
    cssSource,
    /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\.heatmap-explorer \[data-heatmap-image\] \{\s*transition:\s*none;\s*\}/,
    'reduced motion should disable the map-image filter transition'
  );
  assert.doesNotMatch(
    cssSource,
    /(?:\.heatmap-explorer \[data-heatmap-canvas\]|(?:\.heatmap-explorer\s+)?\.heatmap-explorer__static img|\.heatmap-explorer \[data-heatmap-static\](?: img)?)\s*\{[^}]*\b(?:filter|mix-blend-mode)\s*:/,
    'the canvas and static JPEG fallback must not receive filter or blend-mode styling'
  );
}

async function assertFailureActionsUseKnownV1Route() {
  const transport = deferredTransport();
  const harness = richWorkspaceHarness('?page=4&hm_event=deaths', {
    'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
  });
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  workspace.mount();
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 1, 'the initial scene should load before a later failure is exercised');
  transport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();
  workspace._setState({map: 'de_nuke', event: 'deaths', floor: 'all', cell: null}, 'map');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 2, 'changing the current map and event after a successful scene should start a new request');
  transport.requests[1].reject(new Error('later scene failed'));
  await settleWorkspace();
  assert.strictEqual(harness.nodes.alert.children.length, 1, 'failure actions should render one grouped action row');
  assert.strictEqual(harness.nodes.alert.children[0].children.length, 2, 'failure actions should append retry plus the known v1 route');
  assert.strictEqual(harness.nodes.alert.children[0].children[0].textContent, 'Retry');
  assert.strictEqual(harness.nodes.alert.children[0].children[1].tagName, 'A');
  assert.strictEqual(
    harness.nodes.alert.children[0].children[1].attributes.href,
    'heatmap_points.php?game=cstrike&map=de_nuke&player=42&event=deaths'
  );
  assert.notStrictEqual(
    harness.nodes.alert.children[0].children[1].attributes.href,
    workspace._scene.fallback.v1,
    'later failures must not fall back to the loaded scene generic route'
  );
  assert.strictEqual(harness.nodes.alert.children[0].children[1].textContent, 'Open legacy view');
}

function assertWorkspaceStageAspectUsesAuthoritativeSceneDimensions() {
  const aspectGl = fakeGl();
  const harness = richWorkspaceHarness('?page=4');
  harness.nodes.stage.clientWidth = 609;
  harness.nodes.stage.clientHeight = 620;
  harness.nodes.canvas.getContext = () => aspectGl;
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    messages: workspaceMessages,
  });
  workspace._nodes = workspaceNodeBag(harness.nodes);
  const aspectScene = new HeatmapExplorerScene(explorerSceneFixture({
    map: {
      game: 'cstrike',
      realgame: 'cstrike',
      name: 'de_dust2',
      image: {url: './map.jpg', width: 1280, height: 1024},
      projectionHash: 'a4dd45e46d84a12f',
      floorConfigHash: '97d170e1550eee4a',
    },
  }));
  workspace._applyScene(aspectScene, 'map');
  assert.strictEqual(harness.nodes.stage.attributes['data-heatmap-sized'], '1', 'stage sizing should be marked explicitly after a scene is applied');
  assert.strictEqual(harness.nodes.stage.style.aspectRatio, '1280 / 1024', 'stage sizing should follow authoritative scene dimensions');
  assert.ok(Math.abs(workspace._camera.viewportWidth - 609) <= 0.01, 'camera viewport width should follow the measured stage width');
  assert.ok(Math.abs(workspace._camera.viewportHeight - 487) <= 1, 'camera viewport height should follow the authoritative aspect ratio, not the old 620px placeholder');
  assert.deepStrictEqual(aspectGl.calls.viewports.at(-1), [0, 0, 609, 487], 'renderer viewport should use the sized stage height after aspect sync');
  assert.strictEqual(harness.nodes.canvas.style.width, '609px', 'canvas CSS width should follow the measured stage width');
  assert.strictEqual(harness.nodes.canvas.style.height, '487px', 'canvas CSS height should follow the authoritative aspect ratio');
  assert.match(harness.nodes.camera.style.transform, /^translate3d\(/, 'camera transform should be reapplied after viewport sync');
  workspace.destroy();
}

async function assertInitialFailureUsesServerV1RouteWhenSceneIsMissing() {
  for (const scenario of [
    {
      label: 'deaths deep-link should override the trusted base event',
      search: '?page=4&hm_event=deaths',
      v1Url: 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
      expectedHref: 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=deaths',
    },
    {
      label: 'both deep-link should override the trusted base event',
      search: '?page=4&hm_event=both',
      v1Url: 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
      expectedHref: 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=both',
    },
    {
      label: 'map legacy page should retain only its human map route fields',
      search: '?page=4&hm_event=deaths',
      v1Url: 'hlstats.php?mode=mapinfo&game=cstrike&map=de_dust2&heatmap_legacy=1&ignored=1',
      expectedHref: 'hlstats.php?mode=mapinfo&game=cstrike&map=de_dust2&heatmap_legacy=1',
    },
    {
      label: 'player legacy page should retain only its human player route fields',
      search: '?page=4&hm_event=deaths',
      v1Url: 'hlstats.php?mode=playerinfo&player=42&heatmap_legacy=1&ignored=1',
      expectedHref: 'hlstats.php?mode=playerinfo&player=42&heatmap_legacy=1',
    },
  ]) {
    const transport = deferredTransport();
    const harness = richWorkspaceHarness(scenario.search, {
      'data-heatmap-v1-url': scenario.v1Url,
    });
    const workspace = new HeatmapExplorerWorkspace(harness.root, {
      window: harness.window,
      document: harness.document,
      fetch: transport.fetch,
      messages: workspaceMessages,
      Renderer: WorkspaceRenderer,
    });

    workspace.mount();
    await settleWorkspace();
    assert.strictEqual(transport.requests.length, 1, scenario.label + ': initial mount should begin with one scene request');
    assert.strictEqual(workspace._scene, null, scenario.label + ': the initial failing request must happen before a scene is available');

    transport.requests[0].resolve({ok: false, json() { throw new Error('not used'); }});
    await settleWorkspace();
    assert.strictEqual(harness.nodes.alert.hidden, false, scenario.label + ': initial request failures should remain visible');
    assert.strictEqual(harness.nodes.alert.children.length, 1, scenario.label + ': initial request failures should still expose failure actions');
    assert.strictEqual(harness.nodes.alert.children[0].children[1].attributes.href, scenario.expectedHref);
    assert.notStrictEqual(harness.nodes.alert.children[0].children[1].attributes.href, harness.nodes.staticLink.attributes.href);
  }
}

async function assertFloorFocusPersistsThroughEnabledReload() {
  const {transport, harness, workspace} = floorFocusWorkspace();
  workspace.mount();
  await settleWorkspace();
  transport.requests[0].resolve(jsonResponse(floorSceneForFocus('all', true)));
  await settleWorkspace();

  const initialUpper = renderedFloorControl(harness, 'upper');
  const initialAll = renderedFloorControl(harness, 'all');
  assert.ok(initialAll && !initialAll.disabled, 'the all-floor control should remain available alongside upper');
  assert.ok(initialUpper, 'the initial available upper floor control should render');
  initialUpper.focus();
  initialUpper.checked = true;
  harness.nodes.floors.dispatch('change', {target: initialUpper});
  await settleWorkspace();

  assert.strictEqual(transport.requests.length, 2, 'keyboard-style floor selection should request a replacement scene');
  assert.match(transport.requests[1].url, /floor=upper/, 'the replacement scene request should retain the selected upper floor');
  transport.requests[1].resolve(jsonResponse(floorSceneForFocus('upper', true)));
  await settleWorkspace();

  const refreshedUpper = renderedFloorControl(harness, 'upper');
  assert.notStrictEqual(refreshedUpper, initialUpper, 'the refreshed scene should replace the old floor radio');
  assert.strictEqual(refreshedUpper.disabled, false, 'the matching available floor radio should stay enabled');
  assert.strictEqual(harness.document.activeElement, refreshedUpper, 'the refreshed matching enabled floor radio should retain keyboard focus');
}

async function assertFloorFocusDoesNotTargetUnavailableReload() {
  const {transport, harness, workspace} = floorFocusWorkspace();
  workspace.mount();
  await settleWorkspace();
  transport.requests[0].resolve(jsonResponse(floorSceneForFocus('all', true)));
  await settleWorkspace();

  const initialUpper = renderedFloorControl(harness, 'upper');
  initialUpper.focus();
  harness.nodes.floors.dispatch('change', {target: initialUpper});
  await settleWorkspace();
  transport.requests[1].resolve(jsonResponse(floorSceneForFocus('upper', false)));
  await settleWorkspace();

  const unavailableUpper = renderedFloorControl(harness, 'upper');
  assert.strictEqual(unavailableUpper.disabled, true, 'an unavailable upper floor should render as disabled');
  assert.strictEqual(unavailableUpper.focusCalls, 0, 'a replacement unavailable floor radio must not receive forced focus');
}

async function assertFloorFocusDoesNotStealMovedFocus() {
  const {transport, harness, workspace} = floorFocusWorkspace();
  workspace.mount();
  await settleWorkspace();
  transport.requests[0].resolve(jsonResponse(floorSceneForFocus('all', true)));
  await settleWorkspace();

  const initialUpper = renderedFloorControl(harness, 'upper');
  initialUpper.focus();
  harness.nodes.floors.dispatch('change', {target: initialUpper});
  await settleWorkspace();
  harness.document.activeElement = harness.nodes.mapSelect;
  transport.requests[1].resolve(jsonResponse(floorSceneForFocus('upper', true)));
  await settleWorkspace();

  const refreshedUpper = renderedFloorControl(harness, 'upper');
  assert.strictEqual(refreshedUpper.focusCalls, 0, 'a new floor radio must not reclaim focus after the user moved elsewhere');
  assert.strictEqual(harness.document.activeElement, harness.nodes.mapSelect, 'an async scene reload must preserve focus moved outside the floor controls');
}

async function assertScene422TooManyEventsUsesSpecializedStatePresentation() {
  const transport = deferredTransport();
  const harness = richWorkspaceHarness('?page=4&hm_event=both&hm_cell=c2.0', {
    'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
  });
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  const payload = sceneWithState('too_many_events', {
    query: {
      game: 'cstrike',
      map: 'de_nuke',
      player: 42,
      from: 1785456000,
      to: 1788048000,
      event: 'both',
      lens: 'overview',
      floor: 'all',
      lang: 'en',
    },
    map: {
      game: 'cstrike',
      realgame: 'cstrike',
      name: 'de_nuke',
      image: {url: './de_nuke.jpg', width: 64, height: 32},
      projectionHash: 'a4dd45e46d84a12f',
      floorConfigHash: '97d170e1550eee4a',
    },
    fallback: {
      v1: 'heatmap_points.php?game=cstrike&map=de_nuke',
      jpeg: './de_nuke-kill.jpg',
      thumbnail: './de_nuke-kill-thumb.jpg',
    },
    coverage: {
      sourceRows: 4000,
      candidate: 4000,
      validXY: 4000,
      validZ: 4000,
      zHistogram: [{z: 0, count: 4000}],
      missingCoordinates: 0,
      malformedCoordinates: 0,
      assigned: 4000,
      unassigned: 0,
      xyCoverage: 1,
      zCoverage: 1,
      projected: 4000,
      inBounds: 4000,
      outOfBounds: 0,
      projectionCoverage: 1,
    },
    summary: {rowsRead: 4000, sourceRows: 4000, personalSample: 0, otherSample: 0},
  });

  workspace.mount();
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 1, 'initial mount should request one scene before the 422 seam is exercised');
  assert.strictEqual(workspace.state.cell, 'c2.0', 'deep-link cell should be preserved before the blocked scene arrives');

  transport.requests[0].resolve(httpJsonResponse(422, payload));
  await settleWorkspace();

  assert.ok(workspace._scene, 'the accepted 422 seam should still install a validated scene');
  assert.strictEqual(workspace._scene.state, 'too_many_events', 'only the specialized too_many_events scene should pass the 422 seam');
  assert.strictEqual(workspace._scene.map.name, 'de_nuke', 'the accepted 422 scene should update authoritative map state');
  assert.strictEqual(transport.requests.length, 1, 'blocked 422 deep-link scenes must not start a second inspect request');
  assert.strictEqual(workspace.state.cell, 'c2.0', 'blocked 422 deep-link scenes should preserve the selected cell in state');
  assert.strictEqual(harness.nodes.image.attributes.src, './de_nuke.jpg', 'the accepted 422 scene should still render authoritative scene media');
  assert.strictEqual(harness.nodes.status.textContent, 'Too many events matched this view', 'accepted 422 scenes should publish the localized blocked-state status');
  assert.strictEqual(harness.nodes.alert.hidden, false, 'accepted 422 blocked states should remain visible');
  assert.strictEqual(harness.nodes.alert.textContent, 'Too many events matched this view', 'accepted 422 blocked states should keep the specialized localized alert');
  assert.notStrictEqual(harness.nodes.status.textContent, 'Loading', 'blocked 422 deep-link scenes must not remain stuck in loading');
  assert.notStrictEqual(harness.nodes.status.textContent, 'Failed', 'blocked 422 deep-link scenes must not collapse into generic failure');
  assert.match(harness.nodes.summary.textContent, /Period: 1785456000–1788048000 UTC/, 'accepted 422 blocked states should still refresh the textual summary');
  assert.match(harness.nodes.coverage.textContent, /Coverage: XY 100%; Z 100%; Projection 100%/, 'accepted 422 blocked states should still refresh the scene footer coverage');
  assert.strictEqual(harness.nodes.freshness.textContent, 'Freshness: Loaded', 'accepted 422 blocked states should still refresh the footer freshness state');
  assert.match(harness.nodes.share.attributes.href, /hm_cell=c2\.0/, 'blocked 422 deep-link scenes should preserve the pinned-cell URL state');
  assert.strictEqual(harness.nodes.inspectOutput.textContent, '', 'blocked 422 deep-link scenes should not render a provisional inspect summary');
  assert.strictEqual(harness.nodes.alert.children.length, 1, 'accepted 422 blocked states should expose one action group');
  assert.strictEqual(harness.nodes.alert.children[0].children.length, 1, 'accepted 422 blocked states should expose only the legacy action, not generic retry');
  assert.strictEqual(harness.nodes.alert.children[0].children[0].textContent, 'Open legacy view');
  assert.strictEqual(
    harness.nodes.alert.children[0].children[0].attributes.href,
    'heatmap_points.php?game=cstrike&map=de_nuke&player=42&event=both',
    'accepted 422 blocked states should preserve authoritative player/map/event scope in the legacy action'
  );
}

async function assertBlockedDeepLinkScenesDoNotAutoInspect() {
  const transport = deferredTransport();
  const harness = richWorkspaceHarness('?page=4&hm_event=both&hm_cell=c2.0', {
    'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
  });
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });
  const payload = sceneWithState('weak_projection', {
    query: {
      game: 'cstrike',
      map: 'de_nuke',
      player: 42,
      from: 1785456000,
      to: 1788048000,
      event: 'both',
      lens: 'overview',
      floor: 'all',
      lang: 'en',
    },
    map: {
      game: 'cstrike',
      realgame: 'cstrike',
      name: 'de_nuke',
      image: {url: './de_nuke.jpg', width: 64, height: 32},
      projectionHash: 'a4dd45e46d84a12f',
      floorConfigHash: '97d170e1550eee4a',
    },
    fallback: {
      v1: 'heatmap_points.php?game=cstrike&map=de_nuke',
      jpeg: './de_nuke-kill.jpg',
      thumbnail: './de_nuke-kill-thumb.jpg',
    },
    coverage: {
      sourceRows: 175,
      candidate: 350,
      validXY: 350,
      validZ: 350,
      zHistogram: [{z: -128, count: 4}, {z: 32, count: 152}, {z: 192, count: 1}],
      missingCoordinates: 0,
      malformedCoordinates: 0,
      assigned: 0,
      unassigned: 0,
      xyCoverage: 1,
      zCoverage: 1,
      projected: 350,
      inBounds: 30,
      outOfBounds: 320,
      projectionCoverage: 0.08571428571428572,
    },
    summary: {rowsRead: 175, sourceRows: 175, personalSample: 0, otherSample: 0},
  });

  workspace.mount();
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 1, 'blocked 200 deep-link scenes should begin with one scene request');

  transport.requests[0].resolve(jsonResponse(payload));
  await settleWorkspace();

  assert.ok(workspace._scene, 'blocked 200 deep-link scenes should still install the validated scene');
  assert.strictEqual(workspace._scene.state, 'weak_projection');
  assert.strictEqual(transport.requests.length, 1, 'blocked 200 deep-link scenes must not auto-start an inspect request');
  assert.strictEqual(workspace.state.cell, 'c2.0', 'blocked 200 deep-link scenes should preserve the selected cell in state');
  assert.strictEqual(harness.nodes.status.textContent, 'Projection is too weak for Explorer rendering', 'blocked 200 deep-link scenes should keep the specialized blocked status');
  assert.strictEqual(harness.nodes.alert.hidden, false, 'blocked 200 deep-link scenes should keep the blocked alert visible');
  assert.strictEqual(harness.nodes.alert.textContent, 'Projection is too weak for Explorer rendering', 'blocked 200 deep-link scenes should keep the specialized blocked alert');
  assert.notStrictEqual(harness.nodes.status.textContent, 'Loading', 'blocked 200 deep-link scenes must not remain stuck in loading');
  assert.notStrictEqual(harness.nodes.status.textContent, 'Failed', 'blocked 200 deep-link scenes must not collapse into generic failure');
  assert.match(harness.nodes.share.attributes.href, /hm_cell=c2\.0/, 'blocked 200 deep-link scenes should preserve the pinned-cell URL state');
  assert.strictEqual(harness.nodes.inspectOutput.textContent, '', 'blocked 200 deep-link scenes should not render a provisional inspect summary');
}

async function assertSceneNonOkFailuresStayFailClosedExceptTooManyEvents422() {
  const cases = [
    {
      name: 'malformed 422 payload',
      response: httpJsonResponse(422, {schemaVersion: 2, state: 'too_many_events'}),
    },
    {
      name: 'wrong-state 422 payload',
      response: httpJsonResponse(422, sceneWithState('weak_projection')),
    },
    {
      name: '403 payload with too_many_events scene data',
      response: httpJsonResponse(403, sceneWithState('too_many_events')),
    },
    {
      name: '500 response with too_many_events scene data',
      response: httpJsonResponse(500, sceneWithState('too_many_events')),
    },
    {
      name: '422 missing json handler',
      response: {ok: false, status: 422, text() { return Promise.resolve('<html>'); }},
    },
    {
      name: '422 json parse failure',
      response: {ok: false, status: 422, json() { return Promise.reject(new Error('invalid json')); }},
    },
  ];

  for (const testCase of cases) {
    const transport = deferredTransport();
    const harness = richWorkspaceHarness('?page=4&hm_event=both', {
      'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
    });
    const workspace = new HeatmapExplorerWorkspace(harness.root, {
      window: harness.window,
      document: harness.document,
      fetch: transport.fetch,
      messages: workspaceMessages,
      Renderer: WorkspaceRenderer,
    });

    workspace.mount();
    await settleWorkspace();
    assert.strictEqual(transport.requests.length, 1, testCase.name + ': mount should start exactly one scene request');

    transport.requests[0].resolve(testCase.response);
    await settleWorkspace();

    assert.strictEqual(workspace._scene, null, testCase.name + ': invalid non-ok payloads must not install a scene');
    assert.strictEqual(harness.nodes.status.textContent, 'Failed', testCase.name + ': invalid non-ok payloads must stay on generic failure status');
    assert.strictEqual(harness.nodes.alert.hidden, false, testCase.name + ': invalid non-ok payloads must keep the failure alert visible');
    assert.strictEqual(harness.nodes.alert.textContent, 'Failed', testCase.name + ': invalid non-ok payloads must not publish specialized state text');
    assert.strictEqual(harness.nodes.alert.children.length, 1, testCase.name + ': generic failures should expose one action group');
    assert.strictEqual(harness.nodes.alert.children[0].children.length, 2, testCase.name + ': generic failures should keep retry plus legacy actions');
    assert.strictEqual(harness.nodes.alert.children[0].children[0].textContent, 'Retry', testCase.name + ': generic failures must keep the retry action');
    assert.strictEqual(harness.nodes.alert.children[0].children[1].textContent, 'Open legacy view', testCase.name + ': generic failures must keep the legacy fallback action');
    assert.strictEqual(
      harness.nodes.alert.children[0].children[1].attributes.href,
      'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=both',
      testCase.name + ': generic failures before a scene exists must preserve the trusted legacy route rewrite'
    );
  }
}

async function assertFetchPathPublishesSpecializedStates() {
  const cases = [
    {
      name: 'empty fetch should stay a truthful complete state',
      payload: sceneWithState('empty'),
      expectStatus: 'Empty',
      expectAlertHidden: true,
      expectImage: './map.jpg',
    },
    {
      name: 'weak projection fetch should publish the explicit blocked state',
      payload: sceneWithState('weak_projection', {
        coverage: {
          sourceRows: 175,
          candidate: 350,
          validXY: 350,
          validZ: 350,
          zHistogram: [{z: -128, count: 4}, {z: 32, count: 152}, {z: 192, count: 1}],
          missingCoordinates: 0,
          malformedCoordinates: 0,
          assigned: 0,
          unassigned: 0,
          xyCoverage: 1,
          zCoverage: 1,
          projected: 350,
          inBounds: 30,
          outOfBounds: 320,
          projectionCoverage: 0.08571428571428572,
        },
        summary: {rowsRead: 175, sourceRows: 175, personalSample: 0, otherSample: 0},
      }),
      expectStatus: 'Projection is too weak for Explorer rendering',
      expectAlertHidden: false,
      expectAlertText: 'Projection is too weak for Explorer rendering',
    },
    {
      name: 'floors unavailable fetch should publish the explicit blocked floor state',
      payload: sceneWithState('floors_unavailable', {
        query: {
          game: 'cstrike',
          map: 'de_dust2',
          player: 42,
          from: 1785456000,
          to: 1788048000,
          event: 'both',
          lens: 'overview',
          floor: 'upper',
          lang: 'en',
        },
        activeFloor: 'upper',
        floors: [
          {id: 'lower', label: 'Lower', count: 0, available: false},
          {id: 'upper', label: 'Upper', count: 0, available: false},
        ],
        coverage: {
          sourceRows: 1,
          candidate: 1,
          validXY: 1,
          validZ: 0,
          zHistogram: [],
          missingCoordinates: 1,
          malformedCoordinates: 0,
          assigned: 0,
          unassigned: 0,
          xyCoverage: 1,
          zCoverage: 0,
          projected: 0,
          inBounds: 0,
          outOfBounds: 0,
          projectionCoverage: 0,
        },
        summary: {rowsRead: 1, sourceRows: 1, personalSample: 0, otherSample: 0},
      }),
      expectStatus: 'Selected floor is unavailable for this view',
      expectAlertHidden: false,
      expectAlertText: 'Selected floor is unavailable for this view',
    },
  ];

  for (const testCase of cases) {
    const transport = deferredTransport();
    const harness = richWorkspaceHarness('?page=4');
    const workspace = new HeatmapExplorerWorkspace(harness.root, {
      window: harness.window,
      document: harness.document,
      fetch: transport.fetch,
      messages: workspaceMessages,
      Renderer: WorkspaceRenderer,
    });
    workspace.mount();
    await settleWorkspace();
    assert.strictEqual(transport.requests.length, 1, testCase.name + ': mount should request one scene');
    transport.requests[0].resolve(jsonResponse(testCase.payload));
    await settleWorkspace();
    assert.strictEqual(harness.nodes.status.textContent, testCase.expectStatus, testCase.name);
    assert.strictEqual(harness.nodes.alert.hidden, testCase.expectAlertHidden, testCase.name + ': alert visibility should match the explicit state');
    if (Object.prototype.hasOwnProperty.call(testCase, 'expectAlertText')) {
      assert.strictEqual(harness.nodes.alert.textContent, testCase.expectAlertText, testCase.name + ': alert text should stay specialized');
    }
    if (Object.prototype.hasOwnProperty.call(testCase, 'expectImage')) {
      assert.strictEqual(harness.nodes.image.attributes.src, testCase.expectImage, testCase.name + ': complete states should keep the authoritative image');
    }
    assert.notStrictEqual(harness.nodes.status.textContent, 'Failed', testCase.name + ': explicit states must not collapse into generic failure');
  }
}

function assertUnavailableFloorsStayVisible() {
  const {workspace, harness} = mountedWorkspace();
  const floorScene = new HeatmapExplorerScene(blockedSceneFixture('floors_unavailable'));
  workspace.state.floor = 'upper';
  workspace._renderFloors(floorScene);
  const floorControls = harness.root.querySelectorAll('[data-heatmap-floor]');
  assert.strictEqual(floorControls.length, 3, 'all configured floors should remain in the control list');
  assert.strictEqual(floorControls[2].disabled, true, 'unavailable floors should remain visible but disabled');
  assert.strictEqual(floorControls[2].checked, true, 'the selected unavailable floor should remain explainable');
  assert.match(harness.nodes.floorOptions.children[2].textContent, /Upper/);
  assert.match(harness.nodes.floorOptions.children[2].textContent, /Unavailable/);
}

function assertAllFloorsAggregateLabelOmitsMisleadingZeroCount() {
  const {workspace, harness} = mountedWorkspace();
  workspace._renderFloors(validScene);
  assert.strictEqual(harness.nodes.floorOptions.children[0].textContent, 'All floors');
  assert.doesNotMatch(harness.nodes.floorOptions.children[0].textContent, /\(0\)/, 'aggregate floor label must not claim an empty count');
}

async function assertCustomWindowApplyValidation() {
  const transport = deferredTransport();
  assert.deepStrictEqual(
    plain(HeatmapExplorerUrlState.parse('?hm_from=900&hm_to=1300', {nowSeconds: 1000})),
    {from: 900, to: 1300},
    'custom windows up to now+300 should parse like the backend contract'
  );
  assertInvalidUrl(
    () => HeatmapExplorerUrlState.parse('?hm_from=900&hm_to=1301', {nowSeconds: 1000}),
    'custom windows above now+300 should fail during deep-link hydration'
  );

  const futureTransport = deferredTransport();
  const futureHarness = richWorkspaceHarness('?page=4&hm_from=900&hm_to=1301', {'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2'});
  const futureWorkspace = new HeatmapExplorerWorkspace(futureHarness.root, {
    window: futureHarness.window,
    document: futureHarness.document,
    fetch: futureTransport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
    nowSeconds() { return 1000; },
  });
  futureWorkspace.mount();
  await settleWorkspace();
  assert.strictEqual(futureTransport.requests.length, 0, 'deep-linked future windows must fail before the first fetch');
  assert.strictEqual(futureHarness.nodes.status.textContent, 'Invalid URL');

  const {workspace, harness} = mountedWorkspace('?page=4&hm_from=100&hm_to=200&hm_event=both', transport.fetch, {
    workspaceOptions: {nowSeconds() { return 1000; }},
  });
  workspace._bindEvents();
  workspace._syncControls();
  assert.strictEqual(harness.nodes.range.value, 'custom', 'deep-linked custom windows should hydrate the custom selector');
  assert.strictEqual(harness.nodes.from.value, '100');
  assert.strictEqual(harness.nodes.to.value, '200');

  const writesBefore = harness.historyWrites.length;
  harness.nodes.from.value = '200';
  harness.nodes.to.value = '100';
  harness.nodes.apply.dispatch('click');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 0, 'invalid custom windows must not fetch');
  assert.strictEqual(harness.historyWrites.length, writesBefore, 'invalid custom windows must not rewrite history');
  assert.strictEqual(harness.nodes.status.textContent, 'Invalid URL');
  assert.strictEqual(harness.nodes.alert.hidden, false);

  harness.nodes.from.value = '900';
  harness.nodes.to.value = '1301';
  harness.nodes.apply.dispatch('click');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 0, 'future custom windows beyond backend tolerance must not fetch');
  assert.strictEqual(harness.historyWrites.length, writesBefore, 'future custom windows must not rewrite history');
  assert.strictEqual(harness.nodes.status.textContent, 'Invalid URL');

  harness.nodes.from.value = '900';
  harness.nodes.to.value = '1300';
  harness.nodes.apply.dispatch('click');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 1, 'valid custom windows should request a fresh scene');
  assert.match(transport.requests[0].url, /from=900&to=1300/);
  transport.requests[0].resolve(jsonResponse(overviewSceneForWindow(900, 1300)));
  await settleWorkspace();
  assert.match(harness.nodes.share.attributes.href, /hm_from=900&hm_to=1300/);
  assert.doesNotMatch(harness.nodes.share.attributes.href, /hm_range=/);
  assert.strictEqual(harness.nodes.range.value, 'custom');
}

function assertExplicitStateAlertsStayLocalized() {
  const {workspace, harness} = mountedWorkspace('?page=4&hm_event=both', null, {
    rootAttributes: {
      'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
    },
  });
  const blockedScene = new HeatmapExplorerScene(blockedSceneFixture('weak_projection', {
    query: {
      game: 'cstrike',
      map: 'de_nuke',
      player: 42,
      from: 1785456000,
      to: 1788048000,
      event: 'both',
      lens: 'overview',
      floor: 'all',
      lang: 'en',
    },
    map: {
      game: 'cstrike',
      realgame: 'cstrike',
      name: 'de_nuke',
      image: {url: './de_nuke.jpg', width: 64, height: 32},
      projectionHash: 'a4dd45e46d84a12f',
      floorConfigHash: '97d170e1550eee4a',
    },
    fallback: {
      v1: 'heatmap_points.php?game=cstrike&map=de_nuke',
      jpeg: './de_nuke-kill.jpg',
      thumbnail: './de_nuke-kill-thumb.jpg',
    },
  }));
  workspace._applyScene(blockedScene, 'map');
  assert.strictEqual(harness.nodes.alert.hidden, false, 'blocked explicit states should remain visible');
  assert.strictEqual(harness.nodes.alert.textContent, 'Projection is too weak for Explorer rendering');
  assert.match(harness.nodes.summary.textContent, /Period:/, 'blocked states should preserve the textual summary');
  assert.strictEqual(
    harness.nodes.alert.children[0].children[0].attributes.href,
    'heatmap_points.php?game=cstrike&map=de_nuke&player=42&event=both'
  );
  assert.notStrictEqual(
    harness.nodes.alert.children[0].children[0].attributes.href,
    blockedScene.fallback.v1,
    'blocked-state action must preserve player scope and current event from the trusted base'
  );
  assert.strictEqual(harness.nodes.status.textContent, 'Projection is too weak for Explorer rendering');

  const emptyHarness = mountedWorkspace();
  emptyHarness.workspace._applyScene(new HeatmapExplorerScene(emptyScenePayload), 'map');
  assert.strictEqual(emptyHarness.harness.nodes.alert.hidden, true, 'empty should remain a truthful non-error state');
  assert.strictEqual(emptyHarness.harness.nodes.status.textContent, 'Empty');
}

function assertPanModeSuppressesDragClicks() {
  const panGl = fakeGl();
  const panDom = makeDom(panGl);
  let panEnabled = false;
  const panRenderer = new HeatmapGlRenderer(panDom.root, validScene, {
    window: panDom.window,
    pointerPan() { return panEnabled; },
  });
  const panCamera = new HeatmapExplorerCamera({
    viewportWidth: 320,
    viewportHeight: 240,
    contentWidth: 640,
    contentHeight: 480,
  });
  panCamera.zoomAt(2, 160, 120);
  panRenderer.mount();
  panRenderer.setCamera(panCamera);
  const disabledPanX = panCamera.state.panX;
  let disabledMovePrevented = false;
  panDom.nodes.canvas.dispatchEvent({type: 'pointerdown', clientX: 10, clientY: 10, pointerId: 7});
  panDom.nodes.canvas.dispatchEvent({type: 'pointermove', clientX: 40, clientY: 40, pointerId: 7, preventDefault() { disabledMovePrevented = true; }});
  panDom.nodes.canvas.dispatchEvent({type: 'pointerup', clientX: 40, clientY: 40, pointerId: 7});
  assert.strictEqual(panCamera.state.panX, disabledPanX, 'pan mode should stay disabled until requested');
  assert.strictEqual(disabledMovePrevented, false, 'non-pan pointer movement should preserve default scrolling');

  panEnabled = true;
  let thresholdMovePrevented = false;
  let activeDragPrevented = false;
  panDom.nodes.canvas.dispatchEvent({type: 'pointerdown', clientX: 60, clientY: 60, pointerId: 8});
  panDom.nodes.canvas.dispatchEvent({type: 'pointermove', clientX: 58, clientY: 58, pointerId: 8, preventDefault() { thresholdMovePrevented = true; }});
  assert.strictEqual(panCamera.state.panX, disabledPanX, 'sub-threshold movement should not pan the camera');
  assert.strictEqual(thresholdMovePrevented, false, 'threshold probe should not cancel default scrolling yet');
  panDom.nodes.canvas.dispatchEvent({type: 'pointermove', clientX: 28, clientY: 34, pointerId: 8, preventDefault() { activeDragPrevented = true; }});
  assert.notStrictEqual(panCamera.state.panX, 0, 'dragging in pan mode should move the camera');
  assert.strictEqual(activeDragPrevented, true, 'active drag should prevent default scrolling once pan actually starts');
  panDom.nodes.canvas.dispatchEvent({type: 'pointerup', clientX: 28, clientY: 34, pointerId: 8});
  assert.deepStrictEqual(panDom.nodes.canvas.captures, [8], 'drag pan should use pointer capture');
  assert.deepStrictEqual(panDom.nodes.canvas.releasedCaptures, [8], 'drag pan should release pointer capture on completion');
  assert.strictEqual(panRenderer.consumeSuppressedClick(), true, 'dragging should suppress the trailing click');
  assert.strictEqual(panRenderer.consumeSuppressedClick(), false, 'suppressed clicks should be one-shot');
  panRenderer.destroy();

  const {workspace, harness} = mountedWorkspace();
  let suppressed = true;
  workspace._scene = validScene;
  workspace._renderer = {consumeSuppressedClick() { const value = suppressed; suppressed = false; return value; }};
  workspace._bindEvents();
  workspace._syncControls();
  assert.strictEqual(harness.root.attributes['data-heatmap-pan-active'], '0');
  assert.strictEqual(harness.nodes.stage.attributes['data-heatmap-pan-active'], '0');
  assert.strictEqual(harness.nodes.canvas.attributes['data-heatmap-pan-active'], '0');
  assert.strictEqual(harness.nodes.stage.style.touchAction, 'auto');
  assert.strictEqual(harness.nodes.canvas.style.touchAction, 'auto');
  harness.nodes.pan.dispatch('click');
  assert.strictEqual(harness.root.attributes['data-heatmap-pan-active'], '1');
  assert.strictEqual(harness.nodes.stage.attributes['data-heatmap-pan-active'], '1');
  assert.strictEqual(harness.nodes.canvas.attributes['data-heatmap-pan-active'], '1');
  assert.strictEqual(harness.nodes.stage.style.touchAction, 'none');
  assert.strictEqual(harness.nodes.canvas.style.touchAction, 'none');
  harness.nodes.pan.dispatch('click');
  assert.strictEqual(harness.root.attributes['data-heatmap-pan-active'], '0');
  assert.strictEqual(harness.nodes.stage.style.touchAction, 'auto');
  assert.strictEqual(harness.nodes.canvas.style.touchAction, 'auto');
  harness.nodes.canvas.dispatch('click', {clientX: 350, clientY: 60});
  assert.strictEqual(workspace.state.cell, null, 'suppressed drag clicks must not pin a cell');
  harness.nodes.canvas.dispatch('click', {clientX: 350, clientY: 60});
  assert.strictEqual(workspace.state.cell, 'c2.0', 'tap/click pinning should remain available after suppression clears');
}

async function assertInspect422StaysFailClosed() {
  const transport = deferredTransport();
  const harness = richWorkspaceHarness('?page=4&hm_event=both', {
    'data-heatmap-v1-url': 'heatmap_points.php?game=cstrike&map=de_dust2&player=42&event=kills',
  });
  const workspace = new HeatmapExplorerWorkspace(harness.root, {
    window: harness.window,
    document: harness.document,
    fetch: transport.fetch,
    messages: workspaceMessages,
    Renderer: WorkspaceRenderer,
  });

  workspace.mount();
  await settleWorkspace();
  transport.requests[0].resolve(jsonResponse(sceneForMap('de_dust2')));
  await settleWorkspace();
  const retainedScene = workspace._scene;

  workspace.pin('c2.0');
  await settleWorkspace();
  assert.strictEqual(transport.requests.length, 2, 'pinning should issue a dedicated inspect request');
  transport.requests[1].resolve(httpJsonResponse(422, sceneWithState('too_many_events')));
  await settleWorkspace();

  assert.strictEqual(workspace._scene, retainedScene, 'inspect 422 responses must not replace the validated scene');
  assert.strictEqual(harness.nodes.status.textContent, 'Failed', 'inspect 422 responses must stay generic failures');
  assert.strictEqual(harness.nodes.alert.hidden, false, 'inspect 422 failures should remain visible');
  assert.strictEqual(harness.nodes.alert.textContent, 'Failed', 'inspect 422 failures must not borrow the scene-specific too_many_events message');
  assert.strictEqual(harness.nodes.alert.children.length, 1, 'inspect 422 failures should expose one generic action group');
  assert.strictEqual(harness.nodes.alert.children[0].children[0].textContent, 'Retry', 'inspect 422 failures should keep retry available for inspect');
}

(async function runFixRoundOneRegressions() {
  await assertSeparateInspectAndDeepLinkFlow();
  await assertClearedInspectCannotRetry();
  await assertLatestSceneRequestWins();
  await assertStaleMapImageRecoversOnceThenFallsBack();
  await assertSupersededMapRecoveryCannotHideNewestScene();
  await assertFloorFocusPersistsThroughEnabledReload();
  await assertFloorFocusDoesNotTargetUnavailableReload();
  await assertFloorFocusDoesNotStealMovedFocus();
  assertZoomUsesReversibleFactors();
  await assertFailureActionsUseKnownV1Route();
  await assertInitialFailureUsesServerV1RouteWhenSceneIsMissing();
  await assertScene422TooManyEventsUsesSpecializedStatePresentation();
  await assertBlockedDeepLinkScenesDoNotAutoInspect();
  await assertSceneNonOkFailuresStayFailClosedExceptTooManyEvents422();
  await assertFetchPathPublishesSpecializedStates();
  assertUnavailableFloorsStayVisible();
  assertAllFloorsAggregateLabelOmitsMisleadingZeroCount();
  await assertCustomWindowApplyValidation();
  assertExplicitStateAlertsStayLocalized();
  assertPanModeSuppressesDragClicks();
  await assertInspect422StaysFailClosed();
  assertWorkspaceStageAspectUsesAuthoritativeSceneDimensions();
  await assertMapStyleStaysInstanceLocalAndDoesNotReload();
  assertMapStyleCssStaysScoped();
  console.log('heatmap explorer contract smoke ok');
}()).catch(error => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
