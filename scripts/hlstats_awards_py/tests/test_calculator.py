from __future__ import annotations

import pytest

from hlstats_awards_py import cli
from hlstats_awards_py.calculator import (
    _AWARD_SELECTION_QUERY,
    _SELECT_GEOLITE_BLOCK_QUERY,
    _SELECT_GEOLITE_BLOCKS_SMOKE_QUERY,
    _SELECT_GEOLITE_LOCATION_QUERY,
    _SELECT_GEOIP_CANDIDATES_QUERY,
    _SELECT_USE_GEOIP_BINARY_QUERY,
    _UPDATE_PLAYER_GEOIP_QUERY,
    AwardDefinition,
    AwardQueryBuilder,
    AwardsCalculator,
    AwardsReport,
    build_database_config,
)

from .util import FakeConnection, QueryResponse, StubAdapter, normalize_sql

UPDATE_ACTIVITY_NOW = normalize_sql(
    "UPDATE hlstats_Players SET activity = IF("
    " (%s > (UNIX_TIMESTAMP() - hlstats_Players.last_event)),"
    " ((100 / %s) * (%s - (UNIX_TIMESTAMP() - hlstats_Players.last_event))),"
    " -1 )"
)

UPDATE_ACTIVITY_WITH_LAST = normalize_sql(
    "UPDATE hlstats_Players SET activity = IF("
    " (%s > (%s - hlstats_Players.last_event)),"
    " ((100 / %s) * (%s - (%s - hlstats_Players.last_event))),"
    " -1 ) WHERE hlstats_Players.game = %s"
)

HIDE_INACTIVE_QUERY = normalize_sql(
    """
    UPDATE hlstats_Players
    SET hideranking = 3
    WHERE hideranking = 0 AND activity < 0
    """
)

SELECT_AWARDS_DATE = normalize_sql(
    """
    SELECT value, DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    FROM hlstats_Options
    WHERE keyname = 'awards_d_date'
    """
)

UPDATE_AWARDS_DATE = normalize_sql(
    """
    UPDATE hlstats_Options
    SET value = %s
    WHERE keyname = 'awards_d_date'
    """
)

REPLACE_AWARDS_NUMDAYS = normalize_sql(
    """
    REPLACE INTO hlstats_Options (keyname, value, opttype)
    VALUES ('awards_numdays', %s, 2)
    """
)

UPDATE_AWARDS_WINNERS = normalize_sql(
    """
    UPDATE hlstats_Awards
    SET d_winner_id = %s,
        d_winner_count = %s,
        g_winner_id = %s,
        g_winner_count = %s
    WHERE awardId = %s
    """
)

INSERT_PLAYER_AWARDS = normalize_sql(
    """
    INSERT IGNORE INTO hlstats_Players_Awards
    SELECT value, awardId, d_winner_id, d_winner_count, game
    FROM hlstats_Options
    INNER JOIN hlstats_Awards
      ON keyname = 'awards_d_date' AND NOT ISNULL(d_winner_id)
    """
)


def _runtime_settings(
    actions: tuple[cli.AwardsAction, ...],
    policy: cli.RuntimePolicy = cli.RuntimePolicy.STRICT,
) -> cli.RuntimeSettings:
    return cli.RuntimeSettings(
        cli=cli.CliOptions(
            configfile=None,
            requested_actions=actions,
            numdays=1,
            date=None,
            db_host=None,
            db_name=None,
            db_username=None,
            db_password=None,
            verbose=False,
            replay_mode=policy is cli.RuntimePolicy.REPLAY_SAFE,
            version=False,
        ),
        actions=frozenset(actions),
        database=cli.DatabaseConfig(
            host="localhost",
            name="hlstats",
            username="hlx",
            password="secret",
            cpanel_hack=False,
        ),
        config_path=None,
        policy=policy,
    )


def test_run_executes_selected_actions_in_legacy_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calculator = AwardsCalculator(StubAdapter(FakeConnection({})))  # type: ignore[arg-type]
    executed: list[str] = []

    monkeypatch.setattr(calculator, "_prune_events", lambda *_: executed.append("prune"))
    monkeypatch.setattr(calculator, "_optimize_tables", lambda *_: executed.append("optimize"))
    monkeypatch.setattr(
        calculator, "_update_player_activity", lambda *_: executed.append("inactive")
    )
    monkeypatch.setattr(calculator, "_process_awards", lambda *_: executed.append("awards"))
    monkeypatch.setattr(calculator, "_process_ribbons", lambda *_: executed.append("ribbons"))
    monkeypatch.setattr(calculator, "_process_geoip", lambda *_: executed.append("geoip"))

    calculator.run(
        _runtime_settings(
            (
                cli.AwardsAction.GEOIP,
                cli.AwardsAction.RIBBONS,
                cli.AwardsAction.AWARDS,
                cli.AwardsAction.INACTIVE,
                cli.AwardsAction.OPTIMIZE,
                cli.AwardsAction.PRUNE,
            )
        )
    )

    assert executed == ["prune", "optimize", "inactive", "awards", "ribbons", "geoip"]


