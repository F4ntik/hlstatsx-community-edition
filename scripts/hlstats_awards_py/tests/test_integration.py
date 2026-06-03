from __future__ import annotations

from datetime import date

from hlstats_awards_py import cli
from hlstats_awards_py.calculator import (
    _SELECT_GEOLITE_BLOCK_QUERY,
    _SELECT_GEOLITE_BLOCKS_SMOKE_QUERY,
    _SELECT_GEOLITE_LOCATION_QUERY,
    _SELECT_GEOIP_CANDIDATES_QUERY,
    _SELECT_USE_GEOIP_BINARY_QUERY,
    _UPDATE_PLAYER_GEOIP_QUERY,
    _AWARD_SELECTION_QUERY,
    AwardDefinition,
    AwardQueryBuilder,
    AwardResult,
    AwardsCalculator,
    AwardsReport,
    AwardWinner,
)

from .util import FakeConnection, QueryResponse, StubAdapter, normalize_sql

UPDATE_ACTIVITY_NOW = normalize_sql(
    """
    UPDATE hlstats_Players
    SET activity = IF(
        (%s > TIMESTAMPDIFF(SECOND, hlstats_Players.last_event, NOW())),
        ((100 / %s) * (%s - TIMESTAMPDIFF(SECOND, hlstats_Players.last_event, NOW()))),
        -1
    )
    """
)

HIDE_INACTIVE_QUERY = normalize_sql(
    """
    UPDATE hlstats_Players
    SET hideranking = 3
    WHERE hideranking = 0 AND activity < 0
    """
)

RIBBON_ELIGIBLE_AWARDS = normalize_sql(
    """
    SELECT hlstats_Players_Awards.playerId,
           COUNT(hlstats_Players_Awards.playerId) AS CNT
    FROM hlstats_Players_Awards
    INNER JOIN hlstats_Awards
      ON (hlstats_Awards.awardId = hlstats_Players_Awards.awardId
          AND hlstats_Awards.game = hlstats_Players_Awards.game)
    INNER JOIN hlstats_Players
      ON (hlstats_Players.playerId = hlstats_Players_Awards.playerId
          AND hlstats_Players.hideranking = 0)
    WHERE hlstats_Players_Awards.game = %s
      AND hlstats_Awards.code = %s
      AND hlstats_Awards.awardType <> 'V'
    GROUP BY hlstats_Players_Awards.playerId
    HAVING CNT >= %s
    """
)

RIBBON_ELIGIBLE_CONNECTION = normalize_sql(
    """
    SELECT playerId, (connection_time / 3600) AS CNT
    FROM hlstats_Players
    WHERE game = %s
      AND hlstats_Players.hideranking = 0
      AND (connection_time / 3600) >= %s
    """
)


