from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import MappingProxyType

from proxy_daemon_py.balancer import ServerBalancer
from proxy_daemon_py.config import ProxyConfig
from proxy_daemon_py.daemon import ProxyDaemon
from proxy_daemon_py.db import ProxyDaemonTarget
from proxy_daemon_py.log import LoggerConfig, ProxyLogger
from proxy_daemon_py.transport import InboundDatagram


@dataclass(frozen=True, slots=True)
class Message:
    """Datagram emitted by the UDP server during the replay."""

    destination: tuple[str, int]
    payload: str


@dataclass(frozen=True, slots=True)
class LogRecord:
    """Single log record captured during the replay run."""

    level: str
    message: str


@dataclass(frozen=True, slots=True)
class ReplayDatagram:
    """Input datagram that should be consumed by the daemon."""

    description: str
    payload: str
    source: tuple[str, int]


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    """Canonical replay derived from the behaviour of the Perl daemon."""

    proxy_key: str
    daemon_targets: tuple[ProxyDaemonTarget, ...]
    datagrams: tuple[ReplayDatagram, ...]
    expected_messages: tuple[Message, ...]
    expected_assignments: dict[str, str]
    expected_logs: tuple[LogRecord, ...]


class FakeDatabaseAdapter:
    """In-memory database adapter used for deterministic replay testing."""

    def __init__(self, proxy_key: str, targets: tuple[ProxyDaemonTarget, ...]) -> None:
        self._proxy_key = proxy_key
        self._targets = targets
        self.connected = False
        self.reloads = 0

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def fetch_proxy_key(self) -> str:
        return self._proxy_key

    async def fetch_daemons(self) -> list[ProxyDaemonTarget]:
        self.reloads += 1
        return list(self._targets)


class DummyHeartbeatManager:
    """Heartbeat scheduler stub that records registered targets."""

    def __init__(self) -> None:
        self.started = False
        self.targets: set[object] = set()

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False
        self.targets.clear()

    def add_target(self, target: object) -> None:
        self.targets.add(target)

    def remove_target(self, target: object) -> None:
        self.targets.discard(target)


