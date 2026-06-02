# Status: Standalone Python+i18n Product Lane

## Snapshot

- Last updated: `2026-06-02`
- `P6d` is no longer an active residual hunt for `Entries`, `ChangeTeam`,
  `PlayerNames`, `Players_History`, or `TeamBonuses`; those gates are closed
  for the supported narrow/default Python contour.
- The active autonomy track is now release-readiness/product hardening:
  docs truth, repository-wide CI, package/runtime boundaries, lifecycle and
  control-plane hardening, explicit DB modes, parity acceptance automation, and
  PHP EN/RU stabilization.
- If a future parity-affecting change creates a new residual, restart from
  [`docs/parity-debug-pipeline.md`](parity-debug-pipeline.md) and
  [`docs/replay-fast-path.md`](replay-fast-path.md), then write evidence into
  `docs/audits/legacy-python-parity-20260423/`.

Current parity state:

- The defuse-boundary `kill_streak_*` residual is closed. The follow-up
  `L0102207.log` case showed that a recorded `Defused_The_Bomb` should not
  suppress the defuser's pending round-end streak; suppression is now limited
  to defuse actions that are gated by min-player policy. The fresh full
  `narrow-1000` compare no longer lists `hlstats_Actions` or
  `hlstats_Events_PlayerActions`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260518-after-gated-defuse-suppression.md`.
- The first `hlstats_Events_TeamBonuses` hostage-rescue residual is closed.
  `Rescued_A_Hostage` team rewards now bypass the round-status gate in the
  same player-trigger path legacy uses after `Round_End`. The fresh full
  `narrow-1000` compare is `4765/4737`, with `28` legacy-only rows and `0`
  python-only rows. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260519-after-rescue-roundstatus.md`.
- The planted-bomb `hlstats_Events_TeamBonuses` residual cluster is closed.
  Legacy-style post-round team rewards are allowlisted for
  `cstrike:Planted_The_Bomb` in the player-action path alongside
  `Rescued_A_Hostage`. Targeted storage tests, `hlstats-worker` rebuild,
  single-log `L0101059`, and fresh full `narrow-1000` replay were rerun. The
  fresh compare is `4765/4764`, with `1` legacy-only row and `0` python-only
  rows. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260519-after-planted-roundstatus.md`.
- The `L0102211.log` `Dance Bear` / `CTs_Win` TeamBonuses lifecycle residual
  is closed. Perl evidence showed that `rewardTeam` rewards the current
  team-bound player set before the periodic idle timeout scan; generic
  damage-only lines still must not reactivate team-reward membership. Python
  now records the event before the timeout cleanup and uses the legacy timeout
  scan upper bound for deterministic replay. Fresh single-log evidence has
  `hlstats_Events_TeamBonuses legacy=156`, `python=156`, and no
  `uniqueId`-keyed differences. Fresh full `narrow-1000` evidence has
  `legacy=4753`, `python=4753`, and no stable-key TeamBonuses differences.
  Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260523-after-team-bonus-timeout-cadence.md`.
- P6d-M4 `hlstats_Players` is closed as a GeoIP-only contour/policy rule. The
  raw replay compare, before maintenance GeoIP backfill, can show `323/323` with
  `250` legacy-only normalized rows and `250` python-only normalized rows;
  the field classifier reports `250 geoip_only_rows` and `0 non_geoip_rows`.
  Only `country` and `flag` differ, while `lastAddress`, `kills`, `deaths`,
  `suicides`, `skill`, `shots`, `hits`, `teamkills`, `headshots`,
  `kill_streak`, `death_streak`, `activity`, and `hideranking` match. Direct
  SQL anchors confirm `SELECT COUNT(*) FROM hlstats_Players WHERE country <> ''
  OR flag <> '';` as `legacy=250` and `python=0`. Legacy `getAddress` writes
  `lastAddress`, `geoLookup` writes only `country`/`flag`, and `flushDB()`
  stats/session fields do not write `country`/`flag`; on the Python path,
  `storage.py` runtime writes `lastAddress`/stats/session while GeoIP fields
  are maintenance/backfill via `hlstats_awards_py` and not stdin replay. Raw
  replay parity may therefore carry this accepted GeoIP-only diff; release-clean
  parity requires post-replay `hlstats_awards_py --geoip`, after which
  `hlstats_Players` should disappear from the compare. No minimal runtime fix
  remains for `hlstats_Players`.
