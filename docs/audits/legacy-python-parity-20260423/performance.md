# P6d Runtime Performance Notes

## Python test contour default mode (2026-04-24)

- Canonical index for fast replay (links, no duplicate recipes):
  [`../../replay-fast-path.md`](../../replay-fast-path.md).
- Python test contour default import path is now `hlstats_ftp_py -> hlstats_py.runtime --stdin`.
- UDP replay path (`replay_python_log.py`) is preserved as an explicit opt-in mode
  for transport-focused tests.
- **Narrow-window / table-diff runs:** prefer `direct_import_artifacts.py` (stdin
  batch in-process) or `hlstats_ftp_py` over UDP `replay_python_log.py`; throttled
  UDP remains correct but **very slow** on large line counts (delay per datagram).
- `hlstats_ftp_py` now prints timing/throughput summary (`listing`, `download`,
  `parse`, `files/sec`, `lines/sec`) so before/after runs can be compared from CLI output.

## Baseline restore mode (snapshot-first)

- `restore-baseline.ps1` now defaults to snapshot-first DB reset for both
  `legacy` and `python` stacks.
- Snapshot archives are stored at:
  `scripts/replay_baseline/artifacts/snapshots/<stack>/`.
- If snapshot restore is unavailable or fails, script auto-falls back to the
  canonical dump restore path (`baseline.sql.gz -> mysql`) and can persist a
  fresh snapshot afterward.
- Operational commands:
  - fast default restore:
    `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python`
  - force dump restore:
    `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python -ForceDumpRestore`
  - recreate snapshot from current baseline:
    `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python -CreateSnapshot`

## Python replay: UDP delivery (methodology)

The Python helper reports `Sent N replay datagrams` after the in-container UDP
sender finishes. That count reflects **writes to the UDP socket**, not a
guarantee that `hlstats_py.runtime` received or persisted **N** logical events.

Parity contour path: host `replay_python_log.py` streams lines into
`docker exec -i … python -c …` which sends each wrapped line to
`127.0.0.1:<worker_port>` inside the worker. With `--send-delay 0`, the sender
floods UDP; on a smoke sample (`L0217071.log`, 25610 datagrams after filters)
worker logs showed on the order of **~300** `Received … bytes` lines vs
25610 sent — catastrophic loss. With `--send-delay 0.005`, `Received` and
`Recorded` counts matched the sent volume for that file (aside from a handful of
non-replay lines such as heartbeat/proxy traffic).

**Rule for P6d DB/runtime parity:** do **not** run full-corpus Python replay for
diff against legacy with `--send-delay 0`. Treat any full run taken at
`--send-delay 0` as **invalid for parser/DB parity conclusions** even when the
helper prints `errors=0` (worker/DB failures are not folded into that summary).
Use a positive throttle (start from **0.005 s**, same as the script default) and
optionally spot-check `docker logs hlstatsx-python-worker` on a small log before
a long job. Lower delays are allowed only after you measure `Sent` vs worker
`Received`/`Recorded` on a representative sample and document the choice.

Artifacts from the control experiment (2026-04-23):

- `diag-short-replay-L0217071-send0.log`
- `diag-short-replay-L0217071-send0005.log`

## Legacy Restore Gate

