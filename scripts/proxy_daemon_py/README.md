# HLstatsX Proxy Daemon (Python)

This directory hosts the Python reimplementation of the legacy `proxy-daemon.pl`
script.  The project is managed with [Poetry](https://python-poetry.org/) to keep
runtime and development dependencies reproducible.

## Getting started

```bash
cd scripts/proxy_daemon_py
poetry install
```

The command above creates a local virtual environment (by default inside the
project directory) and installs the base dependencies required for future
implementation work.  During the early migration stages, the package contains
scaffolding only, so no executable entry points are exposed yet.

### Local MySQL sandbox

The Python daemon expects a MySQL schema compatible with the legacy
installation.  A minimal dataset for local testing is provided via
`docker-compose`.  To start a disposable MySQL 8.0 instance seeded with the
required `hlstats_Options` entries and placeholder rows in `Proxy_Daemons` on
your local workstation, run:

```bash
cd scripts/proxy_daemon_py
docker compose up -d
```

See [docs/proxy_daemon_local_mysql.md](../../docs/proxy_daemon_local_mysql.md)
for detailed instructions and connection parameters.

## Quality checks

The configuration includes the following tools:

- **Ruff** for linting and import sorting (`poetry run ruff check .`).
- **Black** for code formatting checks (`poetry run black --check .`).
- **mypy** for static type checks (`poetry run mypy .`).
- **pytest** for unit and integration tests (`poetry run pytest`).

The CI workflow runs all of them on every push and pull request that touches the
Python daemon sources.  Running them locally before committing helps keep the
codebase consistent and ready for future tasks in the migration plan.
