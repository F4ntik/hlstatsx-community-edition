from __future__ import annotations

import os
from io import StringIO
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from hlstats_awards_py import cli


@contextmanager
def change_cwd(path: Path) -> Iterator[None]:
    original = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original)


def write_config(path: Path, **values: str) -> None:
    lines = [f"{key} {value}\n" for key, value in values.items()]
    path.write_text("".join(lines), encoding="utf-8")


def test_load_settings_uses_default_actions(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(
        config_path,
        DBHost="db.example",
        DBUsername="user",
        DBPassword="secret",
        DBName="hlstats",
        CpanelHack="1",
    )

    with change_cwd(tmp_path):
        settings = cli.load_settings([])

    assert settings.actions == cli.DEFAULT_ACTIONS
    assert settings.database.host == "db.example"
    assert settings.database.username == "user"
    assert settings.database.password == "secret"
    assert settings.database.name == "hlstats"
    assert settings.database.cpanel_hack is True
    assert settings.config_path == config_path.resolve()


def test_cli_flags_override_default_config(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(
        config_path,
        DBHost="db.example",
        DBUsername="user",
        DBPassword="secret",
        DBName="hlstats",
    )

    with change_cwd(tmp_path):
        settings = cli.load_settings([
            "--db-host",
            "cli.example",
            "--db-username",
            "cli-user",
        ])

    assert settings.database.host == "cli.example"
    assert settings.database.username == "cli-user"
    assert settings.database.password == "secret"
    assert settings.database.name == "hlstats"


def test_explicit_configfile_overrides_cli(tmp_path: Path) -> None:
    default_config = tmp_path / "hlstats.conf"
    write_config(
        default_config,
        DBHost="default",
        DBUsername="user",
        DBPassword="secret",
        DBName="hlstats",
    )

    override_config = tmp_path / "override.conf"
    write_config(
        override_config,
        DBHost="override",
        DBUsername="override-user",
        DBPassword="override-secret",
        DBName="override-db",
    )

    with change_cwd(tmp_path):
        settings = cli.load_settings([
            "--db-host",
            "cli.example",
            "--configfile",
            str(override_config),
        ])

    assert settings.database.host == "override"
    assert settings.database.username == "override-user"
    assert settings.database.password == "override-secret"
    assert settings.database.name == "override-db"
    assert settings.config_path == override_config.resolve()


def test_requested_actions_are_respected(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(
        config_path,
        DBHost="default",
    )

    with change_cwd(tmp_path):
        settings = cli.load_settings([
            "--awards",
            "--geoip",
        ])

    assert settings.actions == frozenset({cli.AwardsAction.AWARDS, cli.AwardsAction.GEOIP})


def test_replay_mode_enables_replay_safe_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(config_path, DBHost="default")

    with change_cwd(tmp_path):
        settings = cli.load_settings(["--replay-mode"])

    assert settings.cli.replay_mode is True
    assert settings.policy is cli.RuntimePolicy.REPLAY_SAFE


def test_date_and_numdays_are_parsed(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(config_path)

    with change_cwd(tmp_path):
        settings = cli.load_settings([
            "--date",
            "2024-01-05",
            "--numdays",
            "3",
        ])

    assert settings.cli.date == date(2024, 1, 5)
    assert settings.cli.numdays == 3


def test_missing_configfile_raises(tmp_path: Path) -> None:
    with change_cwd(tmp_path):
        with pytest.raises(FileNotFoundError):
            cli.load_settings([
                "--configfile",
                "missing.conf",
            ])


def test_main_runs_calculator_and_closes_adapter(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(
        config_path,
        DBHost="db.example",
        DBUsername="user",
        DBPassword="secret",
        DBName="hlstats",
    )

    calls: list[str] = []

    class FakeAdapter:
        def __init__(self, config) -> None:
            calls.append(f"adapter:{config.host}:{config.port}")

        def connect(self) -> None:
            calls.append("connect")

        def close(self) -> None:
            calls.append("close")

        def connection(self):  # pragma: no cover - compatibility only
            raise AssertionError("calculator should not request the connection in this test")

    class FakeCalculator:
        def __init__(self, adapter, *, verbose: bool = False) -> None:
            assert verbose is False
            assert isinstance(adapter, FakeAdapter)

        def run(self, settings) -> None:
            assert settings.database.host == "db.example"
            calls.append("run")

    with change_cwd(tmp_path):
        with patch("hlstats_awards_py.cli.SyncDatabaseAdapter", FakeAdapter):
            with patch("hlstats_awards_py.calculator.AwardsCalculator", FakeCalculator):
                assert cli.main(["--geoip"]) == 0

    assert calls == ["adapter:db.example:3306", "connect", "run", "close"]


def test_main_reports_runtime_error(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    write_config(
        config_path,
        DBHost="db.example",
        DBUsername="user",
        DBPassword="secret",
        DBName="hlstats",
    )

    class FakeAdapter:
        def __init__(self, _config) -> None:
            pass

        def connect(self) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeCalculator:
        def __init__(self, _adapter, *, verbose: bool = False) -> None:
            assert verbose is False

        def run(self, _settings) -> None:
            raise RuntimeError("boom")

    stderr = StringIO()
    with change_cwd(tmp_path):
        with patch("hlstats_awards_py.cli.SyncDatabaseAdapter", FakeAdapter):
            with patch("hlstats_awards_py.calculator.AwardsCalculator", FakeCalculator):
                with patch("sys.stderr", stderr):
                    assert cli.main(["--geoip"]) == 1

    assert "boom" in stderr.getvalue()
