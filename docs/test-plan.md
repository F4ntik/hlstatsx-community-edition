# Test Plan: Standalone Python+i18n Product Lane

## Objective

Validate that the integrated product repository works as one coherent stack:

- Python is the default runtime and operational path
- the PHP frontend renders through the explicit EN/RU i18n runtime
- replay, heatmaps, and core web flows still behave correctly after the donor
  layers were combined

## Canonical runbooks

- replay speed, direct stdin guidance, and contour helpers:
  [`docs/replay-fast-path.md`](replay-fast-path.md)
- parity-debug workflow for narrow residuals:
  [`docs/parity-debug-pipeline.md`](parity-debug-pipeline.md)
- parity acceptance layers, fixture identity, and Perl boundaries:
  [`docs/parity-acceptance.md`](parity-acceptance.md)
- release-readiness metrics, profiling, artifact, and deployment handoff:
  [`docs/release-readiness.md`](release-readiness.md)
- audit flow, artifacts, and parity bug plan:
  [`docs/audits/legacy-python-parity-20260423/README.md`](audits/legacy-python-parity-20260423/README.md)

Do not restate those runbooks here. This document is the verification matrix.

## Targeted gates for replay evidence and heatmaps

For the import/heatmap contract, run the narrow checks before any Docker
replay:

```powershell
$env:PYTHONPATH = 'scripts'
python -m pytest `
  scripts/hlstats_ftp_py/tests/test_main.py `
  scripts/replay_baseline/tests/test_direct_import_artifacts.py `
  scripts/replay_baseline/tests/test_dual_contour_script.py `
  scripts/hlstats_py/tests/test_heatmaps.py `
  scripts/hlstats_py/tests/test_heatmap_projection_migrate.py `
  scripts/hlstats_py/tests/test_heatmap_projection_calibrate.py -q
python -m compileall -q scripts/hlstats_py scripts/hlstats_ftp_py scripts/replay_baseline
node scripts/heatmap_js_smoke.js
node --check web/includes/js/heatmap.js
php scripts/web_heatmap_smoke.php
```

The PHP command requires a PHP CLI on the validation host. If it is absent,
run the same smoke in the built `python-web` Docker image and record that
runtime result explicitly; do not silently call a source-only check a runtime
gate. The acceptance replay additionally requires a fresh Docker worker image, a unique
`EvidenceRunId`, `-UseDumpRestore`, equal final input manifests, both
same-run ignored/drop manifests, matching contour metadata and snapshots, and
no unexpected DB drift. Existing `*-1000` artifacts must first pass the
evidence inventory classification.

Projection migration is read-only by default. Inspect the rotate distribution,
verify a backup, and obtain the separate runtime approval before
`--apply --runtime-gate-approved`; `--apply` without the explicit gate flag is
rejected before DB connection. A distribution containing rotate `2` or `3` is
a manual-classification stop. The DB-first calibration helper applies the same
fail-closed rule: `heatmap_projection_calibrate.py --apply` also requires
`--runtime-gate-approved`.

## Validation scope

In scope:

- `hlstats_py` runtime and CLI entrypoints
- `proxy_daemon_py` runtime and targeted tests
- replay-baseline helpers and compact diff tooling
- Python heatmap batch generation
- explicit EN/RU frontend runtime and representative pages
- language persistence and fallback behavior
- integrated product docs and runbooks

Out of scope:

- upstream RU PR reviewability
- donor-branch-only cleanup that does not affect this product repo
- third locale rollout

## Test levels

### Cost-aware validation ladder

Use the cheapest check that can disprove the current hypothesis, then promote
only when it passes:

- static/source inspection and direct SQL checks
- focused unit or helper tests for the touched behavior
- single-log or extracted-window parity
- automatic `30/30` guard-window parity after point fixes
- small related-log cluster when the bug is lifecycle-dependent
- full `narrow-1000` contour
- maintenance-enabled GeoIP/awards/ribbons and replay-backed web smoke when the
  changed surface can affect those outputs

Do not start with broad replay when a single residual can be reduced to one
log, one SQL anchor, or one focused regression.

### Python / tooling

Run targeted `pytest` for the touched surface:

