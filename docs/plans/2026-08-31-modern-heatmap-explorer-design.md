# Modern Heatmap Explorer Design

**Date:** 2026-08-31  
**Status:** Approved design  
**Product lane:** `hlstatsx-community-edition-python-i18n`

## Result

HLstatsX gets a production-oriented historical Heatmap Explorer for players and
public visitors. It keeps the existing PHP routes, authorization, MySQL event
tables, EN/RU runtime, map assets, and static JPEG URLs, but replaces the
primary interactive renderer with a focused WebGL2 workspace.

The design deliberately stays inside the current Python/PHP/MySQL stack. It
adds no frontend framework, service, queue, tile pyramid, external analytics
store, WebGPU path, full 3D scene, or new AMXX protocol. A derived MySQL grid
read-model is an evidence-gated escalation, not part of the initial design.

## Approved product decisions

- Preserve old URLs, PHP embedding, MySQL authority, and JPEG fallback through
  adapters while allowing a new engine, API contract, and visual design.
- Historical analytics is primary. Live updates are not part of the first
  release, but the query contract must not prevent a later live mode.
- The public player experience is primary; administration exists to maintain
  trustworthy projection, floors, and assets.
- The landing view explains the map as a whole. A player lens adds “me versus
  others” without creating a separate product.
- Use 2.5D floor bands, not a free 3D camera.
- Prefer the current infrastructure. Escalate to a derived MySQL read-model
  only after a measured SLA failure; consider an external store only if that
  read-model also fails.
- Support current WebGL2-capable browsers for the interactive experience.
  Older browsers keep the static JPEG/noscript output, not interactive parity.
- Present the Explorer as a self-contained modern analytics workspace inside
  the existing routes.
- Desktop is the full experience. Mobile is a readable, simplified viewer.
- Release through an opt-in parallel beta with immediate route-level rollback.
- Completion means production/release readiness, not source-only success.

## Current evidence and ownership

The committed product baseline remains the active Python+i18n lane. The
separate `codex/modern-heatmaps-136e5b3` worktree contains useful uncommitted
experiments, but it is not accepted source and must not be merged wholesale.
Implementation may port individually reviewed ideas or tests from it.

The current authoritative flow is:

```text
saved logs / shipped AMXX plugin
              |
              v
Python parser and EventStorage
              |
              v
MySQL Frags / Teamkills / Suicides
              |
              v
PHP heatmap projection and JSON
              |
              v
browser renderer + legacy JPEG output
```

For `cstrike`, the AMXX plugin shipped with HLstatsX already emits attacker and
victim XYZ on kills, headshot information, and suicide position data. The
known losses are downstream: attacker coordinates can be cleared for
headshots, and the public heatmap projection drops Z. The shortest correct path
is to repair those losses rather than add plugin fields.

The shipped DoD/TFC/NS plugins may be extended later only when a replay-backed
coverage report proves that a supported game lacks kill coordinates. Any such
change must copy the existing append-only `attacker_position` and
`victim_position` grammar inside the shipped `.sma`; it must not introduce a
new plugin, transport, JSON log record, `floor_id`, or identity scheme.

## Architecture

The public seam remains `heatmap_points.php`.

- Requests without `v=2` keep the existing contract and renderer.
- Requests with `v=2` return a Heatmap Explorer scene.
- The same v2 endpoint accepts a bounded `inspect` request for one server-issued
  cell identifier.
- `mapinfo` and `playerinfo` continue to host the component through existing
  PHP pages and data attributes.
- The legacy Canvas/JPEG path remains available throughout beta and rollback.

The external conceptual interface has two operations:

```text
query(filters)  -> scene
inspect(cell)   -> bounded details
```

No public class hierarchy or generic query DSL is required. Internally, shared
functions own input validation, event selection, coordinate semantics,
projection, floor assignment, bucketing, response shaping, and cache identity.
The implementation should reuse the current PHP heatmap helpers before
extracting any new module.

### Scene query

The v2 query supports:

- game and map;
- optional public player id;
- exact `from` and `to` timestamps or a supported preset;
- kills, deaths, or both;
- overview, personal, or comparison lens;
- one floor or all floors;
- EN/RU response context.

The response is ordinary versioned JSON:

```text
schemaVersion
query / exact window
map / image / projection identity
floors / active floor
layers: total, me, others
channels: kills, deaths
projected bins
coverage and projection diagnostics
summary metrics
legacy fallback URLs
```

