# Plan: PHP Frontend Internationalization Skeleton

## Goal
- Prepare the legacy PHP frontend for multilingual support without changing frontend behavior.
- Deliver the first stage as an i18n skeleton only:
  - English stays the default language.
  - Translation lookup is introduced.
  - A language switcher is allowed in the UI.
  - Only PHP-code UI strings are moved behind translation keys.
  - Only the `en` dictionary exists in the first milestone.
- Keep the rollout incremental so translation work can continue page by page later.

## Assumptions / constraints
- Scope is phased. Public frontend comes first; admin and ingame areas can follow later.
- The first implementation milestone is infrastructure, not Russian translation.
- No functional changes are allowed in ranking, search, navigation, pagination, sorting, forms, or database behavior.
- English remains the default language for now.
- Translation scope is limited to UI strings stored in PHP source code.
- Database content stays untouched in the first phase, even if it renders English text.
- A small language switcher may be added to the frontend shell.
- Missing translation keys must fail safely to English.

## Research (current state)
- Modules/subprojects involved:
  - `web/` legacy PHP frontend
  - `web/includes/` shared helpers and rendering primitives
  - `web/pages/` page-level renderers
- Key files/paths:
  - `web/hlstats.php` bootstraps config, session, routing, and shared includes.
  - `web/includes/functions.php` contains shared helpers and is the best place for basic i18n helpers.
  - `web/includes/class_table.php` renders shared table headers, pagination, and repeated UI labels.
  - `web/pages/header.php` contains global navigation, breadcrumbs, and top-level shell text.
  - `web/pages/footer.php` contains shared footer text and auth links.
  - `web/pages/search-class.php` contains reusable search form and results labels.
  - `web/pages/help.php` contains long-form static UI content and is a later-page migration candidate.
- Entrypoints (API/UI/CLI/Jobs):
  - `web/index.php` redirects to `web/hlstats.php`.
  - `web/hlstats.php` is the main public entrypoint.
- Related configs/flags:
  - `web/config.php` currently has DB and path constants only; it does not define locale configuration.
  - `HISTORICAL_CACHE` in `web/hlstats.php` caches based on `$_REQUEST`; language selection must be included in request-sensitive rendering or cache logic.
- Data models/storage touched:
  - No database schema change is required for the first phase.
  - Language state can be stored in request/session/cookie only.
- Interfaces/contracts (APIs/events/IPC):
  - No external API contract change is required.
  - The language switcher only affects rendered HTML labels.
- Existing patterns to follow:
  - Shared rendering already flows through `web/hlstats.php` -> `web/includes/*.php` -> `web/pages/*.php`.
  - Common shell and component files should be converted before individual pages.

## Analysis
### Options
1. Use PHP `gettext`.
   - Pros: standard localization approach, mature ecosystem.
   - Cons: too heavy for this legacy codebase, requires extra runtime/tooling discipline, and complicates incremental rollout on Windows.
2. Introduce a lightweight dictionary layer with PHP arrays and helper functions.
   - Pros: low-risk, incremental, easy to audit, works well with legacy mixed PHP/HTML templates.
   - Cons: requires manual extraction of strings and naming discipline for translation keys.
3. Translate files directly in place without an i18n layer.
   - Pros: fast for a one-off Russian fork.
   - Cons: not scalable, no fallback story, difficult to maintain, and blocks future multilingual support.

### Decision
- Chosen: lightweight dictionary layer with PHP arrays and helper functions.
- Why:
  - It minimizes operational and code risk in a legacy frontend.
  - It supports the user's phased rollout requirement.
  - It allows a first milestone where only `en` exists but the structure is already ready for `ru`.

### Risks / edge cases
- Historical cache may serve the wrong language if language state is not part of cache-sensitive input.
- Shared helpers render user-facing labels in multiple places; missing them creates mixed-language pages.
- Some strings are built dynamically and need parameterized translations rather than raw concatenation.
- Date/time and duration formatting currently produce English output and need a later localized formatter.
- Some labels originate from SQL aliases or database content; those are explicitly out of scope for the first milestone.
- A language switcher must preserve current query parameters so navigation behavior does not change.

### Open questions
- None blocking for the planning phase. The initial scope and rollout order were clarified.

