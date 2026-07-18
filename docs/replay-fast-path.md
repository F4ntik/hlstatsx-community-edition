# Быстрый прогон логов (Python): канон и ссылки

Этот файл — **единая точка входа**: здесь не дублируется вся процедура, а
собрано то, что уже отработано в других документах и скриптах. Не изобретать
новый «ускоритель»; следовать ссылкам ниже.

## Что считать быстрым контуром

1. **Прямой импорт в одном процессе (stdin), без UDP**  
   Парсинг и запись в БД идут через `hlstats_py.runtime --stdin`, без построчной
   отправки по сети. Для окон из многих `*.log` используйте:
   - `scripts/replay_baseline/direct_import_artifacts.py` (внутри образа
     `hlstats-worker` путь `/app/scripts/replay_baseline/direct_import_artifacts.py`);
   - или PowerShell-оркестрацию контура FTP:
     `scripts/replay_baseline/comparison/python/Run-ContourFtpArtifacts.ps1`;
   - или `python -m hlstats_ftp_py` в **batch**-режиме (см. README модуля).

2. **Транзакции и тихий лог (уже настроено по умолчанию)**  
   Пакетные коммиты и отключение шумного построчного логирования событий —
   флаги `--stdin-transaction-batch-size`, `--stdin-verbose-events` и профили
   в **`docs/hlstats_py_stdin_import_tuning.md`**. Это отдельно от UDP: речь о
   том, чтобы не упираться в I/O и в `autocommit` на каждую операцию.

3. **Медленный путь (только осознанно)**  
   `replay_python_log.py` — UDP с задержками/пейсингом; годится для проверки
   транспорта и прокси, **не** для массовых table-diff / узких окон на сотнях
   файлов. Подробнее: **`docs/audits/legacy-python-parity-20260423/performance.md`**
   и раздел replay в **`docs/test-plan.md`**.

## Контракт манифестов и артефактов

Для сравнимого batch-прогона список файлов фиксируется после сортировки,
статического отбора и ограничения `--max-files`. В режиме `--static-replay`
FTP-контур не отбрасывает самый новый файл по mtime; это режим для replay,
когда входом является уже выбранный набор файлов.

Прямой импорт и FTP-контур принимают:

```text
--input-manifest <path>
--ignored-lines-manifest <path>
--continue-on-parse-error
```

`--continue-on-parse-error` без `--ignored-lines-manifest` отвергается до
импорта. Манифест входов содержит именно финальный выбранный список, а
манифест ignored-lines пишется из того же Python-процесса. Существующий файл
не перезаписывается неявно; для намеренной замены нужен явный
`--overwrite-manifests`. Runner передаёт временные пути в контейнер и
публикует их в audit-dir только после успешного импорта.

Для каждого прогона задавайте канонический `ArtifactLabel`:
`narrow-1000`, `full-41513` или `prefix-*`, и уникальный `EvidenceRunId`.
Старые артефакты с именем `*-1000` проверяйте по количеству, SHA и contour
metadata: часть из них является misnamed `full-41513`, а не narrow-1000.

## Где искать команды и нюансы

| Тема | Документ / скрипт |
|------|-------------------|
| Пошаговый тест-план replay | `docs/test-plan.md` (раздел Python / replay) |
| UDP vs stdin, методика | `docs/audits/legacy-python-parity-20260423/performance.md` |
| Флаги stdin / batch DB | `docs/hlstats_py_stdin_import_tuning.md` |
| Обзор baseline-реплея | `scripts/replay_baseline/README.md` |
| Бенчи многофайлового импорта | `scripts/replay_baseline/bench_ephemeral/README.md` |
| FTP-контур без UDP | `scripts/replay_baseline/comparison/python/FTP_CONTOUR.md` |
| Batch FTP → runtime | `scripts/hlstats_ftp_py/README.md` |

## Отладочные trace-файлы

Обычный импорт не должен писать дополнительные артефакты. Для точечного разбора
`TeamBonuses` можно включить stage trace явно:

