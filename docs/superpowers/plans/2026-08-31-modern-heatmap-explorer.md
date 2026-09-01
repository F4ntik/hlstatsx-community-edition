# Modern Heatmap Explorer Implementation Plan

> **For Codex:** execute this plan with `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Keep one integration owner, assign disjoint
> file groups, and run each task's focused gate before starting its dependent
> task.

**Goal:** Ship a production-ready historical Heatmap Explorer with correct
attacker/victim XYZ semantics, reviewed 2.5D floors, a compact PHP/MySQL v2
scene API, a native WebGL2 renderer, an accessible EN/RU workspace, a hardened
admin calibration flow, static JPEG compatibility, and an instant v1 rollback.

**Architecture:** Keep the existing `proxy_daemon_py -> hlstats_py -> MySQL ->
PHP` product path. `web/heatmap_points.php` remains the public seam: requests
without `v=2` retain v1, while `v=2` exposes one bounded scene operation and one
bounded cell-inspect operation. PHP validates, filters, projects, floor-assigns,
and buckets existing event rows into a maximum 128 x 128 grid; WebGL2 renders
that compact grid and never decides data semantics. The existing pages, map
assets, static JPEG URLs, and Canvas/JPEG fallback remain available throughout
rollout.

**Tech Stack:** Python 3.10, pytest, PHP 8.2-compatible procedural helpers,
MariaDB 10.11/MySQL, native JavaScript, WebGL2, CSS, Node smoke tests, existing
Docker replay contours, existing EN/RU dictionary runtime.

**Spec:**
[`docs/plans/2026-08-31-modern-heatmap-explorer-design.md`](../../plans/2026-08-31-modern-heatmap-explorer-design.md)

**Global Constraints:**

- Implement only in `hlstatsx-community-edition-python-i18n/`. The two sibling
  repositories are read-only parity/i18n references.
- Start implementation from committed design baseline `210f88d`. Do not merge
  the dirty `codex/modern-heatmaps-136e5b3` worktree wholesale. Port a hunk only
  after reviewing it against this plan and its task tests.
- Use the shipped HLstatsX AMXX sources as the protocol authority. Do not add a
  plugin, transport, identity, `floor_id`, or JSON event protocol.
- The shipped Counter-Strike plugin already emits `attacker_position`,
  `victim_position`, and suicide position. No AMXX edit is planned. Changes to
  DoD/TFC/NS `.sma` files require a real replay fixture that proves a missing
  coordinate on a supported release game.
- Add no frontend framework, deck.gl, WebGPU path, service, queue, metrics
  system, tile pyramid, generic data-source abstraction, or external store.
- Add no daily grid table in this plan. If correct queries, a measured index,
  and ordinary cache still miss the release SLA, stop promotion and write a
  separate read-model design with the captured evidence.
- Use the common validated map image for every floor in the initial release.
  `floors_json` stores only id, EN/RU labels, and Z bounds. Do not extend the
  public image route or add per-floor asset variants unless operator evidence
  first proves that the common projection is insufficient.
- Never synthesize a victim coordinate from an attacker coordinate. XY without
  Z is valid only for the all-floors view. A headshot never changes coordinate
  retention. Suicide is stored with the player's own position, preferring
  `victim_position` and then `attacker_position` because the shipped SourceMod
  and AMXX emitters use different property names. Suicides stay excluded from
  combat-density layers.
- Every Explorer event window is half-open UTC `[from, to)`. Every floor band
  is half-open `[z_min, z_max)`. These boundary rules are shared by scene and
  inspect queries. The compatibility JPEG remains an independent legacy
  rolling snapshot for the configured number of days; it is not period-parity
  for an Explorer selection and must be labelled as such.
- Preserve unrelated dirty work. Stage exact paths for every commit and run
  `rtk git diff --check` before committing.
- Use `rtk` for every local command in this workspace.
- Acceptance labels are strict: unit/lint success is `SOURCE-READY`; populated
  DB, browser, admin, fallback, and rollback evidence is `RUNTIME-ACCEPTED`;
  only the complete performance and operations gate is `RELEASE-READY`.

## Execution prerequisite

Create a fresh worktree instead of reusing the dirty heatmap experiment:

```powershell
rtk git worktree add `
  ..\hlstatsx-community-edition-python-i18n-heatmap-explorer `
  -b feature/modern-heatmap-explorer `
  HEAD
```

Run all remaining commands from that new worktree. Confirm the boundary:

```powershell
rtk git status --short --branch
rtk git rev-parse HEAD
rtk git merge-base --is-ancestor 210f88d HEAD
```

Expected: a clean `feature/modern-heatmap-explorer` worktree containing this
plan, with approved design commit `210f88d` in its ancestry.

## Stable public contracts

The v2 scene request accepts only:

```text
v=2
game=<bounded token>
map=<bounded token>
player=<positive public player id, optional>
range=7d|30d|90d|365d
from=<unix UTC seconds>&to=<unix UTC seconds>  # alternative to range
event=kills|deaths|both
lens=overview|me|difference
floor=all|<configured floor id>
lang=en|ru
inspect=c<grid-x>.<grid-y>                 # optional inspect operation
```

Rules:

- `range` and `from`/`to` are mutually exclusive.
- Custom windows are at most 3650 days and end no more than 300 seconds in the
  future.
- `me` and `difference` require `player > 0`.
- `difference` accepts exactly one channel (`kills` or `deaths`); `both` is
  rejected as `difference_channel_required` rather than combining two
  incomparable deltas.
- `inspect` reuses every scene filter and accepts only a cell id issued by the
  matching scene grid.
- There is no client-selected SQL field, sort, rectangle, bucket size, limit,
  renderer, or normalization expression.

The scene response uses this compact shape:

```json
{
  "schemaVersion": 2,
  "state": "ok",
  "query": {
    "game": "cstrike",
    "map": "de_dust2",
    "player": 0,
    "from": 1785456000,
    "to": 1788048000,
    "event": "both",
    "lens": "overview",
    "floor": "all",
    "lang": "en"
  },
  "map": {
    "game": "cstrike",
    "realgame": "cstrike",
    "name": "de_dust2",
    "image": {"url": "./hlstatsimg/games/cstrike/maps/de_dust2.jpg", "width": 1024, "height": 768},
    "projectionHash": "a4dd45e46d84a12f",
    "floorConfigHash": "97d170e1550eee4a"
  },
  "floors": [],
  "activeFloor": "all",
  "grid": {
    "bucketSize": 8,
    "width": 128,
    "height": 96,
    "fields": ["cell", "x", "y", "kills", "deaths"]
  },
  "layers": {"total": [], "me": [], "others": []},
  "comparison": {
    "fields": ["cell", "x", "y", "killDelta", "deathDelta", "sample"],
    "bins": []
  },
  "coverage": {},
  "summary": {},
  "warnings": [],
  "fallback": {
    "v1": "heatmap_points.php?game=cstrike&map=de_dust2",
    "jpeg": "./hlstatsimg/games/cstrike/heatmaps/de_dust2-kill.jpg",
    "thumbnail": "./hlstatsimg/games/cstrike/heatmaps/de_dust2-kill-thumb.jpg"
  }
}
```

Each layer row is `[cellId, gridX, gridY, kills, deaths]`. `others` is produced
server-side from compatible `total - me` aggregates. For each channel,
`comparison` uses:

```text
me_share     = cell_me / max(1, all_me)
others_share = cell_others / max(1, all_others)
delta        = me_share - others_share
sample       = cell_me + cell_others
```

The renderer may scale the displayed delta to the visible maximum, but it must
show raw counts and mute comparison cells with fewer than three personal
events. It must not invent statistical significance.

