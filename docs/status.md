# Status: Standalone Python+i18n Product Lane

## Snapshot

- Current phase: `P6d` post-P0 — срез P0 (код + тесты + узкое окно 50/300/1000)
  закрыт 2026-04-27; диффы: `runtime-db-diff-p6d-narrow-50-20260427-050502.md`,
  `runtime-db-diff-p6d-narrow-300-20260427-050912.md`,
  `runtime-db-diff-p6d-narrow-1000-20260427-051926.md`. Полный корпус по-прежнему
  описан в `runtime-db-diff-p6d-20260426-161410.md` (не заменять узкими
  артефактами без явного решения о промоции).
- P0/M1 итог:
  - `TeamBonuses`: семантика `round_status`, bot/eligible gates, map-start
    roster reset, same-second hostage multiplicity, candidate-set уточнения и
    active-team reward eligibility уже приведены ближе к legacy. Актуальный
    narrow-1000 хвост всё ещё открыт:
    `legacy=4765`, `python=4773` (дельта `+8`) — **первый незакрытый пункт
    плана** (LP-P6D-001).
  - `Events_Entries`: принято с явной рационализацией (`legacy=0`,
    `python=1231` на 1000); строка сравнения **не** убирать (LP-P6D-002).
- План: `docs/plans.md`, тест-план: `docs/test-plan.md`.
- **Рабочий репозиторий:** правки кода и доков — в этом дереве
  (`hlstatsx-community-edition-python-i18n`); соседние проекты в воркспейсе —
  только для сверки с legacy/донором. **Быстрый массовый replay:** не
  изобретать заново — `docs/replay-fast-path.md` (stdin / `direct_import_artifacts.py`,
  тюнинг в `docs/hlstats_py_stdin_import_tuning.md`).
- Статус ворот: **красный** для P6d до закрытия или явного принятия остатка
  TeamBonuses + кластера RC-B. **Мини-агенты по страницам / маршрутам выключены**
  до явного открытия ворот.
- Last updated: 2026-04-27

## Done

- Stdin batch write path (`scripts/hlstats_py/storage.py`): append-only
  `EventBuffer` flushes when the buffer is full, before a periodic commit, or
  at import boundaries (`end_stdin_batch`, `finalize_import`, `flush_pending`);
  it is no longer flushed after every `record()`. Commits trigger when either
  the number of completed records or buffered plus executed write volume reaches
  `stdin_transaction_batch_size`. In batch mode, additive frag counters for
  weapon upserts, server kill totals, and map counts are merged in memory
  (`frag_write_delta_buffer.py`) and flushed with those queries. Rollback clears
  in-memory buffers without executing them. UDP runtime enables
  `configure_event_buffer(max_buffered_events=5000)` so idle `flush_pending`
  can batch event inserts; `EventBuffer.flush` chunks `executemany` using the
  adapter `executemany_chunk_size` when set.
- Completed post-mapfix drift-reduction execution pass with authoritative
  `-ForceDumpRestore` parity baseline on both stacks and new audit artifacts in
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/`.
- Closed `P5` maintenance backlog on `2026-04-25`:
  - added standalone Python ImportBans replacement:
    - package: `scripts/import_bans_py`
    - entrypoint: `python -m import_bans_py`
    - behavior parity with legacy scope: import-only ban propagation to
      `hlstats_Players.hideranking = 2` (no unban pass)
  - documented exact `hlstats_py.runtime --stdin` compatibility boundaries with
    reproducible command/exit evidence in `docs/test-plan.md`
  - validated Python heatmap generator against real map-pack JPEG assets under
    `heatmaps/src/cstrike` with host-to-comparison DB config
    (`scripts/replay_baseline/comparison/python/hlstats.host-local.conf`)
- Landed map lifecycle attribution hardening in `hlstats_py.runtime`:
  `Loading map` now stages pending map state and event map attribution flips on
  `Started map`.
- Landed `hlstats_Events_ChangeTeam` noise reduction in `hlstats_py.storage`:
  unresolved actors ignored, bot actors ignored, and duplicate team-change
  rows deduplicated by `(server, player, map, team, event_time)`.
- Added targeted regression coverage for lifecycle behavior and ChangeTeam
  filtering/deduping in `scripts/hlstats_py/tests/`.
- Validated control `window-300` replay after fixes; residual drift remains in
  map/action/player-history identity areas and is documented in
  `docs/audits/legacy-python-parity-20260425-post-mapfix-stage/NOTES.md`.

- Created a separate local repository for the standalone product lane.
- Rebased the product lane on clean `upstream/master` history instead of using
  the donor `test` branch as the final base directly (this standalone product
  repo remains separate from that choice). On the **Python migration donor
  fork**, branch `test` was later reset to the stdin performance integration
  tip; see `README.md` and the audit log entry for 2026-04-26.
- Imported the Python donor baseline from
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition`.
- Imported the RU i18n donor web/runtime layer from
  `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n`.
- Rewrote the primary repo docs so this repository now describes the integrated
  product rather than only the migration donor context.
- Preserved the donor-lane references:
  - Python migration runbooks and parity docs stay in this repo as supporting
    product references.
  - RU i18n donor docs stay available as integration background.
- Ran targeted Python validation in the product repo:
  - `hlstats_py` / replay-baseline batch passes when `PYTHONPATH` is set to
    the imported package roots.
  - targeted `proxy_daemon_py` tests pass at the assertion level, but the
    command still exits non-zero because the repo-enforced coverage threshold is
    not met by the small subset run.
- Ran targeted containerized `php -l` checks for the integrated product files:
  `web/hlstats.php`, `web/includes/i18n.php`, `web/includes/functions.php`,
  `web/pages/header.php`, `web/pages/footer.php`, `web/pages/players.php`,
  `web/pages/chat.php`, `web/pages/help.php`, `web/pages/playerinfo.php`,
  `web/pages/admin.php`, and `web/status.php`.
- Fixed the clean `scripts/proxy_daemon_py/fullstack` bootstrap in the product
  repo:
  - normalized `scripts/proxy_daemon_py/sql/02_set_hlstats_auth_plugin.sh` to
    Unix line endings so MySQL init no longer fails on `/bin/sh^M`
  - replaced the proxy-daemon heartbeat upsert with a MySQL 8.0 and
    MariaDB-compatible `ON DUPLICATE KEY UPDATE` form instead of the invalid
    `INSERT ... AS new`
  - switched proxy-daemon heartbeat probes to proxied control packets so
    `hlstats_py.runtime` accepts them from the Docker network and reports the
    worker `up`
- Re-ran product validation on the integrated repo itself:
  - host-side Python suites now pass with the imported package roots on
    `PYTHONPATH`:
    - `scripts/hlstats_py/tests` + `scripts/replay_baseline/tests` -> `56 passed`
    - `scripts/hlstats_awards_py/tests` + `scripts/hlstats_resolve_py/tests`
      -> `17 passed`
    - `scripts/proxy_daemon_py/tests` -> `72 passed` with repo-enforced
      coverage gate satisfied (`83.59%`)
  - targeted regression reruns for the fixed runtime paths pass:
    - `scripts/proxy_daemon_py/tests/test_db.py`
    - `scripts/proxy_daemon_py/tests/test_heartbeat.py`
    - `scripts/hlstats_py/tests/test_runtime.py`
  - clean product full-stack smoke now passes after rebuild:
    - `http://127.0.0.1:8080/` redirects to `hlstats.php`
    - `mode=contents&lang=ru` returns HTTP `200`
    - `status.php?lang=ru` returns HTTP `200`
    - proxy heartbeat persists `hlstats-worker:28000 -> up`
- Replayed the canonical donor fixture set through the integrated repo and
  re-checked the DB against legacy:
  - `L0415056.log` -> clean compact diff, counts `players=9`, `frags=33`
  - `L0415058.log` -> clean compact diff, counts `players=4`, `frags=18`
  - `L0416053.log` -> clean compact diff, counts `players=9`, `frags=34`
  - `L0417051.log` -> clean compact diff, counts `players=9`, `frags=36`
  - `L0417065.log` -> clean compact diff, counts `players=9`, `frags=32`
