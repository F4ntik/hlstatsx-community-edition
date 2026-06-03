# Пошаговое руководство по запуску Python proxy-daemon

Документ предназначен для сотрудников, которые ранее работали с Perl-версией
`proxy-daemon.pl` и теперь переходят на Python-реализацию. Ниже приведён полный
маршрут: от подготовки окружения до запуска демона и проверки его работы.

## 1. Что изменилось после миграции

- Python-реализация хранится в каталоге
  `scripts/proxy_daemon_py` и повторяет архитектуру исходного скрипта, но
  использует асинхронные компоненты и отдельные модули для баланcировщика,
  работы с БД и логирования.【F:scripts/proxy_daemon_py/daemon.py†L1-L106】【F:scripts/proxy_daemon_py/bootstrap.py†L1-L76】
- Downstream-часть статистики теперь запускается отдельным Python worker из
  `scripts/hlstats_py`, который слушает UDP от proxy daemon и пишет события в
  существующую MySQL-схему.
- Интерфейс командной строки оставляет те же параметры `--configfile`, `--debug`
  и `--foreground`, что и Perl-скрипт, поэтому существующие ansible-плейбуки и
  сервисные юниты можно адаптировать с минимальными правками.【F:scripts/proxy_daemon_py/cli.py†L19-L66】
- Конфигурационный файл `hlstats.conf` читается тем же форматом «ключ значение»,
  включая поддержку кавычек и нераспознанных параметров, благодаря
  `ProxyConfig`. Это позволяет повторно использовать текущие файлы
  конфигурации.【F:scripts/proxy_daemon_py/config.py†L12-L100】

## 2. Требования к окружению

1. **Python 3.10+** (проект тестировался на 3.10). Проверьте установку:
   ```bash
   python3 --version
   ```
2. **Poetry** для управления зависимостями.
   - Linux/macOS: `curl -sSL https://install.python-poetry.org | python3 -`
   - Windows (PowerShell): `(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -`
3. **Компилятор и заголовки MySQL** – библиотека `mysqlclient` требует системные
   зависимости. Для Debian/Ubuntu:
   ```bash
   sudo apt update
   sudo apt install build-essential python3-dev default-libmysqlclient-dev
   ```
   Для RHEL/CentOS используйте `gcc`, `python3-devel` и `mariadb-connector-c-devel`.
4. **Docker + Docker Compose** (для локальных стендов и песочниц).
5. Доступ к корпоративному репозиторию HLstatsX Community Edition.

## 3. Клонирование репозитория

```bash
git clone git@github.com:<ваша-организация>/hlstatsx-community-edition.git
cd hlstatsx-community-edition
```

## 4. Установка Python-зависимостей

1. Перейдите в каталог Python-демона:
   ```bash
   cd scripts/proxy_daemon_py
   ```
2. Создайте виртуальное окружение и установите зависимости:
   ```bash
   poetry install
   ```
   Команда скачает рантайм-зависимости (`mysqlclient`) и инструменты разработчика
   (`pytest`, `ruff`, `black`, `mypy`).【F:scripts/proxy_daemon_py/pyproject.toml†L1-L35】
3. Активируйте окружение для текущего shell (опционально):
   ```bash
   poetry shell
   ```
4. Убедитесь, что CLI доступен и возвращает подсказку по параметрам:
   ```bash
   poetry run python -m proxy_daemon_py.cli --help
   ```

## 5. Подготовка `hlstats.conf`

1. Скопируйте пример из корня репозитория:
   ```bash
   cp ../hlstats.conf ./hlstats.local.conf
   ```
2. Отредактируйте значения ключей:
   - `DBHost` – адрес MySQL. Для Docker-песочницы используйте `127.0.0.1:33060`
     (или `33070` для e2e-стека, см. ниже).
   - `DBUsername` / `DBPassword` – учётные данные базы.
   - `DBName` – имя схемы (по умолчанию `hlstatsx_proxy`).
   - `BindIP` и `Port` – адрес, где демон будет слушать входящие UDP-пакеты.
   - `DebugLevel` – уровень логирования (0 – только балансировка, 1 – контроль,
     ≥2 – все уведомления).【F:scripts/proxy_daemon_py/config.py†L53-L100】
3. Проверьте синтаксис:
   ```bash
   poetry run python -m proxy_daemon_py.cli --configfile hlstats.local.conf --foreground
   ```
   Если файл доступен и валиден, команда завершится кодом `0`.

## 6. Подготовка MySQL

### 6.1 Минимальный стенд с одной MySQL

1. В каталоге `scripts/proxy_daemon_py` запустите контейнер:
   ```bash
   docker compose up -d
   ```
   Compose-файл создаст БД с пользователем `hlstats`/`hlstats` и автоматически
   прогонит SQL-скрипты из `sql/` (схема и обязательные записи).【F:scripts/proxy_daemon_py/docker-compose.yml†L1-L17】
2. Проверьте доступность:
   ```bash
   mysql -h 127.0.0.1 -P 33060 -u hlstats -p
   ```

