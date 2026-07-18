# Statsme counter delta buffer implementation plan

## Goal

- Reduce offline stdin SQL round trips by coalescing additive Statsme-derived
  player and server counters without changing event history, online behavior,
  or accepted replay parity.

## Assumptions / constraints

- The user approved the recommended import-only Statsme counter buffer.
- `narrow-1000` stable-key parity is the promotion gate.
- Existing append-only Statsme/Statsme2/Admin event buffering is unchanged.
- Current dirty working-tree changes are preserved; this slice must not revert
  or absorb unrelated work.
- Expected speedup is a measurement target, not a correctness condition.

## Research (current state)

- Modules/subprojects involved:
  - active product lane only: `hlstatsx-community-edition-python-i18n`.
- Key files/paths:
  - `scripts/hlstats_py/storage.py`;
  - `scripts/hlstats_py/frag_write_delta_buffer.py` as the local pattern;
  - `scripts/hlstats_py/tests/test_storage.py`;
  - the 2026-07-18 SQL-write benchmark audit.
- Entrypoints:
  - `hlstats_py.runtime --stdin` through `direct_import_artifacts.py`.
- Related configs/flags:
  - `--stdin-transaction-batch-size`;
  - existing `EventBuffer` and adapter `executemany_chunk_size`.
- Data models/storage touched:
  - additive updates to `hlstats_Players.shots/hits`;
  - additive CT/T total and current-map updates in `hlstats_Servers`.
- Interfaces/contracts:
  - append-only event schemas and runtime CLI remain unchanged.
- Existing patterns to follow:
  - `FragWriteDeltaBuffer` lifecycle, deterministic flush, rollback clear, and
    immediate fallback when no stdin buffer is active.

## Analysis

### Options

1. Add a dedicated typed Statsme delta buffer and route only the three known
   additive counter templates through it.
2. Generalize the frag buffer into a universal SQL delta layer.
3. Increase transaction/buffer sizes without reducing logical counter writes.

### Decision

- Chosen: option 1.
- Why: it captures the 64,540 measured direct updates with the narrowest query
  surface and avoids a broad abstraction or durability/rollback change.

### Risks / edge cases

- Current-map counters must flush before a map-reset statement.
- CT and TERRORIST contributions must remain separated by event-time team.
- A failed flush must not reuse partially emitted in-memory deltas.
- Player lifecycle/cache invalidation must not re-read stale persisted counters.
- Direct/online mode must retain one immediate update per event.

### Open questions

- None. Source inspection during implementation will determine whether an
  additional pre-read flush hook is required; the conservative rule is to
  flush whenever affected persisted counters could be observed.

## Q&A results

- Outcome/acceptance criteria:
  - try the recommended safe optimization and measure it on the same 1,000
    files.
- Scope boundaries:
  - offline acceleration is primary; no event suppression or unsafe parallel
    replay.
- Constraints/non-goals:
  - keep online behavior unchanged and preserve legacy parity.
- Known modules/paths/subprojects:
  - active Python+i18n product lane and its replay tooling.
- Decisions made in Q&A:
  - implement the import-only Statsme counter delta buffer first.
- Remaining open questions:
  - none.

## Implementation plan

1. Add focused unit tests for the standalone delta buffer: aggregation,
   deterministic isolation, flush, and clear.
2. Inspect all reads/resets of affected player/server columns and encode the
   required ordering tests before integrating the buffer.
3. Add the buffer class and route only the player shots/hits plus CT/T server
   shots/hits templates through it while stdin batching is active.
4. Wire initialization, commit/finalize/end flush, map-transition pre-flush,
   rollback/abort/reset clear, and immediate-mode fallback.
5. Run targeted tests, full `hlstats_py` tests, compile checks, and diff checks.
6. Rebuild the worker and run a fresh prefix parity contour.
7. Run a fresh no-reuse Python `narrow-1000` contour against validated legacy
   evidence and verify manifests, anchors, snapshots, and stable-key diff.
8. Repeat the 1,000-file performance measurement without using its result as a
   parity substitute; compare wall time, throughput, logical SQL, physical
   calls, and template counts.
9. Update status/release/performance documentation with measured results and
   limitations.

## Tests to run

- focused delta-buffer and storage lifecycle pytest selection;
- `python -m pytest scripts/hlstats_py/tests -q`;
- `python -m compileall scripts/hlstats_py`;
- `git diff --check`;
- prefix replay/compare;
- canonical `narrow-1000` replay/compare;
- same-manifest 1,000-file benchmark, with normal and/or equivalently profiled
  variants clearly labelled.
