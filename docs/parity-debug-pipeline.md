# Parity Debug Pipeline

Use this loop when a broad replay contour finds a legacy/Python residual. The
goal is to stop debugging against `narrow-1000` directly and reduce each bug to
one log file, then to a smaller line window when possible.

## 0. Legacy-First Triage

Before changing Python behavior, make the legacy rule explicit:

- use a read-only subagent to inspect the Perl implementation and summarize the
  exact legacy algorithm, lifecycle rule, and file/function evidence
- use a separate read-only subagent when useful to group replay artifacts into
  true runtime mismatches versus identity/name/diagnostic noise
- verify the subagent conclusions locally against the source log and DB rows
- write the focused regression test from the legacy rule, not from a Python
  hypothesis

The expected behavior is the legacy Perl result unless a difference is
explicitly documented as accepted policy. Use stable identifiers such as
`uniqueId` when player display-name attribution is itself a known residual.

## 1. Detect With The Broad Contour

Run the normal contour only to discover residuals:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore
```

The release-clean runner performs its own post-import maintenance, compare,
legacy EN-reference smoke, and Python EN/RU product smoke. Use
`-ReuseValidLegacy -SkipMaintenance` only when
deliberately collecting a raw-debug contour; it is not release-clean evidence.

Record the useful example fields:

- `event_time`
- player name and/or unique id
- action or event code
- map
- table name

## 2. Locate Candidate Log Files

Use `locate_residual_logs.py` to rank source logs:

```powershell
python scripts\replay_baseline\locate_residual_logs.py `
  --artifacts-dir scripts\replay_baseline\artifacts `
  --event-time "2024-01-06 00:18:10" `
  --player "Rakza" `
  --unique-id "1:55955613" `
  --map "de_spay" `
  --action "Defused_The_Bomb"
```

The command searches GoldSrc timestamps, Steam id variants, names, maps, action
phrases, and message fragments. Pick the highest-scoring candidate, then inspect
nearby lines with `rg -n` if needed.

## 3. Run Single-Log Parity

Run the file through both stacks and capture the artifacts:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0105062.log `
  -Name rakza-kill-streak `
  -TraceTable hlstats_Events_PlayerActions `
  -TraceParamContains "2024-01-06 00:18:10"
```

Outputs are written under:

```text
scripts/replay_baseline/artifacts/parity-traces/<name>/
```

Important files:

- `compare-stats.txt` - logical DB residuals for this one file/window.
- `write-trace-diff.txt` - normalized DB write differences.
- `legacy-general.log` - legacy MariaDB general-log capture.
- `python-writes.jsonl` - Python pre-batch storage write trace.
- `summary.json` - paths and exit codes.

`Run-SingleLogParity.ps1` restores clean baselines, enables legacy
`general_log`, imports the log into legacy, restores Python, imports with
`HLSTATS_DB_WRITE_TRACE_PATH`, then runs both compare tools.

Use `-TraceTable` and `-TraceParamContains` to keep `write-trace-diff.txt`
focused on the residual from `compare-stats.txt`. The logical DB compare is the
primary pass/fail signal; write trace is the narrower diagnostic view.

After the main single-log pass, the script automatically runs a second guard
pass on a smaller `30` lines before / `30` lines after window when it can find a
safe anchor. Anchors come from `-LineNumber`, `-EventTime`, `-Pattern`, or the
first `YYYY-MM-DD HH:MM:SS` timestamp inside `-TraceParamContains`. The guard
run writes to a sibling directory named `<name>-guard-30x30/` and uses
`-SkipGuardWindow` internally to avoid recursion.

## 4. Cut A Smaller Window When Safe

If the single log is large, extract a smaller window:

```powershell
python scripts\replay_baseline\extract_log_window.py `
  --log-file scripts\replay_baseline\artifacts\L0105062.log `
  --event-time "2024-01-06 00:18:10" `
  --before 300 `
  --after 120 `
  --output scripts\replay_baseline\artifacts\windows\rakza-001.log
```

Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\windows\rakza-001.log `
  -Name rakza-001-window `
  -TraceTable hlstats_Events_PlayerActions `
  -TraceParamContains "2024-01-06 00:18:10"
```

Do not cut too aggressively for lifecycle bugs. Connect, team selection, map
transition, and previous kills may be hundreds of lines before the visible
residual.

## 5. Fix Loop

Use this order for each bug:

1. Reproduce with `Run-SingleLogParity.ps1`.
2. Confirm the legacy Perl rule with subagent-assisted read-only analysis.
3. Add a focused unit/regression test.
4. Change Python behavior.
5. Re-run the same single-log/window parity and inspect the automatic `30/30`
   guard pass as a sanity check against overfitted fixes.
6. Re-run a small cluster of related files when available.
7. Only then run `narrow-1000`.

The broad contour answers "what still differs?" The single-log/window contour
answers "which write and input sequence caused this?" Unit tests prevent the
specific behavior from regressing again.