Inspect is a second request, not a scene/inspect union. Its canonical response
is:

```json
{
  "schemaVersion": 2,
  "operation": "inspect",
  "state": "ok",
  "query": {
    "game": "cstrike",
    "map": "de_dust2",
    "player": 42,
    "from": 1785456000,
    "to": 1788048000,
    "event": "kills",
    "lens": "me",
    "floor": "main",
    "lang": "ru"
  },
  "cell": {
    "id": "c7.11",
    "gridX": 7,
    "gridY": 11,
    "projectedBounds": {"xMin": 56, "xMax": 64, "yMin": 88, "yMax": 96}
  },
  "rows": [
    {
      "eventTime": "2026-08-29T17:12:31Z",
      "event": "kill",
      "killer": {"id": 42, "name": "Alpha"},
      "victim": {"id": 84, "name": "Beta"},
      "weapon": "ak47",
      "headshot": true,
      "teamkill": false
    }
  ],
  "aggregates": {
    "scope": "returned_rows",
    "sampleRows": 1,
    "topWeapons": [{"weapon": "ak47", "count": 1}],
    "participantCounts": {"unique": 2, "killers": 1, "victims": 1}
  },
  "truncated": false,
  "warnings": []
}
```

`rows` and `aggregates` describe the same sanitized returned sample, capped at
100 rows. `topWeapons` contains at most five entries and is sorted by count
descending, then weapon token. `participantCounts` counts distinct positive
public player IDs in the returned sample; hidden or missing identities remain
the public ID `0` and are not counted. If `truncated` is true, these aggregates
remain sample-scoped and must not be presented as exact full-cell totals.

The response never returns raw world coordinates, Steam ids, SQL ids outside
existing public player ids, or a replacement scene.

## Task 1: Make coordinate semantics authoritative in the Python runtime

**Files:**

- Modify: `scripts/hlstats_py/protocol.py`
- Modify: `scripts/hlstats_py/runtime.py`
- Modify: `scripts/hlstats_py/storage.py`
- Modify: `scripts/hlstats_py/heatmaps.py`
- Modify: `scripts/hlstats_py/tests/test_protocol.py`
- Modify: `scripts/hlstats_py/tests/test_runtime.py`
- Modify: `scripts/hlstats_py/tests/test_storage.py`
- Modify: `scripts/hlstats_py/tests/test_heatmaps.py`

### Step 1: Add failing parser and storage regressions

Add fixtures copied from the shipped Counter-Strike grammar:

```python
def test_parse_shipped_cstrike_kill_positions() -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot) '
        '(attacker_position "1 2 3") (victim_position "4 5 6")'
    )
    assert event.properties["attacker_position"] == "1 2 3"
    assert event.properties["victim_position"] == "4 5 6"
    assert event.properties["headshot"] is True
```

Add these named tests:

- `test_parse_inline_setpos_exact_kill_positions`
- `test_runtime_killlocation_is_server_scoped_and_one_shot`
- `test_runtime_inline_positions_override_staged_killlocation`
- `test_runtime_source_boundary_clears_staged_killlocation`
- rename `test_record_headshot_frag_matches_legacy_attacker_position_behavior`
  to `test_record_headshot_frag_preserves_attacker_and_victim_positions` and
  assert all six coordinate values are persisted;
- `test_record_suicide_prefers_victim_position_then_attacker_position`, with
  one SourceMod-form event and one shipped AMXX-form event;
- `test_record_frag_rejects_malformed_and_out_of_mediumint_positions`.
- `test_draw_hud_labels_the_configured_legacy_rolling_days`.

Run the RED gate:

```powershell
$env:PYTHONPATH='scripts'
rtk python -m pytest `
  scripts/hlstats_py/tests/test_protocol.py `
  scripts/hlstats_py/tests/test_runtime.py `
  scripts/hlstats_py/tests/test_storage.py `
  -k "position or killlocation or setpos_exact or headshot or suicide or teamkill or hud" `
  -q
```

Expected: new runtime/staging tests fail; the renamed headshot test shows the
current `(None, None, None)` attacker position defect.

### Step 2: Normalize supported coordinate inputs without changing protocol

In `protocol.py`, keep event properties as the public event representation and
add only private parsing helpers:

```text
Position = tuple[int, int, int]
_parse_position_triplet(value: object) -> Position | None
_extract_inline_kill_positions(body: str) -> tuple[Position | None, Position | None]
```

Precedence for a kill is:

1. `attacker_position` / `victim_position` properties;
2. legacy `killerpos` / `victimpos` properties;
3. supported `setpos_exact x y z` or `[x y z]` inline metadata;
4. one-shot staged `World triggered "killlocation"` data.

Normalize accepted triplets to a single space-separated integer string in the
event properties. Reject NaN, infinity, extra components, decimals outside the
database integer representation, and values outside signed MEDIUMINT bounds.

### Step 3: Add one server-scoped staging slot

Extend `RuntimeMapState` with two optional triplets, not a generic event cache:

```python
pending_kill_attacker: tuple[int, int, int] | None = None
pending_kill_victim: tuple[int, int, int] | None = None
```

When a world event named `killlocation` arrives, stage its validated
`attacker_position` and `victim_position`. On the next kill for that same
server, fill only missing inline properties, dispatch the kill, and clear both
slots in a `finally` block. Also clear both slots on map lifecycle and exact
`Log file started` boundaries. Never carry staged coordinates to another
server or another kill.

### Step 4: Fix persistence semantics

In `_record_frag`:

- remove the headshot branch that clears `attacker_position`;
- resolve aliases through one small private helper;
- keep attacker and victim positions separate for frags and teamkills;
- resolve a suicide's own position from `victim_position` first and
  `attacker_position` second, covering the shipped SourceMod and AMXX emitters;
- keep missing triplets as three SQL NULL values.

Do not alter scoring, streak, role, weapon, or player-resolution behavior.

### Step 5: Make the legacy JPEG period label truthful

Keep the JPEG generator's existing configured-day rolling snapshot and cache
behavior; do not make it depend on Explorer URL state. Replace the hard-coded
30-day HUD range in `draw_hud` with `config.days`, and label the image as a
legacy rolling snapshot. Acceptance regenerates with `--disablecache` so the
visual fallback check never treats an incremental overlay as exact Explorer
period evidence.

### Step 6: Run the GREEN and full Python gates

```powershell
$env:PYTHONPATH='scripts'
rtk python -m pytest `
  scripts/hlstats_py/tests/test_protocol.py `
  scripts/hlstats_py/tests/test_runtime.py `
  scripts/hlstats_py/tests/test_storage.py `
  scripts/hlstats_py/tests/test_heatmaps.py `
  -k "position or killlocation or setpos_exact or headshot or suicide or teamkill" `
  -q
rtk python -m pytest scripts/hlstats_py/tests -q
rtk python -m compileall -q scripts/hlstats_py
rtk git diff --check
```

Expected: focused and full suites pass. Inspect the SQL assertions to confirm a
headshot retains both triplets, both supported suicide property forms retain
the player's own triplet, and the JPEG HUD uses the configured rolling days.

### Step 7: Commit

```powershell
rtk git add `
  scripts/hlstats_py/protocol.py `
  scripts/hlstats_py/runtime.py `
  scripts/hlstats_py/storage.py `
  scripts/hlstats_py/heatmaps.py `
  scripts/hlstats_py/tests/test_protocol.py `
  scripts/hlstats_py/tests/test_runtime.py `
  scripts/hlstats_py/tests/test_storage.py `
  scripts/hlstats_py/tests/test_heatmaps.py