- Compared the integrated frontend to the live RU donor contour on the same
  HTTP routes:
  - target `mode=contents&lang=ru` renders localized RU UI and responds with
    HTTP `200`
  - target `status.php?lang=ru` also renders localized RU labels in the merged
    product contour
- Closed the audit-confirmed frontend residual i18n backlog (`P6b`) on the
  supported shared/public/admin/voice/ingame contour.
- Completed the release-style frontend revalidation pass (`P6c`) with targeted
  syntax checks, keyset diff, representative EN/RU smoke, and language
  persistence/fallback validation.
- Cleaned the replay-baseline working corpus and extended the Python replay
  contour for the second CS 1.6 source server:
  - `scripts/replay_baseline/prune-small-logs.ps1` removed `30,572` disposable
    `*.log` files below `15 KB`
  - the retained replay working set is now `41,576` log files
  - `scripts/replay_baseline/restore-baseline.ps1 -Stack python` now seeds
    `37.230.137.48:27015` as `game='cstrike'`
  - the seeded replay server receives copied `hlstats_Servers_Config` rows from
    the baseline parity server
  - `scripts/replay_baseline/replay_python_log.py` now accepts either a single
    file or a directory corpus and prints processed/skipped/error summary
- Switched the Python replay comparison web service from the legacy upstream
  image to a local build from the integrated product `web/` tree, with a
  comparison-local config pointing at the restored `hlstatsxce` database.
- Brought up the Python replay comparison stack on `2026-04-23` and validated
  the new CS 1.6 source server against real retained logs:
  - `L1231219.log` replay smoke sent `239` datagrams with
    `37.230.137.48:27015`
  - `L1231213.log` replay smoke sent `3,434` datagrams with
    `37.230.137.48:27015`
  - `L0217071.log` replay smoke sent `25,660` datagrams with
    `37.230.137.48:27015`
  - the replayed DB has visible statistics on the new server:
    `players=7`, `hlstats_Events_Frags=2`, `serverId=2`, `kills=2`
  - RU HTTP smoke on the integrated comparison web returns HTTP `200` for:
    - `hlstats.php?lang=ru`
    - `hlstats.php?mode=contents&lang=ru`
    - `hlstats.php?mode=game&game=cstrike&lang=ru`
    - `hlstats.php?mode=players&game=cstrike&lang=ru`
    - `hlstats.php?mode=servers&server_id=2&game=cstrike&lang=ru`
  - `mode=game` and `mode=servers&server_id=2` show both Russian UI labels and
    the replay server `37.230.137.48`
- Completed the full retained corpus replay on `2026-04-23` after fixing the
  corpus sender to stream stdin line-by-line instead of buffering the complete
  input in memory:
  - processed all `41,576` retained log files for `37.230.137.48:27015`
  - skipped `0` files and reported `0` read errors
  - sent `32,765,671` replay datagrams to the Python worker
  - elapsed wall time was `811.046` seconds, about `51.3` files/sec and
    `40,400` datagrams/sec at sender level
  - final replay DB counts on the new server: `players=497`,
    `hlstats_Events_Frags=1,536`, `kills=1,536`, `act_players=396`
  - integrated RU web smoke still returns HTTP `200` for the game, players,
    and server pages on `http://127.0.0.1:8281/`
- Closed `P6e` end-to-end on `2026-04-25`:
  - replay contour FTP import completed on Python stack with
    `Run-ContourFtpArtifacts` equivalent run at `MaxImportFiles=100` (exit `0`)
  - replay-safe awards completed (exit `0`):
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
  - strict/default sanity run completed (exit `0`):
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
  - replay SQL evidence:
    - non-empty map rows:
      `hlstats_Events_Frags=6536`, `hlstats_Events_PlayerActions=6838`,
      `hlstats_Events_Statsme=40047`
    - `hlstats_Maps_Counts`: `de_dust2 (kills=1013)`, `de_nuke (kills=27)`
    - `hlstats_Players_Awards=4`, `hlstats_Players_Ribbons=4`
    - GeoIP fill (`country` + `flag` non-empty in `hlstats_Players`): `148`

## In Progress

