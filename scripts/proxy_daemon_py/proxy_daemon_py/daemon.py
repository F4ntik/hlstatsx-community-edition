"""Core asyncio daemon implementation placeholder.

This module will eventually host the main event loop and orchestration logic of
the Python proxy daemon.  At the preparation stage we only define the public
APIs that other modules will eventually depend on.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from contextlib import suppress

from .balancer import Daemon, ServerAssignment, ServerBalancer
from .config import ProxyConfig
from .db import DatabaseAdapter, ProxyDaemonTarget
from .heartbeat import DaemonHeartbeatTarget, HeartbeatManager
from .log import ProxyLogger
from .transport import InboundDatagram, ProxyUdpServer

_DEFAULT_EVENT_QUEUE_SIZE = 10
_INGRESS_QUEUE_DRAIN_TIMEOUT_SECONDS = 5.0
_FORWARD_QUEUE_DRAIN_TIMEOUT_SECONDS = 5.0
_OVERFLOW_LOG_INTERVAL_SECONDS = 5.0


def _configured_event_queue_size(config: object) -> int:
    """Return the bounded proxy queue capacity from EventQueueSize."""

    size = getattr(config, "event_queue_size", _DEFAULT_EVENT_QUEUE_SIZE)
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("EventQueueSize must be greater than zero")
    return size


class BoundedProxyIngressQueue(asyncio.Queue[InboundDatagram]):
    """Bounded proxy UDP ingress that drops newest datagrams without blocking."""

    def __init__(self, logger: ProxyLogger, *, maxsize: int) -> None:
        super().__init__(maxsize=maxsize)
        self._logger = logger
        self.dropped_datagrams = 0
        self._last_overflow_log_at: float | None = None
        self._dropped_since_last_overflow_log = 0

    def put_nowait(self, item: InboundDatagram) -> None:
        if not self.full():
            super().put_nowait(item)
            return

        self.dropped_datagrams += 1
        self._dropped_since_last_overflow_log += 1
        now = time.monotonic()
        if (
            self._last_overflow_log_at is None
            or now - self._last_overflow_log_at >= _OVERFLOW_LOG_INTERVAL_SECONDS
        ):
            self._logger.e403(
                "Proxy UDP ingress queue full; dropping newest datagram "
                f"dropped_since_last_log={self._dropped_since_last_overflow_log} "
                f"total_dropped={self.dropped_datagrams}"
            )
            self._last_overflow_log_at = now
            self._dropped_since_last_overflow_log = 0


class ProxyDaemon:
    """Container object coordinating the main daemon subsystems."""

    def __init__(
        self,
        config: ProxyConfig,
        db: DatabaseAdapter,
        balancer: ServerBalancer,
        heartbeat: HeartbeatManager,
        udp_server: ProxyUdpServer,
        logger: ProxyLogger,
    ) -> None:
        self._config = config
        self._db = db
        self._balancer = balancer
        self._heartbeat = heartbeat
        self._udp_server = udp_server
        self._logger = logger
        self._loop: asyncio.AbstractEventLoop | None = None
        self._proxy_key: str | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._forwarder_task: asyncio.Task[None] | None = None
        queue_size = _configured_event_queue_size(config)
        self._ingress_queue = BoundedProxyIngressQueue(logger, maxsize=queue_size)
        self._udp_server.replace_queue(self._ingress_queue)
        self._game_packet_queue: asyncio.Queue[InboundDatagram] = asyncio.Queue(maxsize=queue_size)
        self._forward_queue_overflow_count = 0
        self._forward_queue_last_overflow_log_at: float | None = None
        self._forward_queue_dropped_since_last_overflow_log = 0
        self._ingress_queue_shutdown_drop_count = 0
        self._forward_queue_shutdown_drop_count = 0
        self._ingress_queue_inflight = 0
        self._forward_queue_inflight = 0
        self._accepting_game_packets = True
        self._heartbeat_targets: dict[str, DaemonHeartbeatTarget] = {}
        self._reload_lock: asyncio.Lock | None = None

    async def start(self) -> None:
        """Start the daemon by binding the UDP listener."""
        if self._loop is not None:
            raise RuntimeError("Daemon already running")

        self._loop = asyncio.get_running_loop()
        self._accepting_game_packets = True
        await self._db.connect()
        self._proxy_key = await self._db.fetch_proxy_key()
        self._reload_lock = asyncio.Lock()
        await self._reload_daemons()
        await self._heartbeat.start()
        await self._udp_server.start(self._config.bind_ip, self._config.port)
        bound_address = self._udp_server.address
        if bound_address is None:
            host = self._config.bind_ip or "0.0.0.0"
            port = self._config.port
        else:
            host, port = bound_address
        self._logger.notice(f"Proxy daemon listening on {host}:{port}")
        self._consumer_task = asyncio.create_task(self._consume_datagrams())
        self._forwarder_task = asyncio.create_task(self._forward_game_packets())

    async def stop(self) -> None:
        """Stop the daemon and release its resources."""
        if self._loop is None:
            return

        stop_receiving = getattr(self._udp_server, "stop_receiving", None)
        if callable(stop_receiving):
            await stop_receiving()
        if self._consumer_task is not None:
            await self._drain_ingress_queue()
        self._accepting_game_packets = False
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._consumer_task
            self._consumer_task = None
        if self._forwarder_task is not None:
            await self._drain_forward_queue()
            self._forwarder_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._forwarder_task
            self._forwarder_task = None
        await self._heartbeat.stop()
        await self._udp_server.stop()
        await self._db.close()
        self._logger.notice("Proxy daemon stopped")
        self._loop = None
        self._proxy_key = None
        self._heartbeat_targets.clear()
        self._reload_lock = None

    @property
    def game_packet_queue(self) -> asyncio.Queue[InboundDatagram]:
        """Queue containing non-control datagrams awaiting proxying."""

        return self._game_packet_queue

    @property
    def ingress_queue_overflow_count(self) -> int:
        """Return the number of newest UDP datagrams dropped at ingress."""

        return self._ingress_queue.dropped_datagrams

    @property
    def ingress_queue_shutdown_drop_count(self) -> int:
        """Return ingress packets discarded after a bounded shutdown drain expires."""

        return self._ingress_queue_shutdown_drop_count

    @property
    def forward_queue_overflow_count(self) -> int:
        """Return the number of newest packets dropped at the forward boundary."""

        return self._forward_queue_overflow_count

    @property
    def forward_queue_shutdown_drop_count(self) -> int:
        """Return packets discarded after a bounded shutdown drain expires."""

        return self._forward_queue_shutdown_drop_count

    @property
    def balancer(self) -> ServerBalancer:
        """Expose the server balancer for inspection and tests."""

        return self._balancer

    async def _consume_datagrams(self) -> None:
        """Consume datagrams from the UDP queue and dispatch control commands."""

        while True:
            datagram = await self._udp_server.queue.get()
            self._ingress_queue_inflight += 1
            try:
                if not await self._handle_datagram(datagram):
                    self._enqueue_game_packet(datagram)
            finally:
                self._ingress_queue_inflight -= 1
                self._udp_server.queue.task_done()

    def _enqueue_game_packet(self, datagram: InboundDatagram) -> bool:
        """Queue an accepted game packet without blocking the UDP consumer."""

        if not self._accepting_game_packets:
            return False
        if self._game_packet_queue.full():
            self._forward_queue_overflow_count += 1
            self._forward_queue_dropped_since_last_overflow_log += 1
            now = time.monotonic()
            if (
                self._forward_queue_last_overflow_log_at is None
                or now - self._forward_queue_last_overflow_log_at >= _OVERFLOW_LOG_INTERVAL_SECONDS
            ):
                self._logger.e403(
                    "Proxy forwarding queue full; dropping newest packet "
                    "dropped_since_last_log="
                    f"{self._forward_queue_dropped_since_last_overflow_log} "
                    f"total_dropped={self._forward_queue_overflow_count}"
                )
                self._forward_queue_last_overflow_log_at = now
                self._forward_queue_dropped_since_last_overflow_log = 0
            return False
        self._game_packet_queue.put_nowait(datagram)
        return True

    async def _drain_forward_queue(self) -> None:
        """Let accepted forward packets finish before cancelling the worker."""

        try:
            await asyncio.wait_for(
                self._game_packet_queue.join(),
                timeout=_FORWARD_QUEUE_DRAIN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            queued_dropped = 0
            while True:
                try:
                    self._game_packet_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self._game_packet_queue.task_done()
                queued_dropped += 1
            in_flight_dropped = self._forward_queue_inflight
            dropped = queued_dropped + in_flight_dropped
            self._forward_queue_shutdown_drop_count += dropped
            self._logger.e403(
                "Proxy forwarding shutdown drain timed out; "
                f"remaining_dropped={queued_dropped} "
                f"in_flight_dropped={in_flight_dropped} "
                f"total_shutdown_dropped={self._forward_queue_shutdown_drop_count}"
            )

    async def _drain_ingress_queue(self) -> None:
        """Move accepted ingress packets through forwarding before shutdown."""

        try:
            await asyncio.wait_for(
                self._udp_server.queue.join(),
                timeout=_INGRESS_QUEUE_DRAIN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            queued_dropped = 0
            while True:
                try:
                    self._udp_server.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self._udp_server.queue.task_done()
                queued_dropped += 1
            in_flight_dropped = self._ingress_queue_inflight
            dropped = queued_dropped + in_flight_dropped
            self._ingress_queue_shutdown_drop_count += dropped
            self._logger.e403(
                "Proxy UDP ingress shutdown drain timed out; "
                f"remaining_dropped={queued_dropped} "
                f"in_flight_dropped={in_flight_dropped} "
                f"total_shutdown_dropped={self._ingress_queue_shutdown_drop_count}"
            )

    async def _forward_game_packets(self) -> None:
        """Forward queued game datagrams to their assigned downstream daemon."""

        while True:
            datagram = await self._game_packet_queue.get()
            self._forward_queue_inflight += 1
            try:
                self._forward_game_packet(datagram)
            except Exception as exc:  # pragma: no cover - defensive safety
                self._logger.e403(f"Error while forwarding packet: {exc}")
            finally:
                self._forward_queue_inflight -= 1
                self._game_packet_queue.task_done()

    async def _handle_datagram(self, datagram: InboundDatagram) -> bool:
        """Return ``True`` if the datagram was handled as a control command."""

        host, port = datagram.address
        payload = datagram.text.strip()

        if self._is_local_control_host(host) and payload.startswith("C;"):
            if self._requires_authenticated_control(payload):
                unauthenticated_response = self._reject_unauthenticated_mutating_control(
                    payload,
                    host,
                    port,
                )
                self._udp_server.send_text(unauthenticated_response, datagram.address)
                return True
            response = await self._handle_control_payload(payload, host, port)
            if response is not None:
                self._udp_server.send_text(response, datagram.address)
            else:
                self._udp_server.send_text(
                    self._reject_unsupported_control(payload, host, port), datagram.address
                )
            return True

        proxy_command = self._parse_proxy_command(payload)
        if proxy_command is None:
            return False

        proxy_key, command_payload = proxy_command
        if self._proxy_key is None or proxy_key != self._proxy_key:
            message = f"FAILED PROXY REQUEST ({host}:{port})\n"
            self._udp_server.send_text(message, datagram.address)
            self._logger.e403(f"Sending FAILED PROXY REQUEST to {host}:{port}")
            return True

        response = await self._handle_control_payload(command_payload.strip(), host, port)
        if response is None:
            if command_payload.strip().startswith("C;"):
                self._udp_server.send_text(
                    self._reject_unsupported_control(command_payload, host, port),
                    datagram.address,
                )
                return True
            return False

        self._udp_server.send_text(response, datagram.address)
        return True

    async def _handle_control_payload(self, payload: str, host: str, port: int) -> str | None:
        match payload:
            case "C;HEARTBEAT;":
                self._logger.control(f"Sending Heartbeat to {host}:{port}")
                return "Heartbeat OK"
            case "C;SERVERLIST;":
                self._logger.control(f"Sending Serverlist to {host}:{port}")
                server_list = self._format_server_list()
                if server_list.strip() != "ServerList":
                    self._logger.control(server_list)
                return server_list
            case "C;RELOAD;":
                self._logger.control(f"Received reload command from {host}:{port}")
                await self._reload_daemons()
                return "Reload command acknowledged\n"
        return None

    async def _reload_daemons(self) -> None:
        if self._reload_lock is None:
            self._reload_lock = asyncio.Lock()

        async with self._reload_lock:
            try:
                targets = await self._db.fetch_daemons()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.e403(f"Failed to reload proxy daemons: {exc}")
                return

            desired = {self._target_identifier(target): target for target in targets}
            existing_ids = set(self._balancer.manager.daemons.keys())

            # Remove daemons that are no longer configured.
            for identifier in sorted(existing_ids - desired.keys()):
                self._logger.control(f"Removing proxy daemon {identifier}")
                self._balancer.unregister_daemon(identifier)
                removed_heartbeat_target = self._heartbeat_targets.pop(identifier, None)
                if removed_heartbeat_target is not None:
                    self._heartbeat.remove_target(removed_heartbeat_target)

            # Register or update configured daemons.
            for identifier, target in desired.items():
                daemon = self._balancer.manager.daemons.get(identifier)
                if daemon is None:
                    daemon = self._create_daemon(identifier, target)
                    self._balancer.register_daemon(daemon)
                    self._logger.control(f"Registered proxy daemon {identifier}")
                else:
                    daemon.host = target.host
                    daemon.port = target.port

                if identifier not in self._heartbeat_targets:
                    heartbeat_target = DaemonHeartbeatTarget(
                        identifier,
                        self._balancer.manager,
                        self._db,
                        self._logger,
                        timeout=self._default_heartbeat_timeout(daemon),
                    )
                    self._heartbeat_targets[identifier] = heartbeat_target
                    self._heartbeat.add_target(heartbeat_target)

            # Ensure heartbeat targets that no longer have daemons are removed.
            for identifier in list(self._heartbeat_targets.keys()):
                if identifier not in desired:
                    removed_heartbeat_target = self._heartbeat_targets.pop(identifier)
                    self._heartbeat.remove_target(removed_heartbeat_target)

            self._logger.control(f"Reloaded proxy daemon configuration: {len(desired)} entries")

    @staticmethod
    def _target_identifier(target: ProxyDaemonTarget) -> str:
        return f"{target.host}:{target.port}"

    def _create_daemon(self, identifier: str, target: ProxyDaemonTarget) -> Daemon:
        return Daemon(
            identifier=identifier,
            host=target.host,
            port=target.port,
        )

    @staticmethod
    def _default_heartbeat_timeout(daemon: Daemon) -> float:
        return daemon.heartbeat_timeout or 30.0

    def _format_server_list(self) -> str:
        assignments: Iterable[tuple[str, ServerAssignment]] = self._balancer.assignments.items()
        lines = [
            f"{server} -> {assignment.daemon_id}" for server, assignment in sorted(assignments)
        ]
        if lines:
            return "ServerList\n" + "\n".join(lines) + "\n"
        return "ServerList\n"

    @staticmethod
    def _is_local_control_host(host: str) -> bool:
        return host in {"127.0.0.1", "::1"}

    @classmethod
    def _requires_authenticated_control(cls, payload: str) -> bool:
        return cls._normalize_control_payload(payload) == "RELOAD"

    def _reject_unauthenticated_mutating_control(self, payload: str, host: str, port: int) -> str:
        normalized = self._normalize_control_payload(payload)
        self._logger.control(
            f"Rejected unauthenticated mutating control command from {host}:{port}: {normalized}"
        )
        return f"FAILED CONTROL COMMAND: {normalized} requires PROXY Key\n"

    def _reject_unsupported_control(self, payload: str, host: str, port: int) -> str:
        normalized = self._normalize_control_payload(payload)
        self._logger.control(
            f"Rejected unsupported control command from {host}:{port}: {normalized}"
        )
        return f"FAILED CONTROL COMMAND: {normalized} is not supported\n"

    @staticmethod
    def _normalize_control_payload(payload: str) -> str:
        return payload.strip().removeprefix("C;").strip(";").upper()

    @staticmethod
    def _parse_proxy_command(payload: str) -> tuple[str, str] | None:
        if " PROXY " not in payload:
            return None
        prefix, command = payload.rsplit(" PROXY ", 1)
        if not prefix.startswith("PROXY Key="):
            return None
        key_section = prefix.removeprefix("PROXY Key=")
        proxy_key, *_ = key_section.split(" ", 1)
        return proxy_key.strip(), command

    def _forward_game_packet(self, datagram: InboundDatagram) -> None:
        """Forward *datagram* to the assigned downstream daemon if available."""

        if self._proxy_key is None:
            self._logger.e403("Proxy key unavailable; dropping game packet")
            return

        host, port = datagram.address
        server_address = f"{host}:{port}"

        if self._should_skip_payload(datagram.text):
            self._logger.notice(f"Skipping message from {server_address}")
            return

        payload = self._normalise_payload(datagram.text)
        forward_payload = self._format_forward_payload(server_address, payload)

        attempted: set[str] = set()

        while True:
            assignment = self._balancer.assign_server(server_address)
            if assignment is None:
                self._logger.e403(
                    f"No available daemon to handle traffic from {server_address}; dropping packet"
                )
                return

            if assignment.daemon_id in attempted:
                self._logger.e403(
                    f"Exhausted daemon candidates for {server_address}; dropping packet"
                )
                return

            attempted.add(assignment.daemon_id)
            daemon = self._balancer.manager.get(assignment.daemon_id)
            destination = (daemon.host, daemon.port)

            try:
                self._udp_server.send_text(forward_payload, destination)
            except OSError as exc:
                self._logger.e403(
                    f"Failed to forward packet from {server_address} to {daemon.identifier}: {exc}"
                )
                self._balancer.manager.mark_failure(daemon.identifier)
                self._balancer.release_server(server_address)
                continue

            self._logger.balance(f"Forwarded packet from {server_address} to {daemon.identifier}")
            return

    def _format_forward_payload(self, server_address: str, payload: str) -> str:
        return f"PROXY Key={self._proxy_key} {server_address}PROXY {payload}"

    @staticmethod
    def _normalise_payload(payload: str) -> str:
        marker = "RL "
        index = payload.rfind(marker)
        if index == -1:
            return payload
        return payload[index:]

    @staticmethod
    def _should_skip_payload(payload: str) -> bool:
        return ("rcon from" in payload) and (
            'command "status"' in payload or 'command "stats"' in payload or 'command ""' in payload
        )