The overview query returns aggregated cells, not duplicated raw-event metadata.
“Others” is derived from compatible total and player aggregates. The server
must never subtract differently filtered windows, floors, channels, or event
semantics.

### Inspect query

The scene issues opaque or strictly validated cell identifiers. Inspect returns
at most 100 matching events for the same scene filters, plus an explicit
`truncated` flag. It supplies player names, weapon, timestamp, event type, and
headshot/teamkill markers only when those fields are public through the current
HLstatsX page permissions.

Arbitrary SQL-like filters, rectangles, field lists, and client-selected sort
expressions are intentionally excluded.

## Event and coordinate contract

- A kill uses attacker XYZ.
- A death uses victim XYZ.
- A teamkill follows the same participant-position rules and keeps an explicit
  event marker.
- Headshot is an attribute and never changes coordinate retention.
- Suicide uses the player’s own position and remains a distinct event type. It
  is not silently mixed into combat-death density.
- A missing victim position remains missing. Attacker position must never be
  copied into the victim channel.
- XY without Z can contribute to the all-floors view but cannot be assigned to
  a specific floor.
- Non-finite, malformed, or out-of-policy coordinates are rejected and counted
  in coverage diagnostics.

The parser precedence remains explicit event properties, then supported inline
metadata, then one-shot staged legacy kill-location data. Staged coordinates
must remain server-scoped and must be consumed or cleared at the event
boundary.

## 2.5D floor model

Floor support is calibration metadata, not inferred silently on every public
request. Add one optional versioned text field to the existing
`hlstats_Heatmap_Config` record. It stores a small validated JSON array:

```json
[
  {
    "id": "lower",
    "label_en": "Lower",
    "label_ru": "Нижний",
    "z_min": -256,
    "z_max": 32,
    "image": null
  }
]
```

Rules:

- identifiers are stable, bounded ASCII tokens;
- localized labels are length-limited and escaped at output;
- Z ranges may not overlap;
- the upper/lower boundary convention is defined once and tested;
- unmatched events are `unassigned`, not guessed;
- an optional floor image uses the existing source-image serving path;
- otherwise every floor uses the common map image and common projection;
- maps without reviewed floor metadata remain valid single-floor maps;
- weak Z coverage or projection quality disables floor-specific public views
  while retaining the all-floors view.

An offline/admin diagnostic may suggest Z bands from actual distributions, but
an operator reviews and saves them. Automatic clustering is not a runtime
dependency.

## Query execution and escalation

The initial implementation reads the existing event tables, applies an exact
time window, participant semantics, floor assignment, projection, and server
bucketing, then returns a bounded number of cells. It may use existing indexes,
a proven new composite index, and the existing file-cache pattern.

It must not return a biased result silently. If the safe row or memory budget
is exceeded, the endpoint returns a visible `too_many_events` state and asks
for a narrower period. Production promotion for a deployment where a common
accepted scenario hits that state requires the evidence-gated read-model.

Escalation ladder:

1. Correct query shape and participant semantics.
2. Existing or measured composite indexes.
3. Versioned file cache and response compression already supported by the web
   deployment.
4. One additive daily MySQL grid table if populated measurements still miss
   the SLA.
5. A separate analytics store only if the daily grid read-model is also proven
   insufficient.

Callers and the v2 response contract do not change when moving to rung 4 or 5.
No abstraction for those future stores is built before the corresponding gate.

## Cache contract

The cache key includes at least:

- schema version;
- game, realgame, and map;
- player/lens and event channel;
- exact start and end timestamps;
- floor id;
- projection and floor-config hashes;
- resolved image identity;
- normalization and bucket-size version.

Only complete successful scenes are cached. Error, rejected, truncated, or
budget-exceeded responses are not cached. Writes use a same-directory temporary
file and atomic rename. Admin changes invalidate affected game/map aliases only
after durable save and readback succeed.

## WebGL2 renderer

WebGL2 is responsible only for presentation:

- upload compact projected bins;
- accumulate and blur density fields;
- apply fixed semantic palettes;
- draw optional contour lines;
- zoom and pan without refetching;
- switch channels, lenses, and already-loaded floor layers;
- pick cells for inspect requests;
- restore GPU resources after context loss or fall back cleanly.

The renderer does not decide coordinate correctness, floor assignment, public
visibility, or event semantics.

