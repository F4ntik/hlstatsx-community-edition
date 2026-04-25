# Public Web RU Translation Branch

## Goal
- Add a reusable bilingual i18n layer for the public PHP frontend.
- Keep English as the default language.
- Add Russian translations for the public `web/` interface.
- Keep the PR focused on web UI only, without touching Python, Perl, SQL, admin pages, or ingame pages.

## Implemented scope
- `lang=<code>` query parameter with persistence order:
  - `GET`
  - cookie
  - session
  - fallback `en`
- Shared dictionaries under `web/lang/`:
  - `en.php`
  - `ru.php`
- Shared runtime helpers in `web/includes/i18n.php`:
  - `current_lang()`
  - `available_langs()`
  - `t($key, $params = array(), $fallback = null)`
  - `lang_url($code)`
- Language-aware historical cache key in `web/hlstats.php`
- Visible language dropdown in the public header
- Shared UI translation for:
  - header
  - footer
  - search UI
  - table rank/pagination/common labels
  - common warnings/errors
  - compact duration rendering
- Public-page translation coverage via:
  - direct `t(...)` calls in shared/public files
  - dictionary-backed post-render translation for legacy page output
- Voice pages keep their current template mechanism, but receive translated labels from PHP where practical.

## Out of scope
- `web/pages/admin*`
- `web/pages/ingame/*`
- updater implementation changes outside public copy updates
- Python migration files
- Perl daemon files
- SQL schema/data changes
- DB-driven content translation
- Graphic title navigation asset localization (`title-*.png`)

## Notes
- Header navigation images remain visually English in this PR by design.
- The branch is intended to be created from `upstream/master` in a separate worktree so it can be proposed upstream without mixing in local migration work.
- If a translation key is missing in `ru`, runtime falls back to the `en` dictionary.
- For continuation context and live-stand handoff, see `docs/web_frontend_i18n_handoff.md`.
