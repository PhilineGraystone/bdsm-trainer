# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Task decisions per day plan (project document 58 sections 1-3).

WHAT THIS ANSWERS: may the central unit start task X for this day plan, right
now, for as long as it is going to take? Nothing else. It is a filter in front
of the places where the MACHINE chooses - free training and the mystery draw.
It is not a ban on the supervisor: a program somebody starts by hand is a human
deciding, not a random grab, and it passes untouched. What limits the
supervisor are sanctions, the ceiling and `[safety]`, and those stand above
everything here as before.

Everything in here can only make the day SMALLER. There is no entry that lets
something happen which could not have happened without it - that is what makes
this a screen one can hand to a supervisor who is not the author.

THE FOUR MODES, and why two of them are opposites:

    allow       decided and allowed
    block       blocked, always
    block_in    blocked ONLY inside the window    "no action X after 22:00"
    block_out   blocked EXCEPT inside the window  sleep deprivation 22:00-06:00

A window alone does not say which of the two is meant, so the mode carries it.
`from > to` means the window runs over midnight - 22:00-06:00 is the case the
whole thing exists for, and a version that cannot express it would be useless.

THE WHOLE RUN HAS TO FIT, not just its start (decision Philine 2026-09-17). A
task drawn at 21:55 that takes 40 minutes ends at 22:35 and would otherwise be
a surprise nobody can explain. The caller therefore passes the estimated
duration, which `_free_pick()` and `_mystery_allowed()` both know already.

