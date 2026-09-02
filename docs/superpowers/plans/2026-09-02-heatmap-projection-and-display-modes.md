# Heatmap Projection and Display Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Modern Heatmap Explorer coordinates visibly trustworthy on `cstrike/de_dust2` and provide Smooth, Cells, and exact projected Points display modes.

**Architecture:** Preserve the existing MySQL -> PHP v2 scene -> WebGL2 pipeline and static JPEG fallback. Add a bounded exact-coordinate collection seam to the existing scene pass, an admin-only similarity/landmark calibration gate, a cached Gaussian presentation field for Smooth, and a lazy point-geometry operation for Points. Projection mutations continue through the existing authenticated preview, stale-hash, transactional save, and readback path.

**Tech Stack:** PHP 8-compatible product code, vanilla ES5-style JavaScript, WebGL2/GLSL ES 3.00, existing EN/RU dictionaries, Node/PHP smoke harnesses, Playwright-based runtime visual gate.

**Spec:** `docs/plans/2026-09-02-heatmap-projection-and-display-modes-design.md`

## Global Constraints

- Keep `web/heatmap_points.php` as the v1/v2 seam; do not change legacy v1, public URLs, MySQL schema, or static JPEG fallback behavior.
- Keep `HeatmapExplorerBeta` rollout/rollback semantics unchanged.
- Default display mode is `smooth`; display mode is instance-local and never enters share/query URL state.
- Smooth uses `sigma=1.25`, radius `4`, post-smoothing normalization, and the accepted square-root visibility transfer.
- Cells remains the exact authoritative v2 grid and local presentation rollback.
- Points contains projected map-pixel coordinates only; never expose raw XYZ, event IDs, timestamps, weapons, or per-point identities.
- Point geometry is hard-capped at 20,000 unique projected positions; the 20,001st position returns an explicit refusal with no sampled prefix.
- Difference positive/negative lobes stay separate and share one normalization maximum.
- A projection candidate cannot be persisted from in-bounds coverage alone; preview identity and landmark/holdout evidence are mandatory.
- Do not copy Valve/Steam BMP/TXT assets into the repository or release.
- Preserve all pre-existing untracked replay/audit artifacts and stage only task-owned paths.
- Source, local runtime, and production/release acceptance remain distinct claims.

---

### Task 1: Exact Admin Preview and Responsive Projection Controls

**Files:**
- Modify: `web/includes/heatmap_points.php:919-1510`
- Modify: `web/heatmap_admin.php:324-448`
- Modify: `web/includes/js/heatmap.js:602-1707`
- Modify: `web/pages/admintasks/heatmaps.php:25-126`
- Test: `scripts/web_heatmap_smoke.php:953-1091`
- Test: `scripts/heatmap_js_smoke.js:1-180`

**Interfaces:**
- Consumes: existing `heatmap_build_scene()` query/config/image semantics and `HeatmapProjection.unrotate()`.
- Produces: preview-only `exact` geometry, `HeatmapAdminGeometry.canvasDelta()`, `HeatmapAdminGeometry.offsetDelta()`, and `HeatmapCanvas.prototype.drawPoints()`.

- [ ] **Step 1: Write failing PHP tests for preview-only exact coordinates**

Add fixtures that call scene construction with `array('exact' => true, 'exactLimit' => 20000)` and assert this response contract:

```php
$exact = $scene['exact'];
assert_same(array('x', 'y', 'z', 'projectedX', 'projectedY', 'channel', 'participant', 'inBounds'), $exact['fields']);
assert_same(array(10, 20, 30, 11, 42, 'kills', 'attacker', true), $exact['points'][0]);
assert_same(false, array_key_exists('exact', $sceneWithoutExact));
assert_same(true, $overflowScene['exact']['overflow']);
assert_same(array(), $overflowScene['exact']['points']);
```

Cover attacker/kills, victim/deaths, floor rejection, OOB preservation, duplicate events, exact-limit acceptance, and overflow. Assert that weak grid projection may clear grid layers but retains exact preview rows.

- [ ] **Step 2: Run the PHP smoke test and confirm RED**

Run:

```powershell
rtk php scripts/web_heatmap_smoke.php
```

Expected: FAIL because `heatmap_build_scene()` has no exact option/response.

- [ ] **Step 3: Add bounded exact-coordinate collection to the existing scene pass**

