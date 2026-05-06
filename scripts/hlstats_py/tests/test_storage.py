from __future__ import annotations

import json
from calendar import timegm
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

from hlstats_py import EventContext, LocalizationCatalog
from hlstats_py.events import (
    ActionDefinition,
    ConnectEventHandler,
    DisconnectEventHandler,
    EntryEventHandler,
    EventDispatcher,
    GameSchema,
    GenericEventHandler,
    ChatEventHandler,
    KillEventHandler,
    TeamEventHandler,
    TeamTriggerEventHandler,
    TriggerEventHandler,
    WeaponDefinition,
)
from hlstats_py.protocol import parse_log_event
from hlstats_py.storage import (
    _ACTIVE_PLAYER_IDLE_TIMEOUT,
    _FINALIZE_PLAYER_LAST_EVENT_QUERY,
    _INSERT_ACTION_QUERY,
    _INSERT_CHAT_QUERY,
    _INSERT_CONNECT_QUERY,
    _INSERT_ENTRY_QUERY,
    _INSERT_PLAYER_QUERY,
    _INSERT_FRAG_QUERY,
    _INSERT_SUICIDE_QUERY,
    _INSERT_PLAYER_ACTION_QUERY,
    _INSERT_PLAYER_PLAYER_ACTION_QUERY,
    _INSERT_TEAM_CHANGE_QUERY,
    _INSERT_TEAMKILL_QUERY,
    _INSERT_TEAM_BONUS_QUERY,
    _INCREMENT_ACTION_COUNT_QUERY,
    _LAST_INSERT_ID_QUERY,
    _PLAYER_BY_UNIQUE_QUERY,
    _SELECT_ACTION_QUERY,
    _SELECT_PLAYER_BOT_UNIQUE_QUERY,
    _SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY,
    _SELECT_DEFAULT_SERVER_CONFIG_QUERY,
    _SELECT_OPTION_QUERY,
    _SELECT_PLAYER_STATE_QUERY,
    _SELECT_SERVER_CONFIG_QUERY,
    _SELECT_WEAPON_MODIFIER_QUERY,
    _DELETE_PLAYER_HISTORY_QUERY,
    _UPDATE_PLAYER_DEATHS_QUERY,
    _UPDATE_PLAYER_FRAG_ROLLUP_QUERY,
    _UPDATE_PLAYER_KILLS_QUERY,
    _UPDATE_PLAYER_SUICIDES_QUERY,
    _UPDATE_PLAYER_NAME_QUERY,
    _UPDATE_PLAYER_SKILL_QUERY,
    _UPDATE_PLAYER_STREAKS_QUERY,
    _UPDATE_PLAYER_TEAMKILLS_QUERY,
    _UPDATE_PLAYER_HISTORY_QUERY,
    _UPDATE_PLAYER_LAST_ADDRESS_QUERY,
    _UPDATE_PLAYERNAME_LASTUSE_QUERY,
    _UPDATE_PLAYERNAME_TOTALS_QUERY,
    _UPDATE_IGNORED_BOT_PLAYER_QUERY,
    _REPLACE_PLAYER_HISTORY_SNAPSHOT_QUERY,
    _UPDATE_SERVER_FRAG_TOTALS_QUERY,
    _UPDATE_SERVER_MAP_LOADING_QUERY,
    _UPDATE_SERVER_MAP_STARTED_QUERY,
    _UPDATE_SERVER_PLAYER_TOTALS_QUERY,
    _UPSERT_PLAYER_UNIQUE_QUERY,
    _UPSERT_PLAYER_HISTORY_QUERY,
    _UPSERT_PLAYER_NAME_QUERY,
    _UPSERT_MAP_COUNTS_QUERY,
    _UPSERT_WEAPON_QUERY,
    EventStorage,
)


@dataclass
class QueryResponse:
    fetchone: Tuple[object, ...] | None = None
    fetchall: Iterable[Tuple[object, ...]] | None = None


QueryKey = Tuple[str, Tuple[object, ...] | None]


@dataclass
class QueryStore:
    responses: Dict[QueryKey, List[QueryResponse]]
    executed: List[QueryKey]
    executemany_batch_sizes: List[int] = field(default_factory=list)


class FakeCursor:
    def __init__(self, store: QueryStore) -> None:
        self._store = store
        self._key: QueryKey | None = None
        self._response: QueryResponse | None = None
        self.executemany_batches: list[tuple[str, int]] = []

    def execute(self, query: str, params: Iterable[object] | None = None) -> None:
        normalized_params = tuple(params) if params is not None else None
        key = (query, normalized_params)
        queue = self._store.responses.get(key)
        if queue is None:
            response = QueryResponse()
        else:
            if not queue:
                raise AssertionError(f"Unexpected call for query {query!r} with params {params!r}")
            response = queue.pop(0)
        self._store.executed.append(key)
        self._key = key
        self._response = response

    def executemany(self, query: str, params: Iterable[Iterable[object]]) -> None:
        rows = list(params)
        self.executemany_batches.append((query, len(rows)))
        self._store.executemany_batch_sizes.append(len(rows))
        for row in rows:
            self.execute(query, row)

    def fetchone(self) -> Tuple[object, ...] | None:
        if self._response is None:
            raise AssertionError("fetchone called before execute")
        return self._response.fetchone

    def fetchall(self) -> Iterable[Tuple[object, ...]]:
        if self._response is None:
            raise AssertionError("fetchall called before execute")
        return list(self._response.fetchall or [])

    def close(self) -> None:  # pragma: no cover - API compliance
        self._key = None
        self._response = None


