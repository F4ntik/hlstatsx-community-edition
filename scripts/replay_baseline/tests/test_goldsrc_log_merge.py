from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from goldsrc_log_merge import line_starts_new_goldsrc_record


def test_line_starts_new_goldsrc_record_positive() -> None:
    assert line_starts_new_goldsrc_record(
        b'L 01/01/2025 - 00:04:34: Rcon: "rcon secret"\n'
    )


def test_line_starts_new_goldsrc_record_continuation_negative() -> None:
    assert not line_starts_new_goldsrc_record(b'" from "94.198.219.159:34557"')


def test_line_starts_new_strips_utf8_bom() -> None:
    assert line_starts_new_goldsrc_record(
        b"\xef\xbb\xbfL 01/01/2025 - 00:04:34: Log file started\n"
    )
