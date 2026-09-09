# Trusted web database update

The web updater is never a public route. `hlstats.php?mode=updater` returns
`403`, and the `web/updater/` directory stays in the release only for the
trusted command-line runner.

Run the following during a maintenance window, after a verified database
backup. Stop or pause the FTP/import workers first: the runtime-table
conversion can rebuild and lock tables.

1. Confirm that the runner and migration files were shipped without touching a
   database:

   ```bash
   php scripts/run_web_updater.php --check
   ```

2. For an older MyISAM runtime database, apply the runtime prerequisites with
   the configured database client. The checkpoint table must come first:

   ```bash
   mysql --defaults-extra-file=/path/to/hlstats.cnf < sql/migrations/2026_07_22_ftp_checkpoint.sql
   mysql --defaults-extra-file=/path/to/hlstats.cnf < sql/migrations/2026_07_22_0500.sql
   ```

   Do not run this conversion against an active importer. Its `ALTER TABLE`
   statements are not cross-table atomic. If the runtime tables are already
   InnoDB and `hlstats_FTP_Checkpoints` exists, retain the existing evidence
   instead of repeating the conversion.

3. Run the numbered web migrations from the trusted CLI path:

   ```bash
   php scripts/run_web_updater.php
   ```

   Migration `83` widens `hlstats_Users.password` to `varchar(255)` before the
   application writes modern password hashes. It does not run a runtime
   `ALTER TABLE` during ordinary requests.

4. Read back the result before restarting workers:

   ```sql
   SELECT value FROM hlstats_Options WHERE keyname = 'dbversion';
   SHOW COLUMNS FROM hlstats_Users LIKE 'password';
   ```

   The expected database version is `83`, and the password column is
   `varchar(255)`.

For the full-stack Docker image, the same runner is available at
`/var/www/scripts/run_web_updater.php`. The image intentionally retains the
non-public `updater` files. Run the SQL prerequisites with the database
container or an approved operator client, then use the web container only for
the CLI runner.
