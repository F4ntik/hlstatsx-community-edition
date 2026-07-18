# Руководство по эксплуатации Python-портов HLstatsX

Этот документ предназначен для сотрудников, которые ранее работали с Perl-скриптами `proxy-daemon.pl`, `hlstats.pl`, `hlstats-awards.pl` и `hlstats-resolve.pl`. Он описывает Python-модули, заменившие эти утилиты, и даёт пошаговый сценарий запуска: от подготовки окружения до проверки работоспособности. Следуйте разделам последовательно — по мере выполнения шагов вы получите полностью рабочую цепочку сбора статистики.

## 1. Общая подготовка

### 1.1 Требования к окружению

1. **Python 3.10+** — все Python-пакеты заданы с ограничением `^3.10`. Проверьте версию:
   ```bash
   python3 --version
   ```
2. **Poetry** — менеджер зависимостей, используемый во всех подпакетах. Установите через официальный инсталлятор (`curl -sSL https://install.python-poetry.org | python3 -`).
3. **Компилятор и заголовки MySQL** — библиотека `mysqlclient` требуется прокси-демону и скриптам, работающим с БД. На Debian/Ubuntu поставьте `build-essential python3-dev default-libmysqlclient-dev`; на RHEL/CentOS — `gcc python3-devel mariadb-connector-c-devel`.
4. **Docker и Docker Compose** — понадобятся для локальной MySQL и e2e-песочниц.
5. **Доступ к репозиторию HLstatsX Community Edition**.

### 1.2 Структура каталогов

Все Python-порты находятся в каталоге `scripts/` и повторяют названия Perl-предшественников:

| Ключевой модуль | Назначение | Каталог |
| --- | --- | --- |
| `proxy_daemon_py` | UDP-прокси между игровыми серверами и статистикой | `scripts/proxy_daemon_py` |
| `hlstats_py` | Runnable downstream worker: приём UDP от proxy daemon, нормализация событий и запись в БД | `scripts/hlstats_py` |
| `hlstats_awards_py` | Обслуживание наград, лент и архивов БД | `scripts/hlstats_awards_py` |
| `hlstats_resolve_py` | DNS-резолвер IP-адресов игроков и группировка хостов | `scripts/hlstats_resolve_py` |

### 1.3 Базовое конфигурирование

Python-утилиты используют общий формат `hlstats.conf`. Скопируйте рабочий конфиг в корень репозитория (или создайте `hlstats.local.conf` рядом с нужным модулем) и заполните ключи `DBHost`, `DBName`, `DBUsername`, `DBPassword`, `ProxyKey`, `BindIP`, `Port`, `DebugLevel`. Если запускаете стенд из репозитория, достаточно примерного файла `scripts/hlstats.conf` с корректировкой параметров подключения.

## 2. Proxy Daemon (scripts/proxy_daemon_py)

Python-порт прокси-демона — основной сервис, принимающий UDP-пакеты и управляющий балансировкой downstream-демонов.

### 2.1 Расположение и назначение

* **Каталог**: `scripts/proxy_daemon_py`
* **Основные пакеты**: `proxy_daemon_py.cli`, `proxy_daemon_py.runtime`, `proxy_daemon_py.importer`
* **Назначение**: приём UDP-пакетов от игровых серверов, валидация ключа, распределение трафика на downstream-демоны и публикация heartbeat.
* **Почему запускать даже с одним игровым сервером**: Python-демон заменяет Perl-реализацию «один к одному», поэтому остаётся точкой входа для всей статистики. Даже если у вас единственный сервер CS/TF2, именно через прокси проходят heartbeat, проверка ключей и конвертация пакетов в формат `hlstats_py`. Прямое подключение `hlstats_py` к игре не поддерживается — без демона вы потеряете контроль доступа и балансировку heartbeat.

### 2.2 Подготовка окружения

1. Перейдите в каталог проекта:
   ```bash
   cd scripts/proxy_daemon_py
   ```
2. Создайте виртуальное окружение и установите зависимости:
   ```bash
   poetry install
   ```
3. При необходимости активируйте окружение:
   ```bash
   poetry shell
   ```

