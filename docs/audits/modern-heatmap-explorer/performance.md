# Modern Heatmap Explorer — Task 11 performance and migration evidence

## Verdict and evidence boundary

Task 11 retains exactly one index: <code>mapEventTime (map, eventTime)</code> on
<code>hlstats_Events_Teamkills</code>. The retain decision has both an isolated
disposable A/B performance receipt and a fresh staged <code>narrow-1000</code>
dual-contour receipt in which the normal updater installed the index before the
Python import.

This is **not** a strict-logical-comparator green result. Both the original Task
11 contour and the fresh indexed contour stop with the approved
coordinate-only, visible-product residual. The red comparator receipts remain
preserved and the comparator was not changed to hide them. No synthetic events,
raw schema injection into the contour, server-specific index, Suicides index,
second index, or second table was used.

The source change is uncommitted pending independent review. This report is
source/disposable-runtime evidence, not a production deployment record.

## Immutable identities

| Item | Identity |
| --- | --- |
| Source commit at evidence start | <code>a95dcf4459c2eca76d7f37ee9ac484550aa4ccc9</code> |
| Branch | <code>feature/modern-heatmap-explorer</code> |
| Historical populated Python dump SHA-256 | <code>b6a08bb517e04fd85f24a50372df41c0ec636245e67a6c176ffdf191a6a28efa</code> |
| Historical full logical fingerprint | <code>fdce1cc5bbdca9f81f711daed3fc1ea89399bb5fcc77121ef8d071fc6a730a10</code> |
| Historical dump version | <code>dbversion=89</code> |
| External source-log corpus | <code>docs/audits/legacy-python-parity-20260423/legacy-window-1000</code>: 41,513 <code>.log</code> files, 4,228,616,739 bytes |
| Selected canonical input | 1,000 sorted logs, <code>L0101000.log</code> through <code>L0106125.log</code> |
| Selected-input manifest SHA-256 | <code>95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a</code> |
| GeoLite2-City MMDB | <code>scripts/GeoLiteCity/GeoLite2-City.mmdb</code>, 67,714,772 bytes, SHA-256 <code>3784bdbf7bbd06b7f84e6727e481b9afa0d729111c5646fa37fac9bf3a2d22eb</code> |
| Checkout web assets used by staged bridge | <code>web/hlstats.php</code>: <code>337c635dacd92f75ab1c8e6c3141d50b7bd10d0ac542d906e95ae9db87118639</code>; <code>web/includes/heatmap_points.php</code>: <code>70395f473ffaa0f1b9c7a729c861e688bfc96310320c05e5d7c6131f52b8b375</code> |
| Updater source hashes | <code>80.php</code>: <code>6ee9c6c0b70c19423f75223882fabb66a1eb09a0e9bd382f690ee5ec1c168b7f</code>; <code>81.php</code>: <code>a515a04cf8dd51c3fc6f14da94cfd6c9a32b51829bbc6c5fb0fb56208de0aa97</code>; retained <code>82.php</code>: <code>95a21de402683466aefe27a4c9f7badb2a12cd9ef38196b7e33cc82c17ed9911</code> |

The historical archive's version 89 is not a source-migration claim. It is the
version embedded in a populated historical baseline. A fresh source
install/updater chain ended at 81 before this task. Task 11 deliberately
restored that archive, changed only its disposable <code>dbversion</code> to
80, then used the normal HTTP updater so 81 and 82 ran in order.

## Strict comparison disposition

The original narrow contour is retained at
<code>docs/audits/legacy-python-parity-20260423/logical-compare-narrow-1000-cac7cec3-39c7-4f2f-8865-1355cb40bb03.txt</code>.
It is red by the strict comparator. Review classified the residual as
coordinate-bearing fields only: Python retains attacker/killer positions for the
visible heatmap product where legacy omits or has NULL positions. This is the
Task 1-approved residual, not a general data/parity waiver.

The fresh indexed comparison has the same disposition at
<code>docs/audits/legacy-python-parity-20260423/logical-compare-narrow-1000-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.txt</code>:

- <code>hlstats_Events_Frags</code> has 5,464 rows on each side and 2,170
  normalized coordinate-only differences per side.
- <code>hlstats_Events_Teamkills</code> has 42 rows on each side and 15
  normalized coordinate-only differences per side.
- No non-coordinate table or field difference is accepted here.

The comparator therefore exits nonzero by design. It must never be reported as
strict-green.

## Historical updater acceptance: 79 and 80

<code>task-11-evidence/updater-http-31821ddc-25a0-4a75-b97c-ed289eb8e66b.json</code>
is the independent updater receipt. Before each path it restored the original
historical archive, changed only <code>dbversion</code>, mounted the exact
checkout updater files, and used the normal updater route.

| Start path | HTTP result | Response SHA-256 | Terminal requirements |
| --- | --- | --- | --- |
| 79 | HTTP 200, 6,738 bytes | <code>c3baf7232da580604f2fb12b03f072617175e6a1a2fd8bcb54de805ed4f15a25</code> | 81; one <code>floors_json</code>; Config InnoDB; one <code>HeatmapExplorerBeta=0</code> |
| 80 | HTTP 200, 6,582 bytes | <code>2ac99847ebe9b36427f765431c1fee1bec8830f73a1df7eae74abf72678ac058</code> | 81; same postconditions |

After each path and again finally, the harness restored the original
<code>dbversion=89</code> archive and full logical fingerprint. The web image
was unchanged before/after:
<code>sha256:6355a04931b45258e0fe7f319e1fdb6e5b81320fda9deda6afa41cf5554b7c13</code>.
Its finally path removed the temporary updater mount, recreated web, and
restarted/health-checked only the exact proxy and worker writers it had
quiesced.

## Historical projection calibration

The deterministic top coordinate-bearing case is
<code>cstrike/de_dust2/player 162</code>: 175 stored events, 350 coordinate
candidates, and populated inspected cell <code>c82.5</code>. The stored legacy
projection was usable historical data but weak: <code>xoffset=384</code>,
<code>yoffset=1120</code>, <code>scale=1.2599999905</code>,
<code>flipx=0</code>, <code>flipy=1</code>, <code>rotate=0</code>, and only
<code>30/350 = 0.085714</code> coverage.

Over the mandated stored-event window <code>1736115925..1767651925</code>, the
same product scene builder validated the derived normal projection:
<code>state=ok</code>, <code>projected=350</code>, <code>inBounds=350</code>,
<code>coverage=1.0</code>, and <code>cell=c82.5</code>. There were 175 source
rows and 10 excluded suicides.

The supported calibrator, never raw SQL, applied only this disposable target:

~~~text
scripts/heatmap_projection_calibrate.py --apply --runtime-gate-approved --force
  --threshold 0.70 --xoffset 2427 --yoffset 3280 --scale 4.351792
  --flipx 0 --flipy 1 --rotate 0 --assets-root <unique ignored staging root>
~~~

The required force rationale is historical-window timing: the calibrator's
ordinary current-days window saw zero current events, whereas the product scene
builder had already validated the stored historical window. The staging root
contained only
<code>web/hlstatsimg/games/cstrike/maps/de_dust2.jpg</code>; source and staged
SHA-256 were equal:
<code>37d37f7f9c64a3d5c54218aaa87873fde854ac4ead6bb8a8c2a8eecc3bed325f</code>.
The staging root was removed in finally.

The post-apply readback was <code>xoffset=2427</code>,
<code>yoffset=3280</code>, <code>scale=4.3517918587</code>,
<code>flipx=0</code>, <code>flipy=1</code>, <code>rotate=0</code>, and
<code>days=30</code>. Its FLOAT delta from requested 4.351792 is
0.0000001413, inside the approved <= 1e-6 tolerance. A no-override historical
scene then re-proved state ok, coverage >=0.70 (actual 1.0), and a populated
cell. Receipt:
<code>task-11-evidence/calibration-apply-d8bb06c2-26e1-4bed-a443-c5737a9c00b5.json</code>.

## Fixed performance protocol and baseline

The acceptance protocol was fixed before measurement:

