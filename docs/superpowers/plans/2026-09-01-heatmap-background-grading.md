# Heatmap Explorer Background Grading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a localized `Color / Mono` presentation control that grades only the Modern Heatmap Explorer map background without changing heat data, coordinates, assets, URLs, API behavior, or v1/JPEG fallback.

**Architecture:** Keep the calibrated map `<img>` and transparent WebGL canvas as separate layers. Store the background style only in the mounted workspace, expose it through a validated root DOM attribute, and let scoped CSS grade the map image beneath the unchanged canvas. Hide the control whenever the workspace is showing a static or context-loss fallback.

**Tech Stack:** PHP 8-compatible server-rendered HTML, ES5-compatible browser JavaScript, CSS, Node smoke harness, PHP smoke harness, pytest route smoke, Playwright runtime acceptance.

**Spec:** `docs/plans/2026-09-01-heatmap-background-grading-design.md`

## Global Constraints

- Work only in `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer`.
- Run every local command through `rtk`.
- Use strict TDD: add each behavioral test, observe the expected RED failure, then write the minimum production code and observe GREEN.
- Preserve all unrelated dirty/untracked files; stage only the paths named in each task.
- Do not copy, convert, or bundle Steam/Valve overview assets.
- Do not change source image dimensions, hashes, crop, projection, point transforms, scene schema, URL state, API requests, cache keys, SQL, v1 routes, or generated JPEG behavior.
- Apply grading only to `[data-heatmap-image]`; never filter the WebGL canvas or `.heatmap-explorer__static img`.
- `Color` is the default; `Mono` is instance-local and resets on page refresh.
- Do not push.

---

### Task 1: Localized Background Style Controls

**Files:**
- Modify: `web/includes/heatmap_points.php:203-264`
- Modify: `web/lang/en.php:874-906`
- Modify: `web/lang/ru.php:317-349`
- Test: `scripts/web_heatmap_smoke.php:201-276`
- Test: `scripts/replay_baseline/tests/test_web_route_smoke.py`

**Interfaces:**
- Consumes: existing `heatmap_explorer_label(string): string`, `.heatmap-explorer__group`, and `.heatmap-explorer__control` conventions.
- Produces: root attribute `data-heatmap-map-style="color"`; fieldset `data-heatmap-map-style-controls="1"`; buttons `data-heatmap-map-style-option="color|mono"` with correct `aria-pressed` state.

- [ ] **Step 1: Add failing server-rendering assertions**

Extend the existing `heatmap_render_explorer_workspace()` smoke fixture with literal assertions equivalent to:

```php
assert_contains('data-heatmap-map-style="color"', $workspaceHtml, 'Explorer should default to the color map style');
assert_contains('data-heatmap-map-style-controls="1"', $workspaceHtml, 'Explorer should render the background style group');
assert_contains('data-heatmap-map-style-option="color" aria-pressed="true"', $workspaceHtml, 'Color should be selected initially');
assert_contains('data-heatmap-map-style-option="mono" aria-pressed="false"', $workspaceHtml, 'Mono should be available but unselected');
```

Add route-smoke checks that both public mounts still use the shared workspace renderer; do not grep exact CSS filter values.

- [ ] **Step 2: Run the tests and observe RED**

Run:

```powershell
rtk docker run --rm --network none --mount "type=bind,src=$PWD,dst=/workspace,readonly" --workdir /workspace --entrypoint php python-web scripts/web_heatmap_smoke.php
rtk pytest scripts/replay_baseline/tests/test_web_route_smoke.py -q
```

Expected: PHP smoke fails because `data-heatmap-map-style` and the two option buttons do not exist. Route smoke must remain green unless its new behavioral mount assertion is also RED for the intended missing control contract.

- [ ] **Step 3: Add minimal localized markup**

Add translation keys:

```php
// web/lang/en.php
'heatmapExplorer.mapStyle' => 'Map style',
'heatmapExplorer.color' => 'Color',
'heatmapExplorer.mono' => 'Mono',

// web/lang/ru.php
'heatmapExplorer.mapStyle' => 'Стиль карты',
'heatmapExplorer.color' => 'Цвет',
'heatmapExplorer.mono' => 'Ч/Б',
```

Add `data-heatmap-map-style="color"` to the root `<section>`. Add this compact fieldset beside the existing lens/channel fieldsets:

```php
$html .= '<fieldset class="heatmap-explorer__group" data-heatmap-map-style-controls="1"><legend>'
    . heatmap_explorer_html(heatmap_explorer_label('mapStyle')) . '</legend>';
$html .= '<button type="button" class="heatmap-explorer__control is-selected" data-heatmap-map-style-option="color" aria-pressed="true">'
    . heatmap_explorer_html(heatmap_explorer_label('color')) . '</button>';
$html .= '<button type="button" class="heatmap-explorer__control" data-heatmap-map-style-option="mono" aria-pressed="false">'
    . heatmap_explorer_html(heatmap_explorer_label('mono')) . '</button></fieldset>';
```

Do not add query fields, hidden inputs, persistence, or API data.

- [ ] **Step 4: Run server and route checks GREEN**