class FakeUdpServer:
    """UDP server stub that captures outgoing datagrams for assertions."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[InboundDatagram] = asyncio.Queue()
        self.sent_messages: list[Message] = []
        self._running = False
        self._address: tuple[str, int] | None = None

    @property
    def address(self) -> tuple[str, int] | None:
        return self._address if self._running else None

    async def start(self, host: str | None, port: int) -> None:
        if self._running:
            raise RuntimeError("UDP server already running")
        bind_host = host or "0.0.0.0"
        self._address = (bind_host, port)
        self._running = True

    async def stop(self) -> None:
        self._running = False
        self._address = None

    def send_text(self, message: str, address: tuple[str, int]) -> None:
        if not self._running:
            raise RuntimeError("UDP server is not running")
        self.sent_messages.append(Message(destination=address, payload=message))


PERL_REPLAY = ReplayScenario(
    proxy_key="perl-key",
    daemon_targets=(
        ProxyDaemonTarget(host="127.0.0.1", port=28000),
        ProxyDaemonTarget(host="127.0.0.1", port=28001),
    ),
    datagrams=(
        ReplayDatagram(
            description="remote heartbeat via proxy",
            payload="PROXY Key=perl-key PROXY C;HEARTBEAT;",
            source=("198.51.100.10", 27015),
        ),
        ReplayDatagram(
            description="remote serverlist request",
            payload="PROXY Key=perl-key PROXY C;SERVERLIST;",
            source=("198.51.100.10", 27015),
        ),
        ReplayDatagram(
            description="first game packet",
            payload="noise RL FIRST RL PLAYER;connected",
            source=("198.51.100.10", 27015),
        ),
        ReplayDatagram(
            description="second packet from same server",
            payload="RL ROUND;start",
            source=("198.51.100.10", 27015),
        ),
        ReplayDatagram(
            description="packet from second server",
            payload="log RL INFO RL PLAYER;killed",
            source=("203.0.113.5", 27016),
        ),
        ReplayDatagram(
            description="invalid proxy key",
            payload="PROXY Key=wrong PROXY C;HEARTBEAT;",
            source=("198.51.100.10", 27015),
        ),
        ReplayDatagram(
            description="local reload command rejected by product hardening",
            payload="C;RELOAD;",
            source=("127.0.0.1", 9999),
        ),
        ReplayDatagram(
            description="serverlist with assignments",
            payload="PROXY Key=perl-key PROXY C;SERVERLIST;",
            source=("198.51.100.10", 27015),
        ),
    ),
    expected_messages=(
        Message(destination=("198.51.100.10", 27015), payload="Heartbeat OK"),
        Message(destination=("198.51.100.10", 27015), payload="ServerList\n"),
        Message(
            destination=("127.0.0.1", 28000),
            payload="PROXY Key=perl-key 198.51.100.10:27015PROXY RL PLAYER;connected",
        ),
        Message(
            destination=("127.0.0.1", 28000),
            payload="PROXY Key=perl-key 198.51.100.10:27015PROXY RL ROUND;start",
        ),
        Message(
            destination=("127.0.0.1", 28001),
            payload="PROXY Key=perl-key 203.0.113.5:27016PROXY RL PLAYER;killed",
        ),
        Message(
            destination=("198.51.100.10", 27015),
            payload="FAILED PROXY REQUEST (198.51.100.10:27015)\n",
        ),
        Message(
            destination=("127.0.0.1", 9999),
            payload="FAILED CONTROL COMMAND: RELOAD requires PROXY Key\n",
        ),
        Message(
            destination=("198.51.100.10", 27015),
            payload=(
                "ServerList\n"
                "198.51.100.10:27015 -> 127.0.0.1:28000\n"
                "203.0.113.5:27016 -> 127.0.0.1:28001\n"
            ),
        ),
    ),
    expected_assignments={
        "198.51.100.10:27015": "127.0.0.1:28000",
        "203.0.113.5:27016": "127.0.0.1:28001",
    },
    expected_logs=(
        LogRecord(level="CONTROL", message="Registered proxy daemon 127.0.0.1:28000"),
        LogRecord(level="CONTROL", message="Registered proxy daemon 127.0.0.1:28001"),
        LogRecord(level="CONTROL", message="Reloaded proxy daemon configuration: 2 entries"),
        LogRecord(level="NOTICE", message="Proxy daemon listening on 127.0.0.1:27500"),
        LogRecord(level="CONTROL", message="Sending Heartbeat to 198.51.100.10:27015"),
        LogRecord(level="CONTROL", message="Sending Serverlist to 198.51.100.10:27015"),
        LogRecord(
            level="BALANCE",
            message="Forwarded packet from 198.51.100.10:27015 to 127.0.0.1:28000",
        ),
        LogRecord(
            level="BALANCE",
            message="Forwarded packet from 198.51.100.10:27015 to 127.0.0.1:28000",
        ),
        LogRecord(
            level="BALANCE",
            message="Forwarded packet from 203.0.113.5:27016 to 127.0.0.1:28001",
        ),
        LogRecord(
            level="E403",
            message="Sending FAILED PROXY REQUEST to 198.51.100.10:27015",
        ),
        LogRecord(
            level="CONTROL",
            message="Rejected unauthenticated mutating control command from 127.0.0.1:9999: RELOAD",
        ),
        LogRecord(level="CONTROL", message="Sending Serverlist to 198.51.100.10:27015"),
        LogRecord(
            level="CONTROL",
            message=(
                "ServerList\n"
                "198.51.100.10:27015 -> 127.0.0.1:28000\n"
                "203.0.113.5:27016 -> 127.0.0.1:28001"
            ),
        ),
        LogRecord(level="NOTICE", message="Proxy daemon stopped"),
    ),
)


def test_python_daemon_matches_perl_replay() -> None:
    sent_messages, assignments, logs = asyncio.run(_run_perl_replay(PERL_REPLAY))

    assert sent_messages == list(PERL_REPLAY.expected_messages)
    assert assignments == PERL_REPLAY.expected_assignments
    assert logs == list(PERL_REPLAY.expected_logs)


async def _run_perl_replay(
    scenario: ReplayScenario,
) -> tuple[list[Message], dict[str, str], list[LogRecord]]:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    db = FakeDatabaseAdapter(scenario.proxy_key, scenario.daemon_targets)
    heartbeat = DummyHeartbeatManager()
    udp_server = FakeUdpServer()
    daemon = ProxyDaemon(_make_config(), db, ServerBalancer(), heartbeat, udp_server, logger)

    await daemon.start()
    try:
        for datagram in scenario.datagrams:
            inbound = InboundDatagram(
                data=datagram.payload.encode("utf-8"),
                text=datagram.payload,
                address=datagram.source,
            )
            udp_server.queue.put_nowait(inbound)
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.wait_for(daemon.game_packet_queue.join(), timeout=1)
        assignments = {
            server: assignment.daemon_id
            for server, assignment in daemon.balancer.assignments.items()
        }
    finally:
        await daemon.stop()

    logs = _parse_logs(buffer.getvalue())
    return udp_server.sent_messages, assignments, logs


def _parse_logs(raw_output: str) -> list[LogRecord]:
    records: list[LogRecord] = []
    current_level: str | None = None
    current_message_parts: list[str] = []

    for line in raw_output.splitlines():
        if line.startswith("["):
            if current_level is not None:
                records.append(_make_log_record(current_level, current_message_parts))
            parts = line.split("] ", 2)
            if len(parts) >= 3:
                level = parts[1].lstrip("[")
                message = parts[2]
            else:
                level = "UNKNOWN"
                message = line
            current_level = level
            current_message_parts = [message]
        else:
            current_message_parts.append(line)

    if current_level is not None:
        records.append(_make_log_record(current_level, current_message_parts))

    return records


def _make_log_record(level: str, parts: list[str]) -> LogRecord:
    message = "\n".join(parts).rstrip("\n")
    return LogRecord(level=level, message=message)


def _make_config() -> ProxyConfig:
    return ProxyConfig(
        config_path=Path("/tmp/hlstats.conf"),
        db_host="localhost",
        db_username="hlstats",
        db_password="secret",
        db_name="hlstats",
        bind_ip="127.0.0.1",
        port=27500,
        debug_level=0,
        event_queue_size=32,
        cpanel_hack=False,
        raw=MappingProxyType({}),
    )