- four EXPLAIN JSON descriptors once each: <code>scene_total</code>,
  <code>scene_player_comparison_same_sql</code>, <code>inspect</code>, and
  <code>suicide_count</code>;
- exactly 5 cold, 30 warm, and 30 inspect requests (65 samples);
- clean metric-log boundary plus exact expected/observed request correlation
  (65/65), no truncation, partial sample, or request error;
- HTTP 200, one unambiguous gzip response/header block, gzip body SHA capture,
  and bins inspection;
- thresholds: cold p95 <= 1,500 ms, warm p95 <= 300 ms, inspect p95 <= 300 ms,
  gzip <= 409,600 bytes, and bins <= 20,000.

Baseline receipt:
<code>task-11-evidence/performance-summary-93744feb-2db8-41be-8d95-31c1e196ca26.json</code>.
The 65 raw samples have SHA-256
<code>727d390d6cfd2820ee69e523715c2ab27ede85594529bbc2130ef5d634a1143e</code>.

| Gate | Baseline result | Threshold | Result |
| --- | ---: | ---: | --- |
| Cold p95 | 22.573947906494141 ms | 1,500 ms | pass |
| Warm p95 | 4.7440528869628906 ms | 300 ms | pass |
| Inspect p95 | 12.068033218383787 ms | 300 ms | pass |
| Bins returned | 301 | 20,000 | pass |
| Gzip body | 5,176 bytes | 409,600 bytes | pass |
| HTTP / encoding | 200 / gzip | required | pass |

The baseline gzip body SHA-256 is
<code>de5575a52a0fe815489f443e32aa60088aeb91c740f1e1428343d7f17dd914bd</code>.
The repeated Teamkills branches were <code>ALL</code> over 42 rows for this
predicate:

~~~sql
hef.map = :teamkills_map
AND hef.eventTime >= FROM_UNIXTIME(:teamkills_from)
AND hef.eventTime < FROM_UNIXTIME(:teamkills_to)
~~~

The separate Suicides descriptor remained <code>hes ALL</code> over 83 rows and
was deliberately outside this task.

## One-index A/B decision

The sole candidate DDL was:

~~~sql
ALTER TABLE hlstats_Events_Teamkills
  ADD KEY mapEventTime (map, eventTime);
~~~

It took 309.376 ms. Before execution Teamkills had only PRIMARY and
<code>killerId</code>; after readback <code>mapEventTime</code> had exactly
part 1 <code>map</code> and part 2 <code>eventTime</code>. No <code>serverId</code>
variation, Suicides index, second table, or second index was evaluated.

Candidate receipt:
<code>task-11-evidence/performance-summary-d5c8602f-a52c-4607-a95b-4addbc1cdceb.json</code>.
It repeats the same candidate, EXPLAIN descriptors, 5/30/30 count,
metric-correlation guard, and gzip capture. Its samples have SHA-256
<code>89a1306913f41b2c27c5c1b831757357e0d17615d9441abdb674f98884a371f4</code>.

| Gate | Baseline p95 | Candidate p95 | Change | Result |
| --- | ---: | ---: | ---: | --- |
| Cold | 22.573947906494141 ms | 21.52705192565918 ms | -4.64% | pass |
| Warm | 4.7440528869628906 ms | 4.6107769012451172 ms | -2.81% | pass |
| Inspect | 12.068033218383787 ms | 8.9669227600097656 ms | -25.70% | pass |
| Gzip body | 5,176 bytes | 5,176 bytes | 0 bytes | pass |
| Gzip SHA-256 | <code>de5575…14bd</code> | <code>de5575…14bd</code> | identical | pass |
| Correlated metric lines | 65/65 | 65/65 | exact | pass |

The repeated Teamkills branches moved from <code>ALL</code> to
<code>range</code> using <code>mapEventTime</code> for the stated predicate;
associated branches remained <code>ref</code>/<code>eq_ref</code> as
appropriate. The only remaining explicit full scan is the excluded Suicides
descriptor. There is no material regression and all fixed thresholds pass.

