from __future__ import annotations

import pytest

from heatmap_projection_migrate import (
    apply_migration_atomically,
    legacy_rotate_one_update,
    migration_sql,
    parse_args,
    validate_rotate_distribution,
)


class _MigrationCursor:
    def __init__(self, *, fail_on_second: bool = False) -> None:
        self.executed: list[str] = []
        self.fail_on_second = fail_on_second

    def execute(self, statement: str) -> None:
        self.executed.append(statement)
        if self.fail_on_second and len(self.executed) == 2:
            raise RuntimeError("synthetic marker failure")


class _MigrationConnection:
    def __init__(self) -> None:
        self.autocommit_values: list[bool] = []
        self.commits = 0
        self.rollbacks = 0

    def autocommit(self, value: bool) -> None:
        self.autocommit_values.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_legacy_rotate_one_update_preserves_old_projection() -> None:
    assert legacy_rotate_one_update(flipy=0, yoffset=2400) == (1, -2400)
    assert legacy_rotate_one_update(flipy=1, yoffset=-2400) == (0, 2400)


def test_distribution_guard_allows_only_legacy_zero_one() -> None:
    validate_rotate_distribution({0: 12, 1: 4})

    with pytest.raises(RuntimeError, match="manual classification"):
        validate_rotate_distribution({0: 12, 1: 4, 2: 1})


def test_migration_sql_is_explicit_and_versioned() -> None:
    update, marker = migration_sql()
    assert "flipy = 1 - flipy" in update
    assert "yoffset = -yoffset" in update
    assert "heatmap_projection_version" in marker
    assert "VALUES ('heatmap_projection_version', '2')" in marker


def test_apply_rejects_filtered_distribution() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--configfile",
                "hlstats.conf",
                "--game",
                "cstrike",
                "--apply",
                "--runtime-gate-approved",
            ]
        )


def test_apply_requires_explicit_runtime_gate() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--configfile", "hlstats.conf", "--apply"])


def test_apply_migration_rolls_back_when_marker_fails() -> None:
    connection = _MigrationConnection()
    cursor = _MigrationCursor(fail_on_second=True)

    with pytest.raises(RuntimeError, match="synthetic marker failure"):
        apply_migration_atomically(connection, cursor)

    assert len(cursor.executed) == 2
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.autocommit_values == [False, True]
