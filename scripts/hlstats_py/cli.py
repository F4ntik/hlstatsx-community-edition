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
    stdin: bool
    server_ip: str | None
    server_port: int | None
    stdin_verbose_events: bool
    parser_backend: str
    stdin_transaction_batch_size: int


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Merged settings used to construct the worker runtime."""

    config: ProxyConfig
    cli: CliOptions
    log_level: LogLevel
    bind_ip: str | None
    port: int
    stdin: bool
    server_ip: str | None
    server_port: int | None
    stdin_verbose_events: bool
    parser_backend: str
    stdin_transaction_batch_size: int


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
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read raw legacy log lines from standard input instead of UDP",
    )
    parser.add_argument(
        "--server-ip",
        help="Source server IP to associate with --stdin log data",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        help="Source server port to associate with --stdin log data",
    )
    parser.add_argument(
        "--stdin-verbose-events",
        action="store_true",
        help="Emit per-event logs during --stdin import (debug only; slower)",
    )
    parser.add_argument(
        "--parser-backend",
        choices=("python", "native"),
        default="python",
        help="Parser backend for log decoding (default: python)",
    )
    parser.add_argument(
        "--stdin-transaction-batch-size",
        type=int,
        default=1000,
        help="Commit DB transaction every N stdin records (default: 1000; 0 disables batching)",
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
        stdin=parsed.stdin,
        server_ip=parsed.server_ip,
        server_port=parsed.server_port,
        stdin_verbose_events=parsed.stdin_verbose_events,
        parser_backend=parsed.parser_backend,
        stdin_transaction_batch_size=parsed.stdin_transaction_batch_size,
    )


def load_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Load configuration and apply CLI overrides."""

    options = parse_args(argv)
    config = load_config(options.configfile)
    bind_ip = options.bind_ip if options.bind_ip is not None else config.bind_ip
    port = options.port if options.port is not None else config.port
    if port <= 0 or port > 65535:
        raise ConfigError("Port must be between 1 and 65535")
    if options.stdin and (not options.server_ip or options.server_port is None):
        raise ConfigError("--stdin requires both --server-ip and --server-port")
    if options.server_port is not None and (options.server_port <= 0 or options.server_port > 65535):
        raise ConfigError("Server port must be between 1 and 65535")
    if options.stdin_transaction_batch_size < 0:
        raise ConfigError("--stdin-transaction-batch-size must be >= 0")
    log_level = level_from_debug(options.debug, config.debug_level)
    return RuntimeSettings(
        config=config,
        cli=options,
        log_level=log_level,
        bind_ip=bind_ip,
        port=port,
        stdin=options.stdin,
        server_ip=options.server_ip,
        server_port=options.server_port,
        stdin_verbose_events=options.stdin_verbose_events,
        parser_backend=options.parser_backend,
        stdin_transaction_batch_size=options.stdin_transaction_batch_size,
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
