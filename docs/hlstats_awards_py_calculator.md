# Awards calculator SQL plan

The Python calculator mirrors the maintenance logic from `hlstats-awards.pl`
using the shared synchronous MySQL adapter from `proxy_daemon_py`. Each action
emits a deterministic sequence of SQL statements so that the behaviour can be
validated in tests and monitored during roll-out.

When several actions are requested, the legacy-compatible order is `prune`,
`optimize`, `inactive`, `awards`, `ribbons`, then `geoip`. The release-clean
historical contour deliberately selects only the trailing four actions, so
archive events remain available while awards are calculated.

## Player activity refresh (`--inactive`)

1. Read `MinActivity` and `UseTimestamp` from `hlstats_Options`.
2. `hlstats_Servers.last_event` and `hlstats_Players.last_event` are Unix-epoch
   `INT` values. When timestamps are enabled, fetch `MAX(last_event)` per game
   and update activity with numeric `<max> - hlstats_Players.last_event`.
   Otherwise use `UNIX_TIMESTAMP() - hlstats_Players.last_event` as the
   wall-clock fallback; do not apply `TIMESTAMPDIFF` to these integer fields.
3. Hide inactive players (`hideranking = 3`) when `activity < 0`.

## GeoIP backfill (`--geoip`)

1. Check whether `UseGeoIPBinary > 0` in `hlstats_Options`.
2. Select candidate players from `hlstats_Players` where `flag = ''` and
   `lastAddress <> ''`.
3. In DB mode:
   - verify `geoLiteCity_Blocks` contains data,
   - convert the IPv4 string into the legacy integer form,
   - resolve `locId` from `geoLiteCity_Blocks`,
   - join `geoLiteCity_Location` with `hlstats_Countries`.
4. In binary mode:
   - open `scripts/GeoLiteCity/GeoLite2-City.mmdb`,
   - resolve the IP through the MaxMind reader.
5. Update `hlstats_Players.flag`, `country`, `city`, `state`, `lat`, and `lng`
   for each successfully resolved player.
6. Skip blank or invalid non-IPv4 addresses instead of aborting the full batch.
7. Fail fast with an explicit error when the configured GeoIP source is missing,
   so the contour does not silently ship with `Unknown Country`.

## Award winner calculation (`--awards`)

1. Fetch visible award definitions from `hlstats_Awards` joined with
   `hlstats_Games`.
2. Update or insert the `awards_d_date` and `awards_numdays` options using the
   requested award horizon and base date (defaults to `CURRENT_DATE()`).
3. For each award, issue one "daily" and one "global" query:
   - generic awards count matching events in the rolling window,
   - latency averages over `hlstats_Events_Latency`,
   - historical stats from `hlstats_Players_History`,
   - bonus points across unioned action tables,
   - sentry gun kills by weapon prefix, or
   - connection time streaks.
4. Persist the winners into `hlstats_Awards` and mirror them in
   `hlstats_Players_Awards` for ribbon processing.
5. Keep the two historical `headshot` meanings distinct: object/action awards
   (`type=O`) match the literal action code `headshot`, while weapon awards
   (`type=W`) match the numeric frag headshot flag `1`.

## Ribbon recomputation (`--ribbons`)

1. Enumerate games via `hlstats_Games` and clear existing ribbons for the game.
2. Select the configured ribbon thresholds from `hlstats_Ribbons`.
3. Depending on the ribbon type, query either cumulative connection time or the
   per-award counts from `hlstats_Players_Awards` joined with
   `hlstats_Awards` and `hlstats_Players`.
4. Insert qualifying players back into `hlstats_Players_Ribbons`.

## Pruning and optimisation (`--prune`, `--optimize`)

- Delete aged rows from every `hlstats_Events_*` table, player history, trend and
  server load snapshots according to the `DeleteDays` option.
- Run `OPTIMIZE TABLE` for each table returned by `SHOW TABLES` when the
  `--optimize` flag is requested.

The unit tests in `scripts/hlstats_awards_py/tests/test_calculator.py` check
that these queries are emitted with the expected parameters so future refactors
can modify behaviour confidently. The calculator now exposes an `AwardsReport`
structure that records how many rows were touched by each maintenance task,
including GeoIP updates, the selected daily/global winners, and the ribbon
insertions. The integration
test in `scripts/hlstats_awards_py/tests/test_integration.py` drives the
default action set and serialises the resulting report for documentation in
`docs/hlstats_awards_py_reports.md`.
