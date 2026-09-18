-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Narrowing limits per day plan and task (2.5, project document 60)
--
-- Philine asked to be able to carry further settings per entry: "with
-- stimulation, the strength (or a range), the waveform and so on". Accepted was
-- the NARROWING version - a limit, not a value. It computes as a minimum
-- against everything else and therefore needs no precedence rule at all, which
-- is what made this safe enough to build (doc 58 section 7).
--
-- WHY TWO COLUMNS AND NOT A TABLE
--
-- It is the same row: the decision about this task in this day plan. A limit
-- without a decision does not exist, and a plan that says nothing about a task
-- has no row here either.
--
-- WHAT MAY BE LIMITED
--
-- Not every number. The criterion "nothing may come out that could not have
-- come out without the entry" is necessary but NOT sufficient: lowering `warn`
-- to 0 takes the warning away before a pulse, lowering `angle` makes the
-- posture stricter, lowering `repeat_s` puts the pulses closer together. All
-- three pass the wording and make the installation harder.
--
-- So a second sentence holds: a limit exists only for parameters where SMALLER
-- UNDOUBTEDLY MEANS LESS for the person. That list is written down by name in
-- libs/taskblocks.py, with the reasoning beside it - the code cannot derive it.
--
-- `dpa_no_routines` is the waveform side of the same idea. Pinning a waveform
-- would be a setting: the pick by level could never have produced it. Excluding
-- one provably cannot add anything, and `routines.pick_for_level()` has taken
-- an exclude list all along.

ALTER TABLE dayplan_actions ADD COLUMN IF NOT EXISTS dpa_caps VARCHAR(191) NOT NULL DEFAULT ''
  COMMENT 'name=value list, upper limits, only for parameters where smaller means less';
ALTER TABLE dayplan_actions ADD COLUMN IF NOT EXISTS dpa_no_routines VARCHAR(191) NOT NULL DEFAULT ''
  COMMENT 'waveform ids the level pick must not take here';
