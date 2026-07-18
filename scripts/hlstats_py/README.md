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

Projection diagnostics can run directly against the DB without regenerating
JPEGs or replaying logs:

```bash
cd scripts
python -m hlstats_py.heatmaps \
  --configfile hlstats.conf \
  --game cstrike \
  --map de_dust2 \
  --heatmaps-root ../heatmaps \
  --diagnose-projection
```

For maps whose world coordinates do not line up with the overview image, use
the local calibration helper. It can import GoldSrc or Source overview `.txt`
metadata, write a standalone HTML preview with sliders, and apply the chosen
legacy projection values only after the in-bounds ratio passes the configured
threshold and the separate runtime gate is explicitly acknowledged with
`--runtime-gate-approved`:

```bash
cd scripts
python heatmap_projection_calibrate.py \
  --configfile hlstats.conf \
  --game cstrike \
  --map de_dust2 \
  --heatmaps-root ../heatmaps \
  --overview-file path/to/cstrike/overviews/de_dust2.txt
```

GoldSrc overview files such as `cstrike/overviews/<map>.txt` and Source-style
`resource/overviews/<map>.txt` are treated as calibration seeds, not as a
guarantee that the current web JPEG has the same crop and scale as the shipped
radar image. Use `--diagnose-projection` and the calibration preview against
the already populated DB first; only regenerate static JPEGs with
`--disablecache` after the projection is stable.

## Web Heatmap Overlay

The PHP web layer now has a DB-backed JSON overlay path in addition to the
legacy generated JPEGs:

- `web/heatmap_points.php?game=<code>&map=<map>` returns transformed canvas
  points for the global map heatmap.
- `web/heatmap_points.php?game=<code>&map=<map>&player=<id>&event=kills`
  returns the selected player's kill locations.
- `event=deaths` returns where that player died, using victim coordinates when
  available.
- `event=both` returns both channels in one payload.

The response keeps the base image dimensions, diagnostics, transformed points,
and hover metadata. Player-scoped points include separate `killValue` and
`deathValue` fields so the browser can render kills as a warm
yellow/orange/red channel and deaths as a cool cyan/blue/violet channel. Hover
tooltips use the same payload to show top killers, victims, and involved
players for the nearest bucket.

`mapinfo` uses this JSON layer as an inline canvas overlay on top of the map
image while keeping the old `<map>-kill.jpg` and `<map>-kill-thumb.jpg`
lightbox link as a compatibility fallback. `playerinfo` shows a personal
heatmap widget in the Maps & Servers tab; the map selector is built from maps
where the player has DB events and the product has heatmap config plus a map
image.

The module intentionally keeps the legacy topology intact:

`game server -> proxy_daemon_py -> hlstats_py worker -> MySQL -> PHP web`

This allows the PHP web interface and database schema to remain unchanged while
Perl is removed from the runtime path.