Both historical performance harnesses restored the exact historical archive and
full logical fingerprint, removed temporary updater files, recreated web, and
restarted the exact stopped writers.

## Source promotion: updater 82 and fresh install

The retained source surface is intentionally narrow:

- <code>web/updater/82.php</code> guards direct access, checks for
  <code>mapEventTime</code>, adds it only if absent, updates product version,
  and writes <code>dbversion=82</code> last.
- <code>sql/install.sql</code> sets fresh install DBVERSION 82 and declares
  the identical Teamkills index.
- <code>scripts/web_heatmap_smoke.php</code> checks fresh-install schema/version
  and executes updater 82 with both absent and already-present index seams.

The updater seam is idempotent: missing index yields one DDL before the terminal
dbversion update; present index yields no DDL and still ends at 82. It does not
change historical data or projection configuration.

## Fresh indexed canonical contour

The fresh source-contour identity is
<code>bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8</code>, with state receipt
<code>task-11-evidence/dual-contour-index82-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.state.json</code>.
It used supported label <code>narrow-1000</code>, did not overwrite an older
state, and did not perform a second restore/infra run.

1. The canonical runner ran only through <code>-ToStage preflight</code> on the
   fresh state using the external corpus and read-only MMDB above.
2. On that exact state, the ignored staged bridge placed exact checkout updater
   files into loopback web, changed only disposable <code>dbversion</code> to
   80, and used the normal HTTP updater. Receipt:
   <code>task-11-evidence/contour-index82-updater-ac20d01d-77db-4fc9-8303-b81f16da2534.json</code>.
3. The bridge read back terminal <code>dbversion=82</code> and both exact
   <code>mapEventTime</code> parts before resume. The fresh Python database
   therefore imported with retained source migration installed; no ad-hoc DDL
   was injected.
4. The unique FTP source and expected mount mode were inspected before and
   after updater web recreation. Container evidence saw exactly 1,000 logs and
   the matching first/last endpoints. Web alone was recreated with
   <code>--no-deps</code>, preventing a log-ftp rebind.
5. The same state resumed at <code>-FromStage legacy_import</code> without
   overwrite: 1,000 files processed, 0 skipped, 0 errors, 672,223 lines,
   1,969 dropped, 321.267 s (3.11 files/s, 2,092.41 lines/s). The runner does
   not publish a separate Python FTP elapsed time, so none is inferred.
6. Both input manifests are byte-identical: 1,000 lines, 13,000 bytes, the
   stated endpoints and SHA. The Python ignored-lines manifest is intentionally
   empty (0 bytes/0 lines; empty-content SHA), not absent.
7. Shared maintenance passed on both sides on 2026-01-06 using
   replay-window-max-plus-one and <code>numdays=1</code>. Matching counts are
   awards 998, player awards 9, player ribbons 8, and GeoIP
   flag/country/city/state/coordinates 250/250/219/221/250. Both SQL snapshots
   are 1,107 bytes.
8. The runner stopped at the deliberately red strict comparison. The contour
   <code>web_smoke</code> stage is pending and was **not run**. It is recorded
   as absent, not treated as a pass.

The fresh contour proves migration/install-before-import, import, maintenance,
and comparison evidence. It is not a post-comparison browser acceptance.

## Preserved failures and cleanup boundary

Failures remain preserved rather than overwritten:

- <code>cac7cec3-39c7-4f2f-8865-1355cb40bb03</code> is the accepted red
  coordinate-only comparison receipt, not a harness failure.
- <code>contour-index82-updater-bc62ec6a-ed2b-4a45-bf40-3c74044dcc43.failure.json</code>
  records PowerShell backtick handling in helper SQL and stopped before
  controlled runtime mutation.
- <code>contour-index82-updater-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.failure.json</code>
  records formatted docker-inspect handling and stopped before DB writes.
- <code>contour-index82-updater-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8-r2.failure.json</code>
  records the <code>find -printf</code> newline defect and stopped before
  quiesce/mutation.
