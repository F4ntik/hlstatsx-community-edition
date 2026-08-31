from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

import hlstats_py.runtime as runtime_module
import pytest
from hlstats_py.cli import load_settings
from hlstats_py.runtime import BoundedIngressQueue, HlstatsRuntime, build_dispatcher
from hlx_core.db import GameServer
from hlx_core.log import LoggerConfig, ProxyLogger
from hlx_core.transport import InboundDatagram, ProxyUdpServer


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
        self.updates: list[object] = []
        self.map_transitions: list[RecordedMapTransition] = []
        self.reset_calls = 0
        self.finalize_calls = 0
        self.flush_pending_calls = 0
        self.online_event_calls: list[str] = []
        self.source_log_boundaries: list[int] = []

    def begin_online_event(self) -> None:
        self.online_event_calls.append("begin")

    def commit_online_event(self) -> None:
        self.online_event_calls.append("commit")

    def abort_online_event(self) -> None:
        self.online_event_calls.append("abort")

    def mark_source_log_boundary(self, server_id: int) -> None:
        self.source_log_boundaries.append(server_id)
        self.online_event_calls.append("boundary")

    def apply_server_map_transition(
        self, server_id: int, phase: str, map_name: str, event_timestamp: object
    ) -> None:
        self.map_transitions.append(RecordedMapTransition(server_id=server_id, phase=phase, map_name=map_name))

    def record(self, update: object, context: object) -> None:
        self.updates.append(update)
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


def _load_workspace_module(module_name: str, source_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


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


def test_bounded_ingress_queue_drops_overload_and_reports_runtime_metric() -> None:
    stream = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=stream))
    queue = BoundedIngressQueue(logger, maxsize=1)
    server = ProxyUdpServer(logger, queue_factory=lambda: queue)
    first = InboundDatagram(data=b"first", text="first", address=("127.0.0.1", 27020))
    second = InboundDatagram(data=b"second", text="second", address=("127.0.0.1", 27020))

    server.queue.put_nowait(first)
    server.queue.put_nowait(second)

    assert server.queue.maxsize == 1
    assert server.queue.qsize() == 1
    assert queue.dropped_datagrams == 1
    assert "IngressQueueSize is full" in stream.getvalue()

    runtime = HlstatsRuntime(StubAdapter(), server, logger, build_dispatcher(), StubStorage())
    assert runtime.metrics.snapshot()["ingress_datagrams_dropped"] == 1
    runtime.log_metrics_summary("ingress overload")
    assert "ingress_datagrams_dropped=1" in stream.getvalue()


async def _run_stop_closes_ingress_then_drains_queued_packets() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)
    server.queue.put_nowait(
        InboundDatagram(
            data=(
                b'PROXY Key=secret 127.0.0.1:27015PROXY '
                b'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                b'address "1.2.3.4:27005"'
            ),
            text=(
                'PROXY Key=secret 127.0.0.1:27015PROXY '
                'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                'address "1.2.3.4:27005"'
            ),
            address=("127.0.0.1", 27020),
        )
    )

    await runtime.stop()

    assert [event.event_code for event in storage.recorded] == ["connect"]
    assert storage.online_event_calls == ["begin", "commit"]
    assert adapter.closed is True


def test_runtime_stop_closes_ingress_then_drains_queued_packets() -> None:
    asyncio.run(_run_stop_closes_ingress_then_drains_queued_packets())


