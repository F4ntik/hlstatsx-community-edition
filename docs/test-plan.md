# Test Plan

## Source
- Task: prepare a reviewable upstream PR for web RU i18n without hybrid translation or SQL fixes, then remediate the highest-priority review findings
- Plan file: `docs/plans.md`
- Status file: `docs/status.md`
- Repo context: `web/` public PHP frontend in `hlstatsx-community-edition-web-ru-i18n`
- Last updated: 2026-04-21

## Validation Scope
- In scope:
  - language selection and persistence
  - invalid-language fallback that must not overwrite an already persisted valid language
  - EN fallback behavior
  - public `web/` page rendering after removing whole-document translation
  - shared UI translation paths in header, footer, search, tables, lists, and selected detail pages
  - targeted remediation of the reviewed admin/ingame/status files
  - follow-up cleanup on the shared admin/auth/editdetails/newserver surfaces
  - logout redirect behavior
  - syntax validity of touched PHP files through the Docker PHP runtime
- Out of scope:
  - full admin area translation sweep
  - full ingame area translation sweep
  - SQL strict-mode fixes
  - Perl/Python/worker behavior
  - DB-content translation
  - image asset localization such as `title-*.png`

## Environment / Fixtures
- Data fixtures: local seeded demo data currently served at `http://localhost:8381/hlstats.php`
- External dependencies: Docker container `hlstatsx-web-ru-web`, local Apache/PHP runtime inside the container, MySQL demo dataset
- Setup assumptions:
  - container `hlstatsx-web-ru-web` is running
  - target site remains reachable on port `8381`
  - syntax checks use `docker exec ... php -l` because host `php` is unavailable

## Test Levels

### Unit
- Not applicable as a primary gate; this slice is legacy PHP page assembly rather than isolated unit-tested code.
- If helper logic is materially changed, review helper behavior directly in:
  - `web/includes/i18n.php`
  - `web/includes/functions.php`
  - `web/includes/class_table.php`

### Integration
- Validate language resolution order:
  - explicit `?lang=ru`
  - cookie persistence
  - session persistence
  - fallback to `en`
- Validate historical cache remains language-aware.
- Validate logout redirect target does not retain `logout=1`.
- Validate pages that previously depended on hybrid output rewriting still render intended RU copy after explicit translation cleanup.

### End-to-End / Smoke
- `?lang=en&mode=contents`
- `?lang=ru&mode=contents`
- `?lang=en&mode=search`
- `?lang=ru&mode=search`
- `?lang=en&game=cstrike&mode=players`
- `?lang=ru&game=cstrike&mode=players`
- `?lang=en&game=cstrike&mode=clans`
- `?lang=ru&game=cstrike&mode=clans`
- `?lang=en&game=cstrike&mode=playerinfo&player=32`
- `?lang=ru&game=cstrike&mode=playerinfo&player=32`
- `?lang=ru&game=cstrike&mode=servers&server_id=1`
- `?lang=ru&mode=contents&logout=1`
- `?lang=ru&mode=help`
- `?lang=ru&mode=admin`
- `http://localhost:8381/status.php?lang=ru&game=cstrike&server_id=1`

## Negative / Edge Cases
- RU request with missing key falls back to EN instead of exposing raw key names.
- RU session/cookie selection survives a later invalid `?lang=zz` request.
- Fresh request without `lang` defaults to EN.
- Logout request does not redirect to another URL containing `logout=1`.
- RU response does not inject XML preamble or collapse the HTML document structure.
- Search and list pages still render when JavaScript is effectively absent and `nojs` branch is active.
- The targeted admin/ingame/status pages render without exposing the reviewed hardcoded English strings.

## Acceptance Gates
- [x] Translation PR diff no longer contains SQL semantics changes
- [x] `docker exec hlstatsx-web-ru-web php -l ...` passes for all touched PHP files
- [ ] EN smoke checks pass on the retained public pages
- [x] RU smoke checks pass on the retained public pages
- [x] The five cited review findings are resolved on the touched pages and dictionary entries
- [ ] Logout redirect is clean and non-looping
- [ ] No whole-document post-processing remains in the final implementation
- [ ] Final commit stack is reviewable and matches PR scope

## Release / Demo Readiness
- [ ] Core public contents flow works in EN and RU
- [ ] Core search flow works in EN and RU
- [ ] At least one player detail flow works in EN and RU
- [ ] At least one server/listing flow works in EN and RU
- [ ] No blocker-level runtime issue remains
- [ ] PR summary can state exact scope without exceptions for SQL or hybrid rendering

## Command Matrix
```sh
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff --name-only
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff -- web
docker exec hlstatsx-web-ru-web php -l /var/www/html/hlstats.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/includes/i18n.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/includes/functions.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/header.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/footer.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/admintasks/tools_reset.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/ingame/help.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/ingame/accuracy.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/status.php
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=en&mode=contents' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=contents' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=en&mode=search' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=search' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=help' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=admin' -UseBasicParsing | Out-Null"
powershell -Command "$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession; Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=contents' -WebSession $session -UseBasicParsing | Out-Null; Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=zz&mode=contents' -WebSession $session -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/status.php?lang=ru&game=cstrike&server_id=1' -UseBasicParsing | Out-Null"
curl.exe -s -D - -o NUL "http://localhost:8381/hlstats.php?lang=ru&mode=contents&logout=1"
```

## Open Risks
- Removing hybrid translation may temporarily expose untranslated text that was previously hidden by post-processing.
- HTTP smoke checks will not catch every markup regression that a real browser could surface.
- The local dataset may not cover every translated page equally well, especially clan-related edge cases.

## Deferred Coverage
- Full admin and ingame translation beyond the cited files
- Full browser-based validation for every touched public page
- SQL strict-mode verification in the separate non-i18n branch
- Asset-level localization for graphical navigation labels
