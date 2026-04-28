"""Persistence layer that mirrors ``hlstats.pl`` database mutations."""
from __future__ import annotations

from calendar import timegm
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Optional, Protocol

from proxy_daemon_py import db as proxy_db
from .events import EventCategory, EventContext, EventUpdate
from .event_buffer import BufferPolicy, EventBuffer
from .frag_write_delta_buffer import FragWriteDeltaBuffer
from .protocol import PlayerDescriptor

# Public re-exports from ``proxy_daemon_py`` are defined in ``__init__`` so we
# import lazily and guard for type checkers. The runtime package layout keeps the
# modules side by side under ``scripts``.


class StorageError(RuntimeError):
    """Raised when an event update cannot be written to the database."""


class SupportsConnectionProvider(Protocol):
    """Protocol implemented by database adapters that expose a connection."""

    def connection(self) -> proxy_db.SupportsConnection:  # pragma: no cover - protocol
        ...


# Query templates. These constants are shared with tests to validate ordering.
_PLAYER_BY_UNIQUE_QUERY = (
    "SELECT `playerId` FROM hlstats_PlayerUniqueIds WHERE `uniqueId` = %s AND `game` = %s"
)
# Kept for compatibility with validation replay helpers; runtime lookup no longer
# uses name-only fallback to avoid cross-player merges.
_PLAYER_BY_NAME_QUERY = (
    "SELECT `playerId` FROM hlstats_Players WHERE `lastName` = %s AND `game` = %s"
    " ORDER BY `playerId` DESC LIMIT 1"
)
_STEAM_PREFIX_RE = re.compile(r"^STEAM_[01]:", re.IGNORECASE)
_BOT_UNIQUE_RE = re.compile(r"^(?:BOT(?:[:\-].*)?|0|00000000:\d+:0)$", re.IGNORECASE)
_ACTIVE_PLAYER_IDLE_TIMEOUT = timedelta(seconds=250)
_TEAM_ALIASES = {
    "T": "TERRORIST",
    "TS": "TERRORIST",
    "TERRORISTS": "TERRORIST",
    "COUNTERTERRORIST": "CT",
    "COUNTER-TERRORIST": "CT",
    "COUNTER TERRORIST": "CT",
    "CTS": "CT",
}
_SELECT_PLAYER_STATE_QUERY = (
    "SELECT `skill`, `kills`, `lastAddress`, `connection_time` "
    "FROM hlstats_Players WHERE `playerId` = %s LIMIT 1"
)
_INSERT_PLAYER_QUERY = "INSERT INTO hlstats_Players (`game`, `lastName`) VALUES (%s, %s)"
_LAST_INSERT_ID_QUERY = "SELECT LAST_INSERT_ID()"
_UPDATE_PLAYER_NAME_QUERY = "UPDATE hlstats_Players SET `lastName` = %s WHERE `playerId` = %s"
_UPDATE_PLAYER_LAST_ADDRESS_QUERY = "UPDATE hlstats_Players SET `lastAddress` = %s WHERE `playerId` = %s"
_UPSERT_PLAYER_NAME_QUERY = (
    "INSERT INTO hlstats_PlayerNames (`playerId`, `name`, `lastuse`, `numuses`) VALUES (%s, %s, %s, 1) "
    "ON DUPLICATE KEY UPDATE `lastuse` = VALUES(`lastuse`), `numuses` = `numuses` + 1"
)
_UPDATE_PLAYERNAME_LASTUSE_QUERY = (
    "UPDATE hlstats_PlayerNames SET `lastuse` = %s WHERE `playerId` = %s AND `name` = %s"
)
_UPDATE_PLAYERNAME_TOTALS_QUERY = (
    "UPDATE hlstats_PlayerNames "
    "SET `connection_time` = `connection_time` + %s, "
    "`kills` = `kills` + %s, "
    "`deaths` = `deaths` + %s, "
    "`suicides` = `suicides` + %s, "
    "`headshots` = `headshots` + %s, "
    "`shots` = `shots` + %s, "
    "`hits` = `hits` + %s "
    "WHERE `playerId` = %s AND `name` = %s"
)
_UPSERT_PLAYER_UNIQUE_QUERY = (
    "INSERT INTO hlstats_PlayerUniqueIds (`playerId`, `uniqueId`, `game`) VALUES (%s, %s, %s) "
    "ON DUPLICATE KEY UPDATE `playerId` = VALUES(`playerId`)"
)
_UPSERT_PLAYER_HISTORY_QUERY = (
    "INSERT INTO hlstats_Players_History (`playerId`, `eventTime`, `game`, `skill`) "
    "VALUES (%s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE `playerId` = `playerId`"
)
_SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY = (
    "SELECT `connection_time`, `kills`, `deaths`, `suicides`, `skill`, `headshots`, "
    "`shots`, `hits`, `teamkills`, `death_streak`, `kill_streak`, `skill_change` "
    "FROM hlstats_Players_History WHERE `playerId` = %s AND `eventTime` = %s AND `game` = %s LIMIT 1"
)
_REPLACE_PLAYER_HISTORY_SNAPSHOT_QUERY = (
    "UPDATE hlstats_Players_History "
    "SET `connection_time` = %s, "
    "`kills` = %s, "
    "`deaths` = %s, "
    "`suicides` = %s, "
    "`skill` = %s, "
    "`headshots` = %s, "
    "`shots` = %s, "
    "`hits` = %s, "
    "`teamkills` = %s, "
    "`death_streak` = %s, "
    "`kill_streak` = %s, "
    "`skill_change` = %s "
    "WHERE `playerId` = %s AND `eventTime` = %s AND `game` = %s"
)
_DELETE_PLAYER_HISTORY_QUERY = (
    "DELETE FROM hlstats_Players_History WHERE `playerId` = %s AND `eventTime` = %s AND `game` = %s"
)
_UPDATE_PLAYER_HISTORY_QUERY = (
    "UPDATE hlstats_Players_History "
    "SET `connection_time` = `connection_time` + %s, "
    "`kills` = `kills` + %s, "
    "`deaths` = `deaths` + %s, "
    "`suicides` = `suicides` + %s, "
    "`skill` = %s, "
    "`headshots` = `headshots` + %s, "
    "`shots` = `shots` + %s, "
    "`hits` = `hits` + %s, "
    "`teamkills` = `teamkills` + %s, "
    "`death_streak` = IF(%s > `death_streak`, %s, `death_streak`), "
    "`kill_streak` = IF(%s > `kill_streak`, %s, `kill_streak`), "
    "`skill_change` = `skill_change` + %s "
    "WHERE `playerId` = %s AND `eventTime` = %s AND `game` = %s"
)
_INSERT_FRAG_QUERY = (
    "INSERT INTO hlstats_Events_Frags ("
    "`eventTime`, `serverId`, `map`, `killerId`, `victimId`, `weapon`, `headshot`, "
    "`killerRole`, `victimRole`, `pos_x`, `pos_y`, `pos_z`, "
    "`pos_victim_x`, `pos_victim_y`, `pos_victim_z`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_SUICIDE_QUERY = (
    "INSERT INTO hlstats_Events_Suicides ("
    "`eventTime`, `serverId`, `map`, `playerId`, `weapon`, `pos_x`, `pos_y`, `pos_z`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_TEAMKILL_QUERY = (
    "INSERT INTO hlstats_Events_Teamkills ("
    "`eventTime`, `serverId`, `map`, `killerId`, `victimId`, `weapon`, "
    "`pos_x`, `pos_y`, `pos_z`, `pos_victim_x`, `pos_victim_y`, `pos_victim_z`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_UPDATE_PLAYER_KILLS_QUERY = (
    "UPDATE hlstats_Players SET `kills` = `kills` + %s, `headshots` = `headshots` + %s "
    "WHERE `playerId` = %s"
)
_UPDATE_PLAYER_DEATHS_QUERY = (
    "UPDATE hlstats_Players SET `deaths` = `deaths` + 1 WHERE `playerId` = %s"
)
_UPDATE_PLAYER_SUICIDES_QUERY = (
    "UPDATE hlstats_Players SET `suicides` = `suicides` + 1 WHERE `playerId` = %s"
)
_UPDATE_PLAYER_TEAMKILLS_QUERY = (
    "UPDATE hlstats_Players SET `teamkills` = `teamkills` + 1 WHERE `playerId` = %s"
)
_UPDATE_PLAYER_STREAKS_QUERY = (
    "UPDATE hlstats_Players "
    "SET `kill_streak` = IF(%s > `kill_streak`, %s, `kill_streak`), "
    "`death_streak` = IF(%s > `death_streak`, %s, `death_streak`) "
    "WHERE `playerId` = %s"
)
_UPDATE_PLAYER_FRAG_ROLLUP_QUERY = (
    "UPDATE hlstats_Players SET "
    "`kills` = `kills` + %s, "
    "`headshots` = `headshots` + %s, "
    "`deaths` = `deaths` + %s, "
    "`suicides` = `suicides` + %s, "
    "`skill` = `skill` + %s, "
    "`kill_streak` = IF(%s > `kill_streak`, %s, `kill_streak`), "
    "`death_streak` = IF(%s > `death_streak`, %s, `death_streak`) "
    "WHERE `playerId` = %s"
)
_UPSERT_WEAPON_QUERY = (
    "INSERT INTO hlstats_Weapons (`game`, `code`, `name`, `modifier`, `kills`, `headshots`) "
    "VALUES (%s, %s, %s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE "
    "`kills` = `kills` + VALUES(`kills`), "
    "`headshots` = `headshots` + VALUES(`headshots`), "
    "`name` = VALUES(`name`)"
)
_SELECT_WEAPON_MODIFIER_QUERY = (
    "SELECT `modifier` FROM hlstats_Weapons WHERE `game` = %s AND `code` = %s LIMIT 1"
)
_SELECT_ACTION_QUERY = (
    "SELECT `id`, `reward_player`, `reward_team`, `team` FROM hlstats_Actions "
    "WHERE `game` = %s AND `code` = %s LIMIT 1"
)
_SELECT_OPTION_QUERY = "SELECT `value` FROM hlstats_Options WHERE `keyname` = %s LIMIT 1"
_SELECT_SERVER_CONFIG_QUERY = (
    "SELECT `value` FROM hlstats_Servers_Config WHERE `serverId` = %s AND `parameter` = %s LIMIT 1"
)
_SELECT_DEFAULT_SERVER_CONFIG_QUERY = (
    "SELECT `value` FROM hlstats_Servers_Config_Default WHERE `parameter` = %s LIMIT 1"
)
_SELECT_PLAYER_BOT_UNIQUE_QUERY = (
    "SELECT 1 FROM hlstats_PlayerUniqueIds "
    "WHERE `playerId` = %s "
    "AND (`uniqueId` = 'BOT' OR `uniqueId` LIKE 'BOT:%%' OR `uniqueId` = '0' OR `uniqueId` LIKE '00000000:%%:0') "
    "LIMIT 1"
)
_INSERT_ACTION_QUERY = (
    "INSERT INTO hlstats_Actions ("
    "`game`, `code`, `description`, `reward_player`, `reward_team`, `team`) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_INCREMENT_ACTION_COUNT_QUERY = (
    "UPDATE hlstats_Actions SET `count` = `count` + 1 WHERE `id` = %s"
)
_INSERT_PLAYER_ACTION_QUERY = (
    "INSERT INTO hlstats_Events_PlayerActions ("
    "`eventTime`, `serverId`, `map`, `playerId`, `actionId`, `bonus`) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_INSERT_TEAM_BONUS_QUERY = (
    "INSERT INTO hlstats_Events_TeamBonuses ("
    "`eventTime`, `serverId`, `map`, `playerId`, `actionId`, `bonus`) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_INSERT_PLAYER_PLAYER_ACTION_QUERY = (
    "INSERT INTO hlstats_Events_PlayerPlayerActions ("
    "`eventTime`, `serverId`, `map`, `playerId`, `victimId`, `actionId`, `bonus`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_ENTRY_QUERY = (
    "INSERT INTO hlstats_Events_Entries ("
    "`eventTime`, `serverId`, `map`, `playerId`) "
    "VALUES (%s, %s, %s, %s)"
)
_UPDATE_PLAYER_SKILL_QUERY = (
    "UPDATE hlstats_Players SET `skill` = `skill` + %s WHERE `playerId` = %s"
)
_UPDATE_PLAYER_SHOTS_HITS_QUERY = (
    "UPDATE hlstats_Players SET `shots` = `shots` + %s, `hits` = `hits` + %s WHERE `playerId` = %s"
)
_UPDATE_PLAYERNAME_SHOTS_HITS_QUERY = (
    "UPDATE hlstats_PlayerNames "
    "SET `shots` = `shots` + %s, `hits` = `hits` + %s "
    "WHERE `playerId` = %s AND `name` = %s"
)
_INSERT_CHAT_QUERY = (
    "INSERT INTO hlstats_Events_Chat ("
    "`eventTime`, `serverId`, `map`, `playerId`, `message_mode`, `message`) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_INSERT_STATSME_QUERY = (
    "INSERT INTO hlstats_Events_Statsme ("
    "`eventTime`, `serverId`, `map`, `playerId`, `weapon`, `shots`, `hits`, "
    "`headshots`, `damage`, `kills`, `deaths`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_STATSME2_QUERY = (
    "INSERT INTO hlstats_Events_Statsme2 ("
    "`eventTime`, `serverId`, `map`, `playerId`, `weapon`, `head`, `chest`, "
    "`stomach`, `leftarm`, `rightarm`, `leftleg`, `rightleg`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_TEAM_CHANGE_QUERY = (
    "INSERT INTO hlstats_Events_ChangeTeam ("
    "`eventTime`, `serverId`, `map`, `playerId`, `team`) "
    "VALUES (%s, %s, %s, %s, %s)"
)
_INSERT_CONNECT_QUERY = (
    "INSERT INTO hlstats_Events_Connects ("
    "`eventTime`, `serverId`, `map`, `playerId`, `ipAddress`, `hostname`, `hostgroup`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_DISCONNECT_QUERY = (
    "INSERT INTO hlstats_Events_Disconnects ("
    "`eventTime`, `serverId`, `map`, `playerId`) "
    "VALUES (%s, %s, %s, %s)"
)
_INSERT_ADMIN_EVENT_QUERY = (
    "INSERT INTO hlstats_Events_Admin ("
    "`eventTime`, `serverId`, `map`, `type`, `message`, `playerName`) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_UPDATE_SERVER_PLAYER_TOTALS_QUERY = (
    "UPDATE hlstats_Servers "
    "SET `players` = %s, `act_players` = %s "
    "WHERE `serverId` = %s"
)
_FINALIZE_PLAYER_LAST_EVENT_QUERY = "UPDATE hlstats_Players SET `last_event` = UNIX_TIMESTAMP()"
_UPDATE_SERVER_FRAG_TOTALS_QUERY = (
    "UPDATE hlstats_Servers "
    "SET `kills` = `kills` + %s, `headshots` = `headshots` + %s "
    "WHERE `serverId` = %s"
)
_UPDATE_SERVER_CT_SHOTS_HITS_QUERY = (
    "UPDATE hlstats_Servers "
    "SET `ct_shots` = `ct_shots` + %s, `ct_hits` = `ct_hits` + %s, "
    "`map_ct_shots` = `map_ct_shots` + %s, `map_ct_hits` = `map_ct_hits` + %s "
    "WHERE `serverId` = %s"
)
_UPDATE_SERVER_TS_SHOTS_HITS_QUERY = (
    "UPDATE hlstats_Servers "
    "SET `ts_shots` = `ts_shots` + %s, `ts_hits` = `ts_hits` + %s, "
    "`map_ts_shots` = `map_ts_shots` + %s, `map_ts_hits` = `map_ts_hits` + %s "
    "WHERE `serverId` = %s"
)
_UPDATE_SERVER_MAP_LOADING_QUERY = "UPDATE hlstats_Servers SET `act_map` = %s WHERE `serverId` = %s"
_UPDATE_SERVER_MAP_STARTED_QUERY = (
    "UPDATE hlstats_Servers SET "
    "`act_map` = %s, "
    "`map_changes` = `map_changes` + 1, "
    "`map_rounds` = 0, "
    "`map_ct_wins` = 0, "
    "`map_ts_wins` = 0, "
    "`map_ct_shots` = 0, "
    "`map_ct_hits` = 0, "
    "`map_ts_shots` = 0, "
    "`map_ts_hits` = 0, "
    "`map_started` = %s "
    "WHERE `serverId` = %s"
)
_UPSERT_MAP_COUNTS_QUERY = (
    "INSERT INTO hlstats_Maps_Counts (`game`, `map`, `kills`, `headshots`) "
    "VALUES (%s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE "
    "`kills` = `kills` + VALUES(`kills`), "
    "`headshots` = `headshots` + VALUES(`headshots`)"
)
_APPEND_ONLY_EVENT_INSERT_QUERIES = {
    _INSERT_FRAG_QUERY,
    _INSERT_SUICIDE_QUERY,
    _INSERT_TEAMKILL_QUERY,
    _INSERT_PLAYER_ACTION_QUERY,
    _INSERT_TEAM_BONUS_QUERY,
    _INSERT_PLAYER_PLAYER_ACTION_QUERY,
    _INSERT_ENTRY_QUERY,
    _INSERT_CHAT_QUERY,
    _INSERT_STATSME_QUERY,
    _INSERT_STATSME2_QUERY,
    _INSERT_TEAM_CHANGE_QUERY,
    _INSERT_CONNECT_QUERY,
    _INSERT_DISCONNECT_QUERY,
    _INSERT_ADMIN_EVENT_QUERY,
}


