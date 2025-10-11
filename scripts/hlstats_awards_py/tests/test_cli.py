from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

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
