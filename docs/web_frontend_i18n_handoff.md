# Public Web RU i18n Handoff

## Branch and scope
- Repository: `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n`
- Branch: `feature/web-public-ru-i18n`
- Goal: continue RU coverage only for public `web/`
- Default language remains `en`
- RU is added through the shared i18n layer

## Strict scope
- In scope:
  - public `web/` pages
  - PHP-owned UI text
  - shared public i18n helpers and dictionaries
- Out of scope:
  - `web/pages/admin*`
  - `web/pages/ingame/*`
  - updater logic outside public copy
  - Python, Perl, SQL, DB-content translation
  - broader SQL cleanup

## Runtime assumptions
- Local stand is available at `http://localhost:8381/hlstats.php`
- Test data is loaded
- In local test MySQL, `ONLY_FULL_GROUP_BY` is disabled for smoke tests
- One strict-mode-oriented partial fix already exists in `web/pages/playerinfo_general.php`, but SQL cleanup is not the current PR goal

## i18n rules that must stay true
- Language resolution order:
  - `GET lang`
  - cookie
  - session
  - fallback `en`
- Missing RU keys must fall back to `en`
- Do not run global `strtr` over all rendered HTML
- Prefer:
  - direct `t(...)` calls
  - shared exact-literal mapping for common UI labels
  - narrow legacy post-render translation only where already established
- Keep the visible language dropdown in the header

## Core implementation already present
- Shared runtime: `web/includes/i18n.php`
- Dictionaries:
  - `web/lang/en.php`
  - `web/lang/ru.php`
- Shared exact-literal mapper in `web/includes/functions.php`:
  - `translate_ui_literal($text)`
- Shared table/header translation wiring in:
  - `web/includes/class_table.php`
  - `web/includes/functions.php`

## Files already changed in this branch/worktree
- Shared i18n/base:
  - `web/hlstats.php`
  - `web/includes/i18n.php`
  - `web/includes/functions.php`
  - `web/includes/class_table.php`
  - `web/lang/en.php`
  - `web/lang/ru.php`
- Shared public layout/navigation:
  - `web/pages/header.php`
  - `web/pages/footer.php`
  - `web/pages/search-class.php`
  - `web/pages/players.php`
  - `web/pages/teamspeak.php`
  - `web/pages/ventrilo.php`
- Public pages already worked on for RU coverage:
  - `web/pages/contents.php`
  - `web/pages/game.php`
  - `web/pages/livestats.php`
  - `web/pages/servers.php`
  - `web/pages/awards.php`
  - `web/pages/awards_daily.php`
  - `web/pages/awards_global.php`
  - `web/pages/awards_ranks.php`
  - `web/pages/awards_ribbons.php`
  - `web/pages/playerinfo.php`
  - `web/pages/playerinfo_general.php`
  - `web/pages/playerinfo_weapons.php`
  - `web/pages/claninfo.php`
  - `web/pages/claninfo_general.php`
  - `web/pages/claninfo_weapons.php`
  - `web/pages/maps.php`
  - `web/pages/weapons.php`
  - `web/pages/actions.php`
  - `web/pages/roles.php`

## What is already covered
- Shared navigation and language dropdown
- Main contents page and game-home public sections
- Server page live view and load history
- Awards tabs and awards detail blocks
- Player detail page:
  - profile block
  - statistics summary
  - forum signature
  - rank block
  - awards block
  - footer notes and "go to" links
- Clan detail page:
  - summary block
  - player locations heading
  - footer notes and "go to" links
- Weapon target pages for player/clan:
  - "Targets"
  - flash-required text
  - "Show total target statistics"
- Summary strings on:
  - `maps`
  - `weapons`
  - `actions`
  - `roles`
- Live-stats short labels:
  - headshots short label
  - HS:K
  - latency short label
  - skill label

## Container/runtime note that matters
- The running container is `hlstatsx-web-ru-web`
- Not every public page is bind-mounted from the worktree
- Current bind-mounted paths:
  - `web/includes/i18n.php`
  - `web/includes/functions.php`
  - `web/includes/class_table.php`
  - `web/lang/`
  - `web/hlstats.php`
  - `web/pages/header.php`
  - `web/pages/footer.php`
  - `web/pages/search-class.php`
  - `web/pages/players.php`
  - `web/pages/teamspeak.php`
  - `web/pages/ventrilo.php`
- Consequence:
  - after editing non-mounted pages, smoke tests will not see changes until the file is copied into the container
