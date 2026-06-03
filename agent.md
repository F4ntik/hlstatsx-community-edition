# Инструкции для агентов

- Основной архитектурный план переписывания демона: [docs/proxy_daemon_python_migration.md](docs/proxy_daemon_python_migration.md)
- Разбивка на задачи с чеклистом и комментариями: [docs/proxy_daemon_migration_task_breakdown.md](docs/proxy_daemon_migration_task_breakdown.md)
- План исполнения текущего baseline/replay стенда: [docs/plans.md](docs/plans.md)
- Живой статус стенда и последних прогонов: [docs/status.md](docs/status.md)
- Критерии готовности и тестовые ворота: [docs/test-plan.md](docs/test-plan.md)
- Операционный runbook для baseline/replay стенда: [scripts/replay_baseline/README.md](scripts/replay_baseline/README.md)

## Правила ведения прогресса

1. При завершении задачи из чеклиста в `docs/proxy_daemon_migration_task_breakdown.md` отмечайте её выполненной (заменяйте `[ ]` на `[x]`).
2. Под соответствующей строкой `Комментарий` добавляйте краткое описание результата: ключевые изменения, ссылки на пул-реквесты или коммиты.
3. Если добавляете новые задачи или уточняете существующие, сохраняйте формат чекбоксов и комментариев.
4. Обновляя архитектурный план, следите за тем, чтобы форматы входных данных и взаимодействия с БД оставались неизменными.

## Канонический workflow миграции демона

1. Не сравнивайте новый Python-код с production напрямую. Каноническая база для всех прогонов - локальный reset baseline, снятый после ручного сброса статистики в локальном prod-like legacy стеке.
2. Перед любым новым прогоном восстанавливайте baseline в оба сравнительных контура через `scripts/replay_baseline/restore-baseline.ps1`.
3. Первым gate всегда прогоняйте legacy на тех же production-логах офлайн через `hlstats.pl --stdin --server-ip=172.19.0.1 --server-port=27015`. Если legacy после чистого restore не поднимает статистику, сравнение с Python невалидно.
4. Только после успешного legacy smoke переходите к Python-контуру и сравнению БД.
5. После каждого изменения, влияющего на baseline/replay loop, синхронизируйте `docs/plans.md`, `docs/status.md`, `docs/test-plan.md` и `scripts/replay_baseline/README.md`, чтобы следующий запуск мог продолжить работу без восстановления контекста из чата.
