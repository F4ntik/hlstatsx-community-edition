# Release Readiness, Observability, and Profiling

This runbook defines the Phase 9 release handoff contract for the integrated
Python+i18n product lane.

## Runtime Metrics

`hlstats_py` emits a stable one-line metrics summary through the normal daemon
logger at runtime stop and after finite stdin imports:

```text
HLstats metrics: reason='stdin import complete' elapsed_seconds=... events_processed=... events_per_second=... stdin_records=... udp_datagrams=... packets_dropped=... flush_attempts=... flush_failures=... control_commands_total=... control_commands_rejected=... events_by_category=... control_commands_by_type=...
```

Use this as the current structured metrics contract. A Prometheus `/metrics`
exporter is not implemented yet; do not document one as available until the
daemon exposes it.

Important counters:

- `events_processed`: events dispatched to storage.
- `events_per_second`: runtime throughput from process-local counters.
- `stdin_records`: finite import records accepted for a known server.
- `udp_datagrams`: inbound UDP datagrams seen by the worker.
- `packets_dropped`: unknown source, invalid envelope, bad proxy key, or
  unknown stdin source drops.
- `flush_attempts` / `flush_failures`: pending storage flush health.
- `control_commands_total` / `control_commands_rejected`: control-plane
  activity and rejected mutating loopback commands.
- `events_by_category`: event mix for replay/import triage.
- `control_commands_by_type`: actual `hlstats_py` command surface, including
  `HEARTBEAT`, `SERVERLIST`, `RELOAD`, and `KILL`.

For `proxy_daemon_py`, use the existing log and heartbeat runbooks. Its
control surface remains `HEARTBEAT`, `SERVERLIST`, and `RELOAD`; do not add a
`KILL` release expectation for the proxy daemon.

## Profiling And Benchmarks

Use the smallest benchmark that answers the release question.

Parser throughput:

```powershell
$env:PYTHONPATH = "scripts"
python scripts/hlstats_py/benchmarks/benchmark_parser.py `
  scripts/replay_baseline/artifacts/parity-traces/smoke-rakza-runner/input `
  --backend python
```

For a reproducible side-by-side profile of the existing `python` and `native`
parser paths without touching a DB, use the bounded helper and a fresh output
directory (see [`rust-parser-boundary.md`](rust-parser-boundary.md) for the
exact output contract):

```powershell
$env:PYTHONPATH = 'scripts'
$run = Join-Path $env:TEMP 'hlstats-processing-profile-20260718-r1'
python scripts/replay_baseline/profile_processing_subset.py `
  scripts/replay_baseline/artifacts/parity-trace-rakza-window/L0105062.log `
  --max-files 1 --backends python native --output-dir $run
```

The helper writes `processing-profile.json`, per-backend `.pstats`, and
top-function reports under `$run`; it never opens a database.  It is suitable
for processing evidence, not DB-write evidence.

Direct import profile:

```powershell
$env:PYTHONPATH = "scripts;scripts/replay_baseline"
python scripts/replay_baseline/direct_import_artifacts.py `
  --profile `
  --max-files 1 `
  --artifacts-dir scripts/replay_baseline/artifacts `
  --configfile scripts/replay_baseline/comparison/python/hlstats.conf
```

The profiled import writes `perf-profile.txt` plus replay/import summaries
under `scripts/replay_baseline/artifacts/`. Keep those files with the release
candidate evidence when the run is used for release signoff.

For SQL-write profiling, use an explicitly disposable benchmark DB and set
`HLSTATS_DB_WRITE_TRACE_PATH` plus `--audit-dir` to a fresh run directory; the
exact command, expected outputs, and safety boundary are in
[`rust-parser-boundary.md`](rust-parser-boundary.md).  Never run that command
against an accepted parity DB or evidence directory.

Write-path smoke benchmark:

