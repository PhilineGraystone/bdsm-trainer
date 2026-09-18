-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.3 — day form easy / normal / strict (project document 44 §5)
--
-- One row per slave (0 = whole installation) and DAY. There is no "current
-- form" column anywhere: the form of a day is the row for that date, and a
-- day without a row is normal. That is how "it holds until the end of the
-- day and then falls back" works without a timer — tomorrow simply has no
-- row unless the supervisor or a rule writes one (decision Philine 2026-09-16).
-- df_by says who: a user name, or 'rule:<trigger>'.

CREATE TABLE IF NOT EXISTS dayforms (
  df_slave  int(10) unsigned NOT NULL DEFAULT 0,
  df_day    date NOT NULL,
  df_form   enum('easy','normal','strict') NOT NULL DEFAULT 'normal',
  df_by     varchar(64) DEFAULT NULL,
  df_reason varchar(160) NOT NULL DEFAULT '',
  df_set    datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (df_slave, df_day),
  KEY ix_df_day (df_day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The numbers behind the three forms, editable over the web (page scoring).
INSERT IGNORE INTO scoring (sc_key, sc_value, sc_desc) VALUES
  ('dayform_easy_pct',          '85',  'Tagesform leicht: Impulse in % (Bestrafung), höchstens 100 = ihre Decke'),
  ('dayform_strict_pct',        '115', 'Tagesform streng: Impulse in % — wird an der Decke (100 %) gekappt'),
  ('dayform_level_easy',        '-1',  'Tagesform leicht: Versatz auf die Aufgabenstufe (innerhalb der Grenzen)'),
  ('dayform_level_strict',      '1',   'Tagesform streng: Versatz auf die Aufgabenstufe (innerhalb der Grenzen)'),
  ('dayform_budget_easy_pct',   '120', 'Tagesform leicht: Anzahl der Belohnungs-/Durchgangsbudgets in %'),
  ('dayform_budget_strict_pct', '80',  'Tagesform streng: Anzahl der Belohnungs-/Durchgangsbudgets in %; Abstand umgekehrt');
