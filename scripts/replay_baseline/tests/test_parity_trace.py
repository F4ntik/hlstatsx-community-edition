from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.replay_baseline.parity_trace import (
    TraceEvent,
    TraceFilter,
    first_divergence,
    unmatched_writes,
    normalize_sql_event,
    read_trace,
)


def test_normalize_sql_event_keeps_only_db_writes() -> None:
    select_event = normalize_sql_event(
        source="python",
        index=1,
        payload={
            "event_ref": "L0001:10",
            "sql": "SELECT playerId FROM hlstats_Players WHERE game = %s",
            "params": ["cstrike"],
        },
    )
    insert_event = normalize_sql_event(
        source="python",
        index=2,
        payload={
            "event_ref": "L0001:11",
            "sql": " INSERT INTO hlstats_Events_PlayerActions "
            "(eventTime, playerId, actionId, bonus) VALUES (%s, %s, %s, %s)",
            "params": ["2024-01-06 00:18:10", 42, 7, 1],
        },
    )

    assert select_event is None
    assert insert_event == TraceEvent(
        source="python",
        index=2,
        event_ref="L0001:11",
        operation="insert",
        table="hlstats_Events_PlayerActions",
        fingerprint="insert into hlstats_events_playeractions "
        "(eventtime, playerid, actionid, bonus) values (?, ?, ?, ?)",
        params=("2024-01-06 00:18:10", "42", "7", "1"),
    )


def test_first_divergence_reports_first_mismatched_write_intent() -> None:
    legacy = [
        TraceEvent("legacy", 1, "L0001:10", "update", "hlstats_Players", "update a", ("1",)),
        TraceEvent(
            "legacy", 2, "L0001:11", "insert", "hlstats_Events_PlayerActions", "insert b", ("2",)
        ),
    ]
    python = [
        TraceEvent("python", 1, "L0001:10", "update", "hlstats_Players", "update a", ("1",)),
        TraceEvent(
            "python", 2, "L0001:11", "insert", "hlstats_Events_PlayerActions", "insert b", ("3",)
        ),
    ]

    diff = first_divergence(legacy, python)

    assert diff is not None
    assert diff.position == 2
    assert diff.legacy == legacy[1]
    assert diff.python == python[1]
    assert diff.reason == "write-intent mismatch"


def test_unmatched_writes_ignores_order_and_reports_missing_writes() -> None:
    legacy_only = TraceEvent(
        "legacy", 3, "L0001:12", "insert", "hlstats_Events_PlayerActions", "insert c", ("9",)
    )
    python_only = TraceEvent(
        "python", 3, "L0001:12", "insert", "hlstats_Events_PlayerActions", "insert c", ("10",)
    )
    shared_a = TraceEvent("legacy", 1, "L0001:10", "update", "hlstats_Players", "update a", ("1",))
    shared_b = TraceEvent("legacy", 2, "L0001:11", "insert", "hlstats_Frags", "insert b", ("2",))

    result = unmatched_writes(
        legacy=[shared_a, shared_b, legacy_only],
        python=[
            TraceEvent("python", 1, "L0001:11", "insert", "hlstats_Frags", "insert b", ("2",)),
            TraceEvent("python", 2, "L0001:10", "update", "hlstats_Players", "update a", ("1",)),
            python_only,
        ],
    )

    assert result.legacy_only == [legacy_only]
    assert result.python_only == [python_only]


