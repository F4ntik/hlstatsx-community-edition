# P6d narrow-1000 after PlayerNames live-alias attribution fix

Date: `2026-05-23`

Scope:

- Python runtime/storage only.
- PHP/UI untouched.
- Stateful PlayerNames cluster:
  `L0102209..L0102213`, `0:1161623468`,
  `Player21` / `Dim$0n` / `Dim$on`.

## Legacy finding

Read-only legacy inspection showed that the Perl runtime does not update the
live player object's name from every later log descriptor for an already-live
`userid` / `uniqueId` match. The constructor name remains the active alias
until an explicit `changed name to` event or object cleanup/eviction changes
that state.

Relevant legacy references:

- `HLstats_Player.pm::setName` marks the old name dirty before changing the
  object name, but does not flush stat rollups immediately.
- `HLstats_Player.pm::updateDB` marks the object dirty; `flushDB` performs the
  later PlayerNames total write using the current object name.
- `hlstats.pl::getPlayerInfo` updates team/role/timestamp for existing live
  players and does not reconcile the object name from ordinary descriptors.

For the cluster this means:

- the `L0102211` `Player21<136>` constructor alias owns the following
  `Dim$0n<136>` weaponstats until disconnect/flush;
- the `L0102212` `Player21<159>` object keeps `Player21` until the explicit
  `changed name to Dim$on` event;
- the later pending rollup after that explicit name change belongs to
  `Dim$on`, not to the pre-change alias.

## Fix

`EventStorage._resolve_player_id` now updates the runtime alias only when a
player object is first seen, explicitly forced by a name-change/userid-rollover
path, or reopened after a closed object. Ordinary same-live-object descriptors
no longer overwrite the active alias.

This intentionally does not reintroduce the rejected `changed name to`
alias-rollup flush hypothesis.

## Verification

Targeted regression was added:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -q `
  -k "existing_live_player_keeps_constructor_alias"
```

The test failed before the fix with an extra `Dim$0n` alias touch and passed
after the fix.

Targeted alias subset after the fix:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -q `
  -k "existing_live_player_keeps_constructor_alias or name_change_updates_deferred_profile_name or player_name_totals_flush_to_current_alias_after_name_change or name_change_back_to_prior_alias_counts_new_alias_use"
```

Result: `4 passed, 121 deselected`.

Full storage suite:

```powershell
$env:PYTHONPATH='scripts;scripts/proxy_daemon_py'
python -m pytest scripts/hlstats_py/tests/test_storage.py -q
```

Result: `125 passed`.

Same-cluster replay after rebuilding `hlstats-worker`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\replay_baseline\comparison\Run-SingleLogParity.ps1 `
  -LogFile .\scripts\replay_baseline\artifacts\parity-traces\p6d-playernames-player21-L0102209-L0102213-after-alias-flush\input\L0102209-L0102213.log `
  -Name p6d-playernames-player21-L0102209-L0102213-after-live-alias-fix `
  -TraceTable hlstats_PlayerNames `
  -TraceParamContains Player21
```

Result:

- artifact:
  `scripts/replay_baseline/artifacts/parity-traces/p6d-playernames-player21-L0102209-L0102213-after-live-alias-fix`
- write-trace diff: `0` write-intent differences
- `compare-stats.txt` no longer lists `hlstats_PlayerNames`
- `Player21`, `Dim$0n`, and `Dim$on` no longer appear in that cluster's
  PlayerNames diff

The automatic guard-window rerun was skipped as `skipped:no-anchor`; this is
expected for this stateful neighboring-log cluster because a time/line/pattern
anchor was not supplied.

An attempted broad promotion with `-ReuseValidLegacy` immediately after the
single-cluster run was discarded: the previous single-log replay had replaced
the legacy DB, so the reuse path produced an invalid mixed baseline
(`hlstats_Players` legacy rows `31` vs Python rows `323`).

Fresh full contour promotion was then run without legacy reuse:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\replay_baseline\comparison\Run-DualContour-1000.ps1 `
  -MaxImportFiles 1000 `
  -UseDumpRestore

python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Result:

- legacy import: `processed=1000`, `errors=0`, `lines=672223`,
  `dropped_lines=1969`, `elapsed=249.343s`
- run state:
  `scripts/replay_baseline/comparison/.parity-state/20260523-122452.json`
- logical differences remain in `4` tables
- `hlstats_PlayerNames`: `415/416` rows, `0` legacy-only / `1` python-only
  normalized row
- remaining PlayerNames row: Python-only `unnamed` alias for `XYU`,
  `0:552632503`

## Result

The active `Player21` / `Dim$0n` / `Dim$on` PlayerNames cluster improved from
the prior broad contour's `2` legacy-only / `3` python-only normalized rows to
no cluster rows in the same-cluster replay and only the already-known
`XYU`/`unnamed` Python-only alias in the fresh clean `narrow-1000`.

Current broad residuals after this run:

- `hlstats_Players`: `250` legacy-only / `250` python-only normalized rows,
  already classified as GeoIP `country`/`flag` only.
- `hlstats_PlayerNames`: `0` legacy-only / `1` python-only normalized row
  (`XYU` / `unnamed`).
- `hlstats_Players_History`: `50` legacy-only / `50` python-only normalized
  rows.
- `hlstats_Events_Entries`: accepted `0/1017` legacy/Python policy difference.

Next active block: `hlstats_Players_History` streak anchors, starting with
`Rakza`, `STEAM_0:1:55955613`, `L0103144` / `L0103146` / `L0103212`.
