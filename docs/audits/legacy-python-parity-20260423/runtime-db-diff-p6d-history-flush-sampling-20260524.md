# P6d Players_History flush sampling alignment

Date: `2026-05-24`

Scope:

- Python runtime/storage `Players_History` kill-streak sampling.
- Legacy-first review of Perl `HLstats_Player::flushDB` and
  `HLstats_EventHandlers::endKillStreak`.

## Legacy rule

Perl does not sample active `kills_per_life` directly into
`hlstats_Players_History`. `endKillStreak()` first promotes the live object
`kill_streak` max when the life ends, including a single-kill life. It emits a
derived `kill_streak_N` action only when the completed streak is greater than
one. `flushDB()` later writes the current live object `kill_streak` and
`death_streak` fields into `hlstats_Players` and `hlstats_Players_History`
using SQL max semantics.

Relevant legacy files:

- `scripts/HLstats_Player.pm`: `check_history`, `flushDB`, post-flush counter
  reset.
- `scripts/HLstats_EventHandlers.plib`: `endKillStreak`, frag victim-side
  death-streak update, round-boundary streak drain.
- `scripts/hlstats.pl`: stdin EOF flush and player cleanup flush paths.

## Python change

Python previously updated `_player_max_kill_streaks` on each kill event and
passed that max into event-level history rollups. This sampled active
kill-streak state too early. Python now:

- updates max kill streak only when `_end_kill_streak()` drains a life;
- records single-kill completed streaks as `kill_streak=1` without a derived
  player action;
- includes current max streaks when flushing open player connection-time
  sessions, matching the legacy `flushDB()` sampling point;
- clears max streak caches when a live player object is closed, matching Perl's
  new object lifecycle.

## Verification

Targeted tests:

```powershell
$env:PYTHONPATH='scripts;scripts\proxy_daemon_py'
python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-storage scripts\hlstats_py\tests\test_storage.py -q
python -m pytest -p no:cacheprovider --basetemp C:\tmp\hlstats-pytest-validation scripts\hlstats_py\tests\test_validation.py -q
```

Results:

- `scripts/hlstats_py/tests/test_storage.py`: `127 passed`.
- `scripts/hlstats_py/tests/test_validation.py`: `1 passed`.

Replay checks:

```powershell
docker compose build hlstats-worker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 -LogFile scripts\replay_baseline\artifacts\L0103146.log -Name p6d-history-rakza-L0103146-after-flush-sampling -TraceTable hlstats_Players_History -LineNumber 2453
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 -MaxImportFiles 1000 -UseDumpRestore -ReuseValidLegacy
python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Results:

- `L0103146` guard window no longer lists `hlstats_Players_History`; the main
  sliced window still has a legacy-only current-date seed row caused by the
  artificial cut.
- Fresh `narrow-1000` compare reduced `hlstats_Players_History` normalized
  residuals from the retained `50/50` baseline to `14/14`.
- The fresh compare still exits `1` for known/open residuals:
  - `hlstats_Players`: `250/250`, GeoIP-only in normalized examples because
    local `GeoLiteCity/GeoLite2-City.mmdb` was unavailable.
  - `hlstats_PlayerNames`: `0/1`, the existing `XYU` / `unnamed` alias.
  - `hlstats_Players_History`: `14/14`, now mostly skill/stat attribution.
  - `hlstats_Events_Entries`: accepted `0/1017`.
  - `hlstats_Events_TeamBonuses`: `0/1` Python-only `Dance Bear` /
    `CTs_Win` at `2026-01-02 21:40:31`; this needs separate follow-up because
    the flush-sampling change does not touch team reward membership.

Run state:

- `scripts/replay_baseline/comparison/.parity-state/20260524-150506.json`

## Next

- Continue `P6d-M3` on the remaining `Players_History` `14/14` rows, starting
  with the skill/stat attribution examples rather than kill-streak sampling.
- Separately re-triage the fresh `Dance Bear` `Events_TeamBonuses` row before
  treating TeamBonuses as clean in the current local contour.
