"""Runnable UDP worker that replaces the legacy ``hlstats.pl`` process."""

from __future__ import annotations

import asyncio
import contextlib
import sys
import signal
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from datetime import datetime
from typing import Literal, Protocol

from proxy_daemon_py.bootstrap import database_config_from_proxy_config
from proxy_daemon_py.db import GameServer, SyncDatabaseAdapter
from proxy_daemon_py.log import LoggerConfig, ProxyLogger
from proxy_daemon_py.transport import InboundDatagram, ProxyUdpServer

from . import (
    ChatEventHandler,
    ConnectEventHandler,
    DisconnectEventHandler,
    EntryEventHandler,
    EventContext,
    EventDispatcher,
    EventStorage,
    GenericEventHandler,
    KillEventHandler,
    TeamEventHandler,
    TeamTriggerEventHandler,
    TriggerEventHandler,
    WorldEventHandler,
    parse_control_command,
    parse_log_event,
    parse_proxy_envelope,
)
from .cli import load_settings
from .goldsrc_physical_lines import iter_merged_goldsrc_physical_lines


class SupportsWorkerAdapter(Protocol):
    """Protocol implemented by the synchronous database adapter used by the worker."""

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def fetch_proxy_key(self) -> str: ...

    def fetch_servers(self) -> list[GameServer]: ...


class SupportsEventStorage(Protocol):
    """Protocol implemented by persistence backends used in tests and runtime."""

    def record(self, update: object, context: EventContext) -> None: ...

    def reset_runtime_state(self) -> None: ...

    def finalize_import(self) -> None: ...

    def apply_server_map_transition(
        self, server_id: int, phase: str, map_name: str, event_timestamp: datetime
    ) -> None: ...


@dataclass(slots=True)
class RuntimeMapState:
    """Projected map lifecycle state for a server."""

    current_map: str
    map_lifecycle: str = "active"
    pending_map: str = ""

    def apply_started(self, map_name: str) -> None:
        self.current_map = map_name
        self.pending_map = ""
        self.map_lifecycle = "started"

    def apply_loading(self, map_name: str) -> None:
        self.pending_map = map_name
        if not self.current_map:
            self.current_map = map_name
        self.map_lifecycle = "loading"


@dataclass(slots=True)
class TrackedServer:
    """Server metadata cached by the worker for fast event context lookup."""

    server_id: int
    address: str
    port: int
    name: str
    game: str
    state: RuntimeMapState

    @property
    def address_key(self) -> str:
        return f"{self.address}:{self.port}".strip().lower()

    @property
    def current_map(self) -> str:
        return self.state.current_map

    @current_map.setter
    def current_map(self, value: str) -> None:
        self.state.current_map = value

    @property
    def map_lifecycle(self) -> str:
        return self.state.map_lifecycle

    @map_lifecycle.setter
    def map_lifecycle(self, value: str) -> None:
        self.state.map_lifecycle = value

    @property
    def pending_map(self) -> str:
        return self.state.pending_map

    @pending_map.setter
    def pending_map(self, value: str) -> None:
        self.state.pending_map = value


class ServerRegistry:
    """In-memory lookup of tracked servers keyed by ``address:port``."""

    def __init__(self) -> None:
        self._servers: Mapping[str, TrackedServer] = MappingProxyType({})

    def replace(self, servers: Sequence[GameServer]) -> None:
        mapped = {
            f"{server.address}:{server.port}".strip().lower(): TrackedServer(
                server_id=server.server_id,
                address=server.address,
                port=server.port,
                name=server.name,
                game=server.game,
                state=RuntimeMapState(current_map=server.current_map or ""),
            )
            for server in servers
        }
        self._servers = MappingProxyType(mapped)

    def get(self, address: str | None) -> TrackedServer | None:
        if not address:
            return None
        return self._servers.get(address.strip().lower())

    def format_server_list(self) -> str:
        if not self._servers:
            return "ServerList\n"
        lines = [
            f"{server.address}:{server.port} -> {server.name} [{server.game}]"
            for server in sorted(self._servers.values(), key=lambda item: (item.address, item.port))
        ]
        return "ServerList\n" + "\n".join(lines) + "\n"


_LOADING_MAP_INLINE_RE = re.compile(r'Loading map "(?P<map>[^"]+)"')
_STARTED_MAP_INLINE_RE = re.compile(r'Started map "(?P<map>[^"]+)"')
_STDIN_PROGRESS_EVERY = 10000

MapLifecyclePhase = Literal["loading", "started"]


def _last_regex_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None


