#!/usr/bin/env python3
# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#
# Central unit <-> devices per the PunisherDevice framework contract
# (see project document 07-firmware-framework.md).
#
# Device -> central unit:  devices/<uuid>/available|hello|response|state|event|log
# Central unit -> device:  devices/<uuid>/settings|cmd|emergency,
#                      punisher/emergency, punisher/central/heartbeat,
#                      punisher/slaves/<slave_id>/punish|reward  (channel, doc 14 3a)
# Central unit -> display/web: punisher/central/session|event|leaderboard (retained)
# Web -> central unit: punisher/central/reload (DB changed),
#                      punisher/central/request {what: punish|reward|review|propose, ...}

import json
import audit
import mqtttls
import devicemodels
import fwversion
import punsign

# How old a message may be. The envelope carries ts_ms; whatever is older
# is a replay. Generous enough for a device with a badly set clock after the
# start, tight enough that a recording from yesterday can no longer achieve
# anything.
SIGNATURE_MAX_AGE_MS = 120000
import threading
import time

import paho.mqtt.client as paho

DEVICE_TIMEOUT = 30          # s without a sign of life -> device offline
HEARTBEAT_INTERVAL = 1.0     # s between central heartbeats

# The largest payload ANY device accepts: PunisherConfig.mqttBufferSize is 1536
# by default, and a sketch can only raise it. What is bigger than this is not
# "delivered later" — it is thrown away by the device with one line in its own
# log that nobody on the central side ever sees. So it is refused HERE, loudly,
# before it goes out (2.1.1, finding Philine 2026-09-15: a 50-point routine
# chunk with large values was 1046 bytes and fell through a 990-byte callback).
DEVICE_RX_MAX = 1536


