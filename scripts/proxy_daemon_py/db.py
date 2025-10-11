"""Database access layer for the Python proxy daemon."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast


class DatabaseError(RuntimeError):
    """Raised when database connectivity or queries fail."""


class SupportsCursor(Protocol):
    """Protocol describing cursor objects returned by DB-API connectors."""

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> Sequence[Any]: ...

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

        self._config = config
        self._connector = connector
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._sleeper = sleeper or time.sleep
        self._connection: SupportsConnection | None = None

    def connect(self) -> None:
        """Establish a connection to MySQL, retrying with back-off on failures."""

        self._connection = self._connect_with_retries()

    def close(self) -> None:
        """Close the current database connection if one exists."""

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
        if not row:
            raise DatabaseError("Proxy key is not configured in hlstats_Options")
        value = row[0]
        return "" if value is None else str(value)

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
            "connect_timeout": self._connect_timeout,
            "read_timeout": self._read_timeout,
            "init_command": "SET NAMES 'utf8mb4'",
        }
        if self._write_timeout is not None:
            params["write_timeout"] = self._write_timeout

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

    def _load_default_connector(self) -> Callable[..., SupportsConnection]:
        try:
            import MySQLdb
        except ImportError as exc:  # pragma: no cover - requires runtime environment
            raise DatabaseError("mysqlclient (MySQLdb) is required for database access") from exc
        return cast(Callable[..., SupportsConnection], MySQLdb.connect)

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
    "ProxyDaemonTarget",
    "SyncDatabaseAdapter",
]
