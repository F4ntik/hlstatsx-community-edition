# Runtime DB Diff: L0628063 Botlike Userid

## Scope

This records the replay evidence for the `L0628063.log` opening window after
the transient `userid <= 0` bot-classification fix.

## Runs

### Main single-log window

- Source log: `scripts/replay_baseline/artifacts/L0628063.log`
- Extracted input: `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-sql/input/L0628063.log`
- Extracted lines: `1-206` from anchor line `22`
- Legacy replay: `201` lines, `5` dropped
- Python direct import: `206` records
- `compare_stats_dbs.py`: `compare exit 1`
- `parity_trace.py diff`: `trace diff exit 0`

### Guard window

- Extracted input: `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-guard-30x30/input/L0628063.log`
- Extracted lines: `1-52` from anchor line `22`
- Legacy replay: `49` lines, `3` dropped
- Python direct import: `52` records
- `compare_stats_dbs.py`: `compare exit 1`
- `parity_trace.py diff`: `trace diff exit 0`

## Stable-Key SQL

| table | legacy | python | result |
|---|---:|---:|---|
| `hlstats_Events_ChangeTeam` | 5 | 5 | match |
| `hlstats_Events_Frags` | 4 | 4 | match |
| `hlstats_Events_TeamBonuses` | 6 | 6 | match |
| `hlstats_Events_Entries` | 0 | 0 | match |

### Exact rows

- `ChangeTeam`: `2023-06-28 23:35:58` `Mep3ocTb` / `1:45686725` `TERRORIST`
- `Frags`: `2023-06-28 23:43:35`, `23:43:50`, `23:46:13`, `23:46:33`
- `TeamBonuses`: `2023-06-28 23:46:13`, `23:46:33`
- `Entries`: none in this window

## Residual Compare Drift

The main-window compare still reports a separate drift outside the requested
stable keys:

- `hlstats_Players`: GeoIP-only `country` / `flag` split
- `hlstats_Players_History`: `skill_change` drift for `1.em`
- `hlstats_Actions`: `kill_streak_2` count `0` vs `1`
- `hlstats_Events_PlayerActions`: Python-only `kill_streak_2` at
  `2023-06-28 23:44:48`

## Classification Note

This residual is tracked as a must-fix under the parity-acceptance policy
because it changes a visible `PlayerActions`/`Actions` counter. Legacy-first
remains the default triage direction, but legacy is still a reference
implementation and can contain its own bugs; the absence or presence of a row
in legacy is not proof of correctness by itself. Re-check both stacks and the
policy before turning a drift into a code change.

## Raw Artifacts

- Main run dir: `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-sql`
- Guard run dir: `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-guard-30x30`
