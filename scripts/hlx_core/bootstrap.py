"""Shared runtime bootstrap helpers for the HLstatsX Python product lane."""

from __future__ import annotations

from .config import ProxyConfig
from .db import DatabaseConfig


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


__all__ = ["database_config_from_proxy_config"]
