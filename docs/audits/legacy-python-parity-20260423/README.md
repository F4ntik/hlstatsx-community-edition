# Legacy-vs-Python Product Parity Audit

## Objective

Run a distributed 1:1 audit between the original non-Python HLstatsX contour
and the integrated Python+i18n product contour. The output is not a fix set.
The output is a reproducible bug inventory and a follow-up bug plan.

## Contours

| Contour | Purpose | Web | DB | Runtime |
|---|---|---|---|---|
| Legacy reference | Original non-Python behavior | `http://127.0.0.1:8181/hlstats.php` | `hlstatsx-legacy-db` / port `3317` | `startersclan/hlstatsx-community-edition:1.11.4-daemon` |
| Python target | Current product behavior | `http://127.0.0.1:8281/hlstats.php` | `hlstatsx-python-db` / port `3327` | `hlstats_py` worker/proxy |

## Parity Contract

- Runtime parity means both contours start from the same baseline and process
  the same retained corpus for the same logical server identity.
- The audited corpus server is `37.230.137.48:27015`, `game='cstrike'`.
- EN web parity means the Python/current web shows the same data, row meaning,
  links, filters, sorts, pagination behavior, and non-destructive form state as
  legacy. Exact HTML markup and translated wording are not required to match.
- RU web validation is target-only data parity plus localization quality:
  Python RU pages must show the same data as Python EN and must not leak
  unexpected English UI labels.
- Destructive admin actions are out of scope for execution. Open the pages,
  inspect their read-only state, and log unsafe flows without submitting them.

## Required Output Files

Create or update these files during the audit:

```text
docs/audits/legacy-python-parity-20260423/
  README.md
  route-inventory.md
  runtime-db-diff.md
  performance.md
  issues.jsonl
  agent-public-overview.md
  agent-player-clan.md
  agent-game-entities.md
  agent-communication.md
  agent-admin.md
  agent-ingame.md
  agent-render-static.md
  agent-runtime-db.md
  bug-plan.md
```

## Execution Notes

- 2026-04-23: Legacy restore bootstrap now seeds
  `37.230.137.48:27015` for `game='cstrike'` and copies
  `hlstats_Servers_Config` from baseline server `172.19.0.1:27015` on
  `-Stack legacy`, matching the existing Python restore contour.
- 2026-04-23: Added `scripts/replay_baseline/replay_legacy_log.py` as the
  reusable legacy stdin replay helper. It accepts a file or sorted `*.log`
  directory corpus, streams without loading the corpus into memory, preserves
  `--server-identity 37.230.137.48:27015`, and prints
  processed/skipped/errors/elapsed/throughput summary.
- 2026-04-23: Legacy smoke replay passed strongly enough to start the full
  legacy corpus. The representative `L0217071.log` smoke wrote players,
  frags, player history, chat, and statsme rows through the Perl backend.
- 2026-04-23: The first full legacy retained-corpus replay attempt failed
  before completion after queuing `1097` files through `L0107052.log`; no final
  helper summary was written. The resulting DB is partial and must not be used
  for DB/runtime diff or page-audit conclusions.
- 2026-04-23: `scripts/replay_baseline/replay_legacy_log.py` was patched after
  that failure so daemon/stdin pipe closure is reported as a replay failure
  instead of being masked as thousands of per-file read errors. The next full
  run must start from a clean `-Stack legacy` restore.
- 2026-04-23: Python `replay_python_log.py` parity path uses UDP into the worker;
  `--send-delay 0` floods the socket and drops most traffic while the helper
  still reports `errors=0`. Full-corpus DB diff vs legacy requires a **positive**
  send delay (default `0.005`); see `performance.md` and `replay_python_log`
  stderr warning when delay is zero.

## Current Blocker: Legacy Full-Corpus Replay

Status:

- Blocked before DB/runtime diff.
- First full legacy retained-corpus attempt is invalid as a reference.
- Partial DB from that attempt must be discarded with a clean
  `restore-baseline.ps1 -Stack legacy` before any comparison.

Observed failure:

- Input corpus: `41,576` retained `.log` files.
- Helper output file:
  `docs/audits/legacy-python-parity-20260423/legacy-full-corpus-replay-20260423.log`.
- Queued files before failure: `1097`.
- Last queued file: `L0107052.log`.
- First observed failure after that point:
  `failed to read scripts\replay_baseline\artifacts\L0107054.log: [Errno 22] Invalid argument`.
- Final observed failure: `[Errno 22] Invalid argument`.
- No final `Replay summary` was written.

Investigation and fix tasks:

