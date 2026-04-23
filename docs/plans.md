# Plan: HLstatsX Legacy vs Python Replay Baseline

## Repo role

This repository is the Python migration donor lane.

- It owns replay parity, Python runtime migration, proxy daemon, operational
  tooling, and heatmap migration work.
- It is not the standalone product repository.
- The integrated product lane now lives separately at
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n`.

This donor lane should stay focused on clean Python/runtime work that can be
imported into the standalone product repo without carrying the upstream RU PR
scope with it.

## Scope

Build a local, reproducible baseline that mirrors the current production HLstatsX
stack, then use that baseline to compare the legacy Perl runtime against the new
Python runtime on identical replayed logs.

## Assumptions

- Production reference stack is the Portainer compose file at
  `/srv/cs16-pugmod/compose/hlstatsx/hlstatsx-portainer-stack.yml`.
- The initial local target is a prod-like legacy stack with the same images,
  ports, credentials, and seeded data shape as production.
- Baseline reset will be performed by the user in the HLstatsX admin UI after
  the local legacy stack is up.
- Production game-log fixtures will be replayed into both stacks after the
  baseline reset, with a smaller clean subset retained for fast parity gates.
- Acceptance focuses on HLstats statistical tables first; runtime heartbeat and
  other volatile fields are secondary and reported separately.

## Milestones

### [x] M1. Reconstruct the production legacy stack locally

Goal:
Bring up a local stack that matches the current production legacy deployment
closely enough for the user to log in and run the built-in stat reset.

Tasks:
- Capture the production compose file, image tags, container commands, and env.
- Export or otherwise copy the production images required for the legacy stack.
- Create a local compose file for the prod-like legacy stack.
- Dump production HLstatsX data and import it into a local MariaDB volume.
- Verify the local web admin is reachable and backed by imported data.

Definition of done:
- Local Docker stack is running with `db`, `web`, `daemon`, and optional
  `phpmyadmin`.
- HLstatsX admin UI opens locally.
- Imported data is present and recognizable as a production copy.
- Result:
  local stack is up on `http://127.0.0.1:8081/hlstats.php`,
  MariaDB is imported, and the copied production user `admin` exists.

Validation:
- `docker compose -f <legacy compose> up -d`
- `docker compose -f <legacy compose> ps`
- `docker compose -f <legacy compose> logs --tail=100 web daemon db`
- Open local admin UI and confirm access.

Known risks:
- Large image or database transfer from production may fail mid-stream.
- Local Docker Desktop may be unavailable or unstable.
- Production image may contain implicit runtime assumptions not visible in
  compose metadata alone.

Stop-and-fix rule:
- Do not proceed to baseline capture until the local admin UI is usable.

### [x] M2. Capture a reusable reset baseline

Goal:
Turn the imported local legacy stack into a reusable reset baseline after the
user performs the built-in stat reset in the admin UI.

Tasks:
- Wait for the user to run the reset from the local admin UI.
- Snapshot the post-reset MariaDB state as a reusable baseline dump.
- Record any required normalization or volatile tables.
- Result:
  `scripts/replay_baseline/artifacts/baseline_reset_20260418.sql.gz`
  is the canonical reset baseline for all comparison runs.

Definition of done:
- One baseline dump exists and can be restored repeatedly.
- Restored baseline yields:
  `0` players, `0` frag events, `1` configured server.

Validation:
- `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\snapshot-baseline.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy`
- Restore the dump into a fresh local DB and verify the web UI still loads.

Known risks:
- Built-in reset may leave some event/history tables partially populated.

Stop-and-fix rule:
- If the reset leaves replay-sensitive tables dirty, identify the residue
  before building comparison automation.

### [x] M3. Fork the baseline into legacy and Python comparison stacks

Goal:
Create two isolated local stacks from the same baseline: one legacy, one Python.

Tasks:
- Clone the baseline DB into `legacy` and `python` databases or isolated DB
  containers.
- Keep the legacy runtime production-like.
- Wire the Python stack to the migrated runtime and compatible replay ingress.
- Capture stack-specific config needed to replay the same logs into both
  contours.

Definition of done:
- Both stacks restore from the same baseline and expose isolated web/DB
  endpoints.
- Legacy contour is replay-ready.
- Python contour exists locally, is isolated from legacy, and its worker/proxy
  start successfully against the restored baseline.
- Any remaining Python replay readiness work is limited to deterministic replay
  ingress of the same raw production fixture set.

Validation:
- `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy`
- `powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python`
- `docker compose -f scripts\replay_baseline\comparison\legacy\docker-compose.yml ps`
- `docker compose -f scripts\replay_baseline\comparison\python\docker-compose.yml ps`

Known risks:
- Python runtime may require a replay adapter because current production logs
  are raw game logs, not proxy-wrapped payloads.
