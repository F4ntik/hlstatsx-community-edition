from __future__ import annotations

import json
from calendar import timegm
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

from hlstats_py import EventContext, LocalizationCatalog, ReplayRunner
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
    WorldEventHandler,
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
    _UPDATE_SERVER_CT_SHOTS_HITS_QUERY,
    _UPDATE_SERVER_TS_SHOTS_HITS_QUERY,
    _UPDATE_PLAYER_SHOTS_HITS_QUERY,
    _UPSERT_PLAYER_UNIQUE_QUERY,
    _UPSERT_PLAYER_HISTORY_QUERY,
    _UPSERT_PLAYER_NAME_QUERY,
    _UPSERT_MAP_COUNTS_QUERY,
    _UPSERT_WEAPON_QUERY,
    EventStorage,
    StorageError,
)

_UPDATE_SERVER_SUICIDE_TOTALS_QUERY = "UPDATE hlstats_Servers SET `suicides` = `suicides` + 1 WHERE `serverId` = %s"
_UPDATE_PLAYER_CONNECTION_TIME_QUERY = (
    "UPDATE hlstats_Players SET `connection_time` = `connection_time` + %s WHERE `playerId` = %s"
)
_UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY = (
    "UPDATE hlstats_Players SET `last_skill_change` = %s WHERE `playerId` = %s"
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
        self.skip_connection_ping_calls: list[bool] = []

    def connection(self) -> FakeConnection:
        return self._connection

    def set_skip_connection_ping(self, enabled: bool) -> None:
        self.skip_connection_ping_calls.append(enabled)


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


def test_db_write_trace_env_records_pre_batch_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace_path = tmp_path / "writes.jsonl"
    monkeypatch.setenv("HLSTATS_DB_WRITE_TRACE_PATH", str(trace_path))
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))

    storage._execute(connection, _UPDATE_PLAYER_SKILL_QUERY, (5, 162))

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload == {
        "sql": _UPDATE_PLAYER_SKILL_QUERY,
        "params": [5, 162],
    }


def test_stdin_batch_toggles_adapter_connection_ping() -> None:
    adapter = StubAdapter(FakeConnection())
    storage = EventStorage(adapter)

    storage.begin_stdin_batch(transaction_batch_size=2)
    storage.end_stdin_batch()

    assert adapter.skip_connection_ping_calls == [True, False]


def test_disabled_stdin_batch_keeps_adapter_connection_ping_enabled() -> None:
    adapter = StubAdapter(FakeConnection())
    storage = EventStorage(adapter)

    storage.begin_stdin_batch(transaction_batch_size=0)
    storage.end_stdin_batch()

    assert adapter.skip_connection_ping_calls == [False, False]


def test_db_write_trace_reuses_open_file_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace_path = tmp_path / "writes.jsonl"
    monkeypatch.setenv("HLSTATS_DB_WRITE_TRACE_PATH", str(trace_path))
    open_calls = 0
    original_open = Path.open

    def counting_open(self: Path, *args: object, **kwargs: object):
        nonlocal open_calls
        if self == trace_path:
            open_calls += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))

    storage._execute(connection, _UPDATE_PLAYER_SKILL_QUERY, (5, 162))
    storage._execute(connection, _UPDATE_PLAYER_SKILL_QUERY, (6, 163))
    storage.end_stdin_batch()

    assert open_calls == 1
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"sql": _UPDATE_PLAYER_SKILL_QUERY, "params": [5, 162]},
        {"sql": _UPDATE_PLAYER_SKILL_QUERY, "params": [6, 163]},
    ]


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


def test_record_action_rescued_hostage_team_reward_ignores_round_status_gate(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "Rescued_A_Hostage"'
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
        (_SELECT_ACTION_QUERY, ("csgo", "Rescued_A_Hostage")): [QueryResponse(fetchone=(272, 0, 1, "CT"))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})

    storage.record(update, gated_context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 2


def test_record_action_cstrike_planted_the_bomb_team_reward_ignores_round_status_gate(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><TERRORIST>" triggered "Planted_The_Bomb"'
    )
    update = dispatcher.dispatch(event, event_context)
    assert update is not None
    gated_context = EventContext(
        server_id=event_context.server_id,
        game="cstrike",
        schema=GameSchema(game="cstrike", weapons={}, actions={}),
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "cstrike")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("cstrike", "Planted_The_Bomb")): [QueryResponse(fetchone=(269, 0, 2, "TERRORIST"))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102, 103}
    storage._server_reward_eligible_players[7] = {101, 102, 103}
    storage._player_teams.update({101: "TERRORIST", 102: "TERRORIST", 103: "CT"})

    storage.record(update, gated_context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 2
    assert (_INSERT_TEAM_BONUS_QUERY, (update.timestamp, 7, "de_dust2", 101, 269, 2)) in insert_rows
    assert (_INSERT_TEAM_BONUS_QUERY, (update.timestamp, 7, "de_dust2", 102, 269, 2)) in insert_rows


def test_player_player_action_penalizes_victim_skill_like_legacy(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "domination")): [QueryResponse(fetchone=(88, 15, 0, ""))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (
        _INSERT_PLAYER_PLAYER_ACTION_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 102, 88, 15),
    ) in connection.executed
    assert (_UPDATE_PLAYER_SKILL_QUERY, (15, 101)) in connection.executed
    assert (_UPDATE_PLAYER_SKILL_QUERY, (-15, 102)) in connection.executed
    assert all(query != _UPDATE_PLAYER_HISTORY_QUERY for query, _params in connection.executed)

    storage.flush_pending()

    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (0, 0, 0, 0, 985, 0, 0, 0, 0, 0, 0, 0, 0, -15, 102, datetime(2024, 1, 2), "csgo"),
    ) in connection.executed


