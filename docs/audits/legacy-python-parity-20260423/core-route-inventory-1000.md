# Core Route Inventory (1000-log parity)

`legacy_base = http://127.0.0.1:8181/hlstats.php`  
`python_base = http://127.0.0.1:8281/hlstats.php`

## Overview and lists
- `mode=contents`
- `mode=players&game=cstrike`
- `mode=clans&game=cstrike`
- `mode=maps&game=cstrike`
- `mode=weapons&game=cstrike`
- `mode=actions&game=cstrike`
- `mode=awards&game=cstrike`
- `mode=servers&game=cstrike`

## Detail pages (stable IDs chosen from imported data)
- `mode=playerinfo&player=1&game=cstrike`
- `mode=mapinfo&map=de_dust2&game=cstrike`
- `mode=weaponinfo&weapon=ak47&game=cstrike`
- `mode=actioninfo&action=planted_bomb&game=cstrike`
- `mode=claninfo&clan=1&game=cstrike`

## Utility pages
- `mode=help`
- `mode=search`
- `status.php`

## Page-visible checks required for each route
- visible totals/counters
- first page row-set (top rows) and column values
- sort order (default)
- filter outcome (game/entity)
- pagination behavior (if present)
- empty/non-empty state text

## Evidence format (light)
- `legacy_url`
- `python_url`
- `severity` (`P0|P1|P2|P3`)
- `difference` (short text)
