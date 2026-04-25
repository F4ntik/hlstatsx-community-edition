from __future__ import annotations

import asyncio
import socket
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import MappingProxyType

from proxy_daemon_py.balancer import Daemon, ServerAssignment, ServerBalancer
from proxy_daemon_py.config import ProxyConfig
from proxy_daemon_py.daemon import ProxyDaemon
from proxy_daemon_py.db import ProxyDaemonTarget
from proxy_daemon_py.log import LoggerConfig, ProxyLogger
from proxy_daemon_py.transport import InboundDatagram, ProxyUdpServer


class FakeDatabaseAdapter:
    def __init__(self, proxy_key: str, *, daemons: list[ProxyDaemonTarget] | None = None) -> None:
        self._proxy_key = proxy_key
        self.connected = False
        self.daemons = list(daemons or [])

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def fetch_proxy_key(self) -> str:
        return self._proxy_key

    async def fetch_daemons(self) -> list[ProxyDaemonTarget]:
        return list(self.daemons)


class DummyHeartbeatManager:
    def __init__(self) -> None:
        self.started = False
        self.targets: set[object] = set()
        self.added: list[object] = []
        self.removed: list[object] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    def add_target(self, target: object) -> None:
        self.targets.add(target)
        self.added.append(target)

    def remove_target(self, target: object) -> None:
        if target in self.targets:
            self.targets.remove(target)
        self.removed.append(target)


def _make_idle_daemon() -> tuple[ProxyDaemon, StringIO, ProxyUdpServer]:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    server = ProxyUdpServer(logger)
    db = FakeDatabaseAdapter('test')
    balancer = ServerBalancer()
    heartbeat = DummyHeartbeatManager()
    daemon = ProxyDaemon(_make_config(), db, balancer, heartbeat, server, logger)
    daemon._proxy_key = 'test'
    return daemon, buffer, server


def _make_config() -> ProxyConfig:
    return ProxyConfig(
        config_path=Path("/tmp/hlstats.conf"),
        db_host="localhost",
        db_username="hlstats",
        db_password="secret",
        db_name="hlstats",
        bind_ip="127.0.0.1",
        port=0,
        debug_level=0,
        event_queue_size=10,
        cpanel_hack=False,
        raw=MappingProxyType({}),
    )


def test_proxy_daemon_handles_local_commands() -> None:
    asyncio.run(_run_handles_local_commands())


def test_proxy_daemon_handles_proxy_commands() -> None:
    asyncio.run(_run_handles_proxy_commands())


def test_proxy_daemon_rejects_invalid_proxy_key() -> None:
    asyncio.run(_run_rejects_invalid_proxy_key())


def test_proxy_daemon_forwards_non_control_payloads() -> None:
    asyncio.run(_run_forwards_non_control_payloads())


def test_proxy_daemon_reassigns_on_send_failure() -> None:
    asyncio.run(_run_reassigns_on_send_failure())


def test_parse_proxy_command_invalid_inputs() -> None:
    assert ProxyDaemon._parse_proxy_command('invalid') is None
    assert ProxyDaemon._parse_proxy_command('PROXY Foo=bar PROXY C;HEARTBEAT;') is None
    assert ProxyDaemon._parse_proxy_command('PROXY Key=abc PROXY payload') == ('abc', 'payload')


def test_format_server_list_handles_empty_and_populated() -> None:
    daemon, _, _ = _make_idle_daemon()
    assert daemon._format_server_list() == 'ServerList\n'
    daemon._balancer.register_daemon(Daemon(identifier='id', host='127.0.0.1', port=6000))
    daemon._balancer.assignments['srv'] = ServerAssignment(
        server_address='srv',
        daemon_id='id',
        assigned_at=datetime.now(tz=timezone.utc),
    )
    assert daemon._format_server_list() == 'ServerList\nsrv -> id\n'


def test_forward_game_packet_requires_proxy_key() -> None:
    daemon, buffer, _ = _make_idle_daemon()
    daemon._proxy_key = None
    datagram = InboundDatagram(b'data', 'RL data', ('127.0.0.1', 27015))
    daemon._forward_game_packet(datagram)
    assert 'Proxy key unavailable' in buffer.getvalue()


def test_forward_game_packet_logs_when_no_daemon_available() -> None:
    daemon, buffer, _ = _make_idle_daemon()
    datagram = InboundDatagram(b'RL data', 'RL data', ('127.0.0.1', 27015))
    daemon._forward_game_packet(datagram)
    assert 'No available daemon' in buffer.getvalue()


def test_forward_game_packet_skips_ignored_payloads() -> None:
    daemon, buffer, _ = _make_idle_daemon()
    text = 'rcon from 1.2.3.4:27015 command "status"'
    datagram = InboundDatagram(text.encode(), text, ('127.0.0.1', 27015))
    daemon._forward_game_packet(datagram)
    assert 'Skipping message' in buffer.getvalue()


