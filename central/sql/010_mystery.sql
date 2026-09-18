-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — mystery block in the day plan (project document 44 §6)
--
-- A fifth block kind. Its text field carries the pool ("PET, punish:2,
-- reward:1"), its minutes the window; libs/mystery.py parses the pool and
-- draws, libs/dayplan.py runs it. Nothing else changes in the table — the
-- block is a row like the other four.
ALTER TABLE day_blocks MODIFY db_kind enum('plan','program','free','pause','mystery') NOT NULL DEFAULT 'plan';
