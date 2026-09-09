"""Tests for the migration/import helper utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import pytest
from proxy_daemon_py import bootstrap, importer
from proxy_daemon_py.balancer import DaemonState
from proxy_daemon_py.config import ProxyConfig
from proxy_daemon_py.db import GameServer, ProxyDaemonTarget, StoredProxyDaemon


@dataclass(slots=True)
class StubAdapter:
    targets: list[ProxyDaemonTarget]
    statuses: list[StoredProxyDaemon]
    servers: list[GameServer]

    def fetch_daemons(self) -> list[ProxyDaemonTarget]:
        return list(self.targets)

    def fetch_daemon_statuses(self) -> list[StoredProxyDaemon]:
        return list(self.statuses)

    def fetch_servers(self) -> list[GameServer]:
        return list(self.servers)


def test_load_existing_distribution_assigns_round_robin() -> None:
    heartbeat = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    adapter = StubAdapter(
        targets=[
            ProxyDaemonTarget(host="10.0.0.1", port=27900),
            ProxyDaemonTarget(host="10.0.0.2", port=27901),
        ],
        statuses=[
            StoredProxyDaemon(
                host="10.0.0.1",
                port=27900,
                current_state="up",
                previous_state="up",
                last_heartbeat=heartbeat,
                latency_ms=10,
            ),
            StoredProxyDaemon(
                host="10.0.0.2",
                port=27901,
                current_state="up",
                previous_state="up",
                last_heartbeat=None,
                latency_ms=None,
            ),
        ],
        servers=[
            GameServer(server_id=1, address="1.1.1.1", port=27015, name="Alpha", game="tf2"),
            GameServer(server_id=2, address="1.1.1.2", port=27016, name="Bravo", game="tf2"),
            GameServer(server_id=3, address="1.1.1.3", port=27017, name="Charlie", game="tf2"),
        ],
    )

    summary = importer.load_existing_distribution(
        adapter,
        timestamp=heartbeat,
    )

    assert summary.daemon_order == ["10.0.0.1:27900", "10.0.0.2:27901"]
    assert [mapping.daemon_id for mapping in summary.mappings] == [
        "10.0.0.1:27900",
        "10.0.0.2:27901",
        "10.0.0.1:27900",
    ]
    assert summary.unassigned_servers == []
    assert summary.missing_daemons == []
    assert summary.unknown_daemons == []
    assert summary.balancer.manager.daemons["10.0.0.1:27900"].state is DaemonState.UP


def test_load_existing_distribution_handles_missing_and_unknown() -> None:
    adapter = StubAdapter(
        targets=[ProxyDaemonTarget(host="10.0.0.1", port=27900)],
        statuses=[
            StoredProxyDaemon(
                host="10.0.0.1",
                port=27900,
                current_state="down",
                previous_state="up",
                last_heartbeat=None,
                latency_ms=None,
            ),
            StoredProxyDaemon(
                host="ghost",
                port=28000,
                current_state="up",
                previous_state="n/a",
                last_heartbeat=None,
                latency_ms=None,
            ),
        ],
        servers=[
            GameServer(server_id=1, address="1.1.1.1", port=27015, name="Alpha", game="tf2"),
        ],
    )

    summary = importer.load_existing_distribution(adapter)

    assert summary.missing_daemons == []
    assert summary.unknown_daemons == ["ghost:28000"]
    assert [server.server_id for server in summary.unassigned_servers] == [1]
    assert summary.mappings == []


def test_format_summary_lists_sections() -> None:
    adapter = StubAdapter(
        targets=[ProxyDaemonTarget(host="10.0.0.1", port=27900)],
        statuses=[
            StoredProxyDaemon(
                host="10.0.0.1",
                port=27900,
                current_state="up",
                previous_state="up",
                last_heartbeat=None,
                latency_ms=None,
            )
        ],
        servers=[GameServer(server_id=1, address="1.1.1.1", port=27015, name="Alpha", game="tf2")],
    )
    summary = importer.load_existing_distribution(adapter)
    report = importer.format_summary(summary)

    assert "Daemons:" in report
    assert "Server assignments:" in report
    assert "1: 1.1.1.1:27015" in report


def test_database_config_from_proxy_config_parses_port() -> None:
    config = ProxyConfig(
        config_path=Path("/tmp/hlstats.conf"),
        db_host="db.example.com:3307",
        db_username="user",
        db_password="pass",
        db_name="hlstatsx",
        bind_ip=None,
        port=27500,
        debug_level=0,
        event_queue_size=10,
        ingress_queue_size=1000,
        cpanel_hack=False,
        raw=MappingProxyType({}),
    )

    db_config = bootstrap.database_config_from_proxy_config(config)

    assert db_config.host == "db.example.com"
    assert db_config.port == 3307
    assert db_config.username == "user"


def test_database_config_from_proxy_config_requires_host() -> None:
    config = ProxyConfig(
        config_path=Path("/tmp/hlstats.conf"),
        db_host=" ",
        db_username="user",
        db_password="pass",
        db_name="hlstatsx",
        bind_ip=None,
        port=27500,
        debug_level=0,
        event_queue_size=10,
        ingress_queue_size=1000,
        cpanel_hack=False,
        raw=MappingProxyType({}),
    )

    with pytest.raises(ValueError):
        bootstrap.database_config_from_proxy_config(config)
