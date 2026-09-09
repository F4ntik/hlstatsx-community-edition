# Plan: Standalone Python+i18n Product Lane

## Summary

September release integration is described in
[release preparation](release-preparation-20260909.md). Use the separate
[install and upgrade packages](release-install-upgrade.md); existing image and
calibration pairs must remain together during an upgrade.

Bundled geometry follow-up: 25 BSP templates now load automatically in the admin
editor with image-identity matching and a show/hide button. Files are included
under `web/hlstatsimg/heatmap-geometry/cstrike` for ordinary clean installations.

Completed local map refresh: `docs/plans/2026-09-08-steam-map-refresh.md`.
All 25 installed maps with overviews have current images and BSP-derived settings.
See `docs/heatmap-bsp-registration.md` for repeatable preparation and web import.

Current web-settings follow-up: `docs/plans/2026-09-08-heatmap-floor-editor.md`.
Floor and wall configuration is available in the admin UI, including JPEG upload.

Latest heatmap follow-up: `docs/plans/2026-09-08-heatmap-usability-and-regions.md`
and `docs/heatmap-regions-and-scale.md`. User-requested BSP revision tracking
exclusion remains in effect; spatial regions do not imply BSP walkability.

This repository is the product integration lane for a standalone HLstatsX
build that combines:

- the Python runtime and operational tooling from the migration donor lane
- the explicit EN/RU web i18n runtime and page coverage from the RU donor lane

The product lane is intentionally not the same thing as either donor branch.
Its job is to stabilize the combined stack as a releasable project.

Implement and document here. Use
`hlstatsx-community-edition/` and
`hlstatsx-community-edition-web-ru-i18n/` only as read-only reference unless a
task explicitly spans them.

Documentation map:

- use [`docs/README.md`](README.md) to distinguish canonical runbooks from
  historical notes;
- when documents disagree, prefer `docs/status.md`, `docs/plans.md`,
  `docs/test-plan.md`, and `docs/release-readiness.md`.

Canonical runbooks:

- replay mechanics and fast-path guidance:
  [`docs/replay-fast-path.md`](replay-fast-path.md)
- first-divergence workflow for a completed full-corpus legacy/Python replay:
  [`docs/full-corpus-first-divergence.md`](full-corpus-first-divergence.md)
- parity debug workflow for narrow residuals:
  [`docs/parity-debug-pipeline.md`](parity-debug-pipeline.md)
- audit evidence and bug triage:
  [`docs/audits/legacy-python-parity-20260423/README.md`](audits/legacy-python-parity-20260423/README.md)
- release-readiness metrics, profiling, artifact, and deployment handoff:
  [`docs/release-readiness.md`](release-readiness.md)

Historical autonomy follow-up context:

- if the task needs the rationale behind the completed autonomy phases, read
  these in order after `docs/status.md`:
  [`docs/autonomy-review-20260601.md`](autonomy-review-20260601.md),
  [`docs/autonomy-work-plan-20260601.md`](autonomy-work-plan-20260601.md)
- the autonomy work plan starts with doc-truth synchronization, then CI
  expansion, then package/runtime boundary work; do not reopen the stale
  `_ensure_connection()` bugfix path unless fresh evidence contradicts the
  current code/tests

## Product contract

- Default runtime path:
  `proxy_daemon_py -> hlstats_py -> MySQL -> PHP web`
- Release identity:
  publish the product line as `hlstatsx_py` while keeping the Python import
  path as `hlstats_py`
- Legacy reference path:
  Perl runtime scripts are no longer part of the local production runtime.
  Legacy behavior is retained through replay/parity reference tooling and
  sibling donor checkout context.
- Frontend contract:
  - explicit dictionary-backed i18n
  - `lang=en|ru`
  - fallback order `GET -> cookie -> session -> en`
  - no whole-document translation rewriting

## Current focus

- Complete BSP-backed projection diagnostics and Smooth / Cells / Points
  presentation in the Explorer worktree. Current follow-up and verification:
  [`2026-09-07-heatmap-bsp-and-presentation.md`](plans/2026-09-07-heatmap-bsp-and-presentation.md).
  The September 2 provisional GoldSrc numeric candidate is superseded by the
  SDK/BSP-derived transform; do not reuse its ZOOM-as-scale assumption.

- Keep the repo release-clean as the integrated Python+i18n product lane.
- Keep administrator mutations behind the shared session CSRF and task access
  boundary. Retain `web/updater/` only for `scripts/run_web_updater.php`; use
  [`web_updater_runbook.md`](web_updater_runbook.md) for its explicit database
  prerequisite and maintenance sequence.
- Keep the closed/accepted legacy-vs-Python parity state current without
  reopening stale `Entries`, `ChangeTeam`, `PlayerNames`, `Players_History`, or
  `TeamBonuses` residuals.
