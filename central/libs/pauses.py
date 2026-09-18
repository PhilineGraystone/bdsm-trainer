# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Pause / holiday (project document 44 §2) — asked at ONE place.

A pause is a date range for one slave or for the whole installation
(``pa_slave = 0``). While it runs: no login opens a day, no rule fires, no
weekly task falls due, no budget runs — the channel refuses. **The week
stands** (decision Philine 2026-09-16): a week the pause covers completely is
frozen — the review writes "pausiert" instead of grading, the rank does not
move, open plan tasks move on to the next week, streaks bridge the paused
days. Resuming is not a step anyone takes; it is the end date passing.

This module only answers questions. Everything that acts on the answer —
``dayplan.open_day()``, ``logbook.apply_rules()``, ``punish()``/``reward()``,
``review_week()``, ``_streak_days()`` — asks here, so "is she paused?" has one
definition and cannot drift apart between the places.
"""

import datetime
import logging
import time

logger = logging.getLogger(__name__)


class Pauses:
    """Reads the table (cached for a few seconds). ``q(sql, params) -> rows``."""

    CACHE_S = 5.0

    def __init__(self, q):
        self._q = q
        self._rows = None
        self._rows_t = 0.0
        self.enabled = False          # table present? set by the logbook

    def invalidate(self):
        self._rows = None

    def rows(self):
        """Pauses that are running or still to come (past ones are history, not state)."""
        if not self.enabled:
            return []
        now = time.time()
        if self._rows is None or now - self._rows_t > self.CACHE_S:
            try:
                raw = self._q('SELECT * FROM pauses WHERE pa_to >= CURDATE() ORDER BY pa_from, pa_slave') or []
            except Exception as e:  # noqa: BLE001 - a DB hiccup must not stop the installation
                logger.error('pauses: read failed: %s', e)
                raw = self._rows or []
            self._rows = list(raw)
            self._rows_t = now
        return self._rows

    def active(self, slave_id, day=None):
        """The pause that covers `day` (default today) for this slave — the slave's
        own row or the installation-wide one — or None."""
        day = day or datetime.date.today()
        sid = int(slave_id or 0)
        best = None
        for r in self.rows():
            if int(r['pa_slave'] or 0) not in (0, sid):
                continue
            if r['pa_from'] <= day <= r['pa_to']:
                # the slave's own row says more than the installation-wide one
                if best is None or (int(r['pa_slave'] or 0) == sid and int(best['pa_slave'] or 0) == 0):
                    best = r
        return best

    def paused_days(self, slave_id, monday):
        """How many of the seven days from `monday` are covered by a pause.
        Reads the table directly (past weeks are not in the cache)."""
        if not self.enabled:
            return 0
        sid = int(slave_id or 0)
        end = monday + datetime.timedelta(days=6)
        rows = self._q('SELECT pa_from, pa_to FROM pauses WHERE pa_slave IN (0, %s) AND pa_from <= %s AND pa_to >= %s',
                       (sid, end, monday)) or []
        days = set()
        for r in rows:
            d = max(r['pa_from'], monday)
            while d <= min(r['pa_to'], end):
                days.add(d)
                d += datetime.timedelta(days=1)
        return len(days)

    def is_paused_day(self, slave_id, day):
        """For streaks: was this (possibly past) day covered? Direct read."""
        if not self.enabled:
            return False
        r = self._q('SELECT 1 AS x FROM pauses WHERE pa_slave IN (0, %s) AND pa_from <= %s AND pa_to >= %s LIMIT 1',
                    (int(slave_id or 0), day, day), one=True)
        return bool(r)

    @staticmethod
    def describe(r):
        """'bis 20.09.2026 (Urlaub)' — for LCD, display and web."""
        if not r:
            return ''
        until = r['pa_to'].strftime('%d.%m.%Y') if hasattr(r['pa_to'], 'strftime') else str(r['pa_to'])
        why = (r.get('pa_reason') or '').strip()
        return until + (f' ({why})' if why else '')
