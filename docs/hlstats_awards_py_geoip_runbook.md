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
