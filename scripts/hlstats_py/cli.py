"""CLI helpers for the runnable HLstats Python worker."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from proxy_daemon_py.config import ConfigError, ProxyConfig, load_config
from proxy_daemon_py.log import LogLevel, level_from_debug


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Structured result of command line parsing."""

    configfile: Path
    debug: bool
    foreground: bool
    bind_ip: str | None
    port: int | None


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Merged settings used to construct the worker runtime."""

    config: ProxyConfig
    cli: CliOptions
    log_level: LogLevel
    bind_ip: str | None
    port: int


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser matching the supported worker options."""

    parser = argparse.ArgumentParser(prog="hlstats-py")
    parser.add_argument(
        "--configfile",
        type=Path,
        required=True,
        help="Path to hlstats.conf",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging regardless of DebugLevel",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in the foreground instead of daemonizing",
    )
    parser.add_argument(
        "--ip",
        dest="bind_ip",
        help="Override BindIP from hlstats.conf",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override Port from hlstats.conf",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse *argv* into :class:`CliOptions`."""

    parsed = build_parser().parse_args(list(argv) if argv is not None else None)
    return CliOptions(
        configfile=parsed.configfile,
        debug=parsed.debug,
        foreground=parsed.foreground,
        bind_ip=parsed.bind_ip,
        port=parsed.port,
    )


def load_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Load configuration and apply CLI overrides."""

    options = parse_args(argv)
    config = load_config(options.configfile)
    bind_ip = options.bind_ip if options.bind_ip is not None else config.bind_ip
    port = options.port if options.port is not None else config.port
    if port <= 0 or port > 65535:
        raise ConfigError("Port must be between 1 and 65535")
    log_level = level_from_debug(options.debug, config.debug_level)
    return RuntimeSettings(
        config=config,
        cli=options,
        log_level=log_level,
        bind_ip=bind_ip,
        port=port,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate configuration for ``python -m hlstats_py.cli``."""

    try:
        load_settings(argv)
    except (FileNotFoundError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess tests
    raise SystemExit(main())
