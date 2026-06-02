"""Buffered SQL write helpers for high-volume replay imports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from hlx_core import db as proxy_db


@dataclass(slots=True)
class BufferPolicy:
    max_buffered_events: int


class EventBuffer:
    """Batch append-only event table inserts via ``executemany``."""

    def __init__(self, *, policy: BufferPolicy) -> None:
        self._policy = policy
        self._rows_by_query: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        self._buffered_rows = 0

    @property
    def buffered_rows(self) -> int:
        return self._buffered_rows

    def add(self, query: str, params: tuple[Any, ...]) -> bool:
        self._rows_by_query[query].append(params)
        self._buffered_rows += 1
        return self._buffered_rows >= self._policy.max_buffered_events

    def clear(self) -> None:
        """Drop buffered rows without executing SQL (e.g. after transaction rollback)."""

        self._rows_by_query.clear()
        self._buffered_rows = 0

    def flush(self, cursor: proxy_db.SupportsCursor, *, executemany_chunk_size: int | None = None) -> int:
        flushed = 0
        for query, rows in list(self._rows_by_query.items()):
            if not rows:
                continue
            executemany = getattr(cursor, "executemany", None)
            if callable(executemany):
                if executemany_chunk_size is not None and executemany_chunk_size > 0:
                    for offset in range(0, len(rows), executemany_chunk_size):
                        chunk = rows[offset : offset + executemany_chunk_size]
                        executemany(query, chunk)
                else:
                    executemany(query, rows)
            else:
                for row in rows:
                    cursor.execute(query, row)
            flushed += len(rows)
        self._rows_by_query.clear()
        self._buffered_rows = 0
        return flushed
