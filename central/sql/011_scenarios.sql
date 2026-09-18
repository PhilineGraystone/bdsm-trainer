-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — scenarios: the bundle with a name (project document 44 §7)
--
-- A scenario is NOT a new rule system. It is a named bundle of things that
-- exist already — a day plan (with its blocks, mystery included), a set of
-- sanctions, budgets and a day form — activated for one slave with one click
-- and an end date. Activation writes into the very tables the pieces live
-- in (slave_settings, sanctions, budgets, dayforms), tagged with
-- 'scenario:<id>', and the end date takes it all back out again.
--
-- sn_budgets is a JSON list: [{"key": "reward", "period": "day",
-- "max_count": 3, "min_gap_s": null, "on_gap": "drop"}, ...]

CREATE TABLE IF NOT EXISTS scenarios (
  sn_id        int(10) unsigned NOT NULL AUTO_INCREMENT,
  sn_name      varchar(80)  NOT NULL,
  sn_note      varchar(255) DEFAULT NULL,
  sn_day_plan  int(10) unsigned DEFAULT NULL,           -- NULL = keep her plan
  sn_dayform   enum('easy','normal','strict') DEFAULT NULL,   -- NULL = leave the form alone
  sn_sanctions varchar(255) NOT NULL DEFAULT '',        -- comma list of SANCTIONS keys
  sn_budgets   text DEFAULT NULL,                       -- JSON, see above
  sn_by        varchar(64)  DEFAULT NULL,
  sn_updated   datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (sn_id),
  UNIQUE KEY uq_sn_name (sn_name),
  KEY fk_sn_plan (sn_day_plan),
  CONSTRAINT fk_sn_plan FOREIGN KEY (sn_day_plan) REFERENCES day_plans (dp_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One active scenario per slave at a time. sx_prev_plan remembers what her
-- plan was, so the end can give it back.
CREATE TABLE IF NOT EXISTS scenario_active (
  sx_slave     int(10) unsigned NOT NULL,
  sx_scenario  int(10) unsigned NOT NULL,
  sx_from      date NOT NULL,
  sx_until     date NOT NULL,                           -- inclusive
  sx_prev_plan int(10) unsigned DEFAULT NULL,
  sx_by        varchar(64) DEFAULT NULL,
  sx_activated datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (sx_slave),
  KEY fk_sx_scenario (sx_scenario),
  CONSTRAINT fk_sx_slave FOREIGN KEY (sx_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE,
  CONSTRAINT fk_sx_scenario FOREIGN KEY (sx_scenario) REFERENCES scenarios (sn_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