def test_player_player_action_updates_daily_last_skill_change(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "domination")): [QueryResponse(fetchone=(88, 15, 0, ""))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
        (_SELECT_PLAYER_STATE_QUERY, (102,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY for query, _params in connection.executed)

    storage.flush_pending()

    assert (_UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY, (15, 101)) in connection.executed
    assert (_UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY, (-15, 102)) in connection.executed


def test_player_last_skill_change_accumulates_across_same_day_flushes(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    first_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    second_event = parse_log_event(
        'L 01/02/2024 - 03:05:05: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    first_update = dispatcher.dispatch(first_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "domination")): [QueryResponse(fetchone=(88, 15, 0, ""))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
        (_SELECT_PLAYER_STATE_QUERY, (102,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: second_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.flush_pending()
    storage.record(second_update, event_context)
    storage.flush_pending()

    actor_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY and params[1] == 101
    ]
    victim_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY and params[1] == 102
    ]

    assert actor_updates[0] == (15, 101)
    assert actor_updates[-1] == (30, 101)
    assert set(actor_updates) == {(15, 101), (30, 101)}
    assert victim_updates[0] == (-15, 102)
    assert victim_updates[-1] == (-30, 102)
    assert set(victim_updates) == {(-15, 102), (-30, 102)}


def test_player_last_skill_change_does_not_double_count_multiple_events_before_flush(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    first_event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    second_event = parse_log_event(
        'L 01/02/2024 - 03:04:06: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    first_update = dispatcher.dispatch(first_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "domination")): [QueryResponse(fetchone=(88, 15, 0, ""))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
        (_SELECT_PLAYER_STATE_QUERY, (102,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: second_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)
    storage.flush_pending()

    actor_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY and params[1] == 101
    ]
    victim_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY and params[1] == 102
    ]

    assert actor_updates[-1] == (30, 101)
    assert victim_updates[-1] == (-30, 102)


def test_player_last_skill_change_resets_on_new_history_day(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    first_event = parse_log_event(
        'L 01/02/2024 - 23:59:50: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    second_event = parse_log_event(
        'L 01/03/2024 - 00:00:05: "Alice<2><STEAM_1:2><CT>" triggered "domination" '
        'against "Bob<3><STEAM_1:3><TERRORIST>"'
    )
    first_update = dispatcher.dispatch(first_event, event_context)
    second_update = dispatcher.dispatch(second_event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "domination")): [QueryResponse(fetchone=(88, 15, 0, ""))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
        (_SELECT_PLAYER_STATE_QUERY, (102,)): [QueryResponse(fetchone=(1000, 0, "", 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: second_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.flush_pending()
    storage.record(second_update, event_context)
    storage.flush_pending()

    actor_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY and params[1] == 101
    ]
    victim_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY and params[1] == 102
    ]

    assert actor_updates[0] == (15, 101)
    assert actor_updates[-1] == (15, 101)
    assert (30, 101) not in actor_updates
    assert victim_updates[0] == (-15, 102)
    assert victim_updates[-1] == (-15, 102)
    assert (-30, 102) not in victim_updates


def test_ignore_bots_keep_last_skill_change_neutral_on_flush(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler(), DisconnectEventHandler()])
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    disconnect_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:12: "BotOne<664><BOT><CT>" disconnected'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: connect_update.timestamp)

    storage.record(connect_update, event_context)
    storage.record(disconnect_update, event_context)

    assert (_UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY, (0, 201)) in connection.executed


def test_ignored_bot_history_seed_state_is_reset_per_source_log_epoch() -> None:
    storage = EventStorage(StubAdapter(FakeConnection()))
    storage._ignored_bot_history_seeded.add((7, "bot:abc", 664, 201))
    storage.mark_source_log_boundary(7)
    assert storage._ignored_bot_history_seeded == set()
    storage._ignored_bot_history_seeded.add((8, "bot:abc", 664, 201))
    storage.mark_source_log_boundary(7)
    assert storage._ignored_bot_history_seeded == {(8, "bot:abc", 664, 201)}


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


def test_suicide_applies_legacy_skill_penalty(dispatcher: EventDispatcher, event_context: EventContext) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" committed suicide with "worldspawn"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "SuicidePenalty")): [QueryResponse(fetchone=(5,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPDATE_PLAYER_SKILL_QUERY, (-5, 101)) in connection.executed
    assert all(query != _UPDATE_PLAYER_HISTORY_QUERY for query, _params in connection.executed)

    storage.flush_pending()

    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (0, 0, 0, 1, 995, 0, 0, 0, 0, 0, 0, 0, 0, -5, 101, datetime(2024, 1, 2), "csgo"),
    ) in connection.executed


def test_suicide_after_same_second_team_change_is_ignored(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([KillEventHandler(), TeamEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    team_change = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" joined team "TERRORIST"'),
        event_context,
    )
    suicide = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><TERRORIST>" committed suicide with "worldspawn"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: team_change.timestamp)

    storage.record(team_change, event_context)
    storage.record(suicide, event_context)

    assert all(query != _INSERT_SUICIDE_QUERY for query, _params in connection.executed)
    assert all(query != _UPDATE_PLAYER_SUICIDES_QUERY for query, _params in connection.executed)
    assert all(query != _UPDATE_SERVER_SUICIDE_TOTALS_QUERY for query, _params in connection.executed)


def test_suicide_at_team_change_plus_two_seconds_is_accepted(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([KillEventHandler(), TeamEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    team_change = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" joined team "TERRORIST"'),
        event_context,
    )
    suicide = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "Alice<2><STEAM_1:2><TERRORIST>" committed suicide with "worldspawn"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: team_change.timestamp)

    storage.record(team_change, event_context)
    storage.record(suicide, event_context)

    assert (
        _INSERT_SUICIDE_QUERY,
        (suicide.timestamp, 7, "de_dust2", 101, "worldspawn", None, None, None),
    ) in connection.executed
    assert (_UPDATE_PLAYER_SUICIDES_QUERY, (101,)) in connection.executed
    assert (_UPDATE_SERVER_SUICIDE_TOTALS_QUERY, (7,)) in connection.executed


def test_accepted_suicide_increments_player_and_server_counters(
    dispatcher: EventDispatcher, event_context: EventContext
) -> None:
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" committed suicide with "worldspawn"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_UPDATE_PLAYER_SUICIDES_QUERY, (101,)) in connection.executed
    assert (_UPDATE_SERVER_SUICIDE_TOTALS_QUERY, (7,)) in connection.executed


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


def test_restart_round_does_not_end_kill_streak_before_actual_life_end(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([KillEventHandler(), WorldEventHandler()], fallback=GenericEventHandler())
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
    restart_round = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: World triggered "Restart_Round_(1_second)"'),
        event_context,
    )
    life_end = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:08: "Bob<3><STEAM_1:3><TERRORIST>" killed '
            '"Alice<2><STEAM_1:2><CT>" with "ak47"'
        ),
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
    storage.record(restart_round, event_context)
    storage.record(life_end, event_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (restart_round.timestamp, 7, "de_dust2", 101, 702, 0)) not in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (life_end.timestamp, 7, "de_dust2", 101, 702, 0)) in connection.executed


def test_history_samples_kill_streak_only_after_life_end_flush(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), KillEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    connected = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:00: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
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
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: World triggered "Round_End"'),
        event_context,
    )
    history_timestamp = datetime(2024, 1, 2)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:4", "csgo")): [QueryResponse(fetchone=(103,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "kill_streak_2")): [QueryResponse(fetchone=(702, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: connected.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(connected, event_context)
    storage.record(first_kill, event_context)
    storage.record(second_kill, event_context)

    pre_boundary_history = [
        params
        for query, params in connection.executed
        if query == _UPDATE_PLAYER_HISTORY_QUERY and params[-3:] == (101, history_timestamp, "csgo")
    ]
    assert pre_boundary_history == []

    storage.record(round_end, event_context)
    storage.flush_pending()

    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (7, 0, 0, 0, 1004, 0, 0, 0, 0, 0, 0, 2, 2, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_history_samples_single_kill_streak_without_derived_action(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), KillEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    connected = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:00: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
        ),
        event_context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: World triggered "Round_End"'),
        event_context,
    )
    history_timestamp = datetime(2024, 1, 2)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: connected.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(connected, event_context)
    storage.record(kill, event_context)
    storage.record(round_end, event_context)
    storage.flush_pending()

    assert all(query != _INSERT_PLAYER_ACTION_QUERY for query, _params in connection.executed)
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (7, 0, 0, 0, 1002, 0, 0, 0, 0, 0, 0, 1, 1, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_victim_history_rollup_waits_for_legacy_player_flush(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([KillEventHandler()])
    alice_death = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 23:59:50: "Bob<3><STEAM_1:3><TERRORIST>" killed '
            '"Alice<2><STEAM_1:2><CT>" with "ak47"'
        ),
        event_context,
    )
    alice_next_flush = dispatcher.dispatch(
        parse_log_event(
            'L 01/03/2024 - 00:00:05: "Alice<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
        ),
        event_context,
    )
    alice_id = 101
    bob_id = 102
    death_day = datetime(2024, 1, 2)
    flush_day = datetime(2024, 1, 3)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(alice_id,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(bob_id,))],
        (_SELECT_PLAYER_STATE_QUERY, (alice_id,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
        (_SELECT_PLAYER_STATE_QUERY, (bob_id,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: alice_death.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(alice_death, event_context)

    alice_history_after_death = [
        params
        for query, params in connection.executed
        if query == _UPDATE_PLAYER_HISTORY_QUERY and params[-3:] == (alice_id, death_day, "csgo")
    ]
    assert alice_history_after_death == []

    storage.record(alice_next_flush, event_context)
    storage.flush_pending()

    upsert_key = (
        _UPSERT_PLAYER_HISTORY_QUERY,
        (alice_id, flush_day, "csgo", 1000),
    )
    update_key = (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (0, 1, 1, 0, 1000, 0, 0, 0, 0, 1, 1, 0, 0, 0, alice_id, flush_day, "csgo"),
    )
    assert upsert_key in connection.executed
    assert update_key in connection.executed
    assert connection.executed.index(upsert_key) < connection.executed.index(update_key)


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


def test_command_like_chat_is_not_inserted(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "/rank"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_CHAT_QUERY for query, _params in connection.executed)


def test_hlx_command_like_chat_is_not_inserted(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "hlx_display 0"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_CHAT_QUERY for query, _params in connection.executed)


def test_ordinary_chat_still_inserts(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "hold this angle"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_INSERT_CHAT_QUERY, (update.timestamp, 7, "de_dust2", 101, 1, "hold this angle")) in connection.executed


def test_dead_ordinary_chat_still_inserts(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "gg" (dead)'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert (_INSERT_CHAT_QUERY, (update.timestamp, 7, "de_dust2", 101, 1, "gg")) in connection.executed


def test_short_buy_script_chat_is_not_inserted(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "ak47"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_CHAT_QUERY for query, _params in connection.executed)


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
    storage = EventStorage(StubAdapter(connection), clock=lambda: name_update.timestamp)

    storage.record(frag_update, event_context)
    assert all(query != _UPDATE_PLAYERNAME_TOTALS_QUERY for query, _params in connection.executed)

    storage.record(name_update, event_context)
    assert all(query != _UPDATE_PLAYERNAME_TOTALS_QUERY for query, _params in connection.executed)

    storage.finalize_import()

    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (1, 1, 0, 0, 1, 0, 0, 101, "NewAlice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (1, 1, 0, 0, 1, 0, 0, 101, "Alice"),
    ) not in connection.executed


def test_existing_live_player_keeps_constructor_alias_until_explicit_name_change(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), DisconnectEventHandler(), TriggerEventHandler()],
        fallback=GenericEventHandler(),
    )
    connected = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Player21<136><STEAM_1:0:1161623468><>" '
            'connected, address "109.106.244.53:27005"'
        ),
        event_context,
    )
    stats = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Dim$0n<136><STEAM_1:0:1161623468><TERRORIST>" '
            'triggered "weaponstats" (weapon "ak47") (shots "190") (hits "31") '
            '(kills "3") (headshots "1") (tks "0") (damage "400") (deaths "3")'
        ),
        event_context,
    )
    disconnected = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Dim$0n<136><STEAM_1:0:1161623468><TERRORIST>" disconnected'
        ),
        event_context,
    )

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:0:1161623468", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: connected.timestamp)

    storage.record(connected, event_context)
    storage.record(stats, event_context)
    storage.record(disconnected, event_context)

    alias_touches = [params for query, params in connection.executed if query == _UPSERT_PLAYER_NAME_QUERY]
    assert alias_touches == [(101, "Player21", connected.timestamp)]
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (0, 0, 0, 0, 0, 190, 31, 101, "Player21"),
    ) in connection.executed
    assert all(
        params[-1] != "Dim$0n"
        for query, params in connection.executed
        if query == _UPDATE_PLAYERNAME_TOTALS_QUERY
    )


