from __future__ import annotations

from hlstats_py.frag_write_delta_buffer import FragWriteDeltaBuffer
from hlstats_py.storage import _UPSERT_MAP_COUNTS_QUERY, _UPSERT_WEAPON_QUERY, _UPDATE_SERVER_FRAG_TOTALS_QUERY


def test_frag_write_delta_buffer_merges_weapon_and_map() -> None:
    buf = FragWriteDeltaBuffer()
    buf.add_weapon("csgo", "ak47", "AK-47", 1.0, 1, 1)
    buf.add_weapon("csgo", "ak47", "AK-47", 1.0, 1, 0)
    buf.add_map_counts("csgo", "de_dust2", 1, 1)
    buf.add_map_counts("csgo", "de_dust2", 1, 0)

    executed: list[tuple[str, tuple[object, ...]]] = []

    def emit(query: str, row: tuple[object, ...]) -> None:
        executed.append((query, row))

    buf.flush(
        upsert_weapon_query=_UPSERT_WEAPON_QUERY,
        update_server_frag_query=_UPDATE_SERVER_FRAG_TOTALS_QUERY,
        upsert_map_counts_query=_UPSERT_MAP_COUNTS_QUERY,
        execute=emit,
    )

    assert len(executed) == 2
    assert executed[0][0] == _UPSERT_WEAPON_QUERY
    assert executed[0][1][4] == 2
    assert executed[0][1][5] == 1
    assert executed[1][0] == _UPSERT_MAP_COUNTS_QUERY
    assert executed[1][1][2] == 2
    assert executed[1][1][3] == 1


def test_frag_write_delta_buffer_clear() -> None:
    buf = FragWriteDeltaBuffer()
    buf.add_server_frag_totals(1, 1, 7)
    buf.clear()

    executed: list[tuple[str, tuple[object, ...]]] = []

    buf.flush(
        upsert_weapon_query=_UPSERT_WEAPON_QUERY,
        update_server_frag_query=_UPDATE_SERVER_FRAG_TOTALS_QUERY,
        upsert_map_counts_query=_UPSERT_MAP_COUNTS_QUERY,
        execute=lambda q, r: executed.append((q, r)),
    )
    assert executed == []
