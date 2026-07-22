# Dual Contour Evidence Runbook

## Goal
Bring up legacy and Python comparison contours from the same baseline, import
the selected contour window, and prepare attributable page-visible parity
checks. A supported 1,000-log acceptance run is labelled `narrow-1000`; a
full diagnostic run is labelled `full-41513`.

## Mandatory parity condition
Parity testing is valid only if both contours process the exact same replay input:
- same file manifest (same names)
- same processing order
- same line-filter policy
- same server identity

If this condition is not met, any page or SQL mismatch must be treated as input drift first, not runtime parity regression.

## Contour endpoints
- Legacy web: `http://127.0.0.1:8181/hlstats.php`
- Python web: `http://127.0.0.1:8281/hlstats.php`
- Legacy DB container: `hlstatsx-legacy-db`
- Python DB container: `hlstatsx-python-db`

## One-command orchestration
For a fresh supported narrow run, use a unique run id:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -ArtifactLabel narrow-1000 `
  -EvidenceRunId 20260718-narrow-1000-r2 `
  -UseDumpRestore
```

Replace the example `EvidenceRunId` with a new unique id. Reusing an existing
id is refused unless `-OverwriteEvidence` is supplied explicitly.

What it does:
- brings both stacks down/up
- restores baseline for both stacks
- runs bounded import for legacy and python
- configures and verifies `UseTimestamp=1` in both disposable DBs, then runs
  legacy/Python `inactive -> awards -> ribbons -> strict GeoIP` against the
  same resolved historical date/horizon; it never runs prune on the historical
  corpus
- writes full GeoIP/awards/ribbons SQL anchors, stable-key DB compare evidence,
  a legacy EN-reference web-smoke log, and a Python EN/RU product web-smoke
  log; signature IDs are resolved from shared populated combat players rather
  than copied from a stale fixture
- writes final selected manifests, same-run drop/ignored-line manifests,
  contour metadata, and SQL snapshots with the label and run id in each name;
  Python manifests are published to the audit directory only after the
  Python batch import succeeds

The accepted evidence currently retained for this lane is:

| Artifact | Value |
| --- | --- |
| label / run | `narrow-1000` / `20260717-narrow-1000-r1` |
| final manifest | 1,000 lines, 13,000 bytes, SHA-256 `95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a` for both stacks |
| contour anchors | players `323`, frags `5464`, team bonuses `4765`, entries `0`, server rows `1` |
| verdict | accepted narrow gate; raw compare retains only the documented GeoIP-only player residual |

See `runtime-db-diff-narrow-1000-20260717-narrow-1000-r1.md` and
`evidence-inventory-20260717.md` for the complete file list, ignored/drop
manifest hashes, metadata, and normalized snapshots. The older files ending
in `-1000` remain retained history; the inventory classifies those whose
counts/anchors are full corpus as `full-41513`.

### Historical maintenance receipt

The normal runner is **release-clean** by default. It derives
`MaintenanceDate` from the common maximum fragment day plus one, passes the
same `MaintenanceNumDays`, and records both values in
`maintenance-summary-<label>-<run>.txt`. It also records the exact action set,
`UseTimestamp=1` readbacks, table counts, DB-diff verdict, web-smoke logs, and
side-by-side daily/global/ribbons URLs.

The `UseTimestamp` override exists only in the restored disposable test DBs:
otherwise `inactive` follows host clock and hides a historical corpus before
awards. Prune is deliberately omitted because its `DeleteDays` cutoff is also
host-clock based and would erase historical events.

`-SkipMaintenance` produces an explicitly `raw-only` receipt. It is the only
mode where `-ReuseValidLegacy` is allowed; release-clean runs always perform a
fresh legacy import and snapshot so the post-maintenance state is attributable.

For a large source corpus, the Python FTP compose receives only the selected
manifest logs from `.parity-state/ftp-logs/<EvidenceRunId>`. The runner verifies
the staged names/count before compose and the final manifests prove the
selected SHA; it never mounts the full corpus into the FTP server. This avoids
the image startup ownership scan that can otherwise make a healthy replay look
stuck for many minutes.

For the separate full diagnostic, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 41513 `
  -ArtifactLabel full-41513 `
  -EvidenceRunId 20260718-full-41513-r2 `
  -UseDumpRestore
