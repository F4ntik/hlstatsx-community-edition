from __future__ import annotations

from pathlib import Path


def test_single_log_parity_runs_30_line_guard_window() -> None:
    script = Path("scripts/replay_baseline/comparison/Run-SingleLogParity.ps1").read_text(
        encoding="utf-8"
    )

    assert "[int]$GuardBefore = 30" in script
    assert "[int]$GuardAfter = 30" in script
    assert "[switch]$SkipGuardWindow" in script
    assert "Get-TraceTimestampAnchor" in script
    assert '"==> Guard parity pass: $GuardBefore lines before / $GuardAfter lines after"' in script
    assert '"-SkipGuardWindow"' in script