Run the two commands from Step 2 plus:

```powershell
rtk docker run --rm --network none --mount "type=bind,src=$PWD,dst=/workspace,readonly" --workdir /workspace --entrypoint php python-web -l web/includes/heatmap_points.php
rtk git diff --check
```

Expected: all pass with no warnings.

- [ ] **Step 5: Commit the markup contract**

```powershell
rtk git add -- web/includes/heatmap_points.php web/lang/en.php web/lang/ru.php scripts/web_heatmap_smoke.php scripts/replay_baseline/tests/test_web_route_smoke.py
rtk git diff --cached --check
rtk git commit -m "feat(heatmaps): add map style controls"
```

---

### Task 2: Instance-local Style Behavior and Scoped Grade

**Files:**
- Modify: `web/includes/js/heatmap-explorer.js:2070-2090,2422-2460,2907-2940`
- Modify: `web/hlstats.css:670-678,718-765,838-874`
- Test: `scripts/heatmap_js_smoke.js`

**Interfaces:**
- Consumes: Task 1 root attribute and option-button selectors.
- Produces: `HeatmapExplorerWorkspace.prototype._setMapStyle(style): boolean`; validated values `color|mono`; synchronized `aria-pressed`/`.is-selected` state; CSS-only presentation of the background image.

- [ ] **Step 1: Add failing JavaScript behavior tests**

In the rich workspace harness, include the two real option buttons and assert observable behavior:

```javascript
const requestsBeforeStyleChange = transport.requests.length;
const searchBeforeStyleChange = harness.window.location.search;
monoButton.dispatch('click', {currentTarget: monoButton});
assert.strictEqual(harness.root.getAttribute('data-heatmap-map-style'), 'mono');
assert.strictEqual(monoButton.getAttribute('aria-pressed'), 'true');
assert.strictEqual(colorButton.getAttribute('aria-pressed'), 'false');
assert.strictEqual(transport.requests.length, requestsBeforeStyleChange);
assert.strictEqual(harness.window.location.search, searchBeforeStyleChange);

colorButton.dispatch('click', {currentTarget: colorButton});
assert.strictEqual(harness.root.getAttribute('data-heatmap-map-style'), 'color');
```

Also prove that an invalid option value leaves the existing style unchanged and that a newly mounted workspace starts at `color` regardless of the prior instance.

- [ ] **Step 2: Run Node smoke and observe RED**

```powershell
rtk node scripts/heatmap_js_smoke.js
```

Expected: fail because style buttons are not bound and the root attribute/pressed states do not change.

- [ ] **Step 3: Implement the minimal workspace state**

Initialize `_mapStyle` to `color`. Add a strict setter:

```javascript
HeatmapExplorerWorkspace.prototype._setMapStyle = function (style) {
  if (style !== 'color' && style !== 'mono') {
    return false;
  }
  this._mapStyle = style;
  workspaceSetAttribute(this.root, 'data-heatmap-map-style', style);
  this._syncControls();
  return true;
};
```

Extend `_syncControls()` to update `[data-heatmap-map-style-option]` exactly like lens/event buttons. Extend `_bindEvents()` so clicking a style button calls only `_setMapStyle(style)`. It must not call `_setState()`, `_loadScene()`, `_writeUrl()`, `history.replaceState()`, or renderer methods.

- [ ] **Step 4: Add the scoped CSS grade**

Use explicit layer ordering so the decorative grade stays below the semantic canvas:

```css
.heatmap-explorer [data-heatmap-image] {
  position: relative;
  z-index: 0;
  transition: filter 120ms ease;
}

.heatmap-explorer [data-heatmap-camera]::after {
  position: absolute;
  z-index: 1;
  inset: 0;
  content: "";
  pointer-events: none;
  opacity: 0;
  background: linear-gradient(135deg, rgba(213, 161, 94, 0.18), rgba(64, 94, 126, 0.14));
  mix-blend-mode: soft-light;
}

.heatmap-explorer [data-heatmap-canvas] {
  z-index: 2;
}

.heatmap-explorer[data-heatmap-map-style="color"] [data-heatmap-image] {
  filter: sepia(0.22) saturate(1.14) hue-rotate(346deg) contrast(1.03) brightness(0.94);
}

.heatmap-explorer[data-heatmap-map-style="color"] [data-heatmap-camera]::after {
  opacity: 1;
}

.heatmap-explorer[data-heatmap-map-style="mono"] [data-heatmap-image] {
  filter: grayscale(1) contrast(1.05) brightness(0.94);
}

.heatmap-explorer[data-heatmap-state="static_fallback"] [data-heatmap-map-style-controls],
.heatmap-explorer[data-heatmap-state="context_lost"] [data-heatmap-map-style-controls] {
  display: none;
}

@media (prefers-reduced-motion: reduce) {
  .heatmap-explorer [data-heatmap-image] { transition: none; }
}
```

Do not add any selector that targets `.heatmap-explorer__static img` or `[data-heatmap-canvas]` with `filter`/`mix-blend-mode`.

- [ ] **Step 5: Run JavaScript and static checks GREEN**

