# Status: Standalone Python+i18n Product Lane

## Snapshot

- Current phase: `P6d` with `P6e` closed — legacy reference replay and manifests
  are settled; the Python full-corpus run used for the first
  `runtime-db-diff.md` used `--send-delay 0` and is **not** authoritative (UDP
  loss on the parity path). Next gate is a **throttled** Python full replay
  (default `--send-delay 0.005`), then regenerate DB diff.
- Plan file: `docs/plans.md`
- Status: red for P6d runtime parity until a throttled Python full replay backs
  a fresh DB diff; yellow for the broader product lane
- Last updated: 2026-04-25

## Done

- Completed post-mapfix drift-reduction execution pass with authoritative
  `-ForceDumpRestore` parity baseline on both stacks and new audit artifacts in
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/`.
- Closed `P5` maintenance backlog on `2026-04-25`:
  - added standalone Python ImportBans replacement:
    - package: `scripts/import_bans_py`
    - entrypoint: `python -m import_bans_py`
    - behavior parity with legacy scope: import-only ban propagation to
      `hlstats_Players.hideranking = 2` (no unban pass)
  - documented exact `hlstats_py.runtime --stdin` compatibility boundaries with
    reproducible command/exit evidence in `docs/test-plan.md`
  - validated Python heatmap generator against real map-pack JPEG assets under
    `heatmaps/src/cstrike` with host-to-comparison DB config
    (`scripts/replay_baseline/comparison/python/hlstats.host-local.conf`)
- Landed map lifecycle attribution hardening in `hlstats_py.runtime`:
  `Loading map` now stages pending map state and event map attribution flips on
  `Started map`.
- Landed `hlstats_Events_ChangeTeam` noise reduction in `hlstats_py.storage`:
  unresolved actors ignored, bot actors ignored, and duplicate team-change
  rows deduplicated by `(server, player, map, team, event_time)`.
- Added targeted regression coverage for lifecycle behavior and ChangeTeam
  filtering/deduping in `scripts/hlstats_py/tests/`.
- Validated control `window-300` replay after fixes; residual drift remains in
  map/action/player-history identity areas and is documented in
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/NOTES.md`.

- Created a separate local repository for the standalone product lane.
- Rebased the product lane on clean `upstream/master` history instead of using
  the donor `test` branch as the final base directly.
- Imported the Python donor baseline from
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition`.
- Imported the RU i18n donor web/runtime layer from
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n`.
- Rewrote the primary repo docs so this repository now describes the integrated
  product rather than only the migration donor context.
- Preserved the donor-lane references:
  - Python migration runbooks and parity docs stay in this repo as supporting
    product references.
  - RU i18n donor docs stay available as integration background.
- Ran targeted Python validation in the product repo:
  - `hlstats_py` / replay-baseline batch passes when `PYTHONPATH` is set to
    the imported package roots.
  - targeted `proxy_daemon_py` tests pass at the assertion level, but the
    command still exits non-zero because the repo-enforced coverage threshold is
    not met by the small subset run.
- Ran targeted containerized `php -l` checks for the integrated product files:
  `web/hlstats.php`, `web/includes/i18n.php`, `web/includes/functions.php`,
  `web/pages/header.php`, `web/pages/footer.php`, `web/pages/players.php`,
  `web/pages/chat.php`, `web/pages/help.php`, `web/pages/playerinfo.php`,
  `web/pages/admin.php`, and `web/status.php`.
- Fixed the clean `scripts/proxy_daemon_py/fullstack` bootstrap in the product
  repo:
  - normalized `scripts/proxy_daemon_py/sql/02_set_hlstats_auth_plugin.sh` to
    Unix line endings so MySQL init no longer fails on `/bin/sh^M`
  - replaced the proxy-daemon heartbeat upsert with a MySQL 8.0 and
    MariaDB-compatible `ON DUPLICATE KEY UPDATE` form instead of the invalid
    `INSERT ... AS new`
  - switched proxy-daemon heartbeat probes to proxied control packets so
    `hlstats_py.runtime` accepts them from the Docker network and reports the
    worker `up`
- Re-ran product validation on the integrated repo itself:
  - host-side Python suites now pass with the imported package roots on
    `PYTHONPATH`:
    - `scripts/hlstats_py/tests` + `scripts/replay_baseline/tests` -> `56 passed`
    - `scripts/hlstats_awards_py/tests` + `scripts/hlstats_resolve_py/tests`
      -> `17 passed`
    - `scripts/proxy_daemon_py/tests` -> `72 passed` with repo-enforced
      coverage gate satisfied (`83.59%`)
  - targeted regression reruns for the fixed runtime paths pass:
    - `scripts/proxy_daemon_py/tests/test_db.py`
    - `scripts/proxy_daemon_py/tests/test_heartbeat.py`
    - `scripts/hlstats_py/tests/test_runtime.py`
  - clean product full-stack smoke now passes after rebuild:
    - `http://127.0.0.1:8080/` redirects to `hlstats.php`
    - `mode=contents&lang=ru` returns HTTP `200`
    - `status.php?lang=ru` returns HTTP `200`
    - proxy heartbeat persists `hlstats-worker:28000 -> up`
