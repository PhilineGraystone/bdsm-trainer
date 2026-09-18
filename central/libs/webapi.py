# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""REST API /api/v1 of the web interface — counterpart of the Android app (and
of every other client). Registers itself as a Flask blueprint in punisher-web.py.

Auth: POST /api/v1/login {password} -> {token}; afterwards header
      Authorization: Bearer <token>  (valid for 30 days, signed with the
      web secret; without a fixed [web] secret tokens expire on restart).
Responses: JSON; errors as {"ok": false, "error": "..."} with an HTTP status.

Device commands run through the action registry (libs/actions.py) and the same
translation as in the central unit (libs/torturedevice.py) — the app cannot
build a command that the central unit would not build as well.
"""

import functools
import hmac
import os
import time

from flask import Blueprint, jsonify, request, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
import pymysql

import actions
import audit
import devicetest
import devicemodels
import routines

TOKEN_MAX_AGE = 30 * 24 * 3600
BASE_ACTIONS = ('STOP', 'IDENTIFY')      # framework base commands, not in the registry


def register(app, ctx):
    """ctx: namespace with q, x, db, mq, config, WEB_PASSWORD, WEB_USER, PHOTO_DIR,
    photo_file(sid), calibration(sid, device=None), separation(cal),
    status_context(), imu_data(sid, device), device_names()."""
    api = Blueprint('api', __name__, url_prefix='/api/v1')
    ser = URLSafeTimedSerializer(app.secret_key, salt='punisher-api')

    def err(msg, code=400):
        return jsonify(ok=False, error=msg), code

    def current_user():
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            try:
                data = ser.loads(auth[7:], max_age=TOKEN_MAX_AGE)
                return data.get('u')
            except (BadSignature, SignatureExpired):
                return None
        from flask import session
        return session.get('user')

    def auth_required(f):
        @functools.wraps(f)
        def w(*a, **kw):
            u = current_user()
            if not u:
                return err('nicht angemeldet', 401)
            request.api_user = u
            return f(*a, **kw)
        return w

    def body():
        j = request.get_json(silent=True)
        return j if isinstance(j, dict) else {}

    ctx.api_auth_required = auth_required      # further API blueprints (libs/weblogbook.py) use the same auth

    # --- Login --------------------------------------------------------------------
    @api.route('/login', methods=['POST'])
    def login():
        pw = body().get('password', '')
        if not hmac.compare_digest(str(pw), ctx.WEB_PASSWORD):
            audit.web('api_login_failed', None, kind='login', data={'ip': request.remote_addr})
            return err('Passwort falsch', 401)
        tok = ser.dumps({'u': ctx.WEB_USER, 't': int(time.time())})
        audit.web('api_login', ctx.WEB_USER, kind='login', data={'ip': request.remote_addr})
        return jsonify(ok=True, token=tok, user=ctx.WEB_USER, expires_s=TOKEN_MAX_AGE)

    @api.route('/ping')
    @auth_required
    def ping():
        return jsonify(ok=True, user=request.api_user, ts=int(time.time()))

    # --- Status / Registry ----------------------------------------------------------
    @api.route('/status')
    @auth_required
    def status():
        s = ctx.status_context()
        devs = []
        for d in s['devices']:
            # Same fallback chain as the test page: hello, then the model named
            # in hello, then the model from the database. After a restart a
            # device can already count as online without its hello having
            # arrived, and then only the database knows what it is.
            _caps, model = devicetest.capabilities_of(d)
            devs.append({
                'uuid': d['uuid'], 'label': d['label'], 'in_db': d['db'] is not None,
                'model': d['model'], 'model_code': model.code if model else ((d['db'] or {}).get('dev_model')),
                'capabilities': (d['hello'] or {}).get('capabilities') or (sorted(model.capabilities) if model else []),
                'fw': (d['hello'] or {}).get('fw_version') or d['state'].get('fw'),
                # Envelope of THIS device: what its firmware reports, else the
                # model catalogue. A caller that builds a form gets the real
                # ceiling instead of the registry one (decision Philine 2026-09-11).
                'limits': devicemodels.envelope_of(model, (d['hello'] or {}).get('limits')),
                'limits_reported': bool((d['hello'] or {}).get('limits')),
                'online': d['online'], 'age_s': d['age_s'], 'state': d['state'],
                'last_event': d['last_event'],
            })
        return jsonify(ok=True, central_alive=s['central_alive'], central_hb_age=s['central_hb_age'],
                       mqtt=s['mqtt_connected'], devices=devs, slaves=(s.get('session') or {}).get('slaves', []),
                       db_pending=ctx.db_pending() if hasattr(ctx, 'db_pending') else [],
                       events=[{'t': e['t'], 'device': e['device'], 'event': e['event'], 'data': e['data']} for e in s['events'][:30]],
                       last_unknown_rfid=s['last_unknown_rfid'],
                       audit=[{'ts': r['al_ts'].isoformat(sep=' ', timespec='seconds'), 'source': r['al_source'],
                               'kind': r['al_kind'], 'device': r['al_device'], 'slave_id': r['al_slave_id'],
                               'action': r['al_action'], 'user': r['al_user']} for r in s['recent_audit']])

    @api.route('/actions')
    @auth_required
    def actions_schema():
        return jsonify(ok=True, actions=actions.schema(),
                       base=[{'code': 'STOP', 'name': 'Stopp', 'description': 'Sicherer Zustand, Gerät bleibt bedienbar'},
                             {'code': 'IDENTIFY', 'name': 'Blinken', 'description': 'Gerät macht sich bemerkbar'}],
                       models=[{'code': m.code, 'name': m.name, 'capabilities': sorted(m.capabilities),
                                'envelope': devicemodels.envelope_of(m)} for m in devicemodels.MODELS],
                       envelope_keys=devicemodels.ENVELOPE_KEYS)

    # --- Device commands ---------------------------------------------------------------
    @api.route('/devices/<uuid>/action', methods=['POST'])
    @auth_required
    def device_action(uuid):
        # The same path that the test page in the web interface takes as well
        # (libs/devicetest.py). Two implementations of one and the same
        # procedure drift apart, and they do so where it hurts: at the limits.
        j = body()
        code = str(j.get('code', '')).upper()
        sid = j.get('slave_id')
        cal = ctx.calibration(int(sid), uuid).get(uuid, {}) if (sid and code == 'PET') else None
        cut = []
        try:
            p = devicetest.run(ctx.mq, ctx.q, uuid, code, j.get('params') or {},
                               request.api_user, lb=getattr(ctx, 'LB', None),
                               calibration=cal, slave_id=sid, capped=cut)
        except devicetest.TestError as e:
            return err(str(e), 409)
        except actions.ActionError as e:
            return err(str(e))
        # `capped` names the values this device would not take. Without it the
        # caller sees a success and a device doing something else. The field is
        # always present (empty list = nothing was cut), so an older app that
        # ignores it keeps working unchanged (mobile app stays on 1.1).
        return jsonify(ok=True, sent=code, params=p,
                       capped=[{'field': f, 'wanted': w, 'sent': s, 'unit': u}
                               for f, w, s, u in cut])

    @api.route('/stop-all', methods=['POST'])
    @auth_required
    def stop_all():
        targets = ctx.mq.stop_all(user=request.api_user)
        return jsonify(ok=True, devices=targets)

    @api.route('/emergency', methods=['POST'])
    @auth_required
    def emergency():
        if str(body().get('confirm', '')).strip().upper() != 'EMERGENCY':
            return err('Bestätigungswort fehlt')
        ctx.mq.emergency(user=request.api_user)
        return jsonify(ok=True)

    # --- Slaves -------------------------------------------------------------------------
    def slave_row(sid):
        return ctx.q('SELECT s.slave_id, s.slave_name, s.slave_rfid, s.slave_program, p.pro_name '
                     '  FROM slaves s LEFT JOIN program p ON p.pro_id=s.slave_program WHERE s.slave_id=%s', (sid,), one=True)

    def slave_full(sid):
        row = slave_row(sid)
        if not row:
            return None
        row['programs'] = ctx.q('SELECT p.pro_id, p.pro_name, p.pro_functions, (sp.sp_slave IS NOT NULL) AS assigned '
                                '  FROM program p LEFT JOIN slave_program sp ON sp.sp_program=p.pro_id AND sp.sp_slave=%s '
                                ' ORDER BY p.pro_name', (sid,))
        devs = ctx.q('SELECT d.dev_id, d.dev_name, d.dev_model, d.dev_address, (x.dts_id IS NOT NULL) AS assigned, '
                     '       (SELECT GROUP_CONCAT(o.slave_name SEPARATOR ", ") FROM devtoslave y JOIN slaves o ON o.slave_id=y.dts_slaveid '
                     '         WHERE y.dts_deviceid=d.dev_id AND y.dts_slaveid<>%s) AS others '
                     '  FROM devices d LEFT JOIN devtoslave x ON x.dts_deviceid=d.dev_id AND x.dts_slaveid=%s '
                     ' ORDER BY d.dev_address, d.dev_name', (sid, sid))
        cal = ctx.calibration(sid)
        for d in devs:
            m = devicemodels.by_code(d['dev_model'])
            d['needs_cal'] = bool(m and m.has('mode_pet'))
            c = cal.get(d['dev_name'], {})
            d['cal_poses'] = sorted(c.keys())
            d['cal_sep'] = ctx.separation(c)
            d['assigned'] = bool(d['assigned'])
        for p in row['programs']:
            p['assigned'] = bool(p['assigned'])
        row['devices'] = devs
        row['photo'] = ctx.photo_file(sid) is not None
        return row

    @api.route('/slaves')
    @auth_required
    def slaves():
        rows = ctx.q('SELECT s.slave_id, s.slave_name, s.slave_rfid, s.slave_program, p.pro_name, '
                     '       (SELECT COUNT(*) FROM slave_program sp WHERE sp.sp_slave=s.slave_id) AS n_prog, '
                     '       (SELECT COUNT(*) FROM devtoslave x WHERE x.dts_slaveid=s.slave_id) AS n_dev '
                     '  FROM slaves s LEFT JOIN program p ON p.pro_id=s.slave_program ORDER BY s.slave_name')
        for r in rows:
            r['photo'] = ctx.photo_file(r['slave_id']) is not None
        return jsonify(ok=True, slaves=rows)

    @api.route('/slaves', methods=['POST'])
    @auth_required
    def slave_create():
        j = body()
        name, rfid = str(j.get('slave_name', '')).strip(), str(j.get('slave_rfid', '')).strip()
        if not name or not rfid:
            return err('Name und RFID sind Pflicht')
        if ctx.q('SELECT slave_id FROM slaves WHERE slave_rfid=%s', (rfid,), one=True):
            return err('RFID bereits vergeben', 409)
        sid = ctx.x('INSERT INTO slaves (slave_name, slave_rfid, slave_program) VALUES (%s,%s,NULL)', (name, rfid))
        ctx.db().commit()
        audit.web('slave_create', request.api_user, slave_id=sid, data={'name': name, 'rfid': rfid})
        ctx.mq.notify_reload('slave', sid)
        return jsonify(ok=True, slave=slave_full(sid)), 201

    @api.route('/slaves/<int:sid>')
    @auth_required
    def slave_get(sid):
        row = slave_full(sid)
        return jsonify(ok=True, slave=row) if row else err('nicht gefunden', 404)

    @api.route('/slaves/<int:sid>', methods=['PUT'])
    @auth_required
    def slave_update(sid):
        if not slave_row(sid):
            return err('nicht gefunden', 404)
        j = body()
        name, rfid = str(j.get('slave_name', '')).strip(), str(j.get('slave_rfid', '')).strip()
        if not name or not rfid:
            return err('Name und RFID sind Pflicht')
        if ctx.q('SELECT slave_id FROM slaves WHERE slave_rfid=%s AND slave_id<>%s', (rfid, sid), one=True):
            return err('RFID bereits vergeben', 409)
        ctx.x('UPDATE slaves SET slave_name=%s, slave_rfid=%s WHERE slave_id=%s', (name, rfid, sid))
        ctx.db().commit()
        audit.web('slave_update', request.api_user, slave_id=sid, data={'name': name, 'rfid': rfid})
        ctx.mq.notify_reload('slave', sid)
        return jsonify(ok=True, slave=slave_full(sid))

    @api.route('/slaves/<int:sid>', methods=['DELETE'])
    @auth_required
    def slave_delete(sid):
        row = slave_row(sid)
        if not row:
            return err('nicht gefunden', 404)
        ctx.x('UPDATE slaves SET slave_program=NULL WHERE slave_id=%s', (sid,))
        ctx.x('DELETE FROM devtoslave WHERE dts_slaveid=%s', (sid,))
        ctx.x('DELETE FROM slave_program WHERE sp_slave=%s', (sid,))
        ctx.x('DELETE FROM slaves WHERE slave_id=%s', (sid,))
        ctx.db().commit()
        audit.web('slave_delete', request.api_user, slave_id=sid, data={'name': row['slave_name']})
        ctx.mq.notify_reload('slave', sid)
        return jsonify(ok=True)

    @api.route('/slaves/<int:sid>/assign', methods=['PUT'])
    @auth_required
    def slave_assign(sid):
        if not slave_row(sid):
            return err('nicht gefunden', 404)
        j = body()
        prog_ids = {int(v) for v in (j.get('programs') or [])}
        dev_ids = {int(v) for v in (j.get('devices') or [])}
        active = j.get('active')
        active = int(active) if active not in (None, '', 0, '0') else None
        if active is not None:
            prog_ids.add(active)
        ctx.x('UPDATE slaves SET slave_program=NULL WHERE slave_id=%s', (sid,))
        ctx.x('DELETE FROM slave_program WHERE sp_slave=%s', (sid,))
        for pid in prog_ids:
            ctx.x('INSERT INTO slave_program (sp_slave, sp_program) VALUES (%s,%s)', (sid, pid))
        if active is not None:
            ctx.x('UPDATE slaves SET slave_program=%s WHERE slave_id=%s', (active, sid))
        ctx.x('DELETE FROM devtoslave WHERE dts_slaveid=%s', (sid,))
        for did in dev_ids:
            ctx.x('INSERT INTO devtoslave (dts_deviceid, dts_slaveid) VALUES (%s,%s)', (did, sid))
        ctx.db().commit()
        audit.web('slave_assign', request.api_user, slave_id=sid,
                  data={'programs': sorted(prog_ids), 'active': active, 'devices': sorted(dev_ids)})
        ctx.mq.notify_reload('slave', sid)
        return jsonify(ok=True, slave=slave_full(sid))

    @api.route('/slaves/<int:sid>/photo')
    @auth_required
    def slave_photo(sid):
        f = ctx.photo_file(sid)
        if not f:
            return err('kein Foto', 404)
        return send_from_directory(ctx.PHOTO_DIR, f, max_age=0)

    @api.route('/slaves/<int:sid>/photo', methods=['POST', 'DELETE'])
    @auth_required
    def slave_photo_set(sid):
        if not slave_row(sid):
            return err('nicht gefunden', 404)
        old = ctx.photo_file(sid)
        if request.method == 'DELETE':
            if old:
                os.remove(os.path.join(ctx.PHOTO_DIR, old))
                audit.web('photo_delete', request.api_user, slave_id=sid)
            return jsonify(ok=True)
        up = request.files.get('photo')
        if not up or not up.filename:
            return err('Datei fehlt (Feld photo)')
        head = up.stream.read(12)
        up.stream.seek(0)
        ext = 'jpg' if head.startswith(b'\xff\xd8') else ('png' if head.startswith(b'\x89PNG') else None)
        if not ext:
            return err('nur JPEG oder PNG')
        if old:
            os.remove(os.path.join(ctx.PHOTO_DIR, old))
        up.save(os.path.join(ctx.PHOTO_DIR, f'{sid}.{ext}'))
        audit.web('photo_upload', request.api_user, slave_id=sid, data={'file': f'{sid}.{ext}'})
        return jsonify(ok=True, file=f'{sid}.{ext}')

    # --- Calibration --------------------------------------------------------------------------
    @api.route('/slaves/<int:sid>/calibration')
    @auth_required
    def calibration_get(sid):
        cal = ctx.calibration(sid)
        out = {dev: {pose: {'x': c['sc_x'], 'y': c['sc_y'], 'z': c['sc_z'], 'still': bool(c['sc_still']),
                            'ts': c['sc_ts'].isoformat(sep=' ', timespec='minutes') if c.get('sc_ts') else None}
                     for pose, c in poses.items()} | {'separation': ctx.separation(poses)}
               for dev, poses in cal.items()}
        return jsonify(ok=True, calibration=out)

    @api.route('/slaves/<int:sid>/calibrate/<device>/stream', methods=['POST'])
    @auth_required
    def calibrate_stream(sid, device):
        ctx.mq.send_command(device, 'imu_stream', {'seconds': int(body().get('seconds', 90) or 90)}, user=request.api_user)
        return jsonify(ok=True)

    @api.route('/slaves/<int:sid>/calibrate/<device>/capture', methods=['POST'])
    @auth_required
    def calibrate_capture(sid, device):
        if not slave_row(sid):
            return err('nicht gefunden', 404)
        pose = str(body().get('pose', 'pet'))
        if pose not in ('pet', 'stand'):
            return err('pose: pet|stand')
        secs = max(1, min(10, int(body().get('seconds', 3) or 3)))
        ctx.mq.capture_pose(device, sid, pose, secs, request.api_user)
        return jsonify(ok=True, seconds=secs)

    @api.route('/slaves/<int:sid>/calibrate/<device>/depth', methods=['POST'])
    @auth_required
    def calibrate_depth(sid, device):
        """Trainer: measure resting distance / greatest depth (posture 'depth', doc 14)."""
        if not slave_row(sid):
            return err('nicht gefunden', 404)
        secs = max(3, min(120, int(body().get('seconds', 15) or 15)))
        ctx.mq.capture_depth(device, sid, secs, request.api_user)
        return jsonify(ok=True, seconds=secs)

    @api.route('/slaves/<int:sid>/calibration/<device>', methods=['DELETE'])
    @api.route('/slaves/<int:sid>/calibration/<device>/<pose>', methods=['DELETE'])
    @auth_required
    def calibrate_delete(sid, device, pose=None):
        if pose:
            ctx.x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s AND sc_pose=%s', (sid, device, pose))
        else:
            ctx.x('DELETE FROM slave_calibration WHERE sc_slave=%s AND sc_device=%s', (sid, device))
        ctx.db().commit()
        audit.web('calibration_delete', request.api_user, slave_id=sid, device=device, data={'pose': pose})
        ctx.mq.notify_reload('slave', sid)
        return jsonify(ok=True)

    @api.route('/imu/<int:sid>/<device>')
    @auth_required
    def imu(sid, device):
        return jsonify(ok=True, **ctx.imu_data(sid, device))

    # --- Programs ------------------------------------------------------------------------------
    def program_full(pid):
        row = ctx.q('SELECT * FROM program WHERE pro_id=%s', (pid,), one=True)
        if not row:
            return None
        steps = ctx.q('SELECT pc_id, pc_command, pc_parameter FROM program_commands WHERE pc_program=%s ORDER BY pc_id', (pid,))
        out = []
        for i, st in enumerate(steps):
            a = actions.get(st['pc_command'])
            try:
                params = actions.parse_params(a, st['pc_parameter']) if a else {}
                error = None if a else 'unbekannte Aktion'
            except actions.ActionError as e:
                params, error = {}, str(e)
            out.append({'pc_id': st['pc_id'], 'i': i + 1, 'code': st['pc_command'], 'name': a.name if a else st['pc_command'],
                        'params': params, 'raw': st['pc_parameter'], 'error': error,
                        'text': ', '.join(f"{p.label or p.name} {params[p.name]}{(' ' + p.unit) if p.unit else ''}"
                                          for p in (a.params if a else ()) if p.name in params)})
        row['steps'] = out
        row['users'] = ctx.q('SELECT s.slave_id, s.slave_name, (s.slave_program=%s) AS active FROM slaves s '
                             'JOIN slave_program sp ON sp.sp_slave=s.slave_id WHERE sp.sp_program=%s ORDER BY s.slave_name', (pid, pid))
        for u in row['users']:
            u['active'] = bool(u['active'])
        row['errors'] = actions.validate_program(steps)
        return row

    @api.route('/programs')
    @auth_required
    def programs():
        rows = ctx.q('SELECT p.pro_id, p.pro_name, p.pro_functions, '
                     '       (SELECT COUNT(*) FROM program_commands c WHERE c.pc_program=p.pro_id) AS n_steps, '
                     '       (SELECT COUNT(*) FROM slave_program sp WHERE sp.sp_program=p.pro_id) AS n_slaves, '
                     '       (SELECT COUNT(*) FROM slaves s WHERE s.slave_program=p.pro_id) AS n_active '
                     '  FROM program p ORDER BY p.pro_name')
        for r in rows:
            steps = ctx.q('SELECT pc_id, pc_command, pc_parameter FROM program_commands WHERE pc_program=%s ORDER BY pc_id', (r['pro_id'],))
            r['valid'] = not actions.validate_program(steps)
        return jsonify(ok=True, programs=rows)

    @api.route('/programs', methods=['POST'])
    @auth_required
    def program_create():
        j = body()
        name, desc = str(j.get('pro_name', '')).strip(), str(j.get('pro_functions', '')).strip()
        if not name:
            return err('Name ist Pflicht')
        if ctx.q('SELECT pro_id FROM program WHERE pro_name=%s', (name,), one=True):
            return err('Name bereits vergeben', 409)
        pid = ctx.x('INSERT INTO program (pro_name, pro_functions) VALUES (%s,%s)', (name, desc))
        ctx.db().commit()
        audit.web('program_create', request.api_user, data={'pro_id': pid, 'name': name})
        ctx.mq.notify_reload('program', pid)
        return jsonify(ok=True, program=program_full(pid)), 201

    @api.route('/programs/<int:pid>')
    @auth_required
    def program_get(pid):
        row = program_full(pid)
        return jsonify(ok=True, program=row) if row else err('nicht gefunden', 404)

    @api.route('/programs/<int:pid>', methods=['PUT'])
    @auth_required
    def program_update(pid):
        if not ctx.q('SELECT pro_id FROM program WHERE pro_id=%s', (pid,), one=True):
            return err('nicht gefunden', 404)
        j = body()
        name, desc = str(j.get('pro_name', '')).strip(), str(j.get('pro_functions', '')).strip()
        if not name:
            return err('Name ist Pflicht')
        if ctx.q('SELECT pro_id FROM program WHERE pro_name=%s AND pro_id<>%s', (name, pid), one=True):
            return err('Name bereits vergeben', 409)
        ctx.x('UPDATE program SET pro_name=%s, pro_functions=%s WHERE pro_id=%s', (name, desc, pid))
        ctx.db().commit()
        audit.web('program_update', request.api_user, data={'pro_id': pid, 'name': name})
        ctx.mq.notify_reload('program', pid)
        return jsonify(ok=True, program=program_full(pid))

    @api.route('/programs/<int:pid>', methods=['DELETE'])
    @auth_required
    def program_delete(pid):
        row = ctx.q('SELECT pro_name FROM program WHERE pro_id=%s', (pid,), one=True)
        if not row:
            return err('nicht gefunden', 404)
        used = ctx.q('SELECT COUNT(*) AS n FROM slave_program WHERE sp_program=%s', (pid,), one=True)['n']
        if used:
            return err(f'noch {used} Sklaven(n) zugeordnet', 409)
        ctx.x('DELETE FROM program_commands WHERE pc_program=%s', (pid,))
        ctx.x('DELETE FROM program WHERE pro_id=%s', (pid,))
        ctx.db().commit()
        audit.web('program_delete', request.api_user, data={'pro_id': pid, 'name': row['pro_name']})
        ctx.mq.notify_reload('program', pid)
        return jsonify(ok=True)

    def _waveform_step_check(action, p):
        """Check the waveform parameters of a program step against the database
        (check 2026-09-11). Returns an error text or None. The registry cannot do
        that: it knows only numeric ranges, not purpose and axis of the waveform.
        0 stays allowed where it means 'the central unit chooses' resp. 'no coupling'."""
        def head(ro_id):
            try:
                return ctx.q('SELECT ro_id, ro_purpose, ro_axis FROM routines WHERE ro_id=%s',
                             (int(ro_id),), one=True)
            except pymysql.err.Error:
                return None      # database without migration 008/009: nothing can be checked here
        ro = int(p.get('routine') or 0)
        if action.code == 'TRAINER_ROUTINE' and ro:
            row = head(ro)
            if not row:
                return f'Wellenform {ro} gibt es nicht'
            if not routines.is_task(row):
                return (f'Wellenform {ro} ist keine Aufgabe auf der Zeitachse — '
                        'sie kann nicht bewertet werden')
        if action.code == 'ESTIM_ROUTINE' and ro:
            row = head(ro)
            if not row:
                return f'Wellenform {ro} gibt es nicht'
            if (row.get('ro_axis') or routines.AXIS_TIME) != routines.AXIS_TIME \
                    or (row.get('ro_purpose') or routines.PURPOSE_TASK) == routines.PURPOSE_TASK:
                return (f'Wellenform {ro} ist kein abspielbarer Reiz — sie muss auf der '
                        'Zeitachse liegen und den Zweck „Reiz" oder „Belohnung" haben')
        kop = int(p.get('kopplung') or 0)
        if kop:
            row = head(kop)
            if not row:
                return f'Kopplungs-Wellenform {kop} gibt es nicht'
            if (row.get('ro_axis') or routines.AXIS_TIME) != routines.AXIS_DEPTH:
                return (f'Wellenform {kop} liegt nicht auf der Tiefenachse — eine Kopplung '
                        'folgt der gemessenen Tiefe, nicht der Zeit')
        return None

    @api.route('/programs/<int:pid>/steps', methods=['POST'])
    @auth_required
    def step_add(pid):
        if not ctx.q('SELECT pro_id FROM program WHERE pro_id=%s', (pid,), one=True):
            return err('nicht gefunden', 404)
        j = body()
        action = actions.get(str(j.get('code', '')).upper())
        if not action or not action.implemented:
            return err('unbekannte Aktion')
        try:
            p = actions.parse_dict(action, j.get('params') or {})
        except actions.ActionError as e:
            return err(str(e))
        bad = _waveform_step_check(action, p)
        if bad:
            return err(bad)
        raw = actions.to_raw(action, p)
        pc_id = ctx.x('INSERT INTO program_commands (pc_program, pc_command, pc_parameter) VALUES (%s,%s,%s)',
                      (pid, action.code, raw))
        ctx.db().commit()
        audit.web('step_add', request.api_user, data={'pro_id': pid, 'pc_id': pc_id, 'action': action.code, 'params': p})
        ctx.mq.notify_reload('program', pid)
        return jsonify(ok=True, program=program_full(pid)), 201

    @api.route('/programs/<int:pid>/steps/<int:pc_id>', methods=['DELETE'])
    @auth_required
    def step_delete(pid, pc_id):
        st = ctx.q('SELECT * FROM program_commands WHERE pc_id=%s AND pc_program=%s', (pc_id, pid), one=True)
        if not st:
            return err('nicht gefunden', 404)
        ctx.x('DELETE FROM program_commands WHERE pc_id=%s', (pc_id,))
        ctx.db().commit()
        audit.web('step_delete', request.api_user, data={'pro_id': pid, 'pc_id': pc_id, 'action': st['pc_command']})
        ctx.mq.notify_reload('program', pid)
        return jsonify(ok=True, program=program_full(pid))

    @api.route('/programs/<int:pid>/steps/<int:pc_id>/move', methods=['POST'])
    @auth_required
    def step_move(pid, pc_id):
        st = ctx.q('SELECT * FROM program_commands WHERE pc_id=%s AND pc_program=%s', (pc_id, pid), one=True)
        if not st:
            return err('nicht gefunden', 404)
        up = str(body().get('dir', 'up')) == 'up'
        nb = ctx.q('SELECT * FROM program_commands WHERE pc_program=%s AND pc_id' + ('<' if up else '>') + '%s '
                   'ORDER BY pc_id ' + ('DESC' if up else 'ASC') + ' LIMIT 1', (pid, pc_id), one=True)
        if nb:
            ctx.x('UPDATE program_commands SET pc_command=%s, pc_parameter=%s WHERE pc_id=%s', (nb['pc_command'], nb['pc_parameter'], pc_id))
            ctx.x('UPDATE program_commands SET pc_command=%s, pc_parameter=%s WHERE pc_id=%s', (st['pc_command'], st['pc_parameter'], nb['pc_id']))
            ctx.db().commit()
            audit.web('step_move', request.api_user, data={'pro_id': pid, 'pc_id': pc_id, 'dir': 'up' if up else 'down'})
            ctx.mq.notify_reload('program', pid)
        return jsonify(ok=True, program=program_full(pid))

    # --- Devices ------------------------------------------------------------------------------------
    @api.route('/devices')
    @auth_required
    def devices():
        rows = ctx.q('SELECT d.*, (SELECT COUNT(*) FROM devtoslave x WHERE x.dts_deviceid=d.dev_id) AS n_slaves '
                     '  FROM devices d ORDER BY d.dev_address, d.dev_name')
        s = ctx.status_context()
        online = {d['uuid']: d for d in s['devices']}
        for r in rows:
            o = online.get(r['dev_name'])
            r['online'] = bool(o and o['online'])
            r['state'] = o['state'] if o else None
            r['fw'] = (o['hello'] or {}).get('fw_version') if o else None
            m = devicemodels.by_code(r['dev_model'])
            r['model_name'] = m.name if m else r['dev_model']
        unknown = [{'uuid': d['uuid'], 'model': d['model'], 'fw': (d['hello'] or {}).get('fw_version'),
                    'model_code': (devicemodels.by_uuid((d['hello'] or {}).get('model', '')) or devicemodels.MODELS[0]).code
                    if devicemodels.by_uuid((d['hello'] or {}).get('model', '')) else None,
                    'ip': d['state'].get('ip')} for d in s['unknown']]
        return jsonify(ok=True, devices=rows, unknown=unknown)

    @api.route('/devices', methods=['POST'])
    @auth_required
    def device_create():
        j = body()
        name, model, addr = str(j.get('dev_name', '')).strip(), str(j.get('dev_model', '')).strip(), str(j.get('dev_address', '')).strip()
        if not name or not devicemodels.by_code(model):
            return err('device_UUID und gültiges Modell sind Pflicht')
        if ctx.q('SELECT dev_id FROM devices WHERE dev_name=%s', (name,), one=True):
            return err('device_UUID bereits angelegt', 409)
        did = ctx.x("INSERT INTO devices (dev_name, dev_model, dev_address, dev_protocol) VALUES (%s,%s,%s,'MQTT')", (name, model, addr))
        ctx.db().commit()
        audit.web('device_create', request.api_user, device=name, data={'model': model, 'label': addr})
        ctx.mq.notify_reload('devices')
        return jsonify(ok=True, dev_id=did), 201

    @api.route('/devices/<int:did>', methods=['PUT'])
    @auth_required
    def device_update(did):
        row = ctx.q('SELECT * FROM devices WHERE dev_id=%s', (did,), one=True)
        if not row:
            return err('nicht gefunden', 404)
        j = body()
        name = str(j.get('dev_name', row['dev_name'])).strip()
        model = str(j.get('dev_model', row['dev_model'])).strip()
        addr = str(j.get('dev_address', row['dev_address'])).strip()
        if not name or not devicemodels.by_code(model):
            return err('device_UUID und gültiges Modell sind Pflicht')
        if ctx.q('SELECT dev_id FROM devices WHERE dev_name=%s AND dev_id<>%s', (name, did), one=True):
            return err('device_UUID bereits angelegt', 409)
        ctx.x('UPDATE devices SET dev_name=%s, dev_model=%s, dev_address=%s WHERE dev_id=%s', (name, model, addr, did))
        ctx.db().commit()
        audit.web('device_update', request.api_user, device=name, data={'model': model, 'label': addr})
        ctx.mq.notify_reload('devices')
        return jsonify(ok=True)

    @api.route('/devices/<int:did>', methods=['DELETE'])
    @auth_required
    def device_delete(did):
        row = ctx.q('SELECT * FROM devices WHERE dev_id=%s', (did,), one=True)
        if not row:
            return err('nicht gefunden', 404)
        used = ctx.q('SELECT COUNT(*) AS n FROM devtoslave WHERE dts_deviceid=%s', (did,), one=True)['n']
        if used:
            return err(f'noch {used} Sklaven(n) zugeordnet', 409)
        ctx.x('DELETE FROM devices WHERE dev_id=%s', (did,))
        ctx.db().commit()
        audit.web('device_delete', request.api_user, device=row['dev_name'])
        ctx.mq.notify_reload('devices')
        return jsonify(ok=True)

    # --- Audit log ----------------------------------------------------------------------------------
    @api.route('/audit')
    @auth_required
    def audit_list():
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
        limit = min(int(request.args.get('limit', '100') or 100), 500)
        try:
            rows = ctx.q('SELECT * FROM audit_log' + (' WHERE ' + ' AND '.join(where) if where else '') +
                         ' ORDER BY al_id DESC LIMIT %s OFFSET %s', tuple(params) + (limit + 1, (page - 1) * limit))
        except pymysql.Error as e:
            return err(f'DB: {e}', 500)
        names = ctx.device_names()
        out = [{'id': r['al_id'], 'ts': r['al_ts'].isoformat(sep=' ', timespec='seconds'), 'source': r['al_source'],
                'kind': r['al_kind'], 'device': r['al_device'],
                'device_label': (names.get(r['al_device']) or {}).get('dev_address') if r['al_device'] else None,
                'slave_id': r['al_slave_id'], 'action': r['al_action'], 'data': r['al_data'], 'user': r['al_user']}
               for r in rows[:limit]]
        return jsonify(ok=True, entries=out, page=page, more=len(rows) > limit)

    app.register_blueprint(api)
