# Modern Heatmap Explorer runtime acceptance

Status on 2026-09-01: `BLOCKED`

## Background-grading Task 3 readback (exact HEAD `735bda5`)

This is a partial, restored browser pass for the `Color / Mono` presentation
slice only. It does not change the Task 12 status below: the broader Explorer
and release remain blocked.

- Source boundary: with the documented
  `PYTHONPATH=scripts;scripts/replay_baseline`, the full Python suite passed
  (`302 passed`); JavaScript syntax/smoke, PHP read-only-container smoke/lint,
  replay-route (`13 passed`), projection (`6 passed`), and replay (`91 passed`)
  also passed. The earlier `286 passed, 16 failed` invocation omitted that
  required path and is retained only as invalid-environment diagnostic evidence.
- Runtime rows for Color/Mono, keyboard/ARIA, one unchanged v2 request and
  URL, reduced motion, and WebGL-unavailable static fallback pass at their
  captured desktop/browser seam. The old mobile/200% claims are invalidated:
  Chromium used a `980px` layout viewport at nominal `390x844`
  (`visualScale=0.397959`), and the old 200% row used page scale rather than a
  reflow viewport.
- Fix round 1 adds the standard viewport contract in `web/pages/header.php`,
  guarded by a RED/GREEN PHP smoke source contract, and repeats the corrected
  browser proof. True touch mobile is `clientWidth=390`, `innerWidth=393`,
  `scrollWidth=393`, DPR `3`, and visual scale `1`: it is one-column with the
  inspector mobile sheet open and all 19 visible targets at least `44x44` CSS
  px. The three-pixel inner/client difference is the scrollbar boundary, so
  `scrollWidth <= innerWidth` establishes no horizontal overflow. The 2x
  reflow proxy is `innerWidth=720`, `clientWidth=scrollWidth=705`, DPR `2`,
  one-column, usable controls, no horizontal overflow, and `0s` reduced-motion
  transition; no page-scale factor was used.
- Canonical screenshots were replaced from the evidence passes:
  `map-overview-en.png` (`1139x935`), `map-overview-mono-en.png`
  (`1139x935`), `player-difference-ru.png` (`1197x1010`), and
  `mobile-inspector-ru.png` (`936x5460`, SHA-256
  `eba4515c55854c7e2e6c2838deadf9f5f25a8318b59af036666e2e3a1d8b684c`).
- The committed JavaScript smoke deterministically covers the no-browser-fetch
  branch; the failed route-abort experiment is not a substitute for that branch
  and is not a product failure. The first active browser pass visually exercised
  the Russian Difference scene. Its exact invariant is accepted at the bounded
  seam: CSS targets only `[data-heatmap-image]` and the camera pseudo-layer
  below the canvas, while the style click does not call renderer, fetch, or URL
  paths. The later mode-only isolation attempt used the restored `1.26`
  baseline and could not reach a loaded Difference scene; no third activation
  or config mutation was run. This is an evidence-boundary residual, not a
  release blocker for the presentation-only grade.
- Receipts: `.superpowers/sdd/2026-09-01-heatmap-background-grading/`
  `task3-preflight-20260901T192353Z.json`,
  `task3-browser-20260901T192353Z.json`, and
  `task3-restore-20260901T192353Z.json`. Restore readback is exact for
  `HeatmapExplorerBeta=0`, config, asset/JPEG/thumb hashes, temporary users,
  fixture rows, `AUTO_INCREMENT`, sessions, and mounts.
- Fix round 1 source preflight/restore before a transient Docker Hub TLS
  timeout is preserved as `task3-preflight-20260901T204454Z.json` /
  `task3-restore-20260901T204454Z.json` (`exact: true`). The serialized
  accepted browser pair is `task3-preflight-20260901T204537Z.json` /
  `task3-browser-20260901T204537Z.json` /
  `task3-restore-20260901T204537Z.json`, normalized by
  `task3-fix-round1-browser-acceptance-20260901T204537Z.json`; its baseline
  and restore have `sessions=[]` and `exact: true`.
- No Steam/Valve/GoldSrc asset was copied; v1/JPEG remain preserved. No push or
  external publication occurred.
- The grading source line is `40b8f58` / `bf2af84` runtime hardening followed
  by `de5b836`, `7366b07`, `0b6a875`, and viewport remediation `735bda5`.

