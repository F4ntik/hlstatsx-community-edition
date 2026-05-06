# Next Chat Task

Workspace:
`D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n`

Branch:
`refactor/parity-runtime-decisions`

Latest continuation (2026-05-06):

- Continued the derived combat/reward cluster with a legacy-confirmed suicide
  streak boundary. Legacy `doEvent_Suicide()` calls `endKillStreak()` before
  recording the suicide; Python now mirrors that by ending the active
  `kills_per_life` streak before `_record_suicide()`.
- Regression added: `test_suicide_ends_active_kill_streak`.
- Validation so far:
  `PYTHONPATH=scripts;scripts\proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-suicide-green scripts\hlstats_py\tests\test_storage.py -q -k suicide_ends_active_kill_streak`
  -> `1 passed, 66 deselected`;
  `PYTHONPATH=scripts;scripts\proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-storage-suicide scripts\hlstats_py\tests\test_storage.py -q`
  -> `67 passed`;
  `PYTHONPATH=scripts;scripts\proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-target-suicide scripts\hlstats_py\tests\test_events.py scripts\hlstats_py\tests\test_runtime_decisions.py scripts\hlstats_py\tests\test_storage.py -q`
  -> `86 passed`.
- Expected next replay impact: this should reduce residual kill-streak
  `PlayerActions` / `Actions.kill_streak_*` timing drift where a player ends a
  multi-kill life by suicide. It intentionally does not touch broad
  `Chat`/`ChangeTeam`, accepted `Entries`, or TeamBonuses roster policy.

- Current pass was cluster-first, not `fnat1k`-only. Residuals were split into:
  identity/naming/encoding; derived combat/reward counters; event-policy drift;
  accepted differences.
- Dense cluster 1 closed: ignored-bot `"changed name to"` events no longer
  mutate runtime/profile alias state. This closed the bot encoding spillover
  around `49.5 % karrigan` vs `49.5 ％ karrigan`; `PlayerUniqueIds` no longer
  appears in fresh residual compare output.
- Dense cluster 2 closed: Statsme telemetry triggers `time` and `latency` are
  now ignored before `Actions` / `PlayerActions` writes. They are legacy
  telemetry inputs, not player-action awards.
- Regressions added:
  `test_ignore_bots_skips_name_change_profile_update` and
  `test_record_action_skips_status_noise_triggers`.
- Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-clusters scripts\hlstats_ftp_py\tests scripts\hlstats_py\tests\test_events.py scripts\hlstats_py\tests\test_runtime_decisions.py scripts\hlstats_py\tests\test_storage.py -q`
  -> `98 passed`;
  `docker compose build hlstats-worker` -> success;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
  -> success, valid legacy contour reused.
- Fresh compare headline: expected exit `1`, now `10` residual tables.
  `Actions` row count aligned `754/754`; `PlayerActions` improved from
  `4972/6019` to `4972/4977`; `PlayerUniqueIds` disappeared from residual
  output; `PlayerNames` normalized drift improved to `3/4`;
  `Players_History` normalized drift improved to `106/106`; `Players`
  normalized drift improved to `250/250`.
- Remaining open clusters:
  `Servers.act_players/suicides`, `Actions.kill_streak_*`, kill-streak timing
  in `PlayerActions`, `TeamBonuses +9`, broad `ChangeTeam`/`Chat`, and the
  accepted visible `Entries 0/1017`.
- The regenerated
  `docs/audits/legacy-python-parity-20260423/python-sql-snapshot-1000.txt` is
  a replay artifact and should stay out of the intended diff unless explicitly
  requested.

- Continued the remaining `fnat1k` alias-touch trace with two more
  object-lifecycle boundaries instead of a one-row fix.
- Python now marks player objects as closed after idle-prune cleanup and after
  `Started map` roster reset, so the next same-name touch reopens alias use as
  a legacy-style constructor/reconnect boundary.
- Important constraint: `Started map` still does **not** flush deferred profile
  names or `PlayerNames` stat rollups; this slice changes alias-use semantics
  only.
- Regressions added:
  `test_reconnect_after_started_map_counts_alias_use_for_same_userid` and
  `test_reconnect_after_idle_prune_counts_alias_use_for_same_userid`.
- Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-fnat1k scripts\hlstats_py\tests\test_storage.py -q`
  -> `63 passed`;
  targeted FTP/event/runtime/storage suite with external basetemp -> `95 passed`.
