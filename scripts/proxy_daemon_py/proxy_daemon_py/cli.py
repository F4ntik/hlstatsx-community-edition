"""Command line interface bootstrap for the Python proxy daemon."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, ProxyConfig, load_config
from .log import LogLevel, level_from_debug


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Structured result of command line parsing."""

    configfile: Path
    debug: bool
    foreground: bool


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Configuration bundle produced by CLI parsing."""

    config: ProxyConfig
    cli: CliOptions
    log_level: LogLevel


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser matching the Perl daemon options."""

    parser = argparse.ArgumentParser(prog="proxy-daemon")
    parser.add_argument(
        "--configfile",
        type=Path,
        required=True,
        help="Path to hlstats.conf",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (overrides configuration)",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in the foreground instead of daemonizing",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse *argv* and return the resulting :class:`CliOptions`."""

    parsed = build_parser().parse_args(list(argv) if argv is not None else None)
    return CliOptions(
        configfile=parsed.configfile,
        debug=parsed.debug,
        foreground=parsed.foreground,
    )


def load_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Combine CLI parsing with configuration loading."""

    options = parse_args(argv)
    config = load_config(options.configfile)
    log_level = level_from_debug(options.debug, config.debug_level)
    return RuntimeSettings(config=config, cli=options, log_level=log_level)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m proxy_daemon_py.cli``."""

    try:
        load_settings(argv)
    except (FileNotFoundError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess test
    raise SystemExit(main())
