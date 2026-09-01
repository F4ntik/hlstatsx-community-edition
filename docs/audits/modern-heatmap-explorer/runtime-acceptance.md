# Modern Heatmap Explorer runtime acceptance

Status on 2026-09-01: `SOURCE-READY`, `RUNTIME-ACCEPTED`, and
`RELEASE-READY` as a local release candidate. Nothing was pushed, deployed, or
published by this acceptance run.

The accepted product runtime is commit
`cc116620422182d20ebb29df9c3518693a551da7`. Commit `3dc6330` only makes the
coordinate receipt portable to the Windows PowerShell available on this host;
it does not change runtime behavior. The sanitized machine-readable summary is
[`evidence/acceptance-2026-09-01.json`](evidence/acceptance-2026-09-01.json).

## Acceptance result

| Gate | Result | Current evidence |
| --- | --- | --- |
| Source | pass | 302 product tests, 91 replay tests, 13 route tests, 5 coordinate-runner tests, compileall, PHP smoke/lint, JavaScript check/smoke, and diff check |
| Persisted coordinates | pass | Disposable `bench_ephemeral` runner asserted five distinct/consumed/cleared coordinate cases and cleaned itself |
| Migration | pass | Fresh install and HTTP updater 81→82 retained MyISAM, data fingerprint, and exact `mapEventTime(map,eventTime)` index; second update was idempotent |
| Performance | pass | cold p95 55.5241 ms, warm p95 10.3528 ms, inspect p95 13.6879 ms, 4,009-byte gzip, 301 bins, 65/65 metrics |
| Public browser | pass | EN/RU map and player surfaces, Color/Mono, custom period, Difference, inspector aggregates, floor states, keyboard, touch/mobile, 200% reflow, reduced motion, JS/WebGL fallbacks, and legacy rollback |
| Admin browser | pass | authenticated EN/RU upload/save/readback plus access, CSRF, stale-session, file-type, size, floor, and generate-over-HTTP negative cases |
| Map identity | pass | A and B SHA-256 URLs differed; stale A returned 409/no-store; current B returned 200/immutable with matching ETag |
| Restore | exact | mode 0, original config and assets, `counter_hits=293725`, zero temporary users/fixtures/sessions, no mounts, no custom overview |

## Browser proof

The final browser rows used Chromium against `http://127.0.0.1:8281` and the
rebuilt exact product image.

- Color is the default map-only grade. Mono is reversible and changes neither
  scene request nor URL. WebGL-unavailable fallback remains unfiltered.
- Player Difference returned `state=ok`, personal sample 5 and other sample
  170 with `premultipliedAlpha=false`.
- The inspector exposes timestamp, event type, headshot/teamkill state, top
  weapons and bounded participant aggregates for returned rows.
- True mobile used `clientWidth=390`, `innerWidth=scrollWidth=393`, DPR 3 and
  visual scale 1. The workspace is one column, the inspector sheet opens, and
  every enabled Explorer target is at least 44×44 CSS px.
- The 200% reflow proxy used `innerWidth=720`,
  `clientWidth=scrollWidth=705`, DPR 2, all 19 enabled controls usable, and no
  horizontal overflow. Reduced-motion transition duration was `0s`.
- JavaScript-disabled, WebGL2-disabled, WebGL context-loss, static JPEG,
  specialized insufficient-sample, floor keyboard, old share URL, and explicit
  legacy rollback paths were exercised. The compatibility JPEG opened at
  1024×768.

The old auxiliary gap harness still reports one aggregate red flag because it
counts unrelated/superseded small links across the legacy page. Its actual
WebGL-loss, rollback and keyboard actions pass. The canonical enabled-control
measurement above is the release accessibility gate.

## Migration and performance proof

An isolated MariaDB 10.11 contour proved both fresh install and update paths:

- fresh install: `dbversion=82`, Teamkills `MyISAM`, Config `InnoDB`, one
  `floors_json` column, mode 0, and the two-part `mapEventTime` index;
- populated update: 81→82 over 42 Teamkills rows while 120 concurrent reads
  completed, with checksum and row fingerprint unchanged;
- second HTTP updater: 200, no duplicate index, identical data;
- EXPLAIN: `range` on `mapEventTime`, `Using index condition`;
- all temporary container, image, network and volume resources removed.

The strict legacy comparator remains red only for the previously approved
coordinate-bearing product residual. It was not weakened or relabeled green.

## Coordinate proof

The canonical runner now passes through the supported disposable contour:

```powershell
rtk powershell -NoProfile -ExecutionPolicy Bypass -File `
  scripts\replay_baseline\comparison\Run-HeatmapCoordinateAcceptance.ps1 `
  -EvidenceLabel heatmap-coordinate-contract-final
```

The sanitized receipt asserts shipped cstrike attacker/victim positions,
SourceMod victim-only suicide coordinates, one-time staged-pair consumption,
non-reuse, and source-boundary clearing. The disposable database was removed
automatically.

## Map source and GoldSrc research boundary

The local Counter-Strike installation contains color BMP overview maps and TXT
projection metadata. GoldSrc/Xash source confirms the centered 4:3 overview
projection model; MetaMod, AMX Mod X and ReHLDS are not the map-rendering layer
and do not provide a better client overview implementation.

No Valve or Steam asset was copied into the product. Shipping those files
would require a separate licensing decision. The accepted implementation uses
the repository's map images and an elegant map-only Color/Mono grade. An
optional operator-side GoldSrc importer can be designed later without changing
the v1/JPEG compatibility contract.

## Rollout and rollback

`HeatmapExplorerBeta` remains at `0` after acceptance:

- `0`: legacy v1/JPEG only; direct v2 disabled;
- `1`: legacy by default, explicit `heatmap_explorer=1` opt-in;
- `2`: Explorer by default, explicit `heatmap_legacy=1` rollback.

Promote `0 → 1 internal → 1 public beta → 2 default`. Roll back immediately
to `0` for elevated errors, SLA breach, biased/truncated scenes, or coverage
regression. This document establishes local release readiness, not production
deployment acceptance.

## Raw evidence boundary

Raw receipts and disposable backups remain ignored under `.superpowers/sdd/`;
they are not release artifacts and may contain machine-local paths. The final
read-only references are:

- `2026-09-01-heatmap-background-grading/task3-browser-20260901T221236Z.json`
  and its exact restore pair;
- `2026-08-31-modern-heatmap-explorer/task-11-evidence/task11-myisam-current-20260901T221141Z.json`;
- `2026-08-31-modern-heatmap-explorer/task-12-evidence/task12-final-gap-browser-20260901T221909Z.json`;
- `2026-08-31-modern-heatmap-explorer/task-12-evidence/task12-player-difference-gate-20260901T222538Z.json`;
- `2026-08-31-modern-heatmap-explorer/task-12-evidence/task12-public-tail-20260901T224616Z.json`;
- `2026-08-31-modern-heatmap-explorer/task-12-evidence/task12-gap-browser-20260901T224616Z.json`;
- `2026-08-31-modern-heatmap-explorer/task-12-evidence/task12-admin-matrix-current-20260901T2251Z.json`;
- final exact restore
  `2026-08-31-modern-heatmap-explorer/task-12-evidence/task12-final-gap-restore-20260901T225611Z.json`.
