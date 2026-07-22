# SQL write-path optimization — 20260718-sql-write-opt-r1

## Scope and safety boundary

The only production change is an stdin-transaction-mode cache of successfully
ensured `hlstats_Players_History` daily keys `(playerId, history day, game)`.
It suppresses the duplicate-key no-op upsert only after that exact upsert has
succeeded.  It is cleared at batch begin/end, abort/rollback, and runtime
reset.  Online mode is deliberately unchanged.

The preserved Python full-state dump SHA-256 was verified as
`E8D0BA9E93147EAA15F2993C77D67773565A8DE2AADB4BC183515A2438104252`.
All runs used disposable `hlstatsxwritebench` MariaDB volumes only.  The input
was `L0105062.log`, SHA-256
`093A8636B9948EAAF149A337BD2E022174C74529D05CB4B3C53D88B81BB4DDF6`,
378,518 bytes.

## Before / after

| Metric | Baseline | Optimized | Change |
| --- | ---: | ---: | ---: |
| records | 2,287 | 2,287 | equal |
| wall time | 4.457 s | 2.071 s | -53.5% |
| records/s | 513.17 | 1,104.44 | +115.2% |
| logical `_execute` calls | 4,613 | 2,519 | -45.4% |
| logical SQL/record | 2.017 | 1.101 | -45.4% |
| physical MariaDB general-log calls | 3,168 | 1,059 | -66.6% |
| physical `Players_History` upserts | 2,106 | 12 | -99.4% |

`perf-profile.txt` contains the cProfile cumulative views and logical template
counts for each run.  `db-write-trace.jsonl` contains the matching opt-in
storage traces.  The largest removed logical template is exactly the no-op
`Players_History` upsert (2,106 to 12); append-only Admin/Statsme paths retain
their existing stdin buffering and were not changed.

## Parity evidence

The two profiled runs began from separately restored disposable full-state
dumps. Their recorded initial anchors match: 57 tables, 6,092 Players, 537,210
Frags, 15,454,815 Admin rows, and 36,827 Player_History rows. Final row-count
anchors match for Players (6,092), Player_History (36,827), Admin (15,455,550),
Statsme (2,785,510), and Statsme2 (2,785,505).

Checksums match for Player_History, Admin, Statsme, and Statsme2. `Players`
has a raw checksum mismatch because every row's `last_event` is assigned the
run wall-clock timestamp: baseline `1784380269`, optimized `1784379508`.
The sorted stable-key comparison excluding this known processing-time field
has `diff_count=0`; all other Players fields match.  A third disposable
baseline restore/replay produced the baseline stable-key export used for that
classification.  No unexpected affected-table drift remains.

`Players_History` stable-key exports ordered by `(playerId, eventTime, game)`
match byte-for-byte: 36,827 rows and SHA-256
`839AD6935D940500118260EC5463942D780DCADB5FC4F9729E77EBFF22C75816` on
both independently restored runs. A checksum was not used as a substitute for
this comparison.

## Fresh narrow-1000 promotion ladder

The first `20260718-sqlwrite-r1` dual-contour run used
`-ReuseValidLegacy`. Its reused legacy metadata carried full-state anchors and
was therefore retained only as an invalid diagnostic, not parity evidence.
A clean `prefix-000010` run without reuse then matched all metadata anchors
and SQL-snapshot bodies; its only pre-existing slice residual was
`hlstats_Servers.act_players` (`2` legacy versus `0` Python).

The resulting fresh no-reuse `narrow-1000` gate is
`20260718-sqlwrite-r2`. Both contours used 1,000 inputs from `L0101000.log`
through `L0106125.log`; their manifest SHA-256 is
`95BFDB5951922C0C36AAB2C5263E1880B227E845B34C9262939B028D0FBEBE8A` and
their anchors are 323 Players, 5,464 Frags, 4,765 TeamBonuses, zero Entries,
and one Server. After removing the stack/container/timestamp header, the two
58-line SQL snapshots are byte-identical. The legacy dropped-lines file has
1,969 documented `empty-team-enter-event` policy drops; the Python ignored
lines file is present and empty, so this is retained as an explicit policy
classification rather than treated as an input mismatch.

The stable-key database comparison contains no new storage/cache drift. Its
sole residual is the established raw-replay GeoIP classification in
`hlstats_Players`: 250 legacy-only and 250 Python-only rows of the same player
keys, differing only in `country`/`flag` values (legacy GeoIP values versus
empty Python values). It is not release-clean GeoIP-backfill evidence, but it
is separate from this SQL write-path change and does not reopen the accepted
non-GeoIP narrow parity gates. The running Python worker was checked to contain
the cache implementation; the contour metadata's `git_commit=22cd32c` is the
base commit, while the current uncommitted source was built into the worker.

## Rejected alternatives and rollback

- `Events_Admin`, Statsme, and Statsme2 are append-only records and already
  use the existing stdin EventBuffer; suppressing them would lose event
  history.
- Broad batching or a cache in online mode was rejected because reconnect,
  error, and external-row-deletion semantics would change.
- Rollback is a small source revert of the cache; no schema or data migration
  was made.

## Next slice and Rust priority

The next candidate is not another blind event insert batch: first profile a
parity-safe aggregation of Statsme player/server counter updates inside an
existing stdin flush boundary. It needs separate ordering/error tests. After
this SQL reduction, MySQL `Connection.query` remains the dominant cProfile
consumer (1.170 s of 2.071 s); parser work is 0.163 s, about 7.9% of wall
time. Rust remains optional
and parser-only behind the existing backend seam, not a storage/runtime
expansion.