async def _run_stop_fails_closed_when_consumer_exceeds_drain_deadline() -> None:
    class BlockingStorage(StubStorage):
        def __init__(self) -> None:
            super().__init__()
            self.record_started = threading.Event()
            self.record_thread_ids: list[int] = []

        def record(self, update: object, context: object) -> None:
            self.record_thread_ids.append(threading.get_ident())
            self.record_started.set()
            # This intentionally blocks a synchronous storage call.  The
            # runtime must still reach its failure state from the event loop
            # before this worker-side sleep completes.
            time.sleep(0.25)
            super().record(update, context)

    adapter = StubAdapter()
    storage = BlockingStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(
        adapter,
        server,
        logger,
        build_dispatcher(),
        storage,
        shutdown_drain_timeout_seconds=0.05,
        storage_operation_timeout_seconds=0.02,
    )
    event_loop_thread = threading.get_ident()
    await runtime.start("127.0.0.1", 0)
    server.queue.put_nowait(
        InboundDatagram(
            data=(
                b'PROXY Key=secret 127.0.0.1:27015PROXY '
                b'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                b'address "1.2.3.4:27005"'
            ),
            text=(
                'PROXY Key=secret 127.0.0.1:27015PROXY '
                'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                'address "1.2.3.4:27005"'
            ),
            address=("127.0.0.1", 27020),
        )
    )
    await _wait_for(storage.record_started.is_set, timeout=0.1)
    deadline_started_at = asyncio.get_running_loop().time()
    await _wait_for(runtime.shutdown_requested.is_set, timeout=0.12)
    assert asyncio.get_running_loop().time() - deadline_started_at < 0.12

    with pytest.raises(RuntimeError, match="exceeded 0.02 seconds"):
        await runtime.stop()

    assert runtime.shutdown_requested.is_set()
    assert runtime.requires_hard_termination is True
    assert storage.flush_pending_calls == 0
    assert storage.record_thread_ids and storage.record_thread_ids[0] != event_loop_thread
    assert adapter.closed is False
    # The timed-out operation gets a cancellation signal when its synchronous
    # call returns, so it rolls back instead of starting a later commit.
    await asyncio.sleep(0.3)
    assert storage.online_event_calls == ["begin", "abort"]


def test_runtime_stop_fails_closed_when_consumer_exceeds_drain_deadline() -> None:
    asyncio.run(_run_stop_fails_closed_when_consumer_exceeds_drain_deadline())


def test_online_commit_fence_rejects_deadline_after_post_record_check() -> None:
    class RecordingStorage(StubStorage):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[str] = []
            self.record_completed = False

        def begin_online_event(self) -> None:
            self.calls.append("begin")

        def record(self, update: object, context: object) -> None:
            self.calls.append("record")
            self.record_completed = True

        def commit_online_event(self) -> None:
            self.calls.append("commit")

        def abort_online_event(self) -> None:
            self.calls.append("abort")

    class DeadlineAfterPostRecordCheckFence(runtime_module._StorageOperationFence):
        def __init__(self, storage: RecordingStorage) -> None:
            super().__init__()
            self._storage = storage
            self.deadline_injected = False

        def raise_if_cancelled(self) -> None:
            super().raise_if_cancelled()
            if self._storage.record_completed and not self.deadline_injected:
                # The ordinary post-record check above has already passed.  A
                # deadline now wins before the fence's atomic commit admission.
                self.deadline_injected = True
                self.cancel()

    adapter = StubAdapter()
    storage = RecordingStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()
    server = runtime._servers.get("127.0.0.1:27015")
    assert server is not None
    prepared = runtime._prepare_event_payload(
        payload=(
            'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
            'address "1.2.3.4:27005"'
        ),
        server=server,
        source_label="127.0.0.1:27015",
    )
    assert prepared is not None
    event, transition, context, update, _ = prepared
    operation_fence = DeadlineAfterPostRecordCheckFence(storage)
    # Unit-test the worker-only path with this test thread as its owner.
    runtime._storage_owner_thread_id = threading.get_ident()
    runtime._storage_access_mode = "online"

    try:
        with pytest.raises(RuntimeError, match="cancelled before online event commit"):
            runtime._persist_online_event(
                transition=transition,
                event=event,
                context=context,
                update=update,
                operation_fence=operation_fence,
            )
    finally:
        runtime._shutdown_storage_executor()

    assert operation_fence.deadline_injected is True
    assert storage.calls == ["begin", "record", "abort"]


async def _run_direct_storage_helpers_from_second_thread_are_rejected_while_online() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)

    reload_fetch_count = adapter.fetch_servers_calls
    reset_count = storage.reset_calls
    errors: list[Exception] = []

    def mutate_from_second_thread() -> None:
        for helper in (
            runtime._reload_state,
            lambda: runtime.process_stdin_line(
                'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                'address "1.2.3.4:27005"',
                "127.0.0.1:27015",
            ),
            runtime.finalize_stdin_import,
        ):
            try:
                helper()
            except Exception as exc:
                errors.append(exc)

    try:
        second_thread = threading.Thread(target=mutate_from_second_thread)
        second_thread.start()
        second_thread.join(timeout=1.0)

        assert second_thread.is_alive() is False
        assert len(errors) == 3
        assert all(isinstance(error, RuntimeError) for error in errors)
        assert all("HLstats storage executor thread" in str(error) for error in errors)
        assert adapter.fetch_servers_calls == reload_fetch_count
        assert storage.reset_calls == reset_count
        assert storage.recorded == []
        assert storage.finalize_calls == 0
    finally:
        await runtime.stop()