rtk git commit -m "fix(heatmaps): preserve authoritative event coordinates"
```

## Task 2: Add a safe schema bridge, floor metadata, and one rollout flag

**Files:**

- Modify: `sql/install.sql`
- Create: `web/updater/80.php`
- Create: `web/updater/81.php`
- Modify: `scripts/web_heatmap_smoke.php`

### Step 1: Add failing schema assertions

Extend `scripts/web_heatmap_smoke.php` to read the three schema files and
assert:

- fresh installs set `@DBVERSION="81"`;
- fresh `hlstats_Heatmap_Config` has nullable `floors_json TEXT` and uses
  InnoDB;
- fresh options contain `HeatmapExplorerBeta=0`;
- `80.php` advances only version state to dbversion 80;
- `81.php` checks before adding `floors_json`, converts only the small config
  table to InnoDB, inserts the option/choices idempotently, and updates
  dbversion only after all schema/data statements.

Run:

```powershell
rtk php scripts/web_heatmap_smoke.php
```

Expected: failure because updater 80/81 and the fresh-install fields do not
exist.

### Step 2: Restore updater continuity at version 80

`install.sql` has historically used dbversion 80 for the utf8mb4 fresh-install
baseline while the numbered updater stops at 79. Add `web/updater/80.php` as a
schema no-op that sets version `1.7.0` and dbversion `80`. Do not retrofit the
old fresh-install-only charset conversion.

Follow the updater guard used by existing files:

```php
if (!defined('IN_UPDATER')) {
    die('Do not access this file directly.');
}
```

### Step 3: Add dbversion 81

In `sql/install.sql`:

- set `@DBVERSION="81"`;
- define `floors_json TEXT NULL` after `cropy2`;
- change only `hlstats_Heatmap_Config` to `ENGINE=InnoDB`;
- add `HeatmapExplorerBeta` with value `0` and option type `2`;
- add three choices: `0=Off`, `1=Opt-in`, `2=Default`, with `0` default.

In `web/updater/81.php`, use existing `$db` methods and this order:

1. `SHOW COLUMNS FROM hlstats_Heatmap_Config LIKE 'floors_json'`; add the
   column only when absent.
2. `SHOW TABLE STATUS LIKE 'hlstats_Heatmap_Config'`; convert only when the
   engine is not InnoDB.
3. `INSERT IGNORE` the flag and its three choices.
4. Set product version `1.7.0`.
5. Set dbversion `81` last.

This order makes a partially completed migration safely repeatable and avoids
reporting dbversion 81 when a preceding statement failed.

### Step 4: Run schema smoke and lint

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/updater/80.php
rtk php -l web/updater/81.php
rtk git diff --check
```

Expected: smoke passes and both updater files report no syntax errors.

### Step 5: Commit

```powershell
rtk git add sql/install.sql web/updater/80.php web/updater/81.php scripts/web_heatmap_smoke.php
rtk git commit -m "feat(heatmaps): add floor metadata and beta migration"
```

## Task 3: Define and validate the v2 query and floor contracts

**Files:**

- Modify: `web/includes/heatmap_points.php`
- Modify: `scripts/web_heatmap_smoke.php`

### Step 1: Add failing pure-function tests

Add table-driven tests for:

- the four period presets, deterministic `now` injection, and a 15-minute UTC
  aligned preset end (`intdiv($now, 900) * 900`) so repeated historical
  requests share an exact cache identity;
- custom half-open windows and the 3650-day maximum;
- rejection of mixed preset/custom windows, future overflow, invalid lens,
  missing player, `difference+both`, unsupported language, and unknown floor;
- empty `floors_json` producing a valid single all-floors map;
- maximum eight floors, ASCII ids, bounded EN/RU labels, signed MEDIUMINT Z
  values, sorted non-overlapping bands, exact half-open boundary assignment,
  and rejection of unknown fields such as a client-controlled image token;
- XY-only events returning `null` from floor assignment instead of being
  guessed into a band.

Use these stable functions:

```php
heatmap_parse_v2_query(array $input, int $now): array
heatmap_parse_floor_config($json): array
heatmap_assign_floor($z, array $floors): ?string
heatmap_validate_requested_floor(string $floor, array $floors): string
```

Run:

```powershell
rtk php scripts/web_heatmap_smoke.php
```

Expected: undefined-function failure.

### Step 2: Implement bounded parsing

Add constants beside existing heatmap helpers:

```php
const HEATMAP_V2_SCHEMA = 2;
const HEATMAP_MAX_WINDOW_SECONDS = 315360000; // 3650 days
const HEATMAP_MAX_FLOORS = 8;
const HEATMAP_MEDIUMINT_MIN = -8388608;
const HEATMAP_MEDIUMINT_MAX = 8388607;
```

Throw `InvalidArgumentException` with stable machine codes such as
`invalid_window`, `player_required`, `invalid_floor_config`, and
`unknown_floor`. Public endpoint code maps those codes to localized safe
messages; helpers never echo or exit.

`floors_json` remains a small JSON array. Parser behavior is schema version 1
inside the code/cache identity; adding another stored column is unnecessary.
Sort accepted floors by `z_min`, reject overlap, and preserve stable ids.

### Step 3: Include floors in config normalization and identity

Update `heatmap_projection_config`, `heatmap_merge_config_override`,
`heatmap_save_config`, and `heatmap_config_hash` so a validated canonical floor
array round-trips and invalidates v2 cache identity. Keep v1 payload fields and
the no-floor case unchanged.

### Step 4: Run tests and commit

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/includes/heatmap_points.php
rtk git diff --check
rtk git add web/includes/heatmap_points.php scripts/web_heatmap_smoke.php
rtk git commit -m "feat(heatmaps): validate v2 query and floor contracts"
```

## Task 4: Stream correct event rows and build bounded scenes

**Files:**

- Modify: `web/includes/heatmap_points.php`
- Modify: `scripts/web_heatmap_smoke.php`

### Step 1: Add failing SQL and aggregation tests

Add pure tests for these interfaces:

```php
heatmap_build_scene_sql(array $query, array $config): array
heatmap_scene_bucket_size(int $width, int $height): int
heatmap_accumulate_scene_row(array &$state, array $row): void
heatmap_finalize_scene(array $state): array
```

Assertions must prove:

- SQL filters map, server game, and `eventTime >= from AND eventTime < to`;
- Frags and Teamkills are selected once each, with a hard outer limit of
  `250001` source rows;
- death coordinates use only `pos_victim_x/y/z`; the SQL contains no
  `COALESCE(pos_victim_*, pos_*)`;
- a row can contribute one attacker kill cell and one victim death cell;
- headshot and teamkill are attributes, not channels;
- player `me` counts use killer id for kills and victim id for deaths;
- `others` equals compatible total minus me and never becomes negative;
- floor selection uses raw Z before XY projection;
- every floor uses the common validated map image and the same projection;
  floor metadata contains no client path, URL, or image token;
- malformed, missing, unassigned, projected, in-bounds, and out-of-bounds
  counts appear in coverage;
- a 4096 x 2048 image still produces at most a 128 x 128 grid;
- a 250001st row returns `too_many_events` with no partial bins;
- comparison uses per-layer density shares and returns sample size.

Run RED:

```powershell
rtk php scripts/web_heatmap_smoke.php
```

### Step 2: Build one bounded query path

Add these exact limits:

```php
const HEATMAP_MAX_SOURCE_ROWS = 250000;
const HEATMAP_GRID_MAX_AXIS = 128;
const HEATMAP_MIN_FLOOR_Z_COVERAGE = 0.70;
const HEATMAP_MIN_PROJECTION_COVERAGE = 0.70;
```

The 128 x 128 grid itself caps visible cells at 16384, below the 20000 release
target; do not add a second bin-limit mechanism.

The query returns raw participant ids, both coordinate triplets, weapon,
headshot, event time, and a teamkill marker. Iterate with `PDOStatement::fetch`
instead of `fetchAll`. Use the MySQL unbuffered statement option for this v2
statement and restore ordinary connection behavior after the cursor closes.

Do not use SQL row order for scene correctness. If row 250001 exists, discard
the accumulator and return the explicit budget state.

### Step 3: Project and bucket on the server

Choose:

```text
bucketSize = max(4, ceil(max(imageWidth, imageHeight) / 128))
gridWidth  = ceil(imageWidth / bucketSize)
gridHeight = ceil(imageHeight / bucketSize)
cellId     = "c" + gridX + "." + gridY
```

Apply the existing rotate/flip/scale/crop projection after participant and
floor selection. Accumulate one compact row per occupied cell. Sort output by
`gridY, gridX` so JSON and cache receipts are deterministic.

Return every configured floor with localized label, event count, and
availability. `map.image` always remains the common validated map image. The
initial release does not resolve floor-specific assets or extend
`heatmap_map.php`.

Query suicides separately with `COUNT(*)` for the same map/game/window and
report them as `summary.excludedSuicides`; never place them in kill/death
layers.

State precedence is deterministic:

1. `too_many_events` when the source budget is exceeded;
2. `empty` when no requested combat event has valid XY;
3. `floors_unavailable` for a specific floor request below Z coverage 0.70;
4. `weak_projection` below in-bounds coverage 0.70;
5. `insufficient_sample` for comparison with fewer than three personal events;
6. `ok`.

Warnings may accompany successful `ok`; error states never contain biased
partial layers.

### Step 4: Run GREEN and commit

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/includes/heatmap_points.php
rtk git diff --check
rtk git add web/includes/heatmap_points.php scripts/web_heatmap_smoke.php
rtk git commit -m "feat(heatmaps): build bounded v2 heatmap scenes"
```

