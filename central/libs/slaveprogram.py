# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
import logging
import time

import actions
import audit
import devicemodels
import i18n
import tasktypes

logger = logging.getLogger('Punisher')

# Waiting time between sign-on and the first programme step (time to create
# the devices). Comes from the original code (60 s); now visible and in the log.
PROGRAM_START_DELAY_S = 60
# Waiting time after a change of programme during operation (web: a different
# active programme) — the devices have already been created.
PROGRAM_SWITCH_DELAY_S = 5
# Pause after a blocking task (result is in) until the next step
AFTER_RESULT_DELAY_S = 3


class slaveprogram():
    """Works through the programme steps of a slave sequentially.

    Steps come as dicts out of program_commands (pc_id, pc_command,
    pc_parameter), sorted by pc_id. Dispatch and validation run over the
    action registry (libs/actions.py) — no action stands here by name any
    more.

    `plan` is the complete list of steps (for display and web), `pos` the
    number of steps already executed. replace_steps() exchanges the version
    during operation: the position stays, the rest applies anew
    (decision Philine 2026-09-07).

    Logbook (doc 14): trainable steps are adapted to the task level of the
    slave before the command and started as a run; blocking tasks (TaskPad,
    trainer) halt the programme until the device reports the result (or the
    deadline of the action expires). The privilege 'no_restraints' skips
    MAGLOCK steps.
    """

    def __init__(self, slave, steps, start_delay=PROGRAM_START_DELAY_S):
        self.slave = slave
        self.plan = list(steps)
        self.pos = 0
        self.stamp = time.time()
        self.nextaction = time.time() + start_delay
        self.last = None            # last executed step (dict) for the display
        self.wait_run = None        # blocking run whose result is being waited for
        self.finished = not self.plan
        logger.info("Program for '%s': %d steps, first step in %d s",
                    slave.slave_name, len(self.plan), start_delay)
        self.execute()

    # ------------------------------------------------------------------ #
    @property
    def steps(self):
        return self.plan[self.pos:]

    def remaining(self):
        return len(self.plan) - self.pos

    def replace_steps(self, steps):
        """Take over the new version of the programme, keep the position."""
        new = list(steps)
        old_remaining = self.remaining()
        self.plan = new
        if self.pos > len(self.plan):
            self.pos = len(self.plan)
        self.finished = self.pos >= len(self.plan)
        logger.info("Program for '%s' replaced: %d steps, position %d (was %d left, now %d left)",
                    self.slave.slave_name, len(self.plan), self.pos, old_remaining, self.remaining())
        self.slave.on_progress()

    def progress(self):
        """For display/web: plan with markings, next step in n seconds."""
        now = time.time()
        steps = []
        for i, st in enumerate(self.plan):
            a = actions.get(st['pc_command'])
            try:
                params = actions.parse_params(a, st['pc_parameter']) if a else {}
            except actions.ActionError:
                params = {}
            steps.append({
                'i': i + 1, 'code': st['pc_command'],
                'name': a.name if a else st['pc_command'],
                'params': params,
                'text': self._param_text(a, params) if a else st['pc_parameter'],
                'done': i < self.pos, 'current': i == self.pos and not self.finished,
                'trainable': bool(a and a.trainable),
            })
        waiting = self.wait_run is not None and not self.wait_run.finished
        return {
            'steps': steps, 'pos': self.pos, 'total': len(self.plan),
            'finished': self.finished,
            'next_in_s': (None if waiting else max(0, int(self.nextaction - now))) if not self.finished else None,
            'waiting_for': ({'action': self.wait_run.action, 'run': self.wait_run.id,
                             'elapsed_s': int(now - self.wait_run.started)} if waiting else None),
            'last': self.last,
        }

    @staticmethod
    def _param_text(action, params):
        parts = []
        for p in action.params:
            if p.name in params:
                v = params[p.name]
                if p.name == 'max_punish' and v == -1:
                    continue
                parts.append(f"{p.label or p.name} {v}{(' ' + p.unit) if p.unit else ''}")
        return ', '.join(parts)

    # ------------------------------------------------------------------ #
    def execute(self):
        if self.finished:
            return
        # Blocking task: wait until the device has delivered the result
        if self.wait_run is not None:
            if not self.wait_run.finished:
                return
            logger.info("Program for '%s': result for %s received, continuing", self.slave.slave_name, self.wait_run.action)
            # The task is over, so anything coupled to it is over too (doc 19 §6.1).
            if hasattr(self.slave, 'estim_stop'):
                self.slave.estim_stop()
            self.wait_run = None
            self.nextaction = int(time.time()) + AFTER_RESULT_DELAY_S
            self._advance()
            return
        if int(self.nextaction) >= int(time.time()):
            return
        if self.pos >= len(self.plan):
            self._finish()
            return

        step = self.plan[self.pos]
        try:
            action, params = actions.validate_step(step['pc_command'], step['pc_parameter'])
        except actions.ActionError as e:
            # Should no longer occur after the start check; skip the step,
            # do not stand still.
            logger.error("Program step %s for '%s' skipped: %s",
                         step.get('pc_id'), self.slave.slave_name, e)
            self._advance()
            return

        if action.capability and not self.slave.has_capability(action.capability):
            logger.warning("Program step %s (%s) for '%s': no online device with capability '%s' - skipped",
                           step.get('pc_id'), action.code, self.slave.slave_name, action.capability)
            self.slave.on_step(action, params, skipped=f"kein Gerät mit '{action.capability}'")
            self._advance()
            return

        # HERE ONCE STOOD: with the sanction "cage_on" a REMOTE_CONTROL step
        # was REPLACED by the V-Cage. That was dropped on 2026-09-14 (decision
        # Philine: "You can switch it on. But then it has to happen
        # deliberately.").
        #
        # The reason: a programme step would have switched the cage on by
        # itself - at a place where the plan says "mode off". Whoever reads the
        # plan would not see that. Switching on is from now on ALWAYS a move of
        # the supervisor (action V_CAGE or remote control); the sanction only
        # sees to it that a cage already running does not fall away by itself.
        # That stands in slave.py (_cage_hold / _cage_reissue).

        # Sanction "In restraints" (doc 26): the lock stays shut. An UNLOCK step
        # is dropped, and the privilege "No restraints" no longer takes effect -
        # slave.has_privilege() sees to that, it knows the precedence. A
        # programme that opens while a sanction closes would otherwise give a
        # different result depending on the order of the steps.
        if action.code == 'UNLOCK' and self.slave.has_sanction('restrained'):
            logger.info("Program step %s (UNLOCK) for '%s' skipped: sanction restrained",
                        step.get('pc_id'), self.slave.slave_name)
            self.slave.on_step(action, params, skipped=i18n._('Auflage: in Fesseln'))
            self._advance()
            return

        # Privilege "No restraints" (doc 14): MAGLOCK is dropped
        if action.code == 'MAGLOCK' and self.slave.has_privilege('no_restraints'):
            logger.info("Program step %s (MAGLOCK) for '%s' skipped: privilege no_restraints", step.get('pc_id'), self.slave.slave_name)
            self.slave.on_step(action, params, skipped=i18n._('Privileg: ohne Fesseln'))
            self._advance()
            return

        # Logbook: apply the task level, determine target/allowed punishments
        run = None
        prep = None
        lb = getattr(self.slave, 'logbook', None)
        # Additions that the day plan attaches to a synthetic step (libs/dayplan.py):
        # target_override = target of the weekly plan task, level_bump = stretch run in
        # free training, points_factor = half weighting of free training,
        # routine_override = waveform of the plan task/challenge (doc 17 §14).
        if action.trainable and lb is not None and lb.enabled:
            prep = lb.prepare(self.slave.slave_id, action, params,
                              level_bump=int(step.get('level_bump') or 0),
                              target_override=step.get('target_override'),
                              max_punish_override=step.get('max_punish_override'),
                              routine_override=step.get('routine_override'))
            if prep is None and tasktypes.get(action.code) is not None and lb.enabled:
                # Preparation failed (e.g. no waveform at that level):
                # skip the step, do not stand still.
                logger.warning("Program step %s (%s) for '%s' skipped: task could not be prepared",
                               step.get('pc_id'), action.code, self.slave.slave_name)
                self.slave.on_step(action, params, skipped=i18n._('Aufgabe nicht vorbereitbar'))
                self._advance()
                return
        exec_params = prep[0] if prep else params

        # Envelope of the device that is actually going to run this step. Here -
        # and only here - it is known which one that is; in the programme editor
        # it is not (decision Philine 2026-09-11). A value above it is capped, not
        # refused: the run happens, and the deviation is on the record. Without
        # this the device would cap it silently and the logbook would hold a
        # number that never left the plant (doc 24).
        capped = []
        dev_uuid = self.slave.device_for(action.capability) if action.capability else None
        dev = self.slave.devices.get_device(dev_uuid) if dev_uuid else None
        env = getattr(dev, 'envelope', None) if dev else None
        if env:
            exec_params = dict(exec_params)
            for p in action.params:
                if not p.limit or p.name not in exec_params:
                    continue
                cap = devicemodels.limit_for(env, p.limit, p.unit)
                v = exec_params[p.name]
                if cap is None or isinstance(v, bool) or not isinstance(v, int) or v <= cap:
                    continue
                exec_params[p.name] = cap
                capped.append((p.name, v, cap, p.unit))
        if capped:
            logger.warning("Program step %s (%s) for '%s': capped to the device envelope: %s",
                           step.get('pc_id'), action.code, self.slave.slave_name,
                           ', '.join('%s %s->%s%s' % (n_, w, c, (' ' + u) if u else '')
                                     for n_, w, c, u in capped))
            audit.central('step_capped', device=dev_uuid, slave_id=self.slave.slave_id,
                          data={'code': action.code, 'step': step.get('pc_id'),
                                'capped': [{'field': n_, 'wanted': w, 'sent': c, 'unit': u}
                                           for n_, w, c, u in capped]})

        logger.info("Execute %s for '%s' %s%s", action.code, self.slave.slave_name, exec_params,
                    f" (Stufe {prep[1]})" if prep else '')

        # Create the run BEFORE the command: the device answers at once (task_start,
        # on refusal cmd_rejected, in the error case also fault) — these events have to
        # find the run already there (review 2026-09-10; before that the reverse order).
        if prep:
            device = self.slave.device_for(action.capability)
            factor = float(step.get('points_factor') or 1.0)
            run = lb.start(self.slave.slave_id, self.slave.slave_name, action, exec_params, device,
                           prep[1], prep[2], prep[3], program_id=self.slave.program_id,
                           points_factor=factor, free=bool(step.get('points_factor')))

        if action.handler:
            args = [exec_params[p.name] for p in action.params]
            kwargs = {}
            if action.handler == 'hold_task':
                kwargs['kind'] = action.code.lower()
            getattr(self.slave, action.handler)(*args, **kwargs)

        delay = action.next_delay(exec_params)
        # A non-blocking step that plays a WAVEFORM runs as long as the waveform is
        # long - the registry cannot know that, it would need the database. Without
        # this the next step would start on top of a running one (doc 19).
        if not action.blocking and 'routine' in exec_params and lb is not None and lb.routines_enabled:
            pay = lb.routine_payload(exec_params.get('routine'))
            if pay:
                import routines as _routines
                delay = max(delay, _routines.est_seconds(pay['row'], exec_params.get('repeats') or 1))
        if delay:
            self.nextaction = int(time.time()) + delay
            logger.info("Next step for '%s' in %d s (%d left)",
                        self.slave.slave_name, delay, self.remaining() - 1)

        self.last = {'i': self.pos + 1, 'code': action.code, 'name': action.name,
                     'params': exec_params, 'ts': time.time(), 'level': prep[1] if prep else None}
        self.slave.on_step(action, exec_params)

        if run is not None and action.blocking:
            # The programme halts until the device reports the result (deadline: action.timeout)
            self.wait_run = run
            logger.info("Program for '%s' waits for result of %s (up to %d s)",
                        self.slave.slave_name, action.code, action.timeout_s(exec_params))
            self.slave.on_progress()
            return
        self._advance()

    def on_event(self, event, data):
        pass

    def _advance(self):
        # Deliberately NO direct _finish() at the end of the plan: the tick checks
        # `nextaction` BEFORE the end of the plan, so a waveform in the LAST step
        # gets to play out. Finishing right away cut a final 60 s reward off after
        # 4 s, because the next plan block started immediately and its coupling
        # overwrote the bridge (review 2026-09-11, seen in the e2e log). With
        # nextaction already in the past the next tick ends the programme within a
        # second - the same behaviour as before.
        self.pos += 1
        self.slave.on_progress()

    def _finish(self):
        if not self.finished:
            self.finished = True
            logger.info("Program for '%s' finished", self.slave.slave_name)
            self.slave.on_finished()
