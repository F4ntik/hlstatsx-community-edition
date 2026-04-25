# Plan: Standalone Python+i18n Product Lane

## Summary

This repository is the product integration lane for a standalone HLstatsX build
that combines:

- the Python runtime and operational tooling from the migration donor lane
- the explicit EN/RU web i18n runtime and page coverage from the RU donor lane

The product lane is intentionally not the same thing as either donor branch.
Its job is to stabilize the combined stack as a releasable project.

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

### [ ] P5. Close the remaining Python product backlog

Goal:
Finish the Python work required for this repo to act as a standalone product
lane rather than only a migration checkpoint.

Tasks:
- document exact Python `--stdin` compatibility boundaries
- [x] port `HLStatsFTP` to Python on top of `hlstats_py.runtime --stdin` (`scripts/hlstats_ftp_py`)
- port `ImportBans` to Python as a standalone maintenance CLI
- validate the Python heatmap generator on real map-pack assets

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

### [ ] P6e. Runtime/Awards architecture modernization with strict legacy parity

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
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 500`
- `python -m hlstats_awards_py --date 2026-01-04 -a -r --replay-mode`
- optional GeoIP replay-safe check:
  - `python -m hlstats_awards_py --date 2026-01-04 -a -r -g --replay-mode`
- SQL checks:
  - non-empty map in `hlstats_Events_Frags`
  - map population in `hlstats_Maps_Counts` (e.g. `de_dust2`, `de_nuke`)
  - positive row counts in `hlstats_Players_Awards` and `hlstats_Players_Ribbons`
  - if GeoIP data source exists: positive `flag/country` fill count

Stop-and-fix rule:
- if strict/default policy behavior changes unexpectedly in non-replay runs, stop and restore compatibility before continuing
- if replay map flow still emits dominant empty-map rows, stop and compare parser+projection traces against legacy event sequence
- if replay awards still require manual `hideranking` SQL intervention, stop and fix policy/query path before any broader refactor

## Out of scope for this lane

- upstreaming the Python migration into `A1mDev/hlstatsx-community-edition`
- broad SQL refactors that are not required by the product contract
- translating DB content
- adding more locales before EN/RU is fully stable
