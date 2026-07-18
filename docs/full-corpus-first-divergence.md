# Full-Corpus First Divergence Runbook

Use this runbook when a completed legacy replay and a completed Python fast-path
replay processed the same sorted corpus, but final SQL anchors differ. The goal
is not another full replay; the goal is to find the first replay window where
legacy and Python make different runtime decisions.

## Investigation Contour

- Server identity: `37.230.137.48:27015`.
- Corpus: same sorted `*.log` list used by both completed runs.
- Replay policy: keep `--drop-empty-team-enter-events` aligned on both sides.
- Python path: fast-path stdin/import, not UDP.
- Baseline rule: do not rerun legacy full replay unless baseline dump, corpus,
  server identity, or replay policy changes.

For the current full-corpus investigation, use an explicit artifact label such
as `full-41513` so window artifacts do not overwrite the retained
`narrow-1000` evidence.

## Evidence identity and inventory

Every replay artifact has two identities:

- `ArtifactLabel`: the contour class, exactly `narrow-1000`, `full-41513`, or
  `prefix-*`;
- `EvidenceRunId`: a unique run suffix recorded in contour metadata and every
  published manifest/snapshot filename.

The label is not a substitute for a run id. A new run must fail on an existing
artifact unless `-OverwriteEvidence` (or the equivalent explicit manifest
overwrite option) is supplied. The final sorted, selected input list is the
only input manifest accepted as replay evidence; the ignored-lines manifest
must come from the same Python import and the same run.

The retained inventory is recorded in
`docs/audits/legacy-python-parity-20260423/evidence-inventory-20260717.md`.
In particular, files named `legacy-input-manifest-1000.txt` and related
`*-1000` captures are not assumed to be narrow evidence: if their count and
SHA identify the 41,513-log contour, they are classified as `full-41513` and
must not be paired with the valid narrow-1000 manifests.

## Preserve Current Evidence

Capture current anchors and snapshots from the already-loaded contours:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Snapshot-ContourSql.ps1 `
  -Stack legacy `
  -OutputPath docs\audits\legacy-python-parity-20260423\legacy-sql-snapshot-full-41513.txt

powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Snapshot-ContourSql.ps1 `
  -Stack python `
  -OutputPath docs\audits\legacy-python-parity-20260423\python-sql-snapshot-full-41513.txt

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20 --json `
  > docs\audits\legacy-python-parity-20260423\runtime-db-diff-full-41513.json
```

If contour metadata already exists under
`scripts/replay_baseline/comparison/.parity-state/contour-info/`, copy the
matching legacy and Python JSON files into the audit folder. If it does not,
record that metadata is absent rather than rerunning replay just to create it.

## Comparable Input And Drop Artifacts

The retained full-corpus artifacts should include:

- `legacy-input-manifest-full-41513.txt`
- `python-input-manifest-full-41513.txt`
- `legacy-dropped-lines-full-41513.txt`
- `python-ignored-lines-full-41513.txt`

For a fresh runner execution, the concrete filenames also contain the unique
`EvidenceRunId`. Compare the two input manifests byte-for-byte before using
SQL snapshots as parity evidence; compare both ignored/drop manifests and
contour metadata in the same way. Never delete an older artifact to make a
label appear consistent.

When replay is not being rerun, regenerate only the sorted input manifests from
the same corpus directory and compare them byte-for-byte. Do not treat a
regenerated drop/ignore manifest as runtime evidence unless it came from the
same replay path and policy.

Normalize reasons into this taxonomy in the window report:

- `input-filter`
- `parser-drop`
- `policy-ignore`
- `identity-mismatch`
- `flush-boundary`
- `post-processing-only`

## Prefix/Window Search

Use prefix windows on the same sorted list before moving to line-level tracing.
The existing dual-contour runner now supports an explicit artifact label:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 500 `
  -ArtifactLabel prefix-000500 `
  -EvidenceRunId 20260717-prefix-000500-a `
  -UseDumpRestore

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20 --json `
  > docs\audits\legacy-python-parity-20260423\runtime-db-diff-prefix-000500.json
```

Repeat with coarse prefixes (`1000`, `2000`, `5000`, etc.) until the first
prefix that differs is found. Then binary-search between the last clean prefix
and the first dirty prefix. Keep each run's `ArtifactLabel` unique, for example
`prefix-002500`, so manifests, dropped-line files, snapshots, and contour
metadata remain reviewable.

At each step, use the same anchor tables:

- `hlstats_Events_Frags`
- `hlstats_Players`
- `hlstats_Events_TeamBonuses`
- `hlstats_Events_Entries`

Stop the prefix search when the smallest file prefix that introduces the first
anchor divergence is known. Then use `compare_stats_dbs.py` examples and
`locate_residual_logs.py` to select a candidate log.

## Single-Log And Guard Window

Once a candidate log/time/line is identified, switch to the single-log trace
harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile scripts\replay_baseline\artifacts\L0100000.log `
  -Name full-first-divergence-candidate `
  -LineNumber 1234 `
  -TraceTable hlstats_Events_Frags `
  -TraceTable hlstats_Players `
  -TraceTable hlstats_Events_TeamBonuses `
  -TraceTable hlstats_Events_Entries
```

`Run-SingleLogParity.ps1` automatically runs the `30` lines before / `30` lines
after guard pass when it has a line, time, pattern, or trace timestamp anchor.
Treat a guard failure as evidence that the fix candidate is too narrow.

## Classification

Classify the first divergence before proposing a Python behavior change:

- The line did not reach one runtime.
- The line parsed differently.
- The event was ignored by policy.
- The event attached to a different player/session key.
- The event reached both runtimes but flushed to SQL differently.
- The difference appears only in a post-replay stage.

Only after this classification should the work move to a fix candidate,
regression test, and promotion run.

## Output Report

Write the first-window result into:

```text
docs/audits/legacy-python-parity-20260423/first-divergence-window-report.md
```

The report must include:

- contour metadata or an explicit note that metadata was absent;
- sorted input manifest paths and SHA-256 values;
- drop/ignore manifest paths and reason taxonomy;
- smallest clean prefix and first dirty prefix;
- minimal log and line range;
- `30/30` guard-window result;
- stable-key SQL diff for `Frags`, `Players`, `TeamBonuses`, and `Entries`;
- classification: `must-fix`, `accepted`, or `diagnostic backlog`.

Keep GeoIP, flags, and heatmaps out of the raw runtime report. Compare those in
a separate post-processing report after raw runtime divergence is explained.

For the full contour, the first promotion gate is the pair of identical final
input manifests and matching contour metadata; a full-corpus SQL comparison
without that evidence is diagnostic only. Heatmap calibration or projection
migration is a separate gate and must not be inferred from runtime parity.
