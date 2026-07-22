# Rust parser boundary: measured staging plan

## Current evidence

There is no Rust/Cargo source, FFI binding, or compiled parser in this product
lane as of 2026-07-18.  The `native` parser option is a Python fast path in
`scripts/hlstats_py/protocol.py`; it keeps the same `LogEvent` model and shared
event helpers as the default regex-oriented `python` backend.

On the preserved representative file
`scripts/replay_baseline/artifacts/parity-trace-rakza-window/L0105062.log`
(`2,287` physical records), two local non-DB runs measured:

| Tool | Python records/s | Native records/s |
| --- | ---: | ---: |
| `benchmark_parser.py` | 9,086.6 | 13,412.9 |
| `profile_processing_subset.py` unprofiled pass | 12,235.7 | 14,442.4 |

This is a single local, non-DB measurement, not a release benchmark.  It
shows a parser-only native advantage, but its magnitude varies with the
instrumentation and machine state (about 18--48% in these runs).  It does not
establish that parsing is the end-to-end bottleneck.  Existing direct-import
profiles show SQL execution and player-state priming among cumulative-time
consumers, so storage/DB evidence must be collected before funding a Rust
implementation.

## Reproducible processing profile

The bounded helper reads only preserved logs and never opens a DB or launches a
replay.  Use a fresh output directory outside accepted parity evidence:

```powershell
$env:PYTHONPATH = 'scripts'
$run = Join-Path $env:TEMP 'hlstats-processing-profile-20260718-r1'
python scripts/replay_baseline/profile_processing_subset.py `
  scripts/replay_baseline/artifacts/parity-trace-rakza-window/L0105062.log `
  --max-files 1 --backends python native --output-dir $run
```

Outputs are `$run/processing-profile.json`, one `processing-<backend>.pstats`,
and one `processing-<backend>-top-30.txt` per backend.  Capture the command,
input path, and JSON beside a change review.  JSON throughput is measured in a
separate unprofiled pass; `profile_elapsed_seconds` describes the intentionally
slower cProfile pass.  Do not replace `narrow-1000` or `full-41513` evidence
with profiling output.

## Controlled DB-write profile

DB profiling necessarily writes replay rows, so run it only against the
ephemeral benchmark stack, never against parity or accepted evidence DBs:

```powershell
$run = Join-Path $env:TEMP 'hlstats-db-profile-20260718-r1'
$env:PYTHONPATH = 'scripts;scripts/replay_baseline'
$env:HLSTATS_DB_WRITE_TRACE_PATH = Join-Path $run 'db-write-trace.jsonl'
New-Item -ItemType Directory -Force $run | Out-Null
python scripts/replay_baseline/direct_import_artifacts.py `
  --profile --max-files 1 `
  --artifacts-dir scripts/replay_baseline/artifacts/parity-trace-rakza-window `
  --configfile scripts/replay_baseline/bench_ephemeral/hlstats.host.conf `
  --audit-dir $run
```

Expected outputs: `$run/perf-profile.txt` (cProfile, SQL template counts, and
baseline metrics) and `$run/db-write-trace.jsonl` (opt-in storage trace).  The
command requires a separately started disposable DB from
`scripts/replay_baseline/bench_ephemeral/README.md`; it is intentionally not a
safe default.

### Measured full-state disposable run

A disposable MariaDB restored from the `runtime-full-41513-python` dump was
profiled with the same `L0105062.log` input and the `native` backend.  The
2,287-record import took `5.075 s` (`450.67 records/s`) and issued `4,613` SQL
executions (`2.017 SQL/record`).  cProfile attributed `4.266 s` to
`EventStorage.record`, `3.750 s` to `_execute`, and `3.407 s` to MySQL
`Connection.query`; parser-only native time for the same input was `0.168 s`.

The largest SQL groups were `2,106` Player_History upserts, `735`
Events_Admin inserts, and `282` each for Statsme inserts, player-shot updates,
and Statsme2 inserts.  Evidence is preserved under
`docs/audits/legacy-python-parity-20260423/performance-db-full-state-20260718-r1/`.
Those artifact files are inputs to this note and must not be edited.

In this profile, parser-only work is about `3.3%` of import wall time, so even
an unrealistically free parser has a small end-to-end ceiling.  Prioritize
removing redundant SQL and introducing parity-safe batching, with focused
storage tests and SQL-trace/parity comparison, before broadening the Rust
boundary.

The later `20260718-sql-write-opt-r1` stdin-only history-row cache reduced the
same full-state log to 2.071 s; its cProfile still attributes 1.170 s to
MySQL `Connection.query` while parser work is 0.163 s. Rust therefore remains
an optional parser-only stage; storage/runtime expansion remains out of scope.

## First Rust boundary

Stage 1 may add an **optional parser-only** Rust implementation behind the
existing `parse_log_event(payload, backend=...)` seam.  It should initially
replace fixed-header extraction and event classification while returning the
unchanged Python `LogEvent` contract.  Do not move `EventStorage`, SQL
generation, transaction batching, or player lifecycle into Rust at this
stage.

Compatibility gate: add field-level parser equivalence cases, retain the
current `python` default, compare a preserved single-log profile, run focused
parser/runtime tests, then run a separately authorised narrow replay plus SQL
write-trace comparison.  A full-41513 replay is not a Rust-stage prerequisite.

Rollback is a configuration/CLI switch back to `--parser-backend python`; keep
the current `native` Python fast path available until the Rust backend passes
those gates.  Primary risks are malformed-line behavior, BOT/identity
normalization, timestamp parsing, and subtle event/lifecycle ordering.  The
measured full-state profile shows that storage and DB round trips dominate;
re-measure after parity-safe SQL reduction before reconsidering a broader Rust
scope.

The later bounded Statsme counter-delta slice confirms the same boundary at
`narrow-1000` scale: its disposable profile reduced physical
`Connection.query` calls from 124,630 to 60,785, while native parser cumulative
time was 35.541 s. The profiled 462.691 s and isolated-host unprofiled 246.362
s samples are environmentally non-comparable, so they do not establish an
incremental end-to-end wall-speed gain. Rust remains optional parser-only work;
do not use this storage evidence to widen its scope. Evidence:
`docs/audits/legacy-python-parity-20260423/performance-db-sql-opt-narrow-1000-20260718-statsme-bench-r1/`.