### 2.3 Конфигурация и внешние сервисы

* **База данных**: для локальных проверок используйте один из сценариев:
  * Минимальная MySQL — выполните `docker compose up -d`, схема создастся автоматически.
  * E2E-песочница — `e2e/start.sh` запустит MySQL (`localhost:33070`), сам демон и мок-воркеры; `e2e/stop.sh` выключит окружение. Скрипты написаны на Bash, поэтому под Windows их удобнее запускать через WSL или Git Bash. Если у вас только PowerShell, смотрите раздел 6.2 в руководстве по прокси-демону — там описан ручной запуск контейнеров.
  * Полный Python-стек — `fullstack/docker-compose.yml` поднимает `mysql + proxy-daemon + hlstats worker + php web` и подходит для smoke-теста всей цепочки.
* **Конфиг**: убедитесь, что рядом доступен `hlstats.conf` (или `hlstats.local.conf`) с заполненными параметрами `DBHost`, `DBName`, `DBUsername`, `DBPassword`, `ProxyKey`, `BindIP`, `Port`, `DebugLevel`.
* **Верификация**: проверьте конфигурацию, не запуская рабочие процессы:
  ```bash
  poetry run python -m proxy_daemon_py.cli --configfile hlstats.local.conf --foreground
  ```

### 2.4 Основные сценарии запуска

1. Подготовьте MySQL и заполните таблицы `Proxy_Daemons` и `hlstats_Servers` (скрипты из каталога `sql/` или выгрузка из продакшена).
2. Запустите сервис в переднем плане для отладки:
   ```bash
   poetry run python -m proxy_daemon_py.runtime \
     --configfile ../hlstats.local.conf \
     --foreground
   ```
3. Проверьте heartbeat:
   ```bash
   printf 'C;HEARTBEAT;' | nc -u -w1 <bind_ip> <port>
   ```
   В ответ должно прийти `Heartbeat OK`.
4. Для импорта существующего состояния выполните:
   ```bash
   poetry run python -m proxy_daemon_py.importer --configfile hlstats.local.conf
   ```

### 2.5 Тестирование и статические проверки

Перед коммитом прогоните локальный аналог CI:
```bash
poetry run ruff check .
poetry run black --check .
poetry run mypy .
poetry run pytest
```

## 3. Статистический worker hlstats_py (scripts/hlstats_py)

Пакет отвечает за downstream-обработку: worker принимает UDP-события от `proxy_daemon_py`, нормализует их и пишет в БД. Его модули также можно импортировать как библиотеку.

### 3.1 Расположение и назначение

* **Каталог**: `scripts/hlstats_py`
* **Основные пакеты**: `hlstats_py.runtime`, `hlstats_py.events`, `hlstats_py.storage`
* **Назначение**: приём событий от прокси-демона, построение внутренних моделей и применение SQL-операций.

### 3.2 Подготовка окружения

`hlstats_py` имеет собственное Poetry-окружение и использует общий пакет
`hlx_core` для конфигурации, БД, логирования и UDP transport helpers:
```bash
cd scripts/hlstats_py
poetry install
```
Для прямого запуска из корня без активированного окружения достаточно
`PYTHONPATH=scripts`.

### 3.3 Основные сценарии использования

* **Запуск worker на downstream-порту**:
  ```bash
  cd scripts/hlstats_py
  poetry run python -m hlstats_py.runtime \
    --configfile ../hlstats.local.conf \
    --port 28000 \
    --foreground
  ```
* **Переиспользование в сервисах**: импортируйте `parse_proxy_envelope`, `parse_log_event`, `EventDispatcher`, `EventStorage`.
* **Ручная валидация**: воспроизведите тестовый поток пакетов для сравнения с Perl-версией:
  ```bash
  cd scripts/hlstats_py
  poetry run pytest tests/test_validation.py -k replay
  ```

### 3.4 Тестирование

Локальный запуск из пакета:
```bash
cd scripts/hlstats_py
poetry run pytest tests
```

### 3.5 DB modes

Python DB connections have two explicit modes:

- **online strict mode** is the default for daemon/worker/maintenance commands.
  It sets UTF-8 connection names but does not clear `SESSION sql_mode`; the
  database server's strict policy remains active.
- **replay/import compatibility mode** is used only when the runtime is launched
  with `--stdin`, by the FTP batch importer, and by replay/comparison tooling.
  This mode sets `SESSION sql_mode = ''` and may enable MySQL multi-statements
  so legacy stdin/import SQL remains reproducible.

Do not enable multi-statements for online services. If a deployment needs
legacy-compatible import semantics, route that workload through the documented
`--stdin`/FTP/replay paths instead of relaxing the online daemon connection.

### 3.6 Lifecycle launcher-ы для deployment

Python runtime-ы можно запускать через shell launcher-ы из `scripts/`:

```bash
cd scripts
./run_proxy_py start
./run_hlstats_py start 1 28000 1
```

Остановка использует production-safe порядок: сначала `SIGTERM`, затем ожидание
до `HLX_STOP_TIMEOUT` секунд, и только после timeout отправляется `SIGKILL`.
Тот же helper очищает stale PID-файлы, если процесс уже завершился или PID-файл
повреждён:

```bash
HLX_STOP_TIMEOUT=15 ./run_proxy_py stop
HLX_STOP_TIMEOUT=15 ./run_hlstats_py stop 28000
```

Для systemd/инициализационных шаблонов вызывайте `stop`/`restart` этих
launcher-ов, а не прямой `kill -9`: Python runtimes обрабатывают `SIGTERM` и
успевают закрыть UDP transport и соединения с БД.

## 4. Скрипт наград hlstats_awards_py (scripts/hlstats_awards_py)

Python-порт `hlstats-awards.pl` отвечает за пересчёт наград, лент, отчётов по кланам и обслуживание архивов.

### 4.1 Расположение и назначение

* **Каталог**: `scripts/hlstats_awards_py`
* **Основные пакеты**: `hlstats_awards_py.cli`, `hlstats_awards_py.calculator.AwardsCalculator`
* **Назначение**: периодическая обработка активных игроков, пересчёт наград и вспомогательные отчёты.

### 4.2 Подготовка окружения

1. Перейдите в каталог пакета и установите зависимости:
   ```bash
   cd scripts/hlstats_awards_py
   poetry install
   ```
2. Активируйте окружение (если требуется):
   ```bash
   poetry shell
   ```
3. Убедитесь, что доступен общий `hlstats.conf` с корректными параметрами подключения к БД.

### 4.3 Основные сценарии запуска

* Получить справку по параметрам:
  ```bash
  poetry run python -m hlstats_awards_py.cli --help
  ```
* Запустить полный цикл обслуживания (inactive + awards + ribbons + prune):
  ```bash
  poetry run python -m hlstats_awards_py.cli --configfile /path/to/hlstats.conf
  ```
* Пересчитать награды и ленты за последние 7 дней:
  ```bash
  poetry run python -m hlstats_awards_py.cli \
    --configfile /path/to/hlstats.conf \
    --awards --ribbons --numdays 7
  ```
* Сформировать отчёт по кланам и гео-IP без записи в таблицы:
  ```bash
  poetry run python -m hlstats_awards_py.cli \
    --configfile /path/to/hlstats.conf \
    --clans --geoip
  ```

Все команды формируют `AwardsReport` и печатают его в stdout для мониторинга.

### 4.4 Тестирование

```bash
poetry run pytest
```
Тесты проверяют приоритет CLI, структуру SQL-запросов и интеграционный прогон полного цикла.

## 5. DNS-резолвер hlstats_resolve_py (scripts/hlstats_resolve_py)

Модуль заменяет `hlstats-resolve.pl`, выполняя DNS-резолвинг и группировку IP-адресов игроков.

### 5.1 Расположение и назначение

* **Каталог**: `scripts/hlstats_resolve_py`
* **Основные пакеты**: `hlstats_resolve_py.cli`, `hlstats_resolve_py.resolver.HostResolver`
* **Назначение**: периодическое обновление таблиц с хостами и географией игроков.

### 5.2 Подготовка окружения

