# Full-stack Docker for the Python runtime

This stack boots the full Python runtime path without Perl in production flow:

- MySQL 8.0 with the canonical HLstats schema from `sql/install.sql`
- `proxy_daemon_py` as the UDP entrypoint for game servers
- one `hlstats_py` downstream worker
- the existing PHP web frontend

## Location

`scripts/proxy_daemon_py/fullstack/docker-compose.yml`

## Start

```bash
cd scripts/proxy_daemon_py/fullstack
docker compose up -d --build
```

## Exposed ports

- `33080` -> MySQL
- `27500/udp` -> Python proxy daemon
- `8080` -> PHP web frontend

## Seeded runtime state

The stack seeds the following defaults:

- `Proxy_Key = pythonproxysecret`
- `Proxy_Daemons = hlstats-worker:28000`
- one example server row: `127.0.0.1:27015` / `Local Python Server`

This is enough for smoke-testing the path:

`game server/plugin -> proxy daemon -> hlstats worker -> MySQL -> PHP web`

## Web smoke expectations

The full-stack test web image intentionally diverges from a raw legacy web
checkout in two narrow runtime-only ways so the contour can be smoke-tested on
PHP 8.2 without manual cleanup:

- the `web/updater` directory is removed from the container image, so the main
  page must not stop on the legacy "Update Notice" warning
- `E_DEPRECATED` output is suppressed in the test config so legacy `pChart`
  deprecations do not corrupt image responses such as `trend_graph.php`

Quick smoke checks:

```bash
curl -I http://127.0.0.1:8080/
curl -I http://127.0.0.1:8080/hlstats.php
curl -I "http://127.0.0.1:8080/trend_graph.php?player=1"
```

Expected results:

- `/` redirects to `hlstats.php`
- `hlstats.php` responds with `200 OK` and does not show the updater warning
- `trend_graph.php` redirects to a generated PNG under `hlstatsimg/progress`

## Stop

```bash
docker compose down
```
