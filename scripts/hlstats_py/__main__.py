"""Module entry point for ``python -m hlstats_py``."""

from .runtime import main


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