Пакет располагает собственным `scripts/hlstats_resolve_py/pyproject.toml`, однако он хранит только общие настройки Poetry (линтеры, pytest, mypy) и не содержит секции `[tool.poetry]`. Поэтому устанавливать зависимости нужно через общий профиль прокси-демона:
```bash
cd scripts/proxy_daemon_py
poetry shell
```
Активированное окружение предоставляет `mysqlclient` и общие служебные пакеты.
Если вы запускаете модуль из корня репозитория без установки пакета, добавляйте
`PYTHONPATH=scripts`.

### 5.3 Основные сценарии запуска

* Получить список флагов:
  ```bash
  cd ../..
  PYTHONPATH=scripts python -m hlstats_resolve_py.cli --help
  ```
* Запуск из cron в режиме regroup без DNS-запросов:
  ```bash
  cd ../..
  PYTHONPATH=scripts python -m hlstats_resolve_py.cli \
    --configfile /etc/hlstats.conf \
    --regroup
  ```
* Полный прогон с DNS и повышенным логированием:
  ```bash
  cd ../..
  PYTHONPATH=scripts python -m hlstats_resolve_py.cli \
    --configfile /path/to/hlstats.conf \
    --dns-timeout 5 \
    --debug
  ```

Код возврата `0` гарантируется даже при частичных ошибках DNS в режиме `--regroup`, что соответствует поведению Perl-версии.

### 5.4 Тестирование

```bash
cd ../..
PYTHONPATH=scripts python -m pytest scripts/hlstats_resolve_py/tests
```
Набор тестов покрывает парсинг CLI и работу резолвера с подменным DNS-слоем.

## 6. Рекомендованная последовательность для новичка

1. Установите системные зависимости (Python 3.10, Poetry, dev-пакеты MySQL, Docker).
2. Клонируйте репозиторий и скопируйте рабочий `hlstats.conf`.
3. Настройте окружение прокси-демона (`poetry install`, docker-compose, проверка CLI).
4. Запустите e2e-песочницу и убедитесь, что heartbeat отвечает.
5. Поднимите хотя бы один `hlstats_py` worker и добавьте его адрес в `Proxy_Daemons`.
6. Выполните импорт существующих данных демона (`proxy_daemon_py.importer`).
7. Подготовьте пакет `hlstats_py`, прогоните его тесты и реплей-сценарий.
8. Установите и протестируйте `hlstats_awards_py`, затем выполните пробный прогон с тестовой БД.
9. Настройте и протестируйте `hlstats_resolve_py` (ручной запуск + тесты).
10. Перед коммитом запустите все линтеры и тесты в затронутых пакетах.

После прохождения этих шагов у вас будет полностью рабочий Python-пайплайн HLstatsX, готовый к эксплуатации и дальнейшей разработке.

Дополнительно для контейнерного smoke-теста всей цепочки смотрите
`docs/python_fullstack_docker.md`.

## 7. Batch-генерация heatmaps

Python-порт heatmaps теперь доступен как отдельный batch CLI, повторяющий
legacy-модель запуска без встраивания в `hlstats_py.runtime`:

```bash
cd scripts/hlstats_py
poetry run python -m hlstats_py.heatmaps \
  --configfile ../hlstats.conf \
  --web-root ../web \
  --heatmaps-root ../heatmaps
```

Что важно для эксплуатации:

- Генератор читает `hlstats_Heatmap_Config` и `hlstats_Games` из общей MySQL.
- Исходные карты по-прежнему ожидаются в legacy-layout:
  `heatmaps/src/<realgame>/<map>.jpg`.
- Готовые артефакты публикуются туда же, куда их ждёт PHP web:
  `web/hlstatsimg/games/<code>/heatmaps/<map>-kill.jpg` и
  `<map>-kill-thumb.jpg`.
- Overlay-cache сохраняется в `heatmaps/cache/<code>`.
- Поддерживаются legacy-флаги `--game`, `--map`, `--disablecache`,
  `--ignoreinfected`.
- Для быстрой проверки проекции без регенерации JPEG используйте
  `--diagnose-projection`; он считает queried/in-bounds/out-of-bounds,
  raw/transformed bounds и текущие `hlstats_Heatmap_Config` значения.