- `scripts/hlstats_py/tests`
- `scripts/proxy_daemon_py/tests`
- `scripts/replay_baseline/tests`

CI coverage:

- `.github/workflows/product-ci.yml` runs `proxy_daemon_py` lint/type/test,
  `hlstats_py` tests, `replay_baseline` helper tests, PHP syntax lint for
  `web/`, and docs sanity checks on product-lane changes.
- `hlstats_py` CI installs `scripts/hlstats_py`, which declares `hlx_core` as a
  path dependency, then runs an import smoke before tests. This verifies the
  package boundary instead of the old `scripts:scripts/proxy_daemon_py`
  source-tree bridge.
- Reconnect regression coverage lives in `scripts/proxy_daemon_py/tests/test_db.py`
  and pins lazy connect, disabled ping, successful `ping(reconnect=False)`, and
  failed-ping reconnect behavior. `scripts/hlstats_py/tests/test_storage.py`
  pins the stdin batch skip-ping bridge that currently consumes that adapter.
- `.github/workflows/nightly-parity.yml` is the scheduled/manual Phase 7
  parity acceptance workflow and Phase 9 release artifact handoff. It always
  runs lightweight replay helper smoke and has an opt-in/manual plus scheduled
  heavy gate for the Docker-backed legacy-vs-Python replay contour. The heavy
  job is bound to a self-hosted Windows parity runner because the current
  contour scripts use Windows PowerShell, Docker Compose, fixed local container
  names, and host bind paths. Its canonical runner performs dual replay,
  historical-clock maintenance (`inactive`, awards, ribbons, GeoIP), compact
  DB compare, legacy EN-reference plus Python EN/RU replay-backed smoke before
  the retained evidence is packaged.
- The `hlstatsx_py` release line does not ship local Perl production
  entrypoints. Legacy behavior remains a replay/reference acceptance layer, not
  a production runtime dependency.

Boundary checks:

- `hlstats_py.runtime --stdin` CLI contract when the runtime flags or import
  path change
- `scripts/hlstats_ftp_py` only when FTP/replay ordering logic changes
- `scripts/import_bans_py` only when maintenance CLI behavior changes
- Lifecycle launcher changes require `bash -n` syntax checks for
  `scripts/run_proxy_py`, `scripts/run_hlstats_py`, and
  `scripts/lib/process_lifecycle.sh`, plus stop-path smoke tests against a
  short-lived PID-file process and a TERM-ignoring process to prove `SIGKILL`
  remains fallback-only.
- Control-plane hardening requires targeted runtime tests for both command
  surfaces: `hlstats_py` direct loopback `HEARTBEAT`/`SERVERLIST` stay
  read-only, `hlstats_py` `RELOAD`/`KILL` require valid proxied `PROXY Key`,
  `proxy_daemon_py` direct loopback `RELOAD` is rejected, proxied `RELOAD`
  remains allowed, and unsupported `proxy_daemon_py` `C;KILL;` is rejected
  without forwarding.
- DB mode changes require adapter tests for both online and import modes:
  online connections must keep strict/server `sql_mode` active, import mode may
  set `SESSION sql_mode = ''`, and `enable_multi_statements` must be rejected
  unless `import_mode=True`. Also pin positive import-mode multi-statement
  `client_flag` behavior and wiring tests for `hlstats_py --stdin` plus FTP
  batch import.
- Runtime metrics changes require focused `hlstats_py` runtime tests for
  processed-event counters, category grouping, stdin/UDP/drop counters,
  flush-attempt counters, control command/rejection counters, and the stable
  `HLstats metrics:` summary log line.

### Observability / profiling / release handoff

Use [`docs/release-readiness.md`](release-readiness.md) as the canonical
Phase 9 validation runbook.

Required checks when observability or release-handoff behavior changes:

- targeted `hlstats_py` runtime tests for metrics counters and summary logs;
- docs sanity check that `docs/release-readiness.md`, `docs/status.md`, and
  `docs/test-plan.md` stay aligned;
- workflow syntax/review for `.github/workflows/nightly-parity.yml` artifact
  paths when release bundles change.

Release candidate evidence should include:

- product CI results;
- heavy release-clean parity replay with integrated maintenance, compact compare,
  and retained receipt;
