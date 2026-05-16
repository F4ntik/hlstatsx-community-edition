# Status: Standalone Python+i18n Product Lane

## Snapshot

- 2026-05-15 automation continuation: traced the remaining visible positive
  `skill` drift with two subagents against legacy Perl and Python storage.
  Both traces converged on reward-path behavior rather than combat counters:
  legacy `PlayerPlayerActions` applies `reward_player` to the actor and the
  symmetric negative delta to the victim, while Python only rewarded the actor.
  This matches the symptom from the previous replay: kills/deaths/headshots/
  suicides/teamkills match for all common players, but Python visible skill is
  `+415`. Added RED-first regression
  `test_player_player_action_penalizes_victim_skill_like_legacy` and updated
  `_record_action()` so victim-targeted player-player action bonuses now write
  `hlstats_Players.skill -= reward_player` and the matching
  `hlstats_Players_History.skill_change` delta through the existing rollup
  path. Local validation:
  targeted RED/green test passed, and
  `test_runtime_decisions.py test_storage.py -q` reports `113 passed`.
  Replay is still pending for this slice because `docker compose build
  hlstats-worker` could not acquire `C:\Users\semer\.docker\buildx\.lock`
  (`Access is denied`) in this sandbox. Next run should rebuild
  `hlstats-worker`, rerun narrow-1000 with `-ReuseValidLegacy`, run GeoIP
  backfill, and compare whether the visible skill sum drops toward legacy
  before chasing team bonus or history flush cadence.

- 2026-05-15 implementation continuation: completed the first narrow
  `connection_time` parity slice in `scripts/hlstats_py/storage.py`.
  Root-cause review against legacy Perl confirmed that `HLstats_Player::updateDB`
  computes elapsed session time from the last player flush timestamp, clamps
  gaps over `600` seconds to `0`, and writes the same delta into
  `hlstats_Players`, `hlstats_PlayerNames`, and `hlstats_Players_History`.
  Python already had partial PlayerNames/history SQL support, but no elapsed
  session clock, no `hlstats_Players.connection_time` update path, and a
  literal `0` history rollup. Python now tracks a per-player connection-time
  flush timestamp/context, writes `hlstats_Players.connection_time += delta`,
  forwards the same delta through PlayerNames rollups and same-day history
  updates, flushes open sessions from `finalize_import()` / `flush_pending()`,
  and flushes/reset sessions on close boundaries such as disconnect, idle
  close, map-start stale close, and userid rollover. A review-found reconnect
  bug was fixed before handoff: true session close now clears the time baseline
  so offline gaps are not counted after reconnect. RED-first regressions added:
  `test_disconnect_flushes_player_connection_time_rollups`,
  `test_finalize_import_flushes_open_player_connection_time`,
  `test_flush_pending_clamps_connection_time_gap_above_600_seconds`, and
  `test_reconnect_does_not_count_offline_gap_into_connection_time`. Local
  validation: targeted connection-time pytest reports `4 passed, 99 deselected`;
  `test_runtime_decisions.py test_storage.py -q` reports `110 passed`. Replay is
  now complete for this slice: `docker compose build hlstats-worker` succeeded,
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` succeeded, host-side GeoIP backfill exited `0`, and
  `compare_stats_dbs.py --max-examples 5` still exits `1` for `8` residual
  tables. The systemic zero is closed but exact parity is not:
  `connection_time` counts moved from Python `0/0/0` to `285/325/438` for
  `Players` / `PlayerNames` / `Players_History`, versus legacy `298/336/311`.
  The `Alex` anchor moved from Python `connection_time=0` to `1976` versus
  legacy `1958`; `PlayerNames(Alex)` is also `1976` vs `1958`, while
  `numuses` remains `29` vs legacy `37` and skill remains `1713` vs `1679`.
  Aggregate sums show the next bug is flush/history attribution, not missing
  persistence: Python `Players` sum is `157145` vs legacy `155642`,
  `PlayerNames` sum is `157145` vs `155446`, and `Players_History` sum is
  `157145` vs legacy `108852`. Follow-up root-cause tracing isolated the
  largest history overcount to ignored bots: legacy writes bot
  `connection_time` into `Players` and `PlayerNames`, but leaves ignored-bot
  history `connection_time=0`. Python now mirrors that policy while preserving
  bot player/name totals. Added
  `test_ignore_bots_flushes_connection_time_without_history_delta`; targeted
  connection-time tests report `5 passed, 99 deselected`, and
  `test_runtime_decisions.py test_storage.py -q` reports `111 passed`. A second
  rebuild/replay/GeoIP/compare completed successfully. Post-fix SQL anchors:
  Python non-zero `connection_time` counts are `285/325/314`; sums are
  `Players=157145`, `PlayerNames=157145`, `Players_History=114139`; bot sums
  are `43006/43006/0`, matching the legacy ignored-bot history shape. Compare
  still exits `1` for the same `8` residual tables, with `Players 38/38`,
  `PlayerNames 2/3`, and `Players_History 90/90`. Next slice should continue
  human skill/session/alias attribution rather than reopening GeoIP,
  `act_players`, or one-row TeamBonuses/ChangeTeam drift.

- 2026-05-15 continuation: rebuilt `hlstats-worker`, reran the Python
  narrow-1000 contour with reused valid legacy
  (`Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy`), then ran the required host-side GeoIP backfill
  (`python -m hlstats_awards_py --configfile /app/hlstats.conf --geoip`
  through the comparison worker compose file). The 2026-05-14
  `_prune_idle_players_if_due()` equality fix is now replay-verified:
  `hlstats_Servers.act_players` closed and `hlstats_Servers` disappeared from
  fresh `compare_stats_dbs.py --max-examples 5` output. Current compare now
  exits `1` for `8` residual tables: `hlstats_Actions`
  `kill_streak_2 1065/1066`; `hlstats_Events_PlayerActions 4972/4973` with the
  single Python-only `Rakza` row at `2024-01-06 00:18:10` on `de_spay`;
  `hlstats_Events_ChangeTeam 1345/1344` with the single legacy-only
  `UNASSIGNED` row for `Rakza`; `hlstats_Events_TeamBonuses 4765/4764` with the
  single legacy-only `CTs_Win` row for `Dance Bear`; accepted
  `hlstats_Events_Entries 0/1017`; plus the broader identity/history cluster
  in `hlstats_Players`, `hlstats_PlayerNames`, and
  `hlstats_Players_History`. The new must-fix evidence is no longer abstract:
  direct SQL confirms player-facing `skill` and session drift for
  `playerId=162` / `uniqueId=1:507890084` (`Alex`) with
  `legacy skill=1679, connection_time=1958, PlayerNames.numuses=37` vs
  `python skill=1713, connection_time=0, PlayerNames.numuses=29`, while
  kills/deaths remain `141/159`. The `connection_time` gap is systemic, not a
  one-off page quirk: after fresh replay plus GeoIP backfill, legacy still has
  `hlstats_Players.connection_time > 0` for `298` players,
  `hlstats_PlayerNames.connection_time > 0` for `336` alias rows, and
  `hlstats_Players_History.connection_time > 0` for `311` history rows,
  whereas Python is `0/0/0`. GeoIP is back in the expected post-replay state
  (`lastAddress <> ''` with empty `flag`/`country` is `0`), so the remaining
  `Players` drift is no longer a missing-backfill artifact. Next task should
  treat `connection_time` persistence plus the linked `skill` / alias-use /
  history attribution drift as the new primary must-fix slice; do not reopen
  the now-closed `act_players` work.

- 2026-05-14 automation continuation: continued the
  `hlstats_Servers.act_players` residual instead of moving to a new parity
  cluster. Legacy tracing confirmed that Perl's `Started map` clears player
  `team` / `trackable` state but does not remove human `srv_players`, and that
  idle cleanup only runs when `next_timeout < ev_daemontime`. Python's
  live-roster model was already the correct `srv_players` analogue, so the
  fix stayed on the exact timeout gate: `_prune_idle_players_if_due()` now
  waits until the event timestamp is strictly after the scheduled legacy sweep
  boundary instead of pruning at equality. Added
  `test_record_does_not_prune_idle_players_at_exact_legacy_timeout_boundary`
  to cover the equality edge and keep the existing before/after cadence
  regression intact. Also updated the in-memory replay validation database to
  accept the server suicide aggregate query emitted by the suicide parity path.
  Validation: focused act-player tests passed; targeted
  storage/events/runtime-decisions suite reports `118 passed`; broad
  `scripts/hlstats_py/tests -k "not heatmap and not load_settings"` reports
  `164 passed, 8 deselected`. Full unfiltered `scripts/hlstats_py/tests`
  remains blocked in this Windows session by `tmp_path` permission errors for
  heatmap/load-settings tests, but the unrelated replay validation failure was
  fixed. Docker replay/build was not run because Docker API access returned
  `permission denied` on `npipe:////./pipe/dockerDesktopLinuxEngine`. Next run
  should rebuild `hlstats-worker`, rerun the narrow-1000 Python contour with
  `-ReuseValidLegacy`, then confirm whether `act_players` moves from Python
  `0` back to legacy `4`.

- 2026-05-13 overlay: traced the remaining `hlstats_Servers.act_players`
  `4/0` residual back to legacy idle-cleanup cadence. Legacy Perl writes
  `act_players` from `%srv_players` via `HLstats_Server::updatePlayerCount()`;
  `Loading map` removes bots but keeps human player objects, `Started map`
  resets team/trackable state without removing them, and idle cleanup only runs
  when `next_timeout < ev_daemontime` before scheduling the next sweep 30-60s
  later. Python had been pruning stale live-roster members before every event,
  so silent map-tail humans could disappear before the equivalent legacy final
  server flush. Added `_server_next_idle_prune_at` and a legacy-like
  `record()` prune cadence, with RED-first regression
  `test_record_prunes_idle_players_on_legacy_timeout_cadence`. Validation:
  focused cadence tests passed, and targeted
  storage/events/runtime-decisions suite reports `117 passed` with only local
  pytest-cache permission warnings. Replay/compare is still pending for this
  cadence slice; next run should verify whether `act_players` moves from
  Python `0` back toward legacy `4`. A review subagent flagged the existing
  `docs/audits/legacy-python-parity-20260423/python-sql-snapshot-1000.txt`
  dirty change as questionable provenance for the old audit directory; do not
  rely on or commit that artifact without regenerating/relocating evidence.

- 2026-05-13 overlay: continued the narrow `hlstats_Servers.act_players`
  source trace without moving on to Rakza. Focused regressions now cover three
  live-roster edges: `Dropped_The_Bomb` does not create legacy live-roster
  membership, `Loading map` removes bot live-roster members like legacy Perl,
  and connect/userid-rollover live entries keep a fresh activity timestamp so
  idle prune can later remove silent reconnects. The traced overcount source
  for the prior Python `12` was all BOT roster members surviving `Loading map`;
  after bot cleanup the full contour returned to Python `0` vs legacy `4`.
  A deliberately narrow connect-source check showed raw connect membership can
  overgrow to Python `14`, and the rollover/activity fix prunes that back to
  Python `0`; therefore the remaining `4` legacy live members are not explained
  by broad connect growth and still need a narrower legacy source/cadence trace
  before touching combat or rewards. Validation: targeted
  storage/events/runtime-decisions suite reports `116 passed`; `docker compose
  build hlstats-worker` succeeded; narrow-1000 dual contour with
  `-ReuseValidLegacy` succeeded; host-side GeoIP backfill exited `0`; fresh
  compare still exits `1` with `9` residual tables. Current residual movement:
  `hlstats_Servers.act_players` is legacy `4` vs Python `0`; `kill_streak_2`
  remains legacy `1065` vs Python `1066` with the single Python-only Rakza
  `hlstats_Events_PlayerActions` row at `2024-01-06 00:18:10` on `de_spay`;
  `hlstats_Events_ChangeTeam` remains `1345/1343` with only the two
  legacy-only `UNASSIGNED` rows (`Rakza`, `Baggio`);
  `hlstats_Events_TeamBonuses` remains `4765/4763` with only the two
  legacy-only rows (`Planted_The_Bomb` for `*психоделия*`, `CTs_Win` for
  `Dance Bear`). `PlayerNames`, `Players`, `Players_History`, and accepted
  `Entries 0/1017` remain intentionally deferred.

- 2026-05-07 overlay: continued the clustered lifecycle parity fix instead of
  chasing individual compare rows. Added a separate Python live-roster model
  for `hlstats_Servers.act_players`, kept it across `Started map`, pruned stale
  live roster members on idle cleanup, and limited live-roster growth to
  explicit connect/team-selection sources instead of every chat/action
  descriptor. Player object close now clears runtime team and per-life combat
  state; disconnect ends an active kill streak at the disconnect timestamp
  before later round drains can see stale `_player_kills_per_life`. Regression
  coverage added/updated for legacy live roster semantics, cache-hit team
  selection live restore, chat descriptors not inflating DB live roster,
  map-start live roster preservation, stale live roster prune, kicked stale
  `UNASSIGNED` suppression, and disconnect kill-streak drain. Validation:
  targeted storage/events/runtime-decisions suite reports `111 passed`;
  `docker compose build hlstats-worker` succeeded; narrow-1000 dual contour
  with reused valid legacy succeeded; host-side GeoIP backfill completed with
  exit `0`; fresh compare still exits `1` with `9` residual tables. Movement:
  `hlstats_Servers.act_players` improved from Python `0` to Python `12`
  against legacy `4` after intermediate over-broad live roster checks at `62`
  and `30`, so it remains open and needs tracing of the final 12 live-roster
  members. `hlstats_Events_ChangeTeam` improved from `1345/1357` with Python-only
  `UNASSIGNED` rows to `1345/1343` with `2` legacy-only and `0` Python-only
  examples (`Rakza`, `Baggio`). `hlstats_Events_TeamBonuses` moved from mixed
  `2` legacy-only / `3` Python-only at `4765/4766` to `4765/4763` with only
  the two legacy-only rows (`Planted_The_Bomb` for `*психоделия*` and
  `CTs_Win` for `Dance Bear`); no direct reward-roster patch was made because
  the stale Python-only rewards are gone. `kill_streak_2` improved from legacy
  `1065` vs Python `1067` to `1065/1066`, leaving one Python-only
  `hlstats_Events_PlayerActions` row for `Rakza` at `2024-01-06 00:18:10`
  on `de_spay`. `PlayerNames`, `Players`, `Players_History`, and accepted
  `Entries 0/1017` remain deferred residuals until the remaining
  live-roster/combat roots settle.