- [~] **P6d-M1 (LP-P6D-001):** в коде добавлено выравнивание с Perl
  `rewardTeam`: при `IgnoreBots` не пишутся `TeamBonuses` / skill для ботов и
  для `userid <= 0` (`storage._reward_team_players`,
  `_skip_team_reward_for_ignore_bots`, учёт `user_id` в `_resolve_player_id`);
  добавлен idle-prune активного состава перед `record(...)` (last_activity на
  игрока, timeout `250s`) + unit test на исключение idle-игрока из
  `TeamBonuses`. Прогон narrow-1000 после патча:
  `runtime-db-diff-p6d-narrow-1000-20260427-091053.md`
  (`hlstats_Events_TeamBonuses`: `legacy=12588`, `python=49033`) — остаток по
  LP-P6D-001 пока не закрыт. Доп.проверка показала, что snapshot-restore для
  python-контура уже содержал заполненные event-таблицы; валидный narrow-run
  нужно считать только от dump-baseline (`Run-ContourFtpArtifacts.ps1` с
  `-UseDumpRestore`). Runtime-блокер импорта снят минимальным патчем:
  в bot-fallback SQL (`_SELECT_PLAYER_BOT_UNIQUE_QUERY`) экранированы `%` в
  `LIKE` (`BOT:%%`, `00000000:%%:0`), из-за чего batch import больше не падает
  на `not enough arguments for format string`. Повторный python-only narrow-1000
  от dump-baseline: `hlstats_Events_TeamBonuses=4896`, bot/nonbot split:
  `bot=0`, `nonbot=4896`; top actionId: `279=2085`, `278=2053`, `269=529`;
  top map: `$2000$=1226`, `de_dust2=471`, `cs_mansion=314`; дубликаты по
  `(eventTime,actionId,playerId)` до `dup_count=3`. Относительно последнего
  валидного legacy narrow-1000 (`12588`) python теперь ниже на `7692`
  (`~38.9%` от legacy), поэтому LP-P6D-001 остаётся открытым; следующий
  минимальный шаг — точечный дедуп/гейт в `reward_team` без расширения scope.
  Дополнительно переподнят и заново проигран legacy baseline на тех же
  `1000` логах (без python replay): `processed=1000`, `errors=0`; повторный
  `compare_stats_dbs.py` дал `hlstats_Events_TeamBonuses: legacy=4765,
  python=4896` (дельта `+131`, python выше примерно на `2.75%`). Это
  подтверждает, что предыдущая крупная дельта была следствием неконсистентного
  legacy-среза, а текущий эталон для LP-P6D-001 — `4765 vs 4896`.
  Доп.триаж после этого сравнения: найден баг в python storage — в action-пути
  командных наград не учитывался `round_status` (добавлен гейт в
  `_record_action`, покрыт тестом), и найден SQL-формат-баг bot-fallback
  (`LIKE` с неэкранированным `%`, исправлен как `%%`). Для residual-дельты
  добавлен узкий eligibility-gate в `reward_team` (награды только для игроков,
  подтверждённых через `connect/entry` в рамках сессии); повторный python-only
  narrow-1000 от dump-baseline дал `hlstats_Events_TeamBonuses: legacy=4765,
  python=4813` (дельта `+48`, ~`+1.01%`), но LP-P6D-001 пока не закрыт.
  Дополнительный точечный шаг по `(eventTime,actionId,playerId)`:
  in-memory дедуп `TeamBonuses` по ключу `(server_id, player_id, action_id,
  event_time)` в `storage._reward_team_players` (без изменения policy
  `Events_Entries`); `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m
  pytest scripts/hlstats_py/tests` -> `103 passed`. Повторный python-only
  narrow-1000 от dump-baseline + `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`:
  `hlstats_Events_TeamBonuses: legacy=4765, python=4801` (дельта `+36`,
  ~`+0.76%`). Дополнительный минимальный шаг в `storage.py`: team reward теперь
  берёт каноническую команду из `hlstats_Actions.team` (с fallback на payload),
  что устраняет часть CT/T cross-team смещений в TeamBonuses. Полная валидация:
  `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests`
  -> `103 passed`; затем
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  и `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20` дали
  `hlstats_Events_TeamBonuses: legacy=4765, python=4800` (дельта `+35`,
  ~`+0.73%`). Итог: LP-P6D-001 остаётся открытым (COUNT всё ещё выше legacy на
  `35`; текущий минимальный патч уменьшил разрыв на `1`).
  Следующий минимальный шаг: в `storage.apply_server_map_transition(..., phase="started")`
  добавлен reset in-memory roster/team state (active/connected/eligible/last-activity)
  для выравнивания с Perl `doEvent_ChangeMap` и отсечения stale team-состояний
  перед TeamBonuses. Unit-валидация после патча: `103 passed` (включая новый
  тест на reset). После восстановления Docker выполнена обязательная валидация:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (summary `status=ok`, `elapsed_seconds=319.245`) и
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`.
  Новый срез `hlstats_Events_TeamBonuses`: `legacy=4765`, `python=4669`
  (дельта `-96`, python ниже на ~`2.01%`), поэтому LP-P6D-001 остаётся
  **не закрыт** (расхождение COUNT всё ещё ненулевое, сменился знак дельты).
  Точечный triage по ключу `(eventTime, actionId, playerId)` показывает:
  - legacy>python пики: `(2024-01-05 18:01:39,272,145)` `3 vs 0`,
    `(2024-01-05 18:01:39,272,133)` `3 vs 0`,
    `(2024-01-05 18:08:53,272,290)` `2 vs 0`;
  - зеркальные пары playerId-shift в тех же timestamp/action:
    `(2026-01-05 22:25:24,278,317)` `1 vs 0` и
    `(2026-01-05 22:25:24,278,321)` `0 vs 1` (аналогично по `279/269`).
  Следующий минимальный шаг без расширения scope и без изменения policy
  `Events_Entries`: в `reward_team` добавить узкий guard на смену канонического
  `player_id` внутри одного `(server_id, event_time, action_id)` окна
  (предпочитать первый стабильно разрешённый id в окне и не эмитить вторую
  запись при позднем remap этого же игрока), затем повторить narrow-1000.
  Выполнен следующий debug-цикл по первому расхождению:
  - в `storage._resolve_player_id` добавлен guard для пустых дескрипторов
    (нет `unique_id` и пустой `name`), чтобы не создавать phantom-player и не
    сдвигать `playerId` в TeamBonuses;
  - добавлен unit test:
    `test_empty_descriptor_without_unique_id_does_not_create_player`;
  - targeted pytest:
    `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests/test_storage.py -k "empty_descriptor_without_unique_id_does_not_create_player or team_bonus"` -> `9 passed`.
  Полная обязательная валидация после фикса:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (`status=ok`, `elapsed_seconds=271.062`) + `compare_stats_dbs.py --max-examples 20`
  снова даёт `hlstats_Events_TeamBonuses: legacy=4765, python=4669` (дельта `-96`).
  Локальная проверка окна первого расхождения (`L0101058`, `19:03:30..19:04:40`)
  подтверждает, что playerId-shift исправлен (`...279,84...` теперь совпадает на
  обеих сторонах). Residual остаётся в hostage-окне (`L0101061`, `20:33:47`,
  action `272`): legacy сохраняет две строки на игрока в ту же секунду, Python
  — одну из-за текущего in-memory dedupe по `(server_id, player_id, action_id,
  event_time)`. Поэтому LP-P6D-001 всё ещё **не закрыт**: COUNT-дельта осталась
  ненулевой, но источник смещён с identity-shift на multiplicity policy в
  TeamBonuses (без изменений `Events_Entries` policy).
  Дополнительный минимальный шаг по residual multiplicity выполнен:
  - dedupe в `storage._reward_team_players` ослаблен только для
    `event_code == "Rescued_A_Hostage"` (остальные team bonus события
    по-прежнему дедупятся по `(server_id, player_id, action_id, event_time)`);
  - добавлен тест
    `test_team_bonus_rescued_hostage_allows_same_second_duplicates`;
  - targeted pytest + полный пакет `scripts/hlstats_py/tests` -> `105 passed`.
  Обязательный narrow-1000 replay+compare после шага:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (`status=ok`, `elapsed_seconds=259.628`) и
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`
  дали `hlstats_Events_TeamBonuses: legacy=4765, python=4681`
  (дельта `-84`, улучшение на `+12` строк к предыдущему `-96`).
  Санити по hostage-окну `L0101061` (`20:33:46..20:33:47`) теперь совпадает
  1:1 с legacy, включая дубли на `20:33:47` для action `272`. LP-P6D-001 всё
  ещё **не закрыт**: остаётся ненулевая COUNT-дельта `84`, но целевой локальный
  класс расхождения (hostage same-second duplicates) снят.
  Следующий точечный шаг по residual undercount выполнен в idle-prune path:
  `_prune_idle_players` больше не исключает из active/reward-eligible игроков,
  которые всё ещё присутствуют в `connected_players` (даже при старом
  `last_activity`), чтобы не терять team rewards в длинных раундах.
  Добавлен тест `test_team_bonus_keeps_connected_idle_players_for_reward`;
  полный пакет `scripts/hlstats_py/tests` -> `106 passed`.
  Обязательный narrow-1000 replay+compare после шага:
  `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
  (`status=ok`, `elapsed_seconds=347.481`) и
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`
  дали `hlstats_Events_TeamBonuses: legacy=4765, python=4682`
  (дельта `-83`, ещё `+1` к прошлому результату `-84`).
  Локальная проверка de_mirage-окна `2024-01-01 19:41:51..19:51:56` показала,
  что для игрока `playerId=79` (unique `0:1828776565`) часть пропусков остаётся,
  поэтому LP-P6D-001 пока **не закрыт**.
  Дополнительный узкий шаг выполнен в `reward_team`:
  перебор кандидатов для TeamBonuses расширен до объединения
  `active_players ∪ connected_players ∪ reward_eligible_players` при сохранении
  strict-гейта на `reward_eligible_players` и всех действующих policy-гейтов
  (`round_status`, `IgnoreBots`, dedupe).
  Цель: не терять eligible-игроков, временно выпавших только из active-set.
  Валидация:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests` -> `106 passed`;
  - обязательный narrow-1000 replay+compare:
    `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
    (`status=ok`, `elapsed_seconds=282.009`) +
    `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`.
  Новый срез `hlstats_Events_TeamBonuses`: `legacy=4765`, `python=4692`
  (дельта `-73`, улучшение `+10` к предыдущему `-83`).
  LP-P6D-001 всё ещё **не закрыт** (остаток `73`), но хвост продолжает
  уменьшаться без расширения scope и без изменения policy `Events_Entries`.
- [ ] **P6d-M2 (RC-B):** объёмные дельты `ChangeTeam` / `Connects` / `Chat` /
  `PlayerActions` из того же narrow-diff — зафиксировать продуктовое решение и
  выровнять политику.
- `P6d`: full replay is now complete on both stacks for the same logical server
  identity `37.230.137.48:27015`:
  - legacy replay:
    `docs/audits/legacy-python-parity-20260423/legacy-full-corpus-replay-p6d-20260426-034823.log`
    (`processed=41513`, `errors=0`, `dropped_lines=169140`)
  - python direct stdin replay (worker-local batch path, retry with parser backend
    `python`):
    `docs/audits/legacy-python-parity-20260423/python-direct-stdin-import-p6d-20260426-034823-retry1.log`
    (`files=41513`, `records=30302028`, `mode=batch-stdin-local`)
- Input parity for this run is confirmed:
  - legacy input manifest:
    `legacy-full-corpus-input-manifest-p6d-20260426-034823.txt`
  - python processed-file manifest extracted from replay log:
    `python-direct-input-manifest-p6d-20260426-034823-retry1.txt`
  - line-by-line compare result: `diff_count=0` (same ordered filename set).
