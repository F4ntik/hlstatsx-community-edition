# FTP log import in the Python comparison stack

The compose file adds **`log-ftp`** (`fauria/vsftpd`). Its FTP root is a **bind mount from the host** — nothing is copied into the image.

- **Default:** [`ftp_logs/`](./ftp_logs/) (small fixtures next to this compose file).
- **Large corpus:** set **`HLSTATS_FTP_LOGS_HOST_PATH`** to an **absolute** path on your machine (e.g. `scripts/replay_baseline/artifacts` with thousands of `.log` files). Compose mounts that directory straight into `/home/vsftpd/hlxslogs` inside the container.

Copy [`env.ftp-logs.example`](./env.ftp-logs.example) to `env.ftp-logs`, set the variable, then:

```powershell
docker compose --env-file scripts/replay_baseline/comparison/python/env.ftp-logs -f scripts/replay_baseline/comparison/python/docker-compose.yml up -d log-ftp
```

Or export for one shell:

```powershell
$env:HLSTATS_FTP_LOGS_HOST_PATH = (Resolve-Path "scripts\replay_baseline\artifacts").Path
docker compose -f scripts/replay_baseline/comparison/python/docker-compose.yml up -d log-ftp
```

Ensure Docker Desktop **file sharing** includes that drive/path on Windows.

## Credentials (dev only)

| | |
|---|---|
| Host (from your machine) | `127.0.0.1` |
| Port | `2121` |
| User | `hlxslogs` |
| Password | `hlxftp123` |
| Remote directory for listings | `/` (home of `hlxslogs`) |

Passive mode is configured for **`PASV_ADDRESS=127.0.0.1`** with ports **21100–21110** published; this matches clients running **`hlstats_ftp_py` on the host** (not inside Docker).

## Optional: tiny `ftp_logs` smoke mtimes

When using only the default **`ftp_logs/`** two-file fixture, `hlstats_ftp_py` skips the newest `*.log` by mtime; after checkout mtimes may tie. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Seed-FtpMtimes.ps1
```

When binding **`artifacts/`**, real file mtimes are usually enough; no seed script needed.

## Full contour: baseline + FTP from `artifacts/` (thousands of logs)

From repo root, one script (restarts compose, mounts `scripts/replay_baseline/artifacts` on FTP, restores DB, imports into **`37.230.137.48:27015`** so the replay server shows stats in web):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild
```

Default **caps at 400 files** per run (each file = one worker subprocess). Continue with another run (`.last` advances) or use `-MaxImportFiles 2000`, or **`-NoCap`** for the full queue (very long; MDTM over ~40k names alone takes time).

## Typical smoke

From repo root `hlstatsx-community-edition-python-i18n`:

1. Start DB + FTP (and optionally the rest of the stack):

   ```powershell
   docker compose -f scripts/replay_baseline/comparison/python/docker-compose.yml up -d db log-ftp
   ```

2. Restore the baseline into the Python DB (requires `artifacts\baseline_reset_20260418.sql.gz`):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python
   ```

3. Import over FTP into the Python worker (**no UDP**).

   **Recommended on Windows:** run inside the worker image (includes `mysqlclient`). Use **`--ftp-active`** so transfers work against `log-ftp` in Docker (PASV is tuned for `127.0.0.1` from the host). State persists under `ftp_work/` via a bind mount:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-FtpImportInDocker.ps1
   ```

   **From the host** (needs a Python env with `mysqlclient` built for your OS): passive FTP to published port `2121`:

   ```powershell
   $root = Resolve-Path .
   $env:PYTHONPATH = "$root\scripts;$root\scripts\proxy_daemon_py"
   $env:HLSTATS_FTP_PASSWORD = "hlxftp123"
   python -m hlstats_ftp_py `
     --gs-ip 172.19.0.1 --gs-port 27015 `
     --ftp-ip 127.0.0.1 --ftp-port 2121 --ftp-usr hlxslogs --ftp-dir / `
     --configfile "$root\scripts\replay_baseline\comparison\python\hlstats.host.conf" `
     --cwd "$root\scripts\replay_baseline\comparison\python\ftp_work"
   ```

Use **`172.19.0.1:27015`** so the worker matches the canonical baseline server row after restore.

State files (`hlstats-ftp-172.19.0.1-27015.last` and `.tmp`) land under `ftp_work/` (gitignored).

## Linux / macOS

Same compose and restore; export `PYTHONPATH` with `:` separators; use paths to `hlstats.host.conf` and `ftp_work` accordingly. Ensure passive ports 21100–21110 are free if the client runs on the host.
