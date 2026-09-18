# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Read, compare and judge firmware versions.

WHY THIS IS A MODULE OF ITS OWN

Up to 1.x a device reported a single string ("CoyoteBridge-2.7"), and whoever
wanted to know something about it cut the number out themselves. That happened
in several places, each with its own small deviation. From 2.0 on the device
reports three numbers per version, and the comparing lives exactly here.

TWO VERSIONS, TWO FLOORS

A device reports the version of its FRAMEWORK (the same for every device) and
of its SKETCH (specific to the kind of device). The central unit keeps a
minimum version for both, per model. Both have to be met.

Why two floors and not one: a freshly flashed framework with an old sketch
slips straight through a single floor. On a bridge that would be firmware
writing the channel register by the old contract while the central unit has
long assumed the new one - and that lands on skin.

THREE STATES, NOT TWO

    ok        everything up to date
    outdated  above the floor but not current -> runs, and says so
    blocked   below the floor -> takes no commands

The middle state is the important one. Without it you would have to either
refuse every older device (and then the exhibition stops because one pad is
still on 2.0.1) or refuse nothing at all (and then nothing is ever noticed).
"""

import re

_NUM = re.compile(r'^\d+$')


def parse(value):
    """Read a version out of the `hello`. Returns (major, minor, patch) or None.

    Accepted is what firmware from 2.0 sends - an object with the three
    numbers - and, failing that, a string "2.0.1". Everything else is None,
    and None does NOT mean "old", it means "unreadable": a device whose version
    cannot be read is treated like one below the floor. Guessing would be the
    wrong kind of kindness here.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            t = (int(value.get('major')), int(value.get('minor')),
                 int(value.get('patch')))
        except (TypeError, ValueError):
            return None
        return t if all(x >= 0 for x in t) else None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(int(x) for x in value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        parts = value.strip().split('.')
        if len(parts) != 3 or not all(_NUM.match(p) for p in parts):
            return None
        return tuple(int(p) for p in parts)
    return None


def text(v):
    """(2, 0, 1) -> '2.0.1'. None -> '?' - never an invented number."""
    if not v:
        return '?'
    return '%d.%d.%d' % tuple(v)


def cmp(a, b):
    """-1 / 0 / 1. Both have to be real versions."""
    return (a > b) - (a < b)


def sketch_name(hello):
    s = (hello or {}).get('fw_sketch')
    if isinstance(s, dict) and s.get('name'):
        return str(s['name'])[:40]
    return ''


def of(hello):
    """(framework, sketch) out of a hello message. Either is None when unreadable."""
    h = hello or {}
    return parse(h.get('fw_framework')), parse(h.get('fw_sketch'))


# --------------------------------------------------------------------------- #
# Judgement
# --------------------------------------------------------------------------- #

OK       = 'ok'
OUTDATED = 'veraltet'
BLOCKED  = 'gesperrt'


class Verdict:
    """The result of the check, with plain text for the log and the interface.

    `reason` says WHICH of the two versions is too old. Without it the
    supervisor faces "firmware too old" and does not know what to flash.
    """

    def __init__(self, state, reason='', framework=None, sketch=None):
        self.state = state
        self.reason = reason
        self.framework = framework
        self.sketch = sketch

    @property
    def blocked(self):
        return self.state == BLOCKED

    @property
    def outdated(self):
        return self.state == OUTDATED

    def __repr__(self):
        return f'<Verdict {self.state} {self.reason!r}>'


def judge(hello, model):
    """Hold a hello message against a model's floors.

    `model` is a DeviceModel (libs/devicemodels.py) or None. When the model is
    unknown nothing is blocked: blocking is a statement about a known minimum
    version, and there is none in that case.
    """
    fw, sk = of(hello)

    if model is None:
        return Verdict(OK, 'Modell unbekannt — keine Mindestversion hinterlegt',
                       fw, sk)

    min_fw = getattr(model, 'fw_min_framework', None)
    min_sk = getattr(model, 'fw_min_sketch', None)
    cur_fw = getattr(model, 'fw_current_framework', None)
    cur_sk = getattr(model, 'fw_current_sketch', None)

    # Unreadable counts as too old - but only where there is a floor at all.
    # A model without a floor has no opinion.
    if min_fw and fw is None:
        return Verdict(BLOCKED, 'Framework-Version fehlt oder ist unlesbar '
                                f'(mindestens {text(min_fw)})', fw, sk)
    if min_sk and sk is None:
        return Verdict(BLOCKED, 'Sketch-Version fehlt oder ist unlesbar '
                                f'(mindestens {text(min_sk)})', fw, sk)

    if min_fw and fw < min_fw:
        return Verdict(BLOCKED, f'Framework {text(fw)} ist aelter als '
                                f'{text(min_fw)}', fw, sk)
    if min_sk and sk < min_sk:
        return Verdict(BLOCKED, f'Sketch {text(sk)} ist aelter als '
                                f'{text(min_sk)}', fw, sk)

    stale = []
    if cur_fw and fw and fw < cur_fw:
        stale.append(f'Framework {text(fw)} statt {text(cur_fw)}')
    if cur_sk and sk and sk < cur_sk:
        stale.append(f'Sketch {text(sk)} statt {text(cur_sk)}')
    if stale:
        return Verdict(OUTDATED, ', '.join(stale), fw, sk)

    return Verdict(OK, '', fw, sk)
