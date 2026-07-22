#!/usr/bin/env python3
"""Compare legacy and Python replay databases on logical HLstats statistics.

This script intentionally ignores runtime-only noise such as proxy heartbeat
rows and surrogate IDs. Rows are normalized to logical entities
(`address:port`, action codes, player unique IDs) before comparison so the
output stays focused on replay-induced behavioural differences.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable


DEFAULT_DATABASE = "hlstatsxce"
DEFAULT_LEGACY_CONTAINER = "hlstatsx-legacy-db"
DEFAULT_PYTHON_CONTAINER = "hlstatsx-python-db"


JsonDict = dict[str, Any]


def _raise_csv_field_limit() -> None:
    limit = sys.maxsize
    while limit > 0:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_raise_csv_field_limit()


@dataclass(frozen=True)
class PlayerIdentity:
    game: str
    name: str
    unique_ids: tuple[str, ...]

    def to_json(self) -> JsonDict:
        payload: JsonDict = {"game": self.game, "name": self.name}
        if self.unique_ids:
            payload["unique_ids"] = list(self.unique_ids)
        return payload


@dataclass(frozen=True)
class AwardIdentity:
    game: str
    award_type: str
    code: str

    def to_json(self) -> JsonDict:
        return {
            "game": self.game,
            "award_type": self.award_type,
            "code": self.code,
        }


@dataclass(frozen=True)
class RibbonIdentity:
    game: str
    award_code: str
    award_count: int
    special: int

    def to_json(self) -> JsonDict:
        return {
            "game": self.game,
            "award_code": self.award_code,
            "award_count": self.award_count,
            "special": self.special,
        }


@dataclass(frozen=True)
class TableSpec:
    name: str
    sql: str
    normalize_row: Callable[[dict[str, str | None], "NormalizationContext"], JsonDict]


@dataclass
class NormalizationContext:
    players: dict[int, PlayerIdentity]
    actions: dict[int, str]
    servers: dict[int, JsonDict]
    awards: dict[int, AwardIdentity] = field(default_factory=dict)
    ribbons: dict[int, RibbonIdentity] = field(default_factory=dict)

    def player(self, player_id_text: str | None) -> JsonDict:
        if player_id_text is None:
            return {"missing_player_id": None}
        player_id = int(player_id_text)
        identity = self.players.get(player_id)
        if identity is None:
            return {"missing_player_id": player_id}
        return identity.to_json()

    def action(self, action_id_text: str | None) -> str:
        if action_id_text is None:
            return "<missing-action-id>"
        action_id = int(action_id_text)
        return self.actions.get(action_id, f"<missing-action-id:{action_id}>")

    def server(self, server_id_text: str | None) -> JsonDict:
        if server_id_text is None:
            return {"missing_server_id": None}
        server_id = int(server_id_text)
        return self.servers.get(server_id, {"missing_server_id": server_id})

    def award(self, award_id_text: str | None) -> JsonDict:
        if award_id_text is None:
            return {"missing_award_id": None}
        award_id = int(award_id_text)
        identity = self.awards.get(award_id)
        if identity is None:
            return {"missing_award_id": award_id}
        return identity.to_json()

    def ribbon(self, ribbon_id_text: str | None) -> JsonDict:
        if ribbon_id_text is None:
            return {"missing_ribbon_id": None}
        ribbon_id = int(ribbon_id_text)
        identity = self.ribbons.get(ribbon_id)
        if identity is None:
            return {"missing_ribbon_id": ribbon_id}
        return identity.to_json()


class DockerMysqlClient:
    def __init__(self, container: str, *, database: str) -> None:
        self._container = container
        self._database = database

    def query(self, sql: str) -> list[dict[str, str | None]]:
        command = [
            "docker",
            "exec",
            self._container,
            "mysql",
            "-uroot",
            "-proot123",
            "-D",
            self._database,
            "--batch",
            "--raw",
            "-e",
            sql,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"MySQL query failed in {self._container}: {result.stderr.strip() or result.stdout.strip()}"
            )

        lines = result.stdout.splitlines()
        if not lines:
            return []

        reader = csv.DictReader(lines, delimiter="\t")
        rows: list[dict[str, str | None]] = []
        for row in reader:
            rows.append(
                {
                    key: (None if value == "NULL" else value)
                    for key, value in row.items()
                }
            )
        return rows


def fetch_context(client: DockerMysqlClient) -> NormalizationContext:
    players_by_id: dict[int, dict[str, Any]] = {}
    for row in client.query(
        """
        SELECT
            playerId,
            game,
            lastName
        FROM hlstats_Players
        """
    ):
        player_id = int(require(row, "playerId"))
        players_by_id[player_id] = {
            "game": row.get("game") or "unknown",
            "name": row.get("lastName") or "<missing-player-name>",
            "unique_ids": [],
        }

    for row in client.query(
        """
        SELECT
            playerId,
            uniqueId
        FROM hlstats_PlayerUniqueIds
        ORDER BY playerId, uniqueId
        """
    ):
        player_id = int(require(row, "playerId"))
        record = players_by_id.setdefault(
            player_id,
            {"game": "unknown", "name": "<missing-player>", "unique_ids": []},
        )
        unique_id = normalize_unique_id(require(row, "uniqueId"))
        if unique_id not in record["unique_ids"]:
            record["unique_ids"].append(unique_id)

    players = {
        player_id: PlayerIdentity(
            game=str(record["game"]),
            name=str(record["name"]),
            unique_ids=tuple(sorted(str(value) for value in record["unique_ids"])),
        )
        for player_id, record in players_by_id.items()
    }

    actions = {
        int(require(row, "id")): f"{require(row, 'game')}:{require(row, 'code')}"
        for row in client.query(
            """
            SELECT
                id,
                game,
                code
            FROM hlstats_Actions
            """
        )
    }

    awards = {
        int(require(row, "awardId")): AwardIdentity(
            game=require(row, "game"),
            award_type=require(row, "awardType"),
            code=require(row, "code"),
        )
        for row in client.query(
            """
            SELECT
                awardId,
                game,
                awardType,
                code
            FROM hlstats_Awards
            """
        )
    }

    ribbons = {
        int(require(row, "ribbonId")): RibbonIdentity(
            game=require(row, "game"),
            award_code=require(row, "awardCode"),
            award_count=int(require(row, "awardCount")),
            special=int(require(row, "special")),
        )
        for row in client.query(
            """
            SELECT
                ribbonId,
                game,
                awardCode,
                awardCount,
                special
            FROM hlstats_Ribbons
            """
        )
    }

    servers = {
        int(require(row, "serverId")): {
            "address": require(row, "address"),
            "port": int(require(row, "port")),
            "endpoint": f"{require(row, 'address')}:{require(row, 'port')}",
            "name": require(row, "name"),
            "game": require(row, "game"),
        }
        for row in client.query(
            """
            SELECT
                serverId,
                address,
                port,
                name,
                game
            FROM hlstats_Servers
            """
        )
    }

    return NormalizationContext(
        players=players,
        actions=actions,
        servers=servers,
        awards=awards,
        ribbons=ribbons,
    )


def normalize_unique_id(value: str) -> str:
    if value.startswith("STEAM_0:"):
        return value[len("STEAM_0:") :]
    return value


def require(row: dict[str, str | None], key: str) -> str:
    value = row.get(key)
    if value is None:
        raise ValueError(f"Expected non-null value for column '{key}'")
    return value


def compact(payload: JsonDict) -> JsonDict:
    return {key: value for key, value in payload.items() if value is not None}


def normalize_player_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "player": ctx.player(row.get("playerId")),
            "last_address": row.get("lastAddress"),
            "flag": row.get("flag"),
            "country": row.get("country"),
            "city": row.get("city"),
            "state": row.get("state"),
            "lat": to_number(row.get("lat")),
            "lng": to_number(row.get("lng")),
            "kills": to_int(row.get("kills")),
            "deaths": to_int(row.get("deaths")),
            "suicides": to_int(row.get("suicides")),
            "skill": to_int(row.get("skill")),
            "shots": to_int(row.get("shots")),
            "hits": to_int(row.get("hits")),
            "teamkills": to_int(row.get("teamkills")),
            "headshots": to_int(row.get("headshots")),
            "kill_streak": to_int(row.get("kill_streak")),
            "death_streak": to_int(row.get("death_streak")),
            "activity": to_int(row.get("activity")),
            "hide_ranking": to_int(row.get("hideranking")),
        }
    )


def normalize_player_unique_id_row(
    row: dict[str, str | None], ctx: NormalizationContext
) -> JsonDict:
    return compact(
        {
            "player": ctx.player(row.get("playerId")),
            "game": row.get("game"),
            "unique_id": normalize_unique_id(row.get("uniqueId") or ""),
            "merge": to_int(row.get("merge")),
        }
    )


def normalize_player_name_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "player": ctx.player(row.get("playerId")),
            "name": row.get("name"),
            "kills": to_int(row.get("kills")),
            "deaths": to_int(row.get("deaths")),
            "suicides": to_int(row.get("suicides")),
            "headshots": to_int(row.get("headshots")),
            "shots": to_int(row.get("shots")),
            "hits": to_int(row.get("hits")),
        }
    )


def normalize_players_history_row(
    row: dict[str, str | None], ctx: NormalizationContext
) -> JsonDict:
    return compact(
        {
            "player": ctx.player(row.get("playerId")),
            "event_date": row.get("eventTime"),
            "kills": to_int(row.get("kills")),
            "deaths": to_int(row.get("deaths")),
            "suicides": to_int(row.get("suicides")),
            "skill": to_int(row.get("skill")),
            "shots": to_int(row.get("shots")),
            "hits": to_int(row.get("hits")),
            "game": row.get("game"),
            "headshots": to_int(row.get("headshots")),
            "teamkills": to_int(row.get("teamkills")),
            "kill_streak": to_int(row.get("kill_streak")),
            "death_streak": to_int(row.get("death_streak")),
            "skill_change": to_int(row.get("skill_change")),
        }
    )


def normalize_award_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "game": row.get("game"),
            "award_type": row.get("awardType"),
            "code": row.get("code"),
            "name": row.get("name"),
            "verb": row.get("verb"),
            "daily_winner": ctx.player(row.get("d_winner_id")),
            "daily_winner_count": to_int(row.get("d_winner_count")),
            "global_winner": ctx.player(row.get("g_winner_id")),
            "global_winner_count": to_int(row.get("g_winner_count")),
        }
    )


def normalize_player_award_row(
    row: dict[str, str | None], ctx: NormalizationContext
) -> JsonDict:
    return compact(
        {
            "award_date": row.get("awardTime"),
            "award": ctx.award(row.get("awardId")),
            "player": ctx.player(row.get("playerId")),
            "count": to_int(row.get("count")),
            "game": row.get("game"),
        }
    )


def normalize_player_ribbon_row(
    row: dict[str, str | None], ctx: NormalizationContext
) -> JsonDict:
    return compact(
        {
            "player": ctx.player(row.get("playerId")),
            "ribbon": ctx.ribbon(row.get("ribbonId")),
            "game": row.get("game"),
        }
    )


def normalize_server_row(row: dict[str, str | None], _ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "endpoint": f"{require(row, 'address')}:{require(row, 'port')}",
            "name": row.get("name"),
            "game": row.get("game"),
            "kills": to_int(row.get("kills")),
            "players": to_int(row.get("players")),
            "rounds": to_int(row.get("rounds")),
            "suicides": to_int(row.get("suicides")),
            "headshots": to_int(row.get("headshots")),
            "bombs_planted": to_int(row.get("bombs_planted")),
            "bombs_defused": to_int(row.get("bombs_defused")),
            "ct_wins": to_int(row.get("ct_wins")),
            "ts_wins": to_int(row.get("ts_wins")),
            "act_players": to_int(row.get("act_players")),
            "max_players": to_int(row.get("max_players")),
            "act_map": row.get("act_map"),
            "map_rounds": to_int(row.get("map_rounds")),
            "map_ct_wins": to_int(row.get("map_ct_wins")),
            "map_ts_wins": to_int(row.get("map_ts_wins")),
            "map_changes": to_int(row.get("map_changes")),
            "ct_shots": to_int(row.get("ct_shots")),
            "ct_hits": to_int(row.get("ct_hits")),
            "ts_shots": to_int(row.get("ts_shots")),
            "ts_hits": to_int(row.get("ts_hits")),
            "map_ct_shots": to_int(row.get("map_ct_shots")),
            "map_ct_hits": to_int(row.get("map_ct_hits")),
            "map_ts_shots": to_int(row.get("map_ts_shots")),
            "map_ts_hits": to_int(row.get("map_ts_hits")),
        }
    )


def normalize_action_row(row: dict[str, str | None], _ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "game": row.get("game"),
            "code": row.get("code"),
            "reward_player": to_int(row.get("reward_player")),
            "reward_team": to_int(row.get("reward_team")),
            "team": row.get("team"),
            "description": row.get("description"),
            "count": to_int(row.get("count")),
        }
    )


def normalize_weapon_row(row: dict[str, str | None], _ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "game": row.get("game"),
            "code": row.get("code"),
            "kills": to_int(row.get("kills")),
            "headshots": to_int(row.get("headshots")),
        }
    )


def normalize_maps_counts_row(row: dict[str, str | None], _ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "game": row.get("game"),
            "map": row.get("map"),
            "kills": to_int(row.get("kills")),
            "headshots": to_int(row.get("headshots")),
        }
    )


def normalize_change_team_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "team": row.get("team"),
        }
    )


def normalize_legacy_offline_chat_message(message: str | None) -> str | None:
    if message is None:
        return None
    if all(ord(character) < 128 for character in message):
        return message

    # Legacy `hlstats.pl --stdin` offline import corrupts non-ASCII chat payloads
    # to question marks. Preserve runtime storage fidelity in Python and suppress
    # the transport artifact only inside the parity diff.
    return "".join(character if ord(character) < 128 else "?" for character in message)


def normalize_chat_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "message_mode": to_int(row.get("message_mode")),
            "message": normalize_legacy_offline_chat_message(row.get("message")),
        }
    )


def normalize_connect_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "disconnect_time": row.get("eventTime_Disconnect"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "ip_address": row.get("ipAddress"),
            "hostname": row.get("hostname"),
            "hostgroup": row.get("hostgroup"),
        }
    )


def normalize_entry_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
        }
    )


def normalize_frag_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "killer": ctx.player(row.get("killerId")),
            "victim": ctx.player(row.get("victimId")),
            "weapon": row.get("weapon"),
            "headshot": to_int(row.get("headshot")),
            "killer_role": row.get("killerRole"),
            "victim_role": row.get("victimRole"),
            "pos_x": to_int(row.get("pos_x")),
            "pos_y": to_int(row.get("pos_y")),
            "pos_z": to_int(row.get("pos_z")),
            "pos_victim_x": to_int(row.get("pos_victim_x")),
            "pos_victim_y": to_int(row.get("pos_victim_y")),
            "pos_victim_z": to_int(row.get("pos_victim_z")),
        }
    )


def normalize_teamkill_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "killer": ctx.player(row.get("killerId")),
            "victim": ctx.player(row.get("victimId")),
            "weapon": row.get("weapon"),
            "killer_position": [
                to_int(row.get("pos_x")),
                to_int(row.get("pos_y")),
                to_int(row.get("pos_z")),
            ],
            "victim_position": [
                to_int(row.get("pos_victim_x")),
                to_int(row.get("pos_victim_y")),
                to_int(row.get("pos_victim_z")),
            ],
        }
    )


def normalize_player_action_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "action": ctx.action(row.get("actionId")),
            "bonus": to_int(row.get("bonus")),
            "pos_x": to_int(row.get("pos_x")),
            "pos_y": to_int(row.get("pos_y")),
            "pos_z": to_int(row.get("pos_z")),
        }
    )


def normalize_statsme_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "weapon": row.get("weapon"),
            "shots": to_int(row.get("shots")),
            "hits": to_int(row.get("hits")),
            "headshots": to_int(row.get("headshots")),
            "damage": to_int(row.get("damage")),
            "kills": to_int(row.get("kills")),
            "deaths": to_int(row.get("deaths")),
        }
    )


def normalize_statsme2_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "weapon": row.get("weapon"),
            "head": to_int(row.get("head")),
            "chest": to_int(row.get("chest")),
            "stomach": to_int(row.get("stomach")),
            "leftarm": to_int(row.get("leftarm")),
            "rightarm": to_int(row.get("rightarm")),
            "leftleg": to_int(row.get("leftleg")),
            "rightleg": to_int(row.get("rightleg")),
        }
    )


def normalize_team_bonuses_row(row: dict[str, str | None], ctx: NormalizationContext) -> JsonDict:
    return compact(
        {
            "event_time": row.get("eventTime"),
            "server": ctx.server(row.get("serverId")),
            "map": row.get("map"),
            "player": ctx.player(row.get("playerId")),
            "action": ctx.action(row.get("actionId")),
            "bonus": to_int(row.get("bonus")),
        }
    )


def to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def to_number(value: str | None) -> int | float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "hlstats_Servers",
        """
        SELECT
            address, port, name, game, kills, players, rounds, suicides, headshots,
            bombs_planted, bombs_defused, ct_wins, ts_wins, act_players, max_players,
            act_map, map_rounds, map_ct_wins, map_ts_wins, map_changes, ct_shots,
            ct_hits, ts_shots, ts_hits, map_ct_shots, map_ct_hits, map_ts_shots,
            map_ts_hits
        FROM hlstats_Servers
        """,
        normalize_server_row,
    ),
    TableSpec(
        "hlstats_Actions",
        """
        SELECT
            game, code, reward_player, reward_team, team, description, count
        FROM hlstats_Actions
        """,
        normalize_action_row,
    ),
    TableSpec(
        "hlstats_Weapons",
        """
        SELECT
            game, code, name, modifier, kills, headshots
        FROM hlstats_Weapons
        """,
        normalize_weapon_row,
    ),
    TableSpec(
        "hlstats_Maps_Counts",
        """
        SELECT
            game, map, kills, headshots
        FROM hlstats_Maps_Counts
        """,
        normalize_maps_counts_row,
    ),
    TableSpec(
        "hlstats_Players",
        """
        SELECT
            playerId, lastAddress, connection_time, kills, deaths, suicides, skill,
            shots, hits, teamkills, headshots, kill_streak, death_streak, activity,
            hideranking, flag, country, city, state, lat, lng
        FROM hlstats_Players
        """,
        normalize_player_row,
    ),
    TableSpec(
        "hlstats_Awards",
        """
        SELECT
            awardId, awardType, game, code, name, verb,
            d_winner_id, d_winner_count, g_winner_id, g_winner_count
        FROM hlstats_Awards
        """,
        normalize_award_row,
    ),
    TableSpec(
        "hlstats_Players_Awards",
        """
        SELECT
            awardTime, awardId, playerId, count, game
        FROM hlstats_Players_Awards
        """,
        normalize_player_award_row,
    ),
    TableSpec(
        "hlstats_Players_Ribbons",
        """
        SELECT
            playerId, ribbonId, game
        FROM hlstats_Players_Ribbons
        """,
        normalize_player_ribbon_row,
    ),
    TableSpec(
        "hlstats_PlayerUniqueIds",
        """
        SELECT
            playerId, uniqueId, game, merge
        FROM hlstats_PlayerUniqueIds
        """,
        normalize_player_unique_id_row,
    ),
    TableSpec(
        "hlstats_PlayerNames",
        """
        SELECT
            playerId, name, lastuse, connection_time, numuses, kills, deaths,
            suicides, headshots, shots, hits
        FROM hlstats_PlayerNames
        """,
        normalize_player_name_row,
    ),
    TableSpec(
        "hlstats_Players_History",
        """
        SELECT
            playerId, eventTime, connection_time, kills, deaths, suicides, skill,
            shots, hits, game, headshots, teamkills, kill_streak, death_streak,
            skill_change
        FROM hlstats_Players_History
        """,
        normalize_players_history_row,
    ),
    TableSpec(
        "hlstats_Events_ChangeTeam",
        """
        SELECT
            eventTime, serverId, map, playerId, team
        FROM hlstats_Events_ChangeTeam
        """,
        normalize_change_team_row,
    ),
    TableSpec(
        "hlstats_Events_Chat",
        """
        SELECT
            eventTime, serverId, map, playerId, message_mode, message
        FROM hlstats_Events_Chat
        """,
        normalize_chat_row,
    ),
    TableSpec(
        "hlstats_Events_Connects",
        """
        SELECT
            eventTime, serverId, map, playerId, ipAddress, hostname, hostgroup,
            eventTime_Disconnect
        FROM hlstats_Events_Connects
        """,
        normalize_connect_row,
    ),
    TableSpec(
        "hlstats_Events_Entries",
        """
        SELECT
            eventTime, serverId, map, playerId
        FROM hlstats_Events_Entries
        """,
        normalize_entry_row,
    ),
    TableSpec(
        "hlstats_Events_Frags",
        """
        SELECT
            eventTime, serverId, map, killerId, victimId, weapon, headshot,
            killerRole, victimRole, pos_x, pos_y, pos_z, pos_victim_x,
            pos_victim_y, pos_victim_z
        FROM hlstats_Events_Frags
        """,
        normalize_frag_row,
    ),
    TableSpec(
        "hlstats_Events_Teamkills",
        """
        SELECT
            eventTime, serverId, map, killerId, victimId, weapon, pos_x, pos_y,
            pos_z, pos_victim_x, pos_victim_y, pos_victim_z
        FROM hlstats_Events_Teamkills
        """,
        normalize_teamkill_row,
    ),
    TableSpec(
        "hlstats_Events_PlayerActions",
        """
        SELECT
            eventTime, serverId, map, playerId, actionId, bonus, pos_x, pos_y, pos_z
        FROM hlstats_Events_PlayerActions
        """,
        normalize_player_action_row,
    ),
    TableSpec(
        "hlstats_Events_Statsme",
        """
        SELECT
            eventTime, serverId, map, playerId, weapon, shots, hits, headshots,
            damage, kills, deaths
        FROM hlstats_Events_Statsme
        """,
        normalize_statsme_row,
    ),
    TableSpec(
        "hlstats_Events_Statsme2",
        """
        SELECT
            eventTime, serverId, map, playerId, weapon, head, chest, stomach,
            leftarm, rightarm, leftleg, rightleg
        FROM hlstats_Events_Statsme2
        """,
        normalize_statsme2_row,
    ),
    TableSpec(
        "hlstats_Events_TeamBonuses",
        """
        SELECT
            eventTime, serverId, map, playerId, actionId, bonus
        FROM hlstats_Events_TeamBonuses
        """,
        normalize_team_bonuses_row,
    ),
)


def compare_table(
    spec: TableSpec,
    legacy_client: DockerMysqlClient,
    python_client: DockerMysqlClient,
    legacy_ctx: NormalizationContext,
    python_ctx: NormalizationContext,
    *,
    max_examples: int,
) -> dict[str, Any] | None:
    legacy_rows = [spec.normalize_row(row, legacy_ctx) for row in legacy_client.query(spec.sql)]
    python_rows = [spec.normalize_row(row, python_ctx) for row in python_client.query(spec.sql)]

    legacy_counter = Counter(canonicalize(row) for row in legacy_rows)
    python_counter = Counter(canonicalize(row) for row in python_rows)

    if legacy_counter == python_counter:
        return None

    legacy_only = legacy_counter - python_counter
    python_only = python_counter - legacy_counter

    return {
        "table": spec.name,
        "legacy_rows": len(legacy_rows),
        "python_rows": len(python_rows),
        "legacy_only": legacy_only.total(),
        "python_only": python_only.total(),
        "legacy_only_examples": expand_examples(legacy_only, max_examples=max_examples),
        "python_only_examples": expand_examples(python_only, max_examples=max_examples),
    }


def canonicalize(payload: JsonDict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def expand_examples(counter: Counter[str], *, max_examples: int) -> list[JsonDict]:
    examples: list[JsonDict] = []
    for encoded, count in counter.most_common(max_examples):
        row = json.loads(encoded)
        row["_count"] = count
        examples.append(row)
    return examples


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare logical HLstats replay output between legacy and Python databases.",
    )
    parser.add_argument(
        "--legacy-container",
        default=DEFAULT_LEGACY_CONTAINER,
        help=f"Legacy MariaDB container name (default: {DEFAULT_LEGACY_CONTAINER})",
    )
    parser.add_argument(
        "--python-container",
        default=DEFAULT_PYTHON_CONTAINER,
        help=f"Python MariaDB container name (default: {DEFAULT_PYTHON_CONTAINER})",
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"Database name to query (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="Maximum legacy-only/python-only example rows per table.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    return parser.parse_args(argv)


def print_text_report(differences: list[dict[str, Any]]) -> None:
    if not differences:
        print("No logical replay differences found in the configured statistical tables.")
        return

    print(f"Found logical replay differences in {len(differences)} table(s).")
    print()
    for difference in differences:
        print(f"[{difference['table']}]")
        print(
            f"  legacy rows: {difference['legacy_rows']}, python rows: {difference['python_rows']}, "
            f"legacy-only normalized rows: {difference['legacy_only']}, "
            f"python-only normalized rows: {difference['python_only']}"
        )

        if difference["legacy_only_examples"]:
            print("  legacy-only examples:")
            for example in difference["legacy_only_examples"]:
                _print_json_line(example)

        if difference["python_only_examples"]:
            print("  python-only examples:")
            for example in difference["python_only_examples"]:
                _print_json_line(example)

        print()


def _print_json_line(payload: JsonDict) -> None:
    line = "    " + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    try:
        print(line)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = line.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        print(safe)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        legacy_client = DockerMysqlClient(args.legacy_container, database=args.database)
        python_client = DockerMysqlClient(args.python_container, database=args.database)
        legacy_ctx = fetch_context(legacy_client)
        python_ctx = fetch_context(python_client)
        differences = [
            difference
            for spec in TABLE_SPECS
            if (difference := compare_table(
                spec,
                legacy_client,
                python_client,
                legacy_ctx,
                python_ctx,
                max_examples=args.max_examples,
            ))
            is not None
        ]
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(differences, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(differences)

    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
