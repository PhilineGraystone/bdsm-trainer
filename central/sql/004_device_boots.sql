-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.2 — boot and crash history of the devices (project document 42/43)
--
-- One row per START of a device. Not per hello: the hello is retained at the
-- broker and is re-sent on request, so the same start would arrive again and
-- again. What makes a start count once is the boot id the device draws when it
-- comes up — (device, boot id) is unique here, and the writer uses INSERT
-- IGNORE.
--
-- "MagLock restarted three times today because of a brownout" is then
--
--   SELECT db_reason, COUNT(*) FROM device_boots
--    WHERE db_device = ? AND db_seen >= CURDATE() GROUP BY db_reason;
--
-- The columns about the PREVIOUS life (uptime, last command, last error) are
-- NULL when the device could not tell — after a power loss its RTC memory is
-- gone. NULL, not 0: zero would be a statement.

CREATE TABLE IF NOT EXISTS device_boots (
  db_id         bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  db_device     varchar(60)  NOT NULL,                 -- device UUID (topic address)
  db_boot_id    varchar(16)  NOT NULL,                 -- drawn by the device at start
  db_seen       datetime     NOT NULL DEFAULT current_timestamp(),
  db_reason     varchar(16)  NOT NULL DEFAULT 'unknown',
  db_fw_framework varchar(16) NOT NULL DEFAULT '',
  db_fw_sketch  varchar(16)  NOT NULL DEFAULT '',
  db_fw_name    varchar(40)  NOT NULL DEFAULT '',
  db_heap_free  int(10) unsigned DEFAULT NULL,
  db_boot_count int(10) unsigned DEFAULT NULL,         -- starts since last power loss
  db_uptime_s   int(10) unsigned DEFAULT NULL,         -- how long the previous life ran
  db_last_cmd   varchar(24)  DEFAULT NULL,
  db_last_err   varchar(64)  DEFAULT NULL,
  PRIMARY KEY (db_id),
  UNIQUE KEY uq_db_boot (db_device, db_boot_id),
  KEY ix_db_device_seen (db_device, db_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