- DB diff for this run (authoritative): `compare_stats_dbs.py` output is
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-20260426-161410.md`
  (`18` tables differ; triage: `bug-plan.md` in the same folder). The
  `runtime-db-diff-p6d-20260426-034823-retry1.md` capture is a stub/obsolete
  pointer, not a second source of truth.
- The audit runbook is seeded at
  `docs/audits/legacy-python-parity-20260423/README.md`.
- The legacy comparison contour now has the same second-server restore
  bootstrap as Python: `37.230.137.48:27015`, `game='cstrike'`, with
  `32` copied `hlstats_Servers_Config` rows from `172.19.0.1:27015`.
- `scripts/replay_baseline/replay_legacy_log.py` is now available as the
  streaming file/directory replay helper for the legacy Perl daemon.
- Legacy smoke replay has passed the backend write gate:
  `L0217071.log` through the Perl daemon produced frag/stat rows, including
  `hlstats_Events_Frags=39` and `hlstats_Events_Statsme=538` after the smoke
  sequence.
- Legacy full replay is now clean and authoritative with final summary:
  `processed=41576`, `skipped=0`, `errors=0`, `dropped_lines=169419`
  (legacy DB reference counters captured in audit performance notes).
- Python full-corpus **rerun** used `--send-delay 0`: helper summary matched
  legacy (`processed=41576`, `skipped=0`, `errors=0`, `dropped_lines=169419`)
  but UDP flooding means most datagrams were likely **not** delivered to the
  worker; that DB snapshot and the first `runtime-db-diff.md` are **invalid**
  for parser parity conclusions (see audit `performance.md`).
- Input manifests and dropped-line manifests still match exactly between legacy
  and that Python run (same line counts and SHA-256 hashes); policy parity is
  confirmed, transport parity was not.
- A throttled Python full replay (e.g. `--send-delay 0.005`, new log name) plus
  fresh `compare_stats_dbs.py` output is the pending authoritative diff.
- The frontend-specific `P6b`/`P6c` work is still complete for the supported
  EN/RU product contour.

## Next

1. Завершить **P6d-M1**: минимальный фикс + тесты (`test_storage.py` /
   `test_runtime.py` по необходимости) → один прогон narrow 1000 (или 300 при
   отладке) → `python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20`
   → при существенном изменении добавить `runtime-db-diff-p6d-narrow-*` →
   обновить `bug-plan.md`, `issues.jsonl`, `performance.md`, этот `status.md`.
2. **P6d-M2 (RC-B)** после или параллельно, если независимо от M1.
3. **RC-C** (идентичность игроков / история) — после стабилизации RC-B.
4. `Events_Entries` — не убирать из compare; пересмотр рационализации только
   после RC-B/идентичности.
5. HTTP / мини-агенты по маршрутам — только после зелёного или явно принятого
   runtime-ворота.
- `P6e`: режим обслуживания — строгий контракт по умолчанию, регрессионные
  проверки replay/awards без расширения scope.

## Handoff / старт следующего чата

Скопируй в новый чат (репо `hlstatsx-community-edition-python-i18n`):

> Продолжаем `P6d` по `docs/status.md` и `docs/plans.md`. Первый приоритет:
> **LP-P6D-001** — на узком окне 1000 `TeamBonuses` всё ещё `4765` vs `4692`
> после серии narrow-фиксов, последний подтверждённый хвост `delta=-73`. Прочитай
> `docs/audits/legacy-python-parity-20260423/bug-plan.md` и последний артефакт
> `runtime-db-diff-p6d-narrow-1000-20260427-092518.md`. Сверь read-only SQL на
> legacy/python по `hlstats_Events_TeamBonuses` (COUNT, топ action/map) с Perl
> и Python (см. In Progress). Минимальный патч + pytest с
> `PYTHONPATH=scripts;scripts/proxy_daemon_py`. Не трогать строку compare для
> `Events_Entries`. Не включать page-агентов. Перед коммитом проверь `git
> status` на посторонние изменения вне этого среза.

## Assumptions

- Docker-контуры legacy/python подняты как в runbook аудита; SQL только
  read-only для диагностики.
- Канонический полнокорпусный diff остаётся
  `runtime-db-diff-p6d-20260426-161410.md` до явной перезаписи.

## Ready to execute

- Старт: **P6d-M1** (TeamBonuses).
- Цикл: правка → `pytest` (hlstats_py) → narrow replay + compare → правка
  доказательств в `docs/audits/...` и `docs/status.md`.
- Валидация: команды из раздела Next и `docs/test-plan.md` (replay / compare).
- Стоп: блокер воспроизведения, необходимость ручного секрета/деструктива, или
  явное продуктовое «принимаем как есть» с записью в `issues.jsonl`.

## Decisions

- This repo is the product integration lane, not the upstream PR lane.
- Python is the default runtime path for the product lane.
- Perl remains legacy-only for validation and transition scenarios.
- The original non-Python contour is the reference for EN/data parity, not for
  RU wording.
- The integrated Python web on `8281` is the RU/current UI reference; RU audit
  findings are data parity plus localization leaks, not byte-for-byte legacy
  HTML diffs.
- Destructive admin actions are out of scope for the parity audit and must be
  logged read-only instead of submitted.
- The frontend i18n implementation must stay explicit and dictionary-backed.
- EN and RU are the required release locales for v1.
- The frontend i18n fix pass will be executed in this order:
  shared helpers/runtime -> public pages -> admin/voice -> ingame pages ->
  final revalidation.
- Repeated visible labels should be moved to catalog-backed helpers or shared
  keys instead of being retranslated page-by-page.

## Current Risks

- Some Python test commands require explicit `PYTHONPATH` setup because the new
  product repo has not yet added a unified developer bootstrap for the imported
  package roots.
- The supported frontend EN/RU contour is now release-clean on the remediated
  routes, but some deeper legacy tooling still relies on bridge/fallback logic
  and should be watched if future routes are reopened or widened.
- Some older admin tools remain hard to smoke end-to-end because they are not
  fully wired into the current admin navigation contour or depend on broader
  legacy runtime flows; those are now a cleanup/readiness issue rather than a
  blocker for the validated routes.
- The replay comparison Docker contour uses fixed container names
  (`hlstatsx-python-*`), so local concurrent stack users can block rebuild or
  smoke passes until those names are free.
- The legacy full-corpus replay is materially slower than the Python sender, so
  the current full retained-corpus run may need to complete as a long-running
  background audit job before DB diff/page audit can start.
- A legacy replay run without a final helper `Replay summary` is not
  authoritative, even if DB counters increased during the run; partial DBs must
  be treated as contaminated and restored away.
- The first post-manifest `runtime-db-diff.md` largely reflects Python UDP
  overload (`--send-delay 0`), not a reviewed parser-vs-legacy conclusion; do
  not triage the 18-table list until a throttled full replay reproduces
  scale closer to legacy.
- The Python runtime still does not populate `hlstats_Players.country` /
  `flag` inline during connect handling, but the Python maintenance contour now
  owns GeoIP backfill through `hlstats_awards_py --geoip`.
- GeoIP now depends on operational prerequisites rather than missing code:
  either populated `geoLiteCity_*` tables or a readable
  `scripts/GeoLiteCity/GeoLite2-City.mmdb` with `UseGeoIPBinary > 0`; when
  those inputs are absent the Python command fails explicitly instead of
  silently leaving players as `Unknown Country`.
- The Python parser/runtime still differs from legacy Perl in a few
  replay-relevant edge cases:
  - Steam/auth normalization still treats only `STEAM_0:` as canonical
  - pending/unknown auth connect events are not delayed like Perl
  - repeated property parsing does not match Perl's destructive `getProperties`
  - connect-address parsing currently splits on the first `:` instead of
    following the legacy IPv4-only `host:port` rule
- Some game-scoped admin routes still depend on the legacy JS/basic-mode
  navigation split, so direct noninteractive HTTP smoke can verify many of them
  but not every task uniformly.
- `P5` maintenance backlog is closed; remaining lane risk is concentrated in
  `P6d` parity replay throughput/diff evidence rather than missing Python
  maintenance utilities.
- Some donor docs still describe lane-specific context rather than product
  context; the main docs in this repo are now the primary source of truth.

## Audit Log

- 2026-04-26: On the Python migration donor fork (`hlstatsx-community-edition`,
  e.g. `origin` for that clone), remote branch **`test`** was **force-updated**
  to match the former `perf/hlstats-stdin-batch-speedup` tip (stdin import
  batching / DB session reuse). Treat **`test`** as the fork’s integration line
  for that stack; refresh local clones with `git fetch` and
  `git reset --hard origin/test` if they still pointed at the pre-reset
  history. Documented in `README.md` under Git / migration fork.
- 2026-04-25: Closed `P6e` validation/evidence loop:
  - replay contour FTP import completed on the Python stack with `100` file cap
    (direct worker run equivalent to `Run-ContourFtpArtifacts` import stage)
  - fixed intermittent `Run-ContourFtpArtifacts` abort between FTP-state cleanup
    and `docker compose run`:
    - root cause: flaky `Get-ChildItem ... | Remove-Item` path raising
      `NullReferenceException` on some runs
    - remediation: replaced with explicit safe cleanup loop over matched files
      in `scripts/replay_baseline/comparison/python/Run-ContourFtpArtifacts.ps1`
    - stable end-to-end command now passes without manual workaround:
      `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -MaxImportFiles 100`
      (exit `0`)
    - canonical script summary now printed in stdout (`status/import mode/server/
      limits/geoip mode`) for audit-friendly replay evidence
  - replay-safe awards runs completed with exit `0`:
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r --replay-mode`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g --replay-mode`
  - strict/default sanity runs completed with exit `0`:
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r`
    - `python -m hlstats_awards_py --date 2026-01-02 -a -r -g`
  - SQL evidence captured:
    - `hlstats_Events_Frags` non-empty map: `6536`
    - `hlstats_Events_PlayerActions` non-empty map: `6838`
    - `hlstats_Events_Statsme` non-empty map: `40047`
    - `hlstats_Maps_Counts`: `de_dust2 kills=1013`, `de_nuke kills=27`
    - `hlstats_Players_Awards=4`, `hlstats_Players_Ribbons=4`
    - GeoIP fill (`hlstats_Players` non-empty `country` + `flag`): `148`
