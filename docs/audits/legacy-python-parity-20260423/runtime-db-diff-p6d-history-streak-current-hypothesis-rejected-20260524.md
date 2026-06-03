# P6d Players_History streak sampling hypothesis rejected

Date: `2026-05-24`

Scope:

- Python runtime/storage investigation only.
- No retained Python behavior change for this hypothesis.
- Validation-test expectation for the already-existing suicide penalty behavior
  was updated separately.

## Hypothesis

The broad `hlstats_Players_History` residual after the PlayerNames live-alias
fix showed `Rakza` / `1:55955613` rows where Python carried higher
`kill_streak` / `death_streak` values than legacy across multiple history
dates.

A narrow legacy-first read suggested that `HLstats_Player.pm::flushDB` passes
the live object's current `kill_streak` and `death_streak` into both
`hlstats_Players` and `hlstats_Players_History`; the SQL layer then preserves
the maximum with `IF(? > ... )`. Python was passing cached `_player_max_*`
values directly. The candidate fix changed Python to pass current streak
values from the event-level rollup path.

## Result

The candidate was rejected after promotion replay because it broadened the
history drift:

- command:
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
- run state:
  `scripts/replay_baseline/comparison/.parity-state/20260524-141129.json`
- GeoIP backfill:
  `python -m hlstats_awards_py --db-host 127.0.0.1:3327 --db-name hlstatsxce --db-username hlstatsxce --db-password hlx123 --geoip --replay-mode`
- compare:
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`

The compare still exited `1`, as expected for documented residuals, but
`hlstats_Players_History` moved from the prior clean contour's `50/50`
normalized residuals to `106/106`.

Direct `Rakza` SQL after the rejected candidate showed mixed movement:

- `kill_streak` improved on several dates (`2024-01-06`, `2025-01-03`,
  `2026-01-03`, and `2026-01-04` matched legacy for that column).
- `death_streak` regressed or remained mismatched on other dates
  (`2024-01-06` became Python `0` vs legacy `6`; `2025-01-02` still had
  connection-time drift; `2026-01-04` became Python `9` vs legacy `12`).

## Decision

Do not retain the event-level "current streak instead of max streak" change.
The legacy behavior is not simply "write current streak on every event"; it is
flush-cadence sampled state. A real fix needs to model the legacy player
`flushDB` sampling boundary, or at least reduce the next candidate to a
single-player/single-day trace that shows exactly which legacy flush writes the
history streak columns.

## Next

- Continue `P6d-M3` on `hlstats_Players_History` with a write-trace or focused
  SQL timeline for the `Rakza` dates.
- Compare legacy general-log writes for `hlstats_Players_History` against
  Python write trace rather than changing event-level rollups directly.
- Keep the rejected current-streak patch out of `storage.py`.