## Task 5: Route v2 scenes, cache only complete responses, and log one line

**Files:**

- Modify: `web/heatmap_points.php`
- Modify: `web/includes/heatmap_points.php`
- Modify: `scripts/web_heatmap_smoke.php`

### Step 1: Add failing endpoint-helper tests

Add pure tests for:

```php
heatmap_explorer_mode(array $options): int
heatmap_scene_cache_key(array $query, array $config, array $image): string
heatmap_atomic_write_json(string $path, array $payload): bool
heatmap_prune_payload_cache(string $directory, int $now, int $limit = 32): int
heatmap_request_log(array $metrics): string
```

Prove the cache key changes for schema, game/realgame/map, player/lens/channel,
exact timestamps, floor, projection/floor hashes, image identity, language,
and bucket version. Prove an atomic writer leaves the previous complete JSON
readable when staging fails. Prove rejected/error/too-many results are not
cacheable.

### Step 2: Preserve the v1 branch byte-for-shape

In `web/heatmap_points.php`, branch only after bootstrap and option load:

```php
if (intval($_GET['v'] ?? 1) !== 2) {
    // existing v1 code path
}
```

Move the current v1 body into a small function only if that reduces duplicate
response handling. Requests without `v=2` must retain current parameters,
status behavior, JSON shape, old Canvas consumer, and JPEG links.

While retaining shape, correct the v1 death query to require victim XY and
remove attacker fallback. Add a smoke assertion so this correctness fix cannot
regress.

### Step 3: Gate and serve v2

Use the single option `HeatmapExplorerBeta`:

- `0`: v2 returns `404` with state `explorer_disabled`; v1 is untouched;
- `1`: v2 API is enabled and pages mount it only with explicit opt-in;
- `2`: v2 API is enabled and pages mount it by default.

Map helper exceptions to `400`, missing config/image to `404`, source budget to
`422`, and unexpected failures to a safe `500`. Never return SQL, path,
subprocess, stack, or exception text publicly.

Encode JSON once and log its raw byte length. Do not reject an otherwise valid
scene by raw encoded size: the approved 400 KiB target applies to compressed
transport bytes and is a release gate, not a public response contract. Live
guards remain the source-row, grid, PHP memory, and execution-time budgets.

### Step 4: Make cache writes atomic

Replace direct `file_put_contents(cache_path, json)` with:

1. create a random same-directory file;
2. write the full JSON with an exclusive lock;
3. close and atomically rename it over the target;
4. remove only the staging file on failure.

Use the helper for v1 and v2. Cache only complete `ok`, `empty`, and
`insufficient_sample` scenes. Admin invalidation continues to target matching
game/map payloads, now including realgame aliases and the floor hash.

Preset windows are aligned to 15-minute UTC boundaries in Task 3. To prevent
one file per boundary from accumulating forever, prune at most 32 cache files
older than 48 hours after a successful cache write. Compare `filemtime` to the
injected/current timestamp, ignore subdirectories, and never scan or delete
outside `web/cache/heatmaps`. Add an atomic-writer/pruner smoke using a
temporary directory.

### Step 5: Emit one structured existing-log line

Use `error_log` with prefix `hlstats_heatmap` and one compact JSON object per
scene containing only:

```text
version, operation, game, map, windowClass, lens, floor,
rowsRead, binsReturned, rawPayloadBytes, queryMs, totalMs,
cache, xyCoverage, zCoverage, projectionCoverage, state, fallbackReason
```

Do not log player names, raw IP, SQL, coordinates, cell details, or response
bodies.

### Step 6: Verify and commit

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/heatmap_points.php
rtk php -l web/includes/heatmap_points.php
rtk git diff --check
rtk git add web/heatmap_points.php web/includes/heatmap_points.php scripts/web_heatmap_smoke.php
rtk git commit -m "feat(heatmaps): serve cached v2 scenes behind beta flag"
```

## Task 6: Add bounded cell inspection on the same endpoint

**Files:**

- Modify: `web/includes/heatmap_points.php`
- Modify: `web/heatmap_points.php`
- Modify: `scripts/web_heatmap_smoke.php`

### Step 1: Add failing inspect tests

Cover these helpers:

```php
heatmap_parse_cell_id(string $cellId, array $grid): array
heatmap_unproject_cell_bounds(array $cell, array $grid, array $config): array
heatmap_build_inspect_sql(array $query, array $config, array $bounds): array
heatmap_build_inspect_payload(array $rows, bool $truncated): array
```

Prove:

- only `c<0..127>.<0..127>` ids inside the issued grid pass;
- inverse rotation/flip/scale/crop returns the same raw bounds used by scene
  projection;
- kill inspection filters attacker bounds and death inspection filters victim
  bounds without fallback;
- floor inspection applies the same half-open Z band;
- scene game/map/window/player/channel filters are repeated exactly;
- SQL orders by `eventTime DESC, id DESC` and reads at most 101 rows;
- payload returns at most 100 rows plus `truncated=true`;
- public fields are event time, event type, public player ids/names, weapon,
  headshot, and teamkill only; Steam ids and internal fields are absent.

### Step 2: Implement inspect without a new API surface

When `v=2&inspect=c7.11` is present, use the same validated query and config.
Convert the selected projected cell to bounded raw XY ranges, query only that
cell, and stop after 101 results. Sanitize actor names through existing heatmap
name helpers and preserve current public-player visibility behavior.

The fixed window, fixed grid, fixed cell regex, fixed selected columns, and
101-row cap bound query cost and output size. Do not add a process-local or
file-based IP rate limiter; deployment-level request-rate controls remain the
operator boundary and are documented in Task 12.

Inspect responses use `Cache-Control: no-store` and receive the same structured
request log with `operation=inspect`.

### Step 3: Verify and commit

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/heatmap_points.php
rtk php -l web/includes/heatmap_points.php
rtk git diff --check
rtk git add web/heatmap_points.php web/includes/heatmap_points.php scripts/web_heatmap_smoke.php
rtk git commit -m "feat(heatmaps): add bounded hotspot inspection"
```

