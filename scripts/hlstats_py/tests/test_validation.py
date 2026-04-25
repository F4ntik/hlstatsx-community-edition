from __future__ import annotations

from hlstats_py import (
    ActionDefinition,
    ChatEventHandler,
    ConnectEventHandler,
    DisconnectEventHandler,
    EventContext,
    EventDispatcher,
    GameSchema,
    GenericEventHandler,
    KillEventHandler,
    LocalizationCatalog,
    PlayerActionSnapshot,
    ReplayRunner,
    TriggerEventHandler,
    WeaponDefinition,
    WorldEventHandler,
)


def _build_dispatcher() -> EventDispatcher:
    generic = GenericEventHandler()
    return EventDispatcher(
        [
            KillEventHandler(),
            TriggerEventHandler(),
            ChatEventHandler(),
            ConnectEventHandler(),
            DisconnectEventHandler(),
            WorldEventHandler(),
        ],
        fallback=generic,
    )


def _build_context() -> EventContext:
    schema = GameSchema(
        game="csgo",
        weapons={
            "ak47": WeaponDefinition(code="ak47", name="AK-47"),
            "worldspawn": WeaponDefinition(code="worldspawn", name="World"),
        },
        actions={
            "planted_bomb": ActionDefinition(
                code="planted_bomb", description="Bomb planted", points=2
            ),
            "Round_Start": ActionDefinition(
                code="Round_Start", description="Round Start", points=0, team_award=True
            ),
        },
    )
    localization = LocalizationCatalog(templates={}, default_template="{event_code}")
    return EventContext(
        server_id=9,
        game="csgo",
        schema=schema,
        localization=localization,
        extras={"map": "de_dust2"},
    )


def _datagram(payload: str) -> str:
    return f"PROXY Key=proxy 127.0.0.1:27015 PROXY {payload}"


def test_replay_runner_builds_consistent_snapshot() -> None:
    context = _build_context()
    dispatcher = _build_dispatcher()
    runner = ReplayRunner(dispatcher, context)

    datagrams = [
        _datagram(
            'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:1:111><CT>" connected, address "1.2.3.4:27005"'
        ),
        _datagram(
            'L 01/02/2024 - 03:00:01: "Bob<3><STEAM_1:1:222><TERRORIST>" connected, address "5.6.7.8:27005"'
        ),
        _datagram('L 01/02/2024 - 03:00:10: World triggered "Round_Start"'),
        _datagram(
            'L 01/02/2024 - 03:00:20: "Alice<2><STEAM_1:1:111><CT>" say "Hello team"'
        ),
        _datagram(
            'L 01/02/2024 - 03:00:30: "Alice<2><STEAM_1:1:111><CT>" killed '
            '"Bob<3><STEAM_1:1:222><TERRORIST>" with "ak47" (headshot)'
        ),
        _datagram(
            'L 01/02/2024 - 03:00:40: "Bob<3><STEAM_1:1:222><TERRORIST>" committed suicide with "worldspawn"'
        ),
        _datagram(
            'L 01/02/2024 - 03:00:50: "Alice<2><STEAM_1:1:111><CT>" triggered "planted_bomb" (site "A")'
        ),
        _datagram(
            'L 01/02/2024 - 03:01:00: "Alice<2><STEAM_1:1:111><CT>" disconnected (reason "Quit")'
        ),
        _datagram('L 01/02/2024 - 03:01:10: Server cvar "mp_restartgame" changed to "1"'),
    ]

    result = runner.run(datagrams)
    snapshot = result.snapshot

    alice = snapshot.players_by_unique["1:111"]
    assert alice.kills == 1
    assert alice.headshots == 1
    assert alice.deaths == 0
    assert alice.suicides == 0
    assert alice.skill == 1004
    assert alice.connections == 1
    assert alice.disconnects == 1
    assert alice.last_address == "1.2.3.4"

    bob = snapshot.players_by_unique["1:222"]
    assert bob.kills == 0
    assert bob.deaths == 1
    assert bob.suicides == 1
    assert bob.skill == 998
    assert bob.connections == 1
    assert bob.disconnects == 0

    weapons = snapshot.weapons
    assert weapons["ak47"].kills == 1
    assert weapons["ak47"].headshots == 1

    actions = snapshot.actions
    assert actions["planted_bomb"].count == 1
    assert actions["planted_bomb"].reward_player == 2

    assert len(snapshot.frags) == 1
    (kill_frag,) = snapshot.frags
    assert kill_frag.weapon == "ak47"
    assert kill_frag.headshot is True

    chat = snapshot.chat_messages
    assert len(chat) == 1
    assert chat[0].message == "Hello team"

    connections = snapshot.connections
    assert {entry.address for entry in connections} == {"1.2.3.4", "5.6.7.8"}

    disconnects = snapshot.disconnects
    assert len(disconnects) == 1
    assert disconnects[0].player_id == alice.player_id

    admin_events = snapshot.admin_events
    assert len(admin_events) == 1
    assert admin_events[0].event_type == "generic"
    assert "mp_restartgame" in admin_events[0].message

    # Ensure player action rows captured both explicit and derived player actions.
    action_codes = {entry.action_code for entry in snapshot.player_actions}
    assert action_codes == {"planted_bomb", "headshot"}
    planted = next(
        entry for entry in snapshot.player_actions if entry.action_code == "planted_bomb"
    )
    assert isinstance(planted, PlayerActionSnapshot)
    assert planted.player_id == alice.player_id

    # The replay helper should record every query issued by the storage layer.
    assert any(
        query.startswith("INSERT INTO hlstats_Events_Admin")
        for query, _ in result.executed_queries
    )
