from __future__ import annotations

import gzip
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPO_ROOT / "scripts" / "replay_baseline" / "comparison" / "Run-HeatmapCoordinateAcceptance.ps1"
FIXTURE_PATH = REPO_ROOT / "scripts" / "replay_baseline" / "fixtures" / "modern_heatmap_coordinates.log"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "product-ci.yml"
STORAGE_PATH = REPO_ROOT / "scripts" / "hlstats_py" / "storage.py"
RUNTIME_DECISIONS_PATH = REPO_ROOT / "scripts" / "hlstats_py" / "runtime_decisions.py"
BASELINE_DUMP_PATH = REPO_ROOT / "scripts" / "replay_baseline" / "artifacts" / "baseline_reset_20260418.sql.gz"


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


def test_coordinate_acceptance_runner_uses_canonical_identity_table_lookup() -> None:
    """The runner must mirror runtime identity lookup without touching the live DB."""

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    storage = STORAGE_PATH.read_text(encoding="utf-8")
    runtime_decisions = RUNTIME_DECISIONS_PATH.read_text(encoding="utf-8")

    assert "SELECT `playerId` FROM hlstats_PlayerUniqueIds WHERE `uniqueId` = %s AND `game` = %s" in storage
    assert "def canonical_unique_id" in runtime_decisions
    assert "candidates = [raw_unique]" in storage
    assert "candidates.append(canonical_unique)" in storage
    assert "for candidate in candidates:" in storage

    assert "function Get-CanonicalUniqueId" in runner
    assert "function Resolve-PlayerIdByUniqueId" in runner
    assert '$rows = @(Invoke-DatabaseRows -Sql @"' in runner
    assert "FROM hlstats_PlayerUniqueIds" in runner
    assert "AND lookup.game = '$gameId'" in runner
    assert "WHERE frag.killerId = $killerPlayerId" in runner
    assert "AND frag.victimId = $victimPlayerId" in runner
    assert "WHERE suicide.playerId = $victimPlayerId" in runner

    for forbidden_lookup in ("killer.uniqueId", "victim.uniqueId", "hlstats_Players.uniqueId"):
        assert forbidden_lookup not in runner


def test_coordinate_acceptance_runner_baseline_dump_matches_uniqueid_lookup_contract() -> None:
    """The exact disposable baseline used by the runner must expose the expected lookup table."""

    with gzip.open(BASELINE_DUMP_PATH, "rt", encoding="utf-8", errors="ignore") as stream:
        dump = stream.read()

    unique_ids = re.search(
        r"CREATE TABLE `hlstats_PlayerUniqueIds` \((?P<body>.*?)\) ENGINE=",
        dump,
        re.DOTALL,
    )
    assert unique_ids is not None
    assert "`playerId` int(10) unsigned NOT NULL DEFAULT 0" in unique_ids.group("body")
    assert "`uniqueId` varchar(64) NOT NULL DEFAULT ''" in unique_ids.group("body")
    assert "`game` varchar(32) NOT NULL DEFAULT ''" in unique_ids.group("body")
    assert "PRIMARY KEY (`uniqueId`,`game`)" in unique_ids.group("body")
    assert "KEY `playerId` (`playerId`)" in unique_ids.group("body")

    players = re.search(
        r"CREATE TABLE `hlstats_Players` \((?P<body>.*?)\) ENGINE=",
        dump,
        re.DOTALL,
    )
    assert players is not None
    assert "`uniqueId`" not in players.group("body")


def test_coordinate_acceptance_runner_pins_runner_side_candidate_order_and_game_scope() -> None:
    """The runner itself must keep raw-first lookup, exact fallback, and per-case game scoping."""

    runner = RUNNER_PATH.read_text(encoding="utf-8")

    raw_index = runner.index("$null = $candidates.Add($UniqueId)")
    canonical_index = runner.index("$null = $candidates.Add($canonicalUnique)")
    foreach_index = runner.index("foreach ($candidate in $candidates)")
    success_index = runner.index("return $rows[0]")
    null_index = runner.index("return $null")

    assert raw_index < canonical_index < foreach_index < success_index < null_index
    assert 'if ($canonicalUnique -ne $UniqueId) {' in runner
    assert "WHERE lookup.uniqueId = '$escapedCandidate'" in runner
    assert "AND lookup.game = '$gameId'" in runner
    assert 'Resolve-PlayerIdByUniqueId -UniqueId $KillerUniqueId -Game $Game' in runner
    assert 'Resolve-PlayerIdByUniqueId -UniqueId $VictimUniqueId -Game $Game' in runner
    assert runner.count('-Game $case.game') == 2
    assert 'Get-SuicideCoordinates -Game $case.game -VictimUniqueId $case.victim -Weapon $case.weapon' in runner
    assert 'Get-FragCoordinates -Game $case.game -KillerUniqueId $case.killer -VictimUniqueId $case.victim' in runner
    assert runner.count('game = "cstrike"') == 5


def test_coordinate_acceptance_runner_tolerates_native_progress_stderr() -> None:
    """Docker/python progress on stderr must not abort the runner before exit-code checks."""

    runner = RUNNER_PATH.read_text(encoding="utf-8")

    assert "function Invoke-NativeCapture" in runner
    assert "function Wait-ForRestoreRoute" in runner
    assert '$ErrorActionPreference = "Continue"' in runner
    assert "$discardedOutput = @(Invoke-NativeCapture { docker @Arguments })" in runner
    assert "mariadb-admin --protocol=socket -u $script:dbUsername ping" in runner
    assert "mariadb-admin --protocol=TCP -h 127.0.0.1 -u root ping" in runner
    assert "Wait-ForRestoreRoute" in runner
    assert "$rows = @(Invoke-NativeCapture {" in runner
    assert '$rows = @(if ($case.source -eq "suicide") {' in runner
    assert "$fixtureContent | python -m hlstats_py.runtime" in runner
    assert "docker compose -p $composeProject -f $composeFile down -v" in runner
