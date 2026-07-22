# Offline narrow-1000 Statsme SQL-write benchmark — 20260718-statsme-bench-r1

## Scope

Two valid current-working-tree measurements were run on separate disposable
MariaDB 10.11 containers and volumes on host port 3338. Both restored the
accepted baseline dump, imported the exact staged `narrow-1000` corpus with
native parsing and stdin batch size 2500, recorded initial/final anchors, then
removed their containers and volumes. `optimized-statsme/measure3` is the
profiled diagnostic; `optimized-statsme-unprofiled/measure4` is the unprofiled
throughput control. No live parity container was used or changed.

The current measurement is compared with the accepted previous history-only
working-tree measure in
`../performance-db-sql-opt-narrow-1000-20260718-sqlwrite-1000-bench-r1/`.
These are one-sample environment-sensitive throughput results, not a new parity
acceptance or performance-promotion decision.

## Inputs and final state

- Input manifest: 1,000 files, SHA-256
  `95BFDB5951922C0C36AAB2C5263E1880B227E845B34C9262939B028D0FBEBE8A`.
- Ignored-lines manifest: zero bytes.
- Final anchors: players=323, history=659, frags=5464, admin=327624,
  statsme=32290, statsme2=32290.
- `optimized-statsme-measure3-success.txt` exists; the runner output and a
  post-run check confirm that its disposable container and volume were removed.

## Implementation and runtime acceptance

The bounded product slice batches only Statsme player/server counter deltas at
the stdin transaction boundary. It does not suppress the append-only
`hlstats_Events_Statsme` or `hlstats_Events_Statsme2` writes, does not change
public runtime APIs, and is covered by 427 explicit product tests.

Runtime parity was accepted separately from this disposable benchmark:

- Prefix r2: `prefix-000010/20260718-statsme-prefix-r2`.
- Fresh no-reuse narrow r1:
  `narrow-1000/20260718-statsme-r1`, with the same 1,000-file manifest SHA
  `95BFDB5951922C0C36AAB2C5263E1880B227E845B34C9262939B028D0FBEBE8A` and
  anchors players=323, frags=5464, team_bonuses=4765, entries=0,
  server_rows=1.
- Product-path timing while preserving the accepted legacy contour:
  `narrow-1000/20260718-statsme-product-timing-r1` measured Python
  `python_import` only at 138.4203224 s / 4,451.15 records/s, versus fresh
  legacy elapsed 153.389 s (9.76% less elapsed; 1.108x same-corpus elapsed
  ratio, not normalized records/s). See
  `../runtime-product-timing-20260718-statsme-product-timing-r1-legacy-reference.md`.

All three compares retain only the accepted GeoIP-only `hlstats_Players`
residual. The product-timing compare is
`../runtime-db-diff-narrow-1000-20260718-statsme-product-timing-r1.json`.

## Measured result

| Metric | Prior history-only measure | Current Statsme measure3 | Change |
| --- | ---: | ---: | ---: |
| records | 616,130 | 616,130 | equal |
| elapsed | 357.835 s | 462.691 s | +29.3% |
| records/s | 1,721.82 | 1,331.62 | -22.7% |
| logical SQL executions | 546,321 | 546,321 | equal |
| logical SQL/record | 0.887 | 0.887 | equal |
| physical `Connection.query` calls | 124,630 | 60,785 | -51.2% |
| `Connection.query` cumulative | 195.559 s | 298.529 s | +52.7% |
| native parser cumulative | 36.402 s | 35.541 s | -2.4% |

The logical Statsme counter templates remain intentionally visible in the
trace: player shots/hits=32,290, server CT=16,680 and server TS=15,570
(64,540 logical counter executions). The physical profile is not
template-labelled, so it supports the aggregate reduction of 63,845 physical
`Connection.query` calls, rather than a precise per-template physical split.

## Unprofiled throughput control

`optimized-statsme-unprofiled/measure4` records `profile=False` and the exact
import command in `optimized-statsme-unprofiled-measure4-command.txt`; no
profile directory was created. It completed the same 616,130 records in
246.362 s (2,500.91 records/s), with the same input-manifest SHA, zero-byte
ignored-lines file and final anchors as measure3.

For context only, it is 92.973 s (+60.6%) slower than the fresh legacy replay
time of 153.389 s, and 127.612 s (+107.5%) slower than the earlier approximately
118.75 s unprofiled Python figure, which was timestamp-inferred rather than a
dedicated elapsed metric. Differences in host state and the lack of matched
repeat samples prevent a causal performance claim.

## Interpretation

The current source preserves the expected logical trace and produces the
expected final Statsme anchors while reducing aggregate physical DB calls.
The profiled measure3 is 104.856 seconds slower than the prior history-only
profiled sample, while the unprofiled measure4 also remains slower than its
available contextual comparators. Therefore this audit does **not** promote a
performance claim for the incremental Statsme slice; it records physical-call
evidence and retains the runtime parity gate as the correctness proof.

## Helper provenance and invalid diagnostics

`run-sample.ps1` and the 3338 config were copied from the accepted prior audit.
The new audit copy was corrected only for benchmark anchors: the stale table
name was changed to `hlstats_Events_Frags`, SQL metric labels use explicit
single-quoted literals in a PowerShell variable, and initial/final anchor
queries now fail fast on nonzero exit. The initial `measure1` and `measure2`
diagnostics were stopped before completion when those copied-helper anchor
issues were detected; their logs are retained and both disposable resources
were removed. See `optimized-statsme-diagnostic-invalid.md`.