- Python replay may not map packets to `hlstats_Servers` if the replay path does
  not preserve the canonical source server address `172.19.0.1:27015`.

Stop-and-fix rule:
- Do not start long replay runs until both stacks accept the intended input
  format.

### [x] M4. Automate replay and DB diff

Goal:
Run the same production log corpus through both stacks and produce actionable
  differences.

Tasks:
- Copy production log fixtures locally.
- Implement replay tooling for legacy and Python.
- Validate the replay path first on legacy using offline STDIN import of a real
  production log into a clean restored baseline.
- Add a DB diff script that compares only replay-relevant statistical tables and
  suppresses expected runtime metadata noise.
- Dump or query result tables after each run.
- Generate a diff report grouped by table and key.
- Current result:
  `scripts/replay_baseline/compare_stats_dbs.py` and
  `scripts/replay_baseline/replay_python_log.py` now drive the parity loop.
  Python replay preserves the logical source server identity
  `172.19.0.1:27015`, includes paced datagram replay with a drain delay, and
  now reaches the end of `L0415056.log` (`18:48:10` frags/team bonuses,
  `18:48:16` team changes).
  A warmup gate now suppresses the pre-live restart/warmup tail that legacy
  ignores, reducing the DB diff from double-digit table drift down to a smaller
  parity set. The compact diff now reaches `0` replay-semantic table
  differences on a fresh clean cycle; legacy `--stdin` import-tail alias/session
  metadata (`PlayerNames.lastuse/numuses`, `connection_time`) is treated as
  non-statistical noise and excluded from the canonical parity report.
  The clean loop has now been verified on the production fixtures
  `L0415056.log`, `L0415058.log`, `L0416053.log`, `L0417051.log`, and
  `L0417065.log`.
  The diff layer now also normalizes the known legacy offline `--stdin`
  non-ASCII chat corruption (`hlstats_Events_Chat.message`) so transport noise
  does not reopen the canonical gameplay parity gate.

Definition of done:
- One command sequence performs reset restore, replay, and comparison.
- Legacy smoke proves that a clean restored baseline can ingest production logs
  and create HLstats data again.
- Python replay path preserves the same logical source server identity as
  legacy, so the diff compares equivalent inputs rather than transport noise.
- Diff output is compact enough to drive iterative Python fixes without manual
  table spelunking.
- Latest clean parity result:
  `compare_stats_dbs.py` reports no logical replay differences in the configured
  statistical tables after restore -> legacy smoke -> Python replay on
  `L0415056.log`.

Validation:
- Replay completes for both stacks.
- Diff report is generated.
- Legacy smoke command:
  `Get-Content -Raw scripts\replay_baseline\artifacts\L0415056.log | docker run --rm -i --network legacy_hlstatsx_legacy_net startersclan/hlstatsx-community-edition:1.11.4-daemon --stdin --server-ip=172.19.0.1 --server-port=27015 --db-host=db:3306 --db-name=hlstatsxce --db-username=hlstatsxce --db-password=hlx123 --nodns-resolveip`
- Python replay command:
  `python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts\L0415056.log`
- DB diff command:
  `python scripts\replay_baseline\compare_stats_dbs.py`

Known risks:
- Some tables may require normalization of timestamps or ordering.
- Legacy `--stdin` import finalization updates alias/session metadata with
  daemon-timing artifacts that do not reflect replayed statistical behaviour;
  keep those fields out of the compact parity gate unless exact import-tail
  emulation becomes a separate requirement.
- A naive full-schema diff is still too noisy; the dedicated replay diff must
  remain the source of truth for iteration decisions.

Stop-and-fix rule:
- If diffs are dominated by volatile fields, isolate and exclude that noise
  before judging parity.

## Done definition

- Local prod-like stack is available for the user reset step.
- Reset baseline is captured once and restorable.
- Legacy replay smoke from a clean baseline succeeds on real production logs.
- Legacy vs Python replay loop is reproducible.
- DB differences can be traced to concrete tables and then back to Python code.

## Current follow-up

- Keep the canonical loop unchanged:
  `restore baseline -> legacy smoke -> Python replay -> compare_stats_dbs.py`.
- Keep standalone product packaging and EN/RU product validation in
  `hlstatsx-community-edition-python-i18n`; this branch remains the donor lane
  for Python/runtime work.
- Extend the clean fixture set further now that `L0417065.log` is covered by
  the transport-noise normalization in the compact diff.
- Keep exact legacy offline `--stdin` Unicode corruption outside the canonical
  gameplay parity gate unless product requirements later demand byte-for-byte
  emulation of that import path.
- Next migration backlog after replay parity:
  1) exact Python `--stdin` compatibility for `hlstats_py`,
  2) Python port of `HLStatsFTP`,
  3) Python port of `ImportBans`,
  4) optional Prometheus `/metrics` export for runtime observability.