- Keep replay, compare, and representative EN/RU smoke checks runnable without
  duplicating their runbooks across multiple docs.
- Retain the narrow stdin-only `Players_History` ensure-row cache validated by
  `performance-db-sql-opt-20260718-sql-write-opt-r1`; do not broaden it to the
  online runtime. The next SQL candidate needs a separate flush-boundary and
  error-semantics investigation.
- Continue the heatmap upgrade on the hybrid path: DB-backed canvas overlay in
  web, static JPEG compatibility fallback, player-scoped kill/death widgets,
  and per-map projection calibration from overview seeds plus DB-first manual
  diagnostics.
- Modern Heatmap Explorer implementation and all 12 planned gates, plus the
  2026-09-02 sparse-layer visibility correction, are complete for exact commit
  `44f3af97db46107f3ab9b595b3c32b3e5c2c7986`. Source, disposable coordinates,
  MyISAM install/update/performance, public EN/RU browser, objective
  Color/Mono/Difference pixel visibility, authenticated admin, accessibility/
  fallback/rollback, cache identity, independent review, and exact restoration
  are accepted on the tested local stack. Use
  `docs/audits/modern-heatmap-explorer/runtime-acceptance.md` as the current
  truth. Remaining work is operational promotion through mode 0, migration
  readback, mode 1 observation and production monitoring; no production
  deployment, publication, or release acceptance is claimed.
- The September 9 candidate uses separate fresh-install and upgrade packages;
  see `docs/release-install-upgrade.md`. Fresh installs include the September 8
  native maps and matching seeds. Upgrades preserve installed images and their
  calibration. Local acquisition tools stay outside the distribution. Historical
  acceptance at `44f3af9` does not accept this combined candidate.
- The autonomy/release-readiness follow-up through Phase 9 is complete for the
  current scope. For release-candidate preparation, use
  [`docs/release-readiness.md`](release-readiness.md) and update
  `docs/status.md` with fresh evidence.
- Use a legacy-first, subagent-assisted debug loop for parity changes: inspect
  the Perl algorithm before changing Python, reduce each residual to a
  single-log/window case, add a regression test, rerun the same replay, and
  only then broaden validation.

## Execution protocol

- Work language:
  use English internally for technical analysis and code/doc identifiers, but
  answer the user in Russian unless the user explicitly asks for another
  language. Keep repository docs in the existing document language.
- Challenge inefficient or risky directions:
  if a requested path would waste replay time, context, or compute, or would
  weaken parity/i18n guarantees, state the better path and use it unless the
  task explicitly requires the original route.
- Prefer the smallest reliable evidence loop:
  read `docs/status.md`, `docs/plans.md`, and the relevant runbook; inspect the
  legacy Perl rule; reproduce a single log or narrow window; add a focused
  regression test; change Python; rerun the same small contour; broaden only
  after the narrow evidence is stable.
- After a point parity fix, the fast single-log compare must include the
  automatic `30` lines before / `30` lines after guard-window pass when a safe
  event anchor is available. Treat failures there as a sign that the fix is too
  narrow or overfit to one exact line.
- Treat full `narrow-1000`, Docker rebuilds, maintenance, DB compare, and web
  smoke as promotion gates, not first-line debugging tools. Raw replay compare
  can show an accepted GeoIP-only `hlstats_Players` diff because stdin replay
  does not run maintenance backfill; release-clean parity uses the canonical
  dual runner's shared inactive/awards/ribbons/GeoIP maintenance receipt.
- Keep context compact:
  summarize findings, link audit notes, avoid pasting long command transcripts,
  and store detailed SQL/replay evidence under
  `docs/audits/legacy-python-parity-20260423/`.
- Before starting any non-trivial parity fix, run a read-only legacy-analysis
  subagent against the Perl code path to identify how legacy implements the
  behavior, including relevant files/functions and lifecycle rules. Verify that
  conclusion locally before changing Python.
- Use additional subagents only when the task is independent and read-only,
  such as artifact grouping. Verify their conclusions locally before changing
  code.
- Do not chase every diff as a bug. Classify each residual as fixed, accepted,
  diagnostic backlog, or active visible-product drift using
  [`docs/parity-acceptance-policy.md`](parity-acceptance-policy.md).
- Keep changes in this product lane by default. Donor repositories are
  reference sources unless a task explicitly spans them.

## Migration Roadmap

- Finish the legacy Perl to modern Python migration with matching runtime and
  database results for the supported replay contour.
- Keep the modern code lightweight and maintainable while preserving explicit
  EN/RU i18n behavior.
- After stable parity, refactor without regressions and improve the modern
  architecture around runtime boundaries, storage decisions, and replay
  tooling.
- Optimize event processing, daily rewards, weekly rewards, and heatmap
  generation/publishing after correctness is locked.
