# HLstatsX Community Edition: Python + i18n

This repository is the standalone product lane for HLstatsX Community Edition
with:

- Python as the default runtime path for log ingestion and operational tooling
- PHP as the web frontend
- explicit multilingual frontend support with English and Russian catalogs

The intended production topology is:

`game server -> proxy_daemon_py -> hlstats_py -> MySQL -> PHP web`

Perl remains in this repository only as a legacy compatibility and validation
surface. It is not the default runtime contract for this product lane.

## Repository role

**Where we work:** day-to-day implementation, tests, and product documentation
live **in this repository** (`hlstatsx-community-edition-python-i18n`). Treat
sibling checkouts in the same workspace as **read-only reference** (parity,
legacy semantics, donor web i18n) unless a task explicitly says to change them.

This repo is intentionally separate from the two donor lanes used to assemble
it:

- `hlstatsx-community-edition/` — reference for migration, replay baseline, and
  legacy behavior (do not use as the default target for new product commits).
- `hlstatsx-community-edition-web-ru-i18n/` — reference for upstream-friendly RU
  web i18n patterns.

The product repo integrates those two lines without forcing either donor lane
to become the final product branch.

**Fast bulk log replay** (stdin batch / direct import, not slow UDP line relay):
see [`docs/replay-fast-path.md`](docs/replay-fast-path.md).

### Git: `hlstatsx-community-edition` fork used for Python migration

On a fork of the Python migration repo (same tree as
`hlstatsx-community-edition/`, remote often named `origin`), branch **`test`**
is the **integration tip** for the Python stack, including stdin import
performance work. The GitHub **default branch** may still be `main`; use
**`test`** when you need that integration line. Ref
`perf/hlstats-stdin-batch-speedup` may still exist at the same commit until
removed for housekeeping.

## Product contracts

- Default runtime:
  - `scripts/run_proxy_py`
  - `scripts/run_hlstats_py`
  - `python -m hlstats_py.runtime`
- Frontend i18n:
  - language selection is explicit
  - `lang=en|ru`
  - fallback order is `GET -> cookie -> session -> en`
  - frontend copy is rendered through direct dictionary-backed lookups instead
    of whole-document post-processing
- Locale scope for v1:
  - English and Russian are first-class supported locales
  - the runtime and dictionaries should stay extensible for additional locales

## Key docs

- Product plan: `docs/plans.md`
- Product status: `docs/status.md`
- Product validation plan: `docs/test-plan.md`
- Python migration details: `docs/proxy_daemon_python_migration.md`
- Imported RU i18n donor context: `docs/web_frontend_i18n_plan.md`

## Current state

- Python replay parity is already documented and integrated from the migration
  donor lane.
- Explicit RU web i18n runtime cleanup and broad page coverage are integrated
  from the RU donor lane.
- The remaining work is product hardening:
  - finish exact Python `--stdin` boundaries
  - port the remaining Perl-only operational utilities
  - run targeted product validation on the integrated Python+i18n stack
  - prepare release-ready docs and handoff
