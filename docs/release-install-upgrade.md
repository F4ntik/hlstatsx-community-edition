# Install and upgrade packages

Build the exact committed candidate with:

```text
python scripts/build_release.py --revision HEAD --output-dir /outside/checkout/release
```

The builder emits separate `install.zip` and `upgrade.zip` archives plus a JSON
manifest containing the full source commit, archive SHA-256 values and every
packaged file's SHA-256. Output names contain the short commit. Existing output
is never overwritten. Only committed files are read; uncommitted fixes cannot
silently enter an accepted archive. Archive timestamps are fixed for repeatability.

## Fresh installation

Use the **install** archive only with an empty installation directory and a new
database. Copy `web/config.php.example` to `web/config.php`, and
`scripts/hlstats.conf.example` to `scripts/hlstats.conf`, then set installation
credentials. Import `sql/install.sql` into the new database. Follow
`python_migration_usage_guide.md` for the Python services and
`python_fullstack_docker.md` for Docker setup.

The fresh package includes the 25 native Counter-Strike map images and matching
fresh-install calibration seeds, along with BSP-derived geometry. Their origin
and generation evidence are recorded in the source checkout's
`docs/audits/modern-heatmap-explorer/steam-maps-20260908/` and
`web/hlstatsimg/heatmap-geometry/README.md`. Geometry is a visual reference; it does
not automatically define floors or playable regions. The local GoldSrc/BSP
acquisition tools and laboratory exports are excluded from release archives.

## Updating an existing installation

Use the **upgrade** archive. Never overlay an install archive or an unfiltered
source checkout onto an existing site. Before updating, stop event ingestion,
put the web site into maintenance, and retain a complete database backup and a
copy of the installation files. Verify the backup can be restored to a separate
database before proceeding. Keep both backups together for rollback.

Extract the upgrade archive over the existing installation. It deliberately
contains no `heatmaps/`, `web/hlstatsimg/`, or `sql/install*` entries. Existing map
images, overviews, floor images, generated images and their database calibration
remain together. Live configuration files are never overwritten: example files
have a `.example` suffix. Apply the explicit database upgrade procedure described
in the administration-security upgrade runbook, while the site remains offline.
Do not import `install.sql` into an existing database.

The new native map images are a fresh-install default, **not an automatic map
upgrade**. Existing installations keep their maps. If an operator wants a new
map later, use the calibration editor during maintenance and validate its image,
projection and all floors as one operator-managed change with a backup. Do not
copy the native images independently over old calibration. Hash verification
disables bundled BSP geometry when it does not match the installed base image.

Clear derived heatmap payload caches after updating; keep original images and
calibration. Select the desired Explorer mode explicitly in administration
(`HeatmapExplorerBeta`), then verify EN and RU, a player page, a map, a map with
floors, administrator login, and denied restricted-administrator actions. Resume
ingestion only after these checks. To roll back, stop ingestion again and restore
the matching previous files **and database**, then verify the same pages before
restarting.

## Distribution boundary

Archives exclude replay corpora, database dumps, historical audit captures, test
fixtures, caches, local index databases, temporary helpers, and local GeoIP data.
These remain available in the source workspace where appropriate. GeoIP data must
be configured separately. The public HTTP updater is disabled; migration files
are retained for the trusted CLI upgrade route.

The conservative smooth heatmap can hide a sparse point next to a thin blocked
region. Use points or cells to inspect boundaries; this is a documented rendering
limitation and does not delete stored events.
