# FTP durable InnoDB migration design

## Decision

Add a separate, operator-applied production migration in `sql/migrations/`
that converts the exact database write set of `hlstats_ftp_py` to InnoDB.  The
existing `2026_07_22_ftp_checkpoint.sql` remains unchanged: it creates the new
durable cursor table and is applied first.

The new file follows the native legacy migration convention:

- timestamp-style filename: `2026_07_22_0500.sql`;
- `:? Reason`, `:i Info`, and `:! Change` comment header;
- direct `ALTER TABLE ... ENGINE=InnoDB` statements intended for an attended
  operator run, not an application-startup migration runner.

## Scope

The migration converts precisely the 22 tables listed by
`DurableFtpCheckpoint._MUTATED_TABLES`.  It makes no data changes, does not
alter unrelated legacy read tables, and does not modify the existing
checkpoint DDL.

The operator takes a backup and runs the two migrations in this order during a
maintenance window:

1. `sql/migrations/2026_07_22_ftp_checkpoint.sql`
2. `sql/migrations/2026_07_22_0500.sql`

`ALTER TABLE` is not a cross-table transaction and can lock or rebuild tables;
the application therefore continues to fail closed before FTP work if any
required table remains missing or non-InnoDB.  An operator may retain the
explicit `--legacy-file-marker` path only when accepting its non-atomic
semantics.

## Regression contract

A focused test parses the migration and asserts that its ordered target set is
identical to `DurableFtpCheckpoint._MUTATED_TABLES`.  Documentation includes
the preflight, backup, apply, and postflight procedure.  Validation consists
of FTP checkpoint tests, migration-contract tests, syntax/diff checks, and a
fresh `narrow-100` replay after the source checks pass.
