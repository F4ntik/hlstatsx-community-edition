from __future__ import annotations

import asyncio
from io import StringIO

import pytest

from proxy_daemon_py.balancer import Daemon, DaemonManager, DaemonState
from proxy_daemon_py.db import ProxyDaemonState
from proxy_daemon_py.heartbeat import DaemonHeartbeatTarget, HeartbeatManager
from proxy_daemon_py.log import LoggerConfig, ProxyLogger


class _RecordingTarget:
    def __init__(self) -> None:
        self.calls: list[float] = []
        self._event = asyncio.Event()

    async def send_heartbeat(self) -> None:
        self.calls.append(asyncio.get_running_loop().time())
        self._event.set()

    async def wait_for_call(self, timeout: float) -> None:
        await asyncio.wait_for(self._event.wait(), timeout=timeout)
        self._event.clear()


class _FailingTarget:
    def __init__(self) -> None:
        self.calls = 0

    async def send_heartbeat(self) -> None:
        self.calls += 1
        raise RuntimeError("simulated failure")


class _FakeDatabaseAdapter:
    def __init__(self) -> None:
        self.states: list[ProxyDaemonState] = []

    async def update_daemon_state(self, state: ProxyDaemonState) -> None:
        self.states.append(state)


class _HeartbeatResponder(asyncio.DatagramProtocol):
    def __init__(self, response: bytes | None = b"Heartbeat OK") -> None:
        self._response = response
        self.transport: asyncio.DatagramTransport | None = None
        self.received: list[bytes] = []
        self._event = asyncio.Event()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:  # pragma: no cover - trivial
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.received.append(data)
        self._event.set()
        if self._response is not None and self.transport is not None:
            self.transport.sendto(self._response, addr)

    def set_response(self, response: bytes | None) -> None:
        self._response = response

    async def wait_for_request(self, timeout: float) -> None:
        await asyncio.wait_for(self._event.wait(), timeout=timeout)
        self._event.clear()


def test_heartbeat_manager_runs_periodically() -> None:
    asyncio.run(_run_heartbeat_manager_runs_periodically())


async def _run_heartbeat_manager_runs_periodically() -> None:
    manager = HeartbeatManager(0.05)
    target = _RecordingTarget()
    manager.add_target(target)

    await manager.start()
    await target.wait_for_call(0.2)
    await asyncio.sleep(0.12)
    await manager.stop()

    assert len(target.calls) >= 2
    gaps = [b - a for a, b in zip(target.calls, target.calls[1:], strict=False)]
    assert all(gap >= 0 for gap in gaps)


def test_heartbeat_manager_logs_exceptions_without_interrupting() -> None:
    asyncio.run(_run_heartbeat_manager_logs_exceptions_without_interrupting())


async def _run_heartbeat_manager_logs_exceptions_without_interrupting() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    manager = HeartbeatManager(0.05, logger=logger)
    failing = _FailingTarget()
    healthy = _RecordingTarget()
    manager.add_target(failing)
    manager.add_target(healthy)

    await manager.start()
    await healthy.wait_for_call(0.2)
    await asyncio.sleep(0.05)
    await manager.stop()

    assert failing.calls >= 1
    assert len(healthy.calls) >= 1
    assert "simulated failure" in buffer.getvalue()


def test_heartbeat_manager_stop_sending_after_removal() -> None:
    asyncio.run(_run_heartbeat_manager_stop_sending_after_removal())


async def _run_heartbeat_manager_stop_sending_after_removal() -> None:
    manager = HeartbeatManager(0.2)
    target = _RecordingTarget()
    manager.add_target(target)

    await manager.start()
    await target.wait_for_call(0.2)
    manager.remove_target(target)

    with pytest.raises(asyncio.TimeoutError):
        await target.wait_for_call(0.25)

    await manager.stop()


def test_daemon_heartbeat_target_marks_success() -> None:
    asyncio.run(_run_daemon_heartbeat_target_marks_success())


