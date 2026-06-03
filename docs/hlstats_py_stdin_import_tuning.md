# HLstats Python STDIN Import Tuning

For **which entrypoints and orchestration** to use for fast multi-file parity
(direct import, FTP contour, what to avoid), see the canonical index
[`replay-fast-path.md`](replay-fast-path.md) — do not duplicate ad-hoc speed
recipes outside that map.

## Scope

This runbook documents performance-related runtime flags for high-volume stdin imports in:

- `python -m hlstats_py.runtime --stdin ...`
- `python -m hlstats_ftp_py ...` (batch mode and legacy per-file worker mode)

## Defaults Currently In Use

- `--stdin-verbose-events`: default `false`
  - Behavior: per-event `Recorded ...` logging is disabled by default.
- `--parser-backend`: default `python`
  - Allowed values: `python`, `native`.
- `--stdin-transaction-batch-size`: default `1000`
  - Behavior: for stdin imports, DB writes are committed every 1000 SQL operations.
  - Value `0` disables batching and keeps autocommit behavior.

## Why These Defaults

- Quiet-by-default logging removes terminal I/O bottlenecks on large replay corpora.
- `python` parser backend remains the conservative default for compatibility.
- Batch transaction size `1000` balances throughput and recovery granularity.

## Recommended Starting Profiles

- **Safe baseline (default):**
  - `--parser-backend python`
  - `--stdin-transaction-batch-size 1000`
- **Higher throughput trial:**
  - `--parser-backend native`
  - `--stdin-transaction-batch-size 2000` or `5000`
- **Debug investigation:**
  - add `--stdin-verbose-events`
  - keep `--stdin-transaction-batch-size 1000` unless diagnosing transaction behavior

## Example Commands

Runtime stdin import:

`python -m hlstats_py.runtime --configfile <path-to-hlstats.conf> --stdin --server-ip 37.230.137.48 --server-port 27015 --parser-backend python --stdin-transaction-batch-size 1000`

FTP batch import:

`python -m hlstats_ftp_py --gs-ip 37.230.137.48 --gs-port 27015 --ftp-ip <ftp-host> --ftp-usr <user> --ftp-pwd <pass> --ftp-dir <dir> --configfile <path-to-hlstats.conf> --parser-backend python --stdin-transaction-batch-size 1000`

## Operational Notes

- Batched transactions are enabled only for stdin replay/import paths.
- On import completion, pending writes are flushed and autocommit is restored.
- On storage errors while batching, pending transaction is rolled back before raising error.

## Verification Checklist

- Throughput:
  - compare parse/import wall time and lines/sec before vs after tuning.
- Correctness:
  - replay row counts and parity checks stay unchanged for the same manifest.
- Stability:
  - no sustained lock wait spikes or long commit stalls on DB host.

