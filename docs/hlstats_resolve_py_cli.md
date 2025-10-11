# Python CLI for hlstats-resolve

This document outlines how to run the Python port of `hlstats-resolve.pl` and
how it integrates with existing automation.

## Command line interface

The entry point mirrors the historical Perl options while adding the common
`--configfile` override shared across the Python utilities.

```
usage: hlstats-resolve [-h] [--configfile CONFIGFILE] [--debug] [--nodebug]
                       [--db-host DB_HOST] [--db-name DB_NAME]
                       [--db-username DB_USERNAME] [--db-password DB_PASSWORD]
                       [--dns-timeout DNS_TIMEOUT] [--regroup] [--version]
```

Key flags:

- `--regroup` skips DNS lookups and only recalculates host groups for stored
  hostnames. This matches the Perl `-r/--regroup` behaviour used in scheduled
  maintenance jobs.
- `--debug`/`--nodebug` increment or decrement the debug verbosity. When the
  resulting level is greater than zero the resolver logs per-host decisions,
  replicating the verbose Perl output used for troubleshooting.
- Database and DNS parameters may be provided via CLI or loaded from
  `hlstats.conf`; CLI overrides always win.

## Cron/systemd integration

The resolver is safe to invoke from cron or systemd timers. A typical cron entry
looks like this:

```
0 4 * * * /usr/bin/python3 -m hlstats_resolve_py.cli --configfile /etc/hlstats.conf
```

The script prints progress summaries compatible with existing monitoring. When
running in regroup-only mode the exit status remains zero even if some IPs fail
DNS resolution, matching the Perl semantics.

## Database usage

The resolver reuses the shared `SyncDatabaseAdapter` from the proxy-daemon
migration. DNS results and host groups are written back into the
`hlstats_Events_Connects` table using the same update logic as the legacy Perl
implementation. Host group patterns continue to be read from
`hlstats_HostGroups` with shell-style wildcard support.
