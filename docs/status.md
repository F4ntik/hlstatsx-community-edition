# Status: Standalone Python+i18n Product Lane

## Snapshot

- 2026-09-12, визуальное продолжение: добавлены «Чётко / Мягко», разные цвета каналов
  в «Оба», инверсия подложки и термин «тепловая карта». Импорт BSP автоматически
  рассчитывает поверхности. Целевые проверки, сравнение в браузере и обзор пройдены;
  исходники подготовлены к сборке install/upgrade. Движок и SQL не изменены.
  [Состав кандидата и граница проверки](release-heatmap-20260912.md).

- 2026-09-12, отдельная экспериментальная ветка: интеграция подготовленных BSP-поверхностей
  в действующий Explorer реализована. Включены все 25 карт; исходные XYZ распределяются
  до объединения обычных ячеек, стены и выбранные этажи ограничивают распространение.
  При несовпадении картинки/проекции, ошибке файла или покрытии ниже 70% явно включается
  обычная карта. Проверки PHP/JS пройдены; [измерения](audits/bsp-surfaces-performance-20260912.json)
  показывают 15–31 мс для de_dust2 и 50–74 мс для самой крупной as_oilrig на положительном
  поле. Это вычисления по суммарным весам до миллиона, не миллион строк БД: исходный
  предел 250 000 строк сохранён. Итоговая локальная HTTP/браузерная проверка и
  независимый обзор пройдены: [границы и результаты](audits/bsp-heatmap-integration-20260912.md).
  Публичного выпуска нет.

- 2026-09-12: в отдельной экспериментальной ветке подготовлен автономный
  [BSP-пример распространения тепла](audits/modern-heatmap-explorer/bsp-walls-20260912/README.md)
  на реальной de_dust2. Геометрия пола, проверка просвета и соседних переходов
  уменьшают перенос за стену при сохранении полного веса; высоты не смешиваются.
  События синтетические; это не интеграция в продукт. Шесть малых и две реальные
  BSP-проверки пройдены; интерактивная браузерная проверка не выполнена.

- Last updated: `2026-09-09`
- September release fixes and the Explorer snapshot are integrated on
  `release/i18n-20260909`. See [release preparation](release-preparation-20260909.md)
  for the review closure, verified checks and exact artifact acceptance boundary.
- WEB-01 through WEB-05 hardening is integrated:
  classic admin mutations use a session CSRF token and registry access gate;
  passwords use modern hashes with one-time MD5 upgrade and password-free,
  rotating sessions; the public dispatcher revalidates the database password,
  expiry and current access level before routing; the web updater is CLI-only;
  after numbered migrations, its trusted CLI verifies the physical password
  column and repairs only a narrower `varchar` without rewriting newer version
  metadata; and heatmap administration checks the current database password
  fingerprint before reads or mutations.
  isolated MariaDB checks verified a fresh schema 83 and a real 82-to-83 CLI
  upgrade. HTTP checks passed for legacy hash upgrade, special-character
  passwords, CSRF, restricted reset actions and heatmap session revocation.
  Package publication requires the exact-commit acceptance receipt; historical
  acceptance below must not be substituted for that receipt.
- BSP outlines for the 25 native maps are now bundled web assets and load
  automatically in the admin editor, with a visible show/hide control and an
  image-identity check. Fresh installations use the matching existing SQL seeds
  and base images; manual SVG import remains available for custom images.
- All 25 installed Counter-Strike maps with matching BSP/BMP/TXT overviews now
  have native-frame base images, thumbnails and matching seed/local settings.
  Actual HTTP images/configurations passed for all 25 on port 8382; geometry and
  extraction instructions are in `docs/heatmap-bsp-registration.md` and
  `docs/audits/modern-heatmap-explorer/steam-maps-20260908/README.md`.
  These user-requested local asset replacements supersede the earlier no-copy
  snapshot below. No publication or automatic floor/wall reconstruction occurred.
- Floor/wall settings now have a web editor: draw allowed or excluded polygons,
  undo/cancel corners, remove individual outlines and upload floor JPEGs. Saving
  floors against an unchanged projection uses a preview token without requiring
  landmarks again. Calibration changes retain the landmark gate. See
  `docs/plans/2026-09-08-heatmap-floor-editor.md` and the floor-editor section in
  `docs/audits/modern-heatmap-explorer/improvements-20260908/README.md`.
- Heatmap usability/spatial-floor follow-up passed focused PHP/JS checks and
  real browser review on disposable port 8382. It adds UTC date inputs, numeric
  reference scales, optional floor polygons/same-frame images, constrained
  presentation and visual calibration report import. BSP revision persistence
  is explicitly excluded. The temporary region/account were removed and exact
  configuration readback matched the backup. See
  `docs/audits/modern-heatmap-explorer/improvements-20260908/README.md` and
  `docs/heatmap-regions-and-scale.md`. These changes are included in the release candidate snapshot.
- Heatmap BSP/presentation follow-up passed focused checks and browser review
  in a separate local runtime on port 8382. Evidence and screenshots are in
  `docs/audits/modern-heatmap-explorer/improvements-20260907/README.md`.
  The GoldSrc overview importer used the wrong ZOOM and
  origin convention; the earlier September 2 de_dust2 candidate is superseded.
  The new offline BSP tool reads actual v30 geometry, registers the native
  overview to the served image, emits product settings and checks them with
  the production transform. See `docs/heatmap-bsp-registration.md` and
  `docs/plans/2026-09-07-heatmap-bsp-and-presentation.md`. The original runtime
  and its calibration remain untouched; historical acceptance below applies
  only to its named commit, not to this follow-up diff.
