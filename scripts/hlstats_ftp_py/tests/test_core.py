"""Unit tests for hlstats_ftp_py.core (no FTP)."""

from __future__ import annotations

from pathlib import Path

from hlstats_ftp_py.checkpoint import FtpCheckpoint, mtime_to_us
from hlstats_ftp_py.core import (
    LogFileEntry,
    entries_after_checkpoint,
    entries_to_download,
    filter_log_names,
    read_last_mtime,
    without_newest_log,
    write_last_mtime,
)


def test_without_newest_log_empty_or_one() -> None:
    assert without_newest_log([]) == []
    assert without_newest_log([LogFileEntry("a.log", 1.0)]) == []


def test_without_newest_log_drops_newest() -> None:
    entries = [
        LogFileEntry("old.log", 100.0),
        LogFileEntry("mid.log", 200.0),
        LogFileEntry("new.log", 300.0),
    ]
    stable = without_newest_log(entries)
    assert [e.name for e in stable] == ["old.log", "mid.log"]


def test_entries_to_download_respects_last_mtime() -> None:
    stable = [
        LogFileEntry("a.log", 10.0),
        LogFileEntry("b.log", 20.0),
        LogFileEntry("c.log", 30.0),
    ]
    assert [e.name for e in entries_to_download(stable, 0)] == ["a.log", "b.log", "c.log"]
    assert [e.name for e in entries_to_download(stable, 15)] == ["b.log", "c.log"]
    assert entries_to_download(stable, 100) == []


def test_entries_to_download_can_order_by_name_for_replay_parity() -> None:
    stable = [
        LogFileEntry("L0106059.log", 10.0),
        LogFileEntry("L0106057.log", 20.0),
        LogFileEntry("L0106058.log", 30.0),
    ]
    assert [e.name for e in entries_to_download(stable, 0, order_by="name")] == [
        "L0106057.log",
        "L0106058.log",
        "L0106059.log",
    ]


def test_durable_checkpoint_uses_filename_to_resume_same_mtime_without_duplicates() -> None:
    stable = [
        LogFileEntry("a.log", 10.0),
        LogFileEntry("b.log", 10.0),
        LogFileEntry("c.log", 20.0),
    ]
    checkpoint = FtpCheckpoint(mtime_us=mtime_to_us(10.0), name="a.log")

    assert [entry.name for entry in entries_after_checkpoint(stable, checkpoint)] == ["b.log", "c.log"]


def test_legacy_file_marker_bootstrap_preserves_strict_mtime_behavior() -> None:
    stable = [
        LogFileEntry("a.log", 10.0),
        LogFileEntry("b.log", 10.0),
        LogFileEntry("c.log", 20.0),
    ]
    legacy_checkpoint = FtpCheckpoint(mtime_us=mtime_to_us(10.0), name=None)

    assert [entry.name for entry in entries_after_checkpoint(stable, legacy_checkpoint)] == ["c.log"]

def test_filter_log_names() -> None:
    assert filter_log_names(["x.LOG", "dir/game.log", "readme.txt"]) == ["game.log", "x.LOG"]


def test_read_write_last_mtime_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "hlstats-ftp-1.2.3.4-27015.last"
    write_last_mtime(p, 1700000000.9)
    assert p.read_text(encoding="ascii") == "1700000000"
    assert read_last_mtime(p) == 1700000000.0