def test_direct_storage_helpers_from_second_thread_are_rejected_while_online() -> None:
    asyncio.run(_run_direct_storage_helpers_from_second_thread_are_rejected_while_online())


async def _run_stdin_lifecycle_and_async_finalization_share_storage_owner() -> None:
    class ThreadRecordingStorage(StubStorage):
        def __init__(self) -> None:
            super().__init__()
            self.stdin_calls: list[tuple[str, int]] = []

        def begin_stdin_batch(self, *, transaction_batch_size: int) -> None:
            assert transaction_batch_size == 17
            self.stdin_calls.append(("begin", threading.get_ident()))

        def finalize_import(self) -> None:
            self.stdin_calls.append(("finalize", threading.get_ident()))

        def end_stdin_batch(self) -> None:
            self.stdin_calls.append(("end", threading.get_ident()))

        def abort_stdin_batch(self) -> None:
            self.stdin_calls.append(("abort", threading.get_ident()))

    adapter = StubAdapter()
    storage = ThreadRecordingStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)

    await runtime.start_stdin_import(transaction_batch_size=17)
    owner_thread = runtime._storage_owner_thread_id
    assert owner_thread is not None
    assert owner_thread != threading.get_ident()

    direct_errors: list[Exception] = []

    def direct_finalization_from_second_thread() -> None:
        try:
            runtime.finalize_stdin_import()
        except Exception as exc:
            direct_errors.append(exc)

    second_thread = threading.Thread(target=direct_finalization_from_second_thread)
    second_thread.start()
    second_thread.join(timeout=1.0)

    assert second_thread.is_alive() is False
    assert len(direct_errors) == 1
    assert "HLstats storage executor thread" in str(direct_errors[0])

    await runtime.finalize_stdin_import_async()
    await runtime.finish_stdin_import()

    assert [name for name, _ in storage.stdin_calls] == ["begin", "finalize", "end"]
    assert {thread_id for _, thread_id in storage.stdin_calls} == {owner_thread}
    assert adapter.closed is True


def test_stdin_lifecycle_and_async_finalization_share_storage_owner() -> None:
    asyncio.run(_run_stdin_lifecycle_and_async_finalization_share_storage_owner())


async def _run_storage_failure_aborts_event_and_stops_consumer() -> None:
    class FailingStorage(StubStorage):
        def record(self, update: object, context: object) -> None:
            raise RuntimeError("synthetic event write failure")

    adapter = StubAdapter()
    storage = FailingStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)
    server.queue.put_nowait(
        InboundDatagram(
            data=(
                b'PROXY Key=secret 127.0.0.1:27015PROXY '
                b'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                b'address "1.2.3.4:27005"'
            ),
            text=(
                'PROXY Key=secret 127.0.0.1:27015PROXY '
                'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                'address "1.2.3.4:27005"'
            ),
            address=("127.0.0.1", 27020),
        )
    )
    await _wait_for(runtime.shutdown_requested.is_set)

    with pytest.raises(RuntimeError, match="synthetic event write failure"):
        await runtime.stop()

    assert storage.online_event_calls == ["begin", "abort"]
    assert storage.flush_pending_calls == 0
    assert adapter.closed is True


def test_runtime_storage_failure_aborts_event_and_stops_consumer() -> None:
    asyncio.run(_run_storage_failure_aborts_event_and_stops_consumer())


def test_runtime_handles_control_commands_and_reload() -> None:
    asyncio.run(_run_handles_control_commands_and_reload())