def test_forward_game_packet_exhausts_candidates_after_failures() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    failing_server = _FailingProxyUdpServer(logger, fail_destination='127.0.0.1:65001')
    db = FakeDatabaseAdapter('test')
    balancer = ServerBalancer()
    heartbeat = DummyHeartbeatManager()
    daemon = ProxyDaemon(_make_config(), db, balancer, heartbeat, failing_server, logger)
    daemon._proxy_key = 'test'
    balancer.register_daemon(Daemon(identifier='127.0.0.1:65001', host='127.0.0.1', port=65001))
    balancer.manager.mark_heartbeat('127.0.0.1:65001')
    datagram = InboundDatagram(b'RL payload', 'RL payload', ('127.0.0.1', 27015))
    daemon._forward_game_packet(datagram)
    assert 'Exhausted daemon candidates' in buffer.getvalue()


def test_normalise_payload_trims_to_last_marker() -> None:
    daemon, _, _ = _make_idle_daemon()
    assert daemon._normalise_payload('noise RL first RL second') == 'RL second'
    assert daemon._normalise_payload('no marker') == 'no marker'


def test_should_skip_payload_matches_commands() -> None:
    daemon, _, _ = _make_idle_daemon()
    assert daemon._should_skip_payload('rcon from 1 command "status"')
    assert daemon._should_skip_payload('rcon from 1 command "stats"')
    assert daemon._should_skip_payload('rcon from 1 command ""')
    assert not daemon._should_skip_payload('rcon from 1 command "other"')
    assert not daemon._should_skip_payload('some other text')


def test_proxy_daemon_reload_updates_daemon_pool() -> None:
    asyncio.run(_run_reload_updates_daemon_pool())


async def _run_handles_local_commands() -> None:
    buffer, daemon, udp_server = await _start_daemon()
    address = udp_server.address
    assert address is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    try:
        sock.sendto(b"C;HEARTBEAT;", address)
        data, _ = await asyncio.wait_for(asyncio.to_thread(sock.recvfrom, 1024), timeout=3)
    finally:
        sock.close()
        await daemon.stop()

    assert data == b"Heartbeat OK"
    assert "Sending Heartbeat" in buffer.getvalue()


async def _run_handles_proxy_commands() -> None:
    buffer, daemon, udp_server = await _start_daemon()

    balancer = daemon.balancer
    daemon_id = "10.0.0.1:5000"
    balancer.register_daemon(Daemon(identifier=daemon_id, host="10.0.0.1", port=5000))
    balancer.assignments["1.2.3.4:27015"] = ServerAssignment(
        server_address="1.2.3.4:27015",
        daemon_id=daemon_id,
        assigned_at=datetime.now(tz=timezone.utc),
    )

    address = udp_server.address
    assert address is not None

    packet = b"PROXY Key=test PROXY C;SERVERLIST;"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    try:
        sock.sendto(packet, address)
        data, _ = await asyncio.wait_for(asyncio.to_thread(sock.recvfrom, 1024), timeout=1)
    finally:
        sock.close()
        await daemon.stop()

    expected = b"ServerList\n1.2.3.4:27015 -> 10.0.0.1:5000\n"
    assert data == expected
    assert "Sending Serverlist" in buffer.getvalue()


async def _run_rejects_invalid_proxy_key() -> None:
    buffer, daemon, udp_server = await _start_daemon()
    address = udp_server.address
    assert address is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    try:
        sock.sendto(b"PROXY Key=wrong PROXY C;HEARTBEAT;", address)
        data, _ = await asyncio.wait_for(asyncio.to_thread(sock.recvfrom, 1024), timeout=1)
    finally:
        client_port = sock.getsockname()[1]
        sock.close()
        await daemon.stop()

    expected = f"FAILED PROXY REQUEST (127.0.0.1:{client_port})\n".encode()
    assert data == expected
    assert "FAILED PROXY REQUEST" in buffer.getvalue()


async def _run_forwards_non_control_payloads() -> None:
    buffer, daemon, udp_server = await _start_daemon()
    address = udp_server.address
    assert address is not None

    loop = asyncio.get_running_loop()
    protocol = _RecordingProtocol()
    transport, _ = await loop.create_datagram_endpoint(lambda: protocol, local_addr=("127.0.0.1", 0))

    daemon_host, daemon_port = transport.get_extra_info("sockname")[:2]
    identifier = f"{daemon_host}:{daemon_port}"
    daemon.balancer.register_daemon(Daemon(identifier=identifier, host=daemon_host, port=daemon_port))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    try:
        payload = b"noise RL some payload"
        sock.sendto(payload, address)
        forwarded, sender = await asyncio.wait_for(protocol.queue.get(), timeout=1)
        assert sender[0] == address[0]
    finally:
        client_port = sock.getsockname()[1]
        sock.close()
        transport.close()
        await daemon.stop()

    expected = f"PROXY Key=test 127.0.0.1:{client_port}PROXY RL some payload".encode()
    assert forwarded == expected
    assert "Forwarded packet" in buffer.getvalue()


