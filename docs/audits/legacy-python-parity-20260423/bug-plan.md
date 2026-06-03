# P6d Bug Plan — full corpus, direct stdin (2026-04-26)

## Executive summary

- **Policy update (2026-04-29):** use
  `docs/parity-acceptance-policy.md` before changing runtime behavior. P6d is
  now closed or advanced by impact classification, not by byte-for-byte Perl
  quirk matching. Current narrow-1000 `TeamBonuses` residual after the
  filename-order parity runner fix is legacy `4765` vs Python `4774` (delta
  `+9`) and is diagnostic backlog unless RC-B/identity triage proves visible or
  aggregate-critical damage. `Events_Entries`
  `legacy=0` vs `python>0` remains accepted with explicit rationale and must
  stay visible in compare output; current post-RC-C narrow-1000 is
  `python=1017`. RC-C player-count drift is closed for the scoped invalid-id
  subset (`Players 323/323`, visible `250/250`), and the `1:45686725`
  current-name/GeoIP anchor is now aligned after Python GeoIP backfill. The
  later `0:723234133` current-name anchor is also aligned once the Python FTP
  parity contour imports by sorted filename instead of FTP modification time:
  `lastName=Райымбек Гослинг`, kills/deaths `3/4`, `KZ/Kazakhstan`, aliases
  `Player=2` and `Райымбек Гослинг=2`.
  The ignored-bot history seed artifact is also closed: Python still persists
  hidden bot profiles with `skill=0` / `hideranking=1`, but no longer seeds
  bot `Players_History` rows from that reset value. Remaining RC-C work is
  broader human `PlayerUniqueIds` / `PlayerNames` / `Players_History`
  attribution drift.
- **P0 code pass + narrow replay (2026-04-27) completed:** implemented
  runtime-side `round_status` event-order parity for team-trigger rewards and
  stricter ENTRY classification (`entered the game` exact phrase only), then
  re-ran `50/300/1000` dual-contour windows with fresh diffs:
  - `runtime-db-diff-p6d-narrow-50-20260427-050502.md`
  - `runtime-db-diff-p6d-narrow-300-20260427-050912.md`
  - `runtime-db-diff-p6d-narrow-1000-20260427-051926.md`
- **P0/M1 outcome now explicit:**
  - `TeamBonuses` = **substantially narrowed but not closed** at DB parity
    level. The latest narrow-1000 documented tail is legacy `4765` vs Python
    `4692` (delta `-73`) after the round-status, bot/eligibility,
    map-transition, hostage multiplicity, idle-connected-player, and
    candidate-set fixes.
  - `Events_Entries` = **accepted with explicit rationale** for this lane stage:
    Python remains non-zero while legacy remains zero on narrow windows
    (`1000` window: legacy `0`, python `1231`; current post-RC-C narrow-1000
    is `python=1017`), and compare row is kept to
    prevent silent masking.
- **Input parity:** confirmed — ordered manifests match 1:1; server identity `37.230.137.48:27015` for both contours.
- **Authoritative full-corpus DB diff:** `runtime-db-diff-p6d-20260426-161410.md` (from `compare_stats_dbs.py`). Do **not** use `runtime-db-diff-p6d-20260426-034823-retry1.md` (failed/empty; see file stub in repo). Historical P0/P1 rows below describe the pre-policy triage baseline; current acceptance decisions are in `docs/parity-acceptance-policy.md` and the 2026-04-29 RC-B table.
- **P0 triage (2026-04-27, code + diff; live SQL optional):** see **§ P0 triage conclusions** below. TeamBonuses gap is a **concrete bug hypothesis** (missing Perl `round_status` gate on the Python team-bonus path). Events_Entries is **not** “legacy never uses the table” — source writes Entries on `doEvent_EnterGame` for non-bots; `legacy rows: 0` vs `python rows: 190621` in the diff is a **join/enter path mismatch** to trace before changing `compare_stats_dbs` defaults.
- **Confident (evidence in diff):**
  - **`hlstats_Events_TeamBonuses`:** order-of-magnitude inflation on Python vs legacy (≈22.3M vs ≈0.93M rows). This dominates noise and is **not** explainable as normal dictionary drift — treat as **highest-priority** runtime/ingest or semantic mismatch until proven otherwise.
  - **`hlstats_Events_Entries`:** **zero** rows on legacy, **hundreds of thousands** on Python — a **path/schema/wiring** difference between Perl replay and Python worker, not a “small” statistical delta.
  - **Team-change / connect / chat volume:** `hlstats_Events_ChangeTeam`, `hlstats_Events_Connects`, `hlstats_Events_Chat` are far lower on Python than legacy; aligns with **policy differences** (dedup, ignore rules, `UNASSIGNED`/empty team handling, connect coalescing), not a single off-by-one in frags.
  - **Identity and display:** `hlstats_Players` / `PlayerUniqueIds` / `PlayerNames` diffs show **name churn** and Python-only `<missing-player-name>` placeholders; **BOT** rows differ in whether stats are rolled up vs left at zero with `hide_ranking` (legacy examples vs Python heavy stats).