def apply_map_lifecycle_message(
    server: TrackedServer, message: str | None
) -> tuple[MapLifecyclePhase, str] | None:
    """Update *server* map fields when *message* contains GoldSrc map lifecycle text.

    ``Started map`` is preferred over ``Loading map`` when both appear (same line).
    Matches a substring so lines like ``Started map "de_nuke" (CRC "...")`` are recognized.
    During ``loading`` we keep ``current_map`` unchanged and only stage the
    candidate map in ``pending_map``; attribution switches on ``started``.
    """

    if not message:
        return None
    started = _last_regex_match(_STARTED_MAP_INLINE_RE, message)
    if started:
        name = started.group("map")
        server.state.apply_started(name)
        return ("started", name)
    loading = _last_regex_match(_LOADING_MAP_INLINE_RE, message)
    if loading:
        name = loading.group("map")
        server.state.apply_loading(name)
        return ("loading", name)
    return None


def build_dispatcher() -> EventDispatcher:
    """Return the default event dispatcher used by the worker runtime."""

    generic = GenericEventHandler()
    return EventDispatcher(
        [
            KillEventHandler(),
            TriggerEventHandler(),
            ChatEventHandler(),
            TeamEventHandler(),
            ConnectEventHandler(),
            EntryEventHandler(),
            DisconnectEventHandler(),
            TeamTriggerEventHandler(),
            WorldEventHandler(),
        ],
        fallback=generic,
    )


class HlstatsRuntime:
    """Async UDP worker that consumes proxied log envelopes and writes events to MySQL."""

    def __init__(
        self,
        adapter: SupportsWorkerAdapter,
        udp_server: ProxyUdpServer,
        logger: ProxyLogger,
        dispatcher: EventDispatcher,
        storage: SupportsEventStorage,
        *,
        parser_backend: str = "python",
        stdin_verbose_events: bool = False,
    ) -> None:
        self._adapter = adapter
        self._udp_server = udp_server
        self._logger = logger
        self._dispatcher = dispatcher
        self._storage = storage
        self._parser_backend = parser_backend
        self._stdin_verbose_events = stdin_verbose_events
        self._proxy_key = ""
        self._servers = ServerRegistry()
        self._consumer_task: asyncio.Task[None] | None = None
        self._shutdown_requested = asyncio.Event()

    @property
    def shutdown_requested(self) -> asyncio.Event:
        return self._shutdown_requested

    async def start(self, host: str | None, port: int) -> None:
        """Connect to MySQL, load server state, and start the UDP listener."""

        self._adapter.connect()
        self._reload_state()
        await self._udp_server.start(host, port)
        bound_address = self._udp_server.address
        if bound_address is None:
            bind_host = host or "0.0.0.0"
            self._logger.notice(f"HLstats worker listening on {bind_host}:{port}")
        else:
            self._logger.notice(f"HLstats worker listening on {bound_address[0]}:{bound_address[1]}")
        self._consumer_task = asyncio.create_task(self._consume_datagrams())

    async def stop(self) -> None:
        """Stop the UDP listener and close the database connection."""

        if self._consumer_task is not None:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
            self._consumer_task = None
        await self._udp_server.stop()
        self._adapter.close()
        self._logger.notice("HLstats worker stopped")

    def request_shutdown(self) -> None:
        """Signal that the main loop should exit."""

        self._shutdown_requested.set()

    async def _consume_datagrams(self) -> None:
        while True:
            datagram = await self._udp_server.queue.get()
            try:
                await self._handle_datagram(datagram)
            except Exception as exc:  # pragma: no cover - defensive safety
                self._logger.e403(f"Failed to process datagram: {exc}")
            finally:
                self._udp_server.queue.task_done()

    async def _handle_datagram(self, datagram: InboundDatagram) -> None:
        payload = datagram.text.strip()
        host, port = datagram.address

        if self._is_local_control_host(host):
            command = parse_control_command(payload)
            if command is not None:
                response = self._handle_control_command(command.raw, host, port)
                if response is not None:
                    self._udp_server.send_text(response, datagram.address)
                return

        try:
            envelope = parse_proxy_envelope(payload)
        except ValueError:
            self._logger.control(f"Ignoring non-proxied payload from {host}:{port}")
            return

        if envelope.proxy_key != self._proxy_key:
            self._logger.e403(f"Proxy key mismatch from {host}:{port}; dropping packet")
            return

        control = parse_control_command(envelope.payload.strip())
        if control is not None:
            response = self._handle_control_command(control.raw, host, port)
            if response is not None:
                self._udp_server.send_text(response, datagram.address)
            return

        server = self._servers.get(envelope.server_address)
        if server is None:
            self._logger.e403(
                f"Unknown source server '{envelope.server_address or '<missing>'}'; dropping packet"
            )
            return

        self._process_event_payload(
            payload=envelope.payload,
            server=server,
            source_label=f"{server.address}:{server.port}",
        )

    def _handle_control_command(self, command: str, host: str, port: int) -> str | None:
        normalized = command.strip().strip(";").upper()
        self._logger.control(f"Command received from {host}:{port}: {normalized}")

        if normalized == "HEARTBEAT":
            self._logger.control(f"Send heartbeat status to frontend at '{host}:{port}'")
            return "Heartbeat OK"
        if normalized == "SERVERLIST":
            return self._servers.format_server_list()
        if normalized == "RELOAD":
            self._reload_state()
            return "OK, EXECUTING COMMAND: RELOAD"
        if normalized == "KILL":
            self.request_shutdown()
            return "OK, EXECUTING COMMAND: KILL"
        return None

    def _reload_state(self) -> None:
        self._proxy_key = self._adapter.fetch_proxy_key()
        self._servers.replace(self._adapter.fetch_servers())
        self._storage.reset_runtime_state()
        self._logger.control(
            f"Reloaded worker configuration: {len(self._servers.format_server_list().splitlines()) - 1} servers"
        )

    @staticmethod
    def _is_local_control_host(host: str) -> bool:
        return host in {"127.0.0.1", "::1", "localhost"}

    def process_stdin_line(self, line: str, server_address: str) -> None:
        """Handle one raw legacy log line associated with *server_address*."""

        server = self._servers.get(server_address)
        if server is None:
            self._logger.e403(f"Unknown source server '{server_address}'; dropping stdin line")
            return
        self._process_event_payload(payload=line, server=server, source_label=server_address)

    def finalize_stdin_import(self) -> None:
        """Flush import-tail metadata after a finite stdin replay."""

        self._storage.finalize_import()

    def _process_event_payload(self, *, payload: str, server: TrackedServer, source_label: str) -> None:
        event = parse_log_event(
            payload,
            backend=self._parser_backend,
            server_address=source_label,
        )
        transition = apply_map_lifecycle_message(server, event.message)
        if transition is not None:
            phase, map_name = transition
            self._storage.apply_server_map_transition(
                server.server_id, phase, map_name, event.timestamp
            )
        context = EventContext(
            server_id=server.server_id,
            game=server.game,
            extras=MappingProxyType({"map": server.current_map or ""}),
        )
        update = self._dispatcher.dispatch(event, context)
        self._storage.record(update, context)
        if self._stdin_verbose_events:
            self._logger.notice(
                f"Recorded {update.category.value} event '{update.event_code}' for {source_label}"
            )

