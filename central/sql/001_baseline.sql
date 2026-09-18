-- SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
-- Punisher 2.0 — baseline schema
--
-- WHY IT STARTS OVER HERE
--
-- Up to 1.x the schema grew across fourteen migrations. With 2.0 the contract
-- breaks in four places at once: the device UUID is derived from the MAC (every
-- address changes), the minimum-version floor is strict, the version is
-- structured, and every message is signed. An installation can carry none of
-- that over.
--
-- A migration path from 1.x to 2.0 would thus be code written once, tested once
-- and never used again — and which for exactly that reason carries faults that
-- nobody finds. Decided on 2026-09-13: the database is wiped and rebuilt, the
-- transition is dropped without replacement.
--
-- WHAT THAT REMOVES, AND THAT IT IS RIGHT SO
--
-- Slaves, devices, assignments and calibrations are recorded anew. The
-- calibrations above all: `sc_device` carried the old UUID, and a ceiling that
-- went on applying under a new device identity would be the guessed number on
-- skin that migration 011 explicitly ruled out. It is measured anew; until that
-- point the bridge outputs nothing.
--
-- WHERE THE REASONING HAS GONE
--
-- The old migrations carried their decisions as running text in the header. The
-- considerations themselves are in the project docs (German) and go on applying
-- unchanged; what is left here, per table, is only what that table is for.
--
-- The migration mechanism stays: libs/dbmigrate.py keeps counting on from here,
-- 002 preloads the configuration, 003 the reference waveforms. Both belong to
-- the installation, not to the test data (9xx).

SET NAMES utf8mb4;

