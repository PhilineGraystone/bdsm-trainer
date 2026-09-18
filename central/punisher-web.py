#!/usr/bin/env python3
# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Punisher — supervisor web interface (own process alongside punisher.py).

Administration (slaves, programs with step editor, devices, assignments),
live status from MQTT, stop/EMERGENCY, event log (audit_log).
Flask + Jinja, server-rendered, no external resources (isolated WLAN).

Start:   python3 punisher-web.py          (port from config.ini [web], default 8080)
Config:  [web] password=...  secret=...   (secret optional; without a secret the
         login only holds until the next restart)
"""

import sys
import os
punisherdir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(punisherdir, 'libs'))
os.chdir(punisherdir)

import configparser
import datetime
import functools
import hmac
import json
import logging
import secrets

import pymysql
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

import actions
import audit
import devicehealth
import devicemodels
import devicetest
import fwversion
import i18n
import profiles
import programcheck
import routines
import logbook as logbook_mod
import dbmigrate
from webmqtt import WebMQTT

# --------------------------------------------------------------------------- #
logger = logging.getLogger('Punisher')
logger.setLevel(logging.INFO)
_h = logging.FileHandler('logs/punisher-web.log')
_h.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(_h)
_c = logging.StreamHandler(sys.stdout)
_c.setFormatter(logging.Formatter('%(asctime)s %(levelname)-7s %(message)s', '%H:%M:%S'))
logger.addHandler(_c)

config = configparser.ConfigParser()
config.read('config/config.ini')
devicehealth.configure(config)          # [health] thresholds, if the installation sets any
if 'web' not in config or not config['web'].get('password'):
    print('config.ini: Abschnitt [web] mit password=... fehlt — ohne Passwort startet das Webinterface nicht.')
    sys.exit(1)
WEB_PASSWORD = config['web']['password']
WEB_USER = config['web'].get('username', 'aufsicht')

app = Flask(__name__, template_folder='templates', static_folder='static')
# Check templates for changes on every request. Without this Jinja keeps them in
# the cache as long as debug is off: whoever unpacks a package and does NOT restart
# the service keeps getting the old page and looks for the fault in the wrong place.
# Costs one stat() per page — with a handful of supervisors not measurable.
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.secret_key = config['web'].get('secret') or secrets.token_hex(32)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Multilingual: installation default from config.ini, switchable per login
i18n.configure(config['web'].get('lang')
               or (config['display'].get('lang') if 'display' in config else None)
               or 'de')
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024      # Photos of the slave
PHOTO_DIR = os.path.join(punisherdir, 'pics', 'slaves')  # <slave_id>.jpg|png — the HDMI display reads them
# The ORIGINAL of each photo, untouched (2.3.4, project document 56).
#
# What lies in PHOTO_DIR is a 4:5 CUT-OUT — web and display both draw the photo
# 4:5 and cut off the rest themselves, in the middle, where a face rarely is.
# Whoever wants to choose the section has to be able to choose it again, so the
# original has to survive: cutting into the file that is already a cut-out
# loses a little more every time and cannot be undone.
#
# Not in the repository: .gitignore has `pics/slaves/*`, which covers this
# directory as well. A participant's photo never goes into a git history.
ORIG_DIR = os.path.join(PHOTO_DIR, 'orig')
GRADE_DIR = os.path.join(punisherdir, 'pics', 'grades')  # A.png..F.png replace the grade glyphs (web + display)
os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(ORIG_DIR, exist_ok=True)
os.makedirs(GRADE_DIR, exist_ok=True)

# The cut-out, and what it is measured against.
#
# 4:5 is not a taste: the display draws 150x190 and 200x250, the web 160x200 —
# all three 4:5 with `cover`. A cut-out in this ratio is shown WHOLE in all
# three places, and nothing is cut away a second time. That is why the ratio
# lives here and not in the browser: the browser proposes a section, this
# decides what comes out.
CROP_W, CROP_H = 4, 5
CROP_MAX_W = 800            # 4x the largest place it is shown; more is storage
                            # without a picture to go with it

def _sweep_orphan_photos():
    """At startup: clear away image files for which there is no slave.

    Up to 1.17 "delete slave" deleted only the FIRST of several
    image files. What was left lying back then belongs to nobody any more - and
    with a reused number it would turn up on the next one. Checking once at
    startup costs one listing and one query; it makes the promise
    "deleted is deleted" true for EXISTING installations, not only for new ones
    (finding Philine 2026-09-11).
    """
    try:
        cn = pymysql.connect(host=config['database']['hostname'],
                             user=config['database']['username'],
                             password=config['database']['password'],
                             database=config['database']['database'],
                             charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        with cn.cursor() as cur:
            cur.execute('SELECT slave_id FROM slaves')
            known = {str(r['slave_id']) for r in cur.fetchall()}
        cn.close()
    except pymysql.Error as e:
        logger.warning('orphan photo sweep skipped: %s', e)
        return
    gone = []
    # Both directories. An original without a participant is the same orphan
    # as a cut-out without one — and the one with more of the picture in it.
    for d, tag in ((PHOTO_DIR, ''), (ORIG_DIR, 'orig/')):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            stem, _, ext = f.rpartition('.')
            if not stem.isdigit() or ext.lower() not in ('jpg', 'jpeg', 'png'):
                continue
            if stem not in known:
                try:
                    os.remove(os.path.join(d, f))
                    gone.append(tag + f)
                except OSError as e:
                    logger.warning('orphan photo %s not removed: %s', tag + f, e)
    if gone:
        logger.info('orphan photos removed (no such participant): %s', ', '.join(gone))


audit.init(config['database'])
LB = logbook_mod.Logbook()          # read/write the logbook (own connection); channel only via the central unit
LB.init(config['database'])
mq = WebMQTT(logger)
mq.start(config)
_sweep_orphan_photos()


# --------------------------------------------------------------------------- #
# Database: one connection per request
def db():
    if 'db' not in g:
        g.db = pymysql.connect(host=config['database']['hostname'],
                               user=config['database']['username'],
                               password=config['database']['password'],
                               database=config['database']['database'],
                               charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    return g.db


def q(sql, params=(), one=False):
    with db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()


def x(sql, params=()):
    """Writing access; returns lastrowid."""
    with db().cursor() as cur:
        cur.execute(sql, params)
        return cur.lastrowid


@app.teardown_appcontext
def _close_db(exc):
    d = g.pop('db', None)
    if d is not None:
        try:
            if exc is None:
                d.commit()
            else:
                d.rollback()
        finally:
            d.close()


# --------------------------------------------------------------------------- #
# Login + CSRF
def login_required(f):
    @functools.wraps(f)
    def w(*a, **kw):
        if not session.get('user'):
            return redirect(url_for('login', next=request.path))
        if request.method == 'POST':
            tok = request.form.get('_csrf', '')
            if not tok or not hmac.compare_digest(tok, session.get('csrf', '')):
                abort(400, i18n._('CSRF-Token fehlt oder ist ungültig'))
        return f(*a, **kw)
    return w


# Database level: the web does NOT migrate (the central unit does that at startup), it only
# checks and shows a note when migrations are missing (re-checked at most every 60 s).
_db_pending = {'t': 0.0, 'versions': []}


def db_pending():
    import time as _time
    if _time.time() - _db_pending['t'] > 60:
        try:
            with db().cursor() as cur:
                _db_pending['versions'] = [v for v, _ in dbmigrate.pending(cur, 'sql')]
        except (pymysql.Error, dbmigrate.MigrationError, OSError) as e:
            app.logger.warning('db_pending: %s', e)
            _db_pending['versions'] = []
        _db_pending['t'] = _time.time()
    return _db_pending['versions']


@app.before_request
def _set_lang():
    """Language of this request: ?lang= is remembered in the session, otherwise the installation default."""
    want = (request.args.get('lang') or '').strip().lower()
    if want in i18n.LANGS:
        session['lang'] = want
    i18n.set_lang(session.get('lang'))


@app.context_processor
def _inject():
    return {'csrf': session.get('csrf', ''), 'user': session.get('user'),
            'models': devicemodels.MODELS, 'now': datetime.datetime.now(),
            'db_pending': db_pending() if session.get('user') else [],
            'lang': i18n.lang(), 'langs': i18n.choices()}


@app.template_global('_')
def _tr(text, **kw):
    """Translation in the templates: {{ _('Wochenplan') }} — the German text is the key."""
    return i18n._(text, **kw)


@app.template_global('lang_url')
def _lang_url(code):
    """The same page in another language - existing parameters are kept."""
    args = dict(request.args)
    args['lang'] = code
    try:
        return url_for(request.endpoint, **dict(request.view_args or {}), **args)
    except Exception:                      # noqa: BLE001 — the language choice must not blow up a page
        return '?lang=' + code


@app.template_global('cap_list')
def _cap_list(capabilities):
    """[(code, short, long)] of a capability set — for the display in the web interface."""
    return devicemodels.cap_list(capabilities)


@app.template_filter('ts')
def _fmt_ts(t):
    if not t:
        return '–'
    if isinstance(t, (int, float)):
        t = datetime.datetime.fromtimestamp(t if t < 1e11 else t / 1000)
    return t.strftime('%d.%m. %H:%M:%S')


@app.template_filter('jsonpretty')
def _jsonpretty(v):
    if v is None:
        return ''
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return v
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if hmac.compare_digest(pw, WEB_PASSWORD):
            keep_lang = session.get('lang')
            session.clear()
            if keep_lang:
                session['lang'] = keep_lang       # the language choice survives the login
            session['user'] = WEB_USER
            session['csrf'] = secrets.token_hex(16)
            audit.web('login', WEB_USER, kind='login', data={'ip': request.remote_addr})
            return redirect(_local_path(request.args.get('next')) or url_for('dashboard'))
        flash('Passwort falsch.', 'error')
        logger.warning('web: failed login from %s', request.remote_addr)
    return render_template('login.html')


def _local_path(nxt):
    """Only a path on THIS site may be the target after login — or nothing.

    `startswith('/')` used to be the whole check, and `//evil.example/` starts
    with a slash: a browser reads it as a protocol-relative address and leaves
    the site. So does `/\\evil.example`, because browsers straighten the
    backslash. A login link that sends the supervisor somewhere else the
    moment she has typed her password is exactly the kind of link one puts in
    an e-mail (finding Philine 2026-09-15).
    """
    if not nxt or not isinstance(nxt, str):
        return None
    if '\\' in nxt or not nxt.startswith('/') or nxt.startswith('//'):
        return None
    from urllib.parse import urlsplit
    parts = urlsplit(nxt)
    if parts.scheme or parts.netloc:
        return None
    return nxt


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    audit.web('logout', session.get('user'), kind='login')
    session.clear()
    return redirect(url_for('login'))


# --------------------------------------------------------------------------- #
# Dashboard / Live
def _device_names():
    return {r['dev_name']: r for r in q('SELECT dev_id, dev_name, dev_model, dev_address, dev_blocked FROM devices')}


def _health_inputs():
    """Today's restarts and safety events, per device, in two queries (doc 42 point 2).

    Two queries for the whole list — not two per device. The status fragment
    is polled every three seconds, and a page that grows a query per device
    is a page that gets slower with every device one adds.
    """
    boots, safety = {}, {}
    try:
        for b in q('SELECT db_device, db_reason, db_seen FROM device_boots WHERE db_seen >= CURDATE()'):
            boots.setdefault(b['db_device'], []).append(b)
    except Exception:                       # noqa: BLE001 — table missing (old DB)
        pass
    try:
        for r in q('SELECT al_device, COUNT(*) AS n FROM audit_log WHERE al_ts >= CURDATE()'
                   '  AND al_device IS NOT NULL AND al_action IN %s GROUP BY al_device',
                   (devicehealth.SAFETY_ACTIONS,)):
            safety[r['al_device']] = int(r['n'])
    except Exception:                       # noqa: BLE001
        pass
    return boots, safety


def _health_acks():
    """All acknowledgements, device -> key -> row. One query for the whole list.

    Same reason as `_health_inputs()` above: the status fragment is polled
    every three seconds, and one query per device is a page that gets slower
    with every device.
    """
    acks = {}
    try:
        for r in q('SELECT da_device, da_key, da_mark, da_by, da_at FROM device_acks'):
            acks.setdefault(r['da_device'], {})[r['da_key']] = {
                'mark': r['da_mark'], 'by': r['da_by'], 'at': r['da_at']}
    except Exception:                       # noqa: BLE001 — table missing (old DB)
        pass
    return acks


def _judge_health(d, boots, safety, acks=None):
    """Red or green for one snapshot entry, with the reasons."""
    row = d.get('db') or {}
    model = devicemodels.by_uuid((d.get('hello') or {}).get('model', ''))
    outdated = ''
    if d.get('hello') and model:
        v = fwversion.judge(d['hello'], model)
        outdated = v.reason if v.outdated else ''
    return devicehealth.judge(d, boots_today=boots.get(d['uuid']), safety_today=safety.get(d['uuid'], 0),
                              blocked_reason=(row.get('dev_blocked') or ''), outdated_reason=outdated,
                              acks=(acks or {}).get(d['uuid']))


def _unknown_rfid(snap):
    """The marker „last unknown tag" — but only as long as it is true.

    The central unit publishes it retained, and it stayed standing afterwards, even
    when the tag had long belonged to a slave: the hint „create as
    slave" then stood above exactly the slave who is already in the list
    below it (finding Philine 2026-09-11).

    If the tag is known by now, the marker is here not merely hidden,
    but DELETED. Hiding alone would bring it back at the next restart
    — it lies with the broker, not in the memory of this process.
    """
    u = snap.get('last_unknown_rfid')
    rfid = (u or {}).get('rfid')
    if not rfid:
        return None
    if q('SELECT slave_id FROM slaves WHERE slave_rfid=%s', (rfid,), one=True):
        mq.clear_unknown_rfid(session.get('user'), reason='rfid now known')
        snap['last_unknown_rfid'] = None
        return None
    return u


def _status_context():
    snap = mq.snapshot()
    snap['last_unknown_rfid'] = _unknown_rfid(snap)
    names = _device_names()
    boots, safety = _health_inputs()
    acks = _health_acks()
    for d in snap['devices']:
        row = names.get(d['uuid'])
        d['db'] = row
        model = devicemodels.by_uuid((d['hello'] or {}).get('model', ''))
        d['model'] = model.name if model else ((row or {}).get('dev_model') or '?')
        d['label'] = (row or {}).get('dev_address') or d['uuid'][:8]
        d['health'] = _judge_health(d, boots, safety, acks)
    snap['unknown'] = [d for d in snap['devices'] if d['db'] is None]
    snap['health_red'] = [d for d in snap['devices'] if d['db'] is not None and d['health'].red]
    snap['recent_audit'] = q('SELECT al_ts, al_source, al_kind, al_device, al_slave_id, al_action, al_data, al_user '
                             'FROM audit_log ORDER BY al_id DESC LIMIT 25')
    return snap


@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', s=_status_context())


@app.route('/fragment/status')
@login_required
def fragment_status():
    return render_template('_status.html', s=_status_context())


@app.route('/api/status')
@login_required
def api_status():
    s = mq.snapshot()
    return jsonify({'central_alive': s['central_alive'], 'mqtt': s['mqtt_connected'],
                    'devices': [{'uuid': d['uuid'], 'online': d['online'], 'state': d['state']} for d in s['devices']]})


@app.route('/device/<uuid>/cmd/<action>', methods=['POST'])
@login_required
def device_cmd(uuid, action):
    if action not in ('stop', 'identify'):
        abort(400)
    mq.send_command(uuid, action, ttl_ms=2000 if action == 'stop' else 5000, user=session['user'])
    flash(f'{action} an {uuid[:8]}… gesendet.', 'ok')
    return redirect(url_for('dashboard'))


@app.route('/device/<uuid>/ack', methods=['POST'])
@login_required
def device_ack(uuid):
    """Acknowledge one condition, or take an acknowledgement back (2.3.3, doc 55).

    THE MARK COMES FROM THE SERVER, NOT FROM THE FORM. The browser says WHICH
    condition is being acknowledged; what its content is at this moment is
    established here. A mark out of a form field would let somebody
    acknowledge a content the device never had — and the condition would then
    be quiet until it changed into exactly that.
    """
    key = (request.form.get('key') or '').strip()
    take_back = request.form.get('undo') == '1'
    if not key:
        abort(400)

    if take_back:
        x('DELETE FROM device_acks WHERE da_device = %s AND da_key = %s', (uuid, key))
        audit.web('device_ack_undo', session['user'], device=uuid, data={'key': key})
        flash(i18n._('Quittierung zurückgenommen.'), 'ok')
        return redirect(request.referrer or url_for('devices'))

    if key in devicehealth.NOT_ACKABLE:
        # The same rule as in the module. Here as well, and not only there,
        # because this is the door somebody could walk through with a
        # hand-written POST.
        flash(i18n._('Diese Bedingung lässt sich nicht quittieren.'), 'err')
        return redirect(request.referrer or url_for('devices'))

    # What is the content RIGHT NOW? Judge the device again, without the
    # acknowledgements, and take the mark of this condition from that.
    snap = mq.snapshot()
    dev = next((d for d in snap['devices'] if d['uuid'] == uuid), None)
    if dev is None:
        flash(i18n._('Gerät nicht gefunden.'), 'err')
        return redirect(request.referrer or url_for('devices'))
    dev['db'] = q('SELECT * FROM devices WHERE dev_name = %s', (uuid,), one=True)
    boots, safety = _health_inputs()
    h = _judge_health(dev, boots, safety)          # without acks: the raw state
    mark = next((m for k, _t, m in h.reasons if k == key), None)
    if mark is None:
        # Between the page being drawn and the click the condition can have
        # gone. Acknowledging it then would store a mark for something that is
        # not there — and cover the next occurrence.
        flash(i18n._('Die Bedingung besteht nicht mehr.'), 'ok')
        return redirect(request.referrer or url_for('devices'))

    x('INSERT INTO device_acks (da_device, da_key, da_mark, da_by, da_note)'
      ' VALUES (%s, %s, %s, %s, %s)'
      ' ON DUPLICATE KEY UPDATE da_mark = VALUES(da_mark), da_by = VALUES(da_by),'
      '   da_note = VALUES(da_note), da_at = CURRENT_TIMESTAMP',
      (uuid, key, mark, session['user'], (request.form.get('note') or '')[:191]))
    audit.web('device_ack', session['user'], device=uuid, data={'key': key, 'mark': mark})
    flash(i18n._('Quittiert: {k}', k=key), 'ok')
    return redirect(request.referrer or url_for('devices'))


@app.route('/stop-all', methods=['POST'])
@login_required
def stop_all():
    targets = mq.stop_all(user=session['user'])
    flash(f'Stopp an {len(targets)} Gerät(e) gesendet.', 'ok')
    return redirect(url_for('dashboard'))


@app.route('/emergency', methods=['POST'])
@login_required
def emergency():
    if request.form.get('confirm', '').strip().upper() != 'EMERGENCY':
        flash(i18n._('EMERGENCY nicht ausgelöst: Bestätigungswort fehlt.'), 'error')
        return redirect(url_for('dashboard'))
    mq.emergency(user=session['user'])
    logger.critical('web: EMERGENCY broadcast by %s from %s', session['user'], request.remote_addr)
    flash(i18n._('EMERGENCY an alle Geräte gesendet. Geräte bleiben bis zum Aus-/Einschalten gesperrt.'), 'error')
    return redirect(url_for('dashboard'))


# --------------------------------------------------------------------------- #
# Slaves
@app.route('/slaves')
@login_required
def slaves():
    rows = q('SELECT s.slave_id, s.slave_name, s.slave_rfid, s.slave_program, p.pro_name, '
             '       (SELECT COUNT(*) FROM slave_program sp WHERE sp.sp_slave = s.slave_id) AS n_prog, '
             '       (SELECT COUNT(*) FROM devtoslave x WHERE x.dts_slaveid = s.slave_id) AS n_dev '
             '  FROM slaves s LEFT JOIN program p ON p.pro_id = s.slave_program ORDER BY s.slave_name')
    # One marker per row: otherwise the supervisor would have to open every
    # page individually to see whose program does not match their devices.
    snap = mq.snapshot()
    snap['last_unknown_rfid'] = _unknown_rfid(snap)
    for r in rows:
        r['findings'] = programcheck.summary(_findings(r['slave_id'], snap))
    return render_template('slaves.html', rows=rows, snap=snap)


@app.route('/unknown-rfid/dismiss', methods=['POST'])
@login_required
def unknown_rfid_dismiss():
    """Clear the marker away by hand — for the tag that is to belong to
    nobody (a stranger's badge, a card from the drawer, a slip of the hand)."""
    had = mq.clear_unknown_rfid(session['user'])
    flash(i18n._('Merker für den unbekannten Tag {rfid} verworfen.',
                 rfid=(had or {}).get('rfid', '–')) if had
          else i18n._('Es lag kein unbekannter Tag vor.'), 'ok')
    return redirect(request.referrer or url_for('slaves'))


@app.route('/slaves/new', methods=['GET', 'POST'])
@app.route('/slaves/<int:sid>/edit', methods=['GET', 'POST'])
@login_required
def slave_edit(sid=None):
    row = q('SELECT * FROM slaves WHERE slave_id=%s', (sid,), one=True) if sid else None
    if sid and not row:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('slave_name', '').strip()
        rfid = request.form.get('slave_rfid', '').strip()
        if not name or not rfid:
            flash(i18n._('Name und RFID sind Pflicht.'), 'error')
        else:
            dup = q('SELECT slave_id FROM slaves WHERE slave_rfid=%s AND slave_id<>%s', (rfid, sid or 0), one=True)
            if dup:
                flash(i18n._('Diese RFID ist bereits einem anderen Sklaven zugeordnet.'), 'error')
            else:
                if sid:
                    x('UPDATE slaves SET slave_name=%s, slave_rfid=%s WHERE slave_id=%s', (name, rfid, sid))
                    audit.web('slave_update', session['user'], slave_id=sid, data={'name': name, 'rfid': rfid})
                else:
                    sid = x('INSERT INTO slaves (slave_name, slave_rfid, slave_program) VALUES (%s,%s,NULL)', (name, rfid))
                    audit.web('slave_create', session['user'], slave_id=sid, data={'name': name, 'rfid': rfid})
                db().commit()
                mq.notify_reload('slave', sid)
                flash('Gespeichert.', 'ok')
                return redirect(url_for('slave_detail', sid=sid))
    snap = mq.snapshot()
    return render_template('slave_edit.html', row=row, last_rfid=snap['last_unknown_rfid'])


@app.route('/slaves/<int:sid>')
@login_required
def slave_detail(sid):
    row = q('SELECT s.*, p.pro_name FROM slaves s LEFT JOIN program p ON p.pro_id=s.slave_program '
            'WHERE s.slave_id=%s', (sid,), one=True)
    if not row:
        abort(404)
    programs = q('SELECT p.pro_id, p.pro_name, p.pro_functions, '
                 '       (sp.sp_slave IS NOT NULL) AS assigned '
                 '  FROM program p LEFT JOIN slave_program sp ON sp.sp_program=p.pro_id AND sp.sp_slave=%s '
                 ' ORDER BY p.pro_name', (sid,))
    devices = q('SELECT d.dev_id, d.dev_name, d.dev_model, d.dev_address, d.dev_blocked, '
                '       (x.dts_id IS NOT NULL) AS assigned, '
                '       (SELECT GROUP_CONCAT(o.slave_name SEPARATOR ", ") FROM devtoslave y JOIN slaves o ON o.slave_id=y.dts_slaveid '
                '         WHERE y.dts_deviceid=d.dev_id AND y.dts_slaveid<>%s) AS others '
                '  FROM devices d LEFT JOIN devtoslave x ON x.dts_deviceid=d.dev_id AND x.dts_slaveid=%s '
                ' ORDER BY d.dev_address, d.dev_name', (sid, sid))
    online = {d['uuid']: d for d in mq.snapshot()['devices']}
    cal = _calibration(sid)
    for d in devices:
        m = devicemodels.by_code(d['dev_model'])
        d['model_name'] = m.name if m else None
        d['needs_cal'] = bool(m and m.has('mode_pet'))
        d['needs_depth'] = bool(m and m.has('depth_cal'))
        c = cal.get(d['dev_name'], {})
        d['needs_estim'] = bool(m and m.has('estim_routine'))
        d['cal_poses'] = sorted(c.keys())
        d['cal_sep'] = _separation(c)
        d['depth'] = c.get('depth')
        d['estim'] = c.get('estim')
        d['estim_pun'] = c.get('estim_punish')
        d['estim_rew'] = c.get('estim_reward')
    # The profile catalogue for the selection. All six, not only those of the
    # role: which frequency arrives is decided by the electrode placement, not
    # by the catalogue (doc 32 §3). The role stands next to it so that one sees
    # when one steps out of it.
    plist = [{'key': p.key, 'name': p.name, 'role': profiles.role_label(p.role)[0], 'role_key': p.role,
              'hz': '%g–%g Hz' % (p.hz_low, p.hz_high), 'desc': p.description}
             for p in profiles.PROFILES]
    # If her bridges do not agree on the profile, the central unit applies the
    # default of the role (logbook.estim_profile) - so on NO device what is
    # entered there. That has to stand on the page, otherwise somebody looks
    # for the fault on the device.
    prof_clash = {}
    for w, key in (('punish', 'estim_punish'), ('reward', 'estim_reward')):
        seen = {(cal.get(d['dev_name'], {}).get(key) or {}).get('sc_profile') or ''
                for d in devices if d['needs_estim'] and cal.get(d['dev_name'], {}).get(key)}
        prof_clash[w] = len(seen) > 1
    lbctx = _slave_logbook_context(sid) if _slave_logbook_context else None
    findings = programcheck.check_slave(q, sid, online, cal)
    # Calibration run (doc 33). `armed` stands in the database and means the
    # NEXT login; `running` comes from the session status of the central unit and
    # means: she is in it right now. `stale_h` is against forgetting — a flag
    # that has stood armed for days is a trap for the next login.
    calmode = {'armed': False, 'since': None, 'by': None, 'running': False, 'stale_h': 0}
    try:
        r = q('SELECT ss_cal_armed, ss_cal_armed_at, ss_cal_by FROM slave_settings WHERE ss_slave=%s',
              (sid,), one=True)
        if r and r['ss_cal_armed']:
            calmode.update({'armed': True, 'since': r['ss_cal_armed_at'], 'by': r['ss_cal_by']})
            if r['ss_cal_armed_at']:
                calmode['stale_h'] = int((datetime.datetime.now() - r['ss_cal_armed_at']).total_seconds() // 3600)
    except pymysql.Error:
        pass                                    # before migration 014
    # The session state of THIS slave — what the central unit is doing with
    # her right now. The "Overview" card lives off it: on looking, "what is
    # she doing now" is the first question (request Philine 2026-09-13).
    sess = None
    for s in ((mq.snapshot().get('session') or {}).get('slaves') or []):
        if s.get('slave_id') == sid:
            sess = s
            if s.get('calibration_mode'):
                calmode['running'] = True
    return render_template('slave_detail.html', row=row, programs=programs, devices=devices, online=online,
                           photo=_photo_file(sid), orig=_orig_size(sid),
                           lb=lbctx, findings=findings,
                           profile_list=plist, prof_clash=prof_clash, calmode=calmode,
                           sess=sess, finding_kinds=programcheck.SEVERITY,
                           today_iso=datetime.date.today().isoformat())


@app.route('/slaves/<int:sid>/assign', methods=['POST'])
@login_required
def slave_assign(sid):
    row = q('SELECT * FROM slaves WHERE slave_id=%s', (sid,), one=True)
    if not row:
        abort(404)
    prog_ids = {int(v) for v in request.form.getlist('program')}
    dev_ids = {int(v) for v in request.form.getlist('device')}
    active = request.form.get('active', '')
    active = int(active) if active.isdigit() else None
    if active is not None and active not in prog_ids:
        flash(i18n._('Das aktive Programm muss zugeordnet sein — Zuordnung ergänzt.'), 'warn')
        prog_ids.add(active)
    # Release the pointer first (composite FK), then the assignments, then set the pointer
    x('UPDATE slaves SET slave_program=NULL WHERE slave_id=%s', (sid,))
    x('DELETE FROM slave_program WHERE sp_slave=%s', (sid,))
    for pid in prog_ids:
        x('INSERT INTO slave_program (sp_slave, sp_program) VALUES (%s,%s)', (sid, pid))
    if active is not None:
        x('UPDATE slaves SET slave_program=%s WHERE slave_id=%s', (active, sid))
    x('DELETE FROM devtoslave WHERE dts_slaveid=%s', (sid,))
    for did in dev_ids:
        x('INSERT INTO devtoslave (dts_deviceid, dts_slaveid) VALUES (%s,%s)', (did, sid))
    audit.web('slave_assign', session['user'], slave_id=sid,
              data={'programs': sorted(prog_ids), 'active': active, 'devices': sorted(dev_ids)})
    db().commit()
    mq.notify_reload('slave', sid)
    flash(i18n._('Zuordnungen gespeichert — die Zentrale übernimmt sie sofort, auch bei angemeldetem Sklaven.'), 'ok')
    # The new combination may have produced overruns. That belongs here,
    # not only on the next visit to the page: here is the cause.
    total, active = programcheck.summary(_findings(sid))
    if total:
        flash(i18n._('Diese Zuordnung passt an {n} Stellen nicht zu den Geräten — {a} davon im aktiven Programm. '
                     'Die Tafel weiter unten sagt, wo.', n=total, a=active), 'warn')
    return redirect(url_for('slave_detail', sid=sid) + '#zuordnung')


@app.route('/slaves/<int:sid>/delete', methods=['POST'])
@login_required
def slave_delete(sid):
    row = q('SELECT slave_name FROM slaves WHERE slave_id=%s', (sid,), one=True)
    if not row:
        abort(404)
    x('UPDATE slaves SET slave_program=NULL WHERE slave_id=%s', (sid,))
    x('DELETE FROM devtoslave WHERE dts_slaveid=%s', (sid,))
    x('DELETE FROM slave_program WHERE sp_slave=%s', (sid,))
    # Logbook, weekly plans, rank, badges, privileges, calibration: ON DELETE CASCADE (migrations 004/005)
    x('DELETE FROM slaves WHERE slave_id=%s', (sid,))
    # Do not reuse the ID - belt and braces.
    #
    # CAUTION, a wrong justification stood here at first: "MariaDB computes
    # AUTO_INCREMENT at restart as MAX(id)+1". That held for older
    # versions; measured on MariaDB 10.11 it is NOT true - the counter
    # survives the restart, so a deleted number is by itself not handed
    # out again. Reuse can occur all the same: after restoring a
    # backup, after a table rebuild, on older
    # versions. This line costs nothing and closes the case.
    #
    # The REAL protection is a different one: after a deletion NOTHING
    # may exist any more that is named after this number. That is what
    # _photo_remove() here and _sweep_orphan_photos() at startup take
    # care of (finding Philine 2026-09-11).
    # Commit first, then touch the disk. The other way round the photo would
    # be gone and the slave still there on an error.
    db().commit()
    try:
        top = q('SELECT IFNULL(MAX(slave_id), 0) AS m FROM slaves', one=True)
        x('ALTER TABLE slaves AUTO_INCREMENT=%d' % (max(int(top['m']), int(sid)) + 1))
        db().commit()
    except pymysql.Error as e:
        # Must not be allowed to let the deletion fail: a reused number
        # is annoying, a slave that cannot be deleted is
        # worse.
        app.logger.warning('AUTO_INCREMENT not advanced after deleting slave %s: %s', sid, e)
    photos = _photo_remove(sid)
    audit.web('slave_delete', session['user'], slave_id=sid,
              data={'name': row['slave_name'], 'photos': photos})
    db().commit()
    mq.notify_reload('slave', sid)
    flash(i18n._('Sklaven „{name}" samt Logbuch, Plänen und Foto gelöscht.',
                 name=row['slave_name']), 'ok')
    return redirect(url_for('slaves'))


_slave_logbook_context = None     # set by libs/weblogbook.py on registration


def _photo_files(sid):
    """ALL image files of this slave, not the first one.

    The difference is no cosmetic flaw: whoever uses `_photo_file()` for
    deleting leaves the second one lying there. After a restart of the database
    MariaDB hands out the freed ID anew (AUTO_INCREMENT is computed as
    MAX(id)+1), and the next slave then gets to see the photo of the
    deleted one (finding Philine 2026-09-11).
    """
    out = []
    for ext in ('jpg', 'jpeg', 'png'):
        if os.path.exists(os.path.join(PHOTO_DIR, f'{sid}.{ext}')):
            out.append(f'{sid}.{ext}')
    return out


def _photo_file(sid):
    """The file that is DISPLAYED. For deleting take _photo_files()."""
    files = _photo_files(sid)
    return files[0] if files else None


def _orig_files(sid):
    """All originals of this slave — same reasoning as _photo_files()."""
    return [f'{sid}.{ext}' for ext in ('jpg', 'jpeg', 'png')
            if os.path.exists(os.path.join(ORIG_DIR, f'{sid}.{ext}'))]


def _orig_file(sid):
    files = _orig_files(sid)
    return files[0] if files else None


def _orig_size(sid):
    """(width, height) of the original after EXIF rotation, or None.

    The editor needs it to turn what it shows into pixels of the original.
    After the rotation, not before: a telephone photo is 4032x3024 in the file
    and 3024x4032 on the screen, and a box computed on the wrong one lands
    somewhere else entirely.
    """
    f = _orig_file(sid)
    if not f:
        return None
    try:
        from PIL import Image, ImageOps
        with Image.open(os.path.join(ORIG_DIR, f)) as im:
            return ImageOps.exif_transpose(im).size
    except Exception as e:                 # noqa: BLE001
        app.logger.warning('original %s cannot be read: %s', f, e)
        return None


def _render_crop(sid, box=None):
    """Write the 4:5 cut-out from the original into PHOTO_DIR. Returns the file name.

    `box` is (x, y, w) in PIXELS OF THE ORIGINAL — the browser says where it
    wants the section, not how high it is. The height follows from the ratio,
    here, so that there is one place that decides it. A browser that sends a
    height of its own would be a second opinion on a question that has only
    one answer.

    Without a box: the largest 4:5 section in the middle. That is the same
    thing web and display did by themselves up to now, so an upload without
    any editing changes nothing about what one sees — the editor adds a
    choice, it does not force one.
    """
    from PIL import Image, ImageOps

    src = _orig_file(sid)
    if not src:
        return None
    with Image.open(os.path.join(ORIG_DIR, src)) as im:
        # A photo from a telephone carries its orientation in EXIF instead of
        # in the pixels. Without this the section would be chosen on an
        # upright picture and cut out of a lying one.
        im = ImageOps.exif_transpose(im)
        ow, oh = im.size
        if box:
            x, y, w = box
        else:
            w = min(ow, int(round(oh * CROP_W / CROP_H)))
            x, y = (ow - w) // 2, (oh - int(round(w * CROP_H / CROP_W))) // 2
        h = int(round(w * CROP_H / CROP_W))
        # CLAMP, do not refuse. The numbers come from a browser, and a window
        # that was resized between drawing and clicking produces a box that is
        # a few pixels outside. Refusing that would be correct and useless.
        w = max(16, min(int(w), ow))
        h = max(20, min(int(round(w * CROP_H / CROP_W)), oh))
        w = int(round(h * CROP_W / CROP_H))
        x = max(0, min(int(x), ow - w))
        y = max(0, min(int(y), oh - h))
        im = im.crop((x, y, x + w, y + h))
        if im.width > CROP_MAX_W:
            im = im.resize((CROP_MAX_W, int(round(CROP_MAX_W * CROP_H / CROP_W))), Image.LANCZOS)
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        for old in _photo_files(sid):
            try:
                os.remove(os.path.join(PHOTO_DIR, old))
            except OSError:
                pass
        name = f'{sid}.jpg'
        im.save(os.path.join(PHOTO_DIR, name), 'JPEG', quality=90, optimize=True)
    return name


def _photo_remove(sid, keep_orig=False):
    """Remove every image file of this slave. Returns what is gone.

    THE ORIGINAL GOES TOO, unless a new cut-out is about to be written from it.
    „Deleted is deleted" was the whole point of _photo_files() in 2.1 — a
    second copy under orig/ that nobody sees would make that promise false
    again, and it would be the copy with the more of the picture in it.
    """
    gone = []
    for f in _photo_files(sid):
        try:
            os.remove(os.path.join(PHOTO_DIR, f))
            gone.append(f)
        except OSError as e:
            app.logger.warning('photo %s not removed: %s', f, e)
    if not keep_orig:
        for f in _orig_files(sid):
            try:
                os.remove(os.path.join(ORIG_DIR, f))
                gone.append('orig/' + f)
            except OSError as e:
                app.logger.warning('original %s not removed: %s', f, e)
    return gone


def _grade_file(g):
    for ext in ('png', 'jpg', 'svg'):
        if os.path.exists(os.path.join(GRADE_DIR, f'{g}.{ext}')):
            return f'{g}.{ext}'
    return None


@app.route('/slaves/<int:sid>/photo')
@login_required
def slave_photo(sid):
    f = _photo_file(sid)
    if not f:
        abort(404)
    return send_from_directory(PHOTO_DIR, f, max_age=0)


@app.route('/slaves/<int:sid>/photo', methods=['POST'])
@login_required
def slave_photo_upload(sid):
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    if request.form.get('remove'):
        gone = _photo_remove(sid)
        if gone:
            audit.web('photo_delete', session['user'], slave_id=sid, data={'photos': gone})
        flash('Foto entfernt.', 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#foto')
    up = request.files.get('photo')
    if not up or not up.filename:
        flash(i18n._('Keine Datei gewählt.'), 'error')
        return redirect(url_for('slave_detail', sid=sid) + '#foto')
    head = up.stream.read(12)
    up.stream.seek(0)
    if head.startswith(b'\xff\xd8'):
        ext = 'jpg'
    elif head.startswith(b'\x89PNG'):
        ext = 'png'
    else:
        flash('Nur JPEG oder PNG.', 'error')
        return redirect(url_for('slave_detail', sid=sid) + '#foto')
    # All old ones gone, not only the first: otherwise after a switch from
    # JPEG to PNG two files lie there, and which one is displayed is decided by
    # the order in _photo_files().
    _photo_remove(sid)
    # The upload lands in the ORIGINAL; what web and display read is the
    # cut-out that is rendered from it right afterwards (2.3.4).
    up.save(os.path.join(ORIG_DIR, f'{sid}.{ext}'))
    try:
        _render_crop(sid)
    except Exception as e:                 # noqa: BLE001
        # A file that says JPEG in its first two bytes and is not one gets
        # this far. Then the original goes as well: a participant with an
        # original and no picture is a state nothing in the interface shows.
        app.logger.warning('photo %s cannot be read: %s', sid, e)
        _photo_remove(sid)
        flash(i18n._('Das Bild lässt sich nicht lesen.'), 'error')
        return redirect(url_for('slave_detail', sid=sid) + '#foto')
    audit.web('photo_upload', session['user'], slave_id=sid, data={'file': f'{sid}.{ext}'})
    flash(i18n._('Foto gespeichert — unten lässt sich der Ausschnitt wählen.'), 'ok')
    return redirect(url_for('slave_detail', sid=sid) + '#foto')


@app.route('/slaves/<int:sid>/photo/orig')
@login_required
def slave_photo_orig(sid):
    """The original, for the editor. Not for the display — that reads the cut-out."""
    f = _orig_file(sid)
    if not f:
        abort(404)
    return send_from_directory(ORIG_DIR, f, max_age=0)


@app.route('/slaves/<int:sid>/photo/crop', methods=['POST'])
@login_required
def slave_photo_crop(sid):
    """Choose the section anew — always from the ORIGINAL, never from the cut-out.

    That is the whole reason the original is kept. Cutting a cut-out again
    loses a little more each time, and the way back to the wider picture is
    then gone for good.
    """
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    if not _orig_file(sid):
        flash(i18n._('Kein Original vorhanden — bitte neu hochladen.'), 'error')
        return redirect(url_for('slave_detail', sid=sid) + '#foto')
    try:
        box = (int(float(request.form['x'])), int(float(request.form['y'])),
               int(float(request.form['w'])))
    except (KeyError, ValueError):
        abort(400)
    try:
        _render_crop(sid, box)
    except Exception as e:                 # noqa: BLE001
        app.logger.warning('crop %s failed: %s', sid, e)
        flash(i18n._('Das Bild lässt sich nicht lesen.'), 'error')
        return redirect(url_for('slave_detail', sid=sid) + '#foto')
    audit.web('photo_crop', session['user'], slave_id=sid,
              data={'x': box[0], 'y': box[1], 'w': box[2]})
    flash(i18n._('Ausschnitt gespeichert — die Anzeige nutzt ihn ab sofort.'), 'ok')
    return redirect(url_for('slave_detail', sid=sid) + '#foto')


# --------------------------------------------------------------------------- #
# Calibration (pet poses) per slave and collar
def _calibration(sid, device=None):
    try:
        rows = q('SELECT sc_device, sc_pose, sc_x, sc_y, sc_z, sc_still, sc_profile, sc_ts FROM slave_calibration '
                 ' WHERE sc_slave=%s' + (' AND sc_device=%s' if device else ''),
                 (sid, device) if device else (sid,))
    except pymysql.Error:
        # Before migration 013 sc_profile does not exist. Leaving the page
        # empty because of that would be wrong here - then the ceiling would be
        # missing too, and the display „not calibrated" is the most dangerous
        # false report this page can make. So a second attempt without the column.
        try:
            rows = q('SELECT sc_device, sc_pose, sc_x, sc_y, sc_z, sc_still, sc_ts FROM slave_calibration '
                     ' WHERE sc_slave=%s' + (' AND sc_device=%s' if device else ''),
                     (sid, device) if device else (sid,))
        except pymysql.Error:
            return {}
    cal = {}
    for r in rows:
        cal.setdefault(r['sc_device'], {})[r['sc_pose']] = r
    return cal


def _separation(cal):
    """Angle between the two stored poses (quality of the calibration)."""
    import math
    if 'pet' not in cal or 'stand' not in cal:
        return None
    a, b = cal['pet'], cal['stand']
    dot = a['sc_x'] * b['sc_x'] + a['sc_y'] * b['sc_y'] + a['sc_z'] * b['sc_z']
    na = math.sqrt(a['sc_x'] ** 2 + a['sc_y'] ** 2 + a['sc_z'] ** 2)
    nb = math.sqrt(b['sc_x'] ** 2 + b['sc_y'] ** 2 + b['sc_z'] ** 2)
    if not na or not nb:
        return None
    return round(math.degrees(math.acos(max(-1.0, min(1.0, dot / (na * nb))))))


@app.route('/slaves/<int:sid>/calibrate/<device>')
@login_required
def calibrate(sid, device):
    row = q('SELECT * FROM slaves WHERE slave_id=%s', (sid,), one=True)
    dev = q('SELECT * FROM devices WHERE dev_name=%s', (device,), one=True)
    if not row or not dev:
        abort(404)
    cal = _calibration(sid, device).get(device, {})
    online = {d['uuid']: d for d in mq.snapshot()['devices']}.get(device)
    return render_template('calibrate.html', row=row, dev=dev, cal=cal, sep=_separation(cal),
                           online=online, seconds=3)


@app.route('/slaves/<int:sid>/calibrate/<device>/<action>', methods=['POST'])
@login_required
def calibrate_action(sid, device, action):
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    if action == 'stream':
        mq.send_command(device, 'imu_stream', {'seconds': 90}, user=session['user'])
        return jsonify(ok=True)
    if action in ('capture_pet', 'capture_stand'):
        secs = max(1, min(10, int(request.form.get('seconds', 3) or 3)))
        mq.capture_pose(device, sid, 'pet' if action == 'capture_pet' else 'stand', secs, session['user'])
        return jsonify(ok=True, seconds=secs)
    if action in ('delete_pet', 'delete_stand', 'delete'):
        if action == 'delete':
            x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s', (sid, device))
        else:
            x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s AND sc_pose=%s',
              (sid, device, action.split('_')[1]))
        db().commit()
        audit.web('calibration_delete', session['user'], slave_id=sid, device=device, data={'what': action})
        mq.notify_reload('slave', sid)
        flash(i18n._('Kalibrierung gelöscht.'), 'ok')
        return redirect(url_for('calibrate', sid=sid, device=device))
    abort(400)


@app.route('/slaves/<int:sid>/calibration_mode', methods=['POST'])
@login_required
def calibration_mode(sid):
    """The next login of this slave is a calibration run.

    WHAT FOR (request Philine 2026-09-12, doc 33): calibrating only works while
    logged in — otherwise the devices are not assigned to her and nothing can be
    measured. Logging in opens her day, however, and logging out early counts as
    capitulation (doc 14 §12.1). A quarter of an hour of sticking on electrodes
    would thus have cost her the day.

    THE FORM IS A FLAG FOR EXACTLY ONE LOGIN. It does not take effect at once,
    but at the next placing of the card, and logging out takes it back
    again. That way there is no state change in the middle of a run that
    somebody would have to clear up cleanly: the run is one from the start or
    none at all.
    """
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    on = bool(request.form.get('on'))
    try:
        x('INSERT INTO slave_settings (ss_slave, ss_cal_armed, ss_cal_armed_at, ss_cal_by) '
          'VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE ss_cal_armed=VALUES(ss_cal_armed), '
          'ss_cal_armed_at=VALUES(ss_cal_armed_at), ss_cal_by=VALUES(ss_cal_by)',
          (sid, 1 if on else 0, datetime.datetime.now() if on else None, session['user'] if on else None))
        db().commit()
    except pymysql.Error:
        flash(i18n._('Dafür fehlt Migration 014 — die Zentrale spielt sie beim nächsten Start ein.'), 'error')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    audit.web('calibration_mode', session['user'], slave_id=sid, data={'on': on})
    mq.notify_reload('slave', sid)
    if on:
        flash(i18n._('Kalibrierdurchgang scharf gestellt. Die nächste Anmeldung startet kein Programm und '
                     'keinen Tag; mit dem Abmelden ist der Durchgang zu Ende und sie kann sich normal '
                     'anmelden.'), 'warn')
    else:
        flash(i18n._('Kalibrierdurchgang abgeschaltet — die nächste Anmeldung läuft wieder normal.'), 'ok')
    return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')


@app.route('/slaves/<int:sid>/calibrate_estim/<device>', methods=['POST'])
@login_required
def calibrate_estim(sid, device):
    """E-stim: set the pulse height per channel that applies to THIS slave on
    THIS device.

    Unlike pose and depth, no sensor measures this. The height is a
    sensation, and only the wearer knows where it lies — the supervisor slowly
    turns up the raw output of the test page, and what comes out of that stands
    here. That is no weakness of the procedure, but the only honest
    way to get this value.

    It is stored as a percentage, not in device units: the V2 counts
    0..2047, the V3 0..200. The conversion is done by the firmware, which knows
    what it is attached to (doc 28 §5).
    """
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    if request.form.get('delete'):
        x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s AND sc_pose=%s', (sid, device, 'estim'))
        db().commit()
        audit.web('calibration_delete', session['user'], slave_id=sid, device=device, data={'pose': 'estim'})
        mq.notify_reload('slave', sid)
        flash(i18n._('E-Stim-Kalibrierung gelöscht — dieses Gerät gibt für sie nichts mehr aus.'), 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    try:
        a = max(0, min(100, int(request.form.get('a') or 0)))
        b = max(0, min(100, int(request.form.get('b') or 0)))
    except ValueError:
        flash(i18n._('Bitte zwei Zahlen zwischen 0 und 100 eintragen.'), 'err')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    if a <= 0 and b <= 0:
        flash(i18n._('Beide Kanäle auf 0 heißt: keine Ausgabe. Zum Abschalten lieber löschen.'), 'err')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    x('REPLACE INTO slave_calibration (sc_slave, sc_device, sc_pose, sc_x, sc_y, sc_z, sc_still) '
      'VALUES (%s,%s,%s,%s,%s,0,1)', (sid, device, 'estim', float(a), float(b)))
    db().commit()
    audit.web('calibration_estim', session['user'], slave_id=sid, device=device, data={'a': a, 'b': b})
    mq.notify_reload('slave', sid)
    flash(i18n._('E-Stim-Stärke gesetzt: A {a} %, B {b} %.', a=a, b=b), 'ok')
    return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')


@app.route('/slaves/<int:sid>/estim_levels/<device>', methods=['POST'])
@login_required
def estim_levels(sid, device):
    """The three pulse levels per slave — separately for punishment and reward.

    Percent OF HER CEILING, not of the device output: the same meaning that the
    device default 25/45/70 already had, only per person instead of per bridge
    (decision Philine 2026-09-12, doc 31). That keeps it at ONE calculation rule
    in the firmware, and the calibration remains the only upper limit.

    Separate for punishment and reward, because the two are meant to differ in
    character and not in height (doc 19 §3) — if the reward hung on the
    number of the punishment, exactly that would be undone again.

    SINCE DOC 32 the PROFILE stands here as well, and the three levels can be
    tried out individually. Both for the same reason: where the electrodes lie
    decides waveform AND height, and the form of the day shifts them
    („If 50 % was still bearable on Tuesday, it may on Thursday already
    not be so any more" — Philine 2026-09-12).

    The probe SAVES FIRST and then triggers. That is deliberate: could one
    try out a value without saving it, the installation would later run with
    a number nobody has ever felt. What she has felt then stands
    in the database exactly like that.
    """
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    what = 'reward' if request.form.get('what') == 'reward' else 'punish'
    pose = 'estim_' + what
    label = i18n._('Belohnung') if what == 'reward' else i18n._('Bestrafung')
    if request.form.get('delete'):
        x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s AND sc_pose=%s',
          (sid, device, pose))
        db().commit()
        audit.web('estim_levels_delete', session['user'], slave_id=sid, device=device, data={'pose': pose})
        mq.notify_reload('slave', sid)
        flash(i18n._('{what}: Stufen zurückgesetzt — es gilt wieder 25/45/70.', what=label), 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    try:
        lv = [max(1, min(100, int(request.form.get('l%d' % n) or 0))) for n in (1, 2, 3)]
    except ValueError:
        flash(i18n._('Bitte drei Zahlen zwischen 1 und 100 eintragen.'), 'err')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    # A level that lies below the previous one is no level. Better to reject
    # here than to let somebody brood later over a punishment that
    # was weaker at level 3 than at level 1.
    if not (lv[0] <= lv[1] <= lv[2]):
        flash(i18n._('Die Stufen müssen aufsteigend sein: Stufe 1 ≤ Stufe 2 ≤ Stufe 3.'), 'err')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    # The profile. An unknown key does NOT silently become the
    # default - it would come from a form that does not match this version,
    # and then the question is what else does not match.
    prof = (request.form.get('profile') or '').strip().lower()
    if prof and not profiles.get(prof):
        flash(i18n._('Dieses Profil kennt die Anlage nicht: {p}', p=prof), 'err')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    # THE ONE RULE THAT REMAINS FROM DOC 19 §3 AND MUST REMAIN:
    # punishment and reward must not have the SAME profile on one device.
    # Otherwise they are the same stimulus at two heights, and the whole
    # bookkeeping from doc 14 turns into noise for the slave. Which role a
    # profile has in the catalogue, by contrast, is no longer a prohibition -
    # that is decided by the anatomy (doc 32 §3).
    other = q('SELECT sc_profile FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s AND sc_pose=%s',
              (sid, device, 'estim_reward' if what == 'punish' else 'estim_punish'), one=True)
    other_key = ((other or {}).get('sc_profile') or '').strip()
    eff = prof or ('zweitakt' if what == 'reward' else 'stich')
    other_eff = other_key or ('stich' if what == 'reward' else 'zweitakt')
    if other and eff == other_eff:
        flash(i18n._('Bestrafung und Belohnung würden dasselbe Profil benutzen ({p}). Dann sind sie '
                     'derselbe Reiz in zwei Höhen — bitte für eine von beiden ein anderes wählen.',
                     p=profiles.get(eff).name if profiles.get(eff) else eff), 'err')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    x('REPLACE INTO slave_calibration (sc_slave, sc_device, sc_pose, sc_x, sc_y, sc_z, sc_still, sc_profile) '
      'VALUES (%s,%s,%s,%s,%s,%s,1,%s)', (sid, device, pose, float(lv[0]), float(lv[1]), float(lv[2]), prof))
    db().commit()
    audit.web('estim_levels', session['user'], slave_id=sid, device=device,
              data={'pose': pose, 'levels': lv, 'profile': prof})
    mq.notify_reload('slave', sid)

    # Try it out? Then the saving above has already happened, and the pulse
    # goes out with EXACTLY these values.
    try_lv = int(request.form.get('try') or 0)
    if try_lv in (1, 2, 3):
        return _estim_probe(sid, device, what, try_lv, lv[try_lv - 1], eff, label)

    flash(i18n._('{what}: Stufen gesetzt — {a} / {b} / {c} % ihrer Decke, Profil {p}.',
                 what=label, a=lv[0], b=lv[1], c=lv[2],
                 p=profiles.get(eff).name if profiles.get(eff) else eff), 'ok')
    return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')


def _estim_probe(sid, device, what, level, pct, prof, label):
    """Trigger a probe pulse — the same level that has just been saved.

    The probe is NO punishment. It does not go through the punishment channel
    of the slave, but directly to this one device, and it is reported as
    `estim_probe`, not as `punish`. In the logbook it therefore does
    not appear and costs nothing — doc 22: „A test is no achievement."

    It uses up the daily allowance of the device all the same. That one counts current through
    a human being, and the occasion changes nothing about that.
    """
    d = next((e for e in mq.snapshot()['devices'] if e['uuid'] == device), None)
    if not d or not d.get('online'):
        flash(i18n._('Gespeichert. Ausprobieren ging nicht: das Gerät ist nicht online.'), 'warn')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    # If a waveform is running there, the bridge rejects the probe with "busy"
    # - and that would look like success here. A message "level 3 is
    # running now", after which nothing comes, is on this device the worst
    # sort of false report: one then turns it up higher.
    #
    # ONLY ON A FRESH STATE. The state comes over MQTT and is between
    # two messages up to 30 s old; an old "estim: on" would otherwise block a
    # completely legitimate probe, and nobody would see why. The
    # bridge reports immediately on every change of isActive() - what is older
    # than a few seconds says nothing here any more.
    st = d.get('state') or {}
    fresh = d.get('age_s') is not None and d['age_s'] <= 8
    if fresh and (st.get('estim') == 'on' or st.get('raw')):
        flash(i18n._('Gespeichert. Ausprobieren ging nicht: das Gerät gibt gerade schon etwas aus. '
                     'Erst anhalten, dann proben.'), 'warn')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    # The ceiling of THIS device, not the lowest across all her bridges:
    # the probe is made on the device where the electrodes are stuck.
    cal = _calibration(sid, device).get(device, {}).get('estim')
    if not cal:
        flash(i18n._('Gespeichert. Ausprobieren ging nicht: für dieses Gerät ist ihre Stärke noch nicht '
                     'kalibriert — ohne sie gibt die Bridge nichts aus.'), 'warn')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    args = {'op': 'probe',
            'channel': 'b' if what == 'reward' else 'a',
            'profile': prof,
            'pct': max(1, min(100, int(pct))),
            'str_a': max(0, min(100, int(round(cal['sc_x'])))),
            'str_b': max(0, min(100, int(round(cal['sc_y'])))),
            'seconds': 2}
    mq.send_command(device, 'coyote', args, ttl_ms=8000, user=session['user'])
    audit.web('estim_probe', session['user'], kind='cmd', slave_id=sid, device=device,
              data=dict(args, level=level, what=what))
    flash(i18n._('Gespeichert — und Stufe {n} läuft jetzt: {p} auf Kanal {ch}, {pct} % ihrer Decke, 2 s. '
                 'Die Probe wird nicht gebucht.',
                 n=level, p=profiles.get(prof).name if profiles.get(prof) else prof,
                 ch='B' if what == 'reward' else 'A', pct=args['pct']), 'warn')
    return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')


@app.route('/slaves/<int:sid>/calibrate_depth/<device>', methods=['POST'])
@login_required
def calibrate_depth(sid, device):
    """Trainer: measure resting distance and greatest depth (pose 'depth')."""
    if not q('SELECT slave_id FROM slaves WHERE slave_id=%s', (sid,), one=True):
        abort(404)
    if request.form.get('delete'):
        x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s AND sc_pose=%s', (sid, device, 'depth'))
        db().commit()
        audit.web('calibration_delete', session['user'], slave_id=sid, device=device, data={'pose': 'depth'})
        mq.notify_reload('slave', sid)
        flash(i18n._('Tiefenkalibrierung gelöscht.'), 'ok')
        return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')
    secs = max(3, min(120, int(request.form.get('seconds', 15) or 15)))
    mq.capture_depth(device, sid, secs, session['user'])
    flash(f'Tiefe wird {secs} s gemessen — so tief wie möglich. Das Ergebnis erscheint nach dem Neuladen der Seite.', 'ok')
    return redirect(url_for('slave_detail', sid=sid) + '#kalibrierung')


def _imu_data(sid, device):
    snap = mq.imu_snapshot(device)
    cal = _calibration(sid, device).get(device, {})
    snap['stored'] = {p: {'x': c['sc_x'], 'y': c['sc_y'], 'z': c['sc_z'], 'still': c['sc_still'],
                          'ts': c['sc_ts'].strftime('%d.%m. %H:%M') if c.get('sc_ts') else ''} for p, c in cal.items()}
    snap['separation'] = _separation(cal)
    # Recompute the detection as in the collar (two poses, without hysteresis)
    imu = snap.get('imu') or {}
    if 'pet' in cal and 'stand' in cal and imu:
        import math
        def ang(c):
            dot = imu['ax'] * c['sc_x'] + imu['ay'] * c['sc_y'] + imu['az'] * c['sc_z']
            na = math.sqrt(imu['ax'] ** 2 + imu['ay'] ** 2 + imu['az'] ** 2)
            nb = math.sqrt(c['sc_x'] ** 2 + c['sc_y'] ** 2 + c['sc_z'] ** 2)
            return round(math.degrees(math.acos(max(-1.0, min(1.0, dot / (na * nb)))))) if na and nb else None
        ap, as_ = ang(cal['pet']), ang(cal['stand'])
        snap['angle_pet_db'], snap['angle_stand_db'] = ap, as_
        snap['classified'] = 'stand' if (ap is not None and as_ is not None and as_ < ap) else 'pet'
    return snap


@app.route('/api/imu/<int:sid>/<device>')
@login_required
def api_imu(sid, device):
    return jsonify(_imu_data(sid, device))


# --------------------------------------------------------------------------- #
# Programs + steps
ACTIONS_AVAILABLE = [a for a in actions.ACTIONS if a.implemented]


def _known_capabilities():
    """Capabilities for which a device is entered in the installation at all
    (decision Philine 2026-09-10: „take out all the points the Punisher knows no
    device for at all“). The basis is the capability class per model."""
    caps = set()
    for r in q('SELECT DISTINCT dev_model FROM devices') or []:
        m = devicemodels.by_code(r['dev_model'])
        if m:
            caps |= set(m.capabilities)
    return caps


def _slave_capabilities(sid):
    """Capabilities of the devices assigned to the slave."""
    caps = set()
    for r in q('SELECT d.dev_model FROM devtoslave x JOIN devices d ON d.dev_id=x.dts_deviceid '
               'WHERE x.dts_slaveid=%s', (sid,)) or []:
        m = devicemodels.by_code(r['dev_model'])
        if m:
            caps |= set(m.capabilities)
    return caps


def _actions_for(caps):
    """Actions that are possible with these capabilities (framework actions without
    a device capability always stay selectable)."""
    return [a for a in ACTIONS_AVAILABLE if not a.capability or a.capability in caps]


def _findings(sid, snap=None):
    """Where the program of this slave does not match her devices.

    The question can be answered neither on the program nor on the device alone — only
    here do the two meet (doc 24). The `snap` is passed through so that a
    list with ten slaves does not fetch the same state ten times.
    """
    online = {d['uuid']: d for d in (snap or mq.snapshot())['devices']}
    return programcheck.check_slave(q, sid, online, _calibration(sid))


@app.route('/programs')
@login_required
def programs():
    rows = q('SELECT p.pro_id, p.pro_name, p.pro_functions, '
             '       (SELECT COUNT(*) FROM program_commands c WHERE c.pc_program=p.pro_id) AS n_steps, '
             '       (SELECT COUNT(*) FROM slave_program sp WHERE sp.sp_program=p.pro_id) AS n_slaves, '
             '       (SELECT COUNT(*) FROM slaves s WHERE s.slave_program=p.pro_id) AS n_active '
             '  FROM program p ORDER BY p.pro_name')
    invalid = {}
    for r in rows:
        steps = q('SELECT pc_id, pc_command, pc_parameter FROM program_commands WHERE pc_program=%s ORDER BY pc_id', (r['pro_id'],))
        errs = actions.validate_program(steps)
        if errs:
            invalid[r['pro_id']] = errs
    return render_template('programs.html', rows=rows, invalid=invalid)


@app.route('/programs/new', methods=['GET', 'POST'])
@app.route('/programs/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
def program_edit(pid=None):
    row = q('SELECT * FROM program WHERE pro_id=%s', (pid,), one=True) if pid else None
    if pid and not row:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('pro_name', '').strip()
        desc = request.form.get('pro_functions', '').strip()
        if not name:
            flash(i18n._('Name ist Pflicht.'), 'error')
        elif q('SELECT pro_id FROM program WHERE pro_name=%s AND pro_id<>%s', (name, pid or 0), one=True):
            flash(i18n._('Ein Programm mit diesem Namen gibt es schon.'), 'error')
        else:
            if pid:
                x('UPDATE program SET pro_name=%s, pro_functions=%s WHERE pro_id=%s', (name, desc, pid))
                audit.web('program_update', session['user'], data={'pro_id': pid, 'name': name})
            else:
                pid = x('INSERT INTO program (pro_name, pro_functions) VALUES (%s,%s)', (name, desc))
                audit.web('program_create', session['user'], data={'pro_id': pid, 'name': name})
            db().commit()
            mq.notify_reload('program', pid)
            flash('Gespeichert.', 'ok')
            return redirect(url_for('program_detail', pid=pid))
    return render_template('program_edit.html', row=row)


def _param_fields(action):
    """Form fields of an action schema (for the step editor)."""
    out = []
    for p in action.params:
        out.append({'name': p.name, 'label': p.label or p.name, 'min': p.min, 'max': p.max,
                    'unit': p.unit, 'description': p.description, 'default': p.default,
                    'required': p.default is None, 'text': p.type is str,
                    # If the parameter points to a record, it becomes a
                    # selection list. Before, an empty number field stood here
                    # and one had to know the number of the waveform (Philine 2026-09-11).
                    'ref': p.ref or ''})
    return out


def _ref_lists(actions_list):
    """Selection lists for all reference parameters of these actions: {ref: [{id, name}]}."""
    refs = {}
    if not LB.routines_enabled:
        return refs
    for a in actions_list:
        for pp in a.params:
            if pp.ref and pp.ref not in refs:
                refs[pp.ref] = [{'id': r['ro_id'], 'name': r['ro_name']}
                                for r in routines.for_ref(q, pp.ref)]
    return refs


@app.route('/programs/<int:pid>')
@login_required
def program_detail(pid):
    row = q('SELECT * FROM program WHERE pro_id=%s', (pid,), one=True)
    if not row:
        abort(404)
    steps = q('SELECT pc_id, pc_command, pc_parameter FROM program_commands WHERE pc_program=%s ORDER BY pc_id', (pid,))
    for s in steps:
        a = actions.get(s['pc_command'])
        s['action'] = a
        try:
            s['params'] = actions.parse_params(a, s['pc_parameter']) if a else None
            s['error'] = None if a else 'unbekannte Aktion'
        except actions.ActionError as e:
            s['params'] = None
            s['error'] = str(e)
    users = q('SELECT s.slave_id, s.slave_name, (s.slave_program=%s) AS active FROM slaves s '
              'JOIN slave_program sp ON sp.sp_slave=s.slave_id WHERE sp.sp_program=%s ORDER BY s.slave_name', (pid, pid))
    # Device filter: the installation only knows devices with these capabilities
    known = _known_capabilities()
    avail = _actions_for(known)
    # Preview for one slave: his gaps are marked
    preview = request.args.get('for', type=int)
    pcaps = _slave_capabilities(preview) if preview else None
    for st in steps:
        a = st['action']
        st['missing'] = bool(a and a.capability and pcaps is not None and a.capability not in pcaps)
        st['unknown_dev'] = bool(a and a.capability and a.capability not in known)
    # Which assigned slaves cannot do the program completely?
    # Formerly only the missing capabilities; now the same check as on the
    # slave herself (doc 24), so that an overrun is visible from here
    # as well — the same query, the other direction.
    snap = mq.snapshot()
    online = {d['uuid']: d for d in snap['devices']}
    gaps = []
    for u in users:
        devs = programcheck.devices_of(q, u['slave_id'], online)
        f = programcheck.check_program(q, pid, devs, _calibration(u['slave_id']))
        if not f:
            continue
        miss = sorted({x['capability'] for x in f if x['kind'] == programcheck.NO_CAPABILITY})
        gaps.append({'slave_id': u['slave_id'], 'name': u['slave_name'],
                     'missing': [devicemodels.cap_label(c)[0] for c in miss],
                     'n': len(f), 'findings': f})
    sel = request.args.get('action') or (avail[0].code if avail else ACTIONS_AVAILABLE[0].code)
    schema = {a.code: _param_fields(a) for a in avail}
    return render_template('program_detail.html', row=row, steps=steps, users=users,
                           actions_list=avail, schema=schema, sel=sel, refs=_ref_lists(avail),
                           warnings=actions.program_warnings(steps), gaps=gaps,
                           preview=preview, all_slaves=q('SELECT slave_id, slave_name FROM slaves ORDER BY slave_name'),
                           capabilities_total=len(devicemodels.CAPABILITIES))


@app.route('/programs/<int:pid>/steps/add', methods=['POST'])
@login_required
def step_add(pid):
    if not q('SELECT pro_id FROM program WHERE pro_id=%s', (pid,), one=True):
        abort(404)
    code = request.form.get('action', '')
    action = actions.get(code)
    if not action or not action.implemented:
        flash('Unbekannte Aktion.', 'error')
        return redirect(url_for('program_detail', pid=pid))
    # Collect parameters in registry order; leave out empty optional ones at the end
    values = [request.form.get(f'p_{p.name}', '').strip() for p in action.params]
    while values and values[-1] == '' and action.params[len(values) - 1].default is not None:
        values.pop()
    for i, v in enumerate(values):
        if v == '' and action.params[i].default is not None:
            values[i] = str(action.params[i].default)      # gap in the middle -> enter the default
    raw = '|'.join(values)
    try:
        params = actions.parse_params(action, raw)
    except actions.ActionError as e:
        flash(f'Schritt nicht gespeichert: {e}', 'error')
        return redirect(url_for('program_detail', pid=pid, action=code))
    x('INSERT INTO program_commands (pc_program, pc_command, pc_parameter) VALUES (%s,%s,%s)', (pid, code, raw))
    audit.web('step_add', session['user'], data={'pro_id': pid, 'action': code, 'params': params})
    db().commit()
    mq.notify_reload('program', pid)
    flash(f'Schritt {action.name} hinzugefügt.', 'ok')
    return redirect(url_for('program_detail', pid=pid, action=code))


@app.route('/programs/<int:pid>/steps/<int:sid>/<op>', methods=['POST'])
@login_required
def step_op(pid, sid, op):
    step = q('SELECT * FROM program_commands WHERE pc_id=%s AND pc_program=%s', (sid, pid), one=True)
    if not step:
        abort(404)
    if op == 'delete':
        x('DELETE FROM program_commands WHERE pc_id=%s', (sid,))
        audit.web('step_delete', session['user'], data={'pro_id': pid, 'pc_id': sid, 'action': step['pc_command']})
        flash(i18n._('Schritt gelöscht.'), 'ok')
    elif op in ('up', 'down'):
        # Order = pc_id. Moving = swap contents with the neighbour (keys stay).
        if op == 'up':
            nb = q('SELECT * FROM program_commands WHERE pc_program=%s AND pc_id<%s ORDER BY pc_id DESC LIMIT 1', (pid, sid), one=True)
        else:
            nb = q('SELECT * FROM program_commands WHERE pc_program=%s AND pc_id>%s ORDER BY pc_id ASC LIMIT 1', (pid, sid), one=True)
        if nb:
            x('UPDATE program_commands SET pc_command=%s, pc_parameter=%s WHERE pc_id=%s',
              (nb['pc_command'], nb['pc_parameter'], sid))
            x('UPDATE program_commands SET pc_command=%s, pc_parameter=%s WHERE pc_id=%s',
              (step['pc_command'], step['pc_parameter'], nb['pc_id']))
            audit.web('step_move', session['user'], data={'pro_id': pid, 'pc_id': sid, 'op': op})
    else:
        abort(400)
    db().commit()
    mq.notify_reload('program', pid)
    return redirect(url_for('program_detail', pid=pid))


@app.route('/programs/<int:pid>/copy', methods=['POST'])
@login_required
def program_copy(pid):
    """Duplicate and adjust (project document 58 section 9).

    A variant of a sequence without laying down every step again — and the same
    pattern the waveforms have had all along, applied to one more screen. The
    copy is assigned to nobody: one that ran with somebody from the moment it
    was made would be a trap."""
    row = q('SELECT * FROM program WHERE pro_id=%s', (pid,), one=True)
    if not row:
        abort(404)
    name = (row['pro_name'] + ' ' + i18n._('(Kopie)'))[:120]
    n = 2
    while q('SELECT pro_id FROM program WHERE pro_name=%s', (name,), one=True):
        name = (row['pro_name'] + ' ' + i18n._('(Kopie)') + ' %d' % n)[:120]
        n += 1
    new = x('INSERT INTO program (pro_name, pro_functions) VALUES (%s,%s)', (name, row['pro_functions']))
    x('INSERT INTO program_commands (pc_program, pc_command, pc_parameter) '
      'SELECT %s, pc_command, pc_parameter FROM program_commands WHERE pc_program=%s ORDER BY pc_id',
      (new, pid))
    audit.web('program_copy', session['user'], data={'from': pid, 'pro_id': new, 'name': name})
    db().commit()
    flash(i18n._('„{name}“ angelegt — die Schritte sind mitgekommen, zugeordnet ist sie niemandem.',
                 name=name), 'ok')
    return redirect(url_for('program_detail', pid=new))


@app.route('/programs/<int:pid>/delete', methods=['POST'])
@login_required
def program_delete(pid):
    row = q('SELECT pro_name FROM program WHERE pro_id=%s', (pid,), one=True)
    if not row:
        abort(404)
    used = q('SELECT COUNT(*) AS n FROM slave_program WHERE sp_program=%s', (pid,), one=True)['n']
    if used:
        flash(f'Programm ist noch {used} Sklaven(n) zugeordnet — erst dort entfernen.', 'error')
        return redirect(url_for('program_detail', pid=pid))
    x('DELETE FROM program_commands WHERE pc_program=%s', (pid,))
    x('DELETE FROM program WHERE pro_id=%s', (pid,))
    audit.web('program_delete', session['user'], data={'pro_id': pid, 'name': row['pro_name']})
    db().commit()
    mq.notify_reload('program', pid)
    flash(f"Programm „{row['pro_name']}“ gelöscht.", 'ok')
    return redirect(url_for('programs'))


# --------------------------------------------------------------------------- #
# Devices
@app.route('/devices')
@login_required
def devices():
    rows = q('SELECT d.*, (SELECT COUNT(*) FROM devtoslave x WHERE x.dts_deviceid=d.dev_id) AS n_slaves '
             '  FROM devices d ORDER BY d.dev_address, d.dev_name')
    s = _status_context()
    online = {d['uuid']: d for d in s['devices']}
    # Show the functions per device (Philine 2026-09-10): capabilities of the model
    # (libs/devicemodels.py) and, if the device is online, the comparison with what
    # its firmware really reports in the hello.
    for r in rows:
        r['caps'] = _device_caps(r['dev_model'], online.get(r['dev_name']))
        m = devicemodels.by_code(r['dev_model'])
        r['model_name'] = m.name if m else None
    for d in s['unknown']:
        m = devicemodels.by_uuid((d['hello'] or {}).get('model', ''))
        d['caps'] = _device_caps(m.code if m else None, d)
    # Devices that have reported in and belong to no entry. They do
    # NOT come into the list by themselves — the same rule as with an unknown
    # RFID tag: it is displayed, assigning is done by hand.
    try:
        sightings = q("SELECT * FROM device_sightings s "
                      " WHERE NOT EXISTS (SELECT 1 FROM devices d WHERE d.dev_mac = s.ds_mac) "
                      " ORDER BY s.ds_last DESC LIMIT 20")
    except Exception:                       # noqa: BLE001 — table missing (old DB)
        sightings = []
    return render_template('devices.html', rows=rows, online=online,
                           unknown=s['unknown'], sightings=sightings,
                           rejected=s.get('rejected') or [])


def _device_caps(model_code, dev):
    """Capabilities for the display: [{code, short, long, state}]. state 'miss' = the
    model can do it, the running firmware does not report it (firmware too old);
    'extra' = the firmware reports more than the model knows (registry outdated)."""
    model = devicemodels.by_code(model_code) if model_code else None
    known = set(model.capabilities) if model else set()
    reported = None
    if dev and dev.get('online'):
        rep = ((dev.get('hello') or {}).get('capabilities')) or None
        if rep:
            reported = set(rep)
    # What the device reports as out of order (doc 42 point 4): a capability
    # whose every carrier is gone is shown as 'degraded' — still the model's,
    # not usable today. And the components themselves go on the list, so the
    # supervisor reads "cuff3" and not only "lock: degraded".
    degraded = devicemodels.degraded_of((dev or {}).get('hello')) if dev and dev.get('online') else None
    effective, _refused = devicemodels.effective_capabilities(model, reported, degraded) if model else (set(reported or ()), set())
    out = []
    for code, short, long_ in devicemodels.cap_list(known | (reported or set())):
        state = ''
        if reported is not None:
            if code not in reported:
                state = 'miss'
            elif code not in known:
                state = 'extra'
        if degraded and code in known and code not in effective and state == '':
            state = 'degraded'
        out.append({'code': code, 'short': short, 'long': long_, 'state': state})
    for comp in (degraded or []):
        out.append({'code': comp, 'short': comp, 'long': i18n._('vom Gerät abgemeldet'), 'state': 'comp'})
    return out


def _sighting(uuid):
    """The sighting belonging to this device_UUID, or None.

    Deliberately looked up freshly on the server instead of being carried
    through the form: the MAC is the identity of a device, and it has to come
    out of a SIGNED hello, not out of a browser. A hidden field would be a
    place where someone could hand a different one in.
    """
    if not uuid:
        return None
    try:
        return q('SELECT * FROM device_sightings WHERE ds_uuid=%s '
                 ' ORDER BY ds_last DESC LIMIT 1', (uuid,), one=True)
    except Exception:                       # noqa: BLE001 — table missing (old DB)
        return None


@app.route('/devices/new', methods=['GET', 'POST'])
@app.route('/devices/<int:did>/edit', methods=['GET', 'POST'])
@login_required
def device_edit(did=None):
    row = q('SELECT * FROM devices WHERE dev_id=%s', (did,), one=True) if did else None
    if did and not row:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('dev_name', '').strip()
        model = request.form.get('dev_model', '').strip()
        addr = request.form.get('dev_address', '').strip()
        if not name or not devicemodels.by_code(model):
            flash(i18n._('device_UUID und ein gültiges Modell sind Pflicht.'), 'error')
        elif q('SELECT dev_id FROM devices WHERE dev_name=%s AND dev_id<>%s', (name, did or 0), one=True):
            flash(i18n._('Diese device_UUID ist schon angelegt.'), 'error')
        else:
            # THE MAC COMES ALONG AT CREATION, NOT ONLY WITH THE NEXT HELLO.
            #
            # Until 2026-09-14 the row was created with the UUID alone. `dev_mac`
            # stayed empty until the device announced itself again — and a device
            # only sends `hello` when it CONNECTS. One that is already connected
            # sends none, so the row stayed without a MAC for as long as nobody
            # power-cycled it. Two things followed from that, and the second one
            # is the bad one:
            #
            #   * The device stood in BOTH boxes: created below, and above under
            #     "Seen, but not assigned to any device" with a Create button
            #     beside it — the sighting list looks for `dev_mac` (finding
            #     Philine 2026-09-14, three devices on the Pi).
            #   * The check for "a DIFFERENT chip under the same address" had
            #     nothing to compare with. It is the safeguard that stops a
            #     foreign chip from inheriting a human being's calibration, and
            #     it was silently off for every device created this way.
            #
            # The values are taken from the sighting, which comes out of a signed
            # hello. Only when they are missing: an UPDATE leaves an existing MAC
            # alone, it merely fills a gap.
            sight = _sighting(name)
            if did:
                x('UPDATE devices SET dev_name=%s, dev_model=%s, dev_address=%s WHERE dev_id=%s', (name, model, addr, did))
                if sight and not (row or {}).get('dev_mac'):
                    x('UPDATE devices SET dev_mac=%s, dev_chip=%s WHERE dev_id=%s',
                      (sight['ds_mac'], sight['ds_chip'], did))
                audit.web('device_update', session['user'], device=name, data={'model': model, 'label': addr})
            else:
                did = x("INSERT INTO devices (dev_name, dev_model, dev_address, dev_protocol,"
                        "  dev_mac, dev_chip) VALUES (%s,%s,%s,'MQTT',%s,%s)",
                        (name, model, addr,
                         (sight or {}).get('ds_mac') or None,
                         (sight or {}).get('ds_chip') or ''))
                audit.web('device_create', session['user'], device=name,
                          data={'model': model, 'label': addr,
                                'mac': (sight or {}).get('ds_mac') or ''})
            db().commit()
            mq.notify_reload('devices')
            flash('Gespeichert.', 'ok')
            return redirect(url_for('devices'))
    # Prefill from an unknown online device (?uuid=...) or from its sighting.
    #
    # The sighting is the second source and the important one: a device whose
    # hello arrived before anyone pressed "Create" is no longer in the snapshot
    # with a hello of its own, but its sighting is in the database.
    prefill = None
    uuid = request.args.get('uuid')
    if uuid and not row:
        for d in mq.snapshot()['devices']:
            if d['uuid'] == uuid:
                m = devicemodels.by_uuid((d['hello'] or {}).get('model', ''))
                prefill = {'dev_name': uuid, 'dev_model': m.code if m else '', 'dev_address': ''}
        s = _sighting(uuid)
        if s:
            m = devicemodels.by_uuid(s['ds_model'])
            prefill = prefill or {'dev_name': uuid, 'dev_model': m.code if m else '',
                                  'dev_address': ''}
            prefill['dev_mac'] = s['ds_mac']
            prefill['dev_chip'] = s['ds_chip']
    boots, boots_today, health = [], [], None
    if row:
        boots, boots_today = _device_boots(row['dev_name'])
        s = _status_context()
        for d in s['devices']:
            if d['uuid'] == row['dev_name']:
                health = d['health']
    settings, current, resp = (), {}, None
    if row:
        model = devicemodels.by_code(row['dev_model'])
        settings = devicemodels.settings_of(model)
        live = {d['uuid']: d for d in mq.snapshot()['devices']}.get(row['dev_name']) or {}
        # What the device reports as its envelope is what it currently HAS —
        # the same keys as the schema where the two overlap. The form starts
        # from there; a key the hello does not carry shows the default, marked.
        current = dict((live.get('hello') or {}).get('limits') or {})
        resp = live.get('config_response')
    return render_template('device_edit.html', row=row or prefill, is_new=row is None,
                           boots=boots, boots_today=boots_today, health=health,
                           uuid=(row or {}).get('dev_name', ''),
                           settings=settings, current=current, config_response=resp)


@app.route('/devices/<int:did>/config', methods=['POST'])
@login_required
def device_config(did):
    """Send settings to a device — the form is generated from the schema (doc 42 point 5).

    Nothing outside the schema is sent, and nothing outside its bounds. The
    device stores what it gets and answers per key; the answer is shown on the
    card. The change takes effect at the device's next start — `restart` asks
    for one, and the device refuses that while it is active.
    """
    row = q('SELECT * FROM devices WHERE dev_id=%s', (did,), one=True)
    if not row:
        abort(404)
    model = devicemodels.by_code(row['dev_model'])
    accepted, errors = devicemodels.validate_settings(model, request.form)
    for e in errors:
        flash(e, 'error')
    if not accepted and not errors:
        flash(i18n._('Nichts geändert.'), 'error')
    if accepted and not errors:
        restart = request.form.get('restart') == '1'
        mq.send_command(row['dev_name'], 'config', {'set': accepted, 'restart': restart},
                        ttl_ms=10000, user=session.get('user'))
        audit.web('device_config', session.get('user'), kind='cmd', device=row['dev_name'],
                  data={'set': accepted, 'restart': restart})
        flash(i18n._('Einstellungen gesendet — sie gelten ab dem nächsten Start des Geräts.'), 'ok')
    return redirect(url_for('device_edit', did=did) + '#einstellungen')


def _device_boots(uuid, limit=15):
    """(last starts, today's starts by reason) of one device — doc 42 point 1.

    The table may be missing on an installation whose database has not been
    migrated yet; then there is nothing to show, not an error page.
    """
    try:
        last = q('SELECT * FROM device_boots WHERE db_device=%s ORDER BY db_seen DESC LIMIT %s',
                 (uuid, int(limit)))
        today = q('SELECT db_reason AS reason, COUNT(*) AS n FROM device_boots '
                  ' WHERE db_device=%s AND db_seen >= CURDATE() GROUP BY db_reason ORDER BY n DESC',
                  (uuid,))
    except Exception:                       # noqa: BLE001 — table missing (old DB)
        return [], []
    return last, today


# --------------------------------------------------------------------------- #
# Test a device (decision Philine 2026-09-11). For setup, function check and
# bench: a single action on ONE device, without a slave.
#
# What is triggered here does NOT count: no run, no grade, no points,
# no punishment. It does stand in the audit log, though — a physical effect
# triggered by hand in particular has to be traceable (doc 03).
#
# The list of actions comes from the registry, filtered by what the
# RUNNING FIRMWARE reports. That way a new device appears here by itself,
# without a second list that goes stale.
@app.route('/device/<uuid>/test', methods=['GET', 'POST'])
@login_required
def device_test(uuid):
    # From the STATUS CONTEXT, not from the raw MQTT snapshot: that one knows
    # label, model name and the database entry that the page displays.
    d = next((x for x in _status_context()['devices'] if x['uuid'] == uuid), None)
    if not d:
        # Created, but never yet seen: show the page all the same — it then
        # says "offline". A 404 would be the wrong answer here, the device
        # does exist (just not on the air).
        row = q('SELECT * FROM devices WHERE dev_name=%s', (uuid,), one=True)
        if not row:
            abort(404)
        d = {'uuid': uuid, 'db': row, 'label': row['dev_address'] or uuid[:8],
             'model': (devicemodels.by_code(row['dev_model']).name
                       if devicemodels.by_code(row['dev_model']) else row['dev_model']),
             'hello': {}, 'state': {}, 'online': False, 'age_s': None, 'last_event': None}
    acts = devicetest.actions_for(d) if d['online'] else []

    if request.method == 'POST':
        code = request.form.get('action', '')
        action = actions.get(code)
        params = {}
        if action:
            for p in action.params:
                v = request.form.get('p_' + p.name, '')
                if v != '':
                    params[p.name] = v
        # Who does this device belong to right now? For e-stim that is no
        # ornament: the ceiling of the pulse height stands in HER calibration,
        # and without it the bridge outputs nothing (doc 28). Until now
        # devicetest.run() never got a calibration, because up to then only the
        # pose needed one - and that is measured on her own page.
        owner = q('SELECT s.slave_id FROM devtoslave t JOIN devices dv ON dv.dev_id=t.dts_deviceid '
                  '  JOIN slaves s ON s.slave_id=t.dts_slaveid WHERE dv.dev_name=%s LIMIT 1',
                  (uuid,), one=True)
        osid = int(owner['slave_id']) if owner else None
        ocal = _calibration(osid, uuid).get(uuid, {}) if osid else {}
        try:
            cut = []
            done = devicetest.run(mq, q, uuid, code, params, session['user'], lb=LB, dev=d,
                                  calibration=ocal, slave_id=osid, capped=cut)
            flash(i18n._('{action} an {dev} gesendet: {params}', action=(action.name if action else code),
                    dev=(d['label'] or uuid[:8]),
                    params=', '.join('%s=%s' % (k, v) for k, v in done.items()) or '—'), 'ok')
            # Capping happens quietly — saying it happens loudly (decision Philine
            # 2026-09-11: "Limit it and write it down alongside").
            for fld, want, sent, unit in cut:
                flash(i18n._('{field}: {wanted} lässt dieses Gerät nicht durch — gesendet wurden {sent}{unit}.',
                             field=fld, wanted=want, sent=sent,
                             unit=(' ' + unit) if unit else ''), 'warn')
        except (devicetest.TestError, actions.ActionError) as e:
            flash(str(e), 'error')
        return redirect(url_for('device_test', uuid=uuid))

    # Selection lists for parameters that point to a record: better to choose
    # than to guess numbers (Philine 2026-09-11).
    refs = {}
    if LB.routines_enabled:
        for a in acts:
            for p in a.params:
                if p.ref and p.ref not in refs:
                    refs[p.ref] = [{'id': r['ro_id'], 'name': r['ro_name'],
                                    'note': r['ro_note'] or ''} for r in routines.for_ref(q, p.ref)]
    # Envelope of EXACTLY THIS device: what the firmware reports, otherwise the model.
    _caps, _model = devicetest.capabilities_of(d)
    env = devicemodels.envelope_of(_model, (d.get('hello') or {}).get('limits'))
    view = [{'code': a.code, 'name': a.name, 'description': a.description,
             'physical': a.physical, 'blocking': a.blocking,
             'params': devicetest.form_spec(a, env)} for a in acts]
    return render_template('device_test.html', d=d, uuid=uuid, acts=view, refs=refs,
                           envelope=env, envelope_keys=devicemodels.ENVELOPE_KEYS,
                           reported=bool((d.get('hello') or {}).get('limits')),
                           model=_model)


@app.route('/device/<uuid>/coyote', methods=['POST'])
@login_required
def device_coyote(uuid):
    """Bind the e-stim bridge firmly to ONE Coyote — or release it again.

    In the museum several Coyotes lie within radio range; without a binding the
    bridge grabs whatever answers first. Until now that was only possible in the setup portal, that is
    only with the device in hand (request Philine 2026-09-11).

    The bridge stores the binding itself in NVS and disconnects an existing
    connection to another device immediately — one is meant to see from the result whether
    it takes hold, not only at the next restart.
    """
    d = next((x for x in _status_context()['devices'] if x['uuid'] == uuid), None)
    if not d or not d['online']:
        flash(i18n._('Gerät ist nicht online.'), 'error')
        return redirect(url_for('device_test', uuid=uuid))
    op = request.form.get('op', '')

    # Raw output: a known frame, past all of our arithmetic.
    # If the channels stay silent, that separates the suspects: if it stays
    # quiet HERE, it is not down to our conversion (finding Philine
    # 2026-09-11).
    if op in ('raw', 'raw_stop'):
        args = {'op': op}
        if op == 'raw':
            # The strength is the pulse height, and here a human types it in.
            # That is why it is mandatory and has NO default: the raw output is
            # the tool with which one feels one's way to the value that later
            # stands in the calibration (doc 28 §5).
            try:
                strength = int(request.form.get('strength'))
            except (TypeError, ValueError):
                flash(i18n._('Bitte eine Stärke in Prozent angeben — ohne sie gibt die Bridge nichts aus.'), 'error')
                return redirect(url_for('device_test', uuid=uuid))
            args.update({'channel': 1 if request.form.get('channel') == 'b' else 0,
                         'x': int(request.form.get('x') or 1),
                         'y': int(request.form.get('y') or 9),
                         'z': int(request.form.get('z') or 20),
                         'strength': max(0, min(100, strength)),
                         'seconds': max(1, min(30, int(request.form.get('seconds') or 5)))})
        mq.send_command(uuid, 'coyote', args, ttl_ms=8000, user=session['user'])
        audit.web('device_coyote_raw', session['user'], kind='cmd', device=uuid, data=args)
        if op == 'raw':
            flash(i18n._('Rohausgabe gestartet: Kanal {ch}, Stärke {str} %, X={x} Y={y} Z={z} ({us} µs) '
                         'für {s} s. Kommt DABEI nichts an, liegt es nicht an der Umrechnung — dann '
                         'sitzen die Elektroden nicht oder der Kanal ist ein anderer.',
                         ch=(request.form.get('channel') or 'a').upper(), x=args['x'], y=args['y'],
                         z=args['z'], us=args['z'] * 5, s=args['seconds'], str=args['strength']), 'warn')
        else:
            flash(i18n._('Rohausgabe beendet.'), 'ok')
        return redirect(url_for('device_test', uuid=uuid))

    args = {'op': 'unbind' if op == 'unbind' else 'bind'}
    addr = (request.form.get('address') or '').strip().lower()
    if op == 'bind' and addr:
        args['address'] = addr
    mq.send_command(uuid, 'coyote', args, ttl_ms=8000, user=session['user'])
    audit.web('device_bind', session['user'], kind='cmd', device=uuid, data=args)
    flash(i18n._('Bindung gesendet — der Zustand zeigt in ein paar Sekunden, '
                 'ob die Bridge verbunden ist.'), 'ok')
    return redirect(url_for('device_test', uuid=uuid))


@app.route('/devices/<int:did>/delete', methods=['POST'])
@login_required
def device_delete(did):
    row = q('SELECT * FROM devices WHERE dev_id=%s', (did,), one=True)
    if not row:
        abort(404)
    used = q('SELECT COUNT(*) AS n FROM devtoslave WHERE dts_deviceid=%s', (did,), one=True)['n']
    if used:
        flash(f'Gerät ist noch {used} Sklaven(n) zugeordnet — erst dort entfernen.', 'error')
        return redirect(url_for('devices'))
    x('DELETE FROM devices WHERE dev_id=%s', (did,))
    audit.web('device_delete', session['user'], device=row['dev_name'])
    db().commit()
    mq.notify_reload('devices')
    flash(i18n._('Gerät gelöscht.'), 'ok')
    return redirect(url_for('devices'))


# --------------------------------------------------------------------------- #
# Log
@app.route('/audit')
@login_required
def audit_view():
    f = {k: request.args.get(k, '').strip() for k in ('device', 'action', 'kind', 'source', 'slave', 'since')}
    where, params = [], []
    if f['device']:
        where.append('al_device LIKE %s'); params.append(f['device'] + '%')
    if f['action']:
        where.append('al_action LIKE %s'); params.append('%' + f['action'] + '%')
    if f['kind']:
        where.append('al_kind=%s'); params.append(f['kind'])
    if f['source']:
        where.append('al_source=%s'); params.append(f['source'])
    if f['slave'].isdigit():
        where.append('al_slave_id=%s'); params.append(int(f['slave']))
    if f['since']:
        where.append('al_ts >= %s'); params.append(f['since'])
    page = max(int(request.args.get('page', '1') or 1), 1)
    limit = 100
    sql = 'SELECT * FROM audit_log' + (' WHERE ' + ' AND '.join(where) if where else '') + \
          ' ORDER BY al_id DESC LIMIT %s OFFSET %s'
    rows = q(sql, tuple(params) + (limit + 1, (page - 1) * limit))
    more = len(rows) > limit
    names = _device_names()
    return render_template('audit.html', rows=rows[:limit], f=f, page=page, more=more, names=names)


@app.errorhandler(404)
def _404(e):
    return render_template('error.html', code=404, text='Nicht gefunden'), 404


@app.errorhandler(400)
def _400(e):
    return render_template('error.html', code=400, text=str(e)), 400


# --------------------------------------------------------------------------- #
# REST API for the Android app (libs/webapi.py)
import types  # noqa: E402
import webapi  # noqa: E402
_ctx = types.SimpleNamespace(
    q=q, x=x, db=db, mq=mq, config=config, WEB_PASSWORD=WEB_PASSWORD, WEB_USER=WEB_USER,
    PHOTO_DIR=PHOTO_DIR, photo_file=_photo_file, calibration=_calibration, separation=_separation,
    status_context=_status_context, imu_data=_imu_data, device_names=_device_names,
    LB=LB, GRADE_DIR=GRADE_DIR, grade_file=_grade_file, login_required=login_required, db_pending=db_pending,
    slave_capabilities=_slave_capabilities, known_capabilities=_known_capabilities)
webapi.register(app, _ctx)
import weblogbook  # noqa: E402  — logbook/leaderboard/weekly plan/report card/export (doc 14)
weblogbook.register(app, _ctx)
_slave_logbook_context = _ctx.slave_logbook_context


# --------------------------------------------------------------------------- #
if __name__ == '__main__':
    port = int(config['web'].get('port', 8080))
    logger.info('web: start on port %d', port)
    app.run(host=config['web'].get('bind', '0.0.0.0'), port=port, threaded=True, debug=False)
