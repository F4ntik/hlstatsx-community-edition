"""Tests for the command line interface helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from proxy_daemon_py import cli
from proxy_daemon_py.log import LogLevel


def _write_basic_config(tmp_path: Path) -> Path:
    config_file = tmp_path / "hlstats.conf"
    config_file.write_text(
        """
        DBHost "127.0.0.1"
        DBUsername "hlstats"
        DBPassword "secret"
        DBName "hlstats_db"
        Port 27500
        EventQueueSize 10
        """,
        encoding="utf-8",
    )
    return config_file


def test_parse_args_returns_cli_options(tmp_path: Path) -> None:
    config_file = _write_basic_config(tmp_path)

    parsed = cli.parse_args(["--configfile", str(config_file), "--debug", "--foreground"])

    assert parsed.configfile == config_file
    assert parsed.debug is True
    assert parsed.foreground is True


def test_load_settings_combines_cli_and_config(tmp_path: Path) -> None:
    config_file = _write_basic_config(tmp_path)

    settings = cli.load_settings(["--configfile", str(config_file)])

    assert settings.cli.configfile == config_file
    assert settings.cli.debug is False
    assert settings.config.db_host == "127.0.0.1"
    assert settings.log_level is LogLevel.BALANCE


def test_load_settings_honours_debug_override(tmp_path: Path) -> None:
    config_file = _write_basic_config(tmp_path)

    settings = cli.load_settings(["--configfile", str(config_file), "--debug"])

    assert settings.log_level is LogLevel.NOTICE


def test_cli_module_exits_successfully(tmp_path: Path) -> None:
    config_file = _write_basic_config(tmp_path)
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()

    result = subprocess.run(
        [sys.executable, "-m", "proxy_daemon_py.cli", "--configfile", str(config_file)],
        cwd=project_root,
        env=env,
        check=False,
    )

    assert result.returncode == 0


def test_main_reports_errors(tmp_path: Path) -> None:
    missing = tmp_path / "absent.conf"

    result = cli.main(["--configfile", str(missing)])

    assert result == 1
