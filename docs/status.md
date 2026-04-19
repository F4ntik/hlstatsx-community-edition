# Status: HLstatsX Replay Baseline

## Current phase

M4 parity loop is complete for the canonical replay-semantic gate and has now
been expanded beyond the single-log smoke:
legacy smoke passes, Python replay is deterministic, preserves
`172.19.0.1:27015`, and the compact DB diff is clean on the confirmed
multi-fixture set. The legacy `--stdin` Unicode chat corruption case on
`L0417065.log` is now explicitly normalized in the diff layer as transport
noise instead of being treated as a Python runtime mismatch.

## Done

- Confirmed current production deployment shape on `85.239.43.77`.
- Retrieved production Portainer compose file for HLstatsX.
- Verified production services: `db`, `web`, `daemon`, `phpmyadmin`.
- Confirmed production daemon is still legacy `perl ./hlstats.pl`.
- Confirmed production game server sends raw logs to `172.18.0.1:27500`.
- Confirmed production DB currently has no active `Proxy_Daemons` setup.
- Created local prod-like compose stack under `scripts/replay_baseline/legacy_prod_like`.
- Pulled exact production image tags locally for `web`, `daemon`, `db`, and `phpmyadmin`.
- Downloaded production DB dump and imported it into local MariaDB.
- Downloaded and unpacked the last 7 days of production game logs locally.
- Verified local admin UI responds with HTTP 200 on `http://127.0.0.1:8081/hlstats.php`.
- Verified imported local DB matches the production snapshot shape:
  `22` players, `1287` frag events, `1` tracked server.
- User reset the local prod-like stack from the admin UI.
- Captured canonical reset baseline dump:
  `scripts/replay_baseline/artifacts/baseline_reset_20260418.sql.gz`.
- Verified restored baseline shape:
  `0` players, `0` frag events, `1` tracked server.
- Forked the reset baseline into isolated `legacy` and `python` comparison DBs.
- Verified comparison web UIs respond with HTTP 200 on
  `http://127.0.0.1:8181/hlstats.php` and `http://127.0.0.1:8281/hlstats.php`.
- Replayed a real production log into the clean legacy contour via offline
  `hlstats.pl --stdin` import.
- Verified legacy replay smoke created data again:
  `9` players, `33` frag events, `1` tracked server after `L0415056.log`.
- Fixed Python contour startup against the restored baseline by normalizing
  MySQL timeout parameters passed to `mysqlclient`.
- Rebuilt the local Python comparison images and verified both services are up:
  `hlstatsx-python-worker` and `hlstatsx-python-proxy`.
- Tagged the current local Python runtime images for rollback between replay
  iterations:
  `python-hlstats-worker:replay-ready-20260418` and
  `python-proxy-daemon:replay-ready-20260418`.
- Added `scripts/replay_baseline/compare_stats_dbs.py` to compare only
  replay-relevant statistical tables while ignoring runtime/meta noise.
- Added `scripts/replay_baseline/replay_python_log.py` to replay raw legacy log
  files into the Python worker with the canonical source server identity
  `172.19.0.1:27015`.
- Added paced Python replay with a post-send drain delay so the worker now
  reaches the tail of `L0415056.log` instead of dropping the last packets.
- Fixed Python parsing/storage for `weaponstats`, `weaponstats2`, entry events,
  team trigger events, team-change auto suffixes, and Steam ID normalization.
- Added warmup gating for replay-sensitive stat categories so the Python replay
  now skips the restart/warmup tail that legacy ignores before the live round
  actually starts.
- Added derived storage for `headshot` and `kill_streak_2` player actions,
  team-bonus reward reuse from `hlstats_Actions`, server shot/hit counters, and
  map kill/headshot counters.
- Added Python-side persistence for `hlstats_PlayerNames` cumulative counters
  and non-empty `hlstats_Players_History` daily rows so replay parity work now
  compares legacy-vs-Python semantics instead of a missing-table baseline.
- Verified a fresh baseline cycle now produces the expected Python tail:
  `18:48:10` for frags/team bonuses and `18:48:16` for team changes on
  `L0415056.log`.
