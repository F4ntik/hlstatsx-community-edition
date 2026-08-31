"""Runnable UDP worker that replaces the legacy ``hlstats.pl`` process."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Literal, Protocol

from hlx_core.bootstrap import database_config_from_proxy_config
from hlx_core.db import GameServer, SyncDatabaseAdapter
from hlx_core.log import LoggerConfig, ProxyLogger
from hlx_core.transport import InboundDatagram, ProxyUdpServer

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
from .protocol import (
    ControlCommand,
    ControlCommandType,
    LogEvent,
    LogEventType,
    _parse_position_triplet,
)


class SupportsWorkerAdapter(Protocol):
    """Protocol implemented by the synchronous database adapter used by the worker."""

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def fetch_proxy_key(self) -> str: ...

    def fetch_servers(self) -> list[GameServer]: ...


class SupportsEventStorage(Protocol):
    """Protocol implemented by persistence backends used in tests and runtime."""

    def begin_online_event(self) -> None: ...

    def commit_online_event(self) -> None: ...

    def abort_online_event(self) -> None: ...

    def record(self, update: object, context: EventContext) -> None: ...

    def reset_runtime_state(self) -> None: ...

    def finalize_import(self) -> None: ...

    def begin_stdin_batch(self, *, transaction_batch_size: int) -> None: ...

    def end_stdin_batch(self) -> None: ...

    def abort_stdin_batch(self) -> None: ...

    def apply_server_map_transition(
        self, server_id: int, phase: str, map_name: str, event_timestamp: datetime
    ) -> None: ...

    def flush_pending(self) -> None: ...

    def mark_source_log_boundary(self, server_id: int) -> None: ...


class _HardTerminationRequired(RuntimeError):
    """Signal that the executable must abandon an uninterruptible DB worker."""


class _StorageOperationFence:
    """Atomically arbitrate an operation deadline against online commit admission.

    The fence's commit-admission state is the linearization point: a deadline
    that cancels first prevents the commit call entirely, while an already
    admitted commit is never retried or rolled back by a later deadline.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._online_commit_admitted = False

    def cancel(self) -> bool:
        """Try to make deadline cancellation win without blocking on DB I/O."""

        with self._lock:
            if self._online_commit_admitted:
                return False
            self._cancelled = True
            return True

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise RuntimeError("HLstats storage operation cancelled after its deadline")

    def admit_online_commit(self) -> bool:
        """Atomically admit commit only if cancellation did not win the race."""

        with self._lock:
            if self._cancelled:
                return False
            self._online_commit_admitted = True
            return True


_EMPTY_LOG_RECORD_RE = re.compile(
    r"^\s*L \d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}:\s*$"
)


@dataclass(slots=True)
class RuntimeMapState:
    """Projected map lifecycle state for a server."""

    current_map: str
    map_lifecycle: str = "active"
    pending_map: str = ""
    round_status: int = 0
    pending_kill_attacker: tuple[int, int, int] | None = None
    pending_kill_victim: tuple[int, int, int] | None = None

    def apply_started(self, map_name: str) -> None:
        self.current_map = map_name
        self.pending_map = ""
        self.map_lifecycle = "started"
        self.clear_pending_killlocation()

    def apply_loading(self, map_name: str) -> None:
        self.pending_map = map_name
        if not self.current_map:
            self.current_map = map_name
        self.map_lifecycle = "loading"
        self.clear_pending_killlocation()

    def clear_pending_killlocation(self) -> None:
        self.pending_kill_attacker = None
        self.pending_kill_victim = None


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


@dataclass(slots=True)
class RuntimeMetrics:
    """In-memory runtime counters emitted through structured summary logs."""

    started_at: float = field(default_factory=time.perf_counter)
    events_processed: int = 0
    stdin_records: int = 0
    udp_datagrams: int = 0
    packets_dropped: int = 0
    ingress_datagrams_dropped: int = 0
    flush_attempts: int = 0
    flush_failures: int = 0
    control_commands_total: int = 0
    control_commands_rejected: int = 0
    events_by_category: dict[str, int] = field(default_factory=dict)
    control_commands_by_type: dict[str, int] = field(default_factory=dict)

    def record_event(self, category: str) -> None:
        self.events_processed += 1
        self.events_by_category[category] = self.events_by_category.get(category, 0) + 1

    def record_control(self, command: str, *, rejected: bool = False) -> None:
        normalized = command.strip().strip(";").upper()
        self.control_commands_total += 1
        self.control_commands_by_type[normalized] = self.control_commands_by_type.get(normalized, 0) + 1
        if rejected:
            self.control_commands_rejected += 1

    def record_flush(self, *, failed: bool = False) -> None:
        self.flush_attempts += 1
        if failed:
            self.flush_failures += 1

    def snapshot(self) -> dict[str, object]:
        elapsed = time.perf_counter() - self.started_at
        throughput = self.events_processed / elapsed if elapsed > 0 else 0.0
        return {
            "elapsed_seconds": round(elapsed, 3),
            "events_processed": self.events_processed,
            "events_per_second": round(throughput, 1),
            "stdin_records": self.stdin_records,
            "udp_datagrams": self.udp_datagrams,
            "packets_dropped": self.packets_dropped,
            "ingress_datagrams_dropped": self.ingress_datagrams_dropped,
            "flush_attempts": self.flush_attempts,
            "flush_failures": self.flush_failures,
            "control_commands_total": self.control_commands_total,
            "control_commands_rejected": self.control_commands_rejected,
            "events_by_category": dict(sorted(self.events_by_category.items())),
            "control_commands_by_type": dict(sorted(self.control_commands_by_type.items())),
        }


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


