-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — streaks as a thing of their own (project document 44 §3)
--
-- `streaks` holds the definitions: a kind (libs/streaks.py KINDS), optionally
-- one task, and the milestones at which `streak_reached` fires. `streak_state`
-- holds the counter per definition and slave, the best ever, the last day
-- that counted (day kinds), and the last break — count and when — so the
-- loss can be shown for a day (decision Philine 2026-09-16).

CREATE TABLE IF NOT EXISTS streaks (
  st_id         int(10) unsigned NOT NULL AUTO_INCREMENT,
  st_key        varchar(32)  NOT NULL,                  -- short handle for rules and logs
  st_name       varchar(80)  NOT NULL,                  -- what the screen says
  st_kind       varchar(16)  NOT NULL,                  -- clean_days | training_days | passed_runs | failed_runs | plan_weeks
  st_action     varchar(32)  DEFAULT NULL,              -- run kinds: only this task (NULL = any)
  st_milestones varchar(64)  NOT NULL DEFAULT '',       -- "3,7,14"
  st_enabled    tinyint(1)   NOT NULL DEFAULT 1,
  st_by         varchar(64)  DEFAULT NULL,
  st_updated    datetime     NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (st_id),
  UNIQUE KEY uq_st_key (st_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS streak_state (
  sk_streak       int(10) unsigned NOT NULL,
  sk_slave        int(10) unsigned NOT NULL,
  sk_count        int(10) unsigned NOT NULL DEFAULT 0,
  sk_best         int(10) unsigned NOT NULL DEFAULT 0,
  sk_last_day     date DEFAULT NULL,                    -- day kinds: the last day that was counted
  sk_broken_at    datetime DEFAULT NULL,
  sk_broken_count int(10) unsigned NOT NULL DEFAULT 0,  -- how long it was when it broke
  PRIMARY KEY (sk_streak, sk_slave),
  CONSTRAINT fk_sk_streak FOREIGN KEY (sk_streak) REFERENCES streaks (st_id) ON DELETE CASCADE,
  CONSTRAINT fk_sk_slave  FOREIGN KEY (sk_slave)  REFERENCES slaves  (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Two definitions to start with — the ones from the concept. Both without a
-- rule: they count and they break, and the screen shows it. What follows from
-- them is the supervisor's to decide in the rule set.
INSERT IGNORE INTO streaks (st_key, st_name, st_kind, st_action, st_milestones, st_by) VALUES
  ('clean',    'Tage ohne Verstoß',   'clean_days',  NULL, '3,7,14,30', 'migration-007'),
  ('training', 'Trainingstage',       'training_days', NULL, '5,10,20', 'migration-007');
