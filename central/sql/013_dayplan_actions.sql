-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Task decisions per day plan (2.4, project document 58 sections 1 and 2)
--
-- FINDING Philine 2026-09-16: "Single tasks ought to be differentiated. Example:
-- the collar's `sleep` program makes no sense at all in a normal setting. It
-- gets picked anyway."
--
-- It does. Free training filters on three things only - the task is trainable,
-- a device with the capability is online, it fits the remaining time. None of
-- them asks whether the task makes sense in this situation. And free training
-- is the one place in the installation where the central reaches into the full
-- catalogue without anyone having picked anything: a weekly plan task needs an
-- assigned program, so a human said yes to it at some point.
--
-- WHAT IS STORED HERE, AND WHY NOT A PLAIN BLOCK LIST
--
-- Not "these tasks are forbidden" but a DECISION per task. The editor shows the
-- whole catalogue with a box each, so saving states something about every
-- action - and a task that later enters the catalogue has no row at all, which
-- is how it can be told apart from one that was deliberately allowed and shown
-- as "new, not decided yet".
--
-- A plain block list cannot do that: a new action would silently be allowed
-- everywhere, in every plan, without anyone deciding. An allow list fails the
-- other way - "empty" would be ambiguous, and one cannot see whether a missing
-- task was rejected or forgotten.
--
-- A plan nobody ever edited has no rows: everything allowed, exactly today's
-- behaviour. No migration of existing plans, no day that suddenly stands still.
--
-- THE MODES (doc 58 section 2). Two of them are opposites, and both are needed:
--   allow      decided and allowed
--   block      blocked, always
--   block_in   blocked ONLY between from-to    -- "no action X after 22:00"
--   block_out  blocked EXCEPT between from-to  -- sleep deprivation 22:00-06:00
-- `dpa_from > dpa_to` means the window runs over midnight, which is the case
-- the whole thing exists for. Minutes since midnight, in steps of 15.
--
-- The list hangs on the DAY PLAN, not on the single block: with two training
-- blocks one would otherwise maintain the same thing twice, and the time
-- separation is what the window is for. A scenario swaps the day plan, so the
-- list becomes context-dependent without any doing of its own (doc 44 section 7).

CREATE TABLE IF NOT EXISTS dayplan_actions (
  dpa_id     INT UNSIGNED NOT NULL AUTO_INCREMENT,
  dpa_plan   INT UNSIGNED NOT NULL,                    -- day_plans.dp_id
  dpa_action VARCHAR(32)  NOT NULL,                    -- action code out of the catalogue
  dpa_mode   VARCHAR(12)  NOT NULL DEFAULT 'allow',    -- allow | block | block_in | block_out
  dpa_from   SMALLINT UNSIGNED NULL,                   -- minutes since midnight, 0..1439
  dpa_to     SMALLINT UNSIGNED NULL,
  dpa_by     VARCHAR(64)  NOT NULL DEFAULT '',         -- who decided
  dpa_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (dpa_id),
  UNIQUE KEY uq_plan_action (dpa_plan, dpa_action),
  KEY idx_plan (dpa_plan),
  CONSTRAINT fk_dpa_plan FOREIGN KEY (dpa_plan) REFERENCES day_plans (dp_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
