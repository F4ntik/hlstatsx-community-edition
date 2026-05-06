# Parity Runtime Decisions Refactor

## Current baseline

- Branch point: `test` at `9d4bd6b fix(hlstats-py): align team bonus active roster eligibility`.
- Runtime parity issue still open: `LP-P6D-001`.
- Current narrow-1000 TeamBonuses baseline:
  - legacy: `4765`
  - python: `4774`
  - delta: `+9`
- Latest comparison artifact:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260428-175918.md`.
- Do not continue fixing residual TeamBonuses behavior in the first refactor pass.
  The first slice is behavior-neutral structure and traceability.
- Parity acceptance policy:
  `docs/parity-acceptance-policy.md`.
  The residual TeamBonuses `+9` is diagnostic backlog unless RC-B/identity
  triage proves user-visible or aggregate-critical impact.

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

After TeamBonuses is behavior-neutral and validated, use the acceptance policy
before repeating the same pattern for:

- ChangeTeam record/drop decisions
- Connect/Disconnect/Entry record/drop decisions
- identity/name-only edge cases
- broader `server_active_players` lifecycle operations

Do not start these as cosmetic code movement. RC-B impact triage is now
classified by `docs/parity-acceptance-policy.md`; the scoped unresolved
server-origin `PlayerActions` fix has landed, while `ChangeTeam`, `Chat`, and
remaining `PlayerActions` drift stay diagnostic unless RC-C identity/action
attribution evidence promotes a narrower must-fix subset. RC-C runtime slices
also landed for legacy `IgnoreBots` bot policy and transient invalid identity
handling: bot profiles are hidden/reset, bot-owned `Frags` / `PlayerActions` /
`Chat` / `Statsme` / `Statsme2` rows are skipped, `UNKNOWN` / pending / LAN
unique ids no longer create visible players, and `STEAM_[0-9]+:` ids are stored
in the legacy canonical form. Current player-count anchors are `Players
323/323` and visible `250/250`; `Connects` is now `992/992`.

Current extraction status (2026-04-30): identity persistence and unique-id
normalization now have explicit decision helpers in `runtime_decisions.py`
(`canonical_unique_id`, `is_transient_unique_id`, and
`should_persist_player_identity`). This was a behavior-neutral refactor over
the already validated transient-id slice; remaining human
`PlayerNames` / `Players_History` attribution drift still needs evidence before
any behavior change.

Current-name flush follow-up (2026-05-01): after the deferred profile-name
slice, `storage.py` now also flushes cached profile names during
`finalize_import()` and `flush_pending()` through
`_flush_all_player_profile_names(...)`. This keeps the behavior aligned with
legacy periodic/shutdown `flushDB` for players that do not emit a disconnect
before the replay/import tail. The same slice also flushes the previous live
profile name and clears alias-use suppression when a stable unique id reappears
under a new userid, matching the legacy `getPlayerInfo` handoff far enough to
restore repeated alias-use accounting. Idle eviction now also flushes the
cached profile name before removing a stale active player from in-memory
tracking, matching legacy timeout cleanup through `removePlayer` /
`playerCleanup` / `flushDB`. The `0:723234133` alias counters now match legacy,
but its current profile name still needs a narrower follow-up before treating
the broader `PlayerUniqueIds` / `PlayerNames` / `Players_History` drift as
closed.

Name-change follow-up (2026-05-01): Perl routes `"changed name to"` through
`doEvent_ChangeName` and `HLstats_Player->setName($newname)`. Python had parsed
these lines as `NAME_CHANGE` but the fallback handler emitted only generic admin
noise, so the new name was not applied to `PlayerNames` or the deferred
`lastName` cache. Generic name-change updates now carry
`event_code="change_name"` and `new_name`; storage applies the new alias/current-name cache
without incrementing the old alias for an already-known live player. This is a
small behavior fix, not a broad generic-event policy change. Replay
confirmation is recorded in the 2026-05-05 parity-runner ordering follow-up.

Automation continuation (2026-05-05): reviewed the name-change/parser contract
and kept the continuation behavior-neutral. The event test now asserts the
`change_name` / `new_name` contract explicitly, and the obsolete
`track_name_history` parameter was removed from `_touch_player_profile(...)`
because alias-history writes now live at the `_touch_player_name(...)` call
site. Targeted and broad no-Docker Python test gates pass.

Parity-runner ordering follow-up (2026-05-05): legacy evidence for
`0:723234133` matched the Python name-change/storage behavior once the same
filename-sorted input window was used. The Python FTP parity contour had been
sorting eligible logs by modification time, which can replay `L0106059.log`
before `L0106057.log` for this anchor. `hlstats_ftp_py` now keeps mtime sorting
as the default operational behavior and adds `--order-by-name` for replay
parity; `Run-DualContour-1000.ps1` passes the flag for the Python parity import.
Because the normal FTP state marker is mtime-based, `--order-by-name` is
guarded as a fresh-state-only mode; the dual-contour runner deletes the Python
FTP state before invoking it.
Clean replay plus GeoIP backfill closes the anchor (`lastName=Райымбек Гослинг`,
`3/4`, `KZ/Kazakhstan`, alias `numuses=2/2`). Current compare residuals are
`11` tables; `TeamBonuses` moved to `4765/4774` because the parity input order
is now corrected, not because TeamBonuses behavior was changed.

PlayerNames attribution follow-up (2026-05-06): the next RC-C slice treated
human alias attribution as one cluster. Python now accumulates
`hlstats_PlayerNames` stat deltas in memory and writes them only at
player/profile flush boundaries, instead of attaching every event immediately
to the current parsed actor name. Stdin transaction commits are not player
flush points; this matches legacy stdin import, where the periodic player
`flushDB` path is gated by `!$g_stdin`. Profile flushes still occur at import
finalize, explicit `flush_pending()`, disconnect/idle cleanup, and stable
unique-id userid handoff. Alias `numuses` is also forced on explicit name-change
touches and reconnect/object-lifecycle touches, including same-userid reconnect
after disconnect. Narrow-1000 replay improves `hlstats_PlayerNames` normalized
drift from `64/65` to `34/35`; `X3` and `SayNor` anchors align. Remaining
`fnat1k` drift is now only alias `numuses`/`lastuse` (`106` vs `103`), not
per-alias stat totals. A candidate change that flushed rollups before every
explicit name change was rejected after replay because it regressed
`PlayerNames` to `64/65`; do not revive it without tracing the exact legacy
player-object lifecycle for those rows.

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
- python: `4774`
- delta: `+9`

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
