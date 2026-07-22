# P1 Online Hardening Acceptance and EventStorage Evolution

## Accepted scope

P1 online hardening is accepted on 2026-07-22 in the active Python+i18n
lane. It preserves the existing uncommitted SQL/StatsMe optimisation work and
does not stage generated replay evidence.

The accepted implementation provides:

- fail-closed proxy authentication: absent, null, empty, or whitespace proxy
  keys are rejected, and proxy-key values are redacted before diagnostic logs;
- one ordered online worker with one explicit transaction per logical event;
  deferred player/history/name/server rollups are flushed in that same
  transaction, never carried into the next packet;
- bounded, independently configured UDP ingress (`IngressQueueSize`, default
  1000), controlled overload drops, and an exact drop metric; legacy
  `EventQueueSize` retains its prior meaning;
- reload flush-before-reset, ingress-first shutdown, bounded queue drain, and
  fail-closed runtime errors;
- one DB/storage owner thread, finite connect/read/write timeouts, and an
  atomic deadline-versus-commit-admission fence. An uninterruptible DB-API
  deadline reaches the CLI boundary as exit `70`; ordinary runtime failures
  still exit `2`;
- PID identity state tied to Linux boot id, process start time, expected module,
  and `pidfd`, so lifecycle scripts never signal an unrelated reused PID;
- transactional FTP checkpoints, with default durable mode refusing missing or
  non-InnoDB importer-write tables;
- CI coverage for shared operational packages and a metadata-only nightly
  publication artifact; and
- a replay worker image that includes the canonical GeoIP backfill module.

## Deployment prerequisites

- Apply `sql/migrations/2026_07_22_ftp_checkpoint.sql` before enabling the
  default durable FTP path. Convert the same 22 importer-write tables to
  InnoDB first; the CLI intentionally refuses durable operation otherwise.
- Use `scripts/run_proxy_py` and `scripts/run_hlstats_py` only on supported
  Linux/systemd hosts with procfs and Python pidfd support. Non-Linux hosts use
  foreground Python processes under a platform-native supervisor, without
  shell PID-file control.
- Set `IngressQueueSize` independently when site load requires a value other
  than the conservative default. Do not tune it by changing `EventQueueSize`.

## Evidence and commits

Every P1 slice received a fresh disposable `prefix-100` gate. The accepted
full receipt is:

```text
Run-DualContour-1000.ps1
  ArtifactLabel: narrow-1000
  EvidenceRunId: 20260722-p1-full-narrow-1000-r2
  Inputs:        1000 / 1000, byte-identical manifests
  Anchors:       Frags 5464/5464; Players 323/323;
                 Team bonuses 4765/4765; Entries 0/0
```

The r2 worker ran the canonical post-replay command
`python -m hlstats_awards_py --configfile /app/hlstats.conf --geoip` in the
disposable Python contour (exit 0). The subsequent read-only
`compare_stats_dbs.py --max-examples 20` exited 0 with zero logical table
differences. The runner itself writes snapshots/manifests but does not invoke
the comparison; retaining both steps is therefore required for future full
receipts.

P1 commits are intentionally one concern each:

- `1f832a7` — proxy-key redaction and fail-closed configuration;
- `aecff76` — CI path and artifact governance;
- `d3e0b20` — transactional FTP checkpoints and disposable schema setup;
- `24261cf` — PID ownership verification;
- `40dd374` — online transaction/lifecycle/back-pressure hardening; and
- `712bf51` — disposable GeoIP backfill worker packaging.

## Gradual EventStorage decomposition

Do not rewrite `EventStorage` in one change. It remains a compatibility facade
until the final phase, and each extraction moves one vertical behaviour while
preserving the online one-event and stdin-batch contracts.

1. **Characterise the facade.** Freeze the public methods currently used by
   handlers/runtime, document their online versus stdin transaction semantics,
   and add contract tests around reload, rollback, and finalisation. No code
   moves in this phase.

2. **Extract `ServerSessionState`.** Move only in-memory server/player/session
   maps and reset behaviour behind a small state object. `EventStorage` delegates
   to it, so SQL behaviour and handler call sites stay unchanged.

3. **Extract repositories by vertical event family.** Start with an append-only
   low-coupling family, then move `PlayerRepository` (identity/profile/history)
   and `ServerStatsRepository` (totals/map state). Repositories receive a
   transaction-bound connection; they do not open or commit transactions.

4. **Extract `EventUnitOfWork`.** Move explicit online begin/commit/abort and
   stdin batch lifecycle into a dedicated unit of work. It owns the transaction
   boundary, deferred-rollup flush, and commit ambiguity policy. The facade
   delegates so callers retain the existing API during migration.

5. **Move event application services one family at a time.** A service combines
   parsing result, `ServerSessionState`, repositories, and `EventUnitOfWork`.
   Only after every handler family uses services should `EventStorage` shrink to
   a deprecated facade, then be removed in a separately approved breaking
   change.

For every vertical extraction: retain old and new paths behind the facade,
write unit regressions for the moved family, run a fresh disposable
`prefix-100`, and preserve a `narrow-1000` plus GeoIP-backfill/logical-compare
receipt at each completed phase boundary. No extraction may widen a single
online event into a cross-event buffer or make a repository responsible for
transaction ownership.
