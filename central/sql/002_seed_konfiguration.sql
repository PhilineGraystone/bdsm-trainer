-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.0 — fixed installation content: configuration
--
-- WHAT IS IN HERE AND WHY IT IS INSTALLED ALONG WITH THE REST
--
-- Ranks, point counts, the default day plan and the rule set with rewards and
-- punishments. Decided on 2026-09-13: this is not an optional seed but a fixed
-- component. The subject is complex enough that one has to have something to
-- take one's bearings from — and a freshly installed installation without a
-- single program is, for anyone rebuilding this, a dead installation.
--
-- WHAT IS NOT IN HERE
--
-- No slaves, no devices, no assignments, no calibrations. Nowhere. The
-- installation starts empty at exactly those places where a guessed number
-- could end up on skin.
--
-- Everything in here is idempotent (INSERT IGNORE): a second run changes
-- nothing, and whatever the supervisor adjusts later stays adjusted.

SET NAMES utf8mb4;

-- from 005_logbook.sql (1.x)
INSERT IGNORE INTO ranks (rank_no, rank_name, rank_name_alt, rank_up_tasks, rank_up_grade, rank_up_best, rank_up_plan) VALUES
  (1,  'Dreck',           'Neuling',          2, 'C', 0, 0),
  (2,  'Wurm',            'Anwärter',         3, 'C', 0, 0),
  (3,  'Fußabtreter',     'Weiße Seide',      3, 'B', 0, 0),
  (4,  'Köter',           'Rote Seide',       4, 'B', 1, 0),
  (5,  'Hündchen',        'Dienender',        5, 'B', 1, 0),
  (6,  'Nutzvieh',        'Vorzeigestück',    5, 'B', 2, 0),
  (7,  'Spielzeug',       'Vertrauter',       6, 'A', 2, 0),
  (8,  'Haustier',        'Favorit',          6, 'A', 3, 0),
  (9,  'Lieblingsstück',  'Erste Wahl',       0, 'A', 3, 1),   
  (10, 'Kajira / Kajirus','Kajira / Kajirus', 0, 'A', 0, 0);

-- from 005_logbook.sql (1.x)
INSERT IGNORE INTO scoring (sc_key, sc_value, sc_desc) VALUES
  ('base_per_level',      '10',  'Basispunkte je Aufgabenstufe (Basis = Stufe × Wert)'),
  ('factor_a',            '1.5', 'Notenfaktor A'),
  ('factor_b',            '1.2', 'Notenfaktor B'),
  ('factor_c',            '1.0', 'Notenfaktor C'),
  ('factor_d',            '0.7', 'Notenfaktor D'),
  ('factor_e',            '0.4', 'Notenfaktor E'),
  ('factor_f',            '0',   'Notenfaktor F'),
  ('malus_punish',        '3',   'Abzug je Bestrafung im Durchgang (Ergebnis nie unter 0)'),
  ('bonus_best',          '15',  'Bonus für eine neue persönliche Bestleistung (nur bestandene Durchgänge)'),
  ('bonus_streak_step',   '5',   'Serienbonus je Folgetag mit Training'),
  ('bonus_streak_cap',    '25',  'Obergrenze des Serienbonus'),
  ('bonus_week',          '50',  'Bonus für einen vollständig bestandenen Wochenplan'),
  ('bonus_challenge',     '30',  'Bonus für den Sieger einer Herausforderung'),
  ('count_per_day',       '2',   'Anti-Grinding: so viele beste Durchgänge je Aufgabe und Tag zählen'),
  ('default_max_punish',  '2',   'Vorgabe: erlaubte Bestrafungen für ein "bestanden"'),
  ('pass_grade',          'C',   'Schlechteste Note, die noch als bestanden gilt'),
  ('detention_punish',    '6',   'Nachsitzen ab so vielen Bestrafungen in einer Woche (0 = aus)'),
  ('detention_last',      '1',   'Letzter der Wochenrangliste bekommt Nachsitzen (1/0)'),
  ('auto_plan',           '1',   'Sonntags Planvorschlag für die nächste Woche erzeugen (1/0)'),
  ('auto_activate',       '1',   'Unbestätigte Vorschläge beim Wochenwechsel automatisch aktivieren (1/0); in der laufenden Woche nur per Bestätigen'),
  ('channel_queue_max',   '10',  'Bestrafungskanal: höchstens so viele wartende Bestrafungen je Teilnehmer (darüber verworfen, Audit)'),
  ('channel_retry_max',   '1',   'Bestrafungskanal: so oft wiederholen, wenn der Reizgeber "busy" meldet'),
  ('channel_retry_s',     '3',   'Bestrafungskanal: Wartezeit bis zur Wiederholung nach "busy" in Sekunden'),
  ('finish_grace_s',      '10',  'Ergebnis eines Durchgangs wartet höchstens so lange auf den Vollzug offener Bestrafungen'),
  ('review_active_weeks', '4',   'Wochenbewertung nur für Teilnehmer mit Anmeldung in den letzten n Wochen (0 = alle)'),
  ('priv_no_restraints_a','3',   'Privileg "ohne Fesseln": nach so vielen A im Trainer'),
  ('rank_names',          'main','Aktiver Namenssatz der Ränge: main | alt'),
  ('level_max',           '10',  'Höchste Aufgabenstufe'),
  ('last_review_week',    '',    'intern: zuletzt bewertete Woche'),
  ('last_proposal_week',  '',    'intern: zuletzt vorgeschlagene Woche');

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT IGNORE INTO day_plans (dp_name, dp_note, dp_default) VALUES
  ('Standardtag', 'Vorgabe für alle Teilnehmer ohne eigene Zuordnung: Training, Pause, Training, Pause, freies Training', 1);

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_text)
  SELECT dp_id, 1, 'plan', 45, NULL FROM day_plans WHERE dp_name='Standardtag'
   AND NOT EXISTS (SELECT 1 FROM day_blocks WHERE db_plan=dp_id);

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_text)
  SELECT dp_id, 2, 'pause', 15, 'Pause. Du darfst etwas trinken.' FROM day_plans WHERE dp_name='Standardtag'
   AND (SELECT COUNT(*) FROM day_blocks WHERE db_plan=dp_id) = 1;

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_text)
  SELECT dp_id, 3, 'plan', 45, NULL FROM day_plans WHERE dp_name='Standardtag'
   AND (SELECT COUNT(*) FROM day_blocks WHERE db_plan=dp_id) = 2;

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_text)
  SELECT dp_id, 4, 'pause', 30, 'Pause. Du darfst jetzt etwas essen.' FROM day_plans WHERE dp_name='Standardtag'
   AND (SELECT COUNT(*) FROM day_blocks WHERE db_plan=dp_id) = 3;

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT INTO day_blocks (db_plan, db_pos, db_kind, db_minutes, db_text)
  SELECT dp_id, 5, 'free', 45, NULL FROM day_plans WHERE dp_name='Standardtag'
   AND (SELECT COUNT(*) FROM day_blocks WHERE db_plan=dp_id) = 4;

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT IGNORE INTO rules (ru_trigger, ru_cond, ru_effect, ru_param, ru_note, ru_pos) VALUES
  ('challenge', 'place=1',  'reward',          '2',            'Sieger der Herausforderung: Belohnung über den Kanal', 10),
  ('challenge', 'place=1',  'privilege_grant', 'free_stay:1',  'Sieger: freier Aufenthalt für eine Woche', 11),
  ('challenge', 'place=1',  'badge',           'challenge_won','Sieger: Abzeichen Duellant', 12),
  ('challenge', 'place>=3', 'punish',          '1',            'Ab Platz 3: Bestrafung über den Kanal', 20),
  ('challenge', 'place>=3', 'detention',       '',             'Ab Platz 3: Nachsitzen in der nächsten Woche', 21),
  ('challenge', 'last',     'punish',          '2',            'Letzter: stärkere Bestrafung', 22),
  ('capitulation', '',      'detention',       '',             'Kapitulation: Nachsitz-Aufgabe', 30),
  ('capitulation', '',      'day_minutes',     '+30',          'Kapitulation: Tagesdauer 30 min länger — wer aufgibt, braucht mehr Training', 31),
  ('plan_complete', '',     'day_minutes',     '-15',          'Wochenplan vollständig: Tagesdauer 15 min kürzer', 40);

