# Replay Baseline Artifacts

This directory holds the local baseline used to compare the legacy HLstatsX
runtime against the Python migration on identical replayed production logs.

## Layout

- `legacy_prod_like/docker-compose.yml`:
  local prod-like legacy stack derived from the production Portainer compose.
- `comparison/legacy/docker-compose.yml`:
  isolated legacy comparison stack restored from the reset baseline.
- `comparison/python/docker-compose.yml`:
  isolated Python comparison stack restored from the same reset baseline.
- `snapshot-baseline.ps1`:
  capture a reusable reset baseline dump from the local prod-like DB.
- `restore-baseline.ps1`:
  restore that baseline into either comparison DB.
- `artifacts/`:
  downloaded production data such as DB dumps, image archives, and weekly logs.

## Current intent

1. Keep one local prod-like legacy stack only as the source for baseline
   refreshes and admin actions.
2. Treat `artifacts/baseline_reset_20260418.sql.gz` as the canonical clean
   reset point for comparison runs.
3. Restore that same baseline into isolated `legacy` and `python` stacks
   before every replay run.
4. Use legacy replay smoke as the first gate: if legacy cannot recreate
   statistics from the downloaded production logs, the comparison loop is not
   valid yet.
5. Only after legacy smoke passes, run the same fixture set through Python and
   diff the resulting DB state.

## Current state

- Local prod-like legacy stack is available on `http://127.0.0.1:8081/hlstats.php`.
- Canonical reset baseline dump exists at
  `artifacts/baseline_reset_20260418.sql.gz`.
- Legacy comparison stack is available on `http://127.0.0.1:8181/hlstats.php`.
- Python comparison stack web is available on `http://127.0.0.1:8281/hlstats.php`.
- Legacy replay smoke on `L0415056.log` succeeded from a clean baseline and
  recreated stats in the DB.
- Python worker/proxy startup against the restored baseline is fixed; both
  comparison services now stay up after rebuild/restart.
- Local rollback tags exist for the current Python runtime images:
  `python-hlstats-worker:replay-ready-20260418` and
  `python-proxy-daemon:replay-ready-20260418`.
- `replay_python_log.py` is now the canonical local Python replay entrypoint
  for raw legacy logs. It wraps each line into a proxied envelope, preserves
  `172.19.0.1:27015`, paces UDP sends, and waits for the worker to drain the
  tail.
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
2. Before any replay run, restore the canonical baseline into both contours:
   `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy`
   and
   `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python`.
3. Validate the clean legacy baseline:
   players and frag events must both be `0` before replay.
4. Run a legacy smoke replay on a real production log. Canonical example:
   `Get-Content -Raw scripts\replay_baseline\artifacts\L0415056.log | docker run --rm -i --network legacy_hlstatsx_legacy_net startersclan/hlstatsx-community-edition:1.11.4-daemon --stdin --server-ip=172.19.0.1 --server-port=27015 --db-host=db:3306 --db-name=hlstatsxce --db-username=hlstatsxce --db-password=hlx123 --nodns-resolveip`
5. If legacy recreated statistics, keep the fixture set unchanged and run the
   equivalent replay on Python through a path that preserves the logical source
   server identity `172.19.0.1:27015`:
   `python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts\L0415056.log`
6. Compare the two DB results with a dedicated diff script that ignores
   runtime-only metadata noise and reports only replay-relevant differences:
   `python scripts\replay_baseline\compare_stats_dbs.py`
7. Fix Python,
   then repeat from step 2. Do not reuse a dirty DB from a previous replay.

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
