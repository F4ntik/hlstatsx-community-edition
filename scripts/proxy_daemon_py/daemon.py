"""Core asyncio daemon implementation placeholder.

This module will eventually host the main event loop and orchestration logic of
the Python proxy daemon.  At the preparation stage we only define the public
APIs that other modules will eventually depend on.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress

from .balancer import Daemon, ServerAssignment, ServerBalancer
from .config import ProxyConfig
from .db import DatabaseAdapter, ProxyDaemonTarget
from .heartbeat import DaemonHeartbeatTarget, HeartbeatManager
from .log import ProxyLogger
from .transport import InboundDatagram, ProxyUdpServer


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
        self._game_packet_queue: asyncio.Queue[InboundDatagram] = asyncio.Queue()
        self._heartbeat_targets: dict[str, DaemonHeartbeatTarget] = {}
        self._reload_lock: asyncio.Lock | None = None

    async def start(self) -> None:
        """Start the daemon by binding the UDP listener."""
        if self._loop is not None:
            raise RuntimeError("Daemon already running")

        self._loop = asyncio.get_running_loop()
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
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._consumer_task
            self._consumer_task = None
        if self._forwarder_task is not None:
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
    def balancer(self) -> ServerBalancer:
        """Expose the server balancer for inspection and tests."""

        return self._balancer

    async def _consume_datagrams(self) -> None:
        """Consume datagrams from the UDP queue and dispatch control commands."""

        while True:
            datagram = await self._udp_server.queue.get()
            if not await self._handle_datagram(datagram):
                self._game_packet_queue.put_nowait(datagram)

    async def _forward_game_packets(self) -> None:
        """Forward queued game datagrams to their assigned downstream daemon."""

        while True:
            datagram = await self._game_packet_queue.get()
            try:
                self._forward_game_packet(datagram)
            except Exception as exc:  # pragma: no cover - defensive safety
                self._logger.e403(f"Error while forwarding packet: {exc}")
            finally:
                self._game_packet_queue.task_done()

    async def _handle_datagram(self, datagram: InboundDatagram) -> bool:
        """Return ``True`` if the datagram was handled as a control command."""

        host, port = datagram.address
        payload = datagram.text.strip()

        if self._is_local_control_host(host) and payload.startswith("C;"):
            response = await self._handle_control_payload(payload, host, port)
            if response is not None:
                self._udp_server.send_text(response, datagram.address)
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
                target = self._heartbeat_targets.pop(identifier, None)
                if target is not None:
                    self._heartbeat.remove_target(target)

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
                    target = self._heartbeat_targets.pop(identifier)
                    self._heartbeat.remove_target(target)

            self._logger.control(
                f"Reloaded proxy daemon configuration: {len(desired)} entries"
            )

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
        lines = [f"{server} -> {assignment.daemon_id}" for server, assignment in sorted(assignments)]
        if lines:
            return "ServerList\n" + "\n".join(lines) + "\n"
        return "ServerList\n"

    @staticmethod
    def _is_local_control_host(host: str) -> bool:
        return host in {"127.0.0.1", "::1"}

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

            self._logger.balance(
                f"Forwarded packet from {server_address} to {daemon.identifier}"
            )
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
        return (
            ("rcon from" in payload)
            and (
                'command "status"' in payload
                or 'command "stats"' in payload
                or 'command ""' in payload
            )
        )