1. Restore the legacy contour cleanly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy
```

2. Rerun the full legacy corpus with the patched helper and capture a new log:

```powershell
python scripts\replay_baseline\replay_legacy_log.py scripts\replay_baseline\artifacts --server-identity 37.230.137.48:27015 *> docs\audits\legacy-python-parity-20260423\legacy-full-corpus-replay-rerun.log
```

3. If the rerun fails near `L0107052` / `L0107054`, create a small temporary
   failure-window directory containing logs around that point and rerun with
   daemon output enabled:

```powershell
python scripts\replay_baseline\replay_legacy_log.py <failure-window-dir> --server-identity 37.230.137.48:27015 --daemon-output inherit *> docs\audits\legacy-python-parity-20260423\legacy-failure-window.log
```

4. Classify the root cause:

- helper pipe handling
- Perl daemon crash or stdin/import limit
- malformed or corpus-specific log input
- Docker/runtime resource issue
- accepted legacy limitation that requires corpus segmentation

5. Fix or document the chosen mitigation, then repeat from a clean legacy
   restore until a final helper summary and final DB counts are captured.

Do not proceed to `compare_stats_dbs.py`, route inventory, or page mini-agents
until the legacy reference full replay is either cleanly completed or the
remaining limitation is explicitly accepted and represented in the parity plan.

## Issue Format

Append one JSON object per finding to `issues.jsonl`:

```json
{
  "id": "LP-001",
  "agent": "public-overview",
  "severity": "P1",
  "area": "web/public",
  "route_legacy": "http://127.0.0.1:8181/hlstats.php?mode=players&game=cstrike",
  "route_python_en": "http://127.0.0.1:8281/hlstats.php?mode=players&game=cstrike&lang=en",
  "route_python_ru": "http://127.0.0.1:8281/hlstats.php?mode=players&game=cstrike&lang=ru",
  "expected": "Python EN shows the same player rows and sort order as legacy; RU shows the same data with Russian labels.",
  "actual": "Python route differs in row count or visible value.",
  "evidence": "Screenshot path, HTML snippet, SQL count, or container log excerpt.",
  "repro": "Exact URL and steps.",
  "notes": "Normalization rule, known exception, or open question."
}
```

Severity:

- `P0`: crash, data loss, page unusable, replay/runtime blocker.
- `P1`: DB/statistical mismatch, wrong player/server/map data, broken core
  route.
- `P2`: visible page parity issue, broken link, broken form, bad pagination or
  sort.
- `P3`: translation leak, cosmetic mismatch, layout issue, low-risk legacy
  difference.

## Phase 0: Prepare Comparable State

1. Confirm fixed-name comparison containers are free or intentionally owned by
   this audit.
2. Bring up the legacy and Python comparison DB containers.
3. Restore both DBs from the same baseline:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack legacy
powershell -ExecutionPolicy Bypass -File scripts\replay_baseline\restore-baseline.ps1 -Stack python
```

4. Ensure both DBs contain exactly one replay corpus server:

```sql
SELECT serverId, address, port, game, publicaddress, name
FROM hlstats_Servers
WHERE address = '37.230.137.48' AND port = 27015;
```

5. If legacy does not contain that row after restore, add the same bootstrap
   logic used by the Python restore path before any full parity audit.
6. Ensure both replay servers have copied `hlstats_Servers_Config` rows from
   the baseline server.
7. Confirm both DBs are clean before replay:

```sql
SELECT COUNT(*) FROM hlstats_Players;
SELECT COUNT(*) FROM hlstats_Events_Frags;
SELECT COUNT(*) FROM hlstats_Players_History;
```

## Phase 1: Full Corpus Replay

Python/current replay command (UDP path):

```powershell
python scripts\replay_baseline\replay_python_log.py scripts\replay_baseline\artifacts --server-identity 37.230.137.48:27015 --send-delay 0 --drain-delay 10
```