- Modern Heatmap Explorer is `SOURCE-READY`, locally `RUNTIME-ACCEPTED`, and
  `RELEASE-READY` only as a local candidate at exact implementation commit
  `44f3af97db46107f3ab9b595b3c32b3e5c2c7986`. The visibility correction closes
  the previously missed sparse-grid normalization defect: the accepted
  `de_dust2` scene has 175 source events, 301 occupied bins in a 128×103 grid,
  and raw maximum 12. The old renderer produced singleton/peak alpha only
  `0.009259/0.138889` and zero colored pixels above alpha 0.20; the corrected
  transfer produces ordinary singleton intensity `0.258199`, peak `1.0`, and
  35,766 qualifying colored pixels in both Color and Mono. Difference has 161
  bins and 3,740 qualifying warm/cool pixels against a required 189. Heatmap
  hotspots are obvious without zoom; Color/Mono changes only the background,
  with the same raw WebGL hash. Source gates passed 302 product tests with an
  explicit local `PYTHONPATH`, 91 replay tests, 18 focused route/coordinate
  tests, compileall, Node syntax/smoke, and PHP heatmap/i18n smoke. The broad
  browser matrix, objective Color/Mono/Difference pixel gates, and independent
  reviewer all pass (`ship`, zero findings). Final manual readback restored
  exact mode `0`, original config/assets/counter/users/fixtures/
  auto-increments/sessions and no mounts. See
  `docs/audits/modern-heatmap-explorer/runtime-acceptance.md` and
  `docs/audits/modern-heatmap-explorer/evidence/acceptance-2026-09-02.json`.
  No push, deployment, publication, or
  production release acceptance occurred.
- Historical release snapshot: Counter-Strike/GoldSrc color overview BMP/TXT files were researched locally,
  but no Valve/Steam asset was copied or shipped. The product uses repository
  images with Color/Mono grading. Optional operator-side GoldSrc import remains
  a separate licensing and feature decision.
- The release-clean P1 hardening closure for post-ingest maintenance is
  accepted. The canonical runner now stages only the selected FTP logs,
  performs legacy-compatible `inactive -> awards -> ribbons -> strict GeoIP`
  after both fresh imports, saves failed native tool output before fail-close,
  and treats legacy English as the reference while testing the Python product
  in EN and RU. The clean `prefix-100`
  `20260722-maintenance-prefix-100-r8` and the final clean `narrow-1000`
  `20260722-maintenance-narrow-1000-r1` both pass logical DB comparison. The
  latter has shared manifest SHA
  `95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a`,
  `323` players, `5464` frags, `998` awards, `9` player awards, `8` ribbons,
  and matching full GeoIP counts `250/250/219/221/250`. Focused calculator and
  replay-helper tests total `103 passed`. The full report is
  `docs/audits/legacy-python-parity-20260423/maintenance-parity-20260722.md`.
- Heatmap work is active on `feature/heatmap-projection-calibration`: the web
  layer now has a DB-backed canvas overlay for `mapinfo`, a player-scoped
  heatmap widget in `playerinfo` Maps & Servers, hover metadata for top
  killers/victims/players, and separate warm/cool color channels for kills and
  deaths. Static `<map>-kill.jpg` / `<map>-kill-thumb.jpg` generation remains
  the compatibility fallback. Projection calibration is still the main open
  quality gate: overview `.txt` files are useful seeds, but each `{game,map}`
  still needs DB-first in-bounds diagnostics and manual/imported calibration
  before final `--disablecache` regeneration.
- The 2026-07-17 evidence review is source-ready for the import/heatmap
  contract: the valid narrow-1000 manifest pair is recorded separately from
  stale `*-1000` files that are actually full-41513 captures. Batch FTP/direct
  import now require an ignored-lines manifest when parse errors are continued,
  publish final manifests only after successful import, and use canonical
  labels plus unique evidence run ids.
- Heatmap rotate is now a normalized `0..3` quarter-turn contract with shared
  crop normalization across PHP, JavaScript, Python, and the JPEG fallback.
  The versioned rotate migration remains read-only until a distribution check,
  backup, and separate runtime gate; stored `2/3` values are a manual stop.
  Its eventual row conversion and version marker are now applied atomically
  with rollback on marker failure. Non-positive/non-finite projection scales
  are normalized to a safe positive value in render paths, and calibration CLI
  input rejects invalid scale values before any apply.
