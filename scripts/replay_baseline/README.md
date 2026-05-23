# Replay Baseline Artifacts

This directory holds the local baseline used to compare the legacy HLstatsX
runtime against the Python migration on identical replayed production logs.

**Fast multi-file Python import (stdin batch, not UDP):** canonical index and
links — [`../../docs/replay-fast-path.md`](../../docs/replay-fast-path.md).

**Residual-to-fix workflow:** use
[`../../docs/parity-debug-pipeline.md`](../../docs/parity-debug-pipeline.md)
to locate the source `.log`, run single-log parity, cut smaller windows, and
only then return to `narrow-1000`.

## Layout

- `legacy_prod_like/docker-compose.yml`:
  local prod-like legacy stack derived from the production Portainer compose.
- `comparison/legacy/docker-compose.yml`:
  isolated legacy comparison stack restored from the reset baseline.
- `comparison/python/docker-compose.yml`:
  isolated Python comparison stack restored from the same reset baseline. Its
  web service is built from this repository's current `web/` tree so replayed
  data can be inspected through the integrated RU i18n frontend.
- `snapshot-baseline.ps1`:
  capture a reusable reset baseline dump from the local prod-like DB.
- `restore-baseline.ps1`:
  restore that baseline into either comparison DB.
  Default mode is snapshot-first with automatic fallback to dump restore.
- `prune-small-logs.ps1`:
  remove undersized replay logs from `artifacts/` before a large corpus run.
- `artifacts/`:
  downloaded production data such as DB dumps, image archives, and weekly logs.

## Current intent

1. Keep one local prod-like legacy stack only as the source for baseline
   refreshes and admin actions.
2. Treat `artifacts/baseline_reset_20260418.sql.gz` as the canonical clean
   reset point for comparison runs.
3. Remove replay-noise logs under `15 KB` before a production-sized corpus run.
4. Restore that same baseline into isolated `legacy` and `python` stacks
   before every replay run.
5. Use legacy replay smoke as the first gate: if legacy cannot recreate
   statistics from the downloaded production logs, the comparison loop is not
   valid yet.
6. Only after legacy smoke passes, run the same fixture set through Python and
   diff the resulting DB state.

## Current state

- Local prod-like legacy stack is available on `http://127.0.0.1:8081/hlstats.php`.
- Canonical reset baseline dump exists at
  `artifacts/baseline_reset_20260418.sql.gz`.
- Legacy comparison stack is available on `http://127.0.0.1:8181/hlstats.php`.
- Python comparison stack web is available on `http://127.0.0.1:8281/hlstats.php`.
- The Python comparison web container now builds from the current product
  `web/` checkout, not the legacy upstream web image, and uses
  `comparison/python/web-config.php` to connect to the restored `hlstatsxce`
  database.
- Legacy replay smoke on `L0415056.log` succeeded from a clean baseline and
  recreated stats in the DB.
- Python worker/proxy startup against the restored baseline is fixed; both
  comparison services now stay up after rebuild/restart.
- Local rollback tags exist for the current Python runtime images:
  `python-hlstats-worker:replay-ready-20260418` and
  `python-proxy-daemon:replay-ready-20260418`.
- `hlstats_ftp_py` (`hlstats_py.runtime --stdin`) is now the default Python test
  contour replay/import path.
- `replay_python_log.py` remains available as an explicit UDP transport replay
  helper for dedicated transport tests. It wraps each line into a proxied
  envelope, preserves the logical source server identity selected by
  `--server-identity`, paces UDP sends, and waits for the worker to drain the
  tail. **Do not use it for multi-hundred-file table-diff gates:** throttled UDP
  is wall-clock slow; use `direct_import_artifacts.py` (stdin batch in the
  worker image) or `hlstats_ftp_py` instead — see `docs/test-plan.md` and
  `docs/audits/legacy-python-parity-20260423/performance.md`.
- `prune-small-logs.ps1` removed the empty undersized replay noise from the
  current production corpus:
  - before: `72,148` log files
  - removed `< 15 KB`: `30,572`
  - retained replay corpus: `41,576`
- `restore-baseline.ps1 -Stack python` now bootstraps two known replay source
  servers after every restore:
  - baseline parity server `172.19.0.1:27015`
  - CS 1.6 replay corpus server `37.230.137.48:27015`
