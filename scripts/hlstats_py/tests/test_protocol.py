from __future__ import annotations

import hashlib

import pytest

from hlstats_py.protocol import (
    ControlCommandType,
    LogEventType,
    parse_control_command,
    parse_log_event,
    parse_proxy_envelope,
)


def test_parse_proxy_envelope_with_server():
    datagram = (
        "PROXY Key=test 127.0.0.1:27015PROXY L 06/15/2023 - 10:15:42: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" say "hello"'
    )
    envelope = parse_proxy_envelope(datagram)

    assert envelope.proxy_key == "test"
    assert envelope.server_address == "127.0.0.1:27015"
    assert envelope.payload.startswith("L 06/15/2023 - 10:15:42:")


def test_parse_proxy_envelope_without_server():
    datagram = "PROXY Key=test PROXY C;HEARTBEAT;"
    envelope = parse_proxy_envelope(datagram)

    assert envelope.proxy_key == "test"
    assert envelope.server_address is None
    assert envelope.payload == "C;HEARTBEAT;"


@pytest.mark.parametrize(
    "payload, expected",
    [
        ("C;HEARTBEAT;", ControlCommandType.HEARTBEAT),
        ("C;SERVERLIST;", ControlCommandType.SERVERLIST),
        ("C;RELOAD;", ControlCommandType.RELOAD),
        ("C;KILL;", ControlCommandType.KILL),
        ("C;UNKNOWN;", ControlCommandType.UNKNOWN),
    ],
)
def test_parse_control_command(payload: str, expected: ControlCommandType):
    command = parse_control_command(payload)
    assert command is not None
    assert command.command_type is expected


def test_parse_kill_event():
    payload = (
        "L 06/15/2023 - 10:15:42: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" killed '
        '"Bob<3><STEAM_1:1:222><CT>" with "ak47" (headshot)'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.KILL
    assert event.actor and event.actor.name == "Alice"
    assert event.target and event.target.name == "Bob"
    assert event.weapon == "ak47"
    assert event.properties.get("headshot") is True


def test_parse_shipped_cstrike_kill_positions() -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot) '
        '(attacker_position "1 2 3") (victim_position "4 5 6")'
    )

    assert event.properties["attacker_position"] == "1 2 3"
    assert event.properties["victim_position"] == "4 5 6"
    assert event.properties["headshot"] is True


def test_parse_inline_setpos_exact_kill_positions() -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" '
        'setpos_exact 1.5 -2.5 3.5 [4 5 6]'
    )

    assert event.properties["attacker_position"] == "2 -3 4"
    assert event.properties["victim_position"] == "4 5 6"


@pytest.mark.parametrize("position", ["8388607.6 0 0", "-8388608.6 0 0"])
def test_parse_inline_setpos_exact_rejects_after_rounding_out_of_mediumint(
    position: str,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        f'"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" setpos_exact {position}'
    )

    assert event.properties["attacker_position"] == position


@pytest.mark.parametrize(
    "payload",
    [
        (
            'L 01/02/2024 - 03:04:05: "Alice [1 2 3]<2><STEAM_1:2><CT>" '
            'killed "Bob [4 5 6]<3><STEAM_1:3><TERRORIST>" with "ak47"'
        ),
        (
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "[7 8 9]"'
        ),
    ],
)
def test_parse_kill_inline_coordinates_ignore_names_and_weapon(payload: str) -> None:
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.KILL
    assert "attacker_position" not in event.properties
    assert "victim_position" not in event.properties


def test_parse_inline_positions_preserve_invalid_slot_order() -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" '
        "setpos_exact 1,2,3,4 [4 5 6]"
    )

    assert event.properties["attacker_position"] == "1,2,3,4"
    assert event.properties["victim_position"] == "4 5 6"


def test_parse_inline_setpos_exact_rejects_fourth_component() -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" setpos_exact 1,2,3,4'
    )

    assert event.properties["attacker_position"] == "1,2,3,4"
    assert "victim_position" not in event.properties


def test_parse_position_property_rejects_oversized_integer_without_raising() -> None:
    oversized = "9" * 10_000
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        f'"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" '
        f'(attacker_position "{oversized} 0 0")'
    )

    assert event.properties["attacker_position"] == f"{oversized} 0 0"


