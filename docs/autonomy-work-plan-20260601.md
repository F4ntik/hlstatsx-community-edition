# Актуальный план работ по итогам ревью

Завершённый исторический план.

Фазы этого документа закрыты и сохранены как audit trail. Для текущего
исполнения используйте `docs/status.md`, `docs/plans.md`,
`docs/test-plan.md` и `docs/release-readiness.md`.

## Цель

Довести ветку `experiment/parity-trace-harness` до состояния, где:

- Python runtime, replay tooling, PHP web и CI работают как один продуктовый
  контур;
- release-readiness подтверждается воспроизводимыми проверками;
- зависимость от legacy Perl сведена к reference/acceptance layer, а не к
  повседневной опоре разработки;
- work plan опирается на текущее состояние кода, а не на устаревшие пункты из
  старого review.

## Каноническое текущее состояние

Пока `docs/status.md`, `docs/plans.md` и `docs/test-plan.md` не
синхронизированы, при планировании считать источником истины:

- сначала `hlstatsx-community-edition-python-i18n/docs/status.md`
  как наиболее свежую evidence-based сводку;
- затем код и тесты;
- затем `docs/plans.md`;
- `docs/test-plan.md` использовать как verification matrix, но не как
  authoritative parity status без перепроверки.

Принятые факты:

- `DB reconnect bug` как активный кодовый дефект не подтверждается;
- parity narrative в docs частично устарела;
- `hlstats_py` все еще связан с `proxy_daemon_py`;
- CI все еще не покрывает весь product contour;
- shell lifecycle и control plane остаются актуальными hardening-темами.

## Главные принципы

- Не ломать parity ради красивой архитектуры.
- Не начинать с уже закрытых проблем.
- Сначала чинить качество контракта разработки:
  - docs truth;
  - CI gates;
  - package boundaries.
- Большие рефакторы делать только после того, как есть узкие проверяемые
  validation loops.
- Для parity-affecting изменений опираться на legacy-first read-only analysis и
  на уже существующую replay discipline проекта.

## Что исключено из актуального плана

Следующие пункты не должны оставаться как активные стартовые задачи:

- “исправить `_ensure_connection()`”;
- “чинить `proxy_daemon_py KILL` path”;
- “считать `hlstats_py KILL` неграциозным runtime shutdown bug”;
- “трактовать всю parity область как активный bug hunt”.

Их заменяет более точная постановка:

- удержать текущую reconnect логику тестами;
- ужесточить только реальную control surface;
- синхронизировать docs и validation contract;
- сместить фокус на product autonomy и release-readiness.

## Фаза 0. Синхронизировать текущее состояние

### Задача

Привести в согласованный вид:

- `hlstatsx-community-edition-python-i18n/docs/status.md`;
- `hlstatsx-community-edition-python-i18n/docs/plans.md`;
- `hlstatsx-community-edition-python-i18n/docs/test-plan.md`.

### Что нужно сделать

- убрать stale `Next` / `In Progress`, которые снова открывают уже закрытые
  `Entries`, `ChangeTeam`, `PlayerNames`, `Players_History`, `TeamBonuses`;
- явно зафиксировать текущее состояние `P6d`;
- отдельно и однозначно описать GeoIP narrative:
  - что считается raw replay compare result;
  - что считается release-clean result;
  - обязателен ли post-replay GeoIP backfill;
- обновить parity gates в `docs/test-plan.md` под реальное состояние.

### Результат

- у проекта есть одна непротиворечивая формулировка текущего parity state;
- дальнейшие work items можно приоритизировать без повторного разбора
  исторических хвостов.

## Фаза 1. Validation contract и repository-wide CI

### Задача

Сделать так, чтобы CI проверял продуктовый контур, а не только
`proxy_daemon_py`.

### Минимальный scope

- job для `scripts/proxy_daemon_py`;
- job для `scripts/hlstats_py`;
- job для `scripts/replay_baseline`;
- PHP lint для `web`;
- минимальный docs check;
- заготовка под nightly parity/replay workflow.

### Важно

Если `hlstats_py` или `replay_baseline` нельзя честно прогнать в CI без
следующей фазы, это должно быть оформлено как явный blocker с понятным
временным обходом, а не как молчаливый пробел.

### Результат

- validation matrix из `docs/test-plan.md` начинает существовать не только в
  тексте, но и в automation;
- любые следующие рефакторы происходят под реальным quality gate.

## Фаза 2. Reconnect regression coverage

### Задача

Не “чинить reconnect bug”, а зафиксировать текущую корректную логику тестами.

### Что нужно проверить

- connection отсутствует;
- ping отключен;
- ping успешен;
- ping неуспешен и вызывает reconnect;
- существующие сценарии `proxy_daemon_py` не деградируют.

### Результат

- текущая реализация `_ensure_connection()` защищена от регрессии;
- устаревший review point больше не сможет снова попасть в план как active bug.

## Фаза 3. Package autonomy: убрать `hlstats_py -> proxy_daemon_py` coupling

### Задача

Разорвать sibling-coupling между пакетами и убрать ручной `PYTHONPATH`.

### Подзадачи

- инвентаризировать все imports из `proxy_daemon_py` внутри `hlstats_py`;
- вынести только реально общий код в shared package:
  - `hlx_core` или другой минимальный общий package boundary;
- обновить `pyproject.toml` так, чтобы зависимости были явными;
- убрать необходимость в `PYTHONPATH="${SCRIPTPATH}:${SCRIPTPATH}/proxy_daemon_py"`;
- добавить install/import smoke для package boundary.

### Ограничения

- не выносить в shared core бизнес-логику `hlstats_py`;
- не смешивать этот шаг с parity refactor;
- не делать big-bang restructuring без зеленых тестов.

### Результат