```powershell
$env:HLSTATS_TEAM_BONUS_TRACE_PATH = "scripts/replay_baseline/artifacts/team-bonus-stage-trace.json"
```

Без этой переменной `hlstats_py.storage` только собирает счётчики в памяти во
время процесса и не создаёт JSON на диске.

## Переиспользование legacy narrow-1000

Не переподнимать legacy-контур и не молотить те же `1000` логов по привычке.
Legacy Perl в этом окне — стабильный эталон. Его можно переиспользовать, если
не менялись:

- baseline dump/snapshot;
- путь к corpus и первые `1000` sorted `*.log`;
- `server_identity=37.230.137.48:27015`;
- replay policy `--drop-empty-team-enter-events`;
- цель сравнения: narrow-1000 runtime diff.

При Python-only refactor предпочтительный loop: проверить fingerprint/SQL
snapshot legacy narrow-1000, не трогать legacy DB, переиграть только Python
FTP/stdin и запустить `compare_stats_dbs.py`. Если хотя бы один input из списка
выше изменился, legacy нужно переиграть от dump-baseline.

Для инспекции контейнеров следующий tooling milestone должен добавить metadata
в labels и/или mounted file вроде `/app/CONTOUR_INFO.json`: тип контура,
baseline, corpus window, server identity, replay policy, время импорта,
row-count anchors.

Текущий флаг для этого loop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy
```

Если metadata/fingerprint для legacy не найден или anchors невалидны, скрипт
сам откатывается к обычному full dual run. Если legacy валиден, скрипт не
делает `docker compose down` для legacy, не вызывает restore/import legacy и не
перезаписывает legacy SQL snapshot. Metadata пишется в
`scripts/replay_baseline/comparison/.parity-state/contour-info/` и копируется
в запущенные контейнеры как `/CONTOUR_INFO.json`.

Для heatmap-проекции единый контракт rotate — `0..3` с истинными четверть-
оборотами и обратным преобразованием. Старые записи с rotate только `0/1`
можно переводить отдельным версионированным updater после read-only проверки
распределения; при наличии `2/3` updater останавливается для ручной
классификации и не выполняет массовый SQL.

Сначала запускайте dry-run:

```powershell
python scripts/heatmap_projection_migrate.py `
  --configfile scripts/replay_baseline/comparison/python/hlstats.host.conf
```

`--apply --runtime-gate-approved` разрешается только после проверки
распределения, backup и отдельного runtime-gate. Сам `--apply` без второго
флага отклоняется до подключения к БД. Это не часть автоматического replay
или narrow-1000 promotion.

Ручной DB-first калибратор использует тот же fail-closed контракт: его
`--apply` также требует `--runtime-gate-approved`; preview без `--apply` остаётся
read-only.

Если legacy narrow-1000 уже был успешно прогнан до появления metadata, можно
один раз принять текущее состояние как эталон:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -AdoptCurrentLegacy -ReuseValidLegacy -OnlyStage preflight
```

Использовать `-AdoptCurrentLegacy` только после известного успешного replay
того же окна; этот флаг доверяет текущей legacy DB и записывает fingerprint +
row-count anchors.

## Образ worker и свежий код

Скрипты в контейнере **копируются в образ** при сборке. После правок в
`hlstats_py` и т.д. перед прогоном: **`docker compose build hlstats-worker`**
в каталоге `scripts/replay_baseline/comparison/python/` (см. также
`scripts/replay_baseline/README.md`).

## Рабочий репозиторий (монорепо)

Активная разработка и правки документации по этому продукту ведутся **только**
в каталоге **`hlstatsx-community-edition-python-i18n/`**. Соседние деревья
(`hlstatsx-community-edition/`, `hlstatsx-community-edition-web-ru-i18n/` и др.)
используются как **справочник** (архитектура, legacy, донорский веб-i18n), если
задача явно не требует менять их. См. **`AGENTS.md`** в корне этого подпроекта
и корневой **`AGENTS.md`** воркспейса.
