# Status: Standalone Python+i18n Product Lane

## Snapshot

- Last updated: `2026-05-23`
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
- The broader player-facing drift is still in the
  `Players` / `PlayerNames` / `Players_History` cluster (`250/250`,
  `2/3`, and `50/50` normalized residuals respectively). The missing
  `connection_time` persistence root cause is closed, ignored-bot history
  policy is aligned, and `act_players` is closed. What remains is human
  session/skill/alias attribution calibration, not another broad replay
  bootstrap issue.
- `hlstats_Events_Entries` remains an accepted visible policy difference:
  legacy `0`, Python `1017`.

## In Progress

- [ ] `P6d-M3 (RC-C)`: recheck player identity/history attribution now that
  TeamBonuses and the policy-volume event tables are clean in the current
  `narrow-1000` compare. The current open focus is GeoIP parity plus human
  skill-change, kill/death-streak, and alias-use attribution.

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
- Frontend i18n backlog (`P6a`/`P6b`/`P6c`) remains complete for the supported
  EN/RU product contour.

## Next

1. Start the next parity loop on `P6d-M3` with the cost-aware protocol from
   `docs/plans.md`: legacy-first analysis, single-log/window reproduction,
   focused regression, then replay promotion.
2. Separate GeoIP-only `Players` differences from real stats drift before
   touching attribution logic; then isolate the remaining `PlayerNames` and
   `Players_History` session/skill/alias cases.
3. Keep `Events_Entries legacy=0` vs `python>0` visible in compare output
   unless the acceptance policy is explicitly changed.

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
- The remaining `Players` / `PlayerNames` / `Players_History` residuals are
  visible-product drift, not just compare noise, so they should not be
  downgraded without explicit evidence or acceptance notes.
- The replay comparison contour still uses fixed local container names, so
  concurrent local stacks can block rebuild or smoke passes.
