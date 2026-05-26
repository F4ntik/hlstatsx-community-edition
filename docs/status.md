# Status: Standalone Python+i18n Product Lane

## Snapshot

- Last updated: `2026-05-25`
- The active lane is still `P6d`: legacy-vs-Python parity audit, not
  bootstrap/import/i18n remediation.
- The current debug loop should start from
  [`docs/parity-debug-pipeline.md`](parity-debug-pipeline.md) and
  [`docs/replay-fast-path.md`](replay-fast-path.md), then write evidence into
  `docs/audits/legacy-python-parity-20260423/`.

Current open residuals:

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
- The broad `hlstats_Players` residual is now closed for the current
  `narrow-1000` contour. After the final full replay, a strict GeoIP backfill
  against the Python contour reduced `hlstats_Players` from the intermediate
  `250/250` GeoIP-only `country`/`flag` diff to absent from the final logical
  compare. The extra `Fat` (`1:58816828`) `kill_streak` drift had already been
  closed before the GeoIP pass: legacy clamps a `connection_time` gap above
  `600` seconds to `0`, but still continues `flushDB()` and persists pending
  streak counters. Python now keeps the streak flush on that path while
  suppressing only the oversized connection-time increment.
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
- `hlstats_Events_Entries` remains an accepted visible policy difference:
  legacy `0`, Python `1017`.

## In Progress

- [ ] `P6d-M3 (RC-C)`: only the accepted `hlstats_Events_Entries` policy
  residual remains in the final `narrow-1000` logical compare: legacy `0` vs
  Python `1017`. `hlstats_PlayerNames`, `hlstats_Players`,
  `hlstats_Players_History`, and `hlstats_Events_TeamBonuses` are clean in the
  broad contour.

## Done

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
- Closed the stateful `Player21` / `Dim$0n` / `Dim$on` PlayerNames alias
  attribution cluster by preserving the legacy live-object constructor alias
  across ordinary same-live-object descriptors. Targeted storage tests,
  `hlstats-worker` rebuild, same-cluster replay, and fresh full `narrow-1000`
  were rerun; broad `hlstats_PlayerNames` is now `0/1` normalized with only
  the pre-existing `XYU` / `unnamed` Python-only alias left.
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
- Frontend i18n backlog (`P6a`/`P6b`/`P6c`) remains complete for the supported
  EN/RU product contour.

## Next

1. Keep `Events_Entries legacy=0` vs `python>0` visible in compare output
   unless the acceptance policy is explicitly changed.
2. If the policy changes, revisit `hlstats_Events_Entries` as the only current
   broad logical compare residual.

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