class FakeConnection:
    def __init__(self, responses: Dict[QueryKey, List[QueryResponse]] | None = None) -> None:
        self._store = QueryStore(responses or {}, [])
        self.autocommit_calls: list[bool] = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.cursor_calls = 0

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return FakeCursor(self._store)

    def autocommit(self, value: bool) -> None:
        self.autocommit_calls.append(value)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    @property
    def executed(self) -> List[QueryKey]:
        return self._store.executed

    @property
    def executemany_batch_sizes(self) -> List[int]:
        return self._store.executemany_batch_sizes


class StubAdapter:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.executemany_chunk_size = 1000

    def connection(self) -> FakeConnection:
        return self._connection


@pytest.fixture()
def event_context() -> EventContext:
    schema = GameSchema(
        game="csgo",
        weapons={
            "ak47": WeaponDefinition(code="ak47", name="AK-47"),
        },
        actions={
            "planted_bomb": ActionDefinition(code="planted_bomb", description="Bomb planted"),
            "round_start": ActionDefinition(code="round_start", description="Round Start"),
        },
    )
    localization = LocalizationCatalog(templates={}, default_template="{event_code}")
    return EventContext(server_id=7, game="csgo", schema=schema, localization=localization, extras={"map": "de_dust2"})


@pytest.fixture()
def dispatcher() -> EventDispatcher:
    generic = GenericEventHandler()
    return EventDispatcher(
        [
            KillEventHandler(),
            TriggerEventHandler(),
            generic,
        ],
        fallback=generic,
    )


def test_record_frag_event_executes_expected_queries(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed "Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot)'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "headshot")): [QueryResponse(fetchone=None)],
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(501,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    timestamp = update.timestamp
    assert (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")) in connection.executed
    assert (
        _INSERT_FRAG_QUERY,
        (
            timestamp,
            7,
            "de_dust2",
            101,
            102,
            "ak47",
            1,
            "",
            "",
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ) in connection.executed
    assert (_UPDATE_SERVER_FRAG_TOTALS_QUERY, (1, 1, 7)) in connection.executed
    assert (_UPSERT_MAP_COUNTS_QUERY, ("csgo", "de_dust2", 1, 1)) in connection.executed
    rollup_calls = [entry for entry in connection.executed if entry[0] == _UPDATE_PLAYER_FRAG_ROLLUP_QUERY]
    assert len(rollup_calls) == 2
    by_player = {entry[1][-1]: entry[1] for entry in rollup_calls}
    assert by_player[101][:5] == (1, 1, 0, 0, 2)
    assert by_player[102][:5] == (0, 0, 1, 0, -2)
    assert (_SELECT_ACTION_QUERY, ("csgo", "headshot")) in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (timestamp, 7, "de_dust2", 101, 501, 0)) in connection.executed
    assert (_INCREMENT_ACTION_COUNT_QUERY, (501,)) in connection.executed


def test_record_action_creates_missing_definition(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "planted_bomb" (site "A")'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")): [QueryResponse(fetchone=None)],
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(77,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    timestamp = update.timestamp
    assert (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")) in connection.executed
    assert (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")) in connection.executed
    assert (
        _INSERT_ACTION_QUERY,
        ("csgo", "planted_bomb", "Bomb planted", 0, 0, ""),
    ) in connection.executed
    assert (_LAST_INSERT_ID_QUERY, None) in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (timestamp, 7, "de_dust2", 101, 77, 0)) in connection.executed
    assert (_INCREMENT_ACTION_COUNT_QUERY, (77,)) in connection.executed


def test_record_action_skips_unresolved_server_actor_without_victim(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event('L 01/02/2024 - 03:04:05: "<><><>" triggered "amx_chat"')
    update = dispatcher.dispatch(event, event_context)
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_PLAYER_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _SELECT_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_PLAYER_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _INCREMENT_ACTION_COUNT_QUERY for query, _params in connection.executed)


@pytest.mark.parametrize(
    ("action_code", "properties"),
    [
        ("time", '(time "0:34")'),
        ("latency", '(ping "44")'),
    ],
)
def test_record_action_skips_status_noise_triggers(
    dispatcher: EventDispatcher,
    event_context: EventContext,
    action_code: str,
    properties: str,
) -> None:
    event = parse_log_event(
        f'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "{action_code}" {properties}'
    )
    update = dispatcher.dispatch(event, event_context)
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _PLAYER_BY_UNIQUE_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_PLAYER_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _SELECT_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_PLAYER_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _INCREMENT_ACTION_COUNT_QUERY for query, _params in connection.executed)


def test_record_action_team_reward_obeys_round_status_gate(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "planted_bomb" (site "A")'
    )
    update = dispatcher.dispatch(event, event_context)
    gated_context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")): [QueryResponse(fetchone=(77, 15, 2))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, gated_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (update.timestamp, 7, "de_dust2", 101, 77, 15)) in connection.executed
    assert all(query != _INSERT_TEAM_BONUS_QUERY for query, _params in connection.executed)


def test_record_suicide_event_uses_suicides_table(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" committed suicide with "worldspawn"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (
        _INSERT_SUICIDE_QUERY,
        (update.timestamp, 7, "de_dust2", 101, "worldspawn", None, None, None),
    ) in connection.executed
    assert (_UPDATE_PLAYER_SUICIDES_QUERY, (101,)) in connection.executed
    assert all(query != _INSERT_FRAG_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_WEAPON_QUERY for query, _params in connection.executed)
    assert all(query != _UPDATE_SERVER_FRAG_TOTALS_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_MAP_COUNTS_QUERY for query, _params in connection.executed)


def test_suicide_ends_active_kill_streak(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    first_kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
        ),
        event_context,
    )
    second_kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:06: "Alice<2><STEAM_1:2><CT>" killed '
            '"Charlie<4><STEAM_1:4><TERRORIST>" with "ak47"'
        ),
        event_context,
    )
    suicide = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "Alice<2><STEAM_1:2><CT>" committed suicide with "worldspawn"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:4", "csgo")): [QueryResponse(fetchone=(103,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "kill_streak_2")): [QueryResponse(fetchone=(702, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_kill.timestamp)

    storage.record(first_kill, event_context)
    storage.record(second_kill, event_context)
    storage.record(suicide, event_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (suicide.timestamp, 7, "de_dust2", 101, 702, 0)) in connection.executed
    assert (_INCREMENT_ACTION_COUNT_QUERY, (702,)) in connection.executed


def test_record_chat_reuses_cached_player(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    chat_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say_team "Hold position"'
    )
    update = chat_dispatcher.dispatch(chat_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)
    storage.record(update, event_context)

    timestamp = update.timestamp
    expected = [
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")),
        (_SELECT_PLAYER_STATE_QUERY, (101,)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "Alice", timestamp)),
        (_UPSERT_PLAYER_HISTORY_QUERY, (101, datetime(2024, 1, 2, 0, 0), "csgo", 1000)),
        (
            _INSERT_CHAT_QUERY,
            (timestamp, 7, "de_dust2", 101, 2, "Hold position"),
        ),
        (_UPSERT_PLAYER_HISTORY_QUERY, (101, datetime(2024, 1, 2, 0, 0), "csgo", 1000)),
        (
            _INSERT_CHAT_QUERY,
            (timestamp, 7, "de_dust2", 101, 2, "Hold position"),
        ),
    ]

    assert connection.executed == expected


def test_player_last_name_is_deferred_until_disconnect(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ChatEventHandler(),
            DisconnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    chat_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "NewName<2><STEAM_1:2><CT>" say "Hold position"'
    )
    disconnect_event = parse_log_event(
        'L 01/02/2024 - 03:04:06: "NewName<2><STEAM_1:2><CT>" disconnected'
    )
    chat_update = dispatcher.dispatch(chat_event, event_context)
    disconnect_update = dispatcher.dispatch(disconnect_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: chat_update.timestamp)

    storage.record(chat_update, event_context)

    assert (_UPSERT_PLAYER_NAME_QUERY, (101, "NewName", chat_update.timestamp)) in connection.executed
    assert all(query != _UPDATE_PLAYER_NAME_QUERY for query, _params in connection.executed)

    storage.record(disconnect_update, event_context)

    assert (_UPDATE_PLAYER_NAME_QUERY, ("NewName", 101)) in connection.executed


def test_name_change_updates_deferred_profile_name(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher([generic], fallback=generic)
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Player<2><STEAM_1:2><CT>" changed name to "LatestName"'
    )
    update = dispatcher.dispatch(event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)
    storage.flush_pending()

    assert (_UPSERT_PLAYER_NAME_QUERY, (101, "Player", update.timestamp)) not in connection.executed
    assert (_UPSERT_PLAYER_NAME_QUERY, (101, "LatestName", update.timestamp)) in connection.executed
    assert (_UPDATE_PLAYER_NAME_QUERY, ("LatestName", 101)) in connection.executed


def test_name_change_back_to_prior_alias_counts_new_alias_use(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher([ChatEventHandler(), generic], fallback=generic)
    first_seen = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "X3<2><STEAM_1:2><CT>" say "ready"'),
        event_context,
    )
    changed_away = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:06: "X3<2><STEAM_1:2><CT>" changed name to "make me laugh"'),
        event_context,
    )
    changed_back = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "make me laugh<2><STEAM_1:2><CT>" changed name to "X3"'),
        event_context,
    )

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_seen.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_seen, event_context)
    storage.record(changed_away, event_context)
    storage.record(changed_back, event_context)

    x3_alias_uses = [
        entry
        for entry in connection.executed
        if entry[0] == _UPSERT_PLAYER_NAME_QUERY and entry[1][1] == "X3"
    ]
    assert x3_alias_uses == [
        (_UPSERT_PLAYER_NAME_QUERY, (101, "X3", first_seen.timestamp)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "X3", changed_back.timestamp)),
    ]
    assert (_UPSERT_PLAYER_NAME_QUERY, (101, "make me laugh", changed_away.timestamp)) in connection.executed


