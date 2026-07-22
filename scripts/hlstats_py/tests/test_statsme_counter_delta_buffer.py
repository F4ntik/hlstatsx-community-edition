from hlstats_py.statsme_counter_delta_buffer import StatsmeCounterDeltaBuffer


def test_statsme_counter_delta_buffer_aggregates_and_separates_server_teams() -> None:
    buffer = StatsmeCounterDeltaBuffer()
    emitted: list[tuple[str, tuple[object, ...]]] = []

    buffer.add_player(2, 3, 1)
    buffer.add_player(2, 7, 2)
    buffer.add_player(1, 5, 4)
    buffer.add_server(9, "CT", 3, 1, 30, 10)
    buffer.add_server(9, "CT", 7, 2, 70, 20)
    buffer.add_server(9, "TERRORIST", 5, 4, 50, 40)
    writes = buffer.flush(
        update_player_query="player",
        update_server_ct_query="ct",
        update_server_ts_query="ts",
        execute=lambda query, params: emitted.append((query, params)),
    )

    assert writes == 4
    assert emitted == [
        ("player", (5, 4, 1)),
        ("player", (10, 3, 2)),
        ("ct", (10, 3, 100, 30, 9)),
        ("ts", (5, 4, 50, 40, 9)),
    ]


def test_statsme_counter_delta_buffer_keeps_rows_after_failed_emit() -> None:
    buffer = StatsmeCounterDeltaBuffer()
    buffer.add_player(1, 2, 3)

    try:
        buffer.flush(
            update_player_query="player",
            update_server_ct_query="ct",
            update_server_ts_query="ts",
            execute=lambda *_: (_ for _ in ()).throw(RuntimeError("write failed")),
        )
    except RuntimeError:
        pass

    emitted: list[tuple[str, tuple[object, ...]]] = []
    buffer.flush(
        update_player_query="player",
        update_server_ct_query="ct",
        update_server_ts_query="ts",
        execute=lambda query, params: emitted.append((query, params)),
    )
    assert emitted == [("player", (2, 3, 1))]
