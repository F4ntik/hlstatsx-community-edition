from __future__ import annotations

from hlstats_py.event_buffer import BufferPolicy, EventBuffer


class _Cursor:
    def __init__(self) -> None:
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def executemany(self, query: str, params: list[tuple[object, ...]]) -> None:
        self.executemany_calls.append((query, list(params)))


def test_event_buffer_flushes_batched_rows():
    buffer = EventBuffer(policy=BufferPolicy(max_buffered_events=3))
    assert buffer.add("INSERT INTO t VALUES (%s)", (1,)) is False
    assert buffer.add("INSERT INTO t VALUES (%s)", (2,)) is False
    assert buffer.add("INSERT INTO t VALUES (%s)", (3,)) is True

    cursor = _Cursor()
    flushed = buffer.flush(cursor)
    assert flushed == 3
    assert len(cursor.executemany_calls) == 1
    assert cursor.executemany_calls[0][1] == [(1,), (2,), (3,)]
    assert buffer.buffered_rows == 0


def test_event_buffer_splits_by_query_template():
    buffer = EventBuffer(policy=BufferPolicy(max_buffered_events=10))
    buffer.add("INSERT INTO a VALUES (%s)", (1,))
    buffer.add("INSERT INTO b VALUES (%s)", (2,))
    buffer.add("INSERT INTO a VALUES (%s)", (3,))

    cursor = _Cursor()
    flushed = buffer.flush(cursor)
    assert flushed == 3
    assert len(cursor.executemany_calls) == 2


def test_event_buffer_executemany_chunking():
    buffer = EventBuffer(policy=BufferPolicy(max_buffered_events=10))
    for i in range(5):
        buffer.add("INSERT INTO t VALUES (%s)", (i,))

    cursor = _Cursor()
    flushed = buffer.flush(cursor, executemany_chunk_size=2)
    assert flushed == 5
    assert cursor.executemany_calls == [
        ("INSERT INTO t VALUES (%s)", [(0,), (1,)]),
        ("INSERT INTO t VALUES (%s)", [(2,), (3,)]),
        ("INSERT INTO t VALUES (%s)", [(4,)]),
    ]