### 6.2 E2E песочница с моками

Для проверки всей цепочки с тестовыми downstream-демонами используйте сборку из
`e2e/`:

```bash
cd scripts/proxy_daemon_py/e2e
./start.sh
```

- Стартуют сервисы: MySQL (`localhost:33070`), Python daemon, два мок-демона для
  ответа на Heartbeat и проксируемые пакеты.【F:scripts/proxy_daemon_py/e2e/docker-compose.yml†L1-L44】
- Конфигурация `hlstats.conf` лежит рядом; при необходимости скорректируйте
  параметры подключения.
- Логи: `docker compose logs -f proxy-daemon`.
- Остановка: `./stop.sh`.
- Скрипты `start.sh`/`stop.sh` рассчитаны на Bash. На Windows запустите их через
  WSL или Git Bash; при использовании только PowerShell выполните `docker compose`
  из этого каталога вручную (`docker compose up -d`, затем `docker compose down`).

## 7. Импорт текущих распределений (опционально)

Перед переключением с Perl полезно проверить, как Python-демон прочитает текущую
схему БД. Для этого существует CLI-утилита `importer`:

```bash
poetry run python -m proxy_daemon_py.importer \
  --configfile hlstats.local.conf
```

Скрипт подключится к MySQL, прочитает таблицы `Proxy_Daemons`, `Proxy_Daemon_Status`
и `hlstats_Servers`, соберёт балансировщик и выдаст список активных демонов и
назначений серверов.【F:scripts/proxy_daemon_py/importer.py†L1-L123】 Используйте
отчёт, чтобы сравнить результаты с Perl-версией до переключения.

## 8. Запуск Python proxy-daemon

### 8.1 Локальный запуск в foreground

1. Убедитесь, что MySQL доступен и `hlstats.conf` указывает на верные параметры.
2. Запустите демон с теми же флагами, что использовались для Perl-скрипта:
   ```bash
   poetry run python -m proxy_daemon_py.runtime \
     --configfile ../hlstats.local.conf \
     --foreground
   ```
   В логе появится сообщение вида «`Proxy daemon listening on <ip>:<port>`»,
   подтверждающее успешный старт.【F:scripts/proxy_daemon_py/daemon.py†L34-L74】
3. Остановить процесс можно `Ctrl+C` — обработчик сигналов корректно закроет UDP
   сокет, heartbeat и соединение с MySQL.

## 8.1 Запуск downstream statistics worker

После старта proxy daemon поднимите минимум один downstream worker:

```bash
cd scripts/proxy_daemon_py
PYTHONPATH=.. poetry run python -m hlstats_py.runtime \
  --configfile ../hlstats.local.conf \
  --port 28000 \
  --foreground
```

Затем добавьте адрес worker в `hlstats_Options.Proxy_Daemons`, например
`127.0.0.1:28000`, и отправьте proxy daemon команду `RELOAD`.

### 8.2 Проверка heartbeat и проксирования

- Каждые 30 секунд демон опрашивает downstream-демоны и обновляет состояние в
  памяти. Команда `C;SERVERLIST;` отвечает списком серверов. В песочнице можно
  послать UDP-пакет через `netcat`:
  ```bash
  printf 'C;HEARTBEAT;' | nc -u -w1 127.0.0.1 27500
  ```
- При некорректном `ProxyKey` клиент получит `FAILED PROXY REQUEST`, а в логах
  появится запись уровня `E403`.

## 9. Проверка качества перед коммитом

Из каталога `scripts/proxy_daemon_py` выполните:

```bash
poetry run ruff check .
poetry run black --check .
poetry run mypy .
poetry run pytest
```

Набор инструментов совпадает с CI-пайплайном и гарантирует, что изменения
соответствуют стилю и не ломают тесты.【F:scripts/proxy_daemon_py/README.md†L33-L49】

## 10. Типичные проблемы и решения

| Симптом | Решение |
| --- | --- |
| `mysqlclient` не компилируется | Проверьте, что установлены dev-пакеты MySQL (см. раздел 2). |
| `error: Cannot parse configuration line ...` | В `hlstats.conf` лишние пробелы в начале строки или пропущен ключ. Формат — `Key "Value"`. |
| `FAILED PROXY REQUEST` в UDP-ответе | Проверьте поле `ProxyKey` в таблице `Proxy_Daemons` и соответствие конфигурации. |
| Демон не видит downstream-узлы | Убедитесь, что таблица `Proxy_Daemons` заполнена и доступна по сети; при необходимости перезапустите `importer` для диагностики. |

## 11. Дополнительные материалы

- [План миграции на Python](proxy_daemon_python_migration.md)
- [Стенд для e2e-тестов](proxy_daemon_e2e_sandbox.md)
- [Операционный регламент](proxy_daemon_py_operational_runbook.md)

Следуйте этому чек-листу при обучении новых сотрудников и актуализации
инфраструктурных плейбуков.
