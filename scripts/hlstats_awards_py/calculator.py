"""Database-backed awards processing logic for the Python port."""

from __future__ import annotations

import ipaddress
from contextlib import suppress
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from hlx_core.db import DatabaseConfig as DaemonDatabaseConfig
from hlx_core.db import SupportsConnection, SyncDatabaseAdapter

from .cli import AwardsAction, RuntimePolicy, RuntimeSettings


@dataclass(frozen=True, slots=True)
class AwardDefinition:
    """Row from ``hlstats_Awards`` describing an award to evaluate."""

    award_id: int
    game: str
    award_type: str
    code: str


_EVENT_TABLES: tuple[str, ...] = (
    "TeamBonuses",
    "ChangeRole",
    "ChangeName",
    "ChangeTeam",
    "Connects",
    "Disconnects",
    "Entries",
    "Frags",
    "PlayerActions",
    "PlayerPlayerActions",
    "Suicides",
    "Teamkills",
    "Rcon",
    "Admin",
    "Statsme",
    "Statsme2",
    "StatsmeLatency",
    "StatsmeTime",
    "Latency",
    "Chat",
)

_SELECT_USE_GEOIP_BINARY_QUERY = """
    SELECT value
    FROM hlstats_Options
    WHERE keyname = 'UseGeoIPBinary'
      AND value > '0'
    LIMIT 1
"""

_SELECT_GEOLITE_BLOCKS_SMOKE_QUERY = "SELECT locId FROM geoLiteCity_Blocks LIMIT 1"

_SELECT_GEOIP_CANDIDATES_QUERY = """
    SELECT playerId, lastAddress, lastName
    FROM hlstats_Players
    WHERE flag = '' AND lastAddress <> ''
"""

_SELECT_GEOLITE_BLOCK_QUERY = """
    SELECT locId
    FROM geoLiteCity_Blocks
    WHERE startIpNum <= %s AND endIpNum >= %s
    LIMIT 1
"""

_SELECT_GEOLITE_LOCATION_QUERY = """
    SELECT city,
           region AS state,
           name AS country,
           country AS flag,
           latitude AS lat,
           longitude AS lng
    FROM geoLiteCity_Location a
    INNER JOIN hlstats_Countries b ON a.country = b.flag
    WHERE locId = %s
    LIMIT 1
"""

_UPDATE_PLAYER_GEOIP_QUERY = """
    UPDATE hlstats_Players
    SET flag = %s,
        country = %s,
        lat = %s,
        lng = %s,
        city = %s,
        state = %s
    WHERE playerId = %s
"""


@dataclass(frozen=True, slots=True)
class AwardResult:
    """Snapshot of the winners chosen for an award run."""

    definition: AwardDefinition
    daily: AwardWinner
    overall: AwardWinner


@dataclass(slots=True)
class AwardsReport:
    """Aggregated maintenance metrics captured during execution."""

    inactive_updates: int = 0
    players_hidden: int = 0
    awards: list[AwardResult] = field(default_factory=list)
    player_awards_synced: int = 0
    ribbons_cleared: dict[str, int] = field(default_factory=dict)
    ribbons_awarded: dict[str, int] = field(default_factory=dict)
    pruned_tables: dict[str, int] = field(default_factory=dict)
    optimized_tables: list[str] = field(default_factory=list)
    geoip_updates: int = 0


@dataclass(frozen=True, slots=True)
class GeoIpLocation:
    """Resolved GeoIP metadata ready to be written into ``hlstats_Players``."""

    flag: str
    country: str
    city: str
    state: str
    lat: float | None
    lng: float | None


@dataclass(frozen=True, slots=True)
class CalculatorPolicy:
    replay_safe: bool
    include_hidden_players: bool
    strict_geoip: bool

    @classmethod
    def from_runtime(cls, policy: RuntimePolicy) -> "CalculatorPolicy":
        if policy is RuntimePolicy.REPLAY_SAFE:
            return cls(replay_safe=True, include_hidden_players=True, strict_geoip=False)
        return cls(replay_safe=False, include_hidden_players=False, strict_geoip=True)


