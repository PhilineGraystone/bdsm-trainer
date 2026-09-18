# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Logbook, points, rank, week plan, privileges, badges (doc 14).

Own DB connection with a lock like libs/audit.py: the central unit calls from
two threads (main loop + paho network thread). Errors are logged, never passed
up — the logbook must not stop the installation. Everything that is decided
here (grade, points, rank) is scoring; the safety stays in the devices
(doc 03), the punishment channel is a request to them.

Course of a run
  slaveprogram.execute  -> prepare() (apply level) -> device command
                        -> start()   (achievements row, status running)
  device events         -> device_event(): count punish/warn, fault -> channel,
                           result -> finish(): grade, points, best performance,
                           anti-grinding, week plan, detention, badges,
                           privileges, task level
  tick()                -> weekly review (rank), plan proposal, activation
"""

import datetime
import json
import logging
import random
import threading
import time

import pymysql

import actions
import i18n
import audit
import budgets as budgetsmod
import pauses as pausesmod
import streaks as streaksmod
import dayform as dayformmod
import scenarios as scenariosmod
import profiles
import routines
import tasktypes

logger = logging.getLogger('Punisher')

BONUS_WEEK = 'BONUS_WEEK'
BONUS_CHALLENGE = 'BONUS_CHALLENGE'
GRADE_FACTOR_KEYS = {'A': 'factor_a', 'B': 'factor_b', 'C': 'factor_c', 'D': 'factor_d', 'E': 'factor_e', 'F': 'factor_f'}

# Badges: key -> (name, description). Rules in Logbook._badges().
BADGES = {
    'first_a':       ('Erste A', 'Erster Durchgang mit Note A'),
    'tasks_10':      ('Zehn', '10 bestandene Durchgänge'),
    'tasks_50':      ('Fünfzig', '50 bestandene Durchgänge'),
    'tasks_100':     ('Hundert', '100 bestandene Durchgänge'),
    'pet_10h':       ('Zehn Stunden Pet', '10 Stunden im Pet-Modus insgesamt'),
    'week_complete': ('Pflichtbewusst', 'Erster vollständig bestandener Wochenplan'),
    'best_of_week':  ('Wochenbester', 'Bestes Wochenergebnis in einer Aufgabe'),
    'no_drop_4':     ('Standhaft', 'Vier Wochenbewertungen in Folge ohne Abstieg'),
    'rank_5':        ('Halbzeit', 'Rang 5 erreicht'),
    'rank_10':       ('Vollendet', 'Rang 10 erreicht'),
    'challenge_won': ('Duellant', 'Eine Herausforderung gewonnen'),
    'clean_week':    ('Makellos', 'Eine Woche mit Training und ohne einzige Bestrafung'),
}

# Sanctions: key -> (name, effect). The counterpart to the privileges.
#
# A privilege is EARNED and eases things; a sanction is IMPOSED and tightens
# them. Both last — that is what tells them apart from `punish` (one stimulus,
# over at once) and from `detention` (an extra task next week). Until now the
# installation lacked lasting tightening entirely (finding Philine 2026-09-11:
# „the punishment item is missing, for example spending the next while in
# restraints only").
#
# Only what the installation can actually ENFORCE is taken in. A sanction that
# merely stands there is a house rule — and house rules belong in the rule set,
# not in the firmware.
SANCTIONS = {
    'restrained': ('In Fesseln',
                   'MAGLOCK-Schritte werden Pflicht, UNLOCK-Schritte entfallen — das Schloss '
                   'bleibt zu. Sticht das Privileg „Ohne Fesseln" aus.'),
    'cage_on':    ('V-Cage bleibt an',
                   'Ein laufender V-Cage fällt nicht mehr von selbst weg: endet ein anderer '
                   'Halsband-Modus oder läuft die Maximaldauer ab, kommt er zurück. '
                   'EINSCHALTEN tut die Auflage nichts — das bleibt ein Handgriff der Aufsicht. '
                   'Ein Not-Aus beendet ihn und holt ihn nicht zurück.'),
    'no_reward':  ('Keine Belohnungen',
                   'Belohnungen im Kanal werden zurückgehalten. Steht im Protokoll, damit '
                   'niemand einen Fehler vermutet.'),
    'no_warn':    ('Ohne Vorwarnung',
                   'Bestrafungen kommen ohne die Vorwarnung, die sonst vorausgeht. Sticht das '
                   'Privileg „Immer Vorwarnung" aus.'),
}

# Which sanction trumps which privilege. An imposed tightening has to beat
# an earned easing — otherwise the punishment would be without effect on
# exactly the one who has earned something beforehand, and that is the
# wrong order.
SANCTION_BEATS = {'restrained': 'no_restraints', 'no_warn': 'no_warn_off'}

# Privileges: key -> (name, effect)
PRIVILEGES = {
    'no_restraints': ('Ohne Fesseln', 'MAGLOCK-Schritte werden im Programm übersprungen'),
    'no_warn_off':   ('Immer Vorwarnung', 'Bestrafungen kommen stets mit Vorwarnung (Kanal warn=1)'),
    'free_stay':     ('Freier Aufenthalt', 'Kein freies Training am Ende des Tages — der Tag endet, wenn der Plan erfüllt ist'),
}


def week_str(d=None):
    d = d or datetime.date.today()
    if isinstance(d, datetime.datetime):
        d = d.date()
    y, w, _ = d.isocalendar()
    return f'{y}-W{w:02d}'


def week_monday(week):
    """'YYYY-Www' -> Montag als date."""
    y, w = int(week[:4]), int(week[6:8])
    return datetime.date.fromisocalendar(y, w, 1)


def next_week(week):
    return week_str(week_monday(week) + datetime.timedelta(days=7))


def prev_week(week):
    return week_str(week_monday(week) - datetime.timedelta(days=7))


class Run:
    """A run in progress (achievements row with status running)."""

    def __init__(self, ach_id, slave_id, slave_name, action, task, device, params, level, target,
                 max_punish, program_id, blocking, timeout_s, points_factor=1.0, free=False):
        self.id = ach_id
        self.slave_id = slave_id
        self.slave_name = slave_name
        self.action = action
        self.task = task
        self.device = device
        self.params = params
        self.level = level
        self.target = target
        self.max_punish = max_punish
        self.program_id = program_id
        self.started = time.time()
        self.punish = 0
        self.warn = 0
        self.faults = 0
        self.metrics = {}
        self.blocking = blocking
        self.timeout_at = (self.started + timeout_s) if (blocking and timeout_s) else None
        self.timeout_reason = 'timeout'      # 'program': scheduled end without a device message
        self.finished = False
        self.status = None                   # done | failed | aborted (after the end)
        self.points_factor = float(points_factor or 1.0)   # free training: half weighting
        self.free = bool(free)
        self.deferred = None                 # (ev, status, deadline): result waits for open channel punishments

    def snapshot(self):
        return {'id': self.id, 'action': self.action, 'device': self.device, 'level': self.level,
                'target': self.target, 'unit': self.task.target_unit, 'max_punish': self.max_punish,
                'started': int(self.started), 'punish': self.punish, 'warn': self.warn, 'faults': self.faults,
                'elapsed_s': int(time.time() - self.started)}


class Logbook:

    def __init__(self):
        self._cfg = None
        self._db = None
        self._lock = threading.RLock()
        self.runs = {}                 # (slave_id, device) -> Run
        self.pending_cids = {}         # channel id -> {'run': Run|None, 'slave_id', 't', 'reason', 'level', 'kind', 'source', 'user', 'retries'}
        self.channel_queue = []        # waiting channel punishments (minimum pause / repeat after busy), decision Philine 2026-09-10
        self.channel_last = {}         # slave_id -> time of the last channel punishment
        self.reward_last = {}          # slave_id -> time of the last channel reward (cooldown, doc 44 §1)
        self.channel_day = {}          # (slave_id, 'YYYY-MM-DD') -> count
        self.on_event = None           # f(kind, data): the central unit publishes an event (MQTT) + audit
        self.slave_lookup = None       # f(slave_id) -> slave|None (logged in?), set by the central unit
        self.publish_punish = None     # f(slave_id, level, kind, reason, source) -> cid
        # Which punishment kinds the OTHER devices of this slave listen for
        # (2.3.5, doc 57). f(slave_id, except_device) -> set of kinds. Injected
        # like publish_punish, because only punmqtt knows who is online and
        # what each device reported in its hello.
        self.punish_kinds_of = None
        self.publish_reward = None     # f(slave_id, level, kind, reason, source) -> cid
        self._scoring = None
        self._scoring_t = 0.0
        # Safety limits of the channel from config.ini [safety] (decision Philine 2026-09-10:
        # not changeable over the web, therefore not in `scoring`)
        self.limits = {'channel_gap_s': 3, 'channel_day_max': 60,
                       # day model (doc 14 §12.1) — hard limits, no rule raises them
                       'day_minutes_default': 360, 'day_minutes_max': 480,
                       'train_block_max_min': 45, 'break_min_min': 10}
        self.day_enabled = False       # migration 007 present?
        self.routines_enabled = False  # migration 008 present? (waveforms, doc 17)
        self._dead_rules = set()       # rule ids already reported as unreachable (doc 58 §8)
        # Budgets and cooldowns (doc 44 §1): the one place that answers "how often"
        # and "how close". It reads the [safety] ceiling live out of self.limits.
        self.budgets = budgetsmod.Budgets(self._q, self.limits)
        # Pause / holiday (doc 44 §2): the one place that says whether a slave is
        # paused. Day plan, rules, channel, review and streaks all ask here.
        self.pauses = pausesmod.Pauses(self._q)
        # Streaks (doc 44 §3): counters with a counting and a reset condition;
        # they only fire triggers, the consequences live in the rule set.
        self.streaks = streaksmod.Streaks(self)
        self.level_bounds_enabled = False   # slave_levels.sl_min/sl_max present? (migration 008)
        # Day form (doc 44 §5): one modifier over the day; it bends rewards and
        # activity budgets through budgets.modifier, punish budgets it leaves alone.
        self.dayform = dayformmod.Dayform(self)
        self.budgets.modifier = lambda sid: self.dayform.budget_pct(self.dayform.of(sid))
        # Scenarios (doc 44 §7): the bundle with a name, on top of all of the above.
        self.scenarios = scenariosmod.Scenarios(self)
        self._last_tick = 0.0
        self.enabled = False

    # ------------------------------------------------------------------ #
    # DB
    def init(self, db_config):
        self._cfg = dict(host=db_config['hostname'], user=db_config['username'],
                         password=db_config['password'], database=db_config['database'],
                         autocommit=True, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        # ARE THE TABLES THERE?
        #
        # Until 2.0 this read "is there migration 005/007/008?". That went well
        # exactly as long as it took for the migrations to be renumbered: on the
        # first rebuild of the database the day model vanished silently, because
        # there was no 007 any more — the tables had long been there. So the
        # question asked is the one that matters: for the tables themselves.
        self.enabled = self._has_table('achievements')
        if not self.enabled:
            logger.warning('logbook: Tabelle achievements fehlt - Logbuch/Punkte/Rang sind aus')
        self.day_enabled = self._has_table('day_plans') and self._has_table('rules')
        if self.enabled and not self.day_enabled:
            logger.warning('logbook: day_plans/rules fehlen - Tagesmodell/Regeln aus, '
                           'altes Verhalten (ein Programm je Anmeldung)')
        self.routines_enabled = self._has_table('routines')
        if self.enabled and not self.routines_enabled:
            logger.warning('logbook: Tabelle routines fehlt - Wellenform-Routinen sind aus')
        self.budgets.enabled = self._has_table('budgets')
        if self.enabled and not self.budgets.enabled:
            logger.warning('logbook: Tabelle budgets fehlt (Migration 005) - nur die Decke aus [safety] gilt')
        self.pauses.enabled = self._has_table('pauses')
        if self.enabled and not self.pauses.enabled:
            logger.warning('logbook: Tabelle pauses fehlt (Migration 006) - keine Pausen')
        self.streaks.enabled = self._has_table('streaks') and self._has_table('streak_state')
        if self.enabled and not self.streaks.enabled:
            logger.warning('logbook: Tabellen streaks/streak_state fehlen (Migration 007) - keine Serien')
        self.level_bounds_enabled = self._has_column('slave_levels', 'sl_min')
        if self.enabled and not self.level_bounds_enabled:
            logger.warning('logbook: slave_levels.sl_min fehlt (Migration 008) - Stufengrenzen nur anlagenweit')
        self.dayform.enabled = self._has_table('dayforms')
        if self.enabled and not self.dayform.enabled:
            logger.warning('logbook: Tabelle dayforms fehlt (Migration 009) - keine Tagesform')
        self.scenarios.enabled = self._has_table('scenarios') and self._has_table('scenario_active')
        if self.enabled and not self.scenarios.enabled:
            logger.warning('logbook: Tabellen scenarios fehlen (Migration 011) - keine Szenarien')
        return self.enabled

    def _has_column(self, table, column):
        rows = self._q("SELECT column_name FROM information_schema.columns "
                       " WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s", (table, column))
        return bool(rows)

    def _has_table(self, name):
        rows = self._q("SELECT table_name FROM information_schema.tables "
                       " WHERE table_schema = DATABASE() AND table_name = %s", (name,))
        return bool(rows)

    def _connect(self):
        if self._cfg is None:
            return None
        try:
            if self._db is None:
                self._db = pymysql.connect(**self._cfg)
            else:
                try:
                    self._db.ping(reconnect=False)
                except pymysql.Error:
                    self._db = pymysql.connect(**self._cfg)    # pymysql >= 1.1: the reconnect argument is deprecated
            return self._db
        except pymysql.Error as e:
            logger.error('logbook: db connect failed: %s', e)
            self._db = None
            return None

    def _q(self, sql, params=(), one=False):
        with self._lock:
            db = self._connect()
            if db is None:
                return None if one else []
            try:
                with db.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchone() if one else cur.fetchall()
            except pymysql.Error as e:
                logger.error('logbook: query failed: %s -- %s', e, sql[:120])
                return None if one else []

    # Public for libs/dayplan.py: the same connection including the lock instead of a third one
    def query(self, sql, params=(), one=False):
        return self._q(sql, params, one)

    def execute(self, sql, params=()):
        return self._x(sql, params)

    def _x(self, sql, params=()):
        with self._lock:
            db = self._connect()
            if db is None:
                return None
            try:
                with db.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.lastrowid
            except pymysql.Error as e:
                logger.error('logbook: write failed: %s -- %s', e, sql[:120])
                return None

    # ------------------------------------------------------------------ #
    # Settings (scoring)
    def scoring(self, force=False):
        now = time.time()
        if force or self._scoring is None or now - self._scoring_t > 30:
            rows = self._q('SELECT sc_key, sc_value FROM scoring')
            if rows:
                self._scoring = {r['sc_key']: r['sc_value'] for r in rows}
                self._scoring_t = now
            elif self._scoring is None:
                self._scoring = {}
        return self._scoring

    def sc_int(self, key, default):
        try:
            return int(float(self.scoring().get(key, default)))
        except (TypeError, ValueError):
            return default

    def sc_float(self, key, default):
        try:
            return float(self.scoring().get(key, default))
        except (TypeError, ValueError):
            return default

    def sc_str(self, key, default):
        v = self.scoring().get(key)
        return v if v not in (None, '') else default

    def set_scoring(self, key, value):
        self._x('INSERT INTO scoring (sc_key, sc_value) VALUES (%s,%s) ON DUPLICATE KEY UPDATE sc_value=VALUES(sc_value)',
                (key, str(value)))
        self.scoring(force=True)

    def set_limits(self, section):
        """Take over the [safety] section of config.ini (missing keys keep the default)."""
        for k in list(self.limits):
            try:
                v = section.get(k) if section is not None else None
                if v not in (None, ''):
                    self.limits[k] = int(float(v))
            except (TypeError, ValueError, AttributeError):
                logger.warning('logbook: [safety] %s ungueltig - Vorgabe %s bleibt', k, self.limits[k])
        logger.info('logbook: Kanalgrenzen gap=%ss day_max=%s', self.limits['channel_gap_s'], self.limits['channel_day_max'])

    def default_max_punish(self):
        return self.sc_int('default_max_punish', 2)

    def pass_grade(self):
        g = self.sc_str('pass_grade', 'C').upper()
        return g if g in tasktypes.GRADES else 'C'

    def passed(self, grade):
        return grade is not None and grade in tasktypes.GRADES and \
            tasktypes.GRADES.index(grade) <= tasktypes.GRADES.index(self.pass_grade())

    # ------------------------------------------------------------------ #
    # Ranks
    def ranks(self):
        rows = self._q('SELECT * FROM ranks ORDER BY rank_no') or []
        alt = self.sc_str('rank_names', 'main') == 'alt'
        for r in rows:
            r['name'] = (r['rank_name_alt'] or r['rank_name']) if alt else r['rank_name']
        return rows

    def rank_row(self, rank_no):
        for r in self.ranks():
            if r['rank_no'] == rank_no:
                return r
        return None

    def rank_of(self, slave_id):
        r = self._q('SELECT sr_rank, sr_frozen FROM slave_rank WHERE sr_slave=%s', (slave_id,), one=True)
        if not r:
            return 1, False
        return int(r['sr_rank']), bool(r['sr_frozen'])

    def rank_name(self, rank_no):
        r = self.rank_row(rank_no)
        return r['name'] if r else f'Rang {rank_no}'

    def set_rank(self, slave_id, rank_no, by='aufsicht', frozen=None, reason=None):
        rank_no = max(1, min(10, int(rank_no)))
        old, old_frozen = self.rank_of(slave_id)
        if frozen is None:
            frozen = old_frozen
        self._x('INSERT INTO slave_rank (sr_slave, sr_rank, sr_frozen, sr_by) VALUES (%s,%s,%s,%s) '
                'ON DUPLICATE KEY UPDATE sr_rank=VALUES(sr_rank), sr_frozen=VALUES(sr_frozen), sr_by=VALUES(sr_by)',
                (slave_id, rank_no, 1 if frozen else 0, by))
        if old != rank_no:
            self._badges_rank(slave_id, rank_no)
            self._emit('rank_change', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'from': old, 'to': rank_no,
                                       'rank_name': self.rank_name(rank_no), 'by': by, 'reason': reason})
        return rank_no

    # ------------------------------------------------------------------ #
    # Task level
    def level_of(self, slave_id, action):
        r = self._q('SELECT sl_level FROM slave_levels WHERE sl_slave=%s AND sl_action=%s', (slave_id, action), one=True)
        return int(r['sl_level']) if r else 1

    def levels_of(self, slave_id):
        cols = 'sl_action, sl_level, sl_manual' + (', sl_min, sl_max' if self.level_bounds_enabled else '')
        rows = self._q(f'SELECT {cols} FROM slave_levels WHERE sl_slave=%s', (slave_id,)) or []
        return {r['sl_action']: {'level': int(r['sl_level']), 'manual': bool(r['sl_manual']),
                                 'min': r.get('sl_min'), 'max': r.get('sl_max')} for r in rows}

    def level_bounds(self, slave_id, action):
        """(lo, hi) the level may move in for this slave and task (doc 44 §4):
        the row's own bounds where set, else 1 / level_max."""
        lo, hi = 1, self.sc_int('level_max', 10)
        if self.level_bounds_enabled:
            r = self._q('SELECT sl_min, sl_max FROM slave_levels WHERE sl_slave=%s AND sl_action=%s', (slave_id, action), one=True)
            if r:
                if r['sl_min']:
                    lo = max(lo, int(r['sl_min']))
                if r['sl_max']:
                    hi = min(hi, int(r['sl_max']))
        if hi < lo:
            hi = lo
        return lo, hi

    def set_level_bounds(self, slave_id, action, lo, hi, by='aufsicht'):
        """Set (or clear, with None) the bounds; the current level is pulled inside them."""
        if not self.level_bounds_enabled:
            return None
        cap = self.sc_int('level_max', 10)
        lo = max(1, min(cap, int(lo))) if lo else None
        hi = max(1, min(cap, int(hi))) if hi else None
        if lo and hi and hi < lo:
            lo, hi = hi, lo
        self._x('INSERT INTO slave_levels (sl_slave, sl_action, sl_level, sl_min, sl_max, sl_by) VALUES (%s,%s,%s,%s,%s,%s) '
                'ON DUPLICATE KEY UPDATE sl_min=VALUES(sl_min), sl_max=VALUES(sl_max), sl_by=VALUES(sl_by), '
                'sl_level=LEAST(GREATEST(sl_level, COALESCE(VALUES(sl_min), 1)), COALESCE(VALUES(sl_max), sl_level))',
                (slave_id, action, lo or 1, lo, hi, by))
        return lo, hi

    def set_level(self, slave_id, action, level, by='aufsicht'):
        lo, hi = self.level_bounds(slave_id, action)
        level = max(lo, min(hi, int(level)))
        self._x('INSERT INTO slave_levels (sl_slave, sl_action, sl_level, sl_manual, sl_by, sl_streak_up, sl_streak_dn) '
                'VALUES (%s,%s,%s,1,%s,0,0) ON DUPLICATE KEY UPDATE sl_level=VALUES(sl_level), sl_manual=1, '
                'sl_by=VALUES(sl_by), sl_streak_up=0, sl_streak_dn=0', (slave_id, action, level, by))
        return level

    def _adapt_level(self, slave_id, action, grade):
        """Two A/B in a row -> level +1; two D-F in a row -> level -1 (never below 1).
        If the supervisor has set it, the automatic system pauses until the next run."""
        row = self._q('SELECT sl_level, sl_streak_up, sl_streak_dn, sl_manual FROM slave_levels WHERE sl_slave=%s AND sl_action=%s',
                      (slave_id, action), one=True)
        level = int(row['sl_level']) if row else 1
        up = int(row['sl_streak_up']) if row else 0
        dn = int(row['sl_streak_dn']) if row else 0
        manual = bool(row['sl_manual']) if row else False
        if manual:
            self._x('UPDATE slave_levels SET sl_manual=0, sl_streak_up=0, sl_streak_dn=0 WHERE sl_slave=%s AND sl_action=%s',
                    (slave_id, action))
            return level, 0
        change = 0
        lo, hi = self.level_bounds(slave_id, action)      # per slave and task since 2.3 (doc 44 §4)
        if grade in ('A', 'B'):
            up, dn = up + 1, 0
            if up >= 2 and level < hi:
                level += 1
                up = 0
                change = 1
        elif grade in ('D', 'E', 'F'):
            dn, up = dn + 1, 0
            if dn >= 2 and level > lo:
                level -= 1
                dn = 0
                change = -1
        else:
            up = dn = 0
        self._x('INSERT INTO slave_levels (sl_slave, sl_action, sl_level, sl_streak_up, sl_streak_dn, sl_manual, sl_by) '
                'VALUES (%s,%s,%s,%s,%s,0,%s) ON DUPLICATE KEY UPDATE sl_level=VALUES(sl_level), sl_streak_up=VALUES(sl_streak_up), '
                'sl_streak_dn=VALUES(sl_streak_dn), sl_manual=0, sl_by=VALUES(sl_by)',
                (slave_id, action, level, up, dn, 'auto'))
        return level, change

    # ------------------------------------------------------------------ #
    # Waveform routines (doc 17). The database is the truth, the EEPROM of the
    # device only a cache — which is why the central unit always delivers the
    # complete routine here, with a checksum over the byte stream that was sent.
    def routine_payload(self, ro_id):
        """{row, tracks, crc32} for the transfer to the device, None if unknown.

        As of doc 19 a waveform has several tracks; each one goes as its own transaction
        with its own checksum, the overall checksum stands in the header."""
        if not self.routines_enabled or not ro_id:
            return None
        row = routines.get(self._q, ro_id)
        if not row:
            return None
        axis = row.get('ro_axis') or routines.AXIS_TIME
        tracks, whole = [], bytearray()
        for t in routines.tracks(self._q, ro_id):
            pay = routines.track_payload(self._q, ro_id, t, axis)
            if not pay['points']:
                continue
            whole += routines.serialise(pay['points'], axis)
            tracks.append(pay)
        if not tracks:
            logger.error('Logbook: waveform %s has no breakpoints in any track', ro_id)
            return None
        crc = routines.crc32(bytes(whole))
        if int(row.get('ro_crc32') or 0) != crc:
            # The device is always told the checksum of the bytes it actually gets, so a
            # run still works; the stored column is stale (breakpoints changed outside
            # the editor) and only the display and the duration estimate are off.
            logger.warning('Logbook: waveform %s has a stale checksum in the database '
                           '(%08X stored, %08X sent)', ro_id, int(row.get('ro_crc32') or 0), crc)
        return {'row': row, 'tracks': tracks, 'crc32': crc}

    def estim_limits(self):
        """Limits of the output (doc 19). The ceiling is set by the wearer on the device himself —
        these here are the limits of the INSTALLATION, not those of the device."""
        return {'day_max_s': self.sc_int('estim_day_max_s', 3600),
                'event_max_s': self.sc_int('estim_event_max_s', 20),
                'frame_ms': self.sc_int('estim_frame_ms', 100),
                'stale_ms': self.sc_int('live_stale_ms', 1500),
                'level_pct': [self.sc_int('estim_level1_pct', 25),
                              self.sc_int('estim_level2_pct', 45),
                              self.sc_int('estim_level3_pct', 70)]}

    def routine_limits(self):
        """Trigger threshold, lockout time and pause window for the run (doc 17 §9).
        The hard safety limit is NOT among them — it stands in the firmware."""
        return {'fault_ms': self.sc_int('routine_fault_ms', 2000),
                'fault_gap_s': self.sc_int('routine_fault_gap_s', 10),
                'away_pause_s': self.sc_int('routine_away_pause_s', 3),
                'start_wait_s': self.sc_int('routine_start_wait_s', 60),
                'invalid_max': self.sc_int('routine_invalid_max', 30)}

    def routines_for_day(self, slave_id):
        """Routine ids that this slave needs today: from the week plan, from
        open challenges and the waveform that matches their level.
        Sent in advance at login (doc 17 §7)."""
        if not self.routines_enabled:
            return []
        out, week = [], week_str()
        code = 'TRAINER_ROUTINE'
        for r in self._q('SELECT wt_routine FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s '
                         "AND wt_action=%s AND wt_status IN ('proposed','open') AND wt_routine IS NOT NULL",
                         (slave_id, week, code)) or []:
            out.append(int(r['wt_routine']))
        for r in self._q('SELECT ch_routine FROM challenges WHERE ch_week=%s AND ch_action=%s '
                         "AND ch_status='open' AND ch_routine IS NOT NULL", (week, code)) or []:
            out.append(int(r['ch_routine']))
        ro_id = routines.pick_for_level(self._q, self.level_of(slave_id, code))
        if ro_id:
            out.append(int(ro_id))
        seen, uniq = set(), []
        for i in out:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        return uniq

    # ------------------------------------------------------------------ #
    # Runs
    def prepare(self, slave_id, action, params, level_bump=0, target_override=None, max_punish_override=None,
                routine_override=None):
        """Before the device command: apply the task level, determine target and max_punish.
        Returns (params_scaled, level, target, max_punish) or None for actions that cannot be trained."""
        task = tasktypes.get(action.code)
        if task is None or not self.enabled:
            return None
        level = self.level_of(slave_id, action.code)
        if level_bump:
            # free training: every n-th task one level higher (doc 14 §12.3)
            level = max(1, min(self.sc_int('level_max', 10), level + int(level_bump)))
        # day form (doc 44 §5): an offset, inside her bounds (doc 44 §4)
        off = self.dayform.level_offset(self.dayform.of(slave_id))
        if off:
            lo, hi = self.level_bounds(slave_id, action.code)
            level = max(lo, min(hi, level + off))
        scaled = task.apply_level(params, level, self.sc_int('level_max', 10))
        target = task.target(scaled)
        if task.level_select:
            # The level CHOOSES the waveform, it does not scale a target (doc 17 §14).
            # Without a waveform the task cannot run -> the step is dropped.
            if not self.routines_enabled:
                logger.error('Logbook: %s needs migration 008 (waveform routines) - step skipped', action.code)
                return None
            ro = routines.resolve(self._q, int(routine_override or scaled.get('routine') or 0) or None, level)
            if not ro:
                logger.error("Logbook: %s for slave %s has no routine for level %d - step skipped",
                             action.code, slave_id, level)
                return None
            scaled['routine'] = int(ro['ro_id'])
            # The target value is the minimum grade: the plan target beats the default of the waveform.
            target = int(ro.get('ro_min_score') or self.sc_int('routine_min_score', 6000))
        if target_override:
            # The plan target beats the value in the program step (doc 14 §12.2)
            want = int(target_override)
            if task.target_param in scaled:
                scaled[task.target_param] = max(1, int(round(want / (task.target_factor or 1))))
            else:
                # Tasks without a target parameter (level_select): the target comes from
                # the task itself, not from a program step.
                target = want
        if max_punish_override is not None and 'max_punish' in scaled:
            scaled['max_punish'] = int(max_punish_override)
        # Tightened values stay within the allowed range of the action (review 2026-09-10:
        # e.g. nose button 3600 s × 1,15^9 was far above what the pad permits)
        for p in action.params:
            if p.name in scaled and scaled[p.name] is not None and p.type is int:
                v = scaled[p.name]
                if p.min is not None and v < p.min and p.name != 'max_punish':
                    v = p.min
                if p.max is not None and v > p.max:
                    v = p.max
                scaled[p.name] = v
        mp = scaled.get('max_punish', -1)
        if mp is None or mp < 0:
            mp = self.default_max_punish()
        if not task.level_select:
            target = task.target(scaled)     # the target stands in the (possibly capped) parameter
        return scaled, level, target, int(mp)

    def start(self, slave_id, slave_name, action, params, device, level, target, max_punish, program_id=None,
              points_factor=1.0, free=False):
        task = tasktypes.get(action.code)
        if task is None or not self.enabled:
            return None
        key = (slave_id, device)
        old = self.runs.get(key)
        if old and not old.finished:
            self._finish(old, {'reason': 'replaced'}, status='aborted')
        now = datetime.datetime.now()
        ach_id = self._x('INSERT INTO achievements (ach_slave, ach_action, ach_device, ach_program, ach_level, ach_week, ach_day, '
                         ' ach_started, ach_target, ach_target_unit, ach_max_punish, ach_status) '
                         'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,\'running\')',
                         (slave_id, action.code, device, program_id, level, week_str(now), now.date(), now,
                          target, task.target_unit, max_punish))
        run = Run(ach_id, slave_id, slave_name, action.code, task, device, params, level, target, max_punish,
                  program_id, action.blocking, action.timeout_s(params), points_factor=points_factor, free=free)
        self.runs[key] = run
        logger.info("Logbook: run #%s %s for '%s' on %s (level %d, target %d %s, max_punish %d)",
                    ach_id, action.code, slave_name, (device or '?')[:8], level, target, task.target_unit, max_punish)
        return run

    def active_run(self, slave_id, device):
        r = self.runs.get((slave_id, device))
        return r if r and not r.finished else None

    def runs_of(self, slave_id):
        return [r for (sid, _), r in self.runs.items() if sid == slave_id and not r.finished]

    def device_event(self, slave_id, device, ev):
        """Event from a device of the slave. Returns the result of a
        finished run (dict) or None."""
        if not self.enabled:
            return None
        cls = ev.get('cls') or 'info'
        run = self.active_run(slave_id, device)
        if ev.get('event') == 'cmd_rejected' and run is not None and time.time() - run.started < 15:
            # The device has rejected the start command (no sensor, busy ...): the run
            # just created cannot run -> end it ungraded instead of letting the program
            # wait until the deadline and burdening the slave with 'failed' (review 2026-09-10).
            logger.warning("Logbook: run #%s %s aborted - device rejected command (%s)", run.id, run.action, ev.get('error'))
            return self._finish(run, {'reason': 'rejected', 'error': str(ev.get('error') or '')}, status='aborted')
        if ev.get('event') == 'punish_rejected':
            # The stimulator has rejected the channel punishment (busy/emergency): no
            # execution, so do not count it — remove the entry so that _finish() does not
            # count it as open (doc 14: counting at execution). Review 2026-09-10.
            try:
                cid = int(ev.get('cid') or 0)
            except (TypeError, ValueError):
                cid = 0
            pend = self.pending_cids.pop(cid, None) if cid else None
            audit.central('punish_rejected', slave_id=slave_id, device=device,
                          data={'cid': cid, 'reason': ev.get('reason'), 'why': ev.get('error'), 'run': pend['run'].id if pend and pend.get('run') else None})
            logger.warning('Logbook: device %s rejected channel punish cid=%s (%s)', (device or '?')[:8], cid, ev.get('error'))
            if pend and str(ev.get('error') or '') == 'busy' and int(pend.get('retries') or 0) < self.sc_int('channel_retry_max', 1):
                # The stimulator was busy (a pulse was already running): repeat once after channel_retry_s (decision Philine 2026-09-10)
                self._enqueue_punish(pend['slave_id'], pend.get('level', 1), pend.get('kind', 'any'), pend.get('reason', ''),
                                     pend.get('source', 'central'), pend.get('run'), pend.get('user'),
                                     time.time() + self.sc_int('channel_retry_s', 3), int(pend.get('retries') or 0) + 1, 'busy')
            else:
                self._finish_if_deferred(pend.get('run') if pend else None)
            return None
        if cls == 'punish':
            cid = ev.get('cid')
            self._own_punish(slave_id, device, ev)
            target = None
            if cid is not None:
                pend = self.pending_cids.pop(int(cid), None)
                if pend:
                    target = pend.get('run')
                    if target is not None and target.finished:
                        target = None
            if target is None and cid is None:
                target = run                       # punishment of the mode on this device
            if target is None and cid is not None and run is not None and ev.get('source') != 'channel':
                target = run
            if target is not None:
                target.punish += 1
                self._finish_if_deferred(target)
            return None
        if cls == 'warn':
            if run is not None:
                run.warn += 1
            return None
        if cls == 'fault':
            # A device without a stimulator reports a violation: punishment over the channel
            reason = ev.get('reason') or ev.get('event') or 'fault'
            if run is not None:
                run.faults += 1
            level = int(ev.get('level') or self.sc_int('fault_level', 1))
            self.punish(slave_id, level, str(ev.get('kind') or 'any'), reason, device, run=run)
            return None
        if cls == 'result':
            if run is None:
                return None
            if ev.get('event') == 'trainer_end' and run.action == 'TRAINER_ROUTINE':
                # Too many invalid samples (face out of range, soiling):
                # the run cannot be graded and is not counted (doc 17 §9).
                ticks = int(ev.get('ticks') or 0)
                bad = int(ev.get('ticks_invalid') or 0)
                share = (100.0 * bad / ticks) if ticks else 100.0
                if share > self.sc_int('routine_invalid_max', 30):
                    logger.warning('Logbook: run #%s TRAINER_ROUTINE not counted - %.0f %% invalid ticks',
                                   run.id, share)
                    ev = dict(ev, reason='invalid')
                    return self._finish(run, ev, status='aborted')
            if run.task.result_events and ev.get('event') not in run.task.result_events:
                # Result of another process on the same device (e.g. mode_end of the V-Cage)
                if ev.get('event') == 'mode_end' and ev.get('mode') not in ('pet', 'sleep', 'statue'):
                    return None
            return self._finish(run, ev)
        return None

    def finish_by_program(self, slave_id, device, reason='program'):
        """The program ends the background mode (REMOTE_CONTROL): the run ends as
        scheduled — the device usually delivers mode_end (switched) anyway."""
        run = self.active_run(slave_id, device)
        if run and not run.task.fail_ends and run.task.kind == 'duration':
            return self._finish(run, {'reason': reason, 'duration_s': int(time.time() - run.started)})
        return None

    def abort_runs(self, slave_id, reason, device=None):
        out = []
        for key, run in list(self.runs.items()):
            if key[0] != slave_id or run.finished:
                continue
            if device is not None and key[1] != device:
                continue
            out.append(self._finish(run, {'reason': reason}, status='aborted'))
        return out

    def check_timeouts(self):
        """From the main loop (~20/s): queue of the channel, deferred
        results (grace period expired) and deadlines of blocking tasks."""
        now = time.time()
        results = []
        self._pump_channel(now)
        for run in list(self.runs.values()):
            if run.finished or run.deferred is None:
                continue
            ev, status, deadline = run.deferred
            if now >= deadline:
                logger.warning("Logbook: run #%s %s finished without executed punishment (grace over)", run.id, run.action)
                results.append(self._finish(run, ev, status, force=True))
        for run in list(self.runs.values()):
            if run.finished or run.deferred is not None or run.timeout_at is None or now < run.timeout_at:
                continue
            if run.timeout_reason == 'program':
                results.append(self._finish(run, {'reason': 'program', 'duration_s': int(now - run.started)}))
                continue
            logger.warning("Logbook: run #%s %s timed out without result", run.id, run.action)
            results.append(self._finish(run, {'reason': 'timeout', 'duration_s': int(now - run.started)}, status='failed'))
        return results

    @staticmethod
    def _metrics_from(ev):
        skip = {'event', 'cls', 'slave_id', 'ts_ms', 'mode', 'kind', 'reason', 'cid', 'source'}
        out = {}
        for k, v in (ev or {}).items():
            if k in skip:
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = v
            elif isinstance(v, bool):
                out[k] = int(v)
        return out

    def _finish_if_deferred(self, run):
        if run is not None and run.deferred is not None and not run.finished and not self._open_channel(run):
            ev, status, _ = run.deferred
            self._finish(run, ev, status, force=True)

    def _finish(self, run, ev, status=None, force=False):
        if run.finished:
            return None
        # Counting at execution (doc 14, decision Philine 2026-09-10): if channel punishments for
        # this run are still in flight or queued (violation and result often arrive in the very
        # same moment, the collar only fires afterwards), the result waits for the execution —
        # at most finish_grace_s; after that only what was executed counts.
        if status != 'aborted' and not force and self._open_channel(run):
            if run.deferred is None:
                run.deferred = (ev, status, time.time() + self.sc_int('finish_grace_s', 10))
                logger.info("Logbook: run #%s %s result deferred - channel punishment pending", run.id, run.action)
            else:
                run.deferred = (ev, status, run.deferred[2])
            return None
        run.finished = True
        run.deferred = None
        self.runs.pop((run.slave_id, run.device), None)
        if status == 'aborted':
            self._purge_channel(run)
        reason = str((ev or {}).get('reason') or 'done')
        metrics = self._metrics_from(ev)
        metrics.setdefault('duration_s', int(time.time() - run.started))
        dev_punish = metrics.pop('punish', None)
        dev_warn = metrics.pop('warn', None)
        if dev_punish is not None and dev_punish > run.punish:
            run.punish = int(dev_punish)             # the device counted along (e.g. pulses without an event assignment)
        if dev_warn is not None and dev_warn > run.warn:
            run.warn = int(dev_warn)
        metrics['punish'] = run.punish
        metrics['warn'] = run.warn
        metrics['faults'] = run.faults
        if status is None:
            if reason in ('stop', 'stopped', 'imu_lost', 'emergency', 'unassigned', 'device_lost', 'aborted',
                          'logout', 'replaced', 'safe_state', 'switched_early', 'rejected', 'invalid'):
                status = 'aborted'
            elif reason in ('lost', 'timeout', 'max_miss', 'wrong', 'failed', 'not_started'):
                status = 'failed'
            else:
                status = 'done'
        run.status = status
        grade, ratio, points, best = None, 0.0, 0, False
        level_change = 0
        if status != 'aborted':
            grade, ratio = run.task.grade(run, metrics, reason, run.punish, run.max_punish)
            metrics['ratio'] = round(ratio, 3)
            base = self.sc_int('base_per_level', 10) * run.level
            factor = self.sc_float(GRADE_FACTOR_KEYS[grade], 1.0)
            points = max(0, int(round(base * factor)) - self.sc_int('malus_punish', 3) * run.punish)
            if run.points_factor and abs(run.points_factor - 1.0) > 1e-9:
                points = int(round(points * run.points_factor))   # free training: half weighting
                metrics['points_factor'] = round(run.points_factor, 3)
            metrics['points_core'] = points
            # personal best only from passed runs (decision Philine
            # 2026-09-10: before this, even a first run with grade F got the bonus)
            if status in ('done', 'failed') and self.passed(grade):
                val = run.task.best_value(metrics)
                if val is not None:
                    prev = self._best_value(run.slave_id, run.action)
                    if run.task.is_better(val, prev):
                        best = True
                        points += self.sc_int('bonus_best', 15)
            # streak bonus: consecutive days with training (today counted in)
            streak = self._streak_days(run.slave_id)
            bonus_streak = min(self.sc_int('bonus_streak_step', 5) * max(0, streak - 1), self.sc_int('bonus_streak_cap', 25))
            points += bonus_streak
            metrics['streak_days'] = streak
        now = datetime.datetime.now()
        self._x('UPDATE achievements SET ach_ended=%s, ach_duration_s=%s, ach_punish=%s, ach_warn=%s, ach_metrics=%s, '
                'ach_grade=%s, ach_points=%s, ach_best=%s, ach_status=%s WHERE ach_id=%s',
                (now, int(metrics.get('duration_s') or 0), run.punish, run.warn,
                 json.dumps(metrics, ensure_ascii=False), grade, points, 1 if best else 0, status, run.id))
        result = {'slave_id': run.slave_id, 'name': run.slave_name, 'ach_id': run.id, 'action': run.action,
                  'action_name': (actions.get(run.action).name if actions.get(run.action) else run.action),
                  'device': run.device, 'status': status, 'reason': reason, 'grade': grade, 'points': points,
                  'best': best, 'level': run.level, 'target': run.target, 'unit': run.task.target_unit,
                  'punish': run.punish, 'warn': run.warn, 'metrics': metrics, 'week_complete': False,
                  'badges': [], 'privileges': [], 'level_change': 0, 'detention': False, 'counted': True}
        if status != 'aborted':
            result['counted'] = self._recount_day(run.slave_id, run.action, now.date(), run.id)
            if status in ('done', 'failed') and not (run.free and run.points_factor < 1.0 and run.level <= self.level_of(run.slave_id, run.action)):
                # Free training on one's own level does not drive the level up (otherwise light
                # training would tighten the week plan); a stretch run one level higher does.
                level, level_change = self._adapt_level(run.slave_id, run.action, grade)
                result['level_change'] = level_change
                result['level_now'] = level
            if self.passed(grade):
                result['week_complete'] = self._fulfil_weekly(run, grade)
                if result['week_complete']:
                    self._bonus(run.slave_id, BONUS_WEEK, self.sc_int('bonus_week', 50), 'Wochenplan vollständig')
            result['detention'] = self._detention_check(run)
            result['badges'] = self._badges(run, grade, status)
            result['privileges'] = self._privileges(run, grade)
            # Sanctions that are measured in RUNS count down here -
            # and only on a passed one. Otherwise a sanction would run
            # out by aborting, and that would be the wrong lesson (doc 26).
            result['sanctions_done'] = self.sanction_run_passed(run.slave_id)
            self._challenge_check(run)
            # rule set (doc 14 §12.5): run passed / run not passed
            ctx = {'grade': grade, 'action': run.action, 'target': run.target, 'free': run.free}
            slave_obj = self.slave_lookup(run.slave_id) if self.slave_lookup else None
            self.apply_rules('run_passed' if self.passed(grade) else 'run_failed', run.slave_id, ctx, slave=slave_obj)
            if result['week_complete']:
                self.apply_rules('plan_complete', run.slave_id, ctx, slave=slave_obj)
            # streaks (doc 44 §3) — after the rules of the run, so that a chain
            # reads run_failed -> detention, then streak_reached -> escalation
            try:
                self.streaks.on_run(run.slave_id, run.action, self.passed(grade))
            except Exception as e:  # noqa: BLE001 - a streak must never blow up the grading
                logger.error('streaks on_run: %s', e, exc_info=True)
        logger.info("Logbook: run #%s %s for '%s' -> %s grade=%s points=%d punish=%d best=%s reason=%s",
                    run.id, run.action, run.slave_name, status, grade, points, run.punish, best, reason)
        audit.central('achievement', slave_id=run.slave_id, device=run.device, data=result)
        self._emit('achievement', result)
        return result

    def _best_value(self, slave_id, action, exclude_id=None):
        task = tasktypes.get(action)
        rows = self._q("SELECT ach_id, ach_metrics FROM achievements WHERE ach_slave=%s AND ach_action=%s AND ach_status IN ('done','failed') "
                       "AND ach_grade IS NOT NULL AND ach_grade<=%s AND ach_metrics IS NOT NULL ORDER BY ach_id DESC LIMIT 500",
                       (slave_id, action, self.pass_grade())) or []
        best = None
        for r in rows:
            if exclude_id and r['ach_id'] == exclude_id:
                continue
            try:
                m = json.loads(r['ach_metrics'])
            except (TypeError, ValueError):
                continue
            v = task.best_value(m)
            if task.is_better(v, best):
                best = v
        return best

    def _streak_days(self, slave_id):
        rows = self._q("SELECT DISTINCT ach_day FROM achievements WHERE ach_slave=%s AND ach_status IN ('done','failed') "
                       "AND ach_action NOT LIKE 'BONUS_%%' ORDER BY ach_day DESC LIMIT 60", (slave_id,)) or []
        days = [r['ach_day'] for r in rows]
        today = datetime.date.today()
        if today not in days:
            days.insert(0, today)
        streak = 0
        d = today
        for day in days:
            # paused days (doc 44 §2) do not count and do not break: step over them
            while day < d and self.pauses.is_paused_day(slave_id, d):
                d = d - datetime.timedelta(days=1)
            if day == d:
                streak += 1
                d = d - datetime.timedelta(days=1)
            elif day < d:
                break
        return streak

    def _recount_day(self, slave_id, action, day, ach_id):
        """Anti-grinding: per action and day only the best N runs count towards
        the leaderboard (ach_counted). Returns whether the run ach_id counts."""
        # Since 2.3 the number is a budget (activity / activity:<ACTION>, doc 44 §1);
        # the scoring key only remains as the fallback for a database without migration 005.
        n = self.budgets.max_count(budgetsmod.ACTIVITY_PREFIX + action, slave_id, 'day')
        if n is None:
            n = self.sc_int('count_per_day', 2)
        n = max(1, int(n))
        rows = self._q("SELECT ach_id FROM achievements WHERE ach_slave=%s AND ach_action=%s AND ach_day=%s "
                       "AND ach_status IN ('done','failed') ORDER BY ach_points DESC, ach_punish ASC, ach_id ASC",
                       (slave_id, action, day)) or []
        counted = {r['ach_id'] for r in rows[:n]}
        for r in rows:
            self._x('UPDATE achievements SET ach_counted=%s WHERE ach_id=%s', (1 if r['ach_id'] in counted else 0, r['ach_id']))
        return ach_id in counted

    def _fulfil_weekly(self, run, grade):
        """Fulfil an open weekly task of the same action. Returns True if the week
        plan (plan + detention) is thereby complete."""
        week = week_str()
        tasks = self._q("SELECT * FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_action=%s AND wt_status='open' "
                        "ORDER BY wt_target DESC", (run.slave_id, week, run.action)) or []
        done_now = False
        for t in tasks:
            if run.target >= int(t['wt_target'] or 0) and run.punish <= int(t['wt_max_punish']):
                self._x("UPDATE weekly_tasks SET wt_status='done', wt_done_ach=%s WHERE wt_id=%s", (run.id, t['wt_id']))
                done_now = True
                break
        if not done_now:
            return False
        rows = self._q("SELECT wt_status, wt_kind FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_kind IN ('plan','detention')",
                       (run.slave_id, week)) or []
        if not rows or any(r['wt_status'] != 'done' for r in rows):
            return False                # open/proposed OR not passed -> not complete (review 2026-09-10)
        # complete — bonus only once per week
        if self._q("SELECT ach_id FROM achievements WHERE ach_slave=%s AND ach_week=%s AND ach_action=%s",
                   (run.slave_id, week, BONUS_WEEK), one=True):
            return False
        return True

    def _bonus(self, slave_id, code, points, note, week=None):
        now = datetime.datetime.now()
        self._x("INSERT INTO achievements (ach_slave, ach_action, ach_level, ach_week, ach_day, ach_started, ach_ended, "
                " ach_duration_s, ach_target, ach_target_unit, ach_grade, ach_points, ach_counted, ach_status, ach_note) "
                "VALUES (%s,%s,1,%s,%s,%s,%s,0,0,'x','-',%s,1,'done',%s)",
                (slave_id, code, week or week_str(now), now.date(), now, now, points, note))
        self._emit('bonus', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'code': code, 'points': points, 'note': note})

    def _detention_check(self, run):
        """Detention: from detention_punish punishments in the week on, an extra task."""
        thr = self.sc_int('detention_punish', 6)
        if thr <= 0:
            return False
        week = week_str()
        tot = self._q("SELECT COALESCE(SUM(ach_punish),0) AS n FROM achievements WHERE ach_slave=%s AND ach_week=%s",
                      (run.slave_id, week), one=True)
        if not tot or int(tot['n']) < thr:
            return False
        if self._q("SELECT wt_id FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_kind='detention' AND wt_status IN ('open','proposed')",
                   (run.slave_id, week), one=True):
            return False
        # only one detention task per thr punishments
        n_det = self._q("SELECT COUNT(*) AS n FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_kind='detention'",
                        (run.slave_id, week), one=True)
        if n_det and int(n_det['n']) >= int(tot['n']) // thr:
            return False
        self._x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_by) "
                "VALUES (%s,%s,%s,%s,%s,'detention','open','auto')",
                (run.slave_id, week, run.action, run.target, max(0, run.max_punish - 1)))
        self._emit('detention', {'slave_id': run.slave_id, 'name': run.slave_name, 'action': run.action,
                                 'target': run.target, 'punish_week': int(tot['n'])})
        self.apply_rules('punish_threshold', run.slave_id,
                         {'action': run.action, 'target': run.target, 'punish_week': int(tot['n'])},
                         slave=self.slave_lookup(run.slave_id) if self.slave_lookup else None)
        return True

    # ------------------------------------------------------------------ #
    # Badges / privileges / challenges
    def has_badge(self, slave_id, key):
        return bool(self._q('SELECT bd_id FROM badges WHERE bd_slave=%s AND bd_key=%s', (slave_id, key), one=True))

    def grant_badge(self, slave_id, key, ach_id=None):
        if key not in BADGES or self.has_badge(slave_id, key):
            return False
        self._x('INSERT IGNORE INTO badges (bd_slave, bd_key, bd_ach) VALUES (%s,%s,%s)', (slave_id, key, ach_id))
        self._emit('badge', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'badge': key,
                             'badge_name': i18n._(BADGES[key][0])})
        return True

    def badges_of(self, slave_id):
        rows = self._q('SELECT bd_key, bd_earned FROM badges WHERE bd_slave=%s ORDER BY bd_earned', (slave_id,)) or []
        return [{'key': r['bd_key'], 'name': i18n._(BADGES.get(r['bd_key'], (r['bd_key'], ''))[0]), 'earned': str(r['bd_earned'])}
                for r in rows]

    def _badges(self, run, grade, status):
        new = []
        sid = run.slave_id
        if grade == 'A' and self.grant_badge(sid, 'first_a', run.id):
            new.append('first_a')
        n = self._q("SELECT COUNT(*) AS n FROM achievements WHERE ach_slave=%s AND ach_status='done' AND ach_grade<=%s AND ach_action NOT LIKE 'BONUS_%%'",
                    (sid, self.pass_grade()), one=True)
        n = int(n['n']) if n else 0
        for k, thr in (('tasks_10', 10), ('tasks_50', 50), ('tasks_100', 100)):
            if n >= thr and self.grant_badge(sid, k, run.id):
                new.append(k)
        if run.action == 'PET':
            t = self._q("SELECT COALESCE(SUM(ach_duration_s),0) AS s FROM achievements WHERE ach_slave=%s AND ach_action='PET' AND ach_status='done'",
                        (sid,), one=True)
            if t and int(t['s']) >= 36000 and self.grant_badge(sid, 'pet_10h', run.id):
                new.append('pet_10h')
        return new

    def _badges_rank(self, slave_id, rank_no):
        if rank_no >= 5:
            self.grant_badge(slave_id, 'rank_5')
        if rank_no >= 10:
            self.grant_badge(slave_id, 'rank_10')

    def privileges_of(self, slave_id):
        rows = self._q('SELECT pv_key, pv_granted, pv_by, pv_until FROM privileges WHERE pv_slave=%s '
                       'AND pv_revoked IS NULL AND (pv_until IS NULL OR pv_until > NOW())', (slave_id,)) or []
        return [{'key': r['pv_key'], 'name': i18n._(PRIVILEGES.get(r['pv_key'], (r['pv_key'], ''))[0]), 'granted': str(r['pv_granted']),
                 'until': str(r['pv_until'])[:19] if r['pv_until'] else None, 'by': r['pv_by']} for r in rows]

    def has_privilege(self, slave_id, key):
        return bool(self._q('SELECT pv_id FROM privileges WHERE pv_slave=%s AND pv_key=%s AND pv_revoked IS NULL '
                            'AND (pv_until IS NULL OR pv_until > NOW())', (slave_id, key), one=True))

    def grant_privilege(self, slave_id, key, by='rule', weeks=None):
        if key not in PRIVILEGES or self.has_privilege(slave_id, key):
            return False
        until = (datetime.datetime.now() + datetime.timedelta(weeks=int(weeks))) if weeks else None
        self._x('INSERT INTO privileges (pv_slave, pv_key, pv_by, pv_until) VALUES (%s,%s,%s,%s)',
                (slave_id, key, by, until))
        self._emit('privilege', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'privilege': key,
                                 'privilege_name': i18n._(PRIVILEGES[key][0]), 'granted': True, 'by': by})
        return True

    def revoke_privilege(self, slave_id, key, by='aufsicht'):
        self._x('UPDATE privileges SET pv_revoked=NOW(), pv_revoked_by=%s WHERE pv_slave=%s AND pv_key=%s AND pv_revoked IS NULL',
                (by, slave_id, key))
        self._emit('privilege', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'privilege': key,
                                 'privilege_name': i18n._(PRIVILEGES.get(key, (key, ''))[0]), 'granted': False, 'by': by})

    # --------------- Sanctions (doc 26) -------------------------------- #
    def warn_for(self, slave_id):
        """Should a punishment on the channel be preceded by a warning?

        True  — privilege "Always warned"
        False — sanction "Without a warning" (trumps the privilege)
        None  — the installation has no opinion; the default of the device applies

        The sanction comes BEFORE the privilege: an imposed tightening has to
        beat an earned easing (doc 26).
        """
        if self.has_sanction(slave_id, 'no_warn'):
            return False
        if self.has_privilege(slave_id, 'no_warn_off'):
            return True
        return None

    def estim_ceiling(self, slave_id):
        """(A %, B %) for the punishment/reward channel of this slave.

        The channel is ONE envelope for all of their stimulators, but the calibration
        hangs on person AND device. If she has two bridges with different ceilings,
        the LOWER one applies here — the same rule as with the envelopes: the
        strictest limit wins (doc 23). To form an average would mean exceeding a
        limit that somebody has measured.

        None means: measured on none of her devices. The bridge then outputs
        nothing; the collar keeps punishing, that is a different device.
        """
        rows = self._q("SELECT sc_x, sc_y FROM slave_calibration "
                       " WHERE sc_slave=%s AND sc_pose='estim'", (slave_id,)) or []
        vals = [(int(round(r['sc_x'])), int(round(r['sc_y']))) for r in rows]
        vals = [(a, b) for a, b in vals if a > 0 or b > 0]
        if not vals:
            return None
        return (max(0, min(100, min(a for a, _ in vals))),
                max(0, min(100, min(b for _, b in vals))))

    # Default when nothing is entered - the same numbers that used to stand in
    # the NVS of the bridge. They stand here now because the central unit sends
    # them along and the supervisor should be able to see them (doc 31).
    LEVEL_DEFAULT = (25, 45, 70)

    def estim_levels(self, slave_id, what='punish'):
        """(level 1, level 2, level 3) as a percentage of HER CEILING, for channel pulses.

        `what` is 'punish' or 'reward' — the two run on different
        channels and are meant to differ in character, not in height
        (doc 19 §3). If the praise hung on the number of the punishment,
        exactly that separation would be undone again, hence two sets
        (decision Philine 2026-09-12).

        With several bridges the LOWEST value per level applies — the same rule
        as with the ceiling (doc 23): the strictest limit wins. Without an entry
        25/45/70 applies; that is defensible here, because the ceiling caps
        everything anyway and a missing ratio is not an unmeasured maximum.
        """
        pose = 'estim_reward' if what == 'reward' else 'estim_punish'
        rows = self._q("SELECT sc_x, sc_y, sc_z FROM slave_calibration "
                       " WHERE sc_slave=%s AND sc_pose=%s", (slave_id, pose)) or []
        vals = [(int(round(r['sc_x'])), int(round(r['sc_y'])), int(round(r['sc_z']))) for r in rows]
        vals = [v for v in vals if any(x > 0 for x in v)]
        if not vals:
            return self.LEVEL_DEFAULT
        return tuple(max(1, min(100, min(v[i] for v in vals))) for i in range(3))

    def estim_pct(self, slave_id, level, what='punish'):
        """The percentage for EXACTLY this level, ready to be sent along.

        Punishments carry the day form (doc 44 §5) as a factor — and are capped
        at 100, which is her ceiling: strict never goes above what was measured.
        Rewards are not bent by the form; a reward is not discipline."""
        lv = max(1, min(3, int(level or 1)))
        pct = self.estim_levels(slave_id, what)[lv - 1]
        if what == 'punish':
            f = self.dayform.pulse_pct(self.dayform.of(slave_id))
            if f != 100:
                pct = max(1, min(100, int(round(pct * f / 100))))
        return pct

    # Profile when none is entered - exactly what the firmware had hard-wired
    # until 2026-09-12. An installed base without an entry therefore behaves
    # exactly as it did before (doc 32).
    PROFILE_DEFAULT = {'punish': 'stich', 'reward': 'zweitakt'}

    def estim_profile(self, slave_id, what='punish'):
        """The profile for her pulses — which waveform, not how high.

        WHY IT IS SELECTABLE AT ALL: where the electrodes sit decides which
        frequency arrives. `stich` sweeps across the skin at 50..80 Hz — too
        little on the buttocks, too much on the pubic area (finding Philine
        2026-09-12). The firmware had that hard-wired, and thus made an
        anatomical decision that it cannot make.

        WITH SEVERAL BRIDGES there is NO „strictest limit" here as there is with
        the ceiling — a profile is not an amount, `haken` is not smaller than
        `stich`. If her devices do not agree, the default of the role applies.
        A foreign profile on foreign-sitting electrodes would be the worse
        answer than what applied before; the slave side displays the
        contradiction so that somebody resolves it.
        """
        pose = 'estim_reward' if what == 'reward' else 'estim_punish'
        rows = self._q("SELECT sc_profile FROM slave_calibration "
                       " WHERE sc_slave=%s AND sc_pose=%s", (slave_id, pose)) or []
        keys = {(r['sc_profile'] or '').strip() for r in rows}
        keys.discard('')
        if len(keys) == 1:
            key = keys.pop()
            if profiles.get(key):
                return key
        return self.PROFILE_DEFAULT['reward' if what == 'reward' else 'punish']

    def sanctions_of(self, slave_id):
        """The running sanctions of a slave, for the display and the API."""
        rows = self._q('SELECT sa_key, sa_imposed, sa_by, sa_reason, sa_until, sa_until_day, sa_runs_left '
                       '  FROM sanctions WHERE sa_slave=%s AND sa_lifted IS NULL '
                       '   AND (sa_until IS NULL OR sa_until > NOW()) ORDER BY sa_imposed', (slave_id,)) or []
        return [{'key': r['sa_key'],
                 'name': i18n._(SANCTIONS.get(r['sa_key'], (r['sa_key'], ''))[0]),
                 'imposed': str(r['sa_imposed'])[:19], 'by': r['sa_by'], 'reason': r['sa_reason'],
                 'until': str(r['sa_until'])[:19] if r['sa_until'] else None,
                 'until_day': bool(r['sa_until_day']),
                 'runs_left': int(r['sa_runs_left']) if r['sa_runs_left'] is not None else None}
                for r in rows]

    def has_sanction(self, slave_id, key):
        return bool(self._q('SELECT sa_id FROM sanctions WHERE sa_slave=%s AND sa_key=%s AND sa_lifted IS NULL '
                            'AND (sa_until IS NULL OR sa_until > NOW())', (slave_id, key), one=True))

    def impose_sanction(self, slave_id, key, by='aufsicht', reason='',
                        hours=None, until_day=False, runs=None):
        """Impose a sanction. Returns False if it is already running.

        The three ends may be mixed; what ends is whatever comes FIRST. A
        sanction without any end at all is allowed, but it then stands until
        somebody lifts it — and that is exactly the one that gets forgotten.
        Which is why the interface says so.
        """
        if key not in SANCTIONS or self.has_sanction(slave_id, key):
            return False
        until = (datetime.datetime.now() + datetime.timedelta(hours=float(hours))) if hours else None
        self._x('INSERT INTO sanctions (sa_slave, sa_key, sa_by, sa_reason, sa_until, sa_until_day, sa_runs_left) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (slave_id, key, by, (reason or '')[:160], until, 1 if until_day else 0,
                 int(runs) if runs else None))
        self._emit('sanction', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                'sanction': key, 'sanction_name': i18n._(SANCTIONS[key][0]),
                                'imposed': True, 'by': by, 'reason': reason,
                                'until': str(until)[:19] if until else None,
                                'until_day': bool(until_day),
                                'runs_left': int(runs) if runs else None})
        return True

    def lift_sanction(self, slave_id, key, by='aufsicht'):
        n = self._x('UPDATE sanctions SET sa_lifted=NOW(), sa_lifted_by=%s '
                    ' WHERE sa_slave=%s AND sa_key=%s AND sa_lifted IS NULL', (by, slave_id, key))
        self._emit('sanction', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                'sanction': key, 'sanction_name': i18n._(SANCTIONS.get(key, (key, ''))[0]),
                                'imposed': False, 'by': by})
        return n

    def _week_sanctions(self, slave_id, week):
        """Sanctions of a week for the weekly review. (doc 26)

        What is delivered is a short line for the display and the number of
        those still running at the weekend. Neither goes into the scoring — the
        reasoning stands in sql/001_baseline.sql at `wr_sanctions`.
        """
        start = week_monday(week)
        end = start + datetime.timedelta(days=7)
        rows = self._q('SELECT sa_key, sa_lifted, sa_until FROM sanctions '
                       ' WHERE sa_slave=%s AND sa_imposed>=%s AND sa_imposed<%s '
                       ' ORDER BY sa_imposed', (slave_id, start, end)) or []
        if not rows:
            return '', 0
        counts, open_n = {}, 0
        now = datetime.datetime.now()
        for r in rows:
            counts[r['sa_key']] = counts.get(r['sa_key'], 0) + 1
            still = r['sa_lifted'] is None and (r['sa_until'] is None or r['sa_until'] > now)
            if still:
                open_n += 1
        text = ', '.join(f'{k}×{n}' if n > 1 else k for k, n in sorted(counts.items()))
        return text[:255], open_n

    def expire_sanctions(self, slave_id=None, reason='abgelaufen'):
        """Close expired sanctions. Called at the change of day and at
        logout; the queries filter by `sa_until` anyway, but a sanction that
        STANDS THERE closed can be followed in the log, and one that merely no
        longer takes effect cannot."""
        where = 'sa_lifted IS NULL AND sa_until IS NOT NULL AND sa_until <= NOW()'
        args = [reason]
        if slave_id:
            where += ' AND sa_slave=%s'
            args.append(slave_id)
        return self._x('UPDATE sanctions SET sa_lifted=NOW(), sa_lifted_by=%s WHERE ' + where, tuple(args))

    def end_day_sanctions(self, slave_id, by='tagesende'):
        """Sanctions that end with the day."""
        return self._x('UPDATE sanctions SET sa_lifted=NOW(), sa_lifted_by=%s '
                       ' WHERE sa_slave=%s AND sa_lifted IS NULL AND sa_until_day=1', (by, slave_id))

    def sanction_run_passed(self, slave_id):
        """A passed run counts towards every sanction that is measured in
        runs. At 0 it is worked off.

        Counting happens on the PASSED run, not on every one: otherwise a
        sanction would run out by aborting, and that would be the wrong lesson."""
        rows = self._q('SELECT sa_id, sa_key, sa_runs_left FROM sanctions WHERE sa_slave=%s '
                       ' AND sa_lifted IS NULL AND sa_runs_left IS NOT NULL', (slave_id,)) or []
        done = []
        for r in rows:
            left = max(0, int(r['sa_runs_left']) - 1)
            if left:
                self._x('UPDATE sanctions SET sa_runs_left=%s WHERE sa_id=%s', (left, r['sa_id']))
            else:
                self._x("UPDATE sanctions SET sa_runs_left=0, sa_lifted=NOW(), sa_lifted_by='abgearbeitet' "
                        ' WHERE sa_id=%s', (r['sa_id'],))
                done.append(r['sa_key'])
                self._emit('sanction', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                        'sanction': r['sa_key'],
                                        'sanction_name': i18n._(SANCTIONS.get(r['sa_key'], (r['sa_key'], ''))[0]),
                                        'imposed': False, 'by': 'abgearbeitet'})
        return done

    def privilege_active(self, slave_id, key):
        """A privilege applies — UNLESS a sanction trumps it.

        This one function is the reason why sanctions and privileges did not have
        to stand in one table: the precedence belongs in ONE place, and whoever
        asks past it (`has_privilege`) still gets the bare fact. In operation the
        question is asked here."""
        if not self.has_privilege(slave_id, key):
            return False
        for sk, pk in SANCTION_BEATS.items():
            if pk == key and self.has_sanction(slave_id, sk):
                return False
        return True

    def _privileges(self, run, grade):
        new = []
        if run.action.startswith('TRAINER_') and grade == 'A':
            n = self._q("SELECT COUNT(*) AS n FROM achievements WHERE ach_slave=%s AND ach_action LIKE 'TRAINER_%%' AND ach_grade='A' AND ach_status='done'",
                        (run.slave_id,), one=True)
            if n and int(n['n']) >= self.sc_int('priv_no_restraints_a', 3) and self.grant_privilege(run.slave_id, 'no_restraints'):
                new.append('no_restraints')
        return new

    def _challenge_check(self, run):
        """Challenge (doc 14 §12.4): leaderboard over ALL slaves, not a duel.
        As soon as every slave of the field has a scored run, it is
        decided; otherwise at the weekly review at the latest."""
        week = week_str()
        rows = self._q("SELECT * FROM challenges WHERE ch_week=%s AND ch_action=%s AND ch_status='open'",
                       (week, run.action)) or []
        for ch in rows:
            field = self._challenge_field(ch['ch_id'])
            if run.slave_id not in field:
                continue
            if all(self._challenge_result(sid, ch) for sid in field):
                self.decide_challenge(ch['ch_id'])

    def _challenge_field(self, ch_id):
        """Slave field: the entries of the challenge (challenge_entries)."""
        rows = self._q('SELECT ce_slave FROM challenge_entries WHERE ce_challenge=%s', (ch_id,)) or []
        return [int(r['ce_slave']) for r in rows]

    def _challenge_result(self, slave_id, ch):
        """Best scored run of the week in this task (target reached) or None."""
        rows = self._q("SELECT ach_id, ach_grade, ach_punish, ach_points, ach_metrics, ach_ended FROM achievements "
                       "WHERE ach_slave=%s AND ach_week=%s AND ach_action=%s AND ach_status IN ('done','failed') "
                       "AND ach_target>=%s ORDER BY ach_points DESC, ach_punish ASC, ach_ended ASC LIMIT 20",
                       (slave_id, ch['ch_week'], ch['ch_action'], ch['ch_target'])) or []
        if not rows:
            return None
        task = tasktypes.get(ch['ch_action'])
        best = None
        for r in rows:
            try:
                m = json.loads(r['ach_metrics']) if r['ach_metrics'] else {}
            except (TypeError, ValueError):
                m = {}
            val = task.best_value(m) if task else None
            cand = {'ach': r['ach_id'], 'grade': r['ach_grade'], 'punish': int(r['ach_punish'] or 0),
                    'points': int(r['ach_points'] or 0), 'best': val, 'ended': r['ach_ended']}
            if best is None:
                best = cand
                continue
            # order (decision Philine): points, then the best performance of the discipline,
            # then fewer punishments, then the earlier run
            if cand['points'] > best['points']:
                best = cand
            elif cand['points'] == best['points'] and task and task.is_better(cand['best'], best['best']):
                best = cand
        return best

    def decide_challenge(self, ch_id, by='auto'):
        """Write the placements, apply the rules, close the challenge."""
        ch = self._q('SELECT * FROM challenges WHERE ch_id=%s', (ch_id,), one=True)
        if not ch or ch['ch_status'] != 'open':
            return None
        field = self._challenge_field(ch_id)
        if len(field) < 2:
            self._x("UPDATE challenges SET ch_status='void', ch_decided=NOW() WHERE ch_id=%s", (ch_id,))
            return None
        task = tasktypes.get(ch['ch_action'])
        scored, missing = [], []
        for sid in field:
            res = self._challenge_result(sid, ch)
            (scored if res else missing).append((sid, res))

        def key(item):
            _sid, r = item
            g = tasktypes.GRADES.index(r['grade']) if r['grade'] in tasktypes.GRADES else 9
            b = r['best']
            # points descending, then the best performance of the discipline, then grade, then punishments
            bkey = (-(b or 0)) if (task and task.best_higher) else (b if b is not None else 1e12)
            return (-r['points'], bkey, g, r['punish'], r['ended'] or datetime.datetime.max)
        scored.sort(key=key)
        order = scored + [(sid, None) for sid, _ in missing]      # did not compete = at the back
        results = []
        for i, (sid, r) in enumerate(order, start=1):
            self._x('UPDATE challenge_entries SET ce_place=%s, ce_points=%s, ce_best=%s, ce_punish=%s, '
                    'ce_grade=%s, ce_ach=%s, ce_note=%s WHERE ce_challenge=%s AND ce_slave=%s',
                    (i, (r or {}).get('points'), (r or {}).get('best'), (r or {}).get('punish'),
                     (r or {}).get('grade'), (r or {}).get('ach'), None if r else 'nicht angetreten', ch_id, sid))
            results.append({'place': i, 'slave_id': sid, 'name': self._slave_name(sid),
                            'points': (r or {}).get('points'), 'grade': (r or {}).get('grade'),
                            'best': (r or {}).get('best'), 'punish': (r or {}).get('punish'),
                            'entered': r is not None})
        winner = order[0][0] if order and order[0][1] else None
        self._x("UPDATE challenges SET ch_winner=%s, ch_status='decided', ch_decided=NOW() WHERE ch_id=%s",
                (winner, ch_id))
        if winner:
            self._bonus(winner, BONUS_CHALLENGE, self.sc_int('bonus_challenge', 30),
                        f'Herausforderung #{ch_id} gewonnen', week=ch['ch_week'])
        # rewards and punishments by placement come from the rule set
        n = len(order)
        for e in results:
            self.apply_rules('challenge', e['slave_id'],
                             {'place': e['place'], 'last': e['place'] == n, 'count': n,
                              'entered': e['entered'], 'action': ch['ch_action'], 'target': ch['ch_target'],
                              'grade': e['grade']})
        self._emit('challenge', {'challenge': ch_id, 'action': ch['ch_action'],
                                 'action_name': (actions.get(ch['ch_action']).name if actions.get(ch['ch_action']) else ch['ch_action']),
                                 'week': ch['ch_week'], 'target': ch['ch_target'], 'by': by,
                                 'winner': winner, 'winner_name': self._slave_name(winner) if winner else None,
                                 'results': results})
        audit.central('challenge_decided', data={'challenge': ch_id, 'action': ch['ch_action'],
                                                 'winner': winner, 'results': results})
        logger.info('Logbook: Herausforderung #%s (%s) entschieden: %s', ch_id, ch['ch_action'],
                    [(e['place'], e['name']) for e in results])
        return results

    def routine_name(self, ro_id):
        """Name of a waveform for the display, '?' if it has been deleted in the meantime."""
        if not ro_id or not self.routines_enabled:
            return None
        row = self._q('SELECT ro_name FROM routines WHERE ro_id=%s', (int(ro_id),), one=True)
        return row['ro_name'] if row else '?'

    def challenge_board(self, week=None):
        """Second leaderboard (doc 14 §12.4): challenges of the week with placements."""
        week = week or week_str()
        out = []
        for ch in self._q('SELECT * FROM challenges WHERE ch_week=%s ORDER BY ch_id', (week,)) or []:
            a = actions.get(ch['ch_action'])
            t = tasktypes.get(ch['ch_action'])
            rows = self._q('SELECT e.*, s.slave_name FROM challenge_entries e JOIN slaves s ON s.slave_id=e.ce_slave '
                           'WHERE e.ce_challenge=%s ORDER BY (e.ce_place IS NULL), e.ce_place, s.slave_name',
                           (ch['ch_id'],)) or []
            out.append({
                'id': ch['ch_id'], 'week': ch['ch_week'], 'action': ch['ch_action'],
                'action_name': a.name if a else ch['ch_action'], 'target': int(ch['ch_target'] or 0),
                'unit': t.target_unit if t else 's',
                'target_text': self.target_text(ch['ch_target'], t.target_unit if t else 's'),
                'metric': (tasktypes.METRIC_LABELS.get(t.best_metric, t.best_metric) if t else None),
                'status': ch['ch_status'], 'winner': ch['ch_winner'],
                'routine': ch.get('ch_routine'), 'routine_name': self.routine_name(ch.get('ch_routine')),
                'entries': [{'place': r['ce_place'], 'slave_id': r['ce_slave'], 'name': r['slave_name'],
                             'points': r['ce_points'], 'grade': r['ce_grade'], 'best': r['ce_best'],
                             'punish': r['ce_punish'], 'note': r['ce_note']} for r in rows],
            })
        return out

    # ------------------------------------------------------------------ #
    # Reward/punishment editor (doc 14 §12.5): trigger -> condition -> effect
    TRIGGERS = {
        'challenge':       'Herausforderung entschieden',
        'weekly':          'Wochenbewertung',
        'plan_complete':   'Wochenplan vollständig',
        'plan_incomplete': 'Wochenplan unvollständig',
        'punish_threshold': 'Strafregister-Schwelle erreicht',
        'run_passed':      'Durchgang bestanden',
        'run_failed':      'Durchgang nicht bestanden',
        'capitulation':    'Kapitulation (Tag vorzeitig beendet)',
        'day_done':        'Tag regulär beendet',
        'budget_exceeded': 'Budget ausgeschöpft',
        'streak_reached':  'Serie: Meilenstein erreicht',
        'streak_broken':   'Serie gebrochen',
    }
    EFFECTS = {
        'punish':          ('Bestrafung über den Kanal', 'Stärkestufe 1..3'),
        'reward':          ('Belohnung über den Kanal', 'Stärkestufe 1..3'),
        'privilege_grant': ('Privileg erteilen', 'Schlüssel, optional :Wochen — z. B. free_stay:1'),
        'privilege_revoke': ('Privileg entziehen', 'Schlüssel'),
        'sanction_impose': ('Auflage verhängen',
                            'Schlüssel, optional :Stunden, :d (bis Tagesende), :rN (nach N bestandenen '
                            'Durchgängen) — z. B. restrained:2 oder restrained:d:r3'),
        'sanction_lift':   ('Auflage aufheben', 'Schlüssel'),
        'detention':       ('Nachsitz-Aufgabe in den Plan', 'leer = die Aufgabe des Anlasses'),
        'day_minutes':     ('Tagesdauer ändern', '+30 / -15 (relativ) oder 300 (absolut), in Minuten'),
        'points':          ('Punkte gutschreiben/abziehen', 'z. B. 20 oder -10'),
        'badge':           ('Abzeichen verleihen', 'Schlüssel aus der Abzeichenliste'),
        'dayform':         ('Tagesform setzen', 'easy / normal / strict, optional :+1 für morgen — z. B. strict:+1. '
                                                'Gilt für den einen Tag und fällt dann auf normal.'),
    }
    CONDITIONS = {
        '':          'immer',
        'place=1':   'Platz 1',
        'place=2':   'Platz 2',
        'place>=3':  'Platz 3 oder schlechter',
        'last':      'letzter Platz',
        'entered=0': 'nicht angetreten',
        'rank<=3':   'Rang 3 oder niedriger',
        'rank>=8':   'Rang 8 oder höher',
        'grade=A':   'Note A',
        'key=punish':   'Budget: Bestrafungen',
        'key=reward':   'Budget: Belohnungen',
        'key=activity': 'Budget: Durchgänge',
        'period=day':   'Budget je Tag',
        'period=week':  'Budget je Woche',
        'n>=2':         'Serie: mindestens 2',
        'n>=3':         'Serie: mindestens 3',
        'n>=5':         'Serie: mindestens 5',
        'n>=7':         'Serie: mindestens 7',
        'n>=10':        'Serie: mindestens 10',
    }
    # Time conditions (doc 44 §4): appended to any condition with '&' — the
    # rule then holds only when both do. Evaluated against the clock of the
    # central unit at the moment the trigger fires.
    TIME_CONDITIONS = {
        '':                 'zu jeder Zeit',
        'time>=22:00':      'nach 22:00',
        'time>=20:00':      'nach 20:00',
        'time>=18:00':      'nach 18:00',
        'time<08:00':       'vor 8:00',
        'time<10:00':       'vor 10:00',
        'time<12:00':       'vormittags (vor 12:00)',
        'time>=12:00':      'nachmittags (ab 12:00)',
        'weekday=sat,sun':  'am Wochenende',
        'weekday=mon-fri':  'werktags',
        'weekday=mon':      'montags',
        'weekday=fri':      'freitags',
        'weekday=sun':      'sonntags',
    }
    WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')

    # ---------------------------------------------------------------- #
    # WHICH CONDITION CAN EVER MATCH WHICH TRIGGER (project doc 58 §8)
    #
    # FINDING 2026-09-17: the editor offered the full cross product, twelve
    # triggers by twenty-two conditions, and `valid_cond()` only asked whether
    # the condition stood in the table at all. "Day finished regularly" plus
    # "place 1" saved without a murmur; `_cond_ok()` then returned False
    # forever, WITHOUT a log line - the warning only fires for a condition that
    # matches no pattern at all. The rule sat in the list, looked configured
    # and never did anything.
    #
    # The truth is not a matter of taste: a condition can only match if the
    # trigger's context carries the key it reads. What follows is read off the
    # call sites of `apply_rules()`, not guessed.
    #
    # `plan_complete` has TWO call sites with different contexts - once out of
    # a finished run (grade), once out of the weekly review (place/rank). It
    # therefore permits the union of both; a condition that only one of the two
    # paths can satisfy is still reachable.
    COND_FOR = {
        'challenge':        ('place', 'last', 'entered', 'grade'),
        'weekly':           ('place', 'last', 'entered'),
        'plan_complete':    ('place', 'last', 'entered', 'grade'),
        'plan_incomplete':  ('place', 'last', 'entered'),
        'punish_threshold': (),
        'run_passed':       ('grade',),
        'run_failed':       ('grade',),
        'capitulation':     (),
        'day_done':         (),
        'budget_exceeded':  ('key', 'period'),
        'streak_reached':   ('n', 'streak'),
        'streak_broken':    ('n', 'streak'),
    }
    # These do not come out of the context but out of the database, so they hold
    # for every trigger. The time conditions are a select of their own and are
    # not covered here.
    COND_ANY = ('rank',)

    @classmethod
    def cond_family(cls, cond):
        """'place>=3' -> 'place', 'last' -> 'last', '' -> None. The family is what
        `_cond_ok()` branches on, so it is what decides reachability."""
        c = (cond or '').strip()
        if not c:
            return None
        for fam in ('place', 'entered', 'rank', 'key', 'period', 'streak', 'grade'):
            if c.startswith(fam):
                return fam
        if c == 'last':
            return 'last'
        if c.startswith('n>='):
            return 'n'
        return None                       # unknown: not accused, only not helped

    @classmethod
    def cond_fits(cls, trigger, cond):
        """Can this condition ever match this trigger? An unknown trigger counts as
        fitting - the editor must not accuse something it does not know."""
        base, _when = cls.split_cond(cond)
        fam = cls.cond_family(base)
        if fam is None:
            return True
        if trigger not in cls.COND_FOR:
            return True
        return fam in cls.COND_ANY or fam in cls.COND_FOR[trigger]

    # A sentence for every entry of the two selects (doc 58 §5). The help was
    # not missing as TEXT everywhere - effects and block kinds carry theirs and
    # show it - it was missing exactly here, at the two fields one has to fill
    # in first. German is the master.
    TRIGGER_HELP = {
        'challenge':        'Eine Herausforderung ist entschieden, die Platzierungen stehen fest.',
        'weekly':           'Die Wochenbewertung ist gelaufen: Rang, Platz und Punkte der Woche stehen.',
        'plan_complete':    'Der Wochenplan ist vollständig — durch den letzten Durchgang oder bei der Wochenbewertung.',
        'plan_incomplete':  'Bei der Wochenbewertung war der Wochenplan nicht vollständig.',
        'punish_threshold': 'Im Strafregister der Woche ist die eingestellte Schwelle erreicht.',
        'run_passed':       'Ein Durchgang wurde bestanden.',
        'run_failed':       'Ein Durchgang wurde nicht bestanden.',
        'capitulation':     'Sie hat den Tag vorzeitig beendet — die Marke ein zweites Mal aufgelegt.',
        'day_done':         'Der Tag ist regulär zu Ende gegangen.',
        'budget_exceeded':  'Ein Budget ist ausgeschöpft: Bestrafungen, Belohnungen oder Durchgänge.',
        'streak_reached':   'Eine Serie hat einen Meilenstein erreicht.',
        'streak_broken':    'Eine Serie ist gerissen.',
    }
    COND_HELP = {
        '':           'Die Regel greift bei jedem Anlass dieser Art.',
        'place=1':    'Erster Platz.',
        'place=2':    'Zweiter Platz.',
        'place>=3':   'Dritter Platz oder schlechter.',
        'last':       'Letzter Platz des Feldes.',
        'entered=0':  'Sie ist gar nicht angetreten.',
        'rank<=3':    'Ihr Rang ist 3 oder niedriger — je kleiner die Zahl, desto höher der Rang.',
        'rank>=8':    'Ihr Rang ist 8 oder höher, also weit unten.',
        'grade=A':    'Der Durchgang wurde mit A bewertet.',
        'key=punish':   'Es war das Budget für Bestrafungen.',
        'key=reward':   'Es war das Budget für Belohnungen.',
        'key=activity': 'Es war ein Budget für Durchgänge — auch das einer einzelnen Aufgabe.',
        'period=day':   'Das Tagesbudget, nicht das der Woche.',
        'period=week':  'Das Wochenbudget, nicht das des Tages.',
        'n>=2':       'Die Serie stand bei mindestens 2.',
        'n>=3':       'Die Serie stand bei mindestens 3.',
        'n>=5':       'Die Serie stand bei mindestens 5.',
        'n>=7':       'Die Serie stand bei mindestens 7.',
        'n>=10':      'Die Serie stand bei mindestens 10.',
    }
    COND_HELP_STREAK = 'Nur diese eine Serie, keine andere.'

    def cond_help(self):
        """COND_HELP plus a sentence for every streak key, which the fixed table
        cannot know (same reason as in `conditions()`)."""
        out = dict(self.COND_HELP)
        for d in self.streaks.definitions():
            out['streak=' + d['st_key']] = self.COND_HELP_STREAK
        return out

    def conditions(self):
        """CONDITIONS plus one 'streak=<key>' entry per streak definition (doc 44 §3) —
        the fixed table cannot know the keys, the web needs them in the list."""
        out = dict(self.CONDITIONS)
        for d in self.streaks.definitions():
            out['streak=' + d['st_key']] = 'Serie: ' + d['st_name']
        return out

    def valid_cond(self, cond):
        """Is this (possibly combined) condition one the rule set knows?"""
        base, when = self.split_cond(cond)
        return base in self.conditions() and when in self.TIME_CONDITIONS

    def cond_text(self, cond):
        """Human text for a stored condition, both parts translated."""
        base, when = self.split_cond(cond)
        names = i18n.d(self.conditions())
        whens = i18n.d(self.TIME_CONDITIONS)
        t = names.get(base, base or i18n._('immer'))
        if when:
            t += ' · ' + whens.get(when, when)
        return t

    def rules(self, trigger=None):
        if trigger:
            return self._q('SELECT * FROM rules WHERE ru_trigger=%s ORDER BY ru_pos, ru_id', (trigger,)) or []
        return self._q('SELECT * FROM rules ORDER BY ru_trigger, ru_pos, ru_id') or []

    @classmethod
    def split_cond(cls, cond):
        """'place=1&time>=22:00' -> ('place=1', 'time>=22:00'); either part may be empty."""
        parts = [p.strip() for p in str(cond or '').split('&')]
        base = [p for p in parts if p and not p.startswith(('time', 'weekday'))]
        when = [p for p in parts if p.startswith(('time', 'weekday'))]
        return (base[0] if base else ''), (when[0] if when else '')

    @classmethod
    def join_cond(cls, base, when):
        return '&'.join(p for p in (str(base or '').strip(), str(when or '').strip()) if p)

    def _time_ok(self, cond, now=None):
        """time>=HH:MM, time<HH:MM, weekday=sat,sun, weekday=mon-fri."""
        now = now or datetime.datetime.now()
        if cond.startswith('time>='):
            h, m = cond[6:].split(':')
            return (now.hour, now.minute) >= (int(h), int(m))
        if cond.startswith('time<'):
            h, m = cond[5:].split(':')
            return (now.hour, now.minute) < (int(h), int(m))
        if cond.startswith('weekday='):
            spec = cond[8:]
            days = set()
            for part in spec.split(','):
                if '-' in part:
                    a, b = part.split('-', 1)
                    ia, ib = self.WEEKDAYS.index(a), self.WEEKDAYS.index(b)
                    days.update(self.WEEKDAYS[ia:ib + 1])
                else:
                    days.add(part)
            return self.WEEKDAYS[now.weekday()] in days
        raise ValueError(cond)

    def _cond_ok(self, cond, ctx, slave_id):
        cond = (cond or '').strip()
        if not cond:
            return True
        if '&' in cond or cond.startswith(('time', 'weekday')):
            # combined: every part has to hold (doc 44 §4)
            parts = [p.strip() for p in cond.split('&') if p.strip()]
            try:
                return all((self._time_ok(p) if p.startswith(('time', 'weekday')) else self._cond_ok(p, ctx, slave_id))
                           for p in parts)
            except (ValueError, IndexError):
                logger.warning('rules: unbekannte Zeitbedingung %r', cond)
                return False
        try:
            if cond.startswith('place'):
                place = ctx.get('place')
                if place is None:
                    return False
                if cond.startswith('place>='):
                    return int(place) >= int(cond[7:])
                if cond.startswith('place<='):
                    return int(place) <= int(cond[7:])
                return int(place) == int(cond.split('=', 1)[1])
            if cond == 'last':
                return bool(ctx.get('last'))
            if cond.startswith('entered='):
                return bool(ctx.get('entered')) == bool(int(cond.split('=', 1)[1]))
            if cond.startswith('rank'):
                rank, _ = self.rank_of(slave_id)
                if cond.startswith('rank<='):
                    return rank <= int(cond[6:])
                if cond.startswith('rank>='):
                    return rank >= int(cond[6:])
                return rank == int(cond.split('=', 1)[1])
            if cond.startswith('key='):
                # budget_exceeded: 'key=activity' also matches 'activity:<ACTION>'
                want, have = cond[4:], str(ctx.get('key') or '')
                return have == want or have.startswith(want + ':')
            if cond.startswith('period='):
                return str(ctx.get('period') or '') == cond[7:]
            if cond.startswith('streak='):
                # streak_reached / streak_broken: only this definition
                return str(ctx.get('streak') or '') == cond[7:]
            if cond.startswith('n>='):
                return ctx.get('n') is not None and int(ctx['n']) >= int(cond[3:])
            if cond.startswith('grade'):
                g = (ctx.get('grade') or '').upper()
                if not g:
                    return False
                if cond.startswith('grade>='):
                    return g >= cond[7:].upper()
                if cond.startswith('grade<='):
                    return g <= cond[7:].upper()
                return g == cond.split('=', 1)[1].upper()
        except (TypeError, ValueError):
            return False
        logger.warning('rules: unbekannte Bedingung %r', cond)
        return False

    def apply_rules(self, trigger, slave_id, ctx=None, slave=None):
        """Execute all matching rules of a trigger. Returns the list of effects."""
        if not self.day_enabled:
            return []
        pa = self.pauses.active(slave_id)
        if pa is not None:
            # doc 44 §2: no rule fires during a pause. Logged, not audited per
            # trigger — a paused week would otherwise fill the audit with silence.
            logger.info('rules: %s for slave %s skipped - paused until %s', trigger, slave_id, pa['pa_to'])
            return []
        ctx = ctx or {}
        done = []
        for r in self.rules(trigger):
            if not int(r['ru_enabled'] or 0):
                continue
            # A rule whose condition can never match this trigger is not a
            # near miss, it is dead (doc 58 §8). Said once per rule, so a
            # running installation shows it in the log and not only in the
            # editor - and only once, because a trigger that fires every day
            # would otherwise fill the log with the same sentence.
            if not self.cond_fits(trigger, r['ru_cond']):
                if r['ru_id'] not in self._dead_rules:
                    self._dead_rules.add(r['ru_id'])
                    logger.warning("rules: Regel %s (%s) kann bei '%s' nie zutreffen - Bedingung '%s' "
                                   'gehoert zu einem anderen Anlass', r['ru_id'], r['ru_effect'],
                                   trigger, r['ru_cond'])
                continue
            if not self._cond_ok(r['ru_cond'], ctx, slave_id):
                continue
            eff = self._apply_effect(slave_id, r['ru_effect'], r['ru_param'], trigger, ctx, slave)
            if eff:
                done.append(eff)
        if done:
            audit.central('rules_applied', slave_id=slave_id, data={'trigger': trigger, 'ctx': ctx, 'effects': done})
            self._emit('rules', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                 'trigger': trigger, 'trigger_name': self.TRIGGERS.get(trigger, trigger),
                                 'effects': done})
        return done

    def _apply_effect(self, slave_id, effect, param, reason, ctx, slave=None):
        param = (param or '').strip()
        try:
            if effect in ('punish', 'reward'):
                level = int(param or 1)
                if slave is None:
                    # nobody there who could carry it out: remember it until the next day start
                    self._x('INSERT INTO pending_effects (pe_slave, pe_effect, pe_param, pe_reason) VALUES (%s,%s,%s,%s)',
                            (slave_id, effect, str(level), reason[:64]))
                    return {'effect': effect, 'param': level, 'pending': True}
                if effect == 'punish':
                    self.punish(slave_id, level, 'any', reason, 'rule')
                else:
                    self.reward(slave_id, level, 'any', reason, 'rule')
                return {'effect': effect, 'param': level}
            if effect == 'sanction_impose':
                # param: key[:hours][:d][:rNN]  e.g. "restrained:2"
                #   :d   additionally ends with the day
                #   :rNN additionally ends after NN passed runs
                parts = [x.strip() for x in param.split(':')]
                key = parts[0]
                hours = until_day = runs = None
                for x in parts[1:]:
                    if x == 'd':
                        until_day = True
                    elif x.lower().startswith('r') and x[1:].isdigit():
                        runs = int(x[1:])
                    elif x.replace('.', '', 1).isdigit():
                        hours = float(x)
                if self.impose_sanction(slave_id, key, by='rule:' + reason,
                                        reason=self.TRIGGERS.get(reason, reason),
                                        hours=hours, until_day=bool(until_day), runs=runs):
                    return {'effect': effect, 'param': param}
                return None
            if effect == 'sanction_lift':
                self.lift_sanction(slave_id, param, by='rule:' + reason)
                return {'effect': effect, 'param': param}
            if effect == 'privilege_grant':
                key, _, weeks = param.partition(':')
                if self.grant_privilege(slave_id, key.strip(), by='rule:' + reason,
                                        weeks=int(weeks) if weeks.strip().isdigit() else None):
                    return {'effect': effect, 'param': param}
                return None
            if effect == 'privilege_revoke':
                self.revoke_privilege(slave_id, param, by='rule:' + reason)
                return {'effect': effect, 'param': param}
            if effect == 'detention':
                action = param or ctx.get('action')
                target = ctx.get('target')
                nxt = next_week(week_str())
                if action and target:
                    self._x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, "
                            "wt_kind, wt_status, wt_by) VALUES (%s,%s,%s,%s,%s,'detention','open',%s)",
                            (slave_id, nxt, action, int(target), self.default_max_punish(), 'rule:' + reason))
                else:
                    self._detention_last(slave_id, week_str())
                return {'effect': effect, 'param': action or 'letzte Aufgabe'}
            if effect == 'day_minutes':
                return self._effect_day_minutes(slave_id, param, reason)
            if effect == 'points':
                pts = int(param or 0)
                if pts:
                    self._bonus(slave_id, 'BONUS_RULE', pts, f'Regel: {self.TRIGGERS.get(reason, reason)}')
                return {'effect': effect, 'param': pts}
            if effect == 'badge':
                if self.grant_badge(slave_id, param):
                    return {'effect': effect, 'param': param}
                return None
            if effect == 'dayform':
                # 'strict' = today, 'strict:+1' = tomorrow (doc 44 §5). A rule sets
                # the form for one day; the audit names the rule as the author.
                form, _, when = param.partition(':')
                form = form.strip().lower()
                if form not in dayformmod.FORMS:
                    raise ValueError(f'dayform {param!r}')
                day = datetime.date.today() + datetime.timedelta(days=(1 if when.strip() in ('+1', '1', 'morgen', 'tomorrow') else 0))
                if not self.dayform.set(slave_id, form, 'rule:' + reason, reason=self.TRIGGERS.get(reason, reason), day=day):
                    return None
                self._emit('dayform', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'form': form,
                                       'day': day.isoformat(), 'by': 'rule:' + reason})
                return {'effect': effect, 'param': param, 'day': day.isoformat()}
        except (TypeError, ValueError) as e:
            logger.error('rules: Wirkung %s(%r) fehlgeschlagen: %s', effect, param, e)
            return None
        logger.warning('rules: unbekannte Wirkung %r', effect)
        return None

    def _effect_day_minutes(self, slave_id, param, reason):
        """Change the day length per slave — capped at [safety] day_minutes_max."""
        cur = self.day_minutes(slave_id)
        if param.startswith(('+', '-')):
            want = cur + int(param)
        else:
            want = int(param)
        hard = int(self.limits['day_minutes_max'])
        want = max(15, min(want, hard))
        self._x('INSERT INTO slave_settings (ss_slave, ss_day_minutes, ss_by) VALUES (%s,%s,%s) '
                'ON DUPLICATE KEY UPDATE ss_day_minutes=VALUES(ss_day_minutes), ss_by=VALUES(ss_by)',
                (slave_id, want, 'rule:' + reason))
        return {'effect': 'day_minutes', 'param': param, 'from': cur, 'to': want,
                'capped': want != (cur + int(param) if param.startswith(('+', '-')) else int(param))}

    def day_minutes(self, slave_id):
        r = self._q('SELECT ss_day_minutes FROM slave_settings WHERE ss_slave=%s', (slave_id,), one=True)
        hard = int(self.limits['day_minutes_max'])
        if not r:
            return min(int(self.limits['day_minutes_default']), hard)
        return max(5, min(int(r['ss_day_minutes']), hard))

    def apply_pending(self, slave_id, slave=None):
        """Deliver waiting effects (channel) at the start of the day."""
        rows = self._q('SELECT * FROM pending_effects WHERE pe_slave=%s AND pe_applied IS NULL ORDER BY pe_id',
                       (slave_id,)) or []
        for r in rows:
            self._x('UPDATE pending_effects SET pe_applied=NOW() WHERE pe_id=%s', (r['pe_id'],))
            self._apply_effect(slave_id, r['pe_effect'], r['pe_param'], r['pe_reason'], {}, slave)
        if rows:
            logger.info('Logbook: %d wartende Wirkung(en) für Sklaven %s zugestellt', len(rows), slave_id)
        return len(rows)

    # ------------------------------------------------------------------ #
    # Punishment/reward channel (the publisher is only the central unit)
    def punish(self, slave_id, level=1, kind='any', reason='', source='central', run=None, user=None, _retries=0):
        """Request a punishment over the channel.

        Budgets (doc 44 §1) decide: an exhausted budget rejects it — the [safety]
        day limit is one of those budgets and always applies; inside the minimum
        pause the punishment is queued and made up for after the pause
        (``on_gap = queue``, decision Philine 2026-09-10) or lapses (``drop``).
        Returns the channel id, 'queued' or None."""
        if self.publish_punish is None:
            return None
        if self._paused_refuse('punish', slave_id, reason):
            return None
        now = time.time()
        day = datetime.date.today().isoformat()
        hit = self._budget_hit('punish', slave_id)
        if hit is not None:
            audit.central('punish_rejected', slave_id=slave_id,
                          data={'reason': reason, 'why': 'budget ' + self.budgets.describe(hit)})
            logger.warning('Logbook: punish for slave %s rejected (%s)', slave_id, self.budgets.describe(hit))
            self._emit('warning', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                   'text': self._budget_text(hit)})
            return None
        # day form (doc 44 §5): strict one level up, easy one down — inside 1..3
        level = self.dayform.channel_level(self.dayform.of(slave_id), level)
        gap, on_gap = self.budgets.gap('punish', slave_id)
        last = self.channel_last.get(slave_id, 0)
        if gap and now - last < gap:
            if on_gap == 'drop':
                audit.central('punish_dropped', slave_id=slave_id,
                              data={'reason': reason, 'why': f'cooldown {gap}s drop', 'run': run.id if run else None})
                logger.info('Logbook: punish for slave %s dropped (cooldown %ds)', slave_id, gap)
                return None
            return self._enqueue_punish(slave_id, level, kind, reason, source, run, user, last + gap, _retries, 'gap')
        cid = self.publish_punish(slave_id, int(level), kind or 'any', reason or '', source or 'central',
                                  warn=self.warn_for(slave_id),
                                  estim_ceiling=self.estim_ceiling(slave_id),
                                  estim_pct=self.estim_pct(slave_id, level, 'punish'),
                                  estim_profile=self.estim_profile(slave_id, 'punish'))
        if cid is None:
            return None
        self.channel_last[slave_id] = now
        self.channel_day[(slave_id, day)] = self.channel_day.get((slave_id, day), 0) + 1
        self.pending_cids[int(cid)] = {'run': run, 'slave_id': slave_id, 't': now, 'reason': reason, 'level': level,
                                       'kind': kind, 'source': source, 'user': user, 'retries': _retries}
        # forget old entries (without an execution message)
        for k in [k for k, v in self.pending_cids.items() if now - v['t'] > 120]:
            self.pending_cids.pop(k, None)
        audit.log('central', 'channel', 'punish', None, slave_id,
                  {'level': level, 'kind': kind, 'reason': reason, 'source': source, 'cid': cid,
                   'run': run.id if run else None, 'retry': _retries}, user)
        return cid

    # ------------------------------------------------------------------ #
    # Budgets (doc 44 §1) — counters out of the audit log, so they survive a
    # restart of the central unit (Philine 2026-09-10); the in-memory day counter
    # of the punishment channel is only the fallback when the DB does not answer.
    def _channel_count(self, slave_id, what, period):
        """Channel messages of one kind sent to the slave in the current period
        according to the audit log (None = DB error)."""
        since = budgetsmod.period_start(period)
        r = self._q("SELECT COUNT(*) AS n FROM audit_log WHERE al_slave_id=%s AND al_kind='channel' AND al_action=%s "
                    "AND al_ts >= %s", (slave_id, what, since), one=True)
        return int(r['n']) if r else None

    def _channel_count_today(self, slave_id):
        return self._channel_count(slave_id, 'punish', 'day')

    def _own_punish(self, slave_id, device, ev):
        """A device punished ON ITS OWN — count it, and let the others join in.

        THE FINDING (Philine 2026-09-16). The punishment channel has always
        reached every assigned device; what never reached it was a punishment
        the COLLAR decided for itself. PET, V-Cage, sleep deprivation and
        statue call `schedulePulse()` locally, and the E-Stim bridge never
        heard about it. One violation, one device.

        It also never touched a budget. The day limit from `[safety]` applies
        to the channel, so the mode punishments ran beside it — in an hour of
        PET, dozens of them.

        HOW THE COLLAR IS TOLD APART FROM THE CHANNEL: the `shock` event
        carries `source`. A punishment from the channel says "channel" and
        brings the `cid` of the central unit; one from a mode says "pet",
        "cage", "sleep" or "statue" and has no cid. That distinction is in the
        firmware since 2.0 — it only had nobody reading it.

        WHY THE MIRROR CANNOT HIT THE ORIGINATOR: a channel message carries a
        `kind`, and a device only reacts to its own (`kindMatches` in the
        firmware). The collar listens for shock/vibe/beep, the bridge for
        estim. The mirror is therefore sent with the kinds of the OTHER
        devices — the collar does not match them and does not punish twice.
        No firmware change, and no new rule the devices would have to learn.
        """
        if ev.get('source') in (None, '', 'channel') or ev.get('cid') is not None:
            return                             # came from the channel: already counted
        if self.publish_punish is None or not slave_id:
            return
        reason = str(ev.get('source'))
        level = int(ev.get('level') or 0)
        # COUNTED THE SAME WAY as a channel punishment, and in the same place:
        # the budgets read the audit log, so a row of the same shape is all it
        # takes for the ceiling to see it. `by` says who decided — the counter
        # does not care, a person reading the log does.
        audit.log('central', 'channel', 'punish', device, slave_id,
                  {'level': level, 'kind': 'device', 'reason': reason,
                   'source': 'device', 'by': device}, None)
        self.channel_day[(slave_id, datetime.date.today().isoformat())] = \
            self.channel_day.get((slave_id, datetime.date.today().isoformat()), 0) + 1

        # Mirroring is what the budget stops, not the device (decision Philine
        # 2026-09-16). The collar keeps punishing in its mode — it knows no
        # budget, and telling it would need a firmware change and a flash
        # window. So the limit bites on the OTHER devices and on everything
        # the central unit sends itself; it does not reach into a running mode.
        # That is half a limit, and it is the half that was chosen knowingly.
        hit = self._budget_hit('punish', slave_id)
        if hit is not None:
            logger.info('Logbook: own punishment of %s not mirrored (%s)',
                        (device or '?')[:8], self.budgets.describe(hit))
            return
        if self._paused_refuse('punish', slave_id, reason):
            return
        kinds = self.punish_kinds_of(slave_id, device) if self.punish_kinds_of else set()
        for kind in sorted(kinds):
            self.publish_punish(slave_id, max(1, min(3, level or 1)), kind,
                                reason, 'device',
                                estim_ceiling=self.estim_ceiling(slave_id),
                                estim_pct=self.estim_pct(slave_id, level or 1, 'punish'),
                                estim_profile=self.estim_profile(slave_id, 'punish'))
            logger.info("Logbook: %s punished on its own (%s) - mirrored as '%s'",
                        (device or '?')[:8], reason, kind)

    def _budget_hit(self, key, slave_id):
        """The exhausted budget for this key, or None. Raises ``budget_exceeded``
        once per window — the rule set may escalate on it, it is not poked on
        every further refused attempt."""
        day = datetime.date.today().isoformat()

        def counter(period):
            n = self._channel_count(slave_id, key, period)
            if n is None:                    # DB down: the in-memory counter, punish only
                n = self.channel_day.get((slave_id, day), 0) if key == 'punish' else 0
            return n

        hit = self.budgets.exceeded(key, slave_id, counter)
        if hit is not None and self.budgets.fire_once(slave_id, hit.key, hit.period):
            self.apply_rules('budget_exceeded', slave_id,
                             {'key': hit.key, 'period': hit.period, 'max': hit.max_count, 'source': hit.source})
        return hit

    def _paused_refuse(self, what, slave_id, reason):
        """doc 44 §2: during a pause no budget runs — the channel refuses, visibly."""
        pa = self.pauses.active(slave_id)
        if pa is None:
            return False
        audit.central(what + '_rejected', slave_id=slave_id,
                      data={'reason': reason, 'why': 'paused until %s' % pa['pa_to']})
        logger.info('Logbook: %s for slave %s rejected (paused until %s)', what, slave_id, pa['pa_to'])
        self._emit('warning', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                               'text': i18n._('Pause bis {until} — kein Kanal', until=pausesmod.Pauses.describe(pa))})
        return True

    def _budget_text(self, hit):
        what = {'punish': i18n._('Bestrafungen'), 'reward': i18n._('Belohnungen')}.get(hit.key, hit.key)
        per = i18n._('heute') if hit.period == 'day' else i18n._('diese Woche')
        return i18n._('Budget ausgeschöpft: {what} {per} ({n})', what=what, per=per, n=int(hit.max_count))

    def _pause_info(self, slave_id):
        """For web and display: the running pause, or None."""
        pa = self.pauses.active(slave_id)
        if pa is None:
            return None
        return {'id': pa['pa_id'], 'from': str(pa['pa_from']), 'to': str(pa['pa_to']),
                'reason': pa.get('pa_reason') or '', 'all': int(pa['pa_slave'] or 0) == 0,
                'text': pausesmod.Pauses.describe(pa)}

    def budget_status(self, slave_id):
        """For the participant page: every budget with a count, used/max.
        [{'key','period','used','max','gap','on_gap','source'}]"""
        out = []
        seen = set()
        for key in ('punish', 'reward'):
            for r in self.budgets.applicable(key, slave_id):
                if not r.max_count or (r.key, r.period, r.slave, r.source) in seen:
                    continue
                seen.add((r.key, r.period, r.slave, r.source))
                used = self._channel_count(slave_id, key, r.period)
                out.append({'key': r.key, 'period': r.period, 'used': used if used is not None else 0,
                            'max': int(r.max_count), 'gap': r.min_gap_s, 'on_gap': r.on_gap,
                            'source': r.source, 'slave': r.slave})
        return out

    def activity_cooling(self, slave_id, action):
        """Is the task in its cooldown for this slave (doc 44 §1)? Returns the
        seconds still to wait, 0 when it may start."""
        gap, _ = self.budgets.gap(budgetsmod.ACTIVITY_PREFIX + action, slave_id)
        if not gap:
            return 0
        r = self._q("SELECT MAX(ach_started) AS t FROM achievements WHERE ach_slave=%s AND ach_action=%s "
                    "AND ach_status IN ('done','failed','running')", (slave_id, action), one=True)
        if not r or not r['t']:
            return 0
        t = r['t']
        if isinstance(t, str):
            t = datetime.datetime.fromisoformat(t)
        left = gap - (datetime.datetime.now() - t).total_seconds()
        return int(left) if left > 0 else 0

    def _enqueue_punish(self, slave_id, level, kind, reason, source, run, user, due, retries, why, what='punish'):
        """Defer a channel message (minimum pause or repeat after busy).
        At most channel_queue_max per slave; beyond that it is discarded (audit).
        Since 2.3 the queue also carries rewards (``what='reward'``, budgets with
        ``on_gap = queue``, doc 44 §1)."""
        qmax = self.sc_int('channel_queue_max', 10)
        if qmax and sum(1 for q in self.channel_queue if q['slave_id'] == slave_id) >= qmax:
            audit.central(what + '_rejected', slave_id=slave_id, data={'reason': reason, 'why': f'queue full ({qmax})'})
            logger.warning('Logbook: %s for slave %s dropped (queue full %d)', what, slave_id, qmax)
            return None
        self.channel_queue.append({'slave_id': slave_id, 'level': level, 'kind': kind, 'reason': reason, 'source': source,
                                   'run': run, 'user': user, 'due': due, 'retries': retries, 'queued_at': time.time(),
                                   'what': what})
        audit.central(what + '_queued', slave_id=slave_id, data={'reason': reason, 'why': why, 'due_in_s': round(due - time.time(), 1),
                                                                 'run': run.id if run else None, 'retry': retries})
        logger.info('Logbook: %s for slave %s queued (%s, due in %.1fs)', what, slave_id, why, due - time.time())
        return 'queued'

    def _pump_channel(self, now):
        """Send due entries of the queue (one per slave per round, the order is kept)."""
        if not self.channel_queue:
            return
        done_slaves = set()
        for q in sorted(self.channel_queue, key=lambda x: x['due']):
            if q['due'] > now or q['slave_id'] in done_slaves:
                continue
            self.channel_queue.remove(q)
            done_slaves.add(q['slave_id'])
            run = q['run']
            if run is not None and run.finished and run.status == 'aborted':
                # run aborted (logout, stop, device gone): the punishment is dropped.
                # A regularly finished run still gets it (the violation was real).
                audit.central('punish_dropped', slave_id=q['slave_id'], data={'reason': q['reason'], 'why': 'run aborted', 'run': run.id})
                continue
            if q.get('what') == 'reward':
                self.reward(q['slave_id'], q['level'], q['kind'], q['reason'], q['source'], user=q['user'])
                continue
            self.punish(q['slave_id'], q['level'], q['kind'], q['reason'], q['source'], run=run, user=q['user'], _retries=q['retries'])

    def _open_channel(self, run):
        """Does the run still have channel punishments that have not been executed (in flight or queued)?"""
        return any(v.get('run') is run for v in self.pending_cids.values()) or any(q['run'] is run for q in self.channel_queue)

    def _purge_channel(self, run):
        self.channel_queue = [q for q in self.channel_queue if q['run'] is not run]

    def reward(self, slave_id, level=1, kind='any', reason='', source='central', user=None):
        if self.publish_reward is None:
            return None
        if self._paused_refuse('reward', slave_id, reason):
            return None
        # Sanction "no rewards" (doc 26): withhold - but VISIBLY.
        # A reward that quietly disappears looks like a fault, and
        # then the supervisor searches in the wrong place.
        if self.has_sanction(slave_id, 'no_reward'):
            audit.central('reward_withheld', slave_id=slave_id,
                          data={'level': level, 'kind': kind, 'reason': reason,
                                'source': source, 'why': 'sanction no_reward'})
            logger.info('Logbook: reward for slave %s withheld (sanction no_reward)', slave_id)
            self._emit('warning', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                   'text': i18n._('Belohnung zurückgehalten — Auflage „Keine Belohnungen"')})
            return None
        # Budgets and cooldown (doc 44 §1). A reward has no [safety] ceiling —
        # without a row nothing here limits it, exactly as before 2.3.
        hit = self._budget_hit('reward', slave_id)
        if hit is not None:
            audit.central('reward_rejected', slave_id=slave_id,
                          data={'level': level, 'kind': kind, 'reason': reason, 'source': source,
                                'why': 'budget ' + self.budgets.describe(hit)})
            logger.info('Logbook: reward for slave %s rejected (%s)', slave_id, self.budgets.describe(hit))
            self._emit('warning', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                   'text': self._budget_text(hit)})
            return None
        now = time.time()
        gap, on_gap = self.budgets.gap('reward', slave_id)
        last = self.reward_last.get(slave_id, 0)
        if gap and now - last < gap:
            if on_gap == 'queue':
                return self._enqueue_punish(slave_id, level, kind, reason, source, None, user, last + gap, 0, 'gap',
                                            what='reward')
            # drop — visibly, like the withheld reward above
            audit.central('reward_dropped', slave_id=slave_id,
                          data={'level': level, 'kind': kind, 'reason': reason, 'source': source,
                                'why': f'cooldown {gap}s drop'})
            logger.info('Logbook: reward for slave %s dropped (cooldown %ds)', slave_id, gap)
            self._emit('warning', {'slave_id': slave_id, 'name': self._slave_name(slave_id),
                                   'text': i18n._('Belohnung verfallen — Abstand {s} s nicht eingehalten', s=gap)})
            return None
        cid = self.publish_reward(slave_id, int(level), kind or 'any', reason or '', source or 'central',
                                  estim_ceiling=self.estim_ceiling(slave_id),
                                  estim_pct=self.estim_pct(slave_id, level, 'reward'),
                                  estim_profile=self.estim_profile(slave_id, 'reward'))
        if cid is not None:
            self.reward_last[slave_id] = now
        audit.log('central', 'channel', 'reward', None, slave_id,
                  {'level': level, 'kind': kind, 'reason': reason, 'source': source, 'cid': cid}, user)
        self._emit('reward', {'slave_id': slave_id, 'name': self._slave_name(slave_id), 'level': level, 'kind': kind, 'reason': reason})
        return cid

    # ------------------------------------------------------------------ #
    # Weekly review, plan proposal, activation
    def tick(self, now=None):
        """Every 60 s from the main loop: change of week -> review of the previous week,
        activation of the proposals; Sunday -> plan proposal for the next week."""
        if not self.enabled:
            return
        now = now or time.time()
        if now - self._last_tick < 60:
            return
        self._last_tick = now
        try:
            self.scenarios.tick()                 # doc 44 §7: end what has run past its date
            cur = week_str()
            last = self.sc_str('last_review_week', None)
            if last is None:
                self.set_scoring('last_review_week', prev_week(cur))   # first commissioning: review nothing
            elif last != prev_week(cur) and last < prev_week(cur):
                # review all missed weeks one after the other
                w = next_week(last)
                while w <= prev_week(cur):
                    self.review_week(w)
                    w = next_week(w)
                self.set_scoring('last_review_week', prev_week(cur))
                if self.sc_int('auto_activate', 1):
                    self.activate_week(cur)      # only at the change of week (decision Philine 2026-09-10):
                                                  # proposals of the current week wait for "confirm"
            if self.sc_int('auto_plan', 1) and datetime.date.today().weekday() == 6:
                nxt = next_week(cur)
                if self.sc_str('last_proposal_week', '') != nxt:
                    self.propose_week(nxt)
                    self.set_scoring('last_proposal_week', nxt)
        except Exception as e:  # noqa: BLE001 - the logbook must not stop the installation
            logger.error('logbook tick: %s', e, exc_info=True)

    def activate_week(self, week):
        n = self._x("UPDATE weekly_tasks SET wt_status='open' WHERE wt_week=%s AND wt_status='proposed'", (week,))
        return n

    def _week_bests(self, week):
        """Per action: the set of slaves with the best relative result of the week
        (only if >= 2 slaves have done the task)."""
        rows = self._q("SELECT ach_slave, ach_action, ach_grade, ach_punish, ach_level FROM achievements "
                       "WHERE ach_week=%s AND ach_status IN ('done','failed') AND ach_action NOT LIKE 'BONUS_%%'", (week,)) or []
        base = self.sc_int('base_per_level', 10)
        malus = self.sc_int('malus_punish', 3)
        rel = {}   # action -> slave -> best rel
        for r in rows:
            if not r['ach_grade'] or r['ach_grade'] not in tasktypes.GRADES:
                continue
            f = self.sc_float(GRADE_FACTOR_KEYS[r['ach_grade']], 1.0)
            v = f - malus * int(r['ach_punish']) / float(base * max(1, int(r['ach_level'])))
            d = rel.setdefault(r['ach_action'], {})
            d[r['ach_slave']] = max(d.get(r['ach_slave'], -99), v)
        bests = {}
        for action, d in rel.items():
            if len(d) < 2:
                bests[action] = set()
                continue
            top = max(d.values())
            bests[action] = {sid for sid, v in d.items() if abs(v - top) < 1e-9}
        return bests, rel

    def _week_stats(self, slave_id, week, rank_row):
        runs = self._q("SELECT ach_action, ach_grade, ach_punish, ach_status FROM achievements WHERE ach_slave=%s AND ach_week=%s "
                       "AND ach_status IN ('done','failed') AND ach_action NOT LIKE 'BONUS_%%'", (slave_id, week)) or []
        up_grade = (rank_row or {}).get('rank_up_grade', 'C')
        passed_up = {r['ach_action'] for r in runs if r['ach_grade'] and r['ach_grade'] <= up_grade}
        passed = {r['ach_action'] for r in runs if self.passed(r['ach_grade'])}
        plan = self._q("SELECT wt_status FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_kind IN ('plan','detention','challenge')",
                       (slave_id, week)) or []
        plan_total = len(plan)
        plan_done = sum(1 for p in plan if p['wt_status'] == 'done')
        punish = sum(int(r['ach_punish']) for r in runs)
        grades = [r['ach_grade'] for r in runs if r['ach_grade']]
        return {'runs': len(runs), 'passed_up': passed_up, 'passed': passed, 'plan_total': plan_total,
                'plan_done': plan_done, 'plan_complete': plan_total > 0 and plan_done == plan_total,
                'trained': len(runs) > 0, 'punish': punish, 'grades': grades}

    def _decide(self, rank_no, rank_row, st, best_count):
        """(+1|0|-1, reason) according to the rules in doc 14 §4a."""
        if rank_row is None:
            return 0, 'kein Rang definiert'
        need_tasks = int(rank_row['rank_up_tasks'])
        need_best = int(rank_row['rank_up_best'])
        need_plan = bool(rank_row['rank_up_plan'])
        if need_tasks == 0:
            tasks_ok = st['plan_total'] > 0 and st['plan_complete']
        else:
            tasks_ok = len(st['passed_up']) >= need_tasks
        up = rank_no < 10 and tasks_ok and best_count >= need_best and (not need_plan or st['plan_complete'])
        down = (st['plan_total'] > 0 and not st['plan_complete']) or not st['trained']
        if up:
            return 1, (f'{len(st["passed_up"])} Aufgaben ≥ {rank_row["rank_up_grade"]}, {best_count}× Wochenbester'
                       if need_tasks else 'Wochenplan vollständig')
        if down and rank_no > 1:
            return -1, ('kein Training' if not st['trained'] else f'Wochenplan {st["plan_done"]}/{st["plan_total"]}')
        if down:
            return 0, ('kein Training' if not st['trained'] else f'Wochenplan {st["plan_done"]}/{st["plan_total"]}') + ' (Rang 1 bleibt)'
        return 0, 'gehalten'

    def review_week(self, week):
        """Weekly review for all slaves (rank, report card data, detention for the last one)."""
        # Decide the open challenges of the week first: the bonus of the winner
        # still belongs in the score of THIS week (doc 14 §12.4).
        if self.day_enabled and self.sc_int('challenge_auto', 1):
            for ch in self._q("SELECT ch_id FROM challenges WHERE ch_week=%s AND ch_status='open'", (week,)) or []:
                try:
                    self.decide_challenge(ch['ch_id'], by='weekly')
                except Exception as e:  # noqa: BLE001
                    logger.error('decide_challenge %s: %s', ch['ch_id'], e, exc_info=True)
        slaves = self._q('SELECT slave_id, slave_name FROM slaves') or []
        bests, _ = self._week_bests(week)
        board = self.leaderboard(week)['week']
        places = {e['slave_id']: e['place'] for e in board}
        last_place = board[-1]['slave_id'] if len(board) >= 2 else None
        results = []
        active_weeks = self.sc_int('review_active_weeks', 4)
        for s in slaves:
            sid = s['slave_id']
            if self._q('SELECT wr_id FROM weekly_review WHERE wr_slave=%s AND wr_week=%s', (sid, week), one=True):
                continue                       # already reviewed
            paused_days = self.pauses.paused_days(sid, week_monday(week))
            if paused_days >= 7:
                # doc 44 §2: the week stands. Nothing is graded, the rank does not
                # move, open plan tasks go on to the next week, no badge, no
                # detention, no rule. The report card says paused — not
                # 'did not show up' (the wr_reason value itself stays German,
                # like every other reason in that column).
                rank_no, _frozen = self.rank_of(sid)
                self._x("INSERT INTO weekly_review (wr_slave, wr_week, wr_runs, wr_tasks_passed, wr_best_count, wr_plan_total, "
                        " wr_plan_done, wr_plan_complete, wr_trained, wr_punish, wr_score, wr_place, wr_rank_before, wr_rank_after, "
                        " wr_reason, wr_grades, wr_sanctions, wr_sanctions_open, wr_paused_days) "
                        "VALUES (%s,%s,0,0,0,0,0,0,0,0,0,NULL,%s,%s,'pausiert','','',0,%s)",
                        (sid, week, rank_no, rank_no, paused_days))
                moved = self._x("UPDATE weekly_tasks SET wt_week=%s WHERE wt_slave=%s AND wt_week=%s AND wt_status IN ('open','proposed')",
                                (next_week(week), sid, week))
                audit.central('weekly_review', slave_id=sid, data={'week': week, 'reason': 'pausiert', 'tasks_moved': moved})
                results.append({'slave_id': sid, 'name': s['slave_name'], 'week': week, 'rank_before': rank_no,
                                'rank_after': rank_no, 'reason': 'pausiert', 'score': 0})
                continue
            if active_weeks > 0 and not self._active_recently(sid, week, active_weeks):
                continue                       # without a login in the last n weeks: not reviewed (decision Philine 2026-09-10)
            rank_no, frozen = self.rank_of(sid)
            rank_row = self.rank_row(rank_no)
            st = self._week_stats(sid, week, rank_row)
            best_count = sum(1 for a in st['passed_up'] if sid in bests.get(a, set()))
            if frozen:
                change, reason = 0, 'eingefroren'
            else:
                change, reason = self._decide(rank_no, rank_row, st, best_count)
            new_rank = max(1, min(10, rank_no + change))
            score = self._q("SELECT COALESCE(SUM(ach_points),0) AS p FROM achievements WHERE ach_slave=%s AND ach_week=%s AND ach_counted=1 "
                            "AND ach_status IN ('done','failed')", (sid, week), one=True)
            score = int(score['p']) if score else 0
            # Sanctions of the week: they stand on the report card, but `score`
            # above is already computed by then and stays untouched (decision
            # Philine 2026-09-13 — the sanction follows from something that is
            # already in the scoring; counting twice would be punishing twice).
            sanc_text, sanc_open = self._week_sanctions(sid, week)
            cols = ("wr_slave, wr_week, wr_runs, wr_tasks_passed, wr_best_count, wr_plan_total, wr_plan_done, "
                    "wr_plan_complete, wr_trained, wr_punish, wr_score, wr_place, wr_rank_before, wr_rank_after, wr_reason, wr_grades, "
                    "wr_sanctions, wr_sanctions_open")
            vals = [sid, week, st['runs'], len(st['passed_up']), best_count, st['plan_total'], st['plan_done'],
                    1 if st['plan_complete'] else 0, 1 if st['trained'] else 0, st['punish'], score, places.get(sid),
                    rank_no, new_rank, reason, ','.join(st['grades'])[:64], sanc_text, sanc_open]
            if self.pauses.enabled:            # column arrives with migration 006
                cols += ", wr_paused_days"
                vals.append(paused_days)
            self._x(f"INSERT INTO weekly_review ({cols}) VALUES ({','.join(['%s'] * len(vals))})", tuple(vals))
            # open plan tasks of the week count as not passed
            self._x("UPDATE weekly_tasks SET wt_status='failed' WHERE wt_slave=%s AND wt_week=%s AND wt_status IN ('open','proposed')", (sid, week))
            if new_rank != rank_no:
                self.set_rank(sid, new_rank, by='weekly', reason=reason)
            # badges of the weekly review
            if best_count > 0:
                self.grant_badge(sid, 'best_of_week')
            if st['trained'] and st['punish'] == 0:
                self.grant_badge(sid, 'clean_week')
            if st['plan_complete']:
                self.grant_badge(sid, 'week_complete')
            hist = self._q('SELECT wr_rank_before, wr_rank_after FROM weekly_review WHERE wr_slave=%s ORDER BY wr_week DESC LIMIT 4', (sid,)) or []
            if len(hist) >= 4 and all(h['wr_rank_after'] >= h['wr_rank_before'] for h in hist):
                self.grant_badge(sid, 'no_drop_4')
            # detention for the last one in the weekly leaderboard (next week)
            if last_place == sid and self.sc_int('detention_last', 1):
                self._detention_last(sid, week)
            audit.central('weekly_review', slave_id=sid, data={'week': week, 'rank_before': rank_no, 'rank_after': new_rank,
                                                              'reason': reason, 'score': score, 'place': places.get(sid)})
            results.append({'slave_id': sid, 'name': s['slave_name'], 'week': week, 'rank_before': rank_no, 'rank_after': new_rank,
                            'reason': reason, 'score': score})
            # rule set: weekly review and (in)complete plan
            rctx = {'place': places.get(sid), 'last': last_place == sid, 'grade': None,
                    'rank': new_rank, 'entered': st['trained']}
            self.apply_rules('weekly', sid, rctx)
            if st['plan_total'] > 0:
                self.apply_rules('plan_complete' if st['plan_complete'] else 'plan_incomplete', sid, rctx)
                try:
                    self.streaks.on_week(sid, st['plan_complete'])
                except Exception as e:  # noqa: BLE001
                    logger.error('streaks on_week: %s', e, exc_info=True)
        # challenges that could not be decided (field too small): void
        self._x("UPDATE challenges SET ch_status='void', ch_decided=NOW() WHERE ch_week=%s AND ch_status='open'", (week,))
        self._emit('weekly_review', {'week': week, 'results': results})
        logger.info('Logbook: weekly review %s -> %s', week, [(r['name'], r['rank_before'], r['rank_after']) for r in results])
        return results

    def _active_recently(self, slave_id, week, n_weeks):
        """Login (audit) or a run in the n weeks up to and including `week`."""
        start = week_monday(week) - datetime.timedelta(days=7 * (n_weeks - 1))
        end = week_monday(week) + datetime.timedelta(days=7)
        r = self._q("SELECT 1 AS x FROM achievements WHERE ach_slave=%s AND ach_started>=%s AND ach_started<%s LIMIT 1",
                    (slave_id, start, end), one=True)
        if r:
            return True
        r = self._q("SELECT 1 AS x FROM audit_log WHERE al_slave_id=%s AND al_action='login' AND al_ts>=%s AND al_ts<%s LIMIT 1",
                    (slave_id, start, end), one=True)
        return bool(r)

    def _detention_last(self, slave_id, week):
        nxt = next_week(week)
        last = self._q("SELECT ach_action, ach_target, ach_max_punish FROM achievements WHERE ach_slave=%s AND ach_week=%s "
                       "AND ach_status IN ('done','failed') AND ach_action NOT LIKE 'BONUS_%%' ORDER BY ach_grade DESC, ach_punish DESC LIMIT 1",
                       (slave_id, week), one=True)
        if not last:
            return
        self._x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_by) "
                "VALUES (%s,%s,%s,%s,%s,'detention','open','auto')",
                (slave_id, nxt, last['ach_action'], last['ach_target'], last['ach_max_punish']))

    def propose_week(self, week):
        """Plan proposal per slave from rank, task levels and history.

        doc 14 §12.2 (decision Philine 2026-09-10): The proposal is **valid at once**
        (`wt_status='open'`, `wt_by='auto'`) — it no longer waits for a confirmation;
        the supervisor changes, deletes or overrules it afterwards. And it is
        **day-filling**: `plan_day_tasks` tasks per day of the week. If the
        available tasks are not enough for that, they are handed out several times, every repeat
        with a target higher by `plan_step`. Only tasks for which the slave has a
        device assigned — otherwise something stands in the plan that the central unit can never start.
        """
        import devicemodels
        per_day = max(1, self.sc_int('plan_day_tasks', 6)) if self.day_enabled else 0
        slaves = self._q('SELECT slave_id, slave_name FROM slaves') or []
        for s in slaves:
            sid = s['slave_id']
            if self._q("SELECT wt_id FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_kind='plan'", (sid, week), one=True):
                continue                       # the supervisor has already planned
            caps = set()
            for d in self._q('SELECT d.dev_model FROM devtoslave x JOIN devices d ON d.dev_id=x.dts_deviceid WHERE x.dts_slaveid=%s', (sid,)) or []:
                m = devicemodels.by_code(d['dev_model'])
                if m:
                    caps |= set(m.capabilities)
            avail = [t for t in tasktypes.TASKS if actions.get(t.code) and actions.get(t.code).capability in caps]
            if not avail:
                continue
            rank_no, _ = self.rank_of(sid)
            rank_row = self.rank_row(rank_no) or {}
            n = int(rank_row.get('rank_up_tasks') or 3)
            n = max(2, n) if n else 3
            if per_day:
                # day model: the week is to be filled, not only the promotion condition
                n = max(n, min(per_day * 7, len(avail) * 4, 60))
            # history: prefer tasks run most recently, raise the target by plan_step
            hist = {}
            for r in self._q("SELECT ach_action, MAX(ach_target) AS t FROM achievements WHERE ach_slave=%s AND ach_status='done' "
                             "AND ach_grade<=%s GROUP BY ach_action", (sid, self.pass_grade())) or []:
                hist[r['ach_action']] = int(r['t'] or 0)
            avail.sort(key=lambda t: (0 if t.code in hist else 1, random.random()))
            for i in range(n):
                t = avail[i % len(avail)]
                rep = i // len(avail)          # second round of the same task: higher target
                target = int(round(hist[t.code] * t.plan_step)) if hist.get(t.code) else t.plan_default
                if rep:
                    target = int(round(target * (t.plan_step ** rep)))
                self._x("INSERT INTO weekly_tasks (wt_slave, wt_week, wt_action, wt_target, wt_max_punish, wt_kind, wt_status, wt_by) "
                        "VALUES (%s,%s,%s,%s,%s,'plan','open','auto')",
                        (sid, week, t.code, target, self.default_max_punish()))
        self._emit('plan_proposed', {'week': week})
        audit.central('plan_proposed', data={'week': week, 'per_day': per_day})

    # ------------------------------------------------------------------ #
    # Forecast, leaderboard, summary (display/web)
    def forecast(self, slave_id, week=None):
        week = week or week_str()
        rank_no, frozen = self.rank_of(slave_id)
        rank_row = self.rank_row(rank_no)
        st = self._week_stats(slave_id, week, rank_row)
        bests, _ = self._week_bests(week)
        best_count = sum(1 for a in st['passed_up'] if slave_id in bests.get(a, set()))
        out = {'week': week, 'rank': rank_no, 'frozen': frozen, 'plan_done': st['plan_done'], 'plan_total': st['plan_total'],
               'trained': st['trained'], 'tasks_up': len(st['passed_up']), 'best_count': best_count, 'punish': st['punish']}
        if frozen:
            out['risk'] = 'hold'
            out['text'] = 'Rang eingefroren'
            return out
        change, reason = self._decide(rank_no, rank_row, st, best_count)
        if change > 0:
            out['risk'] = 'up'
            out['text'] = (i18n._('Aufstieg in Reichweite — Wochenplan halten') if st['plan_total']
                           else i18n._('Aufstieg in Reichweite'))
        elif change < 0 or (change == 0 and rank_no == 1 and ((st['plan_total'] and not st['plan_complete']) or not st['trained'])):
            out['risk'] = 'down'
            out['text'] = (i18n._('Noch kein Training diese Woche') if not st['trained']
                           else i18n._('Wochenplan {a}/{b}', a=st['plan_done'], b=st['plan_total'])) \
                + (i18n._(' — Abstieg droht') if rank_no > 1 else '')
        else:
            out['risk'] = 'hold'
            need_t = int(rank_row['rank_up_tasks']) if rank_row else 0
            need_b = int(rank_row['rank_up_best']) if rank_row else 0
            parts = []
            if rank_no < 10 and rank_row:
                if need_t and len(st['passed_up']) < need_t:
                    parts.append(i18n._('noch {n} Aufgabe(n) ≥ {g}', n=need_t - len(st['passed_up']), g=rank_row['rank_up_grade']))
                if need_b and best_count < need_b:
                    parts.append(i18n._('noch {n} Bestwert(e)', n=need_b - best_count))
                if not need_t and not st['plan_complete']:
                    parts.append(i18n._('Wochenplan vollständig nötig'))
            out['text'] = (i18n._('Rang wird gehalten')
                           + (' · ' + i18n._('Aufstieg') + ': ' + ', '.join(parts) if parts else ''))
        return out

    def leaderboard(self, week=None):
        week = week or week_str()
        names = {r['slave_id']: r['slave_name'] for r in self._q('SELECT slave_id, slave_name FROM slaves') or []}
        ranks = {r['sr_slave']: int(r['sr_rank']) for r in self._q('SELECT sr_slave, sr_rank FROM slave_rank') or []}
        rank_names = {r['rank_no']: r['name'] for r in self.ranks()}

        def board(rows):
            out = []
            for i, r in enumerate(rows):
                sid = r['ach_slave']
                out.append({'place': i + 1, 'slave_id': sid, 'name': names.get(sid, f'#{sid}'), 'points': int(r['p']),
                            'punish': int(r['pu']), 'runs': int(r['n']), 'rank': ranks.get(sid, 1),
                            'rank_name': rank_names.get(ranks.get(sid, 1), '')})
            return out
        wk = self._q("SELECT ach_slave, SUM(ach_points) AS p, SUM(ach_punish) AS pu, COUNT(*) AS n, MAX(ach_ended) AS last FROM achievements "
                     "WHERE ach_week=%s AND ach_counted=1 AND ach_status IN ('done','failed') GROUP BY ach_slave "
                     "ORDER BY p DESC, pu ASC, last ASC", (week,)) or []
        tot = self._q("SELECT ach_slave, SUM(ach_points) AS p, SUM(ach_punish) AS pu, COUNT(*) AS n, MAX(ach_ended) AS last FROM achievements "
                      "WHERE ach_counted=1 AND ach_status IN ('done','failed') GROUP BY ach_slave "
                      "ORDER BY p DESC, pu ASC, last ASC") or []
        return {'week': board(wk), 'total': board(tot), 'week_id': week, 'ts': int(time.time()),
                'ranks': [{'no': r['rank_no'], 'name': r['name']} for r in self.ranks()],
                # second leaderboard: challenges of the week (doc 14 §12.4)
                'challenges': self.challenge_board(week) if self.day_enabled else []}

    def summary(self, slave_id):
        """For the session status (display, web, app)."""
        if not self.enabled:
            return None
        rank_no, frozen = self.rank_of(slave_id)
        lb = self.leaderboard()
        wk = next((e for e in lb['week'] if e['slave_id'] == slave_id), None)
        tot = next((e for e in lb['total'] if e['slave_id'] == slave_id), None)
        fc = self.forecast(slave_id)
        plan = self._q("SELECT wt_id, wt_action, wt_target, wt_max_punish, wt_kind, wt_status FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s "
                       "AND wt_status<>'proposed' ORDER BY wt_kind, wt_id", (slave_id, week_str())) or []
        for p in plan:
            a = actions.get(p['wt_action'])
            t = tasktypes.get(p['wt_action'])
            p['name'] = a.name if a else p['wt_action']
            p['unit'] = t.target_unit if t else 's'
            p['target_text'] = self.target_text(p['wt_target'], p['unit'])
        last = self._q("SELECT ach_action, ach_grade, ach_points, ach_ended, ach_best FROM achievements WHERE ach_slave=%s AND ach_status IN ('done','failed') "
                       "AND ach_action NOT LIKE 'BONUS_%%' ORDER BY ach_ended DESC, ach_id DESC LIMIT 1", (slave_id,), one=True)
        return {
            'rank': rank_no, 'rank_name': self.rank_name(rank_no), 'frozen': frozen,
            'score_week': wk['points'] if wk else 0, 'place_week': wk['place'] if wk else None,
            'points_total': tot['points'] if tot else 0, 'place_total': tot['place'] if tot else None,
            'participants': len(lb['total']),
            'forecast': fc, 'plan': plan, 'badges': self.badges_of(slave_id), 'privileges': self.privileges_of(slave_id),
            'sanctions': self.sanctions_of(slave_id),
            'budgets': self.budget_status(slave_id),
            'pause': self._pause_info(slave_id),
            'streaks': self.streaks.status(slave_id),
            'dayform': self.dayform.info(slave_id),
            'scenario': self.scenarios.info(slave_id),
            'levels': self.levels_of(slave_id),
            'runs': [r.snapshot() for r in self.runs_of(slave_id)],
            'last': ({'action': last['ach_action'], 'grade': last['ach_grade'], 'points': int(last['ach_points']),
                      'best': bool(last['ach_best']), 'ended': str(last['ach_ended'])} if last else None),
        }

    @staticmethod
    def target_text(target, unit):
        target = int(target or 0)
        if unit == 's':
            if target >= 3600 and target % 3600 == 0:
                return f'{target // 3600} h'
            if target >= 60 and target % 60 == 0:
                return f'{target // 60} min'
            return f'{target} s'
        if unit == 'score':
            # grade of a waveform, 0..10000 (doc 17 §9) — not a count
            return f'{target} ' + i18n._('Punkte')
        return f'{target}×'

    def login(self, slave_id):
        """At login: hand over the report card of the last week (once, for the display)
        and mark it as shown."""
        if not self.enabled:
            return None
        r = self._q('SELECT * FROM weekly_review WHERE wr_slave=%s AND wr_shown=0 ORDER BY wr_week DESC LIMIT 1', (slave_id,), one=True)
        if not r:
            return None
        self._x('UPDATE weekly_review SET wr_shown=1 WHERE wr_id=%s', (r['wr_id'],))
        return {'week': r['wr_week'], 'rank_before': r['wr_rank_before'], 'rank_after': r['wr_rank_after'],
                'rank_name_after': self.rank_name(r['wr_rank_after']), 'reason': r['wr_reason'], 'score': r['wr_score'],
                'place': r['wr_place'], 'grades': r['wr_grades'], 'plan_done': r['wr_plan_done'], 'plan_total': r['wr_plan_total'],
                'punish': r['wr_punish'], 'remark': r['wr_remark'],
                'sanctions': r['wr_sanctions'], 'sanctions_open': r['wr_sanctions_open']}

    # ------------------------------------------------------------------ #
    @staticmethod
    def week_of_today():
        return week_str()

    def emit_event(self, kind, data):
        self._emit(kind, data)

    def _slave_name(self, slave_id):
        r = self._q('SELECT slave_name FROM slaves WHERE slave_id=%s', (slave_id,), one=True)
        return r['slave_name'] if r else f'#{slave_id}'

    def _emit(self, kind, data):
        if self.on_event:
            try:
                self.on_event(kind, data)
            except Exception as e:  # noqa: BLE001
                logger.error('logbook emit %s: %s', kind, e)
