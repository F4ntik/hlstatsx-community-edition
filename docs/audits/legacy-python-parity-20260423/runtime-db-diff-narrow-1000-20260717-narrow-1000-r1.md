# Runtime DB diff — narrow-1000 / 2026-07-17

## Evidence identity

- Label: `narrow-1000`
- Evidence run: `20260717-narrow-1000-r1`
- Mode: fresh `-UseDumpRestore` dual contour
- Input manifest SHA: `95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a` on both stacks
- Selected-log SHA in metadata: `ccc06efc73505e1f1cf0703500f4dacdb05ee1ced634e93ee3cb410cad435566` on both stacks

## Stable evidence

Both contours completed the 1,000-log run successfully. The SQL snapshot
sections match after removing only the stack/container/timestamp header. The
shared anchors are:

```text
players=323
frags=5464
team_bonuses=4765
entries=0
server_rows=1
maps_counts_rows=31
```

The input manifests are byte-identical. The legacy dropped-line manifest and
the Python ignored-line manifest are both published beside the snapshots;
their different counts are expected because the two replay paths expose
different drop/parse classifications.

## Compare result

Command:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python scripts/replay_baseline/compare_stats_dbs.py --max-examples 1000 --json
```

The command exits `1` because the raw comparison keeps the known
`hlstats_Players` GeoIP residual visible. It reports `323/323` player rows,
with `250` legacy-only and `250` Python-only normalized rows. All 250 pairs
have the same logical player identity and every field matches after removing
only `country` and `flag`; the field classifier reports `0` non-GeoIP pairs.
No new aggregate, identity, event, or snapshot drift was observed.

This is the accepted raw-replay GeoIP-only difference documented in
`docs/status.md` and `docs/parity-acceptance-policy.md`; release-clean output
still requires the separate GeoIP maintenance/backfill step.

## Calibration gate

Read-only inspection reported `hlstats_Heatmap_Config.rotate`: `{0: 442}`.
No `2` or `3` values were present. The version marker was not written and the
versioned updater was not applied; calibration migration remains a separate
runtime gate requiring backup and explicit approval.
