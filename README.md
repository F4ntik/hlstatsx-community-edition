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

This repo is intentionally separate from the two donor lanes used to assemble
it:

- `hlstatsx-community-edition/` provides the Python migration, replay-baseline,
  proxy daemon, operational tooling, and heatmap generator work.
- `hlstatsx-community-edition-web-ru-i18n/` provides the upstream-friendly RU
  web i18n runtime cleanup and page coverage work.

The product repo integrates those two lines without forcing either donor lane
to become the final product branch.

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