def test_player_name_totals_flush_to_current_alias_after_name_change(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    generic = GenericEventHandler()
    name_dispatcher = EventDispatcher([generic], fallback=generic)
    frag_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot)'
        ),
        event_context,
    )
    name_update = name_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:06: "Alice<2><STEAM_1:2><CT>" changed name to "NewAlice"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "headshot")): [QueryResponse(fetchone=(501, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: frag_update.timestamp)

    storage.record(frag_update, event_context)
    assert all(query != _UPDATE_PLAYERNAME_TOTALS_QUERY for query, _params in connection.executed)

    storage.record(name_update, event_context)
    assert all(query != _UPDATE_PLAYERNAME_TOTALS_QUERY for query, _params in connection.executed)

    storage.finalize_import()

    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (0, 1, 0, 0, 1, 0, 0, 101, "NewAlice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (0, 1, 0, 0, 1, 0, 0, 101, "Alice"),
    ) not in connection.executed


def test_stdin_batch_commit_does_not_flush_player_name_totals(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    frag_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot)'
        ),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "headshot")): [QueryResponse(fetchone=(501, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: frag_update.timestamp)
    storage.begin_stdin_batch(transaction_batch_size=1)

    storage.record(frag_update, event_context)

    assert connection.commit_calls >= 1
    assert all(query != _UPDATE_PLAYERNAME_TOTALS_QUERY for query, _params in connection.executed)

    storage.finalize_import()

    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (0, 1, 0, 0, 1, 0, 0, 101, "Alice"),
    ) in connection.executed


def test_minplayers_gate_primes_player_team_state_before_ignoring_frag(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(4,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert storage._player_teams == {101: "CT", 102: "TERRORIST"}
    assert storage._active_trackable_players(7) == 2
    assert (_INSERT_FRAG_QUERY, None) not in connection.executed
    assert all(query != _INSERT_FRAG_QUERY for query, _params in connection.executed)


def test_minplayers_gate_ignores_bot_players_when_ignorebots_enabled(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" killed '
        '"BotTwo<665><BOT><TERRORIST>" with "ak47"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(2,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert storage._active_trackable_players(7) == 2
    assert all(query != _INSERT_FRAG_QUERY for query, _params in connection.executed)


def test_minplayers_gate_counts_bot_players_when_ignorebots_disabled(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" killed '
        '"BotTwo<665><BOT><TERRORIST>" with "ak47"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(2,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (
        _INSERT_FRAG_QUERY,
        (
            update.timestamp,
            7,
            "de_dust2",
            101,
            102,
            "ak47",
            0,
            "",
            "",
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ) in connection.executed


def test_record_frag_persists_attacker_and_victim_positions(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" '
        '(attacker_position "1 2 3") (victim_position "4 5 6")'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (
        _INSERT_FRAG_QUERY,
        (
            update.timestamp,
            7,
            "de_dust2",
            101,
            102,
            "ak47",
            0,
            "",
            "",
            1,
            2,
            3,
            4,
            5,
            6,
        ),
    ) in connection.executed


def test_record_headshot_frag_matches_legacy_attacker_position_behavior(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot) '
        '(attacker_position "1 2 3") (victim_position "4 5 6")'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_ACTION_QUERY, ("csgo", "headshot")): [QueryResponse(fetchone=(501, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (
        _INSERT_FRAG_QUERY,
        (
            update.timestamp,
            7,
            "de_dust2",
            101,
            102,
            "ak47",
            1,
            "",
            "",
            None,
            None,
            None,
            4,
            5,
            6,
        ),
    ) in connection.executed


def test_connect_event_updates_last_known_address(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" connected, address "1.2.3.4:27005"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (
        _UPDATE_PLAYER_LAST_ADDRESS_QUERY,
        ("1.2.3.4", 101),
    ) in connection.executed


def test_connect_event_does_not_mark_team_reward_eligibility(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" connected, address "1.2.3.4:27005"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert 101 not in storage._server_reward_eligible_players.get(event_context.server_id, set())


def test_transient_lan_unique_id_connect_does_not_create_visible_player(
    event_context: EventContext,
) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Boost en.Prime-server.info<1834><STEAM_ID_LAN><>" '
        'connected, address "54.74.101.183:11122"'
    )
    update = dispatcher.dispatch(event, event_context)
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_PLAYER_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_PLAYER_UNIQUE_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_PLAYER_NAME_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_PLAYER_HISTORY_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_CONNECT_QUERY for query, _params in connection.executed)


def test_steam3_unique_id_is_stored_with_legacy_canonical_form(
    event_context: EventContext,
) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_3:0:247752695><CT>" '
        'connected, address "46.53.250.223:27005"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(315,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPSERT_PLAYER_UNIQUE_QUERY, (315, "0:247752695", "csgo")) in connection.executed


def test_player_action_rewards_active_teammates_once_minplayers_is_met(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><TERRORIST>" triggered "planted_bomb"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(4,))],
        (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")): [QueryResponse(fetchone=(77, 2, 2))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {201, 202, 203}
    storage._server_reward_eligible_players[7] = {101, 201, 202, 203}
    storage._player_teams.update(
        {
            201: "TERRORIST",
            202: "CT",
            203: "CT",
        }
    )

    storage.record(update, event_context)

    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 77, 2),
    ) in connection.executed
    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 201, 77, 2),
    ) in connection.executed


def test_team_bonus_skips_rows_when_reward_team_is_zero(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(4,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102, 103, 104}
    storage._player_teams.update(
        {
            101: "CT",
            102: "CT",
            103: "TERRORIST",
            104: "TERRORIST",
        }
    )

    storage.record(update, event_context)

    assert (_INCREMENT_ACTION_COUNT_QUERY, (755,)) in connection.executed
    assert all(query != _INSERT_TEAM_BONUS_QUERY for query, _params in connection.executed)


def test_unknown_zero_reward_team_bonus_does_not_create_action_definition(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "Target_Saved"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(4,))],
        (_SELECT_ACTION_QUERY, ("csgo", "Target_Saved")): [QueryResponse(fetchone=None)],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102, 103, 104}
    storage._player_teams.update(
        {
            101: "CT",
            102: "CT",
            103: "TERRORIST",
            104: "TERRORIST",
        }
    )

    storage.record(update, event_context)

    assert (_SELECT_ACTION_QUERY, ("csgo", "Target_Saved")) in connection.executed
    assert all(query != _INSERT_ACTION_QUERY for query, _params in connection.executed)


def test_team_bonus_keeps_connected_idle_players_for_reward(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:10:00: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(1,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 2))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(0,))],
        (_SELECT_PLAYER_STATE_QUERY, (102,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_connected_players[7] = {101, 102}
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})
    storage._server_player_last_activity[7] = {
        101: update.timestamp - _ACTIVE_PLAYER_IDLE_TIMEOUT - timedelta(seconds=1),
        102: update.timestamp,
    }

    storage.record(update, event_context)

    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 102, 755, 2),
    ) in connection.executed
    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 755, 2),
    ) in connection.executed


