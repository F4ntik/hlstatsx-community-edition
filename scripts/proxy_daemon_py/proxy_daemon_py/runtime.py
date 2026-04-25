"""Runnable entry point for the Python proxy daemon."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Sequence

from . import cli
from .bootstrap import build_components


async def _serve(argv: Sequence[str] | None = None) -> int:
    try:
        settings = cli.load_settings(argv)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"error: {exc}")
        return 1

    components = build_components(settings.config, log_level=settings.log_level)
    logger = components.logger
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        await components.daemon.start()
    except Exception as exc:  # pragma: no cover - defensive startup logging
        logger.e403(f"Failed to start proxy daemon: {exc}")
        return 2

    logger.notice("Proxy daemon initialised; waiting for shutdown signal")

    try:
        await stop_event.wait()
    finally:
        await components.daemon.stop()

    logger.notice("Proxy daemon shutdown complete")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m proxy_daemon_py.runtime``."""

    return asyncio.run(_serve(argv))


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
