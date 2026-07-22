"""Database access layer for the Python proxy daemon."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, TypeVar, cast


class DatabaseError(RuntimeError):
    """Raised when database connectivity or queries fail."""


class SupportsCursor(Protocol):
    """Protocol describing cursor objects returned by DB-API connectors."""

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> Sequence[Any]: ...

    def executemany(self, query: str, params: Sequence[Sequence[Any]]) -> Any: ...

    def close(self) -> None: ...


class SupportsConnection(Protocol):
    """Protocol describing the connection object created by ``mysqlclient``."""

    def cursor(self) -> SupportsCursor: ...

    def autocommit(self, value: bool) -> Any: ...

    def ping(self, reconnect: bool = False) -> Any: ...

    def close(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """Connection parameters loaded from configuration."""

    host: str
    port: int
    username: str
    password: str
    database: str


@dataclass(frozen=True, slots=True)
class ProxyDaemonTarget:
    """Representation of a proxy sub-daemon entry fetched from the database."""

    host: str
    port: int


@dataclass(frozen=True, slots=True)
class ProxyDaemonState:
    """Health information for a proxy daemon obtained during heartbeat checks."""

    host: str
    port: int
    current_state: str
    previous_state: str
    checked_at: datetime
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class StoredProxyDaemon:
    """Row persisted in ``Proxy_Daemons`` representing daemon health."""

    host: str
    port: int
    current_state: str
    previous_state: str
    last_heartbeat: datetime | None
    latency_ms: int | None


@dataclass(frozen=True, slots=True)
class GameServer:
    """Minimal subset of fields describing a tracked game server."""

    server_id: int
    address: str
    port: int
    name: str
    game: str
    current_map: str = ""


_VALID_DAEMON_STATES = {"up", "down", "n/a"}

_UPSERT_DAEMON_STATE_QUERY = (
    "INSERT INTO Proxy_Daemons ("
    "`host`, `port`, `curstate`, `oldstate`, `last_heartbeat`, `latency_ms`) "
    "VALUES (%s, %s, %s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE "
    "`curstate` = %s, "
    "`oldstate` = %s, "
    "`last_heartbeat` = %s, "
    "`latency_ms` = %s, "
    "`updated_at` = CURRENT_TIMESTAMP"
)


class SyncDatabaseAdapter:
    """Synchronous database adapter mirroring the behaviour of ``HLstats.plib``."""

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        connector: Callable[..., SupportsConnection] | None = None,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        connect_timeout: float = 5.0,
        read_timeout: float = 5.0,
        write_timeout: float | None = None,
        enable_multi_statements: bool = False,
        executemany_chunk_size: int = 1000,
        import_mode: bool = False,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_backoff < 0:
            raise ValueError("retry_backoff must be non-negative")
        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        if read_timeout <= 0:
            raise ValueError("read_timeout must be positive")
        if executemany_chunk_size <= 0:
            raise ValueError("executemany_chunk_size must be positive")
        if enable_multi_statements and not import_mode:
            raise ValueError("enable_multi_statements requires import_mode=True")

        self._config = config
        self._connector = connector
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._enable_multi_statements = enable_multi_statements
        self._executemany_chunk_size = executemany_chunk_size
        self._import_mode = import_mode
        self._sleeper = sleeper or time.sleep
        self._connection: SupportsConnection | None = None
        self._skip_connection_ping: bool = False

    def set_skip_connection_ping(self, enabled: bool) -> None:
        """When True, reuse the pooled handle without ping checks (bulk import hot path)."""

        self._skip_connection_ping = bool(enabled)

    @property
    def executemany_chunk_size(self) -> int:
        return self._executemany_chunk_size

    def connect(self) -> None:
        """Establish a connection to MySQL, retrying with back-off on failures."""

        self._connection = self._connect_with_retries()

    def close(self) -> None:
        """Close the current database connection if one exists."""

        self._skip_connection_ping = False
        if self._connection is None:
            return
        try:
            self._connection.close()
        finally:
            self._connection = None

    def fetch_options(self) -> dict[str, str]:
        """Return all options stored in ``hlstats_Options`` as a mapping."""

        connection = self._ensure_connection()
        rows = self._fetchall(
            connection,
            "SELECT `keyname`, `value` FROM hlstats_Options",
        )
        return {str(key): "" if value is None else str(value) for key, value in rows}

    def fetch_proxy_key(self) -> str:
        """Fetch the proxy key used to validate administrative UDP commands."""

        connection = self._ensure_connection()
        row = self._fetchone(
            connection,
            "SELECT `value` FROM hlstats_Options WHERE `keyname` = %s",
            ("Proxy_Key",),
        )
        if not row or row[0] is None or not str(row[0]).strip():
            raise DatabaseError("Proxy key is not configured in hlstats_Options")
        return str(row[0])

    def fetch_daemons(self) -> list[ProxyDaemonTarget]:
        """Return the configured proxy sub-daemons ordered as stored in the DB."""

        connection = self._ensure_connection()
        row = self._fetchone(
            connection,
            "SELECT `value` FROM hlstats_Options WHERE `keyname` = %s",
            ("Proxy_Daemons",),
        )
        if not row or row[0] is None:
            return []
        return self._parse_daemon_list(str(row[0]))

    def fetch_daemon_statuses(self) -> list[StoredProxyDaemon]:
        """Return health information persisted in ``Proxy_Daemons``."""

        connection = self._ensure_connection()
        rows = self._fetchall(
            connection,
            "SELECT `host`, `port`, `curstate`, `oldstate`, `last_heartbeat`, `latency_ms` "
            "FROM Proxy_Daemons ORDER BY `host`, `port`",
        )
        statuses: list[StoredProxyDaemon] = []
        for host, port, curstate, oldstate, last_heartbeat, latency_ms in rows:
            statuses.append(
                StoredProxyDaemon(
                    host=str(host).strip(),
                    port=int(port),
                    current_state=str(curstate).strip(),
                    previous_state=str(oldstate).strip(),
                    last_heartbeat=last_heartbeat,
                    latency_ms=None if latency_ms is None else int(latency_ms),
                )
            )
        return statuses

    def fetch_servers(self) -> list[GameServer]:
        """Return the list of tracked game servers."""

        connection = self._ensure_connection()
        rows = self._fetchall(
            connection,
            "SELECT `serverId`, `address`, `port`, `name`, `game`, `act_map` "
            "FROM hlstats_Servers ORDER BY `serverId`",
        )
        servers: list[GameServer] = []
        for server_id, address, port, name, game, current_map in rows:
            servers.append(
                GameServer(
                    server_id=int(server_id),
                    address=str(address).strip(),
                    port=int(port),
                    name=str(name).strip(),
                    game=str(game).strip(),
                    current_map="" if current_map is None else str(current_map).strip(),
                )
            )
        return servers

    def update_daemon_state(self, state: ProxyDaemonState) -> None:
        """Persist heartbeat information for a proxy daemon."""

        host = state.host.strip()
        if not host:
            raise ValueError("host must be a non-empty string")
        if state.port <= 0 or state.port > 65535:
            raise ValueError("port must be in the 1-65535 range")
        if state.current_state not in _VALID_DAEMON_STATES:
            raise ValueError(
                "current_state must be one of 'up', 'down' or 'n/a'",
            )
        if state.previous_state not in _VALID_DAEMON_STATES:
            raise ValueError(
                "previous_state must be one of 'up', 'down' or 'n/a'",
            )
        if state.latency_ms is not None and state.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")

        heartbeat_at = self._normalize_timestamp(state.checked_at)

        connection = self._ensure_connection()
        cursor = connection.cursor()
        try:
            self._execute(
                cursor,
                _UPSERT_DAEMON_STATE_QUERY,
                (
                    host,
                    state.port,
                    state.current_state,
                    state.previous_state,
                    heartbeat_at,
                    state.latency_ms,
                    state.current_state,
                    state.previous_state,
                    heartbeat_at,
                    state.latency_ms,
                ),
            )
        finally:
            cursor.close()

    def connection(self) -> SupportsConnection:
        """Return an active DB-API connection, creating one if required."""

        return self._ensure_connection()

    def _connect_with_retries(self) -> SupportsConnection:
        connector = self._connector or self._load_default_connector()
        params: dict[str, Any] = {
            "host": self._config.host,
            "port": self._config.port,
            "user": self._config.username,
            "passwd": self._config.password,
            "db": self._config.database,
            "charset": "utf8mb4",
            "use_unicode": True,
            "connect_timeout": self._normalize_timeout(self._connect_timeout),
            "read_timeout": self._normalize_timeout(self._read_timeout),
            "init_command": self._connection_init_command(),
        }
        if self._write_timeout is not None:
            params["write_timeout"] = self._normalize_timeout(self._write_timeout)
        if self._enable_multi_statements:
            client_flag = self._resolve_client_multi_statements_flag()
            if client_flag is not None:
                params["client_flag"] = client_flag

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                connection = connector(**params)
            except Exception as exc:  # pragma: no cover - handled via retries below
                last_error = exc
            else:
                self._apply_connection_settings(connection)
                return connection

            if attempt == self._max_retries:
                message = "Failed to connect to MySQL after repeated attempts"
                raise DatabaseError(message) from last_error

            delay = self._retry_backoff * (attempt + 1)
            self._sleeper(delay)

        message = "Failed to connect to MySQL after repeated attempts"
        raise DatabaseError(message) from last_error

    def _ensure_connection(self) -> SupportsConnection:
        connection = self._connection
        if connection is None:
            connection = self._connect_with_retries()
            self._connection = connection
            return connection

        if self._skip_connection_ping:
            return connection

        if not self._connection_alive(connection):
            connection = self._connect_with_retries()
            self._connection = connection
        return connection

    def _connection_alive(self, connection: SupportsConnection) -> bool:
        try:
            connection.ping(reconnect=False)
        except Exception:
            return False
        return True

    def _fetchall(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[Any] | None = None,
    ) -> Sequence[Any]:
        cursor = connection.cursor()
        try:
            self._execute(cursor, query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def _fetchone(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[Any] | None = None,
    ) -> Any:
        cursor = connection.cursor()
        try:
            self._execute(cursor, query, params)
            return cursor.fetchone()
        finally:
            cursor.close()

    def _execute(
        self,
        cursor: SupportsCursor,
        query: str,
        params: Sequence[Any] | None,
    ) -> None:
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)

    def _apply_connection_settings(self, connection: SupportsConnection) -> None:
        try:
            connection.autocommit(True)
        except AttributeError:  # pragma: no cover - depends on driver
            pass

    def _normalize_timeout(self, value: float) -> int:
        """Convert adapter timeouts into integers accepted by ``mysqlclient``."""

        return max(1, int(math.ceil(value)))

    def _normalize_timestamp(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment
        return moment.astimezone(timezone.utc).replace(tzinfo=None)

    def _load_default_connector(self) -> Callable[..., SupportsConnection]:
        try:
            import MySQLdb
        except ImportError as exc:  # pragma: no cover - requires runtime environment
            raise DatabaseError("mysqlclient (MySQLdb) is required for database access") from exc
        return cast(Callable[..., SupportsConnection], MySQLdb.connect)

    def _connection_init_command(self) -> str:
        # Note: innodb_flush_log_at_trx_commit is GLOBAL-only on MariaDB/MySQL and
        # cannot appear in SESSION init_command (connection would fail). Bulk-import
        # tuning belongs in server config or a privileged bootstrap path, not here.
        if self._import_mode:
            return "SET NAMES 'utf8mb4', SESSION sql_mode = ''"
        return "SET NAMES 'utf8mb4'"

    def _resolve_client_multi_statements_flag(self) -> int | None:
        try:
            import MySQLdb
        except ImportError:
            return None
        client = getattr(getattr(MySQLdb, "constants", None), "CLIENT", None)
        if client is not None:
            return getattr(client, "MULTI_STATEMENTS", None)
        try:
            from MySQLdb.constants import CLIENT
        except Exception:
            return None
        return getattr(CLIENT, "MULTI_STATEMENTS", None)

    def _parse_daemon_list(self, raw: str) -> list[ProxyDaemonTarget]:
        entries: list[ProxyDaemonTarget] = []
        if not raw.strip():
            return entries

        for index, chunk in enumerate(raw.split(","), start=1):
            value = chunk.strip()
            if not value:
                continue
            host, separator, port_text = value.partition(":")
            if not separator or not host:
                raise DatabaseError(f"Invalid proxy daemon entry #{index}: {value!r}")
            try:
                port = int(port_text)
            except ValueError as exc:
                raise DatabaseError(
                    f"Invalid port for proxy daemon entry #{index}: {value!r}"
                ) from exc
            if port <= 0 or port > 65535:
                raise DatabaseError(f"Port out of range for proxy daemon entry #{index}: {value!r}")
            entries.append(ProxyDaemonTarget(host=host.strip(), port=port))

        return entries


T = TypeVar("T")
Runner = Callable[[Callable[[], T]], Awaitable[T]]


class DatabaseAdapter:
    """Async wrapper that delegates work to :class:`SyncDatabaseAdapter`."""

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        connector: Callable[..., SupportsConnection] | None = None,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        connect_timeout: float = 5.0,
        read_timeout: float = 5.0,
        write_timeout: float | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        executor: Executor | None = None,
        runner: Runner | None = None,
    ) -> None:
        self._sync = SyncDatabaseAdapter(
            config,
            connector=connector,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
        )
        self._loop = loop
        self._executor = executor
        self._runner = runner

    @property
    def sync(self) -> SyncDatabaseAdapter:
        """Expose the underlying synchronous adapter for direct use when needed."""

        return self._sync

    async def connect(self) -> None:
        await self._run(self._sync.connect)

    async def close(self) -> None:
        await self._run(self._sync.close)

    async def fetch_options(self) -> dict[str, str]:
        return await self._run(self._sync.fetch_options)

    async def fetch_proxy_key(self) -> str:
        return await self._run(self._sync.fetch_proxy_key)

    async def fetch_daemons(self) -> list[ProxyDaemonTarget]:
        return await self._run(self._sync.fetch_daemons)

    async def update_daemon_state(self, state: ProxyDaemonState) -> None:
        await self._run(lambda: self._sync.update_daemon_state(state))

    async def _run(self, func: Callable[[], T]) -> T:
        runner = self._runner
        if runner is not None:
            return await cast(Awaitable[T], runner(func))

        loop = self._loop or asyncio.get_running_loop()
        future = cast(Awaitable[T], loop.run_in_executor(self._executor, func))
        return await future


__all__ = [
    "DatabaseAdapter",
    "DatabaseConfig",
    "DatabaseError",
    "GameServer",
    "ProxyDaemonTarget",
    "ProxyDaemonState",
    "StoredProxyDaemon",
    "SupportsConnection",
    "SupportsCursor",
    "SyncDatabaseAdapter",
    "_UPSERT_DAEMON_STATE_QUERY",
]
