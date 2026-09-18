# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Does the programme fit what the slave actually wears?

The question can be answered neither at the programme nor at the device alone.
A programme step belongs to a slave, not to a device — while editing it is not
even settled which collar will later carry it out. And a device knows nothing
of programmes. Only at the slave do both sides meet: there it stands which
programmes are assigned to her AND which devices she wears (decision Philine
2026-09-11, after a capping in the programme editor was rejected: there the
limit would have been guessed again).

Four kinds of thing are found — all of them causes for a step not running the
way it stands there:

  overflow        A value lies above the envelope of her device. Technically an
                  overflow: the device caps it or refuses.
  no_capability   No assigned device can do what the step demands. The step
                  runs silently into the void.
  offline         The device is assigned but has never reported in.
  no_calibration  A step needs a calibration that is missing for this device
                  and this slave.
  invalid         The step does not go through the registry at all any more.
                  That happens exactly when a stored programme comes from a
                  time in which the installation allowed more — after the
                  alignment with the firmware (doc 23), SHOCK with 30 seconds
                  for instance. Such a step MUST NOT be silently skipped
                  here: it is the worst case, not the most harmless.

Measured against the STRICTEST envelope of all devices with the matching
capability. That is no excess of caution: `slave.device_for()` takes the first
ONLINE device with the capability. If she wears two collars with different
ceilings, either of them can get the step — a display that means only the more
generous one would be plainly wrong.