-- from 007_dayplan_rules_challenge.sql (1.x)
INSERT IGNORE INTO scoring (sc_key, sc_value, sc_desc) VALUES
  ('free_factor',        '0.5', 'Freies Training: Punkte werden mit diesem Faktor gewichtet'),
  ('free_stretch_every', '3',   'Freies Training: jede n-te Aufgabe eine Stufe höher (0 = aus)'),
  ('plan_per_day_min',   '1',   'Wochenplan: mindestens so viele Planaufgaben pro Tag'),
  ('plan_day_tasks',     '6',   'Planvorschlag: so viele Aufgaben je Tag der Woche vorschlagen'),
  ('challenge_auto',     '1',   'Herausforderung bei der Wochenbewertung automatisch entscheiden (1/0)');

-- from 008_routines.sql (1.x)
INSERT IGNORE INTO scoring (sc_key, sc_value, sc_desc) VALUES
  ('routine_fullscale_pct', '25',    'Routine: deviation at which a tick scores zero, in percentage points (default for new waveforms)'),
  ('routine_fault_ms',      '2000',  'Routine: how long outside the tolerance band before a fault is raised'),
  ('routine_fault_gap_s',   '10',    'Routine: minimum gap between two faults of the same run'),
  ('routine_away_pause_s',  '3',     'Routine: beyond the resting distance for this long counts as a pause, not a fault'),
  ('routine_start_wait_s',  '60',    'Routine: how long to wait for the run to start before ending it as not_started'),
  ('routine_invalid_max',   '30',    'Routine: above this share of invalid ticks (percent) the run is not counted'),
  ('routine_min_score',     '6000',  'Routine: default required score for a new waveform (0..10000)');

-- from 009_tracks.sql (1.x)
INSERT IGNORE INTO scoring (sc_key, sc_value, sc_desc) VALUES
  ('estim_day_max_s',    '3600', 'E-Stim: Höchstdauer aller Ausgaben eines Teilnehmers am Tag (Sekunden)'),
  ('estim_event_max_s',  '20',   'E-Stim: Höchstdauer einer einzelnen Kanal-Bestrafung oder -Belohnung'),
  ('estim_frame_ms',     '100',  'E-Stim: Taktrate der Brücke zum Gerät; ohne neuen Rahmen endet die Ausgabe'),
  ('estim_level1_pct',   '25',   'E-Stim: Intensität für Kanalstufe 1 (Prozent der Decke des Trägers)'),
  ('estim_level2_pct',   '45',   'E-Stim: Intensität für Kanalstufe 2'),
  ('estim_level3_pct',   '70',   'E-Stim: Intensität für Kanalstufe 3'),
  ('live_hz',            '5',    'Messwertkanal: wie oft der Trainer Tiefe und Bandfehler meldet (Hz)'),
  ('live_stale_ms',      '1500', 'Messwertkanal: ohne neuen Wert gilt die Kopplung als unbekannt, Spuren gehen auf Null');

INSERT IGNORE INTO schema_migrations (version) VALUES ('002');
