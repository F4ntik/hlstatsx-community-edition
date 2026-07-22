# Maintenance parity design for the dual replay contour

Date: `2026-07-22`

## Goal

Make the canonical dual replay contour prove the post-ingest, web-visible
maintenance result as well as raw event ingestion. A normal release-clean run
must calculate the legacy-compatible default maintenance set plus GeoIP in both
contours, compare the resulting award/ribbon and full GeoIP data, and leave
both web applications populated for an operator's side-by-side inspection.

## Scope and compatibility contract

`Run-DualContour-1000.ps1` gains a default `maintenance` stage after both
legacy and Python imports and before SQL snapshots. It runs the same selected
actions against each contour:

```text
prune -> inactive players -> awards -> ribbons -> GeoIP
```

This is the legacy `hlstats-awards.pl` execution order for the legacy default
actions (`-iarp`) extended with opt-in GeoIP (`-g`). The Python calculator must
move its current GeoIP step from before awards/ribbons to after ribbons.

`optimize` and `clans` are deliberately not part of the default contour:

- legacy does not run either by default;
- table optimisation is an intrusive diagnostic, not a parity calculation;
- Python's parsed `clans` action has no calculator implementation, so claiming
  it in a default parity receipt would be false.

The raw-debug escape hatch is `-SkipMaintenance`. It marks the run state and
its evidence as raw-only; it cannot be used as release-clean or visual
maintenance-parity evidence.

## Deterministic maintenance input

The runner exposes `-MaintenanceDate` and `-MaintenanceNumDays`.

- An explicit date is passed identically to both legacy and Python CLIs.
- If no date is supplied, the runner derives the legacy award base date from
  the completed replay window once, verifies the same event-time boundary in
  the Python contour, then records the resolved value in state and audit
  evidence.
- `MaintenanceNumDays` defaults to legacy-compatible `1` and is likewise
  recorded and passed to both commands.

This avoids comparing two historical replays against a host-clock day that has
no events, while retaining an explicit override for production-like scenarios.

## Runner and failure behavior

The canonical stage sequence becomes:

```text
infra_updown -> baseline_restore -> preflight -> legacy_import -> python_import
-> maintenance -> sql_snapshot
```

The runner invokes legacy maintenance in its own contour and Python
`hlstats_awards_py` in the Python worker. Both commands use the same resolved
date, horizon, selected actions, and their contour-local config. GeoIP runs in
strict mode; a missing database/binary is a failure, not a silent replay-safe
skip.

Any maintenance command failure stops the runner before snapshots. Existing
raw-import artifacts remain useful for diagnosis, but the state records
maintenance as failed and no release-clean claim is made.

## Comparison and visual evidence

The existing event-table comparison remains the raw-ingest oracle. It is
extended, rather than replaced, with stable-key normalizers for:

- `hlstats_Awards`, including resolved daily/global winner identities;
- `hlstats_Players_Awards`;
- `hlstats_Players_Ribbons`; and
- full player GeoIP fields (`flag`, `country`, `city`, `state`, latitude and
  longitude), not only `country`.

The runner also writes a compact maintenance summary alongside SQL snapshots:
resolved date/horizon, action exit status, table counts, stable-key diff result,
and representative awards/ribbons/player routes for legacy (`8181`) and Python
(`8281`). Existing web-route smoke covers the populated award-facing routes;
the summary gives an operator stable, data-backed URLs for side-by-side visual
inspection rather than relying on row counts alone.

## Tests and acceptance

Add focused tests for:

1. Python calculator action ordering matching Perl, including GeoIP after
   awards/ribbons.
2. Runner command construction, stage ordering, shared resolved date/horizon,
   default maintenance, and `-SkipMaintenance` labelling.
3. Stable-key normalization/diffs for awards, player-awards, ribbons, and full
   GeoIP fields.
4. Maintenance-summary and award-facing web-route smoke contracts.

Acceptance is layered:

1. focused tests and a small maintenance-enabled `prefix-100` gate;
2. post-maintenance logical DB compare with no unexplained differences;
3. web smoke and saved visual-inspection summary; then
4. maintenance-enabled `narrow-1000`, GeoIP/awards/ribbons comparison, and
   retained evidence.

All relevant commands, maintenance-date semantics, raw-versus-release-clean
labels, and evidence locations are documented in the replay runbook, test plan,
parity acceptance guide, and status record.