- The first `hlstats_PlayerNames` anchor is stateful, not a clean isolated
  single-log case. The `Player21` / `Dim$0n` / `Dim$on` residual centers on
  `0:1161623468` around `L0102212.log:487`, but isolated `L0102212` produces a
  different alias split than the neighboring-log cluster. A tested hypothesis
  to flush alias rollups on `changed name to` was rejected and not retained.
  Evidence lives in parity traces:
  `p6d-playernames-player21-L0102212-before-alias-flush`,
  `p6d-playernames-player21-L0102212-after-alias-flush-full`, and
  `p6d-playernames-player21-L0102209-L0102213-after-alias-flush`.
- The stateful `Player21` / `Dim$0n` / `Dim$on` PlayerNames cluster is now
  closed. Legacy-first review showed that ordinary same-live-object log
  descriptors do not rename the active player object; only first sight,
  explicit name-change/userid-rollover, or reopened closed objects should
  update the Python runtime alias. The same-cluster replay no longer lists
  `hlstats_PlayerNames`, and a fresh clean `narrow-1000` reduces
  `hlstats_PlayerNames` to `0` legacy-only / `1` python-only normalized row:
  the already-known `XYU` / `unnamed` alias (`0:552632503`). Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260523-after-playernames-live-alias.md`.
- The rejected `changed name to` fix was a process miss, not a valid partial
  fix: the local unit test encoded an oversimplified alias-flush rule before
  proving that the broad residual was caused by name-change flushing. Legacy
  Perl does mark the player dirty before replacing the name, but replay evidence
  shows the residual also depends on prior/following log state, timeout/flush
  cadence, and possibly duplicate weaponstats/name lifecycle ordering. Because
  the full `L0102212` and `L0102209..L0102213` replays still showed
  `PlayerNames` drift after the attempted change, the code and test were
  rolled back; only the analysis notes were kept.
- The first `Players_History` streak hypothesis was also rejected and not
  retained. Changing Python to pass current event-level
  `kill_streak`/`death_streak` values instead of cached max streak values moved
  some `Rakza` kill-streak columns in the right direction, but broadened the
  fresh `narrow-1000` `hlstats_Players_History` normalized residual from
  `50/50` to `106/106`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-history-streak-current-hypothesis-rejected-20260524.md`.
  The next candidate needs to trace legacy `flushDB` sampling boundaries rather
  than changing every event-level rollup.
- The follow-up `Players_History` flush-sampling fix is retained. Legacy-first
  review showed that `kill_streak` is promoted when a life ends, including
  single-kill lives, while derived `kill_streak_N` actions are emitted only for
  streaks greater than one; `flushDB()` later samples those live-object max
  fields into `Players` and `Players_History`. Python now promotes max
  kill-streak only at `_end_kill_streak`, includes max streaks in connection
  flush sampling, and clears max streak cache on live-object close. Targeted
  storage/validation tests pass, and fresh `narrow-1000` reduced
  `hlstats_Players_History` from `50/50` to `14/14`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-history-flush-sampling-20260524.md`.
- A follow-up `Players_History` victim flush-boundary fix is in place at the
  unit level. Legacy review confirmed that an ordinary frag immediately
  flushes the killer object, while the victim's deaths/session skill remain in
  the live object until the next `flushDB()` boundary; Python now defers
  victim-side history rollups and writes them on the later player flush date.
  Targeted storage tests pass, including the new cross-day victim-flush
  regression. Single-log `L0103146` replay was rerun with a `30/30` guard
  window: the main sliced log still has the known artificial current-date
  `Rakza` seed row, while the guard no longer lists `hlstats_Players_History`
  and fails only on the pre-existing `hlstats_Servers` slice residual. Evidence:
  `scripts/replay_baseline/artifacts/parity-traces/p6d-history-rakza-L0103146-victim-flush/`.
- The broad `Players_History` flush-boundary fix is retained. A fresh
  `narrow-1000` run after the victim-specific fix reduced
  `hlstats_Players_History` from the previous `14/14` residual to `10/10`;
  the remaining rows were Jan 6/Jan 7 flush-boundary splits for `Mk`
  (`1:815451478`), `FRANKESTINE` (`0:1089759883`), `Johnny`
  (`0:164297241`), `pardesiboi404` (`0:109115526`), and `Jerry AK`
  (`0:1601618021`). Legacy review confirmed that `updateDB()` only marks the
  live player dirty and `flushDB()` samples the live object into
  `hlstats_Players_History`, so Python now defers all player history
  stat/skill rollups to the live-object flush boundary. The final fresh
  `narrow-1000` compare no longer lists `hlstats_Players_History`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260525-after-history-flush-and-streak-gap-compare.txt`.