- the new `37.230.137.48:27015` row is inserted as `game='cstrike'` and its
  `hlstats_Servers_Config` is copied from the baseline server so the Python
  comparison contour tracks it immediately after restore.
- `compare_stats_dbs.py` is now the canonical compact diff for parity work.
  It normalizes players/actions/servers and reports only replay-relevant
  statistical differences. Legacy `--stdin` import-tail alias/session metadata
  (`PlayerNames.lastuse/numuses`, `connection_time`) is intentionally excluded
  from that compact gate because it is driven by daemon finalization timing
  rather than gameplay semantics.
- Latest clean cycle result on `L0415056.log`:
  Python now reaches the late replay tail, creates the same `9` player rows as
  legacy, and `compare_stats_dbs.py` reports `0` logical replay differences in
  the configured statistical tables.
- Latest expanded clean cycle results on the current production fixture set:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, and `L0417051.log` all
  report `0` logical replay differences after the canonical loop
  `restore baseline -> legacy smoke -> Python replay -> compare_stats_dbs.py`.
- `L0417065.log` is now also clean in the compact parity gate because
  `compare_stats_dbs.py` normalizes the known legacy offline `--stdin`
  non-ASCII chat corruption in `hlstats_Events_Chat.message`. Python runtime
  storage still preserves the original Unicode payload.
- After rebuilding the Python comparison contour from the current workspace on
  `2026-04-18`, `hlstats_Players_History` is now populated on Python; the
  remaining work is matching legacy's event-date / skill / streak semantics
  rather than filling an empty table.
- The latest parity loop also added legacy-style frag skill calculation and
  end-of-streak `kill_streak_*` timing. As a result, the broad
  `hlstats_Players` / `hlstats_Players_History` skill drift is gone; the
  remaining player/history mismatch is now limited to `gatl` missing one
  `CTs_Win` reward and the separate `BanForLife` flush-time tail.

## Development loop

1. If the baseline itself must be refreshed, use the local prod-like stack,
   perform the reset from the admin UI, then run
   `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\snapshot-baseline.ps1`.
2. Before any large replay run, prune the disposable undersized logs from the
   working corpus:
   `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\prune-small-logs.ps1`
3. Before any replay run, restore the canonical baseline into both contours:
   `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy`
   and
   `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python`.
   - Force canonical dump restore (skip snapshot):
     `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python -ForceDumpRestore`
   - Rebuild snapshot after baseline changes:
     `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python -CreateSnapshot`
4. For the Python contour, confirm the post-restore bootstrap if the source
   identity matters for the run:
   - `172.19.0.1:27015` remains available for the canonical parity fixtures
   - `37.230.137.48:27015` is present as `cstrike` for the new CS 1.6 corpus
5. Validate the clean legacy baseline:
   players and frag events must both be `0` before replay.
6. Run a legacy smoke replay on a real production log. Canonical example:
   `Get-Content -Raw scripts\replay_baseline\artifacts\L0415056.log | docker run --rm -i --network legacy_hlstatsx_legacy_net startersclan/hlstatsx-community-edition:1.11.4-daemon --stdin --server-ip=172.19.0.1 --server-port=27015 --db-host=db:3306 --db-name=hlstatsxce --db-username=hlstatsxce --db-password=hlx123 --nodns-resolveip`
7. If legacy recreated statistics, keep the fixture set unchanged and run the
   equivalent replay on Python through the default stdin contour:
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1`
   If transport behavior is under test, run the explicit UDP helper instead:
   `python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts --server-identity 37.230.137.48:27015`
8. Inspect the replayed data through the RU frontend on the Python comparison
   web contour:
   - `http://127.0.0.1:8281/hlstats.php?mode=game&game=cstrike&lang=ru`
   - `http://127.0.0.1:8281/hlstats.php?mode=servers&server_id=2&game=cstrike&lang=ru`
   - `http://127.0.0.1:8281/hlstats.php?mode=players&game=cstrike&lang=ru`
9. Compare the two DB results with a dedicated diff script that ignores
   runtime-only metadata noise and reports only replay-relevant differences:
   `python scripts\replay_baseline\compare_stats_dbs.py`
10. Fix Python,
   then repeat from step 2. Do not reuse a dirty DB from a previous replay.

### First-divergence DB write trace