- **Needs repro / narrow run before coding fixes:** residual drift in **`hlstats_Events_Frags`** and **`hlstats_Events_Statsme` / `Statsme2`** (large tables, moderate normalized-only deltas) — confirm against a 50/300/1000 window **after** the two anomalies above are understood, to avoid mixing causes.

## Canonical artifacts (Step A)

| Role | File |
|------|------|
| **Canonical diff** | `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-20260426-161410.md` |
| **Ignore / non-authoritative** | `runtime-db-diff-p6d-20260426-034823-retry1.md` (empty; stub points here) |
| Legacy replay log | `legacy-full-corpus-replay-p6d-20260426-034823.log` |
| Python direct stdin | `python-direct-stdin-import-p6d-20260426-034823-retry1.log` |
| Input manifests | `legacy-full-corpus-input-manifest-p6d-20260426-034823.txt`, `python-direct-input-manifest-p6d-20260426-034823-retry1.txt` |

## Table list — triage (18 tables)

Severity uses README semantics: **P0** = blocker / wrong data at scale; **P1** = core stats mismatch; **P2** = secondary / mostly downstream. “Class” = audit bucket: **C1** reference aggregates, **C2** event stream / player truth, **C3** noise / policy / compare artifact.

| Table | Class | Severity | Hypothesis (primary) | Code fix? |
|-------|-------|----------|----------------------|-----------|
| `hlstats_Servers` | C2 | P1 | Server-level counters differ (kills, map_changes, suicides, shots); same endpoint row, different rolled-up truth | Yes — if counters are part of product contract |
| `hlstats_Actions` | C1 | P2 | Per-action **count** fields differ; downstream of which actions were recorded and how often | After root causes |
| `hlstats_Weapons` | C1 | P2 | Per-weapon kill/headshot counters differ; downstream of frags and weapon attribution | After root causes |
| `hlstats_Maps_Counts` | C1 | P2 | Per-map kill/headshot aggregates differ; may include map name normalization | After root causes |
| `hlstats_Players` | C2 | P1 | Name/skill/visibility; BOT vs human; **`<missing-player-name>`** on Python; `hide_ranking` semantics | Yes — identity + edge cases |
| `hlstats_PlayerUniqueIds` | C2 / C3 | P1 | Same Steam IDs with **different current display names** (rename churn), compare normalization | Partial (merge/rename policy) |
| `hlstats_PlayerNames` | C2 / C3 | P1 | History of names; legacy-only vs python-only name rows for same player keys | Partial |
| `hlstats_Players_History` | C2 | P1 | Daily rollups: legacy shows many all-zero **2024-01-01** bot rows; Python shows **`<missing-player-name>`** daily rows | Yes — history + missing actor |
| `hlstats_Events_ChangeTeam` | C2 | P1 | **~125k** Python vs **~240k** legacy rows — filtering, dedup, ignored actors, or empty/UNASSIGNED team policy | Yes — must align policy with product intent |
| `hlstats_Events_Chat` | C2 | P1 | Fewer chat rows on Python; dropped duplicates, mode filter, or join normalization | Yes if parity required |
| `hlstats_Events_Connects` | C2 | P1 | Fewer connects on Python; possible dedup of repeated connect lines | Yes if parity required |
| `hlstats_Events_Entries` | C2 | **P0** | **Legacy 0, Python ~190k** — table unused on legacy path or over-filled on Python (map/team entry) | **Yes** — understand schema contract first |
| `hlstats_Events_Frags` | C2 | P1 | **~1.08M** vs **~1.03M** frags; moderate gap after matching manifest | Yes — parser / normalization |
| `hlstats_Events_Teamkills` | C2 | P1 | Smaller count delta | Yes — with frags |
| `hlstats_Events_PlayerActions` | C2 | P1 | **More** actions on Python than legacy — not the same as ChangeTeam (different dedup axes) | Yes |
| `hlstats_Events_Statsme` | C2 | P1 | Large row count gap vs legacy | Yes — with frag/statsme pipeline |
| `hlstats_Events_Statsme2` | C2 | P1 | Same as Statsme | Yes |
| `hlstats_Events_TeamBonuses` | C2 | **P0** | **~22.4M** Python vs **~0.93M** legacy — runaway insert, different bonus semantics, or dedup key bug | **Yes** — urgent |