- The retained <code>performance-*.failure.json</code>,
  <code>performance-bridge-*.failure.json</code>,
  <code>calibration-apply-11e69cfb-0670-44c7-aa1e-f6014b3c5071.failure.json</code>,
  and <code>calibration-preflight-34dfa333-c41d-4fad-a792-255f64354b09.failure.txt</code>
  retain the other failed/aborted harness paths.

The final staged bridge changed harness lifecycle only: exact FTP-stage
environment on every compose call; web-only force recreate with
<code>--no-deps</code>; raw inspect proof of source/mode; and
container <code>find -print</code> leaf-name ordinal sorting against the
manifest. It does not alter product behavior.

Historical updater, calibration, and performance runs completed their finally
cleanup and exact <code>dbversion=89</code> restoration. The fresh
<code>bad9…</code> source contour remains at its captured post-comparison state
under this documentation-only handoff; this turn did not mutate or tear down
containers, services, databases, or receipts. Any later teardown needs a
separate operator decision.

## Evidence inventory

All paths are repository-relative. <code>task-11-evidence</code> is ignored
runtime evidence and remains intentionally untracked.

~~~text
docs/audits/legacy-python-parity-20260423/
  logical-compare-narrow-1000-cac7cec3-39c7-4f2f-8865-1355cb40bb03.txt
  logical-compare-narrow-1000-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.txt
  maintenance-summary-narrow-1000-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.txt
  legacy-sql-snapshot-narrow-1000-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.txt
  python-sql-snapshot-narrow-1000-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.txt
  python-ignored-lines-narrow-1000-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.txt

.superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence/
  updater-http-31821ddc-25a0-4a75-b97c-ed289eb8e66b.json
  calibration-apply-d8bb06c2-26e1-4bed-a443-c5737a9c00b5.json
  performance-summary-93744feb-2db8-41be-8d95-31c1e196ca26.json
  performance-samples-93744feb-2db8-41be-8d95-31c1e196ca26.jsonl
  explains-93744feb-2db8-41be-8d95-31c1e196ca26.json
  gzip-93744feb-2db8-41be-8d95-31c1e196ca26.{headers.txt,body.gz}
  performance-summary-d5c8602f-a52c-4607-a95b-4addbc1cdceb.json
  performance-samples-d5c8602f-a52c-4607-a95b-4addbc1cdceb.jsonl
  explains-d5c8602f-a52c-4607-a95b-4addbc1cdceb.json
  gzip-d5c8602f-a52c-4607-a95b-4addbc1cdceb.{headers.txt,body.gz}
  dual-contour-index82-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.state.json
  contour-index82-updater-ac20d01d-77db-4fc9-8303-b81f16da2534.json
  contour-index82-updater-bc62ec6a-ed2b-4a45-bf40-3c74044dcc43.failure.json
  contour-index82-updater-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.failure.json
  contour-index82-updater-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8-r2.failure.json
~~~

## Exact executed command appendix (archival only)

This appendix preserves the actual Task 11 command lines and immutable
identities. It is a documentary reproduction record, **not** an instruction to
rerun the preserved runs: do not reuse their IDs, state paths, staging roots, or
receipt paths. A future run must allocate new UUIDs for every
<code>EvidenceRunId</code>, <code>BridgeRunId</code>,
<code>CalibrationRunId</code>, and <code>PerformanceRunId</code>, plus a new
state path. The evidence root for the non-contour receipts below is
<code>D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\.superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence</code>.

The fresh <code>cac7...</code> contour used the external immutable corpus
<code>D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\docs\audits\legacy-python-parity-20260423\legacy-window-1000</code>,
the read-only MMDB directory
<code>D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\scripts\GeoLiteCity</code>
(<code>GeoLite2-City.mmdb</code>), and its own state:

~~~powershell
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -Command '& { $env:HLSTATS_GEOIP_DIR_HOST_PATH = "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\scripts\GeoLiteCity"; & "scripts\replay_baseline\comparison\Run-DualContour-1000.ps1" -MaxImportFiles 1000 -ArtifactLabel "narrow-1000" -EvidenceRunId "cac7cec3-39c7-4f2f-8865-1355cb40bb03" -ArtifactsDir "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\docs\audits\legacy-python-parity-20260423\legacy-window-1000" -UseDumpRestore -StatePath ".superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence\dual-contour-cac7cec3-39c7-4f2f-8865-1355cb40bb03.state.json"; exit $LASTEXITCODE }'
~~~