- Earlier replay-pending state from this lifecycle slice is superseded by the
  cluster pass above: narrow-1000 replay and compare completed after the
  bot-name and Statsme telemetry slices.
- Broader human `PlayerNames` attribution was handled as cluster `LP-P6D-004B`,
  not as one-off `X3` / `fnat1k` / `SayNor` fixes.
- Python now defers `hlstats_PlayerNames` stat rollups until player/profile
  flush boundaries. Stdin transaction commits are not player flushes; profile
  flushes still happen at `finalize_import()`, `flush_pending()`,
  disconnect/idle cleanup, and same-unique userid handoff.
- Alias `numuses` now treats explicit name-change touches, stable-unique
  new-userid handoff, and disconnect/reconnect as legacy-style object/lifecycle
  alias touches.
- Rejected investigation: flushing rollups before every explicit name change
  was replay-tested and regressed `PlayerNames` back to `64/65`; do not reapply
  it without a narrower legacy player-object lifecycle trace.
- Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-playernames4 scripts\hlstats_py\tests\test_storage.py -q`
  -> `61 passed`;
  targeted FTP/event/runtime/storage suite with external basetemp -> `93 passed`;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
  -> success, valid legacy contour reused;
  `compare_stats_dbs.py --max-examples 1` -> expected exit `1`.
- Result:
  `hlstats_PlayerNames` normalized drift improved from `64/65` to `34/35`.
  `0:1838619084` (`X3`) now matches alias `numuses` and stats, including
  `X3 numuses=3`.
  `0:2084898310` (`SayNor`) now matches alias split/stats.
  `0:36417680` (`fnat1k`) now has matching per-alias stat totals, but
  `numuses` remains `legacy=106`, Python `103` across `CS: zero condition`,
  `fnat1k`, and `mUrkovskii`.
- The regenerated `python-sql-snapshot-1000.txt` was restored and should not be
  part of the intended diff.
- Next precise task: trace only the remaining `fnat1k` alias-touch-only misses
  against legacy constructor/name-change/reconnect object boundaries. Do not
  reopen player-count / `STEAM_ID_LAN`, `1:45686725`, `0:723234133`,
  TeamBonuses +9, ChangeTeam, Connects, broad Chat, or broad PlayerActions.

Latest continuation (2026-05-05):

- Legacy Perl was checked for the `0:723234133` current-name anchor before
  changing the parity runner. Perl applies `"changed name to"` through
  `doEvent_ChangeName` / `setName(newname)` and persists the live profile name
  on disconnect/cleanup flush.
- Python storage/name-change behavior already matched that shape in a direct
  two-file filename-ordered import. The clean narrow replay mismatch was caused
  by Python FTP parity import order: `hlstats_ftp_py` sorted eligible logs by
  modification time, while the legacy/reference narrow-1000 window is sorted by
  filename.
- Implemented `hlstats_ftp_py --order-by-name` with regression
  `test_entries_to_download_can_order_by_name_for_replay_parity`; production
  default remains mtime sorting.
- `scripts/replay_baseline/comparison/Run-DualContour-1000.ps1` now passes
  `--order-by-name` for the Python parity contour only.
- Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-final-order scripts\hlstats_ftp_py\tests scripts\hlstats_py\tests\test_events.py scripts\hlstats_py\tests\test_runtime_decisions.py scripts\hlstats_py\tests\test_storage.py -q`
  -> `88 passed`;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
  -> success; host-side GeoIP backfill -> exit `0`;
  `compare_stats_dbs.py --max-examples 1` -> expected exit `1` for `11`
  residual tables.