Extend the scene accumulator only after participant selection, floor filtering, projection, and bounds calculation. Use a request-only option; do not add persisted fields.

```php
function heatmap_scene_add_exact_point(array &$scene, array $row, array $projected, string $channel, string $participant): void
{
    if (!isset($scene['exact'])) {
        return;
    }
    if ($scene['exact']['overflow']) {
        return;
    }
    if (count($scene['exact']['points']) >= $scene['exact']['limit']) {
        $scene['exact']['points'] = array();
        $scene['exact']['overflow'] = true;
        return;
    }
    $scene['exact']['points'][] = array(
        (int) $row['pos_x'], (int) $row['pos_y'], (int) $row['pos_z'],
        (int) $projected['x'], (int) $projected['y'],
        $channel, $participant, (bool) $projected['in_bounds'],
    );
}
```

Return exact preview geometry only from authenticated `heatmap_admin.php`; do not expose raw XYZ through the public scene route.

- [ ] **Step 4: Add failing JavaScript tests for responsive drag conversion**

Export a pure `HeatmapAdminGeometry` helper and assert:

```js
assert.deepStrictEqual(
  Array.from(HeatmapAdminGeometry.offsetDelta(10, 20, {width: 640, height: 512}, 1280, 1024, 4, 0)),
  [80, 160]
);
assert.deepStrictEqual(
  Array.from(HeatmapAdminGeometry.offsetDelta(10, 20, {width: 640, height: 512}, 1280, 1024, 4, 1)),
  [160, -80]
);
```

Also cover native-size display, independent X/Y CSS scale, and zero rectangle dimensions without `NaN`/`Infinity`.

- [ ] **Step 5: Run the JavaScript smoke and confirm RED**

Run:

```powershell
rtk node scripts/heatmap_js_smoke.js
```

Expected: FAIL because `HeatmapAdminGeometry` is not exported.

- [ ] **Step 6: Implement native-canvas drag conversion and exact point drawing**

Implement:

```js
function canvasDelta(clientDx, clientDy, rect, canvasWidth, canvasHeight) {
  var width = Math.max(1, Number(rect.width) || 0);
  var height = Math.max(1, Number(rect.height) || 0);
  return [clientDx * canvasWidth / width, clientDy * canvasHeight / height];
}

function offsetDelta(clientDx, clientDy, rect, canvasWidth, canvasHeight, projectionScale, rotateSteps) {
  var nativeDelta = canvasDelta(clientDx, clientDy, rect, canvasWidth, canvasHeight);
  return HeatmapProjection.unrotate(
    nativeDelta[0] * projectionScale,
    nativeDelta[1] * projectionScale,
    rotateSteps
  );
}
```

Capture the rectangle/canvas dimensions at drag start. Add preview-only `points` renderer mode with small circular dots/crosses and explicit OOB edge indicators; do not persist renderer selection.

- [ ] **Step 7: Run focused PHP/JS verification**

Run:

```powershell
rtk node --check web/includes/js/heatmap.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 8: Commit Task 1**

Stage only the six Task 1 paths and commit:

```powershell
rtk git commit -m "feat(heatmap): preview exact calibration coordinates"
```

---

### Task 2: Landmark Similarity Solver and Save Authorization Gate

**Files:**
- Modify: `web/includes/js/heatmap.js:841-1501`
- Modify: `web/pages/admintasks/heatmaps.php:25-126`
- Modify: `web/heatmap_admin.php:269-520`
- Modify: `web/includes/heatmap_points.php:2574-3072`
- Modify: `web/lang/en.php`
- Modify: `web/lang/ru.php`
- Modify: `web/pages/header.php`
- Test: `scripts/heatmap_js_smoke.js`
- Test: `scripts/web_heatmap_smoke.php`
- Test: `scripts/web_i18n_smoke.php`

**Interfaces:**
- Consumes: Task 1 exact admin points and existing normalized projection/config hash.
- Produces: `HeatmapLandmarkSolver.solve()`, per-anchor residuals, preview token, and an explicit registration gate before persistence.

- [ ] **Step 1: Write failing solver tests for all supported orientations**

Create a synthetic truth set with six world/map pairs. For each of four rotations and one optional reflection, assert recovery of the known uniform scale/translation within `1e-6`. Add one gross outlier and require it to be rejected while at least four inliers remain.

```js
var result = HeatmapLandmarkSolver.solve(anchors, {minimumAnchors: 4, outlierPixels: 10});
assert.strictEqual(result.ok, true);
assert.strictEqual(result.rotate, 0);
assert.strictEqual(result.flipX, false);
assert.strictEqual(result.flipY, true);
assert.ok(Math.abs(result.scale - 1.428254465) < 1e-6);
assert.ok(result.rmse < 0.001);
assert.strictEqual(result.inliers.length, 6);
```

Add failure cases for fewer than four anchors, collinear anchors, two holdouts missing, non-finite values, and anisotropic residual growth.

- [ ] **Step 2: Run JavaScript smoke and confirm RED**

Run:

```powershell
rtk node scripts/heatmap_js_smoke.js
```

Expected: FAIL because `HeatmapLandmarkSolver` does not exist.

- [ ] **Step 3: Implement the constrained least-squares solver**

For each supported orientation `D`, solve the similarity model:

```text
pixel = a * D(world) + t
scale = 1 / a
```

Use centered covariance for `a`, means for `t`, and compute residual for every anchor. Reject points above `max(10, medianResidual * 3)` once, refit, then score by holdout RMSE. Return no candidate when X/Y residual trends demonstrate a non-uniform mapping.

Expose only normalized existing config fields:

```js
{
  ok: true,
  xoffset: 376,
  yoffset: 1207,
  scale: 1.428254465,
  flipX: false,
  flipY: true,
  rotate: 0,
  rmse: 2.1,
  maximumResidual: 4.8,
  inliers: [0, 1, 2, 3],
  holdouts: [4, 5]
}
```

- [ ] **Step 4: Write failing tests for preview-token authorization**

Assert that the preview response supplies a token bound to normalized candidate projection, image/overview identity, query window, map, floor, channel, and CSRF session. Assert that any bound-field change invalidates it, while palette/normalization changes do not.

```php
$token = heatmap_admin_preview_token($config, $image, $query, $csrfToken);
assert_same($token, heatmap_admin_preview_token($config, $image, $query, $csrfToken));
$changed = $config;
$changed['scale'] = 1.5;
assert_not_same($token, heatmap_admin_preview_token($changed, $image, $query, $csrfToken));
```

Require `409 preview_required` before any write for missing/mismatched tokens; keep stale `configHash` rejection first.

- [ ] **Step 5: Implement preview token and UI gate**

Add:

```php
function heatmap_admin_preview_token(array $config, array $image, array $query, string $csrfToken): string
{
    $queryIdentity = array(
        'game' => (string) $query['game'],
        'map' => (string) $query['map'],
        'from' => (int) $query['from'],
        'to' => (int) $query['to'],
        'event' => (string) $query['event'],
        'floor' => (string) $query['floor'],
    );
    $canonical = heatmap_admin_config_hash($config, $image)
        . "\n"
        . json_encode($queryIdentity, JSON_UNESCAPED_SLASHES);
    return hash_hmac('sha256', $canonical, $csrfToken);
}
```

The UI invalidates the token after any projection/crop/floor/window/channel edit. Save is enabled only after an exact-point preview, at least four anchors, at least two holdouts, and a solver result inside the selected tolerance. Keep the existing transactional lock/save/readback/hash comparison unchanged.

- [ ] **Step 6: Add EN/RU calibration copy and parity assertions**

Add localized keys for landmark labels, anchor/holdout counts, residuals, candidate refusal, preview-required, asset mismatch, and registration-vs-coverage status. Serialize them through the existing header i18n object and assert dictionary parity.

- [ ] **Step 7: Run focused verification**

Run:

```powershell
rtk node --check web/includes/js/heatmap.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk php scripts/web_i18n_smoke.php
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 8: Commit Task 2**

```powershell
rtk git commit -m "feat(heatmap): gate projection saves on landmark preview"
```

---

### Task 3: Smooth and Cells Presentation Modes

**Files:**
- Modify: `web/includes/js/heatmap-explorer.js:1318-1632`
- Modify: `web/includes/heatmap_points.php:147-260`
- Modify: `web/lang/en.php`
- Modify: `web/lang/ru.php`
- Modify: `web/pages/header.php`
- Modify: `web/hlstats.css:578-820`
- Test: `scripts/heatmap_js_smoke.js:653-1050`
- Test: `scripts/web_heatmap_smoke.php:220-280`
- Test: `scripts/web_i18n_smoke.php`

