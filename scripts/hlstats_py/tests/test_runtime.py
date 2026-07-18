from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from io import StringIO
from unittest.mock import patch

import pytest

import hlstats_py.runtime as runtime_module
from hlstats_py.runtime import HlstatsRuntime, build_dispatcher
from hlstats_py.cli import load_settings
from hlx_core.db import GameServer
from hlx_core.log import LoggerConfig, ProxyLogger
from hlx_core.transport import ProxyUdpServer


@dataclass(slots=True)
class RecordedEvent:
    event_code: str
    category: str
    server_id: int
    game: str
    current_map: str
    round_status: int


@dataclass(slots=True)
class RecordedMapTransition:
    server_id: int
    phase: str
    map_name: str


class StubStorage:
    def __init__(self) -> None:
        self.recorded: list[RecordedEvent] = []
        self.map_transitions: list[RecordedMapTransition] = []
        self.reset_calls = 0
        self.finalize_calls = 0
        self.flush_pending_calls = 0

    def apply_server_map_transition(
        self, server_id: int, phase: str, map_name: str, event_timestamp: object
    ) -> None:
        self.map_transitions.append(RecordedMapTransition(server_id=server_id, phase=phase, map_name=map_name))

    def record(self, update: object, context: object) -> None:
        event_code = getattr(update, "event_code")
        category = getattr(getattr(update, "category"), "value")
        server_id = getattr(context, "server_id")
        game = getattr(context, "game")
        extras = getattr(context, "extras")
        current_map = extras["map"]
        round_status = int(extras.get("round_status", 0))
        self.recorded.append(
            RecordedEvent(
                event_code=event_code,
                category=category,
                server_id=server_id,
                game=game,
                current_map=current_map,
                round_status=round_status,
            )
        )

    def reset_runtime_state(self) -> None:
        self.reset_calls += 1

    def finalize_import(self) -> None:
        self.finalize_calls += 1

    def flush_pending(self) -> None:
        self.flush_pending_calls += 1


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


async def _run_stop_invokes_flush_pending() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)
    await runtime.stop()
    assert storage.flush_pending_calls >= 1


def test_runtime_stop_calls_storage_flush_pending() -> None:
    asyncio.run(_run_stop_invokes_flush_pending())


def test_runtime_handles_control_commands_and_reload() -> None:
    asyncio.run(_run_handles_control_commands_and_reload())


def test_runtime_rejects_direct_mutating_loopback_commands() -> None:
    asyncio.run(_run_rejects_direct_mutating_loopback_commands())


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
            round_status=0,
        )
    ]
    assert storage.finalize_calls == 1


def test_runtime_ignores_empty_timestamp_only_stdin_line() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        "L 01/20/2025 - 03:55:14: ",
        "127.0.0.1:27015",
    )
    runtime.finalize_stdin_import()

    assert storage.recorded == []
    assert storage.finalize_calls == 1


def test_runtime_projects_map_lifecycle_before_followup_events() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: Loading map "de_nuke"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:01: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "127.0.0.1:27015",
    )

    assert storage.map_transitions[0] == RecordedMapTransition(server_id=7, phase="loading", map_name="de_nuke")
    assert storage.recorded[0].current_map == "de_dust2"
    assert storage.recorded[1].current_map == "de_dust2"
    assert storage.recorded[0].round_status == 0
    assert storage.recorded[1].round_status == 0


def test_runtime_started_map_with_crc_suffix_updates_storage() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:31: Started map "de_nuke" (CRC "-1757378041")',
        "127.0.0.1:27015",
    )

    assert storage.map_transitions == [RecordedMapTransition(server_id=7, phase="started", map_name="de_nuke")]
    assert storage.recorded[0].current_map == "de_nuke"
    assert storage.recorded[0].round_status == 0


def test_runtime_started_map_switches_context_for_followup_events() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:29: Loading map "de_nuke"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:31: Started map "de_nuke" (CRC "-1757378041")',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:32: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "127.0.0.1:27015",
    )

    assert storage.map_transitions == [
        RecordedMapTransition(server_id=7, phase="loading", map_name="de_nuke"),
        RecordedMapTransition(server_id=7, phase="started", map_name="de_nuke"),
    ]
    assert storage.recorded[0].current_map == "de_dust2"
    assert storage.recorded[1].current_map == "de_nuke"
    assert storage.recorded[2].current_map == "de_nuke"
    assert [event.round_status for event in storage.recorded] == [0, 0, 0]


def test_runtime_projects_round_status_for_team_trigger_rewards() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:30: Team "CT" triggered "SFUI_Notice_CTs_Win"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:31: Team "CT" triggered "SFUI_Notice_CTs_Win"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:32: World triggered "Round_Start"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/01/2024 - 00:00:33: Team "CT" triggered "SFUI_Notice_CTs_Win"',
        "127.0.0.1:27015",
    )

    assert [event.round_status for event in storage.recorded] == [0, 1, 0, 0]