class BoundedIngressQueue(asyncio.Queue[InboundDatagram]):
    """Bounded UDP ingress queue that drops overload without blocking callbacks."""

    def __init__(self, logger: ProxyLogger, *, maxsize: int) -> None:
        if maxsize <= 0:
            raise ValueError("IngressQueueSize must be greater than zero")
        super().__init__(maxsize=maxsize)
        self._logger = logger
        self.dropped_datagrams = 0

    def put_nowait(self, item: InboundDatagram) -> None:
        if not self.full():
            super().put_nowait(item)
            return

        self.dropped_datagrams += 1
        # Avoid a log-amplification path during overload while retaining an
        # operator-visible, exact counter in runtime metrics.
        if self.dropped_datagrams == 1 or self.dropped_datagrams & (self.dropped_datagrams - 1) == 0:
            host, port = item.address
            self._logger.control(
                "Dropping UDP ingress datagram because IngressQueueSize is full: "
                f"source={host}:{port} total_dropped={self.dropped_datagrams}"
            )


_LOADING_MAP_INLINE_RE = re.compile(r'Loading map "(?P<map>[^"]+)"')
_STARTED_MAP_INLINE_RE = re.compile(r'Started map "(?P<map>[^"]+)"')
_STDIN_PROGRESS_EVERY = 10000
# After ingress is closed, allow this bounded grace period for already queued
# packets.  Service embedders may override it with the constructor argument.
_UDP_SHUTDOWN_DRAIN_TIMEOUT_SECONDS = 5.0
# Every synchronous adapter/storage call runs in the one serialized database
# worker.  This is an event-loop deadline; connector read/write timeouts bound
# the underlying driver call itself.
_STORAGE_OPERATION_TIMEOUT_SECONDS = 5.0
_DEFAULT_INGRESS_QUEUE_SIZE = 1000
_HARD_TERMINATION_EXIT_CODE = 70
_MUTATING_CONTROL_COMMANDS = {
    ControlCommandType.RELOAD,
    ControlCommandType.KILL,
}
_ROUND_WIN_ACTIONS = {
    "CTs_Win",
    "Bomb_Defused",
    "Terrorists_Win",
    "Target_Bombed",
    "SFUI_Notice_CTs_Win",
    "SFUI_Notice_Bomb_Defused",
    "SFUI_Notice_Terrorists_Win",
    "SFUI_Notice_Target_Bombed",
}

MapLifecyclePhase = Literal["loading", "started"]


def _format_metric_mapping(value: object) -> str:
    if not isinstance(value, Mapping):
        return "none"
    if not value:
        return "none"
    return ",".join(f"{key}:{value[key]}" for key in sorted(value))


def _configured_ingress_queue_size(config: object) -> int:
    """Read the worker-only ingress bound without reusing EventQueueSize."""

    size = getattr(config, "ingress_queue_size", _DEFAULT_INGRESS_QUEUE_SIZE)
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("IngressQueueSize must be a positive integer")
    return size