```

Do not promote this full run over the accepted narrow contour; its broad
stable-key residuals remain diagnostic.

## Staged orchestration (resume-friendly)
`Run-DualContour-1000.ps1` now supports staged execution with run-state files under:

- `scripts/replay_baseline/comparison/.parity-state/*.json`

New flags:

- `-OnlyStage <infra_updown|baseline_restore|preflight|legacy_import|python_import|maintenance|sql_snapshot|logical_compare|web_smoke>`
- `-FromStage <stage> -ToStage <stage>`
- `-ResumeLatest` or `-ResumeRunId <id>`
- `-Stack both|legacy|python` (default: `both`)

Strict dependency policy:

- `legacy_import`, `python_import`, `maintenance`, and `sql_snapshot` require
  completed `baseline_restore` and `preflight` in the same run state;
  `maintenance` additionally requires the selected imports, `logical_compare`
  requires snapshots, and `web_smoke` requires a passing logical compare.
- If an earlier stage is rerun, downstream completed stages are invalidated automatically.

### Common operator flows
1) Full one-shot (backward-compatible):

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000`

2) Restart only Python import after a completed baseline+preflight:

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -OnlyStage python_import -ResumeLatest -Stack python -MaxImportFiles 1000`

3) Restart only Legacy import:

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -OnlyStage legacy_import -ResumeLatest -Stack legacy -MaxImportFiles 1000`

4) Fast single-stack restore + replay (no full dual restart):

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -OnlyStage baseline_restore -ResumeLatest -Stack python`

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -OnlyStage preflight -ResumeLatest -Stack python`

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -OnlyStage python_import -ResumeLatest -Stack python -MaxImportFiles 1000`

5) Refresh SQL snapshots only:

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -OnlyStage sql_snapshot -ResumeLatest -Stack both`

6) Raw-only reuse for event/debug investigation (never release-clean):

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy -SkipMaintenance`

### Troubleshooting
- Error `State fingerprint mismatch`: parameters changed compared to the saved run. Start a new run (no resume flags) or rerun baseline+preflight with consistent flags.
- Error `requires completed stage 'baseline_restore'/'preflight'`: run the missing stage(s) first with the same `-ResumeLatest` or `-ResumeRunId`.
- If state was created with wrong options, start clean by creating a new run without resume flags.

## Preflight checklist
- `docker ps` shows all 5 python containers and all 3 legacy containers up
- both web URLs return HTTP 200
- both DBs contain seeded servers before import (`hlstats_Servers > 0`)

## Parity readiness checklist (before page audit)
- non-zero `hlstats_Events_Frags` in both contours
- non-zero `hlstats_Players` in both contours
- maps visible in `hlstats_Events_Frags` and `hlstats_Maps_Counts`
- no dominant empty map rows (`map=''`) in frags
- both contours confirmed against the same 1000-log manifest/window
- after maintenance, both SQL snapshots show `maintenance_use_timestamp=1` and
  nonzero fragment anchors remain present

## Evidence acceptance checklist

Accept a run only when all of these hold:

- legacy and Python final input manifests are byte-identical and have the
  expected count/SHA;
- both same-run ignored/drop manifests exist, including an empty Python
  ignored manifest when no Python records were skipped;
- both contour metadata files carry the same canonical label, run id,
  baseline mode, selected-log fingerprint, and comparable anchors;
- normalized snapshots agree for the accepted scope and
  `compare_stats_dbs.py` reports no new drift beyond an explicitly documented
  policy residual;
- release-clean maintenance summary reports passed maintenance, compare, and
  both web smokes, with matching `UseTimestamp=1` readbacks and inspectable
  daily/global/ribbons URLs;
- no old evidence file was silently replaced.

The runner's temporary Python manifest paths are mounted into the container;
publication into `docs/audits/...` happens only after a zero exit status from
the Python import.

## Notes
- Page parity verdict must be based on visible page data first.
- SQL is supporting evidence for root-cause triage only.

## Fast strict-parity variant (recommended for debugging)
Use this variant when the goal is to compare legacy vs python behavior on the exact same replay input.

Why:
- FTP mode in python is `mtime` and `.last` state driven.
- Legacy bounded replay is usually filename-manifest driven.
- If inputs differ, functional parity conclusions are not reliable.

Rules:
- Build one fixed manifest of 1000 files.
- Feed both contours from that same manifest/window.
- Use same server identity and same line-filter policy on both sides.
- Compare pages first, SQL second.

Minimal flow:
1. Reset both contours to the same dump baseline.
2. Run the canonical runner with a unique `ArtifactLabel`/`EvidenceRunId`.
3. Confirm the runner's final manifests and same-run drop/ignored artifacts.
4. Compare metadata and normalized SQL snapshots for the same run.
5. Run the page-visible parity audit.

Do not manually pair the historical `legacy-window-1000` files with a fresh
Python snapshot; use the runner's published run bundle.

## Heatmap migration and post-migration UI gate

This is a separate runtime-gated operation and is not part of replay
acceptance. First inspect the distribution and verify the retained backup:

```powershell
python scripts/heatmap_projection_migrate.py `
  --configfile scripts/replay_baseline/comparison/python/hlstats.host.conf
```

Do not pass any DB-mutating `--apply` until the owner gives explicit runtime
approval. The versioned updater and the DB-first calibration helper both
require `--runtime-gate-approved`; without that flag they reject the request
before connecting to the database. If the distribution contains stored
`rotate=2` or `rotate=3`, stop for manual classification and do not issue mass
SQL. After an approved migration, use `--disablecache` for one selected map
and manually verify the admin wizard/canvas overlay, diagnostics, and static
map/heatmap JPEG fallback.

The post-migration regeneration command is:

```powershell
python scripts/hlstats_py/heatmaps.py `
  --configfile scripts/replay_baseline/comparison/python/hlstats.host.conf `
  --game cstrike `
  --map de_dust2 `
  --heatmaps-root heatmaps `
  --assets-root heatmaps/src `
  --web-root web `
  --disablecache `
  --diagnose
```

Run this only after the backup and approved migration; the current
pre-migration `de_dust2` diagnostic is recorded in
`runtime-heatmap-migration-gate-20260718.md` and is not acceptance evidence.

## New chat starter template
Copy this into a new chat to restart quickly:

```text
Контекст: нужно strict parity между legacy и python после replay 1000 логов.

Цель:
1) Поднять оба контура (legacy + python) из одинакового baseline.
2) Прогнать ОДИН И ТОТ ЖЕ набор из 1000 логов для обоих.
3) Сравнить parity по данным на страницах (UI-first), SQL использовать только для triage.

Критично:
- Не использовать python FTP incremental режим как единственный источник для parity-прогона.
- Использовать общий фиксированный manifest/window (те же имена файлов, тот же порядок).
- Один и тот же server identity и одинаковые фильтры dropped lines на обоих контурах.

Ожидаемый результат:
- Артефакты запуска (manifest, dropped-lines manifests, SQL snapshots).
- Реестр page-visible mismatch'ей по core маршрутам.
- Короткий triage: input mismatch vs runtime/awards mismatch vs rendering mismatch.

Проверки перед parity verdict:
- В обоих БД не нулевые players/frags.
- Временные диапазоны событий сопоставимы.
- Для обеих сторон подтверждено, что обработан один и тот же manifest.
```
