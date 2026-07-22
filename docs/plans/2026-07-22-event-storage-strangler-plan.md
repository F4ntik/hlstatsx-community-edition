# Gradual EventStorage strangler plan

Date: `2026-07-22`

## Status and decision

Status: **planned, not started**.

`EventStorage` is replay-critical infrastructure, not a normal large class
that should be replaced in one refactor. The current facade in
`scripts/hlstats_py/storage.py` deliberately owns event dispatch, player and
server session state, deferred rollups, append-only write buffers, and both
online and stdin transaction lifecycles. `HlstatsRuntime` confines it and the
DB connection to a one-worker executor to preserve packet order and DB-API
ownership.

The architectural direction is a strangler: keep `EventStorage` as the stable
compatibility facade while extracting one bounded responsibility at a time.
No phase may weaken ordering, transaction, rollback, or replay parity merely
to make the class shorter.

## Non-negotiable contracts

Before moving a line of behavior, preserve these public/lifecycle operations:

- online: `begin_online_event`, `commit_online_event`, `abort_online_event`;
- stdin: `begin_stdin_batch`, `end_stdin_batch`, `abort_stdin_batch`,
  `finalize_import`, and `flush_pending`;
- session reset: `reset_runtime_state`;
- event entrance: `record(update, context)` and the existing category dispatch;
- single-threaded storage execution in `HlstatsRuntime`;
- current buffer flush order, deferred profile/history rollups, autocommit
  restoration, and rollback behavior.

Repositories introduced by the work receive the transaction-bound connection
from the facade/unit of work. They must not open connections, call `commit`, or
make cross-event ordering decisions themselves.

## Incremental sequence

### 0. Characterize the facade first

Freeze the observable contract with focused tests before extracting anything:
event-category dispatch, SQL order where it is externally significant,
online commit/rollback, stdin batch/abort/finalize, reload/reset, buffer flush,
and the `IgnoreBots` source-log epoch rule. Capture the current interface and
callers in a short architecture test note.

Exit condition: the contracts have named regression tests and a clean
100-file bounded replay receipt.

### 1. Extract state containers without changing SQL ownership

Move only cohesive in-memory state (starting with per-server membership,
presence, policy/config, and activity maps) into a typed
`ServerSessionState`-style component. `EventStorage` remains the owner of
reset and supplies the component to existing handlers; no handler or SQL query
moves in this phase.

This is intentionally first because it reduces constructor/caching complexity
without changing a database write, transaction, or event-category boundary.

Exit condition: exact reset/reload/idle-prune tests plus clean 100-file gate.

### 2. Extract transaction-free write repositories by vertical slice

Start with the lowest-coupling append-only event insert family. Each repository
contains SQL mapping only and is called by the facade with its existing
connection/cursor and buffering decision. Move one family at a time; keep
append-only inserts, counter delta buffers, and deferred rollups separate.

Only after that is stable, extract the higher-risk `PlayerRepository`
(identity/profile/name/history) and `ServerStatsRepository` (totals/map
lifecycle). Player identity/history cannot be treated as a simple CRUD table:
the current runtime object lifecycle and flush timing are parity behavior.

Exit condition for every repository slice: repository contract tests, the
affected storage tests, a clean 100-file gate, and no SQL ordering change.

### 3. Make the unit-of-work seam explicit

Introduce an `EventUnitOfWork` behind the facade to own online begin/commit/
abort and stdin batch/end/abort lifecycle. It coordinates existing buffers,
deferred rollup flushes, cursor cleanup, autocommit restoration, and rollback.
It does not make repositories independently transactional.

Exit condition: failure injection proves rollback and autocommit recovery for
both online and stdin modes; full `narrow-1000` acceptance is required because
this phase changes a cross-category boundary.

### 4. Extract application services one event family at a time

Move category behavior from `record()` only after its state and persistence
seams are stable: low-coupling chat/entry/generic families first, then actions,
connections/team state, Statsme, and finally frag/team-bonus logic. The facade
continues to dispatch and owns the original ordering until each service is
proven equivalent. Do not move world-state/min-player gating, dedupe, or
streak/skill rules speculatively.

Exit condition per family: focused legacy-informed regression, clean 100-file
gate, and an accepted logical comparison for the affected event tables.

### 5. Retire only a proven compatibility layer

After all callers use stable ports and a complete milestone has passed its full
replay gate, collapse `EventStorage` into a small orchestration facade or
rename it only if that improves the public contract. No caller migration or
multi-worker execution is allowed until the original one-worker and replay
acceptance contracts have separate evidence.

## Verification cadence

In this repository the requested narrow 100-file gate is named `prefix-100`
in commands and evidence. After **every closed slice**, run focused tests and a
fresh release-clean `prefix-100` using the canonical runner. After a coherent
milestone (for example, a completed repository group or the unit-of-work
boundary), run fresh `narrow-1000` with maintenance, logical DB comparison,
legacy EN reference smoke, and Python EN/RU product smoke.

Long-run monitoring remains delegated and DB-backed: sample
`hlstats_Events_Frags` in both disposable DBs no more than once per 60 seconds.
It is telemetry only; exit status and retained comparison evidence decide the
gate.

## Stop conditions

Stop and revert the active slice before proceeding if any of the following
appears:

- a change in logical DB output, SQL ordering, or rollback semantics without a
legacy-backed explanation;
- an extracted component acquiring its own connection or transaction boundary;
- a need to change more than one event family merely to make a test pass; or
- a failed 100-file gate or an unexplained full `narrow-1000` difference.

This plan deliberately favors many small reversible seams over a rewrite. It
keeps the current migration evidence useful while making the Python stack more
testable, explicit, and maintainable.
