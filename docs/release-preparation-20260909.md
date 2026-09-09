# September release preparation

This candidate integrates the Explorer work through the September 8 map refresh
and the runtime/web findings from the September 8 release review. The original
development worktrees and their uncommitted changes are preserved separately.

## Review closure

- Runtime: mysqlclient ping compatibility, connection ownership during online
  transactions, InnoDB runtime tables, game-scoped player identity, payload-safe
  PROXY parsing, bounded ingress/forward queues and drain-on-stop handling.
  Overflow messages are coalesced over five-second intervals with exact loss
  counters, avoiding synchronous logging for every dropped packet.
  Optional team-bonus diagnostics retain at most 200 distinct keys per stage
  and dimension, with separate omitted-occurrence counters and bounded samples.
- Python 3.10: storage timeout handling now reaches the fail-closed shutdown path.
- Administration: CSRF before mutation, registry access levels before dispatch,
  POST confirmation for optimization, modern password hashes, strict legacy MD5
  upgrade, rotating password-free sessions and database-backed session revocation.
  Public routes also recheck password changes, session expiry and current access
  levels before authorizing IP search.
- Updater: HTTP is denied; the trusted CLI initializes its request context,
  applies migration 83 and checks the resulting database version before success.
  A shutdown guard makes legacy bare-exit failures return a nonzero status.
  Legacy schemas with a higher version marker also receive an explicit,
  idempotent password-capacity check and repair. Their schema/application
  version markers and existing password values are preserved.
- Heatmaps: base uploads must match existing floor-image dimensions before
  staging any files. The upgrade archive preserves installed images/calibration;
  only fresh installs receive the native map defaults and matching seeds.
- CI: EN/RU validation, administrator security smoke and repaired proxy
  formatting/type checks. Unconfigured Google world maps are omitted.

Smooth heatmap rendering can still soften a boundary across a wall. Floor masks
exclude events and fill within their configured polygons; bundled BSP outlines
are visual references, not automatic walkability or floor reconstruction.

## Verification already performed during preparation

- Python 3.10: 310 product tests, 61 operational-tool tests, 95 replay-helper
  tests and 101 proxy tests passed. The two opt-in MariaDB tests passed separately
  with the current source mounted into an isolated worker container.
- Proxy Ruff, Black and Mypy passed using the CI dependency versions. Both
  heatmap JavaScript smoke commands and the PHP heatmap/admin checks passed.
- EN/RU catalogs have 1,258 matching keys. Public HTTP routes passed in both
  languages on a disposable web server.
- Fresh install created schema 83, a 255-character password field and all 24
  InnoDB tables. Upgrade from the old schema applied the two explicit runtime
  SQL migrations and the actual trusted CLI updater. Backup restore and online
  transaction rollback were checked in separate synthetic databases.
- HTTP checks covered legacy login upgrades, special-character passwords,
  session rotation, missing/invalid CSRF, level-80 reset denial, strict magic-hash
  rejection, heatmap preview/upload and password-change revocation. Direct public
  IP-search requests were denied after password change, downgrade and expiry;
  all three stale-session bypasses were reproduced before the fix.
- An incompatible base-image upload returned `400 floor_image_size` while both
  existing image hashes remained unchanged. Upgrade overlay preserved live
  config and the old map-image pair. Browser checks covered the Russian home
  page and the authenticated floor editor on this preserved image.

The final replay comparison, fresh independent review and final archive checks
are recorded in the external acceptance receipt accompanying the artifacts.
Only a receipt naming the exact full commit and archive hashes can accept that
artifact. Earlier screenshots or another commit's parity result do not do so.

## Replay isolation incident

An initial September 9 preparation run accidentally wrote its 1,000-file legacy
replay to the pre-existing local legacy database. The staging wrapper omitted
the helper's database-container and network arguments, and the helper selected
its old defaults. This run is invalid acceptance evidence. It was stopped and
reported; no automatic restore of the pre-existing database was attempted,
because there was no exact pre-run snapshot from which to prove a safe rollback.

The helper now requires both routing arguments before any Docker operation.
The replacement staging run checks explicit network membership and aliases and
rejects containers outside its own namespace. Its receipt and the incident's
timestamps, argv and observed database state are retained in the workspace's
`audit_reports/release-prep-20260909/isolated-acceptance/` directory.

## Distribution

Use [install/upgrade instructions](release-install-upgrade.md) and the
[trusted updater runbook](web_updater_runbook.md). The builder reads only committed
blobs, produces distinct archives and writes SHA-256 manifests. Archives omit
corpora, dumps, caches, test tools, audit captures and local acquisition tools;
the obsolete one-off legacy heatmap script was removed from source.
No public release or production deployment is implied by local preparation.