- Closed anchor: `0:723234133` now matches Python to legacy:
  `lastName=Райымбек Гослинг`, kills/deaths `3/4`, `KZ/Kazakhstan`, aliases
  `Player=2` and `Райымбек Гослинг=2`.
- Stable anchors: `1:45686725` remains `Mep3ocTb`, `198/179`, `RU/Russia`;
  `0:1838619084` remains current-name aligned as `X3`, `138/71`, with the
  known alias `X3 numuses legacy=3` vs Python `2` still open.
- Current compare headline: `11` residual tables. Focused residuals include
  `PlayerUniqueIds 31/31`, `PlayerNames 64/65`, `Players_History 195/195`,
  `TeamBonuses 4765/4774`, `Entries 0/1017`, `Statsme 32290/32290`, and
  `Statsme2 32290/32290`. The TeamBonuses move from `4773` to `4774` is
  explained by corrected parity input order and remains diagnostic backlog.
- Restore/remove generated replay artifacts before handoff; the regenerated
  `docs/audits/legacy-python-parity-20260423/python-sql-snapshot-1000.txt`
  should not be part of the intended diff unless explicitly requested.

Start strictly with:

```powershell
git status --short --branch
git log --oneline --decorate --graph --max-count=20 --all
Get-Content AGENTS.md
Get-Content docs/status.md
Get-Content docs/plans.md
Get-Content docs/replay-fast-path.md
Get-Content docs/parity-runtime-decisions-refactor.md
Get-Content docs/parity-acceptance-policy.md
Get-Content docs/next-chat-task.md
```

Current state:

- RC-B scoped `amx_chat` fix is implemented:
  unresolved no-victim `<><><> triggered "amx_chat"` no longer writes
  `playerId=0` PlayerActions rows or increments `hlstats_Actions`.
- RC-C bot-policy fix is implemented:
  with `IgnoreBots=1`, bot profiles are hidden/reset (`skill=0`,
  `hideranking=1`) and bot-owned `Frags`, `PlayerActions`, `Chat`,
  `Statsme`, and `Statsme2` are skipped.
- RC-C human player-count fix is implemented:
  transient legacy-invalid unique ids (`UNKNOWN`, `STEAM_ID_PENDING`,
  `STEAM_ID_LAN`, `VALVE_ID_PENDING`, `VALVE_ID_LAN`) do not create visible
  player-owned rows, and `STEAM_[0-9]+:` ids are stored in the legacy canonical
  form.
- The extra visible Python human was:
  `STEAM_ID_LAN`, `en.prime-server.info BUY PLAYER` /
  `Boost en.Prime-server.info`, address `54.74.101.183`.
- Regression coverage added:
  - `test_record_action_skips_unresolved_server_actor_without_victim`;
  - `test_ignore_bots_marks_bot_hidden_and_skips_chat`;
  - `test_ignore_bots_skips_frag_when_bot_participates`;
  - `test_ignore_bots_skips_action_when_target_is_bot`;
  - `test_ignored_bot_profile_cache_is_cleared_on_rollback`;
  - `test_transient_lan_unique_id_connect_does_not_create_visible_player`;
  - `test_transient_lan_unique_id_chat_does_not_create_player_or_chat`;
  - `test_steam3_unique_id_is_stored_with_legacy_canonical_form`.
- Validation completed:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py -q`
    -> `50 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests`
    -> `120 passed`;
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
    -> success, valid legacy contour reused;
  - `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
    -> exit `1` as expected for residual documented differences.
- Current post-fix direct SQL anchors:
  - `Players 323/323`;
  - visible players `250/250`;
  - bots `73/73`, visible bots `0/0`, `skill1000_bots 0/0`;
  - `STEAM_ID_LAN` unique rows `0/0`;
  - canonical `0:247752695` unique rows `1/1`;
  - `Connects 992/992`;
  - `Chat 608/662`;
  - `PlayerActions 4972/6019`;
  - `PlayerPlayerActions 0/0`;
  - `Frags 5464/5464`;
  - `Statsme 32290/32290`;
  - `Statsme2 32290/32290`;
  - `TeamBonuses 4765/4773`;
  - `Events_Entries 0/1017`.
