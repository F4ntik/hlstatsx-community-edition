# Plans

## Source
- Task: prepare an upstream-friendly web RU i18n PR for `A1mDev/hlstatsx-community-edition`, then remediate the highest-priority review findings and continue the RU i18n cleanup on remaining admin/runtime surfaces
- Canonical input:
  - user request to evaluate the current implementation, remove the hybrid i18n approach, and exclude SQL fixes from the translation PR
  - follow-up request to add the review findings to the plan and start fixing them
  - follow-up request on 2026-04-21 to continue the i18n work and use sub-agents where helpful per file
- Repo context: `web/` public PHP frontend in `hlstatsx-community-edition-web-ru-i18n`
- Last updated: 2026-04-21

## Assumptions
- The target upstream branch is `upstream/master`.
- The upstream PR must stay scoped to public `web/` UI translation only.
- English remains the default language; Russian is additive.
- Perl/Python/SQL layers and DB-content translation stay out of scope.
- The review-remediation pass is allowed to touch the cited admin and ingame PHP pages only:
  - `web/pages/admintasks/tools_reset.php`
  - `web/pages/ingame/help.php`
  - `web/pages/ingame/accuracy.php`
  - `web/status.php`
- The user has since explicitly approved continuing the RU i18n cleanup on nearby admin/auth/editdetails surfaces when that materially advances the same public web i18n branch:
  - `web/pages/admin.php`
  - `web/pages/adminauth.php`
  - `web/pages/admintasks/newserver.php`
  - `web/pages/admintasks/tools_editdetails_player.php`
  - `web/pages/admintasks/tools_editdetails_clan.php`
- SQL strict-mode fixes and query semantics changes will be split into a separate commit or branch.
- Existing local smoke environment remains available at `http://localhost:8381/hlstats.php`.

## Validation Assumptions
- Local host shell does not expose `php` in `PATH`; syntax validation will run inside Docker container `hlstatsx-web-ru-web`.
- Runtime validation will use browser-less HTTP smoke checks plus targeted `php -l` inside the container.

## Milestone Order
| ID | Title | Depends on | Status |
| --- | --- | --- | --- |
| M1 | Isolate PR scope from SQL and non-i18n changes | - | [x] |
| M2 | Replace hybrid translation flow with explicit i18n runtime | M1 | [x] |
| M3 | Reconcile public page coverage on direct `t(...)` calls | M2 | [~] |
| M4 | Remediate review findings on targeted admin/ingame/status surfaces | M3 | [x] |
| M5 | Fix runtime edge cases and validate EN/RU behavior | M4 | [ ] |
| M6 | Prepare reviewable commit stack and PR handoff | M5 | [ ] |

## M1. Isolate PR scope from SQL and non-i18n changes `[x]`
### Goal
- The translation PR diff contains only public web i18n changes.

### Tasks
- [x] Identify all changed files and hunks that are not part of public web RU i18n.
- [x] Separate SQL-related changes, especially `GROUP BY` or strict-mode fixes, into a dedicated commit or side branch.
- [x] Confirm that the retained diff only covers `web/` public UI translation, i18n runtime, and dictionaries.

### Definition of Done
- No SQL semantics changes remain in the i18n PR branch.
- The future PR can be described as "public web RU i18n only" without caveats.

### Notes
- The residual SQL-scope drift was limited to mixed `GROUP BY` changes inside `web/pages/playerinfo_general.php`.
- Those query changes were reverted back to the upstream SQL shape while keeping the RU/EN translation strings in place.
- The remaining diff is now constrained to public `web/` i18n runtime, dictionaries, and explicit UI copy replacement.

### Validation
```sh
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff --name-only
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff -- web
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff -- web/pages/playerinfo_general.php
```

### Known Risks
- Some mixed hunks may contain both translation and SQL cleanup, which makes surgical separation tedious.
- Existing worktree state may include manual edits that are not yet committed.

### Stop-and-Fix Rule
- If a retained hunk still changes SQL behavior, split or revert that hunk before moving on.

## M2. Replace hybrid translation flow with explicit i18n runtime `[x]`
### Goal
- The frontend uses one explicit translation mechanism instead of a hybrid of direct keys, literal maps, and full-document post-processing.

