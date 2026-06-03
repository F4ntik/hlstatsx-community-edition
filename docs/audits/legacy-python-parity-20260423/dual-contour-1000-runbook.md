# Dual Contour 1000-Log Runbook

## Goal
Bring up legacy and python comparison contours from the same baseline, import 1000 logs each, and prepare page-visible parity checks.

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
Use:

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000`

What it does:
- brings both stacks down/up
- restores baseline for both stacks
- runs bounded import for legacy and python
- writes SQL snapshots:
  - `docs/audits/legacy-python-parity-20260423/legacy-sql-snapshot-1000.txt`
  - `docs/audits/legacy-python-parity-20260423/python-sql-snapshot-1000.txt`

## Staged orchestration (resume-friendly)
`Run-DualContour-1000.ps1` now supports staged execution with run-state files under:

- `scripts/replay_baseline/comparison/.parity-state/*.json`

New flags:

- `-OnlyStage <infra_updown|baseline_restore|preflight|legacy_import|python_import|sql_snapshot>`
- `-FromStage <stage> -ToStage <stage>`
- `-ResumeLatest` or `-ResumeRunId <id>`
- `-Stack both|legacy|python` (default: `both`)

Strict dependency policy:

- `legacy_import`, `python_import`, `sql_snapshot` require completed `baseline_restore` and `preflight` in the same run state.
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
1. Reset both contours to same baseline.
2. Create `legacy-window-1000` and `legacy-input-manifest-1000.txt`.
3. Replay legacy from this window.
4. Replay python from this same window (not from FTP incremental mode).
5. Save SQL snapshots for sanity checks.
6. Run page-visible parity audit.

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
