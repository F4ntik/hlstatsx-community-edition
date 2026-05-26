# Parity Acceptance Policy

## Purpose

P6d is a production-readiness audit for the Python runtime, not an open-ended
attempt to reproduce every legacy Perl quirk byte for byte. A replay difference
blocks the migration only when it threatens user-visible statistics, awards,
identity, or operational counters that the product depends on.

This policy is the gate for classifying legacy-vs-Python differences before
changing runtime behavior. Do not merge a parity fix just because a table count
differs; first classify the impact and record the decision.

## Classification

| Class | Meaning | Required action |
| --- | --- | --- |
| Must-fix | The difference can corrupt visible player/server/map/action stats, awards/ribbons, identity, ranking, or operational counters used by the web UI or maintenance tools. | Create or keep an issue, isolate the root cause on a narrow replay window, implement the smallest behavior fix, then run the relevant Python tests and replay gate. |
| Accepted legacy difference | Python intentionally differs from legacy Perl because the legacy behavior is unused, broken, deprecated, or outside the product contract. | Document the rationale, keep compare output visible when it is useful context, and do not add suppression unless the table is truly irrelevant noise. |
| Diagnostic backlog | The difference is real and useful to understand, but there is no current evidence that it damages production readiness or aggregate-visible behavior. | Keep an issue or note with evidence, avoid behavior changes, and revisit only when a related must-review area shows impact. |

## Must-Fix Criteria

A difference is must-fix when any of these are true:

- It changes user-visible player, clan, server, map, weapon, role, or action
  totals in normal web routes.
- It changes awards, ribbons, ranking eligibility, skill, kills/deaths, or
  other competitive metrics.
- It creates, loses, or merges player identity incorrectly, including
  `playerId`, unique id, bot/human classification, placeholder names, or
  player history attribution.
- It breaks server/map/action counters that operators use to trust the Python
  runtime after replay or live import.
- It is a parser/runtime bug that drops valid log lines or records invalid rows
  in a way that can accumulate on live servers.

## Accepted Legacy Difference Criteria

A difference can be accepted when it is explicitly rationalized and bounded:

- Python records a useful runtime fact that the legacy comparison path does not
  persist, and the web/product contract can tolerate it.
- Legacy behavior is a Perl replay artifact, an unused table path, or a known
  operational quirk that should not be copied into the Python runtime.
- The difference remains visible in compare output so future audits can see the
  tradeoff instead of rediscovering it.

## Diagnostic Backlog Criteria

A difference belongs in diagnostic backlog when it is not yet safe to call
accepted, but it should not block useful product work:

- The remaining delta is small relative to the replay window and has no proven
  visible or aggregate-critical damage.
- The next investigation requires trace tooling or RC-B/identity context before
  a behavior decision would be defensible.
- A behavior-neutral refactor or trace layer is more useful than another
  speculative parity fix.

## Current P6d Matrix

| Area | Current evidence | Classification | Decision |
| --- | --- | --- | --- |
| `hlstats_Events_TeamBonuses` narrow residual | Fresh 2026-05-15 narrow-1000 replay plus GeoIP backfill shows only one legacy-only row remains: `legacy=4765`, `python=4764`, example `Dance Bear` `CTs_Win` on `de_inferno_snow`. | Diagnostic backlog | Do not chase the single missing TeamBonuses row ahead of the identity/session must-fix slice. Revisit only if player-history or award evidence proves a broader reward-accounting bug. |
| `hlstats_Events_Entries` current narrow contour | 2026-05-26 narrow replay/compare confirms `legacy=0`, `python=0`, and the logical compare no longer lists `hlstats_Events_Entries` on the default Python path. The narrow command succeeded after Docker Desktop was started, and the compare still exits nonzero only because of unrelated `hlstats_Players` and `hlstats_Events_ChangeTeam` residuals. | Closed for the current narrow contour/default Python path | Do not reopen `Entries` from this confirmation. Keep the unrelated `Players` and `ChangeTeam` residuals as the next compare focus. |
| `hlstats_Events_ChangeTeam` RC-B | Fresh 2026-05-15 narrow-1000 diff is down to one legacy-only row: `legacy=1345`, `python=1344`, example `Rakza` `UNASSIGNED` on `2025-01-03 23:09:41`. | Diagnostic backlog | Do not change behavior from the count alone. Revisit only if the identity/session slice proves this row participates in visible history or roster damage. |
| `hlstats_Events_Connects` RC-B | The RC-C transient-id fix removed the Python-only `STEAM_ID_LAN` connect spam profile; current narrow-1000 diff is now `legacy=992`, `python=992`. | Closed for the scoped player-count subset | Do not reopen broad Connects policy from the old count. Revisit only if later connection-history or last-address evidence shows a visible mismatch. |
| `hlstats_Events_Chat` RC-B | The same transient-id fix removed one Python-only advertising chat row; current narrow-1000 diff is `legacy=608`, `python=662`. Remaining examples still follow player-name attribution and extra command/help chat rows. | Diagnostic backlog | No broad chat policy change. Promote only if a narrow trace proves dropped/misattributed visible chat messages beyond known identity/name drift. |
| `hlstats_Events_PlayerActions` RC-B | The scoped server/plugin `amx_chat` subset is fixed. Fresh 2026-05-15 narrow-1000 diff is now one Python-only row: `legacy=4972`, `python=4973`, example `Rakza` `kill_streak_2` on `de_spay` at `2024-01-06 00:18:10`. | Diagnostic backlog after scoped fix | Do not continue broad PlayerActions count chasing before the session/skill slice. Revisit after the `connection_time` / skill attribution fix if the same row still remains. |
| Identity/session/stat drift | After the 2026-05-15 replay, `hlstats_Servers.act_players` is closed and GeoIP backfill restored `flag`/`country` (`lastAddress <> ''` with empty `flag`/`country` is `0`). Remaining player-facing drift is now concretely visible, not hypothetical: `Alex` (`playerId=162`, `uniqueId=1:507890084`) was `skill=1679` in legacy vs `1713` in Python, with `connection_time=1958` vs `0` and `PlayerNames.numuses=37` vs `29`. Replay-checked Python slices now write elapsed session deltas into `hlstats_Players`, `hlstats_PlayerNames`, and eligible `hlstats_Players_History` rows; the systemic zero is closed (`0/0/0` moved to `285/325/314`), and ignored-bot history overcount is fixed (`BOT:%` history sum is `0`). Exact human attribution remains open: legacy is `298/336/311`, `Alex` is now Python `1976` vs legacy `1958`, and `Players_History.connection_time` is still slightly high in aggregate (`114139` vs legacy `108852`). | Must-fix | Continue on human history/session flush semantics, skill boundaries, and alias-use attribution in `Players`, `PlayerNames`, and `Players_History` before one-row `TeamBonuses`, `ChangeTeam`, or `PlayerActions` cleanup. |

## Runtime Change Rules

- Do not change behavior without an explicit parity-fix decision tied to the
  matrix above.
- Prefer behavior-neutral decision extraction and opt-in traces while a
  difference is still diagnostic.
- Use `HLSTATS_PARITY_DECISION_TRACE_PATH` only when JSONL decision records
  directly support RC-B or identity classification.
- Do not rerun narrow replay for cosmetic docs or pure code movement. For
  replay-critical behavior changes, use the narrow-1000 gate documented in
  `docs/replay-fast-path.md`.