## P0 triage conclusions (2026-04-27)

### `hlstats_Events_TeamBonuses` (authoritative headcounts: legacy **929,699** vs Python **22,381,762**)

- **Same insert shape (per-player fan-out) on both sides:** legacy `rewardTeam` in `hlstats.pl` calls `recordEvent("TeamBonuses", …)` once **per in-memory player on the rewarded team**; Python `storage._reward_team_players` inserts one `hlstats_Events_TeamBonuses` row per matching id in `_server_active_players`. The ~**24×** row ratio is not explained by “Python inserts one row per team member vs one row per event” alone — both do per-member inserts.
- **`round_status` gate (implemented 2026-04-27, product lane):** Perl `doEvent_TeamAction` only calls `rewardTeam` when `round_status == 0` (`HLstats_EventHandlers.plib` ~1925–1928); Python mirrors this via `HlstatsRuntime` projected `round_status` in `EventContext.extras` and `_record_team_bonus` in `storage.py`. Narrow replay (`runtime-db-diff-p6d-narrow-1000-20260427-051926.md`) still showed a large `TeamBonuses` gap (`5665` vs `41686` on the 1000 window).
- **Residual gap hypothesis → fix (2026-04-27):** narrow diff python-only rows cluster on `BOT:*` players (e.g. `Rescued_A_Hostage`) while legacy-only examples are human Steam ids. Perl `rewardTeam` (`hlstats.pl` ~570–571) skips the `TeamBonuses` insert when `IgnoreBots` and (`is_bot` or `userid <= 0`); Python previously fanned out to every active slot. **Patched:** `_skip_team_reward_for_ignore_bots` in `_reward_team_players` (plus `_player_last_user_id` tracking in `_resolve_player_id`). **Gate:** re-run dual narrow + `compare_stats_dbs.py` to confirm counts before closing LP-P6D-001.
- **SQL follow-up (read-only, when DBs are up):** on each DB, `COUNT(*)`, `MIN(id)`, `MAX(id)`; `COUNT(DISTINCT (eventTime, serverId, map, playerId, actionId, bonus))` or closest natural key; top `(actionId, map)` by count — to confirm concentration by action after the fix, not to replace the code finding above.
- **Classification:** **bug** in Python (missing legacy `round_status` gating — fixed; missing `IgnoreBots` fan-out parity in `rewardTeam` — fixed). **Do not** “accept” the historical 24× delta as product policy without post-fix replay evidence.

### `hlstats_Events_Entries` (legacy **0** vs Python **190,621**)

- **Legacy is not “schema unused”:** `doEvent_EnterGame` calls `recordEvent("Entries", …, $player->{playerid})` for **non-bot** players (`HLstats_EventHandlers.plib` ~579–585). The table is part of the normal Perl pipeline for “entered the game”.
- **Conclusion for the 161410 snapshot:** for this full replay, the legacy side produced **no** persisted `Entries` rows while Python did — **wiring / log classification mismatch** (e.g. enter-game lines not delivered to `doEvent_EnterGame` on the Perl path used in replay, or different bot/real classification), not a reason to delete the table from the schema.
- **Direction:** trace Python `EventCategory.ENTRY` (`protocol` / `events/handlers` “entry” event) vs Perl’s EnterGame routing on the same log snippets; **do not** exclude `Events_Entries` from `compare_stats_dbs` to hide a bug until this is decided (per runbook constraint).
- **Classification:** **parity gap** — treat as **P0** until either legacy is shown to intentionally skip Entries for this mode or Python’s ENTRY emission is proven legacy-equivalent.

