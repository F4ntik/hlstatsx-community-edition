"""Static contract for the disposable P1 FTP checkpoint migration hook."""

from __future__ import annotations

import re
from pathlib import Path

from hlstats_ftp_py.checkpoint import DurableFtpCheckpoint


def test_disposable_restore_applies_ftp_checkpoint_migration_before_bootstrap() -> None:
    script = Path("scripts/replay_baseline/restore-baseline.ps1").read_text(encoding="utf-8")

    assert '$ftpCheckpointMigration = Join-Path $repoRoot "sql\\migrations\\2026_07_22_ftp_checkpoint.sql"' in script
    assert "function Invoke-DisposableFtpCheckpointMigration" in script
    assert "CREATE TABLE" not in script
    assert 'docker cp $ftpCheckpointMigration "${dbContainer}:$containerMigrationPath"' in script
    assert 'WHERE TABLE_SCHEMA = \'$DatabaseName\' AND TABLE_NAME = \'hlstats_FTP_Checkpoints\';' in script
    assert 'if ($engine -ne "InnoDB")' in script

    dump_restore = script.index('gzip -dc /tmp/baseline_reset.sql.gz | mysql -uroot -proot123 $DatabaseName')
    preparation = script.index("    Invoke-DisposableFtpDurableSchemaPreparation", dump_restore)
    bootstrap = script.index("    Invoke-ReplayServerBootstrap", preparation)
    preflight = script.index("    Invoke-StateChecks", bootstrap)
    assert dump_restore < preparation < bootstrap < preflight


def test_disposable_migration_hook_is_limited_to_restore_paths() -> None:
    script = Path("scripts/replay_baseline/restore-baseline.ps1").read_text(encoding="utf-8")

    dump_function = script.index("function Invoke-DumpRestore")
    snapshot_function = script.index("function Invoke-SnapshotRestore")
    first_hook = script.index("    Invoke-DisposableFtpDurableSchemaPreparation")
    second_hook = script.index("    Invoke-DisposableFtpDurableSchemaPreparation", first_hook + 1)
    snapshot_preflight = script.index("    Invoke-StateChecks", second_hook)
    assert dump_function < first_hook < snapshot_function < second_hook < snapshot_preflight
    assert "--legacy-file-marker" not in script


def test_disposable_engine_conversion_is_exactly_the_ftp_importer_write_set() -> None:
    script = Path("scripts/replay_baseline/restore-baseline.ps1").read_text(encoding="utf-8")
    table_block = re.search(r"\$ftpImporterWriteTables = @\((.*?)\n\)", script, re.DOTALL)
    assert table_block is not None
    restored_tables = tuple(re.findall(r'"(hlstats_[A-Za-z0-9_]+)"', table_block.group(1)))

    assert restored_tables == DurableFtpCheckpoint._MUTATED_TABLES
    assert "function Invoke-DisposableFtpImporterEngineMigration" in script
    assert "foreach ($table in $ftpImporterWriteTables)" in script
    assert 'Invoke-ContainerMysql -Sql "ALTER TABLE $table ENGINE=InnoDB;"' in script
    assert "ALTER TABLE hlstats_" not in script

    preparation = script.index("function Invoke-DisposableFtpDurableSchemaPreparation")
    checkpoint = script.index("Invoke-DisposableFtpCheckpointMigration", preparation)
    engine = script.index("Invoke-DisposableFtpImporterEngineMigration", checkpoint)
    assert preparation < checkpoint < engine
