#!/usr/bin/env python3
# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later

import sys
punisherdir = sys.path[0]
sys.path.append(punisherdir + '/libs')

from time import sleep
from datetime import datetime
import logging
import configparser
import signal
import time

import RPi.GPIO as GPIO
import pymysql

import MFRC522
import lcddriver
import actions
import audit
import logbook as logbook_mod
import dayplan as dayplan_mod
import dbmigrate
from torturedevices import torturedevices
from slaves import slaves
from punmqtt import PunMQTT


# --------------------------------------------------------------------------- #
# Logging — previously the FileHandler was attached twice (every line doubled)
logger = logging.getLogger('Punisher')
logger.setLevel(logging.DEBUG)
_handler = logging.FileHandler('logs/punisher.log')
_handler.setLevel(logging.DEBUG)
_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(_handler)
# Console: the original code showed every step with print() ("Execute SHOCK").
# That is back — everything from INFO up shows in the terminal too (log file stays DEBUG).
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s', '%H:%M:%S'))
logger.addHandler(_console)

config = configparser.ConfigParser()
config.read('config/config.ini')

stamp = dict()
realstamp = dict()
tordevices = torturedevices()
slaves = slaves()
old_slave_count = -1
old_device_count = -1
running = True
invalid_programs = {}   # pro_id -> list of error texts (start check against the action registry)

lcd = lcddriver.lcd()
MIFAREReader = MFRC522.MFRC522()

db = None
cursor = None
punmqtt = None
logbook = logbook_mod.Logbook()     # logbook/points/rank (doc 14); off when migration 005 is missing


# --------------------------------------------------------------------------- #
def cleanup():
    """Shut the installation down in an orderly way.

    Now also executed on SIGTERM (systemd stop), not only on Ctrl-C.
    First a stop to all devices — the central unit must never disappear while
    a device is still active (safety architecture A/B).
    """
    try:
        if punmqtt is not None:
            with punmqtt.lock:
                tordevices.stop_all()
                slaves.stop_all()
                slaves.disconnect_all()    # slave_id 0 to everyone: no ghost slave after a restart
                punmqtt.clear_session()
            sleep(0.5)  # a short chance for the stop messages to go out
            punmqtt.stop_heartbeat()   # the device watchdogs trigger by themselves afterwards
            punmqtt.loop_stop()
            punmqtt.disconnect()
    except Exception as e:  # noqa: BLE001 — while shutting down, pass nothing up any more
        logger.error('cleanup: mqtt: %s', e)
    try:
        lcd.lcd_clear()
    except Exception as e:  # noqa: BLE001
        logger.error('cleanup: lcd: %s', e)
    try:
        if db is not None:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.error('cleanup: db: %s', e)
    GPIO.cleanup()


def _on_signal(signum, frame):
    global running
    logger.info('Signal %s received, shutting down', signum)
    running = False


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)


# --------------------------------------------------------------------------- #
def showLCD(line1, line2, line3="", line4=""):
    lcd.lcd_clear()
    lcd.lcd_display_string(line1, 1)
    lcd.lcd_display_string(line2, 2)
    lcd.lcd_display_string(line3, 3)
    lcd.lcd_display_string(line4, 4)


# --- LCD messages without blocking (Philine 2026-09-10) -----------------------------
# Before: showLCD() + sleep(2..10) — during the 12 s after a login neither RFID
# nor program nor stop processing was running. Now: messages are queued with a
# display duration; defaultLCD() (every round) shows them one after another and
# falls back to the standard display afterwards.
_lcd_queue = []          # [(duration_s, (l1, l2, l3, l4))]
_lcd_busy_until = 0.0
_lcd_showing_msg = False


def lcd_message(seconds, line1, line2, line3='', line4=''):
    _lcd_queue.append((float(seconds), (line1, line2, line3, line4)))


def _lcd_tick():
    """Returns True when a message is currently up (then do not draw the standard display)."""
    global _lcd_busy_until, _lcd_showing_msg, old_slave_count, old_device_count, _old_lcd_extra
    now = time.time()
    if _lcd_showing_msg and now < _lcd_busy_until:
        return True
    if _lcd_queue:
        secs, lines = _lcd_queue.pop(0)
        showLCD(*lines)
        _lcd_busy_until = now + secs
        _lcd_showing_msg = True
        return True
    if _lcd_showing_msg:
        _lcd_showing_msg = False
        old_slave_count = old_device_count = -1      # redraw the standard display
        _old_lcd_extra = None
    return False


def listToString(s):
    # OPEN (review): decimal numbers strung together without a separator are
    # not unambiguous ([1,23] and [12,3] both give "123"). Deliberately NOT
    # changed, because existing database entries rest on this format.
    return "".join(str(ele) for ele in s)


