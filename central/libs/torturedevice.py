# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""A single training device (ESP32) on the PunisherDevice framework.

Commands go through the unified cmd envelope (mqtt.send_command).
Capabilities come out of the device's `hello` message; where that is missing, the
model registry (libs/devicemodels.py) steps in as the fallback.

Action names are the ones the device firmware expects in onCommand():
MagLock "lock"/"unlock", Collar "shock"/"vibe"/"beep"/"mode"/"collar_settings",
Trainer "trainer"/"calibrate_depth", TaskPad "task"/"cue".

Punishments do NOT run through this object, but through the channel of the
slave (punmqtt.publish_punish, doc 14 3a) — every stimulator of the
slave listens there.
"""

import devicemodels
import i18n
import routines


class torturedevice:

    def __init__(self, mqtt, model_uuid, device, ip_address, status,
                 capabilities=None, fw=None, limits=None, degraded=None):
        self.mqtt = mqtt
        self.uuid_device = device
        self.uuid_model = model_uuid
        self.ip_address = ip_address
        self.status = status
        self.fw_version = fw
        # Blocked: plain text, why. Empty = running. It gets set out of the
        # assessment of the hello message (libs/fwversion.py), or on a MAC that
        # does not match the one on record.
        self.blocked = ''
        self.last_event = None
        self.last_state = None

        self.model = devicemodels.by_uuid(model_uuid)
        self.uuid_name = self.model.name if self.model else f'unknown model {model_uuid}'

        # Capabilities: THE MODEL'S, narrowed by what the firmware reports and
        # by what the device reports as out of order — never widened (doc 42
        # point 4). Until 2.2.0 this took the reported list as it came, which
        # meant a device could grant itself a capability by claiming it.
        self.degraded = list(degraded or [])
        self.set_capabilities(capabilities, self.degraded)

        # Envelope of exactly THIS device: what its firmware reports in `hello`,
        # falling back to the model catalogue (doc 23). The programme runner caps
        # against it, so a value the device would refuse never leaves the plant.
        self.envelope = devicemodels.envelope_of(self.model, limits)

    def set_capabilities(self, reported, degraded):
        self.capabilities, self.refused_caps = devicemodels.effective_capabilities(
            self.model, reported, degraded)
        self.degraded = list(degraded or [])
        # A cuff that holds without power is a person who cannot get out. That
        # is not "one cuff fewer", it blocks everything that closes — the same
        # switch the firmware floor uses, so the same rule applies: refused,
        # except what releases (see _cmd).
        # Kept as its own text, not folded into `blocked`: set_blocked() writes
        # `blocked` from the firmware verdict after every hello and would wipe
        # this. The two are combined where they are read (is_blocked()).
        stuck = devicemodels.stuck_of(self.degraded)
        self.stuck_reason = i18n._('Komponente klemmt: {c}', c=', '.join(stuck)) if stuck else ''

    def is_blocked(self):
        """The one question everything that acts asks. Firmware floor, MAC
        mismatch — or a component that holds without power."""
        return self.blocked or self.stuck_reason

    def available(self):
        """How many of the counted components are usable (MagLock: cuffs). None if not counted."""
        return devicemodels.available_count(self.model, self.degraded)

    # ------------------------------------------------------------------ #
    def has(self, capability):
        return capability in self.capabilities

    def get_device(self):
        return self.uuid_device

    def _cmd(self, action, args=None, ttl_ms=5000):
        # A BLOCKED DEVICE GETS NO COMMANDS.
        #
        # The exception is everything that SWITCHES OFF. A device whose firmware
        # is too old may well be running right now — and to refuse it the stop
        # because it is blocked would turn the block against the human being
        # instead of pointing it at his protection.
        why = self.is_blocked()
        if why and action not in ('stop', 'emergency', 'estim', 'safe', 'unlock'):
            # `unlock` releases — a stuck cuff is exactly the case in which the
            # release must go through, and the firmware floor never blocked
            # anything that opens.
            import audit
            audit.central('command_refused', device=self.uuid_device,
                          data={'action': action, 'reason': why})
            return
        self.mqtt.send_command(self.uuid_device, action, args, ttl_ms)

    def inital_settings(self):
        pass

    # --- Actions -------------------------------------------------------- #
    def shock(self, seconds, countdown, warn=1):
        if self.has('shock'):
            self._cmd('shock', {'seconds': int(seconds), 'countdown': int(countdown),
                                'warn': bool(warn)})

    def maglock(self, minutes, countdown=30, cuffs=4):
        if not self.has('lock'):
            return
        # The step says how many cuffs it needs; the device says how many it
        # has today (doc 42 point 4). Too few is not "lock what you can" — a
        # cross with three cuffs closed is a different position than the one
        # the programme meant. It is refused, and loudly.
        have = self.available()
        if have is not None and have < int(cuffs):
            import audit
            audit.central('command_refused', device=self.uuid_device,
                          data={'action': 'lock', 'reason': f'needs {int(cuffs)} cuffs, has {have}',
                                'degraded': self.degraded})
            return
        self._cmd('lock', {'lock_in_minutes': int(minutes),
                           'countdown_in_seconds': int(countdown),
                           'cuffs': int(cuffs)},
                  ttl_ms=15000)

    def unlock(self):
        if self.has('lock'):
            self._cmd('unlock')

    def collar_settings(self, shock, vibe, beep, duration):
        if self.has('collar'):
            self._cmd('collar_settings', {'shock': int(shock), 'vibe': int(vibe),
                                          'beep': int(beep), 'duration': int(duration)})

    # --- Trainer (ToF), firmware Trainer-3.x: one command "trainer" with mode ----
    # depth_ref: (rest_mm, deep_mm) out of the slave's calibration (posture
    # 'depth'); percent targets are converted into millimetres here. Without a
    # calibration the trainer gets percent only and falls back on its own defaults.
    @staticmethod
    def _depth_mm(pct, depth_ref):
        if not depth_ref:
            return None
        rest, deep = depth_ref
        return int(round(rest - (rest - deep) * max(0, min(100, pct)) / 100.0))

    def trainer_repetition(self, count, depth_start=40, depth_end=90, stroke_s=8, max_miss=0,
                           max_punish=-1, depth_ref=None):
        if self.has('trainer_rep'):
            args = {'mode': 'repetition', 'count': int(count), 'depth_start_pct': int(depth_start),
                    'depth_end_pct': int(depth_end), 'stroke_s': int(stroke_s), 'max_miss': int(max_miss)}
            if depth_ref:
                args['rest_mm'], args['deep_mm'] = int(depth_ref[0]), int(depth_ref[1])
                args['depth_start_mm'] = self._depth_mm(depth_start, depth_ref)
                args['depth_end_mm'] = self._depth_mm(depth_end, depth_ref)
            self._cmd('trainer', args, ttl_ms=10000)

    def trainer_endurance(self, depth=70, hold_s=30, max_s=300, max_punish=-1, depth_ref=None):
        if self.has('trainer_end'):
            args = {'mode': 'endurance', 'depth_pct': int(depth), 'hold_s': int(hold_s), 'max_s': int(max_s)}
            if depth_ref:
                args['rest_mm'], args['deep_mm'] = int(depth_ref[0]), int(depth_ref[1])
                args['depth_mm'] = self._depth_mm(depth, depth_ref)
            self._cmd('trainer', args, ttl_ms=10000)

    def trainer_freeform(self, minutes, bpm=0, idle_s=30, max_punish=-1, depth_ref=None):
        if self.has('trainer_free'):
            args = {'mode': 'freeform', 'duration_s': int(minutes) * 60, 'bpm': int(bpm), 'idle_s': int(idle_s)}
            if depth_ref:
                args['rest_mm'], args['deep_mm'] = int(depth_ref[0]), int(depth_ref[1])
            self._cmd('trainer', args, ttl_ms=10000)

    # Waveform routines (doc 17 §7, extended for tracks in doc 19 §7). Transferred
    # as a transaction because 1000 breakpoints do not fit into one MQTT message;
    # the device only accepts a COMPLETE waveform whose CRC32 matches the byte
    # stream the central sent. One transfer per track, each with its own checksum.
    def plays_routines(self):
        return self.has('trainer_routine') or self.has('estim_routine')

    def routine_push(self, routine, tracks, crc):
        """tracks: [{track, role, profile, channel, mode, couple, points, crc32}]."""
        if not self.plays_routines():
            return False
        ro_id = int(routine['ro_id'])
        axis = routine.get('ro_axis') or routines.AXIS_TIME
        self._cmd('routine_begin', {
            'routine_id': ro_id, 'crc32': int(crc), 'axis': axis,
            'purpose': routine.get('ro_purpose') or routines.PURPOSE_TASK,
            'tracks_total': len(tracks),
            'points_total': sum(len(t['points']) for t in tracks),
            'tol_default': int(routine.get('ro_tol_default') or 10),
            'fullscale_pct': int(routine.get('ro_fullscale_pct') or 25),
            'loop_ms': int(routine.get('ro_loop_ms') or 0)}, ttl_ms=15000)
        for t in tracks:
            self._cmd('routine_track', {
                'routine_id': ro_id, 'track': t['track'], 'role': t['role'],
                'profile': t['profile'], 'channel': t['channel'], 'mode': t['mode'],
                'couple': t['couple'] or '', 'points_total': len(t['points']),
                'crc32': int(t['crc32'])}, ttl_ms=15000)
            for seq, chunk in enumerate(routines.chunks(t['points'], axis=axis)):
                self._cmd('routine_chunk', {'routine_id': ro_id, 'track': t['track'], 'seq': seq,
                                            'points': [list(p) for p in chunk]}, ttl_ms=15000)
        self._cmd('routine_commit', {'routine_id': ro_id, 'crc32': int(crc)}, ttl_ms=15000)
        return True

    def trainer_routine(self, routine, repeats=1, max_punish=-1, depth_ref=None, crc32=0, limits=None):
        """Start a routine run. The command names id + CRC; on a mismatch the device
        answers 'routine unknown' and the central sends the routine again."""
        if not self.has('trainer_routine'):
            return
        args = {'mode': 'routine', 'routine_id': int(routine['ro_id']), 'crc32': int(crc32),
                'repeats': max(1, min(int(repeats or 1), routines.MAX_REPEATS)),
                'loop_ms': int(routine.get('ro_loop_ms') or 0),
                'fullscale_pct': int(routine.get('ro_fullscale_pct') or 25)}
        # Trigger threshold, lockout and pause window come from `scoring` (doc 17 §9).
        for k in ('fault_ms', 'fault_gap_s', 'away_pause_s', 'start_wait_s', 'invalid_max'):
            if limits and limits.get(k) is not None:
                args[k] = int(limits[k])
        if depth_ref:
            args['rest_mm'], args['deep_mm'] = int(depth_ref[0]), int(depth_ref[1])
        self._cmd('trainer', args, ttl_ms=10000)

    def estim_routine(self, routine, repeats=1, max_pct=100, crc32=0, limits=None, ceiling=None):
        """Play a waveform on the E-Stim bridge (doc 19).

        The curve drives the STRENGTH — the pulse height — and `ceiling` is the only
        thing above it: the participant's calibration for this very device, in percent
        per channel (decision Philine 2026-09-11, doc 28).

        Without a ceiling nothing is sent, and that is not a convenience check. Until
        2026-09-11 the plant never wrote the strength at all, on the assumption that
        the wearer sets it at the device. In this mode she cannot — so the height is
        ours, and a height nobody measured is not a height we may guess. The bridge
        refuses such a command too; this is the same refusal one step earlier, where
        it can still be explained to a person.
        """
        if not self.has('estim_routine') or not ceiling:
            return False
        args = {'mode': 'routine', 'routine_id': int(routine['ro_id']), 'crc32': int(crc32),
                'repeats': max(1, min(int(repeats or 1), routines.MAX_REPEATS)),
                'max_pct': max(1, min(100, int(max_pct or 100))),
                'str_a': max(0, min(100, int(ceiling[0]))),
                'str_b': max(0, min(100, int(ceiling[1]))),
                'loop_ms': int(routine.get('ro_loop_ms') or 0)}
        for k in ('day_max_s', 'event_max_s', 'frame_ms', 'stale_ms'):
            if limits and limits.get(k) is not None:
                args[k] = int(limits[k])
        self._cmd('estim', args, ttl_ms=10000)
        return True

    def estim_stop(self):
        """Stop output. Belt and braces three times over: the command, the device's own
        silence after 100 ms without a frame (doc 19 §4.4), and — since the bridge writes
        the strength itself — an explicit zero, because the strength STAYS in the device
        until somebody changes it."""
        if self.has('estim_routine'):
            self._cmd('estim', {'mode': 'off'})

    def estim_couple(self, routine, tracks, crc, ceiling=None):
        """Hand the bridge the coupling waveform (depth axis) that runs alongside a
        trainer task, and switch it on. Same rule as estim_routine: no ceiling, no run."""
        if not self.has('estim_routine') or not ceiling:
            return False
        self.routine_push(routine, tracks, crc)
        self._cmd('estim', {'mode': 'couple', 'routine_id': int(routine['ro_id']),
                            'str_a': max(0, min(100, int(ceiling[0]))),
                            'str_b': max(0, min(100, int(ceiling[1]))),
                            'crc32': int(crc)}, ttl_ms=10000)
        return True

    def trainer_calibrate(self, seconds=15):
        if self.has('depth_cal'):
            self._cmd('calibrate_depth', {'seconds': int(seconds)}, ttl_ms=10000)

    def trainer_stop(self):
        if self.has('trainer_rep') or self.has('trainer_end') or self.has('trainer_free') \
                or self.has('trainer_routine'):
            self._cmd('trainer', {'mode': 'off'})

    # --- TaskPad, firmware TaskPad-1.x: one command "task" with kind ----------------
    def nose_button(self, target_s, wobble_ms=300, vibe=1, button=1, start_s=15, max_punish=-1):
        if self.has('task_nose'):
            self._cmd('task', {'kind': 'nose', 'target_s': int(target_s), 'wobble_ms': int(wobble_ms),
                               'vibe': int(vibe), 'button': int(button), 'start_s': int(start_s)}, ttl_ms=10000)

    def reaction(self, rounds, deadline_ms=1500, gap_min_s=2, gap_max_s=8, vibe=0, max_punish=-1):
        if self.has('task_reaction'):
            self._cmd('task', {'kind': 'reaction', 'rounds': int(rounds), 'deadline_ms': int(deadline_ms),
                               'gap_min_ms': int(gap_min_s) * 1000, 'gap_max_ms': int(gap_max_s) * 1000,
                               'vibe': int(vibe)}, ttl_ms=10000)

    def rhythm(self, bpm, beats, tol_ms=150, fault_after=3, button=1, max_punish=-1):
        if self.has('task_rhythm'):
            self._cmd('task', {'kind': 'rhythm', 'bpm': int(bpm), 'beats': int(beats), 'tol_ms': int(tol_ms),
                               'fault_after': int(fault_after), 'button': int(button)}, ttl_ms=10000)

    def memory(self, rounds, show_ms=600, vibe=0, max_punish=-1):
        if self.has('task_memory'):
            self._cmd('task', {'kind': 'memory', 'rounds': int(rounds), 'show_ms': int(show_ms),
                               'vibe': int(vibe)}, ttl_ms=10000)

    def cue(self, ms=1500, vibe=2, led=0):
        """Attention signal on the TaskPad (blinks/vibrates); the answer is a press event."""
        if self.has('task_confirm'):
            self._cmd('cue', {'ms': int(ms), 'vibe': int(vibe), 'led': int(led)}, ttl_ms=3000)

    def task_stop(self):
        if any(self.has(c) for c in ('task_nose', 'task_reaction', 'task_rhythm', 'task_memory',
                                      'task_tray', 'task_silence', 'task_kneel')):
            self._cmd('task', {'kind': 'off'})

    # Holding tasks of further devices (tray/silence/kneeling pad): same contract
    def hold_task(self, kind, target_s, tolerance, max_punish=-1):
        cap = {'tray': 'task_tray', 'silence': 'task_silence', 'kneel': 'task_kneel'}.get(kind)
        if cap and self.has(cap):
            self._cmd('task', {'kind': kind, 'target_s': int(target_s), 'tolerance': int(tolerance)}, ttl_ms=10000)

    # --- Fixed modes of the collar: the device decides and punishes on its own.
    def _mode(self, mode, **args):
        payload = {'mode': int(mode)}
        # max_min 0 = maximum of the collar (envelope mode_max_min) -> do not send it along
        payload.update({k: v for k, v in args.items()
                        if v is not None and not (k == 'max_min' and not v)})
        self._cmd('mode', payload)

    def pet(self, max_min, warn=1, angle=45, repeat_s=15, cal_s=5, max_punish=-1, ref_pet=None, ref_stand=None):
        """ref_pet/ref_stand: calibrated postures [x,y,z] (g) of this slave
        for this collar (table slave_calibration). Without references the collar
        learns the posture at the start and uses the angle `angle`."""
        if self.has('mode_pet'):
            self._mode(4, max_min=max_min, warn=bool(warn), angle=angle,
                       repeat_s=repeat_s, cal_s=cal_s, ref_pet=ref_pet, ref_stand=ref_stand)

    def statue(self, max_min, warn=1, angle=20, repeat_s=15, cal_s=3, max_punish=-1, ref=None):
        """Hold a posture (Collar-3.2, mode 6). ref: optional [x,y,z] as a fixed reference,
        otherwise the collar learns the posture after cal_s seconds."""
        if self.has('mode_statue'):
            self._mode(6, max_min=max_min, warn=bool(warn), angle=angle, repeat_s=repeat_s,
                       cal_s=cal_s, ref=ref)

    def v_cage(self, max_min, rssi=-75, warn_s=10, repeat_s=15, punish_max_s=600):
        if self.has('mode_v_cage'):
            # warn is always on in the V-Cage (the firmware enforces it)
            self._mode(1, max_min=max_min, rssi=rssi, warn_s=warn_s,
                       repeat_s=repeat_s, punish_max_s=punish_max_s)

    def sleep_deprivation(self, max_min, warn=1, still_s=60, repeat_s=30, max_punish=-1):
        if self.has('mode_sleep_dep'):
            self._mode(3, max_min=max_min, warn=bool(warn), still_s=still_s, repeat_s=repeat_s)

    def random_mode(self, max_min, warn=1, min_s=10, max_s=340, count=0):
        if self.has('mode_random'):
            self._mode(2, max_min=max_min, warn=bool(warn), min_s=min_s, max_s=max_s, count=count)

    def timer_mode(self, max_min, warn=1, interval_s=60, count=0):
        if self.has('mode_timer'):
            self._mode(5, max_min=max_min, warn=bool(warn), interval_s=interval_s, count=count)

    def remote_control(self):
        if self.has('mode_remote'):
            self._mode(0)

    def vibe(self, level, ms=300):
        if self.has('vibe'):
            self._cmd('vibe', {'level': int(level), 'ms': int(ms)})

    def piep(self, level, ms=300):
        if self.has('beep'):
            self._cmd('beep', {'level': int(level), 'ms': int(ms)})

    def stretch(self):
        pass

    def switch(self):
        pass

    def stop(self):
        """Soft stop (safe state, no freezing) — base action."""
        self._cmd('stop', ttl_ms=2000)

    def identify(self):
        self._cmd('identify', ttl_ms=10000)

    def emergency(self):
        self.mqtt.emergency(self.uuid_device)

    # --- Feedback ------------------------------------------------------- #
    def set_state(self, state):
        self.last_state = state

    def set_response(self, response):
        self.last_event = response

    def get_response(self):
        return self.last_event