async def _run_reload_flush_failure_keeps_existing_state() -> None:
    class FailingFlushStorage(StubStorage):
        def flush_pending(self) -> None:
            self.flush_pending_calls += 1
            raise RuntimeError("synthetic reload flush failure")

    adapter = StubAdapter()
    storage = FailingFlushStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    server = ProxyUdpServer(logger)
    runtime = HlstatsRuntime(adapter, server, logger, build_dispatcher(), storage)
    await runtime.start("127.0.0.1", 0)
    old_server_list = runtime._servers.format_server_list()

    response = await runtime._handle_control_command("RELOAD", "127.0.0.1", 27020)

    assert response == "FAILED CONTROL COMMAND: RELOAD"
    assert runtime.shutdown_requested.is_set()
    assert storage.reset_calls == 1
    assert adapter.fetch_servers_calls == 1
    assert runtime._servers.format_server_list() == old_server_list
    with pytest.raises(RuntimeError, match="synthetic reload flush failure"):
        await runtime.stop()


def test_runtime_reload_flush_failure_keeps_existing_state() -> None:
    asyncio.run(_run_reload_flush_failure_keeps_existing_state())


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


def test_runtime_killlocation_is_server_scoped_and_one_shot() -> None:
    adapter = StubAdapter()
    adapter.server_batches[0].append(
        GameServer(
            server_id=8,
            address="127.0.0.2",
            port=27015,
            name="Inferno",
            game="csgo",
            current_map="de_inferno",
        )
    )
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: World triggered "killlocation" '
        '(attacker_position "10 20 30") (victim_position "40 50 60")',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:01: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"',
        "127.0.0.2:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:02: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:03: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"',
        "127.0.0.1:27015",
    )

    kill_properties = [
        update.attributes["properties"]
        for update in storage.updates
        if getattr(update, "event_code", None) == "ak47"
    ]
    assert "attacker_position" not in kill_properties[0]
    assert kill_properties[1]["attacker_position"] == "10 20 30"
    assert kill_properties[1]["victim_position"] == "40 50 60"
    assert "attacker_position" not in kill_properties[2]
    assert runtime._servers.get("127.0.0.1:27015").state.pending_kill_attacker is None


def test_runtime_inline_positions_override_staged_killlocation() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: World triggered "killlocation" '
        '(attacker_position "10 20 30") (victim_position "40 50 60")',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:01: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" '
        '(attacker_position "70 80 90")',
        "127.0.0.1:27015",
    )

    properties = storage.updates[-1].attributes["properties"]
    assert properties["attacker_position"] == "70 80 90"
    assert properties["victim_position"] == "40 50 60"


def test_runtime_source_boundary_clears_staged_killlocation() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:00: World triggered "killlocation" '
        '(attacker_position "10 20 30") (victim_position "40 50 60")',
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        "L 01/02/2024 - 03:00:01: Log file started",
        "127.0.0.1:27015",
    )
    runtime.process_stdin_line(
        'L 01/02/2024 - 03:00:02: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"',
        "127.0.0.1:27015",
    )

    properties = storage.updates[-1].attributes["properties"]
    assert "attacker_position" not in properties
    assert "victim_position" not in properties


def test_runtime_marks_only_exact_log_file_started_boundary() -> None:
    adapter = StubAdapter()
    storage = StubStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)
    adapter.connect()
    runtime._reload_state()

    runtime.process_stdin_line("L 01/02/2024 - 03:00:00: Log file started", "127.0.0.1:27015")
    runtime.process_stdin_line("L 01/02/2024 - 03:00:01: Log file started elsewhere", "127.0.0.1:27015")

    assert storage.source_log_boundaries == [7]
    assert storage.online_event_calls == ["boundary", "begin", "commit", "begin", "commit"]


async def _run_async_source_log_boundary_uses_storage_executor() -> None:
    class ThreadRecordingStorage(StubStorage):
        def __init__(self) -> None:
            super().__init__()
            self.boundary_threads: list[int] = []

        def mark_source_log_boundary(self, server_id: int) -> None:
            self.boundary_threads.append(threading.get_ident())
            super().mark_source_log_boundary(server_id)

    adapter = StubAdapter()
    storage = ThreadRecordingStorage()
    logger = ProxyLogger(LoggerConfig(stream=StringIO()))
    runtime = HlstatsRuntime(adapter, ProxyUdpServer(logger), logger, build_dispatcher(), storage)
    event_loop_thread = threading.get_ident()

    await runtime.start("127.0.0.1", 0)
    try:
        owner_thread = runtime._storage_owner_thread_id
        assert owner_thread is not None
        assert owner_thread != event_loop_thread

        await runtime.process_stdin_line_async(
            "L 01/02/2024 - 03:00:00: Log file started",
            "127.0.0.1:27015",
        )

        assert storage.source_log_boundaries == [7]
        assert storage.boundary_threads == [owner_thread]
        assert storage.online_event_calls == ["boundary", "begin", "commit"]
    finally:
        await runtime.stop()


