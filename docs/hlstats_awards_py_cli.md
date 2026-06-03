# Python CLI for `hlstats-awards`

The Python port of the awards and maintenance script reuses the existing
`hlstats.conf` parser from the proxy daemon to stay configuration-compatible
with the legacy Perl tooling. The CLI mirrors the original options, including
short aliases:

- `-i`/`--inactive`
- `-a`/`--awards`
- `-r`/`--ribbons`
- `-g`/`--geoip`
- `-t`/`--clans`
- `-p`/`--prune`
- `-o`/`--optimize`

When no actions are specified the script defaults to running inactive player
maintenance, awards, ribbons and pruning, matching the Perl behaviour.

Database parameters are read from `hlstats.conf` in the current working
directory. Command line flags override these defaults, and an explicit
`--configfile` applies another configuration file after CLI overrides—mirroring
the "cannot be overridden" semantics advertised in the Perl help output.

The parser validates `--numdays` and `--date` formats and exposes the structured
values to the rest of the application.  The calculator described in
`docs/hlstats_awards_py_calculator.md` consumes these settings to drive the
database-backed maintenance routines.

Unlike the earlier stub state, `python -m hlstats_awards_py ...` is now a real
entrypoint: it loads settings, builds the shared synchronous MySQL adapter, and
executes the requested maintenance actions through `AwardsCalculator.run(...)`.

## GeoIP backfill

The `-g` / `--geoip` action now performs the Python-owned player location
backfill for this lane:

- it scans `hlstats_Players` rows where `flag = ''` and `lastAddress <> ''`
- it resolves location data either from:
  - `geoLiteCity_Blocks` / `geoLiteCity_Location` + `hlstats_Countries`
  - or `scripts/GeoLiteCity/GeoLite2-City.mmdb` when `UseGeoIPBinary > 0`
- it updates `flag`, `country`, `city`, `state`, `lat`, and `lng`

Typical local invocation from the repository root:

```powershell
$env:PYTHONPATH="scripts"
python -m hlstats_awards_py --configfile scripts/hlstats.conf --geoip
```

The detailed operational steps and SQL verification checks live in
`docs/hlstats_awards_py_geoip_runbook.md`.
