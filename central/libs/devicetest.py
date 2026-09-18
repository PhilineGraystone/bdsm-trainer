# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Send one action to ONE device, without a slave and without a logbook.

Needed in two places: from the REST API (the mobile app) and from the test page
in the web (assembly, function check, bench). Both use exactly this path — two
implementations of the same procedure drift apart otherwise, and they do so at
the spot where it hurts: at the limits.

What does NOT happen here, and deliberately so:

  * NO run in the logbook, no grade, no points, no level promotion.
    A test is not an achievement. (doc 14: what counts is the completion of a
    planned task, not every single command.)
  * NO punishment. Whoever triggers something here is the supervisor with a
    tool in hand, not the installation with a verdict.
  * But VERY MUCH an entry in the audit log (doc 03): every physical effect is
    traceable, the hand-triggered one above all.

The limits of the device apply unchanged — the envelope sits in the firmware
and cannot be raised from here.
"""

import actions
import audit
import devicemodels
import i18n
import routines
from torturedevice import torturedevice


class TestError(ValueError):
    """The attempt was not permitted; the message is for humans."""


class _MqAdapter:
    """torturedevice expects an mqtt object with send_command()/emergency()."""

    def __init__(self, mq, user):
        self.mq, self.user = mq, user

    def send_command(self, device, action, args=None, ttl_ms=5000):
        return self.mq.send_command(device, action, args, ttl_ms, user=self.user)

    def emergency(self, device=None):
        return self.mq.emergency(device, user=self.user)


def device_snapshot(mq, uuid):
    """State of a device as the central unit sees it, or None."""
    for d in mq.snapshot()['devices']:
        if d['uuid'] == uuid:
            return d
    return None


def capabilities_of(d):
    """What the device REALLY can do, in this order:

      1. what the running firmware reports in the `hello` — it is there, it is right
      2. the model it names in the `hello`
      3. the model from the database

    Step 3 is not merely caution: after a restart of the web interface a device
    can already count as online (retained `state`) while its `hello` has not
    arrived yet. Without the fallback the test page would then stand there
    empty, although the database says what the device is.
    """
    hello = d.get('hello') or {}
    model = devicemodels.by_uuid(hello.get('model', ''))
    if not model:
        code = ((d.get('db') or {}).get('dev_model') or '')
        model = devicemodels.by_code(code) if code else None
    caps = hello.get('capabilities')
    return set(caps or (model.capabilities if model else [])), model


def actions_for(d):
    """Actions this device can carry out, in registry order.

    Filtered by the reported capabilities, so the list grows along by itself
    when a new device model is added — no second catalogue that goes stale
    (decision Philine 2026-09-11).
    """
    caps, _model = capabilities_of(d)
    out = []
    for a in actions.ACTIONS:
        if not a.implemented or not a.handler:
            continue
        if not a.capability:
            continue        # channel and sequence actions need a slave
        if a.capability in caps:
            out.append(a)
    return out


def test_default(p):
    """Pre-set of a field in the TEST form: short and low.

    In operation a program step holds whatever the supervisor planned there.
    When testing one wants to see whether anything happens — not wait two
    minutes and not start at full strength. Full values stay typeable
    (decision Philine 2026-09-11: shortened defaults, no hard ceilings).
    """
    def clamp(v):
        if p.min is not None and v < p.min:
            v = p.min
        if p.max is not None and v > p.max:
            v = p.max
        return v
    if p.type is str:
        return p.default if p.default is not None else ''
    if p.unit == 'min':
        return clamp(1)
    if p.unit == 's':
        return clamp(3)
    if p.unit == '%':
        return clamp(25)
    if p.default is not None:
        return p.default
    return p.min if p.min is not None else 1


def form_spec(action, envelope=None):
    """The parameters of an action, ready for a form.

    Prepared here and not in the template: a template that calculates is a
    template nobody can test.

    With `envelope` (the envelope of EXACTLY THIS device) the field is limited
    to what the device really lets through, and the limit stands in the help
    text. Otherwise the supervisor sets 120 minutes, the collar makes 60 out of
    that, and nobody finds out (decision Philine 2026-09-11).
    """
    out = []
    for p in action.params:
        cap = devicemodels.limit_for(envelope, p.limit, p.unit) if p.limit else None
        pmax = p.max
        capped = False
        if cap is not None and (pmax is None or cap < pmax):
            pmax = cap
            capped = True
        val = test_default(p)
        if isinstance(val, int) and pmax is not None and val > pmax:
            val = pmax
        out.append({
            'name': p.name,
            'label': p.label or p.name,
            'unit': p.unit,
            'min': p.min,
            'max': pmax,
            'registry_max': p.max,
            'capped': capped,          # the device is tighter than the installation
            'limit': p.limit or '',
            'required': p.default is None,
            'description': p.description,
            'ref': p.ref or '',
            'is_text': p.type is str,
            'value': val,
        })
    return out


def resolve_refs(q, action, params):
    """Check parameters that point at a record against the database.

    The selection in the form and this check use the same table
    (routines.REF_FILTERS) — what the list offers gets through as well, and what
    it does not offer does not get past by hand either.
    """
    for p in action.params:
        if not p.ref:
            continue
        val = int(params.get(p.name) or 0)
        if not val:
            continue            # 0 = none / the central unit picks
        row = routines.get(q, val)
        if not row:
            raise TestError('Wellenform %d gibt es nicht.' % val)
        test = routines.REF_FILTERS.get(p.ref)
        if test and not test(row):
            raise TestError('Wellenform „%s" passt nicht zu „%s".'
                            % (row['ro_name'], p.label or p.name))
    return params


def apply_envelope(action, params, envelope):
    """Cap values at the envelope of THIS device before they go out.

    The form limits the field already, but `max` in an HTML field is a hint,
    not a barrier: the REST API has no form at all, and a record submitted by
    hand gets past it. The device then refuses or caps silently — to the
    supervisor both look like "nothing happened".

    It is capped, not refused (decision Philine 2026-09-11: "limit it and write
    it down"). What was capped stands in the return value and goes to the page
    as a notice and into the audit log.
    """
    capped = []
    if not envelope:
        return capped
    for p in action.params:
        if not p.limit or p.name not in params:
            continue
        cap = devicemodels.limit_for(envelope, p.limit, p.unit)
        if cap is None:
            continue
        val = params[p.name]
        if isinstance(val, int) and not isinstance(val, bool) and val > cap:
            params[p.name] = cap
            capped.append((p.label or p.name, val, cap, p.unit))
    return capped


def _routine_args(action, params, lb):
    """The two actions that name a WAVEFORM need all the support points on the
    device, not the number.

    torturedevice.trainer_routine()/estim_routine() expect the database row and
    send the curve themselves beforehand; the registry, however, only knows a
    number. Whoever passes the number through gets a TypeError on the first
    access to row['ro_id'] — that is why the REST app could never trigger these
    two actions (finding 2026-09-11). Here the number is resolved to the row
    and the waveform is transmitted before the start.
    """
    if action.code not in ('TRAINER_ROUTINE', 'ESTIM_ROUTINE'):
        return None
    if lb is None or not getattr(lb, 'routines_enabled', False):
        raise TestError('Wellenformen sind nicht verfügbar (Migration 008/009 fehlt).')
    ro_id = int(params.get('routine') or 0)
    if not ro_id:
        raise TestError('Für den Test muss eine Wellenform gewählt werden — '
                        'die Zentrale wählt nur für einen angemeldeten Sklaven.')
    pay = lb.routine_payload(ro_id)
    if not pay:
        raise TestError('Wellenform %d hat keine Stützpunkte.' % ro_id)
    return pay


def run(mq, q, uuid, code, params, user, lb=None, calibration=None, slave_id=None,
        dev=None, capped=None):
    """Send one action to a device. Returns the checked parameters.

    mq            central-unit connection (send_command/snapshot)
    q             database query, for waveforms and calibration
    lb            logbook object, only to load waveforms (nothing is booked)
    calibration   optional: dict of a slave's calibration (PET)
    slave_id      only for the audit log, in case the test belongs to somebody
    capped        optional: list that is written to with what was capped at
                  this device's envelope — (field, wanted, sent, unit). The
                  call site tells the supervisor about it.
    """
    code = (code or '').upper()
    # `dev` is passed through by the call site when it has the enriched object
    # anyway (the web interface) - then the fallback to the model from the
    # database knows its data as well.
    d = dev or device_snapshot(mq, uuid)
    if not d or not d['online']:
        raise TestError('Gerät ist nicht online.')

    # Base commands of the framework are not in the registry.
    if code in ('STOP', 'IDENTIFY'):
        mq.send_command(uuid, code.lower(), ttl_ms=2000 if code == 'STOP' else 5000, user=user)
        audit.web('device_test', user, kind='cmd', device=uuid, slave_id=slave_id,
                  data={'code': code})
        return {}

    action = actions.get(code)
    if not action or not action.implemented or not action.handler:
        raise TestError('Unbekannte Aktion %s.' % code)
    caps, model = capabilities_of(d)
    if action.capability and action.capability not in caps:
        raise TestError('Das Gerät hat die Fähigkeit „%s" nicht.' % action.capability)
    try:
        p = actions.parse_dict(action, params)
    except actions.ActionError as e:
        raise TestError(str(e))
    resolve_refs(q, action, p)
    # The envelope applies EVEN when no form was in between: the REST API has
    # none, and a field with `max` in the HTML is a hint, not a barrier.
    cut = apply_envelope(action, p, devicemodels.envelope_of(model, (d.get('hello') or {}).get('limits')))
    if capped is not None:
        capped.extend(cut)

    td = torturedevice(_MqAdapter(mq, user), (model.uuid if model else ''), uuid, None, True,
                       capabilities=caps)
    args = [p[x.name] for x in action.params]
    kwargs = {}

    pay = _routine_args(action, p, lb)
    if pay is not None:
        # REFUSE FIRST, TRANSMIT AFTERWARDS. The test needs the slave's
        # ceiling too: since the bridge writes the strength itself, that
        # strength is the pulse height, and the calibration is the only thing
        # above it (doc 28). A test with a default would be exactly the path by
        # which an unmeasured height would still reach the skin — and tests run
        # on the live device. For checking WITHOUT a slave there is the raw
        # output; that one demands its value explicitly.
        #
        # The order was the other way round at first, and then a refused test
        # still dutifully transmitted the waveform to the device: work and an
        # entry in the log for something that was never meant to run.
        if action.code == 'ESTIM_ROUTINE':
            est = (calibration or {}).get('estim')
            if not est:
                raise TestError(i18n._('Für diesen Sklave ist an diesem Gerät keine E-Stim-Stärke '
                                       'kalibriert — ohne sie gibt die Bridge nichts aus. Zum Prüfen ohne '
                                       'Sklave die Rohausgabe benutzen.'))
            kwargs['ceiling'] = (int(round(est['sc_x'])), int(round(est['sc_y'])))
        # Transmit the waveform first, then start — exactly as in operation
        # (doc 17 §7). That way the test also checks the transmission and the
        # checksum, not just the start command.
        td.routine_push(pay['row'], pay['tracks'], pay['crc32'])
        args[0] = pay['row']
        kwargs['crc32'] = pay['crc32']
        kwargs['limits'] = lb.estim_limits() if action.code == 'ESTIM_ROUTINE' else lb.routine_limits()
        if action.code == 'TRAINER_ROUTINE':
            # The coupling is the last parameter and does not belong on the
            # device: it goes to the slave's bridges, which do not exist in a test.
            args = args[:3]

    elif action.handler == 'hold_task':
        # TRAY/SILENCE/KNEEL share one handler and differ only in `kind` — and
        # on the device that one comes FIRST, not last. Without this line
        # `target_s` would have landed as the kind and the call would have died
        # with a TypeError (finding 2026-09-11: the REST app could never
        # trigger these three tasks).
        args = [action.code.lower()] + args

    elif action.code == 'PET' and calibration:
        refs = {k: [calibration[k]['sc_x'], calibration[k]['sc_y'], calibration[k]['sc_z']]
                for k in ('pet', 'stand') if k in calibration}
        kwargs['ref_pet'] = refs.get('pet')
        kwargs['ref_stand'] = refs.get('stand')

    getattr(td, action.handler)(*args, **kwargs)
    data = {'code': code, 'params': p}
    if cut:
        # What was capped belongs in the log: otherwise a value stands there
        # that nobody set, and nobody knows why.
        data['capped'] = [{'field': f, 'wanted': w, 'sent': s, 'unit': u} for f, w, s, u in cut]
    audit.web('device_test', user, kind='cmd', device=uuid, slave_id=slave_id, data=data)
    return p