For narrow bug slices, use `parity_trace.py` before running another full
`narrow-1000` loop. It compares normalized DB write intents and reports the
first write that differs, so the debug window can be reduced to one file or a
small line range before changing runtime behavior.

Accepted inputs:

- JSONL query capture:
  `{"event_ref":"L0001:42","sql":"INSERT ... VALUES (%s)","params":[...]}`
- raw MySQL general-log query lines, useful for legacy Perl capture:
  `... Query\tINSERT INTO ...`

Example:

```powershell
python scripts\replay_baseline\parity_trace.py diff `
  --legacy scripts\replay_baseline\artifacts\legacy-writes.log `
  --python scripts\replay_baseline\artifacts\python-writes.jsonl `
  --unordered `
  --include-table-prefix hlstats_ `
  --ignore-table hlstats_Servers `
  --table hlstats_Events_PlayerActions `
  --param-contains "2024-01-06 00:18:10"
```

The tool filters read-only SQL, reassembles multiline legacy general-log SQL,
and normalizes statement shape, table, operation, and bound parameters. It
intentionally does not require byte-for-byte SQL equality because Python may
batch or parameterize writes differently from Perl. Prefer table/time filters
when investigating a concrete `compare_stats_dbs.py` residual.

For Python runtime captures, set `HLSTATS_DB_WRITE_TRACE_PATH` and use direct
stdin import so the trace records pre-batch storage writes:

```powershell
docker run --rm --network python_hlstatsx_python_net `
  -v "${PWD}\scripts:/app/scripts" `
  -v "${PWD}\scripts\replay_baseline\comparison\python\ftp_work:/tmp/ftp_work" `
  -e PYTHONPATH=/app/scripts:/app/scripts/proxy_daemon_py `
  -e HLSTATS_DB_WRITE_TRACE_PATH=/tmp/ftp_work/python-writes.jsonl `
  python-hlstats-worker `
  python /app/scripts/replay_baseline/direct_import_artifacts.py `
    --artifacts-dir /app/scripts/replay_baseline/artifacts `
    --configfile /app/hlstats.conf `
    --work-dir /tmp/ftp_work `
    --max-files 1 `
    --gs-ip 37.230.137.48 `
    --gs-port 27015 `
    --parser-backend python
```

For legacy captures, enable MariaDB `general_log` on `hlstatsx-legacy-db`
after baseline restore and before `legacy_import`, then export
`mysql.general_log.argument` after the import. Prefer `--unordered` for
general-log comparisons because Perl and Python do not emit writes in identical
order.

For the complete one-command workflow, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0105062.log `
  -Name rakza-kill-streak `
  -TraceTable hlstats_Events_PlayerActions `
  -TraceParamContains "2024-01-06 00:18:10"
```

## Current parity state

- On the canonical single-log loop (`L0415056.log`), the compact replay diff is
  now clean after:
  `restore baseline -> legacy smoke -> Python replay -> compare_stats_dbs.py`.
- On the current multi-fixture loop, the compact replay diff is also clean on:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`, and
  `L0417065.log`.
- Legacy offline `--stdin` non-ASCII chat corruption is handled in the compact
  diff: normalize it during comparison and keep it out of the gameplay
  parity gate unless exact byte-for-byte import emulation becomes
  product-relevant.
- Replay-semantic gameplay/statistical tables are the source of truth for this
  gate.
- Exact legacy `--stdin` import-finalize alias/session metadata remains outside
  the compact gate and should only be pursued if exact import-tail emulation
  becomes a separate requirement.

## Runtime rollback

- DB state rollback is handled only through
  `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack <legacy|python>`.
- Snapshot archives are stored under:
  `scripts/replay_baseline/artifacts/snapshots/<stack>/`.
- Snapshot reset is the default fast path; dump restore remains available with
  `-ForceDumpRestore` and is used automatically when snapshot restore fails.
- Python runtime rollback between iterations can use the tagged local images:
  `python-hlstats-worker:replay-ready-20260418` and
  `python-proxy-daemon:replay-ready-20260418`.
- Do not recapture the baseline dump unless the user explicitly performs a new
  intentional baseline refresh from the prod-like legacy admin UI.

## Ports

- prod-like legacy web: `8081`
- legacy comparison web: `8181`
- python comparison web: `8281`
- legacy comparison UDP ingress: `27600/udp`
- python comparison UDP ingress: `27601/udp`
