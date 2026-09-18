# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Streaks as a thing of their own (project document 44 §3).

A streak is a counter with a counting condition and a reset condition:
"7 days without a violation", "5 runs passed in a row", "3 challenges failed
in a row". Reaching a milestone fires ``streak_reached``; breaking fires
``streak_broken``. Both are triggers for the rule set — the reward or the
escalation stays where everything else of that kind is configured. Nothing
in here hands out points or punishments itself.

**The loss is shown** (decision Philine 2026-09-16): "Serie gebrochen: 6 Tage"
on the screen and on the participant page. For the exhibition that is the
more interesting moment than the seventh day.

Kinds — the counting and reset condition come in pairs, so a definition is
a kind plus, where it makes sense, one task and the milestones:

    clean_days      attended days in a row with no channel punishment;
                    a day with one resets, a missed calendar day resets
    training_days   attended days in a row (any training)
    passed_runs     runs passed in a row (of one task, or of any); a failed one resets
    failed_runs     runs failed in a row; a passed one resets
    plan_weeks      weeks in a row with the weekly plan complete

Paused days (doc 44 §2) neither count nor break the day kinds — the pause
module is asked about every day in the gap.

Milestones are a comma list ("3,7,14"): every value fires ``streak_reached``
once when the count reaches it. A streak with no milestones still counts and
still breaks — only nothing celebrates it.
"""

import datetime
import logging
import time

import i18n

logger = logging.getLogger(__name__)

# kind -> (label, help). German; i18n.d() translates for the web.
KINDS = {
    'clean_days':    ('Tage ohne Verstoß', 'Angetretene Tage in Folge ohne Bestrafung über den Kanal. Ein Verstoß oder ein ausgelassener Tag bricht sie.'),
    'training_days': ('Trainingstage', 'Angetretene Tage in Folge. Ein ausgelassener Tag bricht sie.'),
    'passed_runs':   ('Durchgänge bestanden', 'Bestandene Durchgänge in Folge — einer Aufgabe oder aller. Ein nicht bestandener bricht sie.'),
    'failed_runs':   ('Durchgänge gescheitert', 'Nicht bestandene Durchgänge in Folge. Ein bestandener bricht sie. Für Ketten: „zweimal gescheitert → …“'),
    'plan_weeks':    ('Wochen mit vollem Plan', 'Wochen in Folge mit vollständigem Wochenplan. Eine unvollständige bricht sie.'),
}
DAY_KINDS = ('clean_days', 'training_days')
RUN_KINDS = ('passed_runs', 'failed_runs')
UNIT = {'clean_days': 'Tage', 'training_days': 'Tage', 'passed_runs': 'Durchgänge',
        'failed_runs': 'Durchgänge', 'plan_weeks': 'Wochen'}
BROKEN_SHOW_H = 24          # how long the loss stays on the participant page / tile


def parse_milestones(text):
    out = []
    for p in str(text or '').replace(';', ',').split(','):
        p = p.strip()
        if p.isdigit() and int(p) > 0 and int(p) not in out:
            out.append(int(p))
    return sorted(out)


class Streaks:
    """Counts against the definitions in `streaks`, keeps state in `streak_state`.

    ``lb`` is the logbook: it lends the query/execute functions, the pause
    module and ``apply_rules``.
    """

    CACHE_S = 5.0

    def __init__(self, lb):
        self.lb = lb
        self.enabled = False
        self._defs = None
        self._defs_t = 0.0

    def invalidate(self):
        self._defs = None

    def definitions(self):
        if not self.enabled:
            return []
        now = time.time()
        if self._defs is None or now - self._defs_t > self.CACHE_S:
            rows = self.lb._q('SELECT * FROM streaks WHERE st_enabled=1 ORDER BY st_id') or []
            for r in rows:
                r['milestones'] = parse_milestones(r.get('st_milestones'))
            self._defs = rows
            self._defs_t = now
        return self._defs

    # ------------------------------------------------------------------ #
    # the hooks — called by the logbook where things happen
    def on_run(self, slave_id, action, passed):
        """A run has been graded."""
        for d in self.definitions():
            if d['st_kind'] not in RUN_KINDS:
                continue
            if d['st_action'] and d['st_action'] != action:
                continue
            hit = passed if d['st_kind'] == 'passed_runs' else not passed
            self._bump(d, slave_id, hit)

    def on_day_start(self, slave_id, today=None):
        """A day opens: a gap since the last counted day breaks the day kinds —
        noticed now, at login, not silently at the next day end."""
        today = today or datetime.date.today()
        for d in self.definitions():
            if d['st_kind'] not in DAY_KINDS:
                continue
            st = self._state(d['st_id'], slave_id)
            if st['sk_count'] and st['sk_last_day'] and self._gap(slave_id, st['sk_last_day'], today):
                self._reset(d, slave_id, st, why='gap')

    def on_day_end(self, slave_id, punished, today=None):
        """A day is over (regularly or by capitulation). ``punished`` = channel
        punishments today."""
        today = today or datetime.date.today()
        for d in self.definitions():
            if d['st_kind'] not in DAY_KINDS:
                continue
            st = self._state(d['st_id'], slave_id)
            if st['sk_last_day'] == today:
                continue                                  # one day counts once (re-login)
            if st['sk_count'] and st['sk_last_day'] and self._gap(slave_id, st['sk_last_day'], today):
                self._reset(d, slave_id, st, why='gap')
                st = self._state(d['st_id'], slave_id)
            hit = True if d['st_kind'] == 'training_days' else (int(punished or 0) == 0)
            self._bump(d, slave_id, hit, day=today)

    def on_week(self, slave_id, complete):
        for d in self.definitions():
            if d['st_kind'] == 'plan_weeks':
                self._bump(d, slave_id, bool(complete))

    # ------------------------------------------------------------------ #
    def _gap(self, slave_id, last_day, today):
        """Is there an unattended, unpaused day between last_day and today?"""
        d = last_day + datetime.timedelta(days=1)
        while d < today:
            if not self.lb.pauses.is_paused_day(slave_id, d):
                return True
            d += datetime.timedelta(days=1)
        return False

    def _state(self, st_id, slave_id):
        r = self.lb._q('SELECT * FROM streak_state WHERE sk_streak=%s AND sk_slave=%s', (st_id, slave_id), one=True)
        return r or {'sk_streak': st_id, 'sk_slave': slave_id, 'sk_count': 0, 'sk_best': 0, 'sk_last_day': None,
                     'sk_broken_at': None, 'sk_broken_count': 0}

    def _save(self, st_id, slave_id, count, best, last_day, broken_at, broken_count):
        self.lb._x('INSERT INTO streak_state (sk_streak, sk_slave, sk_count, sk_best, sk_last_day, sk_broken_at, sk_broken_count) '
                   'VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE sk_count=VALUES(sk_count), sk_best=VALUES(sk_best), '
                   'sk_last_day=VALUES(sk_last_day), sk_broken_at=VALUES(sk_broken_at), sk_broken_count=VALUES(sk_broken_count)',
                   (st_id, slave_id, count, best, last_day, broken_at, broken_count))

    def _bump(self, d, slave_id, hit, day=None):
        st = self._state(d['st_id'], slave_id)
        if not hit:
            if st['sk_count']:
                self._reset(d, slave_id, st, why='miss', day=day)
            elif day is not None:
                self._save(d['st_id'], slave_id, 0, st['sk_best'], day, st['sk_broken_at'], st['sk_broken_count'])
            return
        n = int(st['sk_count'] or 0) + 1
        best = max(n, int(st['sk_best'] or 0))
        self._save(d['st_id'], slave_id, n, best, day if day is not None else st['sk_last_day'],
                   st['sk_broken_at'], st['sk_broken_count'])
        if n in d['milestones']:
            ctx = {'streak': d['st_key'], 'name': d['st_name'], 'kind': d['st_kind'], 'n': n, 'unit': UNIT[d['st_kind']]}
            logger.info("streak '%s' for slave %s reached %d", d['st_key'], slave_id, n)
            self.lb._emit('streak_reached', dict(ctx, slave_id=slave_id, name_slave=self.lb._slave_name(slave_id),
                                                  text=i18n._('Serie: {name} — {n} {unit}', name=d['st_name'], n=n,
                                                              unit=i18n._(UNIT[d['st_kind']]))))
            self.lb.apply_rules('streak_reached', slave_id, ctx)

    def _reset(self, d, slave_id, st, why, day=None):
        n = int(st['sk_count'] or 0)
        now = datetime.datetime.now()
        self._save(d['st_id'], slave_id, 0, st['sk_best'], day if day is not None else st['sk_last_day'], now, n)
        ctx = {'streak': d['st_key'], 'name': d['st_name'], 'kind': d['st_kind'], 'n': n, 'unit': UNIT[d['st_kind']], 'why': why}
        logger.info("streak '%s' for slave %s broken at %d (%s)", d['st_key'], slave_id, n, why)
        # the loss is shown (decision Philine): screen and participant page
        self.lb._emit('streak_broken', dict(ctx, slave_id=slave_id, name_slave=self.lb._slave_name(slave_id),
                                             text=i18n._('Serie gebrochen: {name} — {n} {unit}', name=d['st_name'], n=n,
                                                         unit=i18n._(UNIT[d['st_kind']]))))
        self.lb.apply_rules('streak_broken', slave_id, ctx)

    # ------------------------------------------------------------------ #
    def status(self, slave_id):
        """For web and display: every definition with count, best and — for a
        day — the loss. [{'key','name','kind','count','best','unit','milestones',
        'next','broken_count','broken_at','broken_recent'}]"""
        out = []
        if not self.enabled:
            return out
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=BROKEN_SHOW_H)
        for d in self.definitions():
            st = self._state(d['st_id'], slave_id)
            nxt = next((m for m in d['milestones'] if m > int(st['sk_count'] or 0)), None)
            ba = st.get('sk_broken_at')
            out.append({'key': d['st_key'], 'name': d['st_name'], 'kind': d['st_kind'], 'action': d['st_action'],
                        'count': int(st['sk_count'] or 0), 'best': int(st['sk_best'] or 0), 'unit': UNIT[d['st_kind']],
                        'milestones': d['milestones'], 'next': nxt,
                        'broken_count': int(st.get('sk_broken_count') or 0),
                        'broken_at': str(ba)[:16] if ba else None,
                        'broken_recent': bool(ba and ba > cutoff and int(st.get('sk_broken_count') or 0) > 0)})
        return out
