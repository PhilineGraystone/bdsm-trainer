# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""MQTT client of the web interface (own process, doc 04 D4).

Listens in on what devices and the central unit publish and keeps the live
state in memory from it. It sends only interventions of the supervisor: stop,
identify, EMERGENCY — in the same envelope as the central unit
(libs/punmqtt.py), so that the devices see no difference.
"""

import collections
import json
import secrets
import threading
import time

import paho.mqtt.client as mqtt
import pymysql

import audit
import mqttaccount
import mqtttls
import punsign

RECENT = 100          # remembered events (devices + central unit)

# How long a control telegram to the central unit stays usable (2.1.1). Both
# sit on the same machine and speak over a local broker; a request that has
# been travelling for more than fifteen seconds has not been delayed, it has
# been recorded.
CONTROL_TTL_MS = 15000


class WebMQTT(mqtt.Client):

    def __init__(self, logger):
        super().__init__(mqtt.CallbackAPIVersion.VERSION2, client_id='PunisherWeb')
        self.log = logger
        self.lock = threading.Lock()
        self.devices = {}                     # uuid -> dict(hello, state, last_seen, last_event, log)
        self.central = {'last_hb': 0.0, 'ts_ms': 0}
        self.events = collections.deque(maxlen=RECENT)
        self.last_unknown_rfid = None
        self.session = {'slaves': []}         # punisher/central/session (retained)
        self.leaderboard = None               # punisher/central/leaderboard (retained, doc 14)
        self.connected = False
        self.error = None
        self._seq = 0
        self.pending = {}                     # device -> {'sid','pose','t'}: pose measurement in progress
        self.pose_results = {}                # device -> last pose_captured/pose_failed (+ 'saved')
        self._dbcfg = None
        # Refused messages, per claimed UUID: {'why', 'n', 't'}.
        #
        # A refused device is NOT shown (hard cut, see on_message). But that
        # something IS being refused belongs in plain sight — otherwise the
        # supervisor looks for a device that from their point of view is
        # simply missing, and the answer stands only in the log.
        #
        # The UUID comes from the topic and is therefore CLAIMED, not checked.
        # It stands here as a hint, never as an object that one can click
        # on.
        self.rejected = {}
        # Sender identity for control telegrams (2.1.1). The boot_id is fresh
        # for every start of this process: whoever restarts the web interface
        # legitimately begins at seq 1 again, and the central unit must be able
        # to tell that apart from a recording that carries the OLD boot_id and
        # a seq long spent.
        self._boot_id = secrets.token_hex(8)
        self._ctl_seq = 0
        self._ctl_lock = threading.Lock()    # see _control_stamp() — NOT self.lock

    # --- Connection ---------------------------------------------------------
    def start(self, config):
        if 'database' in config:
            self._dbcfg = dict(host=config['database']['hostname'], user=config['database']['username'],
                               password=config['database']['password'], database=config['database']['database'],
                               charset='utf8mb4', autocommit=True)
        # Project key: the same computation as in the central unit. Without it
        # the web interface does not sign — and a device from 2.0 on then does
        # not accept its commands. That is intended: better a button that does
        # nothing and says so than one that goes through unchecked.
        self.project_key = (config['mqtt'].get('project_key') or '').strip() or None
        host = config['mqtt']['hostname']
        # A BROKER ACCOUNT OF ITS OWN, WHERE ONE EXISTS (2.1.1).
        #
        # The broker's access list can only separate what the broker can tell
        # apart. Up to 2.1.0 the central unit, this interface, the display and
        # every device spoke as the same `punisher` — so no rule about "what
        # may a device publish" could bite (finding Philine 2026-09-15, doc 40).
        #
        # `[mqtt_web]` is therefore its own section, and its ABSENCE falls back
        # to `[mqtt]`. Not out of comfort: an installation upgraded without
        # touching config.ini has to keep running. But the fallback says so in
        # the log, because an access list without effect is worse than none —
        # it looks like protection.
        user, pw, own = mqttaccount.account(config, 'mqtt_web')
        if user:
            self.username_pw_set(user, pw)
        if own:
            self.log.info('web-mqtt: account %s', user)
        else:
            self.log.warning('web-mqtt: kein eigenes Brokerkonto ([mqtt_web] fehlt) — '
                             'die Zugriffsliste des Brokers wirkt fuer das Webinterface nicht')
        self.reconnect_delay_set(1, 30)
        try:
            # TLS (2.3, doc 53) — same three states as the central unit, and a
            # failure here is an error, not a silent fall back to clear text.
            mqtttls.configure(self, config, self.log)
            self.connect_async(host, mqtttls.port(config), 60)
        except (OSError, ValueError) as e:
            self.error = str(e)
        self.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            self.error = str(reason_code)
            self.log.error('web-mqtt: connect failed: %s', reason_code)
            return
        self.connected = True
        self.error = None
        for t in ('punisher/devices/+/hello', 'punisher/devices/+/state',
                  'punisher/devices/+/available', 'punisher/devices/+/event',
                  'punisher/devices/+/log', 'punisher/devices/+/response',
                  'punisher/central/heartbeat',
                  'punisher/central/event', 'punisher/central/last_unknown_rfid',
                  'punisher/central/session', 'punisher/central/leaderboard'):
            self.subscribe(t, 0)
        self.log.info('web-mqtt: connected')

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        self.log.warning('web-mqtt: disconnected (%s)', reason_code)

    # --- Incoming -----------------------------------------------------------
    def on_message(self, client, userdata, msg):
        parts = msg.topic.split('/')
        try:
            raw = msg.payload.decode('utf-8')
        except UnicodeDecodeError:
            return
        # What arrives here is checked before it goes into the display.
        # Otherwise someone could feign a device to the supervisor that does
        # not exist — or a state that it does not have.
        #
        # ONE RULE, AND IT LIVES IN punsign. This used to ask a second time
        # whether the topic starts with devices/ — a rule beside the rule, and
        # exactly the kind that silently stops covering a topic the moment the
        # first one takes a new one in (2026-09-15, same shape as the one in
        # punmqtt._signed).
        if self.project_key and not punsign.unsigned_topic(msg.topic):
            body, why = punsign.verify(self.project_key, msg.topic, raw,
                                       max_age_ms=120000,
                                       # The same rule as in the central unit.
                                       # This interface subscribes to no
                                       # control topic today — and that is
                                       # exactly why it stands here: a rule
                                       # that holds only where somebody
                                       # remembered it is not a rule.
                                       require_ts=punsign.control_topic(msg.topic))
            if body is None:
                self.log.error('web-mqtt: %s abgewiesen (%s)', msg.topic, why)
                self._note_rejected(parts[2] if len(parts) > 2 else '?', why)
                return
            raw = json.dumps(body)

        now = time.time()
        with self.lock:
            if parts[1] == 'central':
                self._central(parts[2], raw, now)
                return
            if len(parts) < 4 or parts[1] != 'devices':
                return
            uuid, kind = parts[2], parts[3]

            # HARD CUT (decision Philine 2026-09-14)
            #
            # A device comes into being in this display ONLY out of a checked
            # message. Unchecked material may refresh an existing device, but
            # create none.
            #
            # Before, `setdefault` created an entry for EVERY topic, for
            # `available` as well — and that one is deliberately unsigned (the
            # broker's last word; the device computes nothing any more by
            # then). So every 1.x device whose `hello` had not passed the
            # check stood in the list as "online", with model "?" and a
            # "Create" button next to it. The central unit did not know it, no
            # programme step could have used it — the display said the opposite
            # all the same, and the box below it contradicted the display.
            #
            # With 2.0 the agreement is: everything below version 2 is cut, not
            # carried along by halves. What never had a valid registration does
            # not exist here. The reason stands in the log and in the "Refused,
            # not shown" line under the device list — not as a device.
            d = self.devices.get(uuid)
            if d is None:
                if punsign.unsigned_topic(msg.topic):
                    return
                d = self.devices[uuid] = {'uuid': uuid, 'hello': None, 'state': None,
                                          'last_seen': 0, 'last_event': None,
                                          'log': collections.deque(maxlen=20)}
            if kind == 'available':
                d['last_seen'] = now
                return
            j = self._json(raw)
            if j is None:
                return
            if kind == 'hello':
                d['hello'] = j
            elif kind == 'state':
                d['state'] = j
                d['last_seen'] = now if j.get('state') != 'offline' else d['last_seen']
                d['offline_at'] = now if j.get('state') == 'offline' else None
            elif kind == 'event':
                d['last_seen'] = now
                ev = j.get('event', '?')
                if ev == 'imu':                       # live attitude readings: not into the event list
                    d['imu'] = j
                    d['imu_t'] = now
                    return
                d['last_event'] = j
                self.events.appendleft({'t': now, 'device': uuid, 'kind': 'event', 'event': ev, 'data': j})
                if ev in ('pose_captured', 'pose_failed'):
                    self._pose_result(uuid, j, now)
                elif ev in ('depth_captured', 'depth_failed'):
                    self._depth_result(uuid, j, now)
            elif kind == 'log':
                d['log'].appendleft({'t': now, 'level': j.get('level'), 'msg': j.get('msg')})
            elif kind == 'response':
                # Only the answer to `config` is kept (doc 42 point 5): the
                # form wants to say "stored / refused" after the button. Other
                # answers are the central unit's business.
                if j.get('action') == 'config':
                    d['config_response'] = dict(j, t=now)

    def _note_rejected(self, uuid, why):
        """Count it, for the line under the device list.

        EVERY refusal is reported, in the log as well as in the counter.
        Nothing is throttled here, deliberately (decision Philine 2026-09-14): in
        the finished installation nothing below 2.0 runs, so every refusal is a
        finding and not noise.
        """
        r = self.rejected.get(uuid)
        if r is None:
            r = self.rejected[uuid] = {'why': why, 'n': 0, 't': 0.0}
        r['why'] = why
        r['n'] += 1
        r['t'] = time.time()
        # Do not record without limit: a broker with old retained messages
        # can deliver many different UUIDs.
        if len(self.rejected) > 20:
            oldest = min(self.rejected, key=lambda k: self.rejected[k]['t'])
            self.rejected.pop(oldest, None)

    def _pose_result(self, device, j, now):
        """Result of a pose measurement: save it to the waiting calibration."""
        pend = self.pending.pop(device, None)
        res = dict(j, t=now, saved=False, sid=pend['sid'] if pend else None)
        if pend and j.get('event') == 'pose_captured' and self._dbcfg:
            try:
                db = pymysql.connect(**self._dbcfg)
                with db.cursor() as cur:
                    cur.execute('REPLACE INTO slave_calibration (sc_slave, sc_device, sc_pose, sc_x, sc_y, sc_z, sc_still) '
                                'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                                (pend['sid'], device, pend['pose'], float(j['x']), float(j['y']), float(j['z']),
                                 1 if j.get('still', True) else 0))
                db.close()
                res['saved'] = True
                audit.web('calibration_save', pend.get('user'), slave_id=pend['sid'], device=device,
                          data={'pose': pend['pose'], 'x': j['x'], 'y': j['y'], 'z': j['z'], 'still': j.get('still')})
                self.notify_reload('slave', pend['sid'])
            except (pymysql.Error, KeyError, TypeError, ValueError) as e:
                res['error'] = f'DB: {e}'
                self.log.error('calibration save failed: %s', e)
        self.pose_results[device] = res

    def _depth_result(self, device, j, now):
        """Depth calibration of the trainer (doc 14): save the resting distance and the
        greatest depth as pose 'depth' (sc_x = rest_mm, sc_y = deep_mm)."""
        pend = self.pending.pop(device, None)
        res = dict(j, t=now, saved=False, sid=pend['sid'] if pend else None)
        if pend and j.get('event') == 'depth_captured' and self._dbcfg:
            try:
                db = pymysql.connect(**self._dbcfg)
                with db.cursor() as cur:
                    cur.execute('REPLACE INTO slave_calibration (sc_slave, sc_device, sc_pose, sc_x, sc_y, sc_z, sc_still) '
                                'VALUES (%s,%s,%s,%s,%s,0,1)',
                                (pend['sid'], device, 'depth', float(j['rest_mm']), float(j['deep_mm'])))
                db.close()
                res['saved'] = True
                audit.web('calibration_save', pend.get('user'), slave_id=pend['sid'], device=device,
                          data={'pose': 'depth', 'rest_mm': j['rest_mm'], 'deep_mm': j['deep_mm']})
                self.notify_reload('slave', pend['sid'])
            except (pymysql.Error, KeyError, TypeError, ValueError) as e:
                res['error'] = f'DB: {e}'
                self.log.error('depth calibration save failed: %s', e)
        self.pose_results[device] = res

    def capture_depth(self, device, sid, seconds, user):
        with self.lock:
            self.pending[device] = {'sid': sid, 'pose': 'depth', 't': time.time(), 'user': user}
            self.pose_results.pop(device, None)
        return self.send_command(device, 'calibrate_depth', {'seconds': int(seconds)}, ttl_ms=5000, user=user)

    def capture_pose(self, device, sid, pose, seconds, user):
        with self.lock:
            self.pending[device] = {'sid': sid, 'pose': pose, 't': time.time(), 'user': user}
            self.pose_results.pop(device, None)
        return self.send_command(device, 'capture_pose', {'pose': pose, 'seconds': int(seconds)}, ttl_ms=5000, user=user)

    def imu_snapshot(self, device):
        with self.lock:
            d = self.devices.get(device) or {}
            return {'imu': d.get('imu'), 'age': round(time.time() - d['imu_t'], 1) if d.get('imu_t') else None,
                    'pending': self.pending.get(device), 'result': self.pose_results.get(device),
                    'state': d.get('state') or {}}

    def _central(self, kind, raw, now):
        # An EMPTY retained message deletes the marker at the broker. This has
        # to stand BEFORE the None bar: `_json('')` returns None, and the bar
        # would discard the deletion as a broken message — the marker would come
        # back on the next connect (finding Philine 2026-09-11).
        if kind == 'last_unknown_rfid' and not (raw or b'').strip():
            self.last_unknown_rfid = None
            return
        j = self._json(raw)
        if j is None:
            return
        if kind == 'heartbeat':
            self.central['last_hb'] = now
            self.central['ts_ms'] = j.get('ts_ms', 0)
        elif kind == 'event':
            self.events.appendleft({'t': now, 'device': None, 'kind': 'central',
                                    'event': j.get('event', '?'), 'data': j})
            if j.get('event') == 'rfid_unknown':
                self.last_unknown_rfid = j
        elif kind == 'last_unknown_rfid':
            # An EMPTY retained message is the deletion of the marker.
            # `_json()` returns None for it — that is not an error here but the
            # message itself (see clear_unknown_rfid).
            self.last_unknown_rfid = j
        elif kind == 'session':
            self.session = j if 'slaves' in j else {'slaves': []}
        elif kind == 'leaderboard':
            self.leaderboard = j

    @staticmethod
    def _json(raw):
        try:
            j = json.loads(raw)
            return j if isinstance(j, dict) else None
        except json.JSONDecodeError:
            return None

    # --- Snapshot for the pages ------------------------------------------------
    def snapshot(self):
        now = time.time()
        with self.lock:
            devs = []
            for uuid, d in self.devices.items():
                st = d['state'] or {}
                offline = st.get('state') == 'offline' or (now - d['last_seen']) > 45
                devs.append({
                    'uuid': uuid,
                    'hello': d['hello'] or {},
                    'state': st,
                    'config_response': d.get('config_response'),
                    'online': not offline,
                    'age_s': int(now - d['last_seen']) if d['last_seen'] else None,
                    # The moment of the last sign of life, as a whole second.
                    # `age_s` grows with every look and is therefore useless as
                    # the content of a condition; this one stands still while
                    # the device is away and moves on at the next outage
                    # (devicehealth, 2.3.3).
                    'last_seen': int(d['last_seen']) if d['last_seen'] else 0,
                    'last_event': d['last_event'],
                    'log': list(d['log']),
                })
            hb_age = (now - self.central['last_hb']) if self.central['last_hb'] else None
            return {
                'devices': sorted(devs, key=lambda x: (not x['online'], x['uuid'])),
                'central_alive': hb_age is not None and hb_age < 5,
                'central_hb_age': None if hb_age is None else round(hb_age, 1),
                'events': list(self.events),
                'last_unknown_rfid': self.last_unknown_rfid,
                'session': self.session,
                'leaderboard': self.leaderboard,
                'mqtt_connected': self.connected,
                'mqtt_error': self.error,
                'rejected': sorted(
                    ({'uuid': u, 'why': r['why'], 'n': r['n'], 'age_s': int(now - r['t'])}
                     for u, r in self.rejected.items()),
                    key=lambda x: x['age_s']),
            }

    # --- Outgoing (interventions of the supervisor) -----------------------------
    def send_command(self, device, action, args=None, ttl_ms=5000, user=None):
        with self.lock:
            self._seq = (self._seq + 1) & 0xFFFF
            cid = int(time.time() * 1000) % 1_000_000 * 1000 + (self._seq % 1000)
        payload = {'action': action, 'id': cid, 'ts_ms': int(time.time() * 1000), 'ttl_ms': ttl_ms}
        if args:
            payload['args'] = args
        topic = f'punisher/devices/{device}/cmd'
        self.publish(topic, punsign.sign(self.project_key, topic, payload)
                     if self.project_key else json.dumps(payload))
        audit.web(action, user, kind='cmd', device=device, data={'args': args, 'id': cid})
        return cid

    def clear_unknown_rfid(self, user=None, reason='dismissed'):
        """Delete the "Last unknown tag" marker.

        The central unit publishes it RETAINED so that a web interface opened
        later still sees it. Exactly for that reason it also stays put when
        nobody needs it any more — for instance because the tag has long
        belonged to a slave (finding Philine 2026-09-11). An empty retained
        message clears it away at the broker; without it, it would come back on
        the next restart of the web interface.
        """
        had = self.last_unknown_rfid
        self.last_unknown_rfid = None
        self.publish('punisher/central/last_unknown_rfid', b'', retain=True)
        if had:
            audit.web('unknown_rfid_cleared', user, kind='admin',
                      data={'rfid': had.get('rfid'), 'reason': reason})
        return had

    def _control_stamp(self, payload):
        """Give a control telegram its mandatory fields (2.1.1).

        id, boot_id, seq, ts_ms, ttl_ms — what the central unit needs in order
        to recognise the SECOND copy of this telegram. Without them the same
        signed bytes published twice were two punishments over the channel
        (finding Philine 2026-09-15).

        WHY A LOCK OF ITS OWN, and not self.lock: notify_reload() is called
        from _pose_result(), and that one runs inside `with self.lock` in
        on_message. self.lock is a plain Lock, not an RLock — taking it here
        would stop the web interface dead the first time a pose measurement is
        saved. Worth a line of comment, because that deadlock would show up
        only in calibration mode and nowhere else.
        """
        with self._ctl_lock:
            self._ctl_seq += 1
            seq = self._ctl_seq
        out = dict(payload)
        out.update(punsign.control_envelope(self._boot_id, seq,
                                            ttl_ms=CONTROL_TTL_MS))
        return out

    def _publish_signed(self, topic, payload):
        """Publish into the signed envelope, by the one rule in punsign.

        The two control topics under central/ are signed since 2.1.0: what
        arrives on `request` ends up in logbook.punish(), and that is a real
        punishment over the channel. Unsigned it could be given by anyone with
        publish rights at the broker, past the login of this very interface
        (finding Philine 2026-09-15).

        Since 2.1.1 they carry, in addition, the fields by which the central
        unit refuses a repetition. Signature and replay are two different
        questions, and the signature answers only the first.

        Returns what was actually sent, so that the audit entry names the same
        id the central unit will log.
        """
        if punsign.control_topic(topic):
            payload = self._control_stamp(payload)
        if self.project_key and not punsign.unsigned_topic(topic):
            self.publish(topic, punsign.sign(self.project_key, topic, payload))
        else:
            self.publish(topic, json.dumps(payload))
        return payload

    def request(self, what, user=None, **kw):
        """Request to the central unit (punisher/central/request): punishment/reward over
        the channel of the slave (only the central unit publishes there), weekly rating,
        plan proposal, activation. The central unit checks minimum pause/daily limit and audits."""
        payload = {'what': what, 'user': user}
        payload.update({k: v for k, v in kw.items() if v is not None})
        sent = self._publish_signed('punisher/central/request', payload)
        audit.web('request_' + what, user, kind='request', slave_id=kw.get('slave_id'), data=sent)

    def notify_reload(self, what, ident=None):
        """Tell the central unit that something in the DB has changed
        (it reads anew at once; in addition it checks a checksum every 30 s).

        The row number is called `ref_id` and not `id` since 2.1.1: `id` now
        belongs to the control envelope and identifies the TELEGRAM. Two
        different things under one name is how a guard silently stops guarding.
        """
        self._publish_signed('punisher/central/reload',
                             {'what': what, 'ref_id': ident})

    def stop_all(self, user=None):
        with self.lock:
            targets = [u for u, d in self.devices.items()
                       if (d['state'] or {}).get('state') != 'offline']
        for u in targets:
            self.send_command(u, 'stop', ttl_ms=2000, user=user)
        return targets

    def emergency(self, user=None, device=None):
        if device:
            self.publish(f'punisher/devices/{device}/emergency', '{"emergency":true}')
        else:
            self.publish('punisher/emergency', '{"emergency":true}')
        audit.web('emergency', user, kind='emergency', device=device, data={'broadcast': device is None})
