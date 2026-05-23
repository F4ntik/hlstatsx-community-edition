# P6d narrow-1000 after planted-bomb round-status exception

Date: `2026-05-19`

Scope:

- Python runtime/storage only.
- PHP/UI untouched.
- Source log for the first remaining planted-bomb TeamBonuses residual:
  `scripts/replay_baseline/artifacts/L0101059.log`.
- Full `narrow-1000` rerun without `-ReuseValidLegacy`, because the current
  legacy DB had just been used for single-log contours.

## Root cause

The first remaining `hlstats_Events_TeamBonuses` row after the hostage-rescue
fix was in `L0101059.log`:

- `2024-01-01 19:40:12`, `de_mirage`, `Planted_The_Bomb`,
  `*психоделия*`, `0:1828776565`.

The raw log has a Terrorists win and round end before a late planted-bomb
trigger:

- line `558`: `Team "TERRORIST" triggered "Terrorists_Win"`
- line `559`: `World triggered "Round_End"`
- line `560`: `gatl ... triggered "Planted_The_Bomb"`
- line `562`: `World triggered "Round_Start"`

Python already projected `round_status=1` after the team win and blocked the
player-action `reward_team` fan-out for `Planted_The_Bomb`. Legacy still
records the planted-bomb team rewards after that round boundary.

## Fix

- `scripts/hlstats_py/storage.py` now uses an explicit post-round team-reward
  allowlist instead of a hard-coded `Rescued_A_Hostage` check.
- The allowlist includes global `Rescued_A_Hostage` and game-specific
  `cstrike:Planted_The_Bomb`.
- The existing round-status gate remains in place for other team reward
  events, including `csgo:planted_bomb`.
- Added focused regression coverage for post-round
  `cstrike:Planted_The_Bomb` team reward fan-out.

## Verification

Targeted storage subset:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "record_action_team_reward_obeys_round_status_gate or record_action_rescued_hostage_team_reward_ignores_round_status_gate or record_action_cstrike_planted_the_bomb_team_reward_ignores_round_status_gate or team_bonus_rescued_hostage_ignores_round_status_gate or team_bonus_obeys_round_status_gate"
```

Result: `5 passed, 116 deselected`.

Broader targeted storage subset:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -k "team_bonus or planted_bomb or Planted_The_Bomb or Rescued_A_Hostage"
```

Result: `15 passed, 106 deselected`.

Worker rebuild:

```powershell
docker compose build hlstats-worker
```

Result: `Image python-hlstats-worker Built`.

Single-log replay:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0101059.log `
  -Name p6d-team-bonus-planted-L0101059-after-planted-roundstatus `
  -TraceTable hlstats_Events_TeamBonuses `
  -TraceParamContains "2024-01-01 19:40:12"
```

Result: `compare exit: 1`, but `hlstats_Events_TeamBonuses` disappeared from
the single-log logical compare. The remaining single-log differences were
`hlstats_Players` and accepted `hlstats_Events_Entries`.

Full narrow contour:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Fresh compare:

- `runtime-db-diff-p6d-narrow-1000-20260519-after-planted-roundstatus-compare.txt`

## Result

`hlstats_Events_TeamBonuses` improved from:

- `4765/4737`
- `28` legacy-only / `0` python-only normalized rows

to:

- `4765/4764`
- `1` legacy-only / `0` python-only normalized rows

The remaining TeamBonuses example is:

- `2026-01-02 21:40:31`, `de_inferno_snow`, `CTs_Win`,
  `Dance Bear`, `0:1866613407`.

Other current logical diff counts after this run:

- `hlstats_Players`: `250` legacy-only / `250` python-only normalized rows.
- `hlstats_PlayerNames`: `2` legacy-only / `3` python-only normalized rows.
- `hlstats_Players_History`: `52` legacy-only / `52` python-only normalized
  rows.
- `hlstats_Events_Entries`: accepted `0/1017` legacy/Python policy difference.