def test_full_awards_run_populates_report() -> None:
    award_rows = [
        (1, "tf2", "W", "mostkills"),
        (2, "tf2", "B", "bonuspoints"),
    ]
    num_days = 7
    builder = AwardQueryBuilder(num_days=num_days, date_sql="CURRENT_DATE()")
    awards = [AwardDefinition(*row) for row in award_rows]

    responses = {
        (normalize_sql("SELECT value FROM hlstats_Options WHERE keyname = 'MinActivity'"), None): [
            QueryResponse(fetchone=("7",))
        ],
        (normalize_sql("SELECT value FROM hlstats_Options WHERE keyname = 'UseTimestamp'"), None): [
            QueryResponse(fetchone=("0",))
        ],
        (UPDATE_ACTIVITY_NOW, (604800, 604800, 604800)): [QueryResponse(rowcount=5)],
        (HIDE_INACTIVE_QUERY, None): [QueryResponse(rowcount=2)],
        (normalize_sql(_AWARD_SELECTION_QUERY), None): [
            QueryResponse(fetchall=award_rows)
        ],
        (
            normalize_sql(
                """
                SELECT value, DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
                FROM hlstats_Options
                WHERE keyname = 'awards_d_date'
                """
            ),
            None,
        ): [QueryResponse(fetchone=("2024-02-09", date(2024, 2, 8)))],
        (
            normalize_sql(
                """
                UPDATE hlstats_Options
                SET value = %s
                WHERE keyname = 'awards_d_date'
                """
            ),
            (date(2024, 2, 8),),
        ): [QueryResponse(rowcount=1)],
        (
            normalize_sql(
                """
                REPLACE INTO hlstats_Options (keyname, value, opttype)
                VALUES ('awards_numdays', %s, 2)
                """
            ),
            (num_days,),
        ): [QueryResponse(rowcount=1)],
        (normalize_sql("SELECT code FROM hlstats_Games"), None): [
            QueryResponse(fetchall=[("tf2",)])
        ],
        (normalize_sql("DELETE FROM hlstats_Players_Ribbons WHERE game = %s"), ("tf2",)): [
            QueryResponse(rowcount=4)
        ],
        (
            normalize_sql(
                """
                SELECT ribbonId, awardCode, awardCount, special
                FROM hlstats_Ribbons
                WHERE game = %s AND (special = 0 OR special = 2)
                """
            ),
            ("tf2",),
        ): [
            QueryResponse(
                fetchall=[
                    (10, "mostkills", 3, 0),
                    (11, "", 100, 2),
                ]
            )
        ],
        (RIBBON_ELIGIBLE_AWARDS, ("tf2", "mostkills", 3)): [
            QueryResponse(fetchall=[(111, 3), (222, 4)])
        ],
        (RIBBON_ELIGIBLE_CONNECTION, ("tf2", 100)): [
            QueryResponse(fetchall=[(333, 120)])
        ],
        (
            normalize_sql(
                """
                SELECT value FROM hlstats_Options WHERE keyname = 'DeleteDays'
                """
            ),
            None,
        ): [QueryResponse(fetchone=("30",))],
        (
            normalize_sql(
                """
                DELETE FROM hlstats_Events_TeamBonuses
                WHERE eventTime < DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL %s DAY)
                """
            ),
            (30,),
        ): [QueryResponse(rowcount=5)],
        (
            normalize_sql(
                """
                DELETE FROM hlstats_Events_Frags
                WHERE eventTime < DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL %s DAY)
                """
            ),
            (30,),
        ): [QueryResponse(rowcount=1)],
        (
            normalize_sql(
                """
                DELETE FROM hlstats_Players_History
                WHERE eventTime < DATE_SUB(CURRENT_TIMESTAMP(), INTERVAL %s DAY)
                """
            ),
            (30,),
        ): [QueryResponse(rowcount=7)],
        (
            normalize_sql(
                """
                DELETE FROM hlstats_Trend
                WHERE timestamp < (UNIX_TIMESTAMP() - 172800)
                """
            ),
            None,
        ): [QueryResponse(rowcount=3)],
        (
            normalize_sql(
                """
                DELETE FROM hlstats_server_load
                WHERE timestamp < (UNIX_TIMESTAMP(CURRENT_TIMESTAMP() - INTERVAL 1 YEAR))
                """
            ),
            None,
        ): [QueryResponse(rowcount=1)],
        (normalize_sql("SHOW TABLES"), None): [
            QueryResponse(fetchall=[("hlstats_Players",), ("hlstats_Awards",)])
        ],
        (normalize_sql("OPTIMIZE TABLE hlstats_Players"), None): [QueryResponse()],
        (normalize_sql("OPTIMIZE TABLE hlstats_Awards"), None): [QueryResponse()],
        (
            normalize_sql(
                """
                INSERT IGNORE INTO hlstats_Players_Awards
                SELECT value, awardId, d_winner_id, d_winner_count, game
                FROM hlstats_Options
                INNER JOIN hlstats_Awards
                  ON keyname = 'awards_d_date'
                 AND NOT ISNULL(d_winner_id)
                """
            ),
            None,
        ): [QueryResponse(rowcount=2)],
    }

    for award in awards:
        daily_query, daily_params, global_query, global_params = builder.build_queries(award)
        daily_key = (
            normalize_sql(daily_query),
            tuple(daily_params) if daily_params else None,
        )
        responses[daily_key] = [
            QueryResponse(fetchone=((award.award_id * 100) + 11, 15))
        ]
        global_key = (
            normalize_sql(global_query),
            tuple(global_params) if global_params else None,
        )
        responses[global_key] = [
            QueryResponse(fetchone=((award.award_id * 100) + 22, 45))
        ]
        responses[
            (
                normalize_sql(
                    """
                    UPDATE hlstats_Awards
                    SET d_winner_id = %s,
                        d_winner_count = %s,
                        g_winner_id = %s,
                        g_winner_count = %s
                    WHERE awardId = %s
                    """
                ),
                (
                    (award.award_id * 100) + 11,
                    15,
                    (award.award_id * 100) + 22,
                    45,
                    award.award_id,
                ),
            )
        ] = [QueryResponse(rowcount=1)]

    insert_ribbon_sql = normalize_sql(
        """
        INSERT INTO hlstats_Players_Ribbons (playerId, ribbonId, game)
        VALUES (%s, %s, %s)
        """
    )
    responses[(insert_ribbon_sql, (111, 10, "tf2"))] = [QueryResponse(rowcount=1)]
    responses[(insert_ribbon_sql, (222, 10, "tf2"))] = [QueryResponse(rowcount=1)]
    responses[(insert_ribbon_sql, (333, 11, "tf2"))] = [QueryResponse(rowcount=1)]

    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    report = AwardsReport()
    calculator = AwardsCalculator(adapter, report=report)  # type: ignore[arg-type]

    cli_options = cli.CliOptions(
        configfile=None,
        requested_actions=(),
        numdays=num_days,
        date=None,
        db_host=None,
        db_name=None,
        db_username=None,
        db_password=None,
        verbose=False,
        replay_mode=False,
        version=False,
    )

    settings = cli.RuntimeSettings(
        cli=cli_options,
        actions=frozenset(
            {
                cli.AwardsAction.INACTIVE,
                cli.AwardsAction.AWARDS,
                cli.AwardsAction.RIBBONS,
                cli.AwardsAction.PRUNE,
                cli.AwardsAction.OPTIMIZE,
            }
        ),
        database=cli.DatabaseConfig(
            host="localhost",
            name="hlstats",
            username="hlx",
            password="secret",
            cpanel_hack=False,
        ),
        config_path=None,
        policy=cli.RuntimePolicy.STRICT,
    )

    calculator.run(settings)

    assert report.inactive_updates == 5
    assert report.players_hidden == 2
    assert [result.definition.award_id for result in report.awards] == [1, 2]
    assert all(isinstance(result, AwardResult) for result in report.awards)
    assert report.awards[0].daily == AwardWinner(111, 15)
    assert report.awards[1].overall == AwardWinner(222, 45)
    assert report.player_awards_synced == 2
    assert report.ribbons_cleared["tf2"] == 4
    assert report.ribbons_awarded["tf2"] == 3
    assert report.pruned_tables["hlstats_Events_TeamBonuses"] == 5
    assert report.pruned_tables["hlstats_Events_Frags"] == 1
    assert report.pruned_tables["hlstats_Players_History"] == 7
    assert report.pruned_tables["hlstats_Trend"] == 3
    assert report.pruned_tables["hlstats_server_load"] == 1
    assert report.optimized_tables == ["hlstats_Players", "hlstats_Awards"]


