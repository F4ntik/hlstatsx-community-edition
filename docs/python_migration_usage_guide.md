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

| Модуль | Назначение | Каталог |
| --- | --- | --- |
| `proxy_daemon_py` | UDP-прокси между игровыми серверами и статистикой | `scripts/proxy_daemon_py` |
| `hlstats_py` | Парсер UDP-пакетов, нормализация событий и запись в БД | `scripts/hlstats_py` |
| `hlstats_awards_py` | Обслуживание наград, лент и архивов БД | `scripts/hlstats_awards_py` |
| `hlstats_resolve_py` | DNS-резолвер IP-адресов игроков и группировка хостов | `scripts/hlstats_resolve_py` |

### 1.3 Базовое конфигурирование

Python-утилиты используют общий формат `hlstats.conf`. Скопируйте рабочий конфиг в корень репозитория (или создайте `hlstats.local.conf` рядом с нужным модулем) и заполните ключи `DBHost`, `DBName`, `DBUsername`, `DBPassword`, `ProxyKey`, `BindIP`, `Port`, `DebugLevel`. Если запускаете стенд из репозитория, достаточно примерного файла `scripts/hlstats.conf` с корректировкой параметров подключения.

## 2. Proxy Daemon (scripts/proxy_daemon_py)

Python-порт прокси-демона — основной сервис, принимающий UDP-пакеты и управляющий балансировкой downstream-демонов.

### 2.1 Расположение и назначение

* **Каталог**: `scripts/proxy_daemon_py`
* **Основные пакеты**: `proxy_daemon_py.cli`, `proxy_daemon_py.e2e.run_proxy_daemon`, `proxy_daemon_py.importer`
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
* **Конфиг**: убедитесь, что рядом доступен `hlstats.conf` (или `hlstats.local.conf`) с заполненными параметрами `DBHost`, `DBName`, `DBUsername`, `DBPassword`, `ProxyKey`, `BindIP`, `Port`, `DebugLevel`.
* **Верификация**: проверьте конфигурацию, не запуская рабочие процессы:
  ```bash
  poetry run python -m proxy_daemon_py.cli --configfile hlstats.local.conf --foreground
  ```

### 2.4 Основные сценарии запуска

1. Подготовьте MySQL и заполните таблицы `Proxy_Daemons` и `hlstats_Servers` (скрипты из каталога `sql/` или выгрузка из продакшена).
2. Запустите сервис в переднем плане для отладки:
   ```bash
   poetry run python -m proxy_daemon_py.e2e.run_proxy_daemon \
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

## 3. Модуль обработки событий hlstats_py (scripts/hlstats_py)

Пакет отвечает за разбор UDP-событий, нормализацию данных и запись в БД. Его импортируют все остальные модули.

### 3.1 Расположение и назначение

* **Каталог**: `scripts/hlstats_py`
* **Основные пакеты**: `hlstats_py.events`, `hlstats_py.dispatcher`, `hlstats_py.storage`
* **Назначение**: приём событий от прокси-демона, построение внутренних моделей и применение SQL-операций.

### 3.2 Подготовка окружения

`hlstats_py` использует окружение прокси-демона. Повторно активируйте его при необходимости:
```bash
cd scripts/proxy_daemon_py
poetry shell
```
После активации можно вернуться в корень (`cd ../..`) или оставаться в каталоге прокси, добавляя `PYTHONPATH=..` к командам.

### 3.3 Основные сценарии использования

* **Переиспользование в сервисах**: импортируйте `parse_proxy_envelope`, `parse_log_event`, `EventDispatcher`, `EventStorage`.
* **Ручная валидация**: воспроизведите тестовый поток пакетов для сравнения с Perl-версией:
  ```bash
  cd scripts/proxy_daemon_py
  PYTHONPATH=.. poetry run pytest ../hlstats_py/tests/test_validation.py -k replay
  ```

### 3.4 Тестирование

Все автотесты требуют наличия каталога `scripts/` в `PYTHONPATH`:
```bash
cd scripts/proxy_daemon_py
PYTHONPATH=.. poetry run pytest ../hlstats_py/tests
```

## 4. Скрипт наград hlstats_awards_py (scripts/hlstats_awards_py)

Python-порт `hlstats-awards.pl` отвечает за пересчёт наград, лент, отчётов по кланам и обслуживание архивов.

### 4.1 Расположение и назначение

* **Каталог**: `scripts/hlstats_awards_py`
* **Основные пакеты**: `hlstats_awards_py.cli`, `hlstats_awards_py.jobs`
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
* **Основные пакеты**: `hlstats_resolve_py.cli`, `hlstats_resolve_py.worker`
* **Назначение**: периодическое обновление таблиц с хостами и географией игроков.

### 5.2 Подготовка окружения

Пакет не содержит собственного `pyproject.toml`, поэтому используйте окружение прокси-демона:
```bash
cd scripts/proxy_daemon_py
poetry shell
```
Если вы не активируете shell, добавляйте `PYTHONPATH=..` к командам `poetry run`.

### 5.3 Основные сценарии запуска

* Получить список флагов:
  ```bash
  cd scripts/proxy_daemon_py
  PYTHONPATH=.. poetry run python -m hlstats_resolve_py.cli --help
  ```
* Запуск из cron в режиме regroup без DNS-запросов:
  ```bash
  cd scripts/proxy_daemon_py
  PYTHONPATH=.. poetry run python -m hlstats_resolve_py.cli \
    --configfile /etc/hlstats.conf \
    --regroup
  ```
* Полный прогон с DNS и повышенным логированием:
  ```bash
  cd scripts/proxy_daemon_py
  PYTHONPATH=.. poetry run python -m hlstats_resolve_py.cli \
    --configfile /path/to/hlstats.conf \
    --dns-timeout 5 \
    --debug
  ```

Код возврата `0` гарантируется даже при частичных ошибках DNS в режиме `--regroup`, что соответствует поведению Perl-версии.

### 5.4 Тестирование

```bash
cd scripts/proxy_daemon_py
PYTHONPATH=.. poetry run pytest ../hlstats_resolve_py/tests
```
Набор тестов покрывает парсинг CLI и работу резолвера с подменным DNS-слоем.

## 6. Рекомендованная последовательность для новичка

1. Установите системные зависимости (Python 3.10, Poetry, dev-пакеты MySQL, Docker).
2. Клонируйте репозиторий и скопируйте рабочий `hlstats.conf`.
3. Настройте окружение прокси-демона (`poetry install`, docker-compose, проверка CLI).
4. Запустите e2e-песочницу и убедитесь, что heartbeat отвечает.
5. Выполните импорт существующих данных демона (`proxy_daemon_py.importer`).
6. Подготовьте пакет `hlstats_py`, прогоните его тесты и реплей-сценарий.
7. Установите и протестируйте `hlstats_awards_py`, затем выполните пробный прогон с тестовой БД.
8. Настройте и протестируйте `hlstats_resolve_py` (ручной запуск + тесты).
9. Перед коммитом запустите все линтеры и тесты в затронутых пакетах.

После прохождения этих шагов у вас будет полностью рабочий Python-пайплайн HLstatsX, готовый к эксплуатации и дальнейшей разработке.