def test_team_bonus_skips_db_known_bot_when_ignore_bots_enabled(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:10:00: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(1,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 2))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
        (_SELECT_PLAYER_BOT_UNIQUE_QUERY, (101,)): [QueryResponse(fetchone=(1,))],
        (_SELECT_PLAYER_BOT_UNIQUE_QUERY, (102,)): [QueryResponse(fetchone=None)],
        (_SELECT_PLAYER_STATE_QUERY, (102,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_connected_players[7] = {101, 102}
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})
    # Simulate cold runtime cache (legacy bot player restored from DB, not yet marked in-memory).
    storage._player_is_bot.pop(101, None)

    storage.record(update, event_context)

    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 755, 2),
    ) not in connection.executed
    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 102, 755, 2),
    ) in connection.executed


def test_disconnect_refreshes_active_player_count(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            DisconnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" disconnected')
    update = dispatcher.dispatch(event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102}
    storage._server_active_players[7] = {101, 102}

    storage.record(update, event_context)

    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (2, 1, 7)) in connection.executed


def test_disconnect_realigns_history_row_to_event_day(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            DisconnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" disconnected')
    update = dispatcher.dispatch(event, event_context)

    processed_at = datetime(2024, 1, 5, 9, 0, 0)
    source_day = datetime(2024, 1, 5, 0, 0)
    target_day = datetime(2024, 1, 2, 0, 0)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (
            _SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY,
            (101, source_day, "csgo"),
        ): [QueryResponse(fetchone=(0, 3, 5, 0, 1013, 2, 85, 21, 0, 3, 2, 13))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: processed_at)
    storage._server_players[7] = {101}
    storage._server_connected_players[7] = {101}
    storage._server_active_players[7] = {101}

    storage.record(update, event_context)

    assert (_UPSERT_PLAYER_HISTORY_QUERY, (101, target_day, "csgo", 1013)) in connection.executed
    assert (
        _REPLACE_PLAYER_HISTORY_SNAPSHOT_QUERY,
        (0, 3, 5, 0, 1013, 2, 85, 21, 0, 3, 2, 13, 101, target_day, "csgo"),
    ) in connection.executed
    assert (_DELETE_PLAYER_HISTORY_QUERY, (101, source_day, "csgo")) in connection.executed


def test_stdin_processing_uses_event_timestamp_for_name_lastuse(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    chat_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say_team "Hold position"'
    )
    update = chat_dispatcher.dispatch(chat_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: datetime(2024, 1, 9, 12, 0, 0),
        use_event_timestamps_for_processing=True,
    )

    storage.record(update, event_context)

    assert (_UPSERT_PLAYER_NAME_QUERY, (101, "Alice", update.timestamp)) in connection.executed


def test_finalize_import_updates_last_event_for_all_players() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))

    storage.finalize_import()

    assert (_FINALIZE_PLAYER_LAST_EVENT_QUERY, None) in connection.executed