def test_parse_trigger_event():
    payload = (
        "L 06/15/2023 - 10:16:00: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" triggered "planted_bomb" '
        '(site "A")'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.TRIGGER
    assert event.action == "planted_bomb"
    assert event.properties["site"] == "A"


def test_parse_chat_event():
    payload = (
        "L 06/15/2023 - 10:16:10: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" say_team "Hold position"'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.CHAT
    assert event.message == "Hold position"
    assert event.properties.get("team_only") is True


def test_parse_dead_chat_event():
    payload = (
        "L 06/15/2023 - 10:16:10: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" say "gg" (dead)'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.CHAT
    assert event.message == "gg"
    assert event.properties.get("team_only") is None


def test_parse_world_event():
    payload = "L 06/15/2023 - 10:16:30: World triggered \"Round_Start\""
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.WORLD_TRIGGER
    assert event.action == "Round_Start"


def test_parse_connect_event():
    payload = (
        "L 06/15/2023 - 10:17:00: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" connected, address "1.2.3.4:27005"'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.CONNECT
    assert event.properties["address"] == "1.2.3.4"


def test_parse_connect_event_preserves_non_ipv4_address():
    payload = (
        "L 06/15/2023 - 10:17:00: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" connected, address "2001:db8::1:27005"'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.CONNECT
    assert event.properties["address"] == "2001:db8::1:27005"


def test_parse_properties_duplicate_keys_last_value_wins():
    payload = (
        "L 06/15/2023 - 10:15:42: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" killed '
        '"Bob<3><STEAM_1:1:222><CT>" with "ak47" (attacker_position "1 2 3") '
        '(attacker_position "9 9 9")'
    )
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.KILL
    assert event.properties["attacker_position"] == "9 9 9"


def test_parse_player_unique_id_normalizes_steam0_and_steam1_prefixes():
    steam0 = parse_log_event(
        'L 06/15/2023 - 10:15:42: "Alice<2><STEAM_0:1:111><TERRORIST>" say "hello"'
    )
    steam1 = parse_log_event(
        'L 06/15/2023 - 10:15:42: "Alice<2><STEAM_1:1:111><TERRORIST>" say "hello"'
    )

    assert steam0.actor is not None
    assert steam1.actor is not None
    assert steam0.actor.unique_id == "1:111"
    assert steam1.actor.unique_id == "STEAM_1:1:111"


def test_parse_bot_unique_id_is_stabilized_per_player_identity():
    server_address = "37.230.137.48:27015"
    first = parse_log_event(
        'L 06/15/2023 - 10:15:42: "BotOne<664><BOT><CT>" joined team "CT"',
        server_address=server_address,
    )
    second = parse_log_event(
        'L 06/15/2023 - 10:15:43: "BotTwo<665><BOT><TERRORIST>" joined team "TERRORIST"',
        server_address=server_address,
    )

    assert first.actor is not None
    assert second.actor is not None
    assert first.actor.unique_id is not None
    assert second.actor.unique_id is not None
    expected = "BOT:b9cd427d72a4e627fa34d90ea0c96015"
    assert first.actor.unique_id == expected
    assert first.actor.unique_id == (
        "BOT:"
        + hashlib.md5(f"BotOne{server_address}".encode("utf-8", errors="replace")).hexdigest()
    )
    assert second.actor.unique_id.startswith("BOT:")
    assert first.actor.unique_id != second.actor.unique_id


def test_parse_log_event_errors():
    with pytest.raises(ValueError):
        parse_log_event("This is not a log line")


def test_parse_generic_event():
    payload = "L 06/15/2023 - 10:00:00: malformed entry"
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.GENERIC
    assert event.message == "malformed entry"


def test_parse_map_lifecycle_generic_event():
    payload = 'L 06/15/2023 - 10:00:00: Loading map "de_nuke"'
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.GENERIC
    assert event.message == 'Loading map "de_nuke"'


def test_parse_log_event_native_backend_matches_python():
    payload = (
        "L 06/15/2023 - 10:15:42: "
        '"Alice<2><STEAM_1:1:111><TERRORIST>" killed '
        '"Bob<3><STEAM_1:1:222><CT>" with "ak47" (headshot)'
    )
    python_event = parse_log_event(payload, backend="python")
    native_event = parse_log_event(payload, backend="native")

    assert native_event.event_type is python_event.event_type
    assert native_event.weapon == python_event.weapon
    assert native_event.properties == python_event.properties
    assert native_event.actor is not None
    assert python_event.actor is not None
    assert native_event.actor.name == python_event.actor.name


def test_parse_log_event_native_backend_matches_python_for_bot_identity():
    payload = 'L 06/15/2023 - 10:15:42: "BotOne<664><BOT><CT>" joined team "CT"'
    server_address = "37.230.137.48:27015"
    python_event = parse_log_event(payload, backend="python", server_address=server_address)
    native_event = parse_log_event(payload, backend="native", server_address=server_address)

    assert python_event.actor is not None
    assert native_event.actor is not None
    assert python_event.actor.unique_id == native_event.actor.unique_id
    assert python_event.actor.unique_id == "BOT:b9cd427d72a4e627fa34d90ea0c96015"


def test_log_file_started_is_a_generic_epoch_boundary_message():
    event = parse_log_event("L 06/15/2023 - 10:15:42: Log file started")
    assert event.event_type is LogEventType.GENERIC
    assert event.message == "Log file started"