-- The tables stand in alphabetical order, so some of their foreign keys point
-- forward. During the build the checks are therefore off; on again at the end.
-- On the finished tables this has no effect — the foreign keys are in place
-- afterwards and are enforced.
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     varchar(32) NOT NULL,
  applied_at  timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS achievements (
  ach_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  ach_slave int(10) unsigned NOT NULL,
  ach_action varchar(64) NOT NULL,
  ach_device varchar(60) DEFAULT NULL,
  ach_program int(10) unsigned DEFAULT NULL,
  ach_level tinyint(3) unsigned NOT NULL DEFAULT 1,
  ach_week char(8) NOT NULL,
  ach_day date NOT NULL,
  ach_started datetime NOT NULL DEFAULT current_timestamp(),
  ach_ended datetime DEFAULT NULL,
  ach_duration_s int(10) unsigned DEFAULT NULL,
  ach_target int(10) unsigned DEFAULT NULL,
  ach_target_unit varchar(8) NOT NULL DEFAULT 's',
  ach_max_punish tinyint(3) unsigned NOT NULL DEFAULT 2,
  ach_punish smallint(5) unsigned NOT NULL DEFAULT 0,
  ach_warn smallint(5) unsigned NOT NULL DEFAULT 0,
  ach_metrics text DEFAULT NULL,
  ach_grade char(1) DEFAULT NULL,
  ach_points int(11) NOT NULL DEFAULT 0,
  ach_counted tinyint(1) NOT NULL DEFAULT 1,
  ach_best tinyint(1) NOT NULL DEFAULT 0,
  ach_status enum('running','done','failed','aborted') NOT NULL DEFAULT 'running',
  ach_source enum('device','supervisor') NOT NULL DEFAULT 'device',
  ach_user varchar(64) DEFAULT NULL,
  ach_note varchar(255) DEFAULT NULL,
  PRIMARY KEY (ach_id),
  KEY idx_ach_slave_week (ach_slave,ach_week),
  KEY idx_ach_slave_action_day (ach_slave,ach_action,ach_day),
  KEY idx_ach_week_action (ach_week,ach_action),
  KEY idx_ach_status (ach_status),
  CONSTRAINT fk_ach_slave FOREIGN KEY (ach_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------
-- What the installation has done. The only record of it; never cleared
-- automatically.
CREATE TABLE IF NOT EXISTS audit_log (
  al_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  al_ts datetime(3) NOT NULL DEFAULT current_timestamp(3),
  al_source varchar(16) NOT NULL,
  al_kind varchar(16) NOT NULL,
  al_device varchar(60) DEFAULT NULL,
  al_slave_id int(10) unsigned DEFAULT NULL,
  al_action varchar(64) NOT NULL,
  al_data text DEFAULT NULL,
  al_user varchar(64) DEFAULT NULL,
  PRIMARY KEY (al_id),
  KEY idx_audit_ts (al_ts),
  KEY idx_audit_device_ts (al_device,al_ts),
  KEY idx_audit_slave_ts (al_slave_id,al_ts),
  KEY idx_audit_action (al_action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS badges (
  bd_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  bd_slave int(10) unsigned NOT NULL,
  bd_key varchar(32) NOT NULL,
  bd_earned datetime NOT NULL DEFAULT current_timestamp(),
  bd_ach bigint(20) unsigned DEFAULT NULL,
  PRIMARY KEY (bd_id),
  UNIQUE KEY uq_bd_slave_key (bd_slave,bd_key),
  CONSTRAINT fk_bd_slave FOREIGN KEY (bd_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS challenge_entries (
  ce_challenge bigint(20) unsigned NOT NULL,
  ce_slave int(10) unsigned NOT NULL,
  ce_place int(10) unsigned DEFAULT NULL,
  ce_points int(11) DEFAULT NULL,
  ce_best double DEFAULT NULL,
  ce_punish int(10) unsigned DEFAULT NULL,
  ce_grade char(1) DEFAULT NULL,
  ce_ach bigint(20) unsigned DEFAULT NULL,
  ce_note varchar(64) DEFAULT NULL,
  PRIMARY KEY (ce_challenge,ce_slave),
  KEY idx_ce_slave (ce_slave),
  CONSTRAINT fk_ce_ch FOREIGN KEY (ce_challenge) REFERENCES challenges (ch_id) ON DELETE CASCADE,
  CONSTRAINT fk_ce_slave FOREIGN KEY (ce_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS challenges (
  ch_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  ch_week char(8) NOT NULL,
  ch_action varchar(64) NOT NULL,
  ch_routine int(10) unsigned DEFAULT NULL,
  ch_slave_a int(10) unsigned DEFAULT NULL,
  ch_slave_b int(10) unsigned DEFAULT NULL,
  ch_target int(10) unsigned NOT NULL DEFAULT 0,
  ch_set_by varchar(64) NOT NULL DEFAULT 'aufsicht',
  ch_winner int(10) unsigned DEFAULT NULL,
  ch_status enum('open','decided','void') NOT NULL DEFAULT 'open',
  ch_created datetime NOT NULL DEFAULT current_timestamp(),
  ch_decided datetime DEFAULT NULL,
  PRIMARY KEY (ch_id),
  KEY idx_ch_week (ch_week),
  KEY fk_ch_a (ch_slave_a),
  KEY fk_ch_b (ch_slave_b),
  KEY fk_ch_routine (ch_routine),
  CONSTRAINT fk_ch_a FOREIGN KEY (ch_slave_a) REFERENCES slaves (slave_id) ON DELETE CASCADE,
  CONSTRAINT fk_ch_b FOREIGN KEY (ch_slave_b) REFERENCES slaves (slave_id) ON DELETE CASCADE,
  CONSTRAINT fk_ch_routine FOREIGN KEY (ch_routine) REFERENCES routines (ro_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS day_blocks (
  db_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  db_plan int(10) unsigned NOT NULL,
  db_pos int(10) unsigned NOT NULL DEFAULT 0,
  db_kind enum('plan','program','free','pause') NOT NULL DEFAULT 'plan',
  db_minutes int(10) unsigned NOT NULL DEFAULT 30,
  db_program int(10) unsigned DEFAULT NULL,
  db_action varchar(64) DEFAULT NULL,
  db_text varchar(255) DEFAULT NULL,
  PRIMARY KEY (db_id),
  KEY idx_db_plan (db_plan,db_pos),
  KEY fk_db_program (db_program),
  CONSTRAINT fk_db_plan FOREIGN KEY (db_plan) REFERENCES day_plans (dp_id) ON DELETE CASCADE,
  CONSTRAINT fk_db_program FOREIGN KEY (db_program) REFERENCES program (pro_id) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS day_plans (
  dp_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  dp_name varchar(120) NOT NULL,
  dp_note varchar(255) DEFAULT NULL,
  dp_default tinyint(1) NOT NULL DEFAULT 0,
  dp_created datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (dp_id),
  UNIQUE KEY uq_day_plans_name (dp_name)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS day_sessions (
  ds_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  ds_slave int(10) unsigned NOT NULL,
  ds_day date NOT NULL,
  ds_started datetime NOT NULL DEFAULT current_timestamp(),
  ds_planned_end datetime NOT NULL,
  ds_ended datetime DEFAULT NULL,
  ds_status enum('running','done','capitulated','aborted') NOT NULL DEFAULT 'running',
  ds_plan int(10) unsigned DEFAULT NULL,
  ds_pos int(10) unsigned NOT NULL DEFAULT 0,
  ds_block_kind varchar(16) DEFAULT NULL,
  ds_block_text varchar(255) DEFAULT NULL,
  ds_block_started datetime DEFAULT NULL,
  ds_block_end datetime DEFAULT NULL,
  ds_train_s int(10) unsigned NOT NULL DEFAULT 0,
  ds_free_s int(10) unsigned NOT NULL DEFAULT 0,
  ds_tasks int(10) unsigned NOT NULL DEFAULT 0,
  PRIMARY KEY (ds_id),
  UNIQUE KEY uq_ds_slave_day (ds_slave,ds_day),
  KEY idx_ds_status (ds_status),
  KEY fk_ds_plan (ds_plan),
  CONSTRAINT fk_ds_plan FOREIGN KEY (ds_plan) REFERENCES day_plans (dp_id) ON DELETE SET NULL,
  CONSTRAINT fk_ds_slave FOREIGN KEY (ds_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------
-- Devices that have reported in and belong to nobody (yet).
--
-- An unknown MAC is not taken in silently, and it is not discarded silently
-- either: it lands here and waits for the supervisor to assign it
-- deliberately — the same route as the one taken for an unknown RFID tag of a
-- slave.
CREATE TABLE IF NOT EXISTS device_sightings (
  ds_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  ds_mac varchar(17) NOT NULL,
  ds_chip varchar(16) NOT NULL DEFAULT '',
  ds_uuid varchar(60) NOT NULL,
  ds_model varchar(60) NOT NULL DEFAULT '',
  ds_fw_name varchar(40) NOT NULL DEFAULT '',
  ds_first datetime NOT NULL DEFAULT current_timestamp(),
  ds_last datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  ds_count int(10) unsigned NOT NULL DEFAULT 1,
  PRIMARY KEY (ds_id),
  UNIQUE KEY uq_ds_mac (ds_mac)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------
-- The physical devices of the installation.
--
-- dev_address is the derived UUID and thus the MQTT address; dev_mac is the
-- efuse MAC it comes from. The two can no longer drift apart — that was the
-- reason for deriving it in the first place.
--
-- dev_blocked carries plain text saying WHY a device is blocked (firmware too
-- old, missing signature). A bare yes/no would leave the supervisor standing
-- there with "Geraet gesperrt" and no idea what to do about it.
CREATE TABLE IF NOT EXISTS devices (
  dev_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  dev_name varchar(60) NOT NULL,
  dev_model varchar(64) NOT NULL DEFAULT '',
  dev_address varchar(60) NOT NULL,
  dev_mac varchar(17) DEFAULT NULL,
  dev_chip varchar(16) NOT NULL DEFAULT '',
  dev_mac_locked tinyint(1) NOT NULL DEFAULT 0,
  dev_fw_framework varchar(16) NOT NULL DEFAULT '',
  dev_fw_sketch varchar(16) NOT NULL DEFAULT '',
  dev_fw_name varchar(40) NOT NULL DEFAULT '',
  dev_blocked varchar(160) NOT NULL DEFAULT '',
  dev_seen datetime DEFAULT NULL,
  dev_protocol enum('433','MQTT') NOT NULL DEFAULT 'MQTT',
  PRIMARY KEY (dev_id),
  UNIQUE KEY uq_devices_name (dev_name),
  UNIQUE KEY uq_devices_mac (dev_mac)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS devtoslave (
  dts_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  dts_deviceid int(10) unsigned NOT NULL,
  dts_slaveid int(10) unsigned NOT NULL,
  PRIMARY KEY (dts_id),
  UNIQUE KEY uq_devtoslave_pair (dts_deviceid,dts_slaveid),
  KEY idx_devtoslave_slave (dts_slaveid),
  CONSTRAINT fk_devtoslave_device FOREIGN KEY (dts_deviceid) REFERENCES devices (dev_id),
  CONSTRAINT fk_devtoslave_slave FOREIGN KEY (dts_slaveid) REFERENCES slaves (slave_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pending_effects (
  pe_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  pe_slave int(10) unsigned NOT NULL,
  pe_effect varchar(32) NOT NULL,
  pe_param varchar(64) NOT NULL DEFAULT '',
  pe_reason varchar(64) NOT NULL DEFAULT '',
  pe_created datetime NOT NULL DEFAULT current_timestamp(),
  pe_applied datetime DEFAULT NULL,
  PRIMARY KEY (pe_id),
  KEY idx_pe_slave (pe_slave,pe_applied),
  CONSTRAINT fk_pe_slave FOREIGN KEY (pe_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS privileges (
  pv_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  pv_slave int(10) unsigned NOT NULL,
  pv_key varchar(32) NOT NULL,
  pv_granted datetime NOT NULL DEFAULT current_timestamp(),
  pv_by varchar(64) NOT NULL DEFAULT 'rule',
  pv_until datetime DEFAULT NULL,
  pv_revoked datetime DEFAULT NULL,
  pv_revoked_by varchar(64) DEFAULT NULL,
  PRIMARY KEY (pv_id),
  KEY idx_pv_slave (pv_slave,pv_key),
  CONSTRAINT fk_pv_slave FOREIGN KEY (pv_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS program (
  pro_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  pro_name varchar(120) NOT NULL,
  pro_functions varchar(255) NOT NULL,
  PRIMARY KEY (pro_id),
  UNIQUE KEY uq_program_name (pro_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS program_commands (
  pc_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  pc_program int(10) unsigned NOT NULL,
  pc_command varchar(64) NOT NULL,
  pc_parameter varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY (pc_id),
  KEY idx_program_commands_order (pc_program,pc_id),
  CONSTRAINT fk_program_commands_program FOREIGN KEY (pc_program) REFERENCES program (pro_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ranks (
  rank_no tinyint(3) unsigned NOT NULL,
  rank_name varchar(40) NOT NULL,
  rank_name_alt varchar(40) NOT NULL DEFAULT '',
  rank_up_tasks tinyint(3) unsigned NOT NULL DEFAULT 3,
  rank_up_grade char(1) NOT NULL DEFAULT 'C',
  rank_up_best tinyint(3) unsigned NOT NULL DEFAULT 0,
  rank_up_plan tinyint(1) NOT NULL DEFAULT 0,
  rank_icon varchar(64) NOT NULL DEFAULT '',
  PRIMARY KEY (rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS routine_points (
  rp_routine int(10) unsigned NOT NULL,
  rp_track smallint(5) unsigned NOT NULL DEFAULT 0,
  rp_seq smallint(5) unsigned NOT NULL,
  rp_x int(10) unsigned NOT NULL,
  rp_value tinyint(3) unsigned NOT NULL,
  rp_tol_pct tinyint(3) unsigned NOT NULL DEFAULT 10,
  PRIMARY KEY (rp_routine,rp_track,rp_seq),
  CONSTRAINT fk_rp_routine FOREIGN KEY (rp_routine) REFERENCES routines (ro_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS routine_tracks (
  rt_routine int(10) unsigned NOT NULL,
  rt_track smallint(5) unsigned NOT NULL,
  rt_role enum('zieltiefe','bestrafung','stimulation','belohnung') NOT NULL DEFAULT 'zieltiefe',
  rt_profile varchar(32) DEFAULT NULL,
  rt_channel varchar(8) NOT NULL DEFAULT '',
  rt_mode enum('absolut','gekoppelt') NOT NULL DEFAULT 'absolut',
  rt_couple enum('position','genauigkeit') DEFAULT NULL,
  rt_note varchar(255) DEFAULT NULL,
  PRIMARY KEY (rt_routine,rt_track),
  CONSTRAINT fk_rt_routine FOREIGN KEY (rt_routine) REFERENCES routines (ro_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS routines (
  ro_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  ro_name varchar(120) NOT NULL,
  ro_note varchar(255) DEFAULT NULL,
  ro_axis enum('zeit','tiefe') NOT NULL DEFAULT 'zeit',
  ro_purpose enum('aufgabe','reiz','belohnung') NOT NULL DEFAULT 'aufgabe',
  ro_example tinyint(1) NOT NULL DEFAULT 0,
  ro_level tinyint(3) unsigned NOT NULL DEFAULT 1,
  ro_tol_default tinyint(3) unsigned NOT NULL DEFAULT 10,
  ro_fullscale_pct tinyint(3) unsigned NOT NULL DEFAULT 25,
  ro_loop_ms smallint(5) unsigned NOT NULL DEFAULT 1500,
  ro_min_score smallint(5) unsigned NOT NULL DEFAULT 6000,
  ro_punish_level tinyint(3) unsigned NOT NULL DEFAULT 1,
  ro_reward_level tinyint(3) unsigned NOT NULL DEFAULT 0,
  ro_crc32 int(10) unsigned NOT NULL DEFAULT 0,
  ro_points smallint(5) unsigned NOT NULL DEFAULT 0,
  ro_duration_ms int(10) unsigned NOT NULL DEFAULT 0,
  ro_by varchar(64) DEFAULT NULL,
  ro_created datetime NOT NULL DEFAULT current_timestamp(),
  ro_updated datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (ro_id),
  UNIQUE KEY uq_routines_name (ro_name),
  KEY idx_ro_level (ro_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rules (
  ru_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  ru_trigger varchar(32) NOT NULL,
  ru_cond varchar(32) NOT NULL DEFAULT '',
  ru_effect varchar(32) NOT NULL,
  ru_param varchar(64) NOT NULL DEFAULT '',
  ru_note varchar(255) DEFAULT NULL,
  ru_enabled tinyint(1) NOT NULL DEFAULT 1,
  ru_pos int(10) unsigned NOT NULL DEFAULT 0,
  ru_by varchar(64) DEFAULT NULL,
  PRIMARY KEY (ru_id),
  UNIQUE KEY uq_rule (ru_trigger,ru_cond,ru_effect,ru_param),
  KEY idx_ru_trigger (ru_trigger,ru_enabled)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------
-- Sanctions: lasting TIGHTENINGS, the mirror image of the privileges.
--
-- Deliberately a table of its own and not a sign on `privileges`: whoever
-- forgets the sign hands out a punishment as a favour.
CREATE TABLE IF NOT EXISTS sanctions (
  sa_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  sa_slave int(10) unsigned NOT NULL,
  sa_key varchar(32) NOT NULL,
  sa_imposed datetime NOT NULL DEFAULT current_timestamp(),
  sa_by varchar(64) NOT NULL DEFAULT 'aufsicht',
  sa_reason varchar(160) NOT NULL DEFAULT '',
  sa_until datetime DEFAULT NULL,
  sa_until_day tinyint(1) NOT NULL DEFAULT 0,
  sa_runs_left smallint(5) unsigned DEFAULT NULL,
  sa_lifted datetime DEFAULT NULL,
  sa_lifted_by varchar(64) DEFAULT NULL,
  PRIMARY KEY (sa_id),
  KEY idx_sa_slave (sa_slave,sa_key),
  KEY idx_sa_open (sa_slave,sa_lifted),
  CONSTRAINT fk_sa_slave FOREIGN KEY (sa_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scoring (
  sc_key varchar(32) NOT NULL,
  sc_value varchar(64) NOT NULL,
  sc_desc varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY (sc_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------
-- Calibration per slave AND device: poses of the collar, ceiling and pulse
-- levels of the e-stim bridge, plus the chosen waveform.
--
-- Without an entry there is no output. There is no default and no fallback —
-- a guessed number would be the same sort of fault here that was already made
-- once in 2026.
CREATE TABLE IF NOT EXISTS slave_calibration (
  sc_slave int(10) unsigned NOT NULL,
  sc_device varchar(60) NOT NULL,
  sc_pose varchar(16) NOT NULL,
  sc_x float NOT NULL,
  sc_y float NOT NULL,
  sc_z float NOT NULL,
  sc_still tinyint(1) NOT NULL DEFAULT 1,
  sc_profile varchar(24) NOT NULL DEFAULT '',
  sc_ts datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (sc_slave,sc_device,sc_pose),
  CONSTRAINT fk_calibration_slave FOREIGN KEY (sc_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS slave_levels (
  sl_slave int(10) unsigned NOT NULL,
  sl_action varchar(64) NOT NULL,
  sl_level tinyint(3) unsigned NOT NULL DEFAULT 1,
  sl_streak_up tinyint(3) unsigned NOT NULL DEFAULT 0,
  sl_streak_dn tinyint(3) unsigned NOT NULL DEFAULT 0,
  sl_manual tinyint(1) NOT NULL DEFAULT 0,
  sl_updated datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  sl_by varchar(64) NOT NULL DEFAULT 'auto',
  PRIMARY KEY (sl_slave,sl_action),
  CONSTRAINT fk_sl_slave FOREIGN KEY (sl_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS slave_program (
  sp_program int(10) unsigned NOT NULL,
  sp_slave int(10) unsigned NOT NULL,
  PRIMARY KEY (sp_slave,sp_program),
  KEY idx_slave_program_program (sp_program),
  CONSTRAINT fk_slave_program_program FOREIGN KEY (sp_program) REFERENCES program (pro_id),
  CONSTRAINT fk_slave_program_slave FOREIGN KEY (sp_slave) REFERENCES slaves (slave_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS slave_rank (
  sr_slave int(10) unsigned NOT NULL,
  sr_rank tinyint(3) unsigned NOT NULL DEFAULT 1,
  sr_frozen tinyint(1) NOT NULL DEFAULT 0,
  sr_updated datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  sr_by varchar(64) NOT NULL DEFAULT 'weekly',
  PRIMARY KEY (sr_slave),
  CONSTRAINT fk_sr_slave FOREIGN KEY (sr_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS slave_settings (
  ss_slave int(10) unsigned NOT NULL,
  ss_day_plan int(10) unsigned DEFAULT NULL,
  ss_day_minutes int(10) unsigned NOT NULL DEFAULT 360,
  ss_relogin tinyint(1) NOT NULL DEFAULT 0,
  ss_cal_armed tinyint(1) NOT NULL DEFAULT 0,
  ss_cal_armed_at datetime DEFAULT NULL,
  ss_cal_by varchar(64) DEFAULT NULL,
  ss_updated datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  ss_by varchar(64) DEFAULT NULL,
  PRIMARY KEY (ss_slave),
  KEY fk_ss_plan (ss_day_plan),
  CONSTRAINT fk_ss_plan FOREIGN KEY (ss_day_plan) REFERENCES day_plans (dp_id) ON DELETE SET NULL,
  CONSTRAINT fk_ss_slave FOREIGN KEY (ss_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS slaves (
  slave_id int(10) unsigned NOT NULL AUTO_INCREMENT,
  slave_rfid varchar(255) NOT NULL,
  slave_name varchar(255) NOT NULL,
  slave_program int(10) unsigned DEFAULT NULL,
  PRIMARY KEY (slave_id),
  UNIQUE KEY uq_slaves_rfid (slave_rfid),
  KEY idx_slaves_active_program (slave_id,slave_program),
  CONSTRAINT fk_slaves_active_program FOREIGN KEY (slave_id, slave_program) REFERENCES slave_program (sp_slave, sp_program)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS weekly_review (
  wr_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  wr_slave int(10) unsigned NOT NULL,
  wr_week char(8) NOT NULL,
  wr_runs smallint(5) unsigned NOT NULL DEFAULT 0,
  wr_tasks_passed tinyint(3) unsigned NOT NULL DEFAULT 0,
  wr_best_count tinyint(3) unsigned NOT NULL DEFAULT 0,
  wr_plan_total tinyint(3) unsigned NOT NULL DEFAULT 0,
  wr_plan_done tinyint(3) unsigned NOT NULL DEFAULT 0,
  wr_plan_complete tinyint(1) NOT NULL DEFAULT 0,
  wr_trained tinyint(1) NOT NULL DEFAULT 0,
  wr_punish smallint(5) unsigned NOT NULL DEFAULT 0,
  wr_score int(11) NOT NULL DEFAULT 0,
  wr_place tinyint(3) unsigned DEFAULT NULL,
  wr_rank_before tinyint(3) unsigned NOT NULL,
  wr_rank_after tinyint(3) unsigned NOT NULL,
  wr_reason varchar(255) DEFAULT NULL,
  wr_grades varchar(64) DEFAULT NULL,
  -- Sanctions of the week (doc 26). DISPLAY, NO SCORING.
  --
  -- wr_sanctions holds what was imposed and lifted again during the week,
  -- wr_sanctions_open how many of them are still running at the end.
  --
  -- Why that does NOT go into wr_score (decision by Philine, 2026-09-13): a
  -- sanction is imposed BECAUSE something went wrong — and what went wrong is
  -- already in the scoring (failed runs, an incomplete plan, punishments).
  -- Whoever counts the sanction into the points a second time punishes the same
  -- thing twice, and nobody could say afterwards which deduction came from
  -- where.
  wr_sanctions varchar(255) DEFAULT NULL,
  wr_sanctions_open tinyint(3) unsigned NOT NULL DEFAULT 0,
  wr_remark varchar(500) DEFAULT NULL,
  wr_pdf_path varchar(255) DEFAULT NULL,
  wr_shown tinyint(1) NOT NULL DEFAULT 0,
  wr_created datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (wr_id),
  UNIQUE KEY uq_wr_slave_week (wr_slave,wr_week),
  CONSTRAINT fk_wr_slave FOREIGN KEY (wr_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS weekly_tasks (
  wt_id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  wt_slave int(10) unsigned NOT NULL,
  wt_week char(8) NOT NULL,
  wt_action varchar(64) NOT NULL,
  wt_routine int(10) unsigned DEFAULT NULL,
  wt_target int(10) unsigned NOT NULL DEFAULT 0,
  wt_max_punish tinyint(3) unsigned NOT NULL DEFAULT 2,
  wt_level tinyint(3) unsigned DEFAULT NULL,
  wt_kind enum('plan','detention','challenge') NOT NULL DEFAULT 'plan',
  wt_status enum('proposed','open','done','failed') NOT NULL DEFAULT 'open',
  wt_done_ach bigint(20) unsigned DEFAULT NULL,
  wt_challenge bigint(20) unsigned DEFAULT NULL,
  wt_by varchar(64) NOT NULL DEFAULT 'aufsicht',
  wt_created datetime NOT NULL DEFAULT current_timestamp(),
  wt_updated datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (wt_id),
  KEY idx_wt_slave_week (wt_slave,wt_week),
  KEY fk_wt_routine (wt_routine),
  CONSTRAINT fk_wt_routine FOREIGN KEY (wt_routine) REFERENCES routines (ro_id) ON DELETE SET NULL,
  CONSTRAINT fk_wt_slave FOREIGN KEY (wt_slave) REFERENCES slaves (slave_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


SET FOREIGN_KEY_CHECKS = 1;

INSERT IGNORE INTO schema_migrations (version) VALUES ('001');