WebGPU, deck.gl, React, Vue, a new SPA shell, and a generic visualization plugin
system are excluded. Use native modules and the smallest WebGL2 helper surface
that keeps shader/resource lifecycle testable.

## Visual and interaction design

The Explorer is a scoped analytics workspace, not a restyle of the entire
HLstatsX site.

```text
+------------------------------------------------------------------+
| Map | period | Overview / Me / Difference | Kills / Deaths / Both |
+----------+------------------------------------------+------------+
| Floors   |                                          | Inspector  |
| All      |             WebGL2 map stage             | hotspot    |
| Upper    |                                          | counts     |
| Main     |                                          | weapons    |
| Lower    |                                          | sample     |
+----------+------------------------------------------+------------+
| coverage, exact period, freshness, projection quality             |
+------------------------------------------------------------------+
```

### Visual language

- Dark neutral surfaces separate the Explorer from legacy page chrome without
  forcing a global theme rewrite.
- Kill density uses a warm amber/orange scale; death density uses a cool
  cyan/blue scale. The design never relies on red versus green alone.
- “Me versus others” uses intensity and contours: the population remains
  subdued, while the player layer is high-contrast.
- Difference mode uses one fixed diverging palette and always shows sample
  size; low-sample cells are muted rather than exaggerated.
- Avoid rainbow palettes, 3D extrusions, glow-heavy game aesthetics, raw point
  noise, and arbitrary renderer/normalization controls on public pages.
- Motion is limited to short crossfades and camera easing, disabled by
  `prefers-reduced-motion`.

### Public controls

Keep only controls that answer player questions:

- Overview / Me / Difference;
- Kills / Deaths / Both;
- period presets plus an exact custom range;
- floor selector when supported;
- reset view and shareable state URL.

Hover shows a concise cell summary. Click pins the cell and opens the inspector
with bounded event details, top weapons, and participant counts. Coverage,
truncation, period, and projection quality remain visible outside tooltips.

### Responsive behavior

Desktop is the complete three-region layout. Mobile keeps the map, modes,
period, channels, and floor selector, but moves filters and inspector into
bottom sheets and may omit simultaneous compare panels. It remains usable and
truthful, but desktop/mobile feature parity is not a release requirement.

### Accessibility

- Every control exposes programmatic selected/pressed state.
- Keyboard controls cover mode, channel, floor, reset, zoom, pan, and pinned
  cell navigation.
- A textual summary describes the current scene and updates with filters.
- Status and errors live outside the canvas.
- Focus order does not depend on GPU geometry.
- Required contrast and non-color labels are verified in both EN and RU.
- Static JPEG plus descriptive text remains the noscript fallback.

## Public states and error handling

The component has explicit localized states for loading, empty period,
insufficient sample, missing coordinates, weak projection, floors unavailable,
too many events, API failure, GPU context loss, and static fallback.

It must never clear an error into a blank widget. A v2 failure offers retry and
the v1/JPEG path. Product-safe messages appear publicly; SQL, filesystem,
subprocess, stack, and database details remain server-side.

## Admin calibration

Keep the existing admin route and security boundary. Improve it only as needed
for the new contract:

- map/image selection and upload;
- projection and crop preview;
- actual data coverage and in/out-of-bounds diagnostics;
- Z histogram and suggested floor bands;
- editable EN/RU floor labels and non-overlapping ranges;
- optional per-floor image selection;
- preview of all/floor-specific layers;
- compare-and-save using the config hash;
- cache invalidation after successful readback.

Mutating requests require session CSRF and same-origin validation. Uploads are
type/size/dimension checked, written to same-directory temporary files, and
atomically renamed. The HTTP path must not invoke the Python JPEG generator or
another subprocess. JPEG regeneration remains an explicit CLI/deployment step.

The UI reports human-readable results, not raw JSON or command output.

## Security and privacy

- Validate and bound every public parameter.
- Reuse current public-player visibility rules for inspect details.
- Never expose arbitrary SQL fields or internal ids beyond existing public
  behavior.
- Inspect is rate/size bounded and tied to the scene’s filters.
- Escape all map, floor, player, weapon, and localized text at the relevant
  output boundary.
- Keep cache files and uploaded source assets outside executable paths where
  the current deployment permits; otherwise retain existing deny rules.
- Do not trust forwarded origin headers without an explicit deployment proxy
  configuration.
