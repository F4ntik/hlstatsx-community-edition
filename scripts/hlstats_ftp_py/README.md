# hlstats_ftp_py

Python replacement for the historical `HLStatsFTP/hlstats-ftp.pl` utility:
incremental `*.log` fetch over FTP and import via
`python -m hlstats_py.runtime --stdin` (no Perl).

## Requirements

- Python 3.10+
- Working HLstats DB and a readable `hlstats.conf` (same file the PHP stack uses)
- For the default durable FTP mode, the P1 migrations applied to the target
  database in order:
  `sql/migrations/2026_07_22_ftp_checkpoint.sql`, then
  `sql/migrations/2026_07_22_0500.sql`
- Install `hlstats_py`/`hlx_core` in the Python environment used by the FTP
  runner and worker subprocess.

## Enabling durable FTP on an existing database

The migration follows the native HLstatsX `sql/migrations/` convention: it is
an attended, operator-applied SQL file rather than an application-startup
migration runner. Schedule a maintenance window because `ALTER TABLE` can lock
or rebuild tables. Take a verified backup first and do not use `mysql --force`:
an interrupted conversion must be inspected before continuing.

From the repository root, apply the files in this exact order (substitute the
normal database connection arguments and database name):

```sh
mysql -h DB_HOST -u DB_USER -p DB_NAME < sql/migrations/2026_07_22_ftp_checkpoint.sql
mysql -h DB_HOST -u DB_USER -p DB_NAME < sql/migrations/2026_07_22_0500.sql
```

Before enabling the default FTP mode, verify that the checkpoint plus all
importer write tables use InnoDB:

```sql
SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
    'hlstats_FTP_Checkpoints', 'hlstats_Actions', 'hlstats_Events_Admin',
    'hlstats_Events_ChangeTeam', 'hlstats_Events_Chat',
    'hlstats_Events_Connects', 'hlstats_Events_Disconnects',
    'hlstats_Events_Entries', 'hlstats_Events_Frags',
    'hlstats_Events_PlayerActions', 'hlstats_Events_PlayerPlayerActions',
    'hlstats_Events_Statsme', 'hlstats_Events_Statsme2',
    'hlstats_Events_Suicides', 'hlstats_Events_TeamBonuses',
    'hlstats_Events_Teamkills', 'hlstats_Maps_Counts',
    'hlstats_PlayerNames', 'hlstats_Players', 'hlstats_Players_History',
    'hlstats_PlayerUniqueIds', 'hlstats_Servers', 'hlstats_Weapons'
  )
ORDER BY TABLE_NAME;
```

The query must return 23 rows, all with `ENGINE = InnoDB`. The FTP runner
repeats this check at startup and fails closed if a table is missing or has a
different engine. Use `--legacy-file-marker` only when deliberately retaining
the old non-atomic behavior.

## Flags (Perl → Python)

| Perl | Python |
|------|--------|
| `--gs-ip` | `--gs-ip` (also `--server-ip` for the worker) |
| `--gs-port` | `--gs-port` |
| `--ftp-ip` | `--ftp-ip` (default: `--gs-ip`) |
| `--ftp-usr` | `--ftp-usr` |
| `--ftp-pwd` | `--ftp-pwd` or env `HLSTATS_FTP_PASSWORD` (CLI overrides env when `--ftp-pwd` is passed) |
| *(FTP port 21 implied)* | `--ftp-port` (default `21`; set e.g. `2121` when the server is published on a mapped port) |
| `--ftp-dir` | `--ftp-dir` |
| `--quiet` | `--quiet` |
| *(implicit `./hlstats.conf` via cwd)* | `--configfile` **(required)** path to `hlstats.conf` |
| n/a | `--legacy-file-marker` (explicitly use historical local marker; not durable) |
| n/a | `--legacy-per-file-runtime` (fallback mode; requires `--legacy-file-marker`) |
| n/a | `--disable-mlsd` (force NLST+MDTM even if MLSD is supported) |

The MySQL `hlstats_FTP_Checkpoints` row is authoritative. The historical
`hlstats-ftp-<gs_ip>-<gs_port>.last` file is read once to bootstrap an empty
database cursor and is mirrored only after a successful DB commit; it is no
longer the progress authority. The temporary directory remains
`hlstats-ftp-<gs_ip>-<gs_port>.tmp`.

## Behaviour vs Perl

- Uses MLSD metadata listing when available (fallback to NLST+MDTM), sorts by time, **excludes the single newest file** (active log), then resumes after the durable `(mtime, filename)` cursor. A first run bootstrapped from `.last` keeps the historical strict-mtime cutoff.
- **Newest-file exclusion** uses max modification time (deterministic), not fragile `LIST -t` ordering on exotic FTP servers.
- Default import mode is batch stdin: one runtime process handles all queued files in a run.
- In default durable mode, each completed file advances its DB cursor in the
  same transaction as its writes; the final file also contains import-tail
  writes. A failed or unacknowledged commit stops the run without retrying.
- `--legacy-file-marker` and `--legacy-per-file-runtime` preserve old
  operations only as an explicit compatibility escape hatch. They cannot
  guarantee atomic progress or exactly-once ingestion.
- Default durable mode refuses to start if any table written by FTP import is
  not InnoDB. The checkpoint migration creates only its new table; migrate the
  existing importer write tables before use. Only the explicit
  `--legacy-file-marker` compatibility mode can run a mixed-engine legacy
  schema, and it remains non-atomic.
- Multiline GoldSrc records are merged in the worker stdin path (`hlstats_py.runtime`); the FTP tool streams raw file bytes.

## Example cron

```cron
# Run every 10 minutes from the directory that holds .last / .tmp
*/10 * * * * cd /opt/hlstatsx/scripts && HLSTATS_FTP_PASSWORD='***' /opt/hlstatsx/.venv/bin/python -m hlstats_ftp_py --gs-ip=GAME_IP --gs-port=27015 --ftp-usr=loguser --ftp-dir=/cstrike/logs --configfile=/opt/hlstatsx/web/hlstats.conf --quiet
```

Adjust paths and use a root-only file or secret manager for the password instead of inline env when possible.
