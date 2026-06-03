# HLstats Python Worker

This package contains the runnable Python worker that replaces the legacy
`hlstats.pl` runtime in the statistics pipeline.

The worker listens for proxied UDP datagrams from `proxy_daemon_py`, validates
`Proxy_Key`, parses the log envelope, normalizes events via `hlstats_py.events`,
and persists them to the existing HLstats MySQL schema through
`hlstats_py.storage`.

Typical local usage from the shared Poetry environment:

```bash
cd scripts/hlstats_py
poetry run python -m hlstats_py.runtime --configfile ../hlstats.conf --port 28000 --foreground
```

Offline legacy-style import from a `.log` file now also has a dedicated stdin
mode. It requires the canonical source server identity so replayed lines can be
attributed to the correct `hlstats_Servers` row:

```bash
cd scripts/hlstats_py
Get-Content -Raw ..\replay_baseline\artifacts\L0415056.log | `
  python -m hlstats_py.runtime --configfile ..\hlstats.conf --stdin `
  --server-ip 172.19.0.1 --server-port 27015
```

In `--stdin` mode the worker uses event timestamps as the processing clock and
applies an import-finalize pass at EOF, which makes it a better foundation for
the remaining exact `hlstats.pl --stdin` parity work and the future `HLStatsFTP`
port.

## Legacy Heatmaps Batch Generator

The package now also contains a separate batch-style heatmap generator that
replaces the legacy PHP entrypoint `heatmaps/generate.php` without changing the
published asset names expected by the PHP web layer.

Typical local usage from the shared Poetry environment:

```bash
cd scripts/hlstats_py
poetry run python -m hlstats_py.heatmaps \
  --configfile ../hlstats.conf \
  --web-root ../web \
  --heatmaps-root ../heatmaps
```

The generator keeps the legacy execution model:

- It reads map metadata from `hlstats_Heatmap_Config` and visible game codes
  from `hlstats_Games`.
- It consumes the existing heatmap pack layout under
  `heatmaps/src/<realgame>/<map>.jpg` together with `brush_small.png`,
  `brush_large.png`, and `DejaVuSans.ttf`.
- It publishes JPEGs to `web/hlstatsimg/games/<code>/heatmaps` using the
  legacy names `<map>-kill.jpg` and `<map>-kill-thumb.jpg`.
- It keeps the incremental overlay cache in `heatmaps/cache/<code>`.

Supported legacy selectors are available as direct CLI flags:

```bash
cd scripts/hlstats_py
poetry run python -m hlstats_py.heatmaps \
  --configfile ../hlstats.conf \
  --game cstrike \
  --map de_dust2 \
  --disablecache
```

The source map-pack JPEGs are still external assets and are not bundled into
this repository, so a real legacy-vs-Python parity check on production maps
still requires an installed heatmap pack.

The module intentionally keeps the legacy topology intact:

`game server -> proxy_daemon_py -> hlstats_py worker -> MySQL -> PHP web`

This allows the PHP web interface and database schema to remain unchanged while
Perl is removed from the runtime path.