def test_finalize_import_flushes_deferred_player_profile_names(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event('L 01/02/2024 - 03:04:05: "NewName<2><STEAM_1:2><CT>" say "ready"')
    update = chat_dispatcher.dispatch(event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)
    assert all(query != _UPDATE_PLAYER_NAME_QUERY for query, _params in connection.executed)

    storage.finalize_import()

    assert (_UPDATE_PLAYER_NAME_QUERY, ("NewName", 101)) in connection.executed


def test_flush_pending_flushes_deferred_player_profile_names(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event('L 01/02/2024 - 03:04:05: "NewName<2><STEAM_1:2><CT>" say "ready"')
    update = chat_dispatcher.dispatch(event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)
    assert all(query != _UPDATE_PLAYER_NAME_QUERY for query, _params in connection.executed)

    storage.flush_pending()

    assert (_UPDATE_PLAYER_NAME_QUERY, ("NewName", 101)) in connection.executed


def test_unique_id_reconnect_counts_alias_use_for_new_userid(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler()])
    first_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Player<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
    )
    second_event = parse_log_event(
        'L 01/02/2024 - 03:04:35: "Player<3><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
    )
    first_update = dispatcher.dispatch(first_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)

    alias_uses = [
        entry
        for entry in connection.executed
        if entry == (_UPSERT_PLAYER_NAME_QUERY, (101, "Player", first_update.timestamp))
        or entry == (_UPSERT_PLAYER_NAME_QUERY, (101, "Player", second_update.timestamp))
    ]
    assert len(alias_uses) == 2


def test_reconnect_after_disconnect_counts_alias_use_for_same_userid(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ChatEventHandler(), DisconnectEventHandler()])
    first_event = parse_log_event('L 01/02/2024 - 03:04:05: "X3<2><STEAM_1:2><CT>" say "ready"')
    disconnect_event = parse_log_event('L 01/02/2024 - 03:04:06: "X3<2><STEAM_1:2><CT>" disconnected')
    second_event = parse_log_event('L 01/02/2024 - 03:04:07: "X3<2><STEAM_1:2><CT>" say "back"')
    first_update = dispatcher.dispatch(first_event, event_context)
    disconnect_update = dispatcher.dispatch(disconnect_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.record(disconnect_update, event_context)
    storage.record(second_update, event_context)

    alias_uses = [
        entry
        for entry in connection.executed
        if entry[0] == _UPSERT_PLAYER_NAME_QUERY and entry[1][1] == "X3"
    ]
    assert alias_uses == [
        (_UPSERT_PLAYER_NAME_QUERY, (101, "X3", first_update.timestamp)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "X3", second_update.timestamp)),
    ]


def test_reconnect_after_started_map_counts_alias_use_for_same_userid(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ChatEventHandler()])
    first_event = parse_log_event('L 01/02/2024 - 03:04:05: "X3<2><STEAM_1:2><CT>" say "ready"')
    second_event = parse_log_event('L 01/02/2024 - 03:05:07: "X3<2><STEAM_1:2><CT>" say "back"')
    first_update = dispatcher.dispatch(first_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    before_transition = len(connection.executed)

    started_at = datetime(2024, 1, 2, 3, 5, 0)
    storage.apply_server_map_transition(event_context.server_id, "started", "de_nuke", started_at)

    transition_entries = connection.executed[before_transition:]
    assert (_UPDATE_SERVER_MAP_STARTED_QUERY, ("de_nuke", int(timegm(started_at.timetuple())), 7)) in transition_entries
    assert all(query != _UPDATE_PLAYER_NAME_QUERY for query, _params in transition_entries)

    storage.record(second_update, event_context)

    alias_uses = [
        entry
        for entry in connection.executed
        if entry[0] == _UPSERT_PLAYER_NAME_QUERY and entry[1][1] == "X3"
    ]
    assert alias_uses == [
        (_UPSERT_PLAYER_NAME_QUERY, (101, "X3", first_update.timestamp)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "X3", second_update.timestamp)),
    ]


