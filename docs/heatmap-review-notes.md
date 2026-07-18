# Heatmap: заметки по ревизии (review notes)

Дата обзора: 2026-07-16
Охват: Python-генератор, калибратор, PHP-API, фронтенд, тесты.
Цель заметок: передать другому агенту для независимой проверки и подтверждения
каждого пункта (`подтверждено` / `не воспроизводится` / `ожидает фикса`).

Контекст: тепловые карты — единственный активный функциональный трек ветки
`feature/heatmap-projection-calibration`. Статус: DB-backed canvas-оверлей в
`mapinfo`, player-scoped виджет в `playerinfo`, hover-метаданные, отдельные
warm/cool каналы для kills/deaths, статический JPEG — fallback.

## Что проверялось

- `scripts/hlstats_py/heatmaps.py` — генератор и диагностика
- `scripts/heatmap_projection_calibrate.py` — калибратор/apply
- `web/includes/heatmap_points.php` — PHP-API логика (payload, transform, fetch)
- `web/heatmap_points.php`, `web/heatmap_admin.php`, `web/heatmap_map.php` — эндпоинты
- `web/includes/js/heatmap.js` — фронт (отрисовка, калибровка, drag/rotate/resize)
- `web/pages/admintasks/heatmaps.php` — админка
- `scripts/hlstats_py/tests/test_heatmaps.py` — покрытие

## Найденные проблемы

### ВЫСОКИЙ приоритет

**H1. Деление на ноль / отрицательный `scale` в Python-генераторе — FIXED**
- Место: `scripts/hlstats_py/heatmaps.py:1026-1027` (`transform_point`),
  также парсинг в `fetch_map_configs` (`heatmaps.py:289`).
- Результат: Python normalizes non-positive/non-finite values to `1.0` at
  config-load and transform boundaries; PHP applies the same rule. The
  calibration CLI rejects invalid scale overrides before any apply, and its
  interactive preview normalizes invalid values. Regression coverage is in
  `test_heatmaps.py`, `test_heatmap_projection_calibrate.py`, and the PHP/GD
  smoke.

**H2. Cache-reuse игнорирует окно `days`**
- Место: `scripts/hlstats_py/heatmaps.py:820-822` (`build_points_query`),
  `:844`, `:868`, `resolve_cache_entry` `:900-913`.
- Суть: при переиспользовании кэша запрос переключается на
  `eventTime > cache_timestamp` и теряет нижнюю границу
  `timescope = now - days*86400`. Константа `LEGACY_CACHE_MAX_AGE_DAYS = 30`.
  Если `days < 30` и кэш старше `timescope`, но моложе 30 дней, в инкрементальный
  оверлей попадают точки старше окна удержания.
- Ожидание: считать кэш невалидным, когда `cache_timestamp < timescope`
  (регенерировать с нуля).

### СРЕДНИЙ приоритет

**M1. Смерти рисуются в позиции киллера**
- Место: `web/includes/heatmap_points.php:603-608`.
- Суть: для `deaths` координата `COALESCE(hef.pos_victim_x, hef.pos_x)`. Если у
  жертвы нет координат, точка смерти попадает в позицию убийцы.
- Ожидание: пропускать строку, если victim-координаты null.

**M2. Хрупкий route `regenerate`**
- Место: `web/heatmap_admin.php:228-242`.
- Суть: жёстко зашит `scripts/hlstats.conf`, `python`/`python3`, нет
  `--debug-level`/размера вывода; при падении генератора возвращает 500, но
  старый JPEG остаётся. `--game` должен быть `code`, а не `realgame` (конфликт,
  если code≠realgame).
- Ожидание: брать путь конфига из окружения/контракта, пробрасывать
  `--debug-level`, очищать старые артефакты при неудаче.

**M3. Статический генератор не умеет deaths/both**
- Место: `scripts/hlstats_py/heatmaps.py:811-872` (`build_points_query` только
  frags+teamkills как kills), `web/heatmap_admin.php:219-268` (regenerate только
  kills-JPEG).