def test_empty_constructor_name_suppresses_placeholder_alias_until_explicit_name_change(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), EntryEventHandler(), TeamEventHandler()],
        fallback=GenericEventHandler(),
    )
    connected = dispatcher.dispatch(
        parse_log_event(
            'L 01/03/2024 - 16:06:20: "<1216><STEAM_0:0:552632503><>" '
            'connected, address "178.185.29.98:27005"'
        ),
        event_context,
    )
    reconnected = dispatcher.dispatch(
        parse_log_event(
            'L 01/03/2024 - 16:06:25: "<1217><STEAM_0:0:552632503><>" '
            'connected, address "178.185.29.98:27005"'
        ),
        event_context,
    )
    entered = dispatcher.dispatch(
        parse_log_event('L 01/03/2024 - 16:06:29: "unnamed<1217><STEAM_0:0:552632503><>" entered the game'),
        event_context,
    )
    joined = dispatcher.dispatch(
        parse_log_event('L 01/03/2024 - 16:06:37: "unnamed<1217><STEAM_0:0:552632503><>" joined team "TERRORIST"'),
        event_context,
    )
    changed = dispatcher.dispatch(
        parse_log_event(
            'L 01/03/2024 - 16:13:13: "unnamed<1219><STEAM_0:0:552632503><TERRORIST>" '
            'changed name to "XYU"'
        ),
        event_context,
    )

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("0:552632503", "csgo")): [QueryResponse(fetchone=(203,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: connected.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(connected, event_context)
    storage.record(reconnected, event_context)
    storage.record(entered, event_context)
    storage.record(joined, event_context)
    storage.record(changed, event_context)

    alias_touches = [params for query, params in connection.executed if query == _UPSERT_PLAYER_NAME_QUERY]
    assert alias_touches == [(203, "XYU", changed.timestamp)]


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


def test_record_headshot_frag_preserves_attacker_and_victim_positions(
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
            1,
            2,
            3,
            4,
            5,
            6,
        ),
    ) in connection.executed


def test_record_suicide_prefers_victim_position_then_attacker_position(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([KillEventHandler()])
    events = (
        (
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" committed suicide '
            'with "worldspawn" (victim_position "4 5 6")',
            (4, 5, 6),
        ),
        (
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" committed suicide '
            'with "worldspawn" (attacker_position "1 2 3")',
            (1, 2, 3),
        ),
    )

    for payload, position in events:
        update = dispatcher.dispatch(parse_log_event(payload), event_context)
        responses: Dict[QueryKey, List[QueryResponse]] = {
            (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
            (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        }
        connection = FakeConnection(responses)
        storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

        storage.record(update, event_context)

        assert (
            _INSERT_SUICIDE_QUERY,
            (update.timestamp, 7, "de_dust2", 101, "worldspawn", *position),
        ) in connection.executed


@pytest.mark.parametrize("position", ["1 2", "8388608 0 0"])
def test_record_frag_rejects_malformed_and_out_of_mediumint_positions(
    dispatcher: EventDispatcher,
    event_context: EventContext,
    position: str,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" killed '
        f'"Bob<3><STEAM_1:3><TERRORIST>" with "ak47" (attacker_position "{position}")'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    with pytest.raises(StorageError, match="position"):
        storage.record(update, event_context)

    assert all(query != _INSERT_FRAG_QUERY for query, _params in connection.executed)


def test_record_frag_rejects_malformed_positions_before_new_player_resolution(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "New Alice<902><STEAM_1:902><CT>" killed '
        '"New Bob<903><STEAM_1:903><TERRORIST>" with "ak47" '
        '(attacker_position "1 2 3 4")'
    )
    update = dispatcher.dispatch(event, event_context)
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage.begin_stdin_batch(transaction_batch_size=0)

    with pytest.raises(StorageError, match="position"):
        storage.record(update, event_context)

    assert connection.executed == []
    assert storage._player_cache == {}
    assert storage._player_teams == {}
    assert storage._server_connected_players == {}
    storage.end_stdin_batch()


def test_record_frag_rejects_malformed_positions_before_online_player_resolution(
    dispatcher: EventDispatcher,
    event_context: EventContext,
) -> None:
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Online Alice<904><STEAM_1:904><CT>" killed '
        '"Online Bob<905><STEAM_1:905><TERRORIST>" with "ak47" '
        '(victim_position "8388608 0 0")'
    )
    update = dispatcher.dispatch(event, event_context)
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage.begin_online_event()

    with pytest.raises(StorageError, match="position"):
        storage.record(update, event_context)

    assert connection.executed == []
    assert storage._player_cache == {}
    assert storage._online_event_touched_players == set()
    storage.abort_online_event()


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


def test_connect_event_restores_legacy_live_roster(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    event = parse_log_event(
        'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
    )
    update = dispatcher.dispatch(event, event_context)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert storage._server_live_players[event_context.server_id] == {101}
    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (1, 1, event_context.server_id)) in connection.executed


def test_connect_userid_rollover_refreshes_live_roster_activity(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler()])
    first_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    second_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:35: "Alice<3><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)

    assert storage._server_live_players[event_context.server_id] == {101}
    assert storage._server_player_last_activity[event_context.server_id][101] == second_update.timestamp


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


def test_team_bonus_rewards_idle_player_before_legacy_timeout_cleanup(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:10:00: Team "CT" triggered "SFUI_Notice_CTs_Win"')
    update = dispatcher.dispatch(event, event_context)
    assert update is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(1,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_CTs_Win")): [QueryResponse(fetchone=(755, 0, 2))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(0,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
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
        (update.timestamp, 7, "de_dust2", 101, 755, 2),
    ) in connection.executed
    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 102, 755, 2),
    ) in connection.executed
    assert 101 not in storage._server_connected_players[7]
    assert 101 not in storage._server_active_players[7]
    assert 101 not in storage._server_reward_eligible_players[7]
    assert 101 not in storage._server_player_last_activity[7]


def test_generic_attack_does_not_reactivate_idle_player_before_team_bonus(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [TeamEventHandler(), TeamTriggerEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    joined_ct = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 21:30:52: "Dance Bear<65><STEAM_1:0:1866613407><>" joined team "CT"'),
        event_context,
    )
    damage_only = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2026 - 21:40:00: "Dance Bear<65><STEAM_1:0:1866613407><CT>" attacked '
            '"DedMoroz<112><STEAM_0:0:94888080><TERRORIST>" with "m4a1" (damage "21")'
        ),
        event_context,
    )
    team_win = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 21:40:31: Team "CT" triggered "CTs_Win" (CT "4") (T "3")'),
        event_context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 21:40:31: World triggered "Round_End"'),
        event_context,
    )
    next_team_win = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 21:41:57: Team "CT" triggered "CTs_Win" (CT "4") (T "2")'),
        event_context,
    )
    assert joined_ct is not None
    assert damage_only is not None
    assert team_win is not None
    assert round_end is not None
    assert next_team_win is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:0:1866613407", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "CTs_Win")): [
            QueryResponse(fetchone=(755, 0, 2)),
            QueryResponse(fetchone=(755, 0, 2)),
        ],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: joined_ct.timestamp)

    storage.record(joined_ct, event_context)
    storage._server_connected_players[7].discard(101)
    storage.record(damage_only, event_context)
    storage.record(team_win, event_context)
    storage.record(round_end, event_context)
    storage.record(next_team_win, event_context)

    team_bonus_rows = [params for query, params in connection.executed if query == _INSERT_TEAM_BONUS_QUERY]
    assert (team_win.timestamp, 7, "de_dust2", 101, 755, 2) not in team_bonus_rows
    assert (next_team_win.timestamp, 7, "de_dust2", 101, 755, 2) not in team_bonus_rows


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
    storage._server_live_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102}
    storage._server_active_players[7] = {101, 102}

    storage.record(update, event_context)

    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (2, 1, 7)) in connection.executed


def test_server_act_players_uses_legacy_live_roster_not_trackable_presence(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Bob<3><STEAM_1:3><TERRORIST>" joined team "SPECTATOR"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_players[7] = {101, 102}
    storage._server_live_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102}
    storage._server_active_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "TERRORIST"})

    storage.record(update, event_context)

    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (2, 2, 7)) in connection.executed


def test_chat_descriptor_does_not_inflate_legacy_live_roster(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ChatEventHandler()])
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Bob<3><STEAM_1:3><TERRORIST>" say "ready"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_players[7] = {101}
    storage._server_live_players[7] = {101}

    storage.record(update, event_context)

    assert storage._server_players[7] == {101, 102}
    assert storage._server_live_players[7] == {101}


def test_dropped_bomb_action_does_not_inflate_legacy_live_roster(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler()])
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Bob<3><STEAM_1:3><TERRORIST>" triggered "Dropped_The_Bomb"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_SELECT_ACTION_QUERY, ("csgo", "Dropped_The_Bomb")): [QueryResponse(fetchone=(755, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_players[7] = {101}
    storage._server_live_players[7] = {101}

    storage.record(update, event_context)

    assert storage._server_players[7] == {101, 102}
    assert storage._server_live_players[7] == {101}


def test_team_selection_cache_hit_restores_legacy_live_roster(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Bob<3><STEAM_1:3><>" joined team "CT"'),
        event_context,
    )
    assert update.actor is not None
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_players[7] = {102}
    storage._player_cache[storage._cache_key_for_player(event_context.game, update.actor)] = 102

    storage.record(update, event_context)

    assert storage._server_live_players[7] == {102}


def test_disconnect_ends_kill_streak_before_round_drain(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [KillEventHandler(), DisconnectEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
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
    disconnect = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "Alice<2><STEAM_1:2><CT>" disconnected'),
        event_context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:08: World triggered "Round_End"'),
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
    storage.record(disconnect, event_context)
    storage.record(round_end, event_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (disconnect.timestamp, 7, "de_dust2", 101, 702, 0)) in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (round_end.timestamp, 7, "de_dust2", 101, 702, 0)) not in connection.executed


def test_bonus_round_end_records_derived_kill_streak_row_and_count_while_clearing_pending_kills(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher(
        [KillEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    first_kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 00:18:08: "Rakza<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
        ),
        event_context,
    )
    second_kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 00:18:09: "Rakza<2><STEAM_1:2><CT>" killed '
            '"Charlie<4><STEAM_1:4><TERRORIST>" with "ak47"'
        ),
        event_context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: World triggered "Round_End"'),
        event_context,
    )
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
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
    storage.record(round_end, context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (round_end.timestamp, 7, "de_dust2", 101, 702, 0)) in connection.executed
    assert (_INCREMENT_ACTION_COUNT_QUERY, (702,)) in connection.executed
    assert storage._player_kills_per_life.get(101) == 0