Command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy
```

Result on 2026-04-23:

- Restored canonical baseline into `hlstatsx-legacy-db`.
- Replay server bootstrap is present after restore:
  `37.230.137.48:27015`, `game='cstrike'`, `serverId=2`.
- Copied `hlstats_Servers_Config` rows from baseline server:
  `32`.
- Clean pre-replay counts:
  `players=0`, `hlstats_Events_Frags=0`,
  `hlstats_Players_History=0`.

## Legacy Smoke Replays

Command:

```powershell
python scripts\replay_baseline\replay_legacy_log.py scripts\replay_baseline\artifacts\L1231219.log --server-identity 37.230.137.48:27015
```

Result:

- `processed=1`, `skipped=0`, `errors=0`
- `lines=239`
- `elapsed=4.201s`
- throughput: `0.24 files/sec`, `56.89 lines/sec`
- DB impact: created player/history rows but no frag rows. This log is useful
  as a minimal stdin/helper smoke, but not sufficient as the gameplay smoke.

Command:

```powershell
python scripts\replay_baseline\replay_legacy_log.py scripts\replay_baseline\artifacts\L1231213.log --server-identity 37.230.137.48:27015
```

Result after clean restore:

- `processed=1`, `skipped=0`, `errors=0`
- `lines=3434`
- `elapsed=6.140s`
- throughput: `0.16 files/sec`, `559.27 lines/sec`
- DB impact: `players=4`, `hlstats_Events_Frags=0`,
  `hlstats_Players_History=4`, `hlstats_PlayerNames=5`,
  `hlstats_PlayerUniqueIds=4`, `hlstats_Maps_Counts=11`.
- Note: this log contains `killed` lines, but Perl did not persist frag rows
  from this sample. Treat it as a parser/config observation, not as the final
  smoke gate.

Command:

```powershell
python scripts\replay_baseline\replay_legacy_log.py scripts\replay_baseline\artifacts\L0217071.log --server-identity 37.230.137.48:27015
```

Result on top of the `L1231213.log` smoke DB:

- `processed=1`, `skipped=0`, `errors=0`
- `lines=25660`
- `elapsed=20.144s`
- throughput: `0.05 files/sec`, `1273.85 lines/sec`
- DB impact after both smoke logs:
  `players=62`, `hlstats_Events_Frags=39`,
  `hlstats_Players_History=62`, `hlstats_PlayerNames=63`,
  `hlstats_PlayerUniqueIds=62`, `hlstats_Events_Entries=11`,
  `hlstats_Events_Connects=20`, `hlstats_Events_Chat=22`,
  `hlstats_Events_Statsme=538`.
- Server counter check:
  `serverId=2`, `kills=39`, `players=62`, `act_map=fy_pool_day`.

## Legacy Full Corpus Replay

Command:

```powershell
python scripts\replay_baseline\replay_legacy_log.py scripts\replay_baseline\artifacts --server-identity 37.230.137.48:27015 *> docs\audits\legacy-python-parity-20260423\legacy-full-corpus-replay-20260423.log
```

Status:

- Started on 2026-04-23 after a clean legacy restore.
- Input corpus: `41,576` retained `.log` files.
- Raw helper output:
  `docs/audits/legacy-python-parity-20260423/legacy-full-corpus-replay-20260423.log`.
- In-progress DB check confirmed the Perl backend is actively writing runtime
  data during the full replay:
  `players=119`, `hlstats_Events_Frags=693`,
  `hlstats_Events_Statsme=4818` at an early progress sample.
- Follow-up heartbeat on 2026-04-23 found the first full-corpus attempt did not
  complete cleanly:
  - queued files before failure: `1097`
  - last queued file: `L0107052.log`
  - helper log did not contain a final `Replay summary`
  - first logged failure after that point:
    `failed to read scripts\replay_baseline\artifacts\L0107054.log: [Errno 22] Invalid argument`
  - final logged failure: `[Errno 22] Invalid argument`
- The helper was patched after this failure so daemon/stdin pipe closure is no
  longer misreported as per-file read failure. The next full run should be
  started from a clean `-Stack legacy` restore and, if it fails again, rerun the
  failure window with `--daemon-output inherit` to capture the Perl daemon
  stderr.
- Final full-corpus legacy replay counts are not authoritative yet; the current
  full-corpus DB is partial and must not be used for `compare_stats_dbs.py` or
  page-audit conclusions.

Next investigation tasks:

1. Cleanly restore legacy DB before any retry.
2. Rerun the full corpus with the patched helper and write a new output log.
3. If the run fails again around `L0107052` / `L0107054`, create a temporary
   narrowed failure-window directory and replay it with `--daemon-output inherit`.
4. Capture Perl daemon stderr and classify the failure as helper pipe handling,
   daemon crash/limit, malformed/corpus-specific input, Docker/runtime resource
   issue, or accepted legacy limitation.
5. Only after a clean final helper summary, record final DB counts and move to
   Python contour verification plus `compare_stats_dbs.py --max-examples 20`.

## Legacy Reference (Authoritative)

Legacy full replay completed cleanly and is now the parity reference baseline.

- replay helper policy: `--drop-empty-team-enter-events`
- SQL mode for comparison contour: `NO_ENGINE_SUBSTITUTION` (non-strict)
- final helper summary:
  - `processed=41576`
  - `skipped=0`
  - `errors=0`
  - `lines=32596252`
  - `dropped_lines=169419`
  - `elapsed=14974.273s`
  - throughput: `2.78 files/sec`, `2176.82 lines/sec`
- final legacy DB counts:
  - `hlstats_Players=6047`
  - `hlstats_Events_Frags=537484`
  - `hlstats_Events_Statsme=2785501`
  - `hlstats_Players_History=37103`
  - `hlstats_Servers(serverId=2)`: `kills=537484`, `players=6047`,
    `act_players=344`, `act_map=de_aztec_winter`

## Python Full Replay (Rerun at `--send-delay 0` — not authoritative)

Command (historical; **do not repeat for parity**):

```powershell
python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts --server-identity 37.230.137.48:27015 --drop-empty-team-enter-events --send-delay 0 --drain-delay 10 --input-manifest docs\audits\legacy-python-parity-20260423\python-full-corpus-input-manifest-rerun.txt --dropped-lines-manifest docs\audits\legacy-python-parity-20260423\python-full-corpus-dropped-lines-rerun.txt *> docs\audits\legacy-python-parity-20260423\python-full-corpus-replay-regex-filtered-rerun.log
```

Helper output (green summary only — **misleading for DB parity**):

- helper finished with final summary:
  - `processed=41576`
  - `skipped=0`
  - `errors=0`
  - `dropped_lines=169419`
- Python DB counts after that run (not comparable to legacy reference — UDP loss):
  - `hlstats_Players=554`
  - `hlstats_Events_Frags=2007`
  - `hlstats_Events_Statsme=9687`
  - `hlstats_Players_History=73333`
  - `hlstats_Servers(serverId=2)`: `kills=1994`, `players=552`,
    `act_players=408`, `act_map=''`

The large gap vs legacy reference counts is consistent with most datagrams never
being processed, not with a settled parser delta. A **new** full-corpus Python
replay is required with `--send-delay` ≥ a measured-safe value (default **0.005**),
then fresh manifests (should still match legacy byte-for-byte if policy is
unchanged), DB count snapshots, and a regenerated `runtime-db-diff.md`.

Example command for the valid retry (use a **new** log filename; adjust paths if
manifests are regenerated):

```powershell
python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts --server-identity 37.230.137.48:27015 --drop-empty-team-enter-events --send-delay 0.005 --drain-delay 10 --input-manifest docs\audits\legacy-python-parity-20260423\python-full-corpus-input-manifest-rerun.txt --dropped-lines-manifest docs\audits\legacy-python-parity-20260423\python-full-corpus-dropped-lines-rerun.txt *> docs\audits\legacy-python-parity-20260423\python-full-corpus-replay-regex-filtered-throttled.log
```

### Throttled full corpus (live run, 2026-04-23)

- Started from a clean `restore-baseline.ps1 -Stack python` after a successful
  `L0217071.log` smoke at `--send-delay 0.005` (`Sent 25610`, DB showed frags
  and statsme consistent with delivery).
- Detached host process writes:
  - `python-full-corpus-replay-regex-filtered-throttled.log` (stdout; line
    buffering may delay `Queued …` lines in the file)
  - `python-full-corpus-replay-regex-filtered-throttled.err.log` (stderr)
  - manifests: `python-full-corpus-input-manifest-throttled.txt`,
    `python-full-corpus-dropped-lines-throttled.txt`
- When complete: append final summary and DB counts here, confirm manifest
  SHA-256 matches legacy manifests, then regenerate `runtime-db-diff.md`.

## Input Policy and Manifest Parity Gate

Legacy and Python were executed under the same input policy, including the
shared filter `--drop-empty-team-enter-events` (needed to avoid legacy Perl
daemon crash on empty-team `entered the game` events).

Manifest parity checks are exact:

- input manifests:
  - equal: `True`
  - lines: legacy `41576`, python `41576`
  - sha256:
    - `9b65f3c47ecb963ce772fb1ae020973268cdd6a50a7d1863a56d219ebfe86898`
- dropped-lines manifests:
  - equal: `True`
  - lines: legacy `169419`, python `169419`
  - sha256:
    - `c79c4d74a817fe5b578c004dbd47a5dc662ebfa87f1303b2699993907a427c6b`

## Runtime DB Diff (`compare_stats_dbs.py`)

Command:

```powershell
python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Output:

