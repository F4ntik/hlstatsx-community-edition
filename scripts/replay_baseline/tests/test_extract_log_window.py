from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.replay_baseline.extract_log_window import extract_window, find_anchor_line


def test_find_anchor_line_by_event_time(tmp_path: Path) -> None:
    log = tmp_path / "L0105062.log"
    log.write_text(
        "\n".join(
            [
                "L 01/06/2024 - 00:18:08: before",
                "L 01/06/2024 - 00:18:10: target",
                "L 01/06/2024 - 00:18:12: after",
            ]
        ),
        encoding="utf-8",
    )

    assert find_anchor_line(log, event_time="2024-01-06 00:18:10") == 2


def test_extract_window_keeps_context_around_anchor(tmp_path: Path) -> None:
    log = tmp_path / "source.log"
    log.write_text("\n".join(f"line {i}" for i in range(1, 8)) + "\n", encoding="utf-8")
    output = tmp_path / "window.log"

    result = extract_window(log, output, line_number=4, before=2, after=1)

    assert result.start_line == 2
    assert result.end_line == 5
    assert output.read_text(encoding="utf-8").splitlines() == [
        "line 2",
        "line 3",
        "line 4",
        "line 5",
    ]


def test_cli_extracts_window_by_pattern(tmp_path: Path) -> None:
    log = tmp_path / "source.log"
    log.write_text("a\nb target\nc\n", encoding="utf-8")
    output = tmp_path / "window.log"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/replay_baseline/extract_log_window.py",
            "--log-file",
            str(log),
            "--pattern",
            "target",
            "--before",
            "1",
            "--after",
            "1",
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[3],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "source.log:1-3" in result.stdout
    assert output.read_text(encoding="utf-8").splitlines() == ["a", "b target", "c"]
