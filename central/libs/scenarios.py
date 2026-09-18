# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Scenarios — the bundle with a name (project document 44 §7).

Much of the installation already IS a scenario: the day plan (blocks, a
mystery pool), sanctions and privileges, budgets, the day form. What was
missing is the name above it. "Strict" is a day plan with certain
sanctions, tighter budgets and the form `strict`; "Weekend" the same with
other values. So a scenario is NOT a second rule system: it is a bundle of
things that exist, activated for one slave with one click and an end date.

Activation writes into the very tables the pieces live in — `slave_settings`
(her day plan, the previous one remembered), `sanctions` (imposed until the
end date, by `scenario:<id>`), `budgets` (rows for her, by `scenario:<id>`),
`dayforms` (one row per day of the range, by `scenario:<id>`) — and the end
takes it all back out: plan restored, scenario sanctions lifted, scenario
budgets deleted, remaining scenario day forms deleted. The end is the date
passing (checked in the logbook tick) or the supervisor ending it early.

What a scenario does NOT carry: the device assignment. A bundle that
reassigns hardware would take a device away from a logged-in slave in the
middle of her day; the assignment stays on her page, and the plan's blocks
already refuse what she does not wear.
"""

import datetime
import json
import logging

import budgets as budgetsmod
import dayform as dayformmod

logger = logging.getLogger(__name__)

TAG = 'scenario:'


def parse_budgets(text):
    """JSON list -> list of dicts with the five budget fields; bad entries are dropped."""
    try:
        raw = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        key = str(r.get('key') or '')
        period = str(r.get('period') or 'day')
        if key not in budgetsmod.KEYS and not key.startswith(budgetsmod.ACTIVITY_PREFIX):
            continue
        if period not in budgetsmod.PERIODS:
            continue
        mc = r.get('max_count')
        gap = r.get('min_gap_s')
        mc = int(mc) if mc not in (None, '', 0, '0') else None
        gap = int(gap) if gap not in (None, '', 0, '0') else None
        if mc is None and gap is None:
            continue
        og = str(r.get('on_gap') or ('drop' if key == 'reward' else 'queue'))
        out.append({'key': key, 'period': period, 'max_count': mc, 'min_gap_s': gap,
                    'on_gap': og if og in budgetsmod.ON_GAP else 'queue'})
    return out


def parse_budget_lines(text):
    """The editor's form: one budget per line, 'key period max gap on_gap'
    with '-' for none, e.g. 'reward day 3 - drop'. Returns (list, error)."""
    out = []
    for n, line in enumerate(str(text or '').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.replace(',', ' ').split()
        if len(parts) < 3:
            return None, (n, line)
        key, period = parts[0], parts[1]
        mc = parts[2]
        gap = parts[3] if len(parts) > 3 else '-'
        og = parts[4] if len(parts) > 4 else ('drop' if key == 'reward' else 'queue')
        if period not in budgetsmod.PERIODS or og not in budgetsmod.ON_GAP:
            return None, (n, line)
        if not ((mc == '-' or mc.isdigit()) and (gap == '-' or gap.isdigit())) or (mc == '-' and gap == '-'):
            return None, (n, line)
        if key not in budgetsmod.KEYS and not key.startswith(budgetsmod.ACTIVITY_PREFIX):
            return None, (n, line)
        out.append({'key': key, 'period': period, 'max_count': int(mc) if mc != '-' else None,
                    'min_gap_s': int(gap) if gap != '-' else None, 'on_gap': og})
    return out, None


def budget_lines(rows):
    return '\n'.join('%s %s %s %s %s' % (r['key'], r['period'], r['max_count'] if r['max_count'] else '-',
                                         r['min_gap_s'] if r['min_gap_s'] else '-', r['on_gap']) for r in rows)


class Scenarios:
    """``lb`` is the logbook: queries, sanctions, budgets, dayform."""

    def __init__(self, lb):
        self.lb = lb
        self.enabled = False

    # ------------------------------------------------------------------ #
    def list(self):
        rows = self.lb._q('SELECT s.*, p.dp_name AS plan_name, '
                          '(SELECT COUNT(*) FROM scenario_active a WHERE a.sx_scenario=s.sn_id) AS active_n '
                          'FROM scenarios s LEFT JOIN day_plans p ON p.dp_id=s.sn_day_plan ORDER BY s.sn_name') or []
        for r in rows:
            r['budgets'] = parse_budgets(r.get('sn_budgets'))
            r['sanctions'] = [k for k in (r.get('sn_sanctions') or '').split(',') if k]
        return rows

    def get(self, sn_id):
        r = self.lb._q('SELECT * FROM scenarios WHERE sn_id=%s', (sn_id,), one=True)
        if r:
            r['budgets'] = parse_budgets(r.get('sn_budgets'))
            r['sanctions'] = [k for k in (r.get('sn_sanctions') or '').split(',') if k]
        return r

    def save(self, name, note, day_plan, dayform, sanctions, budgets, by, sn_id=None):
        """Create or update. Returns the id."""
        sanc = ','.join(k for k in sanctions if k)       # keys checked by the caller against SANCTIONS
        bj = json.dumps(budgets) if budgets else None
        form = dayform if dayform in dayformmod.FORMS else None
        if sn_id:
            self.lb._x('UPDATE scenarios SET sn_name=%s, sn_note=%s, sn_day_plan=%s, sn_dayform=%s, sn_sanctions=%s, '
                       'sn_budgets=%s, sn_by=%s WHERE sn_id=%s',
                       (name, note, day_plan, form, sanc, bj, by, sn_id))
            return sn_id
        return self.lb._x('INSERT INTO scenarios (sn_name, sn_note, sn_day_plan, sn_dayform, sn_sanctions, sn_budgets, sn_by) '
                          'VALUES (%s,%s,%s,%s,%s,%s,%s)', (name, note, day_plan, form, sanc, bj, by))

    def delete(self, sn_id, by):
        for a in self.lb._q('SELECT sx_slave FROM scenario_active WHERE sx_scenario=%s', (sn_id,)) or []:
            self.deactivate(a['sx_slave'], by, 'scenario deleted')
        return self.lb._x('DELETE FROM scenarios WHERE sn_id=%s', (sn_id,))

    # ------------------------------------------------------------------ #
    def active(self, slave_id):
        return self.lb._q('SELECT a.*, s.sn_name FROM scenario_active a JOIN scenarios s ON s.sn_id=a.sx_scenario '
                          'WHERE a.sx_slave=%s', (slave_id,), one=True)

    def activate(self, slave_id, sn_id, until, by):
        """Put the bundle on her, until `until` (inclusive). Returns (ok, why)."""
        if not self.enabled:
            return False, 'disabled'
        sc = self.get(sn_id)
        if not sc:
            return False, 'unknown scenario'
        today = datetime.date.today()
        if until < today:
            return False, 'until in the past'
        if self.active(slave_id):
            self.deactivate(slave_id, by, 'replaced')          # one at a time; the old one goes first
        tag = TAG + str(sn_id)
        prev = self.lb._q('SELECT ss_day_plan FROM slave_settings WHERE ss_slave=%s', (slave_id,), one=True)
        prev_plan = prev['ss_day_plan'] if prev else None
        self.lb._x('INSERT INTO scenario_active (sx_slave, sx_scenario, sx_from, sx_until, sx_prev_plan, sx_by) '
                   'VALUES (%s,%s,%s,%s,%s,%s)', (slave_id, sn_id, today, until, prev_plan, by))
        # 1. her day plan
        if sc['sn_day_plan']:
            self.lb._x('INSERT INTO slave_settings (ss_slave, ss_day_plan, ss_by) VALUES (%s,%s,%s) '
                       'ON DUPLICATE KEY UPDATE ss_day_plan=VALUES(ss_day_plan), ss_by=VALUES(ss_by)',
                       (slave_id, sc['sn_day_plan'], tag))
        # 2. sanctions until the end of the last day
        end = datetime.datetime.combine(until, datetime.time(23, 59, 59))
        hours = max(0.1, (end - datetime.datetime.now()).total_seconds() / 3600.0)
        for key in sc['sanctions']:
            self.lb.impose_sanction(slave_id, key, by=tag, reason=sc['sn_name'], hours=hours)
        # 3. budgets for her
        for b in sc['budgets']:
            self.lb._x('INSERT INTO budgets (bu_key, bu_slave, bu_period, bu_max_count, bu_min_gap_s, bu_on_gap, bu_note, bu_by) '
                       'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE bu_enabled=1, bu_max_count=VALUES(bu_max_count), '
                       'bu_min_gap_s=VALUES(bu_min_gap_s), bu_on_gap=VALUES(bu_on_gap), bu_note=VALUES(bu_note), bu_by=VALUES(bu_by)',
                       (b['key'], slave_id, b['period'], b['max_count'], b['min_gap_s'], b['on_gap'], sc['sn_name'], tag))
        self.lb.budgets.invalidate()
        # 4. the day form, one row per day
        if sc['sn_dayform'] and sc['sn_dayform'] != 'normal':
            d = today
            while d <= until:
                self.lb.dayform.set(slave_id, sc['sn_dayform'], tag, reason=sc['sn_name'], day=d)
                d += datetime.timedelta(days=1)
        logger.info("scenario '%s' activated for slave %s until %s by %s", sc['sn_name'], slave_id, until, by)
        self.lb._emit('scenario', {'slave_id': slave_id, 'name': self.lb._slave_name(slave_id),
                                   'scenario': sc['sn_name'], 'until': until.isoformat(), 'active': True})
        return True, 'ok'

    def deactivate(self, slave_id, by, why='ended'):
        """Take the bundle off again: everything tagged with it goes, the plan comes back."""
        a = self.active(slave_id)
        if not a:
            return False
        tag = TAG + str(a['sx_scenario'])
        self.lb._x('UPDATE slave_settings SET ss_day_plan=%s, ss_by=%s WHERE ss_slave=%s AND ss_by=%s',
                   (a['sx_prev_plan'], by, slave_id, tag))
        for s in self.lb._q('SELECT sa_key FROM sanctions WHERE sa_slave=%s AND sa_by=%s AND sa_lifted IS NULL', (slave_id, tag)) or []:
            self.lb.lift_sanction(slave_id, s['sa_key'], by=by)
        self.lb._x('DELETE FROM budgets WHERE bu_slave=%s AND bu_by=%s', (slave_id, tag))
        self.lb.budgets.invalidate()
        self.lb._x('DELETE FROM dayforms WHERE df_slave=%s AND df_by=%s AND df_day >= CURDATE()', (slave_id, tag))
        self.lb.dayform.invalidate()
        self.lb._x('DELETE FROM scenario_active WHERE sx_slave=%s', (slave_id,))
        logger.info("scenario '%s' ended for slave %s (%s, by %s)", a['sn_name'], slave_id, why, by)
        self.lb._emit('scenario', {'slave_id': slave_id, 'name': self.lb._slave_name(slave_id),
                                   'scenario': a['sn_name'], 'active': False, 'why': why})
        return True

    def tick(self):
        """From the logbook tick: end what has run past its date."""
        if not self.enabled:
            return 0
        n = 0
        for a in self.lb._q('SELECT sx_slave FROM scenario_active WHERE sx_until < CURDATE()') or []:
            if self.deactivate(a['sx_slave'], 'date', 'date passed'):
                n += 1
        return n

    def info(self, slave_id):
        a = self.active(slave_id)
        if not a:
            return None
        return {'id': a['sx_scenario'], 'name': a['sn_name'], 'from': str(a['sx_from']), 'until': str(a['sx_until']),
                'by': a['sx_by']}
