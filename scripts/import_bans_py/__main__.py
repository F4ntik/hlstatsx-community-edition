"""``python -m import_bans_py`` entrypoint."""

from __future__ import annotations

import sys

from import_bans_py.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