- The previously suspected `Dance Bear` / `CTs_Win`
  `hlstats_Events_TeamBonuses` row did not resurface in the final broad
  contour. The final `narrow-1000` anchors are `legacy=4765`,
  `python=4765`, and the logical compare no longer lists
  `hlstats_Events_TeamBonuses`.
- A final strict GeoIP rerun was required after the broad replay because the
  replay importer repopulates `lastAddress` but does not perform maintenance
  backfill. Before the rerun, Python still had `250` players with
  `lastAddress <> ''` and empty `flag`/`country`; after
  `hlstats_awards_py --geoip`, that count returned to `0` and
  `hlstats_Players` disappeared from the broad compare. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260525-final-after-geoip-compare.txt`.
- The remaining `XYU` / `unnamed` `hlstats_PlayerNames` residual is closed.
  Legacy evidence showed that the player object for `0:552632503` is created
  from a blank-name connect in `L0103048.log`, so later ordinary `unnamed`
  descriptors must not create an alias row; only the explicit
  `changed name to "XYU"` event should touch `hlstats_PlayerNames`. Python now
  preserves the blank constructor alias state without writing a blank/unnamed
  row. Fresh broad `narrow-1000` plus strict GeoIP backfill reduced
  `hlstats_PlayerNames` from `0/1` to absent from the logical compare; direct
  anchors are `legacy=415`, `python=415`, and both DBs now have only
  `(playerId=203, name=XYU)` for `0:552632503`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260525-after-playernames-blank-alias-compare.txt`.