This Task 12 pass did not reach `RUNTIME-ACCEPTED` or `RELEASE-READY`.
Implementation, schema, and harness source stayed frozen at
`93f8a5cd7a75134486c1cd45afa2b979fb2cc39e`. Product-tree writes in this pass
were limited to this report, the screenshot directory, and the canonical
status/plan/release/test documents.

## Evidence boundary

- Worktree: `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer`
- Live web root: `http://127.0.0.1:8281`
- Runtime mode readback at end of pass: `HeatmapExplorerBeta=0`
- Evidence helpers and raw operator notes:
  `.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-12-evidence/`

## Focused coordinate runner

Required command:

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-HeatmapCoordinateAcceptance.ps1 `
  -EvidenceLabel heatmap-coordinate-contract
```

Result: `BLOCKED`, no passing persisted-row receipt.

Recovered disposable-state evidence before cleanup:

- `.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-12-evidence/bench-ephemeral-stale-backup-20260901T024314Z/`

Task-12-only helper evidence:

- `.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-12-evidence/Invoke-Task12CoordinateAcceptance.ps1`
- `.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-12-evidence/Diagnose-Task12CoordinateAcceptance.ps1`
- `.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-12-evidence/docker.cmd`

Fresh diagnostic facts from the frozen harness:

- restore step: `RESTORE_EXIT=0`
- import step: `IMPORT_EXIT=0`
- restored disposable counts: `hlstats_Events_Frags=4`, `hlstats_Events_Suicides=1`
- terminal blocker: `ERROR 1054 (42S22): Unknown column 'uniqueId' in 'SELECT'`

The frozen runner expects `hlstats_Players.uniqueId`, but the restored
disposable baseline schema in this pass did not contain that column. Because
the required persisted-row receipt never materialized, the coordinate gate
remains open and the feature cannot be labeled `RUNTIME-ACCEPTED`.

## SQL truth on the populated live stack

Direct SQL on the running populated Python DB established that current empty
and weak-projection surfaces are not caused by missing live coordinates.

| Check | Result |
| --- | --- |
| `de_dust2` frag rows | `549` |
| `de_dust2` frag rows with killer XY | `549` |
| `de_dust2` suicides with XY | `10` |
| `de_dust2` headshots | `222` |
| `de_dust2` teamkills | `2` |
| Player `162` kills on `de_dust2` | `15` |
| Player `162` deaths on `de_dust2` with victim XY | `12` |
| Configured floor rows (`floors_json <> ''`) | `0` |
| `de_dust2` event time span | `1704138767 .. 1767388184` |
| Current runtime clock during check | `1788231754` |

Interpretation:

- the default 30-day `de_dust2` Explorer scene was empty because the selected
  rolling window had no matching recent rows, not because coordinates were
  absent;
- the 365-day `de_dust2` scene had rows and coordinates, but current
  projection quality remained too weak for accepted rendering.

## Runtime scene and fallback evidence

Browser/runtime report:

- `.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-12-evidence/capture-task12-screens-report.json`

Direct v2 scene results captured on 2026-09-01:

| Route | Result |
| --- | --- |
| `heatmap_points.php?v=2&game=cstrike&map=de_dust2&range=30d&event=both&lens=overview&floor=all&lang=en` | `200`, `state=empty`, `rowsRead=0`, `rawBytes=1285` |
| `heatmap_points.php?v=2&game=cstrike&map=de_dust2&range=365d&event=both&lens=overview&floor=all&lang=en` | `200`, `state=weak_projection`, `rowsRead=175`, `candidate=350`, `excludedSuicides=10`, `inBounds=30`, `outOfBounds=320`, `projectionCoverage=0.08571428571428572`, `rawBytes=1556` |
| Same direct v2 route after final rollback to mode `0` | `404`, `{"schemaVersion":2,"state":"explorer_disabled"}` |

Observed browser/runtime facts from the same report:

- Browser: `Chromium 147.0.7727.15`
- Desktop viewport: `1440x1000`
- Mobile viewport: `390x844`
- Desktop WebGL: `WebGL 2.0 (OpenGL ES 3.0 Chromium)`
- GPU renderer exposed to the browser: `ANGLE (... SwiftShader Device (Subzero) ...)`
- `heatmap-explorer-ready` detail events captured: none (`[]`) for the map,
  player, or mobile surfaces exercised in this pass

Because no `heatmap-explorer-ready` event was emitted on the live browser
surfaces exercised here, Task 12 did not produce an accepted
`durationMs`/FMR receipt.

## Compatibility JPEG evidence

Public compatibility links remained live:

- `http://127.0.0.1:8281/hlstatsimg/games/cstrike/heatmaps/de_dust2-kill.jpg`
  -> `200 OK`, `Content-Length: 227405`
- `http://127.0.0.1:8281/hlstatsimg/games/cstrike/heatmaps/de_dust2-kill-thumb.jpg`
  -> `200 OK`, `Content-Length: 16387`

The compatibility JPEG remains the legacy rolling snapshot. On the live page
it was labeled as `Last 28 Days`; it must not be described as parity with any
Explorer-selected period.

This pass verified public reachability and visual presence, but did not claim a
fresh accepted JPEG regeneration receipt because Task 12 kept product asset
writes frozen outside the permitted documentation/screenshot targets.

## Browser evidence

Required exact-name screenshots captured under
`docs/audits/modern-heatmap-explorer/screenshots/`:

- `map-overview-en.png`
- `player-difference-ru.png`
- `mobile-inspector-ru.png`
- `fallback-jpeg-en.png`

Additional timestamped screenshots from the same pass are preserved in the
same directory.

Observed route behavior:

- mode `0`: plain `mode=mapinfo` served the legacy Canvas/JPEG surface and the
  direct v2 route was disabled;
- mode `1`: plain `mode=mapinfo` stayed legacy, while explicit
  `heatmap_explorer=1` mounted the Explorer surface;
- mode `2`: plain `mode=mapinfo` mounted Explorer, while explicit
  `heatmap_legacy=1` returned the same page to legacy;
- switching mode `2 -> 0` returned the next page request to v1 without schema
  reversal or asset-link loss.

Confirmed browser blockers on the live surface:

1. `empty` and `weak_projection` both rendered the same generic
   `The Explorer data could not be loaded.` alert instead of specialized
   localized state handling.
2. The server can emit `missing_coordinates`, `floors_unavailable`,
   `weak_projection`, and `too_many_events`, but the client accepts only
   `ok`, `empty`, and `insufficient_sample`.
3. The visible period control offered only `Last 7/30/90/365 days`; there was
   no visible custom-period control.
4. Clicking `Use the static fallback` did not switch the view back to v1; the
   alert remained on the Explorer surface.
5. `web/includes/js/heatmap-explorer.js` still hard-codes `pointerPan: false`,
   and the current live browser pass did not produce a healthy accepted scene
   that could override that source-backed blocker.
6. No current populated config row exposed `floors_json`, so
   `floors_unavailable` could not be proven through a legitimate live floor
   configuration in this pass.
7. An API-reachable `insufficient_sample` state exists on current data
   (`de_train`, player `174`, `range=365d`, `event=kills`, `lens=difference`),
   but the normal browser/player flow exercised in this pass did not surface an
   accepted specialized player Explorer scene.

The captured `player-difference-ru.png` and `mobile-inspector-ru.png` are real
browser artifacts, but they document blocked player-surface behavior rather
than accepted difference/inspect completion.

## Accessibility and GPU failure checks

This pass confirmed WebGL2 availability on the reference browser surface, but
Task 12 did not complete accepted evidence for:

- keyboard-only lens/channel/floor/zoom/pan/pin navigation;
- 44px mobile target audit and 200% zoom;
- reduced-motion behavior;
- forced `WEBGL_lose_context` loss/restore;
- WebGL2-disabled browser fallback;
- JavaScript-disabled fallback.

These rows remain open because the current browser surface did not reach a
stable accepted Explorer interaction path.

## Admin acceptance and rollback safety

Authenticated admin acceptance remains `BLOCKED`.

- The live admin route existed, but this pass did not have a validated local
  admin password.
- No admin credential reset was performed.
- No authenticated upload/save/concurrency/cache-invalidation matrix was
  executed.
- Final mode readback was restored to `HeatmapExplorerBeta=0`.

## Final verdict

Task 12 on 2026-09-01 is `BLOCKED`, not `RUNTIME-ACCEPTED`, and not
`RELEASE-READY`.

Open required evidence rows:

- passing focused coordinate-runner persisted-row receipt;
- accepted scene-vs-SQL/inspect/floor matrix;
- accepted player difference/mobile inspector browser flow;
- accepted special-state localization and fallback-to-v1 behavior;
- accepted custom-period control;
- accepted pointer/touch pan behavior;
- accepted accessibility/GPU/JS-disabled matrix;
- accepted authenticated admin backup/mutate/restore matrix;
- accepted `heatmap-explorer-ready.detail.durationMs` / FMR receipt.