## Task 7: Build the smallest WebGL2 renderer around the server grid

**Files:**

- Create: `web/includes/js/heatmap-explorer.js`
- Modify: `scripts/heatmap_js_smoke.js`

### Step 1: Add failing pure-JS tests

Load the new file in the existing Node VM smoke and require these exports:

```javascript
module.exports = {
  HeatmapExplorerScene,
  HeatmapExplorerCamera,
  HeatmapExplorerUrlState,
  HeatmapGlRenderer
};
```

Test without a browser/GPU:

- schema and `grid.fields` validation;
- dense `Float32Array` construction from compact rows;
- kills/deaths/both channel selection;
- total/me/others layer selection;
- difference delta and the `< 3 personal events` opacity cap;
- pointer-to-cell math after zoom/pan;
- directional occupied-cell navigation from a focused map stage;
- camera clamp, reset, keyboard pan, and reduced-motion behavior;
- URL parse/serialize with unknown-key rejection;
- no HTML insertion from API strings.

Run RED:

```powershell
rtk node scripts/heatmap_js_smoke.js
```

### Step 2: Implement one overlay renderer

Use one WebGL2 context and one server-provided density texture:

- build a `Float32Array(grid.width * grid.height)` for the selected layer and
  channel;
- upload it as a single-channel float texture for sampling, not as a render
  target;
- draw one full-canvas quad;
- sample a fixed small neighborhood in the fragment shader for smooth density;
- map normalized kills to amber/orange and deaths to cyan/blue;
- use a fixed blue-neutral-amber diverging palette for difference;
- derive an optional contour line from fixed thresholds in the same shader;
- keep the base map as an `<img>` below the transparent canvas and apply one
  shared CSS camera transform to both.

This avoids point sprites, float-blend extensions, a tile engine, and a GPU
scene graph. It also makes the server's 128 x 128 grid the sole data input.

### Step 3: Handle GPU lifecycle and truthful fallback

On `webglcontextlost`, prevent the default reload, show the localized context
loss state, and keep the JPEG link. On `webglcontextrestored`, rebuild program,
texture, and buffers from the retained scene. If WebGL2 creation or shader
compilation fails, destroy the interactive shell and reveal the static
fallback; never leave a blank canvas.

Expose `destroy()` and remove listeners when the page remounts a player map.
Do not expose shader or driver errors to public UI.

After the first non-empty frame, set `data-heatmap-render-ms` on the root and
dispatch `heatmap-explorer-ready` with the measured duration. This is a local
browser acceptance signal, not a telemetry service.

### Step 4: Verify and commit

```powershell
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
rtk git diff --check
rtk git add web/includes/js/heatmap-explorer.js scripts/heatmap_js_smoke.js
rtk git commit -m "feat(heatmaps): add native WebGL2 grid renderer"
```

## Task 8: Mount the accessible EN/RU Explorer workspace

**Files:**

- Modify: `web/pages/header.php`
- Modify: `web/pages/mapinfo.php`
- Modify: `web/pages/playerinfo_mapperformance.php`
- Modify: `web/pages/admintasks/options.php`
- Modify: `web/lang/en.php`
- Modify: `web/lang/ru.php`
- Modify: `web/hlstats.css`
- Modify: `web/includes/js/heatmap-explorer.js`
- Modify: `scripts/heatmap_js_smoke.js`
- Modify: `scripts/replay_baseline/tests/test_web_route_smoke.py`

### Step 1: Add failing mount, localization, and state tests

Add assertions for the one rollout policy:

```text
mode 0 -> legacy mount regardless of query
mode 1 -> explorer only with heatmap_explorer=1
mode 2 -> explorer unless heatmap_legacy=1
```

Add EN/RU dictionary checks for every public control/state, source assertions
that no runtime English fallback is used for a defined key, and JS state tests
that map changes update image URL, alt text, accessible summary, endpoint, and
share URL together.

### Step 2: Render one semantic shell on both existing pages

Both pages emit the same `.heatmap-explorer` structure through a small PHP
render helper in the existing heatmap include; do not duplicate a new template
system. The player page adds the public player id and enables `me` and
`difference`; mapinfo starts in `overview`.

Desktop structure:

```text
header: map title, period, lens, channel
left rail: all/configured floors
center: base image + WebGL canvas + map controls
right rail: pinned cell inspector
footer: exact UTC window, sample, XY/Z/projection coverage, freshness, fallback
```

Keep a visible static JPEG anchor and `<noscript>` descriptive fallback in the
DOM. The old `.heatmap-viewer` mounts when rollout policy chooses legacy.

### Step 3: Apply a scoped visual system

Add styles only under `.heatmap-explorer` with these tokens:

```css
--hm-bg: #0d1117;
--hm-panel: #151b24;
--hm-panel-raised: #1b2430;
--hm-border: #2a3544;
--hm-text: #eef3f8;
--hm-muted: #9eabb8;
--hm-kill: #ff9f2f;
--hm-death: #35c6e8;
--hm-focus: #f5c451;
```

Use a 220px / minmax(0,1fr) / 300px desktop grid, a map stage with a minimum
height of 620px on wide screens, restrained 8/12/16/24px spacing, one-pixel
borders, and no rainbow, glow, extrusion, or global theme rewrite.

At 900px, move filters and inspector to accessible bottom sheets while keeping
map, period, channel, lens, and floor controls reachable. At 540px, use a
single-column toolbar and a minimum 44px target size.

### Step 4: Implement complete interaction and accessibility state

- Lens, channel, and floor groups expose `aria-pressed` or checked radio state.
- Keyboard supports +/- zoom, arrow pan, Home reset, floor/lens/channel tab
  navigation, Escape unpin, and Enter/Space activation. When the map stage is
  focused, a navigation mode uses arrow keys to move to the nearest occupied
  cell in that direction; Enter/Space pins it, Escape clears it, and the
  textual cell summary changes without requiring a pointer. A dedicated Pan
  control toggles arrow keys back to camera pan so both operations are
  discoverable and never conflict.
- When `difference` is chosen while channel is `both`, the UI selects `kills`,
  announces the change, and disables `both` until another lens is active.
- Hover shows a concise non-focus-stealing summary. Click/Enter pins a cell and
  loads inspect details.
- A visible `role=status` reports loading and coverage; a separate
  `role=alert` reports failure and never clears to blank.
- The textual scene summary changes with every query and remains usable without
  canvas geometry.
- `prefers-reduced-motion` removes camera easing and crossfades.
- URL state uses `hm_range`, `hm_from`, `hm_to`, `hm_lens`, `hm_event`,
  `hm_floor`, and `hm_cell`, while preserving unrelated page query keys.
- Floor changes replace only the filtered layer, label, and textual summary;
  all floors share the common map image and projection in the initial release.
- Retry repeats the same query; fallback switches to the existing v1/JPEG
  path.

### Step 5: Add the operator option

Expose `HeatmapExplorerBeta` as one select in the existing general options page
with localized `Off`, `Opt-in`, and `Default` labels. Do not add a new feature
flag page.

### Step 6: Verify and commit

