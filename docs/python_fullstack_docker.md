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

## Stop

```bash
docker compose down
```
