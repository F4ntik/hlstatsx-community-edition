from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def normalize_sql(query: str) -> str:
    """Collapse whitespace to make SQL comparisons deterministic in tests."""

    return " ".join(query.split())


QueryKey = tuple[str, tuple[object, ...] | None]


@dataclass(slots=True)
class QueryResponse:
    """Pre-programmed response returned by :class:`FakeCursor`."""

    fetchone: Sequence[object] | None = None
    fetchall: Sequence[Sequence[object]] | None = None
    rowcount: int | None = None


class FakeCursor:
    """Minimal DB-API cursor stub used by tests to capture SQL execution."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self._key: QueryKey | None = None
        self._response: QueryResponse | None = None
        self.rowcount = 0

    def execute(self, query: str, params: Iterable[object] | None = None) -> None:
        normalized = normalize_sql(query)
        key = (normalized, None if params is None else tuple(params))
        response = self._connection._pop_response(key)
        self._connection.executed.append(key)
        self._key = key
        self._response = response
        self.rowcount = 0 if response.rowcount is None else int(response.rowcount)

    def fetchone(self) -> Sequence[object] | None:
        if self._response is None:
            raise AssertionError("fetchone called before execute")
        return self._response.fetchone

    def fetchall(self) -> Sequence[Sequence[object]]:
        if self._response is None:
            raise AssertionError("fetchall called before execute")
        return list(self._response.fetchall or [])

    def close(self) -> None:  # pragma: no cover - API compatibility
        self._key = None
        self._response = None


class FakeConnection:
    """Connection stub returning :class:`FakeCursor` objects to tests."""

    def __init__(self, responses: dict[QueryKey, list[QueryResponse]]) -> None:
        self._responses = {key: list(value) for key, value in responses.items()}
        self.executed: list[QueryKey] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def _pop_response(self, key: QueryKey) -> QueryResponse:
        queue = self._responses.get(key)
        if queue:
            return queue.pop(0)
        return QueryResponse()


class StubAdapter:
    """Sync database adapter stub exposing an in-memory connection."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def connection(self) -> FakeConnection:
        return self._connection
