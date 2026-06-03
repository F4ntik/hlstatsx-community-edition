from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.replay_baseline.locate_residual_logs import (
    ResidualNeedle,
    find_candidate_logs,
    goldsrc_timestamp,
    steam_search_terms,
)


def test_goldsrc_timestamp_converts_compare_time_to_log_time() -> None:
    assert goldsrc_timestamp("2024-01-06 00:18:10") == "01/06/2024 - 00:18:10"


def test_steam_search_terms_expands_canonical_unique_id() -> None:
    assert steam_search_terms("1:55955613") == (
        "1:55955613",
        "STEAM_0:1:55955613",
        "STEAM_1:1:55955613",
    )


def test_find_candidate_logs_scores_event_identity_and_map(tmp_path: Path) -> None:
    target = tmp_path / "L0105062.log"
    target.write_text(
        "\n".join(
            [
                'L 01/06/2024 - 00:18:08: "Rakza<1824><STEAM_0:1:55955613><CT>" killed "x"',
                'L 01/06/2024 - 00:18:10: "Rakza<1824><STEAM_0:1:55955613><CT>" triggered "Defused_The_Bomb"',
                'L 01/06/2024 - 00:18:10: Loading map "de_spay"',
            ]
        ),
        encoding="utf-8",
    )
    noise = tmp_path / "L0105063.log"
    noise.write_text('L 01/06/2024 - 00:18:10: "Other<1><STEAM_0:1:2><CT>" say "Rakza"\n', encoding="utf-8")

    results = find_candidate_logs(
        tmp_path,
        ResidualNeedle(
            event_time="2024-01-06 00:18:10",
            player="Rakza",
            unique_id="1:55955613",
            map_name="de_spay",
            action="Defused_The_Bomb",
        ),
        limit=2,
    )

    assert results[0].path == target
    assert results[0].score > results[1].score
    assert "unique_id" in results[0].matched_fields


def test_cli_prints_ranked_candidates(tmp_path: Path) -> None:
    (tmp_path / "L0001.log").write_text(
        'L 01/06/2024 - 00:18:10: "Rakza<1><STEAM_0:1:55955613><CT>" triggered "Defused_The_Bomb"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/replay_baseline/locate_residual_logs.py",
            "--artifacts-dir",
            str(tmp_path),
            "--event-time",
            "2024-01-06 00:18:10",
            "--player",
            "Rakza",
            "--unique-id",
            "1:55955613",
        ],
        cwd=Path(__file__).resolve().parents[3],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "L0001.log" in result.stdout
    assert "score=" in result.stdout
