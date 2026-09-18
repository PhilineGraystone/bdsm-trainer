-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.0 — fixed installation content: reference waveforms
--
-- Formerly sql/904, that is, test data. From 2.0 on this belongs in the
-- installation (decision 2026-09-13): it is documentation that sits next to
-- what it explains, and cannot go stale there.
--
-- Five waveforms — stimulus AND scored task. They are part of the
-- EXPLANATION, not ornament: one compares against something that runs, and
-- that teaches more than any help text. They carry ro_example = 1, their
-- reasoning is in the note, and they can be copied.
--
-- Idempotent: what gets deleted is exclusively what has ro_example = 1 AND
-- carries one of the example names. Copies of one's own stay untouched.

SET NAMES utf8mb4;

DELETE FROM routines WHERE ro_example = 1 AND ro_name IN
  ('Beispiel: Aufwärmen und zwei Tiefen', 'Beispiel: Erst schlucken',
   'Beispiel: Kurz und scharf', 'Beispiel: Zwei Takte', 'Beispiel: Lange Welle');

-- ---------------------------------------------------------------------------
-- 1. TASK, time axis, scored. Deliberately built free of hints: 6 s above 80 %
--    (warning from 30 s on), largest rate of change 16 %/s (from 150 %/s on),
--    seam between start and end 5 percentage points (from 15 on). That way a
--    curve that passes shows how far away from a warning one is.
INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_example, ro_level,
                      ro_tol_default, ro_fullscale_pct, ro_loop_ms, ro_min_score,
                      ro_punish_level, ro_reward_level, ro_by)
VALUES ('Beispiel: Aufwärmen und zwei Tiefen',
        'Maßstab für eigene Aufgaben: anfahren, flach halten, atmen, mittlere Tiefe, atmen, '
        'kurz tief, lösen. Erzeugt absichtlich keine Hinweise — daran lässt sich ablesen, '
        'wie viel Luft die Warnschwellen lassen.',
        'zeit', 'aufgabe', 1, 3, 12, 25, 2000, 6000, 1, 1, 'Beispiel');
SET @r := LAST_INSERT_ID();
INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, rt_mode, rt_note)
VALUES (@r, 0, 'zieltiefe', NULL, '', 'absolut', 'Die Kurve, die nachgefahren und bewertet wird.');
INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) VALUES
  (@r, 0, 0,     0,  0, 15), (@r, 0, 1,  3000, 35, 12), (@r, 0, 2,  8000, 35, 12),
  (@r, 0, 3, 11000, 15, 15), (@r, 0, 4, 14000, 60, 10), (@r, 0, 5, 20000, 60, 10),
  (@r, 0, 6, 23000, 20, 15), (@r, 0, 7, 27000, 85,  8), (@r, 0, 8, 33000, 85,  8),
  (@r, 0, 9, 36000, 25, 15), (@r, 0,10, 40000, 50, 12), (@r, 0,11, 45000,  5, 15);

-- ---------------------------------------------------------------------------
-- 2. COUPLING, depth axis, two tracks on two channels.
--    X is NOT time here but the measured depth: unpleasant as long as nothing
--    has been swallowed, stimulating as soon as it has. The second mode
--    („no pain for not swallowing") is the same waveform with track 0
--    deleted — one copy, one checkbox, nothing drawn anew.
INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_example, ro_level,
                      ro_tol_default, ro_fullscale_pct, ro_loop_ms, ro_min_score,
                      ro_punish_level, ro_reward_level, ro_by)
VALUES ('Beispiel: Erst schlucken',
        'Kopplung zur Aufgabe: X ist die gemessene Tiefe, nicht die Zeit. Flach tut weh, '
        'tief wird angenehm; Übergabe zwischen 70 und 85 Prozent. Die zwei Rollen liegen auf '
        'den zwei Kanälen, damit sie wirklich gleichzeitig laufen und sich getrennt anfühlen.',
        'tiefe', 'reiz', 1, 1, 10, 25, 0, 0, 1, 1, 'Beispiel');
SET @r := LAST_INSERT_ID();
INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, rt_mode, rt_note) VALUES
  (@r, 0, 'bestrafung',  'haken', 'a', 'absolut',
   'Fällt mit zunehmender Tiefe auf Null: der Reiz hört auf, sobald geschluckt ist.'),
  (@r, 1, 'stimulation', 'welle', 'b', 'absolut',
   'Beginnt erst jenseits von 55 Prozent: tief zu sein wird belohnt, nicht nur nicht bestraft.');
-- rp_x counts on the depth axis in steps of 0.1 percent (0..1000 = 0..100 %).
INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) VALUES
  (@r, 0, 0,   0, 45, 0), (@r, 0, 1, 400, 30, 0), (@r, 0, 2, 700, 10, 0),
  (@r, 0, 3, 850,  0, 0), (@r, 0, 4,1000,  0, 0),
  (@r, 1, 0,   0,  0, 0), (@r, 1, 1, 550,  0, 0), (@r, 1, 2, 750, 35, 0),
  (@r, 1, 3, 900, 70, 0), (@r, 1, 4,1000, 85, 0);