```powershell
$env:PYTHONPATH = "scripts;scripts/replay_baseline"
python scripts/replay_baseline/bench_write_path.py --mode subprocess --lines 300
```

The preserved full-state one-log SQL evidence in
`docs/audits/legacy-python-parity-20260423/performance-db-sql-opt-20260718-sql-write-opt-r1/`
measured the stdin-only history ensure-row cache at 4,613 to 2,519 logical
calls and 4.457 s to 2.071 s for 2,287 records. It is development evidence,
not a replacement for an accepted `narrow-1000` contour.

The bounded Statsme counter-delta slice has retained release evidence under
`docs/audits/legacy-python-parity-20260423/performance-db-sql-opt-narrow-1000-20260718-statsme-bench-r1/`.
Its 427 explicit product tests, prefix r2 and fresh no-reuse narrow r1 parity,
and product-path timing record the exact 1,000-file manifest SHA and anchors.
The profile reduced physical `Connection.query` calls from 124,630 to 60,785,
but `462.691 s` profiled and `246.362 s` isolated-host unprofiled wall samples
are not matched incremental-speed evidence. Do not promote this slice on wall
time alone; use its accepted narrow parity and GeoIP-only residual classification
as the correctness evidence. The product-path legacy/Python `1.108x` is a
same-corpus elapsed ratio only; see
`docs/audits/legacy-python-parity-20260423/runtime-product-timing-20260718-statsme-product-timing-r1-legacy-reference.md`.

Ephemeral Docker benchmarks remain optional release diagnostics:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\Run-WriteBenchEphemeral.ps1

powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\Run-LogFilesBenchEphemeral.ps1 -FileCount 300
```

## Release Candidate Checklist

Before calling a release candidate ready, collect fresh evidence for:

- product CI: `proxy_daemon_py`, `hlstats_py`, `replay_baseline`, PHP lint,
  web i18n smoke, and docs sanity check;
- heavy parity acceptance:
  fresh `Run-DualContour-1000.ps1 -UseDumpRestore -MaxImportFiles 1000`
  without `-ReuseValidLegacy`;
- its retained release-clean maintenance receipt: historical `UseTimestamp=1`,
  inactive/awards/ribbons/GeoIP actions, compact DB compare, legacy
  EN-reference route smoke, and Python EN/RU product route smoke;
- `hlstats_py` metrics summary from either stdin import or runtime shutdown;
- benchmark/profile output when the release changes parser, storage, replay,
  DB mode, reconnect, lifecycle, or control-plane behavior;
- updated `docs/status.md` and `docs/test-plan.md` entries for the release
  evidence.

Store detailed replay transcripts and parity evidence under
`docs/audits/legacy-python-parity-20260423/`. Keep long benchmark/profiling
outputs in `scripts/replay_baseline/artifacts/`; nightly CI uploads matching
release-readiness artifacts when present.

## Modern Heatmap Explorer rollout notes

Current status on 2026-09-02: exact implementation commit
`44f3af97db46107f3ab9b595b3c32b3e5c2c7986` is `SOURCE-READY`, locally
`RUNTIME-ACCEPTED`, and `RELEASE-READY` only as a local candidate. Coordinate
persistence, MyISAM install/update/performance, authenticated admin, cache
identity and compatibility evidence remain accepted from the unchanged
DB/API boundary. Fresh source regression, EN/RU browser, objective
Color/Mono/Difference pixel visibility, exact restoration and independent
`ship` review close the sparse-layer correction; see
`docs/audits/modern-heatmap-explorer/runtime-acceptance.md`. This is not a
production deployment, publication, or production release acceptance record.

No Steam/Valve asset is shipped. Local GoldSrc research validated overview
coordinates, while the release uses repository images with reversible map-only
Color/Mono grading. Optional GoldSrc import needs separate licensing and
feature acceptance.

`HeatmapExplorerBeta` meanings:

- `0`: legacy v1 Canvas/JPEG only; direct `v=2` route disabled
- `1`: default legacy; explicit `heatmap_explorer=1` opt-in mounts v2
- `2`: default v2; explicit `heatmap_legacy=1` rollback mounts v1

Direct rollback path:

```sql
UPDATE hlstats_Options
SET value='0'
WHERE keyname='HeatmapExplorerBeta';
```

Read back the same row immediately after the update and verify that the next
page request returns to the legacy `heatmap_points.php` path without `v=2`.

Promotion sequence:

```text
deploy with mode 0 -> migrate/readback -> mode 1 internal opt-in
-> mode 1 public beta -> mode 2 default
```

Rollback to mode `0` when, in a 15-minute sample, any of the following occurs:

- v2 `5xx` exceeds `0.5%`
- warm p95 exceeds `600 ms`
- cold p95 exceeds `3000 ms`
- inspect p95 exceeds `600 ms`
- a scene is biased or truncated
- an accepted map drops below its recorded coverage

Structured request log shape for `web/heatmap_points.php`:

- prefix: `hlstats_heatmap `
- JSON fields: `version`, `operation`, `game`, `map`, `windowClass`, `lens`,
  `floor`, `rowsRead`, `binsReturned`, `rawPayloadBytes`, `queryMs`,
  `totalMs`, `cache`, `xyCoverage`, `zCoverage`, `projectionCoverage`,
  `state`, `fallbackReason`

Illustrative safe line:

```text
hlstats_heatmap {"version":2,"operation":"scene","game":"cstrike","map":"de_dust2","windowClass":"365d","lens":"overview","floor":"all","rowsRead":175,"binsReturned":0,"rawPayloadBytes":1556,"queryMs":12.5,"totalMs":15.4,"cache":"miss","xyCoverage":1,"zCoverage":1,"projectionCoverage":0.08571428571428572,"state":"weak_projection","fallbackReason":"weak_projection"}
```

Public deployment notes:

- `inspect` requests bypass cache and emit `Cache-Control: no-store`; apply a
  reverse-proxy per-IP rate limit on inspect traffic before public rollout.
- payload cache root: `web/cache/heatmaps`
- lock directory: `web/cache/heatmaps/locks`
- cache retention constants in the shipped code: max age `172800` seconds,
  prune limit `32`, lock directory mode `0700`
- admin config/image saves invalidate payload caches through
  `heatmap_clear_payload_cache()` for the current game and the config aliases
  (`game`, `config.game`, `config.realgame`)
- inspect responses also emit `Cache-Control: no-store`
- compatibility JPEG regeneration is CLI-only; the admin HTTP surface must not
  start JPEG generation. The documented operator command remains:

```powershell
$env:PYTHONPATH='scripts'
rtk python -m hlstats_py.heatmaps --game <validated-game> --map <validated-map> --disablecache
```

- if dbversion `82` is retained, keep index rollout inside a maintenance
  window with readback before mode promotion
- if ordinary cache plus the retained index cannot hold the required SLA, stop
  promotion and write a separate daily read-model design instead of expanding
  scope ad hoc
- shipped telemetry claim: the cstrike grammar is verified; other mods may use
  only the coordinates actually present in their logs
- local source/runtime/visual/release-candidate gates are closed at `44f3af9`;
  production promotion must still follow
  mode `0` deploy/readback, mode `1` internal observation, public beta, and the
  rollback thresholds above

## Deployment And Configuration Notes

- Use `docs/python_migration_usage_guide.md` for runtime deployment and
  launcher lifecycle behavior.
- Use `docs/python_fullstack_docker.md` for local integrated stack setup.
- Use `docs/parity-acceptance.md` for fixture identity and heavy acceptance
  rules.
- Online services keep strict/server SQL mode. Replay/import tools use explicit
  import mode; do not enable importer multi-statement behavior in online
  services.
- The current observability contract is log-based. If operators need metrics
  scraping, add and validate an exporter as a separate feature.
