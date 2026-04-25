# Test Plan: Standalone Python+i18n Product Lane

## Objective

Validate that the integrated product repository works as one coherent stack:

- Python is the default runtime and operational path
- the PHP frontend renders through the explicit EN/RU i18n runtime
- replay, heatmaps, and core web flows still behave correctly after the donor
  layers are combined

## Validation scope

- In scope:
  - `hlstats_py` runtime and CLI entrypoints
  - `proxy_daemon_py` runtime and targeted tests
  - replay-baseline helpers and compact diff tooling
  - Python heatmap batch generation
  - explicit EN/RU frontend runtime and representative pages
  - language persistence and fallback behavior
  - integrated product docs and runbooks
- Out of scope:
  - upstream RU PR reviewability
  - donor-branch-only cleanup that does not affect this product repo
  - third locale rollout

## Test levels

### Python / tooling

- targeted `pytest` for:
  - `scripts/hlstats_py/tests`
  - `scripts/proxy_daemon_py/tests`
  - `scripts/replay_baseline/tests`
- exact `--stdin` product-boundary check for one representative legacy log
- targeted validation for `HLStatsFTP` (implemented as [`scripts/hlstats_ftp_py`](../scripts/hlstats_ftp_py/README.md)) and the future Python `ImportBans` replacement once it lands

### Replay / runtime

- prune disposable replay noise from `scripts/replay_baseline/artifacts`
  before a production-sized run:
  - remove `*.log` files smaller than `15 KB`
  - confirm the retained working corpus count afterward
- restore baseline
- verify the Python restore bootstrap:
  - `172.19.0.1:27015` still exists for canonical parity fixtures
  - `37.230.137.48:27015` exists exactly once as `game='cstrike'`
  - the replay server has copied `hlstats_Servers_Config` rows
  - `Proxy_Daemons` still points to `hlstatsx-python-worker:28000`
  - the pre-replay DB is still clean enough to trust the next replay run
    (`0` players / `0` frags / `0` history rows after restore)
- run legacy comparison smoke where needed for the parity reference
- run Python replay against the integrated repo tooling:
  - single-file smoke for one retained `37.230.137.48:27015` log
  - directory corpus replay through `scripts/replay_baseline/replay_python_log.py <dir> --server-identity 37.230.137.48:27015`
  - for production-sized parity runs, prefer the FTP contour helper
    `scripts/replay_baseline/comparison/python/Run-ContourFtpArtifacts.ps1`
    to avoid slow host-to-worker UDP replay; preserve the same corpus and
    server identity
  - for dual-contour parity reruns, use staged orchestration from
    `scripts/replay_baseline/comparison/Run-DualContour-1000.ps1`:
    - `-OnlyStage python_import -ResumeLatest -Stack python` for Python-only rerun
    - `-OnlyStage legacy_import -ResumeLatest -Stack legacy` for Legacy-only rerun
    - `-OnlyStage baseline_restore` + `-OnlyStage preflight` + import stage for
      fast restore+replay in one chosen stack
- run `compare_stats_dbs.py`
- add parser/runtime parity fixtures beyond the compact replay diff:
  - Steam/auth normalization for `STEAM_1:*`, `STEAM_2:*`, and `[U:1:n]`
  - pending/unknown connect handling for `UNKNOWN`, `PENDING`, and
    `VALVE_ID_LAN`
  - repeated property parsing cases that rely on Perl `getProperties`
  - connect-address parsing that should only strip ports from IPv4 `host:port`
- bring up the Python comparison web contour on `http://127.0.0.1:8281/hlstats.php`
  and inspect representative RU pages on replayed data:
  - `mode=game&game=cstrike&lang=ru`
  - `mode=servers&server_id=2&game=cstrike&lang=ru`
  - `mode=players&game=cstrike&lang=ru`

### Full legacy-vs-Python parity audit

- use `docs/audits/legacy-python-parity-20260423/README.md` as the audit
  runbook and write all findings under that directory
- prepare both comparison contours from the same baseline:
  - legacy reference: `http://127.0.0.1:8181/hlstats.php`
  - Python/current target: `http://127.0.0.1:8281/hlstats.php`
  - both DBs contain `37.230.137.48:27015` as `game='cstrike'`
  - both DBs have copied `hlstats_Servers_Config` for that server
