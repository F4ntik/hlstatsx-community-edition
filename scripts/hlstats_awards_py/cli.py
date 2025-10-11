"""Command line interface for the Python hlstats-awards script."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum, auto
from pathlib import Path
from typing import Final

from proxy_daemon_py.config import ConfigError, ProxyConfig, load_config

DEFAULT_CONFIG_PATH: Final[Path] = Path("./hlstats.conf")


class AwardsCliError(RuntimeError):
    """Raised when the CLI arguments are semantically invalid."""


class AwardsAction(Enum):
    """Discrete tasks that the awards script can execute."""

    INACTIVE = auto()
    AWARDS = auto()
    RIBBONS = auto()
    GEOIP = auto()
    CLANS = auto()
    PRUNE = auto()
    OPTIMIZE = auto()


DEFAULT_ACTIONS: Final[frozenset[AwardsAction]] = frozenset(
    {
        AwardsAction.INACTIVE,
        AwardsAction.AWARDS,
        AwardsAction.RIBBONS,
        AwardsAction.PRUNE,
    }
)


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Structured representation of parsed command line arguments."""

    configfile: Path | None
    requested_actions: tuple[AwardsAction, ...]
    numdays: int
    date: date | None
    db_host: str | None
    db_name: str | None
    db_username: str | None
    db_password: str | None
    verbose: bool
    version: bool


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Database connection parameters extracted from configuration files."""

    host: str
    name: str
    username: str
    password: str
    cpanel_hack: bool


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Bundle combining configuration and runtime directives."""

    cli: CliOptions
    actions: frozenset[AwardsAction]
    database: DatabaseConfig
    config_path: Path | None


_DEF_DB: Final[dict[str, object]] = {
    "host": "",
    "name": "hlstats",
    "username": "",
    "password": "",
    "cpanel_hack": False,
}


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser mirroring the Perl script options."""

    parser = argparse.ArgumentParser(prog="hlstats-awards")
    parser.add_argument(
        "--configfile",
        "-c",
        type=Path,
        help="Path to hlstats.conf whose values override command line options",
    )
    parser.add_argument(
        "--numdays",
        type=_positive_int,
        default=1,
        help="Number of days in the awards evaluation window",
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        help="Calculate awards using statistics prior to the given date (YYYY-MM-DD)",
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
        "--verbose",
        action="store_true",
        help="Enable verbose output for troubleshooting",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="store_true",
        help="Print the script version and exit",
    )

    parser.set_defaults(requested_actions=[])
    for option, action, help_text in _ACTION_OPTIONS:
        parser.add_argument(
            *option,
            dest="requested_actions",
            action="append_const",
            const=action,
            help=help_text,
        )

    return parser


_ACTION_OPTIONS: Final[tuple[tuple[tuple[str, ...], AwardsAction, str], ...]] = (
    (
        ("-i", "--inactive"),
        AwardsAction.INACTIVE,
        "Update player activity and deactivate inactive players",
    ),
    (("-a", "--awards"), AwardsAction.AWARDS, "Process daily awards"),
    (("-r", "--ribbons"), AwardsAction.RIBBONS, "Process ribbons"),
    (("-g", "--geoip"), AwardsAction.GEOIP, "Update missing GeoIP entries"),
    (("-t", "--clans"), AwardsAction.CLANS, "Update clan statistics"),
    (("-p", "--prune"), AwardsAction.PRUNE, "Prune expired events and sessions"),
    (("-o", "--optimize"), AwardsAction.OPTIMIZE, "Optimize database tables"),
)


def parse_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse ``argv`` and return the structured :class:`CliOptions`."""

    parsed = build_parser().parse_args(list(argv) if argv is not None else None)
    requested_actions = tuple(parsed.requested_actions)

    return CliOptions(
        configfile=parsed.configfile,
        requested_actions=requested_actions,
        numdays=parsed.numdays,
        date=parsed.date,
        db_host=parsed.db_host,
        db_name=parsed.db_name,
        db_username=parsed.db_username,
        db_password=parsed.db_password,
        verbose=parsed.verbose,
        version=parsed.version,
    )


def load_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Combine CLI parsing with configuration loading and precedence rules."""

    options = parse_args(argv)

    config_data = dict(_DEF_DB)
    config_path: Path | None = None

    default_config = _load_optional_config(DEFAULT_CONFIG_PATH)
    if default_config is not None:
        config_data.update(_proxy_to_dict(default_config))
        config_path = default_config.config_path

    _apply_cli_overrides(config_data, options)

    if options.configfile is not None:
        override_config = load_config(options.configfile)
        config_data.update(_proxy_to_dict(override_config))
        config_path = override_config.config_path

    database = DatabaseConfig(
        host=str(config_data["host"]),
        name=str(config_data["name"]),
        username=str(config_data["username"]),
        password=str(config_data["password"]),
        cpanel_hack=bool(config_data["cpanel_hack"]),
    )

    actions = frozenset(options.requested_actions) or DEFAULT_ACTIONS

    return RuntimeSettings(cli=options, actions=actions, database=database, config_path=config_path)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m hlstats_awards_py.cli``."""

    try:
        load_settings(argv)
    except (FileNotFoundError, ConfigError, AwardsCliError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise argparse.ArgumentTypeError("expected integer value") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _parse_date(value: str) -> date:
    try:
        year, month, day = map(int, value.split("-"))
        return date(year, month, day)
    except ValueError as exc:  # pragma: no cover - defensive
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD date") from exc


def _load_optional_config(path: Path) -> ProxyConfig | None:
    try:
        return load_config(path)
    except FileNotFoundError:
        return None


def _proxy_to_dict(config: ProxyConfig) -> Mapping[str, object]:
    return {
        "host": config.db_host,
        "name": config.db_name,
        "username": config.db_username,
        "password": config.db_password,
        "cpanel_hack": config.cpanel_hack,
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