- Evaluate new product capabilities only when they are realistically
  implementable and do not weaken parity, i18n, or the test pipeline.

## Milestones

### [x] P1. Bootstrap the standalone product repository

Outcome:
The product lane is a separate repository with its own history and ownership
boundary.

### [x] P2. Import the Python donor baseline

Outcome:
`hlstats_py`, `proxy_daemon_py`, replay tooling, and related operational
surface are imported into this product lane.

### [x] P3. Overlay the RU i18n donor web layer

Outcome:
The integrated product lane contains the explicit EN/RU runtime and translated
web coverage from the RU donor lane.

### [x] P4. Stabilize the integrated Python+i18n stack

Outcome:
The merged runtime and web layer now follow one product contract instead of
two parallel donor implementations.

### [x] P5. Close the remaining Python product backlog

Outcome:
Common maintenance flows no longer depend on Perl. Remaining Perl usage is
limited to parity comparison and optional legacy validation paths.

### [~] P6. Validate and package the product lane

Goal:
Keep targeted validation current and leave the repo ready for release-style
handoff once parity gates are either closed or explicitly accepted.

Current scope:

- keep the replay-baseline corpus and comparison restore path operational
- run targeted Python checks after parity/runtime changes
- run targeted PHP syntax checks and representative EN/RU smoke checks when
  frontend/runtime changes affect visible routes
- keep release-readiness evidence in `docs/status.md` and `docs/test-plan.md`
  current without duplicating audit history
- keep replay evidence attributable: canonical `ArtifactLabel` values,
  unique `EvidenceRunId`, final selected input manifests, same-run ignored/drop
  manifests, and explicit no-overwrite behavior
- keep heatmap projection changes behind the source-ready/runtime-accepted
  boundary; rotate migration requires distribution inspection, backup, and a
  separate runtime gate. The 2026-07-18 runtime gate is accepted: the guarded
  migration advanced the version marker from `1` to `2`, retained the
  `{0:442}` distribution and all replay anchors, and passed one-map browser,
  canvas-toggle, and static-JPEG acceptance. The verified pre-migration backup
  and preserved full-41513 databases are recorded in the parity audit.

Definition of done:

- the repo can be described as a standalone Python+i18n product lane
- validation evidence exists for runtime, replay, frontend behavior, and the
  remaining accepted parity differences
- release-readiness has an explicit metrics/profiling/checklist handoff and
  CI artifact path for retained evidence

### [x] P6a. Retire the reviewed frontend i18n backlog

Outcome:
The reviewed shared, public, admin, voice, and ingame EN/RU leaks were
remediated or explicitly bounded.

### [x] P6b. Close the audit-confirmed residual i18n backlog

Outcome:
The confirmed frontend i18n leaks and runtime-quality defects from the audit
were retired for the supported product contour.

### [x] P6c. Re-validate and package after i18n remediation

Outcome:
Release-style frontend and language-persistence revalidation was completed for
the remediated product contour. A supplemental 2026-07-26 sweep also closed
remaining visible English fallbacks in standalone error paths, TeamSpeak,
heatmap/hitbox controls, graph summaries, and shared JavaScript widgets. EN/RU
now have the same 1117 message keys and placeholder sets.

### [x] P6d. Full legacy-vs-Python product parity audit

Goal:
Run a 1:1 audit against the original non-Python HLstatsX contour and the
integrated Python+i18n contour, then convert differences into fixed behavior or
explicit accepted differences.

Current gates:

- `[x] P6d-M1 (LP-P6D-001)`: `hlstats_Events_TeamBonuses` is clean in the
  current full `narrow-1000` contour and direct stable-key SQL.
- `[x] P6d-M2 (RC-B)`: `ChangeTeam`, `Connects`, `Chat`, and `PlayerActions`
  no longer appear in the current full `narrow-1000` logical compare.
- `[x] P6d-M3 (RC-C)`: `hlstats_Events_Entries` is confirmed on the current
  narrow contour/default Python path. The narrow replay compare reports
  `legacy=0`, `python=0`, and `hlstats_Events_Entries` no longer appears in the
  logical compare.
- `[x] P6d-M4`: `hlstats_Players` is classified as a closed GeoIP-only
  contour/policy rule. Raw replay compare can show `250/250` `country`/`flag`
  rows because stdin replay writes `lastAddress` but does not run maintenance
  GeoIP backfill. Release-clean parity invokes the canonical dual runner's
  shared maintenance receipt, after which `hlstats_Players` should disappear
  from the compare.
- `[x] P6d-M5`: `hlstats_Events_ChangeTeam` is closed after the second TDD fix
  and narrow-1000 replay/compare. The final compare had no
  `hlstats_Events_ChangeTeam` residual; SQL anchors were `legacy
  total=1345/unassigned=47` and `python total=1345/unassigned=47`.

Current working rules:

