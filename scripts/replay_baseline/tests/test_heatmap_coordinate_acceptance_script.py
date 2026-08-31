from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "scripts" / "replay_baseline" / "comparison" / "Run-HeatmapCoordinateAcceptance.ps1"
FIXTURE_PATH = REPO_ROOT / "scripts" / "replay_baseline" / "fixtures" / "modern_heatmap_coordinates.log"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "product-ci.yml"


def test_coordinate_acceptance_runner_fixture_and_ci_source_contracts() -> None:
    """Guard the offline source contract; this test never invokes the DB runner."""
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    fixture = FIXTURE_PATH.read_text(encoding="utf-8")
    ci = CI_PATH.read_text(encoding="utf-8")

    ordered_fixture_cases = [
        '"HeatmapFixtureAttacker<101><STEAM_1:0:900001><CT>" killed '
        '"HeatmapFixtureVictim<102><STEAM_1:0:900002><TERRORIST>" with "ak47" (headshot) '
        '(attacker_position "101 202 303") (victim_position "404 505 606")',
        '"HeatmapFixtureSuicide<103><STEAM_1:0:900003><CT>" committed suicide '
        'with "worldspawn" (victim_position "707 808 909")',
        'World triggered "killlocation" (attacker_position "1001 1002 1003") '
        '(victim_position "1101 1102 1103")',
        '"HeatmapFixtureStagedFirst<104><STEAM_1:0:900004><CT>" killed '
        '"HeatmapFixtureStagedVictim<105><STEAM_1:0:900005><TERRORIST>" with "m4a1"',
        '"HeatmapFixtureUnstagedFirst<106><STEAM_1:0:900006><CT>" killed '
        '"HeatmapFixtureUnstagedVictim<107><STEAM_1:0:900007><TERRORIST>" with "m4a1"',
        'World triggered "killlocation" (attacker_position "1201 1202 1203") '
        '(victim_position "1301 1302 1303")',
        "Log file started",
        '"HeatmapFixtureBoundaryFirst<108><STEAM_1:0:900008><CT>" killed '
        '"HeatmapFixtureBoundaryVictim<109><STEAM_1:0:900009><TERRORIST>" with "m4a1"',
    ]
    positions = [fixture.index(case) for case in ordered_fixture_cases]
    assert positions == sorted(positions)
    assert fixture.count('World triggered "killlocation"') == 2
    assert fixture.count("Log file started") == 1
    assert fixture.count("attacker_position") == 3
    assert fixture.count("victim_position") == 4

    assert '[ValidateSet("bench_ephemeral")]' in runner
    assert "bench_ephemeral\\docker-compose.yml" in runner
    assert "comparison\\python" not in runner
    assert "Get-NetTCPConnection" in runner
    assert "hlstatsx-writebench-db" in runner
    assert "Get-FileHash" in runner
    assert "python -m hlstats_py.runtime" in runner
    assert "--stdin" in runner
    assert "MYSQL_PWD" in runner
    assert "MARIADB_PWD" not in runner
    assert "hlstats_Events_Frags" in runner
    assert "hlstats_Events_Suicides" in runner
    for canonical_position_column in (
        "frag.pos_x",
        "frag.pos_y",
        "frag.pos_z",
        "frag.pos_victim_x",
        "frag.pos_victim_y",
        "frag.pos_victim_z",
    ):
        assert canonical_position_column in runner
    assert "ORDER BY frag.id" in runner
    assert "ORDER BY suicide.id" in runner
    for invalid_frag_field in ("frag.suicide", "frag.eventId"):
        assert invalid_frag_field not in runner
    assert "fixture_sha256" in runner
    assert "row_counts" in runner
    assert "asserted_coordinate_tuples" in runner
    assert "verdict" in runner
    assert "finally" in runner
    assert "down -v" in runner
    for literal_secret in ("root123", "hlx123"):
        assert literal_secret not in runner

    assert ci.count("  php-lint:") == 1
    assert "  replay-baseline:" in ci
    lint_index = ci.index("Lint web PHP files")
    node_check_index = ci.index("node --check web/includes/js/heatmap-explorer.js")
    node_smoke_index = ci.index("node scripts/heatmap_js_smoke.js")
    php_smoke_index = ci.index("php scripts/web_heatmap_smoke.php")
    assert lint_index < node_check_index < node_smoke_index < php_smoke_index
