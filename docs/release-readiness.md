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
  `Run-DualContour-1000.ps1 -UseDumpRestore -ReuseValidLegacy -MaxImportFiles 1000`;
- post-replay GeoIP backfill before claiming release-clean player/country
  parity;
- compact DB compare with `compare_stats_dbs.py --max-examples 20`;
- replay-backed EN/RU route smoke with `web_route_smoke.py`;
- `hlstats_py` metrics summary from either stdin import or runtime shutdown;
- benchmark/profile output when the release changes parser, storage, replay,
  DB mode, reconnect, lifecycle, or control-plane behavior;
- updated `docs/status.md` and `docs/test-plan.md` entries for the release
  evidence.

Store detailed replay transcripts and parity evidence under
`docs/audits/legacy-python-parity-20260423/`. Keep long benchmark/profiling
outputs in `scripts/replay_baseline/artifacts/`; nightly CI uploads matching
release-readiness artifacts when present.

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
