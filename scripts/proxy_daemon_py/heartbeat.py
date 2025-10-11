"""Heartbeat scheduling primitives for the Python proxy daemon."""

from __future__ import annotations

from typing import Protocol


class HeartbeatTarget(Protocol):
    """Protocol describing the objects that can receive heartbeat messages."""

    async def send_heartbeat(self) -> None: ...


class HeartbeatManager:
    """Placeholder for the heartbeat subsystem implementation."""

    def __init__(self, interval_seconds: int) -> None:
        self._interval = interval_seconds

    async def start(self) -> None:
        """Start scheduling heartbeat checks."""

        raise NotImplementedError("Heartbeat scheduling not implemented yet")

    async def stop(self) -> None:
        """Stop heartbeat scheduling tasks."""

        raise NotImplementedError("Heartbeat shutdown not implemented yet")