- 2026-05-07 overlay: continued narrow-1000 parity residual work with focused
  RED-first regressions for the derived combat/team counter cluster. Python no
  longer drains `kills_per_life` on `Restart_Round_(1_second)`; world-action
  kill-streak drains now match the legacy `Round_End` / `Round_Win` /
  `Mini_Round_Win` set, with death/suicide/disconnect remaining as life-end
  boundaries. Implicit team sync now primes cached ignored status triggers far
  enough to preserve a blank runtime team baseline and emit the subsequent
  blank -> `UNASSIGNED` transition, while closed player objects and userid
  rollovers do not seed that blank baseline. Server `act_players` refreshes now
  use the trackable active set instead of connected count for ordinary presence
  updates; a map-start pre-clear flush/dirty guard is covered locally, but the
  final replay still shows the server counter residual open. New regressions:
  `test_restart_round_does_not_end_kill_streak_before_actual_life_end`,
  `test_implicit_team_change_emits_on_blank_to_unassigned_from_status_trigger`,
  `test_closed_player_blank_status_does_not_seed_implicit_change_team`,
  `test_server_act_players_uses_trackable_presence_not_connected_count`, and
  `test_started_map_flushes_preclear_roster_count_to_server_act_players`.
  Validation: targeted storage/events/runtime-decisions suite reports
  `105 passed`; `docker compose build hlstats-worker` succeeded; narrow-1000
  dual contour with reused valid legacy succeeded; host-side GeoIP backfill
  completed with exit `0`; fresh compare still exits `1` with `9` residual
  tables. Movement: `hlstats_Events_PlayerActions` improved from `4972/4976`
  to `4972/4974`, now only two Python-only `kill_streak_2` rows; `hlstats_Actions`
  row count remains `754/754` but `kill_streak_2` count is now legacy `1065`
  vs Python `1067`; `hlstats_Events_ChangeTeam` moved past the missing-row
  state to `1345/1357` with `1` legacy-only and `13` Python-only
  `UNASSIGNED` examples, so this remains open and needs a narrower lifecycle
  discriminator; `hlstats_Servers.act_players` remains open at legacy `4` vs
  Python `0`; `hlstats_Events_TeamBonuses` remains `4765/4766` with `2`
  legacy-only and `3` Python-only examples, so no direct reward-eligibility
  change was made in this slice. `PlayerNames`, `Players`, `Players_History`,
  and accepted `Entries 0/1017` remain residual follow-ups.

- 2026-05-06 overlay: closed the next narrow-1000 parity residual slice across
  suicide suppression/server counters, implicit team sync, chat policy, and
  same-unique userid rollover cleanup. Python now mirrors the legacy
  `last_team_change + 2 > event_time` suicide ignore window, increments the
  DB-backed `hlstats_Servers.suicides` aggregate on accepted suicides, filters
  legacy HLX command/buy-script chat before `hlstats_Events_Chat`, emits
  implicit `hlstats_Events_ChangeTeam` rows for known descriptor team drift
  while preserving bot/transient guards, and clears stale per-server live
  roster state on same-unique/new-userid handoff before applying the new
  descriptor. Note: Perl's `total_suicides` is a runtime field sourced from the
  same `hlstats_Servers.suicides` DB column, not a schema column. Regressions
  cover same-second and +2s suicide boundaries, server suicide aggregate,
  command/buy/dead/ordinary chat, implicit ChangeTeam for ignored
  `time`/`latency`, bot/transient guards, and rollover TeamBonuses cleanup.
  Validation: targeted storage/events/runtime suite reports `100 passed`;
  `docker compose build hlstats-worker` succeeded; narrow-1000 dual contour
  with reused valid legacy succeeded; host-side GeoIP backfill completed with
  exit `0`; fresh compare still exits `1`, now with `9` residual tables. Main
  movement: `hlstats_Servers.suicides` aligned at `83/83` (remaining Servers
  drift is `act_players 4/0`), `hlstats_Events_Chat` dropped out of residual
  output, `hlstats_Events_TeamBonuses` improved to `4765/4766`, and GeoIP
  backfill reduced `hlstats_Players` normalized drift to `50/50`. Remaining
  residuals: `Servers.act_players`, kill-streak `Actions` /
  `Events_PlayerActions`, `ChangeTeam 1345/1309`, `TeamBonuses +1`,
  `PlayerNames` (`415/416`, Dim$on/Player21/XYU aliases), `Players` /
  `Players_History` skill/streak attribution, and accepted `Entries 0/1017`.

- 2026-05-06 overlay: continued the derived combat/reward cluster with the
  suicide kill-streak boundary identified from legacy
  `HLstats_EventHandlers.plib`. Legacy `doEvent_Suicide()` calls
  `endKillStreak()` before recording `Suicides`; Python now ends the active
  kill streak before `_record_suicide()`, so a player who suicides after a
  multi-kill life emits the same derived `kill_streak_N` PlayerAction path as
  death/round-drain endings. Regression: `test_suicide_ends_active_kill_streak`.
  Validation: focused RED first failed on missing `_INSERT_PLAYER_ACTION_QUERY`;
  after the fix the focused test passed, and `test_storage.py -q` now reports
  `67 passed`; targeted event/runtime/storage validation reports `86 passed`.
  Replay/compare has not yet been rerun for this slice.

- 2026-05-06 overlay: residual parity work moved from one-symbol anchors to
  clustered triage and two dense behavior slices. Cluster breakdown used for
  this pass:
  identity/naming/encoding (`Players`, `PlayerUniqueIds`, `PlayerNames`,
  `Players_History`); derived combat/reward counters (`Servers.act_players` /
  `suicides`, `Actions.kill_streak_*`, kill-streak `PlayerActions`,
  `TeamBonuses`); event-policy drift (`ChangeTeam`, `Chat`, non-derived
  `PlayerActions`); accepted differences (`Entries 0/1017`, plus diagnostic
  TeamBonuses/ChangeTeam/Chat/PlayerActions backlogs unless a narrower visible
  impact is proven). Two dense fixes landed. First, ignored-bot name-change
  events no longer mutate runtime/profile alias state, closing the bot encoding
  split where `49.5 % karrigan` and `49.5 ％ karrigan` leaked into identity
  comparison. Second, Statsme telemetry triggers `time` and `latency` are now
  excluded before `Actions` / `PlayerActions` writes. Regressions:
  `test_ignore_bots_skips_name_change_profile_update` and
  `test_record_action_skips_status_noise_triggers`. Validation:
  `test_storage.py -q` -> `64 passed`; targeted FTP/event/runtime/storage suite
  -> `98 passed`; `docker compose build hlstats-worker` -> success; narrow-1000
  dual contour with reused valid legacy -> success. Fresh compare still exits
  `1`, now with `10` residual tables. Main movement: `Actions` row count
  aligned `754/754` and telemetry action/player-action SQL counts are `0/0`;
  `PlayerActions` improved from `4972/6019` to `4972/4977`;
  `PlayerUniqueIds` dropped out of residual output; `PlayerNames` improved from
  normalized `34/35` to `3/4`; `Players_History` from `195/195` to `106/106`;
  `Players` from normalized `281/281` to `250/250`. Remaining open clusters:
  `Servers.act_players/suicides`, kill-streak timing, broad
  `ChangeTeam`/`Chat`, residual `PlayerActions`, `TeamBonuses +9`, and accepted
  `Entries`.

- 2026-05-06 overlay: continued the residual `fnat1k` alias-touch trace by
  closing two more object-lifecycle boundaries instead of chasing a single
  alias row. Python now marks player objects as closed after idle-prune cleanup
  and after `Started map` roster reset, so the next same-name touch reopens the
  alias like legacy `playerCleanup()` / reconnect flows. `Started map` does
  **not** add a new profile flush; the change is limited to alias-use
  semantics, keeping the already-aligned deferred `PlayerNames` stat rollup
  contract intact. Regressions:
  `test_reconnect_after_started_map_counts_alias_use_for_same_userid` and
  `test_reconnect_after_idle_prune_counts_alias_use_for_same_userid`.
  Validation at that point: `test_storage.py -q` -> `63 passed`; targeted
  FTP/event/runtime/storage suite -> `95 passed`. The earlier replay-pending
  note from this slice is superseded by the cluster pass above, which completed
  narrow-1000 replay and fresh compare successfully.

- 2026-05-06 overlay: advanced the broader human `PlayerNames` attribution
  cluster as `LP-P6D-004B` instead of chasing one-off anchors. Python now
  defers `hlstats_PlayerNames` stat rollups until player/profile flush
  boundaries, and stdin transaction commits no longer flush player profiles;
  explicit profile flush still happens at `finalize_import()`, `flush_pending()`,
  disconnect/idle cleanup, and same-unique userid handoff. Alias-use accounting
  now treats explicit name changes, same-unique new-userid handoff, and
  disconnect/reconnect as new legacy-style alias touches. Regressions cover
  name-change-back alias use, same-userid reconnect alias use, deferred
  PlayerNames rollup to the current alias, and the stdin-batch no-flush guard.
  Validation: `test_storage.py -q` -> `61 passed`; targeted FTP/event/runtime/
  storage suite -> `93 passed`; narrow-1000 dual contour with reused valid
  legacy -> success; `compare_stats_dbs.py --max-examples 1` still exits `1`
  for documented residual tables. Visible result: `hlstats_PlayerNames`
  normalized drift improved from `64/65` to `34/35`. Anchors now aligned:
  `0:1838619084` (`X3`) alias rows including `X3 numuses=3`, and
  `0:2084898310` (`SayNor`) alias split/stats. `0:36417680` (`fnat1k`) now has
  matching per-alias stat totals, but `numuses` remains `legacy=106`,
  `python=103` across three alias-touch rows (`CS: zero condition`, `fnat1k`,
  `mUrkovskii`). The rejected investigation that flushed rollups before every
  explicit name change was replay-tested and worsened `PlayerNames` back to
  `64/65`; do not reapply it without a narrower legacy-object lifecycle trace.
  Closed constraints remain closed: player-count / `STEAM_ID_LAN`,
  `1:45686725`, `0:723234133`, and the TeamBonuses +9 / ChangeTeam / Connects /
  broad Chat / broad PlayerActions backlogs were not reopened.

- 2026-05-05 overlay: closed the `0:723234133` current-name replay anchor after
  checking the legacy Perl name-change path. The remaining mismatch was not in
  the Python `change_name` handler: the parity runner imported Python FTP logs
  by FTP modification time, while the validated legacy narrow window is the
  first `1000` sorted log filenames. `hlstats_ftp_py` now keeps production
  mtime ordering by default and exposes `--order-by-name` for replay/parity
  runs; because the FTP progress marker remains mtime-based, that flag is
  fresh-state-only and refuses an existing `.last` marker. `Run-DualContour-1000.ps1`
  clears the Python FTP state and passes the flag only for the Python parity
  contour. Regression coverage:
  `test_entries_to_download_can_order_by_name_for_replay_parity` and
  `test_order_by_name_requires_fresh_state`.
  Validation: `hlstats_ftp_py/tests` plus targeted `hlstats_py`
  event/runtime/storage tests -> `88 passed`; clean narrow-1000 replay with
  reused valid legacy contour -> success; host-side GeoIP backfill -> exit `0`;
  `compare_stats_dbs.py --max-examples 1` still exits `1`, now for `11`
  documented residual tables. Closed anchor: `0:723234133` now matches
  `lastName=Райымбек Гослинг`, kills/deaths `3/4`, `KZ/Kazakhstan`, and aliases
  `Player=2`, `Райымбек Гослинг=2`. Stable anchors: `1:45686725` remains aligned
  as `Mep3ocTb` with `198/179`, `RU/Russia`; `0:1838619084` remains aligned as
  `X3` with `138/71`, while the `X3` alias `numuses` artifact remains
  `legacy=3`, `python=2`. Current residual table counts include
  `PlayerUniqueIds 31/31`, `PlayerNames 64/65`, `Players_History 195/195`,
  `TeamBonuses 4765/4774`, `Statsme 32290/32290`, and `Statsme2 32290/32290`;
  the TeamBonuses residual is still diagnostic backlog under the acceptance
  policy, with the count movement explained by corrected filename-order parity
  input rather than a new TeamBonuses code change.