- 2026-04-25: Closed `P5` maintenance-only backlog with validation evidence:
  - `ImportBans` Python CLI implemented as `scripts/import_bans_py`
  - runtime boundary commands:
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin`
      -> exit `1` (`--stdin requires both --server-ip and --server-port`)
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin --server-ip 127.0.0.1 --server-port 27015 --stdin-transaction-batch-size -1`
      -> exit `1` (`--stdin-transaction-batch-size must be >= 0`)
    - `python -m hlstats_py.runtime --configfile hlstats.conf --stdin --server-ip 127.0.0.1 --server-port 27015 --parser-backend native --stdin-transaction-batch-size 0`
      -> exit `1` on local config DB precondition (`DBHost must be configured in hlstats.conf`) after CLI boundary acceptance
  - ImportBans CLI boundary commands:
    - `python -m import_bans_py --help` -> exit `0`
    - `python -m import_bans_py --configfile hlstats.conf --dry-run`
      -> exit `1` (missing required source configuration)
  - real map-pack asset heatmap runs:
    - `python -m hlstats_py.heatmaps --configfile scripts/replay_baseline/comparison/python/hlstats.host-local.conf --game cstrike --map de_dust2 --disablecache --debug-level 2`
      -> exit `0`
    - `python -m hlstats_py.heatmaps --configfile scripts/replay_baseline/comparison/python/hlstats.host-local.conf --game cstrike --map de_nuke --disablecache --debug-level 2`
      -> exit `0`
    - both runs completed generator path (`Heatmap creation done`) and
      skipped render step because queried kill count for the map window was `0`
- 2026-04-24: Landed stdin import performance tuning for Python runtime/FTP path:
  - added quiet-by-default stdin event logging with opt-in debug flag
    `--stdin-verbose-events` (default off)
  - added parser backend selector `--parser-backend` with default `python`
    and optional `native` fast path
  - added stdin DB transaction batching with
    `--stdin-transaction-batch-size` (default `1000`, `0` disables batching)
  - documented defaults, tuning profiles, and verification flow in
    `docs/hlstats_py_stdin_import_tuning.md`
- 2026-04-24: Added `P6e` architecture-modernization parity milestone to
  `docs/plans.md` and aligned execution framing around:
  - explicit runtime map state projection
  - policy-based awards behavior (strict/default vs replay-safe)
  - decoupled GeoIP resolver behavior by policy
  - replay-focused validation gates and stop-and-fix criteria
- 2026-04-23: Began `P6d` execution on the backend/runtime contour:
  - factored `restore-baseline.ps1` so the second replay server bootstrap runs
    for both `-Stack legacy` and `-Stack python`, while Python-only
    `Proxy_Daemons` setup remains Python-only
  - added `scripts/replay_baseline/replay_legacy_log.py`, a reusable streaming
    stdin replay helper for the legacy Perl daemon
  - verified `-Stack legacy` restore creates exactly one
    `37.230.137.48:27015` `cstrike` server with `32` copied config rows and a
    clean pre-replay DB
  - smoke replayed `L1231219.log`, `L1231213.log`, and `L0217071.log`; the
    final representative smoke confirmed Perl writes gameplay stats
    (`players=62`, `frags=39`, `statsme=538`)
  - started the full `41,576` file retained-corpus legacy replay from a clean
    restore; page audit remains blocked until DB/runtime diff is captured
- 2026-04-23: Heartbeat follow-up found the first full legacy retained-corpus
  run failed before completion:
  - helper output reached `L0107052.log` and then logged `[Errno 22] Invalid argument`
  - no final `Replay summary` was written
  - queued files before failure: `1097`
  - the partial legacy DB must not be used for DB diff or page audit
  - patched `replay_legacy_log.py` to report daemon/stdin pipe closure as a
    replay failure instead of masking it as per-file read failures
- 2026-04-23: Completed the P6d backend/runtime parity **capture** gates (with a
  critical caveat on the Python side):
  - legacy full replay completed cleanly and is now the authoritative
    comparison reference
  - Python rerun full replay used `--drop-empty-team-enter-events` and
    `--send-delay 0 --drain-delay 10`; helper summary matched legacy, but
    `--send-delay 0` is now treated as **invalid for DB parity** (UDP loss on
    the docker UDP path; helper `errors=0` does not prove delivery)
  - legacy vs Python input manifests and dropped-line manifests match exactly
    (`41576` inputs, `169419` dropped lines; identical SHA-256 hashes)
  - captured Python post-replay DB snapshot (not comparable to legacy at scale):
    `players=554`, `frags=2007`, `statsme=9687`, `players_history=73333`,
    replay server `kills=1994`, `players=552`, `act_players=408`
  - generated runtime diff report:
    `docs/audits/legacy-python-parity-20260423/runtime-db-diff.md`
    with logical differences in `18` tables — **stale until throttled replay**
  - page/web parity audit remains blocked pending a throttled Python full replay
    and a regenerated DB diff
- 2026-04-23: Documented Python replay UDP methodology (`performance.md`,
  `status.md`, audit `README.md`); `replay_python_log.py` now prints a stderr
  warning when `--send-delay 0`.
- 2026-04-23: Planned `P6d` full legacy-vs-Python product parity audit using
  the `justdoit` workflow:
  - added `P6d` to `docs/plans.md`
  - created the full mini-agent runbook at
    `docs/audits/legacy-python-parity-20260423/README.md`
  - updated `docs/test-plan.md` with the replay, DB diff, route inventory,
    issue logging, and final bug-plan gates
  - first unfinished execution item is legacy/Python comparison setup, with
    legacy second-server bootstrap and streaming full-corpus replay as the
    first prep blockers