- Use:
  - `docker cp <local-file> hlstatsx-web-ru-web:/var/www/html/pages/<file>`
  - then `docker exec hlstatsx-web-ru-web php -l /var/www/html/pages/<file>`

## Smoke checks already confirmed
- RU:
  - `?lang=ru&mode=contents`
  - `?lang=ru&game=cstrike&mode=servers&server_id=1`
  - `?lang=ru&game=cstrike&mode=playerinfo&player=32`
  - `?lang=ru&game=cstrike&mode=playerinfo&player=32&type=ajax&tab=weapons`
  - `?lang=ru&game=cstrike&mode=maps`
  - `?lang=ru&game=cstrike&mode=weapons`
  - `?lang=ru&game=cstrike&mode=actions`
  - `?lang=ru&game=cstrike&mode=roles`
  - `?lang=ru&mode=help`
- EN:
  - `?lang=en&mode=contents`
  - `?lang=en&game=cstrike&mode=servers&server_id=1`
  - `?lang=en&game=cstrike&mode=playerinfo&player=32`
  - `?lang=en&game=cstrike&mode=playerinfo&player=32&type=ajax&tab=weapons`
- Language persistence:
  - verified `GET lang=ru` -> cookie/session persistence on subsequent request without `lang`
  - verified fresh session without `lang` falls back to `en`

## Known blocker in current fixture set
- `claninfo` live detail smoke is not fully validated right now because current local fixture data shows `0` clans on `mode=clans`
- This is a data limitation, not an identified PHP rendering failure

## Highest-priority remaining work
- `web/pages/clans.php`
  - search form text
  - filter/apply text
  - footer "Go to"
  - columns such as `Tag` and `Avg. Points`
- `web/pages/players.php`
  - lower filter/apply/go-to leftovers
- `web/pages/countryclans.php`
  - lower filter/apply/go-to leftovers
  - any remaining English summary labels
- `web/pages/search.php`
  - page header/breadcrumb/form/result framing
- Then do another sweep over:
  - `claninfo_*`
  - `playerinfo_*`
  - remaining list/filter/empty-state copy in public pages

## Things that already surfaced as remaining English tails
- `clans.php`
  - `Find a clan`
  - `Search`
  - `Show only clans with`
  - `Apply`
  - `Go to`
  - `Tag`
  - `Avg. Points`
- `players.php`
  - lower `Apply`
  - lower `Go to`
- `countryclans.php`
  - `Avg. Points`
  - lower `Show only clans with`
  - `Apply`
  - lower `Go to`
- `search.php`
  - page-level `Search` framing still worth explicit review

## Working style constraints for continuation
- Do not revert unrelated changes in the dirty worktree
- Do not touch admin or ingame pages
- Do not expand scope into SQL cleanup
- Prefer exact key-based translation over broad output rewriting
- For every non-mounted edited page:
  - `docker cp`
  - `php -l` in container
  - smoke the live URL in both `ru` and `en` if the page is user-visible

## Recommended next execution order
1. Finish `clans.php`
2. Finish `players.php`
3. Finish `countryclans.php`
4. Review and finish `search.php`
5. If fixture data allows, re-run `claninfo` live smoke
6. Final public-page sweep for list/filter/footer/empty-state leftovers

## Minimal smoke checklist after the next batch
- `http://localhost:8381/hlstats.php?lang=ru&mode=contents`
- `http://localhost:8381/hlstats.php?lang=ru&game=cstrike&mode=clans`
- `http://localhost:8381/hlstats.php?lang=ru&game=cstrike&mode=players`
- `http://localhost:8381/hlstats.php?lang=ru&game=cstrike&mode=countryclans`
- `http://localhost:8381/hlstats.php?lang=ru&mode=search`
- same URLs with `lang=en`

## Suggested opener for a fresh chat
- Continue branch `feature/web-public-ru-i18n` in `D:\PyProjects\hlstatx-ce\hlstatsx-community-edition-web-ru-i18n`
- Read:
  - `docs/web_frontend_i18n_plan.md`
  - `docs/web_frontend_i18n_handoff.md`
- Then continue RU coverage for the remaining public pages, starting with:
  - `web/pages/clans.php`
  - `web/pages/players.php`
  - `web/pages/countryclans.php`
  - `web/pages/search.php`
- Keep:
  - public `web/` only
  - `en` default
  - `ru` via shared i18n
  - fallback `ru -> en`
  - `GET lang -> cookie -> session -> en`
- After edits:
  - copy non-mounted pages into `hlstatsx-web-ru-web`
  - run `php -l` in the container
  - smoke-check live URLs in `ru` and `en`