```powershell
rtk node scripts/heatmap_js_smoke.js
rtk node --check web/includes/js/heatmap-explorer.js
rtk pytest scripts/replay_baseline/tests/test_web_route_smoke.py -q
rtk git diff --check
```

Expected: all pass. Mutation check: removing the style click binding, accepting an arbitrary style, calling `_loadScene()`, or applying the filter to the canvas must fail at least one behavioral/static contract check.

- [ ] **Step 6: Commit behavior and presentation**

```powershell
rtk git add -- web/includes/js/heatmap-explorer.js web/hlstats.css scripts/heatmap_js_smoke.js
rtk git diff --cached --check
rtk git commit -m "feat(heatmaps): grade explorer map backgrounds"
```

---

### Task 3: Browser Acceptance and Release Evidence

**Files:**
- Modify: `docs/audits/modern-heatmap-explorer/runtime-acceptance.md`
- Modify: `docs/audits/modern-heatmap-explorer/screenshots/map-overview-en.png`
- Modify: `docs/audits/modern-heatmap-explorer/screenshots/player-difference-ru.png`
- Modify: `docs/audits/modern-heatmap-explorer/screenshots/mobile-inspector-ru.png`
- Create: `docs/audits/modern-heatmap-explorer/screenshots/map-overview-mono-en.png`
- Modify: `docs/status.md`
- Modify: `docs/plans.md`
- Modify: `docs/release-readiness.md`
- Modify: `docs/test-plan.md`

**Interfaces:**
- Consumes: committed Task 1 and Task 2 behavior on an exact HEAD.
- Produces: browser evidence that the grade is visual-only, reversible, accessible, responsive, and absent from static fallback; updated release boundary.

- [ ] **Step 1: Run the complete current source verification**

```powershell
rtk python -m pytest scripts/hlstats_py/tests -q
rtk python -m pytest scripts/replay_baseline/tests -q
rtk node --check web/includes/js/heatmap.js
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
rtk python -m pytest scripts/replay_baseline/tests/test_web_route_smoke.py -q
rtk python -m pytest scripts/hlstats_py/tests/test_heatmap_projection_calibrate.py -q
rtk git diff --check
```

Run the PHP smoke/lints in the proven read-only Docker container. Record exact totals and substitutions in the acceptance document.

- [ ] **Step 2: Perform one recoverable runtime activation**

Use the established Task 12 operator sequence: exact backup, preflight, one activation, browser proof, independent readback, and exact restore to `HeatmapExplorerBeta=0`. Do not combine this with GoldSrc assets or projection changes.

- [ ] **Step 3: Capture real browser evidence**

On the same accepted `de_dust2` scene:

- capture default Color map overview;
- switch to Mono without a new scene/API request and capture it;
- switch back to Color and prove reversibility;
- capture player Difference and verify the overlay palette remains unchanged while only the map underneath changes;
- verify keyboard focus and `aria-pressed` for both buttons;
- verify 200% zoom, mobile 44px targets, no horizontal overflow, and reduced-motion behavior;
- force WebGL fallback/context loss and prove the static JPEG is unfiltered and the style controls are not exposed while fallback is active.

The receipt must record the map asset hash, scene URL/request count before and after style changes, root style attribute, pressed states, viewport, screenshot paths, and final restore readback.

- [ ] **Step 4: Update acceptance/release documents**

State the exact boundary:

- current Explorer source and browser runtime accepted on the tested local stack;
- v1/JPEG preserved;
- color grade changes presentation only;
- Steam/GoldSrc assets are not shipped;
- optional GoldSrc import remains a future separately accepted feature;
- no push or external release publication occurred.

- [ ] **Step 5: Independently review the final diff and evidence**

Require a fresh read-only reviewer to inspect the exact diff, screenshots, receipts, keyboard/fallback behavior, and excluded dirty files. Resolve all findings before staging.

- [ ] **Step 6: Commit only the release evidence allowlist**

```powershell
rtk git add -- docs/audits/modern-heatmap-explorer/runtime-acceptance.md docs/audits/modern-heatmap-explorer/screenshots docs/status.md docs/plans.md docs/release-readiness.md docs/test-plan.md
rtk git diff --cached --check
rtk git commit -m "docs(heatmaps): accept explorer background grading"
```

Before committing, inspect `rtk git status --short` and exclude all `docs/audits/legacy-python-parity-20260423/` receipts and `scripts/replay_baseline/artifacts/heatmap-coordinate-acceptance/` artifacts.

---

## Self-review

- Spec coverage: default Color, reversible Mono, background-only filtering, no network/URL/API/data changes, keyboard/ARIA, fallback hiding, reduced motion, runtime screenshots, and GoldSrc exclusion each map to a task above.
- Placeholder scan: no TBD/TODO or unspecified implementation step remains.
- Type/name consistency: markup, JavaScript, CSS, tests, and acceptance use `data-heatmap-map-style`, `data-heatmap-map-style-controls`, `data-heatmap-map-style-option`, and `_setMapStyle(style)` consistently.
- Evidence boundary: source checks, browser runtime, local release-readiness documentation, and non-publication are reported separately.