def test_teamkill_records_teamkill_event_and_penalty(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><TERRORIST>" killed '
        '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (headshot) '
        '(attacker_position "1 2 3") (victim_position "4 5 6")'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "TKPenalty")): [QueryResponse(fetchone=(25,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_FRAG_QUERY for query, _params in connection.executed)
    assert (
        _INSERT_TEAMKILL_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 102, "ak47", None, None, None, 4, 5, 6),
    ) in connection.executed
    assert (_UPDATE_PLAYER_TEAMKILLS_QUERY, (101,)) in connection.executed
    assert (_UPDATE_PLAYER_SKILL_QUERY, (-25, 101)) in connection.executed


def test_stdin_batch_event_buffer_executemany_multi_row(event_context: EventContext) -> None:
    """Append-only inserts should batch across record() calls until buffer policy flushes."""

    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [
            QueryResponse(fetchone=(101,)),
            QueryResponse(fetchone=(101,)),
            QueryResponse(fetchone=(101,)),
        ],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: datetime(2024, 1, 2, 3, 4, 5))
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage.configure_event_buffer(max_buffered_events=2)

    for suffix in ("one", "two", "three"):
        event = parse_log_event(
            f'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "msg-{suffix}"'
        )
        update = chat_dispatcher.dispatch(event, event_context)
        storage.record(update, event_context)

    storage.end_stdin_batch()

    assert max(connection.executemany_batch_sizes) > 1
    chat_inserts = [e for e in connection.executed if e[0] == _INSERT_CHAT_QUERY]
    assert len(chat_inserts) == 3


def test_stdin_batch_mode_commits_and_restores_autocommit(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say_team "Hold position"')
    update = chat_dispatcher.dispatch(event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage.begin_stdin_batch(transaction_batch_size=3)

    storage.record(update, event_context)
    storage.finalize_import()
    storage.end_stdin_batch()

    assert connection.autocommit_calls == [False, True]
    assert connection.commit_calls >= 1
    assert connection.rollback_calls == 0
    assert connection.cursor_calls == 1


def test_lookup_does_not_merge_name_only_players_without_unique_id(
    event_context: EventContext,
) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    first_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Player<2><><CT>" say "first"'
    )
    second_event = parse_log_event(
        'L 01/02/2024 - 03:04:06: "Player<3><><TERRORIST>" say "second"'
    )
    first_update = chat_dispatcher.dispatch(first_event, event_context)
    second_update = chat_dispatcher.dispatch(second_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(102,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)

    insert_player_calls = [entry for entry in connection.executed if entry[0] == _INSERT_PLAYER_QUERY]
    assert len(insert_player_calls) == 2
    assert all(query != _UPDATE_PLAYER_NAME_QUERY for query, _params in connection.executed)


def test_empty_descriptor_without_unique_id_does_not_create_player(
    event_context: EventContext,
) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event('L 01/02/2024 - 03:04:05: "<2><><CT>" say "noise"')
    update = chat_dispatcher.dispatch(event, event_context)

    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_PLAYER_QUERY for query, _params in connection.executed)
    assert all(query != _UPDATE_PLAYER_NAME_QUERY for query, _params in connection.executed)
    chat_rows = [entry for entry in connection.executed if entry[0] == _INSERT_CHAT_QUERY]
    assert len(chat_rows) == 1
    assert chat_rows[0][1][3] == 0


def test_transient_lan_unique_id_chat_does_not_create_player_or_chat(
    event_context: EventContext,
) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Boost en.Prime-server.info<1834><STEAM_ID_LAN><SPECTATOR>" '
        'say "Buy players at SERVERBOOST.ML"'
    )
    update = chat_dispatcher.dispatch(event, event_context)
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_PLAYER_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_PLAYER_UNIQUE_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_PLAYER_NAME_QUERY for query, _params in connection.executed)
    assert all(query != _UPSERT_PLAYER_HISTORY_QUERY for query, _params in connection.executed)
    assert all(query != _INSERT_CHAT_QUERY for query, _params in connection.executed)


def test_lookup_does_not_merge_different_bot_players(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    first_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" say "first"'
    )
    second_event = parse_log_event(
        'L 01/02/2024 - 03:04:06: "BotTwo<665><BOT><TERRORIST>" say "second"'
    )
    first_update = chat_dispatcher.dispatch(first_event, event_context)
    second_update = chat_dispatcher.dispatch(second_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,)), QueryResponse(fetchone=(202,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)

    insert_player_calls = [entry for entry in connection.executed if entry[0] == _INSERT_PLAYER_QUERY]
    assert len(insert_player_calls) == 2


def test_ignore_bots_marks_bot_hidden_and_skips_chat(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event('L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" say "first"')
    update = chat_dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPDATE_IGNORED_BOT_PLAYER_QUERY, (201,)) in connection.executed
    assert all(query != _INSERT_CHAT_QUERY for query, _params in connection.executed)


def test_ignore_bots_keeps_history_seed_skill_at_legacy_default(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    event = parse_log_event('L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" say "first"')
    update = chat_dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPDATE_IGNORED_BOT_PLAYER_QUERY, (201,)) in connection.executed
    assert (
        _UPSERT_PLAYER_HISTORY_QUERY,
        (201, datetime(2024, 1, 2, 0, 0), "csgo", 1000),
    ) in connection.executed


def test_ignore_bots_skips_name_change_profile_update(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ChatEventHandler(), GenericEventHandler()])
    first_event = parse_log_event('L 01/02/2024 - 03:04:05: "49.5 % karrigan<664><BOT><CT>" say "first"')
    rename_event = parse_log_event(
        'L 01/02/2024 - 03:04:06: "49.5 % karrigan<664><BOT><CT>" changed name to "49.5 \uff05 karrigan"'
    )
    first_update = dispatcher.dispatch(first_event, event_context)
    rename_update = dispatcher.dispatch(rename_event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, event_context)
    storage.record(rename_update, event_context)

    alias_touches = [params for query, params in connection.executed if query == _UPSERT_PLAYER_NAME_QUERY]
    assert alias_touches == [(201, "49.5 % karrigan", first_update.timestamp)]
    assert storage._player_names[201] == "49.5 % karrigan"