def test_async_source_log_boundary_uses_storage_executor() -> None:
    asyncio.run(_run_async_source_log_boundary_uses_storage_executor())


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

    assert asyncio.run(runtime._handle_control_command("HEARTBEAT", "127.0.0.1", 12345)) == "Heartbeat OK"
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


def test_sync_database_adapter_always_supplies_finite_write_timeout() -> None:
    captured: dict[str, object] = {}

    class Connection:
        def autocommit(self, value: bool) -> None:
            pass

    def connector(**params: object) -> Connection:
        captured.update(params)
        return Connection()

    source_path = Path(__file__).resolve().parents[2] / "hlx_core" / "db.py"
    workspace_db = _load_workspace_module("workspace_hlx_core_db", source_path)

    adapter = workspace_db.SyncDatabaseAdapter(
        workspace_db.DatabaseConfig(
            host="127.0.0.1",
            port=3306,
            username="hlstats",
            password="secret",
            database="hlstats",
        ),
        connector=connector,
    )

    adapter.connect()

    assert captured["connect_timeout"] == 5
    assert captured["read_timeout"] == 5
    assert captured["write_timeout"] == 5


def test_workspace_config_uses_distinct_ingress_queue_size(tmp_path) -> None:
    source_path = Path(__file__).resolve().parents[2] / "hlx_core" / "config.py"
    workspace_config = _load_workspace_module("workspace_hlx_core_config", source_path)
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "EventQueueSize 77",
                "IngressQueueSize 2",
            ]
        ),
        encoding="utf-8",
    )

    loaded = workspace_config.load_config(config_path)

    assert loaded.event_queue_size == 77
    assert loaded.ingress_queue_size == 2


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


