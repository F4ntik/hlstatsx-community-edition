# HLstats Awards Python Port

This package contains the Python implementation of the legacy
`hlstats-awards.pl` maintenance script.  The current milestone ships the
command-line interface alongside a synchronous awards calculator that reuses
the shared MySQL adapter from the proxy daemon port.  The calculator currently
covers the default maintenance actions executed by the Perl script:

- activity recalculation for inactive players,
- daily and historical award winner selection,
- ribbon recomputation, and
- database pruning/optimisation helpers.

Unit tests exercise the CLI precedence rules and the SQL that is issued for
each maintenance workflow so follow-up tasks can iterate safely.  The
integration scenario in `tests/test_integration.py` drives the calculator
through the default action set while collecting an `AwardsReport` summary for
documentation purposes—sample output and guidance live in
`docs/hlstats_awards_py_reports.md`.
