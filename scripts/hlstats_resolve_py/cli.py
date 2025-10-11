"""Command line interface for the Python ``hlstats-resolve`` utility."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence

from proxy_daemon_py.config import ConfigError, ProxyConfig, load_config
from proxy_daemon_py.db import DatabaseError, SyncDatabaseAdapter

from .resolver import HostResolver, ResolveError, build_database_config

DEFAULT_CONFIG_PATH: Final[Path] = Path("./hlstats.conf")


class ResolveCliError(RuntimeError):
    """Raised when CLI arguments are semantically invalid."""


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Structured representation of raw command line options."""

    configfile: Path | None
    debug: int
    nodebug: int
    db_host: str | None
    db_name: str | None
    db_username: str | None
    db_password: str | None
    dns_timeout: int | None
    regroup: bool
    version: bool


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database configuration derived from CLI/config files."""

    host: str
    name: str
    username: str
    password: str
    cpanel_hack: bool


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Bundle combining CLI directives and derived configuration."""

    cli: CliOptions
    database: DatabaseConfig
    dns_timeout: int
    debug_level: int
    config_path: Path | None


_DEF_CONFIG: Final[dict[str, object]] = {
    "host": "",
    "name": "hlstats",
    "username": "",
    "password": "",
    "cpanel_hack": False,
    "dns_timeout": 5,
    "debug_level": 0,
}


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser mirroring the Perl script options."""

    parser = argparse.ArgumentParser(prog="hlstats-resolve")
    parser.add_argument(
        "--configfile",
        "-c",
        type=Path,
        help="Path to hlstats.conf whose values override the defaults",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="count",
        default=0,
        help="Increase debug verbosity (can be repeated)",
    )
    parser.add_argument(
        "--nodebug",
        "-n",
        action="count",
        default=0,
        help="Decrease debug verbosity (can be repeated)",
    )
    parser.add_argument(
        "--db-host",
        dest="db_host",
        help="Database host (host[:port])",
    )
    parser.add_argument(
        "--db-name",
        dest="db_name",
        help="Database name",
    )
    parser.add_argument(
        "--db-username",
        dest="db_username",
        help="Database username",
    )
    parser.add_argument(
        "--db-password",
        dest="db_password",
        help="Database password",
    )
    parser.add_argument(
        "--dns-timeout",
        type=_positive_int,
        dest="dns_timeout",
        help="Timeout DNS queries after the given number of seconds",
    )
    parser.add_argument(
        "--regroup",
        "-r",
        action="store_true",
        help="Only re-group hostnames without performing reverse DNS lookups",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="store_true",
        help="Print the script version and exit",
    )

    return parser


def parse_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse ``argv`` and return a :class:`CliOptions` instance."""

    parsed = build_parser().parse_args(list(argv) if argv is not None else None)
    return CliOptions(
        configfile=parsed.configfile,
        debug=int(parsed.debug),
        nodebug=int(parsed.nodebug),
        db_host=parsed.db_host,
        db_name=parsed.db_name,
        db_username=parsed.db_username,
        db_password=parsed.db_password,
        dns_timeout=parsed.dns_timeout,
        regroup=bool(parsed.regroup),
        version=bool(parsed.version),
    )


def load_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Combine CLI parsing with configuration file precedence rules."""

    options = parse_args(argv)
    config_data = dict(_DEF_CONFIG)
    config_path: Path | None = None

    default_config = _load_optional_config(DEFAULT_CONFIG_PATH)
    if default_config is not None:
        config_data.update(_proxy_to_dict(default_config))
        config_path = default_config.config_path

    if options.configfile is not None:
        override_config = load_config(options.configfile)
        config_data.update(_proxy_to_dict(override_config))
        config_path = override_config.config_path

    _apply_cli_overrides(config_data, options)

    debug_level = _derive_debug_level(config_data["debug_level"], options)
    dns_timeout = _derive_dns_timeout(config_data["dns_timeout"])

    database = DatabaseConfig(
        host=str(config_data["host"]),
        name=str(config_data["name"]),
        username=str(config_data["username"]),
        password=str(config_data["password"]),
        cpanel_hack=bool(config_data["cpanel_hack"]),
    )

    return RuntimeSettings(
        cli=options,
        database=database,
        dns_timeout=dns_timeout,
        debug_level=debug_level,
        config_path=config_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m hlstats_resolve_py.cli``."""

    try:
        settings = load_settings(argv)
    except (FileNotFoundError, ConfigError, ResolveCliError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if settings.cli.version:
        print("hlstats-resolve.py (Python port)")
        return 0

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db_config = build_database_config(settings)
    adapter = SyncDatabaseAdapter(db_config)

    print("++ HLstats Resolve (Python) starting...\n")
    print(
        f"-- Connecting to MySQL database '{db_config.database}' on '{db_config.host}:{db_config.port}' "
        f"as user '{db_config.username}' ... ",
        end="",
    )
    try:
        adapter.connect()
    except DatabaseError as exc:
        print("failed")
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("connected OK")
    print(f"-- DNS timeout is {settings.dns_timeout} seconds. Debug level is {settings.debug_level}.")

    resolver = HostResolver(
        adapter,
        dns_timeout=settings.dns_timeout,
        debug_level=settings.debug_level,
    )

    try:
        summary = resolver.run(regroup_only=settings.cli.regroup)
    except (ResolveError, DatabaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        adapter.close()

    if settings.cli.regroup:
        print(f"++ Re-grouped {summary.regrouped_hosts} hostnames.")
    else:
        print(
            "++ Processed {total} connects; resolved {resolved} new hostnames.".format(
                total=summary.total_connects,
                resolved=summary.resolved_ips,
            )
        )
    print("++ Operation complete.")
    return 0


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise argparse.ArgumentTypeError("expected integer value") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _load_optional_config(path: Path) -> ProxyConfig | None:
    try:
        return load_config(path)
    except FileNotFoundError:
        return None


def _proxy_to_dict(config: ProxyConfig) -> Mapping[str, object]:
    dns_timeout_raw = config.get("DNSTimeout")
    dns_timeout = dns_timeout_raw if dns_timeout_raw is not None else _DEF_CONFIG["dns_timeout"]

    return {
        "host": config.db_host,
        "name": config.db_name,
        "username": config.db_username,
        "password": config.db_password,
        "cpanel_hack": config.cpanel_hack,
        "dns_timeout": dns_timeout,
        "debug_level": config.debug_level,
    }


def _apply_cli_overrides(config_data: dict[str, object], options: CliOptions) -> None:
    if options.db_host is not None:
        config_data["host"] = options.db_host
    if options.db_name is not None:
        config_data["name"] = options.db_name
    if options.db_username is not None:
        config_data["username"] = options.db_username
    if options.db_password is not None:
        config_data["password"] = options.db_password
    if options.dns_timeout is not None:
        config_data["dns_timeout"] = options.dns_timeout


def _derive_debug_level(raw: object, options: CliOptions) -> int:
    try:
        base_level = int(raw)
    except (TypeError, ValueError) as exc:
        raise ResolveCliError("Debug level must be an integer") from exc

    level = base_level + options.debug - options.nodebug
    return max(level, 0)


def _derive_dns_timeout(raw: object) -> int:
    try:
        timeout = int(raw)
    except (TypeError, ValueError) as exc:
        raise ResolveCliError("DNS timeout must be an integer") from exc
    if timeout <= 0:
        raise ResolveCliError("DNS timeout must be greater than zero")
    return timeout


__all__ = [
    "CliOptions",
    "DatabaseConfig",
    "RuntimeSettings",
    "ResolveCliError",
    "build_parser",
    "load_settings",
    "main",
]
