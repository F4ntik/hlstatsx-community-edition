# Test Plan

This test plan applies to the RU donor lane only.

- It validates upstream-friendly RU `web/` scope.
- It does not validate the standalone Python+i18n product lane, which now lives
  in `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-python-i18n`.

## Source
- Task: prepare a reviewable upstream PR for web RU i18n without hybrid translation or SQL fixes, then continue through the broader admin and ingame RU i18n sweep
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
  - full admin list/form translation coverage where strings are owned by `web/pages/admintasks/*.php`
  - progressive ingame page translation coverage where strings are owned by `web/pages/ingame/*.php`
  - logout redirect behavior
  - syntax validity of touched PHP files through the Docker PHP runtime
- Out of scope:
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
  - live HTTP smoke is currently blocked until the local web runtime can resolve the `mysql` hostname again

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
- The broader admin/ingame sweep pages render without PHP syntax errors even when live DB-backed smoke checks are temporarily unavailable.

## Acceptance Gates
- [x] Translation PR diff no longer contains SQL semantics changes
- [x] `docker exec hlstatsx-web-ru-web php -l ...` passes for all touched PHP files
- [ ] EN smoke checks pass on the retained public pages
- [x] RU smoke checks pass on the retained public pages
- [x] The five cited review findings are resolved on the touched pages and dictionary entries
- [x] The new admin and ingame sweep files pass Docker `php -l`
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
- The current local web runtime is temporarily unhealthy for DB-backed smoke checks because `mysql` hostname resolution is failing.

## Deferred Coverage
- Remaining noisy admin operational pages and the last ingame detail/stat pages not yet converted in this sweep
- Full browser-based validation for every touched public page
- SQL strict-mode verification in the separate non-i18n branch
- Asset-level localization for graphical navigation labels

---

## Code Review Findings (Cascade Agent)

**Agent:** Code Review Agent (Cascade)  
**Date:** 2026-04-21  
**Scope:** PHP i18n layer (`i18n.php`, `functions.php`, `lang/*.php`, web pages)  
**Status:** Pending user triage – see decision checklist below

### Immediate Next Steps (High Priority)

| # | Item | Location | Risk if not addressed | User Decision |
|---|------|----------|----------------------|---------------|
| 1 | Remove `$_GET` / `$_REQUEST` mutation from `init_i18n()` | `includes/i18n.php:113-117` | Side effects surprise downstream code (pagination, etc.) | [ ] Accept [ ] Reject [ ] Modify |
| 2 | Replace `@setcookie` with explicit `headers_sent()` guard | `includes/i18n.php:119` | Debug-mode errors masked; broken flows hidden | [ ] Accept [ ] Reject [ ] Modify |
| 3 | Add `debug_mode` key-leakage logging to `t()` | `includes/i18n.php:89-120` | Untranslated keys surface as technical labels to users | [ ] Accept [ ] Reject [ ] Modify |
| 4 | Add null-guard for `$g_options` in `lang_url()` | `includes/i18n.php:162-177` | PHP notice in strict environments if `$g_options` undefined | [ ] Accept [ ] Reject [ ] Modify |
| 5 | Verify `literal.player_rankings` key exists in EN dictionary | `pages/players.php:69` | Missing key renders literal string to user | [ ] Accept [ ] Reject [ ] Modify |
| 6 | Implement CI dictionary sync check (EN/RU key parity) | CI pipeline | Key drift between dictionaries over time | [ ] Accept [ ] Reject [ ] Modify |

### Additional Recommendations

#### Security
- [ ] **SQL injection risk in `buildSearchSqlSafe()`** – `addcslashes` is legacy; consider prepared statements for `$like_filter` / `$match_filter` if DB layer supports it (out of scope for i18n PR, but track for product lane).
- [ ] **XSS via `lang_url()`** – `$_SERVER['PHP_SELF']` not passed through `htmlspecialchars` before rendering in `<a href="...">` language switcher.
- [ ] **Validation errors not through `t()`** – `checkValidGame()` returns raw English strings; should use keys `error.invalid_game_param` / `error.game_param_missing`.

#### Architecture / Process
- [ ] **Dictionary versioning** – Add `dict_rev` to `meta` array; invalidate historical cache on mismatch to prevent stale-key issues.
- [ ] **PR scope split** – Current ~70+ PHP file changes. Consider 2–3 stacked PRs: (1) runtime + lang selection, (2) shared dictionary, (3) public page coverage for upstream reviewability.
- [ ] **Key ordering** – `ru.php` and `en.php` have different key ordering; makes diff review harder. Standardize or add automated sort check.

### Open Questions for User

1. Should `init_i18n()` mutate superglobals to canonicalize language, or expose `resolved_lang()` helper without mutation?
2. Is SQL-strict mode fix integration acceptable in a follow-up PR, or must i18n PR stay completely free of SQL semantics?
3. Do you want the `debug_mode` flag to log missing keys to a file, stderr, or admin-visible panel?

**Next Action Required:** User to tick decision boxes above and route accepted items to implementation agent.