def defaultLCD():
    global old_slave_count, old_device_count, _old_lcd_extra

    # Read the counters ONCE and display and remember exactly those values.
    # Before, they were read again after the (roughly 150 ms slow) LCD write:
    # if a 'hello' arrived during that time (MQTT thread), the display already
    # remembered the new counter but was still showing the old one -> "0 Devices
    # found" stayed up until the slave counter changed.
    if _lcd_tick():
        return                                       # a message is still up
    n_slaves = slaves.count_slaves()
    n_devices = tordevices.count_devices()
    line3 = line4 = ''
    if n_slaves:
        first = slaves.all()[0] if slaves.all() else None
        day = first.day.snapshot() if (first is not None and first.day is not None) else None
        instr = (day or {}).get('instruction')
        summ = first.summary() if first else None        # logbook summary (buffered for 5 s)
        if instr:
            # a neutral instruction is running: it has priority on the small display
            line3 = first.slave_name[:20]
            line4 = str(instr.get('text') or '')[:20]
        elif summ:
            # rank name, weekly points, place (doc 14: LCD line)
            line3 = first.slave_name[:20]
            place = f" #{summ['place_week']}" if summ.get('place_week') else ''
            line4 = f"{summ['rank_name'][:11]} {summ['score_week']}P{place}"[:20]
    if old_slave_count != n_slaves or old_device_count != n_devices or _old_lcd_extra != (line3, line4):
        if n_slaves == 0:
            showLCD('BDSM Trainer', str(n_devices) + ' Devices found', 'Copyright', 'Devious City')
        else:
            showLCD(str(n_slaves) + ' Slave avail.', str(n_devices) + ' Devices found', line3, line4)
        old_slave_count = n_slaves
        old_device_count = n_devices
        _old_lcd_extra = (line3, line4)


_old_lcd_extra = ('', '')


# --------------------------------------------------------------------------- #
def db_ping():
    """MariaDB drops connections after wait_timeout (8 h by default). Without
    a reconnect the installation crashes after the first night in the museum."""
    global cursor
    try:
        db.ping(reconnect=True)
        db.commit()          # better safe than sorry: do not keep an open read transaction
    except pymysql.Error as e:
        logger.error('DB ping failed: %s', e)
        return False
    cursor = db.cursor(pymysql.cursors.DictCursor)
    return True


# All queries: parameterised (no SQL injection via tag content), explicit
# columns instead of SELECT * (schema 002), DictCursor instead of tuple indices.

SQL_SLAVE_BY_RFID = (
    'SELECT s.slave_id, s.slave_rfid, s.slave_name, s.slave_program, '
    '       p.pro_name, p.pro_functions, COALESCE(ss.ss_cal_armed, 0) AS cal_armed '
    '  FROM slaves s LEFT JOIN program p ON p.pro_id = s.slave_program '
    '                LEFT JOIN slave_settings ss ON ss.ss_slave = s.slave_id '
    ' WHERE s.slave_rfid = %s'
)
# Without migration 014 the column does not exist. Then everything runs as before —
# a missing calibration mode is no reason to stop letting anyone log in.
SQL_SLAVE_BY_RFID_NOCAL = (
    'SELECT s.slave_id, s.slave_rfid, s.slave_name, s.slave_program, '
    '       p.pro_name, p.pro_functions, 0 AS cal_armed '
    '  FROM slaves s LEFT JOIN program p ON p.pro_id = s.slave_program '
    ' WHERE s.slave_rfid = %s'
)
# The flag holds for EXACTLY ONE login and falls back on logout
# (decision Philine 2026-09-12, doc 33).
SQL_CAL_DISARM = 'UPDATE slave_settings SET ss_cal_armed = 0 WHERE ss_slave = %s'
SQL_PROGRAM_STEPS = (
    'SELECT pc_id, pc_command, pc_parameter FROM program_commands '
    ' WHERE pc_program = %s ORDER BY pc_id'
)
SQL_SLAVE_DEVICES = (
    'SELECT d.dev_name, d.dev_model, d.dev_address FROM devtoslave x '
    '  JOIN devices d ON d.dev_id = x.dts_deviceid WHERE x.dts_slaveid = %s'
)
SQL_ALL_STEPS = (
    'SELECT pc_program, pc_id, pc_command, pc_parameter FROM program_commands '
    ' ORDER BY pc_program, pc_id'
)
SQL_SLAVE_BY_ID = (
    'SELECT s.slave_id, s.slave_rfid, s.slave_name, s.slave_program, p.pro_name '
    '  FROM slaves s LEFT JOIN program p ON p.pro_id = s.slave_program WHERE s.slave_id = %s'
)
# Checksum over all tables the central unit reads: if the value changes,
# someone (web, mysql client) has changed something -> take the changes over.
SQL_CHECKSUM = 'CHECKSUM TABLE program, program_commands, slaves, slave_program, devtoslave, devices, slave_calibration'
# Logbook tables the web changes (plan, rank, names, numbers): own checksum,
# a change -> only summaries/leaderboard anew, no program reload
SQL_CHECKSUM_LOGBOOK = 'CHECKSUM TABLE weekly_tasks, slave_rank, ranks, scoring, privileges, slave_levels, challenges'
SQL_CALIBRATION = 'SELECT sc_device, sc_pose, sc_x, sc_y, sc_z FROM slave_calibration WHERE sc_slave = %s'
DB_POLL_S = 30


def load_program(program_id):
    """Steps of the ACTIVE program (pointer slaves.slave_program, schema 002)."""
    if program_id is None:
        return []
    cursor.execute(SQL_PROGRAM_STEPS, (program_id,))
    return cursor.fetchall()