- Narrow runtime acceptance for this review is now evidenced by a fresh Docker
  `-UseDumpRestore` dual-contour run under
  `narrow-1000/20260717-narrow-1000-r1`: the final input manifests are
  byte-identical (`1000` lines, SHA
  `95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a`), both
  drop/ignore manifests are published, metadata anchors match
  (`323/5464/4765/0`), and normalized SQL snapshot sections match. The raw
  compare retains only the documented `hlstats_Players` GeoIP-only residual
  (`250` paired rows, `0` non-GeoIP pairs); no new replay drift was observed.
  PHP/GD smoke passed in the Docker web image because local PHP CLI is not
  installed. A separately labelled `full-41513` run completed with matching
  input manifests and explicit Python ignored-line evidence, but its full
  stable-key compare remains diagnostic/non-green; see
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-full-41513-20260717-full-41513-r1.md`.
  A read-only heatmap check against the running Python DB found
  `rotate={0:442}` with no stored `2/3` values. A verified pre-migration
  backup is retained as
  `docs/audits/legacy-python-parity-20260423/runtime-python-db-backup-before-heatmap-migration-20260718-064706.sql.gz`
  (SHA-256
  `BEC10451F6913DD695DEF1CEFB4EF8138B08B1D353AF2AEC02A58524E7B170F4`).
  The explicit runtime approval for either DB-mutating `--apply` and the
  post-migration manual `--disablecache` wizard/canvas/static-JPEG gate remain
  open; see
  `runtime-heatmap-migration-gate-20260718.md`.
  The separate calibration backup/migration plus manual static-JPEG/UI gate
  remains intentionally open.
- `P6d` is no longer an active residual hunt for `Entries`, `ChangeTeam`,
  `PlayerNames`, `Players_History`, or `TeamBonuses`; those gates are closed
  for the supported narrow/default Python contour.
- The bounded Statsme counter-delta slice is source- and runtime-accepted:
  427 explicit product tests passed; prefix r2 and fresh no-reuse narrow r1
  retain only the accepted GeoIP-only `hlstats_Players` residual. The
  product-path Python-only import, with accepted legacy reused, measured
  `138.4203224 s` / `4,451.15 records/s` against fresh legacy `153.389 s`
  (`9.76%` less elapsed; `1.108x` same-corpus elapsed ratio, not normalized
  throughput). Its manifest is
  1,000 files, SHA
  `95BFDB5951922C0C36AAB2C5263E1880B227E845B34C9262939B028D0FBEBE8A`, with
  ignored=0 and anchors `323/5464/4765/0/1`. Disposable profiling observed
  `Connection.query` calls `124,630 -> 60,785` (`-51.2%`), but the profiled
  `462.691 s` and isolated-host unprofiled `246.362 s` samples are
  environmentally non-comparable and do not justify an incremental wall-speed
  promotion. Evidence:
  `docs/audits/legacy-python-parity-20260423/performance-db-sql-opt-narrow-1000-20260718-statsme-bench-r1/` and
  `runtime-product-timing-20260718-statsme-product-timing-r1-legacy-reference.md`.
- The active autonomy track is now release-readiness/product hardening:
  docs truth, repository-wide CI, package/runtime boundaries, lifecycle and
  control-plane hardening, explicit DB modes, parity acceptance automation,
  PHP EN/RU stabilization, and release-readiness observability.
- If a future parity-affecting change creates a new residual, restart from
  [`docs/parity-debug-pipeline.md`](parity-debug-pipeline.md) and
  [`docs/replay-fast-path.md`](replay-fast-path.md), then write evidence into
  `docs/audits/legacy-python-parity-20260423/`.
- A separate full-corpus first-divergence track now exists for cases where both
  completed contours already processed the same sorted corpus but final anchors
  differ. Use
  [`docs/full-corpus-first-divergence.md`](full-corpus-first-divergence.md);
  do not rerun the full legacy replay just to localize the first mismatch.

Current parity state:

- The full-corpus first-divergence root cause for the `L0628063.log` opening
  window is closed at the unit/runtime-state level. Python previously treated a
  real Steam player seen once with transient `userid <= 0` as a permanent bot
  for the whole replay process; for `1:45686725` this suppressed the later
  `Mep3ocTb` `ChangeTeam` row, kept `MinPlayers=4` under-counted, and gated the
  first legacy-only `Frags`/`TeamBonuses` rows on `2023-06-28 23:43..23:46`.
  Persistent bot classification is now based on BOT-style unique IDs, while
  name-only `userid <= 0` descriptors remain bot-like. The fresh main-window
  `L0628063` replay now matches legacy on the requested `ChangeTeam`,
  `Frags`, `TeamBonuses`, and `Entries` anchors; the remaining narrow compare
  drift is the separate `Players` GeoIP-only split plus one Python-only
  `kill_streak_2` `PlayerActions` row at `2023-06-28 23:44:48`. That residual
  is tracked as a must-fix because it changes a visible action counter; legacy
  remains the reference baseline, but it can still contain its own bug, so the
  policy decision comes from the compare impact, not legacy infallibility.
  Targeted regression, real `L0628063` window harness, and storage/runtime
  tests pass.
- The defuse-boundary `kill_streak_*` residual is closed. The follow-up
  `L0102207.log` case showed that a recorded `Defused_The_Bomb` should not
  suppress the defuser's pending round-end streak; suppression is now limited
  to defuse actions that are gated by min-player policy. The fresh full
  `narrow-1000` compare no longer lists `hlstats_Actions` or
  `hlstats_Events_PlayerActions`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260518-after-gated-defuse-suppression.md`.
- The first `hlstats_Events_TeamBonuses` hostage-rescue residual is closed.
  `Rescued_A_Hostage` team rewards now bypass the round-status gate in the
  same player-trigger path legacy uses after `Round_End`. The fresh full
  `narrow-1000` compare is `4765/4737`, with `28` legacy-only rows and `0`
  python-only rows. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260519-after-rescue-roundstatus.md`.
- The planted-bomb `hlstats_Events_TeamBonuses` residual cluster is closed.
  Legacy-style post-round team rewards are allowlisted for
  `cstrike:Planted_The_Bomb` in the player-action path alongside
  `Rescued_A_Hostage`. Targeted storage tests, `hlstats-worker` rebuild,
  single-log `L0101059`, and fresh full `narrow-1000` replay were rerun. The
  fresh compare is `4765/4764`, with `1` legacy-only row and `0` python-only
  rows. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260519-after-planted-roundstatus.md`.
