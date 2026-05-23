# P6d narrow-1000 after TeamBonuses timeout cadence alignment

Date: `2026-05-23`

Scope:

- Python runtime/storage only.
- PHP/UI untouched.
- Source log for the final visible TeamBonuses residual:
  `scripts/replay_baseline/artifacts/L0102211.log`.
- Full `narrow-1000` rerun without `-ReuseValidLegacy`.

## Root cause

The remaining `hlstats_Events_TeamBonuses` row was:

- `2026-01-02 21:40:31`, `de_inferno_snow`, `CTs_Win`,
  `Dance Bear`, `0:1866613407`.

Legacy Perl `rewardTeam` rewards the current team-bound player set and does
not check a per-player activity timestamp during the reward fan-out. Stale
players are removed only by the periodic timeout scan after event handling.
Python was pruning before processing the current event and used a fixed
30-second cadence, which could evict the stale player before the `CTs_Win`
reward that legacy still records.

## Fix

- Keep generic damage-only lines from reactivating team-reward membership.
- Run idle cleanup after the current event has been processed.
- Use the deterministic upper bound of the legacy timeout scan cadence
  (`60` seconds) for replay instead of pruning every fixed `30` seconds.
- Keep stale connected players removable when the timeout scan actually runs.

## Verification

Targeted storage subset:

```powershell
$env:PYTHONPATH='scripts;scripts\proxy_daemon_py'
python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-p6d-green5 `
  scripts\hlstats_py\tests\test_storage.py -q `
  -k "team_bonus_rewards_idle_player_before_legacy_timeout_cleanup or generic_attack_does_not_reactivate_idle_player_before_team_bonus or prune_idle_players_removes_stale_legacy_live_roster_member or record_prunes_idle_players_on_legacy_timeout_cadence or record_does_not_prune_idle_players_at_exact_legacy_timeout_boundary or idle_prune_reschedules_to_legacy_timeout_scan_upper_bound or prune_idle_players_flushes_profile_name_before_eviction"
```

Result: `7 passed, 117 deselected`.

Broader targeted runtime/storage subset:

```powershell
$env:PYTHONPATH='scripts;scripts\proxy_daemon_py'
python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-p6d-green6 `
  scripts\hlstats_py\tests\test_runtime.py scripts\hlstats_py\tests\test_storage.py -q `
  -k "db_write_trace or runtime_projects_round_status_for_team_trigger_rewards or runtime_projects_round_status_for_goldsrc_bomb_defused or team_bonus_rewards_idle_player_before_legacy_timeout_cleanup or generic_attack_does_not_reactivate_idle_player_before_team_bonus or prune_idle_players_removes_stale_legacy_live_roster_member or record_prunes_idle_players_on_legacy_timeout_cadence or record_does_not_prune_idle_players_at_exact_legacy_timeout_boundary or idle_prune_reschedules_to_legacy_timeout_scan_upper_bound or prune_idle_players_flushes_profile_name_before_eviction or team_bonus_awards_live_roster_player_without_active_or_reward_eligible_entry or team_bonus_awards_team_bound_player_without_live_roster or team_bonus_deduplicates_same_signature"
```

Result: `14 passed, 124 deselected`.

Single-log replay:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile .\scripts\replay_baseline\artifacts\L0102211.log `
  -Name p6d-team-bonus-cts-win-L0102211-after-timeout-cadence `
  -TraceTable hlstats_Events_TeamBonuses
```

Result:

- direct import summary: `files=1`, `records=3352`, `elapsed_s=9.553`
- stable TeamBonuses SQL: `legacy=156`, `python=156`
- legacy-only stable keys: none
- python-only stable keys: none

Full narrow contour:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore

python .\scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Result:

- legacy import: `processed=1000`, `errors=0`, `lines=672223`,
  `dropped_lines=1969`, `elapsed=148.610s`
- run state:
  `scripts/replay_baseline/comparison/.parity-state/20260523-012322.json`
- compare now reports logical differences in `4` tables instead of `5`
- `hlstats_Events_TeamBonuses` no longer appears in the logical compare

Direct stable-key TeamBonuses SQL after the full contour:

- `legacy=4753`
- `python=4753`
- legacy-only stable keys: none
- python-only stable keys: none

## Result

`hlstats_Events_TeamBonuses` improved from:

- `4765/4764`
- `1` legacy-only / `0` python-only normalized rows

to:

- absent from `compare_stats_dbs.py`
- stable-key SQL `4753/4753`
- `0` legacy-only / `0` python-only stable-key differences

Other current logical diff counts after this run:

- `hlstats_Players`: `250` legacy-only / `250` python-only normalized rows.
- `hlstats_PlayerNames`: `2` legacy-only / `3` python-only normalized rows.
- `hlstats_Players_History`: `50` legacy-only / `50` python-only normalized
  rows.
- `hlstats_Events_Entries`: accepted `0/1017` legacy/Python policy difference.