def check_all_programs():
    """Start check: check every stored program against the action registry.

    Invalid programs are not started (the slave gets a message), the
    installation carries on running for everyone else.
    """
    cursor.execute(SQL_ALL_STEPS)
    by_program = {}
    for row in cursor.fetchall():
        by_program.setdefault(row['pc_program'], []).append(row)
    invalid_programs.clear()
    program_warnings.clear()
    n_warn = 0
    for pro_id, rows in by_program.items():
        errors = actions.validate_program(rows)
        if errors:
            invalid_programs[pro_id] = errors
            for e in errors:
                logger.error('Program %s invalid: %s', pro_id, e)
        # notes that are not an error, but almost certainly an oversight (MAGLOCK/UNLOCK)
        warns = actions.program_warnings(rows)
        if warns:
            program_warnings[pro_id] = warns
            n_warn += len(warns)
            for w in warns:
                logger.warning('Program %s, Schritt %s: %s', pro_id, w['pc_id'], w['text'])
    logger.info('Program check: %d programs, %d invalid, %d Hinweise', len(by_program), len(invalid_programs), n_warn)


program_warnings = {}


def publish_session():
    punmqtt.publish_session(slaves.snapshot())


def publish_leaderboard():
    if logbook.enabled:
        try:
            punmqtt.publish_leaderboard(logbook.leaderboard())
        except Exception as e:  # noqa: BLE001
            logger.error('leaderboard: %s', e)


def on_logbook_event(kind, data):
    """Pass the logbook's events (achievement, rank_change, badge, privilege,
    bonus, detention, weekly_review, plan_proposed, challenge, warning, reward)
    on to the display/web."""
    punmqtt.publish_central_event(kind, data)
    if kind != 'achievement':                  # achievement is already audited in _finish
        audit.central(kind, slave_id=data.get('slave_id') if isinstance(data, dict) else None, data=data)
    if kind in ('rank_change', 'weekly_review', 'bonus', 'badge', 'privilege', 'detention'):
        for s in slaves.all():
            s.invalidate_summary()
        publish_leaderboard()


def on_day_end(s, status):
    """The day is over (duration expired, capitulation or plan fulfilled): log out."""
    logger.info("Slave '%s': Tag beendet (%s) - Abmeldung", s.slave_name, status)
    audit.central('day_end', slave_id=s.slave_id, data={'status': status})
    punmqtt.publish_central_event('logout', {'slave_id': s.slave_id, 'name': s.slave_name, 'reason': status})
    lcd_message(4, s.slave_name, {'capitulated': 'Aufgegeben.', 'done': 'Tag beendet.'}.get(status, 'Tag beendet.'))
    with punmqtt.lock:
        slaves.remove_slave(s.slave_rfid)
        for other in slaves.all():
            try:
                apply_slave_changes(other)
            except pymysql.Error as e:
                logger.error('apply_slave_changes after day end: %s', e)
    publish_session()
    publish_leaderboard()


def on_slave_notify(kind, s, **kw):
    """Hook of the slave/program engine: refresh the session status (retained)
    for the display, report steps as an event."""
    if kind == 'achievement':
        # result of a run (grade, points) — the event comes from the logbook
        publish_leaderboard()
    elif kind == 'step':
        a = kw.get('action')
        data = {'slave_id': s.slave_id, 'name': s.slave_name, 'code': a.code, 'action': a.name,
                'params': kw.get('params'), 'skipped': kw.get('skipped'),
                'trainable': a.trainable,
                'pos': s.slave_program.pos + 1, 'total': len(s.slave_program.plan)}
        punmqtt.publish_central_event('step', data)
        audit.central('step', slave_id=s.slave_id, data=data)
    elif kind == 'finished':
        punmqtt.publish_central_event('program_finished', {'slave_id': s.slave_id, 'name': s.slave_name})
        audit.central('program_finished', slave_id=s.slave_id)
    elif kind == 'instruction':
        # neutral instruction (pause): display and LCD show it, no assessment
        data = {'slave_id': s.slave_id, 'name': s.slave_name, 'text': kw.get('text'), 'minutes': kw.get('minutes')}
        punmqtt.publish_central_event('instruction', data)
        audit.central('instruction', slave_id=s.slave_id, data=data)
    elif kind == 'warning':
        logger.warning("Slave '%s': %s", s.slave_name, kw.get('text'))
        audit.central('warning', slave_id=s.slave_id, data={'text': kw.get('text')})
        punmqtt.publish_central_event('warning', {'slave_id': s.slave_id, 'name': s.slave_name, 'text': kw.get('text')})
    publish_session()


def program():
    slaves.execute_program()


# --------------------------------------------------------------------------- #
# Take over changes to the database during operation.
# Trigger: the web reports via MQTT (punisher/central/reload) — immediately; in
# addition, every DB_POLL_S seconds a checksum over the tables that are read, so
# that changes made with the mysql client arrive too. Rule (Philine 2026-09-07): a
# running program keeps its position, the rest applies anew; a different active
# program, different devices, a different name are put into effect at once.
_db_checksum = None
_db_last_poll = 0.0


def db_checksum():
    try:
        cursor.execute(SQL_CHECKSUM)
    except pymysql.Error:
        # without migration 004 (slave_calibration), check the core tables
        cursor.execute(SQL_CHECKSUM.replace(', slave_calibration', ''))
    return tuple(r['Checksum'] for r in cursor.fetchall())