- The `L0102211.log` `Dance Bear` / `CTs_Win` TeamBonuses lifecycle residual
  is closed. Perl evidence showed that `rewardTeam` rewards the current
  team-bound player set before the periodic idle timeout scan; generic
  damage-only lines still must not reactivate team-reward membership. Python
  now records the event before the timeout cleanup and uses the legacy timeout
  scan upper bound for deterministic replay. Fresh single-log evidence has
  `hlstats_Events_TeamBonuses legacy=156`, `python=156`, and no
  `uniqueId`-keyed differences. Fresh full `narrow-1000` evidence has
  `legacy=4753`, `python=4753`, and no stable-key TeamBonuses differences.
  Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260523-after-team-bonus-timeout-cadence.md`.
- P6d-M4 `hlstats_Players` is closed as a GeoIP-only contour/policy rule. The
  raw replay compare, before maintenance GeoIP backfill, can show `323/323` with
  `250` legacy-only normalized rows and `250` python-only normalized rows;
  the field classifier reports `250 geoip_only_rows` and `0 non_geoip_rows`.
  Only `country` and `flag` differ, while `lastAddress`, `kills`, `deaths`,
  `suicides`, `skill`, `shots`, `hits`, `teamkills`, `headshots`,
  `kill_streak`, `death_streak`, `activity`, and `hideranking` match. Direct
  SQL anchors confirm `SELECT COUNT(*) FROM hlstats_Players WHERE country <> ''
  OR flag <> '';` as `legacy=250` and `python=0`. Legacy `getAddress` writes
  `lastAddress`, `geoLookup` writes only `country`/`flag`, and `flushDB()`
  stats/session fields do not write `country`/`flag`; on the Python path,
  `storage.py` runtime writes `lastAddress`/stats/session while GeoIP fields
  are maintenance/backfill via `hlstats_awards_py` and not stdin replay. Raw
  replay parity may therefore carry this accepted GeoIP-only diff; current
  release-clean parity uses the canonical dual runner's shared
  inactive/awards/ribbons/GeoIP maintenance receipt, after which
  `hlstats_Players` should disappear from the compare. No minimal runtime fix
  remains for `hlstats_Players`.
- The first `hlstats_PlayerNames` anchor is stateful, not a clean isolated
  single-log case. The `Player21` / `Dim$0n` / `Dim$on` residual centers on
  `0:1161623468` around `L0102212.log:487`, but isolated `L0102212` produces a
  different alias split than the neighboring-log cluster. A tested hypothesis
  to flush alias rollups on `changed name to` was rejected and not retained.
  Evidence lives in parity traces:
  `p6d-playernames-player21-L0102212-before-alias-flush`,
  `p6d-playernames-player21-L0102212-after-alias-flush-full`, and
  `p6d-playernames-player21-L0102209-L0102213-after-alias-flush`.
- The stateful `Player21` / `Dim$0n` / `Dim$on` PlayerNames cluster is now
  closed. Legacy-first review showed that ordinary same-live-object log
  descriptors do not rename the active player object; only first sight,
  explicit name-change/userid-rollover, or reopened closed objects should
  update the Python runtime alias. The same-cluster replay no longer lists
  `hlstats_PlayerNames`, and a fresh clean `narrow-1000` reduces
  `hlstats_PlayerNames` to `0` legacy-only / `1` python-only normalized row:
  the already-known `XYU` / `unnamed` alias (`0:552632503`). Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260523-after-playernames-live-alias.md`.
- The rejected `changed name to` fix was a process miss, not a valid partial
  fix: the local unit test encoded an oversimplified alias-flush rule before
  proving that the broad residual was caused by name-change flushing. Legacy
  Perl does mark the player dirty before replacing the name, but replay evidence
  shows the residual also depends on prior/following log state, timeout/flush
  cadence, and possibly duplicate weaponstats/name lifecycle ordering. Because
  the full `L0102212` and `L0102209..L0102213` replays still showed
  `PlayerNames` drift after the attempted change, the code and test were
  rolled back; only the analysis notes were kept.
- The first `Players_History` streak hypothesis was also rejected and not
  retained. Changing Python to pass current event-level
  `kill_streak`/`death_streak` values instead of cached max streak values moved
  some `Rakza` kill-streak columns in the right direction, but broadened the
  fresh `narrow-1000` `hlstats_Players_History` normalized residual from
  `50/50` to `106/106`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-history-streak-current-hypothesis-rejected-20260524.md`.
  The next candidate needs to trace legacy `flushDB` sampling boundaries rather
  than changing every event-level rollup.
- The follow-up `Players_History` flush-sampling fix is retained. Legacy-first
  review showed that `kill_streak` is promoted when a life ends, including
  single-kill lives, while derived `kill_streak_N` actions are emitted only for
  streaks greater than one; `flushDB()` later samples those live-object max
  fields into `Players` and `Players_History`. Python now promotes max
  kill-streak only at `_end_kill_streak`, includes max streaks in connection
  flush sampling, and clears max streak cache on live-object close. Targeted
  storage/validation tests pass, and fresh `narrow-1000` reduced
  `hlstats_Players_History` from `50/50` to `14/14`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-history-flush-sampling-20260524.md`.
- A follow-up `Players_History` victim flush-boundary fix is in place at the
  unit level. Legacy review confirmed that an ordinary frag immediately
  flushes the killer object, while the victim's deaths/session skill remain in
  the live object until the next `flushDB()` boundary; Python now defers
  victim-side history rollups and writes them on the later player flush date.
  Targeted storage tests pass, including the new cross-day victim-flush
  regression. Single-log `L0103146` replay was rerun with a `30/30` guard
  window: the main sliced log still has the known artificial current-date
  `Rakza` seed row, while the guard no longer lists `hlstats_Players_History`
  and fails only on the pre-existing `hlstats_Servers` slice residual. Evidence:
  `scripts/replay_baseline/artifacts/parity-traces/p6d-history-rakza-L0103146-victim-flush/`.
