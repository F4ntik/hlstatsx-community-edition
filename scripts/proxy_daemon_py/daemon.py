"""Core asyncio daemon implementation placeholder.

This module will eventually host the main event loop and orchestration logic of
the Python proxy daemon.  At the preparation stage we only define the public
APIs that other modules will eventually depend on.
"""

from __future__ import annotations

import asyncio

from .balancer import ServerBalancer
from .config import ProxyConfig
from .db import DatabaseAdapter
from .heartbeat import HeartbeatManager


class ProxyDaemon:
    """Container object coordinating the main daemon subsystems."""

    def __init__(
        self,
        config: ProxyConfig,
        db: DatabaseAdapter,
        balancer: ServerBalancer,
        heartbeat: HeartbeatManager,
    ) -> None:
        self._config = config
        self._db = db
        self._balancer = balancer
        self._heartbeat = heartbeat
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start the daemon.

        The concrete implementation will be added in later tasks once the
        networking and scheduling logic is ready.
        """

        raise NotImplementedError("Daemon startup not implemented yet")

    async def stop(self) -> None:
        """Stop the daemon and release its resources."""

        raise NotImplementedError("Daemon shutdown not implemented yet")
