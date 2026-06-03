# P6d narrow-1000 after defuse-scoped kill-streak suppression

Date: `2026-05-18`

Scope:

- Python runtime/storage only.
- `hlstats-worker` rebuilt before replay.
- Full `narrow-1000` rerun without `-ReuseValidLegacy` after a discarded reuse
  attempt found legacy DB still loaded with a single-log contour.

## Root cause

The previous defuse-boundary fix suppressed derived `kill_streak_*` emission for
the whole server on the next `Round_End`. Legacy only needed the defuser's
defuse-boundary streak suppressed; other players with live pending
`kills_per_life` still receive round-end `kill_streak_*` rows.

## Fix

- `scripts/hlstats_py/storage.py` now stores the next round-end suppression as
  `server_id -> player_id set`.
- `Round_End` still drains every pending player life, but skips derived
  `kill_streak_*` emission only for the suppressed player ids.
- Added a regression where the defuser and another alive player both have a
  pending `kill_streak_2`: the defuser is suppressed and the other player is
  emitted.

## Verification

Targeted pytest:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k 'defuse or bonus_round_end_records_derived_kill_streak_row_and_count_while_clearing_pending_kills'
```

Result: `3 passed, 114 deselected`.

Worker rebuild:

```powershell
docker compose build hlstats-worker
```

Result: `Image python-hlstats-worker Built`.

Single-log:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0102204.log `
  -Name p6d-defuse-streak-L0102204 `
  -TraceTable hlstats_Events_PlayerActions `
  -TraceParamContains "2026-01-02"
```

Result: `compare exit: 1`, but the logical compare no longer contains
`hlstats_Events_PlayerActions`; remaining single-log differences are
`Players`, `Players_History`, accepted `Events_Entries`, and `TeamBonuses`.

Full narrow contour:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Fresh compare:

- `runtime-db-diff-p6d-narrow-1000-20260518-after-defuse-scope-compare.txt`

## Result

`hlstats_Events_PlayerActions` improved from `24` legacy-only rows to `14`
legacy-only rows. The first two defuse-boundary rows from `L0102204.log` are
closed:

- `2026-01-02 19:05:47`, `KToEcJIuHe9I`, `kill_streak_2`
- `2026-01-02 19:15:50`, `Wonsm4n`, `kill_streak_3`

Action aggregate counts improved:

- `kill_streak_2`: legacy `1065` vs python `1056`
- `kill_streak_3`: legacy `203` vs python `201`
- `kill_streak_4`: legacy `48` vs python `47`
- `kill_streak_5`: legacy `12` vs python `11`
- `kill_streak_8`: legacy `2` vs python `1`

Remaining open order:

1. Continue `kill_streak_*` / `Events_PlayerActions` from the first remaining
   row: `2026-01-02 20:12:03`, `Kyco4ek_C4acTb9I`, `de_rats`,
   `kill_streak_4`.
2. Then return to `TeamBonuses` legacy-only residuals.
3. Keep `Players` / `PlayerNames` / `Players_History` attribution cluster
   deferred until row-level event residuals stabilize.
