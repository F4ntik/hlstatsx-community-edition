# Modern Heatmap Explorer runtime acceptance

Status on 2026-09-02: `SOURCE-READY`, locally `RUNTIME-ACCEPTED`, and
`RELEASE-READY` only as a local release candidate. Nothing was pushed,
deployed, published, or accepted for production release by this run.

The accepted visibility-corrected implementation is exact commit
`44f3af97db46107f3ab9b595b3c32b3e5c2c7986`. The previously accepted DB/API,
coordinate, migration, admin, cache and performance evidence remains applicable
because this correction changes only WebGL presentation and its tests. The
sanitized machine-readable summary is
[`evidence/acceptance-2026-09-02.json`](evidence/acceptance-2026-09-02.json);
the 2026-09-01 JSON remains a historical pre-correction receipt.

## Acceptance result

| Gate | Result | Current evidence |
| --- | --- | --- |
| Source | pass | 302 product tests with explicit local `PYTHONPATH`, 91 replay tests, 18 focused route/coordinate-script tests, compileall, PHP heatmap/i18n smoke, JavaScript syntax/smoke including the sparse normalization regression, and diff check |
| Persisted coordinates | pass | Disposable `bench_ephemeral` runner asserted five distinct/consumed/cleared coordinate cases and cleaned itself |
| Migration | pass | Fresh install and HTTP updater 81→82 retained MyISAM, data fingerprint, and exact `mapEventTime(map,eventTime)` index; second update was idempotent |
| Performance | pass | cold p95 55.5241 ms, warm p95 10.3528 ms, inspect p95 13.6879 ms, 4,009-byte gzip, 301 bins, 65/65 metrics |
| Visual legibility | pass | Old shader failed with singleton/peak alpha `0.009259/0.138889` and zero colored pixels above alpha 0.20; corrected Color and Mono each have 35,766 qualifying colored pixels and Difference has 3,740 against required 189 |
| Public browser | pass | EN/RU map and player surfaces, visibly obvious Color/Mono/Difference data, custom period, inspector aggregates, floor states, keyboard, touch/mobile, 200% reflow, reduced motion, JS/WebGL fallbacks, and legacy rollback |
| Admin browser | pass | authenticated EN/RU upload/save/readback plus access, CSRF, stale-session, file-type, size, floor, and generate-over-HTTP negative cases |
| Map identity | pass | A and B SHA-256 URLs differed; stale A returned 409/no-store; current B returned 200/immutable with matching ETag |
| Restore | exact | mode 0, original config and assets, `counter_hits=293725`, zero temporary users/fixtures/sessions, no mounts, no custom overview |

## Sparse-grid visibility correction

The accepted `cstrike/de_dust2` scene contains 175 source events and 301
occupied bins in a 128×103 grid; the raw maximum cell value is 12. The old
fragment path averaged a 3×3 neighborhood and divided by the original global
maximum. An ordinary isolated bin therefore became `1/108 = 0.009259` alpha,
the strongest convolved region became only `15/108 = 0.138889`, and the live
frame maxed at `35/255 = 0.137255`. It produced zero qualifying colored pixels
above alpha 0.20 and failed the retained RED gate.

The corrected path normalizes after convolution and applies the fixed square-
root transfer. An ordinary singleton is `sqrt(1/15) = 0.258199`; the peak is
`1.0`. Live Color and Mono each contain 35,766 qualifying colored pixels with
max alpha 1.0 and identical raw WebGL hash prefix `f06b0da2`; only the styled
background differs, and both composite-contrast checks pass. Difference has
161 bins, 45 warm plus 3,695 cool qualifying pixels (3,740 total versus the
required 189), alpha floor 0.22, max alpha 1.0, and passing contrast. Independent
visual judgment found the hotspots obvious without zoom.

The exact-HEAD objective receipt is
`.superpowers/sdd/2026-09-02-modern-heatmap-visibility/`
`fixed-runtime-visual-gate-44f3af9.json`; it reports PASS at full commit
`44f3af97db46107f3ab9b595b3c32b3e5c2c7986`. The retained old-runtime RED
receipt proves the same gate rejects the legacy rendering.

Canonical before/after evidence:

- [Color before](screenshots/before-normalization-map-overview-en.png) / [Color after](screenshots/map-overview-en.png)
- [Mono before](screenshots/before-normalization-map-overview-mono-en.png) / [Mono after](screenshots/map-overview-mono-en.png)
- [Difference before](screenshots/before-normalization-player-difference-ru.png) / [Difference after](screenshots/player-difference-ru.png)
- [Mobile inspector](screenshots/mobile-inspector-ru.png) / [static JPEG fallback](screenshots/fallback-jpeg-en.png)

## Browser proof

The broad browser rows used Chromium against `http://127.0.0.1:8281`. Receipt
`task3-browser-20260902T010842Z.json` is PASS for keyboard Color/Mono
reversibility without request or URL changes, mobile, 200% zoom/reflow,
reduced motion, legacy mobile, and WebGL fallback. Its embedded repository HEAD
is the pre-commit `59b0786` because the capture ran immediately before commit;
the candidate code content is identical to reviewed `44f3af9`, and the separate
exact-HEAD objective receipt above removes that provenance ambiguity.

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

`HeatmapExplorerBeta` remains at `0` after acceptance. The first generic helper
reported only a `floors_json` comparison mismatch caused by double escaping in
its temporary expected value; that was a helper assertion defect, not a product
restore failure. Final independent manual readback then matched exactly:

- mode `0`, counter `293725`;
- projection `384/1120/1.26`, flips `0/1`, rotate `0`, days `30`, empty floors,
  and crops `0/0/0/0`;
- zero temporary users, fixture rows, and sessions; AUTO_INCREMENT users `0`
  and frags `6937`;
- asset/JPEG/thumb SHA-256
  `ef05c0fae9d8e73eaeab92f4c119dc6d3eeb5c946ad5da7946a49dcba2d5ca15`,
  `258fc395fa5971d3fe0c022e9e1a448e240f88b5313ae340ca42bd6043368039`, and
  `5fb70fee2b6070042ee0cbe80b7e5d5d3e6bb919f923e6ad5860ad9812b0b9ce`;
- no mounts.

Mode meanings remain:

- `0`: legacy v1/JPEG only; direct v2 disabled;
- `1`: legacy by default, explicit `heatmap_explorer=1` opt-in;
- `2`: Explorer by default, explicit `heatmap_legacy=1` rollback.

Promote `0 → 1 internal → 1 public beta → 2 default`. Roll back immediately
to `0` for elevated errors, SLA breach, biased/truncated scenes, or coverage
regression. This document establishes source readiness, acceptance on the
tested local runtime, and local-candidate release readiness. It is not
production deployment or production release acceptance.

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
- visibility RED baseline
  `2026-09-02-modern-heatmap-visibility/old-runtime-visual-gate.json`;
- exact reviewed-HEAD visibility PASS
  `2026-09-02-modern-heatmap-visibility/fixed-runtime-visual-gate-44f3af9.json`;
- broad corrected browser matrix
  `2026-09-01-heatmap-background-grading/task3-browser-20260902T010842Z.json`.

An independent final review of the visibility correction and its evidence
returned `ship` with zero findings.
