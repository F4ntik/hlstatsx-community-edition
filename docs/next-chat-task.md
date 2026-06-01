# Next Chat Task

Workspace:
`D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n`

Branch:
`experiment/parity-trace-harness`

## Start here

Before making changes, read these in order:

1. [`docs/status.md`](status.md)
2. [`docs/plans.md`](plans.md)
3. [`docs/autonomy-review-20260601.md`](autonomy-review-20260601.md)
4. [`docs/autonomy-work-plan-20260601.md`](autonomy-work-plan-20260601.md)

## Current continuation

The repo has a fresh autonomy/release-readiness follow-up plan. Do not resume
the older broad parity continuation from previous versions of this file.

Use this working interpretation:

- the old `_ensure_connection()` reconnect bug is not an active fix item;
- the real active gaps are:
  - docs truth synchronization;
  - repository-wide CI;
  - `hlstats_py -> proxy_daemon_py` coupling;
  - manual `PYTHONPATH`;
  - lifecycle/control-plane hardening;
  - explicit DB-mode separation;
  - parity acceptance automation.

## Immediate task

Start from `Phase 0` in
[`docs/autonomy-work-plan-20260601.md`](autonomy-work-plan-20260601.md):

- reconcile `docs/status.md`, `docs/plans.md`, and `docs/test-plan.md`;
- remove stale reopened parity items from those docs;
- make the GeoIP / post-replay-backfill rule explicit;
- only after that move on to CI expansion.

## Guardrails

- Do not reopen the stale reconnect-code fix unless fresh evidence from code or
  tests contradicts the current implementation.
- Do not treat `proxy_daemon_py` as if it had a `KILL` control path; harden the
  real current control surface only.
- Do not jump into PHP refactor or new features before the docs/CI/package
  boundary work is in place.
- Keep work in this product lane unless a task explicitly spans donor repos.
