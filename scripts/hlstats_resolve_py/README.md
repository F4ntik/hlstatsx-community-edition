# hlstats-resolve (Python)

Python port of the legacy `hlstats-resolve.pl` maintenance job.  The script reads
`hlstats.conf`, connects to the MySQL database shared with the game statistics
pipeline and resolves player IP addresses into hostnames and host groups.

The module exposes a CLI entry point that mirrors the Perl options and can be
invoked either manually or from cron/systemd timers:

```sh
python -m hlstats_resolve_py.cli --configfile /path/to/hlstats.conf --regroup
```

The CLI integrates with the shared configuration loader so the same
`hlstats.conf` file can be reused across the Python ports.