- The broad `Players_History` flush-boundary fix is retained. A fresh
  `narrow-1000` run after the victim-specific fix reduced
  `hlstats_Players_History` from the previous `14/14` residual to `10/10`;
  the remaining rows were Jan 6/Jan 7 flush-boundary splits for `Mk`
  (`1:815451478`), `FRANKESTINE` (`0:1089759883`), `Johnny`
  (`0:164297241`), `pardesiboi404` (`0:109115526`), and `Jerry AK`
  (`0:1601618021`). Legacy review confirmed that `updateDB()` only marks the
  live player dirty and `flushDB()` samples the live object into
  `hlstats_Players_History`, so Python now defers all player history
  stat/skill rollups to the live-object flush boundary. The final fresh
  `narrow-1000` compare no longer lists `hlstats_Players_History`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260525-after-history-flush-and-streak-gap-compare.txt`.
- The previously suspected `Dance Bear` / `CTs_Win`
  `hlstats_Events_TeamBonuses` row did not resurface in the final broad
  contour. The final `narrow-1000` anchors are `legacy=4765`,
  `python=4765`, and the logical compare no longer lists
  `hlstats_Events_TeamBonuses`.
- A final strict GeoIP rerun was required after the broad replay because the
  replay importer repopulates `lastAddress` but does not perform maintenance
  backfill. Before the rerun, Python still had `250` players with
  `lastAddress <> ''` and empty `flag`/`country`; after
  `hlstats_awards_py --geoip`, that count returned to `0` and
  `hlstats_Players` disappeared from the broad compare. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260525-final-after-geoip-compare.txt`.
- The remaining `XYU` / `unnamed` `hlstats_PlayerNames` residual is closed.
  Legacy evidence showed that the player object for `0:552632503` is created
  from a blank-name connect in `L0103048.log`, so later ordinary `unnamed`
  descriptors must not create an alias row; only the explicit
  `changed name to "XYU"` event should touch `hlstats_PlayerNames`. Python now
  preserves the blank constructor alias state without writing a blank/unnamed
  row. Fresh broad `narrow-1000` plus strict GeoIP backfill reduced
  `hlstats_PlayerNames` from `0/1` to absent from the logical compare; direct
  anchors are `legacy=415`, `python=415`, and both DBs now have only
  `(playerId=203, name=XYU)` for `0:552632503`. Evidence:
  `docs/audits/legacy-python-parity-20260423/runtime-db-diff-p6d-narrow-1000-20260525-after-playernames-blank-alias-compare.txt`.
- The `hlstats_Events_Entries` residual is now confirmed closed for the
  current narrow contour/default Python path. After Docker Desktop was
  started, the narrow contour command succeeded and the compare command
  `python scripts/replay_baseline/compare_stats_dbs.py --max-examples 20`
  no longer lists `hlstats_Events_Entries`; the direct counts are
  `legacy=0`, `python=0`. Evidence was recorded in
  `docs/audits/legacy-python-parity-20260423/python-sql-snapshot-1000.txt`
  and `scripts/replay_baseline/comparison/.parity-state/20260526-061001.json`.
- P6d-M5 `hlstats_Events_ChangeTeam` is closed after the second TDD fix and
  the narrow-1000 replay/compare. Root cause: Python lost the blank team seed
  after userid rollover/blank reconnect/entry, so the first ignored
  time/latency `<UNASSIGNED>` saw `previous_team=None` and suppressed the
  implicit `ChangeTeam`; legacy records descriptor-driven nonblank team
  transitions. The fix keeps `seed_blank_team_on_rollover` for ignored
  time/latency priming and now also uses it for connect in `_record_connection`,
  while blank seeding stays guarded by closed-player checks. Targeted tests
  `test_rollover_blank_status_followed_by_unassigned_trigger_emits_implicit_change_team`
  and `test_rollover_blank_connect_and_blank_entry_before_unassigned_trigger_emits_implicit_change_team`
  passed; `unassigned or team_change or rollover` was `12/12`,
  `test_storage.py` was `133/133`, and the historical raw comparison rerun
  with `-ReuseValidLegacy` reused valid legacy from run state
  `20260526-081158.json`. The final compare had no
  `hlstats_Events_ChangeTeam` residual. The only raw-replay difference was the
  accepted pre-backfill `hlstats_Players` GeoIP-only contour/policy diff
  (`323/323`, `250` legacy-only rows, `250` python-only rows); release-clean
  validation now uses the canonical runner maintenance receipt. SQL anchors for
  `ChangeTeam` were `legacy total=1345/unassigned=47` and `python
  total=1345/unassigned=47`.

## In Progress

- [ ] Full-corpus first-divergence investigation remains a diagnostic track,
  separate from the closed supported `narrow-1000` P6d contour. The fresh
  `full-41513/20260717-full-41513-r1` run now has byte-identical input manifests,
  same-run drop/ignore artifacts, SQL snapshots, contour metadata, and a
  recorded non-green stable-key compare in
  `runtime-db-diff-full-41513-20260717-full-41513-r1.md`; next work, if needed,
  is prefix/window localization rather than another full baseline replay.

## Done

- Accepted the heatmap runtime gate after preserving both expensive
  `full-41513` databases as verified restorable dumps. The guarded projection
  migration advanced version `1 -> 2`, retained `{0:442}` and all Python
  replay anchors, and passed one-map admin preview, canvas-toggle, and served
  static-JPEG checks. Browser acceptance also found and fixed a stored-config
  load regression; initial/map/Load requests no longer replace DB values with
  default form controls. Processing and disposable full-state DB profiles show
  that SQL round trips dominate (`4613` executions for `2287` records,
  `450.67 records/s`) while parser-only work is about `3.3%` of import wall
  time. The next performance boundary is parity-safe SQL reduction/batching;
  any first Rust stage should remain an optional parser backend behind the
  existing rollback seam.
- In the historical Windows source-only pass, updated the heatmap admin
  calibration editor so the visual selection box now
  follows the actual overlay point bounds instead of the full map canvas,
  resize handles adjust projection scale with offset compensation, and rotate
  cycles through `0/90/180/270` quarter-turn states while preserving existing
  `rotate=1` compatibility. Targeted Python heatmap tests, JS syntax check, and
  Python compile checks passed; that pass could not run local PHP because
  `php` was unavailable on the Windows `PATH`. The final candidate later passed
  the mounted Docker PHP smoke and lint recorded in the current acceptance.
