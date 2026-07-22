"""Configuration loading utilities for the Python proxy daemon."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


class ConfigError(RuntimeError):
    """Raised when the configuration file contains invalid contents."""


_LINE_RE = re.compile(r"^\s*(?P<key>\w+)\s+(?P<quote>['\"]?)(?P<value>.*?)(?P=quote)\s*$")

_DEFAULTS: Mapping[str, str] = MappingProxyType(
    {
        "DBHost": "",
        "DBUsername": "",
        "DBPassword": "",
        "DBName": "",
        "BindIP": "",
        "Port": "27500",
        "DebugLevel": "0",
        "EventQueueSize": "10",
        # This is intentionally distinct from the legacy proxy-daemon
        # EventQueueSize.  It bounds only the Python HLstats worker's UDP
        # ingress queue.
        "IngressQueueSize": "1000",
        "CpanelHack": "0",
    }
)


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """Container for configuration options parsed from ``hlstats.conf``."""

    config_path: Path
    db_host: str
    db_username: str
    db_password: str
    db_name: str
    bind_ip: str | None
    port: int
    debug_level: int
    event_queue_size: int
    ingress_queue_size: int
    cpanel_hack: bool
    raw: Mapping[str, str]

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the raw configuration value for ``key`` if present."""

        return self.raw.get(key, default)


def load_config(path: Path) -> ProxyConfig:
    """Load and validate configuration from ``path``.

    The parser mirrors the behaviour of ``ConfigReaderSimple`` that the Perl
    implementation used: configuration directives consist of a key followed by a
    value, optionally wrapped in single or double quotes.  Blank lines and lines
    starting with ``#`` are ignored.  Unknown keys are preserved in the ``raw``
    mapping so that future development can read extra options without modifying
    the parser.
    """

    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ConfigError(f"Configuration path '{path}' is not a file")

    raw: dict[str, str] = dict(_DEFAULTS)

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _LINE_RE.match(stripped)
            if match is None:
                raise ConfigError(f"Cannot parse configuration line {line_number}: {stripped!r}")

            raw[match.group("key")] = match.group("value")

    return _build_proxy_config(path.resolve(), raw)


def _build_proxy_config(config_path: Path, raw: Mapping[str, str]) -> ProxyConfig:
    """Construct a :class:`ProxyConfig` with type conversions applied."""

    port = _parse_int(raw.get("Port", ""), "Port")
    if port <= 0 or port > 65535:
        raise ConfigError("Port must be between 1 and 65535")

    debug_level = _parse_int(raw.get("DebugLevel", ""), "DebugLevel")
    event_queue_size = _parse_int(raw.get("EventQueueSize", ""), "EventQueueSize")
    if event_queue_size <= 0:
        raise ConfigError("EventQueueSize must be greater than zero")
    ingress_queue_size = _parse_int(raw.get("IngressQueueSize", ""), "IngressQueueSize")
    if ingress_queue_size <= 0:
        raise ConfigError("IngressQueueSize must be greater than zero")

    cpanel_hack = _parse_bool(raw.get("CpanelHack", ""), "CpanelHack")

    bind_ip = raw.get("BindIP", "").strip() or None

    frozen_raw: Mapping[str, str] = MappingProxyType(dict(raw))

    return ProxyConfig(
        config_path=config_path,
        db_host=raw.get("DBHost", ""),
        db_username=raw.get("DBUsername", ""),
        db_password=raw.get("DBPassword", ""),
        db_name=raw.get("DBName", ""),
        bind_ip=bind_ip,
        port=port,
        debug_level=debug_level,
        event_queue_size=event_queue_size,
        ingress_queue_size=ingress_queue_size,
        cpanel_hack=cpanel_hack,
        raw=frozen_raw,
    )


def _parse_int(value: str, key: str) -> int:
    try:
        return int(value)
    except ValueError as exc:  # pragma: no cover - defensive programming
        raise ConfigError(f"Invalid integer for {key!r}: {value!r}") from exc


def _parse_bool(value: str, key: str) -> bool:
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off", ""}:
        return False
    raise ConfigError(f"Invalid boolean for {key!r}: {value!r}")
