# Parity Runtime Decisions Refactor

## Current baseline

- Branch point: `test` at `9d4bd6b fix(hlstats-py): align team bonus active roster eligibility`.
- Runtime parity issue still open: `LP-P6D-001`.
- Current narrow-1000 TeamBonuses baseline:
  - legacy: `4765`
  - python: `4773`
  - delta: `+8`
- Latest comparison artifact:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260428-175918.md`.
- Do not continue fixing residual TeamBonuses behavior in the first refactor pass.
  The first slice is behavior-neutral structure and traceability.

## Goal

Make Python runtime/storage parity work easier to audit by separating behavior
decisions from SQL persistence. Future agents should be able to inspect one
explicit runtime decision layer when comparing Python behavior against legacy
Perl, instead of reconstructing policy from scattered `storage.py` branches.

## Non-goals

- No page-level audit.
- No edits in `hlstatsx-community-edition/` or
  `hlstatsx-community-edition-web-ru-i18n/`.
- No new parity bug fix unless required to preserve current behavior during the
  refactor.
- No UDP replay for mass validation. Use direct stdin paths only:
  `Run-ContourFtpArtifacts.ps1`, `direct_import_artifacts.py`, or
  `hlstats_ftp_py`.

## Proposed shape

Introduce an explicit runtime decision layer under `scripts/hlstats_py/`, for
example:

- `runtime_state.py`
  - `ServerRuntimeState`
  - per-server roster sets and player lifecycle snapshots
  - map/reset hooks currently represented inside `HLStatsStorage`
- `runtime_decisions.py`
  - small pure decision functions
  - stable reason codes
  - serializable decision records for opt-in parity traces

Keep `storage.py` as the SQL adapter and orchestration boundary:

- resolve DB ids
- call decision functions with a state snapshot
- execute inserts/updates
- update state through explicit methods

## Decision functions

Initial APIs should stay narrow and grow only when moved behavior needs them.

```python
should_reward_team_player(...)
should_record_change_team(...)
should_record_connect(...)
should_record_disconnect(...)
should_record_entry(...)
should_count_for_minplayers(...)
should_ignore_bot(...)
```

Each function should return a small structured result rather than a bare bool:

```python
Decision(
    allowed: bool,
    gate: "team_bonus_eligibility",
    reason: "active_roster" | "reward_eligible" | "wrong_team" | "...",
)
```

Reason code expectations:

- stable strings, safe for grep and JSONL artifacts
- one primary `gate`
- one primary `reason`
- no DB-specific wording unless the decision truly depends on persisted DB state

## Trace contract

Decision tracing must be opt-in and silent by default.

Proposed environment variable:

```powershell
$env:HLSTATS_PARITY_DECISION_TRACE_PATH = "scripts/replay_baseline/artifacts/parity-decisions.jsonl"
```

Artifact rules:

- write JSONL/JSON only when the env var is set
- default path should not be implicit
- generated traces stay untracked unless intentionally copied into
  `docs/audits/...`
- trace writes must not affect runtime decisions

Each decision record should include:

- `event_time`
- `action`
- `map`
- `server_id`
- `player_id`
- `unique_id` and/or `name` when available
- `team`
- `gate`
- `reason`
- `allowed`
- state snapshot relevant to the gate, for example:
  - active roster membership
  - reward eligibility membership
  - last known team
  - IgnoreBots classification
  - MinPlayers count input

## First slice: TeamBonuses roster decisions

Move only the roster/eligibility decisions used by TeamBonuses first. This keeps
the slice small and tied to the fresh LP-P6D-001 context.

Candidate behavior to move without changing:

- active player roster membership
- reward-eligible player membership
- team match gate
- IgnoreBots/team reward bot gate
- MinPlayers count input, if currently coupled to the same roster state
- TeamBonuses dedupe gate, only if it can be moved without changing insert
  order or key semantics

Expected storage boundary after slice:

- `storage.py` still owns DB writes to `hlstats_Events_TeamBonuses`
- `storage.py` calls `should_reward_team_player(...)`
- decision layer returns allow/reject plus reason
- existing tests continue to assert the same rows and counters

## Later slices

After TeamBonuses is behavior-neutral and validated, repeat the same pattern for:

- ChangeTeam record/drop decisions
- Connect/Disconnect/Entry record/drop decisions
- identity/name-only edge cases
- broader `server_active_players` lifecycle operations

Do not start these until the TeamBonuses slice has a clean test run and, if
replay-critical code moved, a narrow replay compare.

## Validation gates

For any behavior-neutral refactor:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests
```

For any refactor that can affect replay-critical row decisions:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000
python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Expected TeamBonuses count for behavior-neutral work remains:

- legacy: `4765`
- python: `4773`
- delta: `+8`

If the count moves, stop and classify it as either an accidental behavior change
or an explicitly approved parity fix.

## Replay reuse optimization

Do not rerun the legacy narrow-1000 contour by habit. Legacy Perl behavior is
the stable reference for this branch, so a prepared legacy DB/container can be
reused when all of these inputs match:

- baseline restore source and snapshot/dump identity
- retained corpus path and first `1000` sorted log filenames
- server identity: `37.230.137.48:27015`
- replay policy: `--drop-empty-team-enter-events`
- comparison scope: narrow-1000 runtime diff

Before skipping legacy replay, record or verify a fingerprint that includes the
items above plus the SQL snapshot timestamp/counts. If any input changes, rerun
legacy from dump. If only Python runtime/storage code changes, prefer restoring
or reusing the already validated legacy narrow-1000 DB and rerun only the Python
FTP/stdin contour plus `compare_stats_dbs.py`.

Future tooling should make this explicit instead of relying on memory:

- store contour state in `scripts/replay_baseline/comparison/.parity-state/`
  with separate legacy and Python stage fingerprints
- use `Run-DualContour-1000.ps1 -ReuseValidLegacy` for Python-only refactors;
  when the legacy metadata/fingerprint is valid, the script skips legacy
  compose down/up, restore, import, and SQL snapshot
- use `-AdoptCurrentLegacy` once after a known-good legacy narrow-1000 run if
  the DB is already loaded but metadata was not created yet
- write inspectable contour metadata to
  `scripts/replay_baseline/comparison/.parity-state/contour-info/`
- expose the same metadata from inside running containers as
  `/CONTOUR_INFO.json`, so `docker exec` can answer what DB/window is currently
  loaded

## Stop rules

- Stop before implementation after this design doc is created.
- Stop if behavior changes without an intentional parity-fix decision.
- Stop if a trace artifact is written without an explicit env var.
- Stop if validation requires UDP for mass replay.
- Stop if the refactor needs edits outside this product lane.
