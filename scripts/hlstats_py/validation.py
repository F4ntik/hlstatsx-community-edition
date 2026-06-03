"""Validation helpers for replaying proxy traffic against the Python pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .events import EventContext, EventDispatcher
from .protocol import parse_log_event, parse_proxy_envelope
from .storage import (
    EventStorage,
    _DELETE_PLAYER_HISTORY_QUERY,
    _INSERT_ACTION_QUERY,
    _INSERT_ADMIN_EVENT_QUERY,
    _INSERT_CHAT_QUERY,
    _INSERT_CONNECT_QUERY,
    _INSERT_DISCONNECT_QUERY,
    _INSERT_FRAG_QUERY,
    _INSERT_PLAYER_ACTION_QUERY,
    _INSERT_PLAYER_PLAYER_ACTION_QUERY,
    _INSERT_PLAYER_QUERY,
    _INSERT_SUICIDE_QUERY,
    _INSERT_TEAMKILL_QUERY,
    _INSERT_TEAM_CHANGE_QUERY,
    _INCREMENT_ACTION_COUNT_QUERY,
    _LAST_INSERT_ID_QUERY,
    _PLAYER_BY_NAME_QUERY,
    _PLAYER_BY_UNIQUE_QUERY,
    _REPLACE_PLAYER_HISTORY_SNAPSHOT_QUERY,
    _SELECT_ACTION_QUERY,
    _SELECT_DEFAULT_SERVER_CONFIG_QUERY,
    _SELECT_OPTION_QUERY,
    _SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY,
    _SELECT_PLAYER_STATE_QUERY,
    _SELECT_SERVER_CONFIG_QUERY,
    _SELECT_WEAPON_MODIFIER_QUERY,
    _UPDATE_PLAYER_DEATHS_QUERY,
    _UPDATE_PLAYER_CONNECTION_TIME_QUERY,
    _UPDATE_PLAYER_FRAG_ROLLUP_QUERY,
    _UPDATE_PLAYER_KILLS_QUERY,
    _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY,
    _UPDATE_PLAYER_NAME_QUERY,
    _UPDATE_PLAYER_STREAKS_QUERY,
    _UPDATE_PLAYER_HISTORY_QUERY,
    _UPDATE_PLAYERNAME_LASTUSE_QUERY,
    _UPDATE_PLAYERNAME_TOTALS_QUERY,
    _UPDATE_PLAYER_SKILL_QUERY,
    _UPDATE_PLAYER_SUICIDES_QUERY,
    _UPDATE_PLAYER_TEAMKILLS_QUERY,
    _UPDATE_SERVER_FRAG_TOTALS_QUERY,
    _UPDATE_SERVER_MAP_LOADING_QUERY,
    _UPDATE_SERVER_MAP_STARTED_QUERY,
    _UPDATE_SERVER_PLAYER_TOTALS_QUERY,
    _UPDATE_SERVER_SUICIDE_TOTALS_QUERY,
    _UPSERT_MAP_COUNTS_QUERY,
    _UPSERT_PLAYER_HISTORY_QUERY,
    _UPSERT_PLAYER_NAME_QUERY,
    _UPSERT_PLAYER_UNIQUE_QUERY,
    _UPSERT_WEAPON_QUERY,
)


_LAST_ADDRESS_UPDATE_QUERY = "UPDATE hlstats_Players SET `lastAddress` = %s WHERE `playerId` = %s"


@dataclass(frozen=True)
class FragSnapshot:
    """Captured frag row produced by :class:`EventStorage`."""

    timestamp: datetime
    server_id: int
    map: str
    killer_id: int
    victim_id: int
    weapon: str
    headshot: bool


@dataclass(frozen=True)
class TeamkillSnapshot:
    """Captured teamkill row produced by :class:`EventStorage`."""

    timestamp: datetime
    server_id: int
    map: str
    killer_id: int
    victim_id: int
    weapon: str


@dataclass(frozen=True)
class PlayerActionSnapshot:
    """Representation of rows written to action event tables."""

    timestamp: datetime
    server_id: int
    map: str
    player_id: int
    action_code: str
    bonus: int
    victim_id: Optional[int] = None


@dataclass(frozen=True)
class ChatMessageSnapshot:
    """Chat payload emitted by :class:`EventStorage`."""

    timestamp: datetime
    player_id: int
    team_only: bool
    message: str


@dataclass(frozen=True)
class ConnectionSnapshot:
    """Connection record inserted during replay."""

    timestamp: datetime
    player_id: int
    address: str


@dataclass(frozen=True)
class DisconnectSnapshot:
    """Disconnect record inserted during replay."""

    timestamp: datetime
    player_id: int


@dataclass(frozen=True)
class AdminEventSnapshot:
    """Generic/admin event captured during replay."""

    timestamp: datetime
    event_type: str
    message: str
    player_name: str


@dataclass(frozen=True)
class ActionSnapshot:
    """Metadata about an action definition used during replay."""

    action_id: int
    code: str
    description: str
    count: int
    reward_player: int
    reward_team: int


@dataclass(frozen=True)
class WeaponSnapshot:
    """Aggregated information about a weapon stat row."""

    code: str
    name: str
    kills: int
    headshots: int


@dataclass(frozen=True)
class PlayerSnapshot:
    """Final counters for a player after processing a replay."""

    player_id: int
    name: str
    unique_ids: Tuple[str, ...]
    kills: int
    headshots: int
    deaths: int
    suicides: int
    teamkills: int
    skill: int
    connections: int
    disconnects: int
    last_address: Optional[str]


@dataclass(frozen=True)
class ReplaySnapshot:
    """Immutable view over the in-memory state gathered during replay."""

    players: Mapping[int, PlayerSnapshot]
    players_by_unique: Mapping[str, PlayerSnapshot]
    actions: Mapping[str, ActionSnapshot]
    weapons: Mapping[str, WeaponSnapshot]
    frags: Tuple[FragSnapshot, ...]
    teamkills: Tuple[TeamkillSnapshot, ...]
    player_actions: Tuple[PlayerActionSnapshot, ...]
    chat_messages: Tuple[ChatMessageSnapshot, ...]
    connections: Tuple[ConnectionSnapshot, ...]
    disconnects: Tuple[DisconnectSnapshot, ...]
    admin_events: Tuple[AdminEventSnapshot, ...]


@dataclass(frozen=True)
class ReplayResult:
    """Result returned by :class:`ReplayRunner`."""

    snapshot: ReplaySnapshot
    executed_queries: Tuple[Tuple[str, Optional[Tuple[object, ...]]], ...]


@dataclass
class _ExecutionResult:
    fetchone: Optional[Tuple[object, ...]] = None
    fetchall: Optional[Sequence[Tuple[object, ...]]] = None


@dataclass
class _PlayerRecord:
    player_id: int
    game: str
    name: str
    unique_ids: List[str] = field(default_factory=list)
    connection_time: int = 0
    kills: int = 0
    headshots: int = 0
    deaths: int = 0
    suicides: int = 0
    teamkills: int = 0
    skill: int = 1000
    last_skill_change: int = 0
    connections: int = 0
    disconnects: int = 0
    last_address: Optional[str] = None


@dataclass
class _ActionRecord:
    action_id: int
    game: str
    code: str
    description: str
    reward_player: int
    reward_team: int
    count: int = 0


@dataclass
class _WeaponRecord:
    game: str
    code: str
    name: str
    kills: int = 0
    headshots: int = 0


@dataclass
class _PlayerHistoryRecord:
    player_id: int
    game: str
    event_time: datetime
    connection_time: int = 0
    kills: int = 0
    deaths: int = 0
    suicides: int = 0
    skill: int = 1000
    headshots: int = 0
    shots: int = 0
    hits: int = 0
    teamkills: int = 0
    death_streak: int = 0
    kill_streak: int = 0
    skill_change: int = 0


class ReplayDatabase:
    """In-memory stand-in for the HLstats MySQL schema used in tests."""

    def __init__(self) -> None:
        self._players: Dict[int, _PlayerRecord] = {}
        self._player_names: Dict[Tuple[str, str], List[int]] = {}
        self._player_unique: Dict[Tuple[str, str], int] = {}
        self._actions_by_code: Dict[Tuple[str, str], _ActionRecord] = {}
        self._actions_by_id: Dict[int, _ActionRecord] = {}
        self._weapons: Dict[Tuple[str, str], _WeaponRecord] = {}
        self._player_history: Dict[Tuple[int, datetime, str], _PlayerHistoryRecord] = {}
        self._frags: List[FragSnapshot] = []
        self._teamkills: List[TeamkillSnapshot] = []
        self._player_actions: List[PlayerActionSnapshot] = []
        self._chat_messages: List[ChatMessageSnapshot] = []
        self._connections: List[ConnectionSnapshot] = []
        self._disconnects: List[DisconnectSnapshot] = []
        self._admin_events: List[AdminEventSnapshot] = []
        self._executed: List[Tuple[str, Optional[Tuple[object, ...]]]] = []
        self._next_player_id = 1
        self._next_action_id = 1
        self._last_insert_id = 0

    # ------------------------------------------------------------------
    # DB-API surface used by :class:`EventStorage`

    def cursor(self) -> "ReplayCursor":
        return ReplayCursor(self)

    @property
    def executed(self) -> Tuple[Tuple[str, Optional[Tuple[object, ...]]], ...]:
        return tuple(self._executed)

    # ------------------------------------------------------------------
    # Query handlers

    def _handle_execute(
        self, query: str, params: Optional[Iterable[object]]
    ) -> _ExecutionResult:
        normalized_params = tuple(params) if params is not None else None
        self._executed.append((query, normalized_params))

        if query == _PLAYER_BY_UNIQUE_QUERY:
            assert normalized_params is not None
            unique_id, game = normalized_params
            player_id = self._player_unique.get((str(game), str(unique_id)))
            return _ExecutionResult(fetchone=(player_id,) if player_id is not None else None)
        if query == _PLAYER_BY_NAME_QUERY:
            assert normalized_params is not None
            name, game = normalized_params
            key = (str(game), str(name).lower())
            ids = self._player_names.get(key, [])
            return _ExecutionResult(fetchone=((ids[-1],) if ids else None))
        if query == _INSERT_PLAYER_QUERY:
            assert normalized_params is not None
            game, name = normalized_params
            player_id = self._next_player_id
            self._next_player_id += 1
            record = _PlayerRecord(player_id=player_id, game=str(game), name=str(name))
            self._players[player_id] = record
            key = (record.game, record.name.lower())
            self._player_names.setdefault(key, []).append(player_id)
            self._last_insert_id = player_id
            return _ExecutionResult()
        if query == _LAST_INSERT_ID_QUERY:
            return _ExecutionResult(fetchone=(self._last_insert_id,))
        if query == _SELECT_PLAYER_STATE_QUERY:
            assert normalized_params is not None
            (player_id,) = normalized_params
            record = self._players.get(int(player_id))
            if record is None:
                return _ExecutionResult(fetchone=None)
            return _ExecutionResult(
                fetchone=(record.skill, record.kills, record.last_address, 0, record.last_skill_change)
            )
        if query == _UPDATE_PLAYER_NAME_QUERY:
            assert normalized_params is not None
            name, player_id = normalized_params
            record = self._players[int(player_id)]
            record.name = str(name)
            key = (record.game, record.name.lower())
            ids = self._player_names.setdefault(key, [])
            if record.player_id not in ids:
                ids.append(record.player_id)
            return _ExecutionResult()
        if query == _UPSERT_PLAYER_NAME_QUERY:
            assert normalized_params is not None
            player_id, name, _lastuse = normalized_params
            record = self._players[int(player_id)]
            record.name = str(name)
            key = (record.game, record.name.lower())
            ids = self._player_names.setdefault(key, [])
            if record.player_id not in ids:
                ids.append(record.player_id)
            return _ExecutionResult()
        if query == _UPDATE_PLAYERNAME_LASTUSE_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_PLAYERNAME_TOTALS_QUERY:
            return _ExecutionResult()
        if query == _UPSERT_PLAYER_HISTORY_QUERY:
            assert normalized_params is not None
            player_id, event_time, game, skill = normalized_params
            self._player_history.setdefault(
                (int(player_id), event_time, str(game)),
                _PlayerHistoryRecord(
                    player_id=int(player_id),
                    event_time=event_time,
                    game=str(game),
                    skill=int(skill),
                ),
            )
            return _ExecutionResult()
        if query == _SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY:
            assert normalized_params is not None
            player_id, event_time, game = normalized_params
            row = self._player_history.get((int(player_id), event_time, str(game)))
            if row is None:
                return _ExecutionResult(fetchone=None)
            return _ExecutionResult(
                fetchone=(
                    row.connection_time,
                    row.kills,
                    row.deaths,
                    row.suicides,
                    row.skill,
                    row.headshots,
                    row.shots,
                    row.hits,
                    row.teamkills,
                    row.death_streak,
                    row.kill_streak,
                    row.skill_change,
                )
            )
        if query == _REPLACE_PLAYER_HISTORY_SNAPSHOT_QUERY:
            assert normalized_params is not None
            (
                connection_time,
                kills,
                deaths,
                suicides,
                skill,
                headshots,
                shots,
                hits,
                teamkills,
                death_streak,
                kill_streak,
                skill_change,
                player_id,
                event_time,
                game,
            ) = normalized_params
            self._player_history[(int(player_id), event_time, str(game))] = _PlayerHistoryRecord(
                player_id=int(player_id),
                event_time=event_time,
                game=str(game),
                connection_time=int(connection_time),
                kills=int(kills),
                deaths=int(deaths),
                suicides=int(suicides),
                skill=int(skill),
                headshots=int(headshots),
                shots=int(shots),
                hits=int(hits),
                teamkills=int(teamkills),
                death_streak=int(death_streak),
                kill_streak=int(kill_streak),
                skill_change=int(skill_change),
            )
            return _ExecutionResult()
        if query == _DELETE_PLAYER_HISTORY_QUERY:
            assert normalized_params is not None
            player_id, event_time, game = normalized_params
            self._player_history.pop((int(player_id), event_time, str(game)), None)
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_HISTORY_QUERY:
            assert normalized_params is not None
            (
                connection_time,
                kills,
                deaths,
                suicides,
                skill,
                headshots,
                shots,
                hits,
                teamkills,
                death_streak,
                _death_streak_again,
                kill_streak,
                _kill_streak_again,
                skill_change,
                player_id,
                event_time,
                game,
            ) = normalized_params
            record = self._player_history.setdefault(
                (int(player_id), event_time, str(game)),
                _PlayerHistoryRecord(
                    player_id=int(player_id),
                    event_time=event_time,
                    game=str(game),
                    skill=int(skill),
                ),
            )
            record.connection_time += int(connection_time)
            record.kills += int(kills)
            record.deaths += int(deaths)
            record.suicides += int(suicides)
            record.skill = int(skill)
            record.headshots += int(headshots)
            record.shots += int(shots)
            record.hits += int(hits)
            record.teamkills += int(teamkills)
            record.death_streak = max(record.death_streak, int(death_streak))
            record.kill_streak = max(record.kill_streak, int(kill_streak))
            record.skill_change += int(skill_change)
            return _ExecutionResult()
        if query == _UPSERT_PLAYER_UNIQUE_QUERY:
            assert normalized_params is not None
            player_id, unique_id, game = normalized_params
            record = self._players[int(player_id)]
            unique = str(unique_id)
            if unique not in record.unique_ids:
                record.unique_ids.append(unique)
            self._player_unique[(str(game), unique)] = record.player_id
            return _ExecutionResult()
        if query == _INSERT_FRAG_QUERY:
            assert normalized_params is not None
            (
                timestamp,
                server_id,
                map_name,
                killer_id,
                victim_id,
                weapon,
                headshot,
                _killer_role,
                _victim_role,
                *_positions,
            ) = normalized_params
            frag = FragSnapshot(
                timestamp=timestamp,
                server_id=int(server_id),
                map=str(map_name),
                killer_id=int(killer_id),
                victim_id=int(victim_id),
                weapon=str(weapon),
                headshot=bool(headshot),
            )
            self._frags.append(frag)
            return _ExecutionResult()
        if query == _INSERT_TEAMKILL_QUERY:
            assert normalized_params is not None
            (
                timestamp,
                server_id,
                map_name,
                killer_id,
                victim_id,
                weapon,
                *_positions,
            ) = normalized_params
            self._teamkills.append(
                TeamkillSnapshot(
                    timestamp=timestamp,
                    server_id=int(server_id),
                    map=str(map_name),
                    killer_id=int(killer_id),
                    victim_id=int(victim_id),
                    weapon=str(weapon),
                )
            )
            return _ExecutionResult()
        if query == _INSERT_SUICIDE_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_SERVER_MAP_LOADING_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_SERVER_MAP_STARTED_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_KILLS_QUERY:
            assert normalized_params is not None
            kills, headshots, player_id = normalized_params
            record = self._players[int(player_id)]
            record.kills += int(kills)
            record.headshots += int(headshots)
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_DEATHS_QUERY:
            assert normalized_params is not None
            (player_id,) = normalized_params
            record = self._players[int(player_id)]
            record.deaths += 1
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_SUICIDES_QUERY:
            assert normalized_params is not None
            (player_id,) = normalized_params
            record = self._players[int(player_id)]
            record.suicides += 1
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_TEAMKILLS_QUERY:
            assert normalized_params is not None
            (player_id,) = normalized_params
            record = self._players[int(player_id)]
            record.teamkills += 1
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_STREAKS_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_FRAG_ROLLUP_QUERY:
            assert normalized_params is not None
            (
                kills,
                headshots,
                deaths,
                suicides,
                skill_delta,
                _kill_streak_cmp,
                _kill_streak_val,
                _death_streak_cmp,
                _death_streak_val,
                player_id,
            ) = normalized_params
            record = self._players[int(player_id)]
            record.kills += int(kills)
            record.headshots += int(headshots)
            record.deaths += int(deaths)
            record.suicides += int(suicides)
            record.skill += int(skill_delta)
            return _ExecutionResult()
        if query == _UPSERT_WEAPON_QUERY:
            assert normalized_params is not None
            game, code, name, _modifier, kills, headshots = normalized_params
            key = (str(game), str(code))
            weapon = self._weapons.get(key)
            if weapon is None:
                weapon = _WeaponRecord(game=str(game), code=str(code), name=str(name))
                self._weapons[key] = weapon
            weapon.name = str(name)
            weapon.kills += int(kills)
            weapon.headshots += int(headshots)
            return _ExecutionResult()
        if query == _SELECT_ACTION_QUERY:
            assert normalized_params is not None
            game, code = normalized_params
            record = self._actions_by_code.get((str(game), str(code)))
            if record is None:
                return _ExecutionResult(fetchone=None)
            return _ExecutionResult(
                fetchone=(record.action_id, record.reward_player, record.reward_team)
            )
        if query == _SELECT_SERVER_CONFIG_QUERY:
            return _ExecutionResult(fetchone=None)
        if query == _SELECT_DEFAULT_SERVER_CONFIG_QUERY:
            return _ExecutionResult(fetchone=None)
        if query == _SELECT_OPTION_QUERY:
            return _ExecutionResult(fetchone=None)
        if query == _SELECT_WEAPON_MODIFIER_QUERY:
            return _ExecutionResult(fetchone=None)
        if query == _INSERT_ACTION_QUERY:
            assert normalized_params is not None
            game, code, description, reward_player, reward_team, _team = normalized_params
            action_id = self._next_action_id
            self._next_action_id += 1
            record = _ActionRecord(
                action_id=action_id,
                game=str(game),
                code=str(code),
                description=str(description),
                reward_player=int(reward_player),
                reward_team=int(reward_team),
            )
            self._actions_by_code[(record.game, record.code)] = record
            self._actions_by_id[action_id] = record
            self._last_insert_id = action_id
            return _ExecutionResult()
        if query == _INCREMENT_ACTION_COUNT_QUERY:
            assert normalized_params is not None
            (action_id,) = normalized_params
            record = self._actions_by_id[int(action_id)]
            record.count += 1
            return _ExecutionResult()
        if query == _INSERT_PLAYER_ACTION_QUERY:
            assert normalized_params is not None
            timestamp, server_id, map_name, player_id, action_id, bonus = normalized_params
            record = self._actions_by_id[int(action_id)]
            snapshot = PlayerActionSnapshot(
                timestamp=timestamp,
                server_id=int(server_id),
                map=str(map_name),
                player_id=int(player_id),
                action_code=record.code,
                bonus=int(bonus),
            )
            self._player_actions.append(snapshot)
            return _ExecutionResult()
        if query == _INSERT_PLAYER_PLAYER_ACTION_QUERY:
            assert normalized_params is not None
            timestamp, server_id, map_name, player_id, victim_id, action_id, bonus = normalized_params
            record = self._actions_by_id[int(action_id)]
            snapshot = PlayerActionSnapshot(
                timestamp=timestamp,
                server_id=int(server_id),
                map=str(map_name),
                player_id=int(player_id),
                victim_id=int(victim_id),
                action_code=record.code,
                bonus=int(bonus),
            )
            self._player_actions.append(snapshot)
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_SKILL_QUERY:
            assert normalized_params is not None
            delta, player_id = normalized_params
            record = self._players[int(player_id)]
            record.skill += int(delta)
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_CONNECTION_TIME_QUERY:
            assert normalized_params is not None
            delta, player_id = normalized_params
            record = self._players[int(player_id)]
            record.connection_time += int(delta)
            return _ExecutionResult()
        if query == _UPDATE_PLAYER_LAST_SKILL_CHANGE_QUERY:
            assert normalized_params is not None
            value, player_id = normalized_params
            record = self._players[int(player_id)]
            record.last_skill_change = int(value)
            return _ExecutionResult()
        if query == _UPDATE_SERVER_PLAYER_TOTALS_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_SERVER_FRAG_TOTALS_QUERY:
            return _ExecutionResult()
        if query == _UPDATE_SERVER_SUICIDE_TOTALS_QUERY:
            return _ExecutionResult()
        if query == _UPSERT_MAP_COUNTS_QUERY:
            return _ExecutionResult()
        if query == _INSERT_CHAT_QUERY:
            assert normalized_params is not None
            timestamp, _server_id, _map_name, player_id, team_only, message = normalized_params
            chat = ChatMessageSnapshot(
                timestamp=timestamp,
                player_id=int(player_id),
                team_only=bool(team_only),
                message=str(message),
            )
            self._chat_messages.append(chat)
            return _ExecutionResult()
        if query == _INSERT_TEAM_CHANGE_QUERY:
            assert normalized_params is not None
            timestamp, _server_id, _map_name, _player_id, _team = normalized_params
            # Team changes are not aggregated for validation yet.
            return _ExecutionResult()
        if query == _INSERT_CONNECT_QUERY:
            assert normalized_params is not None
            timestamp, _server_id, _map_name, player_id, address, _hostname, _hostgroup = normalized_params
            connection = ConnectionSnapshot(
                timestamp=timestamp,
                player_id=int(player_id),
                address=str(address),
            )
            self._connections.append(connection)
            if int(player_id) in self._players:
                record = self._players[int(player_id)]
                record.connections += 1
                record.last_address = connection.address or record.last_address
            return _ExecutionResult()
        if query == _INSERT_DISCONNECT_QUERY:
            assert normalized_params is not None
            timestamp, _server_id, _map_name, player_id = normalized_params
            disconnect = DisconnectSnapshot(
                timestamp=timestamp,
                player_id=int(player_id),
            )
            self._disconnects.append(disconnect)
            if int(player_id) in self._players:
                record = self._players[int(player_id)]
                record.disconnects += 1
            return _ExecutionResult()
        if query == _INSERT_ADMIN_EVENT_QUERY:
            assert normalized_params is not None
            timestamp, _server_id, _map_name, event_type, message, player_name = normalized_params
            admin = AdminEventSnapshot(
                timestamp=timestamp,
                event_type=str(event_type),
                message=str(message),
                player_name=str(player_name),
            )
            self._admin_events.append(admin)
            return _ExecutionResult()
        if query == _LAST_ADDRESS_UPDATE_QUERY:
            assert normalized_params is not None
            address, player_id = normalized_params
            record = self._players.get(int(player_id))
            if record is not None:
                record.last_address = str(address)
            return _ExecutionResult()

        raise ValueError(f"Unhandled query during replay: {query!r}")

    # ------------------------------------------------------------------
    # Snapshot helpers

    def snapshot(self) -> ReplaySnapshot:
        players = {
            player_id: PlayerSnapshot(
                player_id=record.player_id,
                name=record.name,
                unique_ids=tuple(record.unique_ids),
                kills=record.kills,
                headshots=record.headshots,
                deaths=record.deaths,
                suicides=record.suicides,
                teamkills=record.teamkills,
                skill=record.skill,
                connections=record.connections,
                disconnects=record.disconnects,
                last_address=record.last_address,
            )
            for player_id, record in self._players.items()
        }
        players_by_unique = {
            unique: players[player_id]
            for (game, unique), player_id in self._player_unique.items()
            if player_id in players
        }
        actions = {
            code: ActionSnapshot(
                action_id=record.action_id,
                code=record.code,
                description=record.description,
                count=record.count,
                reward_player=record.reward_player,
                reward_team=record.reward_team,
            )
            for (game, code), record in self._actions_by_code.items()
        }
        weapons = {
            code: WeaponSnapshot(
                code=record.code,
                name=record.name,
                kills=record.kills,
                headshots=record.headshots,
            )
            for (game, code), record in self._weapons.items()
        }
        return ReplaySnapshot(
            players=MappingProxyType(players),
            players_by_unique=MappingProxyType(players_by_unique),
            actions=MappingProxyType(actions),
            weapons=MappingProxyType(weapons),
            frags=tuple(self._frags),
            teamkills=tuple(self._teamkills),
            player_actions=tuple(self._player_actions),
            chat_messages=tuple(self._chat_messages),
            connections=tuple(self._connections),
            disconnects=tuple(self._disconnects),
            admin_events=tuple(self._admin_events),
        )


class ReplayCursor:
    """DB-API compatible cursor backed by :class:`ReplayDatabase`."""

    def __init__(self, database: ReplayDatabase) -> None:
        self._database = database
        self._result = _ExecutionResult()

    def execute(self, query: str, params: Optional[Iterable[object]] = None) -> None:
        self._result = self._database._handle_execute(query, params)

    def executemany(self, query: str, params: Sequence[Iterable[object]]) -> None:
        for row in params:
            self.execute(query, row)

    def fetchone(self) -> Optional[Tuple[object, ...]]:
        return self._result.fetchone

    def fetchall(self) -> List[Tuple[object, ...]]:
        if self._result.fetchall is None:
            return []
        return list(self._result.fetchall)

    def close(self) -> None:  # pragma: no cover - API compliance
        self._result = _ExecutionResult()


class ReplayAdapter:
    """Adapter that exposes a :class:`ReplayDatabase` through the expected API."""

    def __init__(self, database: ReplayDatabase) -> None:
        self._database = database

    def connection(self) -> ReplayDatabase:
        return self._database


class ReplayRunner:
    """Utility that replays proxied datagrams through the storage pipeline."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        context: EventContext,
        *,
        storage: Optional[EventStorage] = None,
        database: Optional[ReplayDatabase] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._context = context
        self._database = database or ReplayDatabase()
        self._storage = storage or EventStorage(ReplayAdapter(self._database))

    @property
    def database(self) -> ReplayDatabase:
        return self._database

    def feed(self, datagram: str) -> None:
        envelope = parse_proxy_envelope(datagram)
        event = parse_log_event(envelope.payload)
        update = self._dispatcher.dispatch(event, self._context)
        self._storage.record(update, self._context)

    def run(self, datagrams: Iterable[str]) -> ReplayResult:
        for datagram in datagrams:
            self.feed(datagram)
        snapshot = self._database.snapshot()
        return ReplayResult(snapshot=snapshot, executed_queries=self._database.executed)


__all__ = [
    "ReplayRunner",
    "ReplayDatabase",
    "ReplayAdapter",
    "ReplayResult",
    "ReplaySnapshot",
    "PlayerSnapshot",
    "WeaponSnapshot",
    "ActionSnapshot",
    "FragSnapshot",
    "TeamkillSnapshot",
    "PlayerActionSnapshot",
    "ChatMessageSnapshot",
    "ConnectionSnapshot",
    "DisconnectSnapshot",
    "AdminEventSnapshot",
]
