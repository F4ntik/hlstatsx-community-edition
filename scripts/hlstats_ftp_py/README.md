# hlstats_ftp_py

Python replacement for the historical `HLStatsFTP/hlstats-ftp.pl` utility:
incremental `*.log` fetch over FTP and import via
`python -m hlstats_py.runtime --stdin` (no Perl).

## Requirements

- Python 3.10+
- Working HLstats DB and a readable `hlstats.conf` (same file the PHP stack uses)
- The P1 migration `sql/migrations/2026_07_22_ftp_checkpoint.sql` applied to
  the target database (the new checkpoint table must be InnoDB)
- Install `hlstats_py`/`hlx_core` in the Python environment used by the FTP
  runner and worker subprocess.

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
