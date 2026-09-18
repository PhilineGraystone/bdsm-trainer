# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Waveform routines for the blowjob/deepthroat trainer (project doc 17).

A routine is a list of BREAKPOINTS over time. Each breakpoint carries a target
depth and a tolerance, both in percent of the participant's own calibrated range
(doc 17 §5) — never in millimetres of insertion, because the mapping from sensor
value to physical depth is neither linear nor the same for two people.

The device interpolates between breakpoints, samples at its own rate and scores
every tick. This module owns everything the central unit needs around that:

  * the wire format (4 bytes per breakpoint) and its CRC32
  * chunking for the transfer transaction (begin / chunk / commit)
  * the editor warnings (doc 17 §8: warn, never block)
  * picking a routine for a task level (doc 17 §14: the level SELECTS the routine)
  * the duration estimate the day planner needs to fill a training block

The device keeps a copy in its external EEPROM keyed by id + CRC. That copy is a
CACHE, never the truth: the central always holds the routine, and a mismatching
CRC makes the device ask for it again (doc 17 §7).
"""

import logging
import zlib

from profiles import (COUPLE_ACCURACY, COUPLE_POSITION, MODE_ABSOLUTE, MODE_COUPLED,  # noqa: F401
                      OUTPUT_ROLES, ROLE_TARGET)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Wire format. 4 bytes per breakpoint:
#   dt      uint16, little endian, in 10 ms units since the previous breakpoint
#   depth   uint8, 0..100 percent of the participant's own range
#   tol     uint8, 0..100 percent, half the tolerance band
POINT_BYTES = 4
TICK_MS = 10                      # resolution of dt; the device samples far coarser
DT_MAX = 0xFFFF                   # 655.35 s between two breakpoints
MAX_POINTS = 1000                 # doc 17 §6
# 40, not 50 (2.1.1). A chunk of 50 points with the largest legal values
# (dx 65535, value 255, tol 255) is 1046 bytes in its signed envelope, and the
# firmware up to 2.1.0 refused everything from 990 bytes on — so exactly the
# waveform with the longest gaps and the highest amplitudes was the one that
# never arrived, and it failed silently: the device logged "payload too large",
# the central unit saw a missing `routine_commit` answer and sent the whole
# thing again. With 40 the worst case is 886 bytes, below the old limit AND
# below punmqtt.DEVICE_RX_MAX, and every device on 2.1.0 keeps working
# (finding Philine 2026-09-15). ~25 messages for a full routine.
CHUNK_POINTS = 40
MAX_REPEATS = 20
MAX_TRACKS = 8                    # doc 19 §2.3

# The X axis of a waveform (doc 19 §2.1). This is the distinction everybody has
# to understand first, so it is also the first thing the editor explains.
AXIS_TIME = 'zeit'                # rp_x is milliseconds  -> the curve RUNS
AXIS_DEPTH = 'tiefe'              # rp_x is 0.1 percent   -> the curve FOLLOWS
# (label of the select field, noun for the plain-text line, explanation)
AXES = {
    AXIS_TIME: ('Zeit', 'Zeitachse', 'Die Kurve läuft ab: X ist die Zeit seit dem Start.'),
    AXIS_DEPTH: ('Tiefe', 'Tiefenachse',
                 'Die Kurve läuft nicht ab, sie folgt dem, was gemessen wird: '
                 'X ist die Tiefe in Prozent des eigenen Bereichs.'),
}
X_STEP = {AXIS_TIME: TICK_MS, AXIS_DEPTH: 1}   # one wire unit is 10 ms resp. 0.1 %

# What a waveform is FOR - decides where it may appear (doc 19 §2.2).
PURPOSE_TASK = 'aufgabe'
PURPOSE_STIM = 'reiz'
PURPOSE_REWARD = 'belohnung'
PURPOSES = {
    PURPOSE_TASK: ('Aufgabe', 'Kommt in Wochenplan und Herausforderung, wird bewertet und hat '
                              'eine Mindestnote.'),
    PURPOSE_STIM: ('Reiz', 'Läuft als eigenes Programm oder als Kopplung mit, wird nicht bewertet.'),
    PURPOSE_REWARD: ('Belohnung', 'Wird nur für Erreichtes gegeben. Kann nie eine Planaufgabe sein — '
                                  'sie lässt sich nicht verfehlen.'),
}

# Editor warning codes (doc 17 §8). The editor shows them, nothing is blocked.
W_DEEP_HOLD = 'deep_hold'         # long uninterrupted phase at great depth
W_JUMP = 'jump'                   # step nobody can follow
W_SEAM = 'seam'                   # start and end depth far apart, repeats will jump
W_EMPTY = 'empty'                 # no breakpoints
W_TOO_MANY = 'too_many'           # above MAX_POINTS
W_OVERLAP = 'overlap'             # two tracks want the same channel at the same time
W_NO_CHANNEL = 'no_channel'       # an output track without an output
W_NO_TARGET = 'no_target'         # a task without the scored track

# Thresholds for the warnings only — NOT safety limits. The one hard limit lives
# in the device firmware and cannot be raised over MQTT (doc 17 §12).
WARN_DEEP_PCT = 80                # "deep" starts here
WARN_DEEP_S = 30                  # longer than this at that depth gets a warning
WARN_JUMP_PCT_PER_S = 150         # faster than this is not followable
WARN_SEAM_PCT = 15                # start/end mismatch above this warns


class RoutineError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Reading
def get(q, ro_id):
    """One routine header, or None."""
    if not ro_id:
        return None
    return q('SELECT * FROM routines WHERE ro_id=%s', (int(ro_id),), one=True)


def all_routines(q, purpose=None):
    if purpose:
        return q('SELECT * FROM routines WHERE ro_purpose=%s ORDER BY ro_level, ro_name',
                 (purpose,)) or []
    return q('SELECT * FROM routines ORDER BY ro_purpose, ro_level, ro_name') or []


def tracks(q, ro_id):
    """Tracks of a waveform, in editor order (doc 19 §2.3)."""
    return q('SELECT * FROM routine_tracks WHERE rt_routine=%s ORDER BY rt_track',
             (int(ro_id),)) or []


def track(q, ro_id, no):
    return q('SELECT * FROM routine_tracks WHERE rt_routine=%s AND rt_track=%s',
             (int(ro_id), int(no)), one=True)


def points(q, ro_id, track_no=0):
    """Breakpoints of ONE track, ordered along the axis."""
    return q('SELECT rp_seq, rp_x, rp_value, rp_tol_pct FROM routine_points '
             'WHERE rp_routine=%s AND rp_track=%s ORDER BY rp_seq',
             (int(ro_id), int(track_no))) or []


def as_tuples(rows):
    """[(x, value, tol)] from database rows. x is milliseconds on the time axis
    and 0.1 percent on the depth axis - see AXES."""
    return [(int(r['rp_x']), int(r['rp_value']), int(r['rp_tol_pct'])) for r in rows]


# --------------------------------------------------------------------------- #
# Wire format
def serialise(pts, axis=AXIS_TIME):
    """Breakpoints -> the exact byte stream the device receives.

    Both sides hash THIS representation (doc 17 §7), so the format is defined
    once, here. Unchanged at 4 bytes per breakpoint on both axes - only the unit
    of the first two bytes differs (doc 19 §7):

        time axis  -> dx counts 10 ms steps
        depth axis -> dx counts 0.1 percent steps (0..100 % -> 0..1000)

    A gap longer than DT_MAX is split into several breakpoints that hold the
    previous value, so dx can never overflow.
    """
    step = X_STEP.get(axis, TICK_MS)
    out = bytearray()
    prev_ticks = 0
    prev_value, prev_tol = 0, 0
    for i, (x, value, tol) in enumerate(pts):
        ticks = int(round(int(x) / step))
        if i and ticks < prev_ticks:
            raise RoutineError('breakpoint %d goes backwards along the axis' % i)
        value = max(0, min(100, int(value)))
        tol = max(0, min(100, int(tol)))
        gap = ticks - prev_ticks
        while gap > DT_MAX:                     # hold the previous value, then carry on
            out += DT_MAX.to_bytes(2, 'little') + bytes((prev_value, prev_tol))
            gap -= DT_MAX
            prev_ticks += DT_MAX
        out += gap.to_bytes(2, 'little') + bytes((value, tol))
        prev_ticks = ticks
        prev_value, prev_tol = value, tol
    return bytes(out)


def crc32(blob):
    """CRC32 of the wire format — the value that travels in begin and commit."""
    return zlib.crc32(blob) & 0xFFFFFFFF


def deserialise(blob, axis=AXIS_TIME):
    """Inverse of serialise(), for tests and for the preview in the editor."""
    if len(blob) % POINT_BYTES:
        raise RoutineError('byte stream is not a multiple of %d' % POINT_BYTES)
    step = X_STEP.get(axis, TICK_MS)
    out, x = [], 0
    for i in range(0, len(blob), POINT_BYTES):
        dx = int.from_bytes(blob[i:i + 2], 'little')
        x += dx * step
        out.append((x, blob[i + 2], blob[i + 3]))
    return out


def chunks(pts, per=CHUNK_POINTS, axis=AXIS_TIME):
    """Breakpoints as [[dx, value, tol], ...] blocks for the transfer messages.

    dx is in the same units as the wire format, so the device can append a chunk
    without recomputing anything.
    """
    blob = serialise(pts, axis)
    triples = []
    for i in range(0, len(blob), POINT_BYTES):
        triples.append([int.from_bytes(blob[i:i + 2], 'little'), blob[i + 2], blob[i + 3]])
    return [triples[i:i + per] for i in range(0, len(triples), per)]


# --------------------------------------------------------------------------- #
# Derived values
def duration_ms(pts):
    return int(pts[-1][0]) if pts else 0


def recompute(q, x, ro_id):
    """Refresh the derived columns after any change to any track.

    ro_crc32 is the checksum over ALL tracks in order, so one number still says
    whether a device holds the current waveform; each track additionally carries
    its own checksum on the wire (doc 19 §7).
    """
    row = get(q, ro_id)
    axis = (row or {}).get('ro_axis') or AXIS_TIME
    total, longest, whole = 0, 0, bytearray()
    for t in tracks(q, ro_id):
        pts = as_tuples(points(q, ro_id, t['rt_track']))
        whole += serialise(pts, axis)
        total += len(pts)
        longest = max(longest, duration_ms(pts) if axis == AXIS_TIME else 0)
    x('UPDATE routines SET ro_crc32=%s, ro_points=%s, ro_duration_ms=%s WHERE ro_id=%s',
      (crc32(bytes(whole)), total, longest, int(ro_id)))
    return {'crc32': crc32(bytes(whole)), 'points': total, 'duration_ms': longest}


def track_payload(q, ro_id, track_row, axis=AXIS_TIME):
    """{track, role, profile, channel, mode, couple, points, crc32} for one track."""
    pts = as_tuples(points(q, ro_id, track_row['rt_track']))
    return {'track': int(track_row['rt_track']), 'role': track_row['rt_role'],
            'profile': track_row['rt_profile'] or '', 'channel': track_row['rt_channel'] or '',
            'mode': track_row['rt_mode'], 'couple': track_row['rt_couple'],
            'points': pts, 'crc32': crc32(serialise(pts, axis))}


def est_seconds(routine, repeats=1):
    """Estimated run time, so the day planner can fit the task into a block."""
    if not routine:
        return 300
    ms = int(routine.get('ro_duration_ms') or 0)
    gap = int(routine.get('ro_loop_ms') or 0)
    reps = max(1, min(int(repeats or 1), MAX_REPEATS))
    total = ms * reps + gap * (reps - 1)
    return max(30, int(round(total / 1000.0)))


def target_at(pts, x):
    """Interpolated (value, tolerance) at a point on the axis.

    Works for both axes: on the time axis x is a moment, on the depth axis it is
    the measured depth. The device, the preview in the editor and the tests all
    use this one function, so they cannot drift apart.
    """
    if not pts:
        return (0, 0)
    if x <= pts[0][0]:
        return (pts[0][1], pts[0][2])
    for (x0, v0, l0), (x1, v1, l1) in zip(pts, pts[1:]):
        if x <= x1:
            span = x1 - x0
            f = 0.0 if span <= 0 else (x - x0) / float(span)
            return (v0 + (v1 - v0) * f, l0 + (l1 - l0) * f)
    return (pts[-1][1], pts[-1][2])


def output_at(track_row, pts, x, live=None):
    """What an output track actually emits, 0..100 percent of the wearer's ceiling.

    `absolut`   -> the curve value.
    `gekoppelt` -> the curve value is the UPPER LIMIT and the live measurement
                   decides the share (doc 19 §2.4): by position (how deep she is)
                   or by accuracy (how well she holds the band). Without a fresh
                   live value a coupled track emits nothing - never the maximum.
    """
    value = target_at(pts, x)[0]
    if (track_row.get('rt_mode') or MODE_ABSOLUTE) != MODE_COUPLED:
        return max(0.0, min(100.0, value))
    if not live:
        return 0.0
    couple = track_row.get('rt_couple') or COUPLE_POSITION
    # Explicit None checks: `live.get('err') or 1.0` would read a PERFECT run
    # (err 0.0 is falsy) as the worst one and withhold the whole reward.
    if couple == COUPLE_ACCURACY:
        err = live.get('err')
        share = 1.0 - max(0.0, min(1.0, 1.0 if err is None else float(err)))
    else:
        depth = live.get('depth')
        share = 0.0 if depth is None else max(0.0, min(1.0, float(depth) / 100.0))
    return max(0.0, min(100.0, value * share))


# --------------------------------------------------------------------------- #
# Picking a routine for a task level (doc 17 §14)
def pick_for_level(q, level, exclude=()):
    """Routine on that level; if there is none, the next lower one.

    The level selects the waveform instead of scaling a target, so the existing
    level automation (two runs graded A/B -> level +1) keeps working unchanged.

    Only TASKS on the TIME axis qualify (review 2026-09-11: without the filter a
    level-1 participant was handed 'Beispiel: Erst schlucken' - depth axis, purpose
    'reiz', no scored track - as her training task).
    """
    level = max(1, min(int(level or 1), 10))
    rows = q('SELECT ro_id, ro_level FROM routines '
             'WHERE ro_level<=%s AND ro_purpose=%s AND ro_axis=%s '
             'ORDER BY ro_level DESC, ro_id',
             (level, PURPOSE_TASK, AXIS_TIME)) or []
    for r in rows:
        if int(r['ro_id']) not in set(exclude):
            return int(r['ro_id'])
    return None


def is_task(row):
    """True when this waveform may run as a plan or challenge task: purpose
    'aufgabe' on the TIME axis. Anything else cannot be scored (review 2026-09-11)."""
    if not row:
        return False
    return (row.get('ro_purpose') or PURPOSE_TASK) == PURPOSE_TASK \
        and (row.get('ro_axis') or AXIS_TIME) == AXIS_TIME


def task_routines(q):
    """Waveforms eligible as tasks, for the pickers in plan and challenge."""
    return [r for r in all_routines(q, PURPOSE_TASK)
            if (r.get('ro_axis') or AXIS_TIME) == AXIS_TIME]


def is_stim(row):
    """True when this waveform can be PLAYED on a bridge: stimulus or reward on
    the time axis. A task has a scored track instead of outputs, and a depth-axis
    curve has no end - neither is playable (review 2026-09-11)."""
    if not row:
        return False
    return (row.get('ro_axis') or AXIS_TIME) == AXIS_TIME \
        and (row.get('ro_purpose') or PURPOSE_TASK) != PURPOSE_TASK


def is_couple(row):
    """True when this waveform can run as a COUPLING: it follows what is
    measured, so it has to live on the depth axis."""
    return bool(row) and (row.get('ro_axis') or AXIS_TIME) == AXIS_DEPTH


# What a parameter with actions.Param.ref may point at. One table, so the
# picker in a form and the check on the server can never disagree (2026-09-11).
REF_FILTERS = {
    'waveform_task':   is_task,
    'waveform_stim':   is_stim,
    'waveform_couple': is_couple,
}


def for_ref(q, ref):
    """Waveforms that qualify as the value of a parameter with this reference
    kind, newest meaning first. Empty list for an unknown kind."""
    test = REF_FILTERS.get(ref or '')
    if not test:
        return []
    return [r for r in all_routines(q) if test(r)]


def resolve(q, wt_routine=None, level=1):
    """Routine for a plan task: the named one wins, otherwise pick by level."""
    if wt_routine:
        row = get(q, wt_routine)
        if row and is_task(row):
            return row
        if row:
            # A named non-task cannot be scored - fall back to the level pick
            # instead of sending the trainer a curve it cannot follow.
            logger.warning('routines: task names routine %s (%s/%s), which is not a task '
                           'on the time axis - picking by level instead',
                           wt_routine, row.get('ro_purpose'), row.get('ro_axis'))
        else:
            logger.warning('routines: task names routine %s, which no longer exists', wt_routine)
    ro_id = pick_for_level(q, level)
    return get(q, ro_id) if ro_id else None


# --------------------------------------------------------------------------- #
# Editor warnings (doc 17 §8) — warn, never block. Same decision as MAGLOCK
# (doc 14 §12.7): the supervisor authors the waveform and is shown the problems.
def warnings(pts):
    """[{code, at_ms, text_de}] — the web layer translates via i18n."""
    out = []
    if not pts:
        return [{'code': W_EMPTY, 'at_ms': 0,
                 'text_de': 'Die Wellenform hat keine Stützpunkte — es gibt nichts nachzufahren.'}]
    if len(pts) > MAX_POINTS:
        out.append({'code': W_TOO_MANY, 'at_ms': 0,
                    'text_de': 'Mehr als %d Stützpunkte; das Gerät nimmt die Routine nicht an.' % MAX_POINTS})

    # long uninterrupted phase at great depth
    deep_since = None
    for t_ms, depth, _tol in pts:
        if depth >= WARN_DEEP_PCT:
            if deep_since is None:
                deep_since = t_ms
        else:
            if deep_since is not None and (t_ms - deep_since) > WARN_DEEP_S * 1000:
                out.append({'code': W_DEEP_HOLD, 'at_ms': deep_since,
                            'text_de': 'Ab %.1f s stehen %.0f s am Stück über %d %% Tiefe. '
                                       'Das ist die Stelle, an der der Atemweg am längsten blockiert ist.'
                                       % (deep_since / 1000.0, (t_ms - deep_since) / 1000.0, WARN_DEEP_PCT)})
            deep_since = None
    if deep_since is not None and (pts[-1][0] - deep_since) > WARN_DEEP_S * 1000:
        out.append({'code': W_DEEP_HOLD, 'at_ms': deep_since,
                    'text_de': 'Die Routine endet mit %.0f s am Stück über %d %% Tiefe.'
                               % ((pts[-1][0] - deep_since) / 1000.0, WARN_DEEP_PCT)})

    # steps nobody can follow
    for (t0, d0, _l0), (t1, d1, _l1) in zip(pts, pts[1:]):
        span = max(1, t1 - t0) / 1000.0
        rate = abs(d1 - d0) / span
        if rate > WARN_JUMP_PCT_PER_S:
            out.append({'code': W_JUMP, 'at_ms': t0,
                        'text_de': 'Bei %.1f s springt das Ziel um %d %% in %.2f s — das kann niemand '
                                   'nachfahren, der Tick zählt als Abweichung.' % (t0 / 1000.0, abs(d1 - d0), span)})

    # seam when the routine repeats
    if abs(pts[0][1] - pts[-1][1]) > WARN_SEAM_PCT:
        out.append({'code': W_SEAM, 'at_ms': pts[-1][0],
                    'text_de': 'Anfang (%d %%) und Ende (%d %%) liegen weit auseinander. Beim Wiederholen '
                               'interpoliert das Gerät einen Übergang; kürzer als die Übergangsdauer wird '
                               'es trotzdem hakelig.' % (pts[0][1], pts[-1][1])})
    return out


def waveform_warnings(head, loaded):
    """Warnings for a whole waveform: the per-curve ones plus the structural ones.

    `loaded` is [(track_row, points)]. Warnings never block (doc 17 §8); the two
    that WOULD break a run - no scored track in a task, an output track without an
    output - are still only warnings here, because the supervisor may be halfway
    through building the thing.
    """
    axis = (head or {}).get('ro_axis') or AXIS_TIME
    purpose = (head or {}).get('ro_purpose') or PURPOSE_TASK
    out = []
    for t, pts in loaded:
        for w in warnings(pts):
            # 'jump' and 'deep_hold' ask whether a HUMAN can follow the curve. On an
            # output track a hard onset is the point (profile 'stich'), not a flaw.
            if t['rt_role'] != ROLE_TARGET and w['code'] in (W_JUMP, W_DEEP_HOLD):
                continue
            # 'seam' is about REPEATING. A depth-axis curve never repeats - it is a
            # mapping from what is measured, so start and end are simply two ends.
            if axis == AXIS_DEPTH and w['code'] == W_SEAM:
                continue
            out.append(dict(w, track=int(t['rt_track'])))
        if t['rt_role'] in OUTPUT_ROLES and not (t['rt_channel'] or ''):
            out.append({'code': W_NO_CHANNEL, 'at_ms': 0, 'track': int(t['rt_track']),
                        'text_de': 'Spur %d gibt etwas aus, hat aber keinen Kanal — sie bleibt stumm.'
                                   % int(t['rt_track'])})
    if purpose == PURPOSE_TASK and not any(t['rt_role'] == ROLE_TARGET for t, _ in loaded):
        out.append({'code': W_NO_TARGET, 'at_ms': 0, 'track': 0,
                    'text_de': 'Eine Aufgabe ohne Zieltiefen-Spur kann nicht bewertet werden.'})

    # Two tracks on one channel at the same time: the protocol gives one frame per
    # 100 ms and channel, so they cannot be mixed (doc 19 §6.2). The bridge has a
    # fixed precedence; the editor says where it will bite.
    by_channel = {}
    for t, pts in loaded:
        ch = (t['rt_channel'] or '').strip()
        if ch and t['rt_role'] in OUTPUT_ROLES:
            by_channel.setdefault(ch, []).append((t, pts))
    for ch, group in by_channel.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                at = _overlap_at(group[i][1], group[j][1])
                if at is None:
                    continue
                out.append({'code': W_OVERLAP, 'at_ms': at, 'track': int(group[i][0]['rt_track']),
                            'text_de': 'Spur %d und Spur %d liegen beide auf %s und sind gleichzeitig '
                                       'aktiv. Es klingt nur eine (Bestrafung vor Stimulation vor '
                                       'Belohnung) — besser auf die zwei Kanäle verteilen.'
                                       % (int(group[i][0]['rt_track']), int(group[j][0]['rt_track']),
                                          ch.upper())})
    return out


def _overlap_at(a, b):
    """First X at which two curves are both above zero, or None."""
    if not a or not b:
        return None
    xs = sorted({x for x, _, _ in a} | {x for x, _, _ in b})
    for x in xs:
        if target_at(a, x)[0] > 0 and target_at(b, x)[0] > 0:
            return int(x)
    return None


def summary_line(head, loaded):
    """One sentence that says what this waveform IS — doc 19 §8.7.

    For somebody coming back after three months this line is half the
    documentation, so it is generated and never has to be kept in sync by hand.
    """
    import i18n
    axis = (head or {}).get('ro_axis') or AXIS_TIME
    purpose = (head or {}).get('ro_purpose') or PURPOSE_TASK
    parts = [i18n._(PURPOSES.get(purpose, (purpose, ''))[0]),
             i18n._(AXES.get(axis, (axis, axis, ''))[1])]
    if axis == AXIS_TIME:
        secs = max([duration_ms(pts) for _, pts in loaded] or [0]) / 1000.0
        parts.append('%g s' % round(secs, 1))
    scored = [t for t, _ in loaded if t['rt_role'] == ROLE_TARGET]
    if scored:
        parts.append(i18n._('bewertet, Mindestnote {n}', n=int((head or {}).get('ro_min_score') or 0)))
    outs = [t for t, _ in loaded if t['rt_role'] in OUTPUT_ROLES]
    if outs:
        import profiles
        bits = []
        for t in outs:
            label = profiles.role_label(t['rt_role'])[0]
            ch = (t['rt_channel'] or '').upper()
            mode = '' if t['rt_mode'] == MODE_ABSOLUTE else ' ' + i18n._('gekoppelt')
            bits.append('%s%s%s' % (label, (' (%s)' % ch) if ch else '', mode))
        # NOT `head` - that is the routine row this function was called with
        # (review 2026-09-11: shadowing worked by luck, until the next edit).
        prefix = i18n._('1 Spur: ') if len(outs) == 1 else i18n._('{n} Spuren: ', n=len(outs))
        parts.append(prefix + ', '.join(bits))
    return ' · '.join(parts)


# --------------------------------------------------------------------------- #
# Scoring helper, so central and firmware agree on the arithmetic (doc 17 §9)
def tick_error(depth_is, depth_target, tol, fullscale_pct):
    """Normalised deviation of one tick, 0..1. Inside the tolerance band it is 0."""
    a = abs(float(depth_is) - float(depth_target))
    tol = max(0.0, float(tol))
    if a <= tol:
        return 0.0
    fs = max(1.0, float(fullscale_pct))
    return min(1.0, (a - tol) / fs)


def score(errors):
    """Run score 0..10000 = 10000 * (1 - mean(error^2)).

    Variant A from doc 17 §9: squaring the DEVIATION punishes large lapses hard
    and rewards evenness. Reach's original squares the tick VALUE instead, which
    does the opposite — it rewards occasional perfect ticks over steady accuracy.
    """
    if not errors:
        return 0
    mse = sum(e * e for e in errors) / float(len(errors))
    return max(0, min(10000, int(round(10000 * (1.0 - mse)))))


def in_zone_pct(errors):
    """Share of ticks inside the tolerance band — the number shown to the participant."""
    if not errors:
        return 0
    return int(round(100.0 * sum(1 for e in errors if e <= 0.0) / len(errors)))
