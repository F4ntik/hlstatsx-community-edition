# hlstats_ftp_py

Python replacement for [`HLStatsFTP/hlstats-ftp.pl`](../HLStatsFTP/hlstats-ftp.pl): incremental `*.log` fetch over FTP and import via `python -m hlstats_py.runtime --stdin` (no Perl).

## Requirements

- Python 3.10+
- Working HLstats DB and a readable `hlstats.conf` (same file the PHP stack uses)
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
| n/a | `--legacy-per-file-runtime` (fallback mode: one worker subprocess per file) |
| n/a | `--disable-mlsd` (force NLST+MDTM even if MLSD is supported) |

State files match Perl names in the working directory: `hlstats-ftp-<gs_ip>-<gs_port>.last`, `hlstats-ftp-<gs_ip>-<gs_port>.tmp`.

## Behaviour vs Perl

- Uses MLSD metadata listing when available (fallback to NLST+MDTM), sorts by time, **excludes the single newest file** (active log), then downloads files with `mtime` strictly greater than `.last`.
- **Newest-file exclusion** uses max modification time (deterministic), not fragile `LIST -t` ordering on exotic FTP servers.
- Default import mode is batch stdin: one runtime process handles all queued files in a run.
- `--legacy-per-file-runtime` preserves the old behavior for rollback/debug.
- Multiline GoldSrc records are merged in the worker stdin path (`hlstats_py.runtime`); the FTP tool streams raw file bytes.

## Example cron

```cron
# Run every 10 minutes from the directory that holds .last / .tmp
*/10 * * * * cd /opt/hlstatsx/scripts && HLSTATS_FTP_PASSWORD='***' /opt/hlstatsx/.venv/bin/python -m hlstats_ftp_py --gs-ip=GAME_IP --gs-port=27015 --ftp-usr=loguser --ftp-dir=/cstrike/logs --configfile=/opt/hlstatsx/web/hlstats.conf --quiet
```

Adjust paths and use a root-only file or secret manager for the password instead of inline env when possible.