```powershell
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
$env:PYTHONPATH='scripts;scripts/replay_baseline'
rtk python -m pytest scripts/replay_baseline/tests/test_web_route_smoke.py -q
rtk php -l web/pages/header.php
rtk php -l web/pages/mapinfo.php
rtk php -l web/pages/playerinfo_mapperformance.php
rtk php -l web/pages/admintasks/options.php
rtk php -l web/lang/en.php
rtk php -l web/lang/ru.php
rtk git diff --check
rtk git add `
  web/pages/header.php `
  web/pages/mapinfo.php `
  web/pages/playerinfo_mapperformance.php `
  web/pages/admintasks/options.php `
  web/lang/en.php `
  web/lang/ru.php `
  web/hlstats.css `
  web/includes/js/heatmap-explorer.js `
  scripts/heatmap_js_smoke.js `
  scripts/replay_baseline/tests/test_web_route_smoke.py
rtk git commit -m "feat(heatmaps): mount accessible explorer workspace"
```

## Task 9: Harden admin calibration for floors and durable saves

**Files:**

- Modify: `web/heatmap_admin.php`
- Modify: `web/pages/admintasks/heatmaps.php`
- Modify: `web/includes/heatmap_points.php`
- Modify: `web/includes/js/heatmap.js`
- Modify: `web/lang/en.php`
- Modify: `web/lang/ru.php`
- Modify: `web/hlstats.css`
- Modify: `scripts/web_heatmap_smoke.php`
- Modify: `scripts/heatmap_js_smoke.js`
- Modify: `scripts/replay_baseline/tests/test_web_route_smoke.py`

### Step 1: Add failing security and admin-contract tests

Add tests/source gates for:

- all `save` and `upload` requests requiring POST, access level 80, same
  origin, and `X-HLX-CSRF` matching the session token via `hash_equals`;
- preview remaining read-only;
- maximum upload bytes, JPEG type, maximum 8192 x 8192 dimensions, bounded
  overview text, and tokenized target names;
- both save and upload requiring the last loaded config/image/floor
  `configHash` and returning 409 on mismatch;
- valid floor JSON round-trip and overlap rejection;
- cache invalidation occurring only after committed save and successful
  readback;
- `web/heatmap_admin.php` containing no `proc_open`, command string, stdout,
  stderr, stack, or raw exception detail response;
- JS displaying localized result summaries instead of raw `JSON.stringify`
  output.

### Step 2: Add CSRF using the existing session

Generate one 32-byte random token in the existing authenticated admin page
session, render it as a data attribute on the wizard, and send it in the custom
header for JSON and multipart fetches. Do not create another authentication
cookie or token table.

### Step 3: Make config save compare-and-readback

Use
`web/cache/heatmaps/locks/<sha256(game + NUL + map)>.lock`; create the bounded
`locks` directory through the existing cache helper, keep lock files
non-executable, and never unlink a lock while requests may be waiting.

Because Task 2 converts only the tiny config table to InnoDB:

1. acquire one map-scoped `flock` used by save and upload;
2. start a transaction;
3. lock the complete game/map config row with `SELECT` and `FOR UPDATE`;
4. recompute its canonical config/image/floor hash under the file lock;
5. return 409 if it differs from the client's last-loaded hash;
6. validate and update projection/crop/floors;
7. read the row back and verify the saved canonical hash;
8. commit;
9. invalidate affected game/realgame/map cache entries;
10. emit the existing admin log with actor id, target, old/new hashes, and
    success/failure.

Rollback the transaction on every failure, release the lock in `finally`, and
return only a localized safe message.

### Step 4: Replace uploads atomically

For map JPEG and overview text, require the client's last-loaded `configHash`,
acquire the same map-scoped lock, recompute the current hash, and return 409 on
mismatch. Write a validated same-directory random staging file and retain the
previous target in a same-directory rollback file until completion. Rename the
staging file over the exact tokenized target, reopen it, and verify the saved
artifact identity and resulting canonical hash. Restore the rollback file on
readback failure. Return the new hash to the client, then invalidate cache;
release the lock and remove only owned staging/rollback files in `finally`.

### Step 5: Add a bounded floor editor and Z diagnostic

Keep the current calibration route. Add at most eight editable rows with id,
EN label, RU label, `z_min`, and `z_max`. Show a 32-unit Z histogram for the
selected map/window and a deterministic suggestion that splits only on empty
gaps of at least 128 Z units. Suggestions never save automatically; the
operator reviews and presses Save.

Preview all floors or one selected band through the same scene builder used by
the public endpoint. Show queried/valid XY/with Z/assigned/in-bounds counts and
plain-language warnings.

### Step 6: Remove HTTP subprocess regeneration

Delete the `regenerate` action and button. Replace it with localized text that
JPEG regeneration is an explicit deployment CLI step:

```powershell
$env:PYTHONPATH='scripts'
rtk python -m hlstats_py.heatmaps --game $selectedGame --map $selectedMap --disablecache
```

The UI substitutes the selected validated tokens when showing this instruction;
it never executes or returns a command.

### Step 7: Verify and commit

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk node scripts/heatmap_js_smoke.js
$env:PYTHONPATH='scripts;scripts/replay_baseline'
rtk python -m pytest scripts/replay_baseline/tests/test_web_route_smoke.py -q
rtk php -l web/heatmap_admin.php
rtk php -l web/pages/admintasks/heatmaps.php
rtk php -l web/includes/heatmap_points.php
rtk node --check web/includes/js/heatmap.js
rtk git diff --check
rtk git add `
  web/heatmap_admin.php `
  web/pages/admintasks/heatmaps.php `
  web/includes/heatmap_points.php `
  web/includes/js/heatmap.js `
  web/lang/en.php `
  web/lang/ru.php `
  web/hlstats.css `
  scripts/web_heatmap_smoke.php `
  scripts/heatmap_js_smoke.js `
  scripts/replay_baseline/tests/test_web_route_smoke.py
rtk git commit -m "fix(heatmaps): harden calibration and floor saves"
```

## Task 10: Wire the source gates and obtain SOURCE-READY

**Files:**

- Modify: `.github/workflows/product-ci.yml`
- Modify: `docs/test-plan.md`
- Create: `scripts/replay_baseline/fixtures/modern_heatmap_coordinates.log`
- Create: `scripts/replay_baseline/comparison/Run-HeatmapCoordinateAcceptance.ps1`
- Create: `scripts/replay_baseline/tests/test_heatmap_coordinate_acceptance_script.py`

### Step 1: Add the new static checks to existing CI

In the current web/heatmap CI job, keep existing checks and add:

```yaml
- run: node --check web/includes/js/heatmap-explorer.js
- run: node scripts/heatmap_js_smoke.js
- run: php scripts/web_heatmap_smoke.php
```

Do not add a package manager, browser download, or separate workflow.

Add a source test for the focused coordinate-acceptance runner. The fixture
contains deterministic fake identities and these ordered cases:

1. one shipped CStrike kill with distinct attacker/victim XYZ and headshot;
2. one SourceMod-form suicide with only `victim_position`;
3. one `World triggered "killlocation"` followed by two coordinate-free kills,
   proving only the first consumes the staged pair;
4. another staged pair, exact `Log file started`, then a coordinate-free kill,
   proving the source boundary clears it.

The PowerShell runner must reuse the existing disposable Python comparison
compose and direct `hlstats_py.runtime --stdin` path, refuse a non-disposable
target, start from a fresh restored DB, import exactly this one fixture, and
run fail-closed SQL assertions. It writes a sanitized JSON receipt containing
fixture SHA, row counts, asserted coordinate tuples, and verdict; it never
prints credentials or unique ids.

### Step 2: Document the exact source gate

Add one Modern Heatmap Explorer section to `docs/test-plan.md` listing focused
RED/GREEN tests, full Python tests, PHP lint/smoke, JavaScript parse/smoke,
route smoke, migration assertions, and the distinction between source and
runtime acceptance.

### Step 3: Run the complete source gate

```powershell
$env:PYTHONPATH='scripts;scripts/replay_baseline'
rtk python -m pytest scripts/hlstats_py/tests -q
rtk python -m pytest scripts/replay_baseline/tests -q
rtk python -m compileall -q scripts/hlstats_py scripts/replay_baseline
rtk node --check web/includes/js/heatmap.js
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/heatmap_points.php
rtk php -l web/heatmap_admin.php
rtk php -l web/includes/heatmap_points.php
rtk php -l web/pages/header.php
rtk php -l web/pages/mapinfo.php
rtk php -l web/pages/playerinfo_mapperformance.php
rtk php -l web/pages/admintasks/options.php
rtk php -l web/pages/admintasks/heatmaps.php
rtk php -l web/lang/en.php
rtk php -l web/lang/ru.php
rtk php -l web/updater/80.php
rtk php -l web/updater/81.php
rtk git diff --check
rtk git status --short
```

Expected: all commands pass and status lists only intended heatmap/CI/docs
changes. This establishes `SOURCE-READY`, not runtime or release acceptance.

### Step 4: Commit

```powershell
rtk git add `
  .github/workflows/product-ci.yml `
  docs/test-plan.md `
  scripts/replay_baseline/fixtures/modern_heatmap_coordinates.log `
  scripts/replay_baseline/comparison/Run-HeatmapCoordinateAcceptance.ps1 `
  scripts/replay_baseline/tests/test_heatmap_coordinate_acceptance_script.py
rtk git commit -m "test(heatmaps): enforce explorer source gates"
```

