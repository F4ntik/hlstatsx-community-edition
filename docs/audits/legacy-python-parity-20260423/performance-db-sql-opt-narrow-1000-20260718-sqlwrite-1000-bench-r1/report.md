# Offline narrow-1000 SQL write benchmark — 20260718-sqlwrite-1000-bench-r1

## Result and scope

This is an offline/import throughput measurement only. It compares the clean
`22cd32c` source in a detached worktree with the current working tree whose
only runtime source delta in this slice is represented by storage diff SHA-256
`c2654f3739cf91e22e428196a5a0bf4577fdac37d41dfc69db57a0471aca06bf`
(4,248 UTF-8 bytes). No accepted/comparison database was used.

| Metric | Baseline clean source | Optimized working tree | Change |
| --- | ---: | ---: | ---: |
| input files | 1,000 | 1,000 | equal |
| records | 616,130 | 616,130 | equal |
| elapsed | 887.530 s | 357.835 s | -59.7% |
| records/s | 694.21 | 1,721.82 | +148.0% |
| logical SQL executions | 870,979 | 546,321 | -37.3% |
| SQL/record | 1.414 | 0.887 | -37.3% |
| `Players_History` ensure upsert | 326,677 | 2,019 | -99.4% |
| cProfile `Connection.query` cumulative | 647.445 s | 195.559 s | -69.8% |

Both samples used exactly the accepted `narrow-1000` manifest, 1,000
`L0101000.log..L0106125.log` files, SHA-256
`95BFDB5951922C0C36AAB2C5263E1880B227E845B34C9262939B028D0FBEBE8A`.
Both generated a zero-byte ignored-lines manifest.

## Method

- Baseline source: detached worktree
  `D:\PyProjects\hlstatx-ce\hlstatsx-sqlwrite-1000-baseline-22cd32c` at
  `22cd32ca94c8748a77f779953f6856d9e54aa983`, clean.
- Optimized source: current worktree at the same base commit with the storage
  diff hash above.
- Each variant restored
  `scripts/replay_baseline/artifacts/baseline_reset_20260418.sql.gz` into its
  own disposable MariaDB 10.11 container/volume, with utf8mb4,
  `utf8mb4_unicode_ci`, `max_allowed_packet=256M`, and
  `sql_mode=NO_ENGINE_SUBSTITUTION`.
- Import command: `direct_import_artifacts.py --max-files 1000 --profile
  --parser-backend native --stdin-transaction-batch-size 2500`, through a
  benchmark-only host config on port 3338. Containers and volumes were torn
  down after each completed run.
- cProfile and SQL template counting were enabled in both variants, so wall
  time includes equivalent profiling overhead; it is not a production latency
  estimate.

## Interpretation

The reduction comes from the expected `Players_History` duplicate-key no-op
ensure upsert. Admin and Statsme templates remain present with the same shown
counts, so the benchmark does not claim batching or suppression of append-only
events. MySQL remains dominant even after the cache; parser native cumulative
time is 43.040 s baseline and 36.402 s optimized, so Rust remains optional and
parser-only rather than the next storage change.

## Limits and parity boundary

Only one complete measured sample per variant was practical: the baseline took
14.8 minutes. The initial foreground warm-up was interrupted by an unrelated
occupied port before it completed and is retained only as an invalid diagnostic;
there is no warm-up or repeat distribution. Consequently the percentages are
strong single-sample evidence, not a noise-bounded performance claim.

The background helper correctly preserved per-run manifests, ignored-line
files, profiles, and teardown logs, but did not persist its intended anchor
query output before teardown. It therefore does **not** provide a new
benchmark-specific stable-key/final-DB comparison or hash. Do not use this
report alone for a new parity acceptance claim. The separate fresh no-reuse
`narrow-1000/20260718-sqlwrite-r2` evidence remains the parity proof for the
cache, with only the documented GeoIP-only `Players.country`/`flag` residual.

## Artifacts

- `baseline-measure1-run.log`, `optimized-measure1-run.log`: commands and
  complete importer output.
- `baseline-measure1-profile/perf-profile.txt`,
  `optimized-measure1-profile/perf-profile.txt`: cProfile and template counts.
- `baseline-measure1-input-manifest.txt`,
  `optimized-measure1-input-manifest.txt`: exact final input manifests.
- `run-sample.ps1` and `hlstats-bench-3338.conf`: benchmark-only runner and
  disposable DB configuration.
