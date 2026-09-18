-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — budgets and cooldowns (project document 44 §1)
--
-- One row per (key, slave, period). bu_slave = 0 is the whole installation;
-- a row for one slave applies IN ADDITION to the installation row, and the
-- tighter one wins — that is why 0 and not NULL: a UNIQUE key with NULL in it
-- would let the same installation-wide budget in twice.
--
-- The safety ceiling of the punishment channel (config.ini [safety]
-- channel_day_max / channel_gap_s) is NOT a row here. libs/budgets.py adds it
-- as a synthetic row at evaluation time, so a budget can only tighten the
-- channel and never loosen it. It is not editable over the web, and this
-- table cannot get around it.
--
--   bu_max_count  NULL = unlimited            (the budget: how often)
--   bu_min_gap_s  NULL = no pause             (the cooldown: how close)
--   bu_on_gap     what happens inside the pause: 'queue' waits and is then
--                 delivered, 'drop' lapses. For activity keys it has no
--                 meaning — the day plan simply takes another task.

CREATE TABLE IF NOT EXISTS budgets (
  bu_id        int(10) unsigned NOT NULL AUTO_INCREMENT,
  bu_key       varchar(40)  NOT NULL,                  -- punish | reward | activity | activity:<ACTION>
  bu_slave     int(10) unsigned NOT NULL DEFAULT 0,    -- 0 = whole installation
  bu_period    enum('day','week') NOT NULL DEFAULT 'day',
  bu_max_count int(10) unsigned DEFAULT NULL,
  bu_min_gap_s int(10) unsigned DEFAULT NULL,
  bu_on_gap    enum('queue','drop') NOT NULL DEFAULT 'queue',
  bu_enabled   tinyint(1) NOT NULL DEFAULT 1,
  bu_note      varchar(255) DEFAULT NULL,
  bu_by        varchar(64) DEFAULT NULL,
  bu_updated   datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (bu_id),
  UNIQUE KEY uq_budget (bu_key, bu_slave, bu_period),
  KEY ix_bu_slave (bu_slave)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The anti-grinding count moves here from `scoring` (count_per_day, until now
-- 2 by default): how many runs per task and day count towards the
-- leaderboard. The value that was set is carried over; the scoring key then
-- goes, so there is no second place that could disagree.
INSERT IGNORE INTO budgets (bu_key, bu_slave, bu_period, bu_max_count, bu_min_gap_s, bu_on_gap, bu_note, bu_by)
  SELECT 'activity', 0, 'day', GREATEST(1, CAST(sc_value AS UNSIGNED)), NULL, 'queue',
         'Anti-Grinding: so viele Durchgänge je Aufgabe und Tag zählen (aus scoring.count_per_day)', 'migration-005'
    FROM scoring WHERE sc_key = 'count_per_day';
INSERT IGNORE INTO budgets (bu_key, bu_slave, bu_period, bu_max_count, bu_min_gap_s, bu_on_gap, bu_note, bu_by)
  VALUES ('activity', 0, 'day', 2, NULL, 'queue',
          'Anti-Grinding: so viele Durchgänge je Aufgabe und Tag zählen', 'migration-005');
DELETE FROM scoring WHERE sc_key = 'count_per_day';

-- Rewards: no count, no pause by default — but the switch stands on 'drop'
-- (decision Philine 2026-09-16): a reward that has to wait for a pause is not
-- one. Whoever sets a pause here gets that behaviour without thinking about it.
INSERT IGNORE INTO budgets (bu_key, bu_slave, bu_period, bu_max_count, bu_min_gap_s, bu_on_gap, bu_note, bu_by)
  VALUES ('reward', 0, 'day', NULL, NULL, 'drop', 'Belohnungen: Vorgabe „verfällt“ innerhalb einer Pause', 'migration-005');

-- The punishment channel keeps 'queue' (decision 2026-09-10). Count and pause
-- stay NULL here: the ceiling from [safety] applies anyway, and a number in
-- this row would look like the place to change it.
INSERT IGNORE INTO budgets (bu_key, bu_slave, bu_period, bu_max_count, bu_min_gap_s, bu_on_gap, bu_note, bu_by)
  VALUES ('punish', 0, 'day', NULL, NULL, 'queue', 'Bestrafungskanal: nachholen (Decke aus config.ini [safety])', 'migration-005');