### Tasks
- [x] Remove global output rewriting from `web/hlstats.php`.
- [x] Remove DOM/regex post-render translation helpers from `web/includes/i18n.php`.
- [x] Reduce shared helper behavior to explicit, narrow helpers only where direct `t(...)` calls are impractical.
- [x] Re-check `web/includes/functions.php` and trim `translate_ui_literal(...)` to the smallest defensible shared surface, or remove it entirely if no longer justified.

### Definition of Done
- No request path depends on `translate_output_html(...)` or equivalent whole-page rewriting.
- The i18n runtime consists of language resolution, dictionary loading, fallback, and direct key lookups.

### Notes
- `ob_start('translate_output_html')` is gone from `web/hlstats.php`.
- `web/includes/i18n.php` now stops at language resolution, catalog loading, fallback lookup, and URL generation.
- `translate_ui_literal(...)` remains only as a narrow legacy bridge for shared table/header literals while page-level public copy moves to explicit `t(...)`.
- Public pages that visibly depended on post-processing during smoke cleanup were moved to explicit keys, including `help.php`, `clans.php`, `actions.php`, `maps.php`, `weapons.php`, `roles.php`, selected `claninfo*` pages, `countryclansinfo.php`, and `voicecomm_serverlist.php`.

### Validation
```sh
docker exec hlstatsx-web-ru-web php -l /var/www/html/includes/i18n.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/hlstats.php
```

### Known Risks
- Removing post-processing will expose untranslated strings that were previously masked.
- Shared UI helpers may still hide a second translation source of truth if not reduced aggressively.

### Stop-and-Fix Rule
- If any page still depends on whole-document translation to render RU correctly, translate that page explicitly before proceeding.

## M3. Reconcile public page coverage on direct `t(...)` calls `[~]`
### Goal
- Public pages render RU via explicit translation keys and maintain EN fallback without hidden translation layers.

### Tasks
- [x] Review shared public entry points: `header.php`, `footer.php`, `search-class.php`, `search.php`, `class_table.php`, `functions.php`.
- [~] Review list pages: `contents.php`, `game.php`, `players.php`, `clans.php`, `countryclans.php`, `maps.php`, `weapons.php`, `actions.php`, `roles.php`.
- [~] Review detail pages already touched for RU coverage: `playerinfo*`, `claninfo*`, `chat.php`, `livestats.php`, `servers.php`, `awards*`.
- [x] Add or normalize dictionary keys in `web/lang/en.php` and `web/lang/ru.php`.
- [ ] Remove dictionary keys that existed only to support global HTML post-processing.

### Definition of Done
- Main public flows no longer rely on hybrid translation behavior.
- Dictionary keys match the explicit copy rendered by the retained pages.

### Validation
```sh
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff -- web/lang/en.php web/lang/ru.php
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n grep -n "translate_ui_literal(" -- web
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/search-class.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/header.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/footer.php
```

### Known Risks
- Coverage may temporarily regress while removing the hybrid layer.
- Some strings may be duplicated under inconsistent key namespaces and need cleanup.
- Shared `TableColumn` sorting/header paths still retain a narrow `translate_ui_literal(...)` fallback, so full helper removal depends on converting the remaining legacy column titles or accepting that residual bridge for out-of-scope surfaces.

### Stop-and-Fix Rule
- If a page loses visible RU coverage after hybrid removal, translate that page explicitly before advancing.

## M4. Remediate review findings on targeted admin/ingame/status surfaces `[x]`
### Goal
- Close the concrete review findings without reopening the broader out-of-scope admin/ingame translation backlog.

### Tasks
- [x] Convert `web/pages/admintasks/tools_reset.php` status, confirmation, and action labels to explicit dictionary-backed text.
- [x] Convert `web/pages/ingame/help.php` visible command/help copy to explicit dictionary-backed text.
- [x] Remove the remaining visible hardcoded English in `web/status.php`.
- [x] Convert `web/pages/ingame/accuracy.php` errors and column labels to explicit dictionary-backed text.
- [x] Polish the reviewed RU dictionary entries that are semantically wrong or unsuitable for compact UI.
- [x] Keep dictionary additions synchronized in `web/lang/en.php` and `web/lang/ru.php`.