- Added `docs/README.md` as the documentation map for this product lane so
  canonical task entrypoints are separated from historical migration and i18n
  notes.
- Added `docs/full-corpus-first-divergence.md` and parameterized
  `Run-DualContour-1000.ps1` artifact labels so prefix/window replay runs can
  preserve manifests, dropped-line files, SQL snapshots, and contour metadata
  without overwriting the retained `narrow-1000` evidence.
- Prepared the `hlstatsx_py` release-line cleanup: obsolete local Perl
  production/runtime and maintenance entrypoints were removed from the active
  product lane, while replay/parity harnesses, retained evidence, tests, logs,
  and Python runtime/maintenance replacements remain in place. The admin
  runtime control page now uses a runtime-oriented route/key instead of the old
  Perl-control naming. The Python import path remains `hlstats_py`.
- Restored legacy-style daily `last_skill_change` persistence for the Python
  runtime so the existing player/clan/country ranking arrows render from live
  replay data again. The web layer already consumed `hlstats_Players.last_skill_change`;
  the missing piece was runtime flush parity. Python now persists daily
  cumulative skill deltas to `hlstats_Players.last_skill_change`, keeps
  `hlstats_Players_History.skill_change` on the per-day history row, resets
  the cumulative value on day rollover, and keeps ignored-bot trend neutral.
  Targeted storage tests passed, the broader `test_runtime_decisions.py` +
  `test_storage.py` suite passed, a historical raw `Run-DualContour-1000`
  reuse run completed, the raw `compare_stats_dbs.py --max-examples 20` report still had
  only the accepted pre-backfill GeoIP-only `hlstats_Players` diff, and
  replay-backed `mode=players` HTML on the Python contour now contains rendered
  `t0/t1/t2` trend icons.
- Closed the earlier `hlstats_Servers.act_players` residual and removed it from
  the active parity gate.
- Added the single-log parity-debug workflow on
  `experiment/parity-trace-harness`, including log locating, safe-window
  extraction, and focused DB write tracing.
- Closed the local GoldSrc `Bomb_Defused` / `round_status` projection bug that
  was causing the Python-only Rakza `kill_streak_2` drain before replay
  revalidation.
- Closed the server-wide defuse-boundary suppression bug that dropped other
  players' round-end `kill_streak_*` rows after `Defused_The_Bomb` /
  `Bomb_Defused`. Targeted storage tests, `hlstats-worker` rebuild,
  single-log `L0102204`, and full `narrow-1000` replay were rerun.
- Closed the first TeamBonuses hostage-rescue residual from `L0101061.log`
  (`2024-01-01 20:33:47`, `cs_mansion`, `Rescued_A_Hostage`) with targeted
  storage tests, `hlstats-worker` rebuild, single-log replay, and full
  `narrow-1000` replay.
- Closed the planted-bomb TeamBonuses residual cluster from `L0101059.log`
  (`2024-01-01 19:40:12`, `de_mirage`, `Planted_The_Bomb`) with targeted
  storage tests, `hlstats-worker` rebuild, single-log replay, and full
  `narrow-1000` replay.
- Closed the single-log `Dance Bear` TeamBonuses lifecycle residual from
  `L0102211.log` by aligning Python with legacy idle auto-disconnect and by
  not treating generic damage-only lines as team-reward reactivation. A
  follow-up timeout-cadence fix moved Python idle cleanup after the current
  event and rescheduled cleanup on the legacy timeout scan upper bound. Targeted
  storage/runtime tests, single-log replay, and full `narrow-1000` confirmation
  are green for `hlstats_Events_TeamBonuses`.
- Closed `P6d-M1`: `hlstats_Events_TeamBonuses` no longer appears in the fresh
  logical compare, and direct stable-key SQL reports `legacy=4753`,
  `python=4753`, with empty legacy-only and python-only sets.
- Closed `P6d-M2` for the current contour: `ChangeTeam`, `Connects`, `Chat`,
  and `PlayerActions` no longer appear in the fresh logical compare.
- Closed `hlstats_Events_Entries` for the current narrow contour/default Python
  path after targeted unit coverage and replay promotion; direct counts are
  `legacy=0`, `python=0`.
- Closed the stateful `Player21` / `Dim$0n` / `Dim$on` PlayerNames alias
  attribution cluster by preserving the legacy live-object constructor alias
  across ordinary same-live-object descriptors. Targeted storage tests,
  `hlstats-worker` rebuild, same-cluster replay, and fresh full `narrow-1000`
  were rerun; the later `XYU` / `unnamed` alias residual is also closed.
- Reduced `hlstats_Players_History` from `50/50` to `14/14` by aligning Python
  kill-streak sampling with legacy `endKillStreak` / `flushDB` boundaries.
- Closed the remaining broad `hlstats_Players_History` residual by deferring
  all player history stat/skill rollups to legacy-style player `flushDB`
  boundaries. The path went from `14/14` before the victim fix, to `10/10`
  after the victim-only fix, to absent from the final broad compare.
- Closed the extra `Fat` (`1:58816828`) `hlstats_Players.kill_streak` drift by
  continuing pending streak flushes even when `connection_time` is clamped to
  zero for gaps above `600` seconds.
- Closed the broad `hlstats_Players` GeoIP residual by rerunning strict
  maintenance GeoIP backfill after the final replay. The path went from
  `250/250` `country`/`flag` diffs to absent from the final broad compare, and
  Python players with `lastAddress <> ''` and empty `flag` dropped from `250`
  to `0`.
- Closed the final real `hlstats_PlayerNames` drift for `XYU`
  (`0:552632503`) by treating blank-name connects as a constructed live object
  state without persisting a placeholder alias. The broad logical compare moved
  from `hlstats_PlayerNames` `0/1` to `0/0`.
