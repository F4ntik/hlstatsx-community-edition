# P6d narrow-1000 residual refresh - 2026-05-18

Scope: `scripts/replay_baseline/artifacts/L0105062.log` single-log follow-up, then validated narrow-1000 rerun.

## Commands

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 -LogFile scripts\replay_baseline\artifacts\L0105062.log -Name rakza-kill-streak -TraceTable hlstats_Events_PlayerActions -TraceParamContains "2024-01-06 00:18:10"
python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Full compare output: `runtime-db-diff-p6d-narrow-1000-20260518-compare.txt`.

## Single-log result

- `L0105062.log` replay used `mode=batch-stdin-local`.
- `hlstats_Events_PlayerActions` write trace diff is clean: `trace diff exit: 0`.
- The previous Python-only Rakza `kill_streak_2` at `2024-01-06 00:18:10` is gone.
- Single-log logical compare now has only `hlstats_Players` country/flag attribution and accepted `hlstats_Events_Entries` differences.

## Narrow-1000 residual set

Validated rerun rebuilt both legacy and Python contours. Do not use the intermediate `-ReuseValidLegacy` attempt from this date; it reused the single-log legacy contour and produced an invalid 1-log-vs-1000-log compare.

Current residual tables:

- `hlstats_Actions`: kill streak action counters only.
- `hlstats_Players`: 323/323 rows, 250 normalized row differences.
- `hlstats_PlayerNames`: 415 vs 416 rows, 2 legacy-only / 3 python-only normalized row differences.
- `hlstats_Players_History`: 659/659 rows, 92 normalized row differences.
- `hlstats_Events_Entries`: legacy 0 vs python 1017, accepted difference; keep visible.
- `hlstats_Events_PlayerActions`: legacy 4972 vs python 4948, 24 legacy-only / 0 python-only normalized row differences.
- `hlstats_Events_TeamBonuses`: legacy 4765 vs python 4720, 45 legacy-only / 0 python-only normalized row differences.

Kill streak counter deltas:

- `kill_streak_2`: legacy 1065 vs python 1053.
- `kill_streak_3`: legacy 203 vs python 197.
- `kill_streak_4`: legacy 48 vs python 45.
- `kill_streak_5`: legacy 12 vs python 10.
- `kill_streak_8`: legacy 2 vs python 1.

First `Events_PlayerActions` residual examples are legacy-only derived kill streak rows at `2026-01-02 19:05:47`, `2026-01-02 19:15:50`, `2026-01-02 20:12:03`, and later. The prior `2024-01-06 00:18:10` Rakza overemit is not part of the current residual set.