- 2026-05-01 overlay: continued the RC-C human current-name attribution slice.
  Legacy flushes every live player profile during periodic/shutdown `flushDB`,
  while the Python deferred-`lastName` slice only flushed profile names on
  disconnect. Python now flushes cached profile names during `finalize_import()`
  and `flush_pending()` before the import-tail `last_event` update / shutdown
  commit, preserving immediate `PlayerNames` bookkeeping while closing another
  no-disconnect current-name gap. Python also mirrors the legacy
  same-unique/new-userid handoff far enough to flush the previous live profile
  name and count a new alias use when the userid changes. Regressions:
  `test_finalize_import_flushes_deferred_player_profile_names`,
  `test_flush_pending_flushes_deferred_player_profile_names`,
  `test_unique_id_reconnect_counts_alias_use_for_new_userid`, and
  `test_prune_idle_players_flushes_profile_name_before_eviction`. The idle
  eviction regression was verified red first: stale active players were removed
  without `_UPDATE_PLAYER_NAME_QUERY`; Python now flushes the cached profile
  name before pruning them from active/reward tracking. Targeted validation with
  pytest cache disabled and external basetemp:
  `test_runtime_decisions.py test_storage.py -q` -> `63 passed`, and the full
  `scripts/hlstats_py/tests` suite -> `129 passed`. Narrow-1000 replay with
  reused legacy contour completed successfully; GeoIP backfill completed against
  the restored Python contour. The `0:723234133` alias `numuses` drift is closed
  (`Player=2`, `Райымбек Гослинг=2` on both contours), but the current-name
  profile anchor remains open: legacy `lastName=Райымбек Гослинг`, Python
  `lastName=Player` with matching kills/deaths `3/4`, `KZ/Kazakhstan`, and the
  same alias rows. `0:1838619084` remains current-name aligned as `X3` with
  matching kills/deaths `138/71`, though the `X3` alias `numuses` is still
  `legacy=3`, `python=2`. Current focused anchors remain `PlayerUniqueIds
  1/1`, `PlayerNames 45/36`, `Players_History 110/110`, `TeamBonuses
  4765/4773`, `Statsme 32290/32290`, `Statsme2 32290/32290`.
  Follow-up local TDD found another legacy current-name gap: Perl handles
  `"changed name to"` through `doEvent_ChangeName` / `setName(newname)`, while
  Python had treated it as generic admin noise and never moved the new name
  into the cached profile name. Python now marks name-change generic updates as
  `change_name`, applies the new name to `PlayerNames` and the deferred
  profile-name cache, and avoids incrementing the old alias when the live player
  is already known. Regression:
  `test_name_change_updates_deferred_profile_name`. Validation in this
  Docker-blocked Windows session: targeted
  `test_events.py test_runtime_decisions.py test_storage.py -q` -> `76 passed`;
  broad `scripts/hlstats_py/tests -k "not heatmap and not load_settings"` ->
  `122 passed, 8 deselected`. Full suite and replay were not cleanly runnable
  here: pytest session/temp cleanup hits `WinError 5`, and Docker API access
  returns `permission denied`.

- 2026-04-30 overlay: RC-C current-name and GeoIP anchor slices are validated.
  `uniqueId=1:45686725` now has matching current name and GeoIP on both contours
  (`lastName=Mep3ocTb`, kills/deaths `198/179`, same alias set, `RU/Russia`,
  `lastAddress=178.68.210.14`). Full `scripts/hlstats_py/tests` passes with
  pytest cache disabled (`121 passed`); narrow-1000 replay with reused legacy
  contour completed, GeoIP backfill completed against the Python contour, and
  compare still exits `1` only for documented residual diffs. A follow-up
  ignored-bot history seed fix reduced `hlstats_Players_History` normalized
  drift from `417/417` to `111/111` by keeping hidden bot profile persistence
  (`skill=0`, `hideranking=1`) separate from the legacy default history seed;
  Python now has `0` bot history rows with `skill=0`.

- 2026-04-29 overlay: RC-B `amx_chat`, RC-C legacy `IgnoreBots` bot-policy,
  RC-C transient-id identity slices, and review follow-up bot/rollback hardening
  are implemented and validated. Current post-RC-C narrow-1000 anchors:
  `Players 323/323`, visible players
  `250/250`, `Connects 992/992`, `Frags 5464/5464`, `Statsme 32290/32290`,
  `Statsme2 32290/32290`; `TeamBonuses 4765/4773` stays diagnostic backlog,
  and `Events_Entries legacy=0` vs `python=1017` stays an accepted visible
  compare row. Remaining identity work is broader `PlayerUniqueIds` /
  `PlayerNames` / `Players_History` attribution drift, not an extra
  player-count blocker.

- Current phase: `P6d` post-P0 — срез P0 (код + тесты + узкое окно 50/300/1000)
  закрыт 2026-04-27; диффы: `runtime-db-diff-p6d-narrow-50-20260427-050502.md`,
  `runtime-db-diff-p6d-narrow-300-20260427-050912.md`,
  `runtime-db-diff-p6d-narrow-1000-20260427-051926.md`. Полный корпус по-прежнему
  описан в `runtime-db-diff-p6d-20260426-161410.md` (не заменять узкими
  артефактами без явного решения о промоции).
- P0/M1 итог:
  - `TeamBonuses`: семантика `round_status`, bot/eligible gates, map-start
    roster reset, same-second hostage multiplicity, candidate-set уточнения и
    active-team reward eligibility уже приведены ближе к legacy. Актуальный
    narrow-1000 хвост всё ещё открыт:
    `legacy=4765`, `python=4774` (дельта `+9`) — **первый незакрытый пункт
    плана** (LP-P6D-001).
  - `Events_Entries`: принято с явной рационализацией (`legacy=0`,
    `python=1231` на 1000); строка сравнения **не** убирать (LP-P6D-002).
- План: `docs/plans.md`, тест-план: `docs/test-plan.md`.
- **Рабочий репозиторий:** правки кода и доков — в этом дереве
  (`hlstatsx-community-edition-python-i18n`); соседние проекты в воркспейсе —
  только для сверки с legacy/донором. **Быстрый массовый replay:** не
  изобретать заново — `docs/replay-fast-path.md` (stdin / `direct_import_artifacts.py`,
  тюнинг в `docs/hlstats_py_stdin_import_tuning.md`).
- Статус ворот: **красный** для P6d до закрытия или явного принятия остатка
  TeamBonuses + кластера RC-B. **Мини-агенты по страницам / маршрутам выключены**
  до явного открытия ворот.
- Last updated: 2026-05-14

## Done

- Stdin batch write path (`scripts/hlstats_py/storage.py`): append-only
  `EventBuffer` flushes when the buffer is full, before a periodic commit, or
  at import boundaries (`end_stdin_batch`, `finalize_import`, `flush_pending`);
  it is no longer flushed after every `record()`. Commits trigger when either
  the number of completed records or buffered plus executed write volume reaches
  `stdin_transaction_batch_size`. In batch mode, additive frag counters for
  weapon upserts, server kill totals, and map counts are merged in memory
  (`frag_write_delta_buffer.py`) and flushed with those queries. Rollback clears
  in-memory buffers without executing them. UDP runtime enables
  `configure_event_buffer(max_buffered_events=5000)` so idle `flush_pending`
  can batch event inserts; `EventBuffer.flush` chunks `executemany` using the
  adapter `executemany_chunk_size` when set.
- Completed post-mapfix drift-reduction execution pass with authoritative
  `-ForceDumpRestore` parity baseline on both stacks and new audit artifacts in
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/`.
- Closed `P5` maintenance backlog on `2026-04-25`:
  - added standalone Python ImportBans replacement:
    - package: `scripts/import_bans_py`
    - entrypoint: `python -m import_bans_py`
    - behavior parity with legacy scope: import-only ban propagation to
      `hlstats_Players.hideranking = 2` (no unban pass)
  - documented exact `hlstats_py.runtime --stdin` compatibility boundaries with
    reproducible command/exit evidence in `docs/test-plan.md`
  - validated Python heatmap generator against real map-pack JPEG assets under
    `heatmaps/src/cstrike` with host-to-comparison DB config
    (`scripts/replay_baseline/comparison/python/hlstats.host-local.conf`)
- Landed map lifecycle attribution hardening in `hlstats_py.runtime`:
  `Loading map` now stages pending map state and event map attribution flips on
  `Started map`.
- Landed `hlstats_Events_ChangeTeam` noise reduction in `hlstats_py.storage`:
  unresolved actors ignored, bot actors ignored, and duplicate team-change
  rows deduplicated by `(server, player, map, team, event_time)`.
- Added targeted regression coverage for lifecycle behavior and ChangeTeam
  filtering/deduping in `scripts/hlstats_py/tests/`.
- Validated control `window-300` replay after fixes; residual drift remains in
  map/action/player-history identity areas and is documented in
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/NOTES.md`.

- Created a separate local repository for the standalone product lane.
- Rebased the product lane on clean `upstream/master` history instead of using
  the donor `test` branch as the final base directly (this standalone product
  repo remains separate from that choice). On the **Python migration donor
  fork**, branch `test` was later reset to the stdin performance integration
  tip; see `README.md` and the audit log entry for 2026-04-26.
- Imported the Python donor baseline from
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition`.
- Imported the RU i18n donor web/runtime layer from
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n`.
- Rewrote the primary repo docs so this repository now describes the integrated
  product rather than only the migration donor context.
- Preserved the donor-lane references:
  - Python migration runbooks and parity docs stay in this repo as supporting
    product references.
  - RU i18n donor docs stay available as integration background.
- Ran targeted Python validation in the product repo:
  - `hlstats_py` / replay-baseline batch passes when `PYTHONPATH` is set to
    the imported package roots.
  - targeted `proxy_daemon_py` tests pass at the assertion level, but the
    command still exits non-zero because the repo-enforced coverage threshold is
    not met by the small subset run.
- Ran targeted containerized `php -l` checks for the integrated product files:
  `web/hlstats.php`, `web/includes/i18n.php`, `web/includes/functions.php`,
  `web/pages/header.php`, `web/pages/footer.php`, `web/pages/players.php`,
  `web/pages/chat.php`, `web/pages/help.php`, `web/pages/playerinfo.php`,
  `web/pages/admin.php`, and `web/status.php`.
- Fixed the clean `scripts/proxy_daemon_py/fullstack` bootstrap in the product
  repo:
  - normalized `scripts/proxy_daemon_py/sql/02_set_hlstats_auth_plugin.sh` to
    Unix line endings so MySQL init no longer fails on `/bin/sh^M`
  - replaced the proxy-daemon heartbeat upsert with a MySQL 8.0 and
    MariaDB-compatible `ON DUPLICATE KEY UPDATE` form instead of the invalid
    `INSERT ... AS new`
  - switched proxy-daemon heartbeat probes to proxied control packets so
    `hlstats_py.runtime` accepts them from the Docker network and reports the
    worker `up`
- Re-ran product validation on the integrated repo itself:
  - host-side Python suites now pass with the imported package roots on
    `PYTHONPATH`:
    - `scripts/hlstats_py/tests` + `scripts/replay_baseline/tests` -> `56 passed`
    - `scripts/hlstats_awards_py/tests` + `scripts/hlstats_resolve_py/tests`
      -> `17 passed`
    - `scripts/proxy_daemon_py/tests` -> `72 passed` with repo-enforced
      coverage gate satisfied (`83.59%`)
  - targeted regression reruns for the fixed runtime paths pass:
    - `scripts/proxy_daemon_py/tests/test_db.py`
    - `scripts/proxy_daemon_py/tests/test_heartbeat.py`
    - `scripts/hlstats_py/tests/test_runtime.py`
  - clean product full-stack smoke now passes after rebuild:
    - `http://127.0.0.1:8080/` redirects to `hlstats.php`
    - `mode=contents&lang=ru` returns HTTP `200`
    - `status.php?lang=ru` returns HTTP `200`
    - proxy heartbeat persists `hlstats-worker:28000 -> up`
- Replayed the canonical donor fixture set through the integrated repo and
  re-checked the DB against legacy:
  - `L0415056.log` -> clean compact diff, counts `players=9`, `frags=33`
  - `L0415058.log` -> clean compact diff, counts `players=4`, `frags=18`
  - `L0416053.log` -> clean compact diff, counts `players=9`, `frags=34`
  - `L0417051.log` -> clean compact diff, counts `players=9`, `frags=36`
  - `L0417065.log` -> clean compact diff, counts `players=9`, `frags=32`
- Compared the integrated frontend to the live RU donor contour on the same
  HTTP routes:
  - target `mode=contents&lang=ru` renders localized RU UI and responds with
    HTTP `200`
  - target `status.php?lang=ru` also renders localized RU labels in the merged
    product contour
- Closed the audit-confirmed frontend residual i18n backlog (`P6b`) on the
  supported shared/public/admin/voice/ingame contour.
- Completed the release-style frontend revalidation pass (`P6c`) with targeted
  syntax checks, keyset diff, representative EN/RU smoke, and language
  persistence/fallback validation.
- Cleaned the replay-baseline working corpus and extended the Python replay
  contour for the second CS 1.6 source server:
  - `scripts/replay_baseline/prune-small-logs.ps1` removed `30,572` disposable
    `*.log` files below `15 KB`
  - the retained replay working set is now `41,576` log files
  - `scripts/replay_baseline/restore-baseline.ps1 -Stack python` now seeds
    `37.230.137.48:27015` as `game='cstrike'`
  - the seeded replay server receives copied `hlstats_Servers_Config` rows from
    the baseline parity server
  - `scripts/replay_baseline/replay_python_log.py` now accepts either a single
    file or a directory corpus and prints processed/skipped/error summary
- Switched the Python replay comparison web service from the legacy upstream
  image to a local build from the integrated product `web/` tree, with a
  comparison-local config pointing at the restored `hlstatsxce` database.