### RC-B policy cluster — impact triage before fixes

- **Scope:** `ChangeTeam` / `Connects` / `Chat` / `PlayerActions` volume deltas are tracked under **RC-B** (dedup, `ignore_bots`, `UNASSIGNED` / empty team, `--drop-empty-team-enter-events`, ChangeTeam filter already in Python storage). Classify by impact before changing behavior; do not tune this cluster to explain `TeamBonuses +8`.

### RC-B impact triage (2026-04-29)

Current artifact:
`runtime-db-diff-p6d-narrow-1000-20260428-175918.md`.

| Group | Current narrow-1000 evidence | Classification | Decision |
| --- | --- | --- | --- |
| `hlstats_Events_ChangeTeam` | `legacy=1345`, `python=1280`; examples include name-attribution pairs for the same unique id, legacy-only `UNASSIGNED` rows, HLTV/bot-like rows, and Python's existing unresolved/bot/dedupe filters in `storage._record_team_change`. | Diagnostic backlog | Keep visible. Add `HLSTATS_PARITY_DECISION_TRACE_PATH` only if a concrete player-history, active-roster, player-count, or identity question needs it. |
| `hlstats_Events_Connects` | `legacy=992`, `python=1037` before RC-C invalid-id follow-up; the excess was the repeated `STEAM_ID_LAN` advertising identity. Current post-fix count is `992/992`. | Scoped must-fix closed | Do not change broad Connects policy from the old count. Promote only if connection history, last-address, or player-count semantics are proven wrong. |
| `hlstats_Events_Chat` | `legacy=608`, `python=663` before RC-C invalid-id follow-up; the `STEAM_ID_LAN` advertising row was removed. Current post-fix count is `608/662`; remaining examples follow player-name attribution and extra command/help chat rows. | Diagnostic backlog | Do not tune broad chat policy yet. Revisit with identity trace if visible chat attribution remains wrong beyond known name/current-name drift. |
| `hlstats_Events_PlayerActions` | `legacy=4972`, `python=6221`; python-only examples include `cstrike:amx_chat` action rows with `missing_player_id=0`, generated by server/plugin actor lines like `<><><> triggered "amx_chat"`. | Must-fix, scoped | Fix unresolved/server-origin action recording or action-counter increment first. Keep unrelated headshot/name-attribution deltas diagnostic until identity triage. |

### RC-B scoped fix follow-up (2026-04-29)

- Implemented the scoped `PlayerActions` fix in
  `scripts/hlstats_py/storage.py::_record_action`: unresolved actors with no
  victim now return before `hlstats_Events_PlayerActions` insert and
  `hlstats_Actions.count` increment.
- Regression:
  `test_record_action_skips_unresolved_server_actor_without_victim` covers
  `<><><> triggered "amx_chat"`.
- Validation:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests`
    -> `113 passed`;
  - `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
    -> success with reused legacy contour;
  - `compare_stats_dbs.py --max-examples 20` still reports residual documented
    differences, but `hlstats_Events_PlayerActions` improves from `4972` vs
    `6221` to `4972` vs `6020` before the RC-C bot slice, then to `4972` vs
    `6019` after it; `amx_chat` is absent from Python
    `hlstats_Actions` / `hlstats_Events_PlayerActions`.
- Remaining `PlayerActions` drift is now diagnostic unless RC-C identity or
  headshot/action attribution analysis promotes a narrower must-fix subset.

### RC-C identity/player-count slice (2026-04-29)

- Legacy reference checked before changing behavior:
  `HLstats_EventHandlers.plib` resolves bot player objects, but with
  `ignore_bots=1` it skips bot-owned `Frags`, `PlayerActions`, `Chat`,
  `Statsme`, and `Statsme2`; `HLstats_Player.pm` flushes ignored bot profiles
  with `skill=0` and `hideranking=1`.
- Python now applies the same scoped policy in `storage.py`: resolved bot
  profiles are hidden/reset when `IgnoreBots` is enabled, and bot-owned
  frag/action/chat/statsme rows return before event/counter writes.