class AwardsCalculator:
    """High level coordinator that executes the awards maintenance tasks."""

    def __init__(
        self,
        adapter: SyncDatabaseAdapter,
        *,
        verbose: bool = False,
        report: AwardsReport | None = None,
    ) -> None:
        self._adapter = adapter
        self._verbose = verbose
        self._report = report
        self._policy = CalculatorPolicy.from_runtime(RuntimePolicy.STRICT)

    def run(self, settings: RuntimeSettings) -> None:
        """Execute the requested actions using ``settings`` as directives."""

        self._policy = CalculatorPolicy.from_runtime(settings.policy)
        actions = settings.actions
        connection = self._adapter.connection()

        if AwardsAction.PRUNE in actions:
            self._prune_events(connection)
        if AwardsAction.OPTIMIZE in actions:
            self._optimize_tables(connection)
        if AwardsAction.INACTIVE in actions:
            self._update_player_activity(connection)
        if AwardsAction.GEOIP in actions:
            try:
                self._process_geoip(connection, settings)
            except RuntimeError as exc:
                if self._policy.strict_geoip:
                    raise
                print(f"warning: {exc}; skipping GeoIP in replay-safe mode")
        if AwardsAction.AWARDS in actions:
            self._process_awards(connection, settings.cli.numdays, settings.cli.date)
        if AwardsAction.RIBBONS in actions:
            self._process_ribbons(connection)

    # ------------------------------------------------------------------
    # Inactive player handling
    # ------------------------------------------------------------------
    def _update_player_activity(self, connection: SupportsConnection) -> None:
        min_activity_row = self._fetchone(
            connection,
            """
            SELECT value
            FROM hlstats_Options
            WHERE keyname = 'MinActivity'
            """,
        )
        if min_activity_row and min_activity_row[0] not in (None, ""):
            min_activity_seconds = int(min_activity_row[0]) * 86400
        else:
            min_activity_seconds = 2419200

        if min_activity_seconds <= 0:
            return

        timestamp_row = self._fetchone(
            connection,
            """
            SELECT value
            FROM hlstats_Options
            WHERE keyname = 'UseTimestamp'
            """,
        )
        use_timestamp = False
        if timestamp_row and timestamp_row[0] not in (None, ""):
            try:
                use_timestamp = int(timestamp_row[0]) > 0
            except ValueError:  # pragma: no cover - defensive
                use_timestamp = False

        total_updated = 0
        if use_timestamp:
            rows = self._fetchall(
                connection,
                """
                SELECT game, MAX(last_event)
                FROM hlstats_Servers
                GROUP BY game
                """,
            )
            for game, last_event in rows:
                if last_event is None:
                    continue
                total_updated += self._execute(
                    connection,
                    """
                    UPDATE hlstats_Players
                    SET activity = IF(
                        (%s > TIMESTAMPDIFF(SECOND, hlstats_Players.last_event, %s)),
                        ((100 / %s) * (%s - TIMESTAMPDIFF(SECOND, hlstats_Players.last_event, %s))),
                        -1
                    )
                    WHERE hlstats_Players.game = %s
                    """,
                    (
                        min_activity_seconds,
                        last_event,
                        min_activity_seconds,
                        min_activity_seconds,
                        last_event,
                        game,
                    ),
                )
        else:
            total_updated += self._execute(
                connection,
                """
                UPDATE hlstats_Players
                SET activity = IF(
                    (%s > TIMESTAMPDIFF(SECOND, hlstats_Players.last_event, NOW())),
                    ((100 / %s) * (%s - TIMESTAMPDIFF(SECOND, hlstats_Players.last_event, NOW()))),
                    -1
                )
                """,
                (
                    min_activity_seconds,
                    min_activity_seconds,
                    min_activity_seconds,
                ),
            )

        hidden_players = self._execute(
            connection,
            """
            UPDATE hlstats_Players
            SET hideranking = 3
            WHERE hideranking = 0
              AND activity < 0
            """,
        )

        if self._report is not None:
            self._report.inactive_updates += total_updated
            self._report.players_hidden += hidden_players

    # ------------------------------------------------------------------
    # GeoIP
    # ------------------------------------------------------------------
    def _process_geoip(self, connection: SupportsConnection, settings: RuntimeSettings) -> None:
        use_binary = self._fetchone(connection, _SELECT_USE_GEOIP_BINARY_QUERY) is not None
        candidates = self._fetchall(connection, _SELECT_GEOIP_CANDIDATES_QUERY)
        updates = 0

        if use_binary:
            reader = self._open_geoip_reader(settings)
            try:
                for player_id, address, player_name in candidates:
                    ip_address = self._normalise_ipv4(address)
                    if ip_address is None:
                        self._log_verbose(f"Skipping GeoIP for {player_name}: invalid IPv4 {address!r}")
                        continue
                    location = self._lookup_binary_geoip(reader, ip_address)
                    if location is None:
                        continue
                    updates += self._update_player_geoip(connection, int(player_id), location)
            finally:
                with suppress(Exception):
                    reader.close()
        else:
            smoke = self._fetchone(connection, _SELECT_GEOLITE_BLOCKS_SMOKE_QUERY)
            if smoke is None:
                raise RuntimeError("GeoIP method set to database but geoLiteCity tables are empty.")

            for player_id, address, player_name in candidates:
                ip_address = self._normalise_ipv4(address)
                if ip_address is None:
                    self._log_verbose(f"Skipping GeoIP for {player_name}: invalid IPv4 {address!r}")
                    continue
                location = self._lookup_database_geoip(connection, ip_address)
                if location is None:
                    continue
                updates += self._update_player_geoip(connection, int(player_id), location)

        if self._report is not None:
            self._report.geoip_updates += updates

    def _open_geoip_reader(self, settings: RuntimeSettings) -> Any:
        database_path = self._geoip_database_path(settings)
        if not database_path.is_file():
            raise RuntimeError(
                f"GeoIP method set to binary file lookup but {database_path} NOT FOUND"
            )

        try:
            import geoip2.database
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                "GeoIP method set to binary file lookup but geoip2.database module NOT FOUND"
            ) from exc

        try:
            return geoip2.database.Reader(str(database_path))
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError(
                f"GeoIP method set to binary file lookup but {database_path} errored while opening."
            ) from exc

    def _geoip_database_path(self, settings: RuntimeSettings) -> Path:
        scripts_root = settings.config_path.parent if settings.config_path is not None else Path.cwd()
        return scripts_root / "GeoLiteCity" / "GeoLite2-City.mmdb"

    def _lookup_binary_geoip(self, reader: Any, ip_address: str) -> GeoIpLocation | None:
        try:
            response = reader.city(ip_address)
        except Exception:  # pragma: no cover - runtime dependency
            return None

        country_code = getattr(response.country, "iso_code", None)
        country_name = getattr(response.country, "name", None)
        city = getattr(response.city, "name", None)
        subdivisions = getattr(response, "subdivisions", None)
        most_specific = getattr(subdivisions, "most_specific", None)
        state = getattr(most_specific, "name", None)
        lat = getattr(response.location, "latitude", None)
        lng = getattr(response.location, "longitude", None)

        if not country_code or not country_name or lng is None:
            return None

        return GeoIpLocation(
            flag=str(country_code),
            country=str(country_name),
            city="" if city is None else str(city),
            state="" if state is None else str(state),
            lat=None if lat is None else float(lat),
            lng=None if lng is None else float(lng),
        )

    def _lookup_database_geoip(
        self, connection: SupportsConnection, ip_address: str
    ) -> GeoIpLocation | None:
        ip_number = int(ipaddress.IPv4Address(ip_address))
        block_row = self._fetchone(connection, _SELECT_GEOLITE_BLOCK_QUERY, (ip_number, ip_number))
        if not block_row:
            return None

        location_row = self._fetchone(connection, _SELECT_GEOLITE_LOCATION_QUERY, (int(block_row[0]),))
        if not location_row:
            return None

        city, state, country, flag, lat, lng = location_row
        return GeoIpLocation(
            flag="" if flag is None else str(flag),
            country="" if country is None else str(country),
            city="" if city is None else str(city),
            state="" if state is None else str(state),
            lat=None if lat in (None, "") else float(lat),
            lng=None if lng in (None, "") else float(lng),
        )

    def _update_player_geoip(
        self, connection: SupportsConnection, player_id: int, location: GeoIpLocation
    ) -> int:
        return self._execute(
            connection,
            _UPDATE_PLAYER_GEOIP_QUERY,
            (
                location.flag,
                location.country,
                location.lat,
                location.lng,
                location.city,
                location.state,
                player_id,
            ),
        )

    def _normalise_ipv4(self, raw_address: object) -> str | None:
        text = str(raw_address).strip()
        if not text:
            return None
        try:
            return str(ipaddress.IPv4Address(text))
        except ipaddress.AddressValueError:
            return None

    def _log_verbose(self, message: str) -> None:
        if self._verbose:
            print(message)

    # ------------------------------------------------------------------
    # Awards calculation
    # ------------------------------------------------------------------
    def _process_awards(
        self,
        connection: SupportsConnection,
        num_days: int,
        base_date: date | None,
    ) -> None:
        date_sql = self._date_base_sql(base_date)
        awards = [
            AwardDefinition(*row)
            for row in self._fetchall(connection, _AWARD_SELECTION_QUERY)
        ]

        option_row = self._fetchone(
            connection,
            f"""
            SELECT value, DATE_SUB({date_sql}, INTERVAL 1 DAY)
            FROM hlstats_Options
            WHERE keyname = 'awards_d_date'
            """,
        )

        if option_row:
            _, new_date = option_row
            self._execute(
                connection,
                """
                UPDATE hlstats_Options
                SET value = %s
                WHERE keyname = 'awards_d_date'
                """,
                (new_date,),
            )
        else:
            self._execute(
                connection,
                f"""
                INSERT INTO hlstats_Options (keyname, value, opttype)
                VALUES ('awards_d_date', DATE_SUB({date_sql}, INTERVAL 1 DAY), 2)
                """,
            )

        self._execute(
            connection,
            """
            REPLACE INTO hlstats_Options (keyname, value, opttype)
            VALUES ('awards_numdays', %s, 2)
            """,
            (num_days,),
        )

        daily_queries = AwardQueryBuilder(
            num_days=num_days,
            date_sql=date_sql,
            include_hidden_players=self._policy.include_hidden_players,
        )

        for award in awards:
            (
                daily_query,
                daily_params,
                global_query,
                global_params,
            ) = daily_queries.build_queries(award)

            daily_row = self._fetchone(connection, daily_query, daily_params)
            global_row = self._fetchone(connection, global_query, global_params)

            daily_winner = _normalise_winner(daily_row)
            global_winner = _normalise_winner(global_row)

            self._execute(
                connection,
                """
                UPDATE hlstats_Awards
                SET d_winner_id = %s,
                    d_winner_count = %s,
                    g_winner_id = %s,
                    g_winner_count = %s
                WHERE awardId = %s
                """,
                (
                    daily_winner.player_id,
                    daily_winner.count,
                    global_winner.player_id,
                    global_winner.count,
                    award.award_id,
                ),
            )

            if self._report is not None:
                self._report.awards.append(
                    AwardResult(award, daily_winner, global_winner)
                )

        inserted = self._execute(
            connection,
            """
            INSERT IGNORE INTO hlstats_Players_Awards
            SELECT value, awardId, d_winner_id, d_winner_count, game
            FROM hlstats_Options
            INNER JOIN hlstats_Awards
              ON keyname = 'awards_d_date'
             AND NOT ISNULL(d_winner_id)
            """,
        )

        if self._report is not None:
            self._report.player_awards_synced += inserted

    # ------------------------------------------------------------------
    # Ribbons
    # ------------------------------------------------------------------
    def _process_ribbons(self, connection: SupportsConnection) -> None:
        hidden_filter = "" if self._policy.include_hidden_players else "AND hlstats_Players.hideranking = 0"
        games = self._fetchall(connection, "SELECT code FROM hlstats_Games")
        for (game,) in games:
            cleared = self._execute(
                connection,
                "DELETE FROM hlstats_Players_Ribbons WHERE game = %s",
                (game,),
            )
            if self._report is not None and cleared:
                self._report.ribbons_cleared[game] = (
                    self._report.ribbons_cleared.get(game, 0) + cleared
                )
            ribbons = self._fetchall(
                connection,
                """
                SELECT ribbonId, awardCode, awardCount, special
                FROM hlstats_Ribbons
                WHERE game = %s AND (special = 0 OR special = 2)
                """,
                (game,),
            )
            inserted_total = 0
            for ribbon_id, code, count, special in ribbons:
                if special == 2:
                    query = (
                        f"""
                        SELECT playerId, (connection_time / 3600) AS CNT
                        FROM hlstats_Players
                        WHERE game = %s
                          {hidden_filter}
                          AND (connection_time / 3600) >= %s
                        """,
                        (game, count),
                    )
                else:
                    query = (
                        f"""
                        SELECT hlstats_Players_Awards.playerId,
                               COUNT(hlstats_Players_Awards.playerId) AS CNT
                        FROM hlstats_Players_Awards
                        INNER JOIN hlstats_Awards
                          ON (hlstats_Awards.awardId = hlstats_Players_Awards.awardId
                              AND hlstats_Awards.game = hlstats_Players_Awards.game)
                        INNER JOIN hlstats_Players
                          ON (hlstats_Players.playerId = hlstats_Players_Awards.playerId
                              {hidden_filter})
                        WHERE hlstats_Players_Awards.game = %s
                          AND hlstats_Awards.code = %s
                          AND hlstats_Awards.awardType <> 'V'
                        GROUP BY hlstats_Players_Awards.playerId
                        HAVING CNT >= %s
                        """,
                        (game, code, count),
                )
                eligible = self._fetchall(connection, *query)
                for player_id, _ in eligible:
                    inserted_total += self._execute(
                        connection,
                        """
                        INSERT INTO hlstats_Players_Ribbons (playerId, ribbonId, game)
                        VALUES (%s, %s, %s)
                        """,
                        (player_id, ribbon_id, game),
                    )
            if self._report is not None and inserted_total:
                self._report.ribbons_awarded[game] = (
                    self._report.ribbons_awarded.get(game, 0) + inserted_total
                )

    # ------------------------------------------------------------------
    # Pruning and maintenance
    # ------------------------------------------------------------------
    def _prune_events(self, connection: SupportsConnection) -> None:
        row = self._fetchone(
            connection,
            "SELECT value FROM hlstats_Options WHERE keyname = 'DeleteDays'",
        )
        if not row or row[0] in (None, ""):
            return

        delete_days = int(row[0])
        for table in _EVENT_TABLES:
            deleted = self._execute(
                connection,
                f"""
                DELETE FROM hlstats_Events_{table}
                WHERE eventTime < DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL %s DAY)
                """,
                (delete_days,),
            )
            if self._report is not None and deleted:
                table_name = f"hlstats_Events_{table}"
                self._report.pruned_tables[table_name] = (
                    self._report.pruned_tables.get(table_name, 0) + deleted
                )

        deleted_history = self._execute(
            connection,
            """
            DELETE FROM hlstats_Players_History
            WHERE eventTime < DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL %s DAY)
            """,
            (delete_days,),
        )
        if self._report is not None and deleted_history:
            self._report.pruned_tables["hlstats_Players_History"] = (
                self._report.pruned_tables.get("hlstats_Players_History", 0) + deleted_history
            )

        deleted_trend = self._execute(
            connection,
            """
            DELETE FROM hlstats_Trend
            WHERE timestamp < (UNIX_TIMESTAMP() - 172800)
            """,
        )
        if self._report is not None and deleted_trend:
            self._report.pruned_tables["hlstats_Trend"] = (
                self._report.pruned_tables.get("hlstats_Trend", 0) + deleted_trend
            )

        deleted_load = self._execute(
            connection,
            """
            DELETE FROM hlstats_server_load
            WHERE timestamp < (UNIX_TIMESTAMP(CURRENT_TIMESTAMP() - INTERVAL 1 YEAR))
            """,
        )
        if self._report is not None and deleted_load:
            self._report.pruned_tables["hlstats_server_load"] = (
                self._report.pruned_tables.get("hlstats_server_load", 0) + deleted_load
            )

    def _optimize_tables(self, connection: SupportsConnection) -> None:
        tables = self._fetchall(connection, "SHOW TABLES")
        for (table,) in tables:
            self._execute(connection, f"OPTIMIZE TABLE {table}")
            if self._report is not None:
                self._report.optimized_tables.append(str(table))

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------
    def _execute(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[object] | None = None,
    ) -> int:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            rowcount = getattr(cursor, "rowcount", 0)
        finally:
            cursor.close()
        return 0 if rowcount is None else int(rowcount)

    def _fetchone(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[object] | None = None,
    ) -> Sequence[object] | None:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()

    def _fetchall(
        self,
        connection: SupportsConnection,
        query: str,
        params: Sequence[object] | None = None,
    ) -> list[Sequence[object]]:
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def _date_base_sql(self, base_date: date | None) -> str:
        if base_date is None:
            return "CURRENT_DATE()"
        return f"'{base_date.isoformat()}'"