- replay-backed legacy EN-reference and Python EN/RU web smoke;
- at least one `HLstats metrics:` summary from stdin import or runtime stop;
- benchmark/profile output when parser, storage, replay, DB mode, reconnect,
  lifecycle, or control-plane behavior changed;
- the sanitized `nightly-parity-summary` from nightly/manual parity when
  available.

### Replay / runtime parity

Default rule:

- use direct stdin / worker-local batch import for parity regression
- use UDP replay only for transport/proxy checks, not as the default parity
  route

Required checks when parity-affecting runtime/storage code changes:

- restore a clean comparison baseline
- run the relevant single-log or narrow-window replay first
- for release-clean parity, run the canonical dual runner maintenance stage;
  it records a shared historical award date/horizon, sets and verifies
  `UseTimestamp=1` in the disposable contours, then runs inactive players,
  awards, ribbons, GeoIP, compare, and web smoke fail-closed
- validate `hlstats_Players` full GeoIP plus awards/ribbons through the saved
  compare and maintenance summary; otherwise use `-SkipMaintenance` only for a
  documented raw-only debug result
- record residual classification in `docs/audits/legacy-python-parity-20260423/`

Current parity gates:

- `P6d-M1`: `hlstats_Events_TeamBonuses` is closed for the current
  `narrow-1000` contour.
- `P6d-M2`: `ChangeTeam`, `Connects`, `Chat`, and `PlayerActions` are closed
  for the current `narrow-1000` contour.
- `P6d-M3`: `hlstats_Events_Entries` is closed for the current narrow
  contour/default Python path; direct counts are `legacy=0`, `python=0`.
- `P6d-M4`: `hlstats_Players` raw replay compare can show an accepted
  GeoIP-only diff because stdin replay does not run maintenance. A
  release-clean run uses the dual runner's shared legacy/Python maintenance
  receipt, which compares full GeoIP (`flag`, `country`, `city`, `state`,
  latitude, longitude) alongside awards and ribbons.
- `P6d-M5`: `hlstats_Events_ChangeTeam` is closed for the current
  `narrow-1000` contour; direct SQL anchors are `legacy
  total=1345/unassigned=47` and `python total=1345/unassigned=47`.

No current parity gate should reopen `PlayerNames`, `Players_History`,
`TeamBonuses`, `Entries`, or `ChangeTeam` without fresh focused evidence.

Parity acceptance layers:

- ordinary PR/local work uses the lightweight subset: relevant product CI jobs,
  targeted Python tests for the changed surface, replay helper smoke, and
  narrow Python replay/compare only when the change can affect parity.
- scheduled or manual release-readiness work uses the heavy subset:
  fresh `Run-DualContour-1000.ps1 -UseDumpRestore -MaxImportFiles 1000`
  without `-ReuseValidLegacy`. It performs maintenance, compare, legacy EN
  reference smoke, and Python EN/RU product smoke itself, with artifacts retained from
  `docs/audits/legacy-python-parity-20260423/` and
  `scripts/replay_baseline/comparison/.parity-state/`.
- Legacy reference behavior remains required for baseline regeneration,
  targeted investigation, and the heavy acceptance replay. It is not a local
  production runtime dependency and is not required for every routine PR when
  fixture inputs and the accepted legacy contour are unchanged.

Minimum replay validation loop:

- targeted `pytest` for touched code
- single-log parity or narrow contour replay
- automatic `30/30` guard-window pass for point fixes when an event anchor is
  available
- successful canonical-runner maintenance summary, including non-empty input
  anchors, shared date/horizon, `UseTimestamp=1` readbacks, automatic
  `compare_stats_dbs.py --max-examples 20`, legacy EN-reference and Python
  EN/RU product web-smoke logs
- evidence update in `bug-plan.md`, `issues.jsonl`, or the relevant audit note

### Heatmaps

Run targeted checks when heatmap generation, projection, JSON payloads, or web
overlay behavior changes:

- Python generator tests:
  `python -m pytest scripts/hlstats_py/tests/test_heatmaps.py -q`
- PHP helper smoke:
  `php scripts/web_heatmap_smoke.php` locally when PHP is installed, or the
  same script inside the web container.
