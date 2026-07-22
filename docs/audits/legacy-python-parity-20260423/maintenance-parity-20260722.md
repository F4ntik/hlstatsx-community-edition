# Release-clean maintenance parity — 2026-07-22

## Scope

This record closes the P1 hardening work that makes the dual replay contour
prove post-ingest, web-visible maintenance rather than raw event ingestion
alone. It covers the legacy-compatible award order, historical inactivity
clock, strict GeoIP, runner failure evidence, selected-log FTP staging, and
the correct language boundary for the two web applications.

It does not promote a raw replay or a DB fragment counter into acceptance.
The accepted verdict comes from the canonical runner completing maintenance,
snapshots, logical comparison, and route smoke in one fresh contour.

## Accepted gates

| Gate | Evidence run | Result |
| --- | --- | --- |
| 100-file bounded gate | `prefix-100` / `20260722-maintenance-prefix-100-r8` | Passed after focused regressions; both contours completed `100/100` input files with zero replay errors. |
| Full release gate | `narrow-1000` / `20260722-maintenance-narrow-1000-r1` | Passed: both contours completed the shared 1,000-file manifest and the complete logical compare found no differences. |

The 1,000-file manifests have the same SHA-256:

```text
95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a
```

The final SQL snapshots agree on the replay anchors:

```text
players=323
frags=5464
frags_empty_map=0
maps_counts_rows=31
maintenance_use_timestamp=1
frags_minmax=2024-01-01 19:02:46|2026-01-05 22:25:24
```

The post-maintenance counts match in legacy and Python:

| Measure | Value in both contours |
| --- | ---: |
| award definitions | 998 |
| player awards | 9 |
| player ribbons | 8 |
| GeoIP flag / country | 250 / 250 |
| GeoIP city / state | 219 / 221 |
| GeoIP coordinates | 250 |

The final comparison output is explicit: `No logical replay differences found
in the configured statistical tables.`

## Web contract and visual comparison

The original legacy web has no Russian i18n runtime. It is therefore an
English reference, not an EN/RU product target. The canonical smoke uses a
runtime-resolved populated combat player rather than a hard-coded fixture ID:

| Contour | Languages | Signature player IDs |
| --- | --- | --- |
| Legacy reference | `en` | `69` |
| Python product | `en`, `ru` | `69`, `78` (distinct) |

Both smoke runs passed, including the populated daily/global/ribbons routes,
`status.php`, and the PNG `sig.php` route. The maintenance summary provides
the exact legacy EN and Python EN/RU URLs for an operator's side-by-side visual
inspection.

`sig.php` now keys a cache lookup by the complete query plus the active
language, serves cache hits as PNG bytes, and uses integer duration arithmetic
compatible with PHP 8.2. A source-mounted PHP 8.2 container smoke confirmed a
pure PNG response, a valid cache hit, and no EN-to-RU cache alias. The Windows
host has no PHP CLI, so this is container evidence, not a local-host PHP claim.

## Fixes proven by the gate

| Finding | Correction |
| --- | --- |
| Historical inactive processing treated epoch `last_event` values as SQL timestamps. | Use numeric epoch subtraction for `UseTimestamp=1`, matching the legacy representation. |
| Object and weapon `headshot` awards were conflated. | Keep `O/headshot` as the literal action code and map only `W/headshot` to the frag flag `1`. |
| Full corpus FTP bind-mount startup looked stalled while the image scanned/chowned every source log. | Stage only the selected logs under `.parity-state/ftp-logs/<EvidenceRunId>`; validate names/count before compose and prove selection from the final manifests. |
| A stale fixed signature player could make web smoke non-representative. | Resolve shared populated combat IDs from both DBs, require explicit values, and require distinct Python IDs. |
| The runner could abort on PowerShell native-error semantics before persisting failed smoke/compare output. | Capture stdout/stderr and native exit code before fail-close for both logical compare and web smoke. |
| A Russian marker was incorrectly expected from the English-only legacy web. | Keep legacy EN as the data/reference smoke and apply EN/RU localization markers only to the Python product. |

Focused calculator/replay-helper validation after the final source state:

```powershell
$env:PYTHONPATH = 'scripts;scripts/replay_baseline'
python -m pytest -q scripts/hlstats_awards_py/tests scripts/replay_baseline/tests
```

Result: `103 passed` (the only output was the existing pytest-asyncio
configuration deprecation warning).

## Rejected intermediate runs

The following runs are retained as diagnosis, not acceptance:

| Run(s) | Rejected reason |
| --- | --- |
| `prefix-100` r1–r2 | Legacy maintenance command did not receive its explicit contour DB settings; then PowerShell treated Docker progress stderr as a terminating native error. |
| `prefix-100` r3 | Historical activity did not use the legacy epoch arithmetic. |
| `prefix-100` r4 | The `O/headshot` award matched the wrong representation. |
| `prefix-100` r5 | The full FTP source mount delayed health because the image traversed a large corpus. |
| `prefix-100` r6 | Smoke still used a stale signature player ID. |
| `prefix-100` r7 | The legacy EN-only web was incorrectly required to satisfy a Russian marker; the run also exposed the missing native-output capture. |

The accepted r8 is the first clean 100-file run after all of those corrections;
the final `narrow-1000` is the full closure gate.

## Monitoring rule

One delegated monitor sampled only
`SELECT COUNT(*) FROM hlstats_Events_Frags` in both disposable DBs, never more
often than once per 60 seconds. It did not poll an unchanged terminal line or
infer success from CPU usage. During the final window it observed both contours
at `5464` frags at `2026-07-22 21:25:04` MSK; that is progress telemetry only.
The runner's successful completion plus the saved comparison/smoke evidence is
the acceptance proof.

## Evidence inventory

The final compact artifacts are stored beside this report:

```text
maintenance-summary-prefix-100-20260722-maintenance-prefix-100-r8.txt
logical-compare-prefix-100-20260722-maintenance-prefix-100-r8.txt
legacy-sql-snapshot-prefix-100-20260722-maintenance-prefix-100-r8.txt
python-sql-snapshot-prefix-100-20260722-maintenance-prefix-100-r8.txt

maintenance-summary-narrow-1000-20260722-maintenance-narrow-1000-r1.txt
logical-compare-narrow-1000-20260722-maintenance-narrow-1000-r1.txt
legacy-sql-snapshot-narrow-1000-20260722-maintenance-narrow-1000-r1.txt
python-sql-snapshot-narrow-1000-20260722-maintenance-narrow-1000-r1.txt
```

The runner also emits the final selected manifests, ignored/drop manifests,
maintenance/replay/smoke logs, and state files. Their lifecycle is governed by
the audit `.gitignore` rules; the committed report and compact snapshots carry
the reproducibility identifiers without needlessly versioning every local
transcript.

Intermediate rejected compares can include raw player identity, address, and
location examples. They remain local diagnostic material and are intentionally
not committed; the rejected-runs table records their cause without publishing
those values. The accepted final compare contains no such examples because it
has no differences.

## Acceptance statement

The release-clean maintenance contour is accepted for the supported
`narrow-1000` fixture. Future replay/storage changes must preserve this
contract: targeted regressions, the 100-file bounded gate, then a fresh full
`narrow-1000` gate before a related milestone is closed.
