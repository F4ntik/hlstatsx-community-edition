# HLstats Awards Python GeoIP Runbook

## Purpose

Backfill missing player country metadata in the Python contour after replay or
live ingest has populated `hlstats_Players.lastAddress`.

The Python runtime still writes connect/IP data only. GeoIP enrichment is owned
by the maintenance path:

- `hlstats_py` writes `lastAddress` and `hlstats_Events_Connects`
- `hlstats_awards_py --geoip` resolves location data and updates
  `hlstats_Players.flag`, `country`, `city`, `state`, `lat`, and `lng`

This keeps the product lane aligned with the legacy operational model:
runtime ingest first, maintenance backfill second.

## Historical dual-replay contour

For release-clean parity evidence, do not call this Python command by itself
after replay. `Run-DualContour-1000.ps1` invokes GeoIP together with legacy
maintenance in both disposable contours, after a shared historical award date
is resolved. It records full GeoIP plus awards/ribbons comparison and web
evidence in `maintenance-summary-*`.

The runner first sets and verifies `UseTimestamp=1` in both restored test DBs
so inactive-player processing uses the replay's latest server event instead of
the current host time. It deliberately excludes prune: an old corpus must stay
intact while awards are calculated. This override is confined to the restored
test DB; normal production maintenance keeps its configured behavior.

The accepted maintenance gate is `20260722-maintenance-narrow-1000-r1`: both
contours have `250` populated flags/countries, `219` cities, `221` states, and
`250` coordinate pairs after the receipt. It also proves that this backfill is
not isolated from award rendering: the legacy EN reference and Python EN/RU
award/ribbon routes pass against the populated replay data. See
`docs/audits/legacy-python-parity-20260423/maintenance-parity-20260722.md`.

## Preconditions

- The target DB already contains players with `lastAddress <> ''`
- One of these GeoIP sources is available:
  - populated `geoLiteCity_Blocks` + `geoLiteCity_Location` tables
  - or `scripts/GeoLiteCity/GeoLite2-City.mmdb` with `UseGeoIPBinary > 0`
- install the package dependencies, or run from the repository root with
  `scripts` on `PYTHONPATH`:

```powershell
$env:PYTHONPATH="scripts"
```

## Run command

From the repository root:

```powershell
$env:PYTHONPATH="scripts"
python -m hlstats_awards_py --configfile scripts/hlstats.conf --geoip
```

If the contour uses a different config file, replace `scripts/hlstats.conf`
with that contour-local path.

## Verification

Before the run:

```sql
SELECT COUNT(*) AS missing_geoip
FROM hlstats_Players
WHERE flag = '' AND lastAddress <> '';
```

After the run:

```sql
SELECT COUNT(*) AS missing_geoip
FROM hlstats_Players
WHERE flag = '' AND lastAddress <> '';
```

Spot-check populated rows:

```sql
SELECT playerId, lastName, lastAddress, flag, country, city, state, lat, lng
FROM hlstats_Players
WHERE flag <> ''
ORDER BY playerId DESC
LIMIT 10;
```

## Failure modes

- If `geoLiteCity_*` tables are missing in DB mode, the command exits with:
  `GeoIP method set to database but geoLiteCity tables are empty.`
- If binary mode is enabled but the MaxMind DB is missing, the command exits
  with an explicit `...GeoLite2-City.mmdb NOT FOUND` error.
- Invalid or blank non-IPv4 `lastAddress` values are skipped rather than
  aborting the full batch.

## Related docs

- `docs/hlstats_awards_py_cli.md`
- `docs/hlstats_awards_py_calculator.md`
- `docs/test-plan.md`
