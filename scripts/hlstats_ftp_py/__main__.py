"""``python -m hlstats_ftp_py`` entry point."""

from __future__ import annotations

import sys

from hlstats_ftp_py.main import run

if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