def test_runtime_projects_round_status_for_goldsrc_bomb_defused() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/06/2024 - 00:18:10: Team "CT" triggered "Bomb_Defused" (CT "6") (T "17")',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/06/2024 - 00:18:10: World triggered "Round_End"',
        "127.0.0.1:27015",
    )

    assert [event.round_status for event in storage.recorded] == [0, 1]


def test_runtime_stdin_quiet_by_default_without_per_event_notice() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    stream = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=stream))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "127.0.0.1:27015",
    )

    assert "Recorded connection event" not in stream.getvalue()


def test_runtime_stdin_verbose_emits_per_event_notice() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    stream = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=stream))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(
        adapter,
        server,
        logger,
        build_dispatcher(),
        storage,
        stdin_verbose_events=True,
    )
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "127.0.0.1:27015",
    )

    assert "Recorded connection event 'connect'" in stream.getvalue()


def test_runtime_metrics_track_processed_events_and_summary() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    stream = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=stream))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:01: Team "CT" triggered "SFUI_Notice_CTs_Win"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:02: "Alice<2><STEAM_1:1:111><CT>" said "hello"',
        "127.0.0.1:27015",
    )

    snapshot = runtime.metrics.snapshot()
    assert snapshot["events_processed"] == 3
    assert snapshot["events_by_category"] == {
        "connection": 1,
        "generic": 1,
        "team_bonus": 1,
    }
    assert snapshot["stdin_records"] == 3

    runtime.log_metrics_summary("stdin import complete")

    log_contents = stream.getvalue()
    assert "HLstats metrics: reason='stdin import complete'" in log_contents
    assert "events_processed=3" in log_contents
    assert "events_by_category=connection:1,generic:1,team_bonus:1" in log_contents


def test_runtime_metrics_track_control_and_dropped_packets() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    assert runtime._handle_control_command("HEARTBEAT", "127.0.0.1", 12345) == "Heartbeat OK"
    reload_command = runtime_module.parse_control_command("C;RELOAD;")
    assert reload_command is not None
    assert (
        runtime._reject_unauthenticated_mutating_control(
            reload_command,
            "127.0.0.1",
            12345,
        )
        == "FAILED CONTROL COMMAND: RELOAD requires PROXY Key"
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"',
        "192.0.2.1:27015",
    )

    snapshot = runtime.metrics.snapshot()
    assert snapshot["control_commands_total"] == 2
    assert snapshot["control_commands_by_type"] == {"HEARTBEAT": 1, "RELOAD": 1}
    assert snapshot["control_commands_rejected"] == 1
    assert snapshot["packets_dropped"] == 1


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


def test_load_settings_accepts_stdin_verbose_and_native_parser(tmp_path) -> None:
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
    settings = load_settings(
        [
            "--configfile",
            str(config_path),
            "--stdin",
            "--server-ip",
            "127.0.0.1",
            "--server-port",
            "27015",
            "--stdin-verbose-events",
            "--parser-backend",
            "native",
            "--stdin-transaction-batch-size",
            "2500",
        ]
    )
    assert settings.stdin_verbose_events is True
    assert settings.parser_backend == "native"
    assert settings.stdin_transaction_batch_size == 2500


def test_serve_uses_import_db_mode_for_stdin(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    captured: dict[str, object] = {}

    class StopAfterAdapter(Exception):
        pass

    class RecordingAdapter:
        def __init__(self, config, **kwargs) -> None:
            captured["config"] = config
            captured["kwargs"] = kwargs
            raise StopAfterAdapter

    monkeypatch.setattr(runtime_module, "SyncDatabaseAdapter", RecordingAdapter)

    with pytest.raises(StopAfterAdapter):
        asyncio.run(
            runtime_module._serve(
                [
                    "--configfile",
                    str(config_path),
                    "--stdin",
                    "--server-ip",
                    "127.0.0.1",
                    "--server-port",
                    "27015",
                ]
            )
        )

    assert captured["kwargs"] == {
        "import_mode": True,
        "enable_multi_statements": True,
    }


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
            round_status=0,
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

            sock.sendto(b"PROXY Key=secret PROXY C;KILL;", address)
            assert await _recv_text(sock) == "OK, EXECUTING COMMAND: KILL"
            await _wait_for(runtime.shutdown_requested.is_set)
        finally:
            sock.close()
    finally:
        await runtime.stop()


async def _run_rejects_direct_mutating_loopback_commands() -> None:
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
            sock.sendto(b"C;RELOAD;", address)
            assert await _recv_text(sock) == "FAILED CONTROL COMMAND: RELOAD requires PROXY Key"
            assert storage.reset_calls == 1

            sock.sendto(b"C;KILL;", address)
            assert await _recv_text(sock) == "FAILED CONTROL COMMAND: KILL requires PROXY Key"
            assert not runtime.shutdown_requested.is_set()

            sock.sendto(b"C;HEARTBEAT;", address)
            assert await _recv_text(sock) == "Heartbeat OK"
        finally:
            sock.close()

        assert "Rejected unauthenticated mutating control command from 127.0.0.1" in buffer.getvalue()
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