def test_serve_stdin_failure_aborts_batch_without_ending(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    calls: list[str] = []

    class RecordingAdapter:
        def __init__(self, config, **kwargs) -> None:
            self.closed = False

        def connect(self) -> None:
            calls.append("connect")

        def close(self) -> None:
            calls.append("close")

    class RecordingStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, transaction_batch_size: int) -> None:
            calls.append("begin")

        def end_stdin_batch(self) -> None:
            calls.append("end")

        def abort_stdin_batch(self) -> None:
            calls.append("abort")

        def reset_runtime_state(self) -> None:
            pass

    class FailingRuntime:
        def __init__(self, adapter, transport, logger, dispatcher, storage, **kwargs) -> None:
            self._adapter = adapter
            self._storage = storage

        async def start_stdin_import(self, *, transaction_batch_size: int) -> None:
            self._adapter.connect()
            self._storage.begin_stdin_batch(transaction_batch_size)

        async def process_stdin_line_async(self, line: str, server_address: str) -> None:
            raise RuntimeError("synthetic processing failure")

        async def finalize_stdin_import_async(self) -> None:
            calls.append("finalize")

        async def finish_stdin_import(self) -> None:
            self._storage.end_stdin_batch()
            self._adapter.close()

        async def abort_stdin_import(self) -> None:
            self._storage.abort_stdin_batch()
            self._adapter.close()

        def log_metrics_summary(self, reason: str) -> None:
            pass

    monkeypatch.setattr(runtime_module, "SyncDatabaseAdapter", RecordingAdapter)
    monkeypatch.setattr(runtime_module, "EventStorage", RecordingStorage)
    monkeypatch.setattr(runtime_module, "HlstatsRuntime", FailingRuntime)
    monkeypatch.setattr(runtime_module.sys, "stdin", type("Stdin", (), {"buffer": BytesIO(b"line\n")})())

    result = asyncio.run(
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

    assert result == 2
    assert calls == ["connect", "begin", "abort", "close"]


def test_serve_returns_nonzero_after_fatal_online_flush_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 127.0.0.1",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )

    class FailingRuntime:
        def __init__(self, *args, **kwargs) -> None:
            self.shutdown_requested = asyncio.Event()

        async def start(self, host: str | None, port: int) -> None:
            self.shutdown_requested.set()

        async def stop(self) -> None:
            raise RuntimeError("synthetic final flush failure")

    monkeypatch.setattr(runtime_module, "HlstatsRuntime", FailingRuntime)

    result = asyncio.run(runtime_module._serve(["--configfile", str(config_path)]))

    assert result == 2


def test_main_hard_exits_after_uninterruptible_storage_deadline() -> None:
    """A live executor thread must not make the CLI wait for interpreter exit."""

    child_script = textwrap.dedent(
        """
        import time
        import types

        import hlstats_py.runtime as runtime


        class Logger:
            def notice(self, message):
                pass

            def e403(self, message):
                pass

            def control(self, message):
                pass


        class Adapter:
            def __init__(self, *args, **kwargs):
                pass

            def connect(self):
                pass

            def close(self):
                pass

            def fetch_proxy_key(self):
                return "secret"

            def fetch_servers(self):
                return [
                    runtime.GameServer(
                        server_id=7,
                        address="127.0.0.1",
                        port=27015,
                        name="Dust",
                        game="csgo",
                        current_map="de_dust2",
                    )
                ]


        class Storage:
            def __init__(self, *args, **kwargs):
                pass

            def reset_runtime_state(self):
                pass

            def begin_online_event(self):
                pass

            def record(self, update, context):
                # Simulate a DB-API syscall that ignores the configured timeout.
                time.sleep(10)

            def commit_online_event(self):
                raise AssertionError("commit must not run after the deadline")

            def abort_online_event(self):
                pass

            def apply_server_map_transition(self, *args):
                pass

            def flush_pending(self):
                pass


        class Transport:
            def __init__(self, logger, *, queue_factory=None):
                self._queue = queue_factory()

            @property
            def queue(self):
                return self._queue

            @property
            def address(self):
                return ("127.0.0.1", 27020)

            async def start(self, host, port):
                payload = (
                    'PROXY Key=secret 127.0.0.1:27015PROXY '
                    'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, '
                    'address "1.2.3.4:27005"'
                )
                self._queue.put_nowait(
                    runtime.InboundDatagram(
                        data=payload.encode("utf-8"),
                        text=payload,
                        address=("127.0.0.1", 27020),
                    )
                )

            async def stop(self):
                pass

            def send_text(self, message, address):
                pass


        BaseRuntime = runtime.HlstatsRuntime


        class FastRuntime(BaseRuntime):
            def __init__(self, *args, **kwargs):
                kwargs["storage_operation_timeout_seconds"] = 0.05
                kwargs["shutdown_drain_timeout_seconds"] = 0.05
                super().__init__(*args, **kwargs)


        settings = types.SimpleNamespace(
            config=types.SimpleNamespace(ingress_queue_size=1),
            stdin=False,
            log_level=0,
            parser_backend="python",
            stdin_verbose_events=False,
            bind_ip="127.0.0.1",
            port=27020,
        )
        runtime.load_settings = lambda argv: settings
        runtime.database_config_from_proxy_config = lambda config: object()
        runtime.SyncDatabaseAdapter = Adapter
        runtime.LoggerConfig = lambda **kwargs: object()
        runtime.ProxyLogger = lambda config: Logger()
        runtime.ProxyUdpServer = Transport
        runtime.EventStorage = Storage
        runtime.HlstatsRuntime = FastRuntime

        raise SystemExit(runtime.main(["--configfile", "unused"]))
        """
    )
    project_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    scripts_path = str(project_root / "scripts")
    environment["PYTHONPATH"] = (
        scripts_path
        if not existing_pythonpath
        else f"{scripts_path}{os.pathsep}{existing_pythonpath}"
    )

    started_at = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-c", child_script],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )
    elapsed = time.monotonic() - started_at

    assert completed.returncode == runtime_module._HARD_TERMINATION_EXIT_CODE
    assert elapsed < 2.0
    assert "forcing immediate non-success process exit" in completed.stderr


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