- Validation:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py`
    -> `45 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests`
    -> `115 passed`;
  - `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
    -> success;
  - `compare_stats_dbs.py --max-examples 20` -> expected exit `1` with
    documented residual diffs.
- Current anchors after the fix:
  - bot profiles aligned: `bots=73`, `visible_bots=0`, `skill1000_bots=0` on
    both contours;
  - raw `Frags`, `Statsme`, and `Statsme2` counts aligned:
    `5464`, `32290`, `32290`;
  - before the transient-id follow-up below, the remaining player-count drift
    was one extra Python visible row plus human `PlayerUniqueIds` /
    `PlayerNames` / `Players_History` name-attribution examples.
- Decision at this stage: RC-C bot policy was fixed. The next narrow
  must-review subset was the extra visible human identity and its history/stats
  impact; that subset is closed in the follow-up below.

### RC-C transient-id identity follow-up (2026-04-29)

- Root cause: direct SQL identified the extra visible Python human as
  `STEAM_ID_LAN` advertising connect/chat lines for
  `en.prime-server.info BUY PLAYER` / `Boost en.Prime-server.info`
  (`54.74.101.183`). Legacy Perl `getPlayerInfo` returns these normal-mode
  invalid ids as transient info and does not create `HLstats_Player` /
  `hlstats_PlayerUniqueIds` rows for them.
- Fix: Python now skips transient `UNKNOWN`, `STEAM_ID_PENDING`,
  `STEAM_ID_LAN`, `VALVE_ID_PENDING`, and `VALVE_ID_LAN` identities for
  player-owned persistence, and stores `STEAM_[0-9]+:` unique ids in the
  canonical legacy form.
- Regression:
  `test_transient_lan_unique_id_connect_does_not_create_visible_player`,
  `test_transient_lan_unique_id_chat_does_not_create_player_or_chat`, and
  `test_steam3_unique_id_is_stored_with_legacy_canonical_form`.