- 2026-04-22: Follow-up replay/product audit after the second-server bootstrap:
  - direct SQL inspection of the live Python comparison DB on `127.0.0.1:3327`
    confirms the restore bootstrap is intact even before replay:
    - `172.19.0.1:27015` and `37.230.137.48:27015` both exist in
      `hlstats_Servers`
    - the replay server still has `32` copied `hlstats_Servers_Config` rows
    - `Proxy_Daemons` is configured to `hlstatsx-python-worker:28000`
    - the restored DB is still clean for replay work (`0` players,
      `0` frags, `0` history rows)
  - audited the Python country-resolution path and confirmed that product-lane
    Python runtime does not currently write `hlstats_Players.country` / `flag`
  - audited Python-vs-Perl parser parity and confirmed no repo-vs-repo drift
    between donor/product copies, but several remaining functional deltas in
    Python:
    - Steam/auth normalization is narrower than Perl
    - pending/unknown auth connect handling is missing
    - repeated property parsing is not Perl-equivalent
    - connect-address parsing can diverge from Perl outside IPv4 `host:port`
  - prepared the next replay/web smoke focus list for the restored 8281 contour:
    `status.php`, `show_graph.php`, `sig.php`, `playerhistory`, `updater`,
    core public pages, key admin tasks, and replay-backed ingame status/load
- 2026-04-22: Completed `P6c` release-style frontend revalidation after the
  final `P6b` remediation batch:
  - representative HTTP smoke returns `200` with expected localized EN/RU
    content for:
    - public `mode=playerhistory` error-path rendering
    - public `mode=updater`
    - voice `mode=teamspeak`
    - ingame `mode=ingame&page=status`
    - admin `task=tools_adminevents`
    - admin `task=serversettings&key=1&game=cstrike`
  - explicit language persistence/fallback contract passes:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when only `PHPSESSID` is preserved
    - fresh request without language state falls back to EN
    - invalid `lang=zz` does not overwrite the persisted valid language
  - focused grep over the remediated files no longer shows the retired raw
    English UI copy outside translation-map literals, EN catalogs, and accepted
    fallback strings
- 2026-04-22: Landed the first `P6b` remediation batch for the
  audit-confirmed residual backlog:
  - hardened shared request sanitization in `web/includes/functions.php` and
    the main HTTP/image entrypoints to keep non-Latin input intact
  - fixed the remaining `web/status.php` runtime bootstrap defect so localized
    error handling is available before the PHP-version gate fires
  - localized the residual direct-output public/admin/ingame surfaces in:
    - `web/pages/playerhistory.php`
    - `web/pages/profile.php`
    - `web/pages/updater.php`
    - `web/pages/admintasks/serversettings.php`
    - `web/pages/admintasks/tools_adminevents.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/status.php`
  - extended the shared table/runtime bridge so cell-value literals and runtime
    marker payloads resolve through the catalogs instead of leaking English
- 2026-04-22: Validation for the current `P6b` remediation batch:
  - rebuilt `web` from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml`
  - targeted Dockerized `php -l` passes for all changed shared/public/admin/
    ingame files plus `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff remains clean with `missing_in_ru=0` and
    `missing_in_en=0`

- 2026-04-22: Ran a distributed static i18n audit over the integrated product
  repo with separate passes for:
  - shared/runtime core
  - public `web/pages/*`
  - admin shell and `admintasks`
  - ingame/voice/template surfaces
  - aggregate coverage and keyset completeness
- 2026-04-22: Audit outcome:
  - `web/lang/en.php` and `web/lang/ru.php` remain aligned by keyset
  - the repo is close to release-clean on the public/admin contours, but not
    yet on ingame/shared runtime
  - the highest-risk remaining issues are:
    - ASCII-only request sanitization that can corrupt non-Latin input
    - English event descriptions embedded in `web/pages/playerhistory.php` SQL
    - DB-sourced English help text in
      `web/pages/admintasks/serversettings.php`
    - residual raw-English ingame routes such as `status`, `load`, `mapinfo`,
      and `weaponinfo`
    - remaining bridge/fallback-heavy legacy helpers and utility pages
- 2026-04-22: Inserted a new `P6b` remediation milestone into `docs/plans.md`
  and moved the release-style revalidation pass to `P6c` so the plan matches
  the audit findings.
- 2026-04-22: Replay-baseline corpus hygiene and second-server bootstrap:
  - added `scripts/replay_baseline/prune-small-logs.ps1`
  - pruned the working replay artifacts set from `72,148` logs to `41,576`
    by deleting `30,572` logs smaller than `15 KB`
  - extended `scripts/replay_baseline/restore-baseline.ps1 -Stack python` so
    the restored comparison DB contains:
    - the canonical parity server `172.19.0.1:27015`
    - the CS 1.6 replay server `37.230.137.48:27015`
  - verified the seeded replay server has `32` copied
    `hlstats_Servers_Config` rows
  - extended `scripts/replay_baseline/replay_python_log.py` so it can replay a
    sorted directory corpus under one explicit logical source server identity
- 2026-04-23: Reworked the Python comparison web service so the `8281`
  inspection contour uses the current integrated product `web/` tree instead
  of the legacy upstream web image.
- 2026-04-23: Runtime validation on the freed replay stack:
  - rebuilt and started `scripts/replay_baseline/comparison/python`
  - confirmed `SERVERLIST` exposes both `172.19.0.1:27015` and
    `37.230.137.48:27015`
  - replayed retained CS 1.6 logs under `37.230.137.48:27015`
  - verified the integrated RU frontend on `8281` renders replayed data with
    Russian labels and the new replay server visible on the game/server pages

- 2026-04-22: Ran a full frontend translation review over:
  - shared i18n runtime/catalogs
  - public `web/pages/*` groups
  - voice/templates
  - admin shell and `admintasks`
  - `web/pages/ingame/*`
- 2026-04-22: Review outcome:
  - no evidence that the explicit EN/RU i18n contract is conceptually wrong
  - strong evidence that a large legacy UI layer still bypasses `t(...)`
  - one confirmed catalog gap: `literal.yes` missing in RU
  - one confirmed syntax blocker: `web/pages/ingame/motd.php`
- 2026-04-22: Planned the remediation as `P6a -> P6b` instead of jumping
  directly to final packaging.
- 2026-04-22: Landed `P6a` batch 1:
  - added the missing RU catalog key `literal.yes`
  - added shared catalog coverage for runtime/database/public error-path text
  - localized shared helper/runtime flows in:
    - `web/includes/functions.php`
    - `web/includes/class_db.php`
    - `web/includes/google_maps.php`
    - `web/ingame.php`
  - localized first public/detail surfaces in:
    - `web/pages/search-class.php`
    - `web/pages/help.php`
    - `web/pages/game.php`
    - `web/pages/servers.php`
    - `web/pages/claninfo.php`
    - `web/pages/dailyawardinfo.php`
    - `web/pages/mapinfo.php`
    - `web/pages/rankinfo.php`
    - `web/pages/ribboninfo.php`
    - `web/pages/rolesinfo.php`
    - `web/pages/weaponinfo.php`
