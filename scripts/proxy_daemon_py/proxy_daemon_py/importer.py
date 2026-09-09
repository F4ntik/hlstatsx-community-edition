"""Utilities for importing legacy proxy daemon state from MySQL."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from . import cli
from .balancer import Daemon, DaemonState, ServerBalancer
from .bootstrap import database_config_from_proxy_config
from .config import ConfigError
from .db import DatabaseError, GameServer, StoredProxyDaemon, SyncDatabaseAdapter


@dataclass(frozen=True, slots=True)
class ServerMapping:
    """Result of associating a HLstats server with a daemon."""

    server: GameServer
    daemon_id: str


@dataclass(slots=True)
class ImportSummary:
    """Aggregate result produced by :func:`load_existing_distribution`."""

    balancer: ServerBalancer
    daemon_order: list[str]
    mappings: list[ServerMapping]
    missing_daemons: list[str]
    unknown_daemons: list[str]
    unassigned_servers: list[GameServer]


def load_existing_distribution(
    adapter: SyncDatabaseAdapter,
    *,
    heartbeat_timeout: float = 30.0,
    timestamp: datetime | None = None,
) -> ImportSummary:
    """Load daemon and server information from *adapter* and build assignments."""

    targets = adapter.fetch_daemons()
    statuses = {
        f"{status.host}:{status.port}": status for status in adapter.fetch_daemon_statuses()
    }
    servers = adapter.fetch_servers()

    balancer = ServerBalancer()
    daemon_order: list[str] = []
    missing_daemons: list[str] = []

    for target in targets:
        identifier = f"{target.host}:{target.port}"
        daemon = Daemon(
            identifier=identifier,
            host=target.host,
            port=target.port,
            heartbeat_timeout=heartbeat_timeout,
        )
        status = statuses.pop(identifier, None)
        _apply_status_to_daemon(daemon, status)
        if status is None:
            missing_daemons.append(identifier)
        balancer.register_daemon(daemon)
        daemon_order.append(identifier)

    unknown_daemons = sorted(statuses.keys())

    reference_time = timestamp or datetime.now(tz=timezone.utc)
    mappings: list[ServerMapping] = []
    unassigned: list[GameServer] = []

    for server in servers:
        endpoint = f"{server.address}:{server.port}"
        assignment = balancer.assign_server(endpoint, timestamp=reference_time)
        if assignment is None:
            unassigned.append(server)
        else:
            mappings.append(ServerMapping(server=server, daemon_id=assignment.daemon_id))

    return ImportSummary(
        balancer=balancer,
        daemon_order=daemon_order,
        mappings=mappings,
        missing_daemons=missing_daemons,
        unknown_daemons=unknown_daemons,
        unassigned_servers=unassigned,
    )


def format_summary(summary: ImportSummary) -> str:
    """Return a human-readable report for *summary*."""

    lines: list[str] = []
    lines.append("Daemons:")
    for identifier in summary.daemon_order:
        daemon = summary.balancer.manager.daemons.get(identifier)
        if daemon is None:
            continue
        lines.append(
            f"  - {identifier} (state={daemon.state.value}, "
            f"last_heartbeat={_format_timestamp(daemon.last_heartbeat)})"
        )

    if summary.missing_daemons:
        lines.append("  missing daemon rows: " + ", ".join(summary.missing_daemons))
    if summary.unknown_daemons:
        lines.append("  extra daemon rows: " + ", ".join(summary.unknown_daemons))

    lines.append("")
    lines.append("Server assignments:")
    if summary.mappings:
        for mapping in summary.mappings:
            server = mapping.server
            lines.append(
                f"  - {server.server_id}: {server.address}:{server.port} -> {mapping.daemon_id}"
            )
    else:
        lines.append("  (no servers registered)")

    if summary.unassigned_servers:
        lines.append("")
        lines.append("Unassigned servers:")
        for server in summary.unassigned_servers:
            lines.append(f"  - {server.server_id}: {server.address}:{server.port} ({server.name})")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the migration helper CLI."""

    try:
        settings = cli.load_settings(argv)
    except (FileNotFoundError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        db_config = database_config_from_proxy_config(settings.config)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    adapter = SyncDatabaseAdapter(db_config)
    try:
        adapter.connect()
        summary = load_existing_distribution(adapter)
    except DatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        adapter.close()

    print(format_summary(summary))
    return 0


def _apply_status_to_daemon(daemon: Daemon, status: StoredProxyDaemon | None) -> None:
    if status is None:
        daemon.state = DaemonState.UNKNOWN
        return

    state_text = (status.current_state or "").strip().lower()
    if state_text == "up":
        daemon.state = DaemonState.UP
    elif state_text == "down":
        daemon.state = DaemonState.DOWN
    else:
        daemon.state = DaemonState.UNKNOWN

    heartbeat = _normalize_timestamp(status.last_heartbeat)
    if heartbeat is not None:
        daemon.last_heartbeat = heartbeat


def _normalize_timestamp(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _format_timestamp(moment: datetime | None) -> str:
    if moment is None:
        return "unknown"
    return moment.isoformat()


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