- Completed Phase 0 of `docs/autonomy-work-plan-20260601.md`: `docs/status.md`,
  `docs/plans.md`, and `docs/test-plan.md` now agree that P6d is closed for the
  supported contour, stale reopened parity items are not active work, and the
  GeoIP rule is raw replay diff before backfill versus release-clean parity
  after post-replay `hlstats_awards_py --geoip`.
- Completed Phase 1 of `docs/autonomy-work-plan-20260601.md`: the old
  proxy-only workflow was replaced by repository-wide product CI covering
  `proxy_daemon_py` lint/type/test, `hlstats_py` tests, `replay_baseline`
  helper tests, PHP syntax lint for `web/`, and docs sanity checks. A
  scheduled/manual nightly parity placeholder now runs lightweight replay
  helper smoke while the full Docker-backed parity gate remains deferred to
  Phase 7. Local Phase 1 validation passed for `scripts/replay_baseline/tests`,
  `scripts/hlstats_py/tests`, and `scripts/proxy_daemon_py/tests`; local PHP
  lint could not be run because the Windows workspace does not currently have
  `php` on `PATH`, while GitHub CI installs PHP 8.2 explicitly.
- Completed Phase 2 of `docs/autonomy-work-plan-20260601.md`: added regression
  coverage around the current `SyncDatabaseAdapter._ensure_connection()`
  behavior without changing production code or reopening the stale reconnect
  bugfix. The new tests cover lazy connection creation, disabled ping,
  successful ping reuse, `ping(reconnect=False)`, and reconnect after a failed
  ping. `hlstats_py` storage tests now also pin the stdin batch skip-ping bridge
  that uses this shared adapter. Targeted selected tests passed with
  `--coverage-threshold=0` because the proxy test harness has a global coverage
  gate that is not meaningful for a `-k` slice; the full
  `scripts/proxy_daemon_py/tests` suite passed with the normal coverage gate.
- Completed Phase 3 of `docs/autonomy-work-plan-20260601.md`: introduced
  `hlx_core` as the explicit shared infrastructure package for config, DB,
  logging, UDP transport helpers, and the DB-config bootstrap helper. Focused
  product consumers (`hlstats_py`, `hlstats_ftp_py`, `hlstats_awards_py`,
  `hlstats_resolve_py`, and `import_bans_py`) now import shared infrastructure
  from `hlx_core` instead of the daemon package, while `proxy_daemon_py` keeps
  compatibility wrappers for its own public API and daemon-specific modules.
  `hlstats_py` is now an installable package with a path dependency on
  `hlx_core`; product CI installs it and runs an import smoke instead of using
  the old `scripts:scripts/proxy_daemon_py` bridge. Local validation passed for
  source imports, isolated venv install/import smoke, `hlstats_py` +
  `hlstats_resolve_py` tests, and the full `proxy_daemon_py` suite with the
  normal coverage gate.
- Completed Phase 4 of `docs/autonomy-work-plan-20260601.md`:
  `scripts/run_proxy_py` and `scripts/run_hlstats_py` now share
  `scripts/lib/process_lifecycle.sh`, stop with `SIGTERM` first, wait up to
  `HLX_STOP_TIMEOUT`, and reserve `SIGKILL` for timeout fallback. Deployment
  notes in `docs/python_migration_usage_guide.md` direct service templates to
  call launcher `stop`/`restart` instead of hard-killing runtime processes.
  Validation used Git Bash for `bash -n`, smoke-tested both graceful PID-file
  stop and TERM-ignoring fallback stop, ran `git diff --check` and docs UTF-8
  reads, and covered the runtime signal-adjacent Python slices. The selected
  proxy slice was run with `--coverage-threshold=0` because the package-level
  coverage gate is not meaningful for a tiny lifecycle-adjacent subset.
- Completed Phase 5 of `docs/autonomy-work-plan-20260601.md`:
  control-plane handling now separates read-only loopback commands from
  mutating commands. `hlstats_py` still allows direct loopback `HEARTBEAT` and
  `SERVERLIST`, but `RELOAD` and `KILL` require a valid proxied `PROXY Key`
  envelope. `proxy_daemon_py` keeps its real command surface (`HEARTBEAT`,
  `SERVERLIST`, `RELOAD`), rejects direct loopback `RELOAD` without a proxied
  key, and explicitly rejects unsupported `C;KILL;` without forwarding it as a
  game packet. Targeted control tests cover the allowed and forbidden scenarios.
- Completed Phase 6 of `docs/autonomy-work-plan-20260601.md`: online
  `SyncDatabaseAdapter` connections now keep the server/session `sql_mode`
  active and only set `SET NAMES 'utf8mb4'`; legacy-compatible empty
  `SESSION sql_mode` is explicit `import_mode=True` behavior used by
  stdin/replay/import paths. `enable_multi_statements` now requires
  `import_mode=True`, so online services cannot silently enable that importer
  capability. Tests also pin the positive import-mode `client_flag` path and
  the `hlstats_py --stdin` / FTP batch importer wiring. `docs/python_migration_usage_guide.md`
  documents the split.
- Completed Phase 7 of `docs/autonomy-work-plan-20260601.md`: parity
  acceptance is now split into a lightweight PR/local subset and a
  scheduled/manual heavy replay subset. `docs/parity-acceptance.md` documents
  the accepted fixture identity, artifact expectations, promotion rules, and
  where Perl remains required: reference behavior, baseline regeneration,
  targeted investigation, and heavy acceptance replay. `.github/workflows/nightly-parity.yml`
  now runs replay helper smoke plus a self-hosted Windows parity runner job for
  `Run-DualContour-1000.ps1 -UseDumpRestore` with fresh legacy import and its
  integrated inactive/awards/ribbons/GeoIP maintenance, compact DB compare,
  web smoke, and artifact upload. `docs/test-plan.md`
  records that routine PR work no longer requires live Perl when fixture inputs
  and the accepted legacy contour are unchanged.
