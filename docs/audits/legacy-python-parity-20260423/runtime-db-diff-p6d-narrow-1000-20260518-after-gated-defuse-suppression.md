# P6d narrow-1000 after gated defuse kill-streak suppression

Date: `2026-05-18`

Scope:

- Python runtime/storage only.
- PHP/UI untouched.
- Source log: `scripts/replay_baseline/artifacts/L0102207.log`.
- Full `narrow-1000` rerun without `-ReuseValidLegacy` after a discarded reuse
  attempt found stale contour metadata had reused a single-log legacy DB.

## Root cause

The first remaining `hlstats_Events_PlayerActions` row was:

- `2026-01-02 20:12:03`, `de_rats`, `Kyco4ek_C4acTb9I`,
  `0:1776650646`, `kill_streak_4`.

`L0102207.log` shows the defuser had four kills in the same life before the
defuse-ended round:

- line `457`: first kill
- line `470`: second kill
- line `481`: third kill
- line `493`: fourth kill
- line `500`: `Begin_Bomb_Defuse_Without_Kit`
- line `501`: `Defused_The_Bomb`
- line `502`: `Bomb_Defused`
- line `503`: `Round_End`

The previous player-scoped suppression queued the defuser for next
`Round_End` suppression whenever `Defused_The_Bomb` was seen. Legacy only needs
that suppression when the defuse action itself is filtered by the min-player
gate. When the defuse action is recorded normally, legacy still drains and
emits the defuser's pending round-end `kill_streak_*`.

## Fix

- `scripts/hlstats_py/storage.py` now computes the min-player gate once before
  recording.
- Next-round-end `kill_streak_*` suppression is queued only when the defuse
  action is actually gated by min-player policy.
- Existing gated-defuse behavior remains: gated defuse clears pending kills
  without emitting the defuser's derived streak.
- Added regression coverage for a recorded defuse with four pending kills,
  expecting `kill_streak_4` on `Round_End`.

## Verification

Targeted pytest:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "defuse or bonus_round_end_records_derived_kill_streak_row_and_count_while_clearing_pending_kills"
```

Result: `4 passed, 114 deselected`.

Focused defuse subset:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "bomb_defuse_round_end_records_defuser_kill_streak_when_defuse_action_is_not_gated or bomb_defuse_round_end_clears_pending_kills_when_defuse_actions_are_gated_without_derived_streak or bomb_defuse_round_end_suppresses_only_defuser_derived_kill_streak_when_other_players_are_pending"
```

Result: `3 passed, 115 deselected`.

Worker rebuild:

```powershell
docker compose build hlstats-worker
```

Result: `Image python-hlstats-worker Built`.

Single-log:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0102207.log `
  -Name p6d-kyco4ek-defuse-streak-L0102207-after-gated-suppress `
  -TraceTable hlstats_Events_PlayerActions
```

Result: `compare exit: 1`, but the logical compare no longer contains
`hlstats_Events_PlayerActions`; remaining single-log differences are
`Players` and accepted `Events_Entries`. The write trace contains the Python
insert at `2026-01-02 20:12:03` with `actionId 287`, bonus `3`.

Full narrow contour:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Fresh compare:

- `runtime-db-diff-p6d-narrow-1000-20260518-after-gated-defuse-suppression-compare.txt`

## Result

`hlstats_Actions` and `hlstats_Events_PlayerActions` are no longer present in
the full narrow-1000 logical diff.

Remaining logical diff tables:

- `hlstats_Players`: `250` legacy-only / `250` python-only normalized rows.
- `hlstats_PlayerNames`: `2` legacy-only / `3` python-only normalized rows.
- `hlstats_Players_History`: `80` legacy-only / `80` python-only normalized rows.
- `hlstats_Events_Entries`: accepted `0/1017` legacy/Python policy difference.
- `hlstats_Events_TeamBonuses`: `4765/4720`, `45` legacy-only / `0`
  python-only normalized rows.

Remaining open order:

1. Continue with `hlstats_Events_TeamBonuses` legacy-only residuals.
2. Then return to the `Players` / `PlayerNames` / `Players_History`
   attribution cluster.
