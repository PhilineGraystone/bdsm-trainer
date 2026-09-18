# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Day model (doc 14 §12.1, settled Philine 2026-09-10).

A slave logs in ONCE a day; after that the central unit leads him through the
whole day. No longer "login = one session", but "login = one day".

  Day plan (template, day_plans/day_blocks) = the STRUCTURE the supervisor lays down:
      a sequence of blocks, each block one of four kinds
        plan     — tasks from the weekly plan (optionally fixed to one action)
        program  — one fixed program
        free     — free training (the central unit picks the task)
        pause    — a neutral instruction ("You may eat something now"), counts as a break
      A plan/free block is a TIME BUDGET: as long as it lasts, the next task comes
      in the same block. The template repeats itself until the day is over.

  Day session (day_sessions) = the running day. It lives in the database so that a
      restart or a crash of the central unit CONTINUES the day instead of starting it anew.

Every block is carried out as a program — either a real one from the database or
a synthetic one with a single step (free training, instruction). That way everything
runs through the same engine (libs/slaveprogram.py) and the same logbook.

Hard limits from config.ini [safety] (no rule and no punishment raises them):
  day_minutes_max     absolute length of the day
  train_block_max_min at most this much training, then a compulsory break
  break_min_min       minimum length of that break
The length of the day per slave (slave_settings.ss_day_minutes) is the lever for the
reward/punishment editor and is capped at day_minutes_max.
"""

import datetime
import logging
import random
import time

import actions
import audit
import mystery
import routines
import taskblocks
import tasktypes

logger = logging.getLogger('Punisher')

BLOCK_MIN_S = 120           # below two minutes of remaining time no block is begun any more
BLOCK_GAP_S = 3             # small break between two tasks
IDLE_RETRY_S = 60           # idle (nothing possible): how long until the next attempt
IDLE_NOTIFY_S = 300         # ... and after how long it is reported, so it stays visible


def _minutes(seconds):
    return max(0, int(seconds // 60))


class DayRunner:
    """Leads the day of a logged-in slave (one instance per slave)."""

    def __init__(self, slave, logbook, on_end=None):
        self.slave = slave
        self.lb = logbook
        self.on_end = on_end            # f(slave, status) — the central unit logs out
        self.row = None                 # day_sessions row
        self.blocks = []                # template
        self.plan_name = None
        self.plan_id = None             # the plan the task decisions hang on (doc 58 §1)
        self.instruction = None         # {'text', 'until'} for the display and the LCD
        self.block = None               # running block
        self.idle = None                # {'text', 'since', 'told'} while nothing is possible (doc 58 §4)
        self.free_count = 0             # counter for the stretch run in free training
        self.paused_until = None        # set when open_day() refused because of a pause (doc 44 §2)
        self._next_at = 0.0

    # ------------------------------------------------------------------ #
    @property
    def running(self):
        return bool(self.row) and self.row['ds_status'] == 'running'

    def settings(self):
        r = self.lb.query('SELECT * FROM slave_settings WHERE ss_slave=%s', (self.slave.slave_id,), one=True)
        day_max = int(self.lb.limits['day_minutes_max'])
        default = min(int(self.lb.limits['day_minutes_default']), day_max)
        if not r:
            return {'day_plan': None, 'day_minutes': default, 'relogin': False}
        return {'day_plan': r['ss_day_plan'],
                'day_minutes': max(5, min(int(r['ss_day_minutes'] or default), day_max)),
                'relogin': bool(r['ss_relogin'])}

    def load_blocks(self, plan_id):
        """Blocks of the template; without an assignment the default (dp_default)."""
        row = None
        if plan_id:
            row = self.lb.query('SELECT * FROM day_plans WHERE dp_id=%s', (plan_id,), one=True)
        if not row:
            row = self.lb.query('SELECT * FROM day_plans WHERE dp_default=1 ORDER BY dp_id LIMIT 1', one=True)
        if not row:
            self.blocks, self.plan_name, self.plan_id = [], None, None
            return None
        self.plan_name = row['dp_name']
        self.plan_id = row['dp_id']
        self.blocks = self.lb.query('SELECT * FROM day_blocks WHERE db_plan=%s ORDER BY db_pos, db_id',
                                    (row['dp_id'],)) or []
        return row['dp_id']

    @staticmethod
    def _now_min():
        """Minute of the day by the clock of the central unit — the same clock the
        rule set's time conditions use, so nobody has to learn two of them."""
        n = datetime.datetime.now()
        return n.hour * 60 + n.minute

    def task_blocks(self):
        """The task decisions of the running day plan (doc 58 §1-3)."""
        return taskblocks.TaskBlocks.load(self.lb, self.plan_id)

    # ------------------------------------------------------------------ #
    def open_day(self):
        """Login: begin or continue the day. Returns (ok, reason)."""
        if not self.lb.day_enabled:
            return False, 'disabled'
        pa = self.lb.pauses.active(self.slave.slave_id)
        if pa is not None:
            # doc 44 §2: no login opens a day during a pause. The login itself
            # stands in the audit (punisher.py); this only says why no day follows.
            self.paused_until = pa['pa_to']
            return False, 'paused'
        st = self.settings()
        today = datetime.date.today()
        row = self.lb.query('SELECT * FROM day_sessions WHERE ds_slave=%s AND ds_day=%s',
                            (self.slave.slave_id, today), one=True)
        now = datetime.datetime.now()
        if row and row['ds_status'] != 'running' and not st['relogin']:
            # Capitulation or end of day: today it is over (can be switched off per slave)
            return False, row['ds_status']
        plan_id = self.load_blocks(st['day_plan'])
        if row:
            self.row = dict(row)
            if row['ds_status'] != 'running':
                # Re-login allowed: carry the same row on. The time window of the
                # day stays — capitulation does not lengthen the day.
                self.lb.execute("UPDATE day_sessions SET ds_status='running', ds_ended=NULL WHERE ds_id=%s",
                                (row['ds_id'],))
                self.row['ds_status'] = 'running'
                self.row['ds_ended'] = None
            if not self.row.get('ds_plan') and plan_id:
                self.lb.execute('UPDATE day_sessions SET ds_plan=%s WHERE ds_id=%s', (plan_id, self.row['ds_id']))
                self.row['ds_plan'] = plan_id
            logger.info("Day: '%s' setzt den Tag fort (Block %s, Ende %s)", self.slave.slave_name,
                        self.row['ds_pos'], self.row['ds_planned_end'])
        else:
            end = now + datetime.timedelta(minutes=st['day_minutes'])
            ds_id = self.lb.execute(
                'INSERT INTO day_sessions (ds_slave, ds_day, ds_started, ds_planned_end, ds_status, ds_plan) '
                "VALUES (%s,%s,%s,%s,'running',%s)",
                (self.slave.slave_id, today, now, end, plan_id))
            row = self.lb.query('SELECT * FROM day_sessions WHERE ds_id=%s', (ds_id,), one=True)
            self.row = dict(row) if row else None
            if self.row is None:
                return False, 'db'
            logger.info("Day: '%s' beginnt den Tag (%d min, Plan '%s', %d Blöcke)", self.slave.slave_name,
                        st['day_minutes'], self.plan_name or '-', len(self.blocks))
            self.lb.emit_event('day_start', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                             'minutes': st['day_minutes'], 'plan': self.plan_name,
                                             'end': str(end)[:19]})
            # a gap since the last counted day breaks the day streaks - said now,
            # at login, where she sees it (doc 44 §3)
            try:
                self.lb.streaks.on_day_start(self.slave.slave_id, today)
            except Exception as e:      # noqa: BLE001
                logger.error('streaks on_day_start: %s', e, exc_info=True)
        # deliver waiting effects (channel punishment/reward out of rules) now
        self.lb.apply_pending(self.slave.slave_id, self.slave)
        self._next_at = time.time() + BLOCK_GAP_S
        return True, 'ok'

    # ------------------------------------------------------------------ #
    def capitulate(self):
        """Placing the tag a second time: the slave gives up."""
        self.end_day('capitulated')

    def end_day(self, status='done', quiet=False):
        if not self.row:
            return
        if self.row['ds_status'] == 'running':
            # Settle the running block first, otherwise the training and free time of
            # the last block are missing from the day's balance (test run 2026-09-10:
            # capitulation in the middle of free training left ds_train_s/ds_free_s at 0).
            self._close_block(ending_day=True)
            self.lb.execute("UPDATE day_sessions SET ds_status=%s, ds_ended=NOW(), ds_block_kind=NULL, "
                            'ds_block_text=NULL, ds_block_end=NULL WHERE ds_id=%s', (status, self.row['ds_id']))
        self.row['ds_status'] = status
        self.instruction = None
        self.block = None
        self.idle = None
        if quiet:
            return
        logger.info("Day: '%s' Tag beendet (%s)", self.slave.slave_name, status)
        # Sanctions "until the end of the day" end here - and expired ones are
        # closed. The queries filter by `sa_until` anyway, but a sanction that
        # STANDS THERE closed is traceable in the log; one that merely no longer
        # bites is not (doc 26).
        try:
            self.lb.end_day_sanctions(self.slave.slave_id)
            self.lb.expire_sanctions(self.slave.slave_id)
        except Exception as e:                      # noqa: BLE001 - must never blow up the closing of the day
            logger.warning('Day: Auflagen nicht abgeschlossen: %s', e)
        self.lb.emit_event('day_end', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                       'status': status, 'tasks': int(self.row.get('ds_tasks') or 0)})
        # The consequences of capitulation are in the rule set (doc 14 §12.5), not here.
        if status == 'capitulated':
            self.lb.apply_rules('capitulation', self.slave.slave_id, {}, slave=self.slave)
        elif status == 'done':
            self.lb.apply_rules('day_done', self.slave.slave_id, {}, slave=self.slave)
        # streaks of the day kinds (doc 44 §3): the day counts once it is over
        if status in ('done', 'capitulated'):
            try:
                self.lb.streaks.on_day_end(self.slave.slave_id, self.lb._channel_count_today(self.slave.slave_id) or 0)
            except Exception as e:      # noqa: BLE001 - must never blow up the closing of the day
                logger.error('streaks on_day_end: %s', e, exc_info=True)
        if self.on_end:
            try:
                self.on_end(self.slave, status)
            except Exception as e:      # noqa: BLE001 — the logout must not blow up the day
                logger.error('day on_end: %s', e)

    # ------------------------------------------------------------------ #
    def tick(self):
        """From slave.execute(): work off the task, change of block, end of day."""
        if not self.running:
            return
        sp = getattr(self.slave, 'slave_program', None)
        over = datetime.datetime.now() >= self.row['ds_planned_end']
        if sp is not None and not sp.finished:
            sp.execute()
            if not sp.finished:
                return
            self._next_at = time.time() + BLOCK_GAP_S     # task/instruction finished
        if over:
            self.end_day('done')
            return
        if self.instruction and time.time() < self.instruction.get('until', 0):
            return                       # the instruction is still running (break)
        if time.time() < self._next_at:
            return
        self._advance()

    def _advance(self):
        """Next task in the running block — or the next block of the template."""
        rest = self.remaining_s()
        if rest < BLOCK_MIN_S:
            self.end_day('done')
            return
        b = self.block
        # A step can be finished while the run is still going: collar modes and the
        # magnetic lock are not blocking, they count their time themselves and report
        # the result only afterwards (test run 2026-09-10: STATUE was still running while
        # the next task had already started). As long as the block's time budget lasts it
        # waits; after that _close_block() ends the mode via remote_control().
        if b and self.lb.runs_of(self.slave.slave_id) and time.time() < b.get('end_ts', 0):
            self._next_at = time.time() + BLOCK_GAP_S
            return
        # mystery (doc 44 §6): the moment has come — carry out what was drawn, once
        if b and b['kind'] == 'mystery' and b.get('mystery') and not b['mystery'].get('done'):
            if self._mystery_execute(b):
                return
        # plan/free are time budgets: as long as it lasts, the next task comes in the block
        # (Philine: "in the editor you can state what duration of tasks has to be handed out").
        if b and b['kind'] in ('plan', 'free') and time.time() < b.get('end_ts', 0) - BLOCK_MIN_S:
            budget = min(rest, int(b['end_ts'] - time.time()))
            if b['kind'] == 'plan' and self._run_plan_task(b.get('action'), budget, keep=True):
                return
            if b['kind'] == 'free' and self._run_free(budget, keep=True):
                return
        self._close_block()
        self._start_next_block()

    # --- Change of block ------------------------------------------------ #
    def _close_block(self, ending_day=False):
        b = self.block
        if not b:
            return
        dur = int(time.time() - b.get('started', time.time()))
        if b['kind'] == 'pause':
            self.lb.execute('UPDATE day_sessions SET ds_train_s=0 WHERE ds_id=%s', (self.row['ds_id'],))
            self.row['ds_train_s'] = 0
        else:
            self.row['ds_train_s'] = int(self.row.get('ds_train_s') or 0) + dur
            free = int(self.row.get('ds_free_s') or 0) + (dur if b['kind'] == 'free' else 0)
            self.row['ds_free_s'] = free
            self.lb.execute('UPDATE day_sessions SET ds_train_s=%s, ds_free_s=%s WHERE ds_id=%s',
                            (self.row['ds_train_s'], free, self.row['ds_id']))
        self.block = None
        self.instruction = None
        if b['kind'] in ('plan', 'program', 'free', 'mystery'):
            # Switch off collar modes still running at the end of the block: a mode
            # must not run on into the next block (or into the break).
            #
            # AT THE END OF THE DAY it is a different matter: no block follows
            # then, but the logout. `by='logout'` tells the slave that he must
            # NOT put the V-Cage back on — otherwise the collar would go into
            # the cage at logout although nobody is logged in any more
            # (check run 2026-09-14, noticed on a capitulation).
            try:
                self.slave.remote_control(by='logout' if ending_day else 'program')
            except Exception as e:      # noqa: BLE001
                logger.error('day: remote_control am Blockende: %s', e)

    def remaining_s(self):
        return max(0, int((self.row['ds_planned_end'] - datetime.datetime.now()).total_seconds()))

    def _start_next_block(self):
        rest = self.remaining_s()
        if rest < BLOCK_MIN_S:
            self.end_day('done')
            return
        # Compulsory break: after train_block_max_min minutes of training, break_min_min of break
        block_max = int(self.lb.limits['train_block_max_min']) * 60
        if block_max and int(self.row.get('ds_train_s') or 0) >= block_max:
            mins = max(1, min(int(self.lb.limits['break_min_min']), _minutes(rest)))
            self._run_pause(mins, 'Pflichtpause. Ruhen.', forced=True)
            return
        pos = int(self.row.get('ds_pos') or 0)
        if not self.blocks:
            self._free_or_idle(rest, 'kein Tagesplan, freies Training liefert nichts')
            return
        b = self.blocks[pos % len(self.blocks)]
        self.lb.execute('UPDATE day_sessions SET ds_pos=%s WHERE ds_id=%s', (pos + 1, self.row['ds_id']))
        self.row['ds_pos'] = pos + 1
        kind = b['db_kind']
        minutes = max(1, int(b['db_minutes'] or 30))
        budget = min(rest, minutes * 60)
        if kind == 'pause':
            self._run_pause(min(minutes, max(1, _minutes(rest))), b['db_text'] or 'Pause.')
            return
        if kind == 'program' and b['db_program']:
            if self._run_program(b['db_program'], budget):
                return
            self._free_or_idle(rest, 'Programm des Blocks nicht ausführbar')
            return
        if kind == 'plan':
            if self._run_plan_task(b.get('db_action') or None, budget):
                return
            # nothing (left) in the plan for today
            self._free_or_idle(rest, 'keine offene Planaufgabe ausführbar')
            return
        if kind == 'mystery':
            if self._run_mystery(b, budget):
                return
            # nothing in the pool she can do right now
            self._free_or_idle(rest, 'nichts aus dem Mystery-Pool möglich')
            return
        self._free_or_idle(rest, 'freies Training liefert nichts')

    # --- Idle ----------------------------------------------------------- #
    def _free_or_idle(self, rest, reason):
        """Free training as the filler — and if that yields nothing either, idle."""
        if self._run_free(rest):
            return
        self._idle(reason)

    def _idle(self, reason):
        """Nothing can be started right now — and the day goes on (project doc 58 §4).

        No device online, everything forbidden by the task list, the plan empty,
        the free pool exhausted: none of that is a reason to close the day. Until
        2.4 it was, and that was the worse error — with `ss_relogin` switched off
        she could not even log in again, so one short radio gap cost the whole
        day. The day now waits, looks again every IDLE_RETRY_S, and **says so**:
        a day that silently does nothing for half an hour looks like a fault of
        the installation, and one that nobody notices is worse than a visible
        one. Said ONCE, after IDLE_NOTIFY_S — the retry itself stays quiet,
        otherwise the audit fills up with silence.

        The end of the day stays where it belongs: its planned end, in `tick()`.
        """
        if self.idle is None:
            self.idle = {'text': 'Warten.', 'since': time.time(), 'told': False}
            self.instruction = None
            self.lb.execute("UPDATE day_sessions SET ds_block_kind='idle', ds_block_text=%s, "
                            'ds_block_started=NOW(), ds_block_end=NULL WHERE ds_id=%s',
                            (self.idle['text'], self.row['ds_id']))
            logger.info("Day: '%s' Leerlauf (%s) — der Tag wartet", self.slave.slave_name, reason)
            self.lb.emit_event('day_idle', {'slave_id': self.slave.slave_id,
                                            'name': self.slave.slave_name, 'reason': reason})
            self.slave.on_progress()
        elif not self.idle['told'] and time.time() - self.idle['since'] >= IDLE_NOTIFY_S:
            self.idle['told'] = True
            mins = _minutes(time.time() - self.idle['since'])
            logger.warning("Day: '%s' seit %d min im Leerlauf: %s", self.slave.slave_name, mins, reason)
            self.lb.emit_event('warning', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                           'text': f'Seit {mins} min ist nichts möglich: {reason}'})
        self._next_at = time.time() + IDLE_RETRY_S

    # --- Block kinds ---------------------------------------------------- #
    @staticmethod
    def _steps(code, params_raw, extra=None):
        step = {'pc_id': 0, 'pc_command': code, 'pc_parameter': params_raw}
        if extra:
            step.update(extra)
        return [step]

    def _begin(self, kind, steps, label, text=None, seconds=None, program_id=None, program_name=None,
               budget=None, keep=False, action=None):
        """Start a block (or the next task in it): steps to the engine, state into
        the DB. keep=True keeps the time budget of the running block."""
        from slaveprogram import slaveprogram
        self.idle = None                # something is happening again (doc 58 §4)
        if keep and self.block:
            self.block['label'] = label
        else:
            self.block = {'kind': kind, 'started': time.time(), 'label': label, 'action': action,
                          'end_ts': time.time() + int(budget or seconds or 0)}
        self.instruction = {'text': text, 'until': time.time() + (seconds or 0)} if text else None
        end = (datetime.datetime.now() + datetime.timedelta(seconds=int(seconds or 0))) if seconds else None
        self.lb.execute('UPDATE day_sessions SET ds_block_kind=%s, ds_block_text=%s, ds_block_started=NOW(), '
                        'ds_block_end=%s WHERE ds_id=%s',
                        (kind, (text or label)[:255], end, self.row['ds_id']))
        self.slave.program_id = program_id
        self.slave.program_name = program_name or label
        self.slave.slave_program = slaveprogram(self.slave, steps, start_delay=0)
        self.slave.on_progress()
        logger.info("Day: '%s' %s: %s", self.slave.slave_name, kind, label)

    def _run_pause(self, minutes, text, forced=False):
        minutes = max(1, int(minutes))
        raw = f"{minutes}|{str(text or 'Pause.').replace('|', '/')[:200]}"
        self._begin('pause', self._steps('INSTRUCTION', raw), f'Pause {minutes} min',
                    text=text, seconds=minutes * 60, budget=minutes * 60,
                    program_name=('Pflichtpause' if forced else 'Pause'))
        self.lb.emit_event('instruction', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                           'text': text, 'minutes': minutes, 'forced': forced})
        return True

    @staticmethod
    def program_est(steps):
        """Estimated running time of a program in seconds (waiting times + tasks).
        A block does NOT cut off a running program — which is why a program that takes
        longer than the day has left is not started in the first place."""
        total = 0
        for st in steps:
            a = actions.get(st['pc_command'])
            if not a:
                continue
            try:
                params = actions.parse_params(a, st.get('pc_parameter'))
            except actions.ActionError:
                continue
            total += max(0, a.next_delay(params))
            t = tasktypes.get(st['pc_command'])
            if t is not None and a.blocking:
                total += t.est_seconds(params)
        return total

    def est_of(self, steps):
        """Like program_est(), but with the real length of the waveform: for a routine
        the duration is routine length × repetitions (doc 17 §14) and not the flat
        estimate from libs/tasktypes.py."""
        total = self.program_est(steps)
        for st in steps:
            if st['pc_command'] == 'ESTIM_ROUTINE':
                # Not a task, so program_est() only counted its cooldown; the block
                # still has to make room for the whole waveform.
                a, t = actions.get('ESTIM_ROUTINE'), None
                try:
                    params = actions.parse_params(a, st.get('pc_parameter'))
                except actions.ActionError:
                    continue
                ro = routines.get(self.lb.query, params.get('routine'))
                total += max(0, routines.est_seconds(ro, params.get('repeats')) - max(0, a.next_delay(params)))
                continue
            if st['pc_command'] != 'TRAINER_ROUTINE':
                continue
            a, t = actions.get('TRAINER_ROUTINE'), tasktypes.get('TRAINER_ROUTINE')
            if not a or t is None:
                continue
            try:
                params = actions.parse_params(a, st.get('pc_parameter'))
            except actions.ActionError:
                continue
            total += max(0, self.routine_est(st.get('routine_override') or params.get('routine'),
                                             params.get('repeats')) - t.est_seconds(params))
        return total

    def routine_est(self, routine=None, repeats=1, exclude=()):
        """Estimated running time of the waveform this slave gets here."""
        if not routine and exclude:
            routine = self._free_routine(exclude)
            if not routine:
                return 0
        ro = routines.resolve(self.lb.query, int(routine or 0) or None,
                              self.lb.level_of(self.slave.slave_id, 'TRAINER_ROUTINE'))
        return routines.est_seconds(ro, repeats)

    def _free_routine(self, exclude=()):
        """The waveform the level pick gives here, minus the ones this day plan
        rules out (doc 60 §2).

        Excluding is the only form that is provably a narrowing: pinning one
        could hand out a waveform the pick by level would never have produced,
        and that would be a setting. `pick_for_level()` has taken an exclude
        list all along — nothing new, only a caller that fills it.

        None means: nothing left, so the task cannot run here. That is the same
        outcome as a blocked task and again nothing that was not possible."""
        return routines.pick_for_level(self.lb.query,
                                       self.lb.level_of(self.slave.slave_id, 'TRAINER_ROUTINE'),
                                       exclude=tuple(exclude or ()))

    def _run_program(self, program_id, budget):
        row = self.lb.query('SELECT pro_id, pro_name FROM program WHERE pro_id=%s', (program_id,), one=True)
        steps = self.lb.query('SELECT pc_id, pc_command, pc_parameter FROM program_commands WHERE pc_program=%s '
                              'ORDER BY pc_id', (program_id,)) or []
        if not row or not steps:
            return False
        if self.est_of(steps) > self.remaining_s():
            logger.info("Day: '%s' Programm '%s' passt nicht mehr in den Tag - übersprungen",
                        self.slave.slave_name, row['pro_name'])
            return False
        self._begin('program', [dict(x) for x in steps], row['pro_name'], budget=budget,
                    program_id=row['pro_id'], program_name=row['pro_name'])
        return True

    # --- Mystery (doc 44 §6) -------------------------------------------- #
    def _mystery_allowed(self, pool, budget_s):
        """The pool entries she can actually get right now: tasks her online
        devices can do, that the day plan permits at this hour, and that fit the
        window; channel entries when she has a stimulator at all. Everything else
        about limits is decided at execution by the very same code that decides it
        for every other block.

        The task decisions of the day plan (doc 58 §3) also hold here: this is the
        same situation as free training - the central unit chooses. They govern
        TASKS; `punish:N` and `reward:N` are not actions out of the catalogue and
        are bounded by the ceiling, the sanctions and the budgets as before."""
        tb, now_min = self.task_blocks(), self._now_min()
        out = []
        for entry in pool:
            kind, code, lvl = entry
            if kind == mystery.TASK:
                a, t = actions.get(code), tasktypes.get(code)
                if not a or not t:
                    continue
                if a.capability and not self.slave.has_capability(a.capability):
                    continue
                try:
                    raw = self._free_params(a, t, tb.caps_of(code))
                    params = actions.parse_params(a, raw)
                except (actions.ActionError, KeyError, TypeError, ValueError):
                    continue
                secs = self.routine_est(params.get('routine'), params.get('repeats'),
                                        tb.no_routines_of(code)) \
                    if t.code == 'TRAINER_ROUTINE' else t.est_seconds(params)
                if t.code == 'TRAINER_ROUTINE' and tb.no_routines_of(code) and not secs:
                    continue                  # nothing left after the exclusions
                if secs + 2 * BLOCK_GAP_S > budget_s:
                    continue
                if not tb.allows(code, now_min, -(-int(secs) // 60)):
                    continue
                out.append((entry, raw, a.name, secs))
            else:
                # a stimulator that listens to the channel: collar (shock/vibe/beep) or e-stim
                if not any(self.slave.has_capability(c) for c in ('shock', 'vibe', 'beep', 'estim_a', 'estim_b')):
                    continue
                out.append((entry, None, '%s %d' % (kind, lvl), 5))
        return out

    def _run_mystery(self, b, budget):
        pool = mystery.parse_pool(b.get('db_text'))
        allowed = self._mystery_allowed(pool, budget)
        if not allowed:
            logger.info("Day: '%s' Mystery-Block: nichts aus dem Pool moeglich (%d Eintraege) - uebersprungen",
                        self.slave.slave_name, len(pool))
            return False
        entry, raw, name, secs = mystery.draw(allowed)
        delay = mystery.draw_delay(budget, secs, BLOCK_GAP_S)
        now = time.time()
        due = now + delay
        # written BEFORE it happens - the audit knows, she does not (doc 44 §6)
        audit.central('mystery_drawn', slave_id=self.slave.slave_id,
                      data={'pick': mystery.describe(entry), 'kind': entry[0], 'code': entry[1], 'level': entry[2],
                            'due_in_s': delay, 'window_s': int(budget), 'pool': [mystery.describe(e) for e in pool],
                            'allowed': [x[2] for x in allowed]})
        logger.info("Day: '%s' Mystery: gezogen '%s' in %d s (Fenster %d s, %d/%d moeglich)",
                    self.slave.slave_name, name, delay, budget, len(allowed), len(pool))
        self.block = {'kind': 'mystery', 'started': now, 'label': '?', 'action': None,
                      'end_ts': now + int(budget),
                      'mystery': {'entry': entry, 'raw': raw, 'name': name, 'due': due, 'done': False}}
        self.instruction = {'text': '?', 'until': due}
        self.lb.execute('UPDATE day_sessions SET ds_block_kind=%s, ds_block_text=%s, ds_block_started=NOW(), '
                        'ds_block_end=%s WHERE ds_id=%s',
                        ('mystery', '?', datetime.datetime.fromtimestamp(now + int(budget)), self.row['ds_id']))
        self.slave.program_id = None
        self.slave.program_name = '?'
        self.slave.slave_program = None
        self.slave.on_progress()
        self.lb.emit_event('mystery', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                       'window_s': int(budget)})
        self._next_at = due
        return True

    def _mystery_execute(self, b):
        """Carry out the drawn entry. Returns True while the block goes on."""
        m = b['mystery']
        m['done'] = True
        entry, raw, name = m['entry'], m['raw'], m['name']
        kind, code, lvl = entry
        self.instruction = None
        if kind == mystery.TASK:
            extra = {'points_factor': self.lb.sc_float('free_factor', 0.5)}
            # same as in free training: the marker -1 is limited where it becomes
            # a number, and the waveform was already picked with the exclusions
            tb = self.task_blocks()
            mp = tb.caps_of(code).get('max_punish')
            if mp is not None:
                extra['max_punish_override'] = min(int(self.lb.default_max_punish()), int(mp))
            no_ro = tb.no_routines_of(code)
            if no_ro and code == 'TRAINER_ROUTINE':
                ro = self._free_routine(no_ro)
                if ro:
                    extra['routine_override'] = int(ro)
            steps = self._steps(code, raw, extra)
            a = actions.get(code)
            cap = (a.capability or '') if a else ''
            if cap.startswith('mode_') and cap != 'mode_remote':
                secs = tasktypes.get(code).est_seconds(actions.parse_params(a, raw))
                steps.append({'pc_id': 0, 'pc_command': 'WAIT', 'pc_parameter': str(max(1, -(-int(secs) // 60)))})
                steps.append({'pc_id': 0, 'pc_command': 'REMOTE_CONTROL', 'pc_parameter': ''})
            self._begin('mystery', steps, f'Mystery: {name}', program_name='Mystery', keep=True)
            self.lb.emit_event('mystery_revealed', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                                    'kind': kind, 'text': name})
            return True
        # channel entries: the same functions, the same limits as everywhere else
        if kind == mystery.PUNISH:
            res = self.lb.punish(self.slave.slave_id, lvl, 'any', 'mystery', 'mystery')
        else:
            res = self.lb.reward(self.slave.slave_id, lvl, 'any', 'mystery', 'mystery')
        b['label'] = f'Mystery: {name}'
        self.lb.emit_event('mystery_revealed', {'slave_id': self.slave.slave_id, 'name': self.slave.slave_name,
                                                'kind': kind, 'level': lvl, 'text': name, 'sent': res is not None})
        self._next_at = time.time() + BLOCK_GAP_S
        return False        # nothing runs: the next tick closes the block

    # --- Weekly plan: task for today ------------------------------------ #
    def _week_quota(self):
        """How many plan tasks today? The weekly plan is stretched across the days
        (at least plan_per_day_min, otherwise open tasks / remaining days)."""
        week = self.lb.week_of_today()
        rows = self.lb.query("SELECT wt_status FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s "
                             "AND wt_kind IN ('plan','detention','challenge')",
                             (self.slave.slave_id, week)) or []
        open_n = sum(1 for r in rows if r['wt_status'] in ('open', 'proposed'))
        if not open_n:
            return 0
        left_days = max(1, 7 - datetime.date.today().weekday())     # today counted in
        quota = -(-open_n // left_days)                             # round up
        return max(self.lb.sc_int('plan_per_day_min', 1), quota)

    def _run_plan_task(self, only_action, budget, keep=False):
        if int(self.row.get('ds_tasks') or 0) >= self._week_quota():
            return False
        week = self.lb.week_of_today()
        order = "FIELD(wt_kind,'detention','challenge','plan'), wt_id"
        rows = self.lb.query(f"SELECT * FROM weekly_tasks WHERE wt_slave=%s AND wt_week=%s AND wt_status='open' "
                             f"AND wt_kind IN ('plan','detention','challenge') ORDER BY {order}",
                             (self.slave.slave_id, week)) or []
        for t in rows:
            if only_action and t['wt_action'] != only_action:
                continue
            a = actions.get(t['wt_action'])
            task = tasktypes.get(t['wt_action'])
            if not a or not task:
                continue
            if a.capability and not self.slave.has_capability(a.capability):
                continue
            wait = self.lb.activity_cooling(self.slave.slave_id, t['wt_action'])
            if wait:
                # cooldown of the task (budget activity:<ACTION>, doc 44 §1): another one first
                logger.info("Day: '%s' %s is in its cooldown (%ds left) - skipped for now",
                            self.slave.slave_name, t['wt_action'], wait)
                continue
            found = self._program_for(t['wt_action'])
            if not found:
                logger.info("Day: '%s' Planaufgabe %s hat kein zugeordnetes Programm - übersprungen",
                            self.slave.slave_name, t['wt_action'])
                continue
            pro_id, pro_name, steps = found
            target = int(t['wt_target'] or 0)
            if self.est_of(steps) > self.remaining_s():
                logger.info("Day: '%s' Programm '%s' für %s passt nicht mehr in den Tag",
                            self.slave.slave_name, pro_name, t['wt_action'])
                continue
            ro = t.get('wt_routine') if self.lb.routines_enabled else None
            for st in steps:                    # the plan target overrides the target parameter
                if st['pc_command'] == t['wt_action']:
                    st['target_override'] = target
                    st['max_punish_override'] = int(t['wt_max_punish'])
                    if ro:
                        # the plan task's waveform beats the choice by level (doc 17 §14)
                        st['routine_override'] = int(ro)
            label = f"{a.name} · Ziel {self.lb.target_text(target, task.target_unit)}"
            ro_name = self.lb.routine_name(ro) if ro else None
            if ro_name:
                label += f" · {ro_name}"
            self._begin('plan', steps, label,
                        program_id=pro_id, program_name=pro_name, budget=budget, keep=keep,
                        action=only_action)
            self.lb.execute('UPDATE day_sessions SET ds_tasks=ds_tasks+1 WHERE ds_id=%s', (self.row['ds_id'],))
            self.row['ds_tasks'] = int(self.row.get('ds_tasks') or 0) + 1
            return True
        return False

    def _program_for(self, action_code):
        """The slave's program that contains this task (doc 14 §12.2): among the
        programs ASSIGNED to him, the one with the fewest missing devices."""
        rows = self.lb.query(
            'SELECT p.pro_id, p.pro_name FROM slave_program sp JOIN program p ON p.pro_id=sp.sp_program '
            ' JOIN program_commands pc ON pc.pc_program=p.pro_id '
            ' WHERE sp.sp_slave=%s AND pc.pc_command=%s GROUP BY p.pro_id, p.pro_name ORDER BY p.pro_id',
            (self.slave.slave_id, action_code)) or []
        best = None
        for r in rows:
            steps = self.lb.query('SELECT pc_id, pc_command, pc_parameter FROM program_commands '
                                  'WHERE pc_program=%s ORDER BY pc_id', (r['pro_id'],)) or []
            missing = 0
            for st in steps:
                a = actions.get(st['pc_command'])
                if a and a.capability and not self.slave.has_capability(a.capability):
                    missing += 1
            if best is None or missing < best[0]:
                best = (missing, r['pro_id'], r['pro_name'], [dict(x) for x in steps])
            if missing == 0:
                break
        if best is None:
            return None
        return best[1], best[2], best[3]

    # --- free training -------------------------------------------------- #
    def _run_free(self, budget, keep=False):
        if self.slave.has_privilege('free_stay'):
            # Privilege "Free time": no filler program, the day ends with the plan
            logger.info("Day: '%s' freier Aufenthalt - Tag endet nach dem Plan", self.slave.slave_name)
            self.end_day('done')
            return True
        # NOTHING TO PICK IS NOT THE END OF THE DAY (project doc 58 section 4).
        # Until 2.4 this called end_day('done'): one moment in which no device was
        # online ended the day for good - and with `ss_relogin` switched off she
        # could not even log in again, so a short radio gap cost the whole day.
        # The caller now puts the day into idle instead (`_free_or_idle`); the day
        # ends when its TIME is up, not when the central unit runs out of ideas.
        pick = self._free_pick(budget)
        if not pick:
            return False
        code, raw, bump, name, secs, ro = pick
        self.free_count += 1
        extra = {'level_bump': bump, 'points_factor': self.lb.sc_float('free_factor', 0.5)}
        # `max_punish = -1` means "default of the installation" — a marker, not a
        # number. The limit is therefore applied to the RESOLVED default, and
        # handed over as an override (doc 60 §1). min() of the two, so it can
        # only ever become smaller.
        mp = self.task_blocks().caps_of(code).get('max_punish')
        if mp is not None:
            extra['max_punish_override'] = min(int(self.lb.default_max_punish()), int(mp))
        if ro:
            # The waveform was already picked WITH the plan's exclusions (doc 60
            # §2); handed over as a named one, the logbook does not pick again
            # by level and thereby past the exclusion.
            extra['routine_override'] = int(ro)
        steps = self._steps(code, raw, extra)
        # Collar modes are not blocking: without WAIT the mode would be on for only a
        # moment, because the one-step program is finished at once. Duration out of the
        # estimate of the task, afterwards back to remote control (test run 2026-09-10).
        a = actions.get(code)
        cap = (a.capability or '') if a else ''
        if cap.startswith('mode_') and cap != 'mode_remote':
            steps.append({'pc_id': 0, 'pc_command': 'WAIT', 'pc_parameter': str(max(1, -(-int(secs) // 60)))})
            steps.append({'pc_id': 0, 'pc_command': 'REMOTE_CONTROL', 'pc_parameter': ''})
        self._begin('free', steps,
                    f'Freies Training: {name}' + (' (eine Stufe höher)' if bump else ''),
                    program_name='Freies Training', budget=budget, keep=keep)
        return True

    def _free_pick(self, budget_s):
        """Task for free training: at the slave's level, every n-th one a level
        higher (doc 14 §12.3). What counts is what the online devices can do, what
        the day plan permits at this hour, and what fits into the remaining time;
        what has not run today yet is preferred."""
        today = datetime.date.today()
        done = {r['ach_action'] for r in (self.lb.query(
            'SELECT DISTINCT ach_action FROM achievements WHERE ach_slave=%s AND ach_day=%s',
            (self.slave.slave_id, today)) or [])}
        # THE ONE PLACE THE MACHINE REACHES INTO THE WHOLE CATALOGUE (doc 58).
        # A weekly plan task needs an assigned program, so a human said yes to it
        # at some point; free training builds its steps itself. The decisions of
        # the day plan are the step that was missing here: somebody has to have
        # said yes, or at least not no.
        tb, now_min = self.task_blocks(), self._now_min()
        cand = []
        for t in tasktypes.TASKS:
            a = actions.get(t.code)
            if not a or not a.trainable:
                continue
            if a.capability and not self.slave.has_capability(a.capability):
                continue
            try:
                raw = self._free_params(a, t, tb.caps_of(t.code))
                params = actions.parse_params(a, raw)
            except (actions.ActionError, KeyError, TypeError, ValueError):
                continue
            # The waveform this task would get, with the ones the plan rules out
            # taken away (doc 60 §2). Nothing left means it cannot run here.
            ro = None
            if t.code == 'TRAINER_ROUTINE':
                no_ro = tb.no_routines_of(t.code)
                ro = int(params.get('routine') or 0) or (self._free_routine(no_ro) if no_ro else None)
                if no_ro and not ro:
                    continue
            secs = self.routine_est(params.get('routine'), params.get('repeats'),
                                    tb.no_routines_of(t.code)) \
                if t.code == 'TRAINER_ROUTINE' else t.est_seconds(params)
            if secs > budget_s:
                continue
            # The WHOLE run has to fit into the permitted time, not just its start
            # (decision Philine 2026-09-17): a task drawn at 21:55 that takes 40
            # minutes ends at 22:35.
            if not tb.allows(t.code, now_min, -(-int(secs) // 60)):
                continue
            cand.append((0 if t.code not in done else 1, random.random(), t.code, raw, a.name, secs, ro))
        if not cand:
            return None
        cand.sort(key=lambda x: (x[0], x[1]))
        _, _, code, raw, name, secs, ro = cand[0]
        every = self.lb.sc_int('free_stretch_every', 3)
        bump = 1 if (every and (self.free_count + 1) % every == 0) else 0
        return code, raw, bump, name, secs, ro

    @staticmethod
    def _free_params(action, task, caps=None):
        """Parameter string for free training. The TARGET PARAMETER is always
        written out (defaults such as PET max_min=0 mean "maximum of the device" and
        would be far too long as free training); everything behind it keeps its
        default, in particular max_punish=-1 = "default of the installation".

        `caps` are the upper limits of the day plan (doc 60). A limit only works
        if the parameter is WRITTEN OUT: `max_punish` is the last parameter of
        every task and would otherwise keep its default and the limit would do
        nothing. So the written range reaches at least as far as the last capped
        parameter."""
        caps = caps or {}
        names = [p.name for p in action.params]
        idx = names.index(task.target_param) if task.target_param in names else -1
        capped = [i for i, p in enumerate(action.params) if p.name in caps]
        last = max([i for i, p in enumerate(action.params) if p.default is None] + [idx] + capped)
        vals = []
        for i, p in enumerate(action.params[:last + 1]):
            if i == idx or p.default is None:
                v = DayRunner._free_default(task, p)
            else:
                v = p.default
            # A limit never pushes a value below the permitted range - that would
            # be an invalid parameter, not a milder one.
            v = taskblocks.cap_value(p.name, v, caps)
            # The floor only for real numbers: a negative value is a marker
            # ("default of the installation") and must stay one, otherwise the
            # floor would turn -1 into 0 and thereby into a value.
            if p.min is not None and isinstance(v, int) and v >= 0:
                v = max(p.min, v)
            vals.append(str(v))
        return '|'.join(vals)

    @staticmethod
    def _free_default(task, param):
        """Mandatory parameters without a default: the target parameter gets the plan
        target of the task, everything else the lower bound of the permitted range."""
        if param.name == task.target_param:
            v = int(task.plan_default / (task.target_factor or 1)) or 1
            lo = param.min if param.min is not None else 1
            hi = param.max if param.max is not None else v
            return max(lo, min(v, hi))
        if param.type is int:
            return param.min if param.min is not None else 1
        return ''

    # ------------------------------------------------------------------ #
    def snapshot(self):
        """Day info for the session status (display, web)."""
        if not self.row:
            return None
        rest = self.remaining_s() if self.running else 0
        out = {'status': self.row['ds_status'], 'started': str(self.row['ds_started'])[:19],
               'end': str(self.row['ds_planned_end'])[:19], 'remaining_s': rest,
               'remaining_min': _minutes(rest), 'plan': self.plan_name,
               # idle is not a block one can configure — it is the state of a day that
               # currently has nothing to do (doc 58 §4). The display reads
               # `block_label`, so the waiting text has to arrive there.
               'block': (self.block or {}).get('kind') or ('idle' if self.idle else None),
               'block_label': (self.block or {}).get('label') or (self.idle or {}).get('text'),
               'blocks_done': int(self.row.get('ds_pos') or 0), 'tasks': int(self.row.get('ds_tasks') or 0),
               'free_min': _minutes(int(self.row.get('ds_free_s') or 0)),
               'train_min': _minutes(int(self.row.get('ds_train_s') or 0))}
        if self.instruction and self.instruction.get('text'):
            left = int(self.instruction.get('until', 0) - time.time())
            if left > 0:
                out['instruction'] = {'text': self.instruction['text'], 'remaining_s': max(0, left)}
        nxt = self._peek_next()
        if nxt:
            out['next'] = nxt
        return out

    def _peek_next(self):
        if not self.blocks or not self.running:
            return None
        b = self.blocks[int(self.row.get('ds_pos') or 0) % len(self.blocks)]
        label = {'plan': 'Aufgabe aus dem Wochenplan', 'program': 'Programm',
                 'free': 'Freies Training', 'pause': (b['db_text'] or 'Pause'),
                 'mystery': '?'}.get(b['db_kind'], b['db_kind'])
        return {'kind': b['db_kind'], 'label': label, 'minutes': int(b['db_minutes'] or 0)}
