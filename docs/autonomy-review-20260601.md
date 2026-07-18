# Актуализированная оценка ревью `experiment/parity-trace-harness`

Завершённый исторический обзор.

Этот файл нужен как rationale для уже выполненного autonomy/release-readiness
цикла. Для текущего состояния продукта используйте `docs/status.md`,
`docs/plans.md` и `docs/release-readiness.md`.

## Краткий вывод

Изначальное ревью было полезно как архитектурный обзор, но в текущем виде оно
смешивает:

- реальные актуальные проблемы;
- уже закрытые или частично закрытые темы;
- устаревшие фрагменты внутренних docs.

Из-за этого исходный `goal_plan.md` стартовал с неверного приоритета:
исправления `DB reconnect bug`, который в текущем состоянии ветки уже не
подтверждается кодом.

## Что подтверждено по коду и актуально

### 1. Python product contour еще не автономен

Это подтверждается напрямую:

- `hlstats_py` импортирует код из `proxy_daemon_py`;
- `hlstats_py` не декларирует явную runtime-зависимость на этот общий код;
- запуск `hlstats_py` до сих пор держится на ручном `PYTHONPATH`.

Практический вывод:
главный технический долг здесь не в parity-логике, а в packaging/runtime
boundary между `hlstats_py` и `proxy_daemon_py`.

### 2. CI покрывает только часть продукта

Сейчас в `.github/workflows/` есть только workflow для `proxy_daemon_py`.
Это не соответствует фактическому validation contract проекта, где ожидаются
проверки еще для:

- `hlstats_py`;
- `replay_baseline`;
- PHP lint;
- хотя бы минимального EN/RU smoke.

Практический вывод:
самый очевидный текущий gap для release-readiness — это repository-wide quality
gate, а не low-level runtime bugfix.

### 3. Lifecycle scripts все еще грубые

`scripts/run_hlstats_py` и `scripts/run_proxy_py` по-прежнему используют PID
files и немедленный `kill -9`.

Практический вывод:
это отдельный актуальный ops-hardening трек, но он должен идти как lifecycle
improvement, а не как parity task.

### 4. Control plane стоит ужесточить

Проблема есть, но она уже не такая, как была сформулирована в исходном ревью.

Актуальная формулировка:

- read-only и mutating control commands все еще слишком близко;
- loopback-команды имеют более слабую модель защиты;
- нужно отдельно рассматривать:
  - `hlstats_py`: `HEARTBEAT`, `SERVERLIST`, `RELOAD`, `KILL`;
  - `proxy_daemon_py`: `HEARTBEAT`, `SERVERLIST`, `RELOAD`.

Практический вывод:
это не “полностью открытый неаутентифицированный UDP admin API”, а точечный
hardening control surface.

### 5. Внутренние docs рассинхронизированы

Это сейчас одна из самых реальных проблем для планирования.

По `docs/status.md`, `docs/plans.md` и `docs/test-plan.md` одновременно видно:

- закрытые parity residuals;
- исторические “Next” и “Current working rules”, которые уже устарели;
- противоречивую формулировку по GeoIP residual / post-replay GeoIP backfill;
- stale parity gates в `test-plan.md`.

Практический вывод:
до любого большого автономизационного плана нужно сначала зафиксировать
каноническое текущее состояние.

## Что в исходном ревью устарело или неверно

### 1. `DB reconnect bug` как активный кодовый дефект

Это больше не подтверждается текущим кодом.

`_ensure_connection()` уже реализован в корректной логике:

- если connection нет, он создается;
- при `skip_connection_ping` возвращается текущий connection;
- при failed ping выполняется reconnect.

Следствие:
в плане не нужен task “исправить `_ensure_connection()`”.
Нужен только task “добавить/усилить regression tests, чтобы это поведение не
сломалось снова”.

### 2. Утверждение, что `proxy_daemon_py` обрабатывает `KILL`

Это не подтверждается текущим кодом.
Для `proxy_daemon_py` актуальны `HEARTBEAT`, `SERVERLIST`, `RELOAD`.

Следствие:
control-plane hardening надо планировать по реальной поверхности, а не по
гипотетической.

### 3. Утверждение, что `KILL` в `hlstats_py` делает неграциозную остановку

Тоже устарело.
`KILL` в runtime вызывает shutdown path с flush перед остановкой.

Следствие:
отдельно надо чинить shell wrappers, а не считать сам runtime shutdown
сломанным.

### 4. Утверждение, что все control commands полностью неаутентифицированы

Это слишком широкая формулировка.
Для non-local трафика уже есть envelope/proxy-key validation.

Следствие:
проблема не в полном отсутствии защиты, а в недостаточном разделении режимов и
в более слабом loopback/control surface.

## Каноническая интерпретация текущего состояния

Для обновления плана работ стоит принять такую базовую картину:

- ветка действительно является product lane, а не просто экспериментальной;
- parity по поддерживаемому узкому/default Python contour в основном уже
  закрыта;
- главные открытые темы сейчас не “ловить очередной parity bug”, а:
  - синхронизировать docs;
  - расширить CI;
  - убрать packaging coupling;
  - ужесточить ops/control surface;
  - затем переводить parity/replay discipline в более автономный acceptance
    flow.

Отдельно нужно оставить явную оговорку:
GeoIP narrative в docs сейчас противоречив, и перед release-readiness
формулировкой надо явно решить, считается ли “clean parity” до или после
обязательного post-replay GeoIP backfill.

## Что должно перейти в актуальный план работ

### Высокий приоритет

- синхронизация `docs/status.md`, `docs/plans.md`, `docs/test-plan.md`;
- repository-wide CI;
- regression tests для текущей reconnect логики;
- decoupling `hlstats_py -> proxy_daemon_py`;
- removal of manual `PYTHONPATH`.

### Средний приоритет

- graceful lifecycle для `run_proxy_py` и `run_hlstats_py`;
- control-plane hardening:
  - разделение read-only и mutating commands;
  - отдельное ужесточение для `hlstats_py RELOAD/KILL`;
  - отдельное ужесточение для `proxy_daemon_py RELOAD`;
- явное разделение online vs replay/import DB modes;
- перевод parity acceptance в PR/nightly automation.

### После стабилизации

- PHP request/i18n/cache stabilization;
- replay-backed EN/RU smoke;
- metrics, profiling, benchmark harness;
- release packaging / release checklist / deployment docs.

## Итог

Исходное ревью не надо выбрасывать: оно правильно указывает на направление
автономизации ветки. Но его нужно читать как черновой architectural review,
а не как точный текущий bug list.

Для практической работы правильная последовательность сейчас такая:

1. Сначала выровнять docs и validation contract.
2. Затем расширить CI.
3. Затем убрать packaging coupling.
4. Затем закрыть ops/control hardening.
5. Затем автоматизировать parity acceptance и release-readiness.

Именно в таком виде выводы ревью становятся пригодными для рабочего плана.
