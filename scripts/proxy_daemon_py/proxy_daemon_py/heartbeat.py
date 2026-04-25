"""Heartbeat scheduling primitives for the Python proxy daemon."""

from __future__ import annotations

import asyncio
from asyncio import Task
from datetime import datetime, timezone
from typing import Protocol

from .balancer import DaemonManager, DaemonState
from .db import DatabaseAdapter, ProxyDaemonState
from .log import ProxyLogger


class HeartbeatTarget(Protocol):
    """Protocol describing the objects that can receive heartbeat messages."""

    async def send_heartbeat(self) -> None: ...


class _HeartbeatClientProtocol(asyncio.DatagramProtocol):
    """Protocol that sends a heartbeat payload and records the first response."""

    def __init__(
        self,
        payload: bytes,
        response_future: asyncio.Future[bytes],
    ) -> None:
        self._payload = payload
        self._future = response_future
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # pragma: no cover - exercised indirectly
        self._transport = transport
        transport.sendto(self._payload)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._future.done():
            self._future.set_result(data)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - defensive
        if not self._future.done():
            self._future.set_exception(exc)

    def connection_lost(self, exc: Exception | None) -> None:  # pragma: no cover - defensive
        if exc is not None and not self._future.done():
            self._future.set_exception(exc)


def _state_to_db_value(state: DaemonState) -> str:
    if state is DaemonState.UP:
        return "up"
    if state is DaemonState.DOWN:
        return "down"
    return "n/a"


class DaemonHeartbeatTarget:
    """Heartbeat target that probes a registered downstream daemon."""

    def __init__(
        self,
        identifier: str,
        manager: DaemonManager,
        database: DatabaseAdapter,
        logger: ProxyLogger,
        *,
        timeout: float = 1.5,
        payload: str = "C;HEARTBEAT;",
        expected_response: str = "Heartbeat OK",
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self._identifier = identifier
        self._manager = manager
        self._database = database
        self._logger = logger
        self._timeout = float(timeout)
        self._payload = payload
        self._expected = expected_response
        self._proxy_key: str | None = None

    async def send_heartbeat(self) -> None:
        try:
            daemon = self._manager.get(self._identifier)
        except KeyError:
            self._logger.e403(f"Skipping heartbeat for unknown daemon {self._identifier}")
            return

        timestamp = datetime.now(tz=timezone.utc)
        loop = asyncio.get_running_loop()

        try:
            data, latency = await self._send_probe(
                (daemon.host, daemon.port),
                await self._build_payload(daemon.identifier),
                loop,
            )
        except Exception as exc:
            self._logger.e403(f"Heartbeat to {daemon.identifier} failed: {exc}")
            await self._handle_failure(daemon, timestamp)
            return

        response = data.decode("utf-8", errors="replace").strip()
        if self._expected not in response:
            self._logger.e403(
                f"Unexpected heartbeat response from {daemon.identifier}: {response!r}"
            )
            await self._handle_failure(daemon, timestamp)
            return

        await self._handle_success(daemon, timestamp, latency)

    async def _send_probe(
        self,
        address: tuple[str, int],
        payload: bytes,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[bytes, float]:
        future: asyncio.Future[bytes] = loop.create_future()
        start = loop.time()

        transport: asyncio.DatagramTransport | None = None
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _HeartbeatClientProtocol(payload, future),
                remote_addr=address,
            )
            data = await asyncio.wait_for(future, timeout=self._timeout)
        finally:
            if transport is not None:
                transport.close()
                # Allow the loop to process the close callback before returning.
                await asyncio.sleep(0)

        latency = loop.time() - start
        return data, latency

    async def _build_payload(self, server_identity: str) -> bytes:
        if self._proxy_key is None:
            self._proxy_key = await self._database.fetch_proxy_key()
        return (
            f"PROXY Key={self._proxy_key} {server_identity}PROXY {self._payload}"
        ).encode("utf-8")

    async def _handle_success(
        self,
        daemon: "Daemon",
        timestamp: datetime,
        latency_seconds: float,
    ) -> None:
        previous_state = _state_to_db_value(daemon.state)
        self._manager.mark_heartbeat(self._identifier, timestamp=timestamp)
        current_state = _state_to_db_value(daemon.state)
        latency_ms = int(latency_seconds * 1000)

        if current_state != previous_state:
            self._logger.control(
                f"Daemon {daemon.identifier} state changed: {previous_state} -> {current_state}"
            )
        self._logger.control(
            f"Heartbeat OK from {daemon.identifier} ({latency_ms} ms)"
        )
        await self._persist_state(daemon, timestamp, current_state, previous_state, latency_ms)

    async def _handle_failure(self, daemon: "Daemon", timestamp: datetime) -> None:
        previous_state = _state_to_db_value(daemon.state)
        self._manager.mark_failure(self._identifier, timestamp=timestamp)
        current_state = _state_to_db_value(daemon.state)
        if current_state != previous_state:
            self._logger.control(
                f"Daemon {daemon.identifier} state changed: {previous_state} -> {current_state}"
            )
        await self._persist_state(daemon, timestamp, current_state, previous_state, None)

    async def _persist_state(
        self,
        daemon: "Daemon",
        timestamp: datetime,
        current_state: str,
        previous_state: str,
        latency_ms: int | None,
    ) -> None:
        try:
            await self._database.update_daemon_state(
                ProxyDaemonState(
                    host=daemon.host,
                    port=daemon.port,
                    current_state=current_state,
                    previous_state=previous_state,
                    checked_at=timestamp,
                    latency_ms=latency_ms,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.e403(
                f"Failed to persist heartbeat state for {daemon.identifier}: {exc}"
            )


class HeartbeatManager:
    """Schedule periodic heartbeat checks for downstream daemon targets."""

    def __init__(self, interval_seconds: float, *, logger: ProxyLogger | None = None) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self._interval = float(interval_seconds)
        self._logger = logger
        self._targets: dict[int, HeartbeatTarget] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    def add_target(self, target: HeartbeatTarget) -> None:
        """Register *target* to receive periodic heartbeat invocations."""

        self._targets[id(target)] = target

    def remove_target(self, target: HeartbeatTarget) -> None:
        """Remove *target* from the scheduling set if present."""

        self._targets.pop(id(target), None)

    async def start(self) -> None:
        """Start scheduling heartbeat checks."""

        if self._task is not None:
            raise RuntimeError("Heartbeat manager already running")

        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._task = self._loop.create_task(self._run())

    async def stop(self) -> None:
        """Stop heartbeat scheduling tasks."""

        if self._task is None or self._stop_event is None:
            return

        self._stop_event.set()
        try:
            await self._task
        finally:
            self._task = None
            self._loop = None
            self._stop_event = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        while True:
            await self._dispatch_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue
            else:
                return

    async def _dispatch_once(self) -> None:
        targets = list(self._targets.values())
        if not targets:
            return

        results = await asyncio.gather(
            *(target.send_heartbeat() for target in targets),
            return_exceptions=True,
        )
        for target, result in zip(targets, results, strict=False):
            if isinstance(result, Exception):
                if self._logger is not None:
                    self._logger.e403(f"Heartbeat target {target!r} raised: {result}")
