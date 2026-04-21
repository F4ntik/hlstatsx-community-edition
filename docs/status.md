# Status

## Snapshot
- Current phase: M5. Fix runtime edge cases and validate EN/RU behavior
- Plan file: `docs/plans.md`
- Status: yellow
- Last updated: 2026-04-21

## Done
- Evaluated the current branch against upstream scope and identified the main upstream blockers.
- Confirmed that the public RU i18n branch is conceptually separable from the larger local migration work.
- Confirmed the two highest-risk runtime issues in the current implementation:
  - whole-document post-processing corrupts RU HTML structure;
  - logout redirect preserves `logout=1` and loops.
- Created durable execution docs for a cleanup pass aimed at an upstream PR.
- Isolated the remaining SQL-scope drift in `web/pages/playerinfo_general.php`.
- Reverted the mixed `GROUP BY` changes there back to upstream SQL behavior while preserving the i18n text replacements.
- Re-checked the retained public `web/` diff against `upstream/master`; the remaining scope is translation runtime, dictionaries, and public UI copy changes.
- Removed whole-document translation from the public request path by deleting `ob_start('translate_output_html')` in `web/hlstats.php`.
- Removed DOM/regex output rewriting helpers from `web/includes/i18n.php`; the runtime is now explicit language resolution plus direct `t(...)` lookups.
- Reduced `translate_ui_literal(...)` in `web/includes/functions.php` to a narrow legacy bridge for shared UI literals still used by tables and headers.
- Replaced public pages that still depended on post-processing with explicit key-based rendering, including `help.php`, `clans.php`, `actions.php`, `maps.php`, `weapons.php`, `roles.php`, `rolesinfo.php`, selected `claninfo*` pages, `countryclansinfo.php`, and `voicecomm_serverlist.php`.
- Fixed the public logout redirect so it drops `logout=1` and transient smoke params.
- Re-synced the local Docker validation container with the current worktree before runtime checks because it was not mounted to this workspace copy.
- Re-ran Docker `php -l` on the touched public web PHP files and completed EN/RU smoke checks for contents, search, players, clans, playerinfo, and servers.
- Removed the shared helper path from page titles, breadcrumbs, and section headings by switching `header.php` and `printSectionTitle(...)` consumers to pass already localized text.
- Converted the remaining high-visibility public table headers and page titles to explicit `t(...)`, including `search-class.php`, `chat.php`, `chathistory.php`, `playerhistory.php`, `playersessions.php`, `playerawards.php`, `actioninfo.php`, `mapinfo.php`, `weaponinfo.php`, `dailyawardinfo.php`, `rankinfo.php`, `ribboninfo.php`, `bans.php`, `players.php`, `maps.php`, `weapons.php`, and `help.php`.
- Added normalized dictionary keys for shared labels such as `date`, `message`, `description`, `ban_date`, session/history headings, map kill labels, and Steam profile statuses in `web/lang/en.php` and `web/lang/ru.php`.
- Re-ran Docker `php -l` after syncing the updated `web/` files into the validation container and completed EN/RU smoke checks for search, players, maps, weapons, actions, help, chat, playerinfo, playerhistory, playersessions, chathistory, playerawards, actioninfo, mapinfo, and weaponinfo on `game=cstrike`.
- Completed the targeted review-remediation pass for `web/pages/admintasks/tools_reset.php`, `web/pages/ingame/help.php`, `web/status.php`, and `web/pages/ingame/accuracy.php`.
- Added the remediation keys to `web/lang/en.php` and `web/lang/ru.php`, and corrected the reviewed RU wording issues.
- Verified Docker `php -l` for the touched remediation files and the updated dictionaries.
- Verified HTTP `200` responses for RU `mode=help` and the standalone RU `status.php` widget.
- Fixed `init_i18n()` so an invalid `?lang=...` value no longer overwrites a previously persisted valid language choice from cookie/session.
- Cleaned `lang_url(...)` so removing transient params no longer leaves a dangling `?`.
- Localized the shared admin `EditList` chrome and validation strings in `web/pages/admin.php`, including delete/configure/new labels, password placeholder handling, and row/new-row validation errors.
- Replaced the remaining hardcoded auth/editdetails/newserver literals in `web/pages/adminauth.php`, `web/pages/admintasks/newserver.php`, `web/pages/admintasks/tools_editdetails_player.php`, and `web/pages/admintasks/tools_editdetails_clan.php`, and moved the editdetails form labels to direct keys where those keys already existed.
- Verified Docker `php -l` for the newly touched runtime/admin files after syncing the changed `web/` files into the validation container.
- Verified live HTTP behavior for RU admin auth, invalid-language persistence fallback, and logout redirect cleanup.

## In Progress
- Final validation and handoff after the runtime/admin follow-up pass.

## Next
- Decide whether to continue deeper into the remaining admin/ingame translation backlog or switch to upstream PR preparation (`M6`) from the now-cleaner runtime/admin baseline.

## Decisions Made
- The upstream PR will target public `web/` RU i18n only.
- The hybrid translation approach must be removed rather than refined.
- SQL fixes will not ship inside the translation PR.
- The cleanup should preserve `GET lang -> cookie -> session -> en` unless a concrete defect forces a narrower behavior change.
- The follow-up remediation pass may touch the cited admin and ingame pages because the user explicitly requested fixes for the concrete review findings.
- The broader continuation pass may also touch adjacent admin/auth/editdetails pages because the user explicitly requested that the RU i18n work continue and approved per-file agent assistance.

