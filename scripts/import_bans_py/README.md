# import_bans_py

Python standalone maintenance replacement for the historical
`ImportBans/importbans.pl` utility.

It mirrors the legacy behavior:

- fetches permanent bans from one or multiple external ban DBs
- normalizes Steam IDs to HLstats `uniqueId` format (`STEAM_X:Y:Z` -> `Y:Z`)
- marks matching players as banned in HLstats (`hlstats_Players.hideranking = 2`)
- does not unban players (same as legacy Perl `importbans.pl`)

## Supported sources

- SourceBans (`<prefix>bans`, default prefix `sb_`)
- AMXBans (`<prefix>bans`, default prefix `amx_`)
- BeetlesMod (`<prefix>bans`, default prefix `bm_`)
- ES GlobalBan (`<prefix>ban`, default prefix `gban_`)

## Usage

```powershell
python -m import_bans_py `
  --configfile scripts/hlstats.conf `
  --sourcebans-db-host 127.0.0.1 `
  --sourcebans-db-port 3306 `
  --sourcebans-db-name sourcebans `
  --sourcebans-db-user root `
  --sourcebans-db-password secret
```

Run multiple sources in one pass by adding more `--<source>-...` blocks.

Dry-run mode (no HLstats updates):

```powershell
python -m import_bans_py `
  --configfile scripts/hlstats.conf `
  --sourcebans-db-name sourcebans `
  --sourcebans-db-user root `
  --sourcebans-db-password secret `
  --dry-run
```

## Notes

- At least one source must be fully configured.
- Source credentials are intentionally explicit CLI flags for maintenance jobs.
- For cron/systemd, prefer secret injection instead of plaintext command history.