def test_geoip_action_updates_report() -> None:
    responses = {
        (normalize_sql(_SELECT_USE_GEOIP_BINARY_QUERY), None): [QueryResponse(fetchone=None)],
        (normalize_sql(_SELECT_GEOIP_CANDIDATES_QUERY), None): [
            QueryResponse(fetchall=[(9, "8.8.8.8", "Geo")])
        ],
        (normalize_sql(_SELECT_GEOLITE_BLOCKS_SMOKE_QUERY), None): [QueryResponse(fetchone=(42,))],
        (
            normalize_sql(_SELECT_GEOLITE_BLOCK_QUERY),
            (134744072, 134744072),
        ): [QueryResponse(fetchone=(42,))],
        (
            normalize_sql(_SELECT_GEOLITE_LOCATION_QUERY),
            (42,),
        ): [QueryResponse(fetchone=("Mountain View", "California", "United States", "US", 37.386, -122.0838))],
        (
            normalize_sql(_UPDATE_PLAYER_GEOIP_QUERY),
            ("US", "United States", 37.386, -122.0838, "Mountain View", "California", 9),
        ): [QueryResponse(rowcount=1)],
    }

    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    report = AwardsReport()
    calculator = AwardsCalculator(adapter, report=report)  # type: ignore[arg-type]

    cli_options = cli.CliOptions(
        configfile=None,
        requested_actions=(cli.AwardsAction.GEOIP,),
        numdays=1,
        date=None,
        db_host=None,
        db_name=None,
        db_username=None,
        db_password=None,
        verbose=False,
        replay_mode=False,
        version=False,
    )

    settings = cli.RuntimeSettings(
        cli=cli_options,
        actions=frozenset({cli.AwardsAction.GEOIP}),
        database=cli.DatabaseConfig(
            host="localhost",
            name="hlstats",
            username="hlx",
            password="secret",
            cpanel_hack=False,
        ),
        config_path=None,
        policy=cli.RuntimePolicy.STRICT,
    )

    calculator.run(settings)

    assert report.geoip_updates == 1
