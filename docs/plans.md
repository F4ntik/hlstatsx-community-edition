# Plan: Standalone Python+i18n Product Lane

## Summary

This repository is the product integration lane for a standalone HLstatsX build
that combines:

- the Python runtime and operational tooling from the migration donor lane
- the explicit EN/RU web i18n runtime and page coverage from the RU donor lane

The product lane is intentionally not the same thing as either donor branch.
Its job is to stabilize the combined stack as a releasable project.

**Workspace:** implement and document here; use
`hlstatsx-community-edition/` and `hlstatsx-community-edition-web-ru-i18n/` only
as reference unless the task spans them. **Fast log replay index:**
[`docs/replay-fast-path.md`](replay-fast-path.md).

### Execution update (2026-04-25)

- Ran the post-mapfix drift-reduction stage against authoritative dump-restore
  baselines (`restore-baseline.ps1 -ForceDumpRestore` on both stacks) and
  archived results under
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/`.
- Implemented lifecycle attribution hardening (`Loading map` staging via
  `pending_map`, map switch on `Started map`) and ChangeTeam de-noise/dedupe
  in `hlstats_py`.
- Outcome:
  - window-50: targeted drift substantially reduced, especially
    `hlstats_Events_ChangeTeam`.
  - window-300: residual drift remains in `Maps_Counts`, `Actions` /
    `Events_PlayerActions`, and identity/history alignment.

### Execution update (2026-05-06)

- Continued the derived combat/reward follow-up with a narrow legacy parity
  fix: suicides now end active kill streaks before recording the suicide,
  matching `doEvent_Suicide() -> endKillStreak()` and targeting residual
  `Actions.kill_streak_*` / kill-streak `PlayerActions` timing drift without
  reopening broad event-policy differences.

- Residual parity work is now organized by cluster instead of by single
  identity anchors:
  identity/naming/encoding; derived combat/reward counters; event-policy drift;
  accepted differences.
- Two dense slices were selected because each could move multiple tables:
  ignored-bot name-change encoding/profile state and Statsme `time`/`latency`
  telemetry action writes.
- Result after successful narrow-1000 replay and fresh compare:
  `Actions` aligned on row count (`754/754`), `PlayerActions` shrank from
  `4972/6019` to `4972/4977`, `PlayerUniqueIds` disappeared from residual
  output, `PlayerNames` normalized drift shrank to `3/4`, and
  `Players_History` normalized drift shrank to `106/106`.
- Remaining dense follow-ups are derived combat/reward timing
  (`Servers.suicides`, `Actions.kill_streak_*`, kill-streak `PlayerActions`,
  `TeamBonuses`) and event-policy drift (`ChangeTeam`, `Chat`, residual
  non-derived `PlayerActions`). `Entries 0/1017` remains an accepted visible
  compare row.

- Advanced RC-C human `PlayerNames` attribution as one cluster instead of
  one-off alias fixes.
- Deferred Python `PlayerNames` stat rollups to player/profile flush boundaries
  and kept stdin transaction commits from acting as profile flushes.
- Narrow-1000 replay improved `hlstats_PlayerNames` normalized drift from
  `64/65` to `34/35`; `X3` and `SayNor` anchors now align.
- Remaining follow-up is limited to `fnat1k` alias-touch-only `numuses` misses
  (`106` vs `103`), not profile/history totals or broad event-policy drift.
- Follow-up slice added two more lifecycle-close semantics for alias reuse only:
  idle-prune cleanup and `Started map` roster reset now mark player objects as
  closed before the next same-name touch. New regressions cover reconnect after
  idle prune and reconnect after map start; targeted validation moved to
  `95 passed`.
- The earlier replay-pending note for this follow-up is superseded by the
  cluster pass above: narrow-1000 replay and fresh compare completed
  successfully after the bot-name and telemetry slices.

## Product contract

- Default runtime path:
  `proxy_daemon_py -> hlstats_py -> MySQL -> PHP web`
- Legacy Perl path:
  kept only for compatibility checks, baseline replay comparison, and
  transition tooling
- Frontend contract:
  - explicit dictionary-backed i18n
  - `lang=en|ru`
  - fallback order `GET -> cookie -> session -> en`
  - no whole-document translation rewriting

## Milestones

### [x] P1. Bootstrap the standalone product repository

Goal:
Create a separate repository with full upstream history and a dedicated
`main` branch for the integrated product line.

Tasks:
- clone the upstream history into a new local repository
- separate donor remotes from product ownership
- create a dedicated `main` branch from `upstream/master`

Definition of done:
- this repository is no longer only a worktree or donor branch mirror
- product work can proceed without polluting the Python or RU donor lanes

### [x] P2. Import the Python donor baseline

Goal:
Bring the Python runtime, replay, proxy, heatmap, and operational tooling into
the product lane from the migration donor branch.

Tasks:
- import `hlstats_py`, `proxy_daemon_py`, replay-baseline tooling, and related
  runbooks
- retain the Python-backed web/runtime compatibility changes required by that
  stack
- keep the imported Python docs as supporting references, not as the primary
  product narrative

Definition of done:
- the product repo contains the runnable Python runtime/tooling surface
- the migration donor remains a separate lane of record for Python-specific
  parity work

### [x] P3. Overlay the RU i18n donor web layer

Goal:
Apply the explicit EN/RU frontend runtime and translated page coverage from the
RU donor lane on top of the imported Python baseline.

Tasks:
- overlay the current RU donor `web/` i18n files into the product lane
- retain direct `t(...)`-style translation flow and catalog files
- keep the product repo aligned to the latest donor worktree state so the
  product lane is ahead of the upstream handoff lane rather than behind it

Definition of done:
- the product repo contains the explicit i18n runtime
- EN/RU dictionaries are present
- the visible `web/` coverage from the RU donor lane is available in the
  product lane

### [x] P4. Stabilize the integrated Python+i18n stack

Goal:
Turn the imported layers into one coherent product surface instead of two
coexisting donor snapshots.

Tasks:
- resolve any remaining overlap between Python-side `web/` changes and RU i18n
  files in favor of the product contract
- audit the integrated `web/` layer for Python-runtime assumptions and missing
  EN/RU dictionary-backed text
- keep a short list of any residual literal bridges that still need retirement

Definition of done:
- the integrated `web/` layer behaves as one product surface
- the product repo has one primary source of truth for runtime and i18n rules

### [x] P5. Close the remaining Python product backlog

Goal:
Finish the Python work required for this repo to act as a standalone product
lane rather than only a migration checkpoint.

Tasks:
- [x] document exact Python `--stdin` compatibility boundaries
- [x] port `HLStatsFTP` to Python on top of `hlstats_py.runtime --stdin` (`scripts/hlstats_ftp_py`)
- [x] port `ImportBans` to Python as a standalone maintenance CLI (`scripts/import_bans_py`)
- [x] validate the Python heatmap generator on real map-pack assets

Definition of done:
- Perl is no longer required for the common operational flows of this product
- remaining Perl usage is clearly limited to legacy comparison or optional
  compatibility paths

### [~] P6. Validate and package the product lane

Goal:
Run targeted validation against the combined Python+i18n stack and leave the
repo ready for release-style handoff.

Tasks:
- close the reviewed frontend i18n backlog before final packaging:
  - fill dictionary gaps and brittle catalog keys
  - retire raw English literals in shared helpers and frontend entrypoints
  - retire raw English literals in public page groups
  - retire raw English literals in admin, voice, and ingame page groups
- keep the replay-baseline corpus operational for large real-log checks:
  - prune disposable replay noise under `15 KB` from `scripts/replay_baseline/artifacts`
  - bootstrap the Python comparison restore with both known replay source servers
  - allow `scripts/replay_baseline/replay_python_log.py` to process a directory corpus with an explicit source server identity
- run targeted Python tests
- run targeted PHP syntax checks and EN/RU smoke checks
- verify replay and heatmap paths on the integrated repo
- keep the release-readiness checklist in `docs/test-plan.md` current

Definition of done:
- the repo can be described as a standalone Python+i18n product
- validation evidence exists for runtime, replay, and frontend behavior

### [x] P6a. Retire the reviewed frontend i18n backlog

Goal:
Convert the current RU review findings into one coherent dictionary-backed
frontend surface instead of a mixed EN/RU implementation.

Tasks:
- fix catalog/runtime issues first:
  - add missing dictionary keys such as `literal.yes`
  - remove or harden brittle translated abbreviations that look like
    interpolation tokens
  - keep EN/RU keysets aligned
- fix shared i18n leaks next:
  - `web/includes/functions.php`
  - `web/includes/functions_graph.php`
  - `web/includes/google_maps.php`
  - `web/includes/class_table.php`
  - `web/includes/class_db.php`
  - frontend/bootstrap error paths in `web/hlstats.php` and `web/ingame.php`
- fix high-visibility public routes next:
  - contents/help/search/header/footer
  - players/chat/history/profile/playerinfo/claninfo groups
  - maps/weapons/actions/roles/awards/server-load routes
  - graph/image renderers such as `show_graph.php`, `trend_graph.php`,
    `sig.php`, and heatmap/map side panels
- fix legacy secondary UI surfaces after public routes:
  - Teamspeak/Ventrilo pages and templates
  - admin shell + updater
  - `web/pages/admintasks/*`
  - `web/pages/ingame/*`
- replace repeated raw literals with catalog keys instead of one-off inline
  strings whenever the same label appears in multiple pages
- fix any syntax/runtime blocker uncovered while retiring literals
  - currently known blocker: `web/pages/ingame/motd.php`

Definition of done:
- RU mode no longer visibly falls back to English on the reviewed frontend
  routes except for explicitly accepted legacy content
- repeated UI labels come from the catalogs or shared localized helpers
- known parser/runtime blockers in reviewed frontend files are removed
- EN/RU catalogs stay aligned for the keys touched by the remediation

Validation:
- targeted syntax checks for each touched PHP file
- targeted keyset diff for `web/lang/en.php` vs `web/lang/ru.php`
- EN/RU smoke on one representative route per remediated group
- grep-based regression pass for newly introduced raw English literals in the
  touched files

Stop-and-fix rule:
- if a fix requires changing the product i18n contract
  (`GET -> cookie -> session -> en`, dictionary-backed `t(...)`, no document
  rewriting), stop and resolve that contract issue before continuing

### [x] P6b. Close the audit-confirmed residual i18n backlog

Goal:
Retire the confirmed EN leakage, bridge gaps, and runtime-quality defects found
by the distributed frontend i18n audit before final packaging.

Tasks:
- harden shared/runtime boundaries:
  - replace the ASCII-only request sanitization path in
    `web/includes/functions.php` and `web/includes/google_maps.php` with
    Unicode-safe handling
  - retire the remaining raw-English bootstrap/error paths in
    `web/hlstats.php`, `web/status.php`, `web/show_graph.php`, `web/sig.php`,
    and related shared helpers where practical without changing the product
    i18n contract
  - fix the runtime-quality defects uncovered by the audit in `web/status.php`
    and `web/includes/class_table.php`
- close the highest-risk public-page leaks:
  - move `web/pages/playerhistory.php` event descriptions out of English SQL
    text and onto render-time dictionary-backed strings
  - retire the remaining raw-English labels and fallback strings in the
    residual clan/role/map/detail screens
  - clean up the remaining auxiliary public surfaces that still render English
    UI directly:
    - `web/pages/updater.php`
    - `web/pages/profile.php`
    - `web/pages/teamspeak_query.php`
    - `web/pages/teamspeak_class.php`
  - normalize EN-only date/time or count formatting that still leaks into RU
    output
- close the highest-risk admin leaks:
  - route `web/pages/admintasks/serversettings.php` help text through
    catalog-backed keys instead of DB-sourced English descriptions
  - remove row-value fallbacks such as `Unknown` in
    `web/pages/admintasks/tools_adminevents.php`
  - retire the bridge/fallback-heavy labels and English source copy still
    embedded in:
    - `web/pages/admintasks/games.php`
    - `web/pages/admintasks/roles.php`
    - `web/pages/admintasks/teams.php`
    - `web/pages/admintasks/tools_reset.php`
    - `web/pages/admintasks/options.php`
- close the highest-risk ingame leaks:
  - localize the remaining raw-English routes and summaries in:
    - `web/pages/ingame/status.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/mapinfo.php`
    - `web/pages/ingame/weaponinfo.php`
    - `web/pages/ingame/header.php`
    - `web/pages/ingame/accuracy.php`
    - `web/pages/ingame/actions.php`
    - `web/pages/ingame/players.php`
    - `web/pages/ingame/clans.php`
  - fill the confirmed `translate_ui_literal(...)` bridge gaps for
    `Kills per Death` and `Total Connection Time`
  - reduce help-page fallback dependence where visible RU output can silently
    fall back to English
- keep EN/RU keysets aligned and refresh the focused grep list for residual
  English literals

Definition of done:
- the distributed audit findings are either fixed or explicitly recorded as
  accepted legacy surfaces
- no confirmed P1/P2 i18n leaks remain in the supported shared/public/admin/
  ingame product contour
- remaining English copy is limited to accepted technical or brand strings, or
  to explicitly out-of-scope legacy tooling

Validation:
- targeted syntax checks for every touched PHP file
- targeted keyset diff for `web/lang/en.php` vs `web/lang/ru.php`
- focused EN/RU smoke on one representative route per remediated subgroup
- grep-based confirmation that the confirmed audit literals are removed or are
  intentionally documented as exceptions

### [x] P6c. Re-validate and package after i18n remediation

Goal:
Re-run the release-style checks after the frontend i18n backlog is retired and
leave the repo ready for handoff.

Tasks:
- rerun targeted Python validation already required by this lane
- rerun targeted PHP syntax checks for every touched frontend file
- rerun EN/RU smoke on the representative public/admin/ingame routes
- rerun language persistence checks
- update `docs/status.md` and `docs/test-plan.md` with the final evidence

Definition of done:
- release-readiness evidence reflects the post-remediation frontend state
- remaining untranslated or intentionally legacy surfaces are explicitly called
  out instead of being silent regressions

### [ ] P6d. Full legacy-vs-Python product parity audit

Goal:
Run a distributed 1:1 audit against the original non-Python HLstatsX contour
and the integrated Python+i18n contour, then convert the findings into a
deduplicated bug plan.

**Execution continuation (narrow replay / runtime slice, 2026-04-27):**

- [x] P6d-P0: правки `round_status` для team-trigger наград + строгая классификация
  ENTRY; узкие окна 50/300/1000 на обоих контурах; артефакты
  `runtime-db-diff-p6d-narrow-*-20260427-*.md`; обновлены bug-plan / issues /
  performance / status.
- [~] P6d-M1 (LP-P6D-001): снять остаточный разрыв `hlstats_Events_TeamBonuses`
  (профили action/map, гейты наград игрокам, MinPlayers) до сопоставимых COUNT
  на том же narrow-окне или зафиксировать принятое отличие в issues.
- [~] P6d-M2 (RC-B): выровнять или явно принять политику объёмов
  `ChangeTeam` / `Connects` / `Chat` / `PlayerActions`.
  Current runtime sub-focus: `hlstats_Servers.act_players` legacy live-roster
  cadence remains open after the bot-cleanup pass; keep `Loading map` bot
  removal, preserve human live-roster members across `Started map`, and verify
  legacy-style idle-prune timing by replay/compare before reclassifying the
  remaining RC-B residuals.
- [ ] P6d-M3 (RC-C): повторная проверка идентичности игроков после M2.

Policy checkpoint (2026-04-29):
- `docs/parity-acceptance-policy.md` defines the P6d acceptance matrix:
  must-fix, accepted legacy difference, and diagnostic backlog.
- Current `hlstats_Events_TeamBonuses` narrow-1000 residual (`legacy=4765`,
  `python=4774`, delta `+9`) is diagnostic backlog, not a standalone blocker.
  The count reflects the corrected parity-runner Python input order
  (`--order-by-name`) and does not reopen TeamBonuses code work by itself.
- `Events_Entries legacy=0` vs `python>0` remains an accepted legacy
  difference and must stay visible in compare output; current post-RC-C
  narrow-1000 compare shows `python=1017`.
- Next technical focus is RC-B impact triage for `ChangeTeam`, `Connects`,
  `Chat`, and `PlayerActions`; identity/player count drift is must-review after
  RC-B and must-fix only where it affects visible stats, awards, ranking,
  history, or player-count semantics.

RC-B impact triage, pre-RC-C follow-up (2026-04-29):
- `ChangeTeam` (`1345` legacy vs `1280` Python): diagnostic backlog. Evidence
  at this point mixes intentional filters/dedupe with identity/name attribution
  and legacy-only `UNASSIGNED`/HLTV-style rows; no runtime change without
  visible history/player-count impact evidence.
- `Connects` (`992` legacy vs `1037` Python): diagnostic backlog. Evidence at
  this point is mostly same timestamps/IPs with different current names for the
  same unique ids plus repeated connect-line policy noise.
- `Chat` (`608` legacy vs `663` Python): diagnostic backlog. Evidence at this
  point shows visible chat attribution/name drift and extra command/help rows,
  not a standalone parser-loss proof.
- `PlayerActions` (`4972` legacy vs `6221` Python before the scoped fix):
  scoped must-fix. Python-only
  `amx_chat` rows from server/plugin actor `<><><>` are recorded with
  `playerId=0` and increment action counters; fix this unresolved/server-action
  subset before broad RC-B policy movement.

RC-B scoped fix follow-up (2026-04-29):
- Python now skips unresolved player-action rows without a victim before action
  metadata/count updates. Narrow-1000 revalidation with
  `Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore
  -ReuseValidLegacy` shows `amx_chat` no longer exists in Python
  `hlstats_Actions` and `hlstats_Events_PlayerActions`; `PlayerActions` moved
  from `4972` vs `6221` to `4972` vs `6020`, then to `4972` vs `6019` after
  the RC-C bot-policy slice.
- `TeamBonuses` stayed `4765` vs `4773`; `ChangeTeam` and `Chat` counts stayed
  diagnostic. `Connects` was later closed for the scoped player-count subset by
  the RC-C transient-id follow-up (`992/992`). Next useful slice is RC-C
  identity/player-count review, with remaining `PlayerActions` drift treated as
  diagnostic unless identity/headshot evidence promotes a narrow subset.

RC-C identity/player-count slice (2026-04-29):
- Legacy Perl evidence: with `IgnoreBots=1`, bot profiles are kept but flushed
  hidden/unranked (`skill=0`, `hideranking=1`), and bot-owned
  `Frags` / `PlayerActions` / `Chat` / `Statsme` / `Statsme2` are not recorded.
- Python now applies that same scoped bot policy in storage. Tests:
  `test_ignore_bots_marks_bot_hidden_and_skips_chat`,
  `test_ignore_bots_skips_frag_when_bot_participates`; full
  `scripts/hlstats_py/tests` -> `115 passed`.
- Replay/compare after the fix:
  - bot profiles aligned: `bots=73`, `visible_bots=0`, `skill1000_bots=0` on
    both legacy and Python;
  - raw `Frags`, `Statsme`, and `Statsme2` row counts aligned
    (`5464`, `32290`, `32290`);
  - follow-up identified the extra visible Python human row as a repeated
    legacy-invalid `STEAM_ID_LAN` advertising identity. Python now skips
    transient `UNKNOWN` / pending / LAN unique ids for player-owned persistence
    and canonicalizes `STEAM_[0-9]+:` unique ids to the legacy form.
  - current post-follow-up anchors: `Players 323/323`, visible players
    `250/250`, `Connects 992/992`, `Chat 608/662`, `PlayerActions 4972/6019`,
    `Frags 5464/5464`, `Statsme 32290/32290`, `Statsme2 32290/32290`,
    `TeamBonuses 4765/4773`, `Entries 0/1017`.
- Next narrow must-review subset: remaining `PlayerUniqueIds` / `PlayerNames` /
  `Players_History` name/current-name and GeoIP attribution drift. Do not touch
  `TeamBonuses +8`, `ChangeTeam`, closed `Connects`, or broad `Chat` policy
  without new visible-impact evidence.

RC-C review follow-up (2026-04-29):
- Closed two code-review issues in the bot-policy slice:
  - action filtering now checks both actor and victim before
    `PlayerPlayerActions` / action-counter writes on `IgnoreBots=1` servers;
  - stdin rollback now clears the ignored-bot profile application cache so
    rolled-back `skill=0` / `hideranking=1` updates can be reapplied.
- Regression coverage:
  `test_ignore_bots_skips_action_when_target_is_bot` and
  `test_ignored_bot_profile_cache_is_cleared_on_rollback`.
- Validation: `test_storage.py -q` -> `50 passed`; full
  `scripts/hlstats_py/tests` -> `120 passed`; narrow-1000 dual contour with
  reused legacy succeeded, and compare still exits `1` only for documented
  residual diffs. Anchors stayed stable, including `Players 323/323`,
  `PlayerActions 4972/6019`, `PlayerPlayerActions 0/0`, and
  `TeamBonuses 4765/4773`.

RC-C current-name follow-up (2026-04-29):
- The next identity/name slice is scoped to `hlstats_Players.lastName`
  attribution, starting from the `uniqueId=1:45686725` anchor where aggregate
  kills/deaths match but legacy current name stays one profile flush behind
  Python.
- Python now mirrors the legacy shape more closely for profile names:
  `hlstats_PlayerNames` remains immediate, while `hlstats_Players.lastName`
  writes are deferred until disconnect/profile flush instead of every player
  resolve. This is intended to reduce current-name drift without changing
  player counts, event counts, or broad Chat/Connect policy.
- Unit validation for the storage slice passed (`test_storage.py -q` ->
  `51 passed`).
- Follow-up validation on 2026-04-30 passed:
  - full `scripts/hlstats_py/tests` with pytest cache disabled and basetemp
    outside the locked repo temp dirs -> `121 passed`;
  - narrow-1000 dual contour with `-UseDumpRestore -ReuseValidLegacy` ->
    success;
  - `compare_stats_dbs.py --max-examples 20` still exits `1` for documented
    residual diffs.
- Direct SQL confirms the `uniqueId=1:45686725` current-name anchor is now
  aligned (`lastName=Mep3ocTb`, kills/deaths `198/179` in both contours, same
  three aliases). A follow-up GeoIP backfill run on 2026-04-30 also aligned
  that row's GeoIP (`RU/Russia`, `lastAddress=178.68.210.14`) on both contours,
  so the next RC-C work should focus on broader remaining `PlayerUniqueIds` /
  `PlayerNames` / `Players_History` attribution drift.
- A 2026-04-30 ignored-bot history follow-up closed one broader
  `Players_History` artifact without reopening player counts or bot visibility:
  Python keeps the persisted ignored-bot profile reset (`skill=0`,
  `hideranking=1`) but no longer seeds history rows from that reset value.
  Narrow-1000 focused compare improved `hlstats_Players_History` normalized
  drift from `417/417` to `111/111`; remaining history examples are human
  skill/streak/name attribution drift, not bot hidden-profile rows.
- A 2026-05-01 current-name flush follow-up closed another scoped attribution
  gap in the deferred-name slice. Legacy periodic/shutdown `flushDB` pushes the
  current profile name for live players even when no disconnect line appears;
  Python now mirrors that import-tail behavior by flushing all cached profile
  names from `finalize_import()` before the final `last_event` update. Targeted
  validation for the storage/decision surface passed (`60 passed`), full
  `scripts/hlstats_py/tests` passed (`126 passed`), and narrow-1000 replay with
  reused legacy plus GeoIP backfill completed. Compare still exits `1` for
  documented residual tables, with focused identity drift now at
  `PlayerUniqueIds 1/1`, `PlayerNames 45/36`, and `Players_History 110/110`.
  Remaining RC-C work is still broader human `PlayerNames` / `Players_History`
  stat/name attribution, not player-count, transient-id, GeoIP, or ignored-bot
  history policy.
- A later 2026-05-01 local TDD follow-up closed a second current-name gap in
  the same area: name-change log lines were parsed but handled as generic admin
  events, so Python did not apply the `"changed name to"` target name to
  `hlstats_PlayerNames` or the deferred `hlstats_Players.lastName` cache. The
  storage path now applies `change_name` updates to the new alias/current-name
  cache without incrementing the old alias for already-known live players,
  matching the relevant Perl `doEvent_ChangeName` / `setName(newname)` shape.
  This is expected to help anchors like `0:723234133` where alias counters were
  aligned but current profile name still lagged. Replay validation is covered
  by the 2026-05-05 follow-up below.
- A 2026-05-05 replay follow-up closed that `0:723234133` anchor after
  checking the legacy Perl event path again. The remaining replay mismatch was
  parity-runner input order: Python FTP imported eligible logs by modification
  time, while the validated legacy narrow window is the first `1000` sorted log
  filenames. `hlstats_ftp_py` now has `--order-by-name`, and the dual-contour
  parity runner passes it only for replay validation; production/default FTP
  behavior remains mtime-ordered. Clean replay plus GeoIP backfill now shows
  `lastName=Райымбек Гослинг`, kills/deaths `3/4`, `KZ/Kazakhstan`, and aliases
  `Player=2`, `Райымбек Гослинг=2` on the Python contour. Current compare still
  exits `1` for `11` documented residual tables: focused identity drift is now
  `PlayerUniqueIds 31/31`, `PlayerNames 64/65`, `Players_History 195/195`, and
  `TeamBonuses 4765/4774` remains diagnostic backlog under the acceptance
  policy.

Tasks:
- clear the current legacy full-corpus replay blocker before any DB/page
  conclusions:
  - restore `-Stack legacy` cleanly before each retry
  - rerun the retained corpus with the patched
    `scripts/replay_baseline/replay_legacy_log.py`
  - if it fails again around `L0107052` / `L0107054`, rerun a narrowed
    failure-window corpus with `--daemon-output inherit`
  - capture Perl daemon stderr, helper summary, and DB counts in
    `docs/audits/legacy-python-parity-20260423/performance.md`
  - classify the root cause as helper pipe handling, daemon crash/limit,
    malformed/corpus-specific input, Docker/runtime resource issue, or
    accepted legacy limitation
- prepare both comparison contours from the same baseline:
  - legacy reference on `http://127.0.0.1:8181/hlstats.php`
  - Python/current target on `http://127.0.0.1:8281/hlstats.php`
  - `37.230.137.48:27015` seeded in both databases as `game='cstrike'`
- replay the same retained corpus into both contours:
  - use the existing Python directory replay helper for the Python contour
  - add or verify an equivalent streaming directory replay path for the legacy
    daemon before using full-corpus results as the reference
- capture runtime parity first:
  - replay wall time and throughput
  - final DB row counts and server counters
  - `scripts/replay_baseline/compare_stats_dbs.py` output
- launch mini-agent page audits in independent route groups:
  - public overview and list routes
  - player and clan details
  - maps, weapons, actions, roles, and awards
  - communication, search, help, live, and voice routes
  - admin read-only routes
  - ingame routes
  - graph/image/static renderers
  - runtime/DB parity
- record every finding in
  `docs/audits/legacy-python-parity-20260423/issues.jsonl` with route,
  expected/actual behavior, evidence, severity, and repro steps
- merge mini-agent reports into a final bug plan grouped by root cause:
  Python parser/runtime, DB/bootstrap/config, web route logic, i18n leak,
  accepted legacy difference, or test/tooling gap

Definition of done:
- both contours were restored from the same baseline and replayed with the
  same retained corpus, or any blocker is explicitly logged
- `docs/audits/legacy-python-parity-20260423/` contains the runbook, route
  inventory, runtime diff/performance notes, mini-agent reports, raw issues,
  and the final bug plan
- every page-audit issue is reproducible from a URL, SQL query, screenshot, or
  container log excerpt
- accepted legacy differences are separated from actionable bugs
- the resulting bug plan is ordered by severity and dependency

Validation:
- `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy`
- `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python`
- full-corpus replay command for each contour, recorded with elapsed time
- `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
- HTTP smoke for every route group on both `8181` and `8281`
- RU smoke on the Python/current contour with `lang=ru`
- targeted `php -l` only if an audited route exposes a PHP parse/runtime error

Known risks:
- first full legacy retained-corpus attempt failed after `1097` files through
  `L0107052.log` with `[Errno 22] Invalid argument`; the partial DB is invalid
  for parity conclusions until the failure is investigated and a clean full
  replay completes
- page-level parity can be misleading if DB/runtime parity has not been
  captured first
- destructive admin tools must remain read-only during the audit
- legacy web is not the RU i18n reference; RU validation is data parity plus
  localized current UI checks

Stop-and-fix rule:
- if the legacy reference cannot replay the same corpus cleanly, stop the
  page audit and fix/reference-log that baseline issue first
- if a full legacy replay exits without a final `Replay summary`, discard the
  partial DB, document the failed attempt, restore cleanly, and investigate the
  daemon/helper failure before running `compare_stats_dbs.py`
- if a route triggers destructive state changes, do not execute it; log it as
  read-only-only and continue

### [x] P6e. Runtime/Awards architecture modernization with strict legacy parity

Goal:
Deliver strict behavioral parity for replay-critical map flow, awards/ribbons,
and GeoIP outcomes while modernizing Python architecture around explicit
runtime state, policy-driven behavior, and replaceable service adapters.

Scope:
- `scripts/hlstats_py/*` runtime parse/dispatch/state/storage boundary
- `scripts/hlstats_awards_py/*` policy, query composition, and GeoIP execution
- replay-baseline validation commands and DB parity evidence

Non-goals:
- broad SQL schema changes
- unrelated frontend or i18n work
- changes to legacy Perl reference behavior

Design constraints:
- preserve default production behavior unless an explicit replay mode/policy is enabled
- keep parity-critical behavior deterministic and testable from fixtures
- separate domain decisions (state/policy) from I/O adapters (DB/GeoIP)

Tasks:
- implement an explicit runtime server state projection for `hlstats_py`:
  - add a typed state model per server (`current_map`, map phase, map metadata)
  - project parsed map lifecycle events (`Loading map`, `Started map`) into state
  - remove reliance on static startup-only `current_map` for replay processing
- align parser/dispatcher map semantics with legacy:
  - parse map lifecycle lines as first-class events instead of generic-only messages
  - ensure map transition ordering is deterministic before subsequent gameplay events
  - retain legacy-compatible handling for non-map world triggers
- refactor event persistence boundaries in `hlstats_py`:
  - pass resolved map from projected state into writes for `hlstats_Events_*`
  - guarantee `hlstats_Maps_Counts` uses resolved active map
  - keep storage layer focused on persistence, not map inference
- add policy-driven behavior in `hlstats_awards_py`:
  - introduce a policy abstraction for player visibility (`hideranking`) and operational strictness
  - provide a legacy-default strict policy and a replay-safe policy
  - expose replay policy via explicit CLI flag (no hidden behavior change)
- decouple GeoIP execution from awards critical path:
  - introduce GeoIP resolver/service abstraction (binary DB, SQL DB, no-op)
  - enforce strict failure only in strict policy; in replay policy degrade to warning + skip
  - keep awards/ribbons processing successful when GeoIP prerequisites are absent in replay mode
- harden regression and parity tests:
  - add parser/handler tests for `Loading map` and `Started map`
  - add runtime/storage tests confirming non-empty map writes after map transitions
  - add awards tests for replay policy behavior without manual `hideranking` SQL edits
  - add GeoIP tests for strict vs best-effort behavior
- execute replay-baseline validation and capture parity evidence:
  - run contour replay pipeline with updated Python runtime
  - run awards pipeline in replay-safe mode
  - collect SQL confirmations for maps, awards, ribbons, and optional flags

Definition of done:
- map values are non-empty in replay-critical event tables where legacy emits map context
- `hlstats_Maps_Counts` aggregates by real map names under replay
- awards/ribbons can be produced in replay flow without manual `hideranking` mass updates
- GeoIP absence no longer aborts replay awards pipeline when replay policy is enabled
- strict/default mode remains legacy-compatible and unchanged by default
- parity evidence is documented with command outputs and SQL checks

Validation:
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 100`
- `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
- optional GeoIP replay-safe check:
  - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
- SQL checks:
  - non-empty map in `hlstats_Events_Frags`
  - map population in `hlstats_Maps_Counts` (e.g. `de_dust2`, `de_nuke`)
  - positive row counts in `hlstats_Players_Awards` and `hlstats_Players_Ribbons`
  - if GeoIP data source exists: positive `flag/country` fill count

Execution evidence (2026-04-25):
- Replay contour import (`MaxImportFiles=100`) completed with exit `0` on the Python comparison stack.
- `Run-ContourFtpArtifacts.ps1` no longer flakes on FTP state cleanup:
  - replaced the cleanup pipe with an explicit safe removal loop in
    `scripts/replay_baseline/comparison/python/Run-ContourFtpArtifacts.ps1`
  - stable end-to-end run confirmed with
    `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 100`
    and exit `0`
  - canonical script stdout summary:
    - `status=ok`
    - `import_mode=ftp-stdin`
    - `server_identity=37.230.137.48:27015`
    - `max_import_files=100`
    - `ftp_probe_limit=500`
    - `geoip_mode=strict`
- Replay-safe awards runs completed with exit `0` for both:
  - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
  - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
- Strict/default behavior sanity check completed with exit `0` for both:
  - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
  - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
- SQL evidence captured on `hlstatsx-python-db`:
  - `hlstats_Events_Frags` non-empty `map`: `6536`
  - `hlstats_Events_PlayerActions` non-empty `map`: `6838`
  - `hlstats_Events_Statsme` non-empty `map`: `40047`
  - `hlstats_Maps_Counts`: `de_dust2 -> kills=1013`, `de_nuke -> kills=27`
  - `hlstats_Players_Awards`: `4`; `hlstats_Players_Ribbons`: `4`
  - GeoIP fill (`hlstats_Players` with non-empty `country` and `flag`): `148`

Stop-and-fix rule:
- if strict/default policy behavior changes unexpectedly in non-replay runs, stop and restore compatibility before continuing
- if replay map flow still emits dominant empty-map rows, stop and compare parser+projection traces against legacy event sequence
- if replay awards still require manual `hideranking` SQL intervention, stop and fix policy/query path before any broader refactor

## Out of scope for this lane

- upstreaming the Python migration into `A1mDev/hlstatsx-community-edition`
- broad SQL refactors that are not required by the product contract
- translating DB content
- adding more locales before EN/RU is fully stable