- `hlstats_py` становится самостоятельным installable runtime package;
- product lane получает более честные ownership boundaries.

## Фаза 4. Ops hardening: lifecycle scripts

### Задача

Убрать `kill -9` как первичный lifecycle path для:

- `scripts/run_proxy_py`;
- `scripts/run_hlstats_py`.

### Что нужно сделать

- добавить graceful stop;
- ждать завершения с timeout;
- использовать SIGKILL только как fallback;
- по возможности вынести общую shell-логику в reuseable helper;
- подготовить deployment notes или service templates.

### Результат

- lifecycle scripts становятся ближе к production-safe process supervision;
- shutdown semantics перестают зависеть от жесткого убийства процесса.

## Фаза 5. Control-plane hardening по реальной поверхности

### Задача

Ужесточить control plane, не приписывая проекту несуществующие paths.

### Реальная поверхность

- `hlstats_py`:
  - `HEARTBEAT`;
  - `SERVERLIST`;
  - `RELOAD`;
  - `KILL`.
- `proxy_daemon_py`:
  - `HEARTBEAT`;
  - `SERVERLIST`;
  - `RELOAD`.

### Что нужно сделать

- явно разделить read-only и mutating commands;
- отдельно ужесточить `hlstats_py RELOAD/KILL`;
- отдельно ужесточить `proxy_daemon_py RELOAD`;
- оставить `HEARTBEAT` и `SERVERLIST` read-only;
- пересмотреть loopback behavior, потому что именно там surface сейчас слабее;
- добавить тесты на разрешенные и запрещенные control scenarios.

### Результат

- control plane остается совместимым, но становится менее хрупким и менее
  “широким” для административных действий.

## Фаза 6. Явно разделить DB modes

### Задача

Развести:

- online strict mode;
- replay/import compatibility mode.

### Что нужно сделать

- инвентаризировать `sql_mode`, `SET NAMES`, `multi_statements`,
  `init_command` и related toggles;
- сделать production-safe default для online path;
- оставить compatibility mode только там, где он реально нужен:
  replay, import, comparison, transition tooling;
- документировать это различие в конфиге и runbooks;
- покрыть оба режима тестами.

### Результат

- legacy-tolerant DB behavior перестает быть молчаливым default;
- import/replay semantics становятся явными и легче проверяемыми.

## Фаза 7. Parity acceptance без живой повседневной опоры на Perl

### Задача

Перевести parity discipline из mostly-manual operational knowledge в более
автоматизированный acceptance flow.

### Что нужно сделать

- описать и зафиксировать lightweight PR subset;
- добавить nightly-heavy parity/replay flow;
- подготовить reproducible fixtures/artifacts, достаточные для повседневной
  валидации без обязательного ручного legacy loop;
- документировать, где Perl остается нужен:
  - reference behavior;
  - baseline regeneration;
  - targeted investigation.

### Важно

Не удалять legacy path раньше времени. Цель не удалить Perl, а перестать
зависеть от него в обычной продуктовой итерации.

### Результат

- parity остается строгой, но становится operationally cheaper;
- release-readiness начинает меньше зависеть от ручной памяти о runbooks.

## Фаза 8. PHP stabilization и EN/RU verification

### Задача

После стабилизации CI и runtime boundaries уменьшить global-state coupling в
PHP без big-bang rewrite.

### Реалистичный scope

- request/lang context;
- постепенное уменьшение мутации `$_GET`, `$_REQUEST`, `$_SESSION`;
- cache-service boundary;
- PHP lint;
- replay-backed EN/RU smoke для representative routes.

### Результат

- frontend становится более тестируемым;
- i18n/runtime behavior легче удерживать при изменениях.

## Фаза 9. Observability, profiling, release-readiness

### Задача

После базовой стабилизации добавить измеримость и release packaging.

### Scope

- runtime metrics или хотя бы structured metrics logging;
- benchmark/profiling runbook;
- replay speed / DB flush timing / reconnect counters;
- release checklist;
- deployment/configuration docs;
- при необходимости artifact publishing из CI.

### Результат

- продукт можно не только запускать, но и измерять;
- release state описан и воспроизводим.

## Рекомендованный порядок выполнения

1. Фаза 0 — синхронизировать docs truth.
2. Фаза 1 — расширить CI.
3. Фаза 2 — закрыть reconnect regression coverage.
4. Фаза 3 — убрать package coupling и `PYTHONPATH`.
5. Фаза 4 — сделать lifecycle scripts безопаснее.
6. Фаза 5 — ужесточить control plane.
7. Фаза 6 — разделить DB modes.
8. Фаза 7 — автоматизировать parity acceptance.
9. Фаза 8 — стабилизировать PHP/frontend verification.
10. Фаза 9 — metrics, profiling, release-readiness.

## Definition of Done для актуального плана

План можно считать реализованным, когда одновременно выполнено следующее:

- docs не противоречат друг другу по текущему parity state;
- CI покрывает Python, replay tooling и PHP lint/smoke;
- `hlstats_py` не зависит от ручного `PYTHONPATH` и скрытой sibling-связности;
- reconnect behavior зафиксирован regression tests;
- lifecycle scripts не используют `kill -9` как primary stop path;
- control plane разделяет read-only и mutating surface;
- DB compatibility behavior включается явно, а не молча живет в default path;
- parity acceptance поддерживает обычную разработку без обязательного ручного
  legacy loop;
- release-readiness подтверждается не только документами, но и automation.

## Что делать после этого

Только после выполнения фаз выше имеет смысл расширять scope на:

- более глубокую PHP modularization;
- richer admin/health tooling;
- Prometheus/Grafana integration;
- extended replay UI;
- migration assistant;
- новые продуктовые фичи поверх уже стабилизированного контура.