**Interfaces:**
- Consumes: unchanged authoritative `HeatmapExplorerScene.dense()` arrays.
- Produces: Gaussian presentation helpers, RG density texture, manual bilinear shader sampling, and instance-local `smooth|cells` control.

- [ ] **Step 1: Write failing pure Gaussian-field tests**

Export test-only helpers and assert kernel length 9, symmetry, sum 1, constant-field preservation at corners, radial impulse symmetry, monotonic falloff, finite/nonnegative output, and connected density between impulses separated by two cells.

```js
var kernel = gaussianKernel1d(1.25, 4);
assert.strictEqual(kernel.length, 9);
assert.ok(Math.abs(Array.from(kernel).reduce((a, b) => a + b, 0) - 1) < 1e-7);
var constant = gaussianSmooth(new Float32Array(35).fill(7), 7, 5, kernel);
constant.forEach(value => assert.ok(Math.abs(value - 7) < 1e-6));
```

- [ ] **Step 2: Run JavaScript smoke and confirm RED**

Run `rtk node scripts/heatmap_js_smoke.js`.

Expected: FAIL because Gaussian helpers do not exist.

- [ ] **Step 3: Implement separable edge-renormalized smoothing and signed lobes**

Add:

```js
function gaussianKernel1d(sigma, radius) {
  var kernel = new Float32Array(radius * 2 + 1);
  var sum = 0;
  for (var offset = -radius; offset <= radius; offset += 1) {
    var weight = Math.exp(-(offset * offset) / (2 * sigma * sigma));
    kernel[offset + radius] = weight;
    sum += weight;
  }
  for (var index = 0; index < kernel.length; index += 1) {
    kernel[index] /= sum;
  }
  return kernel;
}

function convolveAxisRenormalized(input, width, height, kernel, horizontal) {
  var radius = Math.floor(kernel.length / 2);
  var output = new Float32Array(input.length);
  for (var y = 0; y < height; y += 1) {
    for (var x = 0; x < width; x += 1) {
      var weighted = 0;
      var surviving = 0;
      for (var offset = -radius; offset <= radius; offset += 1) {
        var sampleX = horizontal ? x + offset : x;
        var sampleY = horizontal ? y : y + offset;
        if (sampleX < 0 || sampleX >= width || sampleY < 0 || sampleY >= height) {
          continue;
        }
        var weight = kernel[offset + radius];
        weighted += input[sampleY * width + sampleX] * weight;
        surviving += weight;
      }
      output[y * width + x] = surviving > 0 ? weighted / surviving : 0;
    }
  }
  return output;
}

function gaussianSmooth(input, width, height, kernel) {
  return convolveAxisRenormalized(
    convolveAxisRenormalized(input, width, height, kernel, true),
    width, height, kernel, false
  );
}

function interleaveDensity(positive, negative) {
  var output = new Float32Array(positive.length * 2);
  for (var index = 0; index < positive.length; index += 1) {
    output[index * 2] = positive[index];
    output[index * 2 + 1] = negative[index];
  }
  return output;
}
```

For Difference use:

```js
rawPositive[i] = Math.max(dense.values[i], 0);
rawNegative[i] = Math.max(-dense.values[i], 0);
weightedConfidence[i] = Math.abs(dense.values[i]) * dense.opacity[i];
support[i] = Math.abs(dense.values[i]);
```

Smooth the four fields separately and derive confidence as smoothed weighted confidence divided by smoothed support. Cache by `mode:layer:channel`. Never mutate raw scene arrays.

- [ ] **Step 4: Write failing Cells/Smooth renderer tests**

Extend fake GL with `RG32F`, `RG`, and `u_smooth`. Assert Cells uploads exact positive/negative raw fields and `u_smooth=0`; Smooth uploads cached Gaussian fields and `u_smooth=1`. Verify a 2x2 field bilinearly samples to 0.5 at center, edge sampling clamps, repeated mode switches reuse resources, and old 3x3 shader loop is absent.

- [ ] **Step 5: Implement RG texture and manual bilinear shader sampling**

Keep `NEAREST` texture configuration. In GLSL, derive `p0/p1/fraction`, use four `texelFetch` samples and nested `mix`. For Difference compute:

```glsl
float balance = (density.r - density.g) / max(density.r + density.g, 0.000001);
float magnitude = max(density.r, density.g);
float amount = sqrt(clamp(magnitude / u_displayMax, 0.0, 1.0));
```

