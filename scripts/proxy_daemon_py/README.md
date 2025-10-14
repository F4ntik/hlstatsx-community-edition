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

### Choosing the right docker-compose bundle

There are **two** compose configurations in this repository, each serving a
different purpose:

| Location | What it starts | When to use |
| --- | --- | --- |
| `scripts/proxy_daemon_py/docker-compose.yml` | A standalone MySQL 8.0 container seeded with the minimal HLstatsX proxy schema. | Developing against a disposable database without running the Python daemon. |
| `scripts/proxy_daemon_py/e2e/docker-compose.yml` | MySQL + the Python proxy daemon + two mock downstream daemons. | End-to-end checks of the daemon behaviour and heartbeat/balancing flows. |

Both bundles share the same SQL fixtures, so the database contents are
consistent no matter which environment you start. Pick the first option if you
only need a database sandbox (for example, when running unit tests locally) and
switch to the `e2e/` setup once you are ready to validate the full stack.

### Local MySQL sandbox

The Python daemon expects a MySQL schema compatible with the legacy
installation.  A minimal dataset for local testing is provided via the
root-level compose file. To start a disposable MySQL 8.0 instance seeded with the
required `hlstats_Options` entries and placeholder rows in `Proxy_Daemons` on
your local workstation, run:

```bash
cd scripts/proxy_daemon_py
docker compose up -d
```

See [docs/proxy_daemon_local_mysql.md](../../docs/proxy_daemon_local_mysql.md)
for detailed instructions and connection parameters.

### End-to-end docker-compose sandbox

To exercise the Python daemon together with mock downstream proxies, use the
compose bundle under `scripts/proxy_daemon_py/e2e/`:

```bash
cd scripts/proxy_daemon_py/e2e
./start.sh
```

The stack contains MySQL, the Python proxy daemon, and two UDP responders that
acknowledge heartbeat probes. It binds MySQL to `localhost:33070` to avoid
conflicting with the standalone database sandbox. Stop the environment with:

```bash
./stop.sh
```

Logs for each service can be inspected via `docker compose logs -f <service>`
from the same directory.

#### Troubleshooting connection issues

If the proxy container reports repeated connection failures (for example,
`[E403] Failed to start proxy daemon: Failed to connect to MySQL after repeated
attempts`), make sure that the `hlstats` account inside the compose environment
can authenticate with the expected credentials and uses the `mysql_native_password`
plugin. The steps below exercise the exact configuration consumed by the Python
daemon:

```bash
cd scripts/proxy_daemon_py/e2e
docker compose exec mysql mysql -uhlstats -phlstats -e "SELECT user, host, plugin FROM mysql.user WHERE user = 'hlstats';"
```

The command should print a single row with `plugin` set to `mysql_native_password`.
If the row is missing or the plugin column shows a different value, recreate the
environment with a clean MySQL volume so that the init scripts under
`scripts/proxy_daemon_py/sql/` can rerun:

```bash
./stop.sh
docker compose down -v
./start.sh
```

After the restart, tail the daemon logs to confirm that the proxy is able to log
in successfully:

```bash
docker compose logs -f proxy-daemon
```

## Quality checks

The configuration includes the following tools:

- **Ruff** for linting and import sorting (`poetry run ruff check .`).
- **Black** for code formatting checks (`poetry run black --check .`).
- **mypy** for static type checks (`poetry run mypy .`).
- **pytest** for unit and integration tests (`poetry run pytest`).

The CI workflow runs all of them on every push and pull request that touches the
Python daemon sources.  Running them locally before committing helps keep the
codebase consistent and ready for future tasks in the migration plan.
