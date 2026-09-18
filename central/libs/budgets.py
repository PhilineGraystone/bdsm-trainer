# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Budgets and cooldowns — one mechanism, two questions (project document 44 §1).

HOW OFTEN may something happen in a period (``max_count``), and HOW CLOSE
together (``min_gap_s``)? Until 2.2 the answers sat in three different
places: the day limit of the punishment channel in ``config.ini [safety]``,
the anti-grinding count in ``scoring``, the minimum pause hard in
``logbook.punish()``. Same pattern every time — a counter out of the audit
log against a limit — so from 2.3 it is one table, ``budgets``, and this
module is the one place that answers.

Keys
----
    punish              punishments over the channel
    reward              rewards over the channel
    activity            runs of any task (anti-grinding: how many COUNT)
    activity:<ACTION>   runs of one task

Scope: one row per (key, slave, period). ``bu_slave = 0`` means the whole
installation. A row for one slave does NOT replace the installation row —
both apply, and the tighter one wins. That is what makes the rule below hold
without a single ``if``.

The safety ceiling
------------------
``[safety] channel_day_max`` and ``channel_gap_s`` are not rows in the table;
they are a synthetic row this module adds for the key ``punish``. It is
evaluated like every other row, which means: a budget can TIGHTEN the channel
(fewer per day, longer pause), it can never loosen it. The ceiling is not
editable over the web (decision Philine 2026-09-10) and the table cannot get
around it.

``on_gap`` — what happens to something that arrives inside the pause:
``queue`` waits until the pause is over and is then delivered (the channel's
choice since 2026-09-10 — a violation that quietly disappears looks like a
fault), ``drop`` lets it lapse (default for rewards: a reward twenty minutes
after the occasion is none). Switchable per row (decision Philine 2026-09-16).

For ``activity`` keys ``max_count`` keeps its old meaning — how many runs per
day count towards the leaderboard — and ``min_gap_s`` is a pause between two
runs of that task that the day plan respects when it picks the next task.
``on_gap`` has no meaning there; the plan simply takes another task.

