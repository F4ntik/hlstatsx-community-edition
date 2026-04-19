from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from io import StringIO
from unittest.mock import patch

from hlstats_py.runtime import HlstatsRuntime, build_dispatcher
from hlstats_py.cli import load_settings
from proxy_daemon_py.db import GameServer
from proxy_daemon_py.log import LoggerConfig, ProxyLogger
from proxy_daemon_py.transport import ProxyUdpServer


@dataclass(slots=True)
class RecordedEvent:
    event_code: str
    category: str
    server_id: int
    game: str
    current_map: str


class StubStorage:
    def __init__(self) -> None:
        self.recorded: list[RecordedEvent] = []
        self.reset_calls = 0
        self.finalize_calls = 0

    def record(self, update: object, context: object) -> None:
        event_code = getattr(update, "event_code")
        category = getattr(getattr(update, "category"), "value")
        server_id = getattr(context, "server_id")
        game = getattr(context, "game")
        extras = getattr(context, "extras")
        current_map = extras["map"]
        self.recorded.append(
            RecordedEvent(
                event_code=event_code,
                category=category,
                server_id=server_id,
                game=game,
                current_map=current_map,
            )
        )

    def reset_runtime_state(self) -> None:
        self.reset_calls += 1

    def finalize_import(self) -> None:
        self.finalize_calls += 1


class StubAdapter:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False
        self.proxy_key = "secret"
        self.server_batches: list[list[GameServer]] = [
            [
                GameServer(
                    server_id=7,
                    address="127.0.0.1",
                    port=27015,
                    name="Dust",
                    game="csgo",
                    current_map="de_dust2",
                )
            ]
        ]
        self.fetch_servers_calls = 0

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.closed = True

    def fetch_proxy_key(self) -> str:
        return self.proxy_key

    def fetch_servers(self) -> list[GameServer]:
        index = min(self.fetch_servers_calls, len(self.server_batches) - 1)
        self.fetch_servers_calls += 1
        return self.server_batches[index]


async def _recv_text(sock: socket.socket, timeout: float = 1.0) -> str:
    loop = asyncio.get_running_loop()
    data = await asyncio.wait_for(loop.sock_recv(sock, 4096), timeout=timeout)
    return data.decode("utf-8")


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for predicate")


def test_runtime_records_proxied_event() -> None:
    asyncio.run(_run_records_proxied_event())


def test_runtime_handles_control_commands_and_reload() -> None:
    asyncio.run(_run_handles_control_commands_and_reload())


def test_runtime_drops_bad_proxy_key_without_response() -> None:
    asyncio.run(_run_drops_bad_proxy_key_without_response())


def test_runtime_processes_stdin_line_for_known_server() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "127.0.0.1:27015",
    )
    runtime.finalize_stdin_import()

    assert storage.recorded == [
        RecordedEvent(
            event_code="connect",
            category="connection",
            server_id=7,
            game="csgo",
            current_map="de_dust2",
        )
    ]
    assert storage.finalize_calls == 1


def test_load_settings_requires_server_identity_for_stdin(tmp_path) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )

    with patch("sys.stderr", new=StringIO()):
        try:
            load_settings(["--configfile", str(config_path), "--stdin"])
        except Exception as exc:
            assert str(exc) == "--stdin requires both --server-ip and --server-port"
        else:
            raise AssertionError("stdin mode should require explicit source server identity")


async def _run_records_proxied_event() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)

    try:
        address = server.address
        assert address is not None

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            payload = (
                'PROXY Key=secret 127.0.0.1:27015PROXY '
                'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                'address "1.2.3.4:27005"'
            ).encode("utf-8")
            sock.sendto(payload, address)
            await _wait_for(lambda: len(storage.recorded) == 1)
        finally:
            sock.close()

        assert storage.recorded == [
            RecordedEvent(
                event_code="connect",
                category="connection",
                server_id=7,
                game="csgo",
                current_map="de_dust2",
            )
        ]
    finally:
        await runtime.stop()


async def _run_handles_control_commands_and_reload() -> None:
    adapter = StubAdapter()
    adapter.server_batches.append(
        [
            GameServer(
                server_id=9,
                address="127.0.0.1",
                port=27016,
                name="Inferno",
                game="csgo",
                current_map="de_inferno",
            )
        ]
    )
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)

    try:
        address = server.address
        assert address is not None

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            sock.sendto(b"C;HEARTBEAT;", address)
            assert await _recv_text(sock) == "Heartbeat OK"

            sock.sendto(b"PROXY Key=secret PROXY C;RELOAD;", address)
            assert await _recv_text(sock) == "OK, EXECUTING COMMAND: RELOAD"
            assert storage.reset_calls == 2

            sock.sendto(b"C;SERVERLIST;", address)
            response = await _recv_text(sock)
            assert "127.0.0.1:27016 -> Inferno [csgo]" in response

            sock.sendto(b"C;KILL;", address)
            assert await _recv_text(sock) == "OK, EXECUTING COMMAND: KILL"
            await _wait_for(runtime.shutdown_requested.is_set)
        finally:
            sock.close()
    finally:
        await runtime.stop()


async def _run_drops_bad_proxy_key_without_response() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)

    try:
        address = server.address
        assert address is not None

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            sock.sendto(b"PROXY Key=wrong PROXY C;HEARTBEAT;", address)
            try:
                await _recv_text(sock, timeout=0.2)
                raise AssertionError("Bad proxy key should not produce a response")
            except asyncio.TimeoutError:
                pass
        finally:
            sock.close()

        assert storage.recorded == []
        assert "Proxy key mismatch" in buffer.getvalue()
    finally:
        await runtime.stop()
