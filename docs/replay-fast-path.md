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

### Scratch-том Python-контура

Для stdin-импорта `Run-DualContour-1000.ps1` создаёт уникальный именованный
Docker volume для `/tmp/ftp_work`, а после успешной фазы экспортирует из него
только два manifest-файла в audit-dir и удаляет volume в `finally`. Не
подменяйте его host bind-mount: на Docker Desktop/Windows 9p доступ к большому
набору логов может остановить Python FTP-воркер в I/O wait. Конфликт имени
volume является ошибкой запуска, а не поводом переиспользовать чужой том.

Перед поднятием Python FTP-сервиса runner также копирует **только выбранные**
логи в `scripts/replay_baseline/comparison/.parity-state/ftp-logs/<EvidenceRunId>`
и монтирует именно эту staging-папку. Он проверяет состав и число файлов до
старта compose; итоговые manifests затем подтверждают их общий SHA. Исходный
corpus не изменяется. Это не косметика: bind-mount всего corpus заставлял
FTP-образ обходить и менять владельца десятков тысяч файлов при старте, из-за
чего health-check выглядел как зависший replay. При неожиданном файле в stage
не очищайте его вручную: сохраните его для диагностики и используйте новый
`EvidenceRunId`.

Для каждого прогона задавайте канонический `ArtifactLabel`:
`narrow-1000`, `full-41513` или `prefix-*`, и уникальный `EvidenceRunId`.
Старые артефакты с именем `*-1000` проверяйте по количеству, SHA и contour
metadata: часть из них является misnamed `full-41513`, а не narrow-1000.

## Мониторинг долгого replay

Долгий Docker-replay не мониторится частым опросом терминала: неподвижная
строка в нём не означает остановку, а такой polling тратит ресурсы оператора.
При доступной командной работе назначайте одного отдельного наблюдателя. Он
снимает MySQL `COUNT(*)` из `hlstats_Events_Frags` в обоих контурах не чаще
одного раза в 60 секунд; основной исполнитель в это время продолжает
подготовку артефактов или анализ результата.

Для стандартного comparison compose используйте запрос ниже, подставив имя
нужного контейнера (`hlstatsx-legacy-db` или `hlstatsx-python-db`):

```powershell
docker exec <db-container> mysql -uroot -proot123 -D hlstatsxce -N -B -e "SELECT COUNT(*) FROM hlstats_Events_Frags;"
```

`root123` здесь — одноразовый fixture-пароль из локального replay compose, а
не production credential. Во время restore таблица может ещё отсутствовать:
один такой ответ является стартовой гонкой, нужно дождаться полного интервала
и повторить выборку, а не объявлять прогон неуспешным. На фазе legacy-import
растёт только legacy-контур; Python-контур может оставаться нулевым до своей
stdin-фазы. Счётчик фрагов — только telemetry живого прогресса, но не критерий
приёмки: успех подтверждают код завершения runner, финальное сравнение
контуров и сохранённые audit-артефакты.

## Release-clean maintenance после исторического replay

Обычный dual runner теперь не заканчивается на raw event import. После обоих
imports он автоматически выполняет в **обоих disposable DB**:

```text
UseTimestamp=1 -> inactive -> awards -> ribbons -> GeoIP
```

`UseTimestamp=1` проверяется readback-ом и заставляет inactive вычислять
активность от максимального `hlstats_Servers.last_event` replay, а не от
текущего времени хоста. Это необходимо для исторического corpus: исходный
`UseTimestamp=0` и `DeleteDays` зависят от wall clock. Поэтому runner намеренно
не передаёт `-p`/`--prune`: prune мог бы удалить архивные events до awards.

Выполняйте maintenance-enabled gate как свежий dual run, без
`-ReuseValidLegacy`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -ArtifactLabel narrow-1000 `
  -EvidenceRunId <new-id> `
  -UseDumpRestore
```

Runner сам сохраняет maintenance logs, SQL snapshots, `logical-compare-*`,
legacy EN-reference web-smoke log и Python EN/RU product web-smoke log.
`maintenance-summary-*` содержит дату/horizon, action set, readback
`UseTimestamp`, GeoIP/awards/ribbons counts, diff verdict, фактические языки и
динамически найденные signature player IDs, а также прямые URL daily/global/
ribbons для ручной side-by-side проверки.

`-SkipMaintenance` — только raw-debug escape hatch. Он делает evidence
`raw-only`; только в этом режиме разрешён `-ReuseValidLegacy`. Для
release-clean acceptance не запускайте отдельный Python-only `--geoip` или
отдельный compare после успешного canonical runner: они уже являются его
fail-closed стадиями.

## Source-log граница IgnoreBots

Для `IgnoreBots` только точное сообщение `Log file started` открывает новую
source-log эпоху: сбрасывается per-server bot-seed epoch, но не cache player
identity. В асинхронном stdin/replay этот reset выполняется сериализованным
storage executor, а не parse-loop/event-loop до постановки DB-операции.

Принятый source-log gate от `2026-07-22`: `prefix-100` и `narrow-1000` прошли
runner, post-replay GeoIP и полное DB-сравнение без drift. Для narrow-1000
используйте evidence ID
`20260722-ignorebots-source-log-narrow-1000-r1`; оба SQL snapshots имеют
`frags=5464`. Подробная история, включая отвергнутые pre-fix прогоны, находится
в `docs/audits/legacy-python-parity-20260423/prefix-100-20260722-p6f-history-cache-validation.md`.

Принятый release-clean maintenance gate от того же дня добавил awards/ribbons
и strict GeoIP к этому контракту: `prefix-100` run
`20260722-maintenance-prefix-100-r8` и финальный `narrow-1000` run
`20260722-maintenance-narrow-1000-r1` завершились без logical DB drift.
Полный прогон имеет одинаковые `frags=5464`, `awards=998`,
`player_awards=9`, `player_ribbons=8` и полные GeoIP counts
`250/250/219/221/250` в legacy/Python. Его воспроизводимое объяснение,
отвергнутые промежуточные гипотезы и границы EN-reference/Python EN/RU лежат в
`docs/audits/legacy-python-parity-20260423/maintenance-parity-20260722.md`.

Минимальный acceptance loop для изменения replay-пути: после точечных
регрессий выполнить maintenance-enabled `prefix-100`, затем полный
maintenance-enabled `narrow-1000`; для каждого прогона дождаться успешного
runner и проверить его maintenance summary, automatic DB compare и web smoke.

Во время долгого replay не опрашивайте постоянно одну и ту же terminal-строку.
Выделенный monitor читает только `COUNT(*)` из `hlstats_Events_Frags` в обеих
disposable DB не чаще одного раза в минуту и фиксирует изменение счётчиков или
явную недоступность DB. Это telemetry для раннего обнаружения зависания, а не
acceptance: итогом остаётся exit code runner и сохранённые maintenance summary,
compare и web-smoke evidence.

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

Для release-clean Python-only изменения legacy всё равно нужно переигрывать
свежо: import anchors не подтверждают post-maintenance состояние. Reuse ниже
предназначен только для raw event-debug.

Для raw event-debug loop (не release-clean) текущий флаг:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy -SkipMaintenance
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
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -AdoptCurrentLegacy -ReuseValidLegacy -SkipMaintenance -OnlyStage preflight
```

Использовать `-AdoptCurrentLegacy` только после известного успешного raw replay
того же окна; этот флаг доверяет текущей legacy DB и записывает fingerprint +
row-count anchors. Такая adoption/reuse-команда даёт только raw-only receipt и
не заменяет свежий release-clean dual run.

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