- 2026-04-22: Validation for `P6a` batch 1:
  - targeted Dockerized `php -l` passes for every file changed in the batch
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` is clean
  - fullstack smoke on `127.0.0.1:8080` returns HTTP `200` with expected
    localized tokens for:
    - `mode=contents`
    - `mode=help`
    - `mode=search`
    - `game=aoc`
    - `mode=servers&game=aoc&server_id=1`
    - `mode=dailyawardinfo&game=aoc&award=1`
    - `mode=mapinfo&game=aoc&map=de_dust2`
    - `mode=rankinfo&game=aoc&rank=1`
    - `mode=rolesinfo&game=aoc&role=Crossbowman`
    - `mode=weaponinfo&game=aoc&weapon=Broadsword`
- 2026-04-22: Landed `P6a` batch 2:
  - localized voice/runtime error paths in:
    - `web/pages/teamspeak.php`
    - `web/pages/ventrilo.php`
  - extended shared dictionary-backed literal mapping and new catalog coverage
    for ingame/admin/voice surface labels and runtime messages in:
    - `web/includes/functions.php`
    - `web/includes/i18n.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - removed or centralized the reviewed ingame/runtime leaks in:
    - `web/pages/ingame/actioninfo.php`
    - `web/pages/ingame/actions.php`
    - `web/pages/ingame/bans.php`
    - `web/pages/ingame/claninfo.php`
    - `web/pages/ingame/clans.php`
    - `web/pages/ingame/footer.php`
    - `web/pages/ingame/header.php`
    - `web/pages/ingame/help.php`
    - `web/pages/ingame/kills.php`
    - `web/pages/ingame/load.php`
    - `web/pages/ingame/mapinfo.php`
    - `web/pages/ingame/maps.php`
    - `web/pages/ingame/motd.php`
    - `web/pages/ingame/players.php`
    - `web/pages/ingame/servers.php`
    - `web/pages/ingame/statsme.php`
    - `web/pages/ingame/status.php`
    - `web/pages/ingame/targets.php`
    - `web/pages/ingame/weaponinfo.php`
    - `web/pages/ingame/weapons.php`
    - `web/pages/ingame/accuracy.php`
  - fixed a real runtime defect while in scope:
    - `web/pages/ingame/motd.php` parser blocker
    - `web/pages/ingame/actioninfo.php` now queries action description by
      `code` instead of an undefined `$action_id`
    - `web/pages/ventrilo.php` now checks password length correctly
- 2026-04-22: Validation for `P6a` batch 2:
  - targeted Dockerized `php -l` passes for all touched voice/shared/ingame
    files, including `web/pages/ingame/motd.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` is clean and
    duplicate-key noise was reduced to zero
  - rebuilt `fullstack-web` from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace code instead of a stale container image
  - fullstack smoke on `127.0.0.1:8080` returns HTTP `200` with expected
    localized tokens for:
    - `hlstats.php?mode=admin&lang=en|ru`
    - `ingame.php?game=aoc&mode=help&lang=en|ru`
    - `ingame.php?game=aoc&mode=servers&lang=en|ru`
    - `ingame.php?game=aoc&mode=motd&lang=en|ru`
    - `ingame.php?game=aoc&mode=actions&lang=en|ru`
    - `ingame.php?game=aoc&mode=statsme&player=1&lang=en|ru`
    - `ingame.php?game=aoc&mode=claninfo&clan=1&lang=en|ru`
    - `hlstats.php?mode=teamspeak&game=aoc&tsId=1&lang=en|ru`
    - `hlstats.php?mode=ventrilo&game=aoc&veId=1&lang=en|ru`
- 2026-04-22: Landed `P6a` batch 3:
  - added shared admin/runtime helper coverage for access-denied handling and
    extra admin edit-list labels in:
    - `web/includes/functions.php`
  - retired the repeated raw-English `admintasks` guard paths across the
    reviewed admin task files so direct-access and access-denied flows now use
    the shared dictionary-backed helpers
  - localized the most reachable remaining admin task runtime/public text in:
    - `web/pages/admintasks/options.php`
    - `web/pages/admintasks/serversettings.php`
    - `web/pages/admintasks/games.php`
    - `web/pages/admintasks/tools_reset_2.php`
    - `web/pages/admintasks/tools_synchronize.php`
    - `web/pages/admintasks/tools_resetdbcollations.php`
  - extended EN/RU catalogs for those admin task surfaces in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - fixed one additional PHP 8 syntax/runtime blocker while in scope:
    - removed invalid call-time pass-by-reference syntax from
      `web/pages/admintasks/tools_synchronize.php`
    - corrected the accidental assignment in the null-default check inside
      `web/pages/admintasks/tools_resetdbcollations.php`