- Brought up the Python replay comparison stack on `2026-04-23` and validated
  the new CS 1.6 source server against real retained logs:
  - `L1231219.log` replay smoke sent `239` datagrams with
    `37.230.137.48:27015`
  - `L1231213.log` replay smoke sent `3,434` datagrams with
    `37.230.137.48:27015`
  - `L0217071.log` replay smoke sent `25,660` datagrams with
    `37.230.137.48:27015`
  - the replayed DB has visible statistics on the new server:
    `players=7`, `hlstats_Events_Frags=2`, `serverId=2`, `kills=2`
  - RU HTTP smoke on the integrated comparison web returns HTTP `200` for:
    - `hlstats.php?lang=ru`
    - `hlstats.php?mode=contents&lang=ru`
    - `hlstats.php?mode=game&game=cstrike&lang=ru`
    - `hlstats.php?mode=players&game=cstrike&lang=ru`
    - `hlstats.php?mode=servers&server_id=2&game=cstrike&lang=ru`
  - `mode=game` and `mode=servers&server_id=2` show both Russian UI labels and
    the replay server `37.230.137.48`
- Completed the full retained corpus replay on `2026-04-23` after fixing the
  corpus sender to stream stdin line-by-line instead of buffering the complete
  input in memory:
  - processed all `41,576` retained log files for `37.230.137.48:27015`
  - skipped `0` files and reported `0` read errors
  - sent `32,765,671` replay datagrams to the Python worker
  - elapsed wall time was `811.046` seconds, about `51.3` files/sec and
    `40,400` datagrams/sec at sender level
  - final replay DB counts on the new server: `players=497`,
    `hlstats_Events_Frags=1,536`, `kills=1,536`, `act_players=396`
  - integrated RU web smoke still returns HTTP `200` for the game, players,
    and server pages on `http://127.0.0.1:8281/`
- Closed `P6e` end-to-end on `2026-04-25`:
  - replay contour FTP import completed on Python stack with
    `Run-ContourFtpArtifacts` equivalent run at `MaxImportFiles=100` (exit `0`)
  - replay-safe awards completed (exit `0`):
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
  - strict/default sanity run completed (exit `0`):
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
  - replay SQL evidence:
    - non-empty map rows:
      `hlstats_Events_Frags=6536`, `hlstats_Events_PlayerActions=6838`,
      `hlstats_Events_Statsme=40047`
    - `hlstats_Maps_Counts`: `de_dust2 (kills=1013)`, `de_nuke (kills=27)`
    - `hlstats_Players_Awards=4`, `hlstats_Players_Ribbons=4`
    - GeoIP fill (`country` + `flag` non-empty in `hlstats_Players`): `148`

## In Progress

- [~] **P6d-M1 (LP-P6D-001):** в коде добавлено выравнивание с Perl
  `rewardTeam`: при `IgnoreBots` не пишутся `TeamBonuses` / skill для ботов и
  для `userid <= 0` (`storage._reward_team_players`,
  `_skip_team_reward_for_ignore_bots`, учёт `user_id` в `_resolve_player_id`);
  добавлен idle-prune активного состава перед `record(...)` (last_activity на
  игрока, timeout `250s`) + unit test на исключение idle-игрока из
  `TeamBonuses`. Прогон narrow-1000 после патча:
  `runtime-db-diff-p6d-narrow-1000-20260427-091053.md`
  (`hlstats_Events_TeamBonuses`: `legacy=12588`, `python=49033`) — остаток по
  LP-P6D-001 пока не закрыт. Доп.проверка показала, что snapshot-restore для
  python-контура уже содержал заполненные event-таблицы; валидный narrow-run
  нужно считать только от dump-baseline (`Run-ContourFtpArtifacts.ps1` с
  `-UseDumpRestore`). Runtime-блокер импорта снят минимальным патчем:
  в bot-fallback SQL (`_SELECT_PLAYER_BOT_UNIQUE_QUERY`) экранированы `%` в
  `LIKE` (`BOT:%%`, `00000000:%%:0`), из-за чего batch import больше не падает
  на `not enough arguments for format string`. Повторный python-only narrow-1000
  от dump-baseline: `hlstats_Events_TeamBonuses=4896`, bot/nonbot split:
  `bot=0`, `nonbot=4896`; top actionId: `279=2085`, `278=2053`, `269=529`;
  top map: `$2000$=1226`, `de_dust2=471`, `cs_mansion=314`; дубликаты по
  `(eventTime,actionId,playerId)` до `dup_count=3`. Относительно последнего
  валидного legacy narrow-1000 (`12588`) python теперь ниже на `7692`
  (`~38.9%` от legacy), поэтому LP-P6D-001 остаётся открытым; следующий
  минимальный шаг — точечный дедуп/гейт в `reward_team` без расширения scope.
  Дополнительно переподнят и заново проигран legacy baseline на тех же
  `1000` логах (без python replay): `processed=1000`, `errors=0`; повторный
  `compare_stats_dbs.py` дал `hlstats_Events_TeamBonuses: legacy=4765,
  python=4896` (дельта `+131`, python выше примерно на `2.75%`). Это
  подтверждает, что предыдущая крупная дельта была следствием неконсистентного
  legacy-среза, а текущий эталон для LP-P6D-001 — `4765 vs 4896`.
  Доп.триаж после этого сравнения: найден баг в python storage — в action-пути
  командных наград не учитывался `round_status` (добавлен гейт в
  `_record_action`, покрыт тестом), и найден SQL-формат-баг bot-fallback
  (`LIKE` с неэкранированным `%`, исправлен как `%%`). Для residual-дельты
  добавлен узкий eligibility-gate в `reward_team` (награды только для игроков,
  подтверждённых через `connect/entry` в рамках сессии); повторный python-only
  narrow-1000 от dump-baseline дал `hlstats_Events_TeamBonuses: legacy=4765,
  python=4813` (дельта `+48`, ~`+1.01%`), но LP-P6D-001 пока не закрыт.
  Дополнительный точечный шаг по `(eventTime,actionId,playerId)`:
  in-memory дедуп `TeamBonuses` по ключу `(server_id, player_id, action_id,
  event_time)` в `storage._reward_team_players` (без изменения policy
  `Events_Entries`); `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m
  pytest scripts/hlstats_py/tests` -> `103 passed`. Повторный python-only
  narrow-1000 от dump-baseline + `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`:
  `hlstats_Events_TeamBonuses: legacy=4765, python=4801` (дельта `+36`,
  ~`+0.76%`). Дополнительный минимальный шаг в `storage.py`: team reward теперь
  берёт каноническую команду из `hlstats_Actions.team` (с fallback на payload),
  что устраняет часть CT/T cross-team смещений в TeamBonuses. Полная валидация:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests`
  -> `103 passed`; затем
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  и `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20` дали
  `hlstats_Events_TeamBonuses: legacy=4765, python=4800` (дельта `+35`,
  ~`+0.73%`). Итог: LP-P6D-001 остаётся открытым (COUNT всё ещё выше legacy на
  `35`; текущий минимальный патч уменьшил разрыв на `1`).
  Следующий минимальный шаг: в `storage.apply_server_map_transition(..., phase="started")`
  добавлен reset in-memory roster/team state (active/connected/eligible/last-activity)
  для выравнивания с Perl `doEvent_ChangeMap` и отсечения stale team-состояний
  перед TeamBonuses. Unit-валидация после патча: `103 passed` (включая новый
  тест на reset). После восстановления Docker выполнена обязательная валидация:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (summary `status=ok`, `elapsed_seconds=319.245`) и
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`.
  Новый срез `hlstats_Events_TeamBonuses`: `legacy=4765`, `python=4669`
  (дельта `-96`, python ниже на ~`2.01%`), поэтому LP-P6D-001 остаётся
  **не закрыт** (расхождение COUNT всё ещё ненулевое, сменился знак дельты).
  Точечный triage по ключу `(eventTime, actionId, playerId)` показывает:
  - legacy>python пики: `(2024-01-05 18:01:39,272,145)` `3 vs 0`,
    `(2024-01-05 18:01:39,272,133)` `3 vs 0`,
    `(2024-01-05 18:08:53,272,290)` `2 vs 0`;
  - зеркальные пары playerId-shift в тех же timestamp/action:
    `(2026-01-05 22:25:24,278,317)` `1 vs 0` и
    `(2026-01-05 22:25:24,278,321)` `0 vs 1` (аналогично по `279/269`).
  Следующий минимальный шаг без расширения scope и без изменения policy
  `Events_Entries`: в `reward_team` добавить узкий guard на смену канонического
  `player_id` внутри одного `(server_id, event_time, action_id)` окна
  (предпочитать первый стабильно разрешённый id в окне и не эмитить вторую
  запись при позднем remap этого же игрока), затем повторить narrow-1000.
  Выполнен следующий debug-цикл по первому расхождению:
  - в `storage._resolve_player_id` добавлен guard для пустых дескрипторов
    (нет `unique_id` и пустой `name`), чтобы не создавать phantom-player и не
    сдвигать `playerId` в TeamBonuses;
  - добавлен unit test:
    `test_empty_descriptor_without_unique_id_does_not_create_player`;
  - targeted pytest:
    `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests/test_storage.py -k "empty_descriptor_without_unique_id_does_not_create_player or team_bonus"` -> `9 passed`.
  Полная обязательная валидация после фикса:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (`status=ok`, `elapsed_seconds=271.062`) + `compare_stats_dbs.py --max-examples 20`
  снова даёт `hlstats_Events_TeamBonuses: legacy=4765, python=4669` (дельта `-96`).
  Локальная проверка окна первого расхождения (`L0101058`, `19:03:30..19:04:40`)
  подтверждает, что playerId-shift исправлен (`...279,84...` теперь совпадает на
  обеих сторонах). Residual остаётся в hostage-окне (`L0101061`, `20:33:47`,
  action `272`): legacy сохраняет две строки на игрока в ту же секунду, Python
  — одну из-за текущего in-memory dedupe по `(server_id, player_id, action_id,
  event_time)`. Поэтому LP-P6D-001 всё ещё **не закрыт**: COUNT-дельта осталась
  ненулевой, но источник смещён с identity-shift на multiplicity policy в
  TeamBonuses (без изменений `Events_Entries` policy).
  Дополнительный минимальный шаг по residual multiplicity выполнен:
  - dedupe в `storage._reward_team_players` ослаблен только для
    `event_code == "Rescued_A_Hostage"` (остальные team bonus события
    по-прежнему дедупятся по `(server_id, player_id, action_id, event_time)`);
  - добавлен тест
    `test_team_bonus_rescued_hostage_allows_same_second_duplicates`;
  - targeted pytest + полный пакет `scripts/hlstats_py/tests` -> `105 passed`.
  Обязательный narrow-1000 replay+compare после шага:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (`status=ok`, `elapsed_seconds=259.628`) и
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`
  дали `hlstats_Events_TeamBonuses: legacy=4765, python=4681`
  (дельта `-84`, улучшение на `+12` строк к предыдущему `-96`).
  Санити по hostage-окну `L0101061` (`20:33:46..20:33:47`) теперь совпадает
  1:1 с legacy, включая дубли на `20:33:47` для action `272`. LP-P6D-001 всё
  ещё **не закрыт**: остаётся ненулевая COUNT-дельта `84`, но целевой локальный
  класс расхождения (hostage same-second duplicates) снят.
  Следующий точечный шаг по residual undercount выполнен в idle-prune path:
  `_prune_idle_players` больше не исключает из active/reward-eligible игроков,
  которые всё ещё присутствуют в `connected_players` (даже при старом
  `last_activity`), чтобы не терять team rewards в длинных раундах.
  Добавлен тест `test_team_bonus_keeps_connected_idle_players_for_reward`;
  полный пакет `scripts/hlstats_py/tests` -> `106 passed`.
  Обязательный narrow-1000 replay+compare после шага:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (`status=ok`, `elapsed_seconds=347.481`) и
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`
  дали `hlstats_Events_TeamBonuses: legacy=4765, python=4682`
  (дельта `-83`, ещё `+1` к прошлому результату `-84`).
  Локальная проверка de_mirage-окна `2024-01-01 19:41:51..19:51:56` показала,
  что для игрока `playerId=79` (unique `0:1828776565`) часть пропусков остаётся,
  поэтому LP-P6D-001 пока **не закрыт**.
  Дополнительный узкий шаг выполнен в `reward_team`:
  перебор кандидатов для TeamBonuses расширен до объединения
  `active_players ∪ connected_players ∪ reward_eligible_players` при сохранении
  strict-гейта на `reward_eligible_players` и всех действующих policy-гейтов
  (`round_status`, `IgnoreBots`, dedupe).
  Цель: не терять eligible-игроков, временно выпавших только из active-set.
  Валидация:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests` -> `106 passed`;
  - обязательный narrow-1000 replay+compare:
    `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
    (`status=ok`, `elapsed_seconds=282.009`) +
    `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`.
  Новый срез `hlstats_Events_TeamBonuses`: `legacy=4765`, `python=4692`
  (дельта `-73`, улучшение `+10` к предыдущему `-83`).
  LP-P6D-001 всё ещё **не закрыт** (остаток `73`), но хвост продолжает
  уменьшаться без расширения scope и без изменения policy `Events_Entries`.
- [~] **P6d-M2 (RC-B):** объёмные дельты `ChangeTeam` / `Connects` / `Chat` /
  `PlayerActions` из того же narrow-diff — зафиксировать продуктовое решение и
  выровнять политику.
- `P6d`: full replay is now complete on both stacks for the same logical server
  identity `37.230.137.48:27015`:
  - legacy replay:
    `docs/audits/legacy-python-parity-20260423/legacy-full-corpus-replay-p6d-20260426-034823.log`
    (`processed=41513`, `errors=0`, `dropped_lines=169140`)
  - python direct stdin replay (worker-local batch path, retry with parser backend
    `python`):
    `docs/audits/legacy-python-parity-20260423/python-direct-stdin-import-p6d-20260426-034823-retry1.log`
    (`files=41513`, `records=30302028`, `mode=batch-stdin-local`)
