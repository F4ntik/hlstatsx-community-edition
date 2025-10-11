from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import pytest

from hlstats_py import EventContext, LocalizationCatalog
from hlstats_py.events import (
    ActionDefinition,
    EventDispatcher,
    GameSchema,
    GenericEventHandler,
    ChatEventHandler,
    KillEventHandler,
    TriggerEventHandler,
    WeaponDefinition,
)
from hlstats_py.protocol import parse_log_event
from hlstats_py.storage import (
    _INSERT_ACTION_QUERY,
    _INSERT_CHAT_QUERY,
    _INSERT_FRAG_QUERY,
    _INSERT_PLAYER_ACTION_QUERY,
    _INCREMENT_ACTION_COUNT_QUERY,
    _LAST_INSERT_ID_QUERY,
    _PLAYER_BY_UNIQUE_QUERY,
    _UPDATE_PLAYER_DEATHS_QUERY,
    _UPDATE_PLAYER_KILLS_QUERY,
    _UPDATE_PLAYER_NAME_QUERY,
    _UPSERT_PLAYER_UNIQUE_QUERY,
    _UPSERT_PLAYER_NAME_QUERY,
    _SELECT_ACTION_QUERY,
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


class FakeCursor:
    def __init__(self, store: QueryStore) -> None:
        self._store = store
        self._key: QueryKey | None = None
        self._response: QueryResponse | None = None

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

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._store)

    @property
    def executed(self) -> List[QueryKey]:
        return self._store.executed


class StubAdapter:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

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
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection))

    storage.record(update, event_context)

    timestamp = update.timestamp
    expected = [
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")),
        (_UPSERT_PLAYER_UNIQUE_QUERY, (101, "STEAM_1:2", "csgo")),
        (_UPDATE_PLAYER_NAME_QUERY, ("Alice", 101)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "Alice", timestamp)),
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")),
        (_UPSERT_PLAYER_UNIQUE_QUERY, (102, "STEAM_1:3", "csgo")),
        (_UPDATE_PLAYER_NAME_QUERY, ("Bob", 102)),
        (_UPSERT_PLAYER_NAME_QUERY, (102, "Bob", timestamp)),
        (
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
        ),
        (_UPDATE_PLAYER_KILLS_QUERY, (1, 1, 101)),
        (_UPDATE_PLAYER_DEATHS_QUERY, (102,)),
        (_UPSERT_WEAPON_QUERY, ("csgo", "ak47", "AK-47", 1.0, 1, 1)),
    ]

    assert connection.executed == expected


def test_record_action_creates_missing_definition(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "planted_bomb" (site "A")'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")): [QueryResponse(fetchone=None)],
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(77,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection))

    storage.record(update, event_context)

    timestamp = update.timestamp
    expected = [
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")),
        (_UPSERT_PLAYER_UNIQUE_QUERY, (101, "STEAM_1:2", "csgo")),
        (_UPDATE_PLAYER_NAME_QUERY, ("Alice", 101)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "Alice", timestamp)),
        (_SELECT_ACTION_QUERY, ("csgo", "planted_bomb")),
        (
            _INSERT_ACTION_QUERY,
            ("csgo", "planted_bomb", "Bomb planted", 0, 0, ""),
        ),
        (_LAST_INSERT_ID_QUERY, None),
        (
            _INSERT_PLAYER_ACTION_QUERY,
            (timestamp, 7, "de_dust2", 101, 77, 0),
        ),
        (_INCREMENT_ACTION_COUNT_QUERY, (77,)),
    ]

    assert connection.executed == expected


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
    storage = EventStorage(StubAdapter(connection))

    storage.record(update, event_context)
    storage.record(update, event_context)

    timestamp = update.timestamp
    expected = [
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")),
        (_UPSERT_PLAYER_UNIQUE_QUERY, (101, "STEAM_1:2", "csgo")),
        (_UPDATE_PLAYER_NAME_QUERY, ("Alice", 101)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "Alice", timestamp)),
        (
            _INSERT_CHAT_QUERY,
            (timestamp, 7, "de_dust2", 101, 1, "Hold position"),
        ),
        (_UPSERT_PLAYER_UNIQUE_QUERY, (101, "STEAM_1:2", "csgo")),
        (_UPDATE_PLAYER_NAME_QUERY, ("Alice", 101)),
        (_UPSERT_PLAYER_NAME_QUERY, (101, "Alice", timestamp)),
        (
            _INSERT_CHAT_QUERY,
            (timestamp, 7, "de_dust2", 101, 1, "Hold position"),
        ),
    ]

    assert connection.executed == expected