- 2026-04-22: Validation for `P6a` batch 3:
  - targeted Dockerized `php -l` passes for all changed admin/helper files in
    the batch, including every touched `web/pages/admintasks/*.php` file
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains
    clean with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` after the final
    `tools_synchronize.php` PHP 8 fix so HTTP smoke used the current workspace
    image
  - authenticated admin HTTP smoke using the existing local fixture admin
    account returns HTTP `200` with expected localized tokens for:
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
    - `hlstats.php?mode=admin&task=games&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_reset_2&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_resetdbcollations&lang=en|ru`
  - explicit language persistence/fallback contract remains intact:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when the `lang` cookie is omitted but the session
      is preserved
    - default EN rendering with a fresh request without `lang`, cookie, or
      session
  - admin route notes from the smoke pass:
    - `serversettings` requires a fuller legacy game-task navigation path than
      the direct noninteractive request used in the smoke, so it was syntax and
      catalog validated in this batch but not token-asserted by direct HTTP
    - `tools_synchronize` is not currently registered in the active admin task
      list even though the file remains present, so it was validated by syntax
      and catalog/runtime grep rather than route-level token smoke
- 2026-04-22: Extended `P6a` batch 3 with the remaining cheap admin helper
  cleanup:
  - localized the longer admin runtime/control tools in:
    - `web/pages/admintasks/tools_perlcontrol.php`
    - `web/pages/admintasks/tools_settings_copy.php`
  - localized the helper/list screens in:
    - `web/pages/admintasks/tools_editdetails.php`
    - `web/pages/admintasks/tools_optimize.php`
    - `web/pages/admintasks/tools_ipstats.php`
    - `web/pages/admintasks/tools_adminevents.php`
  - extended EN/RU catalogs for those helper screens in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - removed one additional in-scope admin filter leak:
    - `web/pages/admintasks/tools_adminevents.php` now uses the shared
      localized `(All)` label instead of a raw English literal
- 2026-04-22: Validation for the batch 3 helper follow-up:
  - targeted Dockerized `php -l` passes for:
    - `web/pages/admintasks/tools_editdetails.php`
    - `web/pages/admintasks/tools_optimize.php`
    - `web/pages/admintasks/tools_ipstats.php`
    - `web/pages/admintasks/tools_adminevents.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` after the final
    `tools_adminevents.php` cleanup so HTTP smoke used the current workspace
    image
  - authenticated admin HTTP smoke using the local fixture admin account returns
    HTTP `200` with expected localized tokens for:
    - `hlstats.php?mode=admin&task=tools_perlcontrol&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_settings_copy&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_editdetails&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_optimize&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_ipstats&lang=en|ru`
    - `hlstats.php?mode=admin&task=tools_adminevents&lang=en|ru`
  - explicit language persistence/fallback contract remains intact on the
    authenticated helper contour:
    - `GET lang=ru`
    - cookie fallback to RU on the next request without `lang`
    - session fallback to RU when only `PHPSESSID` is preserved
    - default EN rendering with a fresh authenticated request without language
      state
- 2026-04-22: Landed `P6a` batch 4 on the next cheap admin `EditList` screens:
  - localized repeated column labels, short guidance text, and submit buttons
    in:
    - `web/pages/admintasks/awards_plyractions.php`
    - `web/pages/admintasks/awards_plyrplyractions.php`
    - `web/pages/admintasks/awards_plyrplyractions_victim.php`
    - `web/pages/admintasks/servers.php`
    - `web/pages/admintasks/voicecomm.php`
    - `web/pages/admintasks/roles.php`
    - `web/pages/admintasks/teams.php`
    - `web/pages/admintasks/ranks.php`
    - `web/pages/admintasks/ribbons_trigger.php`
  - localized the encrypted-password placeholder in
    - `web/pages/admintasks/servers.php`
  - extended EN/RU catalogs for the shared admin labels reused by those
    screens in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 4:
  - targeted Dockerized `php -l` passes for all nine touched admin pages plus
    `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=awards_plyractions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_plyrplyractions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_plyrplyractions_victim&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=servers&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=voicecomm&lang=en|ru`
    - `hlstats.php?mode=admin&task=roles&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=teams&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=ranks&game=cstrike&lang=en|ru`
  - focused raw-literal grep over the nine touched admin files no longer shows
    user-facing raw English outside the standard file header comment block and
    non-UI internals
  - route note:
    - `ribbons_trigger` still falls back to the legacy overview/basic-mode
      contour on a direct noninteractive request after login, so this batch
      validates it by syntax, catalogs, and focused grep, but not by direct
      token-level HTTP smoke
- 2026-04-22: Landed `P6a` batch 5 on the next medium-cost admin pages:
  - localized the remaining repeated column labels, select option labels,
    explanatory copy, and submit buttons in:
    - `web/pages/admintasks/actions.php`
    - `web/pages/admintasks/adminusers.php`
    - `web/pages/admintasks/awards_weapons.php`
    - `web/pages/admintasks/ribbons.php`
    - `web/pages/admintasks/weapons.php`
  - extended EN/RU catalogs for the new shared/admin task literals in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 5:
  - targeted Dockerized `php -l` passes for all five touched admin pages plus
    `web/lang/en.php` and `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero duplicate keys and no missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=actions&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=adminusers&lang=en|ru`
    - `hlstats.php?mode=admin&task=awards_weapons&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=ribbons&game=cstrike&lang=en|ru`
    - `hlstats.php?mode=admin&task=weapons&game=cstrike&lang=en|ru`
  - focused raw-literal grep over the five touched admin files no longer shows
    the retired user-facing raw English literals outside localized key names
    and non-UI internals
- 2026-04-22: Landed `P6a` batch 6 on the remaining heavy admin pages:
  - localized the remaining user-facing text in:
    - `web/pages/admintasks/clantags.php`
    - `web/pages/admintasks/hostgroups.php`
    - `web/pages/admintasks/options.php`
  - extended EN/RU catalogs for:
    - the full `clantags` and `hostgroups` help text blocks
    - the `options` page section headings
    - option field labels and DB-backed select-choice labels used on
      `options.php`
  - kept the options-page rendering dictionary-backed without changing the
    existing admin option definitions by localizing section titles, field
    labels, submit/success text, and choice text at render time
- 2026-04-22: Validation for `P6a` batch 6:
  - targeted Dockerized `php -l` passes for:
    - `web/pages/admintasks/clantags.php`
    - `web/pages/admintasks/hostgroups.php`
    - `web/pages/admintasks/options.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke returns HTTP `200` with expected
    localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=clantags&lang=en|ru`
    - `hlstats.php?mode=admin&task=hostgroups&lang=en|ru`
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
  - focused raw-literal grep over the three touched admin files no longer shows
    the retired user-facing raw English strings outside internal fallback maps,
    legacy internal option definitions, and non-rendered code literals
- 2026-04-22: Landed `P6a` batch 7 on the final shared helper fallback cleanup:
  - removed fallback-only raw-English helper text from
    `web/includes/functions.php`
  - switched the remaining helper/runtime messages there to catalog-key-backed
    lookup without embedded English last-resort strings
  - added the missing shared catalog key `error.invalid_url` in:
    - `web/lang/en.php`
    - `web/lang/ru.php`
- 2026-04-22: Validation for `P6a` batch 7:
  - targeted Dockerized `php -l` passes for:
    - `web/includes/functions.php`
    - `web/lang/en.php`
    - `web/lang/ru.php`
  - EN/RU keyset diff for `web/lang/en.php` vs `web/lang/ru.php` remains clean
    with zero missing cross-locale keys
  - rebuilt `fullstack-web` again from
    `scripts/proxy_daemon_py/fullstack/docker-compose.yml` so HTTP smoke used
    the current workspace image
  - authenticated direct admin HTTP smoke still returns HTTP `200` with
    expected localized EN/RU tokens for:
    - `hlstats.php?mode=admin&task=clantags&lang=en|ru`
    - `hlstats.php?mode=admin&task=hostgroups&lang=en|ru`
    - `hlstats.php?mode=admin&task=options&lang=en|ru`
  - focused helper grep confirms no remaining fallback-only raw-English helper
    strings in `web/includes/functions.php` outside the shared legacy literal
    translation map
- 2026-04-27: `LP-P6D-001` stage-level triage (narrow-1000) выполнен по плану
  `team-bonuses-stage-trace`:
  - baseline подтвержден: `hlstats_Events_TeamBonuses legacy=4765`,
    `python=4692`, `delta=-73` (`legacy-only=904`, `python-only=831`).
  - в `scripts/hlstats_py/storage.py` добавлена stage-level трассировка
    pipeline TeamBonuses с артефактом
    `scripts/replay_baseline/artifacts/team-bonus-stage-trace.json`
    (stages: `candidate_set`, `eligible_gate_reject`, `team_gate_reject`,
    `ignore_bots_gate_reject`, `dedupe_gate_reject`, `inserted` + агрегаты по
    `actionId/map/playerId`).
  - stage-агрегации на narrow-1000: `candidate_set=9667`,
    `inserted=4692`, `team_gate_reject=4665`, `eligible_gate_reject=310`,
    `ignore_bots_gate_reject=0`, `dedupe_gate_reject=0`.
  - dominant gate для residual определен как `eligible_gate_reject`
    (единственный «узкий» отсекающий gate со значимым вкладом при нулевых
    `ignore_bots/dedupe`), top actions: `279=138`, `278=131`, `269=29`.
  - внесен один минимальный фикс в dominant направлении: нормализация team alias
    (`T/TS/TERRORISTS -> TERRORIST`, `COUNTER[- ]TERRORIST/CTS -> CT`) при
    обновлении in-memory team state и team-based gate сравнениях.
  - revalidate после фикса: unit
    `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests/test_storage.py`
    -> `40 passed`; narrow-1000 + compare дали прежний результат
    `legacy=4765`, `python=4692` (`delta=-73`), то есть гипотеза по alias
    **не подтвердилась**.
  - статус `LP-P6D-001`: **не закрыт**; подтвержден следующий минимальный шаг —
    точечно разбирать composition `eligible_gate_reject` (player lifecycle /
    reward eligibility transitions around earliest legacy-only windows:
    `2024-01-01 19:41:51` `de_mirage`, `2024-01-01 20:47:23` `cs_mansion`).
- 2026-04-28: `LP-P6D-001` продолжен от актуального хвоста `4765` vs `4692`.
  Root cause по `eligible_gate_reject`: legacy Perl `rewardTeam` проходит по
  in-memory `%g_players`, а `doEvent_TeamSelection` делает игрока trackable без
  обязательного `entered the game`; Python требовал `reward_eligible_players`
  (Entry-only) и отбрасывал игроков с валидным team state. Минимальный патч:
  `storage._reward_team_players` теперь допускает игрока, если он либо
  `reward_eligible`, либо уже в `server_active_players`; connected-only без
  trackable team по-прежнему отсекается. Regression test:
  `test_team_bonus_awards_trackable_team_player_without_entry`.
  Валидация:
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests/test_storage.py`
    -> `41 passed`;
  - `PYTHONPATH=scripts;scripts/proxy_daemon_py python -m pytest scripts/hlstats_py/tests`
    -> `107 passed`;
  - Python narrow replay:
    `Run-ContourFtpArtifacts.ps1 -SkipBuild -UseDumpRestore -SkipGeoIp -MaxImportFiles 1000`
    -> `status=ok`, `elapsed_seconds=331.5`;
  - legacy reference replay restored from dump and replayed the same first
    `1000` logs -> `processed=1000`, `errors=0`;
  - `compare_stats_dbs.py --max-examples 20` saved as
    `runtime-db-diff-p6d-narrow-1000-20260428-175918.md`.
  Новый срез `hlstats_Events_TeamBonuses`: `legacy=4765`, `python=4773`
  (дельта `+8`, улучшение на `81` строк к предыдущему `-73`). `LP-P6D-001`
  остаётся открыт; следующий минимальный разбор — residual `+8` по
  grouped action/map/time и identity/name-only examples, не page audit.
