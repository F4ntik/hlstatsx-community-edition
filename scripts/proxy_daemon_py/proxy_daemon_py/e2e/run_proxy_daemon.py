"""Backwards-compatible e2e entrypoint for the proxy daemon runtime."""

from __future__ import annotations

from collections.abc import Sequence

from ..runtime import main


def e2e_main(argv: Sequence[str] | None = None) -> int:
    return main(argv)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(e2e_main())