This file only checks and judges. Capping happens when sending (devicetest.py
and torturedevice), not here.
"""

import actions
import devicemodels

OVERFLOW = 'overflow'
NO_CAPABILITY = 'no_capability'
OFFLINE = 'offline'
NO_CALIBRATION = 'no_calibration'
TOO_FEW = 'too_few'            # the step needs more components than the device has usable (doc 42 point 4)
INVALID = 'invalid'

# How urgent a finding is. Steers the order and the colour: a step that does
# not run at all stands above one that is merely capped.
SEVERITY = {INVALID: 0, NO_CAPABILITY: 1, TOO_FEW: 1, OVERFLOW: 2, NO_CALIBRATION: 3, OFFLINE: 4}

# Which capability needs which calibration. Stands here and not in the web
# interface so that central unit and web give the same answer.
NEEDS_CALIBRATION = {
    'mode_pet':   ('pet', 'stand'),     # posture: two reference positions
    'depth_cal':  ('depth',),           # trainer: depth
    'trainer_rep':     ('depth',),
    'trainer_end':     ('depth',),
    'trainer_free':    ('depth',),
    'trainer_routine': ('depth',),
    'estim_routine':   ('estim',),      # e-stim: pulse height per channel
}

# For which capabilities a missing calibration makes the step NOT ONLY
# inaccurate but IMPOSSIBLE.
#
# The difference is important enough for a table of its own: without a depth
# reference the trainer learns for itself at the start and runs on. Without an
# e-stim ceiling nothing runs at all — the ceiling IS the pulse height, and a
# guessed height does not exist on this device (decision Philine 2026-09-11,
# doc 28). A finding that makes both look the same tempts one to treat the
# one like the other.
CALIBRATION_BLOCKS = {'estim_routine'}


def devices_of(q, sid, online=None):
    """The devices assigned to a slave, enriched with model, capabilities and
    envelope.

    `online` is the dict uuid -> device state from mq.snapshot(); without it
    all of them count as offline-unknown, and the envelope comes from the
    model catalogue instead of from what the firmware reports.
    """
    # Careful, the columns are named the other way round than one thinks:
    # `dev_name` is the UUID (and thus the key in the calibration),
    # `dev_address` the name that a human reads.
    rows = q('SELECT d.dev_id, d.dev_name, d.dev_model, d.dev_address '
             '  FROM devtoslave t JOIN devices d ON d.dev_id=t.dts_deviceid '
             ' WHERE t.dts_slaveid=%s ORDER BY d.dev_address', (sid,)) or []
    out = []
    for r in rows:
        model = devicemodels.by_code(r['dev_model'])
        live = (online or {}).get(r['dev_name']) or {}
        hello = live.get('hello') or {}
        degraded = devicemodels.degraded_of(hello)
        caps, _refused = devicemodels.effective_capabilities(
            model, hello.get('capabilities') or None, degraded)
        out.append({
            'id': r['dev_id'], 'uuid': r['dev_name'],
            'name': r['dev_address'] or r['dev_name'],
            'model': model, 'model_code': r['dev_model'],
            'capabilities': caps,
            'degraded': degraded or [],
            'available': devicemodels.available_count(model, degraded),
            'envelope': devicemodels.envelope_of(model, hello.get('limits')),
            'reported': bool(hello.get('limits')),
            'online': bool(live.get('online')),
        })
    return out


def strictest(devs):
    """The tightest envelope across several devices.

    Per key the smallest value — EXCEPT for the keys where larger is the
    stricter one (devicemodels.LARGER_IS_STRICTER): with a cool-down time
    between two pulses, longer is the sharper limit, not shorter. Without this
    distinction the most unsafe of several numbers would silently win here.

    Keys that only one device names still count — a device that says nothing
    about it does not say "unlimited", it says nothing.
    """
    out = {}
    for d in devs:
        for k, v in (d['envelope'] or {}).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue        # tiers like pun_lvl are not an upper limit
            if k not in out:
                out[k] = v
            elif k in devicemodels.LARGER_IS_STRICTER:
                out[k] = max(out[k], v)
            else:
                out[k] = min(out[k], v)
    return out


def _devnames(devs):
    return ', '.join(d['name'] for d in devs)


def check_step(action, params, devs, calibration=None, step_no=None):
    """A single programme step against the devices of ONE slave."""
    found = []
    if not action.capability:
        return found            # WAIT and flow steps need no device

    able = [d for d in devs if action.capability in d['capabilities']]
    if not able:
        found.append({'kind': NO_CAPABILITY, 'step': step_no, 'action': action,
                      'capability': action.capability})
        return found            # without a device everything further is moot

    if not any(d['online'] for d in able):
        found.append({'kind': OFFLINE, 'step': step_no, 'action': action,
                      'devices': _devnames(able)})

    # Counted components (doc 42 point 4): a MagLock with a cuff reported out
    # still has `lock`, but a step that needs all four cannot run on it. Said
    # here, before the day — not discovered as a skipped step in the log.
    need = params.get('cuffs') if isinstance(params, dict) else None
    if isinstance(need, int) and not isinstance(need, bool):
        short = [d for d in able if d.get('available') is not None and d['available'] < need]
        if short and len(short) == len(able):
            found.append({'kind': TOO_FEW, 'step': step_no, 'action': action,
                          'wanted': need, 'have': max(d['available'] for d in short),
                          'devices': _devnames(short)})

    env = strictest(able)
    for p in action.params:
        if not p.limit or p.name not in params:
            continue
        cap = devicemodels.limit_for(env, p.limit, p.unit)
        val = params.get(p.name)
        if cap is None or isinstance(val, bool) or not isinstance(val, int):
            continue
        if val > cap:
            # Which device sets the limit belongs with it — otherwise the
            # supervisor searches the wrong one among three collars.
            tight = [d for d in able
                     if devicemodels.limit_for(d['envelope'], p.limit, p.unit) == cap]
            found.append({'kind': OVERFLOW, 'step': step_no, 'action': action,
                          'param': p, 'wanted': val, 'allowed': cap,
                          'devices': _devnames(tight or able)})

    for pose_set in (NEEDS_CALIBRATION.get(action.capability),):
        if not pose_set:
            continue
        # The calibration stands under the UUID, not under the display name.
        missing = [d for d in able
                   if not set(pose_set) <= set((calibration or {}).get(d['uuid'], {}))]
        if missing and len(missing) == len(able):
            found.append({'kind': NO_CALIBRATION, 'step': step_no, 'action': action,
                          'poses': pose_set, 'devices': _devnames(missing),
                          'blocking': action.capability in CALIBRATION_BLOCKS})
    return found


def check_program(q, pro_id, devs, calibration=None):
    """All steps of a programme against the devices of a slave."""
    rows = q('SELECT pc_id, pc_command, pc_parameter FROM program_commands '
             ' WHERE pc_program=%s ORDER BY pc_id', (pro_id,)) or []
    found = []
    for n, row in enumerate(rows, 1):
        action = actions.get(row['pc_command'])
        if not action or not action.implemented:
            found.append({'kind': INVALID, 'step': n, 'action': None,
                          'code': row['pc_command'],
                          'reason': 'unbekannte oder nicht umgesetzte Aktion'})
            continue
        try:
            params = actions.parse_params(action, row['pc_parameter'])
        except actions.ActionError as e:
            found.append({'kind': INVALID, 'step': n, 'action': action,
                          'code': action.code, 'reason': str(e)})
            continue
        found.extend(check_step(action, params, devs, calibration, step_no=n))
    found.sort(key=lambda f: (SEVERITY.get(f['kind'], 9), f['step'] or 0))
    return found


def check_slave(q, sid, online=None, calibration=None):
    """Findings per programme assigned to a slave.

    Returns [{'program': {...}, 'active': bool, 'findings': [...]}] — only
    programmes WITH a finding, the active one first.
    """
    devs = devices_of(q, sid, online)
    rows = q('SELECT p.pro_id, p.pro_name, (s.slave_program=p.pro_id) AS active '
             '  FROM slave_program sp JOIN program p ON p.pro_id=sp.sp_program '
             '  JOIN slaves s ON s.slave_id=sp.sp_slave '
             ' WHERE sp.sp_slave=%s ORDER BY p.pro_name', (sid,)) or []
    out = []
    for r in rows:
        f = check_program(q, r['pro_id'], devs, calibration)
        if f:
            out.append({'program': {'id': r['pro_id'], 'name': r['pro_name']},
                        'active': bool(r['active']), 'findings': f})
    out.sort(key=lambda e: (not e['active'], e['program']['name']))
    return out


def counts(entries):
    """Count findings by kind — for a marker in the overview."""
    c = {}
    for e in entries:
        for f in e['findings']:
            c[f['kind']] = c.get(f['kind'], 0) + 1
    return c


def summary(entries):
    """(count, count in the ACTIVE programme). The active one weighs more:
    that is what runs today."""
    total = sum(len(e['findings']) for e in entries)
    active = sum(len(e['findings']) for e in entries if e['active'])
    return total, active
