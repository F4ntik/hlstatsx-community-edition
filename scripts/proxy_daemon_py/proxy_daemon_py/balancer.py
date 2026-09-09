"""Server assignment and balancing primitives for the Python proxy daemon."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class DaemonState(str, Enum):
    """Possible runtime states for a downstream daemon."""

    UNKNOWN = "unknown"
    UP = "up"
    DOWN = "down"


@dataclass(slots=True)
class Daemon:
    """State associated with a downstream daemon instance."""

    identifier: str
    host: str
    port: int
    weight: int = 1
    heartbeat_timeout: float = 30.0
    state: DaemonState = DaemonState.UNKNOWN
    last_heartbeat: datetime | None = None
    consecutive_failures: int = 0

    def mark_heartbeat(self, *, timestamp: datetime | None = None) -> None:
        """Record a heartbeat and transition the daemon to the :class:`DaemonState.UP` state."""

        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        self.last_heartbeat = timestamp
        self.state = DaemonState.UP
        self.consecutive_failures = 0

    def mark_failure(self, *, timestamp: datetime | None = None) -> None:
        """Register a failed heartbeat or send attempt."""

        self.consecutive_failures += 1
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        if self.last_heartbeat is None:
            self.state = DaemonState.DOWN
            return
        if timestamp - self.last_heartbeat > timedelta(seconds=self.heartbeat_timeout):
            self.state = DaemonState.DOWN

    def mark_down(self) -> None:
        """Force the daemon into the :class:`DaemonState.DOWN` state."""

        self.state = DaemonState.DOWN

    def is_available(self, *, timestamp: datetime | None = None) -> bool:
        """Return ``True`` if the daemon should be considered for routing."""

        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        if self.state == DaemonState.DOWN:
            return False
        if self.last_heartbeat is None:
            # Unknown daemons are available until proven otherwise.
            return True
        return timestamp - self.last_heartbeat <= timedelta(seconds=self.heartbeat_timeout)


@dataclass(slots=True)
class DaemonManager:
    """Manage registered daemons and provide round-robin scheduling."""

    daemons: dict[str, Daemon] = field(default_factory=dict)
    _round_robin_order: list[str] = field(default_factory=list)
    _rr_index: int = 0

    def register(self, daemon: Daemon) -> None:
        """Add or update *daemon* in the manager."""

        self.daemons[daemon.identifier] = daemon
        if daemon.identifier not in self._round_robin_order:
            self._round_robin_order.append(daemon.identifier)

    def unregister(self, identifier: str) -> None:
        """Remove a daemon from the pool."""

        if identifier in self.daemons:
            del self.daemons[identifier]
        if identifier in self._round_robin_order:
            self._round_robin_order.remove(identifier)
            self._rr_index %= max(len(self._round_robin_order), 1) if self._round_robin_order else 1

    def get(self, identifier: str) -> Daemon:
        """Return a registered daemon or raise :class:`KeyError`."""

        return self.daemons[identifier]

    def mark_heartbeat(self, identifier: str, *, timestamp: datetime | None = None) -> None:
        """Forward heartbeat updates to the managed daemon."""

        self.get(identifier).mark_heartbeat(timestamp=timestamp)

    def mark_failure(self, identifier: str, *, timestamp: datetime | None = None) -> None:
        """Record a failure for the given daemon."""

        self.get(identifier).mark_failure(timestamp=timestamp)

    def mark_down(self, identifier: str) -> None:
        """Immediately mark the daemon as unavailable."""

        self.get(identifier).mark_down()

    def next_available(self, *, timestamp: datetime | None = None) -> Daemon | None:
        """Return the next daemon eligible for assignment."""

        if not self._round_robin_order:
            return None
        start_index = self._rr_index
        scanned = 0
        while scanned < len(self._round_robin_order):
            daemon_id = self._round_robin_order[self._rr_index]
            self._rr_index = (self._rr_index + 1) % len(self._round_robin_order)
            scanned += 1
            daemon = self.daemons[daemon_id]
            if daemon.is_available(timestamp=timestamp):
                return daemon
        # If none are available we reset the index to avoid starvation once a daemon returns.
        self._rr_index = start_index % len(self._round_robin_order)
        return None


@dataclass(slots=True)
class ServerAssignment:
    """Mapping between game servers and daemon instances."""

    server_address: str
    daemon_id: str
    assigned_at: datetime

    def is_valid(self, manager: DaemonManager, *, timestamp: datetime | None = None) -> bool:
        """Return whether the assignment still points to an available daemon."""

        try:
            daemon = manager.get(self.daemon_id)
        except KeyError:
            return False
        return daemon.is_available(timestamp=timestamp)


@dataclass(slots=True)
class ServerBalancer:
    """Round-robin server balancer with sticky assignments."""

    manager: DaemonManager = field(default_factory=DaemonManager)
    assignments: dict[str, ServerAssignment] = field(default_factory=dict)

    def register_daemon(self, daemon: Daemon) -> None:
        self.manager.register(daemon)

    def unregister_daemon(self, identifier: str) -> None:
        self.manager.unregister(identifier)
        self._prune_assignments()

    def assign_server(
        self, server_address: str, *, timestamp: datetime | None = None
    ) -> ServerAssignment | None:
        """Return an assignment for *server_address* or ``None`` if none are available."""

        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)

        existing = self.assignments.get(server_address)
        if existing and existing.is_valid(self.manager, timestamp=timestamp):
            existing.assigned_at = timestamp
            return existing

        daemon = self.manager.next_available(timestamp=timestamp)
        if daemon is None:
            return None

        assignment = ServerAssignment(
            server_address=server_address, daemon_id=daemon.identifier, assigned_at=timestamp
        )
        self.assignments[server_address] = assignment
        return assignment

    def release_server(self, server_address: str) -> None:
        """Forget the assignment for *server_address* if present."""

        self.assignments.pop(server_address, None)

    def _prune_assignments(self) -> None:
        for server, assignment in list(self.assignments.items()):
            if assignment.daemon_id not in self.manager.daemons:
                del self.assignments[server]


__all__ = [
    "DaemonState",
    "Daemon",
    "DaemonManager",
    "ServerAssignment",
    "ServerBalancer",
]
