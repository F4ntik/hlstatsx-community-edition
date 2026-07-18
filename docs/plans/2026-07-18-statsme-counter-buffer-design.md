# Statsme counter delta buffer design

## Goal

Reduce offline stdin import time by coalescing repeated SQL updates derived
from `Statsme` events while preserving every append-only event row and the
accepted `narrow-1000` database result.

The measured contour currently issues 32,290 player shots/hits updates and
32,250 server CT/T shots/hits updates. These 64,540 direct statements are the
largest remaining parity-safe write-reduction candidate after the
`Players_History` ensure cache.

## Scope and invariants

- Enable the optimization only while `begin_stdin_batch()` has an active
  positive transaction batch size.
- Keep `hlstats_Events_Statsme` and `hlstats_Events_Statsme2` inserts unchanged;
  they remain append-only history and continue through `EventBuffer`.
- Accumulate only additive derivatives:
  - `hlstats_Players.shots` and `hlstats_Players.hits`, keyed by `playerId`;
  - `hlstats_Servers` CT/T total and current-map shots/hits, keyed by
    `serverId` and the event-time team.
- Preserve the online/autocommit path exactly: without an active stdin buffer,
  execute the existing SQL immediately.
- Never carry deltas across an import lifecycle reset, rollback, or failed
  transaction.

## Components and data flow

Add a small storage-local delta buffer following the existing
`FragWriteDeltaBuffer` pattern. It owns two deterministic mappings:

1. player id to `(shots, hits)`;
2. `(server id, CT/T)` to `(shots, hits)`.

`_record_statsme()` continues to resolve the player, write the Statsme event,
and update in-memory player rollups at the same point. Its two direct counter
updates are routed into the new buffer only in stdin batch mode.

At a safe flush boundary, the buffer emits one additive player update per
dirty player and one additive server update per dirty server/team key. The
buffer is cleared only after successful emission.

## Ordering and lifecycle boundaries

Flush pending Statsme counters:

- before each stdin transaction commit;
- during `flush_pending()`, `finalize_import()`, and `end_stdin_batch()`;
- before a server map transition resets current-map CT/T counters;
- before any affected persisted counter is re-read after runtime/player-cache
  invalidation, if source inspection identifies such a path.

On rollback or `abort_stdin_batch()`, clear the buffer without emitting SQL.
Initialization, normal completion, abort, and `reset_runtime_state()` must all
leave no stale deltas. Flush order must keep all emitted counter updates in the
same transaction as the event rows that produced them.

## Error handling

An emission failure follows the existing storage failure path: the transaction
is rolled back and all in-memory write buffers are cleared. Partial buffered
state must not be reused after an exception.

## Alternatives rejected

- Coalescing or suppressing Statsme/Admin event inserts would destroy audit
  history and is out of scope.
- A parser rewrite has a much smaller measured ceiling than the remaining SQL
  path.
- Parallel file import is not safe without proving that player, server, map,
  and event ordering can be partitioned.
- Global player-resolution caching has a higher parity risk around reconnects,
  userid rollover, bots, and aliases.

## Acceptance

1. Unit tests cover aggregation, isolation by player/server/team, direct-mode
   fallback, map-reset ordering, commit/finalize flush, and rollback/reset.
2. The complete Python test suite and compile check pass.
3. A fresh prefix replay is stable.
4. A fresh no-reuse Python `narrow-1000` replay matches the accepted legacy
   manifest and stable-key database comparison, allowing only the documented
   GeoIP-only residual.
5. The same 1,000-file performance method reports wall time, throughput,
   logical SQL, physical query calls, and Statsme counter template counts.

The expected additional end-to-end gain is 15-25%, but this is a target, not
an acceptance claim; only the fresh benchmark establishes the result.
