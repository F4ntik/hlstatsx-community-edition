# Runtime DB diff — full-41513 / 2026-07-18

## Evidence identity

- Artifact label: `full-41513`
- Evidence run: `20260717-full-41513-r1`
- Command: `Run-DualContour-1000.ps1 -MaxImportFiles 41513 -ArtifactLabel full-41513 -EvidenceRunId 20260717-full-41513-r1 -SkipBuild -UseDumpRestore`
- Runner exit: `0`
- Final runner state: `scripts/replay_baseline/comparison/.parity-state/20260717-181856.json`
- Logical server: `37.230.137.48:27015`, game `cstrike`
- Baseline mode: dump restore on both contours
- Selected input: `41513` logs, first `L0101000.log`, last `L1231219.log`

## Manifest and parser evidence

| Artifact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| Legacy input manifest | 41513 | 539669 | `B6AE0846763E3780CFBA2DE75D5F43A455CB99160FB786A0AA418AE4AF037929` |
| Python input manifest | 41513 | 539669 | `B6AE0846763E3780CFBA2DE75D5F43A455CB99160FB786A0AA418AE4AF037929` |
| Legacy dropped-lines manifest | 169140 | 6905040 | `EDADCA1A4BCA6EE6B90F850E99E54AA53D1864F0E9F77B30CF908AFC8B861DBC` |
| Python ignored-lines manifest | 7 | 301 | `9636F25DC521697ECACB24A9DC484FC5DDB99B4E65D70AFFFED5934EA0999CAB` |

The input manifests are byte-identical. Python continued only with its
same-run ignored-lines manifest and recorded these seven explicit parser
reasons:

```text
L0120085.log:222:empty-timestamp-only-line
L0721022.log:222:empty-timestamp-only-line
L1021207.log:225:empty-timestamp-only-line
L1030239.log:804:empty-timestamp-only-line
L1127178.log:222:empty-timestamp-only-line
L1129033.log:159:empty-timestamp-only-line
L1203059.log:367:empty-timestamp-only-line
```

The legacy 169140 dropped lines use a different legacy drop taxonomy
(`empty-team-enter-event` in the retained sample), so the two drop/ignore
counts are not expected to be numerically equal. Neither manifest was created
after the fact or omitted from the run.

## Contour metadata anchors

Both metadata files have `artifact_label=full-41513`,
`contour=full-41513`, `evidence_run_id=20260717-full-41513-r1`, and
`baseline_mode=dump`.

| Anchor | Legacy | Python |
|---|---:|---:|
| players | 6039 | 6092 |
| frags | 536996 | 537210 |
| team bonuses | 462840 | 461135 |
| entries | 0 | 313 |
| server rows | 1 | 1 |

## SQL snapshots

The raw snapshots are each 992 bytes / 58 lines. Their raw SHA-256 values
differ because the stack/timestamp headers differ:

- legacy: `9F4D7FDE1B8BC53D1E846433943D28F4E3E9B63D8DC290FF93F7697EC15D26A3`
- Python: `75141ECAB12E53DBA278A6F0A979DE13D4632F16826AAE2516C0007586660514`

After removing the first three header lines, the normalized sections still do
not match:

- legacy normalized SHA-256: `9670AC8335CEFFE613641C03E87D971048FC7BA7A32F40E9DFB9DECA336F7DD7`
- Python normalized SHA-256: `FAF3D837BA6AE0FDB28BC7C79CEA16759BBFE3021540C7E5AD067E40B26B588A`

The snapshot aggregate difference is players `6039/6092`, frags
`536996/537210`, while both contours have `114` map-count rows and the same
frags time range (`2023-06-28 23:43:35` through `2026-04-21 21:32:37`).

## Full stable-key compare

Command: `PYTHONIOENCODING=utf-8 python scripts/replay_baseline/compare_stats_dbs.py --max-examples 0 --json`

Exit code is `1`, meaning residual differences were found. The compact result
was:

| Table | Legacy rows | Python rows | Legacy-only | Python-only |
|---|---:|---:|---:|---:|
| `hlstats_Servers` | 2 | 2 | 1 | 1 |
| `hlstats_Actions` | 754 | 758 | 10 | 14 |
| `hlstats_Weapons` | 993 | 993 | 12 | 12 |
| `hlstats_Maps_Counts` | 114 | 114 | 15 | 15 |
| `hlstats_Players` | 6039 | 6092 | 5790 | 5843 |
| `hlstats_PlayerUniqueIds` | 6039 | 6075 | 28 | 64 |
| `hlstats_PlayerNames` | 10783 | 10843 | 188 | 248 |
| `hlstats_Players_History` | 36969 | 36827 | 10900 | 10758 |
| `hlstats_Events_ChangeTeam` | 119457 | 119814 | 633 | 990 |
| `hlstats_Events_Chat` | 58575 | 61071 | 1132 | 3628 |
| `hlstats_Events_Connects` | 67569 | 67573 | 320 | 324 |
| `hlstats_Events_Entries` | 0 | 313 | 0 | 313 |
| `hlstats_Events_Frags` | 536996 | 537210 | 3806 | 4020 |
| `hlstats_Events_Teamkills` | 1020 | 1001 | 19 | 0 |
| `hlstats_Events_PlayerActions` | 461782 | 462149 | 1384 | 1751 |
| `hlstats_Events_Statsme` | 2784121 | 2785228 | 5723 | 6830 |
| `hlstats_Events_Statsme2` | 2784114 | 2785223 | 5721 | 6830 |
| `hlstats_Events_TeamBonuses` | 462840 | 461135 | 2143 | 438 |

The full contour is therefore not parity-green. The differences are broad
runtime/replay residuals, not a heatmap or manifest-integrity failure. In
particular, `Entries`, `Chat`, player identity/history, statsme, and
TeamBonuses require a separate first-divergence investigation if full-corpus
parity becomes a promotion requirement.

## Acceptance classification

- **Manifest/input gate:** passed; both stacks processed the same byte-identical
  sorted 41513-log selection.
- **Fail-closed parser gate:** passed; Python's seven continued parse cases are
  explicitly recorded in the same-run ignored manifest.
- **Full-corpus parity gate:** not passed; the residual table above is retained
  as diagnostic evidence, not silently accepted as narrow parity.
- **Narrow-1000 gate:** unchanged and remains the supported accepted contour;
  see `runtime-db-diff-narrow-1000-20260717-narrow-1000-r1.md`.
- **Heatmap migration/UI gate:** not executed here. No calibration migration,
  backup-gated mutation, or `--disablecache` manual wizard/canvas/static-JPEG
  acceptance was performed.

The next full-corpus action, if required, is prefix/binary-search localization
using `docs/full-corpus-first-divergence.md`; do not overwrite or reinterpret
the accepted narrow-1000 evidence.