def _raise_if_hard_termination_required(runtime: object, cause: Exception) -> None:
    """Escalate only a deadline that can leave a non-daemon DB thread alive."""

    if getattr(runtime, "requires_hard_termination", False):
        raise _HardTerminationRequired(
            "HLstats storage deadline left a synchronous DB operation uninterruptible"
        ) from cause


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
        shutdown_drain_timeout_seconds: float = _UDP_SHUTDOWN_DRAIN_TIMEOUT_SECONDS,
        storage_operation_timeout_seconds: float = _STORAGE_OPERATION_TIMEOUT_SECONDS,
    ) -> None:
        if not isfinite(shutdown_drain_timeout_seconds) or shutdown_drain_timeout_seconds <= 0:
            raise ValueError("shutdown_drain_timeout_seconds must be positive")
        if (
            not isfinite(storage_operation_timeout_seconds)
            or storage_operation_timeout_seconds <= 0
        ):
            raise ValueError("storage_operation_timeout_seconds must be positive")
        self._adapter = adapter
        self._udp_server = udp_server
        self._logger = logger
        self._dispatcher = dispatcher
        self._storage = storage
        self._parser_backend = parser_backend
        self._stdin_verbose_events = stdin_verbose_events
        self._shutdown_drain_timeout_seconds = shutdown_drain_timeout_seconds
        self._storage_operation_timeout_seconds = storage_operation_timeout_seconds
        # The adapter connection and EventStorage are deliberately confined to
        # this single worker.  A generic or multi-worker executor could reorder
        # logical packets or use one DB-API connection from multiple threads.
        self._storage_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hlstats-db")
        self._storage_executor_shutdown = False
        self._storage_unavailable = False
        self._requires_hard_termination = False
        self._storage_inflight: asyncio.Future[object] | None = None
        self._storage_operation_fence: _StorageOperationFence | None = None
        self._storage_owner_thread_id: int | None = None
        self._storage_access_mode: Literal["inactive", "online", "stdin"] = "inactive"
        self._stdin_import_started = False
        self._proxy_key = ""
        self._servers = ServerRegistry()
        self._consumer_task: asyncio.Task[None] | None = None
        self._shutdown_requested = asyncio.Event()
        self._fatal_error: Exception | None = None
        self._metrics = RuntimeMetrics()

    @property
    def shutdown_requested(self) -> asyncio.Event:
        return self._shutdown_requested

    @property
    def metrics(self) -> RuntimeMetrics:
        self._sync_ingress_drop_metrics()
        return self._metrics

    @property
    def requires_hard_termination(self) -> bool:
        """Whether a non-interruptible storage worker may still hold process exit."""

        return self._requires_hard_termination

    async def start(self, host: str | None, port: int) -> None:
        """Connect to MySQL, load server state, and start the UDP listener."""

        # Claim online ownership before the first worker operation so a
        # concurrently running ordinary thread cannot slip a direct sync
        # adapter/storage call into the startup window.
        self._storage_access_mode = "online"
        try:
            await self._run_storage_operation(
                "connect and initial reload",
                self._worker_connect_and_reload,
            )
            await self._udp_server.start(host, port)
        except Exception:
            await self._close_after_failed_start()
            if not self._storage_unavailable:
                self._storage_access_mode = "inactive"
            raise
        bound_address = self._udp_server.address
        if bound_address is None:
            bind_host = host or "0.0.0.0"
            self._logger.notice(f"HLstats worker listening on {bind_host}:{port}")
        else:
            self._logger.notice(f"HLstats worker listening on {bound_address[0]}:{bound_address[1]}")
        self._consumer_task = asyncio.create_task(self._consume_datagrams())

    async def stop(self) -> None:
        """Stop the UDP listener and close the database connection."""

        failure = self._fatal_error
        try:
            await self._udp_server.stop()
        except Exception as exc:  # pragma: no cover - transport safety
            self._fail_closed(exc, "Failed to close HLstats UDP ingress")
            failure = self._fatal_error

        consumer = self._consumer_task
        if consumer is not None:
            if failure is None:
                drain_task = asyncio.create_task(self._udp_server.queue.join())
                try:
                    done, _ = await asyncio.wait(
                        {consumer, drain_task},
                        timeout=self._shutdown_drain_timeout_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        self._fail_closed(
                            RuntimeError(
                                "HLstats UDP queue did not drain within "
                                f"{self._shutdown_drain_timeout_seconds} seconds"
                            ),
                            "Failed to drain HLstats UDP queue",
                        )
                        failure = self._fatal_error
                    elif self._fatal_error is not None:
                        failure = self._fatal_error
                    elif consumer in done and not drain_task.done():
                        if self._fatal_error is None:
                            self._fail_closed(
                                RuntimeError("HLstats UDP consumer stopped before its queue drained"),
                                "Failed to drain HLstats UDP queue",
                            )
                        failure = self._fatal_error
                except Exception as exc:  # pragma: no cover - queue safety
                    self._fail_closed(exc, "Failed to drain HLstats UDP queue")
                    failure = self._fatal_error
                finally:
                    if not drain_task.done():
                        drain_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await drain_task
            if not consumer.done():
                consumer.cancel()
            try:
                await consumer
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pragma: no cover - consumer safety
                self._fail_closed(exc, "HLstats UDP consumer stopped with an error")
                failure = self._fatal_error
            self._consumer_task = None

        try:
            if failure is None:
                await self._flush_pending_async("shutdown flush")
                await self._run_storage_operation("shutdown close", self._worker_close)
            elif not self._storage_unavailable:
                # The failed operation has completed, so closing on the same
                # serialized worker cannot race the adapter connection.  Do
                # not queue a close after a deadline: that would hide a later
                # DB action behind a stalled one.
                await self._run_storage_operation("failed shutdown close", self._worker_close)
        except Exception as exc:
            self._fail_closed(exc, "Failed to close HLstats database adapter")
            failure = self._fatal_error
        finally:
            self._shutdown_storage_executor()
            if not self._storage_unavailable:
                self._storage_access_mode = "inactive"
            self.log_metrics_summary("runtime stop")
            self._logger.notice("HLstats worker stopped")

        if failure is not None:
            raise failure

    def request_shutdown(self) -> None:
        """Signal that the main loop should exit."""

        self._shutdown_requested.set()

    def log_metrics_summary(self, reason: str) -> None:
        """Emit a stable one-line runtime metrics summary for operators and CI logs."""

        self._sync_ingress_drop_metrics()
        snapshot = self._metrics.snapshot()
        self._logger.notice(
            "HLstats metrics: "
            f"reason={reason!r} "
            f"elapsed_seconds={snapshot['elapsed_seconds']} "
            f"events_processed={snapshot['events_processed']} "
            f"events_per_second={snapshot['events_per_second']} "
            f"stdin_records={snapshot['stdin_records']} "
            f"udp_datagrams={snapshot['udp_datagrams']} "
            f"packets_dropped={snapshot['packets_dropped']} "
            f"ingress_datagrams_dropped={snapshot['ingress_datagrams_dropped']} "
            f"flush_attempts={snapshot['flush_attempts']} "
            f"flush_failures={snapshot['flush_failures']} "
            f"control_commands_total={snapshot['control_commands_total']} "
            f"control_commands_rejected={snapshot['control_commands_rejected']} "
            f"events_by_category={_format_metric_mapping(snapshot['events_by_category'])} "
            f"control_commands_by_type={_format_metric_mapping(snapshot['control_commands_by_type'])}"
        )

    def _sync_ingress_drop_metrics(self) -> None:
        dropped = getattr(self._udp_server.queue, "dropped_datagrams", 0)
        if isinstance(dropped, int) and dropped >= 0:
            self._metrics.ingress_datagrams_dropped = dropped

    async def _flush_pending_async(self, operation_name: str) -> None:
        try:
            await self._run_storage_operation(operation_name, self._worker_flush_pending)
        except Exception:
            self._metrics.record_flush(failed=True)
            raise
        else:
            self._metrics.record_flush()

    async def _run_storage_operation(
        self,
        operation_name: str,
        operation: Callable[[_StorageOperationFence], object],
    ) -> object:
        """Run one ordered DB/storage operation without blocking the event loop.

        Cancellation cannot forcibly interrupt arbitrary DB-API code.  The
        shared fence prevents this runtime from starting a later logical phase
        once its caller has crossed the deadline; it atomically arbitrates the
        deadline against online-event commit admission.  Driver timeouts in
        :mod:`hlx_core.db` bound the remaining syscall.
        """

        if self._storage_unavailable:
            raise RuntimeError("HLstats storage is unavailable after an operation deadline")
        if self._storage_executor_shutdown:
            raise RuntimeError("HLstats storage executor is shut down")

        operation_fence = _StorageOperationFence()

        def owned_operation() -> object:
            self._claim_storage_executor_owner()
            return operation(operation_fence)

        future = asyncio.get_running_loop().run_in_executor(
            self._storage_executor,
            owned_operation,
        )
        self._storage_inflight = future
        self._storage_operation_fence = operation_fence

        def clear_inflight(completed: asyncio.Future[object]) -> None:
            if self._storage_inflight is completed:
                self._storage_inflight = None
                self._storage_operation_fence = None
            # A deadline deliberately stops awaiting the worker future.  Mark
            # its eventual cancellation/rollback exception as observed so it
            # does not surface as an unrelated asyncio warning later.
            if self._storage_unavailable and not completed.cancelled():
                with contextlib.suppress(Exception):
                    completed.exception()

        future.add_done_callback(clear_inflight)
        try:
            return await asyncio.wait_for(
                asyncio.shield(future),
                timeout=self._storage_operation_timeout_seconds,
            )
        except TimeoutError as exc:
            operation_fence.cancel()
            self._storage_unavailable = True
            self._requires_hard_termination = True
            timeout_error = RuntimeError(
                "HLstats storage operation "
                f"'{operation_name}' exceeded {self._storage_operation_timeout_seconds} seconds"
            )
            self._fail_closed(timeout_error, "HLstats storage operation timed out")
            raise timeout_error from exc
        except asyncio.CancelledError:
            # A drain deadline cancels the consumer while a synchronous call
            # may still be running.  Tell that worker to abort rather than
            # advance to a later write (for example, commit after record).
            operation_fence.cancel()
            self._storage_unavailable = True
            self._requires_hard_termination = True
            raise

    def _claim_storage_executor_owner(self) -> None:
        current_thread_id = threading.get_ident()
        owner_thread_id = self._storage_owner_thread_id
        if owner_thread_id is None:
            self._storage_owner_thread_id = current_thread_id
            return
        if owner_thread_id != current_thread_id:
            raise RuntimeError("HLstats storage executor changed its owning thread")

    def _require_storage_executor_owner(self, operation_name: str) -> None:
        if self._storage_owner_thread_id != threading.get_ident():
            raise RuntimeError(f"{operation_name} must run on the HLstats storage executor thread")

    @staticmethod
    def _raise_if_storage_operation_cancelled(operation_fence: _StorageOperationFence) -> None:
        operation_fence.raise_if_cancelled()

    def _worker_connect_and_reload(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_connect_and_reload")
        self._raise_if_storage_operation_cancelled(operation_fence)
        self._adapter.connect()
        try:
            self._raise_if_storage_operation_cancelled(operation_fence)
            self._reload_state()
            self._raise_if_storage_operation_cancelled(operation_fence)
        except Exception:
            if operation_fence.is_cancelled():
                with contextlib.suppress(Exception):
                    self._adapter.close()
            raise

    def _worker_flush_pending(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_flush_pending")
        self._raise_if_storage_operation_cancelled(operation_fence)
        self._storage.flush_pending()
        self._raise_if_storage_operation_cancelled(operation_fence)

    def _worker_close(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_close")
        self._raise_if_storage_operation_cancelled(operation_fence)
        self._adapter.close()

    async def start_stdin_import(self, *, transaction_batch_size: int) -> None:
        """Connect and initialize stdin batching on the serialized DB worker."""

        self._storage_access_mode = "stdin"
        try:
            await self._run_storage_operation(
                "stdin connect and initial reload",
                lambda operation_fence: self._worker_start_stdin_import(
                    operation_fence,
                    transaction_batch_size,
                ),
            )
        except Exception:
            if not self._storage_unavailable:
                self._storage_access_mode = "inactive"
            raise

    def _worker_start_stdin_import(
        self,
        operation_fence: _StorageOperationFence,
        transaction_batch_size: int,
    ) -> None:
        self._require_storage_executor_owner("_worker_start_stdin_import")
        self._raise_if_storage_operation_cancelled(operation_fence)
        self._adapter.connect()
        try:
            self._raise_if_storage_operation_cancelled(operation_fence)
            self._reload_state()
            self._raise_if_storage_operation_cancelled(operation_fence)
            self._storage.begin_stdin_batch(transaction_batch_size=transaction_batch_size)
            self._stdin_import_started = True
            self._raise_if_storage_operation_cancelled(operation_fence)
        except Exception:
            if operation_fence.is_cancelled():
                with contextlib.suppress(Exception):
                    self._adapter.close()
            raise

    async def finish_stdin_import(self) -> None:
        """End a successful stdin batch and close its worker-owned adapter."""

        try:
            await self._run_storage_operation(
                "stdin successful close",
                self._worker_finish_stdin_import,
            )
        except Exception:
            if not self._storage_unavailable:
                self._storage_access_mode = "inactive"
            raise
        else:
            self._storage_access_mode = "inactive"
        finally:
            self._shutdown_storage_executor()

    def _worker_finish_stdin_import(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_finish_stdin_import")
        self._raise_if_storage_operation_cancelled(operation_fence)
        try:
            if self._stdin_import_started:
                self._storage.end_stdin_batch()
                self._stdin_import_started = False
        finally:
            self._adapter.close()

    async def abort_stdin_import(self) -> None:
        """Rollback a failed stdin batch unless a deadline already poisoned it."""

        try:
            if not self._storage_unavailable and not self._storage_executor_shutdown:
                await self._run_storage_operation(
                    "stdin failure rollback",
                    self._worker_abort_stdin_import,
                )
        finally:
            self._shutdown_storage_executor()
            if not self._storage_unavailable:
                self._storage_access_mode = "inactive"

    def _worker_abort_stdin_import(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_abort_stdin_import")
        self._raise_if_storage_operation_cancelled(operation_fence)
        try:
            if self._stdin_import_started:
                self._storage.abort_stdin_batch()
                self._stdin_import_started = False
        finally:
            self._adapter.close()

    def _shutdown_storage_executor(self) -> None:
        if self._storage_executor_shutdown:
            return
        self._storage_executor_shutdown = True
        # Do not wait on the event loop.  A deadline-poisoned operation may
        # still be unwinding in the worker; no later operation can be queued.
        self._storage_executor.shutdown(wait=False, cancel_futures=True)

    async def _close_after_failed_start(self) -> None:
        if self._storage_executor_shutdown:
            return
        try:
            if not self._storage_unavailable:
                await self._run_storage_operation("startup failure close", self._worker_close)
        except Exception as exc:  # pragma: no cover - startup cleanup safety
            self._logger.e403(f"Failed to close HLstats database after startup failure: {exc}")
        finally:
            self._shutdown_storage_executor()

    def _fail_closed(self, exc: Exception, message: str) -> None:
        if self._fatal_error is None:
            self._fatal_error = exc
            self._logger.e403(f"{message}: {exc}")
        self.request_shutdown()

    def _require_non_event_loop_storage_context(self, operation_name: str) -> None:
        """Reject direct storage I/O outside the active serialized owner thread."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                f"{operation_name} performs synchronous storage I/O; use its async runtime path instead"
            )

        if self._storage_access_mode == "inactive" and not self._storage_unavailable:
            return
        if self._storage_owner_thread_id == threading.get_ident():
            return
        raise RuntimeError(
            f"{operation_name} must run on the HLstats storage executor thread while "
            f"{self._storage_access_mode} storage is active"
        )

    async def _consume_datagrams(self) -> None:
        while True:
            datagram = await self._udp_server.queue.get()
            try:
                await self._handle_datagram(datagram)
            except Exception as exc:  # pragma: no cover - defensive safety
                self._fail_closed(exc, "Failed to process HLstats datagram")
                return
            finally:
                self._udp_server.queue.task_done()
            if self._fatal_error is not None:
                return

    async def _handle_datagram(self, datagram: InboundDatagram) -> None:
        self._metrics.udp_datagrams += 1
        payload = datagram.text.strip()
        host, port = datagram.address

        if self._is_local_control_host(host):
            command = parse_control_command(payload)
            if command is not None:
                if self._requires_authenticated_control(command):
                    response = self._reject_unauthenticated_mutating_control(command, host, port)
                    self._udp_server.send_text(response, datagram.address)
                    return
                response = await self._handle_control_command(command.raw, host, port)
                if response is not None:
                    self._udp_server.send_text(response, datagram.address)
                return

        try:
            envelope = parse_proxy_envelope(payload)
        except ValueError:
            self._metrics.packets_dropped += 1
            self._logger.control(f"Ignoring non-proxied payload from {host}:{port}")
            return

        if envelope.proxy_key != self._proxy_key:
            self._metrics.packets_dropped += 1
            self._logger.e403(f"Proxy key mismatch from {host}:{port}; dropping packet")
            return

        control = parse_control_command(envelope.payload.strip())
        if control is not None:
            response = await self._handle_control_command(control.raw, host, port)
            if response is not None:
                self._udp_server.send_text(response, datagram.address)
            return

        server = self._servers.get(envelope.server_address)
        if server is None:
            self._metrics.packets_dropped += 1
            self._logger.e403(
                f"Unknown source server '{envelope.server_address or '<missing>'}'; dropping packet"
            )
            return

        await self._process_event_payload_async(
            payload=envelope.payload,
            server=server,
            source_label=f"{server.address}:{server.port}",
        )

    async def _handle_control_command(self, command: str, host: str, port: int) -> str | None:
        normalized = command.strip().strip(";").upper()
        self._metrics.record_control(normalized)
        self._logger.control(f"Command received from {host}:{port}: {normalized}")

        if normalized == "HEARTBEAT":
            self._logger.control(f"Send heartbeat status to frontend at '{host}:{port}'")
            return "Heartbeat OK"
        if normalized == "SERVERLIST":
            return self._servers.format_server_list()
        if normalized == "RELOAD":
            try:
                await self._flush_pending_async("reload flush")
                await self._run_storage_operation("reload", self._worker_reload)
            except Exception as exc:
                self._fail_closed(exc, "Failed to reload HLstats worker state")
                return "FAILED CONTROL COMMAND: RELOAD"
            return "OK, EXECUTING COMMAND: RELOAD"
        if normalized == "KILL":
            self.request_shutdown()
            return "OK, EXECUTING COMMAND: KILL"
        return None

    @staticmethod
    def _requires_authenticated_control(command: ControlCommand) -> bool:
        return command.command_type in _MUTATING_CONTROL_COMMANDS

    def _reject_unauthenticated_mutating_control(
        self,
        command: ControlCommand,
        host: str,
        port: int,
    ) -> str:
        normalized = command.raw.strip().strip(";").upper()
        self._metrics.record_control(normalized, rejected=True)
        self._logger.control(
            f"Rejected unauthenticated mutating control command from {host}:{port}: {normalized}"
        )
        return f"FAILED CONTROL COMMAND: {normalized} requires PROXY Key"

    def _reload_state(self) -> None:
        self._require_non_event_loop_storage_context("_reload_state")
        proxy_key = self._adapter.fetch_proxy_key()
        servers = self._adapter.fetch_servers()
        self._storage.reset_runtime_state()
        self._proxy_key = proxy_key
        self._servers.replace(servers)
        self._logger.control(
            f"Reloaded worker configuration: {len(self._servers.format_server_list().splitlines()) - 1} servers"
        )

    @staticmethod
    def _position_property(
        properties: Mapping[str, object],
        canonical: str,
        alias: str,
    ) -> tuple[int, int, int] | None:
        value = properties.get(canonical) if canonical in properties else properties.get(alias)
        return _parse_position_triplet(value)

    @staticmethod
    def _format_position(position: tuple[int, int, int]) -> str:
        return f"{position[0]} {position[1]} {position[2]}"

    @staticmethod
    def _clear_pending_killlocation(server: TrackedServer) -> None:
        server.state.clear_pending_killlocation()

    def _stage_killlocation(self, event: LogEvent, server: TrackedServer) -> None:
        if event.event_type is not LogEventType.WORLD_TRIGGER or event.action != "killlocation":
            return
        properties = event.properties
        server.state.pending_kill_attacker = self._position_property(
            properties, "attacker_position", "killerpos"
        )
        server.state.pending_kill_victim = self._position_property(
            properties, "victim_position", "victimpos"
        )

    def _apply_staged_killlocation(self, event: LogEvent, server: TrackedServer) -> LogEvent:
        if event.event_type is not LogEventType.KILL:
            return event
        properties = dict(event.properties)
        if (
            "attacker_position" not in properties
            and "killerpos" not in properties
            and server.state.pending_kill_attacker is not None
        ):
            properties["attacker_position"] = self._format_position(
                server.state.pending_kill_attacker
            )
        if (
            "victim_position" not in properties
            and "victimpos" not in properties
            and server.state.pending_kill_victim is not None
        ):
            properties["victim_position"] = self._format_position(server.state.pending_kill_victim)
        if properties == dict(event.properties):
            return event
        return replace(event, properties=MappingProxyType(properties))

    def _worker_reload(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_reload")
        self._raise_if_storage_operation_cancelled(operation_fence)
        self._reload_state()
        self._raise_if_storage_operation_cancelled(operation_fence)

    @staticmethod
    def _is_local_control_host(host: str) -> bool:
        return host in {"127.0.0.1", "::1", "localhost"}

    def process_stdin_line(self, line: str, server_address: str) -> None:
        """Synchronous replay helper for callers outside the asyncio worker."""

        self._require_non_event_loop_storage_context("process_stdin_line")
        server = self._servers.get(server_address)
        if server is None:
            self._metrics.packets_dropped += 1
            self._logger.e403(f"Unknown source server '{server_address}'; dropping stdin line")
            return
        self._metrics.stdin_records += 1
        self._process_event_payload(payload=line, server=server, source_label=server_address)

    async def process_stdin_line_async(self, line: str, server_address: str) -> None:
        """Handle one stdin line while retaining DB ownership in the worker."""

        server = self._servers.get(server_address)
        if server is None:
            self._metrics.packets_dropped += 1
            self._logger.e403(f"Unknown source server '{server_address}'; dropping stdin line")
            return
        self._metrics.stdin_records += 1
        await self._process_event_payload_async(
            payload=line,
            server=server,
            source_label=server_address,
        )

    def finalize_stdin_import(self) -> None:
        """Flush import-tail metadata after a finite stdin replay."""

        self._require_non_event_loop_storage_context("finalize_stdin_import")
        self._storage.finalize_import()

    async def finalize_stdin_import_async(self) -> None:
        """Flush stdin import metadata through the serialized DB worker."""

        await self._run_storage_operation(
            "stdin import finalization",
            self._worker_finalize_stdin_import,
        )

    def _worker_finalize_stdin_import(self, operation_fence: _StorageOperationFence) -> None:
        self._require_storage_executor_owner("_worker_finalize_stdin_import")
        self._raise_if_storage_operation_cancelled(operation_fence)
        self._storage.finalize_import()
        self._raise_if_storage_operation_cancelled(operation_fence)

    def _process_event_payload(
        self,
        *,
        payload: str,
        server: TrackedServer,
        source_label: str,
    ) -> None:
        prepared = self._prepare_event_payload(
            payload=payload,
            server=server,
            source_label=source_label,
        )
        if prepared is None:
            return
        event, transition, context, update, round_status_for_event = prepared
        self._persist_online_event(
            transition=transition,
            event=event,
            context=context,
            update=update,
        )
        self._finish_processed_event(
            event=event,
            server=server,
            source_label=source_label,
            update=update,
            round_status_for_event=round_status_for_event,
        )

    async def _process_event_payload_async(
        self,
        *,
        payload: str,
        server: TrackedServer,
        source_label: str,
    ) -> None:
        prepared = self._prepare_event_payload(
            payload=payload,
            server=server,
            source_label=source_label,
        )
        if prepared is None:
            return
        event, transition, context, update, round_status_for_event = prepared
        await self._run_storage_operation(
            "online event",
            lambda operation_fence: self._persist_online_event(
                transition=transition,
                event=event,
                context=context,
                update=update,
                operation_fence=operation_fence,
            ),
        )
        self._finish_processed_event(
            event=event,
            server=server,
            source_label=source_label,
            update=update,
            round_status_for_event=round_status_for_event,
        )

    def _prepare_event_payload(
        self,
        *,
        payload: str,
        server: TrackedServer,
        source_label: str,
    ) -> tuple[LogEvent, tuple[MapLifecyclePhase, str] | None, EventContext, object, int] | None:
        if _EMPTY_LOG_RECORD_RE.match(payload):
            return None
        event = parse_log_event(
            payload,
            backend=self._parser_backend,
            server_address=source_label,
        )
        is_kill = event.event_type is LogEventType.KILL
        if event.event_type is LogEventType.GENERIC and event.message == "Log file started":
            self._clear_pending_killlocation(server)
        self._stage_killlocation(event, server)
        if is_kill:
            try:
                event = self._apply_staged_killlocation(event, server)
                round_status_for_event = self._round_status_for_event(event, server)
                transition = apply_map_lifecycle_message(server, event.message)
                if transition is not None:
                    self._clear_pending_killlocation(server)
                context = EventContext(
                    server_id=server.server_id,
                    game=server.game,
                    extras=MappingProxyType(
                        {
                            "map": server.current_map or "",
                            "round_status": round_status_for_event,
                        }
                    ),
                )
                update = self._dispatcher.dispatch(event, context)
                return event, transition, context, update, round_status_for_event
            finally:
                self._clear_pending_killlocation(server)
        if event.event_type is LogEventType.WORLD_TRIGGER:
            self._project_round_status(event, server)
        round_status_for_event = self._round_status_for_event(event, server)
        transition = apply_map_lifecycle_message(server, event.message)
        if transition is not None:
            self._clear_pending_killlocation(server)
        context = EventContext(
            server_id=server.server_id,
            game=server.game,
            extras=MappingProxyType(
                {
                    "map": server.current_map or "",
                    "round_status": round_status_for_event,
                }
            ),
        )
        update = self._dispatcher.dispatch(event, context)
        return event, transition, context, update, round_status_for_event

    def _persist_online_event(
        self,
        *,
        transition: tuple[MapLifecyclePhase, str] | None,
        event: LogEvent,
        context: EventContext,
        update: object,
        operation_fence: _StorageOperationFence | None = None,
    ) -> None:
        if operation_fence is not None:
            self._require_storage_executor_owner("_persist_online_event")
            self._raise_if_storage_operation_cancelled(operation_fence)
        else:
            self._require_non_event_loop_storage_context("_persist_online_event")
        if event.event_type is LogEventType.GENERIC and event.message == "Log file started":
            self._storage.mark_source_log_boundary(context.server_id)
        self._storage.begin_online_event()
        try:
            if operation_fence is not None:
                self._raise_if_storage_operation_cancelled(operation_fence)
            if transition is not None:
                phase, map_name = transition
                self._storage.apply_server_map_transition(
                    context.server_id, phase, map_name, event.timestamp
                )
            if operation_fence is not None:
                self._raise_if_storage_operation_cancelled(operation_fence)
            self._storage.record(update, context)
            # If the event-loop deadline fired during a synchronous record
            # call, rollback rather than start its later commit write.  The
            # fence then atomically decides cancellation versus commit
            # admission, closing the race after this ordinary check.
            if operation_fence is not None:
                self._raise_if_storage_operation_cancelled(operation_fence)
                if not operation_fence.admit_online_commit():
                    raise RuntimeError(
                        "HLstats storage operation cancelled before online event commit"
                    )
            self._storage.commit_online_event()
        except Exception:
            try:
                self._storage.abort_online_event()
            except Exception as abort_exc:  # pragma: no cover - defensive cleanup
                self._logger.e403(f"Failed to rollback HLstats online event: {abort_exc}")
            raise

    def _finish_processed_event(
        self,
        *,
        event: LogEvent,
        server: TrackedServer,
        source_label: str,
        update: object,
        round_status_for_event: int,
    ) -> None:
        self._metrics.record_event(update.category.value)
        self._finalize_round_status(event, server, round_status_for_event)
        if self._stdin_verbose_events:
            self._logger.notice(
                f"Recorded {update.category.value} event '{update.event_code}' for {source_label}"
            )

    @staticmethod
    def _round_status_for_event(event: LogEvent, server: TrackedServer) -> int:
        if event.event_type is LogEventType.TEAM_TRIGGER:
            return server.state.round_status
        return server.state.round_status

    @staticmethod
    def _finalize_round_status(event: LogEvent, server: TrackedServer, round_status_for_event: int) -> None:
        if event.event_type is not LogEventType.TEAM_TRIGGER:
            return
        if round_status_for_event != 0:
            return
        action = event.action or ""
        if action in _ROUND_WIN_ACTIONS:
            server.state.round_status = 1

    @staticmethod
    def _project_round_status(event: LogEvent, server: TrackedServer) -> None:
        if event.event_type is LogEventType.WORLD_TRIGGER:
            action = event.action or ""
            if action in {"Round_Start", "Mini_Round_Start", "Game_Commencing"}:
                server.state.round_status = 0
            return

async def _serve(argv: Sequence[str] | None = None) -> int:
    try:
        settings = load_settings(argv)
    except Exception as exc:  # pragma: no cover - defensive configuration path
        print(f"error: {exc}")
        return 1

    database = SyncDatabaseAdapter(
        database_config_from_proxy_config(settings.config),
        import_mode=settings.stdin,
        enable_multi_statements=settings.stdin,
    )
    logger = ProxyLogger(LoggerConfig(level=settings.log_level))
    ingress_queue = BoundedIngressQueue(
        logger,
        maxsize=_configured_ingress_queue_size(settings.config),
    )
    transport = ProxyUdpServer(logger, queue_factory=lambda: ingress_queue)
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
            await runtime.start_stdin_import(
                transaction_batch_size=settings.stdin_transaction_batch_size,
            )
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
                await runtime.process_stdin_line_async(line, server_address)
                record_count += 1
                if not settings.stdin_verbose_events and record_count % _STDIN_PROGRESS_EVERY == 0:
                    logger.notice(f"STDIN import progress: {record_count} records processed")
            await runtime.finalize_stdin_import_async()
            await runtime.finish_stdin_import()
            logger.notice(f"Import of log file complete. Scanned {record_count} log records.")
            runtime.log_metrics_summary("stdin import complete")
            return 0
        except Exception as exc:  # pragma: no cover - defensive startup logging
            logger.e403(f"Failed to run HLstats worker stdin import: {exc}")
            with contextlib.suppress(Exception):
                await runtime.abort_stdin_import()
            _raise_if_hard_termination_required(runtime, exc)
            return 2

    try:
        await runtime.start(settings.bind_ip, settings.port)
    except Exception as exc:  # pragma: no cover - defensive startup logging
        logger.e403(f"Failed to start HLstats worker: {exc}")
        _raise_if_hard_termination_required(runtime, exc)
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

    try:
        await runtime.stop()
    except Exception as exc:
        logger.e403(f"HLstats worker stopped after fatal storage failure: {exc}")
        _raise_if_hard_termination_required(runtime, exc)
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m hlstats_py.runtime``."""

    try:
        return asyncio.run(_serve(argv))
    except _HardTerminationRequired as exc:
        # ThreadPoolExecutor workers are non-daemon.  Returning or raising
        # SystemExit here would let CPython wait indefinitely for a DB-API
        # syscall that ignored its timeout.  This boundary is intentionally
        # the only hard exit path; ordinary storage errors still return 2.
        sys.stderr.write(f"fatal: {exc}; forcing immediate non-success process exit\n")
        sys.stderr.flush()
        os._exit(_HARD_TERMINATION_EXIT_CODE)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