## Task 11: Prove populated-query performance and add an index only on evidence

**Files:**

- Create: `docs/audits/modern-heatmap-explorer/performance.md`
- Create only if the index gate fires: `web/updater/82.php`
- Modify only if the index gate fires: `sql/install.sql`
- Modify only if the index gate fires: `scripts/web_heatmap_smoke.php`

### Step 1: Create fresh populated evidence

Run the canonical release contour without legacy reuse:

```powershell
$evidenceRunId = [guid]::NewGuid().ToString()
rtk powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -ArtifactLabel heatmap-explorer-narrow-1000 `
  -EvidenceRunId $evidenceRunId `
  -UseDumpRestore
```

Expected: shared input manifest, successful Python import, maintenance receipt,
and logical compare with no new non-accepted visible-product residual. Record
the exact artifact paths and verdict in `performance.md`.

### Step 2: Apply migration on disposable 79 and 80 copies

Take a recoverable dump of the disposable Python DB. On one restored copy set
only `hlstats_Options.dbversion` to 79; on another set it to 80. Run the normal
web updater on each and verify:

```sql
SELECT value FROM hlstats_Options WHERE keyname='dbversion';
SHOW COLUMNS FROM hlstats_Heatmap_Config LIKE 'floors_json';
SHOW TABLE STATUS LIKE 'hlstats_Heatmap_Config';
SELECT value FROM hlstats_Options WHERE keyname='HeatmapExplorerBeta';
```

Expected on both: dbversion 81, one `floors_json` column, InnoDB config table,
and beta value 0. Restore the original disposable dump after the 79-path test
before executing the independent 80-path test.

### Step 3: Select a reproducible populated case

In the Python contour DB, choose the map with the most coordinate-bearing
frags in the last 365 days of stored event time and the player with the most
events on that map. Record the exact game, realgame, map, player id, `from`,
`to`, event counts, XY coverage, and Z coverage in `performance.md`. Do not use
wall-clock `now` against the historical corpus.

Capture `EXPLAIN FORMAT=JSON` for the total scene query, player comparison
query, inspect query, and suicide count before changing indexes.

### Step 4: Measure cold, warm, payload, and inspect targets

Use mode 1 and direct v2 opt-in at `http://127.0.0.1:8281`. Measure five unique
exact windows for cold scenes, 30 repeats of one exact window for warm scenes,
and 30 repeats of a populated cell for inspect. Calculate nearest-rank p95.

Release targets:

```text
cold scene p95 <= 1500 ms
warm scene p95 <= 300 ms
warm inspect p95 <= 300 ms
compressed transport scene <= 409600 bytes
visible bins <= 20000
no PHP memory failure, truncation, or partial payload
```

Save raw timings, response states, cache status, raw JSON bytes, compressed
wire bytes, rows read, bins, and coverage in `performance.md`. Capture
compressed bytes at the reference reverse proxy/browser boundary; do not infer
them from raw PHP string length.

### Step 5: Execute the index gate exactly once

If all targets pass and EXPLAIN uses a bounded map/time path, record
`index_not_required` and do not modify schema.

If a target fails or EXPLAIN scans an event table, identify the single failing
query/table that dominates the measured latency and derive exactly one
candidate index from its equality predicates, range predicate, and observed
plan. Start with the narrowest key that supports that query shape. Do not add
`serverId`, do not index `hlstats_Events_Suicides`, and do not touch a second
event table unless its own EXPLAIN plus timing is the recorded bottleneck.

Test that one candidate on the disposable DB, then repeat the identical
EXPLAIN and timing cases. Keep it only when the plan and timings improve
without regressing ingest acceptance. If retained, encode exactly that proven
DDL in idempotent `web/updater/82.php`, bump fresh install to dbversion 82, add
the same fresh-install index, update dbversion last, and extend schema smoke.
Applying 82 to a large MyISAM event table requires a maintenance window.

When the indexes are retained, rerun the canonical 1000-file contour from a
fresh database with a new generated evidence id and artifact label
`heatmap-explorer-index-narrow-1000`. Require the same logical verdict and
record import elapsed time against the pre-index run; do not accept an ingest
failure or an unexplained material slowdown.

If correct indexed queries plus ordinary cache still miss a target, stop. Mark
release `BLOCKED-READ-MODEL-EVIDENCE`, preserve receipts, and open the separate
daily-grid design required by the approved escalation ladder. Do not add the
table inside this implementation branch.

### Step 6: Commit the evidence and optional migration

Without an index migration:

```powershell
rtk git add docs/audits/modern-heatmap-explorer/performance.md
rtk git commit -m "docs(heatmaps): record populated performance gate"
```

With the proven index migration:

```powershell
rtk php scripts/web_heatmap_smoke.php
rtk php -l web/updater/82.php
rtk git diff --check
rtk git add `
  docs/audits/modern-heatmap-explorer/performance.md `
  web/updater/82.php `
  sql/install.sql `
  scripts/web_heatmap_smoke.php
rtk git commit -m "perf(heatmaps): add measured map-time indexes"
```

## Task 12: Obtain browser, admin, fallback, rollback, and release acceptance

**Files:**

- Create: `docs/audits/modern-heatmap-explorer/runtime-acceptance.md`
- Add real screenshots under: `docs/audits/modern-heatmap-explorer/screenshots/`
- Modify: `docs/status.md`
- Modify: `docs/plans.md`
- Modify: `docs/release-readiness.md`
- Modify: `docs/test-plan.md`

### Step 1: Validate data truth against SQL

First run the focused import against a fresh disposable Python DB:

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-HeatmapCoordinateAcceptance.ps1 `
  -EvidenceLabel heatmap-coordinate-contract
```

Require a passing receipt proving the shipped CStrike attacker/victim triplets,
SourceMod suicide `victim_position`, one-shot staged `killlocation`, and exact
`Log file started` clearing in persisted DB rows. Unit/static results alone do
not satisfy this gate. Attach the receipt to `runtime-acceptance.md`; this is
the first point at which the coordinate change may be called
`RUNTIME-ACCEPTED`.

