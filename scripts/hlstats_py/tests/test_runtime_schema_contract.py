from __future__ import annotations

import re
from pathlib import Path


_RUNTIME_TRANSACTION_TABLES = (
    "hlstats_Actions",
    "hlstats_Events_Admin",
    "hlstats_Events_ChangeTeam",
    "hlstats_Events_Chat",
    "hlstats_Events_Connects",
    "hlstats_Events_Disconnects",
    "hlstats_Events_Entries",
    "hlstats_Events_Frags",
    "hlstats_Events_PlayerActions",
    "hlstats_Events_PlayerPlayerActions",
    "hlstats_Events_Statsme",
    "hlstats_Events_Statsme2",
    "hlstats_Events_Suicides",
    "hlstats_Events_TeamBonuses",
    "hlstats_Events_Teamkills",
    "hlstats_Maps_Counts",
    "hlstats_PlayerNames",
    "hlstats_Players",
    "hlstats_Players_History",
    "hlstats_PlayerUniqueIds",
    "hlstats_Servers",
    "hlstats_Weapons",
)


def _migration_tables(sql: str) -> list[str]:
    return re.findall(
        r"(?im)^\s*ALTER\s+TABLE\s+`([^`]+)`\s+ENGINE\s*=\s*InnoDB\s*;\s*$",
        sql,
    )


def _install_table_engines(sql: str) -> dict[str, str]:
    return {
        table: engine.upper()
        for table, engine in re.findall(
            r"(?ims)^\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+`([^`]+)`.*?\)\s*ENGINE\s*=\s*([A-Za-z0-9_]+)",
            sql,
        )
    }


def test_runtime_transaction_write_set_is_innodb_for_installs_and_upgrades() -> None:
    repository_root = Path(__file__).parents[3]
    storage_source = (repository_root / "scripts" / "hlstats_py" / "storage.py").read_text(
        encoding="utf-8"
    )
    install_sql = (repository_root / "sql" / "install.sql").read_text(encoding="utf-8")
    migration_sql = (
        repository_root / "sql" / "migrations" / "2026_07_22_0500.sql"
    ).read_text(encoding="utf-8")

    write_tables = set(
        re.findall(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+`?(hlstats_[A-Za-z0-9_]+)",
            storage_source,
        )
    )
    expected = set(_RUNTIME_TRANSACTION_TABLES)
    assert write_tables == expected
    assert _migration_tables(migration_sql) == list(_RUNTIME_TRANSACTION_TABLES)

    install_engines = _install_table_engines(install_sql)
    missing = sorted(expected - install_engines.keys())
    non_innodb = sorted(table for table in expected if install_engines.get(table) != "INNODB")

    assert not missing, f"install.sql is missing transactional tables: {missing}"
    assert not non_innodb, f"install.sql transactional tables must use InnoDB: {non_innodb}"
