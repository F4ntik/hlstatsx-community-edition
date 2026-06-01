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
- Until Phase 3 removes the package coupling, the `hlstats_py` CI job must keep
  the explicit `PYTHONPATH=scripts:scripts/proxy_daemon_py` bridge rather than
  pretending the package boundary is already autonomous.
- Reconnect regression coverage lives in `scripts/proxy_daemon_py/tests/test_db.py`
  and pins lazy connect, disabled ping, successful `ping(reconnect=False)`, and
  failed-ping reconnect behavior. `scripts/hlstats_py/tests/test_storage.py`
  pins the stdin batch skip-ping bridge that currently consumes that adapter.
- `.github/workflows/nightly-parity.yml` is the Phase 1 scheduled/manual
  placeholder for parity automation. It runs lightweight replay helper smoke;
  the full Docker-backed legacy-vs-Python replay gate remains a Phase 7
  promotion target.

Boundary checks:

- `hlstats_py.runtime --stdin` CLI contract when the runtime flags or import
  path change
- `scripts/hlstats_ftp_py` only when FTP/replay ordering logic changes
- `scripts/import_bans_py` only when maintenance CLI behavior changes

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
container.

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
- `status.php?lang=ru`

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