Its strict receipt is
<code>docs/audits/legacy-python-parity-20260423/logical-compare-narrow-1000-cac7cec3-39c7-4f2f-8865-1355cb40bb03.txt</code>.
The plan's exact <code>heatmap-explorer-narrow-1000</code> label was rejected by
the runner, which accepts only <code>narrow-1000</code>,
<code>full-41513</code>, or <code>prefix-*</code> as
<code>ArtifactLabel</code>; executed 1,000-file runs used
<code>narrow-1000</code> instead.

The independent 79/80 historical updater acceptance used the original db89
archive and created
<code>task-11-evidence/updater-http-31821ddc-25a0-4a75-b97c-ed289eb8e66b.json</code>:

~~~powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File .superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence\Run-Task11UpdaterAcceptance.ps1 -EvidenceDir .superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence -EvidenceRunId 31821ddc-25a0-4a75-b97c-ed289eb8e66b -RepoRoot .
~~~

The successful db89-to-81 bridge, supported historical calibration, and
baseline performance measurement were:

~~~powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File ".superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence/Prepare-Task11PerformanceSchema.ps1" -EvidenceDir ".superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence" -EvidenceRunId "31821ddc-25a0-4a75-b97c-ed289eb8e66b" -BridgeRunId "c473299a-f504-4426-8120-974169a1cf83" -RepoRoot "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer"
rtk powershell -NoProfile -ExecutionPolicy Bypass -File ".superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence/Run-Task11CalibrationApply.ps1" -EvidenceDir ".superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence" -EvidenceRunId "31821ddc-25a0-4a75-b97c-ed289eb8e66b" -BridgeRunId "c473299a-f504-4426-8120-974169a1cf83" -CalibrationRunId "d8bb06c2-26e1-4bed-a443-c5737a9c00b5" -RepoRoot "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer"
rtk powershell -NoProfile -ExecutionPolicy Bypass -File ".superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence/Run-Task11Performance.ps1" -EvidenceDir ".superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence" -EvidenceRunId "31821ddc-25a0-4a75-b97c-ed289eb8e66b" -PerformanceRunId "93744feb-2db8-41be-8d95-31c1e196ca26" -RepoRoot "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer"
~~~

Their corresponding receipt paths are
<code>task-11-evidence/performance-bridge-c473299a-f504-4426-8120-974169a1cf83.json</code>,
<code>task-11-evidence/calibration-apply-d8bb06c2-26e1-4bed-a443-c5737a9c00b5.json</code>,
and <code>task-11-evidence/performance-summary-93744feb-2db8-41be-8d95-31c1e196ca26.json</code>.
The retained one-index candidate A/B rerun and its receipts were:

~~~powershell
rtk powershell -NoProfile -File .superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence/Run-Task11Performance.ps1 -EvidenceDir .superpowers/sdd/2026-08-31-modern-heatmap-explorer/task-11-evidence -EvidenceRunId 31821ddc-25a0-4a75-b97c-ed289eb8e66b -PerformanceRunId d5c8602f-a52c-4607-a95b-4addbc1cdceb -ApplyApprovedTeamkillsMapEventTimeIndex -RepoRoot .
~~~

<code>task-11-evidence/performance-summary-d5c8602f-a52c-4607-a95b-4addbc1cdceb.json</code>,
its samples, EXPLAIN, and gzip files are the authoritative candidate receipts.

The staged fresh indexed contour kept one state and one external corpus. First,
the exact preflight command created
<code>dual-contour-index82-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.state.json</code>:

