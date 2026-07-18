# L0628063 Botlike Userid Window Report

## Verdict

The bot-classification fix is confirmed for the requested stable keys in the
`L0628063.log` opening window.

## Confirmed

- `hlstats_Events_ChangeTeam` matches legacy for `1:45686725`
- `hlstats_Events_Frags` matches legacy for the requested first-frag rows
- `hlstats_Events_TeamBonuses` matches legacy for the requested first team
  bonus rows
- `hlstats_Events_Entries` remains empty in this window on both contours

## Still Open in the Narrow Compare

The remaining compare drift is separate from the requested stable keys:

- `Players` GeoIP-only `country` / `flag` difference
- one Python-only `kill_streak_2` `PlayerActions` row at
  `2023-06-28 23:44:48`
- the associated `Actions` count and `Players_History` `skill_change` delta

## Classification

This `kill_streak_2` residual is a must-fix parity bug. Keep the legacy-first
workflow, but do not assume the legacy stack is infallible: it is the reference
behavior for parity, not a proof that every legacy row or omission is correct.
If the drift is revisited later, validate the exact event sequence against both
stacks and the acceptance policy before changing Python.

## Evidence Paths

- Main compare output:
  `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-sql/compare-stats.txt`
- Main raw traces:
  `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-sql/legacy-general.log`
  and
  `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-sql/python-writes.jsonl`
- Guard compare output:
  `scripts/replay_baseline/artifacts/parity-traces/L0628063-botlike-userid-guard-30x30/compare-stats.txt`

## Next Step

Do not broaden to the full contour yet. The stable-key event rows are fixed, but
the narrow compare still needs a separate read on the `PlayerActions` /
`Actions` drift before promotion.
