# P1 Online Hardening Design

## Approval and scope

The user approved execution of the P1 hardening priority on 2026-07-22.
Each completed P1 slice must pass a fresh disposable `prefix-100` replay, and
the completed priority must pass a fresh `narrow-1000` replay before it is
published. Changes are committed as small, reviewable units and pushed only
after the final acceptance gate.

The active lane is `hlstatsx-community-edition-python-i18n`. Existing dirty
SQL-write optimisation work and retained evidence are preserved; this design
does not authorise rewriting or overwriting them.

## Chosen architecture

1. **Ingress and authentication**
   - Redact proxy credentials before any packet reaches a log sink.
   - Treat a missing, null, empty, or whitespace `Proxy_Key` as a startup/reload
     error rather than as an empty credential.
   - Bound inbound queues and record controlled drops. `IngressQueueSize` is a
     distinct back-pressure control; it must not silently repurpose the legacy
     `EventQueueSize` persistence threshold.

2. **Ordered online processing**
   - Keep one ordered worker pipeline per runtime so that legacy stateful event
     ordering remains intact.
   - Execute one online logical event in an explicit DB transaction. The
     cross-event event and StatsMe buffers remain stdin-only; an online event
     may only flush data inside its own transaction.
   - On a DB operation or commit error, roll back where possible, stop intake,
     and terminate non-successfully. A network ambiguity during commit is
     explicitly fail-closed, not silently retried without idempotency.

3. **Lifecycle correctness**
   - `RELOAD` must flush deferred state successfully before loading new state
     and resetting caches.
   - Graceful stop closes ingress first, drains accepted work to a deadline,
     then performs an error-propagating final flush.
   - PID files must prove process ownership before status, termination, or
     stale-file cleanup.

4. **FTP checkpoint correctness**
   - Replace the independent file marker with a durable import checkpoint that
     commits in the same MySQL transaction as the accepted file/batch state.
   - Do not move the marker alone: that can either skip rolled-back logs or
     duplicate append-only events after a threshold commit.

5. **Evidence publication**
   - Product CI must cover shared runtime packages and operational tools.
   - CI may upload only an allowlisted, secret/PII-checked publication set;
     raw log, DB snapshot, local configuration, and trace inputs remain local.

## Validation and commit protocol

- Unit/async tests demonstrate each closed invariant before replay.
- Each P1 slice receives a unique `prefix-100` run (`ArtifactLabel=prefix-100`)
  in disposable comparison databases. Monitoring polls frag counts no more than
  once per minute and reports only milestones, deltas, first failure, and the
  final verdict.
- The final gate is a unique `narrow-1000` dual-contour run with matching
  manifests, drop/ignore artefacts, anchors, and stable-key comparison.
- A commit contains one P1 slice and its focused tests/docs only. Before the
  final push, inspect staged files and run a secret scan; do not stage retained
  or generated audit artefacts by wildcard.

## EventStorage evolution after P1

P1 intentionally adds clear transactional seams but does not rewrite
`EventStorage`. The next phases extract `ServerSessionState`, SQL repositories,
and `EventUnitOfWork` one vertical event family at a time, keeping
`EventStorage` as a compatibility facade and retaining the same single-log and
narrow-parity gates for every extraction.