def test_bomb_defuse_round_end_clears_pending_kills_when_defuse_actions_are_gated_without_derived_streak(
    event_context: EventContext,
) -> None:
    schema = GameSchema(
        game=event_context.game,
        weapons=event_context.schema.weapons,
        actions={
            **event_context.schema.actions,
            "Bomb_Defused": ActionDefinition(
                code="Bomb_Defused",
                description="Bomb defused team notice",
                points=0,
                team_award=True,
            ),
            "defused_bomb": ActionDefinition(
                code="defused_bomb",
                description="Bomb defused",
                aliases=("Defused_The_Bomb",),
            ),
        },
    )
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=schema,
        localization=event_context.localization,
        extras={"map": "de_dust2"},
    )
    dispatcher = EventDispatcher(
        [KillEventHandler(), TriggerEventHandler(), TeamTriggerEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    first_kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 00:17:36: "Rakza<2><STEAM_1:2><CT>" killed '
            '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
        ),
        context,
    )
    second_kill = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 00:17:55: "Rakza<2><STEAM_1:2><CT>" killed '
            '"Charlie<4><STEAM_1:4><TERRORIST>" with "knife"'
        ),
        context,
    )
    defused = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: "Rakza<2><STEAM_1:2><CT>" triggered "Defused_The_Bomb"'),
        context,
    )
    bomb_defused = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: Team "CT" triggered "Bomb_Defused" (CT "6") (T "17")'),
        context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: World triggered "Round_End"'),
        context,
    )
    round_end_context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:4", "csgo")): [QueryResponse(fetchone=(103,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "defused_bomb")): [QueryResponse(fetchone=(266, 0, 0))],
        (_SELECT_ACTION_QUERY, ("csgo", "Bomb_Defused")): [QueryResponse(fetchone=(267, 0, 0))],
        (_SELECT_ACTION_QUERY, ("csgo", "kill_streak_2")): [QueryResponse(fetchone=(702, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_kill.timestamp)

    storage.record(first_kill, context)
    storage.record(second_kill, context)
    storage._server_min_players[7] = 10
    storage.record(defused, context)
    storage.record(bomb_defused, context)
    storage.record(round_end, round_end_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (defused.timestamp, 7, "de_dust2", 101, 266, 0)) not in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (round_end.timestamp, 7, "de_dust2", 101, 702, 0)) not in connection.executed
    assert (_INCREMENT_ACTION_COUNT_QUERY, (702,)) not in connection.executed
    assert storage._player_kills_per_life.get(101) == 0


def test_bomb_defuse_round_end_suppresses_only_defuser_derived_kill_streak_when_other_players_are_pending(
    event_context: EventContext,
) -> None:
    schema = GameSchema(
        game=event_context.game,
        weapons=event_context.schema.weapons,
        actions={
            **event_context.schema.actions,
            "Bomb_Defused": ActionDefinition(
                code="Bomb_Defused",
                description="Bomb defused team notice",
                points=0,
                team_award=True,
            ),
            "defused_bomb": ActionDefinition(
                code="defused_bomb",
                description="Bomb defused",
                aliases=("Defused_The_Bomb",),
            ),
        },
    )
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=schema,
        localization=event_context.localization,
        extras={"map": "de_dust2"},
    )
    dispatcher = EventDispatcher(
        [KillEventHandler(), TriggerEventHandler(), TeamTriggerEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    events = [
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:17:36: "Rakza<2><STEAM_1:2><CT>" killed '
                '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
            ),
            context,
        ),
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:17:55: "Rakza<2><STEAM_1:2><CT>" killed '
                '"Charlie<4><STEAM_1:4><TERRORIST>" with "knife"'
            ),
            context,
        ),
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:17:58: "Wonsm4n<5><STEAM_1:5><CT>" killed '
                '"Delta<6><STEAM_1:6><TERRORIST>" with "ak47"'
            ),
            context,
        ),
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:18:00: "Wonsm4n<5><STEAM_1:5><CT>" killed '
                '"Echo<7><STEAM_1:7><TERRORIST>" with "ak47"'
            ),
            context,
        ),
    ]
    defused = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: "Rakza<2><STEAM_1:2><CT>" triggered "Defused_The_Bomb"'),
        context,
    )
    bomb_defused = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: Team "CT" triggered "Bomb_Defused" (CT "6") (T "17")'),
        context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: World triggered "Round_End"'),
        context,
    )
    round_end_context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:4", "csgo")): [QueryResponse(fetchone=(103,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:5", "csgo")): [QueryResponse(fetchone=(105,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:6", "csgo")): [QueryResponse(fetchone=(106,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:7", "csgo")): [QueryResponse(fetchone=(107,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "defused_bomb")): [QueryResponse(fetchone=(266, 0, 0))],
        (_SELECT_ACTION_QUERY, ("csgo", "Bomb_Defused")): [QueryResponse(fetchone=(267, 0, 0))],
        (_SELECT_ACTION_QUERY, ("csgo", "kill_streak_2")): [QueryResponse(fetchone=(702, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: events[0].timestamp)

    for event in events:
        storage.record(event, context)
    storage._server_min_players[7] = 10
    storage.record(defused, context)
    storage.record(bomb_defused, context)
    storage.record(round_end, round_end_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (round_end.timestamp, 7, "de_dust2", 101, 702, 0)) not in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (round_end.timestamp, 7, "de_dust2", 105, 702, 0)) in connection.executed
    assert connection.executed.count((_INCREMENT_ACTION_COUNT_QUERY, (702,))) == 1
    assert storage._player_kills_per_life.get(101) == 0
    assert storage._player_kills_per_life.get(105) == 0


def test_bomb_defuse_round_end_records_defuser_kill_streak_when_defuse_action_is_not_gated(
    event_context: EventContext,
) -> None:
    schema = GameSchema(
        game=event_context.game,
        weapons=event_context.schema.weapons,
        actions={
            **event_context.schema.actions,
            "Bomb_Defused": ActionDefinition(
                code="Bomb_Defused",
                description="Bomb defused team notice",
                points=0,
                team_award=True,
            ),
            "defused_bomb": ActionDefinition(
                code="defused_bomb",
                description="Bomb defused",
                aliases=("Defused_The_Bomb",),
            ),
        },
    )
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=schema,
        localization=event_context.localization,
        extras={"map": "de_dust2"},
    )
    round_end_context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 1},
    )
    dispatcher = EventDispatcher(
        [KillEventHandler(), TriggerEventHandler(), TeamTriggerEventHandler(), WorldEventHandler()],
        fallback=GenericEventHandler(),
    )
    kill_events = [
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:17:36: "Rakza<2><STEAM_1:2><CT>" killed '
                '"Bob<3><STEAM_1:3><TERRORIST>" with "ak47"'
            ),
            context,
        ),
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:17:55: "Rakza<2><STEAM_1:2><CT>" killed '
                '"Charlie<4><STEAM_1:4><TERRORIST>" with "knife"'
            ),
            context,
        ),
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:17:58: "Rakza<2><STEAM_1:2><CT>" killed '
                '"Delta<5><STEAM_1:5><TERRORIST>" with "m4a1"'
            ),
            context,
        ),
        dispatcher.dispatch(
            parse_log_event(
                'L 01/02/2024 - 00:18:00: "Rakza<2><STEAM_1:2><CT>" killed '
                '"Echo<6><STEAM_1:6><TERRORIST>" with "deagle"'
            ),
            context,
        ),
    ]
    defused = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: "Rakza<2><STEAM_1:2><CT>" triggered "Defused_The_Bomb"'),
        context,
    )
    bomb_defused = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: Team "CT" triggered "Bomb_Defused" (CT "6") (T "17")'),
        context,
    )
    round_end = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:18:10: World triggered "Round_End"'),
        context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:3", "csgo")): [QueryResponse(fetchone=(102,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:4", "csgo")): [QueryResponse(fetchone=(103,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:5", "csgo")): [QueryResponse(fetchone=(104,))],
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:6", "csgo")): [QueryResponse(fetchone=(105,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "defused_bomb")): [QueryResponse(fetchone=(266, 0, 0))],
        (_SELECT_ACTION_QUERY, ("csgo", "Bomb_Defused")): [QueryResponse(fetchone=(267, 0, 0))],
        (_SELECT_ACTION_QUERY, ("csgo", "kill_streak_4")): [QueryResponse(fetchone=(704, 0, 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: kill_events[0].timestamp)

    for event in kill_events:
        storage.record(event, context)
    storage.record(defused, context)
    assert storage._suppress_next_round_end_kill_streak.get(7, set()) == set()
    storage.record(bomb_defused, context)
    storage.record(round_end, round_end_context)

    assert (_INSERT_PLAYER_ACTION_QUERY, (defused.timestamp, 7, "de_dust2", 101, 266, 0)) in connection.executed
    assert (_INSERT_PLAYER_ACTION_QUERY, (round_end.timestamp, 7, "de_dust2", 101, 704, 0)) in connection.executed
    assert (_INCREMENT_ACTION_COUNT_QUERY, (704,)) in connection.executed
    assert storage._player_kills_per_life.get(101) == 0


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


def test_realign_history_delete_invalidates_ensured_source_day_cache(event_context: EventContext) -> None:
    source_timestamp = datetime(2024, 1, 5, 9, 0, 0)
    source_day = datetime(2024, 1, 5)
    target_timestamp = datetime(2024, 1, 2, 3, 4, 5)
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (
            _SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY,
            (101, source_day, "csgo"),
        ): [QueryResponse(fetchone=(0, 3, 5, 0, 1013, 2, 85, 21, 0, 3, 2, 13))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)

    storage._ensure_player_history_row(connection, event_context, 101, source_timestamp)
    storage._realign_player_history_day(
        connection,
        context=event_context,
        player_id=101,
        event_timestamp=target_timestamp,
        processed_at=source_timestamp,
    )
    storage._ensure_player_history_row(connection, event_context, 101, source_timestamp)

    source_day_upserts = [
        entry
        for entry in connection.executed
        if entry == (_UPSERT_PLAYER_HISTORY_QUERY, (101, source_day, "csgo", 1000))
    ]
    assert len(source_day_upserts) == 2


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


def test_disconnect_flushes_player_connection_time_rollups(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            DisconnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    disconnect_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:12: "Alice<2><STEAM_1:2><CT>" disconnected'),
        event_context,
    )
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: connect_update.timestamp)

    storage.record(connect_update, event_context)
    storage.record(disconnect_update, event_context)

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (7, 101)) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (7, 0, 0, 0, 0, 0, 0, 101, "Alice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (7, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_ignore_bots_flushes_connection_time_without_history_delta(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler(), DisconnectEventHandler()])
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "BotOne<664><BOT><CT>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    disconnect_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:12: "BotOne<664><BOT><CT>" disconnected'),
        event_context,
    )
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    # Deliberately separate source event day from processing day: replay may
    # attempt to seed both daily keys at this boundary.
    storage = EventStorage(StubAdapter(connection), clock=lambda: datetime(2024, 1, 3, 3, 4, 5))

    storage.record(connect_update, event_context)
    storage.record(disconnect_update, event_context)

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (7, 201)) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (7, 0, 0, 0, 0, 0, 0, 201, "BotOne"),
    ) in connection.executed
    history_upserts = [params for query, params in connection.executed if query == _UPSERT_PLAYER_HISTORY_QUERY]
    assert history_upserts
    assert all(params[1] == datetime(2024, 1, 2) for params in history_upserts)
    assert all(params[1] != datetime(2024, 1, 3) for params in history_upserts)
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (7, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 201, history_timestamp, "csgo"),
    ) not in connection.executed


def test_finalize_import_flushes_open_player_connection_time(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler(), ChatEventHandler()])
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    chat_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:17: "Alice<2><STEAM_1:2><CT>" say "ready"'),
        event_context,
    )
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: chat_update.timestamp)

    storage.record(connect_update, event_context)
    storage.record(chat_update, event_context)

    assert all(query != _UPDATE_PLAYER_CONNECTION_TIME_QUERY for query, _params in connection.executed)

    storage.finalize_import()

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (12, 101)) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (12, 0, 0, 0, 0, 0, 0, 101, "Alice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (12, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_finalize_import_uses_last_event_time_for_stdin_connection_time(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler(), ChatEventHandler()])
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    chat_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:17: "Alice<2><STEAM_1:2><CT>" say "ready"'),
        event_context,
    )
    wall_clock_after_replay = datetime(2026, 5, 16, 12, 0, 0)
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: wall_clock_after_replay,
        use_event_timestamps_for_processing=True,
    )

    storage.record(connect_update, event_context)
    storage.record(chat_update, event_context)
    storage.finalize_import()

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (12, 101)) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (12, 0, 0, 0, 0, 0, 0, 101, "Alice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (12, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_finalize_import_flushes_rollover_session_without_live_activity_entry(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([ChatEventHandler()])
    first_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><CT>" say "ready"'),
        event_context,
    )
    rollover_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:35: "Alice<3><STEAM_1:2><>" say "back"'),
        event_context,
    )
    import_end = datetime(2024, 1, 2, 3, 4, 50)
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: import_end)

    storage.record(first_update, event_context)
    storage.record(rollover_update, event_context)

    assert 101 not in storage._server_player_last_activity[event_context.server_id]

    storage.finalize_import()

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (30, 101)) in connection.executed
    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (15, 101)) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (15, 0, 0, 0, 0, 0, 0, 101, "Alice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (15, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_flush_pending_clamps_connection_time_gap_above_600_seconds(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler(), ChatEventHandler()])
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    stale_chat_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:15:45: "Alice<2><STEAM_1:2><CT>" say "still here"'),
        event_context,
    )
    fresh_chat_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:15:50: "Alice<2><STEAM_1:2><CT>" say "ready again"'),
        event_context,
    )
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [
            QueryResponse(fetchone=(101,)),
            QueryResponse(fetchone=(101,)),
            QueryResponse(fetchone=(101,)),
        ],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: fresh_chat_update.timestamp)

    storage.record(connect_update, event_context)
    storage.record(stale_chat_update, event_context)

    storage.flush_pending()

    assert all(
        entry not in connection.executed
        for entry in [
            (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (700, 101)),
            (_UPDATE_PLAYERNAME_TOTALS_QUERY, (700, 0, 0, 0, 0, 0, 0, 101, "Alice")),
            (
                _UPDATE_PLAYER_HISTORY_QUERY,
                (700, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
            ),
        ]
    )
    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (0, 101)) in connection.executed
    assert (_UPDATE_PLAYER_STREAKS_QUERY, (0, 0, 0, 0, 101)) in connection.executed

    storage.record(fresh_chat_update, event_context)
    storage.finalize_import()

    assert all(
        entry not in connection.executed
        for entry in [
            (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (5, 101)),
            (_UPDATE_PLAYERNAME_TOTALS_QUERY, (5, 0, 0, 0, 0, 0, 0, 101, "Alice")),
            (
                _UPDATE_PLAYER_HISTORY_QUERY,
                (5, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
            ),
        ]
    )


def test_flush_pending_uses_last_event_time_for_stdin_connection_time(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([ConnectEventHandler(), ChatEventHandler()])
    connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    chat_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:17: "Alice<2><STEAM_1:2><CT>" say "ready"'),
        event_context,
    )
    wall_clock_after_replay = datetime(2026, 5, 16, 12, 0, 0)
    history_timestamp = datetime(2024, 1, 2)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: wall_clock_after_replay,
        use_event_timestamps_for_processing=True,
    )

    storage.record(connect_update, event_context)
    storage.record(chat_update, event_context)
    storage.flush_pending()

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (12, 101)) in connection.executed
    assert (
        _UPDATE_PLAYERNAME_TOTALS_QUERY,
        (12, 0, 0, 0, 0, 0, 0, 101, "Alice"),
    ) in connection.executed
    assert (
        _UPDATE_PLAYER_HISTORY_QUERY,
        (12, 0, 0, 0, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 101, history_timestamp, "csgo"),
    ) in connection.executed


