# Docs Map: Python+i18n Product Lane

This directory contains both active product documentation and historical
investigation or migration notes. Do not treat every file here as current
source of truth.

## Start Here

Read these first for almost every task:

1. `docs/status.md`
2. `docs/plans.md`
3. `docs/test-plan.md`

For release-candidate and handoff work, read next:

4. `docs/release-readiness.md`

## Canonical Runbooks

- `docs/replay-fast-path.md`
- `docs/full-corpus-first-divergence.md`
- `docs/parity-acceptance.md`
- `docs/parity-acceptance-policy.md`
- `docs/release-readiness.md`

These define the approved replay loop, first-divergence investigation path,
parity acceptance rules, and release evidence contract for the integrated
product lane.

## Supporting Operations Docs

- `docs/python_migration_usage_guide.md`
- `docs/python_fullstack_docker.md`
- `docs/web_updater_runbook.md`
- `docs/proxy_daemon_py_getting_started.md`
- `docs/proxy_daemon_py_operational_runbook.md`
- `docs/hlstats_py_stdin_import_tuning.md`

Use these when the task is specifically about deployment, onboarding, Docker
smoke setup, or stdin import tuning.

## Technical Reference Docs

- `docs/hlstats_py_protocol.md`
- `docs/hlstats_py_events.md`
- `docs/hlstats_py_storage.md`
- `docs/hlstats_py_validation.md`
- `docs/hlstats_awards_py_cli.md`
- `docs/hlstats_awards_py_calculator.md`
- `docs/hlstats_awards_py_reports.md`
- `docs/hlstats_awards_py_geoip_runbook.md`
- `docs/hlstats_resolve_py_cli.md`

These are reference notes for specific modules, not general task entrypoints.

## Historical Background

These files are retained for traceability and older planning context:

- `docs/autonomy-review-20260601.md`
- `docs/autonomy-work-plan-20260601.md`
- `docs/next-chat-task.md`
- `docs/parity-runtime-decisions-refactor.md`
- `docs/proxy_daemon_python_migration.md`
- `docs/proxy_daemon_migration_task_breakdown.md`
- `docs/web_frontend_i18n_plan.md`
- `docs/web_frontend_i18n_status.md`
- `docs/web_frontend_i18n_test-plan.md`
- `docs/web_frontend_i18n_handoff.md`

Read them only when you need historical rationale.

## Evidence And Audit Artifacts

- `docs/audits/legacy-python-parity-20260423/`
- `docs/audits/modern-heatmap-explorer/runtime-acceptance.md` — current local
  release-candidate source/browser/visual gates, rollout boundary, screenshots,
  exact restore, and raw-receipt index.
- `docs/audits/modern-heatmap-explorer/performance.md` — index decision,
  MyISAM updater/performance evidence, and historical contour non-claims.
- `docs/audits/modern-heatmap-explorer/evidence/acceptance-2026-09-02.json` —
  current sanitized visibility-correction acceptance summary at exact commit
  `44f3af9`.
- `docs/audits/modern-heatmap-explorer/evidence/acceptance-2026-09-01.json` —
  historical pre-visibility-correction acceptance summary.

Keep detailed replay transcripts, compare outputs, and retained parity evidence
there rather than expanding `status.md`.

## Working Rule

If a historical file conflicts with `docs/status.md`, `docs/plans.md`,
`docs/test-plan.md`, or `docs/release-readiness.md`, prefer the canonical
documents.
