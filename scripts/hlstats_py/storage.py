"""Persistence layer that mirrors ``hlstats.pl`` database mutations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from proxy_daemon_py import db as proxy_db
from .events import EventCategory, EventContext, EventUpdate
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
_PLAYER_BY_NAME_QUERY = (
    "SELECT `playerId` FROM hlstats_Players WHERE `lastName` = %s AND `game` = %s"
    " ORDER BY `playerId` DESC LIMIT 1"
)
_INSERT_PLAYER_QUERY = "INSERT INTO hlstats_Players (`game`, `lastName`) VALUES (%s, %s)"
_LAST_INSERT_ID_QUERY = "SELECT LAST_INSERT_ID()"
_UPDATE_PLAYER_NAME_QUERY = "UPDATE hlstats_Players SET `lastName` = %s WHERE `playerId` = %s"
_UPSERT_PLAYER_NAME_QUERY = (
    "INSERT INTO hlstats_PlayerNames (`playerId`, `name`, `lastuse`) VALUES (%s, %s, %s) "
    "ON DUPLICATE KEY UPDATE `lastuse` = VALUES(`lastuse`), `numuses` = `numuses` + 1"
)
_UPSERT_PLAYER_UNIQUE_QUERY = (
    "INSERT INTO hlstats_PlayerUniqueIds (`playerId`, `uniqueId`, `game`) VALUES (%s, %s, %s) "
    "ON DUPLICATE KEY UPDATE `playerId` = VALUES(`playerId`)"
)
_INSERT_FRAG_QUERY = (
    "INSERT INTO hlstats_Events_Frags ("
    "`eventTime`, `serverId`, `map`, `killerId`, `victimId`, `weapon`, `headshot`, "
    "`killerRole`, `victimRole`, `pos_x`, `pos_y`, `pos_z`, "
    "`pos_victim_x`, `pos_victim_y`, `pos_victim_z`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
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
_UPSERT_WEAPON_QUERY = (
    "INSERT INTO hlstats_Weapons (`game`, `code`, `name`, `modifier`, `kills`, `headshots`) "
    "VALUES (%s, %s, %s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE "
    "`kills` = `kills` + VALUES(`kills`), "
    "`headshots` = `headshots` + VALUES(`headshots`), "
    "`name` = VALUES(`name`)"
)
_SELECT_ACTION_QUERY = (
    "SELECT `id`, `reward_player`, `reward_team` FROM hlstats_Actions "
    "WHERE `game` = %s AND `code` = %s LIMIT 1"
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
_INSERT_PLAYER_PLAYER_ACTION_QUERY = (
    "INSERT INTO hlstats_Events_PlayerPlayerActions ("
    "`eventTime`, `serverId`, `map`, `playerId`, `victimId`, `actionId`, `bonus`) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_UPDATE_PLAYER_SKILL_QUERY = (
    "UPDATE hlstats_Players SET `skill` = `skill` + %s WHERE `playerId` = %s"
)
_INSERT_CHAT_QUERY = (
    "INSERT INTO hlstats_Events_Chat ("
    "`eventTime`, `serverId`, `map`, `playerId`, `message_mode`, `message`) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
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


@dataclass(frozen=True, slots=True)
class _PlayerCacheKey:
    scope: str
    identifier: str
    user_id: Optional[int]


class EventStorage:
    """Translate :class:`EventUpdate` objects into SQL statements."""

    def __init__(self, adapter: SupportsConnectionProvider) -> None:
        self._adapter = adapter
        self._player_cache: dict[_PlayerCacheKey, int] = {}
        self._action_cache: dict[tuple[str, str], int] = {}

    def record(self, update: EventUpdate, context: EventContext) -> None:
        """Persist *update* using metadata from *context*."""

        connection = self._connection()
        map_name = self._resolve_map(context)
        timestamp = self._normalize_timestamp(update.timestamp)

        try:
            if update.category is EventCategory.FRAG:
                self._record_frag(connection, update, context, map_name, timestamp)
            elif update.category is EventCategory.ACTION:
                self._record_action(connection, update, context, map_name, timestamp)
            elif update.category is EventCategory.CHAT:
                self._record_chat(connection, update, context, map_name, timestamp)
            elif update.category is EventCategory.TEAM:
                self._record_team_change(connection, update, context, map_name, timestamp)
            elif update.category is EventCategory.CONNECTION:
                self._record_connection(connection, update, context, map_name, timestamp)
            elif update.category is EventCategory.WORLD:
                self._record_world_action(connection, update, context, map_name, timestamp)
            else:
                self._record_generic(connection, update, context, map_name, timestamp)
        except Exception as exc:  # pragma: no cover - safety net
            raise StorageError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Recording helpers

    def _record_frag(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        killer_id = self._resolve_player_id(connection, update.actor, context, timestamp)
        victim_descriptor = update.target if update.target is not None else update.actor
        victim_id = self._resolve_player_id(connection, victim_descriptor, context, timestamp)

        headshot = 1 if update.attributes.get("headshot") else 0
        killer_role = self._extract_role(update.actor)
        victim_role = self._extract_role(update.target)

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
            None,
            None,
            None,
            None,
            None,
            None,
        )
        self._execute(connection, _INSERT_FRAG_QUERY, params)

        if killer_id:
            self._execute(
                connection,
                _UPDATE_PLAYER_KILLS_QUERY,
                (1, headshot, killer_id),
            )
        if victim_id:
            if killer_id and killer_id == victim_id:
                self._execute(connection, _UPDATE_PLAYER_SUICIDES_QUERY, (victim_id,))
            else:
                self._execute(connection, _UPDATE_PLAYER_DEATHS_QUERY, (victim_id,))

        weapon_name = update.attributes.get("weapon_name") or update.event_code
        self._execute(
            connection,
            _UPSERT_WEAPON_QUERY,
            (context.game, update.event_code, weapon_name, 1.0, 1, headshot),
        )

    def _record_action(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp)
        victim_id = self._resolve_player_id(connection, update.target, context, timestamp)
        action_id = self._ensure_action_id(connection, context.game, update)
        bonus = int(update.attributes.get("points") or 0)

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
                    action_id,
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
                    action_id,
                    bonus,
                ),
            )

        self._execute(connection, _INCREMENT_ACTION_COUNT_QUERY, (action_id,))
        if actor_id and bonus:
            self._execute(connection, _UPDATE_PLAYER_SKILL_QUERY, (bonus, actor_id))

    def _record_chat(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp)
        team_only = 1 if update.attributes.get("team_only") else 0
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

    def _record_team_change(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp)
        team = str(update.attributes.get("team", update.event_code))
        self._execute(
            connection,
            _INSERT_TEAM_CHANGE_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                actor_id or 0,
                team,
            ),
        )

    def _record_connection(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        actor_id = self._resolve_player_id(connection, update.actor, context, timestamp)
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
                    "UPDATE hlstats_Players SET `lastAddress` = %s WHERE `playerId` = %s",
                    (address, actor_id),
                )
        else:
            self._execute(
                connection,
                _INSERT_DISCONNECT_QUERY,
                (timestamp, context.server_id, map_name, actor_id or 0),
            )

    def _record_world_action(
        self,
        connection: proxy_db.SupportsConnection,
        update: EventUpdate,
        context: EventContext,
        map_name: str,
        timestamp: datetime,
    ) -> None:
        action_id = self._ensure_action_id(connection, context.game, update)
        bonus = int(update.attributes.get("points") or 0)
        self._execute(
            connection,
            _INSERT_PLAYER_ACTION_QUERY,
            (
                timestamp,
                context.server_id,
                map_name,
                0,
                action_id,
                bonus,
            ),
        )
        self._execute(connection, _INCREMENT_ACTION_COUNT_QUERY, (action_id,))

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

    # ------------------------------------------------------------------
    # Resolution helpers

    def _resolve_player_id(
        self,
        connection: proxy_db.SupportsConnection,
        descriptor: Optional[PlayerDescriptor],
        context: EventContext,
        timestamp: datetime,
    ) -> Optional[int]:
        if descriptor is None:
            return None

        cache_key = self._cache_key_for_player(context.game, descriptor)
        player_id = self._player_cache.get(cache_key)
        if player_id is None:
            player_id = self._lookup_player(connection, descriptor, context.game)
            if player_id is None:
                player_id = self._create_player(connection, descriptor, context.game)
                if descriptor.unique_id:
                    self._execute(
                        connection,
                        _UPSERT_PLAYER_UNIQUE_QUERY,
                        (player_id, descriptor.unique_id, context.game),
                    )
            self._player_cache[cache_key] = player_id

        self._touch_player_profile(connection, player_id, descriptor, timestamp)
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
            row = self._fetchone(
                connection,
                _PLAYER_BY_UNIQUE_QUERY,
                (descriptor.unique_id, game),
            )
            if row:
                return int(row[0])
        row = self._fetchone(
            connection,
            _PLAYER_BY_NAME_QUERY,
            (descriptor.name, game),
        )
        if row:
            return int(row[0])
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
        timestamp: datetime,
    ) -> None:
        self._execute(connection, _UPDATE_PLAYER_NAME_QUERY, (descriptor.name, player_id))
        self._execute(
            connection,
            _UPSERT_PLAYER_NAME_QUERY,
            (player_id, descriptor.name, timestamp),
        )

    def _ensure_action_id(
        self,
        connection: proxy_db.SupportsConnection,
        game: str,
        update: EventUpdate,
    ) -> int:
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
            action_id = int(row[0])
        else:
            description = update.attributes.get("description") or update.event_code
            reward_player = int(update.attributes.get("points") or 0)
            reward_team = 1 if update.attributes.get("team_award") else 0
            team = ""
            self._execute(
                connection,
                _INSERT_ACTION_QUERY,
                (game, update.event_code, description, reward_player, reward_team, team),
            )
            row = self._fetchone(connection, _LAST_INSERT_ID_QUERY, None)
            if not row:
                raise StorageError("Failed to create action definition")
            action_id = int(row[0])
        self._action_cache[cache_key] = action_id
        return action_id

    # ------------------------------------------------------------------
    # Low level helpers

    def _connection(self) -> proxy_db.SupportsConnection:
        return self._adapter.connection()

    def _resolve_map(self, context: EventContext) -> str:
        map_name = context.extras.get("map") if context.extras else None
        if not map_name:
            raise StorageError("Event context is missing current map name")
        return str(map_name)

    def _normalize_timestamp(self, moment: datetime) -> datetime:
        if moment.tzinfo is None:
            return moment
        return moment.astimezone(timezone.utc).replace(tzinfo=None)

    def _extract_role(self, descriptor: Optional[PlayerDescriptor]) -> str:
        if descriptor is None or not descriptor.additional_tokens:
            return ""
        return descriptor.additional_tokens[0]

    def _execute(
        self,
        connection: proxy_db.SupportsConnection,
        query: str,
        params: tuple[Any, ...] | None,
    ) -> None:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
        finally:
            cursor.close()

    def _fetchone(
        self,
        connection: proxy_db.SupportsConnection,
        query: str,
        params: tuple[Any, ...] | None,
    ) -> Optional[tuple[Any, ...]]:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()


__all__ = [
    "EventStorage",
    "StorageError",
]