- replay the same retained corpus into both contours:
  - Python replay uses `scripts/replay_baseline/replay_python_log.py`
  - legacy replay must use an equivalent streaming directory path before its
    full-corpus output is accepted as the reference
  - if legacy replay exits without a final helper summary, the DB is partial
    and must be restored before any retry or comparison
  - for the current blocker, rerun from a clean legacy restore with the patched
    `scripts/replay_baseline/replay_legacy_log.py`; if it fails again near
    `L0107052` / `L0107054`, rerun a narrowed failure window with
    `--daemon-output inherit` and save the Perl daemon stderr
  - record processed/skipped/error counts, elapsed time, files/sec, and
    datagrams/sec or lines/sec in
    `docs/audits/legacy-python-parity-20260423/performance.md`
- capture DB parity before page conclusions:
  - `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
  - save output in
    `docs/audits/legacy-python-parity-20260423/runtime-db-diff.md`
  - ensure Python `country/flag` are backfilled before diff classification:
    `python -m hlstats_awards_py --configfile scripts/hlstats.conf --geoip`
  - classify DB drift as actionable, accepted legacy difference, or downstream
    blocker
- generate `route-inventory.md` with one row per route:
  - owning mini-agent
  - legacy URL
  - Python EN URL
  - Python RU URL where applicable
  - required entity id
  - read-only/destructive status
  - expected data anchor
- split route checks across mini-agents:
  - public overview lists
  - player and clan details
  - game entities and awards
  - communication, search, help, and voice routes
  - admin read-only pages
  - ingame pages
  - render/static/graph endpoints
  - runtime/DB parity
- every route check must record:
  - HTTP status and final URL
  - PHP fatal/warning/SQL error text if present
  - first stable table rows or empty-state text
  - link/sort/pagination behavior
  - data parity between legacy and Python EN
  - data parity between Python EN and Python RU
  - unexpected English UI leaks in Python RU
- every finding must be appended to
  `docs/audits/legacy-python-parity-20260423/issues.jsonl` with:
  - severity `P0` / `P1` / `P2` / `P3`
  - route URLs
  - expected and actual behavior
  - evidence
  - exact repro steps
  - normalization or accepted-difference notes
- final audit gate:
  - `bug-plan.md` groups issues by root cause and severity
  - duplicates are merged
  - accepted legacy differences are separate from actionable bugs
  - every actionable bug has a proposed validation route or command

Current legacy replay blocker validation:

- `legacy-full-corpus-replay-20260423.log` records the first failed full-run
  attempt: `1097` queued files, last queued `L0107052.log`, then
  `[Errno 22] Invalid argument`, with no final `Replay summary`.
- The failed run is not a valid reference. Do not run
  `compare_stats_dbs.py` against that partial DB.
- A fixed attempt is valid only if the helper prints final
  `processed/skipped/errors/lines/elapsed/throughput`, the process exits zero,
  and post-run DB counts are recorded.
- If the narrowed failure-window replay reproduces the issue, classify it as
  one of:
  helper pipe handling, daemon crash/limit, malformed/corpus-specific input,
  Docker/runtime resource issue, or accepted legacy limitation.

### P6e architecture-parity validation (runtime + awards + geoip)

- runtime map lifecycle parity:
  - confirm parser/handler captures both:
    - `Loading map "<map>"`
    - `Started map "<map>"`
  - confirm projected runtime state updates current map before next gameplay writes
  - SQL checks after replay:
    - `hlstats_Events_Frags` no longer dominated by `map=''`
    - `hlstats_Maps_Counts` contains real maps (`de_dust2`, `de_nuke`, etc.)
- awards/ribbons policy parity:
  - strict/default mode remains legacy-compatible (`hideranking = 0` behavior)
  - explicit replay-safe mode yields awards/ribbons without manual
    `UPDATE hlstats_Players SET hideranking=0`
  - SQL checks:
    - `hlstats_Players_Awards` row count `> 0` in replay-safe run
    - `hlstats_Players_Ribbons` row count `> 0` in replay-safe run
- geoip operational behavior:
  - strict/default mode fails clearly when configured GeoIP source is missing
  - replay-safe mode logs warning and continues awards/ribbons processing
  - if GeoIP source is available, verify `flag/country` backfill rows increase
- recommended command sequence:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 500`
  - `python -m hlstats_awards_py --date 2026-01-04 -a -r --replay-mode`
  - optional replay-safe GeoIP run:
    - `python -m hlstats_awards_py --date 2026-01-04 -a -r -g --replay-mode`
  - strict-mode behavior check (optional, expected fail without GeoIP source):
    - `python -m hlstats_awards_py --date 2026-01-04 -a -r -g`

