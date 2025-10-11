"""Runtime helpers for constructing the proxy daemon stack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo

from .balancer import ServerBalancer
from .config import ProxyConfig
from .daemon import ProxyDaemon
from .db import DatabaseAdapter, DatabaseConfig
from .heartbeat import HeartbeatManager
from .log import LogLevel, LoggerConfig, ProxyLogger
from .transport import ProxyUdpServer


@dataclass(slots=True)
class ProxyDaemonComponents:
    """Aggregated objects required to run :class:`ProxyDaemon`."""

    config: ProxyConfig
    logger: ProxyLogger
    database: DatabaseAdapter
    balancer: ServerBalancer
    heartbeat: HeartbeatManager
    transport: ProxyUdpServer
    daemon: ProxyDaemon


def database_config_from_proxy_config(config: ProxyConfig) -> DatabaseConfig:
    """Translate ``hlstats.conf`` DB options into :class:`DatabaseConfig`."""

    host = config.db_host.strip()
    if not host:
        raise ValueError("DBHost must be configured in hlstats.conf")

    port = 3306
    if ":" in host:
        host, port_text = host.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError as exc:  # pragma: no cover - defensive configuration handling
            raise ValueError(f"Invalid DBHost value '{config.db_host}': port must be numeric") from exc
        host = host.strip()
        if not host:
            raise ValueError("DBHost must include a hostname when specifying a port")

    return DatabaseConfig(
        host=host,
        port=port,
        username=config.db_username,
        password=config.db_password,
        database=config.db_name,
    )


def build_components(
    config: ProxyConfig,
    *,
    log_level: LogLevel,
    heartbeat_interval: float = 30.0,
    timezone: tzinfo | None = None,
) -> ProxyDaemonComponents:
    """Instantiate the concrete objects wired into :class:`ProxyDaemon`."""

    db_config = database_config_from_proxy_config(config)
    database = DatabaseAdapter(db_config)
    logger = ProxyLogger(LoggerConfig(level=log_level, timezone=timezone))
    balancer = ServerBalancer()
    heartbeat = HeartbeatManager(heartbeat_interval, logger=logger)
    transport = ProxyUdpServer(logger)
    daemon = ProxyDaemon(config, database, balancer, heartbeat, transport, logger)

    return ProxyDaemonComponents(
        config=config,
        logger=logger,
        database=database,
        balancer=balancer,
        heartbeat=heartbeat,
        transport=transport,
        daemon=daemon,
    )


__all__ = ["ProxyDaemonComponents", "database_config_from_proxy_config", "build_components"]