Пример точечного запуска для одной карты:

```bash
cd scripts/hlstats_py
poetry run python -m hlstats_py.heatmaps \
  --configfile ../hlstats.conf \
  --web-root ../web \
  --heatmaps-root ../heatmaps \
  --game cstrike \
  --map de_dust2 \
  --disablecache
```

### 7.1. Проекция карт и overview-файлы

Координаты `hlstats_Events_Frags.pos_x/pos_y` и
`pos_victim_x/pos_victim_y` приходят из игровых логов как world-координаты.
Для отображения на raster overview они переводятся через
`hlstats_Heatmap_Config`: `xoffset`, `yoffset`, `scale`, `flipx`, `flipy`,
`rotate`.

Правильный источник стартовой сетки:

- GoldSrc / CS 1.6: `cstrike/overviews/<map>.txt` с `ZOOM`, `ORIGIN`,
  `ROTATED`, `IMAGE`, `HEIGHT`.
- Source / CS:S / CS:GO: `resource/overviews/<map>.txt` с `pos_x`, `pos_y`,
  `scale`, `rotate`, `material`.

Эти файлы являются seed для калибровки. Они не гарантируют идеального
попадания, если текущий web JPEG отличается от radar BMP/material по размеру,
crop или версии карты. Для кастомных карт без overview-файла автоматическая
калибровка невозможна: нужен импорт overview-файла или ручная подгонка.

Локальный DB-first helper:

```bash
cd scripts
python heatmap_projection_calibrate.py \
  --configfile hlstats.conf \
  --game cstrike \
  --map de_dust2 \
  --heatmaps-root ../heatmaps \
  --overview-file path/to/cstrike/overviews/de_dust2.txt
```

Helper генерирует HTML preview со слайдерами и может применить значения в
`hlstats_Heatmap_Config` только после прохождения заданного порога
in-bounds-ratio и отдельного runtime-gate через
`--apply --runtime-gate-approved`. Итерации по калибровке нужно делать на уже
заполненной DB; full log replay и `--disablecache` регенерацию стоит запускать
только после стабилизации проекции.

### 7.2. Web overlay и персональные heatmaps

Статические `<map>-kill.jpg` / `<map>-kill-thumb.jpg` остаются legacy fallback,
но основной видимый слой в web теперь строится через локальный canvas overlay:

- `mode=mapinfo&game=<code>&map=<map>` показывает глобальную теплокарту поверх
  изображения карты и оставляет старую thumbnail/lightbox ссылку.
- `web/heatmap_points.php?game=<code>&map=<map>` возвращает JSON-точки,
  image metadata, projection, config hash, renderer settings, cache status и
  diagnostics. По умолчанию используется thermal renderer с `sqrt`
  нормализацией.
- `web/heatmap_points.php?game=<code>&map=<map>&player=<id>&event=kills`
  возвращает точки убийств конкретного игрока.
- `event=deaths` показывает места смерти игрока по victim-координатам.
- `event=both` возвращает оба канала в одном payload; player widget включает
  semantic renderer для раздельных warm/cool каналов.
- `mode=admin&task=heatmaps&game=<code>` открывает мастер настройки карт:
  загрузка JPG/overview, live preview без записи, сохранение
  `hlstats_Heatmap_Config`, invalidation payload cache и web-trigger для
  `python -m hlstats_py.heatmaps --disablecache`.

В карточке игрока персональный виджет находится во вкладке Maps & Servers.
Селект карт строится только из карт, где у игрока есть события и для карты
существуют heatmap config плюс изображение. Основной renderer использует
тепловизорную палитру blue/cyan/yellow/orange/red с alpha channel; semantic
mode сохраняет warm/cool split для сравнения убийств и смертей. Tooltip по
ближайшей точке показывает количество событий, раздельные `Kills`/`Deaths`,
top killers, top victims и involved players.

Открытое ограничение: реальная parity-проверка legacy PHP vs Python на
production map-pack картах требует установленного набора
`heatmaps/src/<game>/<map>.jpg`, который в репозиторий не входит.
