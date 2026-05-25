# Plan: Standalone Python+i18n Product Lane

## Summary

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

Canonical runbooks:

- replay mechanics and fast-path guidance:
  [`docs/replay-fast-path.md`](replay-fast-path.md)
- parity debug workflow for narrow residuals:
  [`docs/parity-debug-pipeline.md`](parity-debug-pipeline.md)
- audit evidence and bug triage:
  [`docs/audits/legacy-python-parity-20260423/README.md`](audits/legacy-python-parity-20260423/README.md)

## Product contract

- Default runtime path:
  `proxy_daemon_py -> hlstats_py -> MySQL -> PHP web`
- Legacy Perl path:
  keep only for compatibility checks, baseline replay comparison, and
  transition tooling
- Frontend contract:
  - explicit dictionary-backed i18n
  - `lang=en|ru`
  - fallback order `GET -> cookie -> session -> en`
  - no whole-document translation rewriting

## Current focus

- Keep the repo release-clean as the integrated Python+i18n product lane.
- Close or explicitly accept the remaining legacy-vs-Python parity residuals.
- Keep replay, compare, and representative EN/RU smoke checks runnable without
  duplicating their runbooks across multiple docs.
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
- Treat full `narrow-1000`, Docker rebuilds, GeoIP backfill, and web smoke as
  promotion gates, not first-line debugging tools. Run them when the touched
  surface requires them or when a narrow fix is ready to prove against the
  supported contour.
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

Definition of done:

- the repo can be described as a standalone Python+i18n product lane
- validation evidence exists for runtime, replay, frontend behavior, and the
  remaining accepted parity differences

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
the remediated product contour.

### [ ] P6d. Full legacy-vs-Python product parity audit

Goal:
Run a 1:1 audit against the original non-Python HLstatsX contour and the
integrated Python+i18n contour, then convert the remaining differences into a
deduplicated bug plan or explicit accepted differences.

Current gates:

- `[x] P6d-M1 (LP-P6D-001)`: `hlstats_Events_TeamBonuses` is clean in the
  current full `narrow-1000` contour and direct stable-key SQL.
- `[x] P6d-M2 (RC-B)`: `ChangeTeam`, `Connects`, `Chat`, and `PlayerActions`
  no longer appear in the current full `narrow-1000` logical compare.
- `[ ] P6d-M3 (RC-C)`: recheck player identity/history attribution now that
  M1/M2 are stable.

Current working rules:

- before starting a non-trivial parity fix, use a read-only subagent to inspect
  and document how the legacy Perl code implements the behavior
- use additional subagents for independent artifact grouping when a parity
  residual is non-trivial
- use single-log and narrow-window replay before another broad contour run
- after a point fix, inspect the automatic `30/30` guard-window parity rerun
  from `Run-SingleLogParity.ps1` before promoting the fix
- separate GeoIP-only player differences from real stats/session/alias drift
  before touching attribution logic
- current `hlstats_Players` normalized drift is already classified as
  GeoIP-only (`country`/`flag`), so the active attribution work should stay on
  `hlstats_PlayerNames` and `hlstats_Players_History`
- the first `PlayerNames` case was stateful across the neighboring
  `L0102209..L0102213` logs; it is now fixed by preserving the legacy
  live-object constructor alias across ordinary same-live-object descriptors
- broad `hlstats_PlayerNames` is now down to the remaining `XYU` / `unnamed`,
  `0:552632503` Python-only alias residual; do not reopen the closed
  `Player21` / `Dim$0n` / `Dim$on` cluster unless new evidence contradicts the
  clean same-cluster replay
- do not repeat the rejected `changed name to` alias-rollup flush fix: it was
  rolled back because it was based on an oversimplified unit-level hypothesis
  and failed the full `L0102212` plus `L0102209..L0102213` replay evidence
- next active M3 block is `hlstats_Players_History` streak attribution, starting
  from `Rakza`, `STEAM_0:1:55955613`, `L0103144` / `L0103146` / `L0103212`
- do not apply the rejected event-level "current streak instead of max streak"
  shortcut for `Players_History`; the 2026-05-24 promotion replay broadened
  history drift from `50/50` to `106/106`, so the next candidate must trace
  legacy `flushDB` sampling cadence first
- the retained flush-sampling fix now aligns Python with legacy
  `endKillStreak` / `flushDB` boundaries and reduces `Players_History` to
  `14/14`; remaining history work should focus on skill/stat attribution
  examples, not another broad kill-streak shortcut
- the fresh `narrow-1000` after that fix surfaced one Python-only
  `Events_TeamBonuses` `Dance Bear` / `CTs_Win` row; recheck that lifecycle
  separately before calling the current contour TeamBonuses-clean again
- treat `Events_Entries legacy=0` vs `python>0` as an accepted visible
  difference unless the acceptance policy is explicitly changed
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

## Out of scope for this lane

- upstreaming the Python migration into `A1mDev/hlstatsx-community-edition`
- broad SQL refactors that are not required by the product contract
- translating DB content
- adding more locales before EN/RU is fully stable