@dataclass(frozen=True, slots=True)
class _PlayerCacheKey:
    scope: str
    identifier: str
    user_id: Optional[int]


@dataclass(frozen=True, slots=True)
class _ActionMetadata:
    action_id: int
    reward_player: int
    reward_team: int
    team: str = ""


class EventStorage:
    """Translate :class:`EventUpdate` objects into SQL statements."""

    def __init__(
        self,
        adapter: SupportsConnectionProvider,
        *,
        clock: Callable[[], datetime] | None = None,
        use_event_timestamps_for_processing: bool = False,
    ) -> None:
        self._adapter = adapter
        self._clock = clock or (lambda: datetime.now().replace(microsecond=0))
        self._use_event_timestamps_for_processing = use_event_timestamps_for_processing
        self._player_cache: dict[_PlayerCacheKey, int] = {}
        self._action_cache: dict[tuple[str, str], _ActionMetadata] = {}
        self._player_teams: dict[int, str] = {}
        self._player_names: dict[int, str] = {}
        self._player_name_uses: set[tuple[int, str]] = set()
        self._player_name_lastuse: dict[tuple[int, str], datetime] = {}
        self._server_players: dict[int, set[int]] = {}
        self._server_connected_players: dict[int, set[int]] = {}
        self._server_active_players: dict[int, set[int]] = {}
        self._server_reward_eligible_players: dict[int, set[int]] = {}
        self._server_player_last_activity: dict[int, dict[int, datetime]] = {}
        self._server_skill_modes: dict[int, int] = {}
        self._server_min_players: dict[int, int] = {}
        self._server_ignore_bots: dict[int, int] = {}
        self._server_tk_penalties: dict[int, int] = {}
        self._option_cache: dict[str, int] = {}
        self._player_is_bot: dict[int, bool] = {}
        self._player_is_bot_cache: dict[tuple[int, str], bool] = {}
        self._player_last_user_id: dict[int, int] = {}
        self._weapon_modifiers: dict[tuple[str, str], float] = {}
        self._player_kill_streaks: dict[int, int] = {}
        self._player_death_streaks: dict[int, int] = {}
        self._player_max_kill_streaks: dict[int, int] = {}
        self._player_max_death_streaks: dict[int, int] = {}
        self._player_kills_per_life: dict[int, int] = {}
        self._player_deaths_in_a_row: dict[int, int] = {}
        self._player_skills: dict[int, int] = {}
        self._player_total_kills: dict[int, int] = {}
        self._seen_team_change_events: set[tuple[int, int, str, str, datetime]] = set()
        self._seen_team_bonus_events: set[tuple[int, int, int, datetime]] = set()
        self._server_totals_dirty: set[int] = set()
        self._transaction_batch_size = 0
        self._pending_writes = 0
        self._pending_records = 0
        self._cached_cursor: proxy_db.SupportsCursor | None = None
        self._cached_cursor_connection: proxy_db.SupportsConnection | None = None
        self._event_buffer: EventBuffer | None = None
        self._frag_write_deltas: FragWriteDeltaBuffer | None = None
        self._team_bonus_stage_counts: dict[str, int] = {}
        self._team_bonus_stage_action_counts: dict[str, dict[int, int]] = {}
        self._team_bonus_stage_map_counts: dict[str, dict[str, int]] = {}
        self._team_bonus_stage_player_counts: dict[str, dict[int, int]] = {}
        self._team_bonus_stage_samples: list[dict[str, Any]] = []

    def _set_skip_adapter_ping(self, enabled: bool) -> None:
        setter = getattr(self._adapter, "set_skip_connection_ping", None)
        if callable(setter):
            setter(enabled)

    def begin_stdin_batch(self, *, transaction_batch_size: int) -> None:
        """Enable batched transaction mode for high-volume stdin imports."""
        if transaction_batch_size <= 0:
            self._transaction_batch_size = 0
            self._pending_writes = 0
            self._pending_records = 0
            self._event_buffer = None
            self._frag_write_deltas = None
            self._set_skip_adapter_ping(False)
            return
        self._transaction_batch_size = transaction_batch_size
        self._pending_writes = 0
        self._pending_records = 0
        self._set_autocommit(False)
        self._set_skip_adapter_ping(True)
        self._event_buffer = EventBuffer(policy=BufferPolicy(max_buffered_events=5000))
        self._frag_write_deltas = FragWriteDeltaBuffer()

    def configure_event_buffer(self, *, max_buffered_events: int) -> None:
        if max_buffered_events <= 0:
            self._event_buffer = None
            return
        self._event_buffer = EventBuffer(policy=BufferPolicy(max_buffered_events=max_buffered_events))

    def end_stdin_batch(self) -> None:
        """Flush pending writes and restore autocommit after stdin import."""
        if self._transaction_batch_size <= 0:
            self._flush_event_buffer()
            self._flush_frag_counter_buffer()
            self._event_buffer = None
            self._set_skip_adapter_ping(False)
            return
        self._flush_event_buffer()
        self._flush_frag_counter_buffer()
        self._commit_pending(force=True)
        self._transaction_batch_size = 0
        self._pending_writes = 0
        self._pending_records = 0
        self._set_autocommit(True)
        self._close_cached_cursor()
        self._event_buffer = None
        self._frag_write_deltas = None
        self._set_skip_adapter_ping(False)

    def reset_runtime_state(self) -> None:
        """Drop replay/session-local caches after a runtime reload."""

        self._player_cache.clear()
        self._player_teams.clear()
        self._player_names.clear()
        self._player_name_uses.clear()
        self._player_name_lastuse.clear()
        self._server_players.clear()
        self._server_connected_players.clear()
        self._server_active_players.clear()
        self._server_reward_eligible_players.clear()
        self._server_player_last_activity.clear()
        self._server_skill_modes.clear()
        self._server_min_players.clear()
        self._server_ignore_bots.clear()
        self._server_tk_penalties.clear()
        self._option_cache.clear()
        self._player_is_bot.clear()
        self._player_is_bot_cache.clear()
        self._player_last_user_id.clear()
        self._weapon_modifiers.clear()
        self._player_kill_streaks.clear()
        self._player_death_streaks.clear()
        self._player_max_kill_streaks.clear()
        self._player_max_death_streaks.clear()
        self._player_kills_per_life.clear()
        self._player_deaths_in_a_row.clear()
        self._player_skills.clear()
        self._player_total_kills.clear()
        self._seen_team_change_events.clear()
        self._seen_team_bonus_events.clear()
        self._server_totals_dirty.clear()

    def finalize_import(self) -> None:
        """Apply import-tail updates after a finite stdin replay."""

        connection = self._connection()
        self._flush_event_buffer()
        self._flush_frag_counter_buffer()
        self._execute(connection, _FINALIZE_PLAYER_LAST_EVENT_QUERY, None)
        self._maybe_commit_batch()
        self._write_team_bonus_stage_trace()

    def flush_pending(self) -> None:
        """Flush buffered inserts and commit pending batched writes."""
        self._flush_event_buffer()
        self._flush_frag_counter_buffer()
        self._commit_pending()

    def apply_server_map_transition(
        self, server_id: int, phase: str, map_name: str, event_timestamp: datetime
    ) -> None:
        """Update ``hlstats_Servers`` for ``Loading map`` / ``Started map`` (Perl ``doEvent_ChangeMap``)."""

        connection = self._connection()
        if phase == "loading":
            self._execute(connection, _UPDATE_SERVER_MAP_LOADING_QUERY, (map_name, server_id))
            return
        if phase == "started":
            normalized = self._normalize_timestamp(event_timestamp)
            started_unix = int(timegm(normalized.timetuple()))
            self._execute(
                connection,
                _UPDATE_SERVER_MAP_STARTED_QUERY,
                (map_name, started_unix, server_id),
            )
            # Align with legacy lifecycle semantics: a new started map resets
            # in-memory active/trackable roster until fresh team/connect/entry data arrives.
            stale_players = set(self._server_active_players.get(server_id, set()))
            stale_players.update(self._server_connected_players.get(server_id, set()))
            stale_players.update(self._server_reward_eligible_players.get(server_id, set()))
            self._server_active_players[server_id] = set()
            self._server_connected_players[server_id] = set()
            self._server_reward_eligible_players[server_id] = set()
            self._server_player_last_activity[server_id] = {}
            for player_id in stale_players:
                self._player_teams.pop(player_id, None)
            self._server_totals_dirty.add(server_id)
            return
        raise ValueError(f"unsupported map lifecycle phase: {phase!r}")

    def record(self, update: EventUpdate, context: EventContext) -> None:
        """Persist *update* using metadata from *context*."""

        connection = self._connection()
        map_name = self._resolve_map(context)
        timestamp = self._normalize_timestamp(update.timestamp)
        processed_at = self._processing_timestamp(timestamp)
        self._prune_idle_players(context.server_id, timestamp)

        try:
            if update.category is EventCategory.WORLD:
                self._handle_world_state(connection, update, context, map_name, timestamp, processed_at)
                self._record_world_action(connection, update, context, map_name, timestamp)
                return

            if update.category in {
                EventCategory.FRAG,
                EventCategory.ACTION,
                EventCategory.STATSME,
                EventCategory.STATSME2,
            }:
                self._prime_player_state(connection, update, context, timestamp, processed_at)

            if (
                update.category in {
                    EventCategory.FRAG,
                    EventCategory.ACTION,
                    EventCategory.STATSME,
                    EventCategory.STATSME2,
                    EventCategory.TEAM_BONUS,
                }
                and self._active_trackable_players_for_gate(connection, context.server_id)
                < self._server_min_players_required(connection, context.server_id)
            ):
                return

            if update.category is EventCategory.FRAG:
                self._record_frag(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.ACTION:
                self._record_action(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.STATSME:
                self._record_statsme(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.STATSME2:
                self._record_statsme2(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.CHAT:
                self._record_chat(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.TEAM:
                self._record_team_change(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.TEAM_BONUS:
                self._record_team_bonus(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.CONNECTION:
                self._record_connection(connection, update, context, map_name, timestamp, processed_at)
            elif update.category is EventCategory.ENTRY:
                self._record_entry(connection, update, context, map_name, timestamp, processed_at)
            else:
                self._record_generic(connection, update, context, map_name, timestamp)
        except Exception as exc:  # pragma: no cover - safety net
            self._rollback_pending()
            raise StorageError(str(exc)) from exc
        if self._transaction_batch_size > 0:
            self._pending_records += 1
        self._maybe_commit_batch()

    # ------------------------------------------------------------------
    # Recording helpers

    def _record_frag(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        killer_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        victim_descriptor = update.target if update.target is not None else update.actor
        victim_id = self._resolve_player_id(connection, victim_descriptor, context, timestamp, processed_at)

        headshot = 1 if update.attributes.get("headshot") else 0
        killer_role = self._extract_role(update.actor)
        victim_role = self._extract_role(update.target)
        properties = update.attributes.get("properties")
        attacker_position = self._parse_position(
            properties.get("attacker_position") if isinstance(properties, Mapping) else None
        )
        victim_position = self._parse_position(
            properties.get("victim_position") if isinstance(properties, Mapping) else None
        )
        is_suicide = bool(update.attributes.get("is_suicide"))
        if killer_id is not None and victim_id is not None and killer_id == victim_id:
            is_suicide = True

        if is_suicide and victim_id:
            self._record_suicide(
                connection,
                context=context,
                map_name=map_name,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=victim_id,
                weapon_code=update.event_code,
                position=attacker_position,
            )
            return

        if headshot:
            attacker_position = (None, None, None)

        killer_team = self._effective_player_team(killer_id, update.actor)
        victim_team = self._effective_player_team(victim_id, update.target)
        is_teamkill = (
            killer_id is not None
            and victim_id is not None
            and killer_id != victim_id
            and killer_team != ""
            and killer_team == victim_team
        )

        if is_teamkill:
            self._record_teamkill(
                connection,
                context=context,
                map_name=map_name,
                timestamp=timestamp,
                processed_at=processed_at,
                killer_id=killer_id,
                victim_id=victim_id,
                weapon_code=update.event_code,
                weapon_name=str(update.attributes.get("weapon_name") or update.event_code),
                headshot=headshot,
                attacker_position=attacker_position,
                victim_position=victim_position,
            )
            return

        params = (
            timestamp,
            context.server_id,
            map_name,
            killer_id or 0,
            victim_id or 0,
            update.event_code,
            headshot,
            killer_role,
            victim_role,
            attacker_position[0],
            attacker_position[1],
            attacker_position[2],
            victim_position[0],
            victim_position[1],
            victim_position[2],
        )
        self._execute(connection, _INSERT_FRAG_QUERY, params)

        weapon_name = update.attributes.get("weapon_name") or update.event_code
        self._execute(
            connection,
            _UPSERT_WEAPON_QUERY,
            (context.game, update.event_code, weapon_name, 1.0, 1, headshot),
        )
        self._execute(
            connection,
            _UPDATE_SERVER_FRAG_TOTALS_QUERY,
            (1, headshot, context.server_id),
        )
        self._execute(
            connection,
            _UPSERT_MAP_COUNTS_QUERY,
            (context.game, map_name, 1, headshot),
        )

        if killer_id and victim_id and killer_id != victim_id:
            self._player_kills_per_life[killer_id] = self._player_kills_per_life.get(killer_id, 0) + 1
            self._player_total_kills[killer_id] = self._player_total_kills.get(killer_id, 0) + 1
            self._player_deaths_in_a_row[victim_id] = self._player_deaths_in_a_row.get(victim_id, 0) + 1
            self._player_deaths_in_a_row[killer_id] = 0
            self._end_kill_streak(
                connection,
                context=context,
                map_name=map_name,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=victim_id,
            )
            killer_streak = self._set_player_streaks(connection, killer_id, kill_delta=1, reset_deaths=True)
            victim_streak = self._set_player_streaks(connection, victim_id, death_delta=1, reset_kills=True)
            killer_skill_delta, victim_skill_delta = self._calculate_frag_skill_deltas(
                connection,
                context=context,
                weapon_code=update.event_code,
                killer_id=killer_id,
                victim_id=victim_id,
            )
            self._apply_frag_player_rollup(
                connection,
                player_id=killer_id,
                kills=1,
                headshots=headshot,
                skill_delta=killer_skill_delta,
            )
            self._apply_frag_player_rollup(
                connection,
                player_id=victim_id,
                deaths=1,
                skill_delta=victim_skill_delta,
            )

            self._update_player_rollups(
                connection,
                context=context,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=killer_id,
                kills=1,
                headshots=headshot,
                skill_delta=killer_skill_delta,
                kill_streak=self._player_max_kill_streaks.get(killer_id, killer_streak),
            )
            self._update_player_rollups(
                connection,
                context=context,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=victim_id,
                deaths=1,
                skill_delta=victim_skill_delta,
                death_streak=self._player_max_death_streaks.get(victim_id, victim_streak),
            )

            if headshot:
                self._record_derived_player_action(
                    connection,
                    context=context,
                    map_name=map_name,
                    timestamp=timestamp,
                    processed_at=processed_at,
                    player_id=killer_id,
                    action_code="headshot",
                )
        elif victim_id:
            self._player_deaths_in_a_row[victim_id] = self._player_deaths_in_a_row.get(victim_id, 0) + 1
            self._end_kill_streak(
                connection,
                context=context,
                map_name=map_name,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=victim_id,
            )
            victim_streak = self._set_player_streaks(connection, victim_id, death_delta=1, reset_kills=True)
            self._apply_frag_player_rollup(
                connection,
                player_id=victim_id,
                deaths=1,
            )
            self._update_player_rollups(
                connection,
                context=context,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=victim_id,
                deaths=1,
                death_streak=self._player_max_death_streaks.get(victim_id, victim_streak),
            )

    def _record_suicide(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
        player_id: int,
        weapon_code: str,
        position: tuple[int | None, int | None, int | None],
    ) -> None:
        self._execute(
            connection,
            _INSERT_SUICIDE_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                player_id,
                weapon_code,
                position[0],
                position[1],
                position[2],
            ),
        )
        self._execute(connection, _UPDATE_PLAYER_SUICIDES_QUERY, (player_id,))
        self._update_player_rollups(
            connection,
            context=context,
            timestamp=timestamp,
            processed_at=processed_at,
            player_id=player_id,
            suicides=1,
        )

    def _record_action(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        victim_id = self._resolve_player_id(connection, update.target, context, timestamp, processed_at)
        action = self._ensure_action_metadata(connection, context.game, update)
        bonus = int(update.attributes.get("points") or action.reward_player)

        if victim_id:
            self._execute(
                connection,
                _INSERT_PLAYER_PLAYER_ACTION_QUERY,
                (
                    timestamp,
                    context.server_id,
                    map_name,
                    actor_id or 0,
                    victim_id,
                    action.action_id,
                    bonus,
                ),
            )
        else:
            self._execute(
                connection,
                _INSERT_PLAYER_ACTION_QUERY,
                (
                    timestamp,
                    context.server_id,
                    map_name,
                    actor_id or 0,
                    action.action_id,
                    bonus,
                ),
            )

        self._execute(connection, _INCREMENT_ACTION_COUNT_QUERY, (action.action_id,))
        if actor_id and bonus:
            self._apply_player_skill_delta(
                connection,
                context=context,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=actor_id,
                delta=bonus,
            )
        if action.reward_team:
            # Keep team-reward gating aligned with legacy behavior:
            # when round status is non-zero, rewardTeam should not emit rows.
            round_status = int((context.extras or {}).get("round_status") or 0)
            if round_status == 0:
                team = action.team or str(
                    update.attributes.get("team") or self._effective_player_team(actor_id, update.actor)
                )
                if team:
                    self._reward_team_players(
                        connection,
                        context=context,
                        map_name=map_name,
                        timestamp=timestamp,
                        processed_at=processed_at,
                        team=team,
                        action=action,
                        bonus=action.reward_team,
                        event_code=update.event_code,
                    )

    def _record_chat(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        team_only = 2 if update.attributes.get("team_only") else 1
        message = str(update.attributes.get("message", ""))
        self._execute(
            connection,
            _INSERT_CHAT_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                actor_id or 0,
                team_only,
                message,
            ),
        )

    def _record_statsme(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        if actor_id is None:
            return

        shots = int(update.attributes.get("shots") or 0)
        hits = int(update.attributes.get("hits") or 0)
        weapon_code = str(update.attributes.get("weapon_code") or update.event_code)
        self._execute(
            connection,
            _INSERT_STATSME_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                actor_id,
                weapon_code,
                shots,
                hits,
                int(update.attributes.get("headshots") or 0),
                int(update.attributes.get("damage") or 0),
                int(update.attributes.get("kills") or 0),
                int(update.attributes.get("deaths") or 0),
            ),
        )
        self._execute(connection, _UPDATE_PLAYER_SHOTS_HITS_QUERY, (shots, hits, actor_id))
        self._update_player_rollups(
            connection,
            context=context,
            timestamp=timestamp,
            processed_at=processed_at,
            player_id=actor_id,
            shots=shots,
            hits=hits,
        )
        player_team = self._effective_player_team(actor_id, update.actor)
        if player_team == "CT":
            self._execute(
                connection,
                _UPDATE_SERVER_CT_SHOTS_HITS_QUERY,
                (shots, hits, shots, hits, context.server_id),
            )
        elif player_team == "TERRORIST":
            self._execute(
                connection,
                _UPDATE_SERVER_TS_SHOTS_HITS_QUERY,
                (shots, hits, shots, hits, context.server_id),
            )

    def _record_statsme2(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        if actor_id is None:
            return

        weapon_code = str(update.attributes.get("weapon_code") or update.event_code)
        self._execute(
            connection,
            _INSERT_STATSME2_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                actor_id,
                weapon_code,
                int(update.attributes.get("head") or 0),
                int(update.attributes.get("chest") or 0),
                int(update.attributes.get("stomach") or 0),
                int(update.attributes.get("leftarm") or 0),
                int(update.attributes.get("rightarm") or 0),
                int(update.attributes.get("leftleg") or 0),
                int(update.attributes.get("rightleg") or 0),
            ),
        )

    def _record_team_change(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        if actor_id is None:
            return
        if self._player_is_bot.get(actor_id, False):
            return
        team = self._normalize_team_name(str(update.attributes.get("team", update.event_code)))
        dedupe_key = (context.server_id, actor_id, map_name, team, timestamp)
        if dedupe_key in self._seen_team_change_events:
            return
        self._seen_team_change_events.add(dedupe_key)
        self._execute(
            connection,
            _INSERT_TEAM_CHANGE_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                actor_id,
                team,
            ),
        )
        self._player_teams[actor_id] = team
        if self._update_player_presence(context.server_id, actor_id, team):
            self._server_totals_dirty.add(context.server_id)
            self._refresh_server_player_totals_if_dirty(connection, context.server_id)

    def _record_team_bonus(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        row = self._fetchone(
            connection,
            _SELECT_ACTION_QUERY,
            (context.game, update.event_code),
        )
        if row:
            action = _ActionMetadata(
                action_id=int(row[0]),
                reward_player=int(row[1] or 0),
                reward_team=int(row[2] or 0),
                team=str(row[3] or "") if len(row) > 3 else "",
            )
            self._action_cache[(context.game, update.event_code)] = action
        else:
            if not update.attributes.get("team_award") and not int(update.attributes.get("points") or 0):
                return
            action = self._ensure_action_metadata(connection, context.game, update)
        team = self._normalize_team_name(action.team or str(update.attributes.get("team") or ""))
        bonus = int(update.attributes.get("points") or action.reward_team)
        self._execute(connection, _INCREMENT_ACTION_COUNT_QUERY, (action.action_id,))

        round_status = int((context.extras or {}).get("round_status") or 0)
        if round_status != 0:
            return
        if not team or bonus == 0:
            return

        self._reward_team_players(
            connection,
            context=context,
            map_name=map_name,
            timestamp=timestamp,
            processed_at=processed_at,
            team=team,
            action=action,
            bonus=bonus,
            event_code=update.event_code,
        )

    def _record_connection(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        if update.event_code == "connect":
            address = str(update.attributes.get("address") or "")
            self._execute(
                connection,
                _INSERT_CONNECT_QUERY,
                (
                    timestamp,
                    context.server_id,
                    map_name,
                    actor_id or 0,
                    address,
                    "",
                    "",
                ),
            )
            if actor_id and address:
                self._execute(
                    connection,
                    _UPDATE_PLAYER_LAST_ADDRESS_QUERY,
                    (address, actor_id),
                )
            self._refresh_server_player_totals_if_dirty(connection, context.server_id)
        else:
            self._execute(
                connection,
                _INSERT_DISCONNECT_QUERY,
                (timestamp, context.server_id, map_name, actor_id or 0),
            )
            if actor_id:
                self._realign_player_history_day(
                    connection,
                    context=context,
                    player_id=actor_id,
                    event_timestamp=timestamp,
                    processed_at=processed_at,
                )
                self._server_active_players.setdefault(context.server_id, set()).discard(actor_id)
                self._server_connected_players.setdefault(context.server_id, set()).discard(actor_id)
                self._server_reward_eligible_players.setdefault(context.server_id, set()).discard(actor_id)
                self._server_player_last_activity.setdefault(context.server_id, {}).pop(actor_id, None)
                self._server_totals_dirty.add(context.server_id)
                self._refresh_server_player_totals(connection, context.server_id)

    def _record_entry(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp, processed_at)
        if actor_id is None or self._player_is_bot.get(actor_id, False):
            return
        self._execute(
            connection,
            _INSERT_ENTRY_QUERY,
            (timestamp, context.server_id, map_name, actor_id),
        )
        self._server_reward_eligible_players.setdefault(context.server_id, set()).add(actor_id)

    def _record_world_action(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        # Legacy replay does not persist standalone world rows such as
        # Round_Start / Round_End into the statistical event tables.
        return

    def _record_generic(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        message = str(update.attributes.get("message", update.message or ""))
        actor_name = update.actor.name if update.actor else ""
        self._execute(
            connection,
            _INSERT_ADMIN_EVENT_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                update.event_code,
                message,
                actor_name,
            ),
        )

    def _prime_player_state(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        descriptors: list[PlayerDescriptor] = []
        if update.actor is not None:
            descriptors.append(update.actor)
        if update.target is not None:
            descriptors.append(update.target)

        seen: set[_PlayerCacheKey] = set()
        for descriptor in descriptors:
            cache_key = self._cache_key_for_player(context.game, descriptor)
            if cache_key in seen:
                continue
            seen.add(cache_key)
            self._resolve_player_id(connection, descriptor, context, timestamp, processed_at)

    # ------------------------------------------------------------------
    # Resolution helpers

    def _canonical_unique_id(self, unique_id: str) -> str:
        return _STEAM_PREFIX_RE.sub("", unique_id.strip())

    def _resolve_player_id(
        self,
        connection: proxy_db.SupportsConnection,
        descriptor: Optional[PlayerDescriptor],
        context: EventContext,
        timestamp: datetime,
        processed_at: datetime,
    ) -> Optional[int]:
        if descriptor is None:
            return None
        if not (descriptor.unique_id or descriptor.name.strip()):
            # Ignore unresolved empty descriptors to avoid creating phantom
            # players that later shift real player ids in TeamBonuses parity.
            return None

        cache_key = self._cache_key_for_player(context.game, descriptor)
        player_id = self._player_cache.get(cache_key)
        if player_id is None:
            player_id = self._lookup_player(connection, descriptor, context.game)
            if player_id is None:
                player_id = self._create_player(connection, descriptor, context.game)
                if descriptor.unique_id:
                    normalized_unique = self._canonical_unique_id(descriptor.unique_id)
                    self._execute(
                        connection,
                        _UPSERT_PLAYER_UNIQUE_QUERY,
                        (player_id, normalized_unique, context.game),
                    )
                self._touch_player_profile(
                    connection,
                    player_id,
                    descriptor,
                    track_name_history=True,
                )
            else:
                self._touch_player_profile(
                    connection,
                    player_id,
                    descriptor,
                    track_name_history=False,
                )
            self._player_cache[cache_key] = player_id
            tracked_players = self._server_players.setdefault(context.server_id, set())
            connected_players = self._server_connected_players.setdefault(context.server_id, set())
            if player_id not in tracked_players:
                tracked_players.add(player_id)
                self._server_totals_dirty.add(context.server_id)
            if player_id not in connected_players:
                connected_players.add(player_id)
                self._server_totals_dirty.add(context.server_id)
        self._player_is_bot[player_id] = self._player_is_bot.get(player_id, False) or self._is_bot_descriptor(
            descriptor
        )
        if descriptor.user_id is not None:
            self._player_last_user_id[player_id] = int(descriptor.user_id)
        self._server_player_last_activity.setdefault(context.server_id, {})[player_id] = timestamp

        normalized_team = self._normalize_team_name(descriptor.team)
        if normalized_team:
            self._player_teams[player_id] = normalized_team
            self._update_player_presence(context.server_id, player_id, normalized_team)
        if descriptor.name:
            self._player_names[player_id] = descriptor.name
            self._touch_player_name(connection, player_id, descriptor.name, processed_at)
        self._ensure_player_history_row(connection, context, player_id, timestamp)
        if self._history_timestamp(processed_at) != self._history_timestamp(timestamp):
            self._ensure_player_history_row(connection, context, player_id, processed_at)
        return player_id

    def _cache_key_for_player(self, game: str, descriptor: PlayerDescriptor) -> _PlayerCacheKey:
        if descriptor.unique_id:
            return _PlayerCacheKey("unique", descriptor.unique_id, None)
        key = f"{descriptor.name.lower()}::{descriptor.user_id}" if descriptor.user_id else descriptor.name.lower()
        return _PlayerCacheKey("name", f"{game}:{key}", descriptor.user_id)

    def _lookup_player(
        self,
        connection: proxy_db.SupportsConnection,
        descriptor: PlayerDescriptor,
        game: str,
    ) -> Optional[int]:
        if descriptor.unique_id:
            raw_unique = descriptor.unique_id
            canonical_unique = self._canonical_unique_id(raw_unique)
            candidates = [raw_unique]
            if canonical_unique != raw_unique:
                candidates.append(canonical_unique)
            for candidate in candidates:
                row = self._fetchone(
                    connection,
                    _PLAYER_BY_UNIQUE_QUERY,
                    (candidate, game),
                )
                if row:
                    return int(row[0])
        # Name-only fallback causes cross-player merges on common nicknames.
        # Keep strict identity: only unique_id can resolve an existing player.
        return None

    def _create_player(
        self,
        connection: proxy_db.SupportsConnection,
        descriptor: PlayerDescriptor,
        game: str,
    ) -> int:
        self._execute(connection, _INSERT_PLAYER_QUERY, (game, descriptor.name))
        row = self._fetchone(connection, _LAST_INSERT_ID_QUERY, None)
        if not row:
            raise StorageError("Failed to create player record")
        return int(row[0])

    def _touch_player_profile(
        self,
        connection: proxy_db.SupportsConnection,
        player_id: int,
        descriptor: PlayerDescriptor,
        *,
        track_name_history: bool,
    ) -> None:
        if self._player_names.get(player_id) != descriptor.name:
            self._execute(connection, _UPDATE_PLAYER_NAME_QUERY, (descriptor.name, player_id))
        self._player_names[player_id] = descriptor.name
        if player_id not in self._player_skills or player_id not in self._player_total_kills:
            row = self._fetchone(connection, _SELECT_PLAYER_STATE_QUERY, (player_id,))
            if row:
                self._player_skills[player_id] = int(row[0] or 1000)
                self._player_total_kills[player_id] = int(row[1] or 0)
            else:
                self._player_skills.setdefault(player_id, 1000)
                self._player_total_kills.setdefault(player_id, 0)
        self._player_max_kill_streaks.setdefault(player_id, 0)
        self._player_max_death_streaks.setdefault(player_id, 0)
        self._player_kills_per_life.setdefault(player_id, 0)
        self._player_deaths_in_a_row.setdefault(player_id, 0)

    def _touch_player_name(
        self,
        connection: proxy_db.SupportsConnection,
        player_id: int,
        player_name: str,
        processed_at: datetime,
    ) -> None:
        key = (player_id, player_name)
        last_use = self._player_name_lastuse.get(key)
        if last_use is not None and (processed_at - last_use).total_seconds() < 1:
            return
        if key not in self._player_name_uses:
            self._execute(connection, _UPSERT_PLAYER_NAME_QUERY, (player_id, player_name, processed_at))
            self._player_name_uses.add(key)
            self._player_name_lastuse[key] = processed_at
            return

        self._execute(
            connection,
            _UPDATE_PLAYERNAME_LASTUSE_QUERY,
            (processed_at, player_id, player_name),
        )
        self._player_name_lastuse[key] = processed_at

    def _ensure_action_metadata(
        self,
        connection: proxy_db.SupportsConnection,
        game: str,
        update: EventUpdate,
    ) -> _ActionMetadata:
        cache_key = (game, update.event_code)
        cached = self._action_cache.get(cache_key)
        if cached is not None:
            return cached

        row = self._fetchone(
            connection,
            _SELECT_ACTION_QUERY,
            (game, update.event_code),
        )
        if row:
            action = _ActionMetadata(
                action_id=int(row[0]),
                reward_player=int(row[1] or 0),
                reward_team=int(row[2] or 0),
                team=str(row[3] or "") if len(row) > 3 else "",
            )
        else:
            description = update.attributes.get("description") or update.event_code
            reward_player = int(update.attributes.get("points") or 0)
            reward_team = 1 if update.attributes.get("team_award") else 0
            team = str(update.attributes.get("team") or "")
            self._execute(
                connection,
                _INSERT_ACTION_QUERY,
                (game, update.event_code, description, reward_player, reward_team, team),
            )
            row = self._fetchone(connection, _LAST_INSERT_ID_QUERY, None)
            if not row:
                raise StorageError("Failed to create action definition")
            action = _ActionMetadata(
                action_id=int(row[0]),
                reward_player=reward_player,
                reward_team=reward_team,
                team=team,
            )
        self._action_cache[cache_key] = action
        return action

    def _effective_player_team(
        self,
        player_id: int | None,
        descriptor: Optional[PlayerDescriptor],
    ) -> str:
        if descriptor and descriptor.team:
            return descriptor.team
        if player_id is None:
            return ""
        return self._player_teams.get(player_id, "")

    def _option_int(
        self,
        connection: proxy_db.SupportsConnection,
        key: str,
        *,
        default: int,
    ) -> int:
        cached = self._option_cache.get(key)
        if cached is not None:
            return cached
        row = self._fetchone(connection, _SELECT_OPTION_QUERY, (key,))
        value = int(row[0]) if row and row[0] is not None else default
        self._option_cache[key] = value
        return value

    def _server_skill_mode(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> int:
        cached = self._server_skill_modes.get(server_id)
        if cached is not None:
            return cached
        row = self._fetchone(connection, _SELECT_SERVER_CONFIG_QUERY, (server_id, "SkillMode"))
        if row and row[0] is not None:
            value = int(row[0])
        else:
            default_row = self._fetchone(connection, _SELECT_DEFAULT_SERVER_CONFIG_QUERY, ("SkillMode",))
            value = int(default_row[0]) if default_row and default_row[0] is not None else 0
        self._server_skill_modes[server_id] = value
        return value

    def _server_min_players_required(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> int:
        cached = self._server_min_players.get(server_id)
        if cached is not None:
            return cached
        row = self._fetchone(connection, _SELECT_SERVER_CONFIG_QUERY, (server_id, "MinPlayers"))
        if row and row[0] is not None:
            value = int(row[0])
        else:
            default_row = self._fetchone(connection, _SELECT_DEFAULT_SERVER_CONFIG_QUERY, ("MinPlayers",))
            value = int(default_row[0]) if default_row and default_row[0] is not None else 0
        self._server_min_players[server_id] = value
        return value

    def _server_tk_penalty(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> int:
        cached = self._server_tk_penalties.get(server_id)
        if cached is not None:
            return cached
        row = self._fetchone(connection, _SELECT_SERVER_CONFIG_QUERY, (server_id, "TKPenalty"))
        if row and row[0] is not None:
            value = int(row[0])
        else:
            default_row = self._fetchone(connection, _SELECT_DEFAULT_SERVER_CONFIG_QUERY, ("TKPenalty",))
            value = int(default_row[0]) if default_row and default_row[0] is not None else 50
        self._server_tk_penalties[server_id] = value
        return value

    def _weapon_modifier(
        self,
        connection: proxy_db.SupportsConnection,
        game: str,
        weapon_code: str,
    ) -> float:
        cache_key = (game, weapon_code)
        cached = self._weapon_modifiers.get(cache_key)
        if cached is not None:
            return cached
        row = self._fetchone(connection, _SELECT_WEAPON_MODIFIER_QUERY, (game, weapon_code))
        value = float(row[0]) if row and row[0] is not None else 1.0
        self._weapon_modifiers[cache_key] = value
        return value

    def _set_player_streaks(
        self,
        connection: proxy_db.SupportsConnection,
        player_id: int,
        *,
        kill_delta: int = 0,
        death_delta: int = 0,
        reset_kills: bool = False,
        reset_deaths: bool = False,
    ) -> int:
        kill_streak = 0 if reset_kills else self._player_kill_streaks.get(player_id, 0)
        death_streak = 0 if reset_deaths else self._player_death_streaks.get(player_id, 0)
        kill_streak += kill_delta
        death_streak += death_delta
        self._player_kill_streaks[player_id] = kill_streak
        self._player_death_streaks[player_id] = death_streak
        max_kill_streak = max(kill_streak, self._player_max_kill_streaks.get(player_id, 0))
        max_death_streak = max(death_streak, self._player_max_death_streaks.get(player_id, 0))
        self._player_max_kill_streaks[player_id] = max_kill_streak
        self._player_max_death_streaks[player_id] = max_death_streak
        return kill_streak

    def _apply_frag_player_rollup(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        player_id: int,
        kills: int = 0,
        headshots: int = 0,
        deaths: int = 0,
        suicides: int = 0,
        skill_delta: int = 0,
    ) -> None:
        kill_streak = self._player_max_kill_streaks.get(player_id, 0)
        death_streak = self._player_max_death_streaks.get(player_id, 0)
        self._execute(
            connection,
            _UPDATE_PLAYER_FRAG_ROLLUP_QUERY,
            (
                kills,
                headshots,
                deaths,
                suicides,
                skill_delta,
                kill_streak,
                kill_streak,
                death_streak,
                death_streak,
                player_id,
            ),
        )

    def _handle_world_state(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        if update.event_code in {"Restart_Round_(1_second)", "Round_End"}:
            self._drain_kill_streaks(connection, context, map_name, timestamp, processed_at)
            self._reset_round_streaks()

    def _reset_round_streaks(self) -> None:
        self._player_kill_streaks.clear()

    def _active_trackable_players(self, server_id: int) -> int:
        return len(self._server_active_players.get(server_id, set()))

    def _prune_idle_players(self, server_id: int, event_time: datetime) -> None:
        last_activity = self._server_player_last_activity.get(server_id)
        if not last_activity:
            return
        cutoff = event_time - _ACTIVE_PLAYER_IDLE_TIMEOUT
        stale_players = [player_id for player_id, seen_at in last_activity.items() if seen_at < cutoff]
        if not stale_players:
            return
        active_players = self._server_active_players.setdefault(server_id, set())
        connected_players = self._server_connected_players.setdefault(server_id, set())
        reward_eligible_players = self._server_reward_eligible_players.setdefault(server_id, set())
        for player_id in stale_players:
            if player_id in connected_players:
                continue
            active_players.discard(player_id)
            connected_players.discard(player_id)
            reward_eligible_players.discard(player_id)
            del last_activity[player_id]
        self._server_totals_dirty.add(server_id)

    def _active_trackable_players_for_gate(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> int:
        active_players = self._server_active_players.get(server_id, set())
        if not active_players:
            return 0
        if not self._server_ignore_bots_enabled(connection, server_id):
            return len(active_players)
        return sum(1 for player_id in active_players if not self._player_is_bot.get(player_id, False))

    def _update_player_presence(self, server_id: int, player_id: int, team: str) -> bool:
        active_players = self._server_active_players.setdefault(server_id, set())
        was_active = player_id in active_players
        if self._is_trackable_team(team):
            active_players.add(player_id)
        else:
            active_players.discard(player_id)
        return was_active != (player_id in active_players)

    def _refresh_server_player_totals(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> None:
        total_players = len(self._server_players.get(server_id, set()))
        active_players = len(self._server_connected_players.get(server_id, set()))
        self._execute(
            connection,
            _UPDATE_SERVER_PLAYER_TOTALS_QUERY,
            (total_players, active_players, server_id),
        )
        self._server_totals_dirty.discard(server_id)

    def _refresh_server_player_totals_if_dirty(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> None:
        if server_id in self._server_totals_dirty:
            self._refresh_server_player_totals(connection, server_id)

    def _is_trackable_team(self, team: str) -> bool:
        normalized = self._normalize_team_name(team)
        return normalized not in {"", "SPECTATOR", "SPECTATORS", "SPEC", "UNASSIGNED"}

    def _normalize_team_name(self, team: str | None) -> str:
        normalized = str(team or "").strip().upper()
        compact = normalized.replace("_", " ")
        alias_key = compact.replace(" ", "")
        if alias_key in _TEAM_ALIASES:
            return _TEAM_ALIASES[alias_key]
        return normalized

    def _is_bot_descriptor(self, descriptor: PlayerDescriptor) -> bool:
        if descriptor.user_id is not None and descriptor.user_id <= 0:
            return True
        unique_id = (descriptor.unique_id or "").strip()
        if not unique_id:
            return False
        return bool(_BOT_UNIQUE_RE.match(unique_id))

    def _server_ignore_bots_enabled(
        self,
        connection: proxy_db.SupportsConnection,
        server_id: int,
    ) -> bool:
        cached = self._server_ignore_bots.get(server_id)
        if cached is not None:
            return bool(cached)
        row = self._fetchone(connection, _SELECT_SERVER_CONFIG_QUERY, (server_id, "IgnoreBots"))
        if row and row[0] is not None:
            value = int(row[0])
        else:
            default_row = self._fetchone(connection, _SELECT_DEFAULT_SERVER_CONFIG_QUERY, ("IgnoreBots",))
            value = int(default_row[0]) if default_row and default_row[0] is not None else 0
        self._server_ignore_bots[server_id] = value
        return bool(value)

    def _skip_team_reward_for_ignore_bots(
        self,
        connection: proxy_db.SupportsConnection,
        game: str,
        server_id: int,
        player_id: int,
    ) -> bool:
        """Match Perl ``rewardTeam`` when ``IgnoreBots`` is set: no bonus rows for bots or userid <= 0."""

        if not self._server_ignore_bots_enabled(connection, server_id):
            return False
        if self._is_bot_player(connection, player_id, game):
            return True
        uid = self._player_last_user_id.get(player_id)
        return uid is not None and uid <= 0

    def _is_bot_player(
        self,
        connection: proxy_db.SupportsConnection,
        player_id: int,
        game: str,
    ) -> bool:
        if self._player_is_bot.get(player_id, False):
            return True
        cache_key = (player_id, game)
        cached = self._player_is_bot_cache.get(cache_key)
        if cached is not None:
            return cached
        row = self._fetchone(connection, _SELECT_PLAYER_BOT_UNIQUE_QUERY, (player_id,))
        is_bot = bool(row)
        self._player_is_bot_cache[cache_key] = is_bot
        return is_bot

    def _record_teamkill(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
        killer_id: int,
        victim_id: int,
        weapon_code: str,
        weapon_name: str,
        headshot: int,
        attacker_position: tuple[int | None, int | None, int | None],
        victim_position: tuple[int | None, int | None, int | None],
    ) -> None:
        self._execute(
            connection,
            _INSERT_TEAMKILL_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                killer_id,
                victim_id,
                weapon_code,
                attacker_position[0],
                attacker_position[1],
                attacker_position[2],
                victim_position[0],
                victim_position[1],
                victim_position[2],
            ),
        )
        self._execute(connection, _UPDATE_PLAYER_TEAMKILLS_QUERY, (killer_id,))
        penalty = (-1) * self._server_tk_penalty(connection, context.server_id)
        if penalty:
            self._execute(connection, _UPDATE_PLAYER_SKILL_QUERY, (penalty, killer_id))
        self._execute(
            connection,
            _UPSERT_WEAPON_QUERY,
            (context.game, weapon_code, weapon_name, 1.0, 1, headshot),
        )
        self._update_player_rollups(
            connection,
            context=context,
            timestamp=timestamp,
            processed_at=processed_at,
            player_id=killer_id,
            teamkills=1,
            skill_delta=penalty,
        )

    def _drain_kill_streaks(
        self,
        connection: proxy_db.SupportsConnection,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        for player_id in list(self._player_kills_per_life):
            self._end_kill_streak(
                connection,
                context=context,
                map_name=map_name,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=player_id,
            )

    def _end_kill_streak(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
        player_id: int,
    ) -> None:
        kill_total = self._player_kills_per_life.get(player_id, 0)
        if kill_total <= 1:
            self._player_kills_per_life[player_id] = 0
            return
        self._record_derived_player_action(
            connection,
            context=context,
            map_name=map_name,
            timestamp=timestamp,
            processed_at=processed_at,
            player_id=player_id,
            action_code=f"kill_streak_{min(kill_total, 12)}",
        )
        self._player_kills_per_life[player_id] = 0

    def _record_derived_player_action(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
        player_id: int,
        action_code: str,
    ) -> None:
        update = EventUpdate(
            category=EventCategory.ACTION,
            event_code=action_code,
            actor=None,
            target=None,
            timestamp=timestamp,
        )
        action = self._ensure_action_metadata(connection, context.game, update)
        bonus = action.reward_player
        self._execute(
            connection,
            _INSERT_PLAYER_ACTION_QUERY,
            (timestamp, context.server_id, map_name, player_id, action.action_id, bonus),
        )
        self._execute(connection, _INCREMENT_ACTION_COUNT_QUERY, (action.action_id,))
        if bonus:
            self._apply_player_skill_delta(
                connection,
                context=context,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=player_id,
                delta=bonus,
            )

    def _ensure_player_history_row(
        self,
        connection: proxy_db.SupportsConnection,
        context: EventContext,
        player_id: int,
        timestamp: datetime,
    ) -> None:
        self._player_skills.setdefault(player_id, 1000)
        self._execute(
            connection,
            _UPSERT_PLAYER_HISTORY_QUERY,
            (player_id, self._history_timestamp(timestamp), context.game, self._player_skills[player_id]),
        )

    def _update_player_rollups(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        timestamp: datetime,
        processed_at: datetime,
        player_id: int,
        kills: int = 0,
        deaths: int = 0,
        suicides: int = 0,
        headshots: int = 0,
        shots: int = 0,
        hits: int = 0,
        teamkills: int = 0,
        skill_delta: int = 0,
        kill_streak: int | None = None,
        death_streak: int | None = None,
    ) -> None:
        current_skill = self._player_skills.setdefault(player_id, 1000) + skill_delta
        self._player_skills[player_id] = current_skill
        history_timestamp = self._history_timestamp(processed_at)
        if history_timestamp != self._history_timestamp(timestamp):
            self._ensure_player_history_row(connection, context, player_id, timestamp)

        player_name = self._player_names.get(player_id)
        if player_name:
            self._execute(
                connection,
                _UPDATE_PLAYERNAME_TOTALS_QUERY,
                (0, kills, deaths, suicides, headshots, shots, hits, player_id, player_name),
            )

        resolved_death_streak = death_streak or 0
        resolved_kill_streak = kill_streak or 0
        self._execute(
            connection,
            _UPDATE_PLAYER_HISTORY_QUERY,
            (
                0,
                kills,
                deaths,
                suicides,
                current_skill,
                headshots,
                shots,
                hits,
                teamkills,
                resolved_death_streak,
                resolved_death_streak,
                resolved_kill_streak,
                resolved_kill_streak,
                skill_delta,
                player_id,
                history_timestamp,
                context.game,
            ),
        )

    def _calculate_frag_skill_deltas(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        weapon_code: str,
        killer_id: int,
        victim_id: int,
    ) -> tuple[int, int]:
        killer_skill = self._player_skills.setdefault(killer_id, 1000)
        victim_skill = self._player_skills.setdefault(victim_id, 1000)
        killer_kills = self._player_total_kills.get(killer_id, 0)
        victim_kills = self._player_total_kills.get(victim_id, 0)
        skill_mode = self._server_skill_mode(connection, context.server_id)
        max_change = self._option_int(connection, "SkillMaxChange", default=100)
        min_change = self._option_int(connection, "SkillMinChange", default=2)
        ratio_cap = self._option_int(connection, "SkillRatioCap", default=0)
        min_kills = self._option_int(connection, "PlayerMinKills", default=50)
        modifier = self._weapon_modifier(connection, context.game, weapon_code)
        killer_team = self._player_teams.get(killer_id, "")

        if killer_skill < 1:
            return min_change, 0
        if victim_skill < 1:
            return min_change, 0

        if ratio_cap > 0:
            low_ratio = 0.7
            high_ratio = 1.0 / low_ratio
            ratio = victim_skill / killer_skill
            if ratio < low_ratio:
                ratio = low_ratio
            if ratio > high_ratio:
                ratio = high_ratio
            killer_change = ratio * 5 * modifier
        else:
            killer_change = (victim_skill / killer_skill) * 5 * modifier

        if killer_change > max_change:
            killer_change = max_change

        victim_change = killer_change
        if skill_mode == 1:
            victim_change = killer_change * 0.75
        elif skill_mode == 2:
            victim_change = killer_change * 0.5
        elif skill_mode == 3:
            victim_change = killer_change * 0.25
        elif skill_mode == 4:
            victim_change = 0
        elif skill_mode == 5:
            if killer_team == "Undead":
                victim_change = killer_change * 0.5
            elif killer_team == "Survivor":
                victim_change = killer_change * 0.25

        if victim_change > max_change:
            victim_change = max_change

        if max_change >= min_change:
            if killer_change < min_change:
                killer_change = min_change
            if victim_change < min_change and skill_mode != 4:
                victim_change = min_change

        if killer_kills < min_kills or victim_kills < min_kills:
            killer_change = min_change
            victim_change = 0 if skill_mode == 4 else min_change

        killer_delta = int(killer_skill + killer_change + 0.5) - killer_skill
        victim_delta = int(victim_skill - victim_change + 0.5) - victim_skill
        return killer_delta, victim_delta

    def _apply_player_skill_delta(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        timestamp: datetime,
        processed_at: datetime,
        player_id: int,
        delta: int,
    ) -> None:
        self._execute(connection, _UPDATE_PLAYER_SKILL_QUERY, (delta, player_id))
        self._update_player_rollups(
            connection,
            context=context,
            timestamp=timestamp,
            processed_at=processed_at,
            player_id=player_id,
            skill_delta=delta,
            kill_streak=self._player_max_kill_streaks.get(player_id, 0),
            death_streak=self._player_max_death_streaks.get(player_id, 0),
        )

    def _reward_team_players(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
        processed_at: datetime,
        team: str,
        action: _ActionMetadata,
        bonus: int,
        event_code: str,
    ) -> None:
        active_players = self._server_active_players.get(context.server_id, set())
        reward_eligible_players = self._server_reward_eligible_players.get(context.server_id, set())
        connected_players = self._server_connected_players.get(context.server_id, set())
        candidate_players = set(active_players)
        candidate_players.update(connected_players)
        candidate_players.update(reward_eligible_players)
        for player_id in sorted(candidate_players):
            self._record_team_bonus_stage(
                "candidate_set",
                action_id=action.action_id,
                map_name=map_name,
                event_code=event_code,
                event_time=timestamp,
                player_id=player_id,
                team=team,
                server_id=context.server_id,
            )
            # Legacy rewardTeam iterates the in-memory player roster. A player
            # that joined a trackable team is eligible even when no separate
            # "entered the game" row was emitted in the replay window.
            if player_id not in reward_eligible_players and player_id not in active_players:
                self._record_team_bonus_stage(
                    "eligible_gate_reject",
                    action_id=action.action_id,
                    map_name=map_name,
                    event_code=event_code,
                    event_time=timestamp,
                    player_id=player_id,
                    team=team,
                    server_id=context.server_id,
                )
                continue
            if self._skip_team_reward_for_ignore_bots(connection, context.game, context.server_id, player_id):
                self._record_team_bonus_stage(
                    "ignore_bots_gate_reject",
                    action_id=action.action_id,
                    map_name=map_name,
                    event_code=event_code,
                    event_time=timestamp,
                    player_id=player_id,
                    team=team,
                    server_id=context.server_id,
                )
                continue
            if self._player_teams.get(player_id) != team:
                self._record_team_bonus_stage(
                    "team_gate_reject",
                    action_id=action.action_id,
                    map_name=map_name,
                    event_code=event_code,
                    event_time=timestamp,
                    player_id=player_id,
                    team=team,
                    server_id=context.server_id,
                )
                continue
            if event_code != "Rescued_A_Hostage":
                dedupe_key = (context.server_id, player_id, action.action_id, timestamp)
                if dedupe_key in self._seen_team_bonus_events:
                    self._record_team_bonus_stage(
                        "dedupe_gate_reject",
                        action_id=action.action_id,
                        map_name=map_name,
                        event_code=event_code,
                        event_time=timestamp,
                        player_id=player_id,
                        team=team,
                        server_id=context.server_id,
                    )
                    continue
                self._seen_team_bonus_events.add(dedupe_key)
            self._record_team_bonus_stage(
                "inserted",
                action_id=action.action_id,
                map_name=map_name,
                event_code=event_code,
                event_time=timestamp,
                player_id=player_id,
                team=team,
                server_id=context.server_id,
            )
            self._execute(
                connection,
                _INSERT_TEAM_BONUS_QUERY,
                (timestamp, context.server_id, map_name, player_id, action.action_id, bonus),
            )
            self._apply_player_skill_delta(
                connection,
                context=context,
                timestamp=timestamp,
                processed_at=processed_at,
                player_id=player_id,
                delta=bonus,
            )

    def _history_timestamp(self, timestamp: datetime) -> datetime:
        return datetime(timestamp.year, timestamp.month, timestamp.day)

    def _realign_player_history_day(
        self,
        connection: proxy_db.SupportsConnection,
        *,
        context: EventContext,
        player_id: int,
        event_timestamp: datetime,
        processed_at: datetime,
    ) -> None:
        source_day = self._history_timestamp(processed_at)
        target_day = self._history_timestamp(event_timestamp)
        if source_day == target_day:
            return

        row = self._fetchone(
            connection,
            _SELECT_PLAYER_HISTORY_SNAPSHOT_QUERY,
            (player_id, source_day, context.game),
        )
        if row is None:
            return

        self._execute(
            connection,
            _UPSERT_PLAYER_HISTORY_QUERY,
            (player_id, target_day, context.game, int(row[4] or 1000)),
        )
        self._execute(
            connection,
            _REPLACE_PLAYER_HISTORY_SNAPSHOT_QUERY,
            (
                int(row[0] or 0),
                int(row[1] or 0),
                int(row[2] or 0),
                int(row[3] or 0),
                int(row[4] or 1000),
                int(row[5] or 0),
                int(row[6] or 0),
                int(row[7] or 0),
                int(row[8] or 0),
                int(row[9] or 0),
                int(row[10] or 0),
                int(row[11] or 0),
                player_id,
                target_day,
                context.game,
            ),
        )
        self._execute(
            connection,
            _DELETE_PLAYER_HISTORY_QUERY,
            (player_id, source_day, context.game),
        )

    def _processing_timestamp(self, event_timestamp: datetime) -> datetime:
        if self._use_event_timestamps_for_processing:
            return event_timestamp
        return self._normalize_timestamp(self._clock())

    # ------------------------------------------------------------------
    # Low level helpers

    def _connection(self) -> proxy_db.SupportsConnection:
        return self._adapter.connection()

    def _resolve_map(self, context: EventContext) -> str:
        map_name = context.extras.get("map") if context.extras else None
        if not map_name or str(map_name) == "unknown":
            return ""
        return str(map_name)

    def _normalize_timestamp(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment
        return moment.astimezone(timezone.utc).replace(tzinfo=None)

    def _extract_role(self, descriptor: Optional[PlayerDescriptor]) -> str:
        if descriptor is None or not descriptor.additional_tokens:
            return ""
        return descriptor.additional_tokens[0]

    def _parse_position(self, value: Any) -> tuple[int | None, int | None, int | None]:
        if not isinstance(value, str):
            return (None, None, None)
        parts = value.split()
        if len(parts) != 3:
            return (None, None, None)
        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return (None, None, None)

    def _execute(
        self,
        connection: proxy_db.SupportsConnection,
        query: str,
        params: tuple[Any, ...] | None,
    ) -> None:
        if params is not None and query in _APPEND_ONLY_EVENT_INSERT_QUERIES:
            buffer = self._event_buffer
            if buffer is not None:
                should_flush = buffer.add(query, params)
                if should_flush:
                    self._flush_event_buffer()
                return
        if params is not None and self._buffer_frag_counter_write(query, params):
            return
        self._execute_direct(connection, query, params)

    def _buffer_frag_counter_write(self, query: str, params: tuple[Any, ...]) -> bool:
        buf = self._frag_write_deltas
        if buf is None:
            return False
        if query == _UPSERT_WEAPON_QUERY:
            game, code, name, modifier, kills, headshots = params
            buf.add_weapon(str(game), str(code), str(name), float(modifier), int(kills), int(headshots))
            return True
        if query == _UPDATE_SERVER_FRAG_TOTALS_QUERY:
            kills, headshots, server_id = params
            buf.add_server_frag_totals(int(kills), int(headshots), int(server_id))
            return True
        if query == _UPSERT_MAP_COUNTS_QUERY:
            game, map_name, kills, headshots = params
            buf.add_map_counts(str(game), str(map_name), int(kills), int(headshots))
            return True
        return False

    def _execute_direct(
        self,
        connection: proxy_db.SupportsConnection,
        query: str,
        params: tuple[Any, ...] | None,
    ) -> None:
        cursor = self._cursor(connection)
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
        self._pending_writes += 1

    def _executemany_chunk_size(self) -> int | None:
        size = getattr(self._adapter, "executemany_chunk_size", None)
        if isinstance(size, int) and size > 0:
            return size
        return None

    def _flush_event_buffer(self) -> None:
        buffer = self._event_buffer
        if buffer is None or buffer.buffered_rows <= 0:
            return
        connection = self._connection()
        cursor = self._cursor(connection)
        flushed = buffer.flush(cursor, executemany_chunk_size=self._executemany_chunk_size())
        self._pending_writes += flushed

    def _flush_frag_counter_buffer(self) -> None:
        buf = self._frag_write_deltas
        if buf is None:
            return
        connection = self._connection()

        def _emit(q: str, row: tuple[object, ...]) -> None:
            self._execute_direct(connection, q, row)

        buf.flush(
            upsert_weapon_query=_UPSERT_WEAPON_QUERY,
            update_server_frag_query=_UPDATE_SERVER_FRAG_TOTALS_QUERY,
            upsert_map_counts_query=_UPSERT_MAP_COUNTS_QUERY,
            execute=_emit,
        )

    def _fetchone(
        self,
        connection: proxy_db.SupportsConnection,
        query: str,
        params: tuple[Any, ...] | None,
    ) -> Optional[tuple[Any, ...]]:
        cursor = self._cursor(connection)
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
        return cursor.fetchone()

    def _cursor(self, connection: proxy_db.SupportsConnection) -> proxy_db.SupportsCursor:
        cached = self._cached_cursor
        if cached is not None and self._cached_cursor_connection is connection:
            return cached
        self._close_cached_cursor()
        cursor = connection.cursor()
        self._cached_cursor = cursor
        self._cached_cursor_connection = connection
        return cursor

    def _close_cached_cursor(self) -> None:
        cursor = self._cached_cursor
        if cursor is None:
            return
        try:
            cursor.close()
        finally:
            self._cached_cursor = None
            self._cached_cursor_connection = None

    def _maybe_commit_batch(self) -> None:
        if self._transaction_batch_size <= 0:
            return
        buffer = self._event_buffer
        buffered_rows = buffer.buffered_rows if buffer is not None else 0
        total_pending = self._pending_writes + buffered_rows
        if (
            self._pending_records >= self._transaction_batch_size
            or total_pending >= self._transaction_batch_size
        ):
            self._flush_event_buffer()
            self._flush_frag_counter_buffer()
            self._commit_pending(force=True)

    def _commit_pending(self, *, force: bool = False) -> None:
        if not force and self._pending_writes <= 0:
            return
        connection = self._connection()
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
        self._pending_writes = 0
        if self._transaction_batch_size > 0:
            self._pending_records = 0

    def _rollback_pending(self) -> None:
        buffer = self._event_buffer
        if buffer is not None:
            buffer.clear()
        if self._frag_write_deltas is not None:
            self._frag_write_deltas.clear()
        if self._transaction_batch_size <= 0:
            return
        connection = self._connection()
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        self._pending_writes = 0
        self._pending_records = 0

    def _set_autocommit(self, enabled: bool) -> None:
        connection = self._connection()
        autocommit = getattr(connection, "autocommit", None)
        if callable(autocommit):
            autocommit(enabled)

    def _record_team_bonus_stage(
        self,
        stage: str,
        *,
        action_id: int,
        map_name: str,
        event_code: str,
        event_time: datetime,
        player_id: int,
        team: str,
        server_id: int,
    ) -> None:
        self._team_bonus_stage_counts[stage] = self._team_bonus_stage_counts.get(stage, 0) + 1
        by_action = self._team_bonus_stage_action_counts.setdefault(stage, {})
        by_action[action_id] = by_action.get(action_id, 0) + 1
        map_key = map_name or "<empty>"
        by_map = self._team_bonus_stage_map_counts.setdefault(stage, {})
        by_map[map_key] = by_map.get(map_key, 0) + 1
        by_player = self._team_bonus_stage_player_counts.setdefault(stage, {})
        by_player[player_id] = by_player.get(player_id, 0) + 1
        if len(self._team_bonus_stage_samples) < 200:
            self._team_bonus_stage_samples.append(
                {
                    "stage": stage,
                    "event_time": event_time.isoformat(sep=" "),
                    "action_id": action_id,
                    "player_id": player_id,
                    "team": team,
                    "map": map_key,
                    "event_code": event_code,
                    "server_id": server_id,
                }
            )

    def _write_team_bonus_stage_trace(self) -> None:
        if not self._team_bonus_stage_counts:
            return
        trace_target = os.environ.get("HLSTATS_TEAM_BONUS_TRACE_PATH")
        if not trace_target:
            return
        trace_path = Path(trace_target)
        payload = {
            "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "stage_counts": self._team_bonus_stage_counts,
            "stage_action_counts": self._team_bonus_stage_action_counts,
            "stage_map_counts": self._team_bonus_stage_map_counts,
            "stage_player_counts": self._team_bonus_stage_player_counts,
            "samples": self._team_bonus_stage_samples,
        }
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "EventStorage",
    "StorageError",
]

