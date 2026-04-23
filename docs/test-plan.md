# Test Plan: HLstatsX Legacy vs Python Replay

This test plan applies to the Python migration donor lane only.

- Product-level Python+i18n validation now lives in
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n`.
- Upstream RU web PR validation stays in
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n`.

## Objective

Validate the Python migration by replaying the same production log fixtures
into two isolated local stacks derived from one common reset baseline and
comparing the resulting database state.

## Test levels

- Environment validation:
  local Docker stack boots and web admin loads.
- Baseline validation:
  post-reset dump restores cleanly.
- Replay validation:
  legacy first consumes the intended input set without fatal errors, then
  Python is held to the same input fixture.
- Result validation:
  database diffs identify parity or concrete mismatches.

## Critical fixtures

- Production-like legacy compose stack.
- Production-derived MariaDB dataset.
- User-triggered admin reset baseline dump.
- Production game logs from the CS server.
- Full local corpus snapshot as of `2026-04-21`:
  `1420` gameplay `L*.log` files from `L0402000.log` to `L0421033.log`.
- Current parity fixture set:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`,
  `L0417065.log`.

## Smoke coverage

- Legacy stack responds on local web port.
- Full-stack test web contour serves the main page without the legacy updater
  notice; the test image removes `web/updater` intentionally so smoke runs do
  not depend on manual post-update cleanup.
- Legacy daemon binds local UDP replay port.
- DB accepts application connections.
- After reset, admin pages remain functional.
- Restored legacy baseline starts from `0` players and `0` frag events.
- Legacy offline replay of a real production log recreates player/event rows.
- Python worker and proxy both start successfully after a baseline restore.
- Python replay helper preserves the logical source server identity
  `172.19.0.1:27015`.
- Python replay reaches the tail of `L0415056.log` without dropping the final
  stat packets.
- Python worker can import one legacy `.log` directly via `hlstats_py.runtime --stdin`
  when `--server-ip` / `--server-port` are supplied explicitly.

## Acceptance gates

- Baseline dump can be restored repeatedly.
- Legacy smoke passes on a clean restored baseline before any Python parity
  claim is considered.
- Replay completes on both stacks.
- Core statistical tables either match or produce a targeted diff report.
- Diff reporting suppresses runtime-only metadata noise so each iteration
  isolates replay-induced behavioural mismatches.
- Any Python mismatch is localizable to specific tables, keys, and code paths.
- The baseline loop stays canonical:
  restore baseline -> legacy smoke -> Python replay -> DB diff -> fix -> repeat.
- The compact replay diff is authoritative only for replay-semantic fields;
  legacy `--stdin` import-finalize alias/session metadata is validated
  separately if exact flush emulation is ever required.
- Legacy offline `--stdin` non-ASCII chat corruption is treated as transport
  noise in the compact diff by normalizing chat payloads to the legacy-safe
  comparison form instead of changing Python runtime storage fidelity.
- The smaller clean parity subset and the widened full-corpus load are tracked
  separately: a clean subset gate does not imply full-history parity.

## Comparison policy

- Primary:
  player, event, weapon, server, ranking, clan, trend, and other HLstats
  statistical tables affected by replayed logs.
- Secondary:
  runtime-only or volatile fields such as heartbeat timing, transient state,
  and execution timestamps.
- Ignore by default:
  proxy daemon heartbeat state, container/runtime timestamps, and other fields
  unrelated to the statistical result of replayed logs.
- Current compact diff focus:
  player/event/action/server/weapon tables that move under replay, while
  runtime/proxy metadata remains out of scope.

## Negative cases

- Corrupt or partial log transfer from production.
- Replay abort caused by malformed lines.
- Python runtime rejecting raw legacy log format without adaptation.
- Reset baseline leaving non-empty event/history tables.
- Python worker or proxy failing to start against the restored comparison DB.
- Python replay path preserving the wrong source server identity and therefore
  failing to match `hlstats_Servers`.
- Python replay overcounting warmup or restart-round events that legacy ignores
  before the live round begins.
- Legacy offline `--stdin` replay corrupting non-ASCII chat payloads, which can
  look like a Python parity failure even when gameplay semantics match.
- Python heatmap generation lacking the required external
  `heatmaps/src/<game>/<map>.jpg` map-pack assets, which blocks real-map parity
  even when the batch CLI itself is implemented.

## Release readiness for parity work

- Legacy baseline stack is stable and documented.
- Baseline restore is automated or scripted.
- Legacy replay smoke is repeatable and can be rerun after every restore.
- Python contour startup is stable and repeatable after every restore.
- Replay workflow is deterministic enough for repeated code-fix cycles.
- Diff output is concise enough to guide Python fixes without manual DB spelunking.
- Current single-log replay-semantic parity gate is clean on `L0415056.log`.
- Current confirmed clean multi-fixture parity set:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`,
  `L0417065.log`.