def test_insert_upsert_trace_compare_ignores_update_clause_syntax(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.log"
    python_path = tmp_path / "python.jsonl"
    legacy_path.write_text(
        "INSERT INTO hlstats_Maps_Counts (game, map, kills, headshots)\n"
        "VALUES ('cstrike', 'de_spay', 1, 0)\n"
        "ON DUPLICATE KEY UPDATE kills=kills+1",
        encoding="utf-8",
    )
    python_path.write_text(
        json.dumps(
            {
                "sql": "INSERT INTO hlstats_Maps_Counts (game, map, kills, headshots) "
                "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                "kills = kills + VALUES(kills), headshots = headshots + VALUES(headshots)",
                "params": ["cstrike", "de_spay", 1, 0],
            }
        ),
        encoding="utf-8",
    )

    result = unmatched_writes(
        read_trace(legacy_path, source="legacy"),
        read_trace(python_path, source="python"),
    )

    assert result.legacy_only == []
    assert result.python_only == []


def test_read_trace_accepts_jsonl_sql_events(tmp_path: Path) -> None:
    trace_path = tmp_path / "python.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps({"sql": "BEGIN"}),
                json.dumps(
                    {
                        "event_ref": "L0002:7",
                        "sql": "UPDATE hlstats_Players SET skill = skill + %s WHERE playerId = %s",
                        "params": [5, 162],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    events = read_trace(trace_path, source="python")

    assert events == [
        TraceEvent(
            source="python",
            index=2,
            event_ref="L0002:7",
            operation="update",
            table="hlstats_Players",
            fingerprint="update hlstats_players set skill = skill + ? where playerid = ?",
            params=("5", "162"),
        )
    ]


def test_read_trace_accepts_mysql_general_log_query_lines(tmp_path: Path) -> None:
    trace_path = tmp_path / "legacy-general.log"
    trace_path.write_text(
        "\n".join(
            [
                "2026-05-17T10:00:00.000000Z\t12 Query\tSELECT 1",
                "2026-05-17T10:00:01.000000Z\t12 Query\tINSERT INTO hlstats_Events_ChangeTeam "
                "(eventTime, playerId, team) VALUES ('2025-01-03 23:09:41', 162, 'UNASSIGNED')",
            ]
        ),
        encoding="utf-8",
    )

    events = read_trace(trace_path, source="legacy")

    assert events == [
        TraceEvent(
            source="legacy",
            index=2,
            event_ref="",
            operation="insert",
            table="hlstats_Events_ChangeTeam",
            fingerprint="insert into hlstats_events_changeteam "
            "(eventtime, playerid, team) values (?, ?, ?)",
            params=("2025-01-03 23:09:41", "162", "UNASSIGNED"),
        )
    ]


def test_read_trace_reassembles_multiline_legacy_sql(tmp_path: Path) -> None:
    trace_path = tmp_path / "legacy-general.log"
    trace_path.write_text(
        "\n".join(
            [
                "INSERT INTO hlstats_Maps_Counts (game, map, kills, headshots)",
                "VALUES ('cstrike', 'de_spay', 1, 0)",
                "ON DUPLICATE KEY UPDATE kills = kills + 1, headshots = headshots + 0",
            ]
        ),
        encoding="utf-8",
    )

    events = read_trace(trace_path, source="legacy")

    assert events == [
        TraceEvent(
            source="legacy",
            index=1,
            event_ref="",
            operation="insert",
            table="hlstats_Maps_Counts",
            fingerprint="insert into hlstats_maps_counts (game, map, kills, headshots) "
            "values (?, ?, ?, ?)",
            params=("cstrike", "de_spay", "1", "0"),
        )
    ]


def test_read_trace_can_filter_infrastructure_tables(tmp_path: Path) -> None:
    trace_path = tmp_path / "python-general.log"
    trace_path.write_text(
        "\n".join(
            [
                "INSERT INTO Proxy_Daemons (host, port) VALUES ('worker', 28000)",
                "UPDATE hlstats_Servers SET act_players=0 WHERE serverId=2",
            ]
        ),
        encoding="utf-8",
    )

    events = read_trace(
        trace_path,
        source="python",
        trace_filter=TraceFilter(include_prefixes=("hlstats_",)),
    )

    assert [event.table for event in events] == ["hlstats_Servers"]


def test_read_trace_can_focus_table_and_parameter_terms(tmp_path: Path) -> None:
    trace_path = tmp_path / "python.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "sql": "INSERT INTO hlstats_Events_PlayerActions "
                        "(eventTime, playerId, actionId) VALUES (%s, %s, %s)",
                        "params": ["2024-01-06 00:18:10", 32, 285],
                    }
                ),
                json.dumps(
                    {
                        "sql": "INSERT INTO hlstats_Events_PlayerActions "
                        "(eventTime, playerId, actionId) VALUES (%s, %s, %s)",
                        "params": ["2024-01-06 00:18:11", 32, 285],
                    }
                ),
                json.dumps(
                    {
                        "sql": "INSERT INTO hlstats_Events_Entries "
                        "(eventTime, playerId) VALUES (%s, %s)",
                        "params": ["2024-01-06 00:18:10", 32],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    events = read_trace(
        trace_path,
        source="python",
        trace_filter=TraceFilter(
            include_tables=("hlstats_Events_PlayerActions",),
            param_contains=("00:18:10",),
        ),
    )

    assert len(events) == 1
    assert events[0].table == "hlstats_Events_PlayerActions"
    assert events[0].params[0] == "2024-01-06 00:18:10"


def test_cli_exits_nonzero_and_prints_first_divergence(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.jsonl"
    python = tmp_path / "python.jsonl"
    legacy.write_text(
        json.dumps(
            {
                "event_ref": "L0100:55",
                "sql": "INSERT INTO hlstats_Events_TeamBonuses (eventTime, playerId) VALUES (%s, %s)",
                "params": ["2026-01-02 21:40:31", 10],
            }
        ),
        encoding="utf-8",
    )
    python.write_text(
        json.dumps(
            {
                "event_ref": "L0100:55",
                "sql": "INSERT INTO hlstats_Events_TeamBonuses (eventTime, playerId) VALUES (%s, %s)",
                "params": ["2026-01-02 21:40:31", 11],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/replay_baseline/parity_trace.py",
            "diff",
            "--legacy",
            str(legacy),
            "--python",
            str(python),
        ],
        cwd=Path(__file__).resolve().parents[3],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "First divergence at write #1" in result.stdout
    assert "hlstats_Events_TeamBonuses" in result.stdout
    assert "legacy params" in result.stdout
    assert "python params" in result.stdout
