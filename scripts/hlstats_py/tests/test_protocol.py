from __future__ import annotations

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
    assert event.properties["address"] == "1.2.3.4:27005"


def test_parse_log_event_errors():
    with pytest.raises(ValueError):
        parse_log_event("This is not a log line")


def test_parse_generic_event():
    payload = "L 06/15/2023 - 10:00:00: malformed entry"
    event = parse_log_event(payload)

    assert event.event_type is LogEventType.GENERIC
    assert event.message == "malformed entry"