- Completed Phase 8 of `docs/autonomy-work-plan-20260601.md`: PHP language
  selection now has pure request-context helpers in `web/includes/i18n.php`.
  `init_i18n()` resolves language from query/cookie/session snapshots without
  mutating `$_GET` or `$_REQUEST`, while session/cookie persistence remains the
  compatibility path. Historical page-cache keys now use an explicit GET/POST
  request snapshot plus `i18n_historical_cache_target()`, so the active
  language is part of the cache identity without mutating or depending on raw
  `$_REQUEST`. `hlstats.php` also clears stale `realgame` session state when an
  explicit `game` change arrives. Product CI runs `scripts/web_i18n_smoke.php`
  after PHP syntax lint to pin EN/RU language priority, URL generation,
  cache-key separation, and no-mutation behavior. The heavy nightly parity
  workflow delegates maintenance, DB compare, and route smoke entirely to the
  canonical runner: legacy is its EN reference and Python is its EN/RU product
  contour, both against replay-backed data.
- Completed Phase 9 of `docs/autonomy-work-plan-20260601.md`: `hlstats_py`
  now emits a stable structured metrics summary on runtime stop and finite
  stdin import completion, including processed events, event throughput, stdin
  and UDP counters, dropped packets, flush attempts/failures, and control-plane
  command/rejection counts. `docs/release-readiness.md` now defines the
  observability contract, profiling/benchmark commands, release candidate
  checklist, deployment/config handoff notes, and the current log-based
  metrics limitation. `.github/workflows/nightly-parity.yml` uploads the
  runner-derived sanitized `nightly-parity-summary` for release handoff rather
  than a second, partial post-run gate.
- Completed player-card/runtime web parity hardening: `sig.php` now uses the
  same EN/RU i18n bootstrap as the public web entrypoints with legacy English
  fallback text, player-card signature preview/direct/BBCode links preserve the
  active `lang`, `Started map` writes `hlstats_Servers.map_started` from the
  runtime wall clock to match legacy `Played` semantics, RU player-card tabs no
  longer rely on fixed 16/18px heights, and replay-backed web smoke now checks
  `sig.php` as a PNG route for both EN and RU.
- Frontend i18n backlog (`P6a`/`P6b`/`P6c`) remains complete for the supported
  EN/RU product contour.
- Supplemental frontend i18n sweep completed on 2026-07-26: standalone error
  routes, TeamSpeak labels/fallbacks, heatmap and hitbox controls, graph
  summaries, tabs, and shared JavaScript loading/error text now use the EN/RU
  dictionaries. The dictionaries have matching 1117-key and placeholder
  sets; remaining English literals are guarded fallbacks or technical/logging
  text rather than untranslated Russian UI.

## Next

1. Use `docs/release-readiness.md` as the release-candidate checklist and
   evidence handoff runbook.
2. Keep the stale reconnect-code fix out of scope unless fresh code or test
   evidence contradicts the current implementation.
3. SQL write-path slice `20260718-sql-write-opt-r1` is source-validated: the
   stdin-only `Players_History` ensure-row cache reduced the preserved
   `L0105062.log` logical SQL count from 4,613 to 2,519 and wall time from
   4.457 s to 2.071 s without stable-key drift outside the known wall-clock
   `Players.last_event` field. A fresh no-reuse `narrow-1000`
   `20260718-sqlwrite-r2` promotion confirms matching manifests, anchors, and
   SQL snapshot bodies; its only database residual is the established
   GeoIP-only `Players.country`/`flag` classification. This remains
   source-validated evidence, not a replacement for the release-clean GeoIP
   backfill gate. See the audit report for disposable-DB evidence.
4. Do not start a broad `EventStorage` rewrite. The planned strangler sequence
   preserves its single-worker ordering and transaction contracts, then moves
   one bounded seam at a time with a clean `prefix-100` after every slice and
   `narrow-1000` after each milestone; see
   [`docs/plans/2026-07-22-event-storage-strangler-plan.md`](plans/2026-07-22-event-storage-strangler-plan.md).

## Decisions

- This repo is the product integration lane, not the upstream PR lane.
- Python is the default runtime path for the product lane.
- Perl remains legacy-only for validation and parity reference behavior through
  replay/reference tooling, not as a local production runtime surface.
- The integrated Python web contour is the EN/RU product UI reference.
- Codex should use English internally for technical analysis but answer the
  user in Russian unless explicitly asked otherwise.
- If a requested approach is slower, riskier, or weaker than a clear
  alternative, prefer the better project path and call out the tradeoff.
- Non-trivial parity behavior changes must start with a read-only subagent
  inspecting the legacy Perl implementation, followed by local verification of
  that conclusion, before Python behavior is changed.
- Detailed replay transcripts, compare counts, and historical slice notes live
  in `docs/audits/...`, not in this status summary.

## Current Risks

- Docker API access can still block single-log or narrow replay verification
  even when the local unit slice is already green.
- Modern Heatmap Explorer is release-ready only as the accepted local
  `44f3af9` candidate; production promotion
  still requires the documented mode-0 deployment, migration readback, staged
  mode-1 observation, reverse-proxy inspect rate limit, and rollback monitoring.
- Some Python test commands still require explicit `PYTHONPATH` setup because
  the imported package roots do not yet have a unified developer bootstrap.
- `PlayerNames`, `Players`, and `Players_History` are no longer open
  broad-contour residuals; avoid reopening them without fresh focused evidence.
- The replay comparison contour still uses fixed local container names, so
  concurrent local stacks can block rebuild or smoke passes.