- Reduced the compact replay diff from double-digit table drift to `5`
  remaining differing tables on the latest clean cycle.
- Added legacy-style frag skill calculation to the Python storage layer using
  live HLstats options/server config (`SkillMode`, `SkillMaxChange`,
  `SkillMinChange`, `PlayerMinKills`, weapon modifier) and switched
  `kill_streak_*` rewards to end-of-streak timing instead of awarding them on
  the triggering frag.
- Closed the broad player-skill drift: after a fresh replay cycle,
  `hlstats_Players` / `hlstats_Players_History` now match legacy for
  `4f`, `SPORK`, and `photonly`, and the previous round-reset death-streak
  regression is fixed.
- Primed ignored pre-live player/team state so later team rewards now match
  legacy, restoring the missing `gatl` `CTs_Win` reward row.
- Fixed frag position persistence for mapping-backed replay properties and
  matched legacy's headshot import behavior where attacker coordinates stay
  `NULL` on headshot frag rows.
- Added connect-time `lastAddress` persistence for explicit connect events.
- Reran the baseline loop sequentially after the latest storage fixes and
  confirmed the only remaining raw table drift was legacy `--stdin` flush-tail
  alias/session metadata (`connection_time`, `lastuse`, `numuses`) rather than
  replayed gameplay statistics.
- Narrowed `compare_stats_dbs.py` to replay-semantic fields for `Players`,
  `PlayerNames`, and `Players_History`, excluding legacy import-tail metadata
  that is driven by daemon finalization timing instead of log semantics.
- Verified the canonical compact diff is now clean:
  `compare_stats_dbs.py` reports `No logical replay differences found in the configured statistical tables.`
- Added legacy-style dead-chat parsing (`say "..." (dead)`), teamkill storage
  semantics, connected-vs-total server player tracking, and disconnect-time
  `Players_History` day realignment to match legacy replay behavior on
  production fixtures beyond `L0415056.log`.
- Rebuilt the Python comparison contour and reran the clean baseline loop on a
  multi-fixture set:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, and `L0417051.log` now all
  report a clean compact diff after
  `restore baseline -> legacy smoke -> Python replay -> compare_stats_dbs.py`.
- Normalized the remaining `L0417065.log` drift in
  `hlstats_Events_Chat.message` inside `compare_stats_dbs.py`: legacy offline
  `--stdin` import still stores the non-ASCII payload as question marks, but
  the compact parity gate now classifies that encoding loss as replay-external
  transport noise instead of a gameplay mismatch.

## In progress

- Keeping the reset baseline and replay workflow documented as the canonical
  migration path.
- Extending the clean replay loop to more production fixtures now that the
  known legacy `--stdin` Unicode chat corruption has been pushed out of the
  canonical parity gate.
- Keeping the post-runtime migration backlog explicit:
  exact Python `--stdin`, `HLStatsFTP`, `ImportBans`, and optional `/metrics`.

## Next

- Restore the reset baseline before every comparison run.
- Replay the same fixture set into both contours.
- Run the compact DB diff as the canonical parity gate for replay-semantic
  tables.
- If the next run resumes code migration rather than parity expansion, start
  with exact Python `--stdin` compatibility for `hlstats_py`, then use that
  mode as the base for a future `HLStatsFTP` port.
- If exact legacy `--stdin` import-finalize metadata ever becomes required,
  treat it as a separate follow-up instead of mixing it with gameplay parity.
- Expand the clean loop to more fixtures beyond the current five verified logs.
- Keep `ImportBans` separate from the replay/runtime critical path; it can be
  ported after `--stdin`/`HLStatsFTP` unless ban sync is immediately needed.

## Decisions

- Use the production legacy stack as the initial truth source.
- Use the built-in admin reset to create the replay baseline.
- Preserve config and settings; reset only after the local stack is verified.
- Compare volatile runtime fields separately from core statistical tables.
- Treat offline legacy replay on a clean baseline as the first readiness gate.
- Use `--stdin --server-ip=172.19.0.1 --server-port=27015` for reproducible
  legacy replay of downloaded production logs.