For the selected populated case, compare scene totals to direct SQL for:

- attacker kills;
- victim deaths with victim coordinates only;
- teamkills;
- headshots retaining attacker coordinates;
- player killer/victim lens counts;
- suicides reported as excluded;
- floor-boundary counts, including exact `z_min`, exact `z_max`, missing Z,
  and unassigned Z.

Verify an inspect cell against the same raw bounds and exact window. Record SQL,
scene values, and verdict without player unique ids or credentials.

Regenerate the selected map's compatibility files from the populated
disposable contour and bypass the incremental overlay cache:

```powershell
$env:PYTHONPATH='scripts'
rtk python -m hlstats_py.heatmaps `
  --game $selectedGame `
  --map $selectedMap `
  --disablecache
```

Verify that both `<map>-kill.jpg` and `<map>-kill-thumb.jpg` are valid non-empty
JPEGs, open them visually, and confirm their public links still resolve. The
HUD must identify the configured rolling-day legacy snapshot; do not compare
its period to the selected Explorer window or present it as interactive parity.

### Step 2: Run the full desktop and mobile visual matrix

Capture real browser screenshots at 1440 x 1000 and 390 x 844:

- `screenshots/map-overview-en.png`;
- `screenshots/player-difference-ru.png`;
- `screenshots/mobile-inspector-ru.png`;
- `screenshots/fallback-jpeg-en.png`.

For EN and RU, verify overview/me/difference, kills/deaths/both, preset/custom
period, all/configured floors, hover, pinned inspect, share/reload, empty,
insufficient sample, weak projection, floors unavailable, too many events,
API failure, and retry.

Visually verify map readability, no rainbow/glow, warm/cool distinction,
non-color labels, legible coverage footer, inspector hierarchy, stable layout,
and no clipped RU strings.

On the documented reference desktop, capture the
`heatmap-explorer-ready.detail.durationMs` value for cold overview and player
scenes. Require first meaningful render at or below 1500 ms and record browser,
GPU, viewport, raw/compressed scene bytes, and bin count in
`runtime-acceptance.md`.

### Step 3: Run accessibility and GPU failure checks

Using keyboard only, execute lens/channel/floor selection, zoom, pan, reset,
focused-cell navigation, pin, inspect, unpin, and fallback. Verify visible
focus, 44px mobile targets,
screen-reader names/states, live status, alert persistence, textual summary,
logical focus order, 200% zoom, and reduced motion.

Force context loss through `WEBGL_lose_context.loseContext()`, verify a visible
localized fallback, restore context, and confirm the same scene returns. Test a
browser with WebGL2 disabled and JavaScript disabled; both must expose the
static JPEG and descriptive text rather than a blank region.

### Step 4: Run authenticated admin acceptance

On a disposable config/map:

- reject missing/wrong CSRF and non-admin access;
- load projection and config hash;
- upload a valid JPEG and overview atomically, verify readback, and accept the
  returned new hash;
- reject oversize, wrong type, excessive dimensions, invalid token, invalid
  floor id, overlapping bands, and stale save/upload hashes without changing
  current files or config;
- open two admin sessions on the same map and prove the second session receives
  409 after the first changes either config or an asset;
- view Z histogram, review a suggestion, edit EN/RU labels, preview all and one
  floor, save, read back, and confirm affected caches were invalidated;
- verify no HTTP action can start JPEG generation and no raw exception/command
  output reaches UI.

Restore the disposable map/config backup after the check.

### Step 5: Prove rollout and instant rollback

Exercise the same page in all three modes:

1. mode 0: v1 Canvas/JPEG only and v2 direct route disabled;
2. mode 1: default v1, explicit `heatmap_explorer=1` mounts v2;
3. mode 2: default v2, explicit `heatmap_legacy=1` mounts v1;
4. switch mode 2 to 0 and confirm the next page request returns to v1 without
   schema reversal, event mutation, cache deletion, or deploy rollback.

Preserve old `heatmap_points.php` without `v=2`, `heatmap_map.php`, map/player
page URLs, and `*-kill.jpg` / `*-kill-thumb.jpg` links in every mode.

### Step 6: Document operations and release decision

In `docs/release-readiness.md`, add:

- `HeatmapExplorerBeta` meanings and rollback command/path;
- structured log fields and a sample safe line;
- reverse-proxy inspect rate-limit recommendation for public deployments;
- cache location, invalidation behavior, and permissions;
- CLI-only JPEG regeneration;
- index maintenance-window note when dbversion 82 is retained;
- escalation stop condition for a daily read-model;
- supported telemetry statement: shipped cstrike grammar verified, other mods
  accept only coordinates actually present in their logs.

Promotion sequence:

```text
deploy with mode 0 -> migrate/readback -> mode 1 internal opt-in
-> mode 1 public beta -> mode 2 default
```

Rollback to mode 0 when, in a 15-minute sample, v2 5xx exceeds 0.5%, warm p95
exceeds 600 ms, cold p95 exceeds 3000 ms, inspect p95 exceeds 600 ms, a scene
is biased/truncated, or an accepted map drops below its recorded coverage.

Update `docs/status.md` and `docs/plans.md` with exact evidence and the honest
final label. Do not write `RELEASE-READY` while any required populated,
browser, admin, performance, fallback, or rollback row is missing.

### Step 7: Final verification and commit

```powershell
$env:PYTHONPATH='scripts;scripts/replay_baseline'
rtk python -m pytest scripts/hlstats_py/tests -q
rtk python -m pytest scripts/replay_baseline/tests -q
rtk node --check web/includes/js/heatmap.js
rtk node --check web/includes/js/heatmap-explorer.js
rtk node scripts/heatmap_js_smoke.js
rtk php scripts/web_heatmap_smoke.php
rtk git diff --check
rtk git status --short
```

Inspect the exact diff, confirm no files from the dirty experimental worktree
were staged implicitly, then commit only acceptance artifacts and canonical
docs:

```powershell
rtk git add `
  docs/audits/modern-heatmap-explorer `
  docs/status.md `
  docs/plans.md `
  docs/release-readiness.md `
  docs/test-plan.md
rtk git commit -m "docs(heatmaps): record explorer release acceptance"
```

## Final acceptance checklist

- [ ] No-v requests retain the v1 contract and old URLs/JPEG files work.
- [ ] CStrike shipped log grammar persists attacker, victim, headshot,
  teamkill, and AMXX suicide coordinates correctly; SourceMod-form suicide
  coordinates also persist through the documented alias order.
- [ ] Staged killlocation data is server-scoped, one-shot, and lower precedence
  than inline data.
- [ ] Death never falls back to attacker coordinates.
- [ ] All-floors accepts XY-only; a specific floor requires validated Z.
- [ ] Floor bands are reviewed, non-overlapping, half-open, localized, and
  cache-invalidating.
- [ ] Scene reads no more than 250000 source rows, emits no more than 20000
  bins, and never returns a biased partial success.
- [ ] Inspect accepts one issued cell, returns at most 100 public rows, and
  reports truncation.
- [ ] WebGL2 renders the server grid, survives context restore, and falls back
  visibly.
- [ ] Desktop, mobile, EN, RU, keyboard, reduced-motion, and textual summaries
  are accepted with real screenshots.
- [ ] Admin save/upload is authenticated, CSRF-protected, validated, atomic,
  compare-and-readback, and subprocess-free.
- [ ] Warm/cold/inspect/compressed-payload/FMR targets pass or promotion is
  blocked with retained evidence.
- [ ] Feature modes 0/1/2 and one-request rollback are proven.
- [ ] Canonical docs name the exact evidence boundary and final acceptance
  label.
