# First Divergence Report (single log)

- Log: `L0101000.log`
- Input parity: `PASS` (`legacy-input-manifest-1.txt` == `python-input-manifest-1.txt`, dropped-lines SHA match)
- Preflight parity: `PASS` (`players=0`, `frags=0` in both DBs before replay)

## First mismatch

The first visible mismatch occurs at the first two player join events:

- `"49.5 ％ coloN<664><BOT><>" joined team "CT"`
- `"49.5 ％ kuben<665><BOT><>" joined team "TERRORIST"`

Legacy outcome:

- `hlstats_Players`: 2 rows (`coloN`, `kuben`)
- `hlstats_PlayerUniqueIds`: 2 unique IDs
  - `BOT:9850941f122e251e44eec5d3ce467d7d`
  - `BOT:211f49395e00a4127f9f0f28b47bf9fd`

Python outcome (before this fix):

- `hlstats_Players`: 1 row
- `hlstats_PlayerUniqueIds`: 1 unique ID (`BOT`)

## Root-cause category

- `parser normalization drift` (primary)
- downstream `storage identity merge` (secondary effect)

## Root-cause details

Python parser keeps bot `unique_id` as literal `BOT`, so multiple bots share the same identity key and collapse into one player record. Legacy derives bot-specific IDs (`BOT:<hash>`), so each bot stays distinct.

Code path:

- `scripts/hlstats_py/protocol.py`:
  - `_consume_player()` assigns `unique_id` from token directly.
  - `_normalize_unique_id()` does not specialize `BOT`.

This causes identity collision before downstream event processing, which then distorts players/frags/actions and UI ranking data.
