# Post-mapfix stage notes

## What was changed
- Runtime map lifecycle handling now stages `Loading map` into `pending_map` and only switches `current_map` on `Started map` (`scripts/hlstats_py/runtime.py`).
- ChangeTeam write path now:
  - ignores unresolved actors,
  - ignores bot actors,
  - deduplicates repeated `(server, player, map, team, event_time)` rows
  (`scripts/hlstats_py/storage.py`).
- Added targeted regression tests for lifecycle and ChangeTeam filtering/dedupe (`scripts/hlstats_py/tests/test_runtime_map_lifecycle.py`, `scripts/hlstats_py/tests/test_runtime.py`, `scripts/hlstats_py/tests/test_storage.py`).

## Critical execution correction
- Snapshot restore was producing misleading drift due to pre-diverged stack snapshots.
- Authoritative parity runs in this stage were re-based to `restore-baseline.ps1 -ForceDumpRestore` for both stacks.
- Pre-replay dump-restore comparison is clean (`runtime-db-diff-after-dump-restore-pre-replay.txt`).

## Window-50 outcome
- Input parity: strict match (`strict-input-parity-50.txt`).
- Maps/Actions targets are no longer dominant error source under dump-restore baseline.
- `hlstats_Events_ChangeTeam` improved from `legacy=7, python=108` to `legacy=7, python=5`.
- Remaining top drift on window-50 is mostly identity/encoding and history alignment, not map lifecycle noise.

## Window-300 control outcome
- Input parity: strict match (`strict-input-parity-300.txt`).
- Residual drift still present on larger corpus:
  - `hlstats_Maps_Counts`: legacy-only 6 / python-only 8
  - `hlstats_Actions`: legacy-only 10 / python-only 13
  - `hlstats_Events_PlayerActions`: legacy-only 129 / python-only 484
  - `hlstats_Events_ChangeTeam`: legacy-only 33 / python-only 15
- This indicates improvement, but not full parity at 300 yet.

## Remaining risks
- Player identity/name normalization (encoding and alias mapping) still shifts rows across Players/Names/History and cascades into actions.
- Action codes `amx_chat`, `time`, `latency` remain python-only in 300-window and need explicit legacy-compat filtering policy.
- Team transition semantics for selected human players still diverge slightly on 300-window.
