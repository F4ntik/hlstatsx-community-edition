"""Runtime helpers for constructing the proxy daemon stack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo

from hlx_core.bootstrap import database_config_from_proxy_config

from .balancer import ServerBalancer
from .config import ProxyConfig
from .daemon import ProxyDaemon
from .db import DatabaseAdapter
from .heartbeat import HeartbeatManager
from .log import LogLevel, LoggerConfig, ProxyLogger
from .transport import ProxyUdpServer

# TODO(proxy-daemon-py/env-bootstrap): добавить чтение переменных окружения
# HLSTATS_CONF, PY_PROXY_DAEMON_LOG_LEVEL и PROM_PUSHGATEWAY для автоматизации
# запуска в эксплуатационных средах.


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
