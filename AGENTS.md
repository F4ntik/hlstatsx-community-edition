# AGENTS.md — hlstatsx-community-edition-python-i18n

## Scope

- **Active development:** this repository only (Python runtime, replay tooling,
  PHP+i18n product lane, docs under `docs/`).
- **Reference only:** sibling folders in the same workspace (for example
  `hlstatsx-community-edition/`, `hlstatsx-community-edition-web-ru-i18n/`) —
  read for legacy behavior, donor web i18n, or parity context; do **not** treat
  them as the default place to land changes unless the task explicitly spans
  them.

## Before coding

- Read `docs/plans.md` and `docs/status.md` for the current milestone and gates.
- For bulk log replay / parity windows: **`docs/replay-fast-path.md`** (canonical
  links; use direct stdin / `direct_import_artifacts.py`, not UDP, for speed).

## Multi-Agent Workflow

- Use multi-agent work for anything that can be parallelized: search, testing,
  investigation, artifact review, and hypothesis checks.
- Choose the model to match the subtask: use `5.4` for deep investigation and
  high-risk reasoning, and `5.4-mini` for quick searches, narrow checks, and
  routine validation.
- Set reasoning depth according to task complexity and risk. Increase depth
  when the task has many dependencies or the cost of a wrong answer is high.
- Give agents concrete, bounded assignments with a clear output format, then
  reconcile their results against code, tests, and artifacts before drawing
  conclusions.
- Use English for agent instructions, agent-facing questions, and internal
  reasoning.
- Use Russian in the main thread for progress updates, summaries, and final
  work reports.
- Ask auxiliary questions only when needed to continue safely or avoid an
  incorrect assumption.
- Do not do parallel manual work yourself if agents can cover it. Treat agents
  as eyes and hands, and keep the main thread focused on synthesis and
  decisions.

## Verification

- Run tests and replay checks in **this** subproject after edits.
- Rebuild `hlstats-worker` when Dockerized replay must pick up new `hlstats_py`
  code (see `docs/replay-fast-path.md`).
- For a long Docker replay, use the DB-backed monitoring procedure in
  `docs/replay-fast-path.md`: delegate one monitor where possible, sample
  MySQL `hlstats_Events_Frags` count in both contours no more than once per 60
  seconds, and do not tightly poll an unchanged terminal line. Counts are
  telemetry only, never replay-acceptance evidence.
- Keep Python replay scratch in a unique named Docker volume per evidence run;
  export only the declared manifests rather than bind-mounting scratch I/O on
  Docker Desktop, where host mounts can stall the import.
- For `IgnoreBots`, the exact source-log message `Log file started` starts a
  new per-server bot-seed epoch without clearing the player identity cache. In
  asynchronous replay that mutation belongs to the serialized storage executor.
