"""Guarded versioned migration from the legacy heatmap rotate=1 transform.

The current contract treats rotate as a real quarter-turn matrix. Legacy
rotate=1 was a diagonal swap. For rows that are still legacy 0/1, toggling
flipy and negating yoffset makes the new rotate=1 matrix preserve that old
projection. Rows already using 2/3 require manual classification and are
never mass-updated by this tool.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from hlx_core.bootstrap import database_config_from_proxy_config
from hlx_core.config import load_config
from hlx_core.db import SyncDatabaseAdapter


LEGACY_PROJECTION_VERSION = 1
QUARTER_TURN_PROJECTION_VERSION = 2
PROJECTION_OPTION = "heatmap_projection_version"


def validate_rotate_distribution(distribution: Mapping[int, int]) -> None:
    """Reject unsupported stored rotate steps before any update is emitted."""

    unexpected = sorted(step for step, count in distribution.items() if count and step not in (0, 1))
    if unexpected:
        raise RuntimeError(
            "manual classification required before migration; stored rotate values include "
            + ", ".join(str(step) for step in unexpected)
        )


def legacy_rotate_one_update(*, flipy: int, yoffset: int) -> tuple[int, int]:
    """Return the version-2 values that preserve the version-1 projection."""

    return (0 if int(flipy) else 1, -int(yoffset))


def migration_sql() -> tuple[str, str]:
    """Return the guarded SQL statements used by the explicit apply gate."""

    return (
        "UPDATE hlstats_Heatmap_Config "
        "SET flipy = 1 - flipy, yoffset = -yoffset "
        "WHERE rotate = 1;",
        "INSERT INTO hlstats_Options (keyname, value) "
        "VALUES ('heatmap_projection_version', '2') "
        "ON DUPLICATE KEY UPDATE value = VALUES(value);",
    )


def apply_migration_atomically(connection, cursor) -> None:
    """Apply the row conversion and version marker as one transaction."""

    statements = migration_sql()
    connection.autocommit(False)
    try:
        cursor.execute(statements[0])
        cursor.execute(statements[1])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.autocommit(True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configfile", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply the guarded version-1 to version-2 update.")
    parser.add_argument(
        "--runtime-gate-approved",
        action="store_true",
        help="Explicitly acknowledge the separate runtime gate required by --apply.",
    )
    parser.add_argument("--game", help="Limit the reported distribution to one game code.")
    parser.add_argument("--map", dest="map_name", help="Limit the reported distribution to one map.")
    args = parser.parse_args(argv)
    if args.apply and not args.runtime_gate_approved:
        parser.error("--apply requires --runtime-gate-approved")
    if args.apply and (args.game or args.map_name):
        parser.error("--apply requires the unfiltered rotate distribution; use --game/--map for read-only inspection")
    return args


def _distribution_query(args: argparse.Namespace) -> tuple[str, tuple[object, ...]]:
    clauses = ["1=1"]
    params: list[object] = []
    if args.game:
        clauses.append("game = %s")
        params.append(args.game)
    if args.map_name:
        clauses.append("map = %s")
        params.append(args.map_name)
    return (
        "SELECT COALESCE(rotate, 0) AS rotate_step, COUNT(*) AS row_count "
        "FROM hlstats_Heatmap_Config WHERE " + " AND ".join(clauses) + " GROUP BY rotate_step ORDER BY rotate_step",
        tuple(params),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.configfile)
    adapter = SyncDatabaseAdapter(database_config_from_proxy_config(config))
    adapter.connect()
    try:
        connection = adapter.connection()
        cursor = connection.cursor()
        try:
            query, params = _distribution_query(args)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            distribution = {int(row[0]): int(row[1]) for row in rows}
            print("stored rotate distribution:", distribution or "<empty>")
            try:
                validate_rotate_distribution(distribution)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2

            cursor.execute(
                "SELECT value FROM hlstats_Options WHERE keyname = %s LIMIT 1",
                (PROJECTION_OPTION,),
            )
            version_row = cursor.fetchone()
            current_version = int(version_row[0]) if version_row and str(version_row[0]).strip() else LEGACY_PROJECTION_VERSION
            if current_version >= QUARTER_TURN_PROJECTION_VERSION:
                print(f"heatmap projection version {current_version} is already current")
                return 0
            if current_version != LEGACY_PROJECTION_VERSION:
                print(
                    f"error: unsupported heatmap projection version {current_version}; "
                    f"expected {LEGACY_PROJECTION_VERSION}",
                    file=sys.stderr,
                )
                return 2

            if not args.apply:
                print(
                    "dry-run only; after the runtime gate pass "
                    "--apply --runtime-gate-approved to migrate legacy 0/1 rows"
                )
                for statement in migration_sql():
                    print(statement)
                return 0

            apply_migration_atomically(connection, cursor)
            print(f"migrated heatmap projection version {LEGACY_PROJECTION_VERSION} -> {QUARTER_TURN_PROJECTION_VERSION}")
            return 0
        finally:
            cursor.close()
    finally:
        adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