def test_ignore_bots_skips_frag_when_bot_participates(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" killed '
        '"Alice<2><STEAM_1:2><TERRORIST>" with "ak47"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,)), QueryResponse(fetchone=(202,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPDATE_IGNORED_BOT_PLAYER_QUERY, (201,)) in connection.executed
    assert all(query != _INSERT_FRAG_QUERY for query, _params in connection.executed)
    assert all(query != _UPDATE_SERVER_FRAG_TOTALS_QUERY for query, _params in connection.executed)


def test_ignore_bots_skips_action_when_target_is_bot(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered '
        '"planted_bomb" against "BotOne<664><BOT><TERRORIST>"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,)), QueryResponse(fetchone=(202,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
        (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")): [QueryResponse(fetchone=(77, 5, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPDATE_IGNORED_BOT_PLAYER_QUERY, (202,)) in connection.executed
    assert all(query != _INSERT_PLAYER_PLAYER_ACTION_QUERY for query, _params in connection.executed)
    assert all(query != _INCREMENT_ACTION_COUNT_QUERY for query, _params in connection.executed)


def test_ignored_bot_profile_cache_is_cleared_on_rollback(event_context: EventContext) -> None:
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)

    storage._apply_ignored_bot_profile(connection, event_context, 201)
    storage._rollback_pending()
    storage._apply_ignored_bot_profile(connection, event_context, 201)

    profile_updates = [entry for entry in connection.executed if entry[0] == _UPDATE_IGNORED_BOT_PLAYER_QUERY]
    assert len(profile_updates) == 2
    assert connection.rollback_calls == 1


def test_apply_server_map_transition_loading_query() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    ts = datetime(2024, 1, 1, 0, 0, 29)
    storage.apply_server_map_transition(7, "loading", "de_inferno", ts)
    assert connection.executed == [(_UPDATE_SERVER_MAP_LOADING_QUERY, ("de_inferno", 7))]


def test_apply_server_map_transition_started_query() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    storage._server_active_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102, 103}
    storage._server_reward_eligible_players[7] = {101, 103}
    storage._server_player_last_activity[7] = {
        101: datetime(2024, 1, 1, 0, 0, 28),
        103: datetime(2024, 1, 1, 0, 0, 30),
    }
    storage._player_teams.update({101: "CT", 102: "TERRORIST", 103: "CT"})
    ts = datetime(2024, 1, 1, 0, 0, 31)
    storage.apply_server_map_transition(7, "started", "de_nuke", ts)
    expected_unix = int(timegm(ts.timetuple()))
    assert connection.executed == [
        (_UPDATE_SERVER_MAP_STARTED_QUERY, ("de_nuke", expected_unix, 7)),
    ]
    assert storage._server_active_players[7] == set()
    assert storage._server_connected_players[7] == set()
    assert storage._server_reward_eligible_players[7] == set()
    assert storage._server_player_last_activity[7] == {}
    assert 101 not in storage._player_teams
    assert 102 not in storage._player_teams
    assert 103 not in storage._player_teams


def test_apply_server_map_transition_started_normalizes_aware_timestamp() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    ts = datetime(2024, 6, 15, 10, 15, 42, tzinfo=timezone.utc)
    storage.apply_server_map_transition(3, "started", "de_dust2", ts)
    expected_naive = datetime(2024, 6, 15, 10, 15, 42)
    expected_unix = int(timegm(expected_naive.timetuple()))
    assert connection.executed[-1][1] == ("de_dust2", expected_unix, 3)


def test_prune_idle_players_keeps_connected_players() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    server_id = 7
    now = datetime(2024, 1, 1, 12, 0, 0)
    stale_seen = now - timedelta(seconds=300)
    storage._server_active_players[server_id] = {101, 102}
    storage._server_connected_players[server_id] = {101}
    storage._server_reward_eligible_players[server_id] = {101, 102}
    storage._server_player_last_activity[server_id] = {101: stale_seen, 102: stale_seen}

    storage._prune_idle_players(connection, server_id, now)

    assert 101 in storage._server_active_players[server_id]
    assert 102 not in storage._server_active_players[server_id]
    assert 101 in storage._server_reward_eligible_players[server_id]
    assert 102 not in storage._server_reward_eligible_players[server_id]


def test_prune_idle_players_flushes_profile_name_before_eviction(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/01/2024 - 12:00:00: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    stale_seen = update.timestamp - _ACTIVE_PLAYER_IDLE_TIMEOUT - timedelta(seconds=1)
    storage._player_names[102] = "LatestName"
    storage._server_active_players[event_context.server_id] = {102}
    storage._server_reward_eligible_players[event_context.server_id] = {102}
    storage._server_player_last_activity[event_context.server_id] = {102: stale_seen}

    storage.record(update, event_context)

    assert (_UPDATE_PLAYER_NAME_QUERY, ("LatestName", 102)) in connection.executed
    assert 102 not in storage._server_active_players[event_context.server_id]
    assert 102 not in storage._server_reward_eligible_players[event_context.server_id]


def test_reconnect_after_idle_prune_counts_alias_use_for_same_userid(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ChatEventHandler()])
    first_event = parse_log_event('L 01/01/2024 - 12:00:00: "fnat1k<2><STEAM_1:2><CT>" say "ready"')
    second_event = parse_log_event('L 01/01/2024 - 12:05:00: "fnat1k<2><STEAM_1:2><CT>" say "back"')
    first_update = dispatcher.dispatch(first_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage._server_connected_players[event_context.server_id].discard(101)
    storage._server_player_last_activity[event_context.server_id][101] = (
        second_update.timestamp - _ACTIVE_PLAYER_IDLE_TIMEOUT - timedelta(seconds=1)
    )

    storage._prune_idle_players(connection, event_context.server_id, second_update.timestamp)

    assert (_UPDATE_PLAYER_NAME_QUERY, ("fnat1k", 101)) in connection.executed

    storage.record(second_update, event_context)

    alias_uses = [
        entry
        for entry in connection.executed
        if entry[0] == _UPSERT_PLAYER_NAME_QUERY and entry[1][1] == "fnat1k"
    ]
    assert alias_uses == [
        (_UPSERT_PLAYER_NAME_QUERY, (101, "fnat1k", first_update.timestamp)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "fnat1k", second_update.timestamp)),
    ]


def test_apply_server_map_transition_invalid_phase() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    with pytest.raises(ValueError, match="unsupported map lifecycle"):
        storage.apply_server_map_transition(1, "unknown", "x", datetime(2024, 1, 1))


def test_record_team_change_ignores_bot_players(event_context: EventContext) -> None:
    team_dispatcher = EventDispatcher([TeamEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" joined team "TERRORIST"')
    update = team_dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(301,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_TEAM_CHANGE_QUERY for query, _params in connection.executed)


def test_record_team_change_deduplicates_same_signature(event_context: EventContext) -> None:
    team_dispatcher = EventDispatcher([TeamEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" joined team "TERRORIST"')
    update = team_dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)
    storage.record(update, event_context)

    insert_team_change_calls = [
        entry for entry in connection.executed if entry[0] == _INSERT_TEAM_CHANGE_QUERY
    ]
    assert len(insert_team_change_calls) == 1


def test_team_bonus_obeys_round_status_gate(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,)), QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [
            QueryResponse(fetchone=(755, 0, 2)),
            QueryResponse(fetchone=(755, 0, 2)),
        ],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})

    storage.record(update, context)

    assert (_INCREMENT_ACTION_COUNT_QUERY, (755,)) in connection.executed
    assert all(query != _INSERT_TEAM_BONUS_QUERY for query, _params in connection.executed)


def test_team_bonus_awards_team_when_round_status_is_zero(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,)), QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [
            QueryResponse(fetchone=(755, 0, 2)),
            QueryResponse(fetchone=(755, 0, 2)),
        ],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})

    storage.record(update, context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 2


def test_team_bonus_awards_trackable_team_player_without_entry(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 2))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101}
    storage._server_reward_eligible_players[7] = set()
    storage._player_teams[101] = "CT"

    storage.record(update, context)

    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 755, 2),
    ) in connection.executed