- Replayed the canonical donor fixture set through the integrated repo and
  re-checked the DB against legacy:
  - `L0415056.log` -> clean compact diff, counts `players=9`, `frags=33`
  - `L0415058.log` -> clean compact diff, counts `players=4`, `frags=18`
  - `L0416053.log` -> clean compact diff, counts `players=9`, `frags=34`
  - `L0417051.log` -> clean compact diff, counts `players=9`, `frags=36`
  - `L0417065.log` -> clean compact diff, counts `players=9`, `frags=32`
- Compared the integrated frontend to the live RU donor contour on the same
  HTTP routes:
  - target `mode=contents&lang=ru` renders localized RU UI and responds with
    HTTP `200`
  - target `status.php?lang=ru` also renders localized RU labels in the merged
    product contour
- Closed the audit-confirmed frontend residual i18n backlog (`P6b`) on the
  supported shared/public/admin/voice/ingame contour.
- Completed the release-style frontend revalidation pass (`P6c`) with targeted
  syntax checks, keyset diff, representative EN/RU smoke, and language
  persistence/fallback validation.
- Cleaned the replay-baseline working corpus and extended the Python replay
  contour for the second CS 1.6 source server:
  - `scripts/replay_baseline/prune-small-logs.ps1` removed `30,572` disposable
    `*.log` files below `15 KB`
  - the retained replay working set is now `41,576` log files
  - `scripts/replay_baseline/restore-baseline.ps1 -Stack python` now seeds
    `37.230.137.48:27015` as `game='cstrike'`
  - the seeded replay server receives copied `hlstats_Servers_Config` rows from
    the baseline parity server
  - `scripts/replay_baseline/replay_python_log.py` now accepts either a single
    file or a directory corpus and prints processed/skipped/error summary
- Switched the Python replay comparison web service from the legacy upstream
  image to a local build from the integrated product `web/` tree, with a
  comparison-local config pointing at the restored `hlstatsxce` database.
- Brought up the Python replay comparison stack on `2026-04-23` and validated
  the new CS 1.6 source server against real retained logs:
  - `L1231219.log` replay smoke sent `239` datagrams with
    `37.230.137.48:27015`
  - `L1231213.log` replay smoke sent `3,434` datagrams with
    `37.230.137.48:27015`
  - `L0217071.log` replay smoke sent `25,660` datagrams with
    `37.230.137.48:27015`
  - the replayed DB has visible statistics on the new server:
    `players=7`, `hlstats_Events_Frags=2`, `serverId=2`, `kills=2`
  - RU HTTP smoke on the integrated comparison web returns HTTP `200` for:
    - `hlstats.php?lang=ru`
    - `hlstats.php?mode=contents&lang=ru`
    - `hlstats.php?mode=game&game=cstrike&lang=ru`
    - `hlstats.php?mode=players&game=cstrike&lang=ru`
    - `hlstats.php?mode=servers&server_id=2&game=cstrike&lang=ru`
  - `mode=game` and `mode=servers&server_id=2` show both Russian UI labels and
    the replay server `37.230.137.48`
- Completed the full retained corpus replay on `2026-04-23` after fixing the
  corpus sender to stream stdin line-by-line instead of buffering the complete
  input in memory:
  - processed all `41,576` retained log files for `37.230.137.48:27015`
  - skipped `0` files and reported `0` read errors
  - sent `32,765,671` replay datagrams to the Python worker
  - elapsed wall time was `811.046` seconds, about `51.3` files/sec and
    `40,400` datagrams/sec at sender level
  - final replay DB counts on the new server: `players=497`,
    `hlstats_Events_Frags=1,536`, `kills=1,536`, `act_players=396`
  - integrated RU web smoke still returns HTTP `200` for the game, players,
    and server pages on `http://127.0.0.1:8281/`
- Closed `P6e` end-to-end on `2026-04-25`:
  - replay contour FTP import completed on Python stack with
    `Run-ContourFtpArtifacts` equivalent run at `MaxImportFiles=100` (exit `0`)
  - replay-safe awards completed (exit `0`):
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
  - strict/default sanity run completed (exit `0`):
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
  - replay SQL evidence:
    - non-empty map rows:
      `hlstats_Events_Frags=6536`, `hlstats_Events_PlayerActions=6838`,
      `hlstats_Events_Statsme=40047`
    - `hlstats_Maps_Counts`: `de_dust2 (kills=1013)`, `de_nuke (kills=27)`
    - `hlstats_Players_Awards=4`, `hlstats_Players_Ribbons=4`
    - GeoIP fill (`country` + `flag` non-empty in `hlstats_Players`): `148`

## In Progress

- `P6d`: **Python throttled full corpus replay running** (started 2026-04-23,
  host `python`, `--send-delay 0.005`, `--drain-delay 10`, same filter and
  server identity). Stdout/stderr:
  `docs/audits/legacy-python-parity-20260423/python-full-corpus-replay-regex-filtered-throttled.log`
  and `.err.log`; new manifests
  `python-full-corpus-input-manifest-throttled.txt` /
  `python-full-corpus-dropped-lines-throttled.txt` (verify SHA vs legacy when
  finished). Wall clock is on the order of **tens of hours** (~32.6M lines ×
  0.005 s sleep per datagram in-container, plus I/O). After `Replay summary`
  appears: snapshot DB counts, start `hlstatsx-legacy-db` if the reference DB
  is still populated, then `compare_stats_dbs.py` → refresh
  `runtime-db-diff.md`.
- The audit runbook is seeded at
  `docs/audits/legacy-python-parity-20260423/README.md`.
