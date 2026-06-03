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
- GeoIP backfill and replay-backed web smoke only when the changed surface can
  affect those outputs

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
  names, and host bind paths. The job runs dual replay, post-replay GeoIP
  backfill, compact DB compare, replay-backed EN/RU smoke, and uploads both
  parity state/audit artifacts and `release-readiness-artifacts`.

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
- heavy parity replay plus post-replay GeoIP backfill and compact compare;
- replay-backed EN/RU web smoke;
- at least one `HLstats metrics:` summary from stdin import or runtime stop;
- benchmark/profile output when parser, storage, replay, DB mode, reconnect,
  lifecycle, or control-plane behavior changed;
- `release-readiness-artifacts` from nightly/manual parity when available.

### Replay / runtime parity

Default rule:

- use direct stdin / worker-local batch import for parity regression
- use UDP replay only for transport/proxy checks, not as the default parity
  route

Required checks when parity-affecting runtime/storage code changes:

- restore a clean comparison baseline
- run the relevant single-log or narrow-window replay first
- run `compare_stats_dbs.py`
- run GeoIP backfill when claiming release-clean parity, validating
  `hlstats_Players`/country/flag output, or checking pages that render GeoIP
  fields; otherwise document raw replay GeoIP-only diffs as pre-backfill
- record residual classification in `docs/audits/legacy-python-parity-20260423/`

Current parity gates:

- `P6d-M1`: `hlstats_Events_TeamBonuses` is closed for the current
  `narrow-1000` contour.
- `P6d-M2`: `ChangeTeam`, `Connects`, `Chat`, and `PlayerActions` are closed
  for the current `narrow-1000` contour.
- `P6d-M3`: `hlstats_Events_Entries` is closed for the current narrow
  contour/default Python path; direct counts are `legacy=0`, `python=0`.
- `P6d-M4`: `hlstats_Players` raw replay compare can show an accepted
  GeoIP-only `country`/`flag` diff because stdin replay does not run
  maintenance GeoIP backfill. Release-clean parity requires post-replay
  `hlstats_awards_py --geoip`, after which `hlstats_Players` should disappear
  from the compare.
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
  `Run-DualContour-1000.ps1 -UseDumpRestore -ReuseValidLegacy
  -MaxImportFiles 1000`, post-replay `hlstats_awards_py --geoip`, and
  `compare_stats_dbs.py --max-examples 20`, with artifacts retained from
  `docs/audits/legacy-python-parity-20260423/` and
  `scripts/replay_baseline/comparison/.parity-state/`.
- Perl remains required for reference behavior, baseline regeneration, targeted
  investigation, and the heavy acceptance replay. It is not required for every
  routine PR when fixture inputs and the accepted legacy contour are unchanged.

Minimum replay validation loop:

- targeted `pytest` for touched code
- single-log parity or narrow contour replay
- automatic `30/30` guard-window pass for point fixes when an event anchor is
  available
- `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
- post-replay `hlstats_awards_py --geoip` when claiming release-clean parity or
  validating `hlstats_Players`/country/flag output
- evidence update in `bug-plan.md`, `issues.jsonl`, or the relevant audit note

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
The heavy nightly parity workflow additionally runs
`python scripts/replay_baseline/web_route_smoke.py --base-url
http://127.0.0.1:8281 --langs en ru` after replay and GeoIP backfill, so
representative EN/RU routes are checked against replay-backed data without
making ordinary PRs depend on the full Docker contour.

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
- `mode=playerinfo&lang=ru`
- `sig.php?player_id=<known>&lang=ru`
- `status.php?lang=ru`

The scripted route smoke covers the first three public routes plus
`status.php` and `sig.php?player_id=<known>` for both `en` and `ru`; use
`--sig-player-id` when the replay fixture's known player anchor differs from
the default. Keep broader browser inspection for layout-specific or
route-specific frontend work.

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