async def _serve(argv: Sequence[str] | None = None) -> int:
    try:
        settings = load_settings(argv)
    except Exception as exc:  # pragma: no cover - defensive configuration path
        print(f"error: {exc}")
        return 1

    database = SyncDatabaseAdapter(database_config_from_proxy_config(settings.config))
    logger = ProxyLogger(LoggerConfig(level=settings.log_level))
    transport = ProxyUdpServer(logger)
    dispatcher = build_dispatcher()
    storage = EventStorage(
        database,
        use_event_timestamps_for_processing=settings.stdin,
    )
    runtime = HlstatsRuntime(
        database,
        transport,
        logger,
        dispatcher,
        storage,
        parser_backend=settings.parser_backend,
        stdin_verbose_events=settings.stdin_verbose_events,
    )

    loop = asyncio.get_running_loop()
    signal_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, signal_event.set)

    if settings.stdin:
        try:
            runtime._adapter.connect()
            runtime._reload_state()
            storage.begin_stdin_batch(transaction_batch_size=settings.stdin_transaction_batch_size)
            logger.notice("UDP listen socket disabled, reading log data from STDIN.")
            logger.notice(
                f"All data from STDIN will be allocated to server '{settings.server_ip}:{settings.server_port}'."
            )
            record_count = 0
            server_address = f"{settings.server_ip}:{settings.server_port}".strip().lower()
            for merged in iter_merged_goldsrc_physical_lines(sys.stdin.buffer):
                line = merged.decode("utf-8", errors="replace")
                if not line:
                    continue
                runtime.process_stdin_line(line, server_address)
                record_count += 1
                if not settings.stdin_verbose_events and record_count % _STDIN_PROGRESS_EVERY == 0:
                    logger.notice(f"STDIN import progress: {record_count} records processed")
            runtime.finalize_stdin_import()
            storage.end_stdin_batch()
            logger.notice(f"Import of log file complete. Scanned {record_count} log records.")
            runtime._adapter.close()
            return 0
        except Exception as exc:  # pragma: no cover - defensive startup logging
            logger.e403(f"Failed to run HLstats worker stdin import: {exc}")
            with contextlib.suppress(Exception):
                storage.end_stdin_batch()
            with contextlib.suppress(Exception):
                runtime._adapter.close()
            return 2

    try:
        await runtime.start(settings.bind_ip, settings.port)
    except Exception as exc:  # pragma: no cover - defensive startup logging
        logger.e403(f"Failed to start HLstats worker: {exc}")
        return 2

    signal_task = asyncio.create_task(signal_event.wait())
    shutdown_task = asyncio.create_task(runtime.shutdown_requested.wait())
    done, pending = await asyncio.wait(
        {signal_task, shutdown_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    for task in done:
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await runtime.stop()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m hlstats_py.runtime``."""

    return asyncio.run(_serve(argv))


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
