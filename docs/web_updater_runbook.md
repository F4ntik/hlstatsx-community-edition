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

   Migration `83` remains the normal `82`-to-`83` path that widens
   `hlstats_Users.password` before the application writes modern password
   hashes. After all numbered migrations, the trusted CLI reads the physical
   password column. If it finds a `varchar` narrower than `255`, it widens the
   column once and reads it back before reporting success. Existing
   `varchar(255)` or wider columns are retained unchanged. The runner fails
   closed for a missing, incompatible, unreadable, or unrepairable column. It
   does not run a runtime `ALTER TABLE` during ordinary requests.

   The runner accepts database version `83` or newer. A database that already
   reports a newer schema and application version, such as `89` / `1.11.4`,
   keeps those values: the compatibility repair changes only a narrow password
   column and does not replay migration `83` or rewrite option metadata.

4. Read back the result before restarting workers:

   ```sql
   SELECT keyname, value
   FROM hlstats_Options
   WHERE keyname IN ('dbversion', 'version');

   SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
   FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = DATABASE()
     AND TABLE_NAME = 'hlstats_Users'
     AND COLUMN_NAME = 'password';
   ```

   The expected database version is `83` after an older upgrade, or the
   unchanged original value when it was already newer. The password column must
   be `varchar` with capacity `255` or greater. Preserve the observed
   application version when the database was already newer.

For the full-stack Docker image, the same runner is available at
`/var/www/scripts/run_web_updater.php`. The image intentionally retains the
non-public `updater` files. Run the SQL prerequisites with the database
container or an approved operator client, then use the web container only for
the CLI runner.
