# Status: Web Frontend i18n

## Current phase

The i18n skeleton exists as the baseline translation architecture, but the
frontend translation pass is not complete. The latest audit confirmed that the
dictionary keys are broadly complete, while many user-facing PHP pages and JS
messages still render English text in the admin area, public pages, ingame
pages, and interactive helpers.

## Done

- Established the translation skeleton in the frontend plan.
- Audited `web/lang/en.php` and `web/lang/ru.php` for key coverage.
- Confirmed the main translation dictionaries are structurally aligned.
- Identified quality issues in `web/lang/ru.php` that need polish.
- Identified untranslated frontend surfaces outside `web/lang/`.

## In progress

- Preparing the full frontend translation backlog for execution in the next
  chat.

## Next

- Start with the admin auth shell and admin navigation surfaces.
- Translate the remaining `web/pages/admintasks/*.php` forms and maintenance
  screens.
- Translate the public/status/ingame pages and the small frontend JS messages.
- Polish the existing Russian dictionary entries that are technically correct
  but read awkwardly.

## Decisions

- Keep product names and technical terms untranslated when they are intentional
  identifiers.
- Use the existing `web/lang/` dictionary pattern as the source of truth.
- Treat visible English in frontend UI as backlog unless it is an intentional
  technical token.

## Assumptions

- No new localization framework is required beyond the existing dictionary
  approach.
- Database content is not part of this pass unless a page renders it as part of
  the visible UI and the translation work needs to preserve labels around it.

## Commands

- File-level string scan:
  `Get-ChildItem D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n\web -Recurse -File | ...`
- PHP syntax validation:
  `php -l <changed-file>`

## Audit log

- 2026-04-21: captured a full frontend translation audit.
- 2026-04-21: confirmed `web/lang/en.php` and `web/lang/ru.php` match on key
  coverage.
- 2026-04-21: identified untranslated English UI text in admin, public, ingame,
  and JS surfaces.
