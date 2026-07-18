from __future__ import annotations

import argparse
import importlib.util
import io
import struct
from pathlib import Path

import pytest


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "replay_python_log.py"
    spec = importlib.util.spec_from_file_location("replay_python_log_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


replay_python_log = _load_module()


def _fr(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + payload


def test_warn_if_unthrottled_udp_replay_prints_once_for_zero(capsys: pytest.CaptureFixture[str]) -> None:
    replay_python_log.warn_if_unthrottled_udp_replay(0)
    err = capsys.readouterr().err
    assert "UDP" in err
    assert "parity" in err.lower()


def test_warn_if_unthrottled_udp_replay_silent_for_positive_delay(capsys: pytest.CaptureFixture[str]) -> None:
    replay_python_log.warn_if_unthrottled_udp_replay(0.005)
    assert capsys.readouterr().err == ""


def test_resolve_log_paths_accepts_single_file(tmp_path: Path) -> None:
    log_path = tmp_path / "L0000001.log"
    log_path.write_text("line\n", encoding="utf-8")

    result = replay_python_log.resolve_log_paths(log_path)

    assert result == [log_path]


def test_resolve_log_paths_sorts_directory_and_filters_non_logs(tmp_path: Path) -> None:
    (tmp_path / "L0000003.log").write_text("c\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "L0000001.log").write_text("a\n", encoding="utf-8")
    (tmp_path / "L0000002.LOG").write_text("b\n", encoding="utf-8")

    result = replay_python_log.resolve_log_paths(tmp_path)

    assert [path.name for path in result] == [
        "L0000001.log",
        "L0000002.LOG",
        "L0000003.log",
    ]


def test_resolve_log_paths_raises_for_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.log"

    with pytest.raises(FileNotFoundError):
        replay_python_log.resolve_log_paths(missing)


def test_write_manifest_uses_lf_for_cross_platform_evidence(tmp_path: Path) -> None:
    output = tmp_path / "input.txt"
    replay_python_log.write_manifest(
        str(output),
        [tmp_path / "L0000001.log", tmp_path / "L0000002.log"],
    )

    assert output.read_bytes() == b"L0000001.log\nL0000002.log\n"


def test_sender_script_streams_stdin_without_buffering_corpus() -> None:
    sender_script = replay_python_log.build_sender_script()

    assert "struct.unpack" in sender_script
    assert "while True:" in sender_script
    assert "sys.stdin.buffer.read().splitlines()" not in sender_script


def test_run_sender_reports_processed_skipped_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    processed = tmp_path / "L0000001.log"
    processed.write_bytes(b"first line\nsecond line\n")
    skipped = tmp_path / "L0000002.log"
    skipped.write_bytes(b"\n\r\n")
    unreadable = tmp_path / "L0000003.log"

    class FakePipe:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

        def write(self, data: bytes) -> int:
            return self.buffer.write(data)

        def close(self) -> None:
            return None

    class FakeProcess:
        def __init__(self, command: list[str]) -> None:
            self.command = command
            self.stdin = FakePipe()

        def wait(self) -> int:
            return 0

    created: list[FakeProcess] = []
    original_open = Path.open

    def fake_popen(command: list[str], stdin: int | None = None) -> FakeProcess:
        assert stdin is replay_python_log.subprocess.PIPE
        process = FakeProcess(command)
        created.append(process)
        return process

    def fake_open(path: Path, *args, **kwargs):
        if path == unreadable:
            raise OSError("boom")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(replay_python_log.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(Path, "open", fake_open)

    args = argparse.Namespace(
        worker_container="hlstatsx-python-worker",
        server_identity="37.230.137.48:27015",
        worker_port=28000,
        skip_reload=False,
        send_delay=0.005,
        drain_delay=1.0,
    )

    summary = replay_python_log.run_sender(
        args=args,
        proxy_key="secret",
        log_paths=[processed, skipped, unreadable],
    )

    assert summary == replay_python_log.ReplaySummary(
        processed=1,
        skipped=1,
        errors=1,
        dropped_lines=0,
    )
    assert len(created) == 1
    assert created[0].stdin.buffer.getvalue() == _fr(b"first line") + _fr(b"second line")


def test_run_sender_inserts_separator_between_files_without_trailing_newline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "L0000001.log"
    first.write_bytes(b"alpha")
    second = tmp_path / "L0000002.log"
    second.write_bytes(b"beta\n")

    class FakePipe:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

        def write(self, data: bytes) -> int:
            return self.buffer.write(data)

        def close(self) -> None:
            return None

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakePipe()

        def wait(self) -> int:
            return 0

    process = FakeProcess()

    def fake_popen(command: list[str], stdin: int | None = None) -> FakeProcess:
        assert stdin is replay_python_log.subprocess.PIPE
        return process

    monkeypatch.setattr(replay_python_log.subprocess, "Popen", fake_popen)

    args = argparse.Namespace(
        worker_container="hlstatsx-python-worker",
        server_identity="37.230.137.48:27015",
        worker_port=28000,
        skip_reload=True,
        send_delay=0.005,
        drain_delay=1.0,
    )

    summary = replay_python_log.run_sender(
        args=args,
        proxy_key="secret",
        log_paths=[first, second],
    )

    assert summary == replay_python_log.ReplaySummary(
        processed=2,
        skipped=0,
        errors=0,
        dropped_lines=0,
    )
    assert process.stdin.buffer.getvalue() == _fr(b"alpha") + _fr(b"beta")


def test_run_sender_merges_multiline_rcon_continuation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_path = tmp_path / "L0101069.log"
    log_path.write_bytes(
        b'L 01/01/2025 - 00:04:34: Rcon: "rcon 428864746 A9k3T2v6L1m4P7n8B5q0R3wF8 ultrahc_ds_get_info\n'
        b'" from "94.198.219.159:34557"\n'
        b'L 01/01/2025 - 00:04:37: World triggered "Round_Start"\n'
    )

    class FakePipe:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

        def write(self, data: bytes) -> int:
            return self.buffer.write(data)

        def close(self) -> None:
            return None

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakePipe()

        def wait(self) -> int:
            return 0

    process = FakeProcess()

    def fake_popen(command: list[str], stdin: int | None = None) -> FakeProcess:
        assert stdin is replay_python_log.subprocess.PIPE
        return process

    monkeypatch.setattr(replay_python_log.subprocess, "Popen", fake_popen)

    args = argparse.Namespace(
        worker_container="hlstatsx-python-worker",
        server_identity="37.230.137.48:27015",
        worker_port=28000,
        skip_reload=True,
        send_delay=0.005,
        drain_delay=1.0,
        dropped_lines_manifest="",
    )

    summary = replay_python_log.run_sender(
        args=args,
        proxy_key="secret",
        log_paths=[log_path],
    )

    assert summary == replay_python_log.ReplaySummary(
        processed=1,
        skipped=0,
        errors=0,
        dropped_lines=0,
    )
    merged = (
        b'L 01/01/2025 - 00:04:34: Rcon: "rcon 428864746 A9k3T2v6L1m4P7n8B5q0R3wF8 ultrahc_ds_get_info\n'
        b'" from "94.198.219.159:34557"'
    )
    second = b'L 01/01/2025 - 00:04:37: World triggered "Round_Start"'
    assert process.stdin.buffer.getvalue() == _fr(merged) + _fr(second)


def test_run_sender_preserves_player_identity_tokens_in_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "L0103000.log"
    line = (
        b'L 01/01/2025 - 00:04:34: '
        b'"Alice<2><STEAM_1:1:111><CT>" killed "Bob<3><STEAM_0:1:222><TERRORIST>" with "ak47"\n'
    )
    log_path.write_bytes(line)

    class FakePipe:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

        def write(self, data: bytes) -> int:
            return self.buffer.write(data)

        def close(self) -> None:
            return None

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakePipe()

        def wait(self) -> int:
            return 0

    process = FakeProcess()

    def fake_popen(command: list[str], stdin: int | None = None) -> FakeProcess:
        assert stdin is replay_python_log.subprocess.PIPE
        return process

    monkeypatch.setattr(replay_python_log.subprocess, "Popen", fake_popen)

    args = argparse.Namespace(
        worker_container="hlstatsx-python-worker",
        server_identity="37.230.137.48:27015",
        worker_port=28000,
        skip_reload=True,
        send_delay=0.005,
        drain_delay=1.0,
        dropped_lines_manifest="",
    )

    summary = replay_python_log.run_sender(
        args=args,
        proxy_key="secret",
        log_paths=[log_path],
    )

    assert summary == replay_python_log.ReplaySummary(
        processed=1,
        skipped=0,
        errors=0,
        dropped_lines=0,
    )
    payload = process.stdin.buffer.getvalue()
    assert b"STEAM_1:1:111" in payload
    assert b"STEAM_0:1:222" in payload
