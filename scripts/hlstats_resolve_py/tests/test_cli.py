from __future__ import annotations

from pathlib import Path

import pytest

from hlstats_resolve_py import cli


def test_load_settings_uses_config_and_cli_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost db.internal:3308",
                "DBUsername hlstats",
                "DBPassword secret",
                "DBName hlstats_prod",
                "DNSTimeout 7",
                "DebugLevel 2",
            ]
        )
    )

    settings = cli.load_settings(
        [
            "--configfile",
            str(config_path),
            "--db-host",
            "db.example.net:3310",
            "--debug",
            "--nodebug",
            "--dns-timeout",
            "9",
        ]
    )

    assert settings.database.host == "db.example.net:3310"
    assert settings.database.name == "hlstats_prod"
    assert settings.database.username == "hlstats"
    assert settings.database.password == "secret"
    assert settings.dns_timeout == 9
    assert settings.debug_level == 2
    assert settings.config_path == config_path.resolve()


def test_load_settings_validates_dns_timeout(tmp_path: Path) -> None:
    config_path = tmp_path / "broken.conf"
    config_path.write_text("DNSTimeout not-a-number\n")

    with pytest.raises(cli.ResolveCliError):
        cli.load_settings(["--configfile", str(config_path)])


def test_main_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["--version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "hlstats-resolve.py" in captured.out