### Frontend / i18n

- syntax checks for the integrated PHP runtime and representative pages
- targeted syntax checks for every file touched during the frontend i18n fix
  pass
- EN/RU smoke for the highest-value routes:
  - `mode=contents`
  - `mode=search`
  - `mode=players`
  - `mode=playerinfo`
  - `mode=servers`
  - `mode=help`
  - `mode=admin`
  - `status.php`
- EN/RU smoke for the reviewed secondary surfaces once their remediation lands:
  - representative graph/image renderers:
    - `show_graph.php`
    - `trend_graph.php`
    - `sig.php`
  - representative voice routes:
    - `mode=teamspeak`
    - `mode=ventrilo`
  - representative ingame routes:
    - `players`
    - `maps`
    - `servers`
    - `status`
    - `load`
- prioritize replay-backed backend/error surfaces once the 8281 contour is up:
  - `status.php?lang=ru`
  - `show_graph.php`
  - `sig.php`
  - `hlstats.php?mode=playerhistory&lang=ru`
  - `hlstats.php?mode=updater&lang=ru`
  - `hlstats.php?mode=admin&task=options|tools_adminevents|tools_perlcontrol|tools_settings_copy&lang=ru`
  - `ingame.php?game=<replayed_game>&mode=status|load|players|clans|mapinfo|weaponinfo|accuracy&lang=ru`
- verify country/flag output explicitly after replayed connect events:
  - if GeoIP is expected, `hlstats_Players.country` / `flag` must populate
  - run `python -m hlstats_awards_py --configfile scripts/hlstats.conf --geoip`
    (or the equivalent contour-local config path) after replay/import so the
    Python maintenance step can backfill `flag`, `country`, `city`, `state`,
    `lat`, and `lng`
  - if the command fails because GeoLiteCity tables or `GeoLite2-City.mmdb`
    are missing, record that as an operational blocker instead of silently
    accepting `Unknown Country`
- language persistence checks:
  - `?lang=ru`
  - cookie/session persistence
  - invalid `?lang=zz` must not overwrite a valid persisted language
  - fresh request without language state must fall back to EN
- catalog integrity checks:
  - EN/RU keysets stay aligned for touched keys
  - known abbreviations and placeholder-bearing strings do not accidentally
    collide with `:placeholder` interpolation
- raw-literal regression checks:
  - grep the touched files for newly added hardcoded English UI text
  - confirm repeated labels are routed through shared keys/helpers instead of
    reintroduced inline

### Heatmaps

- generate a smoke output from synthetic/local assets
- validate at least one real map-pack-backed run once the required assets are
  installed
- confirm the PHP web layer still resolves the published asset names

## Acceptance gates

- Python entrypoints are the documented default runtime path.
- Representative Python tests pass or any failures are explicitly documented.
- Representative PHP syntax checks pass on the integrated files.
- Representative EN/RU smoke flows render without known blocker defects.
- Touched frontend routes no longer show known reviewed English leaks unless
  they are explicitly accepted as legacy-only.
- Replay tooling still performs the canonical baseline loop.
- Python parser/runtime behavior either matches the required legacy auth/connect
  semantics or the accepted differences are explicitly documented.
- Product expectations around GeoIP/country resolution are explicit; this lane
  must not silently ship with `countrydata=1` while Python GeoIP backfill is
  unrun or its GeoLite inputs are unavailable.
- Product docs describe the integrated repo rather than only donor-lane context.

## Release-readiness checklist

- [x] Python runtime path is validated in this repo
- [x] Replay-baseline loop is validated in this repo
- [x] Replay corpus under `15 KB` can be pruned from the working artifacts set
- [x] Python restore bootstrap seeds the second replay server `37.230.137.48:27015`
- [x] Python comparison web uses the integrated product `web/` tree for RU i18n
  inspection on replayed data
- [x] Reviewed frontend i18n backlog is retired on touched routes
- [x] EN/RU catalogs are aligned for the touched keyspace
- [x] Known parser blocker in `web/pages/ingame/motd.php` is removed
- [ ] Exact `--stdin` product boundary is documented
- [x] `HLStatsFTP` Python replacement is landed (`scripts/hlstats_ftp_py` → `hlstats_py.runtime --stdin`)
- [ ] `ImportBans` Python replacement is landed or explicitly called out as a release blocker
- [ ] Heatmap generator is validated on real map assets
- [x] EN core pages render correctly
- [x] RU core pages render correctly
- [x] Language persistence and fallback behave correctly
- [ ] Full legacy-vs-Python parity audit is completed and summarized in
  `docs/audits/legacy-python-parity-20260423/bug-plan.md`
