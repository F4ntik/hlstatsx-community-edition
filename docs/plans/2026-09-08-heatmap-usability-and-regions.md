# Heatmap usability, spatial floors and calibration

Date: 2026-09-08. User approved improvements 1, 3, 4, 5 and 6 from the
follow-up review. Item 2 (BSP revision persistence/enforcement) is explicitly
excluded. This plan extends the September 7 local changes, not a clean HEAD.

## Scope and architecture

Keep PHP/MySQL, Python offline tooling and WebGL. Preserve the original data
and default projection semantics. Add optional spatial floor regions and
presentation constraints rather than a 3D engine. Retain existing authenticated
calibration preview/save validation. No BSP identity registry, automatic revision
invalidation, new online service, production deployment or unrelated cleanup.

Following the user's clarification, root implements and reviews all changes.
The previously dispatched agents were stopped before implementation; no further
delegation was used. Existing AGENTS.md changes and prior receipts remain.

## Implementation sequence

- [x] UI and scale: replace epoch editing with normal date/time controls while
  retaining epoch URL/API representation; collapse diagnostics; distinguish
  legacy page counts from heatmap events; add numerical legend and optional
  reference-scale lock that resets for incompatible metrics/frames.
  Owners/files: web/includes/js/heatmap-explorer.js, web/includes/heatmap_points.php,
  web/pages/mapinfo.php, web/hlstats.css, web/lang/{en,ru}.php.
- [x] Spatial floor contract: extend existing optional floor JSON with bounded
  polygon regions and optional same-frame floor image. Keep old height-only
  definitions compatible. Apply identical membership to density, points and
  inspection. Validate coordinates, polygons and asset paths server-side.
  Owners/files: web/includes/heatmap_points.php, web/heatmap_points.php,
  web/includes/js/heatmap-explorer.js, scripts/hlstats_py/heatmaps.py where used.
- [x] Constrained presentation: use configured spatial regions to limit rendered
  density and smoothing. Do not present raw BSP surface outlines as a navigation
  mesh. No configured geometry means existing unconstrained behavior with honest
  explanation. Raw cells/counts must not be altered by presentation smoothing.
- [x] Calibration workflow: import existing local registration JSON as candidate
  settings, show derived geometry overlay when supplied, and select image
  landmarks by clicking. Keep independent control landmarks and authenticated
  preview/save checks; a report import is not an automatic approval or DB write.
  Owners/files: web/pages/admintasks/heatmaps.php, web/includes/js/heatmap.js,
  web/heatmap_admin.php as required, web/lang/{en,ru}.php, web/hlstats.css.
- [x] Focused acceptance: JS/PHP regression checks for time conversion, scale
  compatibility, region membership, mask behavior, floor assets and report
  parsing; Python checks only for touched Python behavior. Inspect real desktop
  and narrow-screen views and a disposable spatial-floor example. Root reviews
  the final diff per the user's no-subagent direction. No full replay required.
- [x] Finalize guide/status and screenshots with an explicit local-runtime
  boundary, remaining per-map configuration needs and point-2 exclusion.

Evidence: `docs/audits/modern-heatmap-explorer/improvements-20260908/README.md`.
Guide: `docs/heatmap-regions-and-scale.md`.

## Acceptance details

Period changes while a compatible reference scale is locked retain the same
color denominator. A channel/metric/image-frame change releases an incompatible
lock. UTC input round-trips exactly including seconds; invalid ranges do not
replace the last successful scene. Public floor geometry uses projected image
coordinates, not private event XYZ. An optional floor image must be a vetted
local asset in the same projection frame. Polygon membership agrees between
server aggregation and displayed masks, including boundaries and overlaps.

Admin imports are size/type bounded and cannot execute HTML/SVG scripts. They
populate a candidate only, never bypass the existing evidence or authentication.
The original runtime on 8281 remains unchanged. Lab 8382 may be refreshed and
given reversible fixtures, with prior lab settings restored after fixture QA.
