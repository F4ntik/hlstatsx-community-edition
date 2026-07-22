# Prefix-100 validation: durable FTP InnoDB migration

## Scope

This note records validation of
`sql/migrations/2026_07_22_0500.sql`.  It is an operator-applied production
schema migration that converts the exact `hlstats_ftp_py` write set to InnoDB;
it has no data DML.

## Migration-specific acceptance

On a disposable MariaDB schema, copies of all 22 importer-write tables were
first forced to MyISAM. The checkpoint migration and `2026_07_22_0500.sql`
then applied successfully. `information_schema` reported 22/22 write tables
and `hlstats_FTP_Checkpoints` as InnoDB, and the real
`DurableFtpCheckpoint.verify_schema()` call passed.

Focused source validation passed:

- `python -m pytest -q scripts/hlstats_ftp_py/tests
  scripts/replay_baseline/tests/test_restore_baseline_ftp_checkpoint.py`
  — 34 passed;
- static migration contract — legacy comment markers, no checkpoint DDL, and
  ordered `ALTER TABLE ... ENGINE=InnoDB` targets exactly match
  `DurableFtpCheckpoint._MUTATED_TABLES`.

## Prefix-100 replay gate

`Run-DualContour-1000.ps1 -MaxImportFiles 100 -ArtifactLabel prefix-100
-EvidenceRunId 20260722-ftp-innodb-prefix-100-r1 -UseDumpRestore -SkipBuild`
completed successfully. Both containers reached 602 `hlstats_Events_Frags`.

After the required Python GeoIP backfill, the logical compare was **not
green**: `hlstats_Players_History` contained two Python-only bot rows for
`49.5 % FalleN` and `49.5 % cyx` on `2024-01-02`.

This is not attributed to the new migration:

- the replay runner does not invoke `2026_07_22_0500.sql`;
- its pre-existing disposable hook conditionally converts the same 22 tables
  for both legacy and Python contours after restore; and
- the new migration has no data manipulation statements.

The broader bot/`Players_History` mismatch family predates this work, but the
retained prior prefix evidence does not establish these exact two stable-key
rows as accepted. Treat them as a separate unclassified parity follow-up; do
not mark the prefix logical-parity gate green merely because the migration is
causally independent.