-- ---------------------------------------------------------------------------
-- 3. PUNISHMENT as a program of its own.
INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_example, ro_level,
                      ro_tol_default, ro_fullscale_pct, ro_loop_ms, ro_min_score,
                      ro_punish_level, ro_reward_level, ro_by)
VALUES ('Beispiel: Kurz und scharf',
        'Zwei Stöße von 1,3 Sekunden mit Ruhe dazwischen. Harter Einsatz, harter Abfall — '
        'der Unterschied zur Belohnung muss sich FÜHLEN und nicht bloß in der Höhe stehen.',
        'zeit', 'reiz', 1, 1, 10, 25, 0, 0, 2, 0, 'Beispiel');
SET @r := LAST_INSERT_ID();
INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, rt_mode, rt_note)
VALUES (@r, 0, 'bestrafung', 'stich', 'a', 'absolut', 'Profil „Stich": das schärfste im Katalog.');
INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) VALUES
  (@r, 0, 0,    0,  0, 0), (@r, 0, 1,  200, 70, 0), (@r, 0, 2, 1500, 70, 0),
  (@r, 0, 3, 1800,  0, 0), (@r, 0, 4, 3000,  0, 0), (@r, 0, 5, 3200, 70, 0),
  (@r, 0, 6, 4500, 70, 0), (@r, 0, 7, 4800,  0, 0);

-- ---------------------------------------------------------------------------
-- 4. REWARD as a program of its own. Purpose 'belohnung' -> can never end up in
--    the weekly plan; it cannot be failed.
INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_example, ro_level,
                      ro_tol_default, ro_fullscale_pct, ro_loop_ms, ro_min_score,
                      ro_punish_level, ro_reward_level, ro_by)
VALUES ('Beispiel: Zwei Takte',
        'In Stufen aufbauend, mit Ausklang statt Abbruch. Der unverwechselbare Rhythmus kommt '
        'aus dem Profil, nicht aus der Kurve — deshalb ist eine Belohnung auch bei gleicher '
        'Höhe nie mit einer Strafe zu verwechseln.',
        'zeit', 'belohnung', 1, 1, 10, 25, 1000, 0, 0, 2, 'Beispiel');
SET @r := LAST_INSERT_ID();
INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, rt_mode, rt_note)
VALUES (@r, 0, 'belohnung', 'zweitakt', 'b', 'absolut', 'Profil „Zweitakt": zwei Schläge, dann Ruhe.');
INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) VALUES
  (@r, 0, 0,     0,  0, 0), (@r, 0, 1,  2000, 40, 0), (@r, 0, 2, 10000, 40, 0),
  (@r, 0, 3, 12000, 60, 0), (@r, 0, 4, 30000, 60, 0), (@r, 0, 5, 34000, 80, 0),
  (@r, 0, 6, 45000, 80, 0), (@r, 0, 7, 55000, 35, 0), (@r, 0, 8, 60000,  0, 0);

-- ---------------------------------------------------------------------------
-- 5. STIMULATION as a program of its own, coupled to the accuracy: the same
--    curve thereby becomes a form of reward — the values are the upper limit,
--    and how much arrives the accuracy decides. The cheapest way to grasp it.
INSERT INTO routines (ro_name, ro_note, ro_axis, ro_purpose, ro_example, ro_level,
                      ro_tol_default, ro_fullscale_pct, ro_loop_ms, ro_min_score,
                      ro_punish_level, ro_reward_level, ro_by)
VALUES ('Beispiel: Lange Welle',
        'Zehn Minuten, steigend mit Einbrüchen — die Einbrüche sind der Punkt, eine gleichmäßig '
        'steigende Linie stumpft ab. Gekoppelt an die Genauigkeit: die Werte sind die Obergrenze. '
        'Zeigt absichtlich einen Hinweis — sie endet bei 20 und beginnt bei 0.',
        'zeit', 'reiz', 1, 1, 10, 25, 3000, 0, 0, 1, 'Beispiel');
SET @r := LAST_INSERT_ID();
INSERT INTO routine_tracks (rt_routine, rt_track, rt_role, rt_profile, rt_channel, rt_mode, rt_couple, rt_note)
VALUES (@r, 0, 'stimulation', 'welle', 'b', 'gekoppelt', 'genauigkeit',
        'Gekoppelt an die Genauigkeit: Genauigkeit verdient Empfindung, Abweichung nimmt sie weg.');
INSERT INTO routine_points (rp_routine, rp_track, rp_seq, rp_x, rp_value, rp_tol_pct) VALUES
  (@r, 0, 0,      0,  0, 0), (@r, 0, 1,  30000, 25, 0), (@r, 0, 2,  90000, 25, 0),
  (@r, 0, 3, 120000, 45, 0), (@r, 0, 4, 180000, 30, 0), (@r, 0, 5, 240000, 55, 0),
  (@r, 0, 6, 300000, 40, 0), (@r, 0, 7, 400000, 65, 0), (@r, 0, 8, 480000, 45, 0),
  (@r, 0, 9, 560000, 75, 0), (@r, 0,10, 600000, 20, 0);

INSERT IGNORE INTO schema_migrations (version) VALUES ('003');