Smooth Difference alpha is `amount * confidence`; Cells retains the current occupied-cell 0.22 floor.

- [ ] **Step 6: Add the localized Smooth/Cells control and workspace tests**

Default to Smooth. A mode switch calls only renderer `setDisplayMode()` and `_syncControls()`; assert zero fetches, URL/history writes, state changes, or scene replacement. Hide the selector during static fallback/context loss. On Gaussian preparation failure, fall back to Cells with localized status; GL failure still uses existing static fallback.

- [ ] **Step 7: Run focused verification**

```powershell
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk php scripts/web_i18n_smoke.php
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 8: Commit Task 3**

```powershell
rtk git commit -m "feat(heatmap): add smooth and cell display modes"
```

---

### Task 4: Bounded v2 Exact Point Geometry Operation

**Files:**
- Modify: `web/includes/heatmap_points.php:8-1510`
- Modify: `web/heatmap_points.php:108-330`
- Test: `scripts/web_heatmap_smoke.php:108-1800`

**Interfaces:**
- Consumes: exact scene query/filter/projection semantics from Task 1.
- Produces: `geometry=points` v2 operation, strict cache identity, privacy-safe sorted rows, and explicit 20,000-position refusal.

- [ ] **Step 1: Write failing request, aggregation, and cache tests**

Test valid `geometry=points`, invalid geometry, geometry+inspect rejection, exact `[from,to)` preservation, cache separation from grid scenes, projection/floor/image hash identity, duplicate pixel aggregation, attacker/victim channels, Overview/Me/Difference counts, sorting, uniqueness, 20,000 success, and 20,001 refusal with zero retained rows.

Expected ordinary response fields:

```php
assert_same(array('x', 'y', 'kills', 'deaths'), $payload['fields']);
assert_same(array(381, 204, 1, 0), $payload['points'][0]);
assert_same('geometry', $payload['operation']);
assert_same('points', $payload['kind']);
```

Assert forbidden names and values never serialize: `pos_x`, `pos_y`, `pos_z`, `eventId`, `timestamp`, `weapon`, `playerName`.

- [ ] **Step 2: Run PHP smoke and confirm RED**

Run `rtk php scripts/web_heatmap_smoke.php`.

Expected: FAIL because geometry query/response is unsupported.

- [ ] **Step 3: Implement geometry constants and query validation**

Add:

```php
const HEATMAP_POINT_GEOMETRY_VERSION = 1;
const HEATMAP_POINT_MAX_POSITIONS = 20000;
```

Accept only `geometry=points`; reject geometry+inspect. Do not include `geometry` in canonical public query output.

- [ ] **Step 4: Implement shared-pass pixel aggregation**

Extend scene execution with `array('geometry' => 'points')`. Aggregate on canonical `"{$y}.{$x}"` after floor/projection/bounds validation. At the 20,001st unique key set overflow, clear point rows, stop point collection, and continue normal scene counters. Sort by Y then X.

Ordinary rows are `[x,y,kills,deaths]`. Difference rows are `[x,y,personal,others]`, using the existing personal/other sample normalization contract.

- [ ] **Step 5: Implement strict geometry caching and route behavior**

Include geometry version/kind, exact query, projection hash, floor hash, and resolved image identity in the key. Cache only complete `ok` and `empty`; return HTTP 422 plus `Cache-Control: no-store` for `too_many_points`. Log operation, points returned, source rows, bytes, latency, cache status, and fallback reason.

- [ ] **Step 6: Run focused verification**

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/heatmap_points.php
rtk php -l web/includes/heatmap_points.php
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 7: Commit Task 4**

```powershell
rtk git commit -m "feat(heatmap): serve bounded exact point geometry"
```

---

### Task 5: Points Renderer, Lazy Workspace Lifecycle, and Unified Selector

**Files:**
- Modify: `web/includes/js/heatmap-explorer.js:491-3200`
- Modify: `web/includes/heatmap_points.php:147-260`
- Modify: `web/lang/en.php`
- Modify: `web/lang/ru.php`
- Modify: `web/pages/header.php`
- Modify: `web/hlstats.css`
- Test: `scripts/heatmap_js_smoke.js`
- Test: `scripts/web_heatmap_smoke.php`
- Test: `scripts/web_i18n_smoke.php`

**Interfaces:**
- Consumes: Task 3 display state/render resources and Task 4 geometry response.
- Produces: `HeatmapPointGeometry`, lazy geometry lifecycle, circular WebGL `gl.POINTS`, and final Smooth/Cells/Points control.

- [ ] **Step 1: Write failing strict geometry-validator tests**

Add normal and Difference fixtures. Reject extra keys, wrong schema/operation/version/kind, query or map mismatch, incorrect fields, unsorted/duplicate/OOB rows, negative/noninteger counts, more than 20,000 rows, summary mismatch, and Difference with `event=both`.

```js
var geometry = new HeatmapPointGeometry(pointFixture());
assert.strictEqual(geometry.matchesScene(scene), true);
assert.throws(() => new HeatmapPointGeometry(pointFixture({points: [[2, 2, 1, 0], [1, 1, 1, 0]]})));
```

- [ ] **Step 2: Run JavaScript smoke and confirm RED**

Run `rtk node scripts/heatmap_js_smoke.js`.

Expected: FAIL because `HeatmapPointGeometry` does not exist.

- [ ] **Step 3: Implement the strict geometry model and vertex data**

Add:

```text
new HeatmapPointGeometry(payload)
  -> immutable validated geometry or throws TypeError
