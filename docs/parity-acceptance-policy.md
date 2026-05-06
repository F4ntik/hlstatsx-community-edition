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
| `hlstats_Events_TeamBonuses` residual `+8` | Current narrow-1000 baseline is `legacy=4765`, `python=4773` after TeamBonuses decision extraction; the refactor branch is behavior-neutral for this count. | Diagnostic backlog | Do not chase the `+8` as a standalone blocker. Revisit only if RC-B or identity triage proves user-visible or aggregate-critical damage. |
| `hlstats_Events_Entries` `legacy=0` vs `python>0` | Already rationalized for the current stage; current narrow-1000 compare after the RC-C bot slice shows `python=1017`, and the compare row remains intentionally visible. | Accepted legacy difference | Keep the compare line. Revisit after RC-B/identity only if entry rows are shown to damage visible stats or awards. |
| `hlstats_Events_ChangeTeam` RC-B | Current narrow-1000 diff is `legacy=1345`, `python=1280`; examples mix deliberate Python filters/dedupe with player-name attribution drift and legacy-only `UNASSIGNED`/HLTV-style rows. | Diagnostic backlog | Do not change behavior from the count alone. Revisit with decision trace only if player history, active roster, server player totals, or TeamBonuses/identity evidence proves impact. |
| `hlstats_Events_Connects` RC-B | The RC-C transient-id fix removed the Python-only `STEAM_ID_LAN` connect spam profile; current narrow-1000 diff is now `legacy=992`, `python=992`. | Closed for the scoped player-count subset | Do not reopen broad Connects policy from the old count. Revisit only if later connection-history or last-address evidence shows a visible mismatch. |
| `hlstats_Events_Chat` RC-B | The same transient-id fix removed one Python-only advertising chat row; current narrow-1000 diff is `legacy=608`, `python=662`. Remaining examples still follow player-name attribution and extra command/help chat rows. | Diagnostic backlog | No broad chat policy change. Promote only if a narrow trace proves dropped/misattributed visible chat messages beyond known identity/name drift. |
| `hlstats_Events_PlayerActions` RC-B | The scoped server/plugin `amx_chat` subset is fixed: unresolved no-victim actions no longer create `playerId=0` PlayerActions rows or action counters. Latest narrow-1000 diff after the RC-C bot slice is `legacy=4972`, `python=6019`; direct SQL confirms Python `amx_chat` action rows are absent. | Diagnostic backlog after scoped fix | Do not continue broad PlayerActions count chasing. Revisit only if RC-C identity/headshot/action attribution proves visible history, award, ranking, or counter damage. |
| Identity/player count drift | Bot-profile policy is fixed and the single extra visible Python human was traced to `STEAM_ID_LAN` advertising connect/chat lines. Python now skips transient `UNKNOWN` / pending / LAN unique ids for player-owned persistence and canonicalizes `STEAM_[0-9]+:` ids. Current anchors: `Players 323/323`, visible players `250/250`, `bots=73`, `visible_bots=0`, `skill1000_bots=0`, raw `Frags`, `Statsme`, and `Statsme2` aligned. The `uniqueId=1:45686725` current-name and GeoIP anchor is now aligned after Python GeoIP backfill (`lastName=Mep3ocTb`, kills/deaths `198/179`, `RU/Russia`, `lastAddress=178.68.210.14`). A narrow ignored-bot history seed follow-up also aligned the hidden-bot history shape: Python has `0` bot `Players_History` rows with `skill=0`, and focused history drift dropped from `417/417` to `111/111`. | Scoped must-fix closed; residual diagnostic backlog | Remaining `PlayerUniqueIds` / `PlayerNames` / `Players_History` differences are broader human name/current-name/skill-history attribution drift. Treat them as must-fix only if a later trace proves visible stats, awards, ranking, or player-history corruption. |

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
