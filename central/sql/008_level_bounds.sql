-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — level bounds per slave and task (project document 44 §4,
-- "adaptive difficulty")
--
-- The automatic level (two A/B in a row -> +1, two D-F -> -1) so far moved
-- between 1 and the installation-wide scoring key level_max. These two
-- columns bound it PER SLAVE AND TASK: the automatic system moves only
-- between sl_min and sl_max, and the supervisor's own setting is clamped to
-- them as well. NULL = the installation-wide bound applies (1 / level_max).
-- The bounds stand visibly on the card next to the level.
ALTER TABLE slave_levels ADD COLUMN IF NOT EXISTS sl_min tinyint(3) unsigned DEFAULT NULL;
ALTER TABLE slave_levels ADD COLUMN IF NOT EXISTS sl_max tinyint(3) unsigned DEFAULT NULL;