_AWARD_SELECTION_QUERY = """
    SELECT
        hlstats_Awards.awardId,
        hlstats_Awards.game,
        hlstats_Awards.awardType,
        hlstats_Awards.code
    FROM hlstats_Awards
    LEFT JOIN hlstats_Games ON hlstats_Games.code = hlstats_Awards.game
    WHERE hlstats_Games.hidden = '0'
    ORDER BY hlstats_Awards.game, hlstats_Awards.awardType
"""


@dataclass(frozen=True, slots=True)
class AwardWinner:
    player_id: int | None
    count: int | None


def _normalise_winner(row: Sequence[object] | None) -> AwardWinner:
    if not row:
        return AwardWinner(None, None)
    player_id, value = row[0], row[1] if len(row) > 1 else None
    if value is None:
        return AwardWinner(int(player_id) if player_id is not None else None, None)
    try:
        count = int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return AwardWinner(int(player_id) if player_id is not None else None, None)
    if count < 1:
        return AwardWinner(None, None)
    return AwardWinner(int(player_id), count)


@dataclass(slots=True)
class AwardQueryBuilder:
    num_days: int
    date_sql: str
    include_hidden_players: bool = False

    def _visible_player_clause(self) -> str:
        if self.include_hidden_players:
            return ""
        return "AND hlstats_Players.hideranking = 0"

    def build_queries(
        self, award: AwardDefinition
    ) -> tuple[str, Sequence[object] | None, str, Sequence[object] | None]:
        if award.code == "latency":
            return (
                self._latency_daily(award.game),
                (award.game,),
                self._latency_global(award.game),
                (award.game,),
            )
        if award.code == "mostkills":
            return (
                self._history_stat_daily(award.game, "kills"),
                (award.game, self.num_days),
                self._player_stat_global(award.game, "kills"),
                (award.game,),
            )
        if award.code == "suicide":
            return (
                self._history_stat_daily(award.game, "suicides"),
                (award.game, self.num_days),
                self._player_stat_global(award.game, "suicides"),
                (award.game,),
            )
        if award.code == "teamkills":
            return (
                self._history_stat_daily(award.game, "teamkills"),
                (award.game, self.num_days),
                self._player_stat_global(award.game, "teamkills"),
                (award.game,),
            )
        if award.code == "bonuspoints":
            return (
                self._bonus_points_daily(award.game),
                (award.game,),
                self._bonus_points_global(award.game),
                (award.game,),
            )
        if award.code == "allsentrykills":
            return (
                self._sentry_kills_daily(award.game),
                (award.game,),
                self._sentry_kills_global(award.game),
                (award.game,),
            )
        if award.code == "connectiontime":
            return (
                self._history_stat_daily(award.game, "connection_time"),
                (award.game, self.num_days),
                self._player_stat_global(award.game, "connection_time"),
                (award.game,),
            )
        if award.code == "killstreak":
            return (
                self._history_stat_daily(award.game, "kill_streak"),
                (award.game, self.num_days),
                self._player_stat_global(award.game, "kill_streak"),
                (award.game,),
            )
        if award.code == "deathstreak":
            return (
                self._history_stat_daily(award.game, "death_streak"),
                (award.game, self.num_days),
                self._player_stat_global(award.game, "death_streak"),
                (award.game,),
            )

        context = _award_context(award)
        match_value = 1 if award.code == "headshot" else award.code
        return (
            self._generic_daily(context, match_value),
            (award.game, match_value),
            self._generic_global(context, match_value),
            (award.game, match_value),
        )

    # ------------------------------------------------------------------
    # Generic award queries
    # ------------------------------------------------------------------
    def _generic_daily(self, context: _AwardContext, _match_value: Any) -> str:
        return (
            f"""
            SELECT {context.player_field}, COUNT({context.match_field}) AS awardcount
            FROM {context.table}
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = {context.player_field}
             {self._visible_player_clause()}
            {context.join}
            WHERE {context.table}.eventTime < {self.date_sql}
              AND {context.table}.eventTime > DATE_SUB(
                  {self.date_sql}, INTERVAL {self.num_days} DAY
              )
              AND hlstats_Players.game = %s
              AND {context.match_field} = %s
            GROUP BY {context.player_field}
            ORDER BY awardcount DESC, hlstats_Players.skill DESC
            LIMIT 1
            """
        )

    def _generic_global(self, context: _AwardContext, _match_value: Any) -> str:
        return (
            f"""
            SELECT {context.player_field}, COUNT({context.match_field}) AS awardcount
            FROM {context.table}
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = {context.player_field}
             {self._visible_player_clause()}
            {context.join}
            WHERE hlstats_Players.game = %s
              AND {context.match_field} = %s
            GROUP BY {context.player_field}
            ORDER BY awardcount DESC, hlstats_Players.skill DESC
            LIMIT 1
            """
        )

    # ------------------------------------------------------------------
    # Special case builders
    # ------------------------------------------------------------------
    def _latency_daily(self, game: str) -> str:
        return (
            f"""
            SELECT hlstats_Events_Latency.playerId,
                   ROUND(ROUND(SUM(ping) / COUNT(ping), 0) / 2, 0) AS av_latency
            FROM hlstats_Events_Latency
            INNER JOIN hlstats_Servers
              ON hlstats_Servers.serverId = hlstats_Events_Latency.serverId
             AND hlstats_Servers.game = %s
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = hlstats_Events_Latency.playerId
             {self._visible_player_clause()}
            WHERE hlstats_Events_Latency.eventTime < {self.date_sql}
              AND hlstats_Events_Latency.eventTime > DATE_SUB(
                  {self.date_sql}, INTERVAL {self.num_days} DAY
              )
            GROUP BY hlstats_Events_Latency.playerId
            ORDER BY av_latency
            LIMIT 1
            """
        )

    def _latency_global(self, game: str) -> str:
        return (
            f"""
            SELECT hlstats_Events_Latency.playerId,
                   ROUND(ROUND(SUM(ping) / COUNT(ping), 0) / 2, 0) AS av_latency
            FROM hlstats_Events_Latency
            INNER JOIN hlstats_Servers
              ON hlstats_Servers.serverId = hlstats_Events_Latency.serverId
             AND hlstats_Servers.game = %s
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = hlstats_Events_Latency.playerId
             {self._visible_player_clause()}
            GROUP BY hlstats_Events_Latency.playerId
            ORDER BY av_latency
            LIMIT 1
            """
        )

    def _history_stat_daily(self, game: str, column: str) -> str:
        return (
            f"""
            SELECT hlstats_Players_History.playerId,
                   hlstats_Players_History.{column}
            FROM hlstats_Players_History, hlstats_Players
            WHERE hlstats_Players_History.game = %s
              AND hlstats_Players.playerId = hlstats_Players_History.playerId
              {self._visible_player_clause()}
              AND eventTime = DATE_SUB({self.date_sql}, INTERVAL %s DAY)
            ORDER BY hlstats_Players_History.{column} DESC
            LIMIT 1
            """
        )

    def _player_stat_global(self, game: str, column: str) -> str:
        return (
            f"""
            SELECT playerId, {column}
            FROM hlstats_Players
            WHERE hlstats_Players.game = %s
              {self._visible_player_clause()}
            ORDER BY {column} DESC
            LIMIT 1
            """
        )

    def _bonus_points_daily(self, game: str) -> str:
        return (
            f"""
            SELECT actions.playerId, SUM(actions.bonus) AS av_bonuspoints
            FROM (
                SELECT playerId, bonus, serverId, eventTime
                FROM hlstats_Events_PlayerActions
                WHERE eventTime < {self.date_sql}
                  AND eventTime > DATE_SUB({self.date_sql}, INTERVAL {self.num_days} DAY)
                UNION ALL
                SELECT playerId, bonus, serverId, eventTime
                FROM hlstats_Events_PlayerPlayerActions
                WHERE eventTime < {self.date_sql}
                  AND eventTime > DATE_SUB({self.date_sql}, INTERVAL {self.num_days} DAY)
            ) AS actions
            INNER JOIN hlstats_Servers
              ON hlstats_Servers.serverId = actions.serverId
             AND hlstats_Servers.game = %s
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = actions.playerId
             {self._visible_player_clause()}
            GROUP BY playerId
            ORDER BY av_bonuspoints DESC
            LIMIT 1
            """
        )

    def _bonus_points_global(self, game: str) -> str:
        return (
            f"""
            SELECT actions.playerId, SUM(actions.bonus) AS av_bonuspoints
            FROM (
                SELECT playerId, bonus, serverId, eventTime
                FROM hlstats_Events_PlayerActions
                UNION ALL
                SELECT playerId, bonus, serverId, eventTime
                FROM hlstats_Events_PlayerPlayerActions
            ) AS actions
            INNER JOIN hlstats_Servers
              ON hlstats_Servers.serverId = actions.serverId
             AND hlstats_Servers.game = %s
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = actions.playerId
             {self._visible_player_clause()}
            GROUP BY playerId
            ORDER BY av_bonuspoints DESC
            LIMIT 1
            """
        )

    def _sentry_kills_daily(self, game: str) -> str:
        return (
            f"""
            SELECT hlstats_Events_Frags.killerId, COUNT(hlstats_Events_Frags.weapon) AS awardcount
            FROM hlstats_Events_Frags
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = hlstats_Events_Frags.killerId
             {self._visible_player_clause()}
            WHERE hlstats_Events_Frags.eventTime < {self.date_sql}
              AND hlstats_Events_Frags.eventTime > DATE_SUB(
                  {self.date_sql}, INTERVAL {self.num_days} DAY
              )
              AND hlstats_Players.game = %s
              AND hlstats_Events_Frags.weapon LIKE 'obj_sentrygun%'
            GROUP BY hlstats_Events_Frags.killerId
            ORDER BY awardcount DESC, hlstats_Players.skill DESC
            LIMIT 1
            """
        )

    def _sentry_kills_global(self, game: str) -> str:
        return (
            f"""
            SELECT hlstats_Events_Frags.killerId, COUNT(hlstats_Events_Frags.weapon) AS awardcount
            FROM hlstats_Events_Frags
            INNER JOIN hlstats_Players
              ON hlstats_Players.playerId = hlstats_Events_Frags.killerId
             {self._visible_player_clause()}
            WHERE hlstats_Players.game = %s
              AND hlstats_Events_Frags.weapon LIKE 'obj_sentrygun%'
            GROUP BY hlstats_Events_Frags.killerId
            ORDER BY awardcount DESC, hlstats_Players.skill DESC
            LIMIT 1
            """
        )


