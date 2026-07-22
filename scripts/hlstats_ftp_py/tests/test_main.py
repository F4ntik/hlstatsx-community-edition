"""Tests for FTP CLI helpers (mocked FTP)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import hlstats_ftp_py.main as ftp_main
from hlstats_ftp_py.checkpoint import (
    CheckpointCommitUncertainError,
    DurableFtpCheckpoint,
    FtpCheckpoint,
    mtime_to_us,
)
from hlstats_ftp_py.core import entries_after_checkpoint
from hlstats_ftp_py.main import (
    _collect_log_entries,
    _parse_mdtm_response,
    _parse_modify_fact,
    _write_manifest,
    run,
)


def _write_ftp_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _ftp_args(config_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        configfile=config_path,
        gs_ip="127.0.0.1",
        gs_port=27015,
        parser_backend="native",
        stdin_transaction_batch_size=1000,
        stdin_verbose_events=False,
        quiet=True,
    )


def test_run_version() -> None:
    assert run(["--version"]) == 0


def test_order_by_name_requires_fresh_state(tmp_path: Path, capsys) -> None:
    state = tmp_path / "hlstats-ftp-37.230.137.48-27015.last"
    state.write_text("1700000000", encoding="ascii")

    result = run(
        [
            "--gs-ip",
            "37.230.137.48",
            "--gs-port",
            "27015",
            "--ftp-usr",
            "hlxslogs",
            "--ftp-pwd",
            "secret",
            "--ftp-dir",
            "/",
            "--configfile",
            "hlstats.conf",
            "--cwd",
            str(tmp_path),
            "--order-by-name",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "--order-by-name requires a fresh FTP state" in captured.err


def test_continue_on_parse_error_requires_manifest_before_ftp(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run(
            [
                "--gs-ip",
                "127.0.0.1",
                "--gs-port",
                "27015",
                "--ftp-usr",
                "hlxslogs",
                "--ftp-pwd",
                "secret",
                "--ftp-dir",
                "/",
                "--configfile",
                "hlstats.conf",
                "--continue-on-parse-error",
            ]
        )

    assert exc_info.value.code == 2
    assert "--continue-on-parse-error requires --ignored-lines-manifest" in capsys.readouterr().err


def test_legacy_per_file_runtime_requires_explicit_unsafe_marker_mode(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run(
            [
                "--gs-ip",
                "127.0.0.1",
                "--gs-port",
                "27015",
                "--ftp-usr",
                "hlxslogs",
                "--ftp-pwd",
                "secret",
                "--ftp-dir",
                "/",
                "--configfile",
                "hlstats.conf",
                "--legacy-per-file-runtime",
            ]
        )

    assert exc_info.value.code == 2
    assert "--legacy-per-file-runtime requires explicit --legacy-file-marker" in capsys.readouterr().err


def test_manifest_writer_refuses_implicit_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    entries = [
        ftp_main.LogFileEntry(name="a.log", mtime=1),
        ftp_main.LogFileEntry(name="b.log", mtime=2),
    ]

    _write_manifest(path, entries)
    assert path.read_text(encoding="utf-8") == "a.log\nb.log\n"
    with pytest.raises(FileExistsError):
        _write_manifest(path, entries)


def test_batch_import_uses_import_db_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        configfile=config_path,
        gs_ip="127.0.0.1",
        gs_port=27015,
        parser_backend="native",
        stdin_transaction_batch_size=1000,
        stdin_verbose_events=False,
        quiet=True,
    )
    settings = ftp_main._build_runtime_settings(args)
    captured: dict[str, object] = {}

    class StopAfterAdapter(Exception):
        pass

    class RecordingAdapter:
        def __init__(self, config, **kwargs) -> None:
            captured["config"] = config
            captured["kwargs"] = kwargs
            raise StopAfterAdapter

    monkeypatch.setattr(ftp_main, "SyncDatabaseAdapter", RecordingAdapter)

    with pytest.raises(StopAfterAdapter):
        ftp_main._import_logs_batch([], tmp_path, args=args, settings=settings, last_path=tmp_path / ".last")

    assert captured["kwargs"] == {
        "import_mode": True,
        "enable_multi_statements": True,
    }


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


def test_import_logs_batch_records_empty_timestamp_only_ignores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "L0000001.log"
    log_path.write_text(
        'L 01/20/2025 - 03:55:14: \n'
        'L 01/20/2025 - 03:55:15: World triggered "Round_Start"\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        configfile=config_path,
        gs_ip="127.0.0.1",
        gs_port=27015,
        parser_backend="native",
        stdin_transaction_batch_size=1000,
        stdin_verbose_events=False,
        quiet=True,
    )
    settings = ftp_main._build_runtime_settings(args)
    ignored_manifest = tmp_path / "ignored.txt"

    class FakeAdapter:
        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, transaction_batch_size: int) -> None:
            return None

        def end_stdin_batch(self) -> None:
            return None

    class FakeRuntime:
        def __init__(self, adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            return None

        def process_stdin_line(self, line: str, server_address: str) -> None:
            return None

        def finalize_stdin_import(self) -> None:
            return None

    monkeypatch.setattr(ftp_main, "SyncDatabaseAdapter", lambda *args, **kwargs: FakeAdapter())
    monkeypatch.setattr(ftp_main, "EventStorage", FakeStorage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", FakeRuntime)

    with ignored_manifest.open("w", encoding="utf-8") as handle:
        records = ftp_main._import_logs_batch(
            [ftp_main.LogFileEntry(name=log_path.name, mtime=log_path.stat().st_mtime)],
            tmp_path,
            args=args,
            settings=settings,
            last_path=tmp_path / ".last",
            ignored_lines_manifest=handle,
        )

    assert records == 1
    assert "L0000001.log:1:empty-timestamp-only-line" in ignored_manifest.read_text(encoding="utf-8")


def test_import_logs_batch_can_continue_on_parse_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "L0000002.log"
    log_path.write_text(
        'L 01/20/2025 - 03:55:14: malformed entry\n'
        'L 01/20/2025 - 03:55:15: World triggered "Round_Start"\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        configfile=config_path,
        gs_ip="127.0.0.1",
        gs_port=27015,
        parser_backend="native",
        stdin_transaction_batch_size=1000,
        stdin_verbose_events=False,
        quiet=True,
    )
    settings = ftp_main._build_runtime_settings(args)
    ignored_manifest = tmp_path / "ignored-parse.txt"

    class FakeAdapter:
        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, transaction_batch_size: int) -> None:
            return None

        def end_stdin_batch(self) -> None:
            return None

    class FakeRuntime:
        def __init__(self, adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            return None

        def process_stdin_line(self, line: str, server_address: str) -> None:
            if "malformed entry" in line:
                raise ValueError("synthetic-parse-error")

        def finalize_stdin_import(self) -> None:
            return None

    monkeypatch.setattr(ftp_main, "SyncDatabaseAdapter", lambda *args, **kwargs: FakeAdapter())
    monkeypatch.setattr(ftp_main, "EventStorage", FakeStorage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", FakeRuntime)

    with ignored_manifest.open("w", encoding="utf-8") as handle:
        records = ftp_main._import_logs_batch(
            [ftp_main.LogFileEntry(name=log_path.name, mtime=log_path.stat().st_mtime)],
            tmp_path,
            args=args,
            settings=settings,
            last_path=tmp_path / ".last",
            ignored_lines_manifest=handle,
            continue_on_parse_error=True,
        )

    assert records == 1
    manifest_text = ignored_manifest.read_text(encoding="utf-8")
    assert "L0000002.log:1:parse-error:synthetic-parse-error" in manifest_text


def test_import_logs_batch_fail_fast_aborts_pending_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
                "ProxyKey secret",
            ]
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "L0000003.log"
    log_path.write_text('L 01/20/2025 - 03:55:14: malformed entry\n', encoding="utf-8")
    args = argparse.Namespace(
        configfile=config_path,
        gs_ip="127.0.0.1",
        gs_port=27015,
        parser_backend="native",
        stdin_transaction_batch_size=1000,
        stdin_verbose_events=False,
        quiet=True,
    )
    settings = ftp_main._build_runtime_settings(args)
    ignored_manifest = tmp_path / "ignored-fail-fast.txt"
    calls = {"abort": 0, "end": 0}

    class FakeAdapter:
        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, transaction_batch_size: int) -> None:
            return None

        def end_stdin_batch(self) -> None:
            calls["end"] += 1

        def abort_stdin_batch(self) -> None:
            calls["abort"] += 1

    class FakeRuntime:
        def __init__(self, adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            return None

        def process_stdin_line(self, line: str, server_address: str) -> None:
            raise ValueError("synthetic-fail-fast")

        def finalize_stdin_import(self) -> None:
            raise AssertionError("finalize must not run after a parse error")

    monkeypatch.setattr(ftp_main, "SyncDatabaseAdapter", lambda *args, **kwargs: FakeAdapter())
    monkeypatch.setattr(ftp_main, "EventStorage", FakeStorage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", FakeRuntime)

    with ignored_manifest.open("w", encoding="utf-8") as handle:
        with pytest.raises(ValueError, match="synthetic-fail-fast"):
            ftp_main._import_logs_batch(
                [ftp_main.LogFileEntry(name=log_path.name, mtime=log_path.stat().st_mtime)],
                tmp_path,
                args=args,
                settings=settings,
                last_path=tmp_path / ".last",
                ignored_lines_manifest=handle,
            )

    assert calls == {"abort": 1, "end": 0}
    assert "synthetic-fail-fast" in ignored_manifest.read_text(encoding="utf-8")


def test_durable_batch_keeps_committed_cursor_when_legacy_marker_mirror_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_ftp_config(tmp_path)
    entries = [
        ftp_main.LogFileEntry(name="L0000001.log", mtime=10.0),
        ftp_main.LogFileEntry(name="L0000002.log", mtime=20.0),
    ]
    for entry in entries:
        (tmp_path / entry.name).write_text('L 01/20/2025 - 03:55:15: World triggered "Round_Start"\n')
    args = _ftp_args(config_path)
    settings = ftp_main._build_runtime_settings(args)
    actions: list[str] = []

    class FakeAdapter:
        pass

    class FakeStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, *, transaction_batch_size: int) -> None:
            actions.append(f"storage-begin:{transaction_batch_size}")

        def end_stdin_batch(self) -> None:
            actions.append("storage-end")

        def abort_stdin_batch(self) -> None:
            actions.append("storage-abort")

    class FakeRuntime:
        def __init__(self, adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            actions.append("reload")

        def process_stdin_line(self, line: str, server_address: str) -> None:
            actions.append("write")

        def finalize_stdin_import(self) -> None:
            actions.append("finalize")

    class FakeCheckpoint:
        def __init__(self) -> None:
            self.active = False
            self.committed: ftp_main.LogFileEntry | None = None

        def begin(self) -> None:
            self.active = True
            actions.append("checkpoint-begin")

        def advance(self, entry: ftp_main.LogFileEntry) -> None:
            assert self.active
            actions.append(f"checkpoint-advance:{entry.name}")
            self.pending = entry

        def commit(self) -> None:
            assert self.active
            actions.append("checkpoint-commit")
            self.committed = self.pending
            self.active = False

        def rollback(self) -> None:
            actions.append("checkpoint-rollback")
            self.active = False

    checkpoint = FakeCheckpoint()
    monkeypatch.setattr(ftp_main, "EventStorage", FakeStorage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", FakeRuntime)
    def fail_final_legacy_marker(path: Path, mtime: float) -> None:
        actions.append(f"legacy-marker:{int(mtime)}")
        if mtime == 20.0:
            raise OSError("synthetic crash after DB commit")

    monkeypatch.setattr(ftp_main, "write_last_mtime", fail_final_legacy_marker)

    records = ftp_main._import_logs_batch(
        entries,
        tmp_path,
        args=args,
        settings=settings,
        last_path=tmp_path / ".last",
        checkpoint_store=checkpoint,  # type: ignore[arg-type]
        adapter=FakeAdapter(),  # type: ignore[arg-type]
    )

    assert records == 2
    assert actions == [
        "reload",
        "storage-begin:0",
        "checkpoint-begin",
        "write",
        "checkpoint-advance:L0000001.log",
        "checkpoint-commit",
        "legacy-marker:10",
        "checkpoint-begin",
        "write",
        "finalize",
        "checkpoint-advance:L0000002.log",
        "checkpoint-commit",
        "legacy-marker:20",
        "storage-end",
    ]
    assert checkpoint.committed == entries[-1]
    restart_cursor = FtpCheckpoint(mtime_us=mtime_to_us(20.0), name="L0000002.log")
    remaining = entries_after_checkpoint(entries + [ftp_main.LogFileEntry("L0000003.log", 30.0)], restart_cursor)
    assert [entry.name for entry in remaining] == ["L0000003.log"]


def test_durable_batch_error_before_checkpoint_rolls_back_and_keeps_restart_cursor_unadvanced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_ftp_config(tmp_path)
    entry = ftp_main.LogFileEntry(name="L0000004.log", mtime=40.0)
    (tmp_path / entry.name).write_text('L 01/20/2025 - 03:55:15: malformed\n')
    args = _ftp_args(config_path)
    settings = ftp_main._build_runtime_settings(args)
    actions: list[str] = []

    class FakeAdapter:
        pass

    class FakeStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, *, transaction_batch_size: int) -> None:
            actions.append("storage-begin")

        def abort_stdin_batch(self) -> None:
            actions.append("storage-abort")

    class FakeRuntime:
        def __init__(self, adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            return None

        def process_stdin_line(self, line: str, server_address: str) -> None:
            actions.append("write-error")
            raise ValueError("synthetic-before-checkpoint")

    class FakeCheckpoint:
        active = False

        def begin(self) -> None:
            self.active = True
            actions.append("checkpoint-begin")

        def advance(self, entry: ftp_main.LogFileEntry) -> None:
            actions.append("checkpoint-advance")

        def commit(self) -> None:
            actions.append("checkpoint-commit")

        def rollback(self) -> None:
            actions.append("checkpoint-rollback")
            self.active = False

    monkeypatch.setattr(ftp_main, "EventStorage", FakeStorage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", FakeRuntime)
    monkeypatch.setattr(ftp_main, "write_last_mtime", lambda *_: actions.append("legacy-marker"))

    with pytest.raises(ValueError, match="synthetic-before-checkpoint"):
        ftp_main._import_logs_batch(
            [entry],
            tmp_path,
            args=args,
            settings=settings,
            last_path=tmp_path / ".last",
            checkpoint_store=FakeCheckpoint(),  # type: ignore[arg-type]
            adapter=FakeAdapter(),  # type: ignore[arg-type]
        )

    assert actions == ["storage-begin", "checkpoint-begin", "write-error", "checkpoint-rollback", "storage-abort"]
    assert entries_after_checkpoint([entry], None) == [entry]


def test_durable_batch_stops_without_marker_when_commit_outcome_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_ftp_config(tmp_path)
    entry = ftp_main.LogFileEntry(name="L0000005.log", mtime=50.0)
    (tmp_path / entry.name).write_text('L 01/20/2025 - 03:55:15: World triggered "Round_Start"\n')
    args = _ftp_args(config_path)
    settings = ftp_main._build_runtime_settings(args)
    actions: list[str] = []

    class FakeAdapter:
        pass

    class FakeStorage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, *, transaction_batch_size: int) -> None:
            actions.append("storage-begin")

        def abort_stdin_batch(self) -> None:
            actions.append("storage-abort")

    class FakeRuntime:
        def __init__(self, adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            return None

        def process_stdin_line(self, line: str, server_address: str) -> None:
            actions.append("write")

        def finalize_stdin_import(self) -> None:
            actions.append("finalize")

    class FakeCheckpoint:
        active = False

        def begin(self) -> None:
            self.active = True
            actions.append("checkpoint-begin")

        def advance(self, entry: ftp_main.LogFileEntry) -> None:
            actions.append("checkpoint-advance")

        def commit(self) -> None:
            actions.append("checkpoint-commit-unknown")
            self.active = False
            raise CheckpointCommitUncertainError("synthetic unknown commit")

        def rollback(self) -> None:
            actions.append("checkpoint-rollback")

    monkeypatch.setattr(ftp_main, "EventStorage", FakeStorage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", FakeRuntime)
    monkeypatch.setattr(ftp_main, "write_last_mtime", lambda *_: actions.append("legacy-marker"))

    with pytest.raises(CheckpointCommitUncertainError, match="synthetic unknown commit"):
        ftp_main._import_logs_batch(
            [entry],
            tmp_path,
            args=args,
            settings=settings,
            last_path=tmp_path / ".last",
            checkpoint_store=FakeCheckpoint(),  # type: ignore[arg-type]
            adapter=FakeAdapter(),  # type: ignore[arg-type]
        )

    assert actions == [
        "storage-begin",
        "checkpoint-begin",
        "write",
        "finalize",
        "checkpoint-advance",
        "checkpoint-commit-unknown",
        "checkpoint-rollback",
        "storage-abort",
    ]


def test_durable_batch_uses_the_same_connection_for_game_writes_and_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_ftp_config(tmp_path)
    entry = ftp_main.LogFileEntry(name="L0000006.log", mtime=60.0)
    (tmp_path / entry.name).write_text('L 01/20/2025 - 03:55:15: World triggered "Round_Start"\n')
    args = _ftp_args(config_path)
    settings = ftp_main._build_runtime_settings(args)

    class Cursor:
        def __init__(self, connection: "Connection") -> None:
            self.connection = connection

        def execute(self, query: str, params=None) -> None:
            self.connection.actions.append(("sql", id(self.connection), query, params))

        def fetchone(self):
            return None

        def fetchall(self):
            return []

        def close(self) -> None:
            return None

    class Connection:
        def __init__(self) -> None:
            self.actions: list[tuple[object, ...]] = []

        def cursor(self) -> Cursor:
            return Cursor(self)

        def autocommit(self, enabled: bool) -> None:
            self.actions.append(("autocommit", id(self), enabled))

        def commit(self) -> None:
            self.actions.append(("commit", id(self)))

        def rollback(self) -> None:
            self.actions.append(("rollback", id(self)))

    class Adapter:
        def __init__(self, connection: Connection) -> None:
            self._connection = connection
            self.ping_modes: list[bool] = []

        def connection(self) -> Connection:
            return self._connection

        def set_skip_connection_ping(self, enabled: bool) -> None:
            self.ping_modes.append(enabled)

    class Storage:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def begin_stdin_batch(self, *, transaction_batch_size: int) -> None:
            assert transaction_batch_size == 0

        def end_stdin_batch(self) -> None:
            return None

    class Runtime:
        def __init__(self, adapter: Adapter, *args, **kwargs) -> None:
            self._adapter = adapter

        def _reload_state(self) -> None:
            return None

        def process_stdin_line(self, line: str, server_address: str) -> None:
            cursor = self._adapter.connection().cursor()
            cursor.execute("INSERT INTO hlstats_Events_Frags (id) VALUES (1)")
            cursor.close()

        def finalize_stdin_import(self) -> None:
            cursor = self._adapter.connection().cursor()
            cursor.execute("UPDATE hlstats_Players SET last_event = 1")
            cursor.close()

    connection = Connection()
    adapter = Adapter(connection)
    checkpoint = DurableFtpCheckpoint(adapter, source_key="shared-connection-test")
    monkeypatch.setattr(ftp_main, "EventStorage", Storage)
    monkeypatch.setattr(ftp_main, "HlstatsRuntime", Runtime)
    monkeypatch.setattr(ftp_main, "write_last_mtime", lambda *_: None)

    assert (
        ftp_main._import_logs_batch(
            [entry],
            tmp_path,
            args=args,
            settings=settings,
            last_path=tmp_path / ".last",
            checkpoint_store=checkpoint,
            adapter=adapter,  # type: ignore[arg-type]
        )
        == 1
    )

    sql_actions = [action for action in connection.actions if action[0] == "sql"]
    assert all(action[1] == id(connection) for action in sql_actions)
    game_write = next(index for index, action in enumerate(sql_actions) if "Events_Frags" in str(action[2]))
    checkpoint_write = next(
        index for index, action in enumerate(sql_actions) if "hlstats_FTP_Checkpoints" in str(action[2])
    )
    commit_index = connection.actions.index(("commit", id(connection)))
    checkpoint_sql_index = connection.actions.index(sql_actions[checkpoint_write])
    game_sql_index = connection.actions.index(sql_actions[game_write])
    begin_index = connection.actions.index(("autocommit", id(connection), False))
    assert game_write < checkpoint_write
    assert begin_index < game_sql_index < checkpoint_sql_index < commit_index
    assert adapter.ping_modes == [True, False]