- saved to:
  - `docs/audits/legacy-python-parity-20260423/runtime-db-diff.md`
  - `docs/audits/legacy-python-parity-20260423/runtime-db-diff.err.txt`
- report header: `Found logical replay differences in 18 table(s).`
- differing tables:
  - `hlstats_Servers`
  - `hlstats_Actions`
  - `hlstats_Weapons`
  - `hlstats_Maps_Counts`
  - `hlstats_Players`
  - `hlstats_PlayerUniqueIds`
  - `hlstats_PlayerNames`
  - `hlstats_Players_History`
  - `hlstats_Events_ChangeTeam`
  - `hlstats_Events_Chat`
  - `hlstats_Events_Connects`
  - `hlstats_Events_Entries`
  - `hlstats_Events_Frags`
  - `hlstats_Events_Teamkills`
  - `hlstats_Events_PlayerActions`
  - `hlstats_Events_Statsme`
  - `hlstats_Events_Statsme2`
  - `hlstats_Events_TeamBonuses`

Conclusion: the captured `runtime-db-diff.md` reflects the **throttled-off**
Python contour (`--send-delay 0`) and must not be read as parser parity until a
throttled full replay reproduces comparable DB scale to legacy. Page/web audit
remains blocked until an authoritative throttled Python DB diff is reviewed.

