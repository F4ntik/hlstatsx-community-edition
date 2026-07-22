# Prefix-100 validation: P6f cache and IgnoreBots history lifecycle

Date: `2026-07-22`

## Scope

This record covers the current P6f SQL write-path source state, including the
stdin-transaction `Players_History` ensure-row cache and the final
`IgnoreBots` history-seed lifecycle correction. It links the short
`prefix-100` gate to the matching final `narrow-1000` gate; neither is a
replacement for the retained earlier P6f performance evidence.

## Investigation and corrective runs

The first rebuilt-worker run (`20260722-p6f-history-cache-prefix-100-r1`)
completed its imports but compare reported two Python-only empty
`hlstats_Players_History` rows for `49.5 % FalleN`
(`BOT:c978c1be48576af7145252f0edb97b2a`) and `49.5 % cyx`
(`BOT:b1ea13a294ed2ec9660925eb4f67514c`) on `2024-01-02`. They have zero
gameplay counters and `skill=1000`.

The first proposed broad suppression of ignored-bot seeds was rejected by a
fresh replay: it removed the legacy-compatible initial Jan-1 seeds as well.
Tracing the actual `L0101068` lifecycle showed both BOT identities are created
before midnight and continue across midnight without a new identity. Legacy
creates one initial seed for that runtime player object, but does not add a
new daily seed for its later events. Python had instead called history ensure
for every resolution/event day.

That short window did not cross a second independent source log. The first
full `narrow-1000` check (`20260722-p1-full-narrow-1000-r4`) consequently
found 233 legacy-only zero/default `IgnoreBots=1` BOT history rows. They are
the seed rows created when legacy materialises a fresh player object at the
next `Log file started`; their absence was a source-log lifecycle mismatch,
not a calendar-day rule.

The final correction keeps the persistent player cache intact and separately
tracks ignored-BOT history seeds per `(server, canonical BOT identity, user
id, player id)` source-log epoch. Only the exact parsed generic message
`Log file started` clears that server's seed state. Thus a log that crosses
midnight does not add a seed, while a new input log can add the legacy-matching
seed for the same cached identity. Non-bots and `IgnoreBots=0` retain their
existing behavior. The boundary mutation executes inside the storage
owner/executor (before `begin_online_event`), not on the async runtime thread;
focused tests cover the exact message, cross-midnight suppression, source-log
reseed, rollback/reset, and executor ownership.

The previous `20260722-ignorebots-prefix-100-r4` artifacts remain a useful
rejected intermediate hypothesis, not acceptance evidence. The final prefix
runner used:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 100 -ArtifactLabel prefix-100 -EvidenceRunId 20260722-ignorebots-source-log-prefix-100-r1 -UseDumpRestore -SkipBuild
```

The dual import completed successfully. A separate monitor sampled
`hlstats_Events_Frags` no more than once per 60 seconds instead of polling the
terminal; startup socket/container races were treated as non-verdict samples.
The disposable post-replay GeoIP backfill exited `0`.

`python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
exited `0`: no logical replay differences were found in the configured
statistical tables.

The final full gate used the same runner with `-MaxImportFiles 1000`,
`-ArtifactLabel narrow-1000`, and
`-EvidenceRunId 20260722-ignorebots-source-log-narrow-1000-r1`. Both runner
imports completed; the GeoIP pass exited `0`; and the same logical comparison
exited `0` with no differences. The independent monitor saw the terminal
fragment counts converge at legacy `5464` and Python `5464`. Those counts are
progress telemetry only; the runner, GeoIP, and final DB diff are the
acceptance evidence. The earlier r1/r2/r3/r4 artifacts, including the 233-row
failure, are retained to document rejected hypotheses and the Docker Desktop
bind-mount I/O diagnosis that led to the named scratch-volume harness.