- The `hlstats_Events_Entries` residual is now confirmed closed for the
  current narrow contour/default Python path. After Docker Desktop was
  started, the narrow contour command succeeded and the compare command
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`
  no longer lists `hlstats_Events_Entries`; the direct counts are
  `legacy=0`, `python=0`. Evidence was recorded in
  `docs/audits/legacy-python-parity-20260423/python-sql-snapshot-1000.txt`
  and `scripts/replay_baseline/comparison/.parity-state/20260526-061001.json`.
- P6d-M5 `hlstats_Events_ChangeTeam` is closed after the second TDD fix and
  the narrow-1000 replay/compare. Root cause: Python lost the blank team seed
  after userid rollover/blank reconnect/entry, so the first ignored
  time/latency `<UNASSIGNED>` saw `previous_team=None` and suppressed the
  implicit `ChangeTeam`; legacy records descriptor-driven nonblank team
  transitions. The fix keeps `seed_blank_team_on_rollover` for ignored
  time/latency priming and now also uses it for connect in `_record_connection`,
  while blank seeding stays guarded by closed-player checks. Targeted tests
  `test_rollover_blank_status_followed_by_unassigned_trigger_emits_implicit_change_team`
  and `test_rollover_blank_connect_and_blank_entry_before_unassigned_trigger_emits_implicit_change_team`
  passed; `unassigned or team_change or rollover` was `12/12`,
  `test_storage.py` was `133/133`, and the final `Run-DualContour-1000` rerun
  with `-ReuseValidLegacy` reused valid legacy from run state
  `20260526-081158.json`. The final compare had no
  `hlstats_Events_ChangeTeam` residual. The only raw-replay difference was the
  accepted pre-backfill `hlstats_Players` GeoIP-only contour/policy diff
  (`323/323`, `250` legacy-only rows, `250` python-only rows); release-clean
  validation applies the post-replay GeoIP backfill described above. SQL anchors
  for `ChangeTeam` were `legacy total=1345/unassigned=47` and `python
  total=1345/unassigned=47`.

## In Progress

- [ ] Phase 8 of `docs/autonomy-work-plan-20260601.md`: stabilize PHP
  request/lang state, cache boundaries, and replay-backed EN/RU verification
  without a big-bang frontend rewrite.

## Done

- Restored legacy-style daily `last_skill_change` persistence for the Python
  runtime so the existing player/clan/country ranking arrows render from live
  replay data again. The web layer already consumed `hlstats_Players.last_skill_change`;
  the missing piece was runtime flush parity. Python now persists daily
  cumulative skill deltas to `hlstats_Players.last_skill_change`, keeps
  `hlstats_Players_History.skill_change` on the per-day history row, resets
  the cumulative value on day rollover, and keeps ignored-bot trend neutral.
  Targeted storage tests passed, the broader `test_runtime_decisions.py` +
  `test_storage.py` suite passed, fresh `Run-DualContour-1000 -ReuseValidLegacy`
  completed, the raw `compare_stats_dbs.py --max-examples 20` report still had
  only the accepted pre-backfill GeoIP-only `hlstats_Players` diff, and
  replay-backed `mode=players` HTML on the Python contour now contains rendered
  `t0/t1/t2` trend icons.
- Closed the earlier `hlstats_Servers.act_players` residual and removed it from
  the active parity gate.
- Added the single-log parity-debug workflow on
  `experiment/parity-trace-harness`, including log locating, safe-window
  extraction, and focused DB write tracing.
- Closed the local GoldSrc `Bomb_Defused` / `round_status` projection bug that
  was causing the Python-only Rakza `kill_streak_2` drain before replay
  revalidation.
- Closed the server-wide defuse-boundary suppression bug that dropped other
  players' round-end `kill_streak_*` rows after `Defused_The_Bomb` /
  `Bomb_Defused`. Targeted storage tests, `hlstats-worker` rebuild,
  single-log `L0102204`, and full `narrow-1000` replay were rerun.
- Closed the first TeamBonuses hostage-rescue residual from `L0101061.log`
  (`2024-01-01 20:33:47`, `cs_mansion`, `Rescued_A_Hostage`) with targeted
  storage tests, `hlstats-worker` rebuild, single-log replay, and full
  `narrow-1000` replay.
- Closed the planted-bomb TeamBonuses residual cluster from `L0101059.log`
  (`2024-01-01 19:40:12`, `de_mirage`, `Planted_The_Bomb`) with targeted
  storage tests, `hlstats-worker` rebuild, single-log replay, and full
  `narrow-1000` replay.
- Closed the single-log `Dance Bear` TeamBonuses lifecycle residual from
  `L0102211.log` by aligning Python with legacy idle auto-disconnect and by
  not treating generic damage-only lines as team-reward reactivation. A
  follow-up timeout-cadence fix moved Python idle cleanup after the current
  event and rescheduled cleanup on the legacy timeout scan upper bound. Targeted
  storage/runtime tests, single-log replay, and full `narrow-1000` confirmation
  are green for `hlstats_Events_TeamBonuses`.
- Closed `P6d-M1`: `hlstats_Events_TeamBonuses` no longer appears in the fresh
  logical compare, and direct stable-key SQL reports `legacy=4753`,
  `python=4753`, with empty legacy-only and python-only sets.
- Closed `P6d-M2` for the current contour: `ChangeTeam`, `Connects`, `Chat`,
  and `PlayerActions` no longer appear in the fresh logical compare.
- Closed `hlstats_Events_Entries` for the current narrow contour/default Python
  path after targeted unit coverage and replay promotion; direct counts are
  `legacy=0`, `python=0`.
- Closed the stateful `Player21` / `Dim$0n` / `Dim$on` PlayerNames alias
  attribution cluster by preserving the legacy live-object constructor alias
  across ordinary same-live-object descriptors. Targeted storage tests,
  `hlstats-worker` rebuild, same-cluster replay, and fresh full `narrow-1000`
  were rerun; the later `XYU` / `unnamed` alias residual is also closed.
- Reduced `hlstats_Players_History` from `50/50` to `14/14` by aligning Python
  kill-streak sampling with legacy `endKillStreak` / `flushDB` boundaries.
- Closed the remaining broad `hlstats_Players_History` residual by deferring
  all player history stat/skill rollups to legacy-style player `flushDB`
  boundaries. The path went from `14/14` before the victim fix, to `10/10`
  after the victim-only fix, to absent from the final broad compare.
- Closed the extra `Fat` (`1:58816828`) `hlstats_Players.kill_streak` drift by
  continuing pending streak flushes even when `connection_time` is clamped to
  zero for gaps above `600` seconds.
- Closed the broad `hlstats_Players` GeoIP residual by rerunning strict
  maintenance GeoIP backfill after the final replay. The path went from
  `250/250` `country`/`flag` diffs to absent from the final broad compare, and
  Python players with `lastAddress <> ''` and empty `flag` dropped from `250`
  to `0`.
- Closed the final real `hlstats_PlayerNames` drift for `XYU`
  (`0:552632503`) by treating blank-name connects as a constructed live object
  state without persisting a placeholder alias. The broad logical compare moved
  from `hlstats_PlayerNames` `0/1` to `0/0`.
- Completed Phase 0 of `docs/autonomy-work-plan-20260601.md`: `docs/status.md`,
  `docs/plans.md`, and `docs/test-plan.md` now agree that P6d is closed for the
  supported contour, stale reopened parity items are not active work, and the
  GeoIP rule is raw replay diff before backfill versus release-clean parity
  after post-replay `hlstats_awards_py --geoip`.
- Completed Phase 1 of `docs/autonomy-work-plan-20260601.md`: the old
  proxy-only workflow was replaced by repository-wide product CI covering
  `proxy_daemon_py` lint/type/test, `hlstats_py` tests, `replay_baseline`
  helper tests, PHP syntax lint for `web/`, and docs sanity checks. A
  scheduled/manual nightly parity placeholder now runs lightweight replay
  helper smoke while the full Docker-backed parity gate remains deferred to
  Phase 7. Local Phase 1 validation passed for `scripts/replay_baseline/tests`,
  `scripts/hlstats_py/tests`, and `scripts/proxy_daemon_py/tests`; local PHP
  lint could not be run because the Windows workspace does not currently have
  `php` on `PATH`, while GitHub CI installs PHP 8.2 explicitly.
- Completed Phase 2 of `docs/autonomy-work-plan-20260601.md`: added regression
  coverage around the current `SyncDatabaseAdapter._ensure_connection()`
  behavior without changing production code or reopening the stale reconnect
  bugfix. The new tests cover lazy connection creation, disabled ping,
  successful ping reuse, `ping(reconnect=False)`, and reconnect after a failed
  ping. `hlstats_py` storage tests now also pin the stdin batch skip-ping bridge
  that uses this shared adapter. Targeted selected tests passed with
  `--coverage-threshold=0` because the proxy test harness has a global coverage
  gate that is not meaningful for a `-k` slice; the full
  `scripts/proxy_daemon_py/tests` suite passed with the normal coverage gate.
- Completed Phase 3 of `docs/autonomy-work-plan-20260601.md`: introduced
  `hlx_core` as the explicit shared infrastructure package for config, DB,
  logging, UDP transport helpers, and the DB-config bootstrap helper. Focused
  product consumers (`hlstats_py`, `hlstats_ftp_py`, `hlstats_awards_py`,
  `hlstats_resolve_py`, and `import_bans_py`) now import shared infrastructure
  from `hlx_core` instead of the daemon package, while `proxy_daemon_py` keeps
  compatibility wrappers for its own public API and daemon-specific modules.
  `hlstats_py` is now an installable package with a path dependency on
  `hlx_core`; product CI installs it and runs an import smoke instead of using
  the old `scripts:scripts/proxy_daemon_py` bridge. Local validation passed for
  source imports, isolated venv install/import smoke, `hlstats_py` +
  `hlstats_resolve_py` tests, and the full `proxy_daemon_py` suite with the
  normal coverage gate.
- Completed Phase 4 of `docs/autonomy-work-plan-20260601.md`:
  `scripts/run_proxy_py` and `scripts/run_hlstats_py` now share
  `scripts/lib/process_lifecycle.sh`, stop with `SIGTERM` first, wait up to
  `HLX_STOP_TIMEOUT`, and reserve `SIGKILL` for timeout fallback. Deployment
  notes in `docs/python_migration_usage_guide.md` direct service templates to
  call launcher `stop`/`restart` instead of hard-killing runtime processes.
  Validation used Git Bash for `bash -n`, smoke-tested both graceful PID-file
  stop and TERM-ignoring fallback stop, ran `git diff --check` and docs UTF-8
  reads, and covered the runtime signal-adjacent Python slices. The selected
  proxy slice was run with `--coverage-threshold=0` because the package-level
  coverage gate is not meaningful for a tiny lifecycle-adjacent subset.
- Completed Phase 5 of `docs/autonomy-work-plan-20260601.md`:
  control-plane handling now separates read-only loopback commands from
  mutating commands. `hlstats_py` still allows direct loopback `HEARTBEAT` and
  `SERVERLIST`, but `RELOAD` and `KILL` require a valid proxied `PROXY Key`
  envelope. `proxy_daemon_py` keeps its real command surface (`HEARTBEAT`,
  `SERVERLIST`, `RELOAD`), rejects direct loopback `RELOAD` without a proxied
  key, and explicitly rejects unsupported `C;KILL;` without forwarding it as a
  game packet. Targeted control tests cover the allowed and forbidden scenarios.
- Completed Phase 6 of `docs/autonomy-work-plan-20260601.md`: online
  `SyncDatabaseAdapter` connections now keep the server/session `sql_mode`
  active and only set `SET NAMES 'utf8mb4'`; legacy-compatible empty
  `SESSION sql_mode` is explicit `import_mode=True` behavior used by
  stdin/replay/import paths. `enable_multi_statements` now requires
  `import_mode=True`, so online services cannot silently enable that importer
  capability. Tests also pin the positive import-mode `client_flag` path and
  the `hlstats_py --stdin` / FTP batch importer wiring. `docs/python_migration_usage_guide.md`
  documents the split.
- Completed Phase 7 of `docs/autonomy-work-plan-20260601.md`: parity
  acceptance is now split into a lightweight PR/local subset and a
  scheduled/manual heavy replay subset. `docs/parity-acceptance.md` documents
  the accepted fixture identity, artifact expectations, promotion rules, and
  where Perl remains required: reference behavior, baseline regeneration,
  targeted investigation, and heavy acceptance replay. `.github/workflows/nightly-parity.yml`
  now runs replay helper smoke plus a self-hosted Windows parity runner job for
  `Run-DualContour-1000.ps1 -UseDumpRestore -ReuseValidLegacy`, post-replay
  GeoIP backfill, compact DB compare, and artifact upload. `docs/test-plan.md`
  records that routine PR work no longer requires live Perl when fixture inputs
  and the accepted legacy contour are unchanged.
- Frontend i18n backlog (`P6a`/`P6b`/`P6c`) remains complete for the supported
  EN/RU product contour.

## Next

1. Start Phase 8: reduce PHP request/lang global-state coupling, maintain PHP
   lint coverage, and add focused replay-backed EN/RU smoke for representative
   routes.
2. Keep the stale reconnect-code fix out of scope unless fresh code or test
   evidence contradicts the current implementation.

## Decisions

- This repo is the product integration lane, not the upstream PR lane.
- Python is the default runtime path for the product lane.
- Perl remains legacy-only for validation and parity reference behavior.
- The integrated Python web contour is the EN/RU product UI reference.
- Codex should use English internally for technical analysis but answer the
  user in Russian unless explicitly asked otherwise.
- If a requested approach is slower, riskier, or weaker than a clear
  alternative, prefer the better project path and call out the tradeoff.
- Non-trivial parity behavior changes must start with a read-only subagent
  inspecting the legacy Perl implementation, followed by local verification of
  that conclusion, before Python behavior is changed.
- Detailed replay transcripts, compare counts, and historical slice notes live
  in `docs/audits/...`, not in this status summary.

## Current Risks

- Docker API access can still block single-log or narrow replay verification
  even when the local unit slice is already green.
- Some Python test commands still require explicit `PYTHONPATH` setup because
  the imported package roots do not yet have a unified developer bootstrap.
- `PlayerNames`, `Players`, and `Players_History` are no longer open
  broad-contour residuals; avoid reopening them without fresh focused evidence.
- The replay comparison contour still uses fixed local container names, so
  concurrent local stacks can block rebuild or smoke passes.
