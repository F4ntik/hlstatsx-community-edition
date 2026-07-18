# Preserved full-41513 runtime state — 2026-07-18

This checkpoint preserves both completed full-41513 contour databases before
the approved heatmap projection migration. It is intended for later diagnosis,
profiling, and DB-data corrections without repeating the roughly 4h20m legacy
full replay.

## Evidence identity

- Artifact label: `full-41513`
- Evidence run: `20260717-full-41513-r1`
- Input files: `41513`
- Input manifest SHA-256 (both contours):
  `B6AE0846743E3780CFBA2DE75D5F43A455CB99160FB786A0AA418AE4AF037929`
- Source comparison: `runtime-db-diff-full-41513-20260717-full-41513-r1.md`

## Live anchors before dump

| Anchor | Legacy | Python |
|---|---:|---:|
| players | 6039 | 6092 |
| frags | 536996 | 537210 |
| team bonuses | 462840 | 461135 |
| entries | 0 | 313 |
| servers | 2 | 2 |
| map-count rows | 114 | 114 |

The Python heatmap configuration had rotate distribution `{0: 442}` and no
`heatmap_projection_version` option before the dump.

## Restorable database dumps

Both dumps were created with `mysqldump --single-transaction --routines
--triggers --events` and `gzip -1`. Each gzip stream was read through to EOF
after copying it out of its DB container.

| Contour | Artifact | Compressed bytes | Uncompressed bytes | SHA-256 | Gzip |
|---|---|---:|---:|---|---|
| Legacy | `runtime-full-41513-legacy-db-before-heatmap-migration-20260718-142431.sql.gz` | 88908858 | 555060714 | `1E24476AC5C51CFDFB300F7C80DC024F9F49959239DF7761A47E48E9752B35AB` | passed |
| Python | `runtime-full-41513-python-db-before-heatmap-migration-20260718-142431.sql.gz` | 354018205 | 3019135919 | `E8D0BA9E93147EAA15F2993C77D67773565A8DE2AADB4BC183515A2438104252` | passed |

The older Python-only pre-migration backup remains retained separately as
`runtime-python-db-backup-before-heatmap-migration-20260718-064706.sql.gz`.
None of these artifacts may be overwritten implicitly.

Restore only into a disposable or explicitly selected database. Do not restore
over either running comparison contour merely to inspect data; use a separate
container/volume and verify the artifact SHA-256 first.