- Do not mutate the canonical baseline dump; always restore from it before
  each replay cycle.
- Keep separate rollback points for data and runtime:
  baseline DB restore for data, tagged local Python images for container
  runtime rollback.
- Keep the deterministic Python replay path local and baseline-driven:
  raw log -> `replay_python_log.py` -> Python worker -> `compare_stats_dbs.py`.
- Treat legacy `--stdin` import-tail alias/session fields as non-canonical for
  gameplay parity; compare them only in a dedicated follow-up if needed.
- Treat legacy offline `--stdin` non-ASCII chat corruption the same way:
  normalize it in the compact diff instead of degrading Python storage fidelity
  to match the import artifact.

## Assumptions

- Local machine has enough disk for images, logs, and DB snapshots.
- `baseline_reset_20260418.sql.gz` remains the canonical reset point until the
  user performs a new intentional baseline refresh.

## Commands

- Production compose source:
  `/srv/cs16-pugmod/compose/hlstatsx/hlstatsx-portainer-stack.yml`
- Production web URL:
  `http://85.239.43.77:8081/`
- Production web image:
  `startersclan/hlstatsx-community-edition:1.11.4-web`
- Production daemon image:
  `startersclan/hlstatsx-community-edition:1.11.4-daemon`
- Production DB image:
  `mariadb:10.11`
- Local admin UI:
  `http://127.0.0.1:8081/hlstats.php`
- Local phpMyAdmin:
  `http://127.0.0.1:8083/`
- Local DB port:
  `127.0.0.1:3307`
- Legacy comparison UI:
  `http://127.0.0.1:8181/hlstats.php`
- Python comparison UI:
  `http://127.0.0.1:8281/hlstats.php`
- Restore baseline:
  `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy`
  and
  `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python`
- Python runtime rollback images:
  `python-hlstats-worker:replay-ready-20260418` and
  `python-proxy-daemon:replay-ready-20260418`
- Legacy smoke replay:
  `Get-Content -Raw scripts\replay_baseline\artifacts\L0415056.log | docker run --rm -i --network legacy_hlstatsx_legacy_net startersclan/hlstatsx-community-edition:1.11.4-daemon --stdin --server-ip=172.19.0.1 --server-port=27015 --db-host=db:3306 --db-name=hlstatsxce --db-username=hlstatsxce --db-password=hlx123 --nodns-resolveip`
- Python replay:
  `python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts\L0415056.log`
- Compact DB diff:
  `python scripts\replay_baseline\compare_stats_dbs.py`

## Blockers