- PHP syntax lint for touched heatmap web files:
  `web/includes/heatmap_points.php`, `web/heatmap_points.php`,
  `web/heatmap_map.php`, `web/heatmap_admin.php`,
  `web/pages/admintasks/heatmaps.php`, `web/pages/mapinfo.php`, and any
  touched `playerinfo_*` include.
- DB-first projection diagnostics before expensive replay/regeneration:
  `python scripts/hlstats_py/heatmaps.py --configfile scripts/replay_baseline/comparison/python/hlstats.host.conf --game cstrike --map de_dust2 --heatmaps-root heatmaps --assets-root heatmaps/src --diagnose-projection`
- Browser verification for `mode=mapinfo&game=<code>&map=<map>`: canvas overlay
  visible, static JPEG/thumb fallback still linked, diagnostics badge appears
  when in-bounds ratio is weak, console/network clean.
- Browser verification for `mode=playerinfo&player=<id>&game=<code>` in the
  Maps & Servers tab: map selector appears for configured maps, `Kills`,
  `Deaths`, and `Kills/Deaths` redraw the same canvas, warm/cool colors are
  distinguishable, and hover tooltip shows event counts plus top
  killers/victims/players.
- Browser verification for `mode=admin&task=heatmaps&game=<code>`: upload JPG
  and overview, preview changes offset/scale/flip/rotate/crop without saving,
  save updates DB config and invalidates payload cache, regenerate returns the
  Python heatmap command result.

Full replay and `--disablecache` heatmap regeneration are promotion checks.
Use the already populated DB for visual/projection iteration first.

### Modern Heatmap Explorer

#### Background-grading runtime acceptance (`0b6a875`)

- Passing local runtime rows: default/reversible Color and Mono without a scene
  request or URL mutation; keyboard focus and `aria-pressed`; Russian mobile
  `44px` style targets without horizontal overflow; 200% scale; reduced
  motion; and WebGL-unavailable unfiltered static JPEG with hidden controls.
- The committed JavaScript smoke is the deterministic no-`fetch` proof; a
  route-abort tests a different failure path. Difference invariance is accepted
  at the CSS/JS seam (image/pseudo-layer only, no renderer/fetch/URL call) and
  visual runtime scene. The isolated-canvas attempt on baseline `1.26` is
  retained as a bounded non-loading residual, with no third activation.
- Record the exact restore readback and the documented whole-suite source
  result (`302 passed` with `PYTHONPATH=scripts;scripts/replay_baseline`) in the
  runtime acceptance receipt. The earlier `286/16` was the invalid no-PYTHONPATH
  invocation, not a source regression.

- Focused RED/GREEN source contract: `python -m pytest
  scripts/replay_baseline/tests/test_heatmap_coordinate_acceptance_script.py -q`.
- Full Python source checks: `python -m pytest scripts/hlstats_py/tests -q`,
  `python -m pytest scripts/replay_baseline/tests -q`, and
  `python -m compileall -q scripts/hlstats_py scripts/replay_baseline`.
- PHP lint/smoke: `php scripts/web_heatmap_smoke.php` plus the focused web and
  updater `php -l` checks; on Windows without PHP, use the approved
  `python-web:latest` Docker image with the same commands.
- JavaScript syntax/smoke: `node --check web/includes/js/heatmap.js`,
  `node --check web/includes/js/heatmap-explorer.js`, and
  `node scripts/heatmap_js_smoke.js`.
- Route smoke: `python -m pytest
  scripts/replay_baseline/tests/test_web_route_smoke.py -q`. Migration checks
  include the focused source assertions and `php -l web/updater/80.php` plus
  `php -l web/updater/81.php`.
- Coordinate runner: `powershell -NoProfile -ExecutionPolicy Bypass -File
  scripts/replay_baseline/comparison/Run-HeatmapCoordinateAcceptance.ps1` only
  against the disposable `bench_ephemeral` contour; it is deliberately not a
  normal source test.
- Current runtime truth for the frozen 2026-09-01 pass is
  `docs/audits/modern-heatmap-explorer/runtime-acceptance.md`. That pass
  remained blocked at release/runtime acceptance because the disposable runner
  did not produce a persisted-row receipt (`Unknown column 'uniqueId'` on the
  restored schema), the live player/mobile browser surface did not produce an
  accepted Explorer interaction path or any
  `heatmap-explorer-ready.detail.durationMs` receipt, and the live image did
  not contain `scripts/web_heatmap_smoke.php` even though `php -l
  /var/www/html/heatmap_points.php` and `php -l
  /var/www/html/includes/heatmap_points.php` passed inside the running web
  container.