- The legacy comparison contour now has the same second-server restore
  bootstrap as Python: `37.230.137.48:27015`, `game='cstrike'`, with
  `32` copied `hlstats_Servers_Config` rows from `172.19.0.1:27015`.
- `scripts/replay_baseline/replay_legacy_log.py` is now available as the
  streaming file/directory replay helper for the legacy Perl daemon.
- Legacy smoke replay has passed the backend write gate:
  `L0217071.log` through the Perl daemon produced frag/stat rows, including
  `hlstats_Events_Frags=39` and `hlstats_Events_Statsme=538` after the smoke
  sequence.
- Legacy full replay is now clean and authoritative with final summary:
  `processed=41576`, `skipped=0`, `errors=0`, `dropped_lines=169419`
  (legacy DB reference counters captured in audit performance notes).
- Python full-corpus **rerun** used `--send-delay 0`: helper summary matched
  legacy (`processed=41576`, `skipped=0`, `errors=0`, `dropped_lines=169419`)
  but UDP flooding means most datagrams were likely **not** delivered to the
  worker; that DB snapshot and the first `runtime-db-diff.md` are **invalid**
  for parser parity conclusions (see audit `performance.md`).
- Input manifests and dropped-line manifests still match exactly between legacy
  and that Python run (same line counts and SHA-256 hashes); policy parity is
  confirmed, transport parity was not.
- A throttled Python full replay (e.g. `--send-delay 0.005`, new log name) plus
  fresh `compare_stats_dbs.py` output is the pending authoritative diff.
- The frontend-specific `P6b`/`P6c` work is still complete for the supported
  EN/RU product contour.

## Next

- Continue `P6d` after a **throttled** Python full replay:
  - confirm manifest SHA parity with legacy (or document any drift)
  - capture final DB counts aligned to legacy audit queries
  - run `scripts/replay_baseline/compare_stats_dbs.py --max-examples 20` and
    replace `runtime-db-diff.md` / `.err.txt` with UTF-8-safe capture
  - only then classify any remaining table deltas (`parser/runtime`, DB
    semantics, normalization)
  - keep `--drop-empty-team-enter-events` mandatory on both sides; SQL mode
    `NO_ENGINE_SUBSTITUTION` for comparison
  - page/web mini-agent audit stays blocked until that diff is reviewed
- Keep `P6e` in maintenance-only mode:
  - preserve strict/default behavior as the default contract
  - keep replay-safe policy and SQL evidence checks available for regressions

## Decisions

- This repo is the product integration lane, not the upstream PR lane.
- Python is the default runtime path for the product lane.
- Perl remains legacy-only for validation and transition scenarios.
- The original non-Python contour is the reference for EN/data parity, not for
  RU wording.
- The integrated Python web on `8281` is the RU/current UI reference; RU audit
  findings are data parity plus localization leaks, not byte-for-byte legacy
  HTML diffs.
- Destructive admin actions are out of scope for the parity audit and must be
  logged read-only instead of submitted.
- The frontend i18n implementation must stay explicit and dictionary-backed.
- EN and RU are the required release locales for v1.
- The frontend i18n fix pass will be executed in this order:
  shared helpers/runtime -> public pages -> admin/voice -> ingame pages ->
  final revalidation.
- Repeated visible labels should be moved to catalog-backed helpers or shared
  keys instead of being retranslated page-by-page.

## Current Risks

- Some Python test commands require explicit `PYTHONPATH` setup because the new
  product repo has not yet added a unified developer bootstrap for the imported
  package roots.
- The supported frontend EN/RU contour is now release-clean on the remediated
  routes, but some deeper legacy tooling still relies on bridge/fallback logic
  and should be watched if future routes are reopened or widened.
- Some older admin tools remain hard to smoke end-to-end because they are not
  fully wired into the current admin navigation contour or depend on broader
  legacy runtime flows; those are now a cleanup/readiness issue rather than a
  blocker for the validated routes.
- The replay comparison Docker contour uses fixed container names
  (`hlstatsx-python-*`), so local concurrent stack users can block rebuild or
  smoke passes until those names are free.
- The legacy full-corpus replay is materially slower than the Python sender, so
  the current full retained-corpus run may need to complete as a long-running
  background audit job before DB diff/page audit can start.
- A legacy replay run without a final helper `Replay summary` is not
  authoritative, even if DB counters increased during the run; partial DBs must
  be treated as contaminated and restored away.
- The first post-manifest `runtime-db-diff.md` largely reflects Python UDP
  overload (`--send-delay 0`), not a reviewed parser-vs-legacy conclusion; do
  not triage the 18-table list until a throttled full replay reproduces
  scale closer to legacy.
- The Python runtime still does not populate `hlstats_Players.country` /
  `flag` inline during connect handling, but the Python maintenance contour now
  owns GeoIP backfill through `hlstats_awards_py --geoip`.
- GeoIP now depends on operational prerequisites rather than missing code:
  either populated `geoLiteCity_*` tables or a readable
  `scripts/GeoLiteCity/GeoLite2-City.mmdb` with `UseGeoIPBinary > 0`; when
  those inputs are absent the Python command fails explicitly instead of
  silently leaving players as `Unknown Country`.
