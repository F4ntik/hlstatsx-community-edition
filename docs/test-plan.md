# Test Plan: HLstatsX Legacy vs Python Replay

## Objective

Validate the Python migration by replaying the same production weekly logs into
two isolated local stacks derived from one common reset baseline and comparing
the resulting database state.

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
- Weekly production game logs from the CS server.
- Current parity fixture set:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`,
  `L0417065.log`.

## Smoke coverage

- Legacy stack responds on local web port.
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
  future Python `hlstats_py --stdin` path, including import-tail metadata when
  that parity target is explicitly enabled.
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