_lb_checksum = None


def logbook_checksum():
    if not logbook.enabled:
        return None
    cursor.execute(SQL_CHECKSUM_LOGBOOK)
    return tuple(r['Checksum'] for r in cursor.fetchall())


def apply_logbook_changes(reason):
    """The web changed plan/rank/names/numbers: summaries and leaderboard anew."""
    logger.info('Logbook change (%s): refreshing summaries and leaderboard', reason)
    logbook.scoring(force=True)
    logbook.budgets.invalidate()        # budgets (doc 44 §1) are edited over the web too
    logbook.pauses.invalidate()
    logbook.streaks.invalidate()
    logbook.dayform.invalidate()
    logbook.scenarios.tick()
    for s in slaves.all():
        s.invalidate_summary()
    publish_session()
    publish_leaderboard()


def device_held_by_other(device, s):
    """A physical device can be with only ONE logged-in slave.
    If it is assigned to several in the DB and the other one is logged in right
    now and holding it, this slave does not get it (first come, first served)."""
    holder = slaves.holder_of(device)
    if holder is None or holder is s:
        return False
    logger.warning("Slave '%s': device %s is held by '%s' - not assigned", s.slave_name, device, holder.slave_name)
    audit.central('device_busy', slave_id=s.slave_id, device=device, data={'held_by': holder.slave_id})
    punmqtt.publish_central_event('device_busy', {'slave_id': s.slave_id, 'name': s.slave_name,
                                                  'device': device, 'held_by': holder.slave_name})
    return True


def load_calibration(slave_id):
    """Pose references per device (migration 004). Without the table: empty."""
    try:
        cursor.execute(SQL_CALIBRATION, (slave_id,))
    except pymysql.Error as e:
        logger.warning('calibration: %s (Migration 004 eingespielt?)', e)
        return {}
    cal = {}
    for r in cursor.fetchall():
        cal.setdefault(r['sc_device'], {})[r['sc_pose']] = [round(r['sc_x'], 4), round(r['sc_y'], 4), round(r['sc_z'], 4)]
    return cal


def apply_slave_changes(s):
    """Reconcile a logged-in slave with the DB."""
    cursor.execute(SQL_SLAVE_BY_ID, (s.slave_id,))
    row = cursor.fetchone()
    if row is None:
        logger.warning("Slave '%s' (#%s) deleted in DB while logged in -> logout", s.slave_name, s.slave_id)
        s.stop()
        slaves.remove_slave(s.slave_rfid)
        showLCD(s.slave_name, 'removed (DB)')
        return
    if row['slave_name'] != s.slave_name:
        logger.info("Slave #%s renamed: '%s' -> '%s'", s.slave_id, s.slave_name, row['slave_name'])
        s.rename(row['slave_name'])
    if row['slave_rfid'] != s.slave_rfid:
        # the registry key is the RFID -> re-hang it
        slaves.slaves[row['slave_rfid']] = slaves.slaves.pop(s.slave_rfid)
        s.slave_rfid = row['slave_rfid']

    # active program
    if row['slave_program'] != s.program_id:
        if row['slave_program'] is None:
            logger.info("Slave '%s': active program cleared -> stop", s.slave_name)
            s.stop()
            s.clear_program()
        elif row['slave_program'] in invalid_programs:
            logger.error("Slave '%s': new active program %s is invalid -> keeping current",
                         s.slave_name, row['slave_program'])
        else:
            logger.info("Slave '%s': active program %s -> %s ('%s')", s.slave_name,
                        s.program_id, row['slave_program'], row['pro_name'])
            s.stop()
            s.switch_program(row['slave_program'], row['pro_name'], load_program(row['slave_program']))
    elif s.program_id is not None:
        # same program: compare the step list
        steps = load_program(s.program_id)
        current = [(x['pc_command'], x['pc_parameter']) for x in s.slave_program.plan]
        new = [(x['pc_command'], x['pc_parameter']) for x in steps]
        if current != new:
            if s.program_id in invalid_programs:
                logger.error("Slave '%s': changed program %s is invalid -> keeping old steps",
                             s.slave_name, s.program_id)
            else:
                s.replace_program(steps)
        if row['pro_name'] != s.program_name:
            s.program_name = row['pro_name']

    # devices
    cursor.execute(SQL_SLAVE_DEVICES, (s.slave_id,))
    rows = cursor.fetchall()
    s.device_labels = {d['dev_name']: d['dev_address'] or '' for d in rows}
    cal = load_calibration(s.slave_id)
    if cal != s.calibration:
        logger.info("Slave '%s': calibration updated (%s)", s.slave_name, {k[:8]: sorted(v) for k, v in cal.items()})
        s.calibration = cal
    wanted = [d['dev_name'] for d in rows if not device_held_by_other(d['dev_name'], s)]
    added, removed = s.set_devices(wanted)
    if added or removed:
        logger.info("Slave '%s': devices +%s -%s", s.slave_name, added, removed)


