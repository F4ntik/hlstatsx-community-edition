# P6d narrow-1000 after hostage rescue round-status exception

Date: `2026-05-19`

Scope:

- Python runtime/storage only.
- PHP/UI untouched.
- Source log for the first TeamBonuses residual:
  `scripts/replay_baseline/artifacts/L0101061.log`.
- Full `narrow-1000` rerun without `-ReuseValidLegacy`, because the current
  legacy DB had just been used for a single-log contour.

## Root cause

The first remaining `hlstats_Events_TeamBonuses` row was in `L0101061.log`:

- `2024-01-01 20:33:47`, `cs_mansion`, `Rescued_A_Hostage`,
  `HardC0re`, `0:210111505`.

The raw log has a CT round win followed by hostage rescue triggers:

- line `527`: `Team "CT" triggered "CTs_Win"`
- line `528`: `World triggered "Round_End"`
- lines `535-537`: `"Alenka<845><STEAM_1:0:2032503011><CT>" triggered
  "Rescued_A_Hostage"`

Python set `round_status=1` after the CT win and blocked the later hostage
rescue team fan-out. Legacy still records those `Rescued_A_Hostage`
`hlstats_Events_TeamBonuses` rows after the round boundary.

The event is a player trigger, not a `Team "CT"` trigger, so the decisive path
is `_record_action()` with `reward_team`, not only `_record_team_bonus()`.

## Fix

- `scripts/hlstats_py/storage.py` now lets `Rescued_A_Hostage` team rewards
  bypass the round-status gate in both team-bonus and player-action
  `reward_team` paths.
- The existing round-status gate remains in place for other team reward events,
  including the existing planted-bomb/round-win coverage.
- Added focused regression coverage for:
  - player-trigger `Rescued_A_Hostage` team reward with `round_status=1`
  - team-trigger `Rescued_A_Hostage` with `round_status=1`

## Verification

Targeted pytest, RED/GREEN:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "record_action_rescued_hostage_team_reward_ignores_round_status_gate"
```

Initial result before the production fix: `1 failed`.

Focused gate/regression subset:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "record_action_rescued_hostage_team_reward_ignores_round_status_gate or record_action_team_reward_obeys_round_status_gate or rescued_hostage_ignores_round_status_gate or team_bonus_rescued_hostage_allows_same_second_duplicates"
```

Result: `4 passed, 116 deselected`.

Broader targeted storage subset:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "team_bonus or planted_bomb or Rescued_A_Hostage"
```

Result: `14 passed, 106 deselected`.

Worker rebuild:

```powershell
docker compose build hlstats-worker
```

Result: `Image python-hlstats-worker Built`.

Single-log replay:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0101061.log `
  -Name p6d-team-bonus-hostage-L0101061-after-action-rescue-roundstatus `
  -TraceTable hlstats_Events_TeamBonuses `
  -TraceParamContains "2024-01-01 20:33"
```

Result: `compare exit: 1`, but `hlstats_Events_TeamBonuses` changed from
`9` legacy-only rows to `0` legacy-only rows for this single-log contour.
The remaining single-log `TeamBonuses` difference is `3` python-only
`Terrorists_Win` rows later in the file, outside the first residual.

Full narrow contour:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Fresh compare:

- `runtime-db-diff-p6d-narrow-1000-20260519-after-rescue-roundstatus-compare.txt`

## Result

`hlstats_Events_TeamBonuses` improved from `4765/4720`, `45` legacy-only /
`0` python-only normalized rows to:

- `4765/4737`
- `28` legacy-only / `0` python-only normalized rows

The first hostage-rescue residual is closed. Remaining TeamBonuses examples now
start with `Planted_The_Bomb`:

- `2024-01-01 19:40:12`, `de_mirage`, `Planted_The_Bomb`,
  `*����������*`, `0:1828776565`

Other current logical diff counts after this run:

- `hlstats_Players`: `250` legacy-only / `250` python-only normalized rows.
- `hlstats_PlayerNames`: `2` legacy-only / `3` python-only normalized rows.
- `hlstats_Players_History`: `76` legacy-only / `76` python-only normalized
  rows.
- `hlstats_Events_Entries`: accepted `0/1017` legacy/Python policy difference.
