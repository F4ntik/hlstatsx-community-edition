"""Tests for the configuration parser."""

from __future__ import annotations

from pathlib import Path

import pytest
from proxy_daemon_py import config


def test_load_config_parses_known_keys(tmp_path: Path) -> None:
    config_file = tmp_path / "hlstats.conf"
    config_file.write_text(
        """
        # comment line
        DBHost "127.0.0.1"
        DBUsername "hlstats"
        DBPassword "secret"
        DBName "hlstats_db"
        BindIP ""
        Port 27501
        DebugLevel 2
        EventQueueSize 32
        CpanelHack 1
        ExtraOption "keep me"
        """,
        encoding="utf-8",
    )

    loaded = config.load_config(config_file)

    assert loaded.config_path == config_file.resolve()
    assert loaded.db_host == "127.0.0.1"
    assert loaded.db_username == "hlstats"
    assert loaded.db_password == "secret"
    assert loaded.db_name == "hlstats_db"
    assert loaded.bind_ip is None
    assert loaded.port == 27501
    assert loaded.debug_level == 2
    assert loaded.event_queue_size == 32
    assert loaded.cpanel_hack is True
    assert loaded.get("ExtraOption") == "keep me"


def test_load_config_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "absent.conf"

    with pytest.raises(FileNotFoundError):
        config.load_config(missing)


def test_load_config_rejects_invalid_line(tmp_path: Path) -> None:
    config_file = tmp_path / "broken.conf"
    config_file.write_text("DBHost\n", encoding="utf-8")

    with pytest.raises(config.ConfigError):
        config.load_config(config_file)
