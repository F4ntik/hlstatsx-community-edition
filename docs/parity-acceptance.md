# Parity Acceptance Runbook

## Purpose

Phase 7 moves parity from manual operator knowledge into a documented
acceptance flow that is cheap enough for routine product work and still strict
enough for release-readiness.

This runbook does not replace the detailed replay/debug procedures in:

- `docs/replay-fast-path.md`
- `docs/parity-debug-pipeline.md`
- `docs/parity-acceptance-policy.md`

Use this file to decide which parity path to run, which artifacts must be kept,
and when legacy Perl is still required.

## Acceptance Layers

### 1. Lightweight PR subset

Use this on ordinary pull requests and local pre-merge validation.

Goal:

- catch obvious parity regressions early;
- avoid making daily development depend on a fresh full legacy replay.

Expected scope:

- the repository-wide product CI workflow in
  `.github/workflows/product-ci.yml`;
- targeted Python tests for the changed runtime/storage/replay code;
- replay-helper smoke for the touched path;
- when behavior is parity-affecting, a narrow Python replay/compare loop using
  the documented reusable legacy narrow-1000 baseline from
  `docs/replay-fast-path.md`.

Do not require a fresh dual legacy+Python full replay for every PR. Reuse the
known-good legacy narrow-1000 state when its inputs are unchanged.

### 2. Nightly-heavy replay flow

Use this on scheduled/manual heavy validation, not on every product iteration.

Goal:

- confirm that the accepted product contour still matches the current legacy
  reference on the broad replay gate;
- regenerate parity evidence after replay-critical changes;
- catch slow drift that a narrow PR loop can miss.

Expected scope:

- scheduled/manual `.github/workflows/nightly-parity.yml` execution on the
  self-hosted Windows parity runner;
- full Docker-backed dual replay for the supported contour via
  `scripts/replay_baseline/comparison/Run-DualContour-1000.ps1` without
  `-ReuseValidLegacy`;
- the runner's shared historical maintenance receipt: `UseTimestamp=1`,
  inactive players, awards, ribbons, strict GeoIP, SQL anchors, stable-key DB
  compare, legacy EN-reference web smoke, and Python EN/RU product web smoke;
- archived artifacts sufficient to reproduce or investigate failures later.

## Reproducible Fixtures and Artifacts

Parity acceptance is only useful if the same contour can be replayed again.
Keep these inputs and outputs stable and inspectable.

### Required fixture identity

Record the fixture identity for any accepted parity baseline:

- baseline dump/snapshot identity, currently
  `scripts/replay_baseline/artifacts/baseline_reset_20260418.sql.gz`;
- source dump/corpus identity, currently
  `scripts/replay_baseline/artifacts/hlstatsxce_prod_20260418.sql.gz` and
  `scripts/replay_baseline/artifacts/hlstats_logs_last7d_20260418.tgz`;
- corpus path and exact replay window, currently
  `scripts/replay_baseline/artifacts/`;
- sorted-file selection rule, currently first `MaxImportFiles` `*.log` files by
  name for `narrow-1000`;
- `server_identity=37.230.137.48:27015`;
- replay policy such as `--drop-empty-team-enter-events`;
- whether the run is raw-only or release-clean;
- for release-clean: resolved maintenance date/horizon, exact selected actions,
  `UseTimestamp=1` readback in each disposable contour, and the no-prune
  historical-corpus rule.

### Required stored artifacts

Keep or refresh these artifacts for the accepted contour:

- contour metadata/fingerprint from
  `scripts/replay_baseline/comparison/.parity-state/contour-info/`;
- compare output from `compare_stats_dbs.py`;
- SQL row-count anchors/snapshots for the relevant run;
- `maintenance-summary-*`, two maintenance logs, and two web-smoke logs for a
  release-clean run;
- any targeted audit note needed to explain an accepted difference or failure.

The current accepted `narrow-1000` metadata lives in:

- `scripts/replay_baseline/comparison/.parity-state/contour-info/legacy-narrow-1000.json`
- `scripts/replay_baseline/comparison/.parity-state/contour-info/python-narrow-1000.json`

The artifact set must be enough to answer two questions without rerunning from
memory: "what exact contour was replayed?" and "why was the result accepted?"

## When Perl Is Still Required

Perl remains part of the acceptance/reference layer, but not of the ordinary
product runtime path.

### Required Perl use

Keep Perl for these cases only:

- reference behavior: confirming how legacy actually handled a disputed
  event/lifecycle rule before changing Python behavior;
- baseline regeneration: rebuilding the accepted legacy replay baseline when the
  fixture inputs change or when the reusable legacy state is no longer valid;
- targeted investigation: narrow residual tracing when the current artifacts are
  not enough to classify a difference under `docs/parity-acceptance-policy.md`.

### Not required for routine work

Perl should not be a live dependency for:

- ordinary PR validation on unchanged fixtures;
- routine Python-only refactors that do not alter replay behavior;
- day-to-day release-readiness checks that can rely on the preserved accepted
  baseline and nightly-heavy evidence.

## Promotion Rules

Promote from the lightweight PR subset to the nightly-heavy flow when any of
these are true:

- replay/storage/runtime behavior changed in a way that can affect parity;
- the reusable legacy baseline inputs changed;
- a current diff cannot be classified confidently from existing artifacts;
- a release-readiness checkpoint needs fresh broad evidence.

If a difference remains after the heavy run, classify it with
`docs/parity-acceptance-policy.md` as must-fix, accepted legacy difference, or
diagnostic backlog.

## Done Criteria for Phase 7

Phase 7 is operationally complete when:

- routine PR work can use the lightweight subset without rerunning fresh legacy
  replay by habit;
- scheduled/manual heavy replay produces reproducible artifacts for the broad
  contour;
- the repo documents exactly where Perl is still needed and where it is not;
- parity remains strict, but ordinary development no longer depends on live
  day-to-day Perl operation.
