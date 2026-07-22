"""Focused durable-checkpoint transaction tests without a live MySQL server."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hlstats_ftp_py.checkpoint import (
    CheckpointCommitUncertainError,
    CheckpointSchemaError,
    DurableFtpCheckpoint,
    checkpoint_identity,
)
from hlstats_ftp_py.core import LogFileEntry


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self._connection = connection

    def execute(self, query: str, params=None) -> None:
        self._connection.actions.append(("sql", query, params))

    def fetchone(self):
        return self._connection.fetchone_result

    def fetchall(self):
        return self._connection.fetchall_result

    def close(self) -> None:
        self._connection.actions.append(("cursor-close",))


class _Connection:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.actions: list[tuple[object, ...]] = []
        self.fail_commit = fail_commit
        self.fetchone_result = None
        self.fetchall_result = []

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def autocommit(self, value: bool) -> None:
        self.actions.append(("autocommit", value))

    def commit(self) -> None:
        self.actions.append(("commit",))
        if self.fail_commit:
            raise OSError("lost MySQL acknowledgement")

    def rollback(self) -> None:
        self.actions.append(("rollback",))


class _Adapter:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self.actions: list[bool] = []

    def connection(self) -> _Connection:
        return self._connection

    def set_skip_connection_ping(self, enabled: bool) -> None:
        self.actions.append(enabled)


def _checkpoint(connection: _Connection) -> DurableFtpCheckpoint:
    return DurableFtpCheckpoint(
        _Adapter(connection),
        source_key=checkpoint_identity(
            game_server_ip="127.0.0.1",
            game_server_port=27015,
            ftp_host="127.0.0.1",
            ftp_port=21,
            ftp_dir="/logs",
        ),
    )


def test_checkpoint_advance_is_issued_before_its_commit() -> None:
    connection = _Connection()
    adapter = _Adapter(connection)
    checkpoint = DurableFtpCheckpoint(adapter, source_key="test")

    checkpoint.begin()
    checkpoint.advance(LogFileEntry("L0000001.log", 123.25))
    checkpoint.commit()

    actions = connection.actions
    advance_index = next(index for index, action in enumerate(actions) if action[0] == "sql")
    commit_index = actions.index(("commit",))
    assert actions[0] == ("autocommit", False)
    assert advance_index < commit_index
    assert actions[-1] == ("autocommit", True)
    assert adapter.actions == [True, False]


def test_unacknowledged_commit_rolls_back_where_possible_and_is_fail_closed() -> None:
    connection = _Connection(fail_commit=True)
    adapter = _Adapter(connection)
    checkpoint = DurableFtpCheckpoint(adapter, source_key="test")
    checkpoint.begin()
    checkpoint.advance(LogFileEntry("L0000001.log", 123.25))

    with pytest.raises(CheckpointCommitUncertainError, match="outcome is unknown"):
        checkpoint.commit()

    assert ("commit",) in connection.actions
    assert ("rollback",) in connection.actions
    assert checkpoint.transaction_active is False
    assert adapter.actions == [True, False]


def test_mixed_engine_import_write_schema_is_rejected_before_default_ftp_mode() -> None:
    connection = _Connection()
    connection.fetchone_result = ("InnoDB",)
    connection.fetchall_result = [("hlstats_Players", "MyISAM")]
    checkpoint = _checkpoint(connection)

    with pytest.raises(CheckpointSchemaError, match="non_innodb=hlstats_Players"):
        checkpoint.verify_schema()

    assert any("TABLE_NAME IN" in str(action[1]) for action in connection.actions if action[0] == "sql")


def test_transactional_schema_gate_covers_every_event_storage_write_table() -> None:
    storage_source = Path("scripts/hlstats_py/storage.py").read_text(encoding="utf-8")
    written_tables = set(
        re.findall(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+`?(hlstats_[A-Za-z0-9_]+)",
            storage_source,
        )
    )

    assert written_tables <= set(DurableFtpCheckpoint._MUTATED_TABLES)