### Definition of Done
- The five cited review findings are addressed in code rather than only documented.
- The touched pages render through `t(...)` lookups or existing dictionary-backed helpers.
- RU wording for the corrected keys is fit for UI use.

### Validation
```sh
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/admintasks/tools_reset.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/ingame/help.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/ingame/accuracy.php
docker exec hlstatsx-web-ru-web php -l /var/www/html/status.php
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=admin' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=help' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/status.php?lang=ru&game=cstrike&server_id=1' -UseBasicParsing | Out-Null"
```

### Known Risks
- These files were previously outside the narrow public-page scope, so they may contain more legacy hardcoded text than the initial findings exposed.
- The standalone `status.php` widget has bespoke rendering paths that can hide additional untranslated labels.

### Stop-and-Fix Rule
- If a touched page still emits visible English after the remediation pass, keep converting that page until the reviewed surface is coherent.

## M5. Fix runtime edge cases and validate EN/RU behavior `[ ]`
### Goal
- Language switching, fallback behavior, caching, and logout all behave correctly in both languages.

### Tasks
- [x] Fix logout redirect so it does not preserve `logout=1`.
- [x] Ensure `lang_url(...)` can produce a clean URL without transient query params.
- [x] Keep historical cache keys language-aware.
- [ ] Verify fresh-session fallback to EN.
- [x] Verify RU persistence through query param, cookie, and session, including invalid `lang` fallback behavior.
- [ ] Verify generated HTML stays structurally valid without XML/document corruption.

### Definition of Done
- No logout redirect loop remains.
- RU and EN both render from the same explicit runtime with stable HTML output.
- Invalid or stale `lang` query params do not clobber an already persisted valid language choice.

### Notes
- `init_i18n()` now walks `GET -> cookie -> session -> en` by first valid supported language instead of treating an invalid `GET` value as a forced reset to EN.
- `lang_url(...)` now returns the base URL cleanly when all transient params were removed, instead of appending a dangling `?`.
- The runtime checks confirmed that historical-cache request hashing is still language-aware because `current_lang()` is injected into the cache key input in `web/hlstats.php`.
- The same pass also cleaned remaining shared admin UI strings in `web/pages/admin.php` and moved `adminauth.php` / `tools_editdetails_*` form labels off fragile raw English literals where direct keys already existed.

### Validation
```sh
curl.exe -s -D - -o NUL "http://localhost:8381/hlstats.php?lang=ru&mode=contents&logout=1"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=en&mode=contents' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=contents' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=en&mode=search' -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=search' -UseBasicParsing | Out-Null"
powershell -Command "$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession; Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=contents' -WebSession $session -UseBasicParsing | Out-Null; Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=zz&mode=contents' -WebSession $session -UseBasicParsing | Out-Null"
powershell -Command "Invoke-WebRequest -Uri 'http://localhost:8381/hlstats.php?lang=ru&mode=admin' -UseBasicParsing | Out-Null"
```

### Known Risks
- Browser-tolerated markup issues may still exist even after basic HTTP checks.
- Cookie/session behavior can differ between fresh requests and an already warmed local environment.

### Stop-and-Fix Rule
- If any smoke check shows malformed HTML, redirect loops, or broken EN fallback, fix that runtime defect before PR preparation.

## M6. Prepare reviewable commit stack and PR handoff `[ ]`
### Goal
- The branch is easy for `A1mDev` to review and the PR description accurately reflects the real scope.

### Tasks
- [ ] Split retained work into reviewable commits:
  - i18n runtime and language selection
  - shared UI and dictionary support
  - public page translation coverage
- [ ] Keep SQL fixes out of this stack.
- [ ] Write a compact PR description with strict scope and validation notes.
- [ ] Update handoff docs if the plan changed materially during cleanup.

### Definition of Done
- The final branch history is clean enough for upstream review.
- Another run can open the PR without reconstructing intent from chat history.

### Validation
```sh
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n status --short
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff --stat
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n log --oneline --decorate -n 10
```

### Known Risks
- If commit boundaries are chosen too late, cleanup work may have to be restaged repeatedly.
- Residual mixed hunks can make the final history noisier than intended.

### Stop-and-Fix Rule
- If a commit message cannot be described as one coherent upstream concern, split or reorder it before handoff.
