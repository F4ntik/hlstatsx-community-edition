"""Tests for GoldSrc physical line merge helpers."""

from __future__ import annotations

import io

from hlstats_py.goldsrc_physical_lines import (
    iter_merged_goldsrc_physical_lines,
    line_starts_new_goldsrc_record,
)
from hlstats_py.protocol import parse_log_event


def test_line_starts_new_goldsrc_record_detects_prefix() -> None:
    assert line_starts_new_goldsrc_record(b"L 01/02/2024 - 03:04:05: hello")
    assert line_starts_new_goldsrc_record(b"  L 01/02/2024 - 03:04:05: hello")
    assert line_starts_new_goldsrc_record(b"\xef\xbb\xbfL 01/02/2024 - 03:04:05: x")
    assert not line_starts_new_goldsrc_record(b"continuation without timestamp")


def test_iter_merged_joins_continuation_lines() -> None:
    raw = (
        b'L 01/02/2024 - 03:04:05: "Alice<2><STEAM_1:1:111><CT>" say "line1\n'
        b'line2"\n'
        b"L 01/02/2024 - 03:04:06: World triggered \"Round_Start\"\n"
    )
    merged = list(iter_merged_goldsrc_physical_lines(io.BytesIO(raw)))
    assert len(merged) == 2
    assert b"\n" in merged[0]
    assert merged[1].startswith(b"L 01/02/2024 - 03:04:06:")
    first = merged[0].decode("utf-8")
    assert "line1" in first and "line2" in first
    parse_log_event(first)


def test_iter_merged_single_line_record() -> None:
    raw = b'L 01/02/2024 - 03:04:05: World triggered "Round_End"\n'
    merged = list(iter_merged_goldsrc_physical_lines(io.BytesIO(raw)))
    assert len(merged) == 1
