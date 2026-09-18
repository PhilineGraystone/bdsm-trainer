# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Day form — easy / normal / strict (project document 44 §5).

One modifier over everything the day does: a factor on the pulse levels
(inside her ceiling, never above it), an offset on the task level (inside
the bounds of doc 44 §4), and rewards / activity budgets tighter or looser.

WHO SETS IT (decision Philine 2026-09-16): the supervisor — or a rule, as an
automatism. A rule sets it FOR ONE DAY, today or tomorrow (``strict:+1``),
never for good. **It holds until the end of the day** and then falls back to
``normal`` by itself, unless a rule sets it again. That is not a timer: a
day form is a row for one date, and tomorrow has no row unless somebody
writes one. The audit says who wrote it, rule or human — otherwise "strict"
is the new normal after three weeks and nobody notices.

WHAT IT NEVER DOES: raise a ceiling. Pulse percentages are capped at 100 %
of her calibrated ceiling, the level stays inside its bounds, punishment
budgets (which cap punishments) are not touched by the form at all —
"strict" must neither weaken discipline nor widen a safety limit, so the
form leaves them alone.

Numbers live in `scoring` (editable over the web):
    dayform_easy_pct / dayform_strict_pct        pulse factor in %   (85 / 115)
    dayform_level_easy / dayform_level_strict    level offset        (-1 / +1)
    dayform_budget_easy_pct / dayform_budget_strict_pct
        factor on the COUNT of reward and activity budgets (120 / 80);
        the gap moves the other way (100/factor)
"""

import datetime
import logging
import time

logger = logging.getLogger(__name__)

FORMS = ('easy', 'normal', 'strict')
LABELS = {'easy': 'leicht', 'normal': 'normal', 'strict': 'streng'}
HELP = {'easy':   'Impulse schwächer, Aufgabenstufe eine tiefer, Belohnungen großzügiger.',
        'normal': 'Alles wie eingestellt.',
        'strict': 'Impulse stärker (nie über der Decke), Aufgabenstufe eine höher, Belohnungen knapper.'}


class Dayform:
    """Reads/writes `dayforms`; answers the modifier questions. ``lb`` is the logbook."""

    CACHE_S = 5.0

    def __init__(self, lb):
        self.lb = lb
        self.enabled = False
        self._rows = None
        self._rows_t = 0.0

    def invalidate(self):
        self._rows = None

    def _today_rows(self):
        """Rows for today and tomorrow (cached) — that is all anyone asks about live."""
        if not self.enabled:
            return []
        now = time.time()
        if self._rows is None or now - self._rows_t > self.CACHE_S:
            self._rows = self.lb._q('SELECT * FROM dayforms WHERE df_day BETWEEN CURDATE() AND CURDATE() + INTERVAL 1 DAY') or []
            self._rows_t = now
        return self._rows

    def row(self, slave_id, day=None):
        """The row that applies: her own beats the installation-wide one (0). None = normal."""
        day = day or datetime.date.today()
        sid = int(slave_id or 0)
        best = None
        for r in self._today_rows():
            if r['df_day'] != day or int(r['df_slave'] or 0) not in (0, sid):
                continue
            if best is None or (int(r['df_slave'] or 0) == sid and int(best['df_slave'] or 0) == 0):
                best = r
        return best

    def of(self, slave_id, day=None):
        r = self.row(slave_id, day)
        return (r['df_form'] if r and r['df_form'] in FORMS else 'normal')

    def set(self, slave_id, form, by, reason='', day=None):
        """Write the form for one day. 'normal' deletes the row — normal is the absence of a row."""
        if not self.enabled or form not in FORMS:
            return False
        day = day or datetime.date.today()
        sid = int(slave_id or 0)
        if form == 'normal':
            self.lb._x('DELETE FROM dayforms WHERE df_slave=%s AND df_day=%s', (sid, day))
        else:
            self.lb._x('INSERT INTO dayforms (df_slave, df_day, df_form, df_by, df_reason) VALUES (%s,%s,%s,%s,%s) '
                       'ON DUPLICATE KEY UPDATE df_form=VALUES(df_form), df_by=VALUES(df_by), df_reason=VALUES(df_reason), df_set=NOW()',
                       (sid, day, form, str(by or '')[:64], str(reason or '')[:160]))
        self.invalidate()
        logger.info("dayform: slave %s %s = %s (%s)", sid, day, form, by)
        return True

    # ------------------------------------------------------------------ #
    # the modifiers — all read live out of scoring, all bounded
    def pulse_pct(self, form):
        if form == 'easy':
            return max(10, min(100, self.lb.sc_int('dayform_easy_pct', 85)))
        if form == 'strict':
            return max(100, min(150, self.lb.sc_int('dayform_strict_pct', 115)))
        return 100

    def level_offset(self, form):
        if form == 'easy':
            return min(0, max(-3, self.lb.sc_int('dayform_level_easy', -1)))
        if form == 'strict':
            return max(0, min(3, self.lb.sc_int('dayform_level_strict', 1)))
        return 0

    def budget_pct(self, form):
        """(count %, gap %) for reward and activity budgets — never for punish."""
        if form == 'easy':
            c = max(100, min(200, self.lb.sc_int('dayform_budget_easy_pct', 120)))
        elif form == 'strict':
            c = max(50, min(100, self.lb.sc_int('dayform_budget_strict_pct', 80)))
        else:
            return 100, 100
        return c, int(round(10000 / c))

    def channel_level(self, form, level):
        """Punishment level 1..3 shifted by the form, inside 1..3."""
        lv = int(level or 1)
        if form == 'strict':
            lv += 1
        elif form == 'easy':
            lv -= 1
        return max(1, min(3, lv))

    # ------------------------------------------------------------------ #
    def info(self, slave_id):
        """For web and display."""
        today = datetime.date.today()
        r = self.row(slave_id, today)
        t = self.row(slave_id, today + datetime.timedelta(days=1))
        form = r['df_form'] if r else 'normal'
        return {'form': form, 'label': LABELS.get(form, form),
                'by': (r['df_by'] if r else None), 'reason': (r['df_reason'] if r else ''),
                'all': bool(r and int(r['df_slave'] or 0) == 0),
                'tomorrow': (t['df_form'] if t else None),
                'pulse_pct': self.pulse_pct(form), 'level_offset': self.level_offset(form)}