@pytest.mark.parametrize(
    ("policy", "raises_error"),
    [
        (cli.RuntimePolicy.STRICT, True),
        (cli.RuntimePolicy.REPLAY_SAFE, False),
    ],
)
def test_geoip_error_follows_awards_and_ribbons(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    policy: cli.RuntimePolicy,
    raises_error: bool,
) -> None:
    calculator = AwardsCalculator(StubAdapter(FakeConnection({})))  # type: ignore[arg-type]
    executed: list[str] = []

    monkeypatch.setattr(calculator, "_process_awards", lambda *_: executed.append("awards"))
    monkeypatch.setattr(calculator, "_process_ribbons", lambda *_: executed.append("ribbons"))

    def fail_geoip(*_: object) -> None:
        executed.append("geoip")
        raise RuntimeError("GeoIP unavailable")

    monkeypatch.setattr(calculator, "_process_geoip", fail_geoip)

    settings = _runtime_settings(
        (
            cli.AwardsAction.AWARDS,
            cli.AwardsAction.RIBBONS,
            cli.AwardsAction.GEOIP,
        ),
        policy=policy,
    )
    if raises_error:
        with pytest.raises(RuntimeError, match="GeoIP unavailable"):
            calculator.run(settings)
    else:
        calculator.run(settings)
        warning = capsys.readouterr().out
        assert "warning: GeoIP unavailable; skipping GeoIP in replay-safe mode" in warning

    assert executed == ["awards", "ribbons", "geoip"]


def test_update_player_activity_without_timestamp() -> None:
    responses = {
        (normalize_sql("SELECT value FROM hlstats_Options WHERE keyname = 'MinActivity'"), None): [
            QueryResponse(fetchone=("30",))
        ],
        (normalize_sql("SELECT value FROM hlstats_Options WHERE keyname = 'UseTimestamp'"), None): [
            QueryResponse(fetchone=("0",))
        ],
        (
            UPDATE_ACTIVITY_NOW,
            (2592000, 2592000, 2592000),
        ): [QueryResponse()],
        (
            HIDE_INACTIVE_QUERY,
            None,
        ): [QueryResponse()],
    }
    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    calculator = AwardsCalculator(adapter)  # type: ignore[arg-type]

    calculator._update_player_activity(connection)

    assert (HIDE_INACTIVE_QUERY, None) in connection.executed


def test_update_player_activity_with_timestamp_per_game() -> None:
    responses = {
        (normalize_sql("SELECT value FROM hlstats_Options WHERE keyname = 'MinActivity'"), None): [
            QueryResponse(fetchone=("28",))
        ],
        (normalize_sql("SELECT value FROM hlstats_Options WHERE keyname = 'UseTimestamp'"), None): [
            QueryResponse(fetchone=("1",))
        ],
        (
            normalize_sql("SELECT game, MAX(last_event) FROM hlstats_Servers GROUP BY game"),
            None,
        ): [QueryResponse(fetchall=[("tf2", 1706745600), ("csgo", None)])],
        (
            UPDATE_ACTIVITY_WITH_LAST,
            (2419200, 1706745600, 2419200, 2419200, 1706745600, "tf2"),
        ): [QueryResponse()],
        (
            HIDE_INACTIVE_QUERY,
            None,
        ): [QueryResponse()],
    }
    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    calculator = AwardsCalculator(adapter)  # type: ignore[arg-type]

    calculator._update_player_activity(connection)

    executed_queries = [entry[0] for entry in connection.executed]
    assert UPDATE_ACTIVITY_WITH_LAST in executed_queries
    assert "TIMESTAMPDIFF" not in UPDATE_ACTIVITY_WITH_LAST
    assert "(%s - hlstats_Players.last_event)" in UPDATE_ACTIVITY_WITH_LAST
    assert (
        UPDATE_ACTIVITY_WITH_LAST,
        (2419200, 1706745600, 2419200, 2419200, 1706745600, "tf2"),
    ) in connection.executed


