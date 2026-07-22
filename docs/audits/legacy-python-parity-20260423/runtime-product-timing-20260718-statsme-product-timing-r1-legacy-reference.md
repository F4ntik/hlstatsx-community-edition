# Legacy reference for product-path timing

This note makes the elapsed-time reference for
`20260718-statsme-product-timing-r1` reproducible. It compares same-corpus
elapsed times only. It does **not** compare legacy log-line throughput with
Python record throughput, and it does **not** establish an incremental Statsme
wall-speed improvement.

## Fresh legacy reference

The fresh no-reuse dual-contour command is preserved in
`runtime-narrow-1000-20260718-statsme-r1-process.txt`:

```text
-NoProfile -ExecutionPolicy Bypass -File scripts/replay_baseline/comparison/Run-DualContour-1000.ps1 -MaxImportFiles 1000 -ArtifactLabel narrow-1000 -EvidenceRunId 20260718-statsme-r1 -UseDumpRestore -SkipBuild
```

Its runner transcript in `runtime-narrow-1000-20260718-statsme-r1-runner.log`
records a fresh dump restore and 1,000-file legacy import:

```text
Restore mode: dump
Restore complete for hlstatsx-legacy-db. source=dump snapshot=...legacy-baseline_reset_20260418-with-bootstrap.tar.gz
Replayed 1000 log files ... through the legacy daemon with logical source server 37.230.137.48:27015.
Replay summary: processed=1000, skipped=0, errors=0, lines=672223, dropped_lines=1969, elapsed=153.389s, throughput=6.52 files/sec, 4382.49 lines/sec
```

`legacy-input-manifest-narrow-1000-20260718-statsme-r1.txt` has 1,000 entries
and SHA-256
`95BFDB5951922C0C36AAB2C5263E1880B227E845B34C9262939B028D0FBEBE8A`.
Legacy metadata is
`scripts/replay_baseline/comparison/.parity-state/contour-info/legacy-narrow-1000-20260718-statsme-r1.json`:

- fingerprint `1697c2cc1fc306a69db082baba0dc21afcd1bf284605072b986ea468da2880c9`;
- inputs: 1,000 logs `L0101000.log..L0106125.log`, corpus hash
  `ccc06efc73505e1f1cf0703500f4dacdb05ee1ced634e93ee3cb410cad435566`,
  server `37.230.137.48:27015`, policy `drop-empty-team-enter-events`, dump
  baseline;
- anchors: players=323, frags=5464, team_bonuses=4765, entries=0,
  server_rows=1.

## Timed Python product path

The exact timed invocation is preserved in
`runtime-product-timing-20260718-statsme-product-timing-r1-python-import-rerun-process.txt`:

```text
-NoProfile -ExecutionPolicy Bypass -File scripts/replay_baseline/comparison/Run-DualContour-1000.ps1 -MaxImportFiles 1000 -ArtifactLabel narrow-1000 -EvidenceRunId 20260718-statsme-product-timing-r1 -Stack both -ReuseValidLegacy -UseDumpRestore -SkipBuild -OverwriteEvidence -OnlyStage python_import -StatePath "...\\.parity-state\\20260718-statsme-product-timing-r1.json"
```

It started at `2026-07-18T21:22:55.4424712+03:00`; the explicit state records
completion at `2026-07-18T21:25:13.8627936+03:00`. The resulting isolated
`python_import` interval is `138.4203224 s` for 616,130 Python records
(`4,451.15 records/s`). It excludes infrastructure startup, baseline restore,
preflight, snapshot, and compare. The transcript records `Reusing valid legacy
narrow-1000 contour`; legacy was not restored or imported.

Python metadata is
`scripts/replay_baseline/comparison/.parity-state/contour-info/python-narrow-1000-20260718-statsme-product-timing-r1.json`:

- fingerprint `f2dc81ddd35e7b5ca40502fa207b8ea45a99287edcd723620de795708953e9d1`;
- same 1,000-log corpus hash, server, policy, dump baseline, and anchors as
  the legacy reference; `use_python_udp_replay=false`.

The compare artifact is
`runtime-db-diff-narrow-1000-20260718-statsme-product-timing-r1.json`. It
retains only the accepted GeoIP-only `hlstats_Players` residual; servers,
Statsme/Statsme2, PlayerNames, and Players_History match.

## Correct ratio interpretation

`153.389 / 138.4203224 = 1.108x` is a same-corpus elapsed-time ratio, and
Python elapsed is 9.76% lower. It is not a normalized records/s claim because
the legacy transcript reports 672,223 log lines while the Python import reports
616,130 records. It also does not isolate an incremental Statsme wall-time
effect: the fresh legacy and later Python timing runs differ in timing context.