@dataclass(frozen=True, slots=True)
class _AwardContext:
    table: str
    join: str
    match_field: str
    player_field: str


def _award_context(award: AwardDefinition) -> _AwardContext:
    if award.award_type == "O":
        return _AwardContext(
            table="hlstats_Events_PlayerActions",
            join=(
                "LEFT JOIN hlstats_Actions ON "
                "hlstats_Actions.id = hlstats_Events_PlayerActions.actionId"
            ),
            match_field="hlstats_Actions.code",
            player_field="hlstats_Events_PlayerActions.playerId",
        )
    if award.award_type == "W":
        if award.code == "headshot":
            return _AwardContext(
                table="hlstats_Events_Frags",
                join="",
                match_field="hlstats_Events_Frags.headshot",
                player_field="hlstats_Events_Frags.killerId",
            )
        return _AwardContext(
            table="hlstats_Events_Frags",
            join="",
            match_field="hlstats_Events_Frags.weapon",
            player_field="hlstats_Events_Frags.killerId",
        )
    if award.award_type == "P":
        return _AwardContext(
            table="hlstats_Events_PlayerPlayerActions",
            join=(
                "LEFT JOIN hlstats_Actions ON "
                "hlstats_Actions.id = hlstats_Events_PlayerPlayerActions.actionId"
            ),
            match_field="hlstats_Actions.code",
            player_field="hlstats_Events_PlayerPlayerActions.playerId",
        )
    if award.award_type == "V":
        return _AwardContext(
            table="hlstats_Events_PlayerPlayerActions",
            join=(
                "LEFT JOIN hlstats_Actions ON "
                "hlstats_Actions.id = hlstats_Events_PlayerPlayerActions.actionId"
            ),
            match_field="hlstats_Actions.code",
            player_field="hlstats_Events_PlayerPlayerActions.victimId",
        )
    raise ValueError(f"Unsupported award type: {award.award_type}")


def build_database_config(settings: RuntimeSettings) -> DaemonDatabaseConfig:
    """Convert :class:`RuntimeSettings` DB info into :class:`DatabaseConfig`."""

    host = settings.database.host.strip()
    port = 3306
    if ":" in host:
        host, port_text = host.rsplit(":", 1)
        port = int(port_text)
    if not host:
        raise ValueError("Database host must be provided")

    return DaemonDatabaseConfig(
        host=host,
        port=port,
        username=settings.database.username,
        password=settings.database.password,
        database=settings.database.name,
    )


__all__ = [
    "AwardsCalculator",
    "AwardDefinition",
    "build_database_config",
]