def test_reconnect_does_not_count_offline_gap_into_connection_time(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [
            ConnectEventHandler(),
            DisconnectEventHandler(),
            generic,
        ],
        fallback=generic,
    )
    first_connect = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:00:00: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    first_disconnect = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:00:10: "Alice<2><STEAM_1:2><CT>" disconnected'),
        event_context,
    )
    second_connect = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:00:20: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    second_disconnect = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:00:25: "Alice<2><STEAM_1:2><CT>" disconnected'),
        event_context,
    )

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,)), QueryResponse(fetchone=(101,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_connect.timestamp)

    storage.record(first_connect, event_context)
    storage.record(first_disconnect, event_context)
    storage.record(second_connect, event_context)
    storage.record(second_disconnect, event_context)

    player_connection_updates = [
        params for query, params in connection.executed if query == _UPDATE_PLAYER_CONNECTION_TIME_QUERY
    ]
    assert player_connection_updates == [(10, 101), (5, 101)]
    assert (15, 101) not in player_connection_updates
    assert (20, 101) not in player_connection_updates


def test_replay_runner_handles_connection_time_player_update(event_context: EventContext) -> None:
    generic = GenericEventHandler()
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), DisconnectEventHandler(), generic],
        fallback=generic,
    )
    runner = ReplayRunner(dispatcher, event_context)

    result = runner.run(
        [
            'PROXY Key=proxy 127.0.0.1:27015 PROXY '
            'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" connected, address "1.2.3.4:27005"',
            'PROXY Key=proxy 127.0.0.1:27015 PROXY '
            'L 01/02/2024 - 03:04:12: "Alice<2><STEAM_1:2><CT>" disconnected',
        ]
    )

    assert (_UPDATE_PLAYER_CONNECTION_TIME_QUERY, (7, 1)) in result.executed_queries
    assert result.snapshot.players[1].disconnects == 1


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


def test_unique_id_reconnect_clears_old_live_roster_state(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    first_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Player<2><STEAM_1:2><TERRORIST>" say "ready"'),
        event_context,
    )
    second_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:35: "Player<3><STEAM_1:2><>" say "back"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, event_context)
    storage._server_live_players[7] = {101}
    storage._server_active_players[7].add(101)
    storage._server_connected_players[7].add(101)
    storage._server_reward_eligible_players[7] = {101}
    storage._server_player_last_activity[7][101] = first_update.timestamp
    storage._player_teams[101] = "TERRORIST"

    storage.record(second_update, event_context)

    assert 101 not in storage._server_live_players[7]
    assert 101 not in storage._server_active_players[7]
    assert 101 not in storage._server_connected_players[7]
    assert 101 not in storage._server_reward_eligible_players[7]
    assert 101 not in storage._server_player_last_activity[7]
    assert 101 not in storage._player_teams
    assert 101 not in storage._closed_player_objects


def test_same_unique_reconnect_before_team_win_does_not_reward_stale_team(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([ChatEventHandler(), TeamTriggerEventHandler()], fallback=GenericEventHandler())
    first_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 19:02:17: "Player<2><STEAM_1:2><TERRORIST>" say "ready"'),
        event_context,
    )
    reconnect_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 19:02:18: "Player<3><STEAM_1:2><>" say "back"'),
        event_context,
    )
    team_win = dispatcher.dispatch(
        parse_log_event('L 01/02/2026 - 19:02:18: Team "TERRORIST" triggered "SFUI_Notice_Terrorists_Win"'),
        event_context,
    )
    context = EventContext(
        server_id=event_context.server_id,
        game=event_context.game,
        schema=event_context.schema,
        localization=event_context.localization,
        extras={"map": "de_dust2", "round_status": 0},
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "SFUI_Notice_Terrorists_Win")): [QueryResponse(fetchone=(756, 0, 2))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: first_update.timestamp)

    storage.record(first_update, context)
    storage._server_active_players[7].add(101)
    storage._server_connected_players[7].add(101)
    storage._server_reward_eligible_players[7] = {101}
    storage._player_teams[101] = "TERRORIST"
    storage.record(reconnect_update, context)
    storage.record(team_win, context)

    assert all(query != _INSERT_TEAM_BONUS_QUERY for query, _params in connection.executed)


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
    expected_map_started = int(timegm(first_update.timestamp.timetuple()))
    assert (_UPDATE_SERVER_MAP_STARTED_QUERY, ("de_nuke", expected_map_started, 7)) in transition_entries
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
        (update.timestamp, 7, "de_dust2", 101, 102, "ak47", 1, 2, 3, 4, 5, 6),
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


def test_ignore_bots_keeps_initial_resolution_history_seed(event_context: EventContext) -> None:
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
    history_upserts = [params for query, params in connection.executed if query == _UPSERT_PLAYER_HISTORY_QUERY]
    assert history_upserts
    assert all(params[1] == datetime(2024, 1, 2) for params in history_upserts)
    assert all(params[1] != datetime(2024, 1, 3) for params in history_upserts)


def test_ignore_bots_does_not_seed_later_event_day_for_same_identity(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    first_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 23:59:59: "BotOne<664><BOT><CT>" say "first"'),
        event_context,
    )
    second_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:00:01: "BotOne<664><BOT><CT>" say "second"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)

    history_upserts = [params for query, params in connection.executed if query == _UPSERT_PLAYER_HISTORY_QUERY]
    assert history_upserts == [(201, datetime(2024, 1, 1), "csgo", 1000)]


def test_ignore_bots_reseeds_after_source_log_boundary_for_same_userid(
    event_context: EventContext,
) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    first_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 23:59:59: "BotOne<664><BOT><CT>" say "first"'),
        event_context,
    )
    continuous_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:00:01: "BotOne<664><BOT><CT>" say "continuous"'),
        event_context,
    )
    next_log_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:05:48: "BotOne<664><BOT><CT>" say "next log"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.record(continuous_update, event_context)
    storage.mark_source_log_boundary(event_context.server_id)
    storage.record(next_log_update, event_context)

    history_upserts = [params for query, params in connection.executed if query == _UPSERT_PLAYER_HISTORY_QUERY]
    assert history_upserts == [
        (201, datetime(2024, 1, 1), "csgo", 1000),
        (201, datetime(2024, 1, 2), "csgo", 1000),
    ]