## Q&A results (captured after the session)
- Outcome/acceptance criteria:
  - Create a reusable i18n skeleton for the PHP frontend.
  - Keep the site default language as English.
  - Do not ship Russian text in the first milestone.
  - Make later Russian translation straightforward by adding keys to dictionaries.
- Scope boundaries:
  - Work sequentially.
  - Start with shared/public frontend pieces first.
  - Limit the first milestone to PHP-source UI strings.
- Constraints/non-goals:
  - No functional changes.
  - No database translation layer yet.
  - No attempt to localize DB-driven content in the first phase.
- Known modules/paths/subprojects:
  - `web/hlstats.php`
  - `web/includes/functions.php`
  - `web/includes/class_table.php`
  - `web/pages/header.php`
  - `web/pages/footer.php`
  - `web/pages/search-class.php`
  - Then individual public pages in `web/pages/*.php`
- Decisions made in Q&A:
  - Work incrementally.
  - English stays default for now.
  - Translate only PHP-code UI strings for now.
  - A visible language switcher is acceptable.
  - First milestone is the i18n skeleton with only an `en` dictionary.
- Remaining open questions (if any):
  - None required before milestone 1.

## Implementation plan
1. Add i18n bootstrap in `web/hlstats.php`.
   - Resolve current language from request/session/cookie with `en` as default.
   - Load the matching dictionary file.
   - Make the current language and translations globally available to page rendering.
   - Review request-based cache logic so language-aware output cannot collide across languages.

2. Add shared i18n helpers in `web/includes/functions.php`.
   - Introduce helpers such as:
     - `current_lang()`
     - `available_langs()`
     - `t($key, $params = array(), $fallback = null)`
   - Keep fallback behavior strict: missing keys resolve to English or explicit fallback.
   - Keep helper API simple so legacy templates can adopt it with minimal churn.

3. Create the dictionary structure.
   - Add a new directory such as `web/lang/`.
   - Add `web/lang/en.php` as the first and only dictionary in milestone 1.
   - Group keys by shell/component/page domains, for example:
     - `nav.*`
     - `footer.*`
     - `table.*`
     - `search.*`
     - `players.*`
   - Document naming conventions in comments at the top of the dictionary file.

4. Add a language switcher in shared shell rendering.
   - Place it in `web/pages/header.php`.
   - Preserve current query parameters when switching language.
   - Keep the switcher minimal and functional.
   - For milestone 1 it can display only `EN`, or `EN` plus disabled/future-ready `RU` depending on implementation choice.

5. Convert shared shell text first.
   - Replace hardcoded UI strings in `web/pages/header.php` with translation keys.
   - Replace hardcoded UI strings in `web/pages/footer.php` with translation keys.
   - Ensure breadcrumb labels and menu labels use translated values.

6. Convert shared component text next.
   - Replace hardcoded labels in `web/includes/class_table.php`:
     - rank header
     - pagination labels
     - generic alt/title text such as `No Country`
   - Replace hardcoded text in `web/pages/search-class.php`.
   - Replace generic helper output in `web/includes/functions.php` where it is visible to users.

7. Convert the first public pages after the shared shell is stable.
   - Suggested first batch:
     - `web/pages/contents.php`
     - `web/pages/game.php`
     - `web/pages/players.php`
     - `web/pages/clans.php`
     - `web/pages/servers.php`
   - Move only PHP-source UI labels to keys.
   - Keep page-by-page review small to reduce regressions.

8. Leave later milestones explicitly separate.
   - Milestone 2: add `web/lang/ru.php`.
   - Milestone 3: translate remaining public pages.
   - Milestone 4: optionally translate admin and ingame areas.
   - Milestone 5: decide whether DB-driven content and date/time formatting should be localized.

## Suggested milestone breakdown
### M1. Skeleton only
- Add language bootstrap.
- Add helpers.
- Add `web/lang/en.php`.
- Add language switcher.
- Convert shared shell/common components enough to prove the architecture works.
- No Russian strings yet.

Definition of done:
- Site renders exactly as before in English.
- All converted strings come from the `en` dictionary.
- Language choice flows through one common bootstrap path.
- The switcher exists and does not break navigation.

### M2. Public frontend coverage
- Continue page-by-page extraction of public PHP UI strings into translation keys.

