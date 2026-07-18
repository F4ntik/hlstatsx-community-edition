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