geometry.matchesScene(scene)
  -> boolean identity comparison
geometry.vertexData(scene)
  -> Float32Array [normalizedX, normalizedY, value, confidence] rows
```

Vertex rows contain normalized pixel X/Y plus value/confidence. Preserve one shared maximum for Difference. Export the constructor through the existing frozen module surface.

- [ ] **Step 4: Write failing lazy workspace tests**

Assert Smooth<->Cells makes zero requests; first Points selection makes exactly one canonical geometry request using scene `from/to`; switching away invalidates pending results; unchanged scene reuses geometry; new map/window/floor/lens/channel clears it; cap/network/malformed/identity failure selects Cells; geometry never appears in inspect or share URL.

- [ ] **Step 5: Implement lazy geometry lifecycle**

Add workspace fields and these exact method contracts:

```js
this._displayMode = 'smooth';
this._pointGeometry = null;
this._geometryGeneration = 0;
this._geometryLoading = false;

pointGeometryUrl(scene) -> canonical URL with exact from/to and geometry=points
_loadPointGeometry() -> one generation-guarded Promise or retained geometry
_applyPointGeometry(geometry) -> validates scene identity and renders Points
_fallbackFromPoints(messageKey) -> selects Cells and publishes localized status
```

Use generation equality plus `matchesScene()` before applying a response. Retain geometry only for the current immutable scene.

- [ ] **Step 6: Write failing WebGL point-resource tests**

Extend fake GL with `POINTS`, attribute buffers, point-size uniform, and draw evidence. Assert lazy resource creation, one vertex per aggregated coordinate, circular `gl_PointCoord` discard, bounded marker size, palette semantics, Difference normalization/confidence, context restoration, cleanup, and Cells fallback without static JPEG.

- [ ] **Step 7: Implement native circular Points rendering**

Add lazy point program/buffer methods. Vertex shader converts authoritative map pixel positions directly to clip space. Fragment shader uses:

```glsl
vec2 delta = gl_PointCoord - vec2(0.5);
if (dot(delta, delta) > 0.25) { discard; }
```

Call `gl.drawArrays(gl.POINTS, 0, vertexCount)`. Keep marker diameter screen-legible and bounded; count changes intensity, not marker area. Point-resource failures fall back to Cells.

- [ ] **Step 8: Complete localized unified selector and inspector regression**

Render Smooth/Cells/Points buttons with 44x44 minimum targets and ARIA pressed state. Keep pointer-to-cell, pin, inspect URL, keyboard navigation, and 100-row detail contract unchanged in all modes. Hide selector during no-JS/WebGL/static fallback.

- [ ] **Step 9: Run focused verification**

```powershell
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk php scripts/web_i18n_smoke.php
rtk git diff --check
```

Expected: all PASS.

- [ ] **Step 10: Commit Task 5**

```powershell
rtk git commit -m "feat(heatmap): add exact points display mode"
```

---

### Task 6: Objective Visual Gates, de_dust2 Preview, and Acceptance Boundary

**Files:**
- Modify: `scripts/heatmap_visual_gate.js:293-760`
- Modify after current evidence passes: `docs/audits/modern-heatmap-explorer/runtime-acceptance.md`
- Modify after current evidence passes: `docs/status.md`
- Create after current evidence passes: `docs/audits/modern-heatmap-explorer/evidence/acceptance-2026-09-02-projection-modes.json`
- Create after current evidence passes: screenshots under `docs/audits/modern-heatmap-explorer/screenshots/`

**Interfaces:**
- Consumes: Tasks 1-5, the exact served `de_dust2` image identity, populated local runtime, and the non-persisted candidate `376/1207/1.428254465/0/1/0`.
- Produces: repeatable smoothness/mode evidence and a clearly bounded projection preview receipt; persistent config save occurs only after landmark/user visual acceptance.

- [ ] **Step 1: Write failing smoothness/mode visual metrics**

Add frame metrics:

```js
distinctPositiveAlphaBytes
activeGridBoundaryJumpMean
neutralPixels
pointCircularityError
```

Capture default Smooth, Cells, Smooth again, and Points. Assert no request/URL/query change for Smooth/Cells, one canonical lazy request for Points, byte-identical repeated Smooth frames, different mode hashes, at least 32 distinct Smooth alpha levels, lower Smooth grid-boundary jump than Cells, warm/cool/neutral Difference evidence, and bounded circular point error.

- [ ] **Step 2: Run the source gate and confirm new assertions are RED before implementation integration**

Run the existing visual-gate command against the exact local contour using its documented arguments. Expected: the old square renderer fails the new Smooth continuity/circularity checks.

- [ ] **Step 3: Run the complete source verification set**

```powershell
rtk node --check web/includes/js/heatmap-explorer.js
rtk node --check web/includes/js/heatmap.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk php scripts/web_i18n_smoke.php
rtk python -m pytest scripts\hlstats_py\tests -q
rtk python -m pytest scripts\replay_baseline\tests -q
rtk git diff --check
```

Set `PYTHONPATH` to the checkout's `scripts` directory for product tests and to
`scripts;scripts/replay_baseline` for replay tests before the corresponding
command. Expected: all available checks PASS. If local dependencies are absent,
use the repository's documented interpreter/container and record the exact
replacement; do not relabel an unrun gate.

- [ ] **Step 4: Back up and preview the image-derived projection candidate without saving**

Record current config/image/hash. Preview exact events using:

```text
xoffset=376
yoffset=1207
scale=1.428254465
flipx=0
flipy=1
rotate=0
crop=0/0/0/0
```

Capture exact Points, Cells, and Smooth over the same immutable historical `[from,to)` window. Confirm the response projection hash changes while map asset hash and event window remain fixed.

- [ ] **Step 5: Run landmark/visual acceptance before any persistent save**

Use at least four anchors and two holdouts. Preview screenshots may be presented
to the user for early visual judgment, but they do not replace landmark
evidence and cannot authorize persistence. If live landmark capture is not yet
available, stop at a non-persisted preview, leave the stored DB config unchanged,
and record `PROJECTION-PREVIEWED / LANDMARK-NOT-RUN`. Do not claim landmark
acceptance from image registration alone.

- [ ] **Step 6: If accepted, save through authenticated preview token and verify exact readback**

Save only the accepted candidate, then verify config hash, numeric readback, map identity, grid/point cache invalidation, public EN/RU Smooth/Cells/Points, Difference, mobile, 200% reflow, context loss, static JPEG fallback, and legacy rollback. Regenerate JPEG through the existing supported path. On any failure restore the exact backup and read it back.

- [ ] **Step 7: Update acceptance/status documentation with exact boundaries**

Record source checks, mode/browser receipts, candidate vs stored config, landmark or user-visual acceptance status, restore state, and whether anything was persisted. Do not overwrite historical receipts. Do not call the work production/release accepted unless the corresponding production/release gates actually run.

- [ ] **Step 8: Obtain independent current-diff reviews**

Request one fresh review of projection/data/cache/privacy semantics and one fresh review of WebGL/UI/accessibility/visual evidence. Resolve every P0-P2 finding, rerun affected gates, and invalidate prior review receipts after post-review edits.

- [ ] **Step 9: Commit Task 6 documentation/evidence only after gates pass**

Stage only intended scripts, sanitized evidence, accepted screenshots, and docs:

```powershell
rtk git commit -m "test(heatmap): accept trusted projection display modes"
```

Do not stage ignored raw runtime receipts, machine-local paths, Steam assets, database backups, or pre-existing replay artifacts.
