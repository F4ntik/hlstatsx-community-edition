"""Server assignment and balancing primitives for the Python proxy daemon."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DaemonInfo:
    """State associated with a downstream daemon instance."""

    identifier: str
    host: str
    port: int
    is_online: bool = True
    weight: int = 1


@dataclass
class ServerAssignment:
    """Mapping between game servers and daemon instances."""

    server_address: str
    daemon_id: str


@dataclass
class ServerBalancer:
    """Placeholder implementation of the balancing subsystem."""

    daemons: dict[str, DaemonInfo] = field(default_factory=dict)
    assignments: dict[str, ServerAssignment] = field(default_factory=dict)
    _round_robin_order: list[str] = field(default_factory=list)
    _rr_index: int = 0

    def register_daemon(self, daemon: DaemonInfo) -> None:
        """Register a daemon and include it into the round-robin pool."""

        self.daemons[daemon.identifier] = daemon
        if daemon.identifier not in self._round_robin_order:
            self._round_robin_order.append(daemon.identifier)

    def assign_server(self, server_address: str) -> ServerAssignment | None:
        """Assign *server_address* to the next available daemon."""

        if not self._round_robin_order:
            return None
        daemon_id = self._round_robin_order[self._rr_index % len(self._round_robin_order)]
        self._rr_index += 1
        assignment = ServerAssignment(server_address=server_address, daemon_id=daemon_id)
        self.assignments[server_address] = assignment
        return assignment

    def get_assignment(self, server_address: str) -> ServerAssignment | None:
        """Return the cached assignment for *server_address* if present."""

        return self.assignments.get(server_address)
