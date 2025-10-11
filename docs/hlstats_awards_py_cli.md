# Python CLI for `hlstats-awards`

The Python port of the awards and maintenance script reuses the existing
`hlstats.conf` parser from the proxy daemon to stay configuration-compatible
with the legacy Perl tooling.  The CLI mirrors the original options, including
short aliases:

- `-i`/`--inactive`
- `-a`/`--awards`
- `-r`/`--ribbons`
- `-g`/`--geoip`
- `-t`/`--clans`
- `-p`/`--prune`
- `-o`/`--optimize`

When no actions are specified the script defaults to running inactive player
maintenance, awards, ribbons and pruning, matching the Perl behaviour.

Database parameters are read from `hlstats.conf` in the current working
directory.  Command line flags override these defaults, and an explicit
`--configfile` applies another configuration file after CLI overrides—mirroring
the "cannot be overridden" semantics advertised in the Perl help output.

The parser validates `--numdays` and `--date` formats and exposes the structured
values to the rest of the application.  The calculator described in
`docs/hlstats_awards_py_calculator.md` consumes these settings to drive the
database-backed maintenance routines.
