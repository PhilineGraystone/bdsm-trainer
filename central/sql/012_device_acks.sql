-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Acknowledged device conditions (2.3.3, project document 55)
--
-- FINDING Philine 2026-09-16: a device stays red until midnight after a flash,
-- because the restarts of today are counted — including the ones somebody
-- caused on purpose. "A monitor that is permanently red is one nobody takes
-- seriously any more."
--
-- WHAT IS STORED HERE, AND WHY EXACTLY THAT
--
-- Not "condition X is acknowledged" but "condition X WITH THIS CONTENT is
-- acknowledged". `da_mark` is the content: for the restarts the count per
-- reason, for `degraded` the list of components, for the signal the measured
-- value. Once it changes, the acknowledgement no longer applies and the
-- condition is red again.
--
-- That is the whole difference between acknowledging and covering up: a
-- second brownout stays quiet, a third reports. An acknowledgement per key
-- without a content would be a switch that turns a condition off forever —
-- and that is the same monitor nobody takes seriously, only in green.
--
-- One row per (device, condition). Acknowledging again replaces the content;
-- the history of acknowledgements lives in audit_log, not here.

CREATE TABLE IF NOT EXISTS device_acks (
  da_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
  da_device   VARCHAR(64)  NOT NULL,            -- device_UUID, as in device_boots
  da_key      VARCHAR(24)  NOT NULL,            -- devicehealth key: restart, rssi, ...
  da_mark     VARCHAR(191) NOT NULL,            -- the content that was acknowledged
  da_by       VARCHAR(64)  NOT NULL DEFAULT '', -- the logged-in user
  da_note     VARCHAR(191) NOT NULL DEFAULT '', -- optional: why
  da_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (da_id),
  UNIQUE KEY uq_device_key (da_device, da_key),
  KEY idx_device (da_device)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