## Assumptions In Force
- `upstream/master` remains the correct merge target.
- The local Docker container `hlstatsx-web-ru-web` is the validation environment for PHP syntax and smoke checks.
- Existing handoff docs in `docs/web_frontend_i18n_plan.md` and `docs/web_frontend_i18n_handoff.md` remain useful background but are no longer the primary source of truth.
- This pass is still not a full admin/ingame translation sweep; only the reviewed files are in scope.

## Commands
```sh
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff --name-only
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff -- web
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n diff upstream/master -- web/pages/playerinfo_general.php
git -C D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n grep -n "translate_ui_literal(" -- web
docker exec hlstatsx-web-ru-web php -l /var/www/html/hlstats.php
curl.exe -s -D - -o NUL "http://localhost:8381/hlstats.php?lang=ru&mode=contents&logout=1"
```

## Current Blockers
- None for planning.
- Execution blocker to watch: host shell has no `php` binary in `PATH`, so syntax validation must use Docker.

## Audit Log
| Date | Milestone | Files | Commands | Result | Next |
| --- | --- | --- | --- | --- | --- |
| 2026-04-20 | Planning | `web/hlstats.php`, `web/includes/i18n.php`, `web/includes/functions.php`, selected public pages | `git diff`, `docker exec ... php -l`, `Invoke-WebRequest`, `curl.exe -D -` | found hybrid HTML corruption and logout loop; planning pack created | start M1 scope isolation |
| 2026-04-20 | M1 | `web/pages/playerinfo_general.php`, `docs/plans.md`, `docs/status.md` | `git diff upstream/master -- web/pages/playerinfo_general.php`, `git diff upstream/master -- web` | removed the mixed SQL `GROUP BY` drift from the i18n worktree; retained diff is translation-only in scope | start M2 hybrid-runtime cleanup |
| 2026-04-20 | M2/M4 | `web/hlstats.php`, `web/includes/i18n.php`, `web/includes/functions.php`, `web/lang/en.php`, `web/lang/ru.php`, selected public pages, `docs/plans.md`, `docs/status.md` | `docker exec hlstatsx-web-ru-web php -l ...`, `fetch(...)` smoke via `js_repl`, targeted `docker exec` sync commands | removed whole-document translation, narrowed shared literal helper, converted remaining public call sites to explicit keys, and fixed logout redirect | continue M3 coverage review |
| 2026-04-20 | M3 | `web/pages/header.php`, `web/includes/functions.php`, `web/lang/en.php`, `web/lang/ru.php`, remaining public search/chat/history/detail/list pages, `docs/plans.md`, `docs/status.md` | `git grep`, `docker cp`, `docker exec php -l`, `fetch(...)` smoke via `js_repl` | removed helper usage from title/breadcrumb/section rendering, normalized high-visibility shared labels to explicit keys, and validated EN/RU on live `game=cstrike` routes | decide whether to remove the residual shared table fallback before M4 |
| 2026-04-21 | M4 | `web/pages/admintasks/tools_reset.php`, `web/pages/ingame/help.php`, `web/status.php`, `web/pages/ingame/accuracy.php`, `web/lang/en.php`, `web/lang/ru.php`, `docs/plans.md`, `docs/status.md`, `docs/test-plan.md` | review findings audit, targeted file reads, parallel worker pass, `docker exec ... php -l`, focused HTTP smoke checks | remediation pass completed for the five concrete findings; page copy now routes through dictionary lookups and reviewed RU wording was corrected | decide whether to continue with broader upstream handoff work |
| 2026-04-21 | M5 follow-up | `web/includes/i18n.php`, `web/pages/admin.php`, `web/pages/adminauth.php`, `web/pages/admintasks/newserver.php`, `web/pages/admintasks/tools_editdetails_player.php`, `web/pages/admintasks/tools_editdetails_clan.php`, `web/lang/en.php`, `web/lang/ru.php`, `docs/plans.md`, `docs/status.md` | parallel explorer audit, `docker exec ... php -l`, targeted `docker cp`, `Invoke-WebRequest`, `curl.exe -D -` | fixed invalid-language persistence fallback, cleaned `lang_url(...)`, localized shared admin edit-list strings, and validated RU admin auth plus logout/runtime persistence on live HTTP routes | decide between further admin backlog cleanup and M6 PR prep |

## Smoke / Demo Checklist
- [x] Clean translation-only diff prepared
- [x] Hybrid output translation removed
- [x] EN contents page renders correctly
- [x] RU contents page renders correctly
- [x] EN search page renders correctly
- [x] RU search page renders correctly
- [x] EN players page renders correctly
- [x] RU players page renders correctly
- [x] RU maps page renders correctly
- [x] RU weapons page renders correctly
- [x] RU chat page renders correctly
- [x] RU help page renders correctly
- [x] RU playerinfo / playerhistory / playersessions / chathistory / playerawards pages render correctly
- [x] RU actioninfo / mapinfo / weaponinfo pages render correctly
- [x] Logout no longer loops
- [x] Targeted review findings are fixed in code
- [ ] PR description and commit stack are ready for upstream review