- [ ] `P6e` architecture-parity remediation is validated (runtime map-flow,
  replay-safe awards policy, GeoIP strict-vs-replay behavior)
- [ ] Product repo can be handed off without relying on donor-branch chat history

---

## Code Review Findings (Cascade Agent)

**Agent:** Code Review Agent (Cascade)  
**Date:** 2026-04-21  
**Scope:** Integrated product lane (Python + i18n); donor-layer integration gaps  
**Status:** Pending user triage – see decision checklist below

### Immediate Next Steps (High Priority)

| # | Item | Location | Risk if not addressed | User Decision |
|---|------|----------|----------------------|---------------|
| 1 | Add root `pyproject.toml` for package discoverability | Repo root | PYTHONPATH hacks required for tests/runtime | [ ] Accept [ ] Reject [ ] Modify |
| 2 | Document exact `--stdin` product boundary (finalize omissions) | `docs/` or inline | Unclear what parity is guaranteed vs. explicitly skipped | [ ] Accept [ ] Reject [ ] Modify |
| 3 | `HLStatsFTP` Python port | `scripts/hlstats_ftp_py` | Landed; Perl script deprecated for this flow | [x] Done |
| 4 | Add `ImportBans` Python port to release blockers or land it | Backlog checklist | Product requires Perl for operational flows | [ ] Accept [ ] Reject [ ] Modify |
| 5 | Address 18-table full-corpus drift (inherit from donor lane) | Inherited from `hlstatsx-community-edition` | Production-scale behavior diverges from compact fixture gate | [ ] Accept [ ] Reject [ ] Modify |
| 6 | Add per-table diff logging to `compare_stats_dbs.py` | Inherited tooling | Cannot localize drift without manual DB spelunking | [ ] Accept [ ] Reject [ ] Modify |

### Additional Recommendations

#### Integration Gaps (Inherited from Donor Lanes)
- [ ] **Headshot coordinate nulling undocumented** – Inherited from Python donor; behavior in `storage.py` needs inline comment.
- [ ] **Superglobal mutation in i18n** – Inherited from RU donor; `init_i18n()` mutates `$_GET` / `$_REQUEST`.
- [ ] **Dictionary key drift** – Inherited from RU donor; EN/RU dictionaries may have mismatched keysets over time.
- [ ] **Steam ID normalization gaps** – Inherited from Python donor; `STEAM_ID_LAN` / `BOT` handling vs. legacy Perl needs verification.

#### Operational / Observability
- [ ] **Healthcheck endpoint** – Python runtime lacks `/health` or `/ready` for K8s/Docker Compose.
- [ ] **Control host validation** – `_is_local_control_host` too narrow for Docker networks (only allows loopback).
- [ ] **DB reconnect logic** – `SyncDatabaseAdapter` connects once at startup; does not survive MariaDB restart.
- [ ] **Unified Dockerfile** – No `Dockerfile` for `hlstats_py.runtime` in product repo; requires ad-hoc PYTHONPATH.

#### Testing & Release
- [ ] **Full-corpus regression test** – CI job that runs compact fixture gate automatically (restore → legacy smoke → Python replay → diff assert).
- [ ] **Heatmap real-map parity** – Blocked on external map-pack assets; need `scripts/fetch-map-assets.sh` or documented source.
- [ ] **Rollback tagging** – No `scripts/build-images.sh` or `docker-bake.hcl` for versioned releases.

### Open Questions for User

1. Is the 18-table full-corpus drift a release blocker, or is the compact 5-fixture gate sufficient for initial product handoff?
2. Should `HLStatsFTP` and `ImportBans` be ported to Python before product release, or is Perl compatibility acceptable for operational flows?
3. Do you want the product repo to include a unified `docker-compose.yml` that replaces the donor-lane split-stack setup?
4. Should the Python runtime relax control-host validation for Docker environments, or maintain strict loopback-only policy?

**Next Action Required:** User to tick decision boxes above; route accepted items to implementation agent. Inherited items from donor lanes should be fixed in donor repos first, then re-imported to product lane.