- Input parity for this run is confirmed:
  - legacy input manifest:
    `legacy-full-corpus-input-manifest-p6d-20260426-034823.txt`
  - python processed-file manifest extracted from replay log:
    `python-direct-input-manifest-p6d-20260426-034823-retry1.txt`
  - line-by-line compare result: `diff_count=0` (same ordered filename set).
- DB diff for this run (authoritative): `compare_stats_dbs.py` output is
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-20260426-161410.md`
  (`18` tables differ; triage: `bug-plan.md` in the same folder). The
  `runtime-db-diff-p6d-20260426-034823-retry1.md` capture is a stub/obsolete
  pointer, not a second source of truth.
- The audit runbook is seeded at
  `docs/audits/legacy-python-parity-20260423/README.md`.
- The legacy comparison contour now has the same second-server restore
  bootstrap as Python: `37.230.137.48:27015`, `game='cstrike'`, with
  `32` copied `hlstats_Servers_Config` rows from `172.19.0.1:27015`.
- `scripts/replay_baseline/replay_legacy_log.py` is now available as the
  streaming file/directory replay helper for the legacy Perl daemon.
- Legacy smoke replay has passed the backend write gate:
  `L0217071.log` through the Perl daemon produced frag/stat rows, including
  `hlstats_Events_Frags=39` and `hlstats_Events_Statsme=538` after the smoke
  sequence.
- Legacy full replay is now clean and authoritative with final summary:
  `processed=41576`, `skipped=0`, `errors=0`, `dropped_lines=169419`
  (legacy DB reference counters captured in audit performance notes).
- Python full-corpus **rerun** used `--send-delay 0`: helper summary matched
  legacy (`processed=41576`, `skipped=0`, `errors=0`, `dropped_lines=169419`)
  but UDP flooding means most datagrams were likely **not** delivered to the
  worker; that DB snapshot and the first `runtime-db-diff.md` are **invalid**
  for parser parity conclusions (see audit `performance.md`).
- Input manifests and dropped-line manifests still match exactly between legacy
  and that Python run (same line counts and SHA-256 hashes); policy parity is
  confirmed, transport parity was not.
- A throttled Python full replay (e.g. `--send-delay 0.005`, new log name) plus
  fresh `compare_stats_dbs.py` output is the pending authoritative diff.
- The frontend-specific `P6b`/`P6c` work is still complete for the supported
  EN/RU product contour.

## Next

1. Завершить **P6d-M1**: минимальный фикс + тесты (`test_storage.py` /
   `test_runtime.py` по необходимости) → один прогон narrow 1000 (или 300 при
   отладке) → `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
   → при существенном изменении добавить `runtime-db-diff-p6d-narrow-*` →
   обновить `bug-plan.md`, `issues.jsonl`, `performance.md`, этот `status.md`.
2. **P6d-M2 (RC-B)** после или параллельно, если независимо от M1.
3. **RC-C** (идентичность игроков / история) — после стабилизации RC-B.
4. `Events_Entries` — не убирать из compare; пересмотр рационализации только
   после RC-B/идентичности.
5. HTTP / мини-агенты по маршрутам — только после зелёного или явно принятого
   runtime-ворота.
- `P6e`: режим обслуживания — строгий контракт по умолчанию, регрессионные
  проверки replay/awards без расширения scope.

## Handoff / старт следующего чата

Скопируй в новый чат (репо `hlstatsx-community-edition-python-i18n`):

> Продолжаем `P6d` по `docs/status.md` и `docs/plans.md`. Первый приоритет:
> **LP-P6D-001** — на узком окне 1000 `TeamBonuses` всё ещё `4765` vs `4692`
> после серии narrow-фиксов, последний подтверждённый хвост `delta=-73`. Прочитай
> `docs/audits/legacy-python-parity-20260423/bug-plan.md` и последний артефакт
> `runtime-db-diff-p6d-narrow-1000-20260427-092518.md`. Сверь read-only SQL на
> legacy/python по `hlstats_Events_TeamBonuses` (COUNT, топ action/map) с Perl
> и Python (см. In Progress). Минимальный патч + pytest с
> `PYTHONPATH=scripts;scripts/proxy_daemon_py`. Не трогать строку compare для
> `Events_Entries`. Не включать page-агентов. Перед коммитом проверь `git
> status` на посторонние изменения вне этого среза.

## Assumptions

- Docker-контуры legacy/python подняты как в runbook аудита; SQL только
  read-only для диагностики.
- Канонический полнокорпусный diff остаётся
  `runtime-db-diff-p6d-20260426-161410.md` до явной перезаписи.

## Ready to execute

- Старт: **P6d-M1** (TeamBonuses).
- Цикл: правка → `pytest` (hlstats_py) → narrow replay + compare → правка
  доказательств в `docs/audits/...` и `docs/status.md`.
- Валидация: команды из раздела Next и `docs/test-plan.md` (replay / compare).
- Стоп: блокер воспроизведения, необходимость ручного секрета/деструктива, или
  явное продуктовое «принимаем как есть» с записью в `issues.jsonl`.

## Decisions

- This repo is the product integration lane, not the upstream PR lane.
- Python is the default runtime path for the product lane.
- Perl remains legacy-only for validation and transition scenarios.
- The original non-Python contour is the reference for EN/data parity, not for
  RU wording.
- The integrated Python web on `8281` is the RU/current UI reference; RU audit
  findings are data parity plus localization leaks, not byte-for-byte legacy
  HTML diffs.
- Destructive admin actions are out of scope for the parity audit and must be
  logged read-only instead of submitted.
- The frontend i18n implementation must stay explicit and dictionary-backed.
- EN and RU are the required release locales for v1.
- The frontend i18n fix pass will be executed in this order:
  shared helpers/runtime -> public pages -> admin/voice -> ingame pages ->
  final revalidation.
- Repeated visible labels should be moved to catalog-backed helpers or shared
  keys instead of being retranslated page-by-page.

## Current Risks

- Some Python test commands require explicit `PYTHONPATH` setup because the new
  product repo has not yet added a unified developer bootstrap for the imported
  package roots.
- The supported frontend EN/RU contour is now release-clean on the remediated
  routes, but some deeper legacy tooling still relies on bridge/fallback logic
  and should be watched if future routes are reopened or widened.
- Some older admin tools remain hard to smoke end-to-end because they are not
  fully wired into the current admin navigation contour or depend on broader
  legacy runtime flows; those are now a cleanup/readiness issue rather than a
  blocker for the validated routes.
- The replay comparison Docker contour uses fixed container names
  (`hlstatsx-python-*`), so local concurrent stack users can block rebuild or
  smoke passes until those names are free.
- The legacy full-corpus replay is materially slower than the Python sender, so
  the current full retained-corpus run may need to complete as a long-running
  background audit job before DB diff/page audit can start.
- A legacy replay run without a final helper `Replay summary` is not
  authoritative, even if DB counters increased during the run; partial DBs must
  be treated as contaminated and restored away.
- The first post-manifest `runtime-db-diff.md` largely reflects Python UDP
  overload (`--send-delay 0`), not a reviewed parser-vs-legacy conclusion; do
  not triage the 18-table list until a throttled full replay reproduces
  scale closer to legacy.
- The Python runtime still does not populate `hlstats_Players.country` /
  `flag` inline during connect handling, but the Python maintenance contour now
  owns GeoIP backfill through `hlstats_awards_py --geoip`.
- GeoIP now depends on operational prerequisites rather than missing code:
  either populated `geoLiteCity_*` tables or a readable
  `scripts/GeoLiteCity/GeoLite2-City.mmdb` with `UseGeoIPBinary > 0`; when
  those inputs are absent the Python command fails explicitly instead of
  silently leaving players as `Unknown Country`.
- The Python parser/runtime still differs from legacy Perl in a few
  replay-relevant edge cases:
  - Steam/auth normalization still treats only `STEAM_0:` as canonical
  - pending/unknown auth connect events are not delayed like Perl
  - repeated property parsing does not match Perl's destructive `getProperties`
  - connect-address parsing currently splits on the first `:` instead of
    following the legacy IPv4-only `host:port` rule
- Some game-scoped admin routes still depend on the legacy JS/basic-mode
  navigation split, so direct noninteractive HTTP smoke can verify many of them
  but not every task uniformly.
- `P5` maintenance backlog is closed; remaining lane risk is concentrated in
  `P6d` parity replay throughput/diff evidence rather than missing Python
  maintenance utilities.
- Some donor docs still describe lane-specific context rather than product
  context; the main docs in this repo are now the primary source of truth.

## Audit Log

- 2026-04-26: On the Python migration donor fork (`hlstatsx-community-edition`,
  e.g. `origin` for that clone), remote branch **`test`** was **force-updated**
  to match the former `perf/hlstats-stdin-batch-speedup` tip (stdin import
  batching / DB session reuse). Treat **`test`** as the fork’s integration line
  for that stack; refresh local clones with `git fetch` and
  `git reset --hard origin/test` if they still pointed at the pre-reset
  history. Documented in `README.md` under Git / migration fork.
- 2026-04-25: Closed `P6e` validation/evidence loop:
  - replay contour FTP import completed on the Python stack with `100` file cap
    (direct worker run equivalent to `Run-ContourFtpArtifacts` import stage)
  - fixed intermittent `Run-ContourFtpArtifacts` abort between FTP-state cleanup
    and `docker compose run`:
    - root cause: flaky `Get-ChildItem ... | Remove-Item` path raising
      `NullReferenceException` on some runs
    - remediation: replaced with explicit safe cleanup loop over matched files
      in `scripts/replay_baseline/comparison/python/Run-ContourFtpArtifacts.ps1`
    - stable end-to-end command now passes without manual workaround:
      `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 100`
      (exit `0`)
    - canonical script summary now printed in stdout (`status/import mode/server/
      limits/geoip mode`) for audit-friendly replay evidence
  - replay-safe awards runs completed with exit `0`:
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
  - strict/default sanity runs completed with exit `0`:
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
  - SQL evidence captured:
    - `hlstats_Events_Frags` non-empty map: `6536`
    - `hlstats_Events_PlayerActions` non-empty map: `6838`
    - `hlstats_Events_Statsme` non-empty map: `40047`
    - `hlstats_Maps_Counts`: `de_dust2 kills=1013`, `de_nuke kills=27`
    - `hlstats_Players_Awards=4`, `hlstats_Players_Ribbons=4`
    - GeoIP fill (`hlstats_Players` non-empty `country` + `flag`): `148`
