# Ephemeral DB for write-path benchmarks

This folder defines a **separate** MariaDB instance so you can load a baseline dump
and run `hlstats_py.runtime --stdin` benchmarks **without** touching the main
comparison Python stack (`scripts/replay_baseline/comparison/python`, port **3327**,
container `hlstatsx-python-db`).

## Ports and names

| Resource | Ephemeral (this compose) | Main Python comparison |
|----------|--------------------------|-------------------------|
| Host DB port | **3328** | 3327 |
| DB container | `hlstatsx-writebench-db` | `hlstatsx-python-db` |
| Compose project | pass `-p hlstatsxwritebench` | default / `python` |

## 1. Start ephemeral DB

From repository root:

```powershell
docker compose -p hlstatsxwritebench -f scripts/replay_baseline/bench_ephemeral/docker-compose.yml up -d db
```

Wait until healthy (`docker ps` shows healthy).

## 2. Load schema + data (once per volume)

Use the same canonical dump as parity restore (gzip). Example:

```powershell
$dump = "scripts\replay_baseline\artifacts\baseline_reset_20260418.sql.gz"
docker run --rm `
  --network container:hlstatsx-writebench-db `
  -v "${PWD}/${dump}:/dump.sql.gz:ro" `
  mariadb:10.11 bash -c "gunzip -c /dump.sql.gz | mariadb -h 127.0.0.1 -uroot -proot123 hlstatsxce"
```

This writes **only** into the ephemeral volume (`hlstatsx_writebench_mysql`), not into `hlstatsx_python_db`.

## 3. Run benchmark (host Python)

```powershell
$env:PYTHONPATH = "scripts;scripts\proxy_daemon_py"
python scripts/replay_baseline/bench_write_path.py `
  --mode subprocess `
  --lines 300 `
  --configfile scripts/replay_baseline/bench_ephemeral/hlstats.host.conf `
  --server-ip 172.19.0.1 `
  --server-port 27015
```

Defaults in `bench_write_path.py` already point `--configfile` at this file and
use `172.19.0.1` / `27015`, so you can shorten to:

`python scripts/replay_baseline/bench_write_path.py --mode subprocess --lines 300`

`--server-ip` / `--server-port` must match `hlstats_Servers` in the loaded baseline
(default baseline row uses `172.19.0.1` and `27015`).

## 4. Tear down ephemeral stack

```powershell
docker compose -p hlstatsxwritebench -f scripts/replay_baseline/bench_ephemeral/docker-compose.yml down -v
```

`-v` removes the ephemeral data volume only.

## Automation

- **Chat-line stdin micro-bench** (300 *lines*, one process): `Run-WriteBenchEphemeral.ps1`
- **Multi-file log import** (300 separate `*.log` files, same code path as `hlstats_ftp_py` batch): `Run-LogFilesBenchEphemeral.ps1`  
  Uses `direct_import_artifacts.py --file-count 300`: if `artifacts/` has fewer than 300 logs, files are **replicated** round-robin into `work/bench_staged_logs` until there are 300 files (real disk copies, then full import).

Example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\Run-LogFilesBenchEphemeral.ps1 -FileCount 300
```

`direct_import_artifacts.py` defaults to **172.19.0.1:27015** (`--gs-ip` / `--gs-port`) to match `baseline_reset_*.sql.gz`; override if your dump uses another `hlstats_Servers` row.
