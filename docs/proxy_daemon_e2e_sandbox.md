# E2E sandbox for the Python proxy daemon

This document describes the docker-compose bundle that exercises the Python
proxy daemon together with mock downstream proxies. The environment mirrors the
requirements from the migration plan (MySQL + Python daemon + daemon emulators)
and can be used to validate integration flows without touching production
systems.

## Components

The compose file at `scripts/proxy_daemon_py/e2e/docker-compose.yml` defines
four services:

- **mysql** – MySQL 8.0 seeded with the minimal schema and proxy configuration.
  Data is initialised by reusing the SQL fixtures from
  `scripts/proxy_daemon_py/sql/` and an extra script that rewrites
  `Proxy_Daemons` entries to point at the mock services.
- **proxy-daemon** – Container image built from the Python sources via
  `Dockerfile.proxy`. It installs the package with `pip`, loads the
  configuration from `hlstats.conf`, and starts `proxy_daemon_py.e2e.run_proxy_daemon`.
- **mock-daemon-a** and **mock-daemon-b** – Lightweight asyncio responders that
  listen on UDP ports `27900` and `27901`, reply to `C;HEARTBEAT;` payloads with
  `Heartbeat OK`, and log forwarded packets.

All services share an isolated docker network. MySQL is also exposed on
`localhost:33070` so that developers can inspect the database contents while the
stack is running.

## Usage

```bash
cd scripts/proxy_daemon_py/e2e
./start.sh
```

The helper script sets a deterministic `COMPOSE_PROJECT_NAME` and runs `docker
compose up -d`. Once the MySQL healthcheck passes, the proxy daemon will connect
and start logging to stdout. Tail the logs via `docker compose logs -f`.

Shut down the environment with:

```bash
./stop.sh
```

To rebuild the images after modifying the Python sources, add `--build` to the
`docker compose up` invocation or run `docker compose build` explicitly.

## Configuration details

- The proxy configuration (`hlstats.conf`) specifies `DBHost mysql` so that the
  daemon connects to the compose service name. It binds UDP to `0.0.0.0:27500` to
  accept traffic from other containers or the host (via port forwarding).
- The SQL overrides set `Proxy_Daemons` to
  `mock-daemon-a:27900,mock-daemon-b:27901`, matching the mock services.
- The mock daemons can be customised via environment variables (see
  `mock_daemon.py`). For example, setting `MOCK_DAEMON_HEARTBEAT_RESPONSE` lets
  you experiment with negative heartbeat paths.

## Next steps

This sandbox covers the minimum integration flow for migration task 6.2. Future
iterations can add a synthetic game server client that sends UDP traffic through
the proxy or extend the mock daemons to emulate real downstream behaviour.