def test_award_query_builder_handles_special_cases() -> None:
    builder = AwardQueryBuilder(num_days=3, date_sql="CURRENT_DATE()")
    award = AwardDefinition(1, "tf2", "O", "latency")
    daily, daily_params, global_query, global_params = builder.build_queries(award)
    assert "hlstats_Events_Latency" in daily
    assert daily_params == ("tf2",)
    assert "hlstats_Events_Latency" in global_query
    assert global_params == ("tf2",)


def test_award_query_builder_distinguishes_headshot_award_types() -> None:
    builder = AwardQueryBuilder(num_days=3, date_sql="CURRENT_DATE()")

    object_daily, object_daily_params, object_global, object_global_params = builder.build_queries(
        AwardDefinition(1, "tf2", "O", "headshot")
    )
    assert "hlstats_Events_PlayerActions" in object_daily
    assert "hlstats_Actions" in object_daily
    assert object_daily_params == ("tf2", "headshot")
    assert "hlstats_Events_PlayerActions" in object_global
    assert "hlstats_Actions" in object_global
    assert object_global_params == ("tf2", "headshot")

    weapon_daily, weapon_daily_params, weapon_global, weapon_global_params = builder.build_queries(
        AwardDefinition(2, "tf2", "W", "headshot")
    )
    assert "hlstats_Events_Frags" in weapon_daily
    assert weapon_daily_params == ("tf2", 1)
    assert "hlstats_Events_Frags" in weapon_global
    assert weapon_global_params == ("tf2", 1)


def test_award_query_builder_replay_safe_omits_hideranking_filter() -> None:
    strict_builder = AwardQueryBuilder(num_days=1, date_sql="CURRENT_DATE()", include_hidden_players=False)
    replay_builder = AwardQueryBuilder(num_days=1, date_sql="CURRENT_DATE()", include_hidden_players=True)
    award = AwardDefinition(10, "tf2", "W", "ak47")

    strict_daily, _, _, _ = strict_builder.build_queries(award)
    replay_daily, _, _, _ = replay_builder.build_queries(award)

    assert "hideranking = 0" in strict_daily
    assert "hideranking = 0" not in replay_daily


def test_process_awards_updates_winner_records() -> None:
    builder = AwardQueryBuilder(num_days=1, date_sql="CURRENT_DATE()")
    award = AwardDefinition(10, "tf2", "O", "capture")
    daily_query, daily_params, global_query, global_params = builder.build_queries(award)

    responses = {
        (normalize_sql(_AWARD_SELECTION_QUERY), None): [
            QueryResponse(fetchall=[(award.award_id, award.game, award.award_type, award.code)])
        ],
        (
            SELECT_AWARDS_DATE,
            None,
        ): [QueryResponse(fetchone=("2024-01-01", "2024-01-02"))],
        (
            UPDATE_AWARDS_DATE,
            ("2024-01-02",),
        ): [QueryResponse()],
        (
            REPLACE_AWARDS_NUMDAYS,
            (1,),
        ): [QueryResponse()],
        (normalize_sql(daily_query), daily_params): [QueryResponse(fetchone=(101, 5))],
        (normalize_sql(global_query), global_params): [QueryResponse(fetchone=(102, 7))],
        (
            UPDATE_AWARDS_WINNERS,
            (101, 5, 102, 7, 10),
        ): [QueryResponse()],
        (
            INSERT_PLAYER_AWARDS,
            None,
        ): [QueryResponse()],
    }

    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    calculator = AwardsCalculator(adapter)  # type: ignore[arg-type]

    calculator._process_awards(connection, num_days=1, base_date=None)

    assert (UPDATE_AWARDS_WINNERS, (101, 5, 102, 7, 10)) in connection.executed


def test_build_database_config_parses_host_and_port() -> None:
    settings = cli.RuntimeSettings(
        cli=cli.CliOptions(
            configfile=None,
            requested_actions=(cli.AwardsAction.AWARDS,),
            numdays=1,
            date=None,
            db_host=None,
            db_name=None,
            db_username=None,
            db_password=None,
            verbose=False,
            replay_mode=False,
            version=False,
        ),
        actions=frozenset({cli.AwardsAction.AWARDS}),
        database=cli.DatabaseConfig(
            host="db.example:3307",
            name="hlstats",
            username="user",
            password="secret",
            cpanel_hack=False,
        ),
        config_path=None,
        policy=cli.RuntimePolicy.STRICT,
    )

    config = build_database_config(settings)

    assert config.host == "db.example"
    assert config.port == 3307
    assert config.username == "user"
    assert config.database == "hlstats"


