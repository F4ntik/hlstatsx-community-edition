# HLstats Python Worker

This package contains the runnable Python worker that replaces the legacy
`hlstats.pl` runtime in the statistics pipeline.

The worker listens for proxied UDP datagrams from `proxy_daemon_py`, validates
`Proxy_Key`, parses the log envelope, normalizes events via `hlstats_py.events`,
and persists them to the existing HLstats MySQL schema through
`hlstats_py.storage`.

Typical local usage from the shared Poetry environment:

```bash
cd scripts/proxy_daemon_py
PYTHONPATH=.. poetry run python -m hlstats_py.runtime --configfile ../hlstats.conf --port 28000 --foreground
```

The module intentionally keeps the legacy topology intact:

`game server -> proxy_daemon_py -> hlstats_py worker -> MySQL -> PHP web`

This allows the PHP web interface and database schema to remain unchanged while
Perl is removed from the runtime path.
