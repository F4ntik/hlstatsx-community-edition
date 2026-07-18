from __future__ import annotations

import sys
from pathlib import Path

import pytest

from replay_baseline import direct_import_artifacts as direct


def test_continue_on_parse_error_requires_manifest_before_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["direct_import_artifacts.py", "--continue-on-parse-error"],
    )

    with pytest.raises(SystemExit) as exc_info:
        direct._parse_args()

    assert exc_info.value.code == 2
    assert "--continue-on-parse-error requires --ignored-lines-manifest" in capsys.readouterr().err


def test_direct_cli_writes_sorted_input_manifest_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "b.log").write_text("b", encoding="utf-8")
    (artifacts / "a.log").write_text("a", encoding="utf-8")
    config = tmp_path / "hlstats.conf"
    config.write_text("placeholder", encoding="utf-8")
    work = tmp_path / "work"
    manifest = tmp_path / "audit" / "input.txt"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "direct_import_artifacts.py",
            "--artifacts-dir",
            str(artifacts),
            "--configfile",
            str(config),
            "--work-dir",
            str(work),
            "--input-manifest",
            str(manifest),
        ],
    )
    monkeypatch.setattr(direct, "_build_runtime_settings", lambda args: object())

    def fake_import(entries, read_dir, **kwargs) -> int:
        captured["names"] = [entry.name for entry in entries]
        return 7

    monkeypatch.setattr(direct, "_import_logs_batch", fake_import)

    assert direct.main() == 0
    assert captured["names"] == ["a.log", "b.log"]
    assert manifest.read_text(encoding="utf-8") == "a.log\nb.log\n"


def test_direct_cli_passes_ignored_manifest_to_importer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "a.log").write_text("synthetic", encoding="utf-8")
    config = tmp_path / "hlstats.conf"
    config.write_text("placeholder", encoding="utf-8")
    ignored_manifest = tmp_path / "audit" / "ignored.txt"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "direct_import_artifacts.py",
            "--artifacts-dir",
            str(artifacts),
            "--configfile",
            str(config),
            "--work-dir",
            str(tmp_path / "work"),
            "--ignored-lines-manifest",
            str(ignored_manifest),
            "--continue-on-parse-error",
        ],
    )
    monkeypatch.setattr(direct, "_build_runtime_settings", lambda args: object())

    def fake_import(entries, read_dir, **kwargs) -> int:
        captured["continue_on_parse_error"] = kwargs["continue_on_parse_error"]
        handle = kwargs["ignored_lines_manifest"]
        assert handle is not None
        handle.write("a.log:1:parse-error:synthetic\tpayload\n")
        return 1

    monkeypatch.setattr(direct, "_import_logs_batch", fake_import)

    assert direct.main() == 0
    assert captured["continue_on_parse_error"] is True
    assert "a.log:1:parse-error:synthetic" in ignored_manifest.read_text(encoding="utf-8")


def test_direct_cli_propagates_fail_fast_parse_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "a.log").write_text("synthetic", encoding="utf-8")
    config = tmp_path / "hlstats.conf"
    config.write_text("placeholder", encoding="utf-8")
    ignored_manifest = tmp_path / "audit" / "ignored-fail-fast.txt"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "direct_import_artifacts.py",
            "--artifacts-dir",
            str(artifacts),
            "--configfile",
            str(config),
            "--work-dir",
            str(tmp_path / "work"),
            "--ignored-lines-manifest",
            str(ignored_manifest),
        ],
    )
    monkeypatch.setattr(direct, "_build_runtime_settings", lambda args: object())

    def fake_import(entries, read_dir, **kwargs) -> int:
        assert kwargs["continue_on_parse_error"] is False
        handle = kwargs["ignored_lines_manifest"]
        assert handle is not None
        handle.write("a.log:1:parse-error:synthetic-fail-fast\n")
        raise ValueError("synthetic-fail-fast")

    monkeypatch.setattr(direct, "_import_logs_batch", fake_import)

    with pytest.raises(ValueError, match="synthetic-fail-fast"):
        direct.main()

    assert "synthetic-fail-fast" in ignored_manifest.read_text(encoding="utf-8")