Python/current replay command (recommended fast path via FTP import + optional GeoIP):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\replay_baseline\comparison\python\Run-ContourFtpArtifacts.ps1 -SkipBuild -NoCap
```

Notes for parity safety:
- FTP path must import the same retained corpus and preserve server identity
  `37.230.137.48:27015`.
- Keep/import manifests so legacy and Python inputs remain comparable.
- The helper now runs `hlstats_awards_py --geoip` after import by default.
  Use `-SkipGeoIp` only for targeted debug runs and record it in audit notes.

Legacy replay uses `scripts/replay_baseline/replay_legacy_log.py`. The helper
must:

- read `scripts/replay_baseline/artifacts/*.log` in sorted order
- stream lines to the legacy daemon without loading the full corpus into memory
- preserve `--server-ip=37.230.137.48` and `--server-port=27015`
- record processed/skipped/error counts
- record elapsed time and throughput

Record both runs in `performance.md`:

- start/end wall time
- processed/skipped/error file count
- lines or datagrams sent
- files/sec
- lines/sec or datagrams/sec
- final DB count summary
- container CPU/memory snapshots if available

## Phase 2: Runtime DB Parity

Run the compact diff after both replays:

```powershell
python scripts\replay_baseline\compare_stats_dbs.py --max-examples 20
```

Save output in `runtime-db-diff.md`.

Runtime agent must additionally query:

- `hlstats_Servers`
- `hlstats_Players`
- `hlstats_Events_Frags`
- `hlstats_Events_PlayerActions`
- `hlstats_Events_TeamBonuses`
- `hlstats_Events_Statsme`
- `hlstats_Events_Statsme2`
- `hlstats_Players_History`
- `hlstats_Weapons`
- `hlstats_Actions`
- `hlstats_Maps_Counts`
- country/flag fields in player rows

For country parity, run explicit GeoIP maintenance on the Python contour before
declaring DB parity:

```powershell
python -m hlstats_awards_py --configfile scripts/hlstats.conf --geoip
```

If strict GeoIP fails because GeoLite sources are missing, treat it as an
operational blocker and log it; do not silently accept blank country/flag
fields as parity.

If DB parity fails, page agents may still run, but every page finding must
state whether it is likely downstream of the DB mismatch.

## Phase 3: Route Inventory

Create `route-inventory.md` before page agents start.

For each route record:

- owner agent
- legacy URL
- Python EN URL
- Python RU URL when applicable
- required entity id or fixture source
- destructive or read-only status
- expected data anchor

Recommended entity anchors:

- replay server: `server_id=2`
- top player by kills
- top map by event count
- top weapon by kills
- top clan if present
- top action if present

## Phase 4: Mini-Agent Assignments

### Agent 0: Orchestrator

Owns:

- contour state
- route inventory
- final issue merge
- duplicate detection
- final `bug-plan.md`

Stop conditions:

- baseline restore fails
- legacy reference cannot replay the same corpus
- both contours are not accessible
- a destructive admin route is required to continue

### Agent 1: Public Overview

Routes:

- `mode=contents`
- `mode=gameslist`
- `mode=game&game=cstrike`
- `mode=servers&server_id=2&game=cstrike`
- `mode=players&game=cstrike`
- `mode=clans&game=cstrike`
- `mode=countryclans&game=cstrike`
- `mode=countryclansinfo` if entity data exists

Check:

- HTTP status
- no PHP fatal/warning text
- table row counts
- first 3 visible rows
- primary links resolve
- pagination and sort links keep game/lang state
- RU page uses Russian UI labels and same data as Python EN

### Agent 2: Player and Clan Detail

Routes:

- `mode=playerinfo&player=<top_player_id>`
- `mode=playerhistory&player=<top_player_id>`
- `mode=playersessions&player=<top_player_id>`
- `mode=playerawards&player=<top_player_id>`
- playerinfo subpanels visible from the page
- `mode=claninfo&clan=<top_clan_id>` and claninfo subpanels if clans exist
- `mode=profile&player=<top_player_id>` if supported by the route

Check:

- top player identity and key stats
- weapon/map/team/action subtables
- session/history rows
- graph/image links
- tab links and selected state
- RU labels and no unexpected English UI leaks

### Agent 3: Game Entities

Routes:

- `mode=maps&game=cstrike`
- `mode=mapinfo&map=<top_map>&game=cstrike`
- `mode=weapons&game=cstrike`
- `mode=weaponinfo&weapon=<top_weapon>&game=cstrike`
- `mode=actions&game=cstrike`
- `mode=actioninfo&action=<top_action>&game=cstrike`
- `mode=roles&game=cstrike`
- `mode=rolesinfo&role=<role>&game=cstrike`
- `mode=awards&game=cstrike`
- `mode=awards_daily&game=cstrike`
- `mode=awards_global&game=cstrike`
- `mode=awards_ranks&game=cstrike`
- `mode=awards_ribbons&game=cstrike`
- `mode=dailyawardinfo` / `rankinfo` / `ribboninfo` when linked

Check:

- entity counts and names
- detail-page key stats
- empty states
- links back to player/detail pages
- sort and pagination
- RU labels

### Agent 4: Communication and Misc Public

Routes:

- `mode=chat&game=cstrike`
- `mode=chathistory&game=cstrike`
- `mode=bans&game=cstrike`
- `mode=livestats&game=cstrike`
- `mode=search`
- `mode=help`
- `mode=teamspeak`
- `mode=ventrilo`
- `mode=voicecomm_serverlist`

Check:

- route availability
- search form behavior without destructive writes
- encoding of chat/player names
- empty states for unavailable voice servers
- RU labels and no unexpected English UI leaks

### Agent 5: Admin Read-Only

Routes:

- `mode=admin`
- `mode=admin&task=servers&game=cstrike`
- `mode=admin&task=serversettings&server_id=2&game=cstrike`
- `mode=admin&task=newserver&game=cstrike`
- `mode=admin&task=games`
- `mode=admin&task=options`
- `mode=admin&task=actions&game=cstrike`
- `mode=admin&task=weapons&game=cstrike`
- `mode=admin&task=ranks&game=cstrike`
- `mode=admin&task=roles&game=cstrike`
- `mode=admin&task=teams&game=cstrike`
- `mode=admin&task=clantags`
- `mode=admin&task=hostgroups`
- `mode=admin&task=voicecomm`
- `mode=admin&task=adminusers`
- award/ribbon admin tasks
- tools routes only in read-only open mode

Check:

- login/session flow
- HTTP status
- form fields and selected values
- no accidental submit
- copied server config is visible for `37.230.137.48:27015`
- RU labels
- PHP warnings/notices

### Agent 6: Ingame

Routes via `ingame.php`:

- `mode=players&game=cstrike`
- `mode=servers&game=cstrike`
- `mode=status&game=cstrike`
- `mode=load&game=cstrike`
- `mode=maps&game=cstrike`
- `mode=mapinfo&game=cstrike`
- `mode=weapons&game=cstrike`
- `mode=weaponinfo&game=cstrike`
- `mode=accuracy&game=cstrike`
- `mode=actions&game=cstrike`
- `mode=clans&game=cstrike`
- `mode=bans&game=cstrike`
- `mode=kills&game=cstrike`
- `mode=statsme&game=cstrike`
- `mode=targets&game=cstrike`
- `mode=motd&game=cstrike`
- `mode=help&game=cstrike`

Check:

- compact page renders
- no PHP fatal/warning text
- same data anchors as public pages
- RU/EN behavior
- route-specific empty states

### Agent 7: Render and Static Endpoints

Routes:

- `status.php?lang=en|ru`
- `show_graph.php` links discovered from pages
- `trend_graph.php` links discovered from pages
- `sig.php` for a known player if supported
- image and graph URLs referenced by audited pages
- heatmap/map side panels if linked

Check:

- HTTP status
- content type
- image renders, not HTML error text
- no broken image links
- no raw PHP warnings in binary/text output
- RU labels where endpoint renders HTML/text

### Agent 8: Runtime and DB

Owns:

- `runtime-db-diff.md`
- DB count snapshots
- known normalization classification
- accepted legacy-difference list

Check:

- compact diff tables
- full count drift by table
- country/flag behavior
- auth normalization artifacts
- player history and awards drift
- server counters
- top entities used by page agents

## Phase 5: Page Check Protocol

For every assigned route:

1. Open legacy EN URL.
2. Open Python EN URL.
3. Open Python RU URL when applicable.
4. Record HTTP status and final URL.
5. Scan HTML for fatal/warning/SQL error text.
6. Capture stable text anchors and first 3 table rows.
7. Check key links and sort/pagination links.
8. Compare visible data.
9. Compare Python EN vs Python RU data.
10. Append `issues.jsonl` only for reproducible mismatches.

## Phase 6: Final Bug Plan

`bug-plan.md` must contain:

- summary counts by severity and area
- confirmed bugs
- suspected bugs needing deeper repro
- accepted legacy differences
- duplicate/merged findings
- root-cause groups:
  - Python parser/runtime
  - DB/bootstrap/config
  - web route logic
  - i18n RU leak
  - accepted legacy difference
  - test/tooling gap
- proposed fix order
- validation command or route for each bug

## Acceptance Gates

- Legacy and Python DBs were restored from the same baseline.
- Both contours contain `37.230.137.48:27015`.
- Both contours processed the same retained corpus, or the reference blocker is
  explicitly logged.
- Runtime diff was captured before page conclusions.
- All route groups have an agent report.
- Every issue has a repro URL/SQL/log/screenshot anchor.
- Destructive admin actions were not executed.
- RU findings are separated from legacy-vs-Python data parity findings.

## Known Risks and Assumptions

- Legacy full-corpus replay may need prep tooling before this audit can be
  considered authoritative.
- The Python/current `8281` web uses integrated i18n code and is expected to
  differ in wording from legacy EN where labels were intentionally modernized.
- Legacy is not a RU reference.
- Some route differences may be caused by known runtime parser gaps rather than
  web bugs; classify them under runtime if DB diff confirms the cause.
- Fixed container names can conflict with other local stacks.