~~~powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -Command '& { $env:HLSTATS_GEOIP_DIR_HOST_PATH = "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\scripts\GeoLiteCity"; & rtk powershell -NoProfile -ExecutionPolicy Bypass -File "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\scripts\replay_baseline\comparison\Run-DualContour-1000.ps1" -MaxImportFiles 1000 -ArtifactLabel narrow-1000 -EvidenceRunId "bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8" -ArtifactsDir "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\docs\audits\legacy-python-parity-20260423\legacy-window-1000" -UseDumpRestore -StatePath "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\.superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence\dual-contour-index82-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.state.json" -ToStage preflight; exit $LASTEXITCODE }'
~~~

The normal HTTP updater bridge used the unique FTP stage
<code>D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\scripts\replay_baseline\comparison\.parity-state\ftp-logs\bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8</code>
and wrote
<code>task-11-evidence/contour-index82-updater-ac20d01d-77db-4fc9-8303-b81f16da2534.json</code>:

~~~powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\.superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence\Run-Task11StagedIndex82Bridge.ps1" -EvidenceDir "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\.superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence" -EvidenceRunId "bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8" -BridgeRunId "ac20d01d-77db-4fc9-8303-b81f16da2534" -RepoRoot "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer" -StatePath "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\.superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence\dual-contour-index82-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.state.json" -FtpLogStagePath "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\scripts\replay_baseline\comparison\.parity-state\ftp-logs\bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8"
~~~

It then resumed the same state, not a second restore/infra run, from
<code>legacy_import</code>:

~~~powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -Command '& { $env:HLSTATS_GEOIP_DIR_HOST_PATH = "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\scripts\GeoLiteCity"; & rtk powershell -NoProfile -ExecutionPolicy Bypass -File "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\scripts\replay_baseline\comparison\Run-DualContour-1000.ps1" -MaxImportFiles 1000 -ArtifactLabel narrow-1000 -EvidenceRunId "bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8" -ArtifactsDir "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n\docs\audits\legacy-python-parity-20260423\legacy-window-1000" -UseDumpRestore -StatePath "D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer\.superpowers\sdd\2026-08-31-modern-heatmap-explorer\task-11-evidence\dual-contour-index82-bad9b5ea-6dd3-494d-b8b3-0ceaa2fd4cc8.state.json" -FromStage legacy_import; exit $LASTEXITCODE }'
~~~

### Current source-validation boundary and engine caveat

The current source-only checks were run against an immutable checkout mount:

~~~powershell
rtk docker run --rm --network none --mount "type=bind,src=D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer,dst=/workspace,readonly" --workdir /workspace --entrypoint php python-web -l web/updater/82.php
rtk docker run --rm --network none --mount "type=bind,src=D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n-heatmap-explorer,dst=/workspace,readonly" --workdir /workspace --entrypoint php python-web scripts/web_heatmap_smoke.php
rtk git diff --check
~~~

They passed: Docker PHP lint reported no syntax errors, the mounted-source
<code>web_heatmap_smoke.php</code> reported <code>web heatmap smoke ok</code>,
and the diff check was clean. This is a source/mounted smoke boundary only; it
does not convert the pending contour <code>web_smoke</code> stage into a pass.

The measured candidate database's <code>hlstats_Events_Teamkills</code> table
was InnoDB. Fresh <code>sql/install.sql</code> intentionally remains MyISAM.
Therefore the historical A/B timing result is not a fresh-install MyISAM
performance claim. Before a release, a maintenance-window acceptance must
verify the actual production table engine, DDL locking/availability behavior,
and runtime performance; no timing result is transferred across those engines.

## Explicit acceptance and non-claims

Accepted at this boundary:

- the one <code>mapEventTime (map, eventTime)</code> index is
  source-justified, idempotent through the updater, fresh-install declared, and
  proved before fresh Python import;
- the calibration used the supported route only and has a no-override
  historical scene proof;
- both A/B measurement sets meet all fixed performance, gzip, request-count,
  metric-correlation, EXPLAIN, and index-retention gates;
- the fresh narrow contour imported, maintained, and matched all
  non-coordinate anchors/snapshots before the known red residual.

Not accepted or claimed:

- strict logical comparator green;
- contour <code>web_smoke</code> success;
- production migration, calibration, deploy, teardown, or commit;
- scope expansion beyond this one Teamkills composite index.
