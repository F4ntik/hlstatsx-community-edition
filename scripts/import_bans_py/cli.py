"""Standalone ImportBans replacement for HLstatsX in Python."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

from proxy_daemon_py.config import ConfigError, load_config
from proxy_daemon_py.db import DatabaseConfig, DatabaseError, SyncDatabaseAdapter


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """One external ban source configured by CLI flags."""

    source: str
    host: str
    port: int
    user: str
    password: str
    database: str
    table_prefix: str

    def label(self) -> str:
        return _SOURCE_LABELS[self.source]


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Validated CLI settings for one ImportBans run."""

    configfile: Path
    dry_run: bool
    sources: list[SourceConfig]


_SOURCE_LABELS: Final[dict[str, str]] = {
    "sourcebans": "SourceBans",
    "amxbans": "AMXBans",
    "beetlesmod": "BeetlesMod",
    "globalban": "ES GlobalBan",
}


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for ``import_bans_py``."""

    p = argparse.ArgumentParser(
        prog="python -m import_bans_py",
        description="Import permanent external bans into hlstats_Players.hideranking=2.",
    )
    p.add_argument("--configfile", type=Path, required=True, help="Path to hlstats.conf for HLstats DB")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not update HLstats DB; print how many unique IDs would be marked banned.",
    )

    _add_source_flags(p, source="sourcebans", default_prefix="sb_")
    _add_source_flags(p, source="amxbans", default_prefix="amx_")
    _add_source_flags(p, source="beetlesmod", default_prefix="bm_")
    _add_source_flags(p, source="globalban", default_prefix="gban_")
    return p


def load_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Parse and validate CLI options."""

    parsed = build_parser().parse_args(list(argv) if argv is not None else None)
    sources: list[SourceConfig] = []
    for source in _SOURCE_LABELS:
        cfg = _parse_source_config(parsed, source)
        if cfg is not None:
            sources.append(cfg)

    if not sources:
        raise ConfigError("At least one ban source must be configured (e.g. --sourcebans-db-name ...)")

    return RuntimeSettings(
        configfile=parsed.configfile,
        dry_run=bool(parsed.dry_run),
        sources=sources,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    try:
        settings = load_settings(argv)
    except (ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        hlx_config = load_config(settings.configfile)
    except (FileNotFoundError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    hlx_db = SyncDatabaseAdapter(
        DatabaseConfig(
            host=_parse_host_from_db_host(hlx_config.db_host),
            port=_parse_port_from_db_host(hlx_config.db_host),
            username=hlx_config.db_username,
            password=hlx_config.db_password,
            database=hlx_config.db_name,
        )
    )
    source_ids: list[str] = []

    print("++ ImportBans Python run starting...")
    for source in settings.sources:
        print(f"-- Connecting to {source.label()} database '{source.database}' on '{source.host}:{source.port}' ... ", end="")
        try:
            ids = _fetch_source_ids(source)
        except (DatabaseError, RuntimeError) as exc:
            print("failed")
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print("ok")
        print(f"   Retrieved {len(ids)} Steam IDs from {source.label()}.")
        source_ids.extend(ids)

    normalized_ids = _normalize_unique_ids(source_ids)
    if not normalized_ids:
        print("No banned users found in configured source databases; nothing to update.")
        return 1

    print(f"-- Unique normalized Steam IDs ready for import: {len(normalized_ids)}")
    if settings.dry_run:
        print(f"-- Dry-run: would mark {len(normalized_ids)} IDs as hideranking=2 in HLstats.")
        return 0

    try:
        updated = _update_hlx_bans(hlx_db, normalized_ids)
    except DatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"++ {updated} users newly marked as banned in HLstats.")
    print("++ ImportBans Python run complete.")
    return 0


def _add_source_flags(parser: argparse.ArgumentParser, *, source: str, default_prefix: str) -> None:
    parser.add_argument(f"--{source}-db-host", default="localhost")
    parser.add_argument(f"--{source}-db-port", type=int, default=3306)
    parser.add_argument(f"--{source}-db-user")
    parser.add_argument(f"--{source}-db-password")
    parser.add_argument(f"--{source}-db-name")
    parser.add_argument(
        f"--{source}-table-prefix",
        default=default_prefix,
        help=f"Table prefix for {source} tables (default: {default_prefix})",
    )


def _parse_source_config(parsed: argparse.Namespace, source: str) -> SourceConfig | None:
    db_name = getattr(parsed, f"{source}_db_name")
    user = getattr(parsed, f"{source}_db_user")
    password = getattr(parsed, f"{source}_db_password")

    if db_name is None and user is None and password is None:
        return None
    if not db_name or not user or password is None:
        raise ConfigError(
            f"Incomplete {source} connection settings: provide --{source}-db-name, "
            f"--{source}-db-user, and --{source}-db-password"
        )
    port = int(getattr(parsed, f"{source}_db_port"))
    if port <= 0 or port > 65535:
        raise ConfigError(f"Invalid --{source}-db-port: {port}")

    return SourceConfig(
        source=source,
        host=str(getattr(parsed, f"{source}_db_host")),
        port=port,
        user=str(user),
        password=str(password),
        database=str(db_name),
        table_prefix=str(getattr(parsed, f"{source}_table_prefix")),
    )


def _fetch_source_ids(source: SourceConfig) -> list[str]:
    db = SyncDatabaseAdapter(
        config=DatabaseConfig(
            host=source.host,
            port=source.port,
            username=source.user,
            password=source.password,
            database=source.database,
        )
    )
    try:
        db.connect()
        conn = db.connection()
        cursor = conn.cursor()
        try:
            query = _source_query(source)
            cursor.execute(query)
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        db.close()
    return [str(row[0]).strip() for row in rows if row and row[0]]


def _source_query(source: SourceConfig) -> str:
    prefix = source.table_prefix
    if source.source == "sourcebans":
        return (
            "SELECT `authid` "
            f"FROM `{prefix}bans` "
            "WHERE `length` = 0 AND `RemovedBy` IS NULL"
        )
    if source.source == "amxbans":
        return (
            f"SELECT `player_id` FROM `{prefix}bans` "
            "WHERE `ban_length` = 0"
        )
    if source.source == "beetlesmod":
        return (
            f"SELECT `steamid` FROM `{prefix}bans` "
            "WHERE `Until` IS NULL"
        )
    if source.source == "globalban":
        return (
            f"SELECT `steam_id` FROM `{prefix}ban` "
            "WHERE `active` = 1 AND `pending` = 0 AND `length` = 0"
        )
    raise RuntimeError(f"Unsupported source {source.source}")


def _normalize_unique_ids(source_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in source_ids:
        cleaned = value.strip()
        if not cleaned:
            continue
        if cleaned.upper().startswith("STEAM_"):
            _, _, tail = cleaned.partition(":")
            cleaned = tail or cleaned
        cleaned = cleaned.upper()
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _update_hlx_bans(hlx_db: SyncDatabaseAdapter, unique_ids: list[str]) -> int:
    hlx_db.connect()
    try:
        conn = hlx_db.connection()
        cursor = conn.cursor()
        try:
            placeholders = ",".join(["%s"] * len(unique_ids))
            query = (
                "UPDATE `hlstats_Players` "
                "SET `hideranking` = 2 "
                "WHERE `playerId` IN ("
                "SELECT `playerId` FROM `hlstats_PlayerUniqueIds` "
                f"WHERE `uniqueId` IN ({placeholders})"
                ") AND `hideranking` < 2"
            )
            cursor.execute(query, tuple(unique_ids))
            return int(cursor.rowcount)
        finally:
            cursor.close()
    finally:
        hlx_db.close()


def _parse_port_from_db_host(db_host: str) -> int:
    host = db_host.strip()
    if ":" not in host:
        return 3306
    _, _, port_text = host.rpartition(":")
    try:
        return int(port_text)
    except ValueError as exc:
        raise ConfigError(f"Invalid DBHost value '{db_host}'") from exc


def _parse_host_from_db_host(db_host: str) -> str:
    host = db_host.strip()
    if ":" in host:
        host, _, _ = host.rpartition(":")
        host = host.strip()
    if not host:
        raise ConfigError("DBHost must include hostname")
    return host