- The regenerated `python-sql-snapshot-1000.txt` was restored and is not part
  of the working diff.
- Concrete next RC-C identity/name anchor:
  `uniqueId=1:45686725`, `playerId=187`, same aggregate kills/deaths in both
  DBs (`198/179`) but different current name:
  legacy `hlstats_Players.lastName=Mep3ocTb`, Python `Ра-та-та`; both
  `hlstats_PlayerNames` contain `Mep3ocTb`, `Ра-та-та`, and
  `Mep3ocTb Новогодняя`. This is name/current-name attribution drift, not a
  reopened player-count issue.
- `Actions` and `Weapons` still have compare differences. Current direct SQL
  shows top weapon aggregate kills/headshots match 1:1 on the narrow-1000
  contour, while `hlstats_Actions` differs in derived/extra action counters
  (`time`, `latency`, kill-streak counts). Treat these as downstream
  diagnostics unless identity/headshot/action attribution proves a narrower
  visible-impact fix.
- Current-name follow-up started:
  Python now defers `hlstats_Players.lastName` updates out of normal player
  resolve and writes the cached profile name on disconnect via
  `_flush_player_profile_name`, while keeping immediate `hlstats_PlayerNames`
  tracking. This follows the legacy Perl split where `setName` touches
  `PlayerNames` immediately but `lastName` is persisted through `flushDB`.
- New/updated regression coverage:
  - `test_player_last_name_is_deferred_until_disconnect`;
  - `test_record_chat_reuses_cached_player` now expects no immediate
    `hlstats_Players.lastName` update;
  - `test_lookup_does_not_merge_name_only_players_without_unique_id` now
    expects profile-name updates to stay deferred.
- Validation from the current run:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py -q`
    -> `51 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\hlstats-pytest-basetemp-current" scripts/hlstats_py/tests`
    -> `121 passed`;
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
    -> success, valid legacy contour reused;
  - `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
    -> exit `1` as expected for residual documented differences.
- Current-name / GeoIP anchor result:
  direct SQL now shows `uniqueId=1:45686725`, `playerId=187`,
  `hlstats_Players.lastName=Mep3ocTb`, and kills/deaths `198/179` on both
  contours. Both `hlstats_PlayerNames` sets contain the same three aliases.
  The initial remaining difference on that row was GeoIP: legacy `Russia/RU`,
  Python empty. This was checked by running GeoIP backfill against the Python
  contour after replay.
- GeoIP backfill result:
  the command shape from the previous note using `scripts/hlstats.conf` fails in
  this local host-side contour because that config has blank DB settings and
  overrides CLI DB flags. The successful host-side command was run from
  `scripts/` so the resolver could find `GeoLiteCity/GeoLite2-City.mmdb`:
  ```powershell
  $env:PYTHONPATH=".;proxy_daemon_py"
  python -m hlstats_awards_py --db-host 127.0.0.1:3327 --db-name hlstatsxce --db-username hlstatsxce --db-password hlx123 --geoip --replay-mode
  ```
  It exited `0`. Post-backfill SQL shows the `1:45686725` row now fully
  matches: `playerId=187`, `lastName=Mep3ocTb`, kills/deaths `198/179`,
  `flag=RU`, `country=Russia`, `lastAddress=178.68.210.14` on both contours.
  Python has `0` players with non-empty `lastAddress` and empty `flag`/`country`.
  A fresh `compare_stats_dbs.py --max-examples 20` still exits `1` for `15`
  documented residual tables.
  The regenerated `python-sql-snapshot-1000.txt` was restored and is not part
  of the working diff.
- Ignored-bot `Players_History` follow-up completed:
  legacy creates ignored-bot history rows with the default history skill and
  resets only the persisted player profile to `skill=0` / `hideranking=1`.
  Python now keeps that split by no longer mutating the in-memory skill cache in
  `_apply_ignored_bot_profile`.
- New regression coverage:
  - `test_ignore_bots_keeps_history_seed_skill_at_legacy_default`.
- Validation from the latest run:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py -q`
    -> `52 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\hlstats-pytest-basetemp-current" scripts/hlstats_py/tests`
    -> `122 passed`;
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
    -> success, valid legacy contour reused;
  - host-side GeoIP backfill command above -> exit `0`;
  - `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 5`
    -> exit `1` as expected for `15` documented residual tables.
