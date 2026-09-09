"""Opt-in MariaDB checks for runtime identity and online-event atomicity.

The fixture deletes data from the named runtime tables. It is deliberately
disabled unless both isolation switches are set for a disposable database.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from hlstats_py import EventContext, LocalizationCatalog, PlayerDescriptor, parse_log_event
from hlstats_py.events import ChatEventHandler, EventDispatcher, GameSchema
from hlstats_py.storage import EventStorage, StorageError

_IDENTITY_TABLES = (
    "hlstats_PlayerNames",
    "hlstats_Players_History",
    "hlstats_PlayerUniqueIds",
    "hlstats_Players",
)
_ONLINE_EVENT_TABLES = (
    "hlstats_Events_Chat",
    "hlstats_PlayerNames",
    "hlstats_Players_History",
    "hlstats_PlayerUniqueIds",
    "hlstats_Players",
    "hlstats_Servers",
)
_EVENT_EFFECT_TABLES = (
    "hlstats_Players",
    "hlstats_PlayerUniqueIds",
    "hlstats_PlayerNames",
    "hlstats_Players_History",
    "hlstats_Events_Chat",
)
_REQUIRED_ENVIRONMENT = (
    "HLSTATS_MARIADB_HOST",
    "HLSTATS_MARIADB_PORT",
    "HLSTATS_MARIADB_USER",
    "HLSTATS_MARIADB_PASSWORD",
    "HLSTATS_MARIADB_DATABASE",
)
_WRITE_TABLE_RE = re.compile(
    r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+\x60?([A-Za-z_]+)",
    re.IGNORECASE,
)


class _ConnectionAdapter:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def connection(self) -> Any:
        return self._connection


class _InjectedWriteFailure(RuntimeError):
    """Signal a deterministic fault after two distinct write tables."""


class _FaultInjectingCursor:
    def __init__(self, connection: _FaultInjectingConnection, cursor: Any) -> None:
        self._connection = connection
        self._cursor = cursor

    def execute(self, query: str, params: Any = None) -> Any:
        match = _WRITE_TABLE_RE.match(query)
        table = match.group(1) if match else None
        if table and table not in self._connection.successful_write_tables:
            if len(self._connection.successful_write_tables) >= 2:
                raise _InjectedWriteFailure("fault injected after two distinct database write steps")
            self._connection.successful_write_tables.add(table)
        if params is None:
            return self._cursor.execute(query)
        return self._cursor.execute(query, params)

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> Any:
        return self._cursor.fetchall()

    def close(self) -> None:
        self._cursor.close()


class _FaultInjectingConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.successful_write_tables: set[str] = set()

    def cursor(self) -> _FaultInjectingCursor:
        return _FaultInjectingCursor(self, self._connection.cursor())

    def autocommit(self, enabled: bool) -> None:
        self._connection.autocommit(enabled)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _new_connection() -> Any:
    import MySQLdb

    return MySQLdb.connect(
        host=os.environ["HLSTATS_MARIADB_HOST"],
        port=int(os.environ["HLSTATS_MARIADB_PORT"]),
        user=os.environ["HLSTATS_MARIADB_USER"],
        passwd=os.environ["HLSTATS_MARIADB_PASSWORD"],
        db=os.environ["HLSTATS_MARIADB_DATABASE"],
        charset="utf8mb4",
    )


def _clear_rows(connection: Any, tables: tuple[str, ...]) -> None:
    cursor = connection.cursor()
    try:
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")
    finally:
        cursor.close()


@pytest.fixture()
def maria_connection() -> Iterator[Any]:
    if os.environ.get("HLSTATS_MARIADB_INTEGRATION") != "1":
        pytest.skip("set HLSTATS_MARIADB_INTEGRATION=1 for disposable MariaDB coverage")
    if os.environ.get("HLSTATS_MARIADB_INTEGRATION_ISOLATED") != "1":
        pytest.skip("MariaDB target must declare HLSTATS_MARIADB_INTEGRATION_ISOLATED=1")
    missing = [name for name in _REQUIRED_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        pytest.skip("MariaDB integration target is incomplete: " + ", ".join(missing))

    connection = _new_connection()
    connection.autocommit(True)
    _clear_rows(connection, _ONLINE_EVENT_TABLES)
    try:
        yield connection
    finally:
        _clear_rows(connection, _ONLINE_EVENT_TABLES)
        connection.close()


def _context(game: str, *, map_name: str = "de_identity") -> EventContext:
    return EventContext(
        server_id=1,
        game=game,
        schema=GameSchema(game=game),
        localization=LocalizationCatalog(templates={}, default_template="{event_code}"),
        extras={"map": map_name},
    )


def _insert_server(connection: Any) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO hlstats_Servers "
            "(serverId, address, port, name, game, act_map) "
            "VALUES (1, '127.0.0.1', 27015, 'Atomicity Gate', 'csgo', 'de_atomic')"
        )
    finally:
        cursor.close()


def _chat_update(context: EventContext) -> Any:
    event = parse_log_event(
        'L 07/28/2026 - 12:00:00: "Atomic Alice<7><STEAM_1:1:4242><CT>" say "atomic gate"'
    )
    return EventDispatcher([ChatEventHandler()]).dispatch(event, context)


def _event_effect_counts(connection: Any) -> dict[str, int]:
    cursor = connection.cursor()
    try:
        counts: dict[str, int] = {}
        for table in _EVENT_EFFECT_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = int(cursor.fetchone()[0])
        return counts
    finally:
        cursor.close()


def test_real_rows_keep_same_steam_id_separate_per_game(maria_connection: Any) -> None:
    timestamp = datetime(2026, 7, 28, 12, 0, 0)
    stable = PlayerDescriptor(
        name="Identity Gate",
        user_id=7,
        unique_id="STEAM_1:1:4242",
        team="CT",
    )
    storage = EventStorage(_ConnectionAdapter(maria_connection), clock=lambda: timestamp)

    cstrike_player_id = storage._resolve_player_id(
        maria_connection, stable, _context("cstrike"), timestamp, timestamp
    )
    csgo_player_id = storage._resolve_player_id(
        maria_connection, stable, _context("csgo"), timestamp, timestamp
    )

    assert cstrike_player_id is not None
    assert csgo_player_id is not None
    assert cstrike_player_id != csgo_player_id

    cursor = maria_connection.cursor()
    try:
        cursor.execute("SELECT playerId, game FROM hlstats_PlayerUniqueIds ORDER BY game")
        assert set(cursor.fetchall()) == {
            (cstrike_player_id, "cstrike"),
            (csgo_player_id, "csgo"),
        }
    finally:
        cursor.close()


def test_online_event_write_fault_rolls_back_all_effects(maria_connection: Any) -> None:
    _insert_server(maria_connection)
    writer = _new_connection()
    writer.autocommit(True)
    faulting_writer = _FaultInjectingConnection(writer)
    context = _context("csgo", map_name="de_atomic")
    update = _chat_update(context)
    assert update is not None
    storage = EventStorage(_ConnectionAdapter(faulting_writer), clock=lambda: update.timestamp)

    storage.begin_online_event()
    try:
        with pytest.raises(StorageError, match="two distinct"):
            storage.record(update, context)
    finally:
        storage.abort_online_event()
        writer.close()

    assert len(faulting_writer.successful_write_tables) == 2
    assert _event_effect_counts(maria_connection) == {
        "hlstats_Players": 0,
        "hlstats_PlayerUniqueIds": 0,
        "hlstats_PlayerNames": 0,
        "hlstats_Players_History": 0,
        "hlstats_Events_Chat": 0,
    }
