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

## Verification

- Run tests and replay checks in **this** subproject after edits.
- Rebuild `hlstats-worker` when Dockerized replay must pick up new `hlstats_py`
  code (see `docs/replay-fast-path.md`).
