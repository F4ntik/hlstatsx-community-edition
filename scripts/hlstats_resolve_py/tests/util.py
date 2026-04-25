"""Testing utilities for the hlstats-resolve Python port."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class QueryLogEntry:
    """Record of an executed query and its parameters."""

    query: str
    params: Sequence[object] | None


class InMemoryConnection:
    """Very small DB-API compatible stub for resolver unit tests."""

    def __init__(
        self,
        *,
        hostgroups: Sequence[tuple[str, str]] | None = None,
        regroup_rows: Sequence[tuple[int, str]] | None = None,
        resolve_rows: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        self.hostgroups = list(hostgroups or [])
        self.regroup_rows = list(regroup_rows or [])
        self.resolve_rows = list(resolve_rows or [])
        self.query_log: list[QueryLogEntry] = []
        self.regroup_updates: list[tuple[str, int]] = []
        self.resolve_updates: list[tuple[str, str, str]] = []

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    def autocommit(self, _value: bool) -> None:  # pragma: no cover - compatibility shim
        return None

    def close(self) -> None:  # pragma: no cover - compatibility shim
        return None


class _Cursor:
    def __init__(self, connection: InMemoryConnection) -> None:
        self._connection = connection
        self._rows: list[tuple[object, ...]] = []

    def execute(self, query: str, params: Sequence[object] | None = None) -> None:
        self._connection.query_log.append(QueryLogEntry(query=query, params=params))
        if query.startswith("SELECT pattern"):
            self._rows = [(pattern, name) for pattern, name in self._connection.hostgroups]
        elif query.startswith("SELECT id, hostname"):
            self._rows = [(row_id, hostname) for row_id, hostname in self._connection.regroup_rows]
        elif query.startswith("SELECT DISTINCT ipAddress"):
            self._rows = [
                (ip, hostname) for ip, hostname in self._connection.resolve_rows
            ]
        elif query.startswith("UPDATE hlstats_Events_Connects SET hostgroup"):
            assert params is not None
            hostgroup, row_id = params
            self._connection.regroup_updates.append((str(hostgroup), int(row_id)))
            self._rows = []
        elif query.startswith("UPDATE hlstats_Events_Connects SET hostname"):
            assert params is not None
            hostname, hostgroup, ip_address = params
            self._connection.resolve_updates.append(
                (str(hostname), str(hostgroup), str(ip_address))
            )
            self._rows = []
        else:  # pragma: no cover - defensive programming
            raise AssertionError(f"Unexpected query executed: {query}")

    def fetchall(self) -> Sequence[tuple[object, ...]]:
        return list(self._rows)

    def close(self) -> None:
        return None


class StubAdapter:
    """Adapter exposing only the ``connection`` method used by the resolver."""

    def __init__(self, connection: InMemoryConnection) -> None:
        self._connection = connection

    def connection(self) -> InMemoryConnection:
        return self._connection


__all__ = [
    "InMemoryConnection",
    "QueryLogEntry",
    "StubAdapter",
]
