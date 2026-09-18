-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — pause / holiday (project document 44 §2)
--
-- One row per pause: a date range (both days inclusive) for one slave or,
-- with pa_slave = 0, for the whole installation. Rows may overlap; the
-- question "is she paused today?" is answered by libs/pauses.py and nowhere
-- else. Nothing ends a pause but its end date — there is no 'active' flag to
-- forget to clear.

CREATE TABLE IF NOT EXISTS pauses (
  pa_id      int(10) unsigned NOT NULL AUTO_INCREMENT,
  pa_slave   int(10) unsigned NOT NULL DEFAULT 0,      -- 0 = whole installation
  pa_from    date NOT NULL,
  pa_to      date NOT NULL,
  pa_reason  varchar(160) NOT NULL DEFAULT '',
  pa_by      varchar(64) DEFAULT NULL,
  pa_created datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (pa_id),
  KEY ix_pa_slave_to (pa_slave, pa_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The weekly review records how many days of the week were paused. A week
-- covered completely is frozen (wr_reason 'pausiert', rank unchanged); a week
-- covered in part is graded as usual, and the report card says how much of it
-- was pause rather than absence.
ALTER TABLE weekly_review ADD COLUMN IF NOT EXISTS wr_paused_days tinyint(3) unsigned NOT NULL DEFAULT 0;