def test_daemon_heartbeat_target_marks_failure_on_bad_response() -> None:
    asyncio.run(_run_daemon_heartbeat_target_marks_failure_on_bad_response())


def test_daemon_heartbeat_target_recovers_from_failure() -> None:
    asyncio.run(_run_daemon_heartbeat_target_recovers_from_failure())


async def _run_daemon_heartbeat_target_marks_success() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    db = _FakeDatabaseAdapter()
    manager = DaemonManager()

    loop = asyncio.get_running_loop()
    responder = _HeartbeatResponder()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: responder, local_addr=("127.0.0.1", 0)
    )
    try:
        host, port = transport.get_extra_info("sockname")[:2]
        identifier = f"{host}:{port}"
        daemon = Daemon(identifier=identifier, host=host, port=port, heartbeat_timeout=1.0)
        manager.register(daemon)

        target = DaemonHeartbeatTarget(identifier, manager, db, logger, timeout=0.2)
        await target.send_heartbeat()

        await responder.wait_for_request(0.2)
    finally:
        transport.close()
        await asyncio.sleep(0)

    assert manager.get(identifier).state is DaemonState.UP
    assert db.states
    state = db.states[-1]
    assert state.current_state == "up"
    assert state.previous_state == "n/a"
    assert state.latency_ms is not None and state.latency_ms >= 0
    output = buffer.getvalue()
    assert "Heartbeat OK from" in output
    assert "state changed: n/a -> up" in output


async def _run_daemon_heartbeat_target_marks_failure_on_bad_response() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    db = _FakeDatabaseAdapter()
    manager = DaemonManager()

    loop = asyncio.get_running_loop()
    responder = _HeartbeatResponder(response=b"NOPE")
    transport, _ = await loop.create_datagram_endpoint(
        lambda: responder, local_addr=("127.0.0.1", 0)
    )
    try:
        host, port = transport.get_extra_info("sockname")[:2]
        identifier = f"{host}:{port}"
        daemon = Daemon(identifier=identifier, host=host, port=port, heartbeat_timeout=1.0)
        manager.register(daemon)

        target = DaemonHeartbeatTarget(identifier, manager, db, logger, timeout=0.2)
        await target.send_heartbeat()
        await responder.wait_for_request(0.2)
    finally:
        transport.close()
        await asyncio.sleep(0)

    assert manager.get(identifier).state is DaemonState.DOWN
    assert db.states
    state = db.states[-1]
    assert state.current_state == "down"
    assert state.previous_state == "n/a"
    assert state.latency_ms is None
    output = buffer.getvalue()
    assert "Unexpected heartbeat response" in output
    assert "state changed: n/a -> down" in output


async def _run_daemon_heartbeat_target_recovers_from_failure() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    db = _FakeDatabaseAdapter()
    manager = DaemonManager()

    loop = asyncio.get_running_loop()
    responder = _HeartbeatResponder(response=None)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: responder, local_addr=("127.0.0.1", 0)
    )
    try:
        host, port = transport.get_extra_info("sockname")[:2]
        identifier = f"{host}:{port}"
        daemon = Daemon(identifier=identifier, host=host, port=port, heartbeat_timeout=0.1)
        manager.register(daemon)

        target = DaemonHeartbeatTarget(identifier, manager, db, logger, timeout=0.1)

        await target.send_heartbeat()
        await responder.wait_for_request(0.2)

        responder.set_response(b"Heartbeat OK")
        await target.send_heartbeat()
        await responder.wait_for_request(0.2)
    finally:
        transport.close()
        await asyncio.sleep(0)

    assert len(db.states) >= 2
    first, second = db.states[-2:]
    assert first.current_state == "down" and first.previous_state == "n/a"
    assert second.current_state == "up" and second.previous_state in {"down", "n/a"}
    daemon = manager.get(identifier)
    assert daemon.state is DaemonState.UP
    assert daemon.consecutive_failures == 0
    output = buffer.getvalue()
    assert "state changed: n/a -> down" in output
    assert "state changed: down -> up" in output