- The Python parser/runtime still differs from legacy Perl in a few
  replay-relevant edge cases:
  - Steam/auth normalization still treats only `STEAM_0:` as canonical
  - pending/unknown auth connect events are not delayed like Perl
  - repeated property parsing does not match Perl's destructive `getProperties`
  - connect-address parsing currently splits on the first `:` instead of
    following the legacy IPv4-only `host:port` rule
- Some game-scoped admin routes still depend on the legacy JS/basic-mode
  navigation split, so direct noninteractive HTTP smoke can verify many of them
  but not every task uniformly.
- `P5` maintenance backlog is closed; remaining lane risk is concentrated in
  `P6d` parity replay throughput/diff evidence rather than missing Python
  maintenance utilities.
- Some donor docs still describe lane-specific context rather than product
  context; the main docs in this repo are now the primary source of truth.

## Audit Log

- 2026-04-25: Closed `P6e` validation/evidence loop:
  - replay contour FTP import completed on the Python stack with `100` file cap
    (direct worker run equivalent to `Run-ContourFtpArtifacts` import stage)
  - fixed intermittent `Run-ContourFtpArtifacts` abort between FTP-state cleanup
    and `docker compose run`:
    - root cause: flaky `Get-ChildItem ... | Remove-Item` path raising
      `NullReferenceException` on some runs
    - remediation: replaced with explicit safe cleanup loop over matched files
      in `scripts/replay_baseline/comparison/python/Run-ContourFtpArtifacts.ps1`
    - stable end-to-end command now passes without manual workaround:
      `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 100`
      (exit `0`)
    - canonical script summary now printed in stdout (`status/import mode/server/
      limits/geoip mode`) for audit-friendly replay evidence
  - replay-safe awards runs completed with exit `0`:
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
  - strict/default sanity runs completed with exit `0`:
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
  - SQL evidence captured:
    - `hlstats_Events_Frags` non-empty map: `6536`
    - `hlstats_Events_PlayerActions` non-empty map: `6838`
    - `hlstats_Events_Statsme` non-empty map: `40047`
    - `hlstats_Maps_Counts`: `de_dust2 kills=1013`, `de_nuke kills=27`
    - `hlstats_Players_Awards=4`, `hlstats_Players_Ribbons=4`
    - GeoIP fill (`hlstats_Players` non-empty `country` + `flag`): `148`