- 2026-04-25: Closed `P5` maintenance-only backlog with validation evidence:
  - `ImportBans` Python CLI implemented as `scripts/import_bans_py`
  - runtime boundary commands:
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin`
      -> exit `1` (`--stdin requires both --server-ip and --server-port`)
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin --server-ip 127.0.0.1 --server-port 27015 --stdin-transaction-batch-size -1`
      -> exit `1` (`--stdin-transaction-batch-size must be >= 0`)
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin --server-ip 127.0.0.1 --server-port 27015 --parser-backend native --stdin-transaction-batch-size 0`
      -> exit `1` on local config DB precondition (`DBHost must be configured in hlstats.conf`) after CLI boundary acceptance
  - ImportBans CLI boundary commands:
    - `python -m import_bans_py --help` -> exit `0`
    - `python -m import_bans_py --configfile hlstats.conf --dry-run`
      -> exit `1` (missing required source configuration)
  - real map-pack asset heatmap runs:
    - `python -m hlstats_py.heatmaps --configfile scripts/replay_baseline/comparison/python/hlstats.host-local.conf --game cstrike --map de_dust2 --disablecache --debug-level 2`
      -> exit `0`
    - `python -m hlstats_py.heatmaps --configfile scripts/replay_baseline/comparison/python/hlstats.host-local.conf --game cstrike --map de_nuke --disablecache --debug-level 2`
      -> exit `0`
    - both runs completed generator path (`Heatmap creation done`) and
      skipped render step because queried kill count for the map window was `0`
- 2026-04-24: Landed stdin import performance tuning for Python runtime/FTP path:
  - added quiet-by-default stdin event logging with opt-in debug flag
    `--stdin-verbose-events` (default off)
  - added parser backend selector `--parser-backend` with default `python`
    and optional `native` fast path
  - added stdin DB transaction batching with
    `--stdin-transaction-batch-size` (default `1000`, `0` disables batching)
  - documented defaults, tuning profiles, and verification flow in
    `docs/hlstats_py_stdin_import_tuning.md`
- 2026-04-24: Added `P6e` architecture-modernization parity milestone to
  `docs/plans.md` and aligned execution framing around:
  - explicit runtime map state projection
  - policy-based awards behavior (strict/default vs replay-safe)
  - decoupled GeoIP resolver behavior by policy
  - replay-focused validation gates and stop-and-fix criteria
- 2026-04-23: Began `P6d` execution on the backend/runtime contour:
  - factored `restore-baseline.ps1` so the second replay server bootstrap runs
    for both `-Stack legacy` and `-Stack python`, while Python-only
    `Proxy_Daemons` setup remains Python-only
  - added `scripts/replay_baseline/replay_legacy_log.py`, a reusable streaming
    stdin replay helper for the legacy Perl daemon
  - verified `-Stack legacy` restore creates exactly one
    `37.230.137.48:27015` `cstrike` server with `32` copied config rows and a
    clean pre-replay DB
  - smoke replayed `L1231219.log`, `L1231213.log`, and `L0217071.log`; the
    final representative smoke confirmed Perl writes gameplay stats
    (`players=62`, `frags=39`, `statsme=538`)
  - started the full `41,576` file retained-corpus legacy replay from a clean
    restore; page audit remains blocked until DB/runtime diff is captured
- 2026-04-23: Heartbeat follow-up found the first full legacy retained-corpus
  run failed before completion:
  - helper output reached `L0107052.log` and then logged `[Errno 22] Invalid argument`
  - no final `Replay summary` was written
  - queued files before failure: `1097`
  - the partial legacy DB must not be used for DB diff or page audit
  - patched `replay_legacy_log.py` to report daemon/stdin pipe closure as a
    replay failure instead of masking it as per-file read failures
- 2026-04-23: Completed the P6d backend/runtime parity **capture** gates (with a
  critical caveat on the Python side):
  - legacy full replay completed cleanly and is now the authoritative
    comparison reference
  - Python rerun full replay used `--drop-empty-team-enter-events` and
    `--send-delay 0 --drain-delay 10`; helper summary matched legacy, but
    `--send-delay 0` is now treated as **invalid for DB parity** (UDP loss on
    the docker UDP path; helper `errors=0` does not prove delivery)
  - legacy vs Python input manifests and dropped-line manifests match exactly
    (`41576` inputs, `169419` dropped lines; identical SHA-256 hashes)
  - captured Python post-replay DB snapshot (not comparable to legacy at scale):
    `players=554`, `frags=2007`, `statsme=9687`, `players_history=73333`,
    replay server `kills=1994`, `players=552`, `act_players=408`
  - generated runtime diff report:
    `docs/audits/legacy-python-parity-20260423/runtime-db-diff.md`
    with logical differences in `18` tables — **stale until throttled replay**
  - page/web parity audit remains blocked pending a throttled Python full replay
    and a regenerated DB diff
- 2026-04-23: Documented Python replay UDP methodology (`performance.md`,
  `status.md`, audit `README.md`); `replay_python_log.py` now prints a stderr
  warning when `--send-delay 0`.
- 2026-04-23: Planned `P6d` full legacy-vs-Python product parity audit using
  the `justdoit` workflow:
  - added `P6d` to `docs/plans.md`
  - created the full mini-agent runbook at
    `docs/audits/legacy-python-parity-20260423/README.md`
  - updated `docs/test-plan.md` with the replay, DB diff, route inventory,
    issue logging, and final bug-plan gates
  - first unfinished execution item is legacy/Python comparison setup, with
    legacy second-server bootstrap and streaming full-corpus replay as the
    first prep blockers
- 2026-04-22: Follow-up replay/product audit after the second-server bootstrap:
  - direct SQL inspection of the live Python comparison DB on `127.0.0.1:3327`
    confirms the restore bootstrap is intact even before replay:
    - `172.19.0.1:27015` and `37.230.137.48:27015` both exist in
      `hlstats_Servers`
    - the replay server still has `32` copied `hlstats_Servers_Config` rows
    - `Proxy_Daemons` is configured to `hlstatsx-python-worker:28000`
    - the restored DB is still clean for replay work (`0` players,
      `0` frags, `0` history rows)
  - audited the Python country-resolution path and confirmed that product-lane
    Python runtime does not currently write `hlstats_Players.country` / `flag`
  - audited Python-vs-Perl parser parity and confirmed no repo-vs-repo drift
    between donor/product copies, but several remaining functional deltas in
    Python:
    - Steam/auth normalization is narrower than Perl
    - pending/unknown auth connect handling is missing
    - repeated property parsing is not Perl-equivalent
    - connect-address parsing can diverge from Perl outside IPv4 `host:port`
  - prepared the next replay/web smoke focus list for the restored 8281 contour:
    `status.php`, `show_graph.php`, `sig.php`, `playerhistory`, `updater`,
    core public pages, key admin tasks, and replay-backed ingame status/load
- 2026-04-22: Completed `P6c` release-style frontend revalidation after the
  final `P6b` remediation batch:
  - representative HTTP smoke returns `200` with expected localized EN/RU
    content for:
    - public `mode=playerhistory` error-path rendering
    - public `mode=updater`
    - voice `mode=teamspeak`
    - ingame `mode=ingame&page=status`
    - admin `task=tools_adminevents`
    - admin `task=serversettings&key=1&game=cstrike`
  - explicit language persistence/fallback contract passes:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when only `PHPSESSID` is preserved
    - fresh request without language state falls back to EN
    - invalid `lang=zz` does not overwrite the persisted valid language
  - focused grep over the remediated files no longer shows the retired raw
    English UI copy outside translation-map literals, EN catalogs, and accepted
    fallback strings
- 2026-04-22: Landed the first `P6b` remediation batch for the
  audit-confirmed residual backlog:
  - hardened shared request sanitization in `web/includes/functions.php` and
    the main HTTP/image entrypoints to keep non-Latin input intact
  - fixed the remaining `web/status.php` runtime bootstrap defect so localized
    error handling is available before the PHP-version gate fires
  - localized the residual direct-output public/admin/ingame surfaces in:
    - `web/pages/playerhistory.php`
    - `web/pages/profile.php`
    - `web/pages/updater.php`
    - `web/pages/admintasks/serversettings.php`
    - `web/pages/admintasks/tools_adminevents.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/status.php`
  - extended the shared table/runtime bridge so cell-value literals and runtime
    marker payloads resolve through the catalogs instead of leaking English
- 2026-04-22: Validation for the current `P6b` remediation batch:
  - rebuilt `web` from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml`
  - targeted Dockerized `php -l` passes for all changed shared/public/admin/
    ingame files plus `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff remains clean with `missing_in_ru=0` and
    `missing_in_en=0`

- 2026-04-22: Ran a distributed static i18n audit over the integrated product
  repo with separate passes for:
  - shared/runtime core
  - public `web/pages/*`
  - admin shell and `admintasks`
  - ingame/voice/template surfaces
  - aggregate coverage and keyset completeness
- 2026-04-22: Audit outcome:
  - `web/lang/en.php` and `web/lang/ru.php` remain aligned by keyset
  - the repo is close to release-clean on the public/admin contours, but not
    yet on ingame/shared runtime
  - the highest-risk remaining issues are:
    - ASCII-only request sanitization that can corrupt non-Latin input
    - English event descriptions embedded in `web/pages/playerhistory.php` SQL
    - DB-sourced English help text in
      `web/pages/admintasks/serversettings.php`
    - residual raw-English ingame routes such as `status`, `load`, `mapinfo`,
      and `weaponinfo`
    - remaining bridge/fallback-heavy legacy helpers and utility pages
- 2026-04-22: Inserted a new `P6b` remediation milestone into `docs/plans.md`
  and moved the release-style revalidation pass to `P6c` so the plan matches
  the audit findings.
- 2026-04-22: Replay-baseline corpus hygiene and second-server bootstrap:
  - added `scripts/replay_baseline/prune-small-logs.ps1`
  - pruned the working replay artifacts set from `72,148` logs to `41,576`
    by deleting `30,572` logs smaller than `15 KB`
  - extended `scripts/replay_baseline/restore-baseline.ps1 -Stack python` so
    the restored comparison DB contains:
    - the canonical parity server `172.19.0.1:27015`
    - the CS 1.6 replay server `37.230.137.48:27015`
  - verified the seeded replay server has `32` copied
    `hlstats_Servers_Config` rows
  - extended `scripts/replay_baseline/replay_python_log.py` so it can replay a
    sorted directory corpus under one explicit logical source server identity
- 2026-04-23: Reworked the Python comparison web service so the `8281`
  inspection contour uses the current integrated product `web/` tree instead
  of the legacy upstream web image.
- 2026-04-23: Runtime validation on the freed replay stack:
  - rebuilt and started `scripts/replay_baseline/comparison/python`
  - confirmed `SERVERLIST` exposes both `172.19.0.1:27015` and
    `37.230.137.48:27015`
  - replayed retained CS 1.6 logs under `37.230.137.48:27015`
  - verified the integrated RU frontend on `8281` renders replayed data with
    Russian labels and the new replay server visible on the game/server pages

- 2026-04-22: Ran a full frontend translation review over:
  - shared i18n runtime/catalogs
  - public `web/pages/*` groups
  - voice/templates
  - admin shell and `admintasks`
  - `web/pages/ingame/*`
- 2026-04-22: Review outcome:
  - no evidence that the explicit EN/RU i18n contract is conceptually wrong
  - strong evidence that a large legacy UI layer still bypasses `t(...)`
  - one confirmed catalog gap: `literal.yes` missing in RU
  - one confirmed syntax blocker: `web/pages/ingame/motd.php`
- 2026-04-22: Planned the remediation as `P6a -> P6b` instead of jumping
  directly to final packaging.
- 2026-04-22: Landed `P6a` batch 1:
  - added the missing RU catalog key `literal.yes`
  - added shared catalog coverage for runtime/database/public error-path text
  - localized shared helper/runtime flows in:
    - `web/includes/functions.php`
    - `web/includes/class_db.php`
    - `web/includes/google_maps.php`
    - `web/ingame.php`
  - localized first public/detail surfaces in:
    - `web/pages/search-class.php`
    - `web/pages/help.php`
    - `web/pages/game.php`
    - `web/pages/servers.php`
    - `web/pages/claninfo.php`
    - `web/pages/dailyawardinfo.php`
    - `web/pages/mapinfo.php`
    - `web/pages/rankinfo.php`
    - `web/pages/ribboninfo.php`
    - `web/pages/rolesinfo.php`
    - `web/pages/weaponinfo.php`
- 2026-04-22: Validation for `P6a` batch 1:
  - targeted Dockerized `php -l` passes for every file changed in the batch
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` is clean
  - fullstack smoke on `127.0.0.1:8080` returns HTTP `200` with expected
    localized tokens for:
    - `mode=contents`
    - `mode=help`
    - `mode=search`
    - `game=aoc`
    - `mode=servers&game=aoc&server_id=1`
    - `mode=dailyawardinfo&game=aoc&award=1`
    - `mode=mapinfo&game=aoc&map=de_dust2`
    - `mode=rankinfo&game=aoc&rank=1`
    - `mode=rolesinfo&game=aoc&role=Crossbowman`
    - `mode=weaponinfo&game=aoc&weapon=Broadsword`
- 2026-04-22: Landed `P6a` batch 2:
  - localized voice/runtime error paths in:
    - `web/pages/teamspeak.php`
    - `web/pages/ventrilo.php`
  - extended shared dictionary-backed literal mapping and new catalog coverage
    for ingame/admin/voice surface labels and runtime messages in:
    - `web/includes/functions.php`
    - `web/includes/i18n.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - removed or centralized the reviewed ingame/runtime leaks in:
    - `web/pages/ingame/actioninfo.php`
    - `web/pages/ingame/actions.php`
    - `web/pages/ingame/bans.php`
    - `web/pages/ingame/claninfo.php`
    - `web/pages/ingame/clans.php`
    - `web/pages/ingame/footer.php`
    - `web/pages/ingame/header.php`
    - `web/pages/ingame/help.php`
    - `web/pages/ingame/kills.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/mapinfo.php`
    - `web/pages/ingame/maps.php`
    - `web/pages/ingame/motd.php`
    - `web/pages/ingame/players.php`
    - `web/pages/ingame/servers.php`
    - `web/pages/ingame/statsme.php`
    - `web/pages/ingame/status.php`
    - `web/pages/ingame/targets.php`
    - `web/pages/ingame/weaponinfo.php`
    - `web/pages/ingame/weapons.php`
    - `web/pages/ingame/accuracy.php`
  - fixed a real runtime defect while in scope:
    - `web/pages/ingame/motd.php` parser blocker
    - `web/pages/ingame/actioninfo.php` now queries action description by
      `code` instead of an undefined `$action_id`
    - `web/pages/ventrilo.php` now checks password length correctly
- 2026-04-22: Validation for `P6a` batch 2:
  - targeted Dockerized `php -l` passes for all touched voice/shared/ingame
    files, including `web/pages/ingame/motd.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` is clean and
    duplicate-key noise was reduced to zero
  - rebuilt `fullstack-web` from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace code instead of a stale container image
  - fullstack smoke on `127.0.0.1:8080` returns HTTP `200` with expected
    localized tokens for:
    - `hlstats.php?mode=admin&lang=en|ru`
    - `ingame.php?game=aoc&mode=help&lang=en|ru`
    - `ingame.php?game=aoc&mode=servers&lang=en|ru`
    - `ingame.php?game=aoc&mode=motd&lang=en|ru`
    - `ingame.php?game=aoc&mode=actions&lang=en|ru`
    - `ingame.php?game=aoc&mode=statsme&player=1&lang=en|ru`
    - `ingame.php?game=aoc&mode=claninfo&clan=1&lang=en|ru`
    - `hlstats.php?mode=teamspeak&game=aoc&tsId=1&lang=en|ru`
    - `hlstats.php?mode=ventrilo&game=aoc&veId=1&lang=en|ru`
- 2026-04-22: Landed `P6a` batch 3:
  - added shared admin/runtime helper coverage for access-denied handling and
    extra admin edit-list labels in:
    - `web/includes/functions.php`
  - retired the repeated raw-English `admintasks` guard paths across the
    reviewed admin task files so direct-access and access-denied flows now use
    the shared dictionary-backed helpers
  - localized the most reachable remaining admin task runtime/public text in:
    - `web/pages/admintasks/options.php`
    - `web/pages/admintasks/serversettings.php`
    - `web/pages/admintasks/games.php`
    - `web/pages/admintasks/tools_reset_2.php`
    - `web/pages/admintasks/tools_synchronize.php`
    - `web/pages/admintasks/tools_resetdbcollations.php`
  - extended EN/RU catalogs for those admin task surfaces in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - fixed one additional PHP 8 syntax/runtime blocker while in scope:
    - removed invalid call-time pass-by-reference syntax from
      `web/pages/admintasks/tools_synchronize.php`
    - corrected the accidental assignment in the null-default check inside
      `web/pages/admintasks/tools_resetdbcollations.php`
- 2026-04-22: Validation for `P6a` batch 3:
  - targeted Dockerized `php -l` passes for all changed admin/helper files in
    the batch, including every touched `web/pages/admintasks/*.php` file
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains
    clean with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` after the final
    `tools_synchronize.php` PHP 8 fix so HTTP smoke used the current workspace
    image
  - authenticated admin HTTP smoke using the existing local fixture admin
    account returns HTTP `200` with expected localized tokens for:
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
    - `hlstats.php?mode=admin&task=games&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_reset_2&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_resetdbcollations&lang=en|ru`
  - explicit language persistence/fallback contract remains intact:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when the `lang` cookie is omitted but the session
      is preserved
    - default EN rendering with a fresh request without `lang`, cookie, or
      session
  - admin route notes from the smoke pass:
    - `serversettings` requires a fuller legacy game-task navigation path than
      the direct noninteractive request used in the smoke, so it was syntax and
      catalog validated in this batch but not token-asserted by direct HTTP
    - `tools_synchronize` is not currently registered in the active admin task
      list even though the file remains present, so it was validated by syntax
      and catalog/runtime grep rather than route-level token smoke
- 2026-04-22: Extended `P6a` batch 3 with the remaining cheap admin helper
  cleanup:
  - localized the longer admin runtime/control tools in:
    - `web/pages/admintasks/tools_perlcontrol.php`
    - `web/pages/admintasks/tools_settings_copy.php`
  - localized the helper/list screens in:
    - `web/pages/admintasks/tools_editdetails.php`
    - `web/pages/admintasks/tools_optimize.php`
    - `web/pages/admintasks/tools_ipstats.php`
    - `web/pages/admintasks/tools_adminevents.php`
  - extended EN/RU catalogs for those helper screens in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - removed one additional in-scope admin filter leak:
    - `web/pages/admintasks/tools_adminevents.php` now uses the shared
      localized `(All)` label instead of a raw English literal
- 2026-04-22: Validation for the batch 3 helper follow-up:
  - targeted Dockerized `php -l` passes for:
    - `web/pages/admintasks/tools_editdetails.php`
    - `web/pages/admintasks/tools_optimize.php`
    - `web/pages/admintasks/tools_ipstats.php`
    - `web/pages/admintasks/tools_adminevents.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` after the final
    `tools_adminevents.php` cleanup so HTTP smoke used the current workspace
    image
  - authenticated admin HTTP smoke using the local fixture admin account returns
    HTTP `200` with expected localized tokens for:
    - `hlstats.php?mode=admin&task=tools_perlcontrol&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_settings_copy&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_editdetails&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_optimize&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_ipstats&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_adminevents&lang=en|ru`
  - explicit language persistence/fallback contract remains intact on the
    authenticated helper contour:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when only `PHPSESSID` is preserved
    - default EN rendering with a fresh authenticated request without language
      state
- 2026-04-22: Landed `P6a` batch 4 on the next cheap admin `EditList` screens:
  - localized repeated column labels, short guidance text, and submit buttons
    in:
    - `web/pages/admintasks/awards_plyractions.php`
    - `web/pages/admintasks/awards_plyrplyractions.php`
    - `web/pages/admintasks/awards_plyrplyractions_victim.php`
    - `web/pages/admintasks/servers.php`
    - `web/pages/admintasks/voicecomm.php`
    - `web/pages/admintasks/roles.php`
    - `web/pages/admintasks/teams.php`
    - `web/pages/admintasks/ranks.php`
    - `web/pages/admintasks/ribbons_trigger.php`
  - localized the encrypted-password placeholder in
    - `web/pages/admintasks/servers.php`
  - extended EN/RU catalogs for the shared admin labels reused by those
    screens in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 4:
  - targeted Dockerized `php -l` passes for all nine touched admin pages plus
    `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=awards_plyractions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_plyrplyractions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_plyrplyractions_victim&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=servers&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=voicecomm&lang=en|ru`
    - `hlstats.php?mode=admin&task=roles&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=teams&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=ranks&game=cstrike&lang=en|ru`
  - focused raw-literal grep over the nine touched admin files no longer shows
    user-facing raw English outside the standard file header comment block and
    non-UI internals
  - route note:
    - `ribbons_trigger` still falls back to the legacy overview/basic-mode
      contour on a direct noninteractive request after login, so this batch
      validates it by syntax, catalogs, and focused grep, but not by direct
      token-level HTTP smoke
- 2026-04-22: Landed `P6a` batch 5 on the next medium-cost admin pages:
  - localized the remaining repeated column labels, select option labels,
    explanatory copy, and submit buttons in:
    - `web/pages/admintasks/actions.php`
    - `web/pages/admintasks/adminusers.php`
    - `web/pages/admintasks/awards_weapons.php`
    - `web/pages/admintasks/ribbons.php`
    - `web/pages/admintasks/weapons.php`
  - extended EN/RU catalogs for the new shared/admin task literals in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 5:
  - targeted Dockerized `php -l` passes for all five touched admin pages plus
    `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=actions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=adminusers&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_weapons&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=ribbons&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=weapons&game=cstrike&lang=en|ru`
  - focused raw-literal grep over the five touched admin files no longer shows
    the retired user-facing raw English literals outside localized key names
    and non-UI internals
- 2026-04-22: Landed `P6a` batch 6 on the remaining heavy admin pages:
  - localized the remaining user-facing text in:
    - `web/pages/admintasks/clantags.php`
    - `web/pages/admintasks/hostgroups.php`
    - `web/pages/admintasks/options.php`
  - extended EN/RU catalogs for:
    - the full `clantags` and `hostgroups` help text blocks
    - the `options` page section headings
    - option field labels and DB-backed select-choice labels used on
      `options.php`
  - kept the options-page rendering dictionary-backed without changing the
    existing admin option definitions by localizing section titles, field
    labels, submit/success text, and choice text at render time
- 2026-04-22: Validation for `P6a` batch 6:
  - targeted Dockerized `php -l` passes for:
    - `web/pages/admintasks/clantags.php`
    - `web/pages/admintasks/hostgroups.php`
    - `web/pages/admintasks/options.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=clantags&lang=en|ru`
    - `hlstats.php?mode=admin&task=hostgroups&lang=en|ru`
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
  - focused raw-literal grep over the three touched admin files no longer shows
    the retired user-facing raw English strings outside internal fallback maps,
    legacy internal option definitions, and non-rendered code literals
- 2026-04-22: Landed `P6a` batch 7 on the final shared helper fallback cleanup:
  - removed fallback-only raw-English helper text from
    `web/includes/functions.php`
  - switched the remaining helper/runtime messages there to catalog-key-backed
    lookup without embedded English last-resort strings
  - added the missing shared catalog key `error.invalid_url` in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 7:
  - targeted Dockerized `php -l` passes for:
    - `web/includes/functions.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke still returns HTTP `200` with
    expected localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=clantags&lang=en|ru`
    - `hlstats.php?mode=admin&task=hostgroups&lang=en|ru`
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
  - focused helper grep confirms no remaining fallback-only raw-English helper
    strings in `web/includes/functions.php` outside the shared legacy literal
    translation map
- 2026-04-27: `LP-P6D-001` stage-level triage (narrow-1000) выполнен по плану
  `team-bonuses-stage-trace`:
  - baseline подтвержден: `hlstats_Events_TeamBonuses legacy=4765`,
    `python=4692`, `delta=-73` (`legacy-only=904`, `python-only=831`).
  - в `scripts/hlstats_py/storage.py` добавлена stage-level трассировка
    pipeline TeamBonuses с артефактом
    `scripts/replay_baseline/artifacts/team-bonus-stage-trace.json`
    (stages: `candidate_set`, `eligible_gate_reject`, `team_gate_reject`,
    `ignore_bots_gate_reject`, `dedupe_gate_reject`, `inserted` + агрегаты по
    `actionId/map/playerId`).
  - stage-агрегации на narrow-1000: `candidate_set=9667`,
    `inserted=4692`, `team_gate_reject=4665`, `eligible_gate_reject=310`,
    `ignore_bots_gate_reject=0`, `dedupe_gate_reject=0`.
  - dominant gate для residual определен как `eligible_gate_reject`
    (единственный «узкий» отсекающий gate со значимым вкладом при нулевых
    `ignore_bots/dedupe`), top actions: `279=138`, `278=131`, `269=29`.
  - внесен один минимальный фикс в dominant направлении: нормализация team alias
    (`T/TS/TERRORISTS -> TERRORIST`, `COUNTER[- ]TERRORIST/CTS -> CT`) при
    обновлении in-memory team state и team-based gate сравнениях.
  - revalidate после фикса: unit
    `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests/test_storage.py`
    -> `40 passed`; narrow-1000 + compare дали прежний результат
    `legacy=4765`, `python=4692` (`delta=-73`), то есть гипотеза по alias
    **не подтвердилась**.
  - статус `LP-P6D-001`: **не закрыт**; подтвержден следующий минимальный шаг —
    точечно разбирать composition `eligible_gate_reject` (player lifecycle /
    reward eligibility transitions around earliest legacy-only windows:
    `2024-01-01 19:41:51` `de_mirage`, `2024-01-01 20:47:23` `cs_mansion`).
- 2026-04-28: `LP-P6D-001` продолжен от актуального хвоста `4765` vs `4692`.
  Root cause по `eligible_gate_reject`: legacy Perl `rewardTeam` проходит по
  in-memory `%g_players`, а `doEvent_TeamSelection` делает игрока trackable без
  обязательного `entered the game`; Python требовал `reward_eligible_players`
  (Entry-only) и отбрасывал игроков с валидным team state. Минимальный патч:
  `storage._reward_team_players` теперь допускает игрока, если он либо
  `reward_eligible`, либо уже в `server_active_players`; connected-only без
  trackable team по-прежнему отсекается. Regression test:
  `test_team_bonus_awards_trackable_team_player_without_entry`.
  Валидация:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests/test_storage.py`
    -> `41 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests`
    -> `107 passed`;
  - Python narrow replay:
    `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
    -> `status=ok`, `elapsed_seconds=331.5`;
  - legacy reference replay restored from dump and replayed the same first
    `1000` logs -> `processed=1000`, `errors=0`;
  - `compare_stats_dbs.py --max-examples 20` saved as
    `runtime-db-diff-p6d-narrow-1000-20260428-175918.md`.
  Новый срез `hlstats_Events_TeamBonuses`: `legacy=4765`, `python=4773`
  (дельта `+8`, улучшение на `81` строк к предыдущему `-73`). `LP-P6D-001`
  остаётся открыт; следующий минимальный разбор — residual `+8` по
  grouped action/map/time и identity/name-only examples, не page audit.
- 2026-04-28: added a narrow diagnostic extension for the remaining
  `LP-P6D-001` `+8` TeamBonuses tail. The existing
  `HLSTATS_TEAM_BONUS_TRACE_PATH` payload now includes
  `stage_event_counts`, grouped by `event_time|actionId|map|team`, so the next
  narrow replay can identify exact inserted/rejected event signatures instead
  of relying only on action/map/player aggregates. Code changes:
  `scripts/hlstats_py/storage.py` and regression
  `test_team_bonus_trace_groups_by_event_signature` in
  `scripts/hlstats_py/tests/test_storage.py`. Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py`
  -> `42 passed`. Full `scripts/hlstats_py/tests` reached `107 passed` before
  environment teardown/setup failures from local pytest temp/cache directory
  permissions; Docker replay was not runnable in this session because Docker
  API access returned `permission denied`.
- 2026-04-29: validated the current `refactor/parity-runtime-decisions` HEAD
  after the TeamBonuses decision extraction and diagnostic trace commits.
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` reused the valid legacy narrow-1000 contour and replayed
  the Python contour successfully after adding a root `.dockerignore` for local
  pytest/cache artifacts that must not enter Docker build context.
  `compare_stats_dbs.py --max-examples 20` still reports the expected open
  logical differences, with `hlstats_Events_TeamBonuses legacy=4765`,
  `python=4773` (delta `+8`). Conclusion: the current refactor baseline is
  behavior-neutral for the tracked TeamBonuses count, so the next safe slice is
  policy/RC-B impact triage, with parity decision JSONL tracing only when it
  directly supports classification.
- 2026-04-29: added `docs/parity-acceptance-policy.md` to stop treating every
  Perl/Python diff as a byte-for-byte blocker. Current P6d classification:
  `TeamBonuses +8` is diagnostic backlog unless RC-B/identity triage proves
  visible or aggregate-critical impact; `Events_Entries legacy=0` vs
  `python>0` remains an accepted legacy difference and stays in compare
  output; current post-RC-C narrow-1000 compare shows `python=1017`.
  At that checkpoint, RC-B (`ChangeTeam` / `Connects` / `Chat` /
  `PlayerActions`) and identity/player count drift were the next must-review
  areas before any runtime behavior change.
- 2026-04-29: completed docs-only RC-B impact triage on
  `runtime-db-diff-p6d-narrow-1000-20260428-175918.md`. `ChangeTeam` and
  `Chat` stay diagnostic backlog because current examples are dominated by
  deliberate filters, repeated-line policy noise, and identity/name attribution
  drift; `Connects` was later closed for the scoped player-count subset by the
  transient-id follow-up. `PlayerActions` is promoted to a scoped must-fix for
  Python-only server/plugin `amx_chat` action rows recorded with `playerId=0`
  and counted in action totals. No runtime behavior was changed.
- 2026-04-29: landed the scoped RC-B `PlayerActions` runtime fix. In
  `scripts/hlstats_py/storage.py`, `_record_action` now returns before action
  metadata/count writes when the actor cannot resolve and the action has no
  victim, covering server/plugin lines like `<><><> triggered "amx_chat"`.
  Regression:
  `test_record_action_skips_unresolved_server_actor_without_victim`.
  Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests` -> `113 passed`;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` -> success with reused legacy contour;
  `compare_stats_dbs.py --max-examples 20` still exits `1` for documented
  residual diffs, but `hlstats_Events_PlayerActions` improved from
  `legacy=4972`, `python=6221` to `legacy=4972`, `python=6020`, `amx_chat`
  is absent from Python `hlstats_Actions`, and direct SQL confirms
  `amx_chat` PlayerActions rows with `playerId=0` are `0`. `TeamBonuses`
  remained `4765` vs `4773`; `ChangeTeam` and `Chat` were not changed, and
  `Connects` closed later through the transient-id player-count fix.
- 2026-04-29: completed the first RC-C identity/player-count slice against
  legacy `IgnoreBots` behavior. Legacy Perl resolves bot player objects, but
  bot-owned `Frags`, `PlayerActions`, `Chat`, `Statsme`, and `Statsme2` are
  not recorded when `IgnoreBots=1`, and bot player profiles are flushed with
  `skill=0` / `hideranking=1`. Python now mirrors that scoped policy in
  `scripts/hlstats_py/storage.py`: resolved bot profiles are hidden/reset once
  per server/player, and bot-owned frag/action/chat/statsme rows are skipped.
  Regression coverage:
  `test_ignore_bots_marks_bot_hidden_and_skips_chat` and
  `test_ignore_bots_skips_frag_when_bot_participates`. Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py`
  -> `45 passed`;
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests` -> `115 passed`;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` -> success; `compare_stats_dbs.py --max-examples 20`
  still exits `1` for documented residual diffs. Current SQL/compare anchors:
  bot rows are aligned (`bots=73`, `visible_bots=0`, `skill1000_bots=0` on
  both contours), `hlstats_Events_Frags` raw count is aligned (`5464/5464`),
  `hlstats_Events_Statsme` and `Statsme2` raw counts are aligned
  (`32290/32290`). At this intermediate point, before the transient-id
  follow-up below, the remaining player-count drift was one extra Python row.
  Follow-up RC-C work should stay on human identity/name drift, not
  TeamBonuses or broad RC-B counts.
- 2026-04-29: completed the RC-C human identity/player-count follow-up.
  Direct SQL identified the extra visible Python human as a legacy-invalid
  `STEAM_ID_LAN` advertising identity (`en.prime-server.info BUY PLAYER`,
  `54.74.101.183`) created from repeated connect/chat lines. Legacy Perl
  `getPlayerInfo` treats `UNKNOWN` / pending / LAN ids as transient and does
  not create `HLstats_Player` or `hlstats_PlayerUniqueIds` rows for them in
  normal mode. Python now skips those transient identities for player-owned
  persistence and canonicalizes `STEAM_[0-9]+:` unique ids to the legacy form.
  Regression coverage:
  `test_transient_lan_unique_id_connect_does_not_create_visible_player`,
  `test_transient_lan_unique_id_chat_does_not_create_player_or_chat`, and
  `test_steam3_unique_id_is_stored_with_legacy_canonical_form`. Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py`
  -> `48 passed`;
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests` -> `118 passed`;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` -> success; `compare_stats_dbs.py --max-examples 20`
  still exits `1` for documented residual diffs. Current anchors:
  `Players 323/323`, visible players `250/250`, `Connects 992/992`,
  `Chat 608/662`, `PlayerActions 4972/6019`, `Frags 5464/5464`,
  `Statsme 32290/32290`, `Statsme2 32290/32290`, `TeamBonuses 4765/4773`,
  `Entries 0/1017`, `STEAM_ID_LAN` unique rows `0/0`, and canonical
  `0:247752695` unique rows `1/1`.
- 2026-04-29: closed review follow-ups on the RC-C bot-policy slice. Python now
  applies `IgnoreBots=1` action filtering to both action actor and target before
  writing `hlstats_Events_PlayerPlayerActions` or action counters, and
  `_rollback_pending()` clears the ignored-bot profile application cache so a
  rolled-back stdin batch can reapply `skill=0` / `hideranking=1`. Regression
  coverage:
  `test_ignore_bots_skips_action_when_target_is_bot` and
  `test_ignored_bot_profile_cache_is_cleared_on_rollback`. Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py -q`
  -> `50 passed`;
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests` -> `120 passed`;
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` -> success; `compare_stats_dbs.py --max-examples 20`
  still exits `1` for documented residual diffs. Current anchors stayed
  stable: `Players 323/323`, visible players `250/250`, bots `73/73`, visible
  bots `0/0`, `skill1000_bots 0/0`, `Connects 992/992`, `Chat 608/662`,
  `PlayerActions 4972/6019`, `PlayerPlayerActions 0/0`, `Frags 5464/5464`,
  `Statsme 32290/32290`, `Statsme2 32290/32290`, `TeamBonuses 4765/4773`,
  `Entries 0/1017`.
- 2026-04-29: recorded the next concrete RC-C identity/name anchor. For
  `uniqueId=1:45686725` (`playerId=187`), aggregate kills/deaths match
  (`198/179`) but current-name attribution differs:
  legacy `hlstats_Players.lastName=Mep3ocTb`, Python `Ра-та-та`; both
  `hlstats_PlayerNames` contain `Mep3ocTb`, `Ра-та-та`, and
  `Mep3ocTb Новогодняя`. This is the right next slice for
  `PlayerNames` / `Players_History` / current-name drift. Direct SQL also
  shows top `hlstats_Weapons` kills/headshots match 1:1 on the current
  narrow-1000 contour, while `hlstats_Actions` still differs in derived/extra
  counters (`time`, `latency`, kill-streak counts), so those remain diagnostic
  unless identity/headshot/action attribution proves a narrower visible-impact
  fix.
- 2026-04-29: started the RC-C current-name attribution fix from the
  `1:45686725` anchor. Legacy Perl `HLstats_Player->setName` updates
  `hlstats_PlayerNames` immediately but only pushes `hlstats_Players.lastName`
  through `flushDB`; Python previously updated `lastName` during every player
  resolve, so late name-only/chat lines could make current names newer than the
  legacy contour. Python now keeps immediate `PlayerNames` tracking but defers
  `hlstats_Players.lastName` writes until disconnect/profile flush via
  `_flush_player_profile_name`. Regression:
  `test_player_last_name_is_deferred_until_disconnect`, with existing cached
  player/name-only tests adjusted to the deferred profile-name contract.
  Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o
  cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py -q`
  -> `51 passed`. Full `scripts/hlstats_py/tests` could not produce a clean
  process exit in this Windows session because pytest tmp/cache cleanup hits
  `WinError 5` permission errors, but the run reached all collected tests with
  no assertion failures before cleanup failure (`116 passed` plus tmp-path
  setup/cleanup errors depending on basetemp mode). Docker replay was not run:
  Docker API access returned `permission denied`.
- 2026-04-30: reviewed the current RC-C diff and completed validation for the
  current-name slice. Full storage/runtime validation passes when pytest cache
  is disabled and basetemp is moved out of the locked repo temp dirs:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p
  no:cacheprovider --basetemp "$env:TEMP\hlstats-pytest-basetemp-current"
  scripts/hlstats_py/tests` -> `121 passed`. The narrow-1000 replay gate also
  completed with a reused valid legacy contour:
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` -> success. `compare_stats_dbs.py --max-examples 20`
  still exits `1` for documented residual differences. Direct SQL now confirms
  the `uniqueId=1:45686725` current-name anchor is aligned:
  legacy and Python both have `playerId=187`, `lastName=Mep3ocTb`, and
  kills/deaths `198/179`; both alias sets contain the same three names. The
  regenerated
  `python-sql-snapshot-1000.txt` was restored and is not part of the intended
  diff.
- 2026-04-30: completed the required GeoIP backfill sanity check before
  treating the `1:45686725` GeoIP gap as real drift. The initial documented
  command with `scripts/hlstats.conf` is invalid for this local contour because
  that config contains blank DB settings and overrides CLI DB flags. The working
  host-side command was run from `scripts/` so the resolver could find
  `GeoLiteCity/GeoLite2-City.mmdb`:
  `PYTHONPATH=.;proxy_daemon_py python -m hlstats_awards_py --db-host
  127.0.0.1:3327 --db-name hlstatsxce --db-username hlstatsxce --db-password
  hlx123 --geoip --replay-mode` -> exit `0`. Post-backfill SQL confirms
  `uniqueId=1:45686725` is now aligned on both contours:
  `playerId=187`, `lastName=Mep3ocTb`, kills/deaths `198/179`, `flag=RU`,
  `country=Russia`, `lastAddress=178.68.210.14`. Python has no players with a
  non-empty `lastAddress` and empty `flag`/`country`; a fresh compare still
  exits `1` for `15` documented residual tables. Follow-up should stay on
  broader `PlayerUniqueIds` / `PlayerNames` / `Players_History` attribution
  drift.
- 2026-04-30: closed a narrow `Players_History` attribution slice in the
  ignored-bot profile path. Legacy Perl creates ignored-bot history rows through
  `check_history` with the default history skill, then the ignored-bot
  `flushDB` branch resets only `hlstats_Players.skill` to `0` and skips the
  normal `hlstats_Players_History` update. Python now mirrors that split:
  `_apply_ignored_bot_profile` still persists `skill=0` / `hideranking=1`, but
  no longer mutates the in-memory skill used to seed history rows. Regression:
  `test_ignore_bots_keeps_history_seed_skill_at_legacy_default`. Validation:
  `test_storage.py -q` -> `52 passed`; full `scripts/hlstats_py/tests` with
  pytest cache disabled -> `122 passed`; narrow-1000 dual contour with reused
  legacy -> success; GeoIP backfill -> exit `0`; `compare_stats_dbs.py
  --max-examples 5` still exits `1` for documented residual diffs. Direct SQL
  anchors: `hlstats_Players_History 659/659`, Python bot history rows with
  `skill=0` -> `0`, `uniqueId=1:45686725` remains aligned with `RU/Russia`.
  Focused identity compare now shows `PlayerUniqueIds 2/2`, `PlayerNames
  47/38`, and `Players_History 111/111`.
- 2026-04-30: continued the P6d RC-C refactor with a behavior-neutral
  identity decision extraction. `runtime_decisions.py` now owns Steam unique-id
  canonicalization, transient unique-id detection, and the structured
  `should_persist_player_identity(...)` gate; `storage.py` delegates identity
  persistence decisions to that layer. Regression coverage was added in
  `test_runtime_decisions.py`. Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p
  no:cacheprovider --basetemp <workspace-temp>
  scripts/hlstats_py/tests/test_runtime_decisions.py
  scripts/hlstats_py/tests/test_storage.py -q` -> `59 passed`. Full
  `scripts/hlstats_py/tests` still cannot produce a clean Windows exit in this
  session because pytest tmp cleanup hits `WinError 5`; Docker/API-backed
  replay and compare are also blocked by Docker API `permission denied`.
- 2026-05-01: closed a narrow current-name flush gap found while continuing the
  broader human `PlayerNames` / `Players_History` drift investigation. Legacy
  periodic/shutdown `flushDB` writes each live player's current `lastName`; after
  the Python deferred-name slice, players that never emitted a disconnect could
  keep the old `hlstats_Players.lastName` until another explicit profile flush.
  `finalize_import()` now calls `_flush_all_player_profile_names(...)` before
  the import-tail `last_event` update. Regression:
  `test_finalize_import_flushes_deferred_player_profile_names`, first observed
  failing because `finalize_import()` only executed
  `_FINALIZE_PLAYER_LAST_EVENT_QUERY`, then passing after the helper extraction.
  Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p
  no:cacheprovider --basetemp "$env:TEMP\hlstats-pytest-basetemp-current"
  scripts/hlstats_py/tests/test_runtime_decisions.py
  scripts/hlstats_py/tests/test_storage.py -q` -> `60 passed`; full
  `scripts/hlstats_py/tests` -> `126 passed`. Narrow-1000 dual contour with
  reused legacy succeeded, followed by the host-side GeoIP backfill. Fresh
  `compare_stats_dbs.py --max-examples 5` still exits `1` for the documented 15
  residual tables. Focused compare moved to `PlayerUniqueIds 1/1`,
  `PlayerNames 45/36`, and `Players_History 110/110`; `TeamBonuses` remains
  `4765/4773`, while `Statsme` and `Statsme2` stay count-aligned at
  `32290/32290`. The regenerated `python-sql-snapshot-1000.txt` was restored
  and is not part of the intended diff.
- 2026-05-05 automation continuation: reviewed the current RC-C diff and kept
  the player-count / `STEAM_ID_LAN` and TeamBonuses gates closed. Added an
  explicit event-handler contract assertion for parsed `"changed name to"`
  updates (`event_code="change_name"`, `new_name`) and removed the stale
  `_touch_player_profile(..., track_name_history=...)` parameter left after the
  deferred profile-name refactor. No replay-critical behavior was intentionally
  changed in this continuation. Validation:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -p
  no:cacheprovider --basetemp C:\tmp\hlstats-pytest-automation
  scripts/hlstats_py/tests/test_events.py
  scripts/hlstats_py/tests/test_runtime_decisions.py
  scripts/hlstats_py/tests/test_storage.py -q` -> `76 passed`; broad
  `scripts/hlstats_py/tests -k "not heatmap and not load_settings"` with
  external basetemp -> `122 passed, 8 deselected`.