class PunMQTT(paho.Client):
    def __init__(self, client_id):
        super().__init__(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.app_logger = None
        self.devices = None
        self.cursor = None
        self._retained_now = False       # see _touch(): history is not presence
        self.identity_writes = []        # see _record_identity(): the main loop writes
        self.boot_writes = []            # see _record_boot(): likewise (2.2.0)
        self.slaves = None
        # Project key for the signature. None = off (only for an
        # installation that has not been converted yet; from 2.0 on it belongs set).
        self.project_key = None

        self.tdevice = {}            # device_uuid -> {'timestamp', 'status'}
        # device -> ts of the last signature complaint.
        #
        # The gap is deliberately SHORT (30 s) and deliberately does NOT grow
        # the longer the fault lasts (decision Philine 2026-09-14). A rejected
        # signature is not noise in the finished installation: nothing below
        # 2.0 runs there any more, the floors do not permit it. Whoever turns
        # up here has a foreign key or a firmware that nobody should have
        # flashed — and that belongs reported loudly, not growing quieter
        # over time.
        #
        # During the conversion this writes a lot; that is a state lasting
        # days, not a property of the installation. Whoever clears the old
        # retained `hello` messages at the broker is rid of the lines.
        self._sig_complained = {}
        # (device, routine_id) -> ts of the last resend. A WINDOW, not a one-shot:
        # a set never forgets, so after one resend a device that legitimately lost
        # its EEPROM again was refused until restart (review 2026-09-11).
        self._routine_resent = {}
        self._routine_resend_gap_s = 600
        self.lock = threading.RLock()
        self.fatal_error = None
        self._last_hb = 0.0
        self._cmd_seq = 0            # running cmd id (duplicate protection in the device)
        self._hb_thread = None
        self._hb_stop = threading.Event()
        self.reload_requests = []    # [(what, id)] from the web; the main loop works them off
        self.requests = []           # requests from the web (channel, weekly grading ...); main loop
        # Already-seen control telegrams (2.1.1). Lives in the client and not
        # globally: it belongs to this connection, and a restart of the central
        # unit empties it on purpose — what a restart forgets, ts_ms/ttl_ms
        # still catch.
        self.control_guard = punsign.ReplayGuard()

    # ------------------------------------------------------------------ #
    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code == 0:
            self.app_logger.info('MQTT: connected')
            self.subscribe('punisher/devices/+/available', 0)
            self.subscribe('punisher/devices/+/hello', 0)
            self.subscribe('punisher/devices/+/response', 0)
            # Live measurement of the trainer (doc 19 §5.2), ~5 Hz. Own topic, not
            # `state`, so the retained device state is not rewritten 5 times a second.
            self.subscribe('punisher/devices/+/live', 0)
            self.subscribe('punisher/devices/+/state', 0)
            self.subscribe('punisher/devices/+/event', 0)
            self.subscribe('punisher/devices/+/log', 0)
            self.subscribe('punisher/central/reload', 0)     # the web reports DB changes
            self.subscribe('punisher/central/request', 0)    # the web asks for channel/grading
            return
        messages = {1: 'Wrong protocol version', 2: 'Identification failed',
                    3: 'Server not reachable', 4: 'Bad user/password', 5: 'Not authorized'}
        text = messages.get(int(reason_code), f'Invalid return code: {reason_code}')
        self.app_logger.error('MQTT: ' + text)
        self.fatal_error = text

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.app_logger.warning(f'MQTT: disconnected (rc={reason_code})')

    # --- Outgoing ------------------------------------------------------- #
    def _signed(self, topic, obj):
        """Put the message into the signed envelope — or precisely not.

        WHAT ACTS ON A DEVICE IS SIGNED: punisher/devices/# and
        punisher/slaves/# (on the latter the stimulators listen on the channel
        of their slave — a forged entry there lands on skin).

        NOT signed is punisher/central/# — leaderboard and session for the
        display. Nothing acts there, and the display should show something
        even when the signature jams once. THE HEARTBEAT IS THE EXCEPTION
        under that prefix since 2.1.0: it carries the only clock the devices
        have and it resets their 120-second watchdog. Both of those act.

        ALSO not signed is the emergency stop, in both directions. A forged
        emergency shutdown shuts down — that is the harmless direction.
        An emergency stop that fails a check would be the dangerous one.

        The decision is made in ONE place, punsign.signed_topic(). This method
        used to ask a second time whether the topic starts with devices/ or
        slaves/ — a second rule beside the first, and it silently excluded the
        heartbeat even after punsign had taken it in.
        """
        if not self.project_key or punsign.unsigned_topic(topic):
            return json.dumps(obj)
        return punsign.sign(self.project_key, topic, obj)

    def _publish_json(self, topic, obj):
        wire = self._signed(topic, obj)
        if len(wire.encode('utf-8')) >= DEVICE_RX_MAX:
            # Not sent. A device would drop it anyway, and then the fault
            # stands in the wrong log. Here it stands in the right one, with
            # the action, so that whoever built the waveform finds it.
            what = obj.get('action') if isinstance(obj, dict) else '?'
            self.app_logger.error(
                f'MQTT: message on {topic} not sent — {len(wire)} B, devices accept < {DEVICE_RX_MAX} B '
                f'(action {what!r})')
            audit.central('payload_too_large', data={'topic': topic, 'action': what, 'bytes': len(wire)})
            return False
        self.publish(topic, wire)
        return True

    def send_command(self, device, action, args=None, ttl_ms=5000):
        """A command to a device: cmd envelope with id, timestamp + TTL.
        The id makes redelivery (QoS 1) recognisable in the device -> no double pulse."""
        cid = self._cid()
        payload = {'action': action, 'id': cid,
                   'ts_ms': int(time.time() * 1000), 'ttl_ms': ttl_ms}
        if args:
            payload['args'] = args
        self._publish_json(f'punisher/devices/{device}/cmd', payload)
        audit.command(device, action, args, cid)

    def _settings(self, device, obj, ttl_ms=10000):
        """A settings message, with the same guards as a command (2.1.0).

        `settings` carries the assignment to a slave — which channel a
        stimulator listens on. It went out without an id and without a
        timestamp until 2.1.0, so the device had nothing to recognise a
        repetition or an old message by, and it checked neither (finding Philine
        2026-09-15). A replayed assignment is not a small thing: it puts a
        device back on a person it was taken off.

        The TTL is longer than for a command. A command is a pulse, a setting
        is a state — and a setting that arrives a moment late is still the
        right setting.
        """
        payload = dict(obj)
        payload['id'] = self._cid()
        payload['ts_ms'] = int(time.time() * 1000)
        payload['ttl_ms'] = ttl_ms
        self._publish_json(f'punisher/devices/{device}/settings', payload)

    def assign_slave(self, device, slave_id, slave_name):
        self._settings(device, {'slave_id': slave_id, 'slave_name': slave_name})

    def request_initial(self, device):
        self._settings(device, {'initial': 'functions'})

    def emergency(self, device=None):
        """device=None -> broadcast to all devices."""
        if device:
            self.publish(f'punisher/devices/{device}/emergency', '{"emergency":true}')
        else:
            self.publish('punisher/emergency', '{"emergency":true}')
        audit.log('central', 'emergency', 'emergency', device, None, {'broadcast': device is None})

    def _cid(self):
        with self.lock:
            self._cmd_seq = (self._cmd_seq + 1) & 0xFFFFFFFF
            return int(time.time() * 1000) % 1_000_000 * 1000 + (self._cmd_seq % 1000)

    def publish_punish(self, slave_id, level=1, kind='any', reason='', source='central', ttl_ms=5000,
                       warn=None, estim_ceiling=None, estim_pct=None, estim_profile=None):
        """Punishment channel of the slave (doc 14 3a): every stimulator assigned to
        him listens. Same envelope as cmd (id, ts_ms, ttl_ms). The publisher is ONLY the
        central unit; minimum pause/daily limit are checked by libs/logbook.py beforehand.

        `warn` says whether a pre-warning should precede. None means: the installation
        has no opinion, the default of the device applies (ENV_WARN_DEFAULT).
        The collar has always read `args.warn` - the central unit merely never
        sent it, which is why the privilege 'Always warned' had no effect
        (finding 2026-09-11 while building the sanctions, doc 26).

        `estim_ceiling` is (A %, B %) from the calibration of this slave at
        her bridge. The channel is ONE envelope for all her stimulators, and the
        collar does not need the value - the bridge does: with it the level 1..3
        is only a share, the height stands elsewhere (doc 28). If the value is
        missing, the bridge outputs nothing; the collar punishes anyway.
        """
        cid = self._cid()
        args = {'level': int(level), 'kind': kind or 'any', 'reason': reason or '', 'source': source or 'central'}
        if warn is not None:
            args['warn'] = 1 if warn else 0
        if estim_ceiling:
            args['str_a'] = max(0, min(100, int(estim_ceiling[0])))
            args['str_b'] = max(0, min(100, int(estim_ceiling[1])))
        # How many percent OF HER CEILING this level uses. Without the value
        # the device takes its own default - the collar ignores it anyway,
        # with it the level says something else (doc 31).
        if estim_pct is not None:
            args['pct'] = max(1, min(100, int(estim_pct)))
        # WHICH profile. Until 2026-09-12 nothing stood here, and the bridge
        # took a fixed 'stich' - an assumption about anatomy, made by somebody
        # who does not stick on the electrodes (doc 32). The collar knows no
        # profiles and ignores the value.
        if estim_profile:
            args['profile'] = str(estim_profile)[:24]
        payload = {'action': 'punish', 'id': cid, 'ts_ms': int(time.time() * 1000), 'ttl_ms': ttl_ms,
                   'args': args}
        self._publish_json(f'punisher/slaves/{int(slave_id)}/punish', payload)
        return cid

    def punish_kinds_of(self, slave_id, except_device):
        """Which punishment kinds the OTHER devices of this slave listen for.

        Used to mirror a punishment a device decided on its own (2.3.5, doc 57).
        A channel message carries ONE kind, and a device only reacts to its own
        (`kindMatches` in the firmware) — so the kinds of the originator are
        SUBTRACTED, not merely skipped. That subtraction is the whole guard
        against punishing the same body twice for one violation, and it has to
        hold even if another device of the same model is assigned.

        The price of that, said out loud: two collars on one person would mean
        the second one does not join in. This installation has one, and a
        double pulse is the worse of the two mistakes.
        """
        s = self.slaves.by_id(int(slave_id or 0)) if self.slaves else None
        if s is None:
            return set()
        own, others = set(), set()
        for uuid in list(getattr(s, 'slave_devices', []) or []):
            dev = self.devices.get_device(uuid)
            code = getattr(getattr(dev, 'model', None), 'code', None)
            if not code:
                continue
            kinds = set(devicemodels.PUNISHERS.get(code, ()))
            if uuid == except_device:
                own |= kinds
            else:
                others |= kinds
        return others - own

    def publish_reward(self, slave_id, level=1, kind='any', reason='', source='central', ttl_ms=5000,
                       estim_ceiling=None, estim_pct=None, estim_profile=None):
        cid = self._cid()
        args = {'level': int(level), 'kind': kind or 'any', 'reason': reason or '', 'source': source or 'central'}
        if estim_ceiling:
            args['str_a'] = max(0, min(100, int(estim_ceiling[0])))
            args['str_b'] = max(0, min(100, int(estim_ceiling[1])))
        if estim_pct is not None:
            args['pct'] = max(1, min(100, int(estim_pct)))
        if estim_profile:
            args['profile'] = str(estim_profile)[:24]
        payload = {'action': 'reward', 'id': cid, 'ts_ms': int(time.time() * 1000), 'ttl_ms': ttl_ms,
                   'args': args}
        self._publish_json(f'punisher/slaves/{int(slave_id)}/reward', payload)
        return cid

    def publish_live(self, slave_id, payload):
        """Measured value of the participant for every device that couples to it
        (doc 19 §5.2): depth in percent, normalised band error, valid, away.

        NOT retained - a stale live value must never look current; the bridges
        additionally drop to zero after `live_stale_ms` without a new one.
        """
        topic = f'punisher/slaves/{int(slave_id)}/live'
        self.publish(topic, self._signed(topic, payload))

    def publish_leaderboard(self, board):
        """Ranking (week + total) retained for display/web/app."""
        self.publish('punisher/central/leaderboard', json.dumps(board, default=str), retain=True)

    def publish_session(self, slaves_snapshot):
        """Registered slaves with plan and progress — retained, so that the
        display knows the state at any time (even after a restart of its own)."""
        payload = {'ts_ms': int(time.time() * 1000), 'slaves': slaves_snapshot}
        self.publish('punisher/central/session', json.dumps(payload, default=str), retain=True)

    def clear_session(self):
        self.publish('punisher/central/session',
                     json.dumps({'ts_ms': int(time.time() * 1000), 'slaves': []}), retain=True)

    def publish_central_event(self, event, data=None):
        """Event of the central unit (login/logout/rfid_unknown) for display and web.
        Not retained, except the last unknown tag (the web should see that one
        even when it is opened only later)."""
        payload = {'event': event, 'ts_ms': int(time.time() * 1000)}
        if data:
            payload.update(data)
        self.publish('punisher/central/event', json.dumps(payload))
        if event == 'rfid_unknown':
            self.publish('punisher/central/last_unknown_rfid', json.dumps(payload), retain=True)

    def heartbeat(self):
        """Send one central heartbeat (time source + sign of life)."""
        now = time.time()
        self._last_hb = now
        if self.is_connected():
            self._publish_json('punisher/central/heartbeat', {'ts_ms': int(now * 1000)})

    def _heartbeat_loop(self):
        # Own thread: the main loop blocks in several places (LCD sleeps at
        # the login). If the heartbeat hung there, the device watchdogs (3 s)
        # would trip all active devices at every login.
        while not self._hb_stop.wait(HEARTBEAT_INTERVAL):
            try:
                self.heartbeat()
            except Exception as e:  # noqa: BLE001 - the heartbeat must never stop
                if self.app_logger:
                    self.app_logger.error('heartbeat: %s', e)

    def stop_heartbeat(self):
        self._hb_stop.set()

    # --- Incoming ------------------------------------------------------- #
    def sweep_timeouts(self):
        now = time.time()
        with self.lock:
            for uuid in list(self.tdevice.keys()):
                if self.tdevice[uuid]['timestamp'] + DEVICE_TIMEOUT < now:
                    self.app_logger.info('MQTT: device timeout ' + str(uuid))
                    self.tdevice.pop(uuid, None)
                    self.devices.remove_device(uuid)
                    self.slaves.set_online_device_to_offline(uuid)

    def _touch(self, device, status='online'):
        """Mark the device as present, now.

        A RETAINED MESSAGE ESTABLISHES NO PRESENCE (2.1.0).

        `hello` and `state` are both retained, and both for a good reason: a
        freshly started central unit should know what the devices ARE and what
        they were doing, without having to wait for each of them to speak. But
        retained means old, and until 2.0.0 both of them ran through here and
        marked the device online. Every restart of the central unit therefore
        resurrected every device that had ever registered — including ones long
        unscrewed — until the 45-second sweep took them out again (finding
        Philine 2026-09-15). They are validly signed, so no signature check
        catches it: it is the replay of something that was true once.

        Enforcing an age on them would be the wrong repair — it would throw
        away exactly what makes them worth retaining. The honest distinction is
        the one the broker already makes for us: MQTT clears the retain flag on
        a message delivered to an ESTABLISHED subscription, and sets it on one
        delivered because the subscription is new. retain=1 therefore means
        "this is history", retain=0 means "this is happening now".

        Presence comes from what is happening now: the sign of life on
        `available`, an event, a log line. What is gone says so on `available`,
        and that is handled before this method is reached.
        """
        if self._retained_now:
            return
        self.tdevice[device] = {'timestamp': time.time(), 'status': status}

    def on_message(self, client, userdata, msg):
        parts = msg.topic.split('/')
        # Is this message happening, or is it history? See _touch(). Set here,
        # once, before anything is dispatched — on_message runs in the single
        # thread of the paho loop, so one field is enough and beats threading
        # the flag through every handler.
        self._retained_now = bool(getattr(msg, 'retain', False))
        try:
            raw = msg.payload.decode('utf-8')
        except UnicodeDecodeError:
            self.app_logger.warning('MQTT: non-utf8 payload on ' + msg.topic)
            return

        # CHECK THE SIGNATURE BEFORE ANYTHING AT ALL HAPPENS WITH THE CONTENT.
        #
        # This block used to sit further down, BELOW the two central/ branches
        # — and those two were therefore reached without any check at all. What
        # arrives on `request` is handed to handle_requests(), which calls
        # logbook.punish(): a real punishment over the channel. Anyone with
        # publish rights at the broker could give it, past the login of the web
        # interface, and could put any name they liked in the `user` field
        # (finding Philine 2026-09-15).
        #
        # It is hoisted now, so there is ONE door and everything goes through
        # it. punsign.signed_topic() alone decides what needs an envelope.
        #
        # Rejection is LOUD. A silent rejection would be the worst thing here:
        # a device that cannot register and tells nobody why looks like a
        # device with a loose contact — and after that somebody searches for
        # hours at the wrong end.
        if self.project_key and not punsign.unsigned_topic(msg.topic):
            body, why = punsign.verify(self.project_key, msg.topic, raw,
                                       max_age_ms=SIGNATURE_MAX_AGE_MS,
                                       # A control telegram without ts_ms is
                                       # refused (2.1.1). The web interface
                                       # knows what time it is; a device before
                                       # its first heartbeat does not, and that
                                       # is the whole reason this is a
                                       # parameter and not the rule for all.
                                       require_ts=punsign.control_topic(msg.topic))
            # The latch is per SENDER. For a device that is its UUID; under
            # central/ there is none, so the topic itself does the job.
            who = str(parts[2]) if len(parts) >= 4 else msg.topic
            what = parts[3] if len(parts) >= 4 else parts[-1]
            if body is None:
                now = time.time()
                last = self._sig_complained.get(who, 0)
                if now - last > 30:      # not the same line every second
                    self._sig_complained[who] = now
                    self.app_logger.error(
                        f'MQTT: {who} — Nachricht auf {what} abgewiesen: {why}')
                    audit.central('signature_rejected', device=who,
                                  data={'kind': what, 'reason': why})
                # DELIBERATELY NOTHING IS BLOCKED HERE.
                #
                # Old RETAINED messages may lie at the broker — a `hello` or a
                # `state` from the time before the conversion, unsigned. Those
                # arrive once more after every restart of the central unit. If
                # a rejected message blocked, the installation would lock
                # itself out at the first start after the rollout, and nobody
                # would find the reason.
                #
                # Blocking happens via the registration, and that one IS signed:
                # a device without a valid key never gets a `hello` through and
                # therefore never becomes ready for operation. Simply
                # discarding the message here is enough.
                return
            raw = json.dumps(body)
            # A message that gets through clears the latch. That only makes it
            # LOUDER, never quieter: if one is rejected again afterwards, it
            # stands in the log at once instead of only after the 30 seconds
            # have elapsed.
            self._sig_complained.pop(who, None)

        # HAS THIS INSTRUCTION ALREADY BEEN HERE? (2.1.1)
        #
        # The signature proves who wrote the telegram. It says nothing at all
        # about how often that telegram may be delivered — and the same bytes
        # a second time were a second punishment over the channel (finding
        # Philine 2026-09-15, reproduced on the bench in centest/t_replay.py).
        #
        # This stands AFTER the signature and BEFORE both branches, and it
        # stands here and nowhere else: exactly one door for both control
        # topics, exactly as with the signature above it.
        #
        # It runs independently of project_key. Not because a key-less
        # installation deserves the protection more, but because a guard that
        # is sometimes on is a guard nobody can reason about — and the fields
        # cost the sender nothing.
        if punsign.control_topic(msg.topic):
            try:
                ctl = json.loads(raw)
            except json.JSONDecodeError:
                return
            ok, why = self.control_guard.check(ctl)
            if not ok:
                # LOUD, and without the 30-second latch of the signature
                # complaint above. That latch exists for devices that talk
                # every second; here there is one sender, the web interface,
                # and every refusal on this path is a finding.
                self.app_logger.error(
                    f'MQTT: Steuertelegramm auf {msg.topic} abgewiesen: {why}')
                audit.central('control_rejected',
                              data={'topic': msg.topic, 'reason': why,
                                    'id': ctl.get('id') if isinstance(ctl, dict) else None,
                                    'what': ctl.get('what') if isinstance(ctl, dict) else None})
                return

        if msg.topic == 'punisher/central/reload':
            # {"what": "program"|"slave"|"devices"|"logbook"|"all", "ref_id": n}
            # plus the control envelope (id, boot_id, seq, ts_ms, ttl_ms).
            #
            # `ref_id` and not `id` since 2.1.1: `id` identifies the TELEGRAM
            # now, the row number needed a name of its own.
            with self.lock:
                self.reload_requests.append((str(ctl.get('what', 'all')),
                                             ctl.get('ref_id')))
            return
        if msg.topic == 'punisher/central/request':
            # {"what": "punish"|"reward"|"review"|"propose"|"activate", "slave_id", "level", "kind", "reason", "user", "week"}
            # plus the control envelope (id, boot_id, seq, ts_ms, ttl_ms).
            with self.lock:
                self.requests.append(ctl)
            return

        if len(parts) < 4:
            return
        self.sweep_timeouts()
        device = str(parts[2])
        kind = parts[3]

        # The signature has already been checked at the top of this method —
        # for EVERY topic, including the two under central/. There used to be a
        # second copy of that check here, which is why the central/ branches
        # above it were reached unchecked.

        with self.lock:
            if kind == 'available':
                # THE LAST WORD OF THE BROKER ARRIVES HERE, not on `state`.
                #
                # Until 2.1.0 the firmware put its will on `state`. That topic is
                # signed, a will cannot be signed, and so every single one was
                # thrown away — the central unit never learned that a device had
                # gone (finding Philine 2026-09-15). `available` is unsigned by
                # design, and the reason given in punsign.py is exactly this one.
                #
                # Three payloads, and only one of them means anything:
                #   "offline"  the will, or a clean deregistration
                #   "online"   set retained by the device when it connects
                #   "ping"     sign of life, every heartbeat
                if raw.strip() == 'offline':
                    self.app_logger.info('MQTT: device offline (LWT) ' + device)
                    audit.central('device_offline', device=device)
                    self.tdevice.pop(device, None)
                    self.devices.remove_device(device)
                    self.slaves.set_online_device_to_offline(device)
                    return
                # Sign of life; ask an unknown device for its functions.
                if device not in self.tdevice:
                    self.app_logger.info('MQTT: new device ' + device)
                    self._touch(device, 'pending')
                    # THE CLOCK FIRST, THEN THE QUESTION (2.1.0).
                    #
                    # A device that has just connected owns no time yet — it
                    # borrows one from the heartbeat, and since 2.1.0 it drops
                    # anything whose age it cannot judge. A `settings` sent into
                    # that first second would be thrown away, and the device
                    # would wait for an answer that never comes.
                    #
                    # One extra heartbeat closes the window. Same connection,
                    # same QoS, so it is on the wire before the settings are —
                    # MQTT keeps the order of one publisher.
                    self.heartbeat()
                    self.request_initial(device)
                else:
                    self._touch(device, self.tdevice[device]['status'])

            elif kind == 'hello':
                # {model, device, fw_version, capabilities[]}
                self._register_from_hello(device, raw)

            elif kind == 'response':
                # Answer to {initial}: bare model_UUID (36 characters)
                answer = raw.strip()
                if len(answer) == 36 and device in self.tdevice:
                    self.devices.add_device(self, answer, device, None, True)
                    self._touch(device, 'online')
                    self.slaves.get_slave_id_from_offline_device(device)
                elif answer.startswith('{'):
                    self._handle_response(device, answer)
                else:
                    self.app_logger.debug(f'MQTT: response from {device}: {answer!r}')

            elif kind == 'state':
                self._handle_state(device, raw)

            elif kind == 'event':
                self._handle_event(device, raw)

            elif kind == 'live':
                self._handle_live(device, raw)

            elif kind == 'log':
                self._handle_log(device, raw)

    # ------------------------------------------------------------------ #
    def _register_from_hello(self, device, raw):
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            self.app_logger.warning('MQTT: bad hello from ' + device)
            return
        model = j.get('model')
        caps = j.get('capabilities') or []
        fw = j.get('fw_version')
        # The envelope that the device reports ITSELF. Not every one does so:
        # it is filled per device type from `reportLimits()`, and a device
        # without capabilities (e.g. the SelfTest) has nothing to report. `None`
        # therefore means "nothing reported", not "firmware too old".
        lim = j.get('limits') or None
        if not model:
            return

        # ---- Judge the firmware (from 2.0 on) -------------------------------
        #
        # Two floors per model: framework AND sketch. Below the floor the device
        # is REGISTERED — it is there after all, and the supervisor should see
        # it — but no longer accepts any commands. Letting a device that is too
        # old quietly run along would be the opposite of what the floor is
        # there for; not showing it at all would leave the supervisor in the
        # dark about why a device is missing.
        mdl = devicemodels.by_uuid(model)
        verdict = fwversion.judge(j, mdl)
        mac = (j.get('mac') or '').strip().lower()
        chip = (j.get('chip') or '').strip().lower()
        locked = bool(j.get('mac_locked'))

        degraded = devicemodels.degraded_of(j)
        self.devices.add_device(self, model, device, None, True, capabilities=caps, fw=fw,
                                limits=lim, degraded=degraded)
        dobj = self.devices.get_device(device)
        if dobj is not None and getattr(dobj, 'refused_caps', None):
            # A device claimed more than its model. That is the SelfTest hole
            # of 2026-09-14, and it is loud on purpose.
            self.app_logger.warning(
                f'MQTT: {device} claims capabilities its model does not have — refused: '
                f'{sorted(dobj.refused_caps)}')
            audit.central('capability_refused', device=device,
                          data={'model': model, 'refused': sorted(dobj.refused_caps)})
        if degraded:
            self.app_logger.warning(f'MQTT: {device} reports components out of order: {degraded}')
            audit.central('device_degraded', device=device, data={'degraded': degraded})
        # A hello DESCRIBES. Whether the device is there is decided elsewhere —
        # see _touch(): a retained message establishes no presence.
        self._touch(device, 'online')
        self.devices.set_blocked(device, verdict.reason if verdict.blocked else '')
        self.slaves.get_slave_id_from_offline_device(device)
        self._record_identity(device, model, mac, chip, locked, verdict, j)
        self._record_boot(device, verdict, j)

        self.app_logger.info(f'MQTT: hello {device} model={model} caps={caps} fw={fw}'
                             + (f' mac={mac}' if mac else ' mac=none (Firmware < 2.0)')
                             + (f' limits={lim}' if lim else ' limits=none (keine gemeldet)'))
        audit.central('device_online', device=device,
                      data={'model': model, 'fw': fw, 'mac': mac, 'chip': chip})

        if verdict.blocked:
            self.app_logger.error(f'MQTT: {device} GESPERRT — {verdict.reason}')
            audit.central('device_blocked', device=device,
                          data={'reason': verdict.reason,
                                'framework': fwversion.text(verdict.framework),
                                'sketch': fwversion.text(verdict.sketch)})
            # AND TAKE IT OFF THE CHANNEL.
            #
            # Finding 2026-09-14: commands to a blocked device are indeed
            # refused (torturedevice._cmd) — but the punishment channel of the
            # slave does not run over the device topic, it runs over
            # punisher/slaves/<id>/punish, on which EVERY assigned stimulator
            # listens. A block that closes the one way and leaves the other
            # one open is none.
            #
            # The central unit cannot exempt anybody on a broadcast. So it
            # takes the assignment away from the device: it cancels the channel.
            # The release goes via `settings`, not via a command — it is
            # protective, and the block must never hit anything protective.
            self.assign_slave(device, 0, '')
        elif verdict.outdated:
            self.app_logger.warning(f'MQTT: {device} veraltet — {verdict.reason}')
            audit.central('device_outdated', device=device,
                          data={'reason': verdict.reason})

    def _record_identity(self, device, model, mac, chip, locked, verdict, hello):
        """Hand MAC and versions to the main loop for writing.

        THIS RUNS IN THE PAHO THREAD, AND THE DATABASE BELONGS TO THE OTHER ONE.

        Until 2.0.0 it wrote here, with `self.cursor` — the very cursor of the
        one connection that punisher.py uses in its main loop. PyMySQL is not
        thread-safe: two threads on one connection can interleave a query with
        another\'s result, and the outcome is not always an error. It can be a
        fetchall() that returns somebody else\'s rows, and in this installation
        that could be the wrong slave\'s calibration (finding Philine 2026-09-15).
        The burst is real, too: every hello lands here, and at startup they all
        arrive at once while the main loop is querying.

        The codebase already had the right shape for this — `reload_requests`
        and `requests` are queues that the main loop drains under the lock.
        This was the one place that reached past it. So it queues now as well,
        and identity_queue() writes it, single-threaded, like everything else.

        The cost is honest and small: the identity lands one main-loop pass
        later instead of at once. Nothing acts on it in between.
        """
        if not mac:
            return
        with self.lock:
            self.identity_writes.append(
                {'device': device, 'model': model, 'mac': mac, 'chip': chip,
                 'locked': bool(locked),
                 'framework': fwversion.text(verdict.framework),
                 'sketch': fwversion.text(verdict.sketch),
                 'name': fwversion.sketch_name(hello),
                 'blocked': verdict.reason if verdict.blocked else ''})

    def _record_boot(self, device, verdict, hello):
        """Queue this start of the device for the main loop to write (2.2.0).

        The hello carries `boot`: the id the device drew when it came up, the
        reset reason, and — when its RTC memory survived — how long the
        previous life ran and what it was doing last. The hello is RETAINED
        and is re-sent on request, so the same start arrives more than once;
        (device, boot id) is unique in the table and the writer uses INSERT
        IGNORE. A firmware below 2.2.0 sends no `boot`, and then there is
        nothing to record — not a row with made-up values.
        """
        b = hello.get('boot')
        if not isinstance(b, dict) or not b.get('id'):
            return
        with self.lock:
            self.boot_writes.append({
                'device': device, 'boot_id': str(b.get('id'))[:16],
                'reason': str(b.get('reason') or 'unknown')[:16],
                'framework': fwversion.text(verdict.framework),
                'sketch': fwversion.text(verdict.sketch),
                'name': fwversion.sketch_name(hello),
                'heap_free': b.get('heap_free'), 'count': b.get('count'),
                'uptime_s': b.get('uptime_before_s'),
                'last_cmd': (str(b['last_cmd'])[:24] if b.get('last_cmd') else None),
                'last_err': (str(b['last_err'])[:64] if b.get('last_err') else None)})

    def write_boot(self, cursor, rec):
        """Write ONE queued start. Main loop, main cursor. Returns True when
        the row was NEW — only then is it a start worth a log line."""
        def _int(v):
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None
        try:
            n = cursor.execute(
                "INSERT IGNORE INTO device_boots (db_device, db_boot_id, db_reason,"
                "  db_fw_framework, db_fw_sketch, db_fw_name, db_heap_free, db_boot_count,"
                "  db_uptime_s, db_last_cmd, db_last_err)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (rec['device'], rec['boot_id'], rec['reason'], rec['framework'], rec['sketch'],
                 rec['name'], _int(rec['heap_free']), _int(rec['count']), _int(rec['uptime_s']),
                 rec['last_cmd'], rec['last_err']))
        except Exception as e:  # noqa: BLE001 — a missing table must not stop the loop
            self.app_logger.error(f'device_boots: {e}')
            return False
        if not n:
            return False
        why = rec['reason']
        # A restart the device did not choose is a finding, and it is loud.
        # A software or power-on start is what a flash or a switch-on looks
        # like; those are information.
        line = (f"MQTT: {rec['device']} started ({why})"
                + (f", previous life {rec['uptime_s']} s" if rec['uptime_s'] is not None else ', previous life unknown')
                + (f", last cmd {rec['last_cmd']}" if rec['last_cmd'] else '')
                + (f", last error {rec['last_err']!r}" if rec['last_err'] else ''))
        if why in ('poweron', 'software', 'external', 'deepsleep'):
            self.app_logger.info(line)
        else:
            self.app_logger.warning(line)
        audit.central('device_boot', device=rec['device'],
                      data={k: rec[k] for k in ('boot_id', 'reason', 'uptime_s', 'last_cmd',
                                                'last_err', 'heap_free', 'count')})
        return True

    def write_identity(self, cursor, rec):
        """Write ONE queued identity. Called by the main loop, with its cursor.

        THREE CASES, AND THE THIRD IS THE ONE THAT GETS FORGOTTEN

        1. The device stands in the database and the MAC matches -> refresh.
        2. The device is not there yet -> it does NOT get in by itself.
           It lands in `device_sightings` and waits for the supervisor to
           assign it deliberately — the same way as with an unknown
           RFID tag. An installation that equips itself is an installation
           in which nobody knows what is attached to it.
        3. The device stands there but reports a DIFFERENT MAC. Then it is a
           different device under the same address. That is reported and the
           assignment is NOT overwritten — otherwise a foreign chip silently
           inherits the calibration of a human being.
        """
        device, mac, chip = rec['device'], rec['mac'], rec['chip']
        model, name = rec['model'], rec['name']
        fw_f, fw_s = rec['framework'], rec['sketch']
        try:
            cursor.execute(
                "SELECT dev_id, dev_mac FROM devices WHERE dev_address = %s "
                "   OR dev_name = %s LIMIT 1", (device, device))
            row = cursor.fetchone()

            if row is None:
                cursor.execute(
                    "INSERT INTO device_sightings "
                    "  (ds_mac, ds_chip, ds_uuid, ds_model, ds_fw_name) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE ds_uuid=VALUES(ds_uuid), "
                    "  ds_chip=VALUES(ds_chip), ds_model=VALUES(ds_model), "
                    "  ds_fw_name=VALUES(ds_fw_name), ds_count=ds_count+1",
                    (mac, chip, device, model, name))
                self.app_logger.warning(
                    f'MQTT: unbekanntes Geraet {mac} ({device}) — wartet auf Zuordnung')
                audit.central('device_unknown', device=device,
                              data={'mac': mac, 'chip': chip, 'model': model})
                return

            old_mac = (row.get('dev_mac') or '').strip().lower()
            if mac and old_mac and old_mac != mac:
                self.app_logger.error(
                    f'MQTT: {device} meldet MAC {mac}, eingetragen ist {old_mac} — '
                    f'das ist ein ANDERES Geraet unter derselben Adresse')
                audit.central('device_mac_mismatch', device=device,
                              data={'reported': mac, 'stored': old_mac})
                self.devices.set_blocked(
                    device, f'meldet eine andere MAC ({mac}) als eingetragen ({old_mac})')
                return

            cursor.execute(
                "UPDATE devices SET dev_mac = COALESCE(NULLIF(%s, ''), dev_mac), "
                "  dev_chip = %s, dev_mac_locked = %s, dev_fw_framework = %s, "
                "  dev_fw_sketch = %s, dev_fw_name = %s, dev_blocked = %s, "
                "  dev_seen = NOW() "
                " WHERE dev_id = %s",
                (mac, chip, 1 if rec['locked'] else 0, fw_f, fw_s, name,
                 rec['blocked'], row['dev_id']))
        except Exception as e:                      # noqa: BLE001
            # The installation must not come to a halt over a bookkeeping question.
            self.app_logger.error(f'MQTT: Geraeteidentitaet nicht gespeichert: {e}')

    def _handle_state(self, device, raw):
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            return
        st = j.get('state')
        if st == 'offline':
            # NOT the will any more — that one arrives on `available` since
            # 2.1.0 (see there). What can still land here is a device that says
            # goodbye deliberately, in a signed message. Kept for that case;
            # the firmware of the installation does not use it.
            self.app_logger.info('MQTT: device reports offline ' + device)
            audit.central('device_offline', device=device)
            self.tdevice.pop(device, None)
            self.devices.remove_device(device)
            self.slaves.set_online_device_to_offline(device)
            return
        self._touch(device, 'online')
        self.devices.set_state(device, j)
        # The device holds an assignment the central unit does not know (e.g.
        # after a restart of the central unit): release it. The central unit is
        # master.
        sid = j.get('slave_id')
        if sid and not self.slaves.has_slave_id(int(sid)):
            self.app_logger.info(f'MQTT: {device} holds unknown slave_id {sid} -> unassign')
            self.assign_slave(device, 0, '')

    def _handle_event(self, device, raw):
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            return
        self._touch(device, 'online')
        event = j.get('event', '?')
        slave_id = j.get('slave_id', 0)
        self.app_logger.info(f'EVENT {device} slave={slave_id} {event} {j}')
        audit.device_event(device, slave_id, event, j)
        # This is where the adaptive plan / WAITEVENT hooks in later:
        # the central unit translates events (reward/punishment/not_attached/
        # bond_lost/...) into consequences per program and envelope.
        self.devices.set_response(device, j)
        self.slaves.on_device_event(device, slave_id, event, j)

    def _handle_response(self, device, raw):
        """JSON answer to a command. The central only acts on one of them: a routine the
        device does not hold with a matching checksum (doc 17 §7). The database is the
        truth, so the central sends the routine again - once, to avoid a ping-pong."""
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            self.app_logger.debug(f'MQTT: response from {device}: {raw!r}')
            return
        self._touch(device, 'online')
        self.app_logger.info(f'RESPONSE {device} {j}')
        ro_id = j.get('routine_id')
        err = str(j.get('error') or j.get('reason') or '')
        if not ro_id or 'routine' not in err.lower():
            return
        s = self.slaves.holder_of(device)
        key = (device, int(ro_id))
        last = self._routine_resent.get(key, 0.0)
        if not s or time.time() - last < self._routine_resend_gap_s:
            self.app_logger.warning(f'MQTT: {device} keeps rejecting routine {ro_id} ({err})')
            return
        self._routine_resent[key] = time.time()
        self.app_logger.warning(f'MQTT: {device} does not have routine {ro_id} ({err}) - sending it again')
        s.routine_push(int(ro_id))

    def _handle_live(self, device, raw):
        """Trainer -> central -> the participant's bridges. The central stays the only
        publisher on a slave channel (doc 14 3a), and it is the place where 'away'
        is turned into silence for EVERY track (doc 19 §6.1)."""
        try:
            j = json.loads(raw)
        except json.JSONDecodeError:
            return
        slave_id = int(j.get('slave_id') or 0)
        if not slave_id or not self.slaves.has_slave_id(slave_id):
            return
        # The device CLAIMS a slave_id; the assignment is the truth (doc 03: the
        # central is the only publisher on a slave channel, so it vouches for what
        # it relays). A mismatch is dropped, not corrected - a device that is wrong
        # about its wearer must not steer anybody's bridge. (Review 2026-09-11.)
        holder = self.slaves.holder_of(device)
        if not holder or int(getattr(holder, 'slave_id', 0)) != slave_id:
            self.app_logger.warning(f'MQTT: live value from {device} claims slave {slave_id}, '
                                    f'which does not hold this device - dropped')
            return
        # MISSING IS PESSIMISTIC (2.1.1): a reading that does not say whether
        # it is valid is not, and one that does not say whether the person is
        # there is relayed as "gone". Until then the defaults here were the
        # optimistic pair (valid, present) — the one spot on this path where an
        # absent field counted as permission. The device side reads it the
        # same way now; the two must agree, or the device's silence and the
        # relay's disagree about the same reading (finding Philine 2026-09-15).
        away = bool(j.get('away', True)) or not bool(j.get('valid', False))
        # Explicit None checks (review 2026-09-11): a MISSING err is unknown, and
        # unknown stays pessimistic (1.0) - `or 0.0` would read it as a perfect run
        # and hand out the full accuracy-coupled reward, while err 0.0 itself is
        # falsy and must survive as 0.0. Missing depth stays 0.0: no depth, no share.
        err = j.get('err')
        depth = j.get('depth')
        out = {'ts_ms': int(time.time() * 1000), 'device': device, 'away': away,
               'depth': 0.0 if (away or depth is None) else float(depth),
               'err': 1.0 if (away or err is None) else float(err),
               'valid': not away}
        self.publish_live(slave_id, out)

    def _handle_log(self, device, raw):
        try:
            j = json.loads(raw)
            self.app_logger.info(f'DEVLOG {device} [{j.get("level")}] {j.get("msg")}')
        except json.JSONDecodeError:
            self.app_logger.info(f'DEVLOG {device} {raw}')

    # --- paho callbacks -------------------------------------------------- #
    def on_publish(self, client, userdata, mid, reason_code, properties):
        pass

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        self.app_logger.debug(f'MQTT subscribed {mid} {reason_code_list}')

    def on_log(self, client, userdata, level, buf):
        pass

    # ------------------------------------------------------------------ #
    # Between two attempts to reach the broker at start-up: it grows, because an
    # installation that has been waiting a quarter of an hour is not helped by a
    # line every two seconds.
    CONNECT_WAIT_S = (2, 5, 10, 20, 30)

    def _connect_waiting(self, host, port, keepalive):
        """Wait for the broker instead of dying at it.

        UNTIL 2.5 THIS WAS A BARE `connect()`. A broker that was not up yet — a
        restart of the machine in which mosquitto comes a moment later, a
        service that was restarted by hand — killed the central unit with a
        traceback. On the bench that happened twice in one afternoon, and both
        times it first looked like a fault of the installation.

        Dying is not better than waiting: the process manager restarts it
        anyway, so the effect is the same and only the log is worse. Waiting is
        visible, says why, and the moment the broker is there the day goes on.

        Everything is caught, including a certificate error (`ssl.SSLError` is
        an `OSError`). That is deliberate: a wrong certificate at three in the
        morning must not take the display and the web interface with it. It is
        written out on EVERY attempt, so a permanent fault is loud and not
        quietly waited away."""
        wait, n = 0, 0
        while True:
            try:
                self.connect(host, port, keepalive)
                if n:
                    self.app_logger.info('MQTT: Broker %s:%s erreicht (nach %d Versuchen)', host, port, n + 1)
                return
            except OSError as e:
                n += 1
                wait = self.CONNECT_WAIT_S[min(n - 1, len(self.CONNECT_WAIT_S) - 1)]
                self.app_logger.warning('MQTT: Broker %s:%s nicht erreichbar (%s: %s) — '
                                        'neuer Versuch in %d s', host, port, type(e).__name__, e, wait)
            time.sleep(wait)

    def run(self, config, logger, devices, db, slaves):
        self.app_logger = logger
        self.devices = devices
        self.cursor = db
        self.slaves = slaves
        self.project_key = (config['mqtt'].get('project_key') or '').strip() or None
        if self.project_key:
            logger.info('MQTT: Nachrichten werden signiert (HMAC-SHA256)')
        else:
            logger.warning('MQTT: KEIN project_key in der config.ini — Nachrichten '
                           'werden weder signiert noch geprueft')
        # The central unit keeps `[mqtt]` — it is the one process that has
        # always had that section to itself in spirit. What is new (2.1.1) is
        # that the OTHERS have their own now, so that the broker's access list
        # can tell them apart at all; see libs/mqttaccount.py and project
        # document 40. The account is logged because an installation in which
        # everything still speaks as one user has an access list without
        # effect, and that is worse than none: it looks like protection.
        logger.info('MQTT: Konto %s', config['mqtt']['username'])
        self.username_pw_set(config['mqtt']['username'], config['mqtt']['password'])
        # TLS (2.3, doc 53). Before connect(), and it raises rather than falling
        # back: a configuration that asks for TLS and cannot get it must not
        # quietly send the device account's password in the clear.
        mqtttls.configure(self, config, logger)
        # The port from the config, not 1883 written into the code. The example
        # config has offered `port` for a long time and the web interface and
        # the display have read it — only the central unit did not, so a broker
        # on any other port was reachable for everyone except the one process
        # that matters (finding Philine 2026-09-15).
        self._connect_waiting(config['mqtt']['hostname'], mqtttls.port(config), 180)
        self.loop_start()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop,
                                           name='central-heartbeat', daemon=True)
        self._hb_thread.start()