- Current post-follow-up direct SQL / focused compare anchors:
  - `hlstats_Players_History 659/659`;
  - Python bot history rows with `skill=0`: `0`;
  - `uniqueId=1:45686725` remains aligned with `lastName=Mep3ocTb`, kills/deaths
    `198/179`, `flag=RU`, `country=Russia`, `lastAddress=178.68.210.14`;
  - Python players with non-empty `lastAddress` and empty `flag`/`country`: `0`;
  - focused identity compare: `PlayerUniqueIds 2/2`, `PlayerNames 47/38`,
    `Players_History 111/111`.
  The regenerated `python-sql-snapshot-1000.txt` was restored and is not part
  of the working diff.

Do next:

Current continuation after the 2026-04-30 ignored-bot history pass:
the current diff has been reviewed, storage/full `scripts/hlstats_py/tests`
passed in the prior validated run, narrow-1000 replay passed with reused legacy,
the `1:45686725` current-name/GeoIP anchor is closed, and the ignored-bot
history seed artifact is closed. A behavior-neutral identity decision
extraction was then added: `runtime_decisions.py` now owns
`canonical_unique_id`, `is_transient_unique_id`, and
`should_persist_player_identity`, with `storage.py` delegating stable/transient
identity decisions to that layer.

Latest validation:
- `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p no:cacheprovider --basetemp <workspace-temp> scripts/hlstats_py/tests/test_runtime_decisions.py scripts/hlstats_py/tests/test_storage.py -q`
  -> `60 passed` after adding the import-tail profile-name flush regression.
- Full `scripts/hlstats_py/tests` with pytest cache disabled and external
  basetemp -> `126 passed`.