**Source gate:** static contract, Python, PHP, JavaScript, route, migration,
and diff checks pass without Docker DB execution. **Runtime acceptance:** a
fresh disposable coordinate-runner receipt proves persisted tuples. **Release
acceptance:** adds the approved live DB/browser/regeneration and release
evidence; source or runtime results alone do not establish it.

### Frontend / i18n

Run targeted checks when frontend-visible behavior changes:

- `php -l` for every touched PHP file
- representative EN/RU smoke for the affected route group
- language persistence and fallback behavior if request/session handling changed

CI now runs `php -l` over all `web/**/*.php` files using PHP 8.2. Local Windows
validation may require installing PHP or running the lint inside the web
container. CI also runs `php scripts/web_i18n_smoke.php`, which pins the
request/cookie/session language priority, language-aware URL generation,
historical cache key language separation, and the no-mutation contract for the
new request/cache helpers.
The heavy runner invokes `web_route_smoke.py` after its maintenance compare:
the English-only legacy web is the EN reference, while the Python product is
checked in EN and RU. It resolves one populated combat signature player for
legacy and two distinct populated combat players for Python before smoke, so a
stale fixture ID cannot silently turn a meaningful PNG route into a weak
check. This keeps representative routes replay-backed without making ordinary
PRs depend on the full Docker contour.

Request/language/cache boundary checks:

- `init_i18n()` must resolve language from request snapshots without mutating
  `$_GET` or `$_REQUEST`; session/cookie persistence remains the compatibility
  path.
- historical page cache keys must include `current_lang()` without changing the
  source request array; `hlstats.php` should pass an explicit request snapshot,
  not raw `$_REQUEST`, into the cache helper.
- `lang_url()` and the underlying URL helper must preserve unrelated query
  parameters, drop explicitly excluded parameters, and avoid mutating their
  input arrays.
- `hlstats.php` may persist the selected `game` in session, but changing the
  explicit game must clear stale `realgame` before lazy recomputation.

Representative route groups:

- public overview and search pages
- players, clans, maps, weapons, actions, roles, awards
- admin read-only routes
- ingame routes
- graph/image/static renderers
- `status.php`

### Replay-backed web smoke

When a parity/runtime change can affect rendered data:

- bring up the Python comparison web contour
- inspect the affected representative routes on replayed data
- compare data parity before chasing UI-only differences

Representative replay-backed routes:

- `mode=game&game=cstrike&lang=ru`
- `mode=servers&server_id=2&game=cstrike&lang=ru`
- `mode=players&game=cstrike&lang=ru`
- `mode=awards&game=cstrike&tab=daily&lang=ru`
- `mode=awards&game=cstrike&tab=global&lang=ru`
- `mode=awards&game=cstrike&tab=ribbons&lang=ru`
- `mode=playerinfo&lang=ru`
- `sig.php?player_id=<known>&lang=ru`
- `status.php?lang=ru`

The scripted route smoke covers public/game/player/server routes, all three
populated awards tabs, `status.php`, and `sig.php?player_id=<known>`. The
canonical parity runner calls it as legacy `--langs en` and Python
`--langs en ru`, with explicit resolved `--sig-player-id` values; do not apply
the RU marker contract to the original English-only legacy web. Keep broader
browser inspection for layout-specific or route-specific frontend work.

## Stop-and-fix rules

- If the legacy reference cannot replay the same corpus cleanly, stop page
  audit work and fix or log the baseline blocker first.
- If a replay exits without a trustworthy helper summary, discard the partial
  DB and restore before continuing.
- If a route triggers destructive state changes, do not execute it; keep that
  route read-only in the audit.

## Evidence expectations

- Keep command transcripts, SQL counts, compare deltas, and long-form replay
  history in `docs/audits/...`, not in this file.
- Keep `docs/status.md` limited to current state and next actions.
- Keep `docs/plans.md` limited to active milestones, gates, and scope.