- Record admin actor, target map, config hash, and success/failure through the
  existing logging facility.

## Performance targets and escalation gate

Measure on a populated disposable contour and a documented reference desktop.
Initial targets:

- warm scene API p95 <= 300 ms;
- cold scene API p95 <= 1.5 s for accepted common windows;
- warm inspect p95 <= 300 ms;
- compressed initial scene <= 400 KiB;
- <= 20,000 visible bins in an initial scene;
- first meaningful render <= 1.5 s on the reference desktop;
- interaction remains responsive during zoom, pan, floor, and channel changes;
- no PHP memory-limit failure and no silent row truncation.

Before adding a composite index, capture cold timing and `EXPLAIN`. Before
adding the daily grid table, prove that correct queries plus allowed indexes
and ordinary caching still miss a target. Before adding an external store,
prove the daily grid table also misses it.

## Observability

Use the existing application/web logging path. Emit one structured line per
scene/inspect request with route version, game/map, window class, player lens,
floor, rows read, bins returned, payload bytes, query/total latency, cache
result, coverage ratios, result state, and fallback reason.

Do not add a metrics service for this feature. Add dashboards or exporters only
if the deployment already has them or production operation proves log-based
diagnosis insufficient.

## Beta, rollback, and compatibility

- Keep v1 and v2 behind one existing-style configuration/feature flag.
- Allow explicit admin/test opt-in before public beta.
- Do not duplicate every production request in shadow mode. Sample comparisons
  only where needed for acceptance.
- Keep existing `heatmap_points.php`, `heatmap_map.php`, PHP page URLs, EN/RU
  route behavior, and `*-kill.jpg` / `*-kill-thumb.jpg` outputs.
- A beta failure switches the mounting path back to v1 without reversing source
  event data or floor metadata.
- Remove old interactive code only after stable v2 release evidence and a
  separate cleanup decision. JPEG compatibility remains.

## Verification and acceptance

### Source gate

- parser and storage regressions for normal kill, headshot, teamkill, suicide,
  missing victim position, malformed/non-finite coordinates, and one-shot
  staged legacy coordinates;
- floor JSON validation and exact boundary assignment;
- projection/crop/rotation invariants;
- API v1 compatibility and v2 contract/cache tests;
- inspect authorization and limit tests;
- WebGL2 shader/resource/context-loss checks at the smallest useful seam;
- JS syntax/smoke, PHP lint/smoke, Python tests/compile, EN/RU key parity, and
  `git diff --check`.

### Populated-data gate

- fresh direct-stdin replay on a disposable contour with a unique evidence id;
- coordinate coverage by game, map, event type, participant, headshot,
  teamkill, suicide, and Z availability;
- at least one accepted multi-floor map, one single-floor map, and one map that
  correctly refuses floor mode;
- exact-window readback and no attacker-to-victim synthesis;
- cold/warm query, payload, memory, cache, inspect, and `EXPLAIN` evidence;
- alias/realgame image and cache invalidation readback.

### Browser gate

- EN and RU desktop flows for map overview and player comparison;
- simplified mobile flows;
- period, channel, floor, overview/me/difference, hover, pin, inspect, reset,
  shareable URL, empty/error/weak-projection states;
- keyboard and reduced-motion behavior;
- clean console/network and WebGL context-loss fallback;
- current static JPEG/noscript route.

### Admin and release gate

- preview, floor suggestion/edit, save, conflicting-save rejection, upload,
  invalidation, and failure readback;
- beta opt-in, sampled v1/v2 comparison, rollback, and re-enable;
- CLI JPEG/thumb regeneration and compatibility URLs;
- current documentation reconciled to distinguish historical rotate/crop
  migration evidence from the new Explorer’s acceptance.

`SOURCE-READY` means the source gate is green. `RUNTIME-ACCEPTED` requires the
populated-data, PHP/container, browser, admin, fallback, and rollback gates.
`RELEASE-READY` additionally requires the documented performance targets,
operational logging, migration/upgrade coverage, and final release review.

## Non-goals

- live match streaming;
- full 3D/BSP rendering;
- player movement trajectories;
- WebGPU;
- SPA or frontend framework adoption;
- a new AMXX plugin or log protocol;
- generic analytics/query DSL;
- precomputed tile service;
- external analytics storage without evidence;
- automatic publication of guessed floor definitions;
- removal of JPEG compatibility.

