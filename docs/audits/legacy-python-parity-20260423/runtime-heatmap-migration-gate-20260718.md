# Heatmap projection migration gate — 2026-07-18

This report records the read-only check, restorable backups, explicitly
approved versioned migration, and post-migration one-map acceptance for the
shared heatmap projection contract.

## Read-only distribution

Command:

```powershell
python scripts/heatmap_projection_migrate.py `
  --configfile scripts/replay_baseline/comparison/python/hlstats.host.conf
```

Result:

```text
stored rotate distribution: {0: 442}
dry-run only; after the runtime gate pass --apply --runtime-gate-approved to migrate legacy 0/1 rows
```

The selected host configuration targets the running Python database at
`127.0.0.1:3327`. The repository-default `scripts/hlstats.conf` is an empty
template and therefore is not a runtime connection configuration.

No stored `rotate=2` or `rotate=3` values were found, so the manual-stop rule
was not triggered. The projection version marker is still legacy/absent; the
updater printed its guarded SQL but did not execute it.

## Pre-migration backup

The current Python database was dumped before any projection mutation:

```text
runtime-python-db-backup-before-heatmap-migration-20260718-064706.sql.gz
bytes: 354018207
sha256: BEC10451F6913DD695DEF1CEFB4EF8138B08B1D353AF2AEC02A58524E7B170F4
gzip test: passed
```

The dump was produced from `hlstatsx-python-db` with
`--single-transaction --routines --triggers --events`. It is retained beside
this report as an audit artifact and must not be overwritten implicitly.

Before the approved runtime mutation, both completed full-41513 contours were
also preserved as independently validated dumps. Their live anchors, sizes,
SHA-256 values, and restore boundary are recorded in
`runtime-full-41513-preserved-state-20260718.md`. This retains the expensive
full replay for later diagnosis and profiling without rerunning it.

## Source-only hardening after the read-only check

The guarded updater now disables autocommit for the row conversion and version
marker, commits both statements together, rolls back on any failure, and then
restores autocommit. Both DB-mutating entrypoints—the versioned updater and
`heatmap_projection_calibrate.py`—reject `--apply` unless
`--runtime-gate-approved` is present. At this source-gate stage no migration
had been run. The Python and PHP render paths also normalize non-positive or
non-finite projection scales to `1.0`, while the calibration CLI rejects
invalid scale overrides before an apply can be attempted.

The dual-contour runner also checks legacy manifest/drop/log/window paths and
SQL snapshot destinations before writing them; a repeated evidence id is
refused unless `-OverwriteEvidence` is supplied explicitly.

## Approved runtime migration

The user supplied the separate runtime gate on 2026-07-18. Immediately before
apply, the updater again reported `{0: 442}`, no stored `2/3`, and an absent
legacy version marker. The guarded command completed successfully:

```text
stored rotate distribution: {0: 442}
migrated heatmap projection version 1 -> 2
```

The post-apply read-only check reports version `2` and the same `{0: 442}`
distribution. Because there were no rotate=1 rows, the row-conversion UPDATE
changed no calibration rows; only the version marker was added. Python runtime
anchors remained `6092` players, `537210` frags, `461135` team bonuses, `313`
entries, `2` servers, and `114` map-count rows.

This approval covered the versioned migration. It does not authorize arbitrary
calibration proposals: future `heatmap_projection_calibrate.py --apply` runs
still require their own reviewed proposal and explicit runtime-gate flag.

## Pre-migration UI diagnostics

The published Python web was checked read-only on `127.0.0.1:8281`. The
`de_dust2` map-details page exposed the static map image, static heatmap
thumbnail, and the heatmap canvas/toggle. The admin heatmap route remained
authorization-protected; no credentials were entered and no form was
submitted.

The point endpoint was queried without changing the database:

```text
GET /heatmap_points.php?game=cstrike&map=de_dust2&days=3650
status: 200
points: 1853
max: 6
queried: 10034
inBounds: 1896
inBounds ratio: 0.188957544349213
manualRequired: true
image: heatmap_map.php?game=cstrike&map=de_dust2&v=1780491018
projection: xoffset=384 yoffset=1120 flipx=0 flipy=1 rotate=0 scale=1.26
raw range: minX=-2159 maxX=1775 minY=-1007 maxY=3087
transformed range: minX=-1408 maxX=1713 minY=-1561 maxY=1688
```

This pre-migration diagnostic remains the calibration-quality baseline. The
broad out-of-bounds range and `manualRequired=true` mean that visual projection
calibration is still intentionally manual; the version migration does not
claim to correct those map-specific values.

## Post-migration one-map regeneration

A literal `--disablecache` run at the current clock correctly found zero points
because `de_dust2.days=30` and the preserved replay data is older. A guarded,
temporary attempt to use the schema maximum `days=127` also found no points and
restored the value to `30` in `finally`; the last positioned `de_dust2` event is
2026-02-13.

The same generator was then run for only `cstrike/de_dust2` with
`--disablecache`, preserving the real output/cache clock while fixing only the
query-window clock to 2026-03-14 so the replay-era rows were eligible. It
generated the JPEG from `102` points (`22` in bounds, `80` out of bounds,
ratio `0.216`) and wrote:

```text
web/hlstatsimg/games/cstrike/heatmaps/de_dust2-kill.jpg
bytes: 229318
sha256: 504A2CBE64701CB140BFD761B6A38390E67A72D21983F656E6EAB95E3EDA33DD
web/hlstatsimg/games/cstrike/heatmaps/de_dust2-kill-thumb.jpg
bytes: 17042
```

The Python web service was rebuilt afterward so the manual browser check uses
the current PHP helper, JavaScript, and regenerated static JPEG rather than a
stale image layer.

## Post-migration manual browser acceptance

The authorization-protected admin wizard was exercised with a guarded local
authentication fixture; the original admin credential hash was restored
immediately after the session was established. No browser `Save`, upload, or
regeneration action was submitted, so this check did not change projection
rows or image files.

The first browser pass exposed a real UI defect: initial load, map selection,
and the explicit `Load` action sent the form defaults and overwrote the stored
configuration in the read-only response. The JavaScript request contract was
fixed so stored-config requests send only action/game/map, while preview,
edit, save, scheduled generation, and regeneration continue to send current
controls. The Node regression smoke pins this distinction.

After the fix, selecting `de_dust2` loaded the stored projection unchanged:
`xoffset=384`, `yoffset=1120`, `scale=1.26`, `flipx=0`, `flipy=1`, `rotate=0`,
and zero crop. A DOM-only `days=3650` preview (not persisted to the DB) rendered
the replay-era points and reported `1896/10034 in bounds`, ratio
`0.18895754434921266`, and `manualRequired=true`. The canvas heatmap layer was
visibly toggled off and back on, and the browser console reported zero errors
or warnings.

The separately served static fallback was opened successfully at
`/hlstatsimg/games/cstrike/heatmaps/de_dust2-kill.jpg`; the browser decoded it
as a `1024x768` JPEG. Browser screenshots and the regenerated JPEG/thumb are
retained locally and intentionally excluded from Git publication; their
observable dimensions, hashes, and acceptance results are recorded in this
report.

## Final validation

The source and runtime-accepted result were validated after the final web
rebuild:

```text
relevant Python/FTP/replay/heatmap tests: 306 passed, 2 known pytest warnings
Docker PHP/GD smoke: web heatmap smoke ok
Node projection smoke and JS syntax check: passed
Python source compilation: exit 0
git diff --check: exit 0
```

The rebuilt container and host copies match for `heatmap.js`, the generated
JPEG, and its thumbnail. Final DB checks report projection version `2`, rotate
distribution `{0:442}`, unchanged replay anchors, `de_dust2.days=30`, and the
original admin credential hash. The two pytest warnings are the existing
`pytest-asyncio` default-scope warning and a non-fatal cache-permission warning;
no test failed.