- 2026-04-25: Closed `P5` maintenance-only backlog with validation evidence:
  - `ImportBans` Python CLI implemented as `scripts/import_bans_py`
  - runtime boundary commands:
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin`
      -> exit `1` (`--stdin requires both --server-ip and --server-port`)
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin --server-ip 127.0.0.1 --server-port 27015 --stdin-transaction-batch-size -1`
      -> exit `1` (`--stdin-transaction-batch-size must be >= 0`)
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin --server-ip 127.0.0.1 --server-port 27015 --parser-backend native --stdin-transaction-batch-size 0`
      -> exit `1` on local config DB precondition (`DBHost must be configured in hlstats.conf`) after CLI boundary acceptance
  - ImportBans CLI boundary commands:
    - `python -m import_bans_py --help` -> exit `0`
    - `python -m import_bans_py --configfile hlstats.conf --dry-run`
      -> exit `1` (missing required source configuration)
  - real map-pack asset heatmap runs:
    - `python -m hlstats_py.heatmaps --configfile scripts/replay_baseline/comparison/python/hlstats.host-local.conf --game cstrike --map de_dust2 --disablecache --debug-level 2`
      -> exit `0`
    - `python -m hlstats_py.heatmaps --configfile scripts/replay_baseline/comparison/python/hlstats.host-local.conf --game cstrike --map de_nuke --disablecache --debug-level 2`
      -> exit `0`
    - both runs completed generator path (`Heatmap creation done`) and
      skipped render step because queried kill count for the map window was `0`
- 2026-04-24: Landed stdin import performance tuning for Python runtime/FTP path:
  - added quiet-by-default stdin event logging with opt-in debug flag
    `--stdin-verbose-events` (default off)
  - added parser backend selector `--parser-backend` with default `python`
    and optional `native` fast path
  - added stdin DB transaction batching with
    `--stdin-transaction-batch-size` (default `1000`, `0` disables batching)
  - documented defaults, tuning profiles, and verification flow in
    `docs/hlstats_py_stdin_import_tuning.md`
- 2026-04-24: Added `P6e` architecture-modernization parity milestone to
  `docs/plans.md` and aligned execution framing around:
  - explicit runtime map state projection
  - policy-based awards behavior (strict/default vs replay-safe)
  - decoupled GeoIP resolver behavior by policy
  - replay-focused validation gates and stop-and-fix criteria
- 2026-04-23: Began `P6d` execution on the backend/runtime contour:
  - factored `restore-baseline.ps1` so the second replay server bootstrap runs
    for both `-Stack legacy` and `-Stack python`, while Python-only
    `Proxy_Daemons` setup remains Python-only
  - added `scripts/replay_baseline/replay_legacy_log.py`, a reusable streaming
    stdin replay helper for the legacy Perl daemon
  - verified `-Stack legacy` restore creates exactly one
    `37.230.137.48:27015` `cstrike` server with `32` copied config rows and a
    clean pre-replay DB
  - smoke replayed `L1231219.log`, `L1231213.log`, and `L0217071.log`; the
    final representative smoke confirmed Perl writes gameplay stats
    (`players=62`, `frags=39`, `statsme=538`)
  - started the full `41,576` file retained-corpus legacy replay from a clean
    restore; page audit remains blocked until DB/runtime diff is captured
- 2026-04-23: Heartbeat follow-up found the first full legacy retained-corpus
  run failed before completion:
  - helper output reached `L0107052.log` and then logged `[Errno 22] Invalid argument`
  - no final `Replay summary` was written
  - queued files before failure: `1097`
  - the partial legacy DB must not be used for DB diff or page audit
  - patched `replay_legacy_log.py` to report daemon/stdin pipe closure as a
    replay failure instead of masking it as per-file read failures
- 2026-04-23: Completed the P6d backend/runtime parity **capture** gates (with a
  critical caveat on the Python side):
  - legacy full replay completed cleanly and is now the authoritative
    comparison reference
  - Python rerun full replay used `--drop-empty-team-enter-events` and
    `--send-delay 0 --drain-delay 10`; helper summary matched legacy, but
    `--send-delay 0` is now treated as **invalid for DB parity** (UDP loss on
    the docker UDP path; helper `errors=0` does not prove delivery)
  - legacy vs Python input manifests and dropped-line manifests match exactly
    (`41576` inputs, `169419` dropped lines; identical SHA-256 hashes)
  - captured Python post-replay DB snapshot (not comparable to legacy at scale):
    `players=554`, `frags=2007`, `statsme=9687`, `players_history=73333`,
    replay server `kills=1994`, `players=552`, `act_players=408`
  - generated runtime diff report:
    `docs/audits/legacy-python-parity-20260423/runtime-db-diff.md`
    with logical differences in `18` tables — **stale until throttled replay**
  - page/web parity audit remains blocked pending a throttled Python full replay
    and a regenerated DB diff
- 2026-04-23: Documented Python replay UDP methodology (`performance.md`,
  `status.md`, audit `README.md`); `replay_python_log.py` now prints a stderr
  warning when `--send-delay 0`.
- 2026-04-23: Planned `P6d` full legacy-vs-Python product parity audit using
  the `justdoit` workflow:
  - added `P6d` to `docs/plans.md`
  - created the full mini-agent runbook at
    `docs/audits/legacy-python-parity-20260423/README.md`
  - updated `docs/test-plan.md` with the replay, DB diff, route inventory,
    issue logging, and final bug-plan gates
  - first unfinished execution item is legacy/Python comparison setup, with
    legacy second-server bootstrap and streaming full-corpus replay as the
    first prep blockers
- 2026-04-22: Follow-up replay/product audit after the second-server bootstrap:
  - direct SQL inspection of the live Python comparison DB on `127.0.0.1:3327`
    confirms the restore bootstrap is intact even before replay:
    - `172.19.0.1:27015` and `37.230.137.48:27015` both exist in
      `hlstats_Servers`
    - the replay server still has `32` copied `hlstats_Servers_Config` rows
    - `Proxy_Daemons` is configured to `hlstatsx-python-worker:28000`
    - the restored DB is still clean for replay work (`0` players,
      `0` frags, `0` history rows)
  - audited the Python country-resolution path and confirmed that product-lane
    Python runtime does not currently write `hlstats_Players.country` / `flag`
  - audited Python-vs-Perl parser parity and confirmed no repo-vs-repo drift
    between donor/product copies, but several remaining functional deltas in
    Python:
    - Steam/auth normalization is narrower than Perl
    - pending/unknown auth connect handling is missing
    - repeated property parsing is not Perl-equivalent
    - connect-address parsing can diverge from Perl outside IPv4 `host:port`
  - prepared the next replay/web smoke focus list for the restored 8281 contour:
    `status.php`, `show_graph.php`, `sig.php`, `playerhistory`, `updater`,
    core public pages, key admin tasks, and replay-backed ingame status/load
- 2026-04-22: Completed `P6c` release-style frontend revalidation after the
  final `P6b` remediation batch:
  - representative HTTP smoke returns `200` with expected localized EN/RU
    content for:
    - public `mode=playerhistory` error-path rendering
    - public `mode=updater`
    - voice `mode=teamspeak`
    - ingame `mode=ingame&page=status`
    - admin `task=tools_adminevents`
    - admin `task=serversettings&key=1&game=cstrike`
  - explicit language persistence/fallback contract passes:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when only `PHPSESSID` is preserved
    - fresh request without language state falls back to EN
    - invalid `lang=zz` does not overwrite the persisted valid language
  - focused grep over the remediated files no longer shows the retired raw
    English UI copy outside translation-map literals, EN catalogs, and accepted
    fallback strings
- 2026-04-22: Landed the first `P6b` remediation batch for the
  audit-confirmed residual backlog:
  - hardened shared request sanitization in `web/includes/functions.php` and
    the main HTTP/image entrypoints to keep non-Latin input intact
  - fixed the remaining `web/status.php` runtime bootstrap defect so localized
    error handling is available before the PHP-version gate fires
  - localized the residual direct-output public/admin/ingame surfaces in:
    - `web/pages/playerhistory.php`
    - `web/pages/profile.php`
    - `web/pages/updater.php`
    - `web/pages/admintasks/serversettings.php`
    - `web/pages/admintasks/tools_adminevents.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/status.php`
  - extended the shared table/runtime bridge so cell-value literals and runtime
    marker payloads resolve through the catalogs instead of leaking English
- 2026-04-22: Validation for the current `P6b` remediation batch:
  - rebuilt `web` from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml`
  - targeted Dockerized `php -l` passes for all changed shared/public/admin/
    ingame files plus `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff remains clean with `missing_in_ru=0` and
    `missing_in_en=0`

- 2026-04-22: Ran a distributed static i18n audit over the integrated product
  repo with separate passes for:
  - shared/runtime core
  - public `web/pages/*`
  - admin shell and `admintasks`
  - ingame/voice/template surfaces
  - aggregate coverage and keyset completeness
- 2026-04-22: Audit outcome:
  - `web/lang/en.php` and `web/lang/ru.php` remain aligned by keyset
  - the repo is close to release-clean on the public/admin contours, but not
    yet on ingame/shared runtime
  - the highest-risk remaining issues are:
    - ASCII-only request sanitization that can corrupt non-Latin input
    - English event descriptions embedded in `web/pages/playerhistory.php` SQL
    - DB-sourced English help text in
      `web/pages/admintasks/serversettings.php`
    - residual raw-English ingame routes such as `status`, `load`, `mapinfo`,
      and `weaponinfo`
    - remaining bridge/fallback-heavy legacy helpers and utility pages
- 2026-04-22: Inserted a new `P6b` remediation milestone into `docs/plans.md`
  and moved the release-style revalidation pass to `P6c` so the plan matches
  the audit findings.
- 2026-04-22: Replay-baseline corpus hygiene and second-server bootstrap:
  - added `scripts/replay_baseline/prune-small-logs.ps1`
  - pruned the working replay artifacts set from `72,148` logs to `41,576`
    by deleting `30,572` logs smaller than `15 KB`
  - extended `scripts/replay_baseline/restore-baseline.ps1 -Stack python` so
    the restored comparison DB contains:
    - the canonical parity server `172.19.0.1:27015`
    - the CS 1.6 replay server `37.230.137.48:27015`
  - verified the seeded replay server has `32` copied
    `hlstats_Servers_Config` rows
  - extended `scripts/replay_baseline/replay_python_log.py` so it can replay a
    sorted directory corpus under one explicit logical source server identity
- 2026-04-23: Reworked the Python comparison web service so the `8281`
  inspection contour uses the current integrated product `web/` tree instead
  of the legacy upstream web image.
- 2026-04-23: Runtime validation on the freed replay stack:
  - rebuilt and started `scripts/replay_baseline/comparison/python`
  - confirmed `SERVERLIST` exposes both `172.19.0.1:27015` and
    `37.230.137.48:27015`
  - replayed retained CS 1.6 logs under `37.230.137.48:27015`
  - verified the integrated RU frontend on `8281` renders replayed data with
    Russian labels and the new replay server visible on the game/server pages

- 2026-04-22: Ran a full frontend translation review over:
  - shared i18n runtime/catalogs
  - public `web/pages/*` groups
  - voice/templates
  - admin shell and `admintasks`
  - `web/pages/ingame/*`
- 2026-04-22: Review outcome:
  - no evidence that the explicit EN/RU i18n contract is conceptually wrong
  - strong evidence that a large legacy UI layer still bypasses `t(...)`
  - one confirmed catalog gap: `literal.yes` missing in RU
  - one confirmed syntax blocker: `web/pages/ingame/motd.php`
- 2026-04-22: Planned the remediation as `P6a -> P6b` instead of jumping
  directly to final packaging.
- 2026-04-22: Landed `P6a` batch 1:
  - added the missing RU catalog key `literal.yes`
  - added shared catalog coverage for runtime/database/public error-path text
  - localized shared helper/runtime flows in:
    - `web/includes/functions.php`
    - `web/includes/class_db.php`
    - `web/includes/google_maps.php`
    - `web/ingame.php`
  - localized first public/detail surfaces in:
    - `web/pages/search-class.php`
    - `web/pages/help.php`
    - `web/pages/game.php`
    - `web/pages/servers.php`
    - `web/pages/claninfo.php`
    - `web/pages/dailyawardinfo.php`
    - `web/pages/mapinfo.php`
    - `web/pages/rankinfo.php`
    - `web/pages/ribboninfo.php`
    - `web/pages/rolesinfo.php`
    - `web/pages/weaponinfo.php`
- 2026-04-22: Validation for `P6a` batch 1:
  - targeted Dockerized `php -l` passes for every file changed in the batch
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` is clean
  - fullstack smoke on `127.0.0.1:8080` returns HTTP `200` with expected
    localized tokens for:
    - `mode=contents`
    - `mode=help`
    - `mode=search`
    - `game=aoc`
    - `mode=servers&game=aoc&server_id=1`
    - `mode=dailyawardinfo&game=aoc&award=1`
    - `mode=mapinfo&game=aoc&map=de_dust2`
    - `mode=rankinfo&game=aoc&rank=1`
    - `mode=rolesinfo&game=aoc&role=Crossbowman`
    - `mode=weaponinfo&game=aoc&weapon=Broadsword`
- 2026-04-22: Landed `P6a` batch 2:
  - localized voice/runtime error paths in:
    - `web/pages/teamspeak.php`
    - `web/pages/ventrilo.php`
  - extended shared dictionary-backed literal mapping and new catalog coverage
    for ingame/admin/voice surface labels and runtime messages in:
    - `web/includes/functions.php`
    - `web/includes/i18n.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - removed or centralized the reviewed ingame/runtime leaks in:
    - `web/pages/ingame/actioninfo.php`
    - `web/pages/ingame/actions.php`
    - `web/pages/ingame/bans.php`
    - `web/pages/ingame/claninfo.php`
    - `web/pages/ingame/clans.php`
    - `web/pages/ingame/footer.php`
    - `web/pages/ingame/header.php`
    - `web/pages/ingame/help.php`
    - `web/pages/ingame/kills.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/mapinfo.php`
    - `web/pages/ingame/maps.php`
    - `web/pages/ingame/motd.php`
    - `web/pages/ingame/players.php`
    - `web/pages/ingame/servers.php`
    - `web/pages/ingame/statsme.php`
    - `web/pages/ingame/status.php`
    - `web/pages/ingame/targets.php`
    - `web/pages/ingame/weaponinfo.php`
    - `web/pages/ingame/weapons.php`
    - `web/pages/ingame/accuracy.php`
  - fixed a real runtime defect while in scope:
    - `web/pages/ingame/motd.php` parser blocker
    - `web/pages/ingame/actioninfo.php` now queries action description by
      `code` instead of an undefined `$action_id`
    - `web/pages/ventrilo.php` now checks password length correctly
- 2026-04-22: Validation for `P6a` batch 2:
  - targeted Dockerized `php -l` passes for all touched voice/shared/ingame
    files, including `web/pages/ingame/motd.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` is clean and
    duplicate-key noise was reduced to zero
  - rebuilt `fullstack-web` from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace code instead of a stale container image
  - fullstack smoke on `127.0.0.1:8080` returns HTTP `200` with expected
    localized tokens for:
    - `hlstats.php?mode=admin&lang=en|ru`
    - `ingame.php?game=aoc&mode=help&lang=en|ru`
    - `ingame.php?game=aoc&mode=servers&lang=en|ru`
    - `ingame.php?game=aoc&mode=motd&lang=en|ru`
    - `ingame.php?game=aoc&mode=actions&lang=en|ru`
    - `ingame.php?game=aoc&mode=statsme&player=1&lang=en|ru`
    - `ingame.php?game=aoc&mode=claninfo&clan=1&lang=en|ru`
    - `hlstats.php?mode=teamspeak&game=aoc&tsId=1&lang=en|ru`
    - `hlstats.php?mode=ventrilo&game=aoc&veId=1&lang=en|ru`
- 2026-04-22: Landed `P6a` batch 3:
  - added shared admin/runtime helper coverage for access-denied handling and
    extra admin edit-list labels in:
    - `web/includes/functions.php`
  - retired the repeated raw-English `admintasks` guard paths across the
    reviewed admin task files so direct-access and access-denied flows now use
    the shared dictionary-backed helpers
  - localized the most reachable remaining admin task runtime/public text in:
    - `web/pages/admintasks/options.php`
    - `web/pages/admintasks/serversettings.php`
    - `web/pages/admintasks/games.php`
    - `web/pages/admintasks/tools_reset_2.php`
    - `web/pages/admintasks/tools_synchronize.php`
    - `web/pages/admintasks/tools_resetdbcollations.php`
  - extended EN/RU catalogs for those admin task surfaces in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - fixed one additional PHP 8 syntax/runtime blocker while in scope:
    - removed invalid call-time pass-by-reference syntax from
      `web/pages/admintasks/tools_synchronize.php`
    - corrected the accidental assignment in the null-default check inside
      `web/pages/admintasks/tools_resetdbcollations.php`
- 2026-04-22: Validation for `P6a` batch 3:
  - targeted Dockerized `php -l` passes for all changed admin/helper files in
    the batch, including every touched `web/pages/admintasks/*.php` file
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains
    clean with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` after the final
    `tools_synchronize.php` PHP 8 fix so HTTP smoke used the current workspace
    image
  - authenticated admin HTTP smoke using the existing local fixture admin
    account returns HTTP `200` with expected localized tokens for:
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
    - `hlstats.php?mode=admin&task=games&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_reset_2&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_resetdbcollations&lang=en|ru`
  - explicit language persistence/fallback contract remains intact:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when the `lang` cookie is omitted but the session
      is preserved
    - default EN rendering with a fresh request without `lang`, cookie, or
      session
  - admin route notes from the smoke pass:
    - `serversettings` requires a fuller legacy game-task navigation path than
      the direct noninteractive request used in the smoke, so it was syntax and
      catalog validated in this batch but not token-asserted by direct HTTP
    - `tools_synchronize` is not currently registered in the active admin task
      list even though the file remains present, so it was validated by syntax
      and catalog/runtime grep rather than route-level token smoke
- 2026-04-22: Extended `P6a` batch 3 with the remaining cheap admin helper
  cleanup:
  - localized the longer admin runtime/control tools in:
    - `web/pages/admintasks/tools_perlcontrol.php`
    - `web/pages/admintasks/tools_settings_copy.php`
  - localized the helper/list screens in:
    - `web/pages/admintasks/tools_editdetails.php`
    - `web/pages/admintasks/tools_optimize.php`
    - `web/pages/admintasks/tools_ipstats.php`
    - `web/pages/admintasks/tools_adminevents.php`
  - extended EN/RU catalogs for those helper screens in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - removed one additional in-scope admin filter leak:
    - `web/pages/admintasks/tools_adminevents.php` now uses the shared
      localized `(All)` label instead of a raw English literal
- 2026-04-22: Validation for the batch 3 helper follow-up:
  - targeted Dockerized `php -l` passes for:
    - `web/pages/admintasks/tools_editdetails.php`
    - `web/pages/admintasks/tools_optimize.php`
    - `web/pages/admintasks/tools_ipstats.php`
    - `web/pages/admintasks/tools_adminevents.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` after the final
    `tools_adminevents.php` cleanup so HTTP smoke used the current workspace
    image
  - authenticated admin HTTP smoke using the local fixture admin account returns
    HTTP `200` with expected localized tokens for:
    - `hlstats.php?mode=admin&task=tools_perlcontrol&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_settings_copy&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_editdetails&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_optimize&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_ipstats&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_adminevents&lang=en|ru`
  - explicit language persistence/fallback contract remains intact on the
    authenticated helper contour:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when only `PHPSESSID` is preserved
    - default EN rendering with a fresh authenticated request without language
      state
- 2026-04-22: Landed `P6a` batch 4 on the next cheap admin `EditList` screens:
  - localized repeated column labels, short guidance text, and submit buttons
    in:
    - `web/pages/admintasks/awards_plyractions.php`
    - `web/pages/admintasks/awards_plyrplyractions.php`
    - `web/pages/admintasks/awards_plyrplyractions_victim.php`
    - `web/pages/admintasks/servers.php`
    - `web/pages/admintasks/voicecomm.php`
    - `web/pages/admintasks/roles.php`
    - `web/pages/admintasks/teams.php`
    - `web/pages/admintasks/ranks.php`
    - `web/pages/admintasks/ribbons_trigger.php`
  - localized the encrypted-password placeholder in
    - `web/pages/admintasks/servers.php`
  - extended EN/RU catalogs for the shared admin labels reused by those
    screens in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 4:
  - targeted Dockerized `php -l` passes for all nine touched admin pages plus
    `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=awards_plyractions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_plyrplyractions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_plyrplyractions_victim&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=servers&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=voicecomm&lang=en|ru`
    - `hlstats.php?mode=admin&task=roles&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=teams&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=ranks&game=cstrike&lang=en|ru`
  - focused raw-literal grep over the nine touched admin files no longer shows
    user-facing raw English outside the standard file header comment block and
    non-UI internals
  - route note:
    - `ribbons_trigger` still falls back to the legacy overview/basic-mode
      contour on a direct noninteractive request after login, so this batch
      validates it by syntax, catalogs, and focused grep, but not by direct
      token-level HTTP smoke
- 2026-04-22: Landed `P6a` batch 5 on the next medium-cost admin pages:
  - localized the remaining repeated column labels, select option labels,
    explanatory copy, and submit buttons in:
    - `web/pages/admintasks/actions.php`
    - `web/pages/admintasks/adminusers.php`
    - `web/pages/admintasks/awards_weapons.php`
    - `web/pages/admintasks/ribbons.php`
    - `web/pages/admintasks/weapons.php`
  - extended EN/RU catalogs for the new shared/admin task literals in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 5:
  - targeted Dockerized `php -l` passes for all five touched admin pages plus
    `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=actions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=adminusers&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_weapons&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=ribbons&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=weapons&game=cstrike&lang=en|ru`
  - focused raw-literal grep over the five touched admin files no longer shows
    the retired user-facing raw English literals outside localized key names
    and non-UI internals
- 2026-04-22: Landed `P6a` batch 6 on the remaining heavy admin pages:
  - localized the remaining user-facing text in:
    - `web/pages/admintasks/clantags.php`
    - `web/pages/admintasks/hostgroups.php`
    - `web/pages/admintasks/options.php`
  - extended EN/RU catalogs for:
    - the full `clantags` and `hostgroups` help text blocks
    - the `options` page section headings
    - option field labels and DB-backed select-choice labels used on
      `options.php`
  - kept the options-page rendering dictionary-backed without changing the
    existing admin option definitions by localizing section titles, field
    labels, submit/success text, and choice text at render time
- 2026-04-22: Validation for `P6a` batch 6:
  - targeted Dockerized `php -l` passes for:
    - `web/pages/admintasks/clantags.php`
    - `web/pages/admintasks/hostgroups.php`
    - `web/pages/admintasks/options.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=clantags&lang=en|ru`
    - `hlstats.php?mode=admin&task=hostgroups&lang=en|ru`
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
  - focused raw-literal grep over the three touched admin files no longer shows
    the retired user-facing raw English strings outside internal fallback maps,
    legacy internal option definitions, and non-rendered code literals
- 2026-04-22: Landed `P6a` batch 7 on the final shared helper fallback cleanup:
  - removed fallback-only raw-English helper text from
    `web/includes/functions.php`
  - switched the remaining helper/runtime messages there to catalog-key-backed
    lookup without embedded English last-resort strings
  - added the missing shared catalog key `error.invalid_url` in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 7:
  - targeted Dockerized `php -l` passes for:
    - `web/includes/functions.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke still returns HTTP `200` with
    expected localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=clantags&lang=en|ru`
    - `hlstats.php?mode=admin&task=hostgroups&lang=en|ru`
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
  - focused helper grep confirms no remaining fallback-only raw-English helper
    strings in `web/includes/functions.php` outside the shared legacy literal
    translation map