def apply_db_changes(reason):
    """Renew the start check and reconcile all logged-in slaves."""
    if not db_ping():
        return
    logger.info('DB change (%s): re-reading programs and assignments', reason)
    check_all_programs()
    logbook.scoring(force=True)
    for s in slaves.all():
        try:
            apply_slave_changes(s)
            s.invalidate_summary()
        except pymysql.Error as e:
            logger.error('apply_slave_changes: %s', e)
    publish_session()
    publish_leaderboard()
    audit.central('db_reload', data={'reason': reason})


def write_device_identities():
    """Write what the MQTT thread saw — in THIS thread, with THIS cursor.

    The paho callback runs in a thread of its own. It used to write the
    device identity straight into the one connection that this loop uses, and
    PyMySQL is not thread-safe: two threads on one connection can interleave a
    query with another's result, and the quiet version of that failure is a
    fetchall() that hands back somebody else's rows (finding Philine
    2026-09-15). In this installation the wrong rows could be a slave's
    calibration.

    So the callback queues and this writes. The same shape the reload requests
    have had all along.
    """
    with punmqtt.lock:
        pending = punmqtt.identity_writes
        punmqtt.identity_writes = []
    if not pending:
        return
    if not db_ping():
        # Put them back rather than dropping them — the database comes back.
        with punmqtt.lock:
            punmqtt.identity_writes = pending + punmqtt.identity_writes
        return
    for rec in pending:
        punmqtt.write_identity(cursor, rec)
    db.commit()


def write_device_boots():
    """Same shape as write_device_identities(), for the boot history (2.2.0)."""
    with punmqtt.lock:
        pending = punmqtt.boot_writes
        punmqtt.boot_writes = []
    if not pending:
        return
    if not db_ping():
        with punmqtt.lock:
            punmqtt.boot_writes = pending + punmqtt.boot_writes
        return
    for rec in pending:
        punmqtt.write_boot(cursor, rec)
    db.commit()


def poll_db_changes():
    """Main loop: the web's reload requests at once, the checksum periodically."""
    global _db_checksum, _db_last_poll, _lb_checksum
    with punmqtt.lock:
        requests = punmqtt.reload_requests
        punmqtt.reload_requests = []
    now = time.time()
    due = (now - _db_last_poll) >= DB_POLL_S
    if not requests and not due:
        return
    _db_last_poll = now
    if not db_ping():
        return
    try:
        cs = db_checksum()
        lcs = logbook_checksum()
    except pymysql.Error as e:
        logger.error('db checksum: %s', e)
        return
    lb_requests = [r for r in requests if r[0] == 'logbook']
    requests = [r for r in requests if r[0] != 'logbook']
    if requests:
        with punmqtt.lock:
            apply_db_changes('web: ' + ', '.join(f"{w}{('#' + str(i)) if i else ''}" for w, i in requests))
    elif _db_checksum is not None and cs != _db_checksum:
        with punmqtt.lock:
            apply_db_changes('checksum')
    elif lb_requests or (_lb_checksum is not None and lcs != _lb_checksum):
        with punmqtt.lock:
            apply_logbook_changes('web' if lb_requests else 'checksum')
    _db_checksum = cs
    _lb_checksum = lcs


def handle_requests():
    """Requests from the web/the app (punisher/central/request): punishment/reward
    over the channel (only the central unit publishes there), weekly assessment,
    plan proposal, activation — all of it with an audit entry."""
    with punmqtt.lock:
        reqs = punmqtt.requests
        punmqtt.requests = []
    if not reqs:
        return
    for j in reqs:
        what = str(j.get('what', ''))
        sid = j.get('slave_id')
        user = j.get('user')
        try:
            sid = int(sid) if sid not in (None, '') else None
        except (TypeError, ValueError):
            sid = None
        try:
            if what == 'punish' and sid:
                s = slaves.by_id(sid)
                runs = logbook.runs_of(sid)
                if s is None:
                    logger.warning('request punish for slave %s: not logged in - no device listens', sid)
                logbook.punish(sid, int(j.get('level') or 1), str(j.get('kind') or 'any'), str(j.get('reason') or 'aufsicht'),
                               'web', run=runs[0] if runs else None, user=user)
            elif what == 'reward' and sid:
                logbook.reward(sid, int(j.get('level') or 1), str(j.get('kind') or 'any'), str(j.get('reason') or 'aufsicht'),
                               'web', user=user)
            elif what == 'review':
                week = str(j.get('week') or logbook_mod.prev_week(logbook_mod.week_str()))
                if week >= logbook_mod.week_str() and not j.get('force'):
                    # The running week is only assessed after it has ended: a premature
                    # assessment would be final (slaves count as "already assessed") and
                    # the Monday run would find nothing any more (review 2026-09-10).
                    logger.warning('request review %s refused: week not finished (force=1 to override)', week)
                    punmqtt.publish_central_event('warning', {'text': f'Wochenbewertung {week} abgelehnt: Woche läuft noch'})
                    continue
                logbook.review_week(week)
                if week > (logbook.sc_str('last_review_week', '') or ''):
                    logbook.set_scoring('last_review_week', week)
            elif what == 'propose':
                logbook.propose_week(str(j.get('week') or logbook_mod.next_week(logbook_mod.week_str())))
            elif what == 'activate':
                logbook.activate_week(str(j.get('week') or logbook_mod.week_str()))
            else:
                logger.warning('request: unknown %r', j)
                continue
            audit.log('web', 'request', what, None, sid, j, user)
        except Exception as e:  # noqa: BLE001
            logger.error('request %s: %s', what, e, exc_info=True)
    for s in slaves.all():
        s.invalidate_summary()
    publish_session()
    publish_leaderboard()


