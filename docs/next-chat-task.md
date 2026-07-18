# Next Chat Task

Historical continuation note only.

Do not use this file as the primary task entrypoint. For current work, start
from `docs/status.md`, `docs/plans.md`, `docs/test-plan.md`, and
`docs/release-readiness.md`.

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

The autonomy/release-readiness follow-up plan through Phase 9 is complete for
the current scope. Do not resume the older broad parity continuation from
previous versions of this file.

Use this working interpretation:

- the old `_ensure_connection()` reconnect bug is not an active fix item;
- release-candidate preparation should now use
  [`docs/release-readiness.md`](release-readiness.md) as the checklist and
  evidence handoff runbook.

## Immediate task

For the next work item, start from the specific user request and verify it
against:

- [`docs/status.md`](status.md)
- [`docs/plans.md`](plans.md)
- [`docs/test-plan.md`](test-plan.md)
- [`docs/release-readiness.md`](release-readiness.md)

If the request is release-candidate preparation, collect fresh evidence from
the release checklist and update `docs/status.md`.

## Guardrails

- Do not reopen the stale reconnect-code fix unless fresh evidence from code or
  tests contradicts the current implementation.
- Do not treat `proxy_daemon_py` as if it had a `KILL` control path; harden the
  real current control surface only.
- Do not jump into PHP refactor or new features unless the request explicitly
  targets that work and the relevant checks are scoped first.
- Keep work in this product lane unless a task explicitly spans donor repos.