def test_ignore_bots_disabled_seeds_each_event_day_for_same_bot_identity(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    first_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 23:59:59: "BotOne<664><BOT><CT>" say "first"'),
        event_context,
    )
    second_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 00:00:01: "BotOne<664><BOT><CT>" say "second"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(201,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(0,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(
        StubAdapter(connection),
        clock=lambda: first_update.timestamp,
        use_event_timestamps_for_processing=True,
    )

    storage.record(first_update, event_context)
    storage.record(second_update, event_context)

    history_upserts = [params for query, params in connection.executed if query == _UPSERT_PLAYER_HISTORY_QUERY]
    assert history_upserts == [
        (201, datetime(2024, 1, 1), "csgo", 1000),
        (201, datetime(2024, 1, 2), "csgo", 1000),
    ]


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


def test_online_events_commit_independently_without_cross_event_buffering() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.configure_event_buffer(max_buffered_events=5000)

    for message in ("first", "second"):
        storage.begin_online_event()
        storage._execute(
            connection,
            _INSERT_CHAT_QUERY,
            (datetime(2024, 1, 2, 3, 4, 5), 7, "de_dust2", 101, 1, message),
        )
        assert (_INSERT_CHAT_QUERY, (datetime(2024, 1, 2, 3, 4, 5), 7, "de_dust2", 101, 1, message)) in connection.executed
        storage.commit_online_event()

    assert connection.commit_calls == 2
    assert connection.autocommit_calls == [False, True, False, True]
    assert storage._event_buffer is None


def test_online_commit_failure_rolls_back_and_restores_autocommit() -> None:
    class FailingCommitConnection(FakeConnection):
        def commit(self) -> None:
            super().commit()
            raise RuntimeError("synthetic commit failure")

    connection = FailingCommitConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_online_event()
    storage._execute(
        connection,
        _INSERT_CHAT_QUERY,
        (datetime(2024, 1, 2, 3, 4, 5), 7, "de_dust2", 101, 1, "failed"),
    )

    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        storage.commit_online_event()

    assert connection.commit_calls == 1
    assert connection.rollback_calls == 1
    assert connection.autocommit_calls == [False, True]
    assert storage._online_event_active is False


def test_online_event_abort_rolls_back_and_restores_autocommit() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_online_event()
    storage._execute(
        connection,
        _INSERT_CHAT_QUERY,
        (datetime(2024, 1, 2, 3, 4, 5), 7, "de_dust2", 101, 1, "failed"),
    )

    storage.abort_online_event()

    assert connection.rollback_calls == 1
    assert connection.autocommit_calls == [False, True]
    assert storage._online_event_active is False


def test_online_event_commit_scopes_deferred_player_name_and_history_rollups(
    event_context: EventContext,
) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    storage._player_names[101] = "Alice"
    storage._player_connection_time_context[101] = (event_context.server_id, event_context.game)

    for kills in (1, 2):
        storage.begin_online_event()
        storage._update_player_rollups(
            connection,
            context=event_context,
            timestamp=timestamp,
            processed_at=timestamp,
            player_id=101,
            kills=kills,
        )
        assert 101 in storage._player_name_rollups
        assert 101 in storage._player_history_rollups
        storage.commit_online_event()
        assert storage._player_name_rollups == {}
        assert storage._player_history_rollups == {}

    history_kills = [
        params[1]
        for query, params in connection.executed
        if query == _UPDATE_PLAYER_HISTORY_QUERY and params is not None
    ]
    name_kills = [
        params[1]
        for query, params in connection.executed
        if query == _UPDATE_PLAYERNAME_TOTALS_QUERY and params is not None
    ]
    assert history_kills == [1, 2]
    assert name_kills == [1, 2]
    assert connection.commit_calls == 2


def test_online_event_commit_does_not_update_unrelated_cached_player_profile(
    event_context: EventContext,
) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    storage._player_names[101] = "Alice"
    storage._player_names[202] = "Unrelated"
    storage._player_connection_time_context[101] = (event_context.server_id, event_context.game)
    storage._player_connection_time_context[202] = (event_context.server_id, event_context.game)
    storage._player_connection_time_flush_at[101] = timestamp
    storage._player_connection_time_flush_at[202] = timestamp

    storage.begin_online_event()
    # The real resolver marks only identities encountered by this logical
    # packet.  Keep a second cached player present to catch an accidental
    # all-player profile/connection scan during commit.
    storage._online_event_touched_players.add(101)
    storage._update_player_rollups(
        connection,
        context=event_context,
        timestamp=timestamp,
        processed_at=timestamp,
        player_id=101,
        kills=1,
    )
    storage.commit_online_event()

    assert (_UPDATE_PLAYER_NAME_QUERY, ("Unrelated", 202)) not in connection.executed
    assert all(
        not (query == _UPDATE_PLAYER_CONNECTION_TIME_QUERY and params is not None and params[-1] == 202)
        for query, params in connection.executed
    )


def test_zero_sized_stdin_batch_does_not_open_online_event_transactions() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=0)
    storage.begin_online_event()
    storage._execute(
        connection,
        _INSERT_CHAT_QUERY,
        (datetime(2024, 1, 2, 3, 4, 5), 7, "de_dust2", 101, 1, "stdin"),
    )
    storage.commit_online_event()
    storage.end_stdin_batch()

    assert connection.autocommit_calls == []
    assert connection.commit_calls == 0


def test_zero_sized_stdin_batch_keeps_deferred_rollups_for_import_finalization(
    event_context: EventContext,
) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    storage.begin_stdin_batch(transaction_batch_size=0)
    storage._player_names[101] = "Alice"
    storage._player_connection_time_context[101] = (event_context.server_id, event_context.game)
    storage._update_player_rollups(
        connection,
        context=event_context,
        timestamp=timestamp,
        processed_at=timestamp,
        player_id=101,
        kills=1,
    )

    storage.begin_online_event()
    storage.commit_online_event()

    assert 101 in storage._player_name_rollups
    assert 101 in storage._player_history_rollups
    storage.finalize_import()
    assert storage._player_name_rollups == {}
    assert storage._player_history_rollups == {}


def test_player_history_row_ensure_is_cached_per_player_day_and_game(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    storage.begin_stdin_batch(transaction_batch_size=100)

    storage._ensure_player_history_row(connection, event_context, 101, timestamp)
    storage._ensure_player_history_row(connection, event_context, 101, timestamp)
    other_game = EventContext(
        server_id=event_context.server_id,
        game="cstrike",
        schema=event_context.schema,
        localization=event_context.localization,
        extras=event_context.extras,
    )
    storage._ensure_player_history_row(connection, other_game, 101, timestamp)
    storage._ensure_player_history_row(connection, event_context, 101, timestamp + timedelta(days=1))

    history_upserts = [entry for entry in connection.executed if entry[0] == _UPSERT_PLAYER_HISTORY_QUERY]
    assert history_upserts == [
        (_UPSERT_PLAYER_HISTORY_QUERY, (101, datetime(2024, 1, 2), "csgo", 1000)),
        (_UPSERT_PLAYER_HISTORY_QUERY, (101, datetime(2024, 1, 2), "cstrike", 1000)),
        (_UPSERT_PLAYER_HISTORY_QUERY, (101, datetime(2024, 1, 3), "csgo", 1000)),
    ]


def test_db_write_trace_keeps_statsme_counter_templates_when_buffered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    trace_path = tmp_path / "writes.jsonl"
    monkeypatch.setenv("HLSTATS_DB_WRITE_TRACE_PATH", str(trace_path))
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))

    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (2, 1, 101))
    storage._execute(connection, _UPDATE_SERVER_CT_SHOTS_HITS_QUERY, (5, 2, 50, 20, 7))
    storage._execute(connection, _UPDATE_SERVER_TS_SHOTS_HITS_QUERY, (6, 3, 4, 1, 7))
    storage.end_stdin_batch()

    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {"sql": _UPDATE_PLAYER_SHOTS_HITS_QUERY, "params": [2, 1, 101]},
        {"sql": _UPDATE_SERVER_CT_SHOTS_HITS_QUERY, "params": [5, 2, 50, 20, 7]},
        {"sql": _UPDATE_SERVER_TS_SHOTS_HITS_QUERY, "params": [6, 3, 4, 1, 7]},
    ]


def test_player_history_row_ensure_cache_is_invalidated_by_batch_rollback(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    storage.begin_stdin_batch(transaction_batch_size=100)

    storage._ensure_player_history_row(connection, event_context, 101, timestamp)
    storage._rollback_pending()
    storage._ensure_player_history_row(connection, event_context, 101, timestamp)

    history_upserts = [entry for entry in connection.executed if entry[0] == _UPSERT_PLAYER_HISTORY_QUERY]
    assert len(history_upserts) == 2
    assert connection.rollback_calls == 1


def test_player_history_row_ensure_does_not_cache_failed_execute(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    original_execute = storage._execute

    def fail_execute(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated write failure")

    storage._execute = fail_execute  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated write failure"):
        storage._ensure_player_history_row(connection, event_context, 101, timestamp)
    storage._execute = original_execute  # type: ignore[method-assign]
    storage._ensure_player_history_row(connection, event_context, 101, timestamp)

    history_upserts = [entry for entry in connection.executed if entry[0] == _UPSERT_PLAYER_HISTORY_QUERY]
    assert len(history_upserts) == 1


def test_player_history_row_ensure_cache_is_cleared_on_normal_stdin_end(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._ensure_player_history_row(connection, event_context, 101, timestamp)
    storage.end_stdin_batch()
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._ensure_player_history_row(connection, event_context, 101, timestamp)

    history_upserts = [entry for entry in connection.executed if entry[0] == _UPSERT_PLAYER_HISTORY_QUERY]
    assert len(history_upserts) == 2


def test_player_history_row_ensure_remains_uncached_online(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    timestamp = datetime(2024, 1, 2, 3, 4, 5)

    storage._ensure_player_history_row(connection, event_context, 101, timestamp)
    storage._ensure_player_history_row(connection, event_context, 101, timestamp)

    history_upserts = [entry for entry in connection.executed if entry[0] == _UPSERT_PLAYER_HISTORY_QUERY]
    assert len(history_upserts) == 2


def test_statsme_counter_deltas_aggregate_flush_and_online_fallback(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (2, 1, 101))
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (3, 4, 101))
    storage._execute(connection, _UPDATE_SERVER_CT_SHOTS_HITS_QUERY, (5, 2, 50, 20, 7))
    storage._flush_statsme_counter_buffer()
    assert (_UPDATE_PLAYER_SHOTS_HITS_QUERY, (5, 5, 101)) in connection.executed
    assert (_UPDATE_SERVER_CT_SHOTS_HITS_QUERY, (5, 2, 50, 20, 7)) in connection.executed
    storage.end_stdin_batch()
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (1, 1, 101))
    assert (_UPDATE_PLAYER_SHOTS_HITS_QUERY, (1, 1, 101)) in connection.executed


def test_statsme_counter_deltas_clear_on_rollback_and_flush_before_map_reset(event_context: EventContext) -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._execute(connection, _UPDATE_SERVER_TS_SHOTS_HITS_QUERY, (2, 3, 2, 3, 7))
    storage.apply_server_map_transition(7, "started", "de_nuke", datetime(2024, 1, 1))
    queries = [query for query, _ in connection.executed]
    assert queries.index(_UPDATE_SERVER_TS_SHOTS_HITS_QUERY) < queries.index(_UPDATE_SERVER_MAP_STARTED_QUERY)
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (4, 5, 101))
    storage._rollback_pending()
    storage._flush_statsme_counter_buffer()
    assert (_UPDATE_PLAYER_SHOTS_HITS_QUERY, (4, 5, 101)) not in connection.executed


def test_statsme_counter_buffer_is_disabled_by_zero_sized_batch() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (2, 1, 101))
    storage.begin_stdin_batch(transaction_batch_size=0)
    storage.end_stdin_batch()

    assert not any(query == _UPDATE_PLAYER_SHOTS_HITS_QUERY for query, _ in connection.executed)


def test_maybe_commit_batch_flushes_statsme_counter_delta() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=1)
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (2, 1, 101))
    storage._pending_records = 1

    storage._maybe_commit_batch()

    assert (_UPDATE_PLAYER_SHOTS_HITS_QUERY, (2, 1, 101)) in connection.executed
    assert connection.commit_calls == 1


def test_partial_statsme_flush_is_cleared_by_abort() -> None:
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection))
    storage.begin_stdin_batch(transaction_batch_size=100)
    storage._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (2, 1, 101))
    storage._execute(connection, _UPDATE_SERVER_CT_SHOTS_HITS_QUERY, (5, 2, 5, 2, 7))
    original_execute_direct = storage._execute_direct
    calls = 0

    def partial_execute(connection_arg, query, params):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated statsme flush failure")
        return original_execute_direct(connection_arg, query, params)

    storage._execute_direct = partial_execute  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated statsme flush failure"):
        storage._flush_statsme_counter_buffer()
    storage.abort_stdin_batch()
    storage._execute_direct = original_execute_direct  # type: ignore[method-assign]
    storage._flush_statsme_counter_buffer()

    assert connection.rollback_calls == 1
    assert storage._statsme_counter_deltas is None
    assert calls == 2