- Narrow-1000 replay:
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` -> success, valid legacy contour reused.
- Host-side GeoIP backfill against the restored Python contour -> exit `0`.
- Fresh `compare_stats_dbs.py --max-examples 5` still exits `1` for the
  documented 15 residual tables. Current focused anchors:
  `PlayerUniqueIds 1/1`, `PlayerNames 45/36`, `Players_History 110/110`,
  `TeamBonuses 4765/4773`, `Statsme 32290/32290`, `Statsme2 32290/32290`.
- The regenerated `python-sql-snapshot-1000.txt` was restored and is not part of
  the intended diff.

Latest code follow-up:
- Legacy periodic/shutdown `flushDB` writes live players' current profile names
  even without a disconnect line. Python now mirrors that in
  `EventStorage.finalize_import()` and `EventStorage.flush_pending()` by
  flushing cached profile names before `_FINALIZE_PLAYER_LAST_EVENT_QUERY` /
  shutdown commit.
- Same-unique/new-userid handling now flushes the previous live profile name and
  clears alias-use suppression for the new userid. This mirrors the legacy
  `getPlayerInfo` handoff far enough to count repeated alias uses.
- Idle eviction now flushes cached profile names before removing stale active
  players from in-memory tracking, mirroring legacy timeout cleanup through
  `removePlayer` / `playerCleanup` / `flushDB`.
- Regressions added:
  `test_finalize_import_flushes_deferred_player_profile_names`,
  `test_flush_pending_flushes_deferred_player_profile_names`,
  `test_unique_id_reconnect_counts_alias_use_for_new_userid`, and
  `test_prune_idle_players_flushes_profile_name_before_eviction`.
- Latest validation in this continuation:
  `test_runtime_decisions.py test_storage.py -q` -> `63 passed`;
  full `scripts/hlstats_py/tests` -> `129 passed`;
  narrow-1000 replay with reused valid legacy contour -> success;
  host-side GeoIP backfill -> exit `0`.
- Direct SQL after replay/backfill: `0:723234133` now matches alias
  `numuses` (`Player=2`, `Райымбек Гослинг=2`) and profile kills/deaths
  `3/4`, `KZ/Kazakhstan`, `lastAddress=95.58.206.38`, but the current profile
  name remains open: legacy `lastName=Райымбек Гослинг`, Python
  `lastName=Player`. `0:1838619084` remains current-name aligned as `X3` with
  kills/deaths `138/71`; the remaining narrow alias artifact there is
  `X3 numuses legacy=3`, Python `2`.
- Latest local follow-up in this run: Python now handles parsed
  `"changed name to"` events as `change_name` updates instead of only generic
  admin noise. Storage applies the new name to `hlstats_PlayerNames` and the
  deferred `hlstats_Players.lastName` cache, while avoiding an old-alias
  `numuses` increment for already-known live players. Regression:
  `test_name_change_updates_deferred_profile_name`.
- Latest validation in this run:
  - targeted `test_events.py test_runtime_decisions.py test_storage.py -q`
    -> `76 passed`;
  - broad `scripts/hlstats_py/tests -k "not heatmap and not load_settings"`
    -> `122 passed, 8 deselected`;
  - full `scripts/hlstats_py/tests` still cannot finish cleanly in this
    Windows session because pytest basetemp/session cleanup raises `WinError 5`;
  - Docker replay/compare was not runnable because Docker API access returned
    `permission denied`.
- 2026-05-05 automation continuation reviewed this diff for consistency and
  made only behavior-neutral cleanup:
  - `test_events.py` now asserts parsed name-change updates carry
    `event_code="change_name"` and `attributes["new_name"]`;
  - `storage.py` no longer carries the stale
    `_touch_player_profile(..., track_name_history=...)` parameter.
- Validation from the 2026-05-05 continuation:
  - targeted `test_events.py test_runtime_decisions.py test_storage.py -q`
    with `-p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-automation`
    -> `76 passed`;
  - broad `scripts/hlstats_py/tests -k "not heatmap and not load_settings"`
    with external basetemp -> `122 passed, 8 deselected`.

Continue with broader human `PlayerUniqueIds` / `PlayerNames` /
`Players_History` attribution drift; the older `1:45686725` anchor is retained
as history but no longer requires reopening.

1. Review the current diff for code/docs consistency.
2. Treat the player-count blocker as closed; do not reopen `STEAM_ID_LAN`.
3. If continuing RC-C, focus on remaining `PlayerUniqueIds` / `PlayerNames` /
   `Players_History` name/current-name, GeoIP, and history attribution drift;
   start with the `1:45686725` / `Mep3ocTb` vs `Ра-та-та` example above.
   Note: the `1:45686725` current-name mismatch is now closed. Its GeoIP
   mismatch must be checked only after running the separate GeoIP backfill
   command above. Update: the GeoIP backfill has now been run successfully and
   the `1:45686725` current-name/GeoIP anchor is closed; continue with broader
   `PlayerUniqueIds` / `PlayerNames` / `Players_History` attribution drift.
   Update after the ignored-bot history pass: `1:45686725` current-name/GeoIP
   and ignored-bot history skill drift are closed. Continue with human
   attribution examples such as `0:1838619084` (`X3` vs `make me laugh`),
   `0:723234133` (`Райымбек Гослинг` vs `Player`), and `PlayerNames` stat
   splits for `fnat1k`, `SayNor`, and `Rakza`.
4. Do not chase TeamBonuses `+8`.
5. Do not change ChangeTeam / Connects / broad Chat without new visible-impact
   evidence.
6. Treat remaining PlayerActions drift as diagnostic unless identity/headshot/
   action attribution proves a narrower must-fix subset.
7. Do not commit regenerated replay artifacts without an explicit decision.
