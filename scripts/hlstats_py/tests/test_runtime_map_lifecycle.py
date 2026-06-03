from __future__ import annotations

from hlstats_py.runtime import RuntimeMapState, TrackedServer, apply_map_lifecycle_message


def _server() -> TrackedServer:
    return TrackedServer(
        server_id=1,
        address="127.0.0.1",
        port=27015,
        name="Test",
        game="cstrike",
        state=RuntimeMapState(current_map=""),
    )


def test_apply_map_lifecycle_started_with_crc_suffix() -> None:
    server = _server()
    body = 'L 01/01/2024 - 00:00:31: Started map "de_nuke" (CRC "-1757378041")'
    assert apply_map_lifecycle_message(server, body) == ("started", "de_nuke")
    assert server.current_map == "de_nuke"
    assert server.map_lifecycle == "started"


def test_apply_map_lifecycle_loading_plain_line() -> None:
    server = _server()
    server.current_map = "de_dust2"
    body = 'L 01/01/2024 - 00:00:29: Loading map "de_nuke"'
    assert apply_map_lifecycle_message(server, body) == ("loading", "de_nuke")
    assert server.map_lifecycle == "loading"
    assert server.current_map == "de_dust2"
    assert server.pending_map == "de_nuke"


def test_apply_map_lifecycle_started_wins_when_both_substrings() -> None:
    server = _server()
    body = 'Loading map "a" then Started map "b" (CRC "0")'
    assert apply_map_lifecycle_message(server, body) == ("started", "b")
    assert server.current_map == "b"


def test_apply_map_lifecycle_last_started_when_multiple() -> None:
    server = _server()
    body = 'Started map "first" (CRC "1") ... Started map "second" (CRC "2")'
    assert apply_map_lifecycle_message(server, body) == ("started", "second")