## P6d triage: anchor counts (2026-04-27)

P0 triage is documented in `bug-plan.md` (canonical diff:
`runtime-db-diff-p6d-20260426-161410.md`). The following are **headline table
row totals from that diff** (not a second compare run). When the legacy and
Python comparison MySQL instances are up, the runbook read-only queries in
`README.md` should be re-run to log **live** `COUNT(*)` for `hlstats_Players`,
`hlstats_Events_Frags`, `hlstats_Maps_Counts`, `hlstats_Events_Statsme*`,
`hlstats_Players_History`, and the replay server row in `hlstats_Servers` for
`37.230.137.48:27015` — append those numbers under this section for page agents.

| Table / scope | legacy rows (161410) | python rows (161410) |
| --- | ---:| ---:|
| `hlstats_Events_TeamBonuses` | 929,699 | 22,381,762 |
| `hlstats_Events_Entries` | 0 | 190,621 |
| `hlstats_Events_Frags` | 1,078,740 | 1,028,032 |
| `hlstats_Servers` (total rows) | 2 | 2 |

## P0 closure execution pass (2026-04-27)

### Baseline clean-state check

Commands:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy -ForceDumpRestore
powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python -ForceDumpRestore
```

Read-only anchor counts after restore (both contours):

- `hlstats_Players=0`
- `hlstats_Events_Frags=0`
- `hlstats_Players_History=0`
- `hlstats_Events_Entries=0`
- `hlstats_Events_TeamBonuses=0`

### Code/test pass

- P0 code edits:
  - `scripts/hlstats_py/runtime.py` (TeamBonuses round-status event-order semantics)
  - `scripts/hlstats_py/protocol.py` (strict ENTRY classification)
  - tests:
    - `scripts/hlstats_py/tests/test_runtime.py`
    - `scripts/hlstats_py/tests/test_storage.py`
    - `scripts/hlstats_py/tests/test_events.py`
- Test command:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'; python -m pytest scripts/hlstats_py/tests/test_runtime.py scripts/hlstats_py/tests/test_storage.py scripts/hlstats_py/tests/test_events.py
```

- Result: `56 passed`

### Narrow windows + compare

Replay commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 50
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 300
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000
python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20
```

Generated artifacts:

- `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-50-20260427-050502.md`
- `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-300-20260427-050912.md`
- `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260427-051926.md`

### Anchor counts after 1000-window run

- Legacy:
  - `hlstats_Players=323`
  - `hlstats_Events_Frags=6540`
  - `hlstats_Players_History=659`
  - `hlstats_Events_Entries=0`
  - `hlstats_Events_TeamBonuses=5665`
- Python:
  - `hlstats_Players=326`
  - `hlstats_Events_Frags=7828`
  - `hlstats_Players_History=675`
  - `hlstats_Events_Entries=1231`
  - `hlstats_Events_TeamBonuses=41686`

### P6d-M1 TeamBonuses continuation (2026-04-28)

- Root cause confirmed for part of `eligible_gate_reject`: Perl `rewardTeam`
  rewards players in the in-memory roster after `doEvent_TeamSelection`
  updates a trackable team; it does not require a separate `Entries` row.
- Python patch: `storage._reward_team_players` now accepts players that are
  either `reward_eligible` or already in `server_active_players`; connected-only
  players without a trackable team remain rejected.
- Validation:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests`
    -> `107 passed`
  - Python narrow replay:
    `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
    -> `status=ok`, `elapsed_seconds=331.5`
  - Legacy reference replay from dump, same first `1000` logs:
    `processed=1000`, `errors=0`, `elapsed=156.512s`
  - Compare artifact:
    `runtime-db-diff-p6d-narrow-1000-20260428-175918.md`
- Updated `hlstats_Events_TeamBonuses` count:
  `legacy=4765`, `python=4773`, delta `+8` (previous current tail was
  `legacy=4765`, `python=4692`, delta `-73`).
