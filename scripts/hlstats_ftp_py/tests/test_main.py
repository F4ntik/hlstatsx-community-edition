"""Tests for FTP CLI helpers (mocked FTP)."""

from __future__ import annotations

from unittest.mock import MagicMock

from hlstats_ftp_py.main import (
    _collect_log_entries,
    _parse_mdtm_response,
    _parse_modify_fact,
    run,
)


def test_run_version() -> None:
    assert run(["--version"]) == 0


def test_parse_mdtm_response() -> None:
    assert _parse_mdtm_response("213 20240102103045") is not None
    assert _parse_mdtm_response("213 20240102103045.12") is not None
    assert _parse_mdtm_response("500 bad") is None


def test_parse_modify_fact() -> None:
    assert _parse_modify_fact("20240102103045") is not None
    assert _parse_modify_fact("20240102103045.12") is not None
    assert _parse_modify_fact("not-a-timestamp") is None


def test_collect_log_entries_prefers_mlsd_when_available() -> None:
    ftp = MagicMock()
    ftp.mlsd.return_value = [
        ("a.log", {"modify": "20240101000000"}),
        ("b.txt", {"modify": "20240101000000"}),
    ]
    ftp.nlst.return_value = ["fallback.log"]

    entries = _collect_log_entries(ftp, "/logs")
    ftp.cwd.assert_called_once_with("/logs")
    assert len(entries) == 1
    assert entries[0].name == "a.log"
    ftp.nlst.assert_not_called()


def test_collect_log_entries_uses_nlst_and_mdtm() -> None:
    ftp = MagicMock()
    ftp.mlsd.side_effect = AttributeError
    ftp.nlst.return_value = ["a.log", "b.txt"]
    ftp.sendcmd.return_value = "213 20240101000000"

    entries = _collect_log_entries(ftp, "/logs")
    ftp.cwd.assert_called_once_with("/logs")
    assert len(entries) == 1
    assert entries[0].name == "a.log"
    ftp.sendcmd.assert_called_once()


def test_collect_log_entries_name_cap() -> None:
    ftp = MagicMock()
    ftp.nlst.return_value = ["z.log", "a.log", "m.log"]
    ftp.sendcmd.return_value = "213 20240101000000"

    entries = _collect_log_entries(ftp, "/logs", name_cap=2)
    assert len(entries) == 2
    assert [e.name for e in entries] == ["a.log", "m.log"]