def test_apply_server_map_transition_loading_query() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    ts = datetime(2024, 1, 1, 0, 0, 29)
    storage.apply_server_map_transition(7, "loading", "de_inferno", ts)
    assert connection.executed == [(_UPDATE_SERVER_MAP_LOADING_QUERY, ("de_inferno", 7))]


def test_loading_map_removes_bot_from_legacy_live_roster() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    seen_at = datetime(2024, 1, 1, 0, 0, 0)
    storage._server_players[7] = {101, 102}
    storage._server_live_players[7] = {101, 102}
    storage._server_active_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._server_player_last_activity[7] = {101: seen_at, 102: seen_at}
    storage._player_teams.update({101: "TERRORIST", 102: "CT"})
    storage._player_is_bot.update({101: True, 102: False})

    storage.apply_server_map_transition(7, "loading", "de_inferno", datetime(2024, 1, 1, 0, 0, 29))

    assert storage._server_live_players[7] == {102}
    assert storage._server_active_players[7] == {102}
    assert storage._server_connected_players[7] == {102}
    assert storage._server_reward_eligible_players[7] == {102}
    assert storage._server_player_last_activity[7] == {102: seen_at}
    assert storage._player_teams == {102: "CT"}
    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (2, 1, 7)) in connection.executed


def test_apply_server_map_transition_started_query() -> None:
    connection = FakeConnection({})
    wall_clock = datetime(2024, 1, 1, 0, 1, 3)
    storage = EventStorage(StubAdapter(connection), clock=lambda: wall_clock)
    storage._server_active_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102, 103}
    storage._server_reward_eligible_players[7] = {101, 103}
    storage._server_player_last_activity[7] = {
        101: datetime(2024, 1, 1, 0, 0, 28),
        103: datetime(2024, 1, 1, 0, 0, 30),
    }
    storage._player_teams.update({101: "CT", 102: "TERRORIST", 103: "CT"})
    event_ts = datetime(2024, 1, 1, 0, 0, 31)
    storage.apply_server_map_transition(7, "started", "de_nuke", event_ts)
    expected_unix = int(timegm(wall_clock.timetuple()))
    assert connection.executed == [
        (_UPDATE_SERVER_MAP_STARTED_QUERY, ("de_nuke", expected_unix, 7)),
    ]
    assert storage._server_active_players[7] == set()
    assert storage._server_connected_players[7] == set()
    assert storage._server_reward_eligible_players[7] == set()
    assert storage._server_player_last_activity[7] == {}
    assert storage._player_teams[101] == ""
    assert storage._player_teams[102] == ""
    assert storage._player_teams[103] == ""


def test_started_map_blank_team_baseline_allows_unassigned_status_change(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Rakza<23><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._player_cache[storage._cache_key_for_player(event_context.game, update.actor)] = 101
    storage._server_active_players[7] = {101}
    storage._server_connected_players[7] = {101}
    storage._player_teams[101] = "TERRORIST"

    storage.apply_server_map_transition(7, "started", "de_nuke", update.timestamp)
    storage.record(update, event_context)

    assert (_INSERT_TEAM_CHANGE_QUERY, (update.timestamp, 7, "de_dust2", 101, "UNASSIGNED")) in connection.executed
    assert storage._player_teams[101] == "UNASSIGNED"


def test_started_map_flushes_preclear_roster_count_to_server_act_players() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    storage._server_players[7] = {101, 102, 103, 104, 105}
    storage._server_live_players[7] = {101, 102, 103, 104}
    storage._server_active_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102, 103, 104}
    storage._server_reward_eligible_players[7] = {103}

    storage.apply_server_map_transition(7, "started", "de_nuke", datetime(2024, 1, 1, 0, 0, 31))

    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (5, 4, 7)) in connection.executed
    assert storage._server_live_players[7] == {101, 102, 103, 104}
    assert 7 not in storage._server_totals_dirty


def test_started_map_preserves_legacy_live_roster_for_next_map_count() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    storage._server_players[7] = {101, 102, 103, 104}
    storage._server_live_players[7] = {101, 102, 103, 104}
    storage._server_active_players[7] = {101, 102}
    storage._server_connected_players[7] = {101, 102, 103, 104}

    storage.apply_server_map_transition(7, "started", "de_nuke", datetime(2024, 1, 1, 0, 0, 31))
    storage._refresh_server_player_totals(connection, 7)

    assert (_UPDATE_SERVER_PLAYER_TOTALS_QUERY, (4, 4, 7)) in connection.executed


def test_started_map_preserves_live_roster_activity_for_idle_prune() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    seen_at = datetime(2024, 1, 1, 0, 0, 0)
    started_at = seen_at + timedelta(seconds=10)
    prune_at = seen_at + _ACTIVE_PLAYER_IDLE_TIMEOUT + timedelta(seconds=1)
    storage._server_players[7] = {101}
    storage._server_live_players[7] = {101}
    storage._server_active_players[7] = {101}
    storage._server_connected_players[7] = {101}
    storage._server_player_last_activity[7] = {101: seen_at}

    storage.apply_server_map_transition(7, "started", "de_nuke", started_at)
    storage._prune_idle_players(connection, 7, prune_at)

    assert storage._server_live_players[7] == set()
    assert storage._server_player_last_activity[7] == {}


def test_apply_server_map_transition_started_uses_wall_clock_for_aware_event_timestamp() -> None:
    connection = FakeConnection({})
    wall_clock = datetime(2024, 6, 15, 10, 16, 5)
    storage = EventStorage(StubAdapter(connection), clock=lambda: wall_clock)
    event_ts = datetime(2024, 6, 15, 10, 15, 42, tzinfo=timezone.utc)
    storage.apply_server_map_transition(3, "started", "de_dust2", event_ts)
    expected_unix = int(timegm(wall_clock.timetuple()))
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


def test_prune_idle_players_removes_stale_legacy_live_roster_member() -> None:
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection))
    server_id = 7
    now = datetime(2024, 1, 1, 12, 0, 0)
    stale_seen = now - timedelta(seconds=300)
    storage._server_players[server_id] = {101, 102}
    storage._server_live_players[server_id] = {101, 102}
    storage._server_connected_players[server_id] = {101, 102}
    storage._server_active_players[server_id] = {101, 102}
    storage._server_reward_eligible_players[server_id] = {101, 102}
    storage._server_player_last_activity[server_id] = {101: now, 102: stale_seen}

    storage._prune_idle_players(connection, server_id, now)

    assert storage._server_live_players[server_id] == {101}
    assert 102 not in storage._server_connected_players[server_id]
    assert server_id in storage._server_totals_dirty


def test_record_prunes_idle_players_on_legacy_timeout_cadence(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([WorldEventHandler()], fallback=GenericEventHandler())
    before_timeout = dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 12:04:20: World triggered "Round_Start"'),
        event_context,
    )
    after_timeout = dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 12:04:31: World triggered "Round_Start"'),
        event_context,
    )
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: before_timeout.timestamp)
    server_id = event_context.server_id
    stale_seen = datetime(2024, 1, 1, 12, 0, 0)
    storage._server_players[server_id] = {101}
    storage._server_live_players[server_id] = {101}
    storage._server_active_players[server_id] = {101}
    storage._server_player_last_activity[server_id] = {101: stale_seen}
    storage._server_next_idle_prune_at[server_id] = datetime(2024, 1, 1, 12, 4, 30)

    storage.record(before_timeout, event_context)

    assert storage._server_live_players[server_id] == {101}
    assert storage._server_player_last_activity[server_id] == {101: stale_seen}

    storage.record(after_timeout, event_context)

    assert storage._server_live_players[server_id] == set()
    assert storage._server_player_last_activity[server_id] == {}


def test_record_does_not_prune_idle_players_at_exact_legacy_timeout_boundary(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([WorldEventHandler()], fallback=GenericEventHandler())
    at_timeout = dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 12:04:30: World triggered "Round_Start"'),
        event_context,
    )
    after_timeout = dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 12:04:31: World triggered "Round_Start"'),
        event_context,
    )
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: at_timeout.timestamp)
    server_id = event_context.server_id
    stale_seen = datetime(2024, 1, 1, 12, 0, 0)
    storage._server_players[server_id] = {101, 102, 103, 104}
    storage._server_live_players[server_id] = {101, 102, 103, 104}
    storage._server_active_players[server_id] = {101, 102, 103, 104}
    storage._server_player_last_activity[server_id] = {
        101: stale_seen,
        102: stale_seen,
        103: stale_seen,
        104: stale_seen,
    }
    storage._server_next_idle_prune_at[server_id] = at_timeout.timestamp

    storage.record(at_timeout, event_context)

    assert storage._server_live_players[server_id] == {101, 102, 103, 104}
    assert storage._server_player_last_activity[server_id] == {
        101: stale_seen,
        102: stale_seen,
        103: stale_seen,
        104: stale_seen,
    }
    assert storage._server_next_idle_prune_at[server_id] == at_timeout.timestamp

    storage.record(after_timeout, event_context)

    assert storage._server_live_players[server_id] == set()
    assert storage._server_player_last_activity[server_id] == {}


