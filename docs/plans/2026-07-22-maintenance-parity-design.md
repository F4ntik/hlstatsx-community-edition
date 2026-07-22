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
UseTimestamp=1 -> inactive players -> awards -> ribbons -> GeoIP
```

This is the legacy calculation order with an explicit historical-clock setup
inside the disposable replay DBs. `UseTimestamp=1` makes both implementations
derive activity from the latest server event in the replay rather than the
host's wall clock. The Python calculator must move its current GeoIP step from
before awards/ribbons to after ribbons.

`prune`, `optimize`, and `clans` are deliberately not part of the default
historical contour:

- prune uses the host-clock `DeleteDays` cutoff and would erase an old replay
  corpus before awards can be calculated;
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
-> maintenance -> sql_snapshot -> logical_compare -> web_smoke
```

The runner invokes legacy maintenance in its own contour and Python
`hlstats_awards_py` in the Python worker. Both commands use the same resolved
date, horizon, selected actions, historical inactivity clock, and their
contour-local config. GeoIP runs in strict mode; a missing database/binary is a
failure, not a silent replay-safe skip. A release-clean run must freshly import
and snapshot legacy: `-ReuseValidLegacy` is allowed only with
`-SkipMaintenance`, which marks the result raw-only.

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
resolved date/horizon, action set, `UseTimestamp` readbacks, action exit status,
table counts, stable-key diff result, and representative daily/global/ribbons/
player routes for legacy (`8181`) and Python (`8281`). The original legacy web
is English-only and is therefore the EN reference; the Python product smoke
covers the same populated award tabs in EN and RU. The summary gives an
operator stable, data-backed URLs for side-by-side visual inspection rather
than relying on row counts alone.

## Tests and acceptance

Add focused tests for:

1. Python calculator action ordering matching Perl, including GeoIP after
   awards/ribbons.
2. Runner command construction, stage ordering, shared resolved date/horizon,
   historical `UseTimestamp=1` override/readback, no-prune invariant, fresh
   legacy requirement, default maintenance, and `-SkipMaintenance` labelling.
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

## Accepted implementation evidence

The acceptance sequence completed on `2026-07-22`:

- `prefix-100` / `20260722-maintenance-prefix-100-r8` passed after the focused
  calculator and runner regressions;
- `narrow-1000` / `20260722-maintenance-narrow-1000-r1` processed the shared
  1,000-file manifest (SHA-256
  `95bfdb5951922c0c36aab2c5263e1880b227e845b34c9262939b028d0fbebe8a`),
  retained matching `frags=5464`, passed full logical DB comparison and the
  legacy EN/Python EN+RU route smoke; and
- the canonical CI workflow now treats this one runner as the authority for
  maintenance, compare, and route smoke, then packages only its sanitized
  summary.

The detailed evidence, including rejected intermediate runs and DB-only
progress-monitoring rules, is recorded in
`docs/audits/legacy-python-parity-20260423/maintenance-parity-20260722.md`.