async def _run_reassigns_on_send_failure() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    failing_server = _FailingProxyUdpServer(logger, fail_destination="127.0.0.1:65001")
    db = FakeDatabaseAdapter("test")
    balancer = ServerBalancer()
    heartbeat = DummyHeartbeatManager()
    config = _make_config()

    daemon = ProxyDaemon(config, db, balancer, heartbeat, failing_server, logger)
    await daemon.start()

    balancer.register_daemon(Daemon(identifier="127.0.0.1:65001", host="127.0.0.1", port=65001))

    loop = asyncio.get_running_loop()
    protocol = _RecordingProtocol()
    transport, _ = await loop.create_datagram_endpoint(lambda: protocol, local_addr=("127.0.0.1", 0))
    daemon_host, daemon_port = transport.get_extra_info("sockname")[:2]
    second_identifier = f"{daemon_host}:{daemon_port}"
    balancer.register_daemon(Daemon(identifier=second_identifier, host=daemon_host, port=daemon_port))

    address = failing_server.address
    assert address is not None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1)
    try:
        sock.sendto(b"RL forward me", address)
        forwarded, _ = await asyncio.wait_for(protocol.queue.get(), timeout=1)
    finally:
        client_port = sock.getsockname()[1]
        sock.close()
        transport.close()
        await daemon.stop()

    expected = f"PROXY Key=test 127.0.0.1:{client_port}PROXY RL forward me".encode()
    assert forwarded == expected
    assert failing_server.failed_once
    assignment = balancer.assignments.get(f"127.0.0.1:{client_port}")
    assert assignment is not None and assignment.daemon_id == second_identifier


async def _run_reload_updates_daemon_pool() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    heartbeat = DummyHeartbeatManager()
    initial_target = ProxyDaemonTarget(host="127.0.0.1", port=65001)
    db = FakeDatabaseAdapter("test", daemons=[initial_target])
    balancer = ServerBalancer()
    server = ProxyUdpServer(logger)
    config = _make_config()

    daemon = ProxyDaemon(config, db, balancer, heartbeat, server, logger)
    await daemon.start()

    try:
        address = server.address
        assert address is not None

        identifier_old = "127.0.0.1:65001"
        assert identifier_old in balancer.manager.daemons
        assignment = balancer.assign_server("1.2.3.4:27015")
        assert assignment is not None and assignment.daemon_id == identifier_old
        assert heartbeat.started

        db.daemons = [ProxyDaemonTarget(host="127.0.0.1", port=65002)]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        try:
            sock.sendto(b"C;RELOAD;", address)
            data, _ = await asyncio.wait_for(asyncio.to_thread(sock.recvfrom, 1024), timeout=1)
        finally:
            sock.close()

        assert data == b"Reload command acknowledged\n"

        identifier_new = "127.0.0.1:65002"
        assert identifier_new in balancer.manager.daemons
        assert identifier_old not in balancer.manager.daemons
        assert not balancer.assignments
        heartbeat_ids = {getattr(target, "_identifier", None) for target in heartbeat.targets}
        assert heartbeat_ids == {identifier_new}
    finally:
        await daemon.stop()


class _RecordingProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:  # pragma: no cover - exercised via asyncio
        self.queue.put_nowait((data, addr))


class _FailingProxyUdpServer(ProxyUdpServer):
    def __init__(self, logger: ProxyLogger, *, fail_destination: str) -> None:
        super().__init__(logger)
        self._fail_destination = fail_destination
        self.failed_once = False

    def send_text(self, message: str, address: tuple[str, int]) -> None:
        destination = f"{address[0]}:{address[1]}"
        if destination == self._fail_destination and not self.failed_once:
            self.failed_once = True
            raise OSError("simulated network failure")
        super().send_text(message, address)


async def _start_daemon(*, udp_server: ProxyUdpServer | None = None) -> tuple[StringIO, ProxyDaemon, ProxyUdpServer]:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    server = udp_server or ProxyUdpServer(logger)
    db = FakeDatabaseAdapter("test")
    balancer = ServerBalancer()
    heartbeat = DummyHeartbeatManager()
    config = _make_config()

    daemon = ProxyDaemon(config, db, balancer, heartbeat, server, logger)
    await daemon.start()

    return buffer, daemon, server
