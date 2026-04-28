# P6d Bug Plan — full corpus, direct stdin (2026-04-26)

## Executive summary

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
    (`1000` window: legacy `0`, python `1231`), and compare row is kept to
    prevent silent masking.
- **Input parity:** confirmed — ordered manifests match 1:1; server identity `37.230.137.48:27015` for both contours.
- **Authoritative DB diff:** `runtime-db-diff-p6d-20260426-161410.md` (from `compare_stats_dbs.py`). Do **not** use `runtime-db-diff-p6d-20260426-034823-retry1.md` (failed/empty; see file stub in repo).
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

### P1 policy cluster (RC-B) — next fix wave after P0

- **Scope:** `ChangeTeam` / `Connects` / `Chat` / `PlayerActions` volume deltas in `runtime-db-diff-p6d-20260426-161410.md` are tracked under **RC-B** (dedup, `ignore_bots`, `UNASSIGNED` / empty team, `--drop-empty-team-enter-events`, ChangeTeam filter already in Python storage). **Do not** tune this cluster to explain `TeamBonuses` until the `round_status` (or equivalent) hypothesis is fixed or disproved on a narrow replay.

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
  - `LP-P6D-001 TeamBonuses`: **fixed (code)**, keep open as parity follow-up
    because row-scale drift persists after fix.
  - `LP-P6D-002 Entries`: **accepted with explicit rationale (temporary)**;
    keep included in `compare_stats_dbs` and revisit after RC-B policy alignment.
- Remaining short list (replaces blind 18-table triage):
  1. close residual `TeamBonuses` drift with focused action/map-level comparison
  2. align RC-B policy cluster (`ChangeTeam` / `Connects` / `Chat` / `PlayerActions`)
  3. re-check RC-C identity fallout (`Players*` / naming) after RC-B

## Obsolete

- Prior bug-plan text keyed to **2026-04-25 throttled / UDP** scale mismatch (e.g. Python `Players=1651`) is **superseded** by the 2026-04-26 direct-stdin run; keep old narratives out of the critical path.