- Суть: веб-оверлей поддерживает kills/deaths/both, а кнопка «regenerate»
  пересоберёт только kills-JPEG. Покрытие regenerate расходится с вебом.
- Ожидание: расширить генератор ИЛИ задокументировать, что статический JPEG —
  только kills (legacy-совместимо).

### НИЗКИЙ приоритет (косметика / robustness)

**L1. HUD-дата захардкожена на 30 дней**
- Место: `scripts/hlstats_py/heatmaps.py:1174` — использует `60*60*24*30`
  вместо `config.days`.

**L2. Дрейф точности слайдера scale в админке**
- Место: `web/pages/admintasks/heatmaps.php:59` + `web/includes/js/heatmap.js`
  `sliderToScale`/`scaleToSlider` с `step=1`. Ручное значение вроде 1.26 после
  движения слайдера округляется (~1.16).

**L3. `manualRequired` срабатывает при сбое метаданных картинки**
- Место: `web/includes/heatmap_points.php:348, 420`. Если `width<=0`, все точки
  out-of-bounds и `manualRequired=true`, хотя причина — не проекция, а картинка.

**L4. Лейбл rotate-кнопки**
- Место: `web/includes/js/heatmap.js:637-638` — всегда `is-active` после первого
  поворота.

## Проверено как НЕ баги

- Rotate-компенсация в `heatmap.js` (`rotateCoordinate`/`unrotateCoordinate`)
  самосогласована: четыре одинаковых quarter-turn возвращают точку, а
  `unrotate(rotate(point))` возвращает исходную точку. Шаги 1/2/3 не являются
  инволюциями по отдельности; их обратные матрицы — шаги 3/2/1.
- PHP `heatmap_transform_point` (`heatmap_points.php:238-271`) и Python
  `transform_point` дают одинаковый результат, включая вычитание crop и
  quarter-turn ротации.
- `pos_victim_x` / `pos_victim_y` реально присутствуют в схеме БД (подтверждено
  по parity-дампам), запрос в `heatmap_fetch_rows` валиден.
- Кеш-ключ PHP (`heatmap_points.php:57-64`) корректно включает `configHash`
  (проекция + days + brush + imageMtime) и scope/renderer/normalization.

## Пробелы в тестах

`scripts/hlstats_py/tests/test_heatmaps.py` покрывает transform / stats /
overview-парсинг / генератор / sparse-visibility, а отдельные тесты покрывают:
- guard `scale=0` и отрицательный scale (H1);
- поведение cache-reuse относительно `days` (H2);
- victim-fetch и COALESCE-поведение (M1);
- путь `regenerate` (M2).

## Рекомендованные правки (если подтверждается)

- A. Защита `scale` в `transform_point`/`fetch_map_configs` + тест — выполнено.
- B. Инвалидация кэша при `cache_timestamp < timescope` + тест на два прогона
  с `days` меньше возраста кэша.
- C. В `heatmap_fetch_rows` не делать COALESCE на killer-позицию для deaths.
- D. Устойчивость route `regenerate` (конфиг из окружения, `--debug-level`,
  очистка артефактов при неудаче).
- E. HUD-дата → `config.days`; уточнить `manualRequired` (не триггерить на
  отсутствии картинки).
- F. (опц.) deaths/both в статическом генераторе или документация.
- G. Мелочи: слайдер scale (step), лейбл rotate.

## Верификация после правок

- `pytest scripts/hlstats_py/tests/test_heatmaps.py`
- `php -l web/heatmap_points.php web/heatmap_admin.php web/heatmap_map.php`
- `php scripts/web_heatmap_smoke.php`
- Проверка `--scale 0`, отрицательного и `NaN` значений через CLI-тесты;
  runtime `--apply --runtime-gate-approved` остаётся отдельным gate и не
  выполняется автоматически.