NO ROW MEANS NOT DECIDED, and not decided means allowed - which is exactly the
behaviour of a day plan nobody has edited, so nothing changes for existing
installations. `undecided()` is the other side of that coin: it names the
actions a plan has never said anything about, so the editor can show them as
new instead of letting them in silently.
"""

import logging

logger = logging.getLogger('Punisher')

DAY_MIN = 1440
STEP_MIN = 15                    # the window is set in quarter hours (doc 58 §2)

MODE_ALLOW = 'allow'
MODE_BLOCK = 'block'
MODE_IN = 'block_in'
MODE_OUT = 'block_out'
MODES = (MODE_ALLOW, MODE_BLOCK, MODE_IN, MODE_OUT)
WINDOW_MODES = (MODE_IN, MODE_OUT)

# Speaking names for the editor and the views. German is the master.
LABELS = {
    MODE_ALLOW: ('erlaubt', 'Die Zentrale darf die Aufgabe von sich aus wählen.'),
    MODE_BLOCK: ('gesperrt, immer', 'Die Zentrale wählt sie nie von selbst. Die Aufsicht kann sie weiterhin starten.'),
    MODE_IN:    ('gesperrt, nur zwischen', 'Innerhalb des Zeitfensters gesperrt, sonst erlaubt — für Ruhezeiten.'),
    MODE_OUT:   ('gesperrt, außer zwischen',
                 'Außerhalb des Zeitfensters gesperrt — für Aufgaben, die nur zu einer Tageszeit Sinn ergeben.'),
}


# --------------------------------------------------------------------------- #
# Narrowing limits (project document 60)
#
# WHICH PARAMETERS MAY BE LIMITED, and why this is a list and not a rule.
#
# The criterion out of doc 58 - "nothing may come out that could not have come
# out without the entry" - is necessary but NOT sufficient. It asks whether a
# value was possible before, not whether it is milder. Three counter-examples
# from the catalogue that pass the wording and do the opposite:
#
#   warn        -> 0 takes the warning away before the pulse
#   angle, tolerance, tol_ms, max_miss  -> smaller is STRICTER, not milder
#   repeat_s, still_s, gap_min_s        -> smaller puts the pulses CLOSER
#
# So a second sentence holds: a limit exists only where SMALLER UNDOUBTEDLY
# MEANS LESS for the person. The code cannot derive that - `bpm` alone would
# need an argument either way - so it stands here by name, and what is not on
# the list cannot be limited. In doubt it does not go on the list.
LOWERABLE = ('max_punish',                                   # fewer punishments in the run
             'max_min', 'minutes', 'max_s', 'target_s', 'hold_s',   # shorter
             'count', 'rounds', 'repeats', 'beats',          # fewer repetitions
             'depth', 'depth_start', 'depth_end')            # not as deep


def lowerable(action):
    """The parameters of this action that may carry an upper limit."""
    if action is None:
        return []
    return [p for p in action.params if p.name in LOWERABLE and p.max is not None and not p.ref]


def parse_caps(text):
    """'max_punish=2,max_min=20' -> {'max_punish': 2, 'max_min': 20}.
    Unreadable entries are dropped: a limit nobody can read is no limit."""
    out = {}
    for part in str(text or '').replace(';', ',').split(','):
        name, _, val = part.strip().partition('=')
        name = name.strip()
        # A negative limit is not a limit. Zero is kept because it is meaningful
        # for `max_punish` ("no punishment at all") — where it takes effect is
        # decided in `cap_value()`.
        if name in LOWERABLE and val.strip().isdigit():
            out[name] = int(val)
    return out


def format_caps(caps):
    return ','.join('%s=%d' % (k, int(v)) for k, v in sorted((caps or {}).items()) if k in LOWERABLE)


def parse_ids(text):
    """'3,7' -> {3, 7}."""
    out = set()
    for part in str(text or '').replace(';', ',').split(','):
        if part.strip().isdigit():
            out.add(int(part))
    return out


def format_ids(ids):
    return ','.join(str(int(i)) for i in sorted(ids or ()))


def cap_value(name, value, caps):
    """The value, but never above its limit. Anything not in `caps` passes.

    A NEGATIVE VALUE IS A SENTINEL, not a number: `max_punish = -1` means
    "default of the installation", and that default may be smaller than the
    limit. Taking the minimum of the two would compare a limit with a marker,
    and replacing the marker by the limit could RAISE the effective value - the
    one thing a narrowing must never do. So a sentinel passes untouched here and
    is limited where it is resolved into a real number (`prepare()` in the
    logbook, reached through `max_punish_override`)."""
    lim = (caps or {}).get(name)
    # A limit of zero does not bite HERE: for several parameters zero is itself
    # a marker ("0 = upper limit of the device"), and writing it would widen
    # instead of narrow. Zero is meaningful for `max_punish`, and that one is
    # limited on the resolved path, not here.
    if lim is None or int(lim) < 1:
        return value
    try:
        v = int(value)
    except (TypeError, ValueError):
        return value
    return value if v < 0 else min(v, int(lim))


def hhmm(minutes):
    """420 -> '07:00'. None stays None."""
    if minutes is None:
        return None
    m = int(minutes) % DAY_MIN
    return '%02d:%02d' % (m // 60, m % 60)


def parse_hhmm(text):
    """'22:00' -> 1320, rounded to the quarter hour. None for anything unreadable."""
    try:
        h, _, m = str(text or '').partition(':')
        v = int(h) * 60 + int(m or 0)
    except (TypeError, ValueError):
        return None
    if not 0 <= v < DAY_MIN:
        return None
    return (v // STEP_MIN) * STEP_MIN


def win_parts(frm, to):
    """The window as one or two segments on [0, 1440). Empty when from == to."""
    frm, to = int(frm) % DAY_MIN, int(to) % DAY_MIN
    if frm == to:
        return []
    if frm < to:
        return [(frm, to)]
    return [(frm, DAY_MIN), (0, to)]          # over midnight


def run_parts(start, minutes):
    """The run as one or two segments on [0, 1440), wrapping at midnight.

    Longer than a day is cut to a day: something that runs round the clock can
    never lie inside a window anyway, and it must not wrap twice and thereby
    look shorter than it is."""
    start = int(start) % DAY_MIN
    mins = max(1, min(int(minutes), DAY_MIN))
    end = start + mins
    if end <= DAY_MIN:
        return [(start, end)]
    return [(start, DAY_MIN), (0, end - DAY_MIN)]


def overlap(a, b):
    """Minutes that the two segment lists have in common."""
    total = 0
    for a0, a1 in a:
        for b0, b1 in b:
            total += max(0, min(a1, b1) - max(a0, b0))
    return total


def allowed(mode, frm, to, start, minutes):
    """May a run of `minutes` minutes, beginning at minute `start` of the day,
    happen under this entry?

    A window mode WITHOUT a window is treated as a full block. It cannot arise
    through the editor (which demands the window); it can only come from a hand
    edit in the database, and of the two possible readings the tightening one
    is the one that matches the principle of doc 44 - a component may tighten,
    never widen."""
    if mode == MODE_BLOCK:
        return False
    if mode not in WINDOW_MODES:
        return True                           # allow, and anything unknown
    if frm is None or to is None:
        logger.warning('taskblocks: %s ohne Zeitfenster - wie gesperrt behandelt', mode)
        return False
    run = run_parts(start, minutes)
    win = win_parts(frm, to)
    hit = overlap(run, win)
    if mode == MODE_IN:
        return hit == 0                       # must not touch the window at all
    return hit == sum(b - a for a, b in run)  # must lie inside it completely


def summary(mode, frm, to):
    """One line for the folded editor row and the plan overview.

    Folded, a mere arrow would hide exactly what one wants to see (doc 58 §5),
    so what is set has to be legible without unfolding."""
    name = LABELS.get(mode, (mode, ''))[0]
    if mode in WINDOW_MODES and frm is not None and to is not None:
        over = ' (über Mitternacht)' if int(frm) % DAY_MIN > int(to) % DAY_MIN else ''
        return '%s %s–%s%s' % (name, hhmm(frm), hhmm(to), over)
    return name


class TaskBlocks:
    """The decisions of one day plan, ready to be asked."""

    def __init__(self, rows=None):
        self.rows = {}
        for r in rows or []:
            code = str(r['dpa_action'])
            self.rows[code] = {'mode': str(r['dpa_mode'] or MODE_ALLOW),
                               'from': None if r['dpa_from'] is None else int(r['dpa_from']),
                               'to': None if r['dpa_to'] is None else int(r['dpa_to']),
                               # 2.5, doc 60 — a plan from before migration 014 has neither
                               'caps': parse_caps(r.get('dpa_caps')),
                               'no_routines': parse_ids(r.get('dpa_no_routines'))}

    @classmethod
    def load(cls, lb, plan_id):
        """Read afresh for the plan. Deliberately not cached: a task the
        supervisor blocks during the running day must take effect at the next
        pick, and a pick happens once per task, not once per tick."""
        if not plan_id:
            return cls()
        try:
            rows = lb.query('SELECT * FROM dayplan_actions WHERE dpa_plan=%s', (plan_id,)) or []
        except Exception as e:                # noqa: BLE001 - a missing table must not stop the day
            logger.warning('taskblocks: Entscheidungen nicht lesbar (%s) - alles erlaubt', e)
            return cls()
        return cls(rows)

    def get(self, code):
        return self.rows.get(str(code))

    def allows(self, code, start, minutes):
        r = self.rows.get(str(code))
        if not r:
            return True                       # not decided is allowed (doc 58 §1)
        return allowed(r['mode'], r['from'], r['to'], start, minutes)

    def caps_of(self, code):
        """The upper limits for this task — empty when there are none (doc 60)."""
        r = self.rows.get(str(code))
        return dict(r['caps']) if r else {}

    def no_routines_of(self, code):
        """The waveforms the level pick must not take here (doc 60 §2)."""
        r = self.rows.get(str(code))
        return set(r['no_routines']) if r else set()

    def summary_of(self, code):
        r = self.rows.get(str(code))
        if not r:
            return None
        out = summary(r['mode'], r['from'], r['to'])
        # What is narrowed belongs in the folded line as well, otherwise a task
        # looks untouched while it is capped (doc 58 §5, doc 60 §4).
        if r['caps']:
            out += ' · ' + ', '.join('%s ≤ %d' % (k, v) for k, v in sorted(r['caps'].items()))
        if r['no_routines']:
            out += ' · %d Wellenform(en) ausgeschlossen' % len(r['no_routines'])
        return out

    def undecided(self, codes):
        """Those of `codes` the plan has never said anything about — the editor
        shows them as new instead of letting them in unnoticed."""
        return [c for c in codes if str(c) not in self.rows]

    def blocked_codes(self):
        return sorted(c for c, r in self.rows.items() if r['mode'] != MODE_ALLOW)