def test_team_bonus_deduplicates_same_signature(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [
            QueryResponse(fetchone=(0,)),
            QueryResponse(fetchone=(0,)),
        ],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [
            QueryResponse(fetchone=(755, 0, 2)),
            QueryResponse(fetchone=(755, 0, 2)),
        ],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})

    storage.record(update, context)
    storage.record(update, context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 2


def test_team_bonus_trace_groups_by_event_signature(
    event_context: EventContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 2))],
    }
    trace_path = Path(__file__).with_name(".tmp-team-bonus-trace.json")
    trace_path.unlink(missing_ok=True)
    monkeypatch.setenv("HLSTATS_TEAM_BONUS_TRACE_PATH", str(trace_path))
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "TERRORIST"})

    try:
        storage.record(update, context)
        storage.finalize_import()

        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        event_key = "2024-01-02 03:04:05|755|de_dust2|CT"
        assert payload["stage_event_counts"]["candidate_set"][event_key] == 2
        assert payload["stage_event_counts"]["inserted"][event_key] == 1
        assert payload["stage_event_counts"]["team_gate_reject"][event_key] == 1
    finally:
        trace_path.unlink(missing_ok=True)


def test_team_bonus_rescued_hostage_allows_same_second_duplicates(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "Rescued_A_Hostage"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [
            QueryResponse(fetchone=(0,)),
            QueryResponse(fetchone=(0,)),
        ],
        (_SELECT_ACTION_QUERY, ("csgo", "Rescued_A_Hostage")): [
            QueryResponse(fetchone=(272, 0, 1, "CT")),
            QueryResponse(fetchone=(272, 0, 1, "CT")),
        ],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})

    storage.record(update, context)
    storage.record(update, context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 4


def test_team_bonus_skips_bots_when_ignore_bots_enabled(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 2))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})
    storage._player_is_bot[102] = True

    storage.record(update, context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 1
    assert insert_rows[0][1][3] == 101


def test_entry_event_ignores_bots(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), EntryEventHandler()],
        fallback=GenericEventHandler(),
    )
    connect_event = parse_log_event(
        'L 01/02/2024 - 03:04:04: "BotOne<664><BOT><CT>" connected, address "1.2.3.4:27005"'
    )
    entry_event = parse_log_event('L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" entered the game')
    connect_update = dispatcher.dispatch(connect_event, event_context)
    entry_update = dispatcher.dispatch(entry_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(301,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: datetime(2024, 1, 2, 3, 4, 5))

    storage.record(connect_update, event_context)
    storage.record(entry_update, event_context)

    assert all(query != _INSERT_ENTRY_QUERY for query, _params in connection.executed)
