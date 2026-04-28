import pytest

from hlstats_py import (
    ActionDefinition,
    ChatEventHandler,
    ConnectEventHandler,
    DisconnectEventHandler,
    EntryEventHandler,
    EventCategory,
    EventContext,
    EventDispatcher,
    GameSchema,
    GenericEventHandler,
    KillEventHandler,
    LocalizationCatalog,
    TeamEventHandler,
    TeamTriggerEventHandler,
    TriggerEventHandler,
    WeaponDefinition,
    WorldEventHandler,
    parse_log_event,
)


@pytest.fixture()
def event_context() -> EventContext:
    schema = GameSchema(
        game="csgo",
        weapons={
            "ak47": WeaponDefinition(code="ak47", name="AK-47", aliases=("ak",)),
            "trigger_hurt": WeaponDefinition(code="trigger_hurt", name="Trigger Hurt"),
        },
        actions={
            "planted_bomb": ActionDefinition(
                code="planted_bomb", description="Bomb planted", aliases=("planted_bomb",)
            ),
            "round_start": ActionDefinition(
                code="round_start", description="Round Start", aliases=("Round_Start",)
            ),
        },
    )
    catalog = LocalizationCatalog(
        templates={
            "kill.ak47": "{actor} eliminated {target} with {weapon}",
            "kill": "{actor} defeated {target}",
            "trigger.planted_bomb": "{actor} planted the bomb",
            "trigger": "{actor} triggered {action}",
            "chat": "{actor}: {message}",
            "chat.team": "[TEAM] {actor}: {message}",
            "team_change": "{actor} joined {team}",
            "connect": "{actor} connected from {message}",
            "disconnect": "{actor} disconnected ({reason})",
            "world.round_start": "{action}",
            "world": "World event: {action}",
            "generic": "{message}",
        },
        default_template="{actor} {event_code}",
    )
    return EventContext(server_id=7, game="csgo", schema=schema, localization=catalog)


@pytest.fixture()
def dispatcher() -> EventDispatcher:
    generic = GenericEventHandler()
    return EventDispatcher(
        [
            KillEventHandler(),
            TriggerEventHandler(),
            ChatEventHandler(),
            TeamEventHandler(),
            ConnectEventHandler(),
            EntryEventHandler(),
            DisconnectEventHandler(),
            TeamTriggerEventHandler(),
            WorldEventHandler(),
            generic,
        ],
        fallback=generic,
    )


def test_kill_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed "Bob<3><STEAM_1:3><TERRORIST>" '
        'with "ak47" (headshot)'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.FRAG
    assert update.event_code == "ak47"
    assert update.attributes["weapon_name"] == "AK-47"
    assert update.attributes["headshot"] is True
    assert update.message == "Alice eliminated Bob with AK-47"


def test_suicide_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" committed suicide with "trigger_hurt"'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.FRAG
    assert update.event_code == "trigger_hurt"
    assert update.attributes["is_suicide"] is True
    assert update.message == "Alice defeated Alice"


def test_trigger_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "planted_bomb" (site "A")'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.ACTION
    assert update.event_code == "planted_bomb"
    assert update.attributes["description"] == "Bomb planted"
    assert update.message == "Alice planted the bomb"


def test_chat_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say_team "Hold position"'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.CHAT
    assert update.attributes["team_only"] is True
    assert update.message == "[TEAM] Alice: Hold position"


def test_dead_chat_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "gg" (dead)'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.CHAT
    assert update.attributes["team_only"] is False
    assert update.message == "Alice: gg"


def test_connect_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" connected, address "1.2.3.4:27005"'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.CONNECTION
    assert update.attributes["address"] == "1.2.3.4"
    assert update.message == "Alice connected from 1.2.3.4"


def test_disconnect_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" disconnected (reason "Kicked")'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.CONNECTION
    assert update.attributes["reason"] == "Kicked"
    assert update.message == "Alice disconnected (Kicked)"


def test_world_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event('L 01/02/2024 - 03:04:05: World triggered "Round_Start"')

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.WORLD
    assert update.event_code == "round_start"
    assert update.message == "Round Start"


def test_entry_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_0:1:2><CT>" entered the game'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.ENTRY
    assert update.actor is not None
    assert update.actor.unique_id == "1:2"


def test_entry_event_requires_exact_phrase(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_0:1:2><CT>" entered the game unexpectedly'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.GENERIC


def test_team_trigger_event(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "CTs_Win" (CT "1") (T "0")')

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.TEAM_BONUS
    assert update.attributes["team"] == "CT"


def test_generic_fallback(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" changed name to "Alicia"'
    )

    update = dispatcher.dispatch(event, event_context)

    assert update.category is EventCategory.GENERIC
    assert update.message == "Alicia"