# RFID: poll every RFID_POLL_S (before: every round, ~20 SPI queries/s) and
# debounce — a tag lying there counts once; only once it has not been read for
# at least RFID_GONE_S does putting it down again count (login/logout).
RFID_POLL_S = 0.2
RFID_GONE_S = 1.5
RFID_MIN_GAP_S = 3.0      # in addition: the same tag not twice within 3 s
_rfid_last_tag = None
_rfid_last_seen = 0.0
_rfid_last_action = {}


def rfid():
    global _rfid_last_tag, _rfid_last_seen
    (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
    if status != MIFAREReader.MI_OK:
        return

    (status, uid) = MIFAREReader.MFRC522_Anticoll()
    if status != MIFAREReader.MI_OK:
        return

    key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
    try:
        MIFAREReader.MFRC522_SelectTag(uid)
    except Exception as e:  # noqa: BLE001
        # before: log.warning() on the FileHandler -> AttributeError
        logger.warning('RFID select error: %s', e)
        return

    status = MIFAREReader.MFRC522_Auth(MIFAREReader.PICC_AUTHENT1A, 8, key, uid)
    if status != MIFAREReader.MI_OK:
        return

    data = MIFAREReader.MFRC522_Read(8)
    MIFAREReader.MFRC522_StopCrypto1()
    if not data:
        return
    slaveid = listToString(data[:9])

    now = time.time()
    still_there = (slaveid == _rfid_last_tag and now - _rfid_last_seen < RFID_GONE_S)
    _rfid_last_tag, _rfid_last_seen = slaveid, now
    if still_there:
        return                                       # the tag is still lying on the reader
    if now - _rfid_last_action.get(slaveid, 0) < RFID_MIN_GAP_S:
        return
    _rfid_last_action[slaveid] = now

    if not db_ping():
        lcd_message(2, 'Database error', 'see log')
        return

    try:
        cursor.execute(SQL_SLAVE_BY_RFID, (slaveid,))
    except pymysql.Error:
        cursor.execute(SQL_SLAVE_BY_RFID_NOCAL, (slaveid,))    # before migration 014
    slave = cursor.fetchone()

    if slave is None:
        logger.info('Slave not found - RFID ' + slaveid)
        audit.central('rfid_unknown', data={'rfid': slaveid})
        punmqtt.publish_central_event('rfid_unknown', {'rfid': slaveid})
        lcd_message(2, 'Slave not found', '')
        return

    rfid_key = slave['slave_rfid']
    name = slave['slave_name']

    with punmqtt.lock:
        if slaves.slave_online(rfid_key):
            s_on = slaves.by_id(slave['slave_id'])
            if s_on is not None and getattr(s_on, 'day', None) is not None and s_on.day.running:
                # Day model (doc 14 §12.1): logging out early counts as CAPITULATION.
                # The logout itself is done by on_day_end(); logging in again today only
                # if it is allowed for this slave (slave_settings.ss_relogin).
                logger.info("Slave '%s' kapituliert - RFID %s", name, slaveid)
                audit.central('capitulation', slave_id=slave['slave_id'], data={'name': name})
                s_on.day.capitulate()
                return
            # The logout ENDS a calibration run, and it does so definitively:
            # the flag falls back, the next login is an ordinary one again. It
            # stands here and not in disconnect(), because it means exactly
            # this one event — she puts the card down and leaves.
            # A restart of the central unit in the middle deliberately leaves it
            # standing: the run was then not at its end.
            was_cal = bool(getattr(s_on, 'calibration_mode', False)) if s_on is not None else False
            if was_cal:
                try:
                    cursor.execute(SQL_CAL_DISARM, (slave['slave_id'],))
                    db.commit()
                except pymysql.Error as e:
                    logger.error('calibration disarm: %s', e)
                logger.info("Slave '%s': calibration run finished", name)
                audit.central('calibration_end', slave_id=slave['slave_id'], data={'name': name})
                punmqtt.publish_central_event('calibration_end',
                                              {'slave_id': slave['slave_id'], 'name': name})
            logger.info("Slave '%s' disconnected - RFID %s", name, slaveid)
            audit.central('logout', slave_id=slave['slave_id'], data={'name': name})
            punmqtt.publish_central_event('logout', {'slave_id': slave['slave_id'], 'name': name})
            slaves.remove_slave(rfid_key)
            # Devices that have become free: another logged-in slave they are also
            # assigned to gets them now (share a device, use it one after another).
            for other in slaves.all():
                try:
                    apply_slave_changes(other)
                except pymysql.Error as e:
                    logger.error('apply_slave_changes after logout: %s', e)
            publish_session()
            lcd_message(2, name, 'Slave disconnected')
            lcd_message(2, 'Training program', 'disabled...')
            return

        # CALIBRATION RUN (doc 33). The supervisor has set the flag in the
        # profile; this one login then serves the calibration exclusively:
        # devices are assigned to her, but no program, no day plan and no
        # routine runs.
        #
        # The crucial point is what does NOT happen: open_day() is never
        # called. So there is no day that could run, end, capitulate or be
        # locked - afterwards she logs in perfectly normally and still has her
        # day. A quarter of an hour of sticking on electrodes would otherwise
        # have cost her the day (doc 14 §12.1).
        cal_mode = bool(slave.get('cal_armed'))

        # The two refusals do not apply to the calibration run: it needs no
        # program at all, and a broken one does not disturb it.
        if not cal_mode and slave['slave_program'] is None and not logbook.day_enabled:
            logger.warning("Slave '%s' has no active program", name)
            lcd_message(3, name, 'No active program')
            return

        if not cal_mode and slave['slave_program'] in invalid_programs and not logbook.day_enabled:
            logger.error("Slave '%s': active program %s is invalid, not started",
                         name, slave['slave_program'])
            lcd_message(3, name, 'Program invalid', 'see log')
            return

        logger.info("Slave '%s' connected - RFID %s%s", name, slaveid,
                    ' (calibration run)' if cal_mode else '')
        audit.central('calibration_start' if cal_mode else 'login', slave_id=slave['slave_id'],
                      data={'name': name, 'program': slave['slave_program'], 'program_name': slave['pro_name']})
        punmqtt.publish_central_event('calibration_start' if cal_mode else 'login',
                                      {'slave_id': slave['slave_id'], 'name': name,
                                       'program': None if cal_mode else slave['pro_name']})
        # In the day model the day plan leads (libs/dayplan.py); the active program is
        # only a fallback any more, for when migration 007 is missing.
        day_mode = logbook.day_enabled and not cal_mode
        prog = [] if (day_mode or cal_mode) else load_program(slave['slave_program'])
        slaves.add_slave(punmqtt, tordevices, slave['slave_id'], rfid_key, name, prog,
                         slave['pro_functions'], program_id=None if day_mode else slave['slave_program'],
                         program_name=None if day_mode else slave['pro_name'])
        stamp[rfid_key] = datetime.timestamp(datetime.now())
        realstamp[rfid_key] = datetime.timestamp(datetime.now())
        cursor.execute(SQL_SLAVE_DEVICES, (slave['slave_id'],))
        dev_rows = cursor.fetchall()            # fetch first, load_calibration() uses the same cursor
        s_obj = slaves.slaves[rfid_key]
        # The marker on the slave object, not only in the database: the display,
        # the session status and execute() ask it, and none of them should have
        # to touch the database for that.
        s_obj.calibration_mode = cal_mode
        s_obj.calibration = load_calibration(slave['slave_id'])
        s_obj.review = logbook.login(slave['slave_id']) if logbook.enabled else None   # report card of the previous week (display)
        if day_mode:
            s_obj.day = dayplan_mod.DayRunner(s_obj, logbook, on_end=on_day_end)
        for dev in dev_rows:
            # dev_name is the MQTT device id (topic segment)
            s_obj.device_labels[dev['dev_name']] = dev['dev_address'] or ''
            if device_held_by_other(dev['dev_name'], s_obj):
                continue
            if tordevices.device_online(dev['dev_name']):
                slaves.add_device(rfid_key, dev['dev_name'])
            else:
                slaves.add_offline_device(rfid_key, dev['dev_name'])
        # Sending the waveforms in advance (doc 17 §7): the day's routines go to the
        # trainer at login, so that the start does not hang on the transfer. Only when
        # that has not taken hold does "routine unknown" take hold at the start.
        # In the calibration run there is no day and therefore no routines of the
        # day - sending in advance would have nothing to send and would only
        # delay the login.
        if logbook.enabled and not cal_mode and s_obj.has_capability('trainer_routine'):
            for ro_id in logbook.routines_for_day(slave['slave_id']):
                if s_obj.routine_push(ro_id):
                    logger.info("Preloaded routine %s for '%s'", ro_id, name)
        if day_mode:
            ok, why = s_obj.day.open_day()
            if not ok:
                # already finished or given up today: no second login
                logger.warning("Slave '%s': Anmeldung abgelehnt (%s)", name, why)
                audit.central('login_refused', slave_id=slave['slave_id'], data={'reason': why})
                punmqtt.publish_central_event('login_refused', {'slave_id': slave['slave_id'], 'name': name,
                                                                'reason': why})
                slaves.remove_slave(rfid_key)
                lcd_message(4, name, {'capitulated': 'Aufgegeben - heute Schluss.',
                                      'done': 'Tag schon beendet.',
                                      'paused': 'Pause bis %s' % getattr(s_obj.day, 'paused_until', '?')}
                            .get(why, 'Anmeldung abgelehnt.'))
                publish_session()
                return
        publish_session()

    if cal_mode:
        lcd_message(2, name, 'Calibration run')
        lcd_message(10, 'Kalibrierung', 'kein Programm, kein Tag')
        return
    lcd_message(2, name, 'Slave connected')
    if logbook.day_enabled:
        day = slaves.slaves[rfid_key].day
        snap = day.snapshot() if day else None
        mins = (snap or {}).get('remaining_min') or 0
        lcd_message(10, 'Tagesplan', f"{(snap or {}).get('plan') or '-'} / {mins} min")
    else:
        lcd_message(10, 'Training program', (slave['pro_name'] or '?') + ' started...')


# --------------------------------------------------------------------------- #
try:
    db = pymysql.connect(
        host=config['database']['hostname'],
        user=config['database']['username'],
        password=config['database']['password'],
        database=config['database']['database'],
        # IMPORTANT: without autocommit the connection hangs in ONE transaction
        # (REPEATABLE READ) and would never see changes from the web until a
        # restart -- every SELECT would return the state of the first access.
        autocommit=True,
    )
except pymysql.Error as e:
    # before: db.close() and mqtt.loop.stop() on objects that do not exist
    print("Error: MySQL connection failed, program start failed")
    print("pymysql %d: %s" % (e.args[0], e.args[1]))
    logger.critical('MySQL connection failed: %s', e)
    lcd.lcd_clear()
    GPIO.cleanup()
    sys.exit(1)

cursor = db.cursor(pymysql.cursors.DictCursor)

# Bring the database up to the state of the code (decision Philine 2026-09-10): missing
# migrations from sql/ are applied at startup (a backup to logs/ beforehand).
# If that fails, the central unit does NOT start - half a schema is more dangerous
# than a clear stop. [database] auto_migrate=0 switches to "only check and warn".
try:
    _auto, _bak, _req = dbmigrate.config_flags(config['database'])
    _mig = dbmigrate.run(config['database'], 'sql', log_dir='logs', auto=_auto, do_backup=_bak, require_backup=_req)
    if _mig['pending'] and not _auto:
        logger.warning('DB: Migrationen fehlen (%s) - auto_migrate=0, bitte von Hand einspielen', ', '.join(_mig['pending']))
except dbmigrate.MigrationError as e:
    logger.critical('DB-Migration fehlgeschlagen: %s', e)
    print(f'Error: DB-Migration fehlgeschlagen: {e}')
    showLCD('DB-Migration', 'fehlgeschlagen', 'siehe logs/', 'Start abgebrochen')
    sleep(5)
    GPIO.cleanup()
    sys.exit(1)
except pymysql.Error as e:
    logger.critical('DB-Migration: Datenbankfehler: %s', e)
    print(f'Error: DB-Migration: {e}')
    sys.exit(1)

audit.init(config['database'])       # event log (migration 003), own connection
if _mig['applied']:
    audit.central('db_migrated', data={'applied': _mig['applied'], 'backup': _mig['backup']})
logbook.init(config['database'])     # logbook/points/rank (migration 005), own connection
logbook.set_limits(config['safety'] if config.has_section('safety') else None)   # channel limits from the configuration
check_all_programs()

punmqtt = PunMQTT('Punisher')
slaves.notify = on_slave_notify
slaves.logbook = logbook
logbook.on_event = on_logbook_event
logbook.slave_lookup = slaves.by_id      # rule effects at once when the slave is there
logbook.publish_punish = punmqtt.publish_punish
# Who else would punish (2.3.5, doc 57) — only punmqtt knows which devices the
# slave is currently holding and what model each of them is.
logbook.punish_kinds_of = punmqtt.punish_kinds_of
logbook.publish_reward = punmqtt.publish_reward
punmqtt.run(config, logger, tordevices, cursor, slaves)
sleep(0.5)
punmqtt.clear_session()                 # after a restart: nobody logged in
if logbook.enabled:
    logbook.tick(time.time())           # catch up on a missed weekly assessment
    publish_leaderboard()
try:
    _db_checksum = db_checksum()
    _lb_checksum = logbook_checksum()
    _db_last_poll = time.time()
except pymysql.Error as e:
    logger.error('db checksum: %s', e)

defaultLCD()
_rfid_next = 0.0

try:
    while running:
        if punmqtt.fatal_error:
            logger.critical('MQTT fatal: %s', punmqtt.fatal_error)
            showLCD('MQTT error', punmqtt.fatal_error[:20])
            break

        # The central heartbeat runs in a thread of its own (punmqtt),
        # independent of the blocking places of this loop.
        punmqtt.sweep_timeouts()
        write_device_identities()        # what the MQTT thread saw, written HERE
        write_device_boots()
        poll_db_changes()                # web messages at once, checksum every 30 s
        handle_requests()                # channel/assessment on request from the web
        if logbook.enabled:
            logbook.tick()               # week change, plan proposal (internally every 60 s)
            # Deadlines of blocking tasks: _finish() reports the event itself (on_event);
            # here only summary/session/leaderboard are refreshed (review 2026-09-10:
            # before, 'achievement' was published twice)
            timed_out = logbook.check_timeouts()
            if timed_out:
                for res in timed_out:
                    s_to = slaves.by_id(res.get('slave_id'))
                    if s_to is not None:
                        s_to.invalidate_summary()
                publish_session()
                publish_leaderboard()

        if tordevices.count_devices() > 0 and time.time() >= _rfid_next:
            _rfid_next = time.time() + RFID_POLL_S
            rfid()

        defaultLCD()

        if slaves.count_slaves() > 0 and tordevices.count_devices() > 0:
            with punmqtt.lock:
                program()

        # before: busy loop without a pause -> 100 % CPU on the Pi
        time.sleep(0.05)
finally:
    cleanup()
