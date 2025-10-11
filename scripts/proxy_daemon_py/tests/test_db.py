"""Tests for the database adapter layer."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from proxy_daemon_py import db

CONFIG = db.DatabaseConfig(
    host="db", port=3306, username="hlstats", password="secret", database="hlstatsx"
)


@dataclass(slots=True)
class QueryResponse:
    fetchall: list[tuple[object, ...]] | None = None
    fetchone: tuple[object, ...] | None = None


QueryKey = tuple[str, tuple[object, ...] | None]


@dataclass(slots=True)
class QueryStore:
    responses: dict[QueryKey, QueryResponse]
    executed: list[QueryKey]


class FakeCursor(db.SupportsCursor):
    """Cursor stub that serves pre-defined results for queries."""

    def __init__(self, store: QueryStore) -> None:
        self._store = store
        self._key: QueryKey | None = None

    def execute(self, query: str, params: Sequence[object] | None = None) -> None:
        normalized_params = tuple(params) if params is not None else None
        self._key = (query, normalized_params)
        self._store.executed.append(self._key)
        if self._key not in self._store.responses:
            raise AssertionError(f"Unexpected query {query!r} with params {params!r}")

    def fetchall(self) -> list[tuple[object, ...]]:
        assert self._key is not None
        response = self._store.responses[self._key]
        return list(response.fetchall or [])

    def fetchone(self) -> tuple[object, ...] | None:
        assert self._key is not None
        return self._store.responses[self._key].fetchone

    def close(self) -> None:  # pragma: no cover - API compatibility
        return None


class FakeConnection(db.SupportsConnection):
    def __init__(self, responses: dict[QueryKey, QueryResponse] | None = None) -> None:
        self._store = QueryStore(responses or {}, [])
        self.autocommit_value: bool | None = None
        self.closed = False
        self.pings = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._store)

    def autocommit(self, value: bool) -> None:
        self.autocommit_value = value

    def ping(self, reconnect: bool = False) -> bool:
        self.pings += 1
        return True

    def close(self) -> None:
        self.closed = True

    @property
    def executed(self) -> list[QueryKey]:
        return self._store.executed


Connector = Callable[..., db.SupportsConnection]


def connector_for(connection: FakeConnection) -> Connector:
    def _connect(**_: object) -> db.SupportsConnection:
        return connection

    return _connect


def test_sync_connect_retries_until_success() -> None:
    connection = FakeConnection()
    attempts: list[dict[str, object]] = []
    delays: list[float] = []

    def connector(**kwargs: object) -> db.SupportsConnection:
        attempts.append(kwargs)
        if len(attempts) < 3:
            raise OSError("connection failed")
        return connection

    adapter = db.SyncDatabaseAdapter(
        CONFIG,
        connector=connector,
        max_retries=2,
        retry_backoff=0.5,
        sleeper=delays.append,
    )

    adapter.connect()

    assert len(attempts) == 3
    assert attempts[-1]["host"] == CONFIG.host
    assert attempts[-1]["init_command"] == "SET NAMES 'utf8mb4'"
    assert connection.autocommit_value is True
    assert delays == [0.5, 1.0]


def test_connection_returns_existing_connection() -> None:
    connection = FakeConnection()
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))

    adapter.connect()

    assert adapter.connection() is connection


def test_sync_fetch_options_returns_mapping() -> None:
    responses: dict[QueryKey, QueryResponse] = {
        ("SELECT `keyname`, `value` FROM hlstats_Options", None): QueryResponse(
            fetchall=[("Proxy_Key", "abc"), ("Mode", 1)]
        )
    }
    connection = FakeConnection(responses)

    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    result = adapter.fetch_options()

    assert result == {"Proxy_Key": "abc", "Mode": "1"}
    assert connection.executed == [("SELECT `keyname`, `value` FROM hlstats_Options", None)]


def test_sync_fetch_proxy_key_requires_value() -> None:
    responses: dict[QueryKey, QueryResponse] = {
        ("SELECT `value` FROM hlstats_Options WHERE `keyname` = %s", ("Proxy_Key",)): QueryResponse(
            fetchone=None
        )
    }
    connection = FakeConnection(responses)
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    with pytest.raises(db.DatabaseError):
        adapter.fetch_proxy_key()


def test_sync_fetch_daemons_parses_entries() -> None:
    responses: dict[QueryKey, QueryResponse] = {
        (
            "SELECT `value` FROM hlstats_Options WHERE `keyname` = %s",
            ("Proxy_Daemons",),
        ): QueryResponse(fetchone=("10.0.0.1:27015, example.org:27016",))
    }
    connection = FakeConnection(responses)
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    result = adapter.fetch_daemons()

    assert result == [
        db.ProxyDaemonTarget(host="10.0.0.1", port=27015),
        db.ProxyDaemonTarget(host="example.org", port=27016),
    ]


def test_sync_fetch_daemons_validates_ports() -> None:
    responses: dict[QueryKey, QueryResponse] = {
        (
            "SELECT `value` FROM hlstats_Options WHERE `keyname` = %s",
            ("Proxy_Daemons",),
        ): QueryResponse(fetchone=("127.0.0.1:notaport",))
    }
    connection = FakeConnection(responses)
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    with pytest.raises(db.DatabaseError):
        adapter.fetch_daemons()


def test_sync_fetch_daemon_statuses_reads_rows() -> None:
    heartbeat = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    responses: dict[QueryKey, QueryResponse] = {
        (
            "SELECT `host`, `port`, `curstate`, `oldstate`, `last_heartbeat`, `latency_ms` "
            "FROM Proxy_Daemons ORDER BY `host`, `port`",
            None,
        ): QueryResponse(
            fetchall=[("alpha", 27015, "up", "down", heartbeat, 42)],
        )
    }
    connection = FakeConnection(responses)
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    result = adapter.fetch_daemon_statuses()

    assert result == [
        db.StoredProxyDaemon(
            host="alpha",
            port=27015,
            current_state="up",
            previous_state="down",
            last_heartbeat=heartbeat,
            latency_ms=42,
        )
    ]


def test_sync_fetch_servers_returns_expected_records() -> None:
    responses: dict[QueryKey, QueryResponse] = {
        (
            "SELECT `serverId`, `address`, `port`, `name`, `game` FROM hlstats_Servers ORDER BY `serverId`",
            None,
        ): QueryResponse(
            fetchall=[(1, "10.0.0.5", 27015, "Arena", "tf2")],
        )
    }
    connection = FakeConnection(responses)
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    result = adapter.fetch_servers()

    assert result == [
        db.GameServer(
            server_id=1,
            address="10.0.0.5",
            port=27015,
            name="Arena",
            game="tf2",
        )
    ]


def test_async_adapter_uses_runner() -> None:
    responses: dict[QueryKey, QueryResponse] = {
        ("SELECT `keyname`, `value` FROM hlstats_Options", None): QueryResponse(
            fetchall=[("Proxy_Key", "abc")]
        )
    }
    connection = FakeConnection(responses)

    calls: list[Callable[[], object]] = []

    async def runner(func: Callable[[], object]) -> object:
        calls.append(func)
        return func()

    adapter = db.DatabaseAdapter(
        CONFIG,
        connector=connector_for(connection),
        runner=runner,
    )

    async def run() -> None:
        await adapter.connect()
        options = await adapter.fetch_options()
        assert options == {"Proxy_Key": "abc"}

    asyncio.run(run())
    assert len(calls) >= 2


def test_sync_update_daemon_state_executes_upsert() -> None:
    heartbeat_at = datetime(2024, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
    normalized = datetime(2024, 1, 1, 12, 30, 0)

    responses: dict[QueryKey, QueryResponse] = {
        (
            db._UPSERT_DAEMON_STATE_QUERY,
            ("daemon.example.com", 27900, "up", "down", normalized, 120),
        ): QueryResponse()
    }
    connection = FakeConnection(responses)
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(connection))
    adapter.connect()

    adapter.update_daemon_state(
        db.ProxyDaemonState(
            host="daemon.example.com",
            port=27900,
            current_state="up",
            previous_state="down",
            checked_at=heartbeat_at,
            latency_ms=120,
        )
    )

    assert connection.executed == [
        (
            db._UPSERT_DAEMON_STATE_QUERY,
            ("daemon.example.com", 27900, "up", "down", normalized, 120),
        )
    ]


def test_sync_update_daemon_state_validates_inputs() -> None:
    adapter = db.SyncDatabaseAdapter(CONFIG, connector=connector_for(FakeConnection()))
    adapter.connect()

    with pytest.raises(ValueError):
        adapter.update_daemon_state(
            db.ProxyDaemonState(
                host=" ",
                port=27900,
                current_state="up",
                previous_state="down",
                checked_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(ValueError):
        adapter.update_daemon_state(
            db.ProxyDaemonState(
                host="daemon.example.com",
                port=70000,
                current_state="up",
                previous_state="down",
                checked_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(ValueError):
        adapter.update_daemon_state(
            db.ProxyDaemonState(
                host="daemon.example.com",
                port=27900,
                current_state="maybe",
                previous_state="down",
                checked_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(ValueError):
        adapter.update_daemon_state(
            db.ProxyDaemonState(
                host="daemon.example.com",
                port=27900,
                current_state="up",
                previous_state="down",
                checked_at=datetime.now(timezone.utc),
                latency_ms=-1,
            )
        )


def test_async_update_daemon_state_uses_runner() -> None:
    normalized = datetime(2024, 1, 1, 15, 0, 0)
    responses: dict[QueryKey, QueryResponse] = {
        (
            db._UPSERT_DAEMON_STATE_QUERY,
            ("daemon.example.com", 27900, "n/a", "n/a", normalized, None),
        ): QueryResponse()
    }
    connection = FakeConnection(responses)

    calls: list[Callable[[], object]] = []

    async def runner(func: Callable[[], object]) -> object:
        calls.append(func)
        return func()

    adapter = db.DatabaseAdapter(
        CONFIG,
        connector=connector_for(connection),
        runner=runner,
    )

    state = db.ProxyDaemonState(
        host="daemon.example.com",
        port=27900,
        current_state="n/a",
        previous_state="n/a",
        checked_at=datetime(2024, 1, 1, 15, 0, 0),
    )

    async def run() -> None:
        await adapter.update_daemon_state(state)

    asyncio.run(run())

    assert calls, "Runner should be invoked for the update call"
    assert connection.executed == [
        (
            db._UPSERT_DAEMON_STATE_QUERY,
            ("daemon.example.com", 27900, "n/a", "n/a", normalized, None),
        )
    ]