- Remaining non-goal for this gate:
  exact legacy `--stdin` import-finalize alias/session metadata
  (`connection_time`, `lastuse`, `numuses`) is not required for gameplay
  parity and should be tracked only as a separate follow-up if it becomes
  product-relevant.

## Follow-up validation backlog

- Exact Python `--stdin` mode:
  compare one identical `.log` imported through `hlstats.pl --stdin` and the
  current Python `hlstats_py.runtime --stdin` path, including import-tail
  metadata only when that parity target is explicitly enabled.
- `HLStatsFTP` port:
  validate `mtime` checkpointing, skipping the active tail file, idempotent
  repeated runs, and delegation into Python `--stdin` without Perl.
- `ImportBans` port:
  validate SteamID normalization, multi-source ban aggregation, and the chosen
  sync policy (`ban`-only parity versus `ban/unban` upgrade).
- `/metrics` export:
  validate scrape stability, counter/gauge semantics, and zero impact on the
  existing UDP/runtime behaviour.
- Heatmaps batch CLI:
  validate `python -m hlstats_py.heatmaps` against 1-2 real maps with an
  installed legacy map-pack, compare the generated `*-kill.jpg`,
  `*-kill-thumb.jpg`, and overlay cache behaviour against legacy PHP output,
  and confirm the PHP web pages continue to resolve the published assets
  without path/name changes.

---

## Code Review Findings (Cascade Agent)

**Agent:** Code Review Agent (Cascade)  
**Date:** 2026-04-21  
**Scope:** Python runtime, protocol, storage, events; comparison with legacy Perl  
**Status:** Pending user triage – see decision checklist below

### Immediate Next Steps (High Priority)

| # | Item | Location | Risk if not addressed | User Decision |
|---|------|----------|----------------------|---------------|
| 1 | Document headshot coordinate nulling logic | `storage.py:437-438` | Future maintainers may treat as bug | [ ] Accept [ ] Reject [ ] Modify |
| 2 | Document `--stdin` finalize omissions (`connection_time`, `numuses`, `lastuse`) | `storage.py:347-351` | Misalignment with legacy behavior expectations | [ ] Accept [ ] Reject [ ] Modify |
| 3 | Add per-table diff logging to `compare_stats_dbs.py` | `scripts/replay_baseline/` | Cannot localize 18-table drift without manual DB spelunking | [ ] Accept [ ] Reject [ ] Modify |
| 4 | Review Steam ID normalization for `STEAM_ID_LAN` / `BOT` edge cases | `protocol.py:279-282` | Player-cache misses on legacy LAN / bot logs | [ ] Accept [ ] Reject [ ] Modify |
| 5 | Remove dead `reason` parameter from `_build_message` | `events/handlers.py:48-72` | Dead code accumulation | [ ] Accept [ ] Reject [ ] Modify |
| 6 | Add threaded stress test for query ordering under concurrency | `tests/test_storage.py` | Race conditions undetected in current fake-cursor tests | [ ] Accept [ ] Reject [ ] Modify |

### Additional Recommendations

#### Security & Stability
- [ ] **Control host validation too narrow** – `_is_local_control_host` only allows `127.0.0.1`, `::1`, `localhost`. Docker control packets from `172.18.0.1` / `192.168.x.x` may be rejected. Legacy Perl likely did not validate source IP or used `$opt_proxy_ip`.
- [ ] **No healthcheck endpoint** – Python runtime lacks `/health` or `/ready`; needed for K8s/Docker Compose.
- [ ] **DB reconnect logic** – `SyncDatabaseAdapter.connect()` called once at startup; if MariaDB restarts, worker fails. Legacy DBI may have implicit reconnect.

#### Architecture / Process
- [ ] **Connection pooling** – Every `_connection()` call goes through adapter synchronously; higher overhead than Perl DBI single-handle. Document as known operational delta or implement pooling.
- [ ] **Unified Dockerfile for worker** – Product lane lacks `Dockerfile` for `hlstats_py.runtime`; currently requires ad-hoc `PYTHONPATH`.
- [ ] **Rollback tags** – Add `scripts/build-images.sh` or `docker-bake.hcl` for versioned runtime images.

### Open Questions for User

1. Is exact `--stdin` import-finalize metadata parity (`connection_time`, `lastuse`, `numuses`) required for your product use case, or is gameplay-semantics parity sufficient?
2. Should the 18-table full-corpus drift be the immediate priority, or should focus remain on the compact 5-fixture gate?
3. Do you want the Python runtime to support the same IP-based control validation as legacy Perl, or relax it for Docker environments?

**Next Action Required:** User to tick decision boxes above and route accepted items to implementation agent.