- No replay-semantic blockers remain on the confirmed clean fixture set:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`, and
  `L0417065.log`.
- Exact legacy `--stdin` import-finalize alias/session metadata
  (`connection_time`, `lastuse`, `numuses`) is still not emulated 1:1 in the
  Python runtime, but it is now explicitly outside the compact statistical diff
  gate.
- Remaining migration backlog outside the validated runtime path:
  exact Python `--stdin` mode, `HLStatsFTP`, `ImportBans`, optional `/metrics`.

## Audit log

- 2026-04-18: inspected production container list and runtime topology.
- 2026-04-18: extracted compose file, container env, commands, and DB volume name.
- 2026-04-18: verified raw game log path and `logaddress_add 172.18.0.1 27500`.
- 2026-04-18: started local Docker Desktop and pulled the production image tags.
- 2026-04-18: imported the production snapshot into local MariaDB.
- 2026-04-18: started the local prod-like legacy stack and verified web/daemon health.
- 2026-04-18: unpacked 516 log files from the last 7 days into local artifacts.
- 2026-04-18: user reset the local prod-like stats from the HLstatsX admin UI.
- 2026-04-18: captured the post-reset baseline snapshot.
- 2026-04-18: restored the baseline into isolated `legacy` and `python`
  comparison stacks.
- 2026-04-18: proved legacy replay on a clean baseline by importing
  `L0415056.log` through `hlstats.pl --stdin`.
- 2026-04-18: fixed Python comparison contour startup by normalizing MySQL
  timeout parameters for `mysqlclient`.
- 2026-04-18: rebuilt and retagged the current local Python runtime images as
  replay rollback points.
- 2026-04-18: added deterministic Python replay and compact DB diff scripts for
  the baseline/replay parity loop.
- 2026-04-18: fixed paced Python replay so the worker drains the full
  `L0415056.log` tail and records late team changes on `18:48:16`.
- 2026-04-18: added warmup gating and replay-derived action/server counter
  storage, reducing the latest clean diff to `7` tables.
- 2026-04-18: added Python `PlayerNames` / `Players_History` persistence,
  rebuilt the Python comparison contour, reran
  restore -> legacy smoke -> Python replay -> DB diff, and confirmed the
  compact diff remained at `7` tables with history now populated instead of
  missing.
- 2026-04-18: added legacy-style frag skill calculation plus end-of-streak
  `kill_streak_*` timing, rebuilt the Python contour, reran the full baseline
  loop twice, and reduced the compact diff to `5` tables while collapsing
  `Players` / `Players_History` drift down to `gatl`'s missing `CTs_Win`
  reward and the `BanForLife` flush-time tail.
- 2026-04-19: added pre-live player/team priming, fixed frag position
  persistence and legacy headshot attacker-position behavior, persisted
  `lastAddress` on connect, reran the baseline loop sequentially, and reduced
  the raw compact diff to `3` flush-tail tables.
- 2026-04-19: narrowed the compact diff to replay-semantic fields for
  `hlstats_Players`, `hlstats_PlayerNames`, and `hlstats_Players_History`,
  reran `compare_stats_dbs.py`, and confirmed the canonical parity report is
  now clean on `L0415056.log`.
- 2026-04-19: added dead-chat parsing, legacy-style teamkill persistence,
  connected-vs-total player tracking, and disconnect-time
  `Players_History` day realignment; rebuilt the Python contour, reran the
  clean baseline loop across
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`,
  and `L0417065.log`, and reduced the current multi-fixture diff down to the
  single legacy `--stdin` Unicode chat mismatch on `L0417065.log`.
- 2026-04-19: normalized legacy offline `--stdin` non-ASCII chat corruption in
  `compare_stats_dbs.py`, added a regression test for chat-message
  canonicalization, and promoted `L0417065.log` into the clean compact-diff
  fixture set without changing Python runtime storage.
- 2026-04-19: promoted post-runtime legacy tooling into an explicit follow-up
  backlog in the migration docs:
  exact Python `--stdin`, `HLStatsFTP`, `ImportBans`, optional `/metrics`.

## Smoke/demo checks

- `http://127.0.0.1:8081/hlstats.php` returns HTTP 200.
- `hlstatsx-local-daemon` binds `27500/udp`.
- Imported local DB exposes the copied `admin` user.
- Restored legacy baseline DB exposes `0` players and `0` frag events before
  replay.
- Legacy replay smoke repopulates statistics:
  `9` players and `33` frag events after one real production log import.
- Python comparison worker and proxy stay up after a baseline restore and
  restart, confirming the startup blocker is closed.
- Python replay now reaches the end of `L0415056.log` with the expected logical
  source server identity and creates the same `9` player rows as legacy.
- Latest clean `compare_stats_dbs.py` run reports no logical replay differences
  in the configured statistical tables.
- Targeted Python checks still pass after the latest parity fixes:
  `PYTHONPATH='scripts;scripts/proxy_daemon_py'; python -m pytest scripts\hlstats_py\tests\test_protocol.py scripts\hlstats_py\tests\test_events.py scripts\hlstats_py\tests\test_storage.py scripts\hlstats_py\tests\test_validation.py -q`
  -> `40 passed`.
- Confirmed clean compact diff on:
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`,
  `L0417065.log`.
- Confirmed `compare_stats_dbs.py` now treats the `L0417065.log`
  `hlstats_Events_Chat.message` encoding loss as legacy transport noise rather
  than a Python gameplay-parity failure.
