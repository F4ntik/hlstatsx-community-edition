# Core Page Triage (1000 logs)

Source: `core-page-mismatches-1000.jsonl`

## Summary
- `P1`: 11 findings
- `P2`: 6 findings
- `P0/P3`: 0 findings

## Grouping by likely root cause

## 1) Data volume / aggregation drift (`P1`)
- players/clans/maps/weapons/actions row counts and totals differ between contours.
- probable cause: replay ingestion coverage/ordering mismatch across contours for same 1000 window.

## 2) Detail-page rendering gaps (`P1`)
- claninfo in python misses identity/counters/sections present in legacy.
- probable cause: route query/adapter mismatch or incomplete mapping layer for clan aggregates.

## 3) Presentation/label parity (`P2`)
- metric labels differ (`K:D` vs `Kpd`, `HS:K` vs `Hpk`, etc.).
- probable cause: UI naming conventions diverged; not necessarily data bug but page-visible non-parity.

## 4) Awards page structure drift (`P2`)
- python awards page shows extra visible list entries not present in legacy.
- probable cause: navigation/layout divergence for awards route family.

## Next fix order
1. Reconcile ingestion parity for 1000-window counters (`P1` totals/row counts).
2. Fix `claninfo` data blocks in python (`P1`).
3. Normalize metric labels and awards list layout where required for strict page-visible parity (`P2`).