Definition of done:
- Main public pages are consistently backed by dictionary keys instead of inline strings.

### M3. Russian dictionary
- Add `web/lang/ru.php`.
- Translate already-extracted keys.
- Verify fallback behavior for any missing keys.

Definition of done:
- Switching to Russian changes translated UI strings only.
- Behavior and routing remain identical.

### M4. Complete the visible frontend translation pass
- Audit and translate every user-facing frontend surface that still renders English after the initial i18n skeleton.
- Keep product names, protocol terms, commands, and code identifiers untranslated when they are intentional technical terms.
- Polish the existing Russian dictionary so the RU locale reads naturally instead of looking machine-translated or copied from English.

Definition of done:
- The visible PHP frontend and frontend JS no longer expose untranslated English in the audited UI surfaces, except for intentional technical terms.
- `web/lang/ru.php` reads naturally and preserves placeholders, counts, and short labels.
- Admin, public, ingame, status, and interactive JS surfaces are covered by the same translation rules.

Backlog captured from the latest audit:
- Dictionary quality pass:
  - `web/lang/ru.php` `literal.help_aliases`
  - `web/lang/ru.php` `literal.help_set_3`
  - `web/lang/ru.php` `literal.joined`
  - `web/lang/ru.php` `kill_streak_short`
  - `web/lang/ru.php` `awards.ribbon_class`
  - remaining RU wording that is technically correct but awkward in UI context
- Admin surfaces:
  - `web/pages/adminauth.php`
  - `web/pages/admin.php`
  - `web/pages/admintasks/options.php`
  - `web/pages/admintasks/newserver.php`
  - `web/pages/admintasks/adminusers.php`
  - `web/pages/admintasks/actions.php`
  - `web/pages/admintasks/clantags.php`
  - `web/pages/admintasks/games.php`
  - `web/pages/admintasks/hostgroups.php`
  - `web/pages/admintasks/roles.php`
  - `web/pages/admintasks/teams.php`
  - `web/pages/admintasks/servers.php`
  - `web/pages/admintasks/serversettings.php`
  - `web/pages/admintasks/ribbons.php`
  - `web/pages/admintasks/ribbons_trigger.php`
  - `web/pages/admintasks/tools_editdetails.php`
  - `web/pages/admintasks/tools_editdetails_clan.php`
  - `web/pages/admintasks/tools_editdetails_player.php`
  - `web/pages/admintasks/weapons.php`
  - `web/pages/admintasks/voicecomm.php`
  - `web/pages/admintasks/tools_perlcontrol.php`
  - `web/pages/admintasks/tools_reset.php`
  - `web/pages/admintasks/tools_reset_2.php`
  - `web/pages/admintasks/tools_resetdbcollations.php`
  - `web/pages/admintasks/tools_settings_copy.php`
  - `web/pages/admintasks/tools_synchronize.php`
  - `web/pages/admintasks/tools_optimize.php`
- Public surfaces:
  - `web/status.php`
  - `web/show_graph.php`
  - `web/pages/ingame/claninfo.php`
  - `web/pages/ingame/accuracy.php`
  - `web/pages/teamspeak_class.php`
  - `web/includes/js/search-suggestions.js`
  - `web/includes/js/tabs.js`
  - `web/includes/js/syntax.js`
  - any similar user-facing leftovers discovered in the same scan pattern

Validation:
- File-level scan for user-facing English text in the audited frontend surfaces.
- Browser smoke checks for the translated admin shell and representative public pages.
- PHP syntax validation for every changed PHP file.
- Manual review of short labels and placeholders after translation so UI layout does not regress.

## Tests to run
- Manual smoke:
  - open `hlstats.php` with default settings and verify English output remains unchanged
  - switch language through the new UI control and verify no broken links or lost query parameters
  - verify navigation, breadcrumbs, search forms, pagination, and footer still work
- Regression checks on representative pages:
  - `?mode=contents`
  - `?mode=players&game=<code>`
  - `?mode=search`
  - `?mode=help`
- Cache check:
  - verify cached output does not leak one language into another request path
- PHP validation:
  - run `php -l` on every changed PHP file
- Optional comparison check:
  - capture before/after HTML for a few pages in English and confirm only source-of-string plumbing changed, not behavior