def test_idle_prune_reschedules_to_legacy_timeout_scan_upper_bound(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher([WorldEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/01/2024 - 12:00:00: World triggered "Round_Start"'),
        event_context,
    )
    assert update is not None
    connection = FakeConnection({})
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    server_id = event_context.server_id
    storage._server_player_last_activity[server_id] = {101: update.timestamp}
    storage._server_next_idle_prune_at[server_id] = update.timestamp - timedelta(seconds=1)

    storage.record(update, event_context)

    assert storage._server_next_idle_prune_at[server_id] == update.timestamp + timedelta(seconds=60)


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


def test_ignored_trigger_with_unassigned_team_emits_implicit_change_team(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._player_teams[101] = "TERRORIST"

    storage.record(update, event_context)

    assert (_INSERT_TEAM_CHANGE_QUERY, (update.timestamp, 7, "de_dust2", 101, "UNASSIGNED")) in connection.executed
    assert storage._player_teams[101] == "UNASSIGNED"


def test_implicit_team_change_emits_on_blank_to_unassigned_from_status_trigger(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    blank_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Silver<2><STEAM_1:2><>" triggered "time"'),
        event_context,
    )
    unassigned_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:06: "Silver<2><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    assert blank_update.actor is not None
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: unassigned_update.timestamp)
    storage._player_cache[storage._cache_key_for_player(event_context.game, blank_update.actor)] = 101

    storage.record(blank_update, event_context)
    storage.record(unassigned_update, event_context)

    assert (_INSERT_TEAM_CHANGE_QUERY, (unassigned_update.timestamp, 7, "de_dust2", 101, "UNASSIGNED")) in connection.executed
    assert storage._player_teams[101] == "UNASSIGNED"


def test_rollover_blank_status_followed_by_unassigned_trigger_emits_implicit_change_team(
    event_context: EventContext,
) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    trigger_dispatcher = EventDispatcher([TriggerEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    first_update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Silver<2><STEAM_1:2><TERRORIST>" say "ready"'),
        event_context,
    )
    rollover_update = trigger_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:06: "Silver<3><STEAM_1:2><>" triggered "time"'),
        event_context,
    )
    unassigned_update = trigger_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "Silver<3><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: unassigned_update.timestamp)

    storage.record(first_update, event_context)
    storage.record(rollover_update, event_context)
    storage.record(unassigned_update, event_context)

    assert (_INSERT_TEAM_CHANGE_QUERY, (unassigned_update.timestamp, 7, "de_dust2", 101, "UNASSIGNED")) in connection.executed
    assert storage._player_teams[101] == "UNASSIGNED"


def test_rollover_blank_connect_and_blank_entry_before_unassigned_trigger_emits_implicit_change_team(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), EntryEventHandler(), TriggerEventHandler(), GenericEventHandler()],
        fallback=GenericEventHandler(),
    )
    first_connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Silver<719><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    rollover_connect_update = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:06: "Silver<720><STEAM_1:2><>" connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    entry_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "Silver<720><STEAM_1:2><>" entered the game'),
        event_context,
    )
    unassigned_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:08: "Silver<720><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: unassigned_update.timestamp)

    storage.record(first_connect_update, event_context)
    storage.record(rollover_connect_update, event_context)
    storage.record(entry_update, event_context)
    storage.record(unassigned_update, event_context)

    team_change_rows = [
        entry for entry in connection.executed if entry[0] == _INSERT_TEAM_CHANGE_QUERY
    ]
    assert team_change_rows == [
        (_INSERT_TEAM_CHANGE_QUERY, (unassigned_update.timestamp, 7, "de_dust2", 101, "UNASSIGNED"))
    ]
    assert storage._player_teams[101] == "UNASSIGNED"


def test_closed_player_blank_status_does_not_seed_implicit_change_team(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    blank_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Rakza<2><STEAM_1:2><>" triggered "time"'),
        event_context,
    )
    unassigned_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:06: "Rakza<2><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    assert blank_update.actor is not None
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: unassigned_update.timestamp)
    storage._player_cache[storage._cache_key_for_player(event_context.game, blank_update.actor)] = 101
    storage._closed_player_objects.add(101)

    storage.record(blank_update, event_context)
    storage.record(unassigned_update, event_context)

    assert all(query != _INSERT_TEAM_CHANGE_QUERY for query, _params in connection.executed)
    assert storage._player_teams[101] == "UNASSIGNED"


def test_kicked_unassigned_status_does_not_emit_stale_implicit_change_team(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [DisconnectEventHandler(), TriggerEventHandler(), GenericEventHandler()],
        fallback=GenericEventHandler(),
    )
    disconnect_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Rakza<2><STEAM_1:2><TERRORIST>" disconnected (reason "Kicked")'),
        event_context,
    )
    blank_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:06: "Rakza<2><STEAM_1:2><>" triggered "time"'),
        event_context,
    )
    unassigned_update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:07: "Rakza<2><STEAM_1:2><UNASSIGNED>" triggered "time"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: disconnect_update.timestamp)
    storage._player_teams[101] = "TERRORIST"

    storage.record(disconnect_update, event_context)
    storage.record(blank_update, event_context)
    storage.record(unassigned_update, event_context)

    assert all(query != _INSERT_TEAM_CHANGE_QUERY for query, _params in connection.executed)
    assert storage._player_teams[101] == "UNASSIGNED"


def test_blank_descriptor_team_does_not_emit_implicit_change_team(event_context: EventContext) -> None:
    chat_dispatcher = EventDispatcher([ChatEventHandler()])
    update = chat_dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:2><>" say "ready"'),
        event_context,
    )
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo")): [QueryResponse(fetchone=(101,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._player_teams[101] = "TERRORIST"

    storage.record(update, event_context)

    assert all(query != _INSERT_TEAM_CHANGE_QUERY for query, _params in connection.executed)
    assert storage._player_teams[101] == "TERRORIST"


def test_ignored_bot_implicit_team_sync_updates_runtime_only(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "BotOne<664><BOT><TERRORIST>" triggered "time"'),
        event_context,
    )
    assert update.actor is not None
    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, (update.actor.unique_id, "csgo")): [QueryResponse(fetchone=(501,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._player_cache[storage._cache_key_for_player(event_context.game, update.actor)] = 501
    storage._player_teams[501] = "CT"

    storage.record(update, event_context)

    assert all(query != _INSERT_TEAM_CHANGE_QUERY for query, _params in connection.executed)
    assert storage._player_teams[501] == "TERRORIST"


def test_transient_id_implicit_team_sync_writes_no_change_team(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TriggerEventHandler(), GenericEventHandler()], fallback=GenericEventHandler())
    update = dispatcher.dispatch(
        parse_log_event('L 01/02/2024 - 03:04:05: "AdBot<2><STEAM_ID_LAN><TERRORIST>" triggered "time"'),
        event_context,
    )
    connection = FakeConnection()
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)

    storage.record(update, event_context)

    assert all(query != _INSERT_TEAM_CHANGE_QUERY for query, _params in connection.executed)


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


def test_team_bonus_awards_live_roster_player_without_active_or_reward_eligible_entry(
    event_context: EventContext,
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
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(0,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_live_players[7] = {101}
    storage._server_active_players[7] = set()
    storage._server_connected_players[7] = set()
    storage._server_reward_eligible_players[7] = set()
    storage._player_teams[101] = "CT"

    storage.record(update, context)

    assert (
        _INSERT_TEAM_BONUS_QUERY,
        (update.timestamp, 7, "de_dust2", 101, 755, 2),
    ) in connection.executed


def test_team_bonus_awards_team_bound_player_without_live_roster(
    event_context: EventContext,
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
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(0,))],
        (_SELECT_PLAYER_STATE_QUERY, (101,)): [QueryResponse(fetchone=(1000, 0, "", 0))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_players[7] = {101}
    storage._server_live_players[7] = set()
    storage._server_active_players[7] = set()
    storage._server_connected_players[7] = set()
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


def test_team_bonus_rescued_hostage_ignores_round_status_gate(event_context: EventContext) -> None:
    dispatcher = EventDispatcher([TeamTriggerEventHandler()], fallback=GenericEventHandler())
    event = parse_log_event('L 01/02/2024 - 03:04:05: Team "CT" triggered "Rescued_A_Hostage"')
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
        (_SELECT_SERVER_CONFIG_QUERY, (7, "MinPlayers")): [QueryResponse(fetchone=(0,))],
        (_SELECT_ACTION_QUERY, ("csgo", "Rescued_A_Hostage")): [QueryResponse(fetchone=(272, 0, 1, "CT"))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: update.timestamp)
    storage._server_active_players[7] = {101, 102}
    storage._server_reward_eligible_players[7] = {101, 102}
    storage._player_teams.update({101: "CT", 102: "CT"})

    storage.record(update, context)

    insert_rows = [entry for entry in connection.executed if entry[0] == _INSERT_TEAM_BONUS_QUERY]
    assert len(insert_rows) == 2


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


def test_transient_zero_userid_does_not_mark_steam_player_as_permanent_bot(
    event_context: EventContext,
) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), TeamEventHandler()],
        fallback=GenericEventHandler(),
    )
    transient_connect = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:04: "Mep3ocTb<0><STEAM_0:1:45686725><>" '
            'connected, address "1.2.3.4:27005"'
        ),
        event_context,
    )
    valid_team_join = dispatcher.dispatch(
        parse_log_event(
            'L 01/02/2024 - 03:04:05: "Mep3ocTb<2><STEAM_0:1:45686725><>" joined team "TERRORIST"'
        ),
        event_context,
    )
    assert transient_connect is not None
    assert valid_team_join is not None

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_PLAYER_BY_UNIQUE_QUERY, ("1:45686725", "csgo")): [QueryResponse(fetchone=(187,))],
        (_SELECT_SERVER_CONFIG_QUERY, (7, "IgnoreBots")): [QueryResponse(fetchone=(1,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: transient_connect.timestamp)

    storage.record(transient_connect, event_context)
    storage.record(valid_team_join, event_context)

    assert (
        _INSERT_TEAM_CHANGE_QUERY,
        (valid_team_join.timestamp, 7, "de_dust2", 187, "TERRORIST"),
    ) in connection.executed
    assert storage._player_is_bot[187] is False
    assert storage._server_active_players[7] == {187}


def test_entry_event_records_non_empty_team_players(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), EntryEventHandler()],
        fallback=GenericEventHandler(),
    )
    connect_event = parse_log_event(
        'L 01/02/2024 - 03:04:04: "Alice<664><STEAM_0:1:2><CT>" connected, address "1.2.3.4:27005"'
    )
    entry_event = parse_log_event('L 01/02/2024 - 03:04:05: "Alice<664><STEAM_0:1:2><CT>" entered the game')
    connect_update = dispatcher.dispatch(connect_event, event_context)
    entry_update = dispatcher.dispatch(entry_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(301,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: datetime(2024, 1, 2, 3, 4, 5))

    storage.record(connect_update, event_context)
    storage.record(entry_update, event_context)

    entry_rows = [params for query, params in connection.executed if query == _INSERT_ENTRY_QUERY]
    assert entry_update.actor is not None
    assert entry_update.actor.team == "CT"
    assert entry_rows == [(datetime(2024, 1, 2, 3, 4, 5), 7, "de_dust2", 301)]


def test_entry_event_skips_empty_team_players(event_context: EventContext) -> None:
    dispatcher = EventDispatcher(
        [ConnectEventHandler(), EntryEventHandler()],
        fallback=GenericEventHandler(),
    )
    connect_event = parse_log_event(
        'L 01/02/2024 - 03:04:04: "Alice<664><STEAM_0:1:2><>" connected, address "1.2.3.4:27005"'
    )
    entry_event = parse_log_event('L 01/02/2024 - 03:04:05: "Alice<664><STEAM_0:1:2><>" entered the game')
    connect_update = dispatcher.dispatch(connect_event, event_context)
    entry_update = dispatcher.dispatch(entry_event, event_context)

    responses: Dict[QueryKey, List[QueryResponse]] = {
        (_LAST_INSERT_ID_QUERY, None): [QueryResponse(fetchone=(301,))],
    }
    connection = FakeConnection(responses)
    storage = EventStorage(StubAdapter(connection), clock=lambda: datetime(2024, 1, 2, 3, 4, 5))

    storage.record(connect_update, event_context)
    storage.record(entry_update, event_context)

    assert entry_update.actor is not None
    assert entry_update.actor.team == ""
    assert all(query != _INSERT_ENTRY_QUERY for query, _params in connection.executed)