- Validation:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests/test_storage.py`
    -> `48 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest -o cache_dir=.pytest-cache-local scripts/hlstats_py/tests`
    -> `118 passed`;
  - `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy`
    -> success;
  - `compare_stats_dbs.py --max-examples 20` -> expected exit `1` with
    documented residual diffs.
- Current anchors after the fix:
  - `Players 323/323`, visible players `250/250`;
  - `Connects 992/992`;
  - `STEAM_ID_LAN` unique rows `0/0`;
  - canonical `0:247752695` unique rows `1/1`;
  - `Chat 608/662`, `PlayerActions 4972/6019`;
  - `Frags 5464/5464`, `Statsme 32290/32290`, `Statsme2 32290/32290`;
  - `TeamBonuses 4765/4774`, `Entries 0/1017`.
- Decision: the player-count blocker is closed. A 2026-04-30 GeoIP backfill
  also aligned the previously noted `1:45686725` GeoIP gap (`RU/Russia` on both
  contours). Remaining RC-C identity work is diagnostic unless a narrower trace
  proves visible stats, awards, ranking, or player-history corruption.

### RC-C ignored-bot history seed follow-up (2026-04-30)

- Root cause: legacy Perl `check_history` can create ignored-bot
  `hlstats_Players_History` rows with the default history skill before
  `flushDB` reaches the ignored-bot profile branch. That branch resets
  `hlstats_Players.skill=0` / `hideranking=1` but skips the normal
  `hlstats_Players_History` update. Python was additionally mutating the
  in-memory skill cache during `_apply_ignored_bot_profile`, so later history
  row seeds used `0`.
- Fix: `_apply_ignored_bot_profile` still persists the hidden/reset bot profile
  but no longer changes the in-memory skill used for history seeds.
- Regression: `test_ignore_bots_keeps_history_seed_skill_at_legacy_default`.
- Validation: `test_storage.py -q` -> `52 passed`; full
  `scripts/hlstats_py/tests` -> `122 passed`; narrow-1000 dual contour with
  reused legacy -> success; host-side GeoIP backfill -> exit `0`;
  `compare_stats_dbs.py --max-examples 5` still exits `1` for documented
  residual diffs. Focused `Players_History` drift improved from `417/417` to
  `111/111`, Python bot history rows with `skill=0` are `0`, and
  `hlstats_Players_History` counts remain `659/659`.

### RC-C PlayerNames alias/flush attribution cluster (2026-05-06)

- Current task: `LP-P6D-004B`.
- Scope is human `PlayerNames` / `Players_History` attribution only. This does
  not reopen the closed player-count / `STEAM_ID_LAN` blocker, the closed
  `1:45686725` and `0:723234133` current-name anchors, `TeamBonuses +9`,
  `Connects`, `ChangeTeam`, broad `Chat`, or broad `PlayerActions`.
- Initial read-only SQL on the running narrow contours showed the useful
  pattern:
  - `0:1838619084` was aligned at the profile/history level
    (`lastName=X3`, kills/deaths `138/71`), but the `X3` alias row was still
    `numuses legacy=3`, Python `2`.
  - `0:36417680` (`fnat1k` family) and `0:2084898310` (`SayNor` family) had
    matching summed `PlayerNames` kills/deaths/headshots/shots/hits, but Python
    distributed those totals across alias rows differently from legacy.
  - `1:55955613` (`Rakza`) read more like a `Players_History`
    skill/current-name attribution anchor than a standalone `PlayerNames`
    split unless a narrower row example proves otherwise.
- Legacy behavior model:
  `HLstats_Player->setName()` increments `hlstats_PlayerNames.numuses` on a
  real constructor/name-change/reconnect name touch. `flushDB()` later applies
  the pending player counters to the *current* in-memory alias row and updates
  `hlstats_Players.lastName`. The stats are not attached to every event's
  textual name immediately.
- Implemented slice:
  `_update_player_rollups()` now accumulates `PlayerNames` stat deltas until a
  player/profile flush boundary instead of writing them immediately per event;
  stdin transaction commits are not profile flushes. Alias-use suppression is
  cleared on explicit name-change touches, stable-unique userid handoff, and
  disconnect/reconnect lifecycle touches.
- Validation:
  `test_storage.py -q` -> `61 passed`; targeted FTP/event/runtime/storage suite
  -> `93 passed`; narrow-1000 dual contour with reused legacy -> success;
  `compare_stats_dbs.py --max-examples 1` still exits `1` for documented
  residuals.
- Result:
  `hlstats_PlayerNames` normalized drift improved from `64/65` to `34/35`.
  `0:1838619084` (`X3`) and `0:2084898310` (`SayNor`) now align. `0:36417680`
  (`fnat1k`) now has matching per-alias stat totals, but `numuses` remains
  `legacy=106`, Python `103` across three alias-touch rows. A candidate flush
  before every explicit name change was replay-tested and rejected because it
  regressed `PlayerNames` to `64/65`; do not restore it without a narrower
  legacy object-lifecycle trace.
- Next implementation target:
  trace the remaining `fnat1k` alias-touch-only misses (`CS: zero condition`,
  `fnat1k`, `mUrkovskii`) against legacy constructor/name-change/reconnect
  object boundaries. Do not reopen profile/history totals or broad event-policy
  backlogs for this cluster.

## Root-cause clusters (Step D → E)

1. **RC-A (P0): Team bonus / entries semantics** — `Events_TeamBonuses` scale explosion and `Events_Entries` only on Python. Likely **one or two** bugs or explicit Python-only feature paths, not 18 separate issues.
2. **RC-B (P1): Event policy** — `ChangeTeam` / `Connects` / `Chat` / `PlayerActions` differences: deduplication, bot filtering, `UNASSIGNED`, connect/chat line interpretation vs `--drop-empty-team-enter-events`-class flags on legacy.
3. **RC-C (P1): Identity and aggregates** — `Players*`, `Maps_Counts`, `Weapons`, `Actions`, `Servers` reflect **remaining** frag/stats and naming after RC-A/RC-B are bounded.

## План разбора (как вести RC-A → RC-C)

Цель: не «чинить 18 таблиц», а закрыть **1–2 блокирующих** вопроса (P0) и **одну** политику событий (P1), после чего остальное классифицировать как следствие или accepted difference.

### Фаза 0 — зафиксировать контракт сравнения

- [x] Подтвердить: оба DB после replay, один `serverId`/endpoint `37.230.137.48:27015`, один и тот же ordered manifest (уже `diff_count=0`).
- [x] Не подмешивать старые артефакты UDP/throttle и пустой `...034823-retry1.md` diff.
- [x] Каноничный triage-артефакт: `runtime-db-diff-p6d-20260426-161410.md`.

**Выход (зафиксировано 2026-04-27):** triage ведётся по одному снимку `161410` при подтверждённых предусловиях handoff; не смешивать с UDP-ранами и stub-diff.

### Фаза 1 — P0: `hlstats_Events_TeamBonuses` (первый)

1. **SQL (только чтение), оба контура** — снять не только `COUNT(*)`, а распределение, чтобы поймать «шум в одной колонке»:
   - `COUNT(*)`, `MIN(id)`, `MAX(id)`, `COUNT(DISTINCT event_id|player_id|как в схеме)`.
   - Топ-5 по частоте пары/ключа, если в схеме есть `map`, `team`, `bonuscode` (уточнить по `DESCRIBE`).
2. **Код** — `rg`/поиск: где в `hlstats_py` (и при необходимости в Perl) пишутся строки в `Events_TeamBonuses` / `TeamBonuses`.
3. **Гипотезы (проверить по коду, не догадкой):** дублирование вставок на один лог-ивент, другой `INSERT` path для round-end, неверный chunk/dedup, или Python пишет то, что legacy на stdin вообще не пишет.
4. **Решение по продукту:** либо баг в рантайме, либо намеренное расхождение — тогда **зафиксировать accepted difference** в `bug-plan` + коммент в `issues.jsonl`.

**Выход:** один абзац «причина X / баг-реп / accepted» + при необходимости новая issue в `issues.jsonl`.

*Выполнено 2026-04-27:* код-аудит + числа из diff — см. § P0 triage `TeamBonuses`; optional SQL-распределения — when DBs available.*

### Фаза 2 — P0: `hlstats_Events_Entries` (ноль в legacy)

1. Убедиться: в legacy-контуре **действительно** `0` строк (один `SELECT COUNT(*)`), а не артефакт сравнения.
2. Проверить, вызывается ли заполнение этой таблицы из **Perl daemon** при replay и есть ли feature flag.
3. В Python: точка(и) `INSERT` в `Events_Entries` — сопоставить с типом лога (вход в игру, join team, `triggered` и т.д.).
4. **Решение:** «таблица не используется в legacy / deprecated» **или** «Python пишет лишнее / Perl должен писать» — зафиксировать явно; от этого зависит, сравнивать ли эту таблицу в `compare_stats_dbs` в будущем (исключение из сравнения **только** после согласования).

**Выход:** классификация: *баг* | *намеренно только в Python* | *legacy gap*; обновить README/runbook, если сравнение по этой таблице вводит в заблуждение.

*Выполнено 2026-04-27:* классификация **parity gap** (не «deprecated») — см. § P0 triage `Events_Entries`; live `SELECT COUNT(*)` на legacy при появлении БД — подтверждение 0 из diff.*

### Фаза 3 — P1: политика событий (ChangeTeam, Connects, Chat, PlayerActions)

1. Свести **числа** из diff в одну таблицу (уже в артефакте) — отношения Python/legacy.
2. Снять **образец**: 10–20 конкретных `event_time`+`player` из legacy-only `ChangeTeam` и проверить, есть ли те же сырые строки в логе и что делает Python (фильтр, дедуп, `UNASSIGNED`, боты).
3. Сверить флаги запуска: `--drop-empty-team-enter-events` (и аналоги) на **обоих** контурах; зафиксировать расхождение в командной строке, если было.
4. **Не** смешивать с P0 до явного сепарата: сначала закрыть или принять A, иначе тесты на политику будут шуметь.

**Выход:** список «legacy записывает X / Python — Y» с отсылкой к участкам кода; решение: выровнять политику **или** зафиксировать product preference.

### Фаза 4 — идентичность и агрегаты (RC-C)

- После фаз 1–3: пересчитать, какие отличия в `Players` / `PlayerNames` / `PlayerUniqueIds` / `Players_History` остаются.
- Раздельно: **`<missing-player-name>`** (отдельный мини-корневик), **гео/флаги** (если triage скажет), **BOT + hide_ranking**.

**Выход:** остаточный список P1/P2; при необходимости узкий прогон (см. фаза 5).

### Фаза 5 — узкий прогон (только по необходимости)

- Запуск **50/300/1000** логов с теми же флагами, **после** гипотезы по одному RC; не как замена full corpus, а для изоляции.
- Снова `compare_stats_dbs.py`; новый `runtime-db-diff-*.md` с датой в имени.

**Выход:** дифф «до/после» одного фикса или сужение причины.

### Фаза 6 — якорные SQL (runbook, read-only)

Когда P0 сняты или сняты в accepted: выполнить **пакетно** на обоих DB (запросы из README/parity runbook, без admin):

- `hlstats_Players` — `COUNT`, при необходимости топ по `kills` / smoke player id;
- `hlstats_Events_Frags` — `COUNT`;
- `hlstats_Maps_Counts` — несколько карт-якорей;
- `hlstats_Events_Statsme*`, `hlstats_Players_History` — как минимум counts.

**Выход:** короткий текстовый снимок в `docs/audits/.../performance.md` **или** одна вставка в `bug-plan` — на усмотрение; главное: числа, с которыми согласована страница/агенты позже.

### Когда открывать page-level audit

- После: закрыт P0 triage (или зафиксированы accepted) **и** согласована политика P1 **или** явно сказано «сравниваем только frags+statsme при текущей политике».

### Чеклист Definition of Done для разбора (не кода)

- [x] P0-таблицы объяснены (баг / accepted / out of compare list). — *TeamBonuses: bug, fix direction; Entries: parity gap, not “unused table”.*
- [x] Оставшиеся 15+ таблиц разнесены по RC-B/C с пометкой «нужен фикс» / «downstream». — *RC-B P1 policy; RC-C identity/frags after P0; см. executive summary + RC clusters.*
- [x] `bug-plan` и при необходимости `issues.jsonl` обновлены; канон diff не переписан вручную.
- [x] `docs/status.md` отражает «триаж завершён / в работе фиксы / страницы заблокированы» по факту.

---

## Next validation (Step F, optional)

- Narrow replay (50/300/1000) **only** to isolate a single RC after fixing or scoping RC-A.
- Re-run `compare_stats_dbs.py` and replace canonical diff filename in this doc.
- **Do not** start page-level parity agents until this triage is accepted or downscoped per README.

### Post-fix focused outcome (2026-04-27)

- Completed:
  - baseline clean restore on both stacks with `-ForceDumpRestore`
  - read-only anchor checks (both stacks empty pre-replay)
  - P0 code changes + targeted tests:
    - `scripts/hlstats_py/runtime.py`
    - `scripts/hlstats_py/protocol.py`
    - `scripts/hlstats_py/tests/test_runtime.py`
    - `scripts/hlstats_py/tests/test_storage.py`
    - `scripts/hlstats_py/tests/test_events.py`
  - targeted test run: `56 passed`
- Narrow-window 1000 read-only anchor counts:
  - legacy: `Players=323`, `Frags=6540`, `Players_History=659`,
    `Events_Entries=0`, `Events_TeamBonuses=5665`
  - python: `Players=326`, `Frags=7828`, `Players_History=675`,
    `Events_Entries=1231`, `Events_TeamBonuses=41686`
- Decision for P0 gate:
  - `LP-P6D-001 TeamBonuses`: narrowed to `legacy=4765`, `python=4773`
    (delta `+8`) and classified as diagnostic backlog under the acceptance
    policy unless RC-B/identity proves visible or aggregate-critical impact.
  - `LP-P6D-002 Entries`: accepted with explicit rationale; keep included in
    `compare_stats_dbs` and revisit only if RC-B/identity proves visible stats
    or awards damage.
- Remaining short list (replaces blind 18-table triage):
  1. re-check RC-C identity fallout (`Players*` / naming) after the scoped
     `PlayerActions` fix
  2. inspect remaining `PlayerActions` drift only through identity/headshot
     attribution evidence, not as a broad count chase
  3. keep `TeamBonuses +8`, `ChangeTeam`, `Connects`, and `Chat` as diagnostic
     backlog unless later evidence promotes them

## Obsolete

- Prior bug-plan text keyed to **2026-04-25 throttled / UDP** scale mismatch (e.g. Python `Players=1651`) is **superseded** by the 2026-04-26 direct-stdin run; keep old narratives out of the critical path.