def test_process_geoip_updates_players_from_database_lookup() -> None:
    responses = {
        (normalize_sql(_SELECT_USE_GEOIP_BINARY_QUERY), None): [QueryResponse(fetchone=None)],
        (normalize_sql(_SELECT_GEOIP_CANDIDATES_QUERY), None): [
            QueryResponse(fetchall=[(5, "1.2.3.4", "Alice"), (6, "bad-ip", "Broken")])
        ],
        (normalize_sql(_SELECT_GEOLITE_BLOCKS_SMOKE_QUERY), None): [QueryResponse(fetchone=(1001,))],
        (
            normalize_sql(_SELECT_GEOLITE_BLOCK_QUERY),
            (16909060, 16909060),
        ): [QueryResponse(fetchone=(1001,))],
        (
            normalize_sql(_SELECT_GEOLITE_LOCATION_QUERY),
            (1001,),
        ): [QueryResponse(fetchone=("Paris", "Ile-de-France", "France", "FR", 48.8566, 2.3522))],
        (
            normalize_sql(_UPDATE_PLAYER_GEOIP_QUERY),
            ("FR", "France", 48.8566, 2.3522, "Paris", "Ile-de-France", 5),
        ): [QueryResponse(rowcount=1)],
    }
    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    report = AwardsReport()
    calculator = AwardsCalculator(adapter, report=report)  # type: ignore[arg-type]

    settings = cli.RuntimeSettings(
        cli=cli.CliOptions(
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
        ),
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

    calculator._process_geoip(connection, settings)

    assert report.geoip_updates == 1
    assert (
        normalize_sql(_UPDATE_PLAYER_GEOIP_QUERY),
        ("FR", "France", 48.8566, 2.3522, "Paris", "Ile-de-France", 5),
    ) in connection.executed


def test_process_geoip_fails_when_database_tables_are_empty() -> None:
    responses = {
        (normalize_sql(_SELECT_USE_GEOIP_BINARY_QUERY), None): [QueryResponse(fetchone=None)],
        (normalize_sql(_SELECT_GEOIP_CANDIDATES_QUERY), None): [QueryResponse(fetchall=[])],
        (normalize_sql(_SELECT_GEOLITE_BLOCKS_SMOKE_QUERY), None): [QueryResponse(fetchone=None)],
    }
    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    calculator = AwardsCalculator(adapter)  # type: ignore[arg-type]

    settings = cli.RuntimeSettings(
        cli=cli.CliOptions(
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
        ),
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

    with pytest.raises(RuntimeError, match="geoLiteCity tables are empty"):
        calculator._process_geoip(connection, settings)


def test_replay_safe_geoip_warning_skips_failure(capsys: pytest.CaptureFixture[str]) -> None:
    responses = {
        (normalize_sql(_SELECT_USE_GEOIP_BINARY_QUERY), None): [QueryResponse(fetchone=None)],
        (normalize_sql(_SELECT_GEOIP_CANDIDATES_QUERY), None): [QueryResponse(fetchall=[])],
        (normalize_sql(_SELECT_GEOLITE_BLOCKS_SMOKE_QUERY), None): [QueryResponse(fetchone=None)],
    }
    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    calculator = AwardsCalculator(adapter)  # type: ignore[arg-type]
    settings = cli.RuntimeSettings(
        cli=cli.CliOptions(
            configfile=None,
            requested_actions=(cli.AwardsAction.GEOIP,),
            numdays=1,
            date=None,
            db_host=None,
            db_name=None,
            db_username=None,
            db_password=None,
            verbose=False,
            replay_mode=True,
            version=False,
        ),
        actions=frozenset({cli.AwardsAction.GEOIP}),
        database=cli.DatabaseConfig(
            host="localhost",
            name="hlstats",
            username="hlx",
            password="secret",
            cpanel_hack=False,
        ),
        config_path=None,
        policy=cli.RuntimePolicy.REPLAY_SAFE,
    )

    calculator.run(settings)
    assert "warning:" in capsys.readouterr().out


def test_strict_geoip_failure_bubbles_up_from_run() -> None:
    responses = {
        (normalize_sql(_SELECT_USE_GEOIP_BINARY_QUERY), None): [QueryResponse(fetchone=None)],
        (normalize_sql(_SELECT_GEOIP_CANDIDATES_QUERY), None): [QueryResponse(fetchall=[])],
        (normalize_sql(_SELECT_GEOLITE_BLOCKS_SMOKE_QUERY), None): [QueryResponse(fetchone=None)],
    }
    connection = FakeConnection(responses)
    adapter = StubAdapter(connection)
    calculator = AwardsCalculator(adapter)  # type: ignore[arg-type]
    settings = cli.RuntimeSettings(
        cli=cli.CliOptions(
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
        ),
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

    with pytest.raises(RuntimeError, match="geoLiteCity tables are empty"):
        calculator.run(settings)
