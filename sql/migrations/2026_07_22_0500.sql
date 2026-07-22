/*
:? Reason: Durable FTP checkpoints must commit with every table the importer
            can mutate, rather than with a MyISAM subset that auto-commits.
:i Info: Apply `2026_07_22_ftp_checkpoint.sql` first. Run this file once in a
         maintenance window after a verified backup; `ALTER TABLE` can rebuild
         and lock a table, and this migration is not cross-table atomic.
:! Change: Convert the exact hlstats_ftp_py EventStorage write set to InnoDB.
*/

ALTER TABLE `hlstats_Actions` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Admin` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_ChangeTeam` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Chat` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Connects` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Disconnects` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Entries` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Frags` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_PlayerActions` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_PlayerPlayerActions` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Statsme` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Statsme2` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Suicides` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_TeamBonuses` ENGINE=InnoDB;
ALTER TABLE `hlstats_Events_Teamkills` ENGINE=InnoDB;
ALTER TABLE `hlstats_Maps_Counts` ENGINE=InnoDB;
ALTER TABLE `hlstats_PlayerNames` ENGINE=InnoDB;
ALTER TABLE `hlstats_Players` ENGINE=InnoDB;
ALTER TABLE `hlstats_Players_History` ENGINE=InnoDB;
ALTER TABLE `hlstats_PlayerUniqueIds` ENGINE=InnoDB;
ALTER TABLE `hlstats_Servers` ENGINE=InnoDB;
ALTER TABLE `hlstats_Weapons` ENGINE=InnoDB;