Exceeding a budget is a TRIGGER for the rule set (``budget_exceeded``), fired
once per (slave, key, period window) — the rule set may escalate, it must not
be poked on every further refused attempt.
"""

import collections
import datetime
import logging
import time

logger = logging.getLogger(__name__)

PERIODS = ('day', 'week')
ON_GAP = ('queue', 'drop')

# key -> (label, help). Both German; i18n.d() translates for the web.
KEYS = collections.OrderedDict([
    ('punish',   ('Bestrafungen über den Kanal',
                  'Wie viele je Tag oder Woche, und wie dicht — unter der Decke aus config.ini [safety].')),
    ('reward',   ('Belohnungen über den Kanal',
                  'Eine Belohnung lange nach dem Anlass ist keine: Vorgabe „verfällt“.')),
    ('activity', ('Durchgänge (alle Aufgaben)',
                  'Anzahl = wie viele je Tag für die Rangliste zählen (Anti-Grinding); Abstand = Pause zwischen zwei Durchgängen.')),
])
ACTIVITY_PREFIX = 'activity:'

Budget = collections.namedtuple('Budget', 'id key slave period max_count min_gap_s on_gap source')


def key_label(key):
    """Human label for a key, including ``activity:<ACTION>``."""
    if key in KEYS:
        return KEYS[key][0]
    if key.startswith(ACTIVITY_PREFIX):
        return 'Durchgänge ' + key[len(ACTIVITY_PREFIX):]
    return key


def valid_key(key, action_codes=()):
    if key in KEYS:
        return True
    return key.startswith(ACTIVITY_PREFIX) and key[len(ACTIVITY_PREFIX):] in action_codes


def period_start(period, now=None):
    """Start of the current period as a datetime (day: midnight, week: Monday 0:00)."""
    now = now or datetime.datetime.now()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'week':
        return day - datetime.timedelta(days=day.weekday())
    return day


def window_id(period, now=None):
    """A string that names the current period window — the key for 'fired once'."""
    return period_start(period, now).date().isoformat() + ':' + period


class Budgets:
    """Reads the table (cached for a few seconds), answers count and gap questions.

    ``q`` is a query function ``q(sql, params) -> rows`` (DictCursor rows).
    ``limits`` is the logbook's ``[safety]`` dict — the ceiling comes from it live,
    so a changed config.ini is picked up without restarting this object.
    """

    CACHE_S = 5.0

    def __init__(self, q, limits):
        self._q = q
        self._limits = limits
        self._rows = None
        self._rows_t = 0.0
        self.enabled = False          # table present? set by the logbook after the migration check
        self._fired = {}              # (slave, key, window) -> True
        # Day form (doc 44 §5): f(slave_id) -> (count %, gap %) for reward and
        # activity rows. Never applied to 'punish' and never to the ceiling.
        self.modifier = None

    # ------------------------------------------------------------------ #
    def invalidate(self):
        self._rows = None

    def rows(self):
        """All enabled rows of the table (cached)."""
        if not self.enabled:
            return []
        now = time.time()
        if self._rows is None or now - self._rows_t > self.CACHE_S:
            try:
                raw = self._q('SELECT * FROM budgets WHERE bu_enabled=1 ORDER BY bu_slave, bu_key, bu_period') or []
            except Exception as e:  # noqa: BLE001 - a DB hiccup must not stop the channel
                logger.error('budgets: read failed: %s', e)
                raw = self._rows or []
                self._rows_t = now
                return [r for r in raw]
            self._rows = [Budget(r['bu_id'], r['bu_key'], int(r['bu_slave'] or 0), r['bu_period'],
                                 r['bu_max_count'], r['bu_min_gap_s'], r['bu_on_gap'] or 'queue', 'table')
                          for r in raw]
            self._rows_t = now
        return self._rows

    def ceiling(self):
        """The synthetic [safety] row for the punishment channel. 0 = unlimited (as before)."""
        cap = int(self._limits.get('channel_day_max') or 0) or None
        gap = int(self._limits.get('channel_gap_s') or 0) or None
        return Budget(0, 'punish', 0, 'day', cap, gap, 'queue', 'safety')

    def applicable(self, key, slave_id):
        """Every row that speaks about this key for this slave: the exact key, the
        family key for ``activity:X``, installation-wide and slave-specific, plus
        the ceiling for ``punish``."""
        keys = {key}
        if key.startswith(ACTIVITY_PREFIX):
            keys.add('activity')
        out = [r for r in self.rows() if r.key in keys and r.slave in (0, int(slave_id or 0))]
        if key != 'punish' and self.modifier is not None and out:
            cpct, gpct = self.modifier(slave_id)
            if (cpct, gpct) != (100, 100):
                out = [r._replace(max_count=(max(1, int(r.max_count * cpct / 100)) if r.max_count else None),
                                  min_gap_s=(max(1, int(r.min_gap_s * gpct / 100)) if r.min_gap_s else None))
                       for r in out]
        if key == 'punish':
            out.append(self.ceiling())
        return out

    # ------------------------------------------------------------------ #
    def exceeded(self, key, slave_id, counter):
        """Is any applicable budget used up? ``counter(period) -> int`` counts what
        already happened in the current window. Returns the row that is hit
        (the one with the smallest max) or None."""
        hit = None
        for r in self.applicable(key, slave_id):
            if not r.max_count:
                continue
            if counter(r.period) >= int(r.max_count):
                if hit is None or int(r.max_count) < int(hit.max_count):
                    hit = r
        return hit

    def max_count(self, key, slave_id, period='day'):
        """The smallest max_count for this period, or None when nothing limits it."""
        vals = [int(r.max_count) for r in self.applicable(key, slave_id) if r.period == period and r.max_count]
        return min(vals) if vals else None

    def gap(self, key, slave_id):
        """(min_gap_s, on_gap): the longest pause among the applicable rows, and
        what its row says about arrivals inside it. (0, None) when nothing applies."""
        best = None
        for r in self.applicable(key, slave_id):
            if r.min_gap_s and (best is None or int(r.min_gap_s) > int(best.min_gap_s)):
                best = r
        if best is None:
            return 0, None
        return int(best.min_gap_s), best.on_gap

    def fire_once(self, slave_id, key, period, now=None):
        """True the first time in this window — the caller then raises the trigger."""
        k = (int(slave_id or 0), key, window_id(period, now))
        if k in self._fired:
            return False
        # keep the dict small: forget windows that are over
        if len(self._fired) > 256:
            cur_day = window_id('day', now)
            cur_week = window_id('week', now)
            self._fired = {kk: v for kk, v in self._fired.items() if kk[2] in (cur_day, cur_week)}
        self._fired[k] = True
        return True

    def describe(self, r):
        """One line for logs and audit: 'punish/day max 60 (safety)'."""
        bits = []
        if r.max_count:
            bits.append('max %d' % int(r.max_count))
        if r.min_gap_s:
            bits.append('gap %ds %s' % (int(r.min_gap_s), r.on_gap))
        who = 'all' if r.slave == 0 else 'slave %d' % r.slave
        return '%s/%s %s (%s, %s)' % (r.key, r.period, ' '.join(bits) or '-', who, r.source)