- Do not reopen `Entries`, `ChangeTeam`, `PlayerNames`, `Players_History`, or
  `TeamBonuses` without fresh focused evidence.
- Before starting any non-trivial new parity fix, use a read-only subagent to
  inspect and document how the legacy Perl code implements the behavior.
- Treat legacy as a reference, not an oracle: verify whether the legacy trace
  is internally consistent before calling a Python row a regression.
- Use single-log and narrow-window replay before another broad contour run.
- For any fresh contour, verify the evidence inventory before pairing artifacts;
  a filename ending in `-1000` is not sufficient to establish narrow-1000.
- Accept a replay contour only after input manifests, ignored/drop manifests,
  contour metadata, snapshots, and stable-key SQL drift all agree.
- The fresh `full-41513` run is retained as diagnostic evidence: its input
  manifests and parser artifacts are valid, but its broad stable-key residuals
  are not promoted into the supported narrow-1000 acceptance gate. Use the
  full-corpus runbook for any follow-up prefix/window localization.
- After a point fix, inspect the automatic `30/30` guard-window parity rerun
  from `Run-SingleLogParity.ps1` before promoting the fix.
- Separate raw replay GeoIP-only player differences from real
  stats/session/alias drift before touching attribution logic.
- keep detailed compare counts, replay transcripts, and slice-by-slice triage
  in `docs/audits/legacy-python-parity-20260423/`, not in this plan
- keep the acceptance matrix in
  [`docs/parity-acceptance-policy.md`](parity-acceptance-policy.md)

Definition of done:

- every remaining runtime/database difference is either fixed, accepted, or
  downgraded to documented diagnostic backlog
- the audit folder contains reproducible evidence, current bug grouping, and
  acceptance notes
- `docs/status.md` can summarize the remaining open parity work without
  replaying the full investigation history

Validation:

- targeted `pytest` for touched Python runtime/storage paths
- narrow replay and compare loop from
  [`docs/replay-fast-path.md`](replay-fast-path.md)
- parity triage and evidence updates in
  [`docs/audits/legacy-python-parity-20260423/`](audits/legacy-python-parity-20260423/)

### [x] P6e. Runtime/Awards architecture modernization with strict legacy parity

Outcome:
Replay-critical map flow, awards/ribbons behavior, and GeoIP handling were
modernized and replay-validated without changing the default strict product
contract.

### [x] P6f. Bounded Statsme counter-delta write slice

Outcome:
Statsme player/server counter updates are batched at the stdin transaction
boundary while append-only Statsme events remain explicit. The slice has 427
explicit product tests, prefix r2 plus fresh no-reuse narrow r1 parity, and a
Python-only product-path timing gate with only the accepted GeoIP Players
residual. The legacy/Python `1.108x` figure is a same-corpus elapsed ratio, not
normalized records/s or incremental Statsme wall-speed proof. The disposable
profile shows fewer physical DB calls, but its profiled and isolated-host wall
samples are not a promotion claim. See
`docs/audits/legacy-python-parity-20260423/performance-db-sql-opt-narrow-1000-20260718-statsme-bench-r1/`.

### [x] P6g. Release-clean maintenance parity and P1 hardening closure

Outcome:
The only canonical heavy gate now starts both contours from a fresh baseline,
performs the shared historical maintenance receipt (`UseTimestamp=1`, inactive,
awards, ribbons, strict GeoIP), then snapshots, compares, and smokes the web
before it can pass. Legacy is tested as an EN reference; the Python product is
tested in EN and RU with dynamically resolved populated signature IDs. The
accepted clean gates are `prefix-100/20260722-maintenance-prefix-100-r8` and
`narrow-1000/20260722-maintenance-narrow-1000-r1`; both report no logical DB
differences after maintenance. The runner stages only selected FTP logs to
avoid Docker Desktop startup stalls, and CI packages its sanitized canonical
outcome rather than rerunning partial post-gates. Evidence and the rejected
intermediate hypotheses are in
[`maintenance-parity-20260722.md`](audits/legacy-python-parity-20260423/maintenance-parity-20260722.md).

### [ ] P6h. Gradual EventStorage strangler split

Status: planned, not started.

Do not replace the replay-critical storage facade wholesale. Characterize and
preserve its serialized transaction/order contract, then extract one bounded
state, repository, or event-family seam at a time behind the existing facade.
Every completed slice requires focused contract tests and a clean
`prefix-100`; each coherent milestone additionally requires a clean
`narrow-1000`. The concrete dependency order and stop conditions are in
[`2026-07-22-event-storage-strangler-plan.md`](plans/2026-07-22-event-storage-strangler-plan.md).

## Out of scope for this lane

- upstreaming the Python migration into `A1mDev/hlstatsx-community-edition`
- broad SQL refactors that are not required by the product contract
- translating DB content
- adding more locales before EN/RU is fully stable