- Recommended execution order:
  finish exact `--stdin` parity first, because `HLStatsFTP` depends on it and
  `ImportBans` is operationally independent from the replay/runtime path.

## Remaining milestones

### [ ] M5. Measure exact Python `--stdin` parity boundaries

Goal:
Promote the runnable Python `--stdin` path from replay support tooling to an
explicitly bounded legacy-compatibility surface.

Tasks:
- Diff one identical fixture through legacy `hlstats.pl --stdin` and Python
  `hlstats_py.runtime --stdin`.
- Record which import-tail fields are still expected to drift
  (`connection_time`, `lastuse`, `numuses`) and whether they are product
  requirements or intentional non-goals for gameplay parity.
- Keep the canonical compact diff focused on replay semantics unless the team
  explicitly decides to widen the parity target.

Definition of done:
- The repo documents whether exact import-finalize metadata parity is required.
- Python `--stdin` is described consistently across plan/status/runbook docs as
  runnable today, with any remaining mismatch narrowed to a named field set.

Validation:
- `Get-Content -Raw scripts\replay_baseline\artifacts\L0415056.log | docker run --rm -i --network legacy_hlstatsx_legacy_net startersclan/hlstatsx-community-edition:1.11.4-daemon --stdin --server-ip=172.19.0.1 --server-port=27015 --db-host=db:3306 --db-name=hlstatsxce --db-username=hlstatsxce --db-password=hlx123 --nodns-resolveip`
- `cd scripts\proxy_daemon_py`
- `$env:PYTHONPATH='..'; Get-Content -Raw ..\replay_baseline\artifacts\L0415056.log | poetry run python -m hlstats_py.runtime --configfile ..\hlstats.conf --stdin --server-ip 172.19.0.1 --server-port 27015`
- `python scripts\replay_baseline\compare_stats_dbs.py`

Known risks:
- Legacy `--stdin` finalization blends gameplay semantics with daemon-timing
  artefacts, which can reopen noisy diffs if the field set is widened too early.

Stop-and-fix rule:
- Do not start `HLStatsFTP` porting until the exact role of import-tail metadata
  is documented and accepted.

### [ ] M6. Port the remaining operational utilities

Goal:
Remove the last required Perl-only operational scripts from the post-runtime
workflow.

Tasks:
- Port `HLStatsFTP/hlstats-ftp.pl` to Python using `hlstats_py.runtime --stdin`
  as the ingestion backend.
- Port `ImportBans/importbans.pl` to Python as a standalone maintenance CLI.
- Add optional `/metrics` export only after the runtime surface is stable.

Definition of done:
- The repo contains Python replacements for `HLStatsFTP` and `ImportBans`.
- Operators can run the common maintenance/import flows without invoking Perl.
- `/metrics` stays optional and does not alter the existing replay/runtime path.

Validation:
- `$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'; python -m pytest scripts\hlstats_py\tests\test_runtime.py scripts\hlstats_py\tests\test_storage.py scripts\hlstats_py\tests\test_protocol.py scripts\hlstats_py\tests\test_events.py scripts\hlstats_py\tests\test_validation.py -q`
- Targeted utility tests for FTP checkpointing and ban import normalization.

Known risks:
- `HLStatsFTP` correctness depends on idempotent replay, checkpoint persistence,
  and active-tail file handling rather than only on parser parity.
- `ImportBans` may need an explicit product decision on `ban`-only parity
  versus a richer `ban/unban` sync model.

Stop-and-fix rule:
- Keep `ImportBans` and `/metrics` out of the runtime-critical path if
  `HLStatsFTP` or direct replay parity still needs fixes.

### [ ] M7. Validate Python heatmaps on real map-pack assets

Goal:
Close the remaining heatmap migration gap with a real legacy-vs-Python parity
check on production-style assets.

Tasks:
- Install the external `heatmaps/src/<game>/<map>.jpg` map-pack used by legacy.
- Run the legacy and Python generators on 1-2 representative production maps.
- Compare published `*-kill.jpg`, `*-kill-thumb.jpg`, and cache behaviour.

Definition of done:
- The Python heatmap generator is validated on real assets, not only synthetic
  smoke fixtures.
- The PHP web layer resolves the generated assets without path or naming changes.

Validation:
- `$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'; python -m pytest scripts\hlstats_py\tests\test_heatmaps.py -q`
- Manual or scripted comparison on 1-2 installed production maps.

Known risks:
- The required map-pack is external to this repository and can block parity
  work even when the generator implementation itself is already correct.

Stop-and-fix rule:
- Do not weaken the current synthetic heatmap regression suite while waiting for
  external asset parity runs.
