# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
import logging
import random
import time

import audit
import i18n
import routines
from slaveprogram import slaveprogram, PROGRAM_SWITCH_DELAY_S

logger = logging.getLogger('Punisher')

SUMMARY_CACHE_S = 5.0          # recompute the logbook summary per slave at most every 5 s
REVIEW_SHOW_S = 90             # report card of the previous week stays in the session state this long after login


class slave:
    """A registered slave: his devices and his running program.

    `program_id`/`program_name` belong to the active program (pointer in the DB).
    Changes from the database during operation come in via
    replace_program() / switch_program() / set_devices() / rename()
    (punisher.py apply_db_changes). Progress and steps report via
    the hooks on_step/on_progress/on_finished to `notify` (the central unit
    publishes the session state for display and web).

    Logbook (doc 14): trainable steps are kept as runs in the logbook
    (libs/logbook.py); device events run through the logbook
    (count punishments, violations -> punishment channel, result -> grade).
    """

    def __init__(self, mqtt, devices, slave_id, slave_name, rfid, program, mode,
                 program_id=None, program_name=None, notify=None, logbook=None):
        self.mqtt = mqtt
        self.devices = devices
        self.logbook = logbook

        self.slave_id = slave_id
        self.slave_name = slave_name
        self.slave_rfid = rfid
        self.slave_mode = mode
        self.program_id = program_id
        self.program_name = program_name
        self.notify = notify or (lambda kind, slave, **kw: None)
        self.login_ts = time.time()
        self.events = []             # last device events (for the display)
        self.device_labels = {}      # device UUID -> label from the DB (dev_address)
        self.calibration = {}        # device-UUID -> {'pet': [x,y,z], 'stand': [x,y,z], 'depth': [rest_mm, deep_mm, 0]}
        self.review = None           # report card of the previous week (once after login, display)
        self.attention = None        # guard attention (ATTENTION_ON)
        self.day = None              # libs/dayplan.py DayRunner — the running day (doc 14 §12.1)
        # Calibration run (doc 33): this login serves exclusively for
        # calibrating. No program, no day plan, no routine — but the devices
        # are assigned to her, otherwise nothing at all could be measured.
        # The central unit sets this directly after add_slave().
        self.calibration_mode = False
        self._summary = (0.0, None)

        # V-Cage (doc 26, decision Philine 2026-09-14)
        #
        # `_cage_hold` remembers WITH WHICH VALUES the V-Cage was last switched
        # on deliberately — None means: it is not running. This is set NOT at
        # the call of v_cage(), but at the mode_start event of the
        # collar. Reason: the supervisor often switches it on via the
        # remote control of the web interface, and that sends the command
        # directly to the device, without running through this object. Whoever
        # hangs on the call sees precisely this path not at all.
        #
        # The sanction `cage_on` switches NOTHING on. It only makes sure that
        # a running cage does not fall away by itself.
        self._cage_hold = None
        # `_cage_pending` stands at True between the reissue and the
        # mode_start that confirms it. It prevents several events shortly after
        # one another from sending the cage multiple times — but it does NOT
        # block the next genuine occasion once the collar has confirmed.
        # A pure time lock did exactly that: after a reissue a REMOTE_CONTROL
        # one second later fell into the lock, and the cage was
        # gone (test run 2026-09-14).
        self._cage_pending = False
        self._cage_sent_at = 0.0

        # CRITICAL BUGFIX: these two lists were class attributes and
        # therefore shared by ALL slaves. A device that was assigned
        # to slave A also showed up at slave B;
        # B's program would have triggered A's devices.
        self.slave_devices = []
        self.slave_offline_devices = []

        # `program`: list of dicts (pc_id, pc_command, pc_parameter), sorted
        self.slave_program = slaveprogram(self, program)

    # ------------------------------------------------------------------ #
    def _settings(self, device, slave_id):
        self.mqtt.assign_slave(device, slave_id, self.slave_name)

    def add_device(self, device):
        if device not in self.slave_devices:
            self.slave_devices.append(device)
        self._settings(device, self.slave_id)
        # Collar preset only if the device is a collar.
        dev = self.devices.get_device(device)
        if dev and dev.has('collar'):
            # OPEN: magic numbers -> into the DB, within the envelope.
            self.collar_settings(10, 25, 20, 250)
        self.on_progress()

    def on_event(self, event, data):
        """Event of a device of this slave. Runs through the logbook
        (count punishments, violations -> channel, result -> grade) and the
        attention monitoring (button press)."""
        device = data.get('device') if isinstance(data, dict) else None
        cls = data.get('cls', 'info') if isinstance(data, dict) else 'info'
        if cls != 'info' or event in ('press', 'mode_start', 'task_start', 'trainer_start', 'lost', 'locked', 'released'):
            self.events.append({'ts': time.time(), 'event': event, 'device': device, 'cls': cls,
                                'data': data})
            self.events = self.events[-20:]
        if self.attention and event == 'press' and self.attention.get('cue_at'):
            self.attention['answered'] = True
            self.attention['hits'] = self.attention.get('hits', 0) + 1
        if event in ('mode_start', 'mode_end') and isinstance(data, dict):
            self._cage_track(event, data)
        if self.logbook is not None and isinstance(data, dict):
            result = self.logbook.device_event(self.slave_id, device, data)
            if result:
                self.invalidate_summary()
                self.notify('achievement', self, result=result)
        if hasattr(self.slave_program, 'on_event'):
            self.slave_program.on_event(event, data)
        self.notify('event', self, event=event, data=data)

    # --- Hooks of the program engine -------------------------------------
    def on_step(self, action, params, skipped=None):
        self.notify('step', self, action=action, params=params, skipped=skipped)

    def on_progress(self):
        self.notify('progress', self)

    def on_finished(self):
        self.notify('finished', self)

    # --- Logbook -----------------------------------------------------------
    def device_for(self, capability):
        """First online device with the capability (that is where the run happens)."""
        for device in self.slave_devices:
            dev = self.devices.get_device(device)
            if dev and dev.has(capability):
                return device
        return None

    def has_privilege(self, key):
        """Does this privilege REALLY apply — or does a sanction trump it?

        The precedence sits in logbook.privilege_active(). THIS function is
        deliberately called here and not has_privilege(): whoever asks during
        operation wants to know whether the privilege takes effect, not whether
        it was granted (decision Philine 2026-09-11).
        """
        return self.logbook is not None and self.logbook.privilege_active(self.slave_id, key)

    def has_sanction(self, key):
        """Is this sanction currently running? (doc 26)"""
        return self.logbook is not None and self.logbook.has_sanction(self.slave_id, key)

    def sanction_minutes_left(self, key):
        """How many minutes the sanction still runs, or None.

        Needed where a sanction has to be translated into a DURATION — the
        The V-Cage for instance needs a maximum duration. Without an end in time it
        returns None, and the call site inserts its own default."""
        if self.logbook is None:
            return None
        for s in self.logbook.sanctions_of(self.slave_id):
            if s['key'] != key or not s.get('until'):
                continue
            import datetime as _dt
            try:
                end = _dt.datetime.strptime(s['until'], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                return None
            return max(1, int((end - _dt.datetime.now()).total_seconds() // 60))
        return None

    def invalidate_summary(self):
        self._summary = (0.0, None)

    def summary(self):
        if self.logbook is None or not self.logbook.enabled:
            return None
        t, data = self._summary
        if data is None or time.time() - t > SUMMARY_CACHE_S:
            data = self.logbook.summary(self.slave_id)
            self._summary = (time.time(), data)
        return data

    def tick(self):
        """Periodic own logic (from execute()): attention monitoring."""
        a = self.attention
        if not a:
            return
        now = time.time()
        if a.get('cue_at'):
            if a.get('answered'):
                a['cue_at'] = None
                a['next_at'] = now + random.randint(a['min_s'], a['max_s'])
            elif now - a['cue_at'] > a['window_s']:
                a['cue_at'] = None
                a['missed'] = a.get('missed', 0) + 1
                a['next_at'] = now + random.randint(a['min_s'], a['max_s'])
                self.notify('warning', self, text='Aufmerksamkeit: Signal nicht bestätigt')
                if self.logbook is not None:
                    runs = self.logbook.runs_of(self.slave_id)
                    self.logbook.punish(self.slave_id, 1, 'any', 'attention_missed', 'central',
                                        run=runs[0] if runs else None)
            return
        if now >= a['next_at']:
            a['cue_at'] = now
            a['answered'] = False
            a['cues'] = a.get('cues', 0) + 1
            # Signal: the collar beeps, the TaskPad blinks/vibrates — answer = press on the TaskPad
            self._each_device('piep', 40, 400)
            self._each_device('cue', int(a['window_s'] * 1000), 2, 0)
            self.notify('event', self, event='attention_cue', data={'window_s': a['window_s']})

    # --- Changes from the database during operation ------------------------
    def replace_program(self, steps):
        """Same program ID, new step list: hold the position, the rest anew."""
        self.slave_program.replace_steps(steps)

    def switch_program(self, program_id, program_name, steps):
        """Different active program: anew from step 1, short start delay."""
        self.program_id = program_id
        self.program_name = program_name
        self.slave_program = slaveprogram(self, steps, start_delay=PROGRAM_SWITCH_DELAY_S)
        self.on_progress()

    def clear_program(self):
        self.program_id = None
        self.program_name = None
        self.slave_program = slaveprogram(self, [])
        self.on_progress()

    def rename(self, new_name):
        if new_name != self.slave_name:
            self.slave_name = new_name
            for device in self.slave_devices:      # devices display the name
                self._settings(device, self.slave_id)
            self.on_progress()

    def set_devices(self, wanted):
        """Take over the assignment from the DB (device UUIDs). Devices that have
        gone are released (slave_id 0), new online ones assigned, new offline ones
        remembered. Returns (added, removed)."""
        wanted = list(wanted)
        current = set(self.slave_devices) | set(self.slave_offline_devices)
        removed = [d for d in current if d not in wanted]
        added = [d for d in wanted if d not in current]
        for d in removed:
            if d in self.slave_devices:
                dev = self.devices.get_device(d)
                if dev:
                    dev.stop()
                self._settings(d, 0)
                self.slave_devices.remove(d)
                if self.logbook is not None:
                    self.logbook.abort_runs(self.slave_id, 'unassigned', device=d)
            self.remove_offline_device(d)
        for d in added:
            if self.devices.device_online(d):
                self.add_device(d)
            else:
                self.add_offline_device(d)
        if added or removed:
            self.on_progress()
        return added, removed

    def add_offline_device(self, device):
        if device not in self.slave_offline_devices:
            self.slave_offline_devices.append(device)

    def disconnect(self):
        self.estim_stop()                       # doc 19 §6.1: nothing keeps running without the slave
        if self.logbook is not None:
            self.logbook.abort_runs(self.slave_id, 'logout')
        if self.day is not None and self.day.running:
            self.day.end_day('aborted', quiet=True)   # logout without capitulation (supervisor/restart)
        self.attention = None
        for device in self.slave_devices:
            self._settings(device, 0)

    def stop(self):
        """Stop all devices of this slave immediately."""
        # First clear the marker, then stop: `stop` ends a running mode, and
        # the mode_end belonging to it must not repeat the V-Cage.
        self._cage_hold = None
        self.estim_stop()
        for device in self.slave_devices:
            dev = self.devices.get_device(device)
            if dev:
                dev.stop()
        if self.logbook is not None:
            self.logbook.abort_runs(self.slave_id, 'stop')

    def has_capability(self, capability):
        """Does this slave have at least one online device with the capability?"""
        return self.device_for(capability) is not None

    def get_offline_device(self, off_device):
        return off_device in self.slave_offline_devices

    def get_online_device(self, on_device):
        return on_device in self.slave_devices

    def set_offline_device_as_online(self, off_device):
        self.remove_offline_device(off_device)
        self.add_device(off_device)

    def set_online_device_as_offline(self, on_device):
        self.remove_online_device(on_device)
        self.add_offline_device(on_device)
        if self.logbook is not None:
            self.logbook.abort_runs(self.slave_id, 'device_lost', device=on_device)
        self.on_progress()

    def remove_offline_device(self, off_device):
        if off_device in self.slave_offline_devices:
            self.slave_offline_devices.remove(off_device)

    def remove_online_device(self, on_device):
        if on_device in self.slave_devices:
            self.slave_devices.remove(on_device)

    def execute(self):
        self.tick()
        # In a calibration run NOTHING runs by itself (doc 33). The central
        # unit gives it an empty program and no day anyway — but this here
        # is the explicit lock, and it stands at the only place that
        # triggers steps. A lock that relies on the list staying
        # empty is none: in this project it has twice been enough
        # that somewhere else something was written into it again.
        if self.calibration_mode:
            return
        if self.day is not None and self.day.running:
            self.day.tick()          # the day model leads the blocks (and thereby the program)
        else:
            self.slave_program.execute()

    def get_slave_name(self):
        return self.slave_name

    def get_slave_rfid(self):
        return self.slave_rfid

    def inital_settings(self):
        pass

    def snapshot(self):
        """State for the session status (display, web)."""
        snap = {
            'slave_id': self.slave_id, 'name': self.slave_name,
            'login_ts': int(self.login_ts),
            'calibration_mode': bool(self.calibration_mode),
            'program': {'id': self.program_id, 'name': self.program_name},
            'progress': self.slave_program.progress() if getattr(self, 'slave_program', None) else None,
            'devices': list(self.slave_devices),
            'devices_offline': list(self.slave_offline_devices),
            'device_labels': dict(self.device_labels),
            'calibrated': {d: sorted(c.keys()) for d, c in self.calibration.items()},
            'events': [{'ts': int(e['ts']), 'event': e['event'], 'device': e['device'], 'cls': e.get('cls', 'info')}
                       for e in self.events[-8:]],
            'attention': ({'active': True, 'cues': self.attention.get('cues', 0), 'hits': self.attention.get('hits', 0),
                           'missed': self.attention.get('missed', 0), 'cue_open': bool(self.attention.get('cue_at'))}
                          if self.attention else None),
        }
        if self.day is not None:
            day = self.day.snapshot()
            if day:
                snap['day'] = day
        summary = self.summary()
        if summary is not None:
            snap['logbook'] = summary
        if self.review and time.time() - self.login_ts < REVIEW_SHOW_S:
            snap['review'] = self.review
        return snap

    # ------------------------------------------------------------------ #
    def _each_device(self, method, *args, **kw):
        """Calls `method` on every online device of this slave.
        Devices that have meanwhile disappeared from the registry
        are skipped instead of raising a KeyError."""
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if dev and hasattr(dev, method):
                getattr(dev, method)(*args, **kw)

    def shock(self, seconds, countdown, warn=1):
        self._each_device('shock', seconds, countdown, warn)

    def vibe(self, level, ms=300):
        self._each_device('vibe', level, ms)

    def piep(self, level, ms=300):
        self._each_device('piep', level, ms)

    def stretch(self):
        pass

    def switch(self):
        pass

    # Fixed collar modes (the device decides itself, the central unit only switches)
    def pet(self, max_min, warn=1, angle=45, repeat_s=15, cal_s=5, max_punish=-1):
        # Pass along this slave's calibration per device (if present)
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if not dev or not dev.has('mode_pet'):
                continue
            cal = self.calibration.get(device) or {}
            if 'pet' not in cal:
                self.notify('warning', self, text=f'PET ohne Kalibrierung auf {device[:8]} - Halsband lernt beim Start ein')
            dev.pet(max_min, warn, angle, repeat_s, cal_s,
                    ref_pet=cal.get('pet'), ref_stand=cal.get('stand'))

    def statue(self, max_min, warn=1, angle=20, repeat_s=15, cal_s=3, max_punish=-1):
        self._each_device('statue', max_min, warn, angle, repeat_s, cal_s)

    def v_cage(self, max_min, rssi=-75, warn_s=10, repeat_s=15, punish_max_s=600):
        self._each_device('v_cage', max_min, rssi, warn_s, repeat_s, punish_max_s)
        # Remember the values here, do not read them only from the event:
        # mode_start reports back only max_min, not threshold, warning time and
        # repetition. Without them the cage would come back with the defaults
        # instead of with what the supervisor has set.
        self._cage_hold = {'max_min': int(max_min), 'rssi': int(rssi), 'warn_s': int(warn_s),
                           'repeat_s': int(repeat_s), 'punish_max_s': int(punish_max_s)}

    def sleep_deprivation(self, max_min, warn=1, still_s=60, repeat_s=30, max_punish=-1):
        self._each_device('sleep_deprivation', max_min, warn, still_s, repeat_s)

    def random_mode(self, max_min, warn=1, min_s=10, max_s=340, count=0):
        self._each_device('random_mode', max_min, warn, min_s, max_s, count)

    def timer_mode(self, max_min, warn=1, interval_s=60, count=0):
        self._each_device('timer_mode', max_min, warn, interval_s, count)

    def remote_control(self, by='program'):
        """End the collar mode.

        `by='program'`  — a program step or a block change in the day plan.
        `by='remote'`   — the supervisor, by hand.
        `by='logout'`   — the end of the day. Nothing comes after that.

        The difference counts only for the sanction `cage_on`: a program must
        not take the V-Cage away (almost every mode section ends with
        REMOTE_CONTROL — the cage would be gone at the first end of a section,
        and that is exactly what the sanction is to prevent). The supervisor
        may do it, for she imposed the sanction and can also lift it.

        The remote control of the web interface does NOT run through here
        today: it sends the command directly to the device. That is why
        `_cage_track()` recognises this case by the event mode_end(reason='off'),
        and `by='remote'` is the way for everything that later does go through
        this object after all (REST).
        """
        self._each_device('remote_control')
        # Running collar runs end as planned: the collar delivers mode_end
        # (switched, cls result); if not (offline), the logbook closes after 20 s.
        if self.logbook is not None:
            for device in list(self.slave_devices):
                dev = self.devices.get_device(device)
                if dev and dev.has('mode_remote'):
                    run = self.logbook.active_run(self.slave_id, device)
                    if run is not None:
                        run.timeout_at = time.time() + 20
                        run.timeout_reason = 'program'
        if by in ('remote', 'logout'):
            if self._cage_hold is not None:
                logger.info("V-Cage for '%s' dropped (%s)", self.slave_name, by)
            self._cage_hold = None
            # The mode_end('off') of the collar arrives in a moment. If a
            # fresh send timestamp still stood here, `_cage_track` would take
            # the event for the consequence of a program step and leave the
            # marker standing. So reset it explicitly.
            self._cage_pending = False
            self._cage_sent_at = 0.0
        else:
            self._cage_reissue('program_off')

    # ------------------------------------------------------------------ #
    # V-Cage: held, never switched on by itself
    #
    # Switching on is always a manual act of the supervisor — action V_CAGE in
    # the program or the remote control. The sanction `cage_on` only holds what
    # is already running. That is why nowhere here stands a call that switches
    # something on without `_cage_hold`: without a previous switch-on nothing
    # happens, no matter how many sanctions are running.
    def _cage_track(self, event, data):
        mode = data.get('mode')
        if event == 'mode_start':
            if mode == 'cage':
                # The collar confirms: the cage is running. Any reissue is
                # thereby done with.
                self._cage_pending = False
                if self._cage_hold is None:
                    # Switched on via the remote control — the command went
                    # past the central unit. What the device reports is all
                    # we know; the rest stays on the defaults.
                    self._cage_hold = {'max_min': int(data.get('max_min') or 0)}
                    logger.info("V-Cage for '%s' switched on by hand (%s min)",
                                self.slave_name, self._cage_hold['max_min'])
            return

        reason = data.get('reason') or ''
        if reason == 'stop':
            # Emergency stop or safe(). After the switch-off nothing comes
            # back by itself — that is the harmless direction, and it stays harmless.
            if self._cage_hold is not None:
                logger.info("V-Cage for '%s' dropped: mode ended with 'stop'", self.slave_name)
            self._cage_hold = None
            return
        if reason == 'switched':
            # Another mode follows in a moment. Now there is nothing to do —
            # the cage comes back when THAT one ends.
            return
        if reason == 'off':
            # Somebody switched the mode off explicitly (command mode 0).
            #
            # WHO, the device does not tell us — it cannot know whether the
            # command came from the program or from the supervisor. The central
            # unit knows: if it came from the program, remote_control() has
            # just reissued and `_cage_sent_at` stands fresh. If it does not
            # stand, it was the remote control — and the supervisor may switch
            # the cage off, even while the sanction is running. She imposed
            # it; she can also lift it.
            if time.time() - self._cage_sent_at >= 5:
                if self._cage_hold is not None:
                    logger.info("V-Cage for '%s' switched off by hand", self.slave_name)
                self._cage_hold = None
            return
        # max_duration, count, imu_lost: the mode has run out.
        self._cage_reissue(reason or 'mode_end')

    def _cage_reissue(self, why):
        if self._cage_hold is None or not self.has_sanction('cage_on'):
            return
        now = time.time()
        if self._cage_pending and now - self._cage_sent_at < 10:
            # Already reissued, the collar has only not yet confirmed it.
            # A mode change produces several events shortly after one another;
            # without this lock the cage would go out several times. The ten
            # seconds are the emergency brake for the case that the mode_start
            # never comes (device offline) — then the next occasion may try
            # again.
            return
        self._cage_pending = True
        self._cage_sent_at = now
        p = dict(self._cage_hold)
        logger.info("V-Cage for '%s' reissued (%s): sanction cage_on", self.slave_name, why)
        self.v_cage(p.get('max_min', 0), p.get('rssi', -75), p.get('warn_s', 10),
                    p.get('repeat_s', 15), p.get('punish_max_s', 600))
        audit.central('sanction_enforced', slave_id=self.slave_id,
                      data={'sanction': 'cage_on', 'why': why, 'params': p})

    def maglock(self, minutes, countdown=30, cuffs=4):
        self._each_device('maglock', minutes, countdown, cuffs)

    def unlock(self):
        self._each_device('unlock')

    def collar_settings(self, shock, vibe, beep, duration):
        self._each_device('collar_settings', shock, vibe, beep, duration)

    # --- Trainer (ToF) ------------------------------------------------------
    def _depth_ref(self, device):
        """(rest_mm, deep_mm) from the calibration 'depth' of this slave at the trainer."""
        cal = (self.calibration.get(device) or {}).get('depth')
        if cal and len(cal) >= 2 and cal[0] > cal[1] > 0:
            return (cal[0], cal[1])
        return None

    def _trainer(self, method, capability, *args, **kw):
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if not dev or not dev.has(capability):
                continue
            ref = self._depth_ref(device)
            if ref is None:
                self.notify('warning', self,
                            text=i18n._('Trainer {dev} ohne Tiefenkalibrierung - Gerätevorgaben gelten', dev=device[:8]))
            getattr(dev, method)(*args, depth_ref=ref, **kw)

    def trainer_repetition(self, count, depth_start=40, depth_end=90, stroke_s=8, max_miss=0, max_punish=-1):
        self._trainer('trainer_repetition', 'trainer_rep', count, depth_start, depth_end, stroke_s, max_miss, max_punish)

    def trainer_endurance(self, depth=70, hold_s=30, max_s=300, max_punish=-1):
        self._trainer('trainer_endurance', 'trainer_end', depth, hold_s, max_s, max_punish)

    def trainer_freeform(self, minutes, bpm=0, idle_s=30, max_punish=-1):
        self._trainer('trainer_freeform', 'trainer_free', minutes, bpm, idle_s, max_punish)

    def trainer_routine(self, routine, repeats=1, max_punish=-1, kopplung=0):
        """Follow a waveform (doc 17). The routine is pushed to the device first; the
        database is the truth, the device EEPROM only a cache (doc 17 §7)."""
        pay = self.logbook.routine_payload(routine) if self.logbook else None
        if not pay:
            self.notify('warning', self, text=i18n._('Wellenform {id} ist unbekannt - Aufgabe entfällt', id=routine))
            return
        if not routines.is_task(pay['row']) or not any(t['role'] == 'zieltiefe' for t in pay['tracks']):
            # Guard for MANUAL starts and API calls: the plan paths are filtered by
            # resolve(), but nothing stops a hand-typed id from naming a stimulation
            # waveform - the trainer would read 0.1 % steps as time and have nothing
            # to score (review 2026-09-11).
            self.notify('warning', self,
                        text=i18n._('Wellenform {id} ist keine bewertbare Aufgabe - Aufgabe entfällt', id=routine))
            return
        if kopplung:
            # Coupling waveform on the depth axis: the bridges react to how deep she
            # is while the task runs (doc 19 §2.1).
            self.estim_couple(int(kopplung))
        else:
            # No coupling wanted: disarm whatever an earlier run left on the bridges,
            # or a stale coupling would answer THIS task's live values (review 2026-09-11).
            self.estim_stop()
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if not dev or not dev.has('trainer_routine'):
                continue
            ref = self._depth_ref(device)
            if ref is None:
                self.notify('warning', self,
                            text=i18n._('Trainer {dev} ohne Tiefenkalibrierung - Gerätevorgaben gelten', dev=device[:8]))
            dev.routine_push(pay['row'], pay['tracks'], pay['crc32'])
            dev.trainer_routine(pay['row'], repeats, max_punish, depth_ref=ref, crc32=pay['crc32'],
                                limits=self.logbook.routine_limits())

    def routine_push(self, routine):
        """Push a waveform to every device of this participant that plays waveforms,
        ahead of the run (at login, and refilled during breaks - doc 17 §7)."""
        pay = self.logbook.routine_payload(routine) if self.logbook else None
        if not pay:
            return False
        sent = False
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if dev and dev.plays_routines():
                dev.routine_push(pay['row'], pay['tracks'], pay['crc32'])
                sent = True
        return sent

    # --- E-Stim bridge (doc 19) ---------------------------------------------- #
    def estim_ceiling(self, device):
        """(A %, B %) — the pulse-height ceiling for THIS participant at THIS bridge.

        Stored as calibration pose 'estim' (sc_x = channel A, sc_y = channel B, doc 28).
        It hangs on person AND device because both matter: how much she can take, and
        which Coyote generation and electrode placement it is measured at. Percent, not
        device units, because V2 counts 0..2047 and V3 counts 0..200 — the conversion
        belongs in the firmware, at the one place that knows which device it is talking
        to.

        None means: not measured. The caller must then not run. There is no default
        here on purpose; a default would be a guessed pulse height.
        """
        cal = (self.calibration.get(device) or {}).get('estim')
        if not cal or len(cal) < 2:
            return None
        a, b = int(round(cal[0])), int(round(cal[1]))
        if a <= 0 and b <= 0:
            return None
        return (max(0, min(100, a)), max(0, min(100, b)))

    def estim_uncalibrated(self):
        """Bridges of this participant that have no e-stim calibration. The names the
        supervision needs in order to fix it, not just a boolean."""
        out = []
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if dev and dev.has('estim_routine') and self.estim_ceiling(device) is None:
                out.append(device)
        return out

    def estim_routine(self, routine, repeats=1, max_pct=100):
        """Play a waveform on every E-Stim bridge of this participant."""
        pay = self.logbook.routine_payload(routine) if self.logbook else None
        if not pay:
            self.notify('warning', self, text=i18n._('Wellenform {id} ist unbekannt - Aufgabe entfällt', id=routine))
            return
        row = pay['row']
        if (row.get('ro_axis') or routines.AXIS_TIME) != routines.AXIS_TIME \
                or (row.get('ro_purpose') or routines.PURPOSE_TASK) == routines.PURPOSE_TASK:
            # What the parameter description promises, enforced (review 2026-09-11):
            # a depth-axis waveform has no end on the bridge (nothing runs out), and a
            # task has a scored track instead of outputs - neither is playable here.
            self.notify('warning', self,
                        text=i18n._('Wellenform {id} ist kein abspielbarer Reiz (Zweck oder Achse '
                                    'passen nicht) - Schritt entfällt', id=routine))
            return
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if not dev or not dev.has('estim_routine'):
                continue
            # Without a measured ceiling no output. Since 2026-09-11 this is a
            # refusal and no longer a warning: the curve drives the
            # pulse height, and the calibration is the only thing above it (doc 28).
            ceiling = self.estim_ceiling(device)
            if ceiling is None:
                self.notify('warning', self,
                            text=i18n._('E-Stim {dev} ohne Kalibrierung - kein Reiz', dev=device[:8]))
                continue
            dev.routine_push(pay['row'], pay['tracks'], pay['crc32'])
            dev.estim_routine(pay['row'], repeats, max_pct, crc32=pay['crc32'],
                              limits=self.logbook.estim_limits(), ceiling=ceiling)

    def estim_couple(self, routine):
        """Hand the coupling waveform (depth axis) to the bridges before a trainer task."""
        pay = self.logbook.routine_payload(routine) if self.logbook else None
        if not pay:
            return False
        if (pay['row'].get('ro_axis') or 'zeit') != 'tiefe':
            self.notify('warning', self,
                        text=i18n._('Wellenform {id} ist keine Kopplung (falsche Achse)', id=routine))
            return False
        sent = False
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if not dev or not dev.has('estim_routine'):
                continue
            ceiling = self.estim_ceiling(device)
            if ceiling is None:
                self.notify('warning', self,
                            text=i18n._('E-Stim {dev} ohne Kalibrierung - kein Reiz', dev=device[:8]))
                continue
            dev.estim_couple(pay['row'], pay['tracks'], pay['crc32'], ceiling=ceiling)
            sent = True
        return sent

    def estim_stop(self):
        """Silence every bridge. Called when a run ends and when she withdraws —
        doc 19 §6.1: 'weg' takes ALL tracks to zero, the punishment track too."""
        for device in list(self.slave_devices):
            dev = self.devices.get_device(device)
            if dev and dev.has('estim_routine'):
                dev.estim_stop()

    def trainer_calibrate(self, seconds=15):
        self._each_device('trainer_calibrate', seconds)

    # --- TaskPad --------------------------------------------------------------
    def nose_button(self, target_s, wobble_ms=300, vibe=1, button=1, start_s=15, max_punish=-1):
        self._each_device('nose_button', target_s, wobble_ms, vibe, button, start_s)

    def reaction(self, rounds, deadline_ms=1500, gap_min_s=2, gap_max_s=8, vibe=0, max_punish=-1):
        self._each_device('reaction', rounds, deadline_ms, gap_min_s, gap_max_s, vibe)

    def rhythm(self, bpm, beats, tol_ms=150, fault_after=3, button=1, max_punish=-1):
        self._each_device('rhythm', bpm, beats, tol_ms, fault_after, button)

    def memory(self, rounds, show_ms=600, vibe=0, max_punish=-1):
        self._each_device('memory', rounds, show_ms, vibe)

    def hold_task(self, target_s, tolerance, max_punish=-1, kind=None):
        """TRAY / SILENCE / KNEEL: the action determines the kind (slaveprogram passes kind along)."""
        self._each_device('hold_task', kind, target_s, tolerance)

    def instruction(self, minutes, text='Pause.'):
        """Neutral instruction (doc 14 §12.1): text on display and LCD, counts as a pause.
        No grading, no confirmation — the responsibility lies with the slave."""
        self.notify('instruction', self, text=str(text), minutes=int(minutes))

    # --- Channel / attention (framework) ---------------------------------------
    def channel_punish(self, level=1, kind='any'):
        if self.logbook is not None:
            runs = self.logbook.runs_of(self.slave_id)
            self.logbook.punish(self.slave_id, level, kind, 'program', 'central', run=runs[0] if runs else None)

    def channel_reward(self, level=1, kind='any'):
        if self.logbook is not None:
            self.logbook.reward(self.slave_id, level, kind, 'program', 'central')

    def attention_on(self, min_s=60, max_s=300, window_s=5):
        if not self.has_capability('task_confirm'):
            # Without a button (TaskPad) nobody can confirm the signal — every signal
            # would be a certain punishment (review 2026-09-10): do not activate, only warn.
            self.notify('warning', self, text='Aufmerksamkeit nicht aktiviert: kein Gerät mit Taster (task_confirm)')
            return
        min_s, max_s = int(min_s), max(int(min_s), int(max_s))
        self.attention = {'min_s': min_s, 'max_s': max_s, 'window_s': int(window_s),
                          'next_at': time.time() + random.randint(min_s, max_s), 'cue_at': None,
                          'answered': False, 'cues': 0, 'hits': 0, 'missed': 0}

    def attention_off(self):
        self.attention = None
