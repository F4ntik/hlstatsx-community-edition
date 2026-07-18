# Test Plan: Web Frontend i18n

Historical donor-web test note only.

This file is retained as reference for the older web-only i18n pass. Use
`docs/test-plan.md` for the current integrated product-lane validation matrix.

## Objective

Verify that the frontend translation pass removes unintended English UI text
from the visible PHP frontend and supporting JS while preserving behavior,
placeholders, technical identifiers, and navigation flow.

## Test levels

- Static coverage scan:
  search the frontend for user-facing English text after each batch.
- File validation:
  run PHP syntax checks on changed PHP files.
- Page smoke:
  open representative admin, public, ingame, and status pages in a browser.
- Translation quality review:
  inspect short labels, plural forms, and placeholder-heavy strings manually.

## Critical fixtures

- `web/lang/en.php`
- `web/lang/ru.php`
- `web/pages/adminauth.php`
- `web/pages/admin.php`
- `web/pages/admintasks/options.php`
- `web/pages/admintasks/newserver.php`
- `web/status.php`
- `web/show_graph.php`
- `web/pages/ingame/claninfo.php`
- `web/pages/ingame/accuracy.php`
- `web/pages/teamspeak_class.php`
- `web/includes/js/search-suggestions.js`
- `web/includes/js/tabs.js`
- `web/includes/js/syntax.js`

## Smoke coverage

- Admin login screen renders localized labels and helper text.
- Admin shell menus and tool pages render translated visible labels.
- A representative admin form can still be submitted after translation.
- Public status and graph pages still render titles, links, and image labels.
- Ingame pages still render summary labels and table headers.
- Teamspeak prompts and JS alerts remain functional.

## Acceptance gates

- No unintended English user-facing strings remain in the audited frontend
  surfaces.
- Intentional technical terms remain untouched.
- Placeholders, counts, and short labels still fit their UI context.
- PHP lint passes on every changed PHP file.
- Browser smoke does not reveal broken links, missing labels, or navigation
  regressions.

## Negative cases

- A translation change breaks placeholder order or leaves an unfilled token.
- A short label becomes too long and harms table layout.
- An intentional technical term is translated when it should stay as-is.
- A frontend JS alert or prompt loses its behavior after localization.

## Release readiness

- The file-level scan no longer finds stray user-facing English in the audited
  frontend surfaces.
- The representative browser smoke set passes in both admin and public areas.
- Any remaining English is documented as an intentional technical exception,
  not an omission.
