# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Pulse profiles for the output side of a waveform (project doc 19 section 3).

A PROFILE describes how a pulse FEELS - rhythm, frequency, shape. The
CHOREOGRAPHY - when how much - is the curve the supervisor draws. By doc 01
("catalogue in code, variable data in the database") the profile therefore lives
here and not in a table.

That is not just tidiness, it carries weight: reward and punishment must differ
in CHARACTER, not in height. Same electrodes, same profile, once at 60 percent as
praise and once at 60 percent as punishment are indistinguishable - and then the
whole bookkeeping of doc 14 turns into noise for the participant. So the roles
are fixed here and cannot be configured away. The collar is the precedent: its
reward is TWO GENTLE PULSES, not a quiet shock.

The curve only sets the INTENSITY of the profile, 0..100 percent of the ceiling
the wearer set on the device himself. The rhythm stays untouched.
"""

import math
from dataclasses import dataclass, field

import i18n

# Roles a track can have. 'zieltiefe' is the scored curve from doc 17 and has no
# profile - it is not an output.
ROLE_TARGET = 'zieltiefe'
ROLE_PUNISH = 'bestrafung'
ROLE_STIM = 'stimulation'
ROLE_REWARD = 'belohnung'
OUTPUT_ROLES = (ROLE_PUNISH, ROLE_STIM, ROLE_REWARD)
ROLES = (ROLE_TARGET,) + OUTPUT_ROLES

ROLE_LABELS = {
    ROLE_TARGET: ('Zieltiefe', 'Die Kurve, die nachgefahren und bewertet wird. Kein Ausgang.'),
    ROLE_PUNISH: ('Bestrafung', 'Unangenehm. Harter Einsatz, damit sie sich von einer Belohnung '
                                'unterscheidet — nicht nur in der Höhe, sondern im Gefühl.'),
    ROLE_STIM:   ('Stimulation', 'Weder Lob noch Strafe: Reiz, der die Aufgabe begleitet.'),
    ROLE_REWARD: ('Belohnung', 'Angenehm und unverwechselbar. Wird nur für Erreichtes gegeben.'),
}

# Coupling: what a 'gekoppelt' track follows.
COUPLE_POSITION = 'position'
COUPLE_ACCURACY = 'genauigkeit'
COUPLE_LABELS = {
    COUPLE_POSITION: ('Position', 'Wie tief sie gerade ist, bestimmt den Anteil.'),
    COUPLE_ACCURACY: ('Genauigkeit', 'Wie gut sie im Toleranzband liegt, bestimmt den Anteil.'),
}

MODE_ABSOLUTE = 'absolut'
MODE_COUPLED = 'gekoppelt'
MODE_LABELS = {
    MODE_ABSOLUTE: ('Absolut', 'Der Wert der Kurve kommt so heraus.'),
    MODE_COUPLED: ('Gekoppelt', 'Der Wert der Kurve ist die Obergrenze; wie viel davon ankommt, '
                                'hängt von ihr ab.'),
}

# Output channels. 'a' and 'b' are the two independent channels of a Coyote, each
# on its own pair of electrodes; 'vibe' is a vibrator.
CHANNELS = {
    'a': ('Kanal A', 'Erstes Elektrodenpaar der Coyote.'),
    'b': ('Kanal B', 'Zweites Elektrodenpaar der Coyote.'),
    'vibe': ('Vibration', 'Vibrator statt Strom.'),
}


@dataclass(frozen=True)
class Profile:
    """One pulse character.

    hz_low/hz_high are the frequency band the profile sweeps; the bridge converts
    to the compressed period value the device wants (the Coyote takes 10..240 for
    a 10..1000 ms period: 100 ms -> 100 = 10 Hz, 650 ms -> 204 = 1.53 Hz).

    shape is the loop the bridge repeats, one entry per 100 ms frame, each a
    factor 0..1 on the intensity the curve asks for. That is what makes a profile
    recognisable: 'zweitakt' is two beats and a rest, at any intensity.
    """
    key: str
    role: str
    name_de: str
    desc_de: str
    hz_low: float
    hz_high: float
    shape: tuple = field(default=(1.0,))

    @property
    def name(self):
        return i18n._(self.name_de)

    @property
    def description(self):
        return i18n._(self.desc_de)

    @property
    def loop_ms(self):
        return len(self.shape) * 100


PROFILES = (
    Profile('stich', ROLE_PUNISH, 'Stich',
            'Harter Einsatz, beißend, kein Nachlassen. Das schärfste Profil.',
            50.0, 80.0, (1.0, 1.0)),
    Profile('haken', ROLE_PUNISH, 'Haken',
            'Langsames Ziehen, unangenehm ohne Spitze. Für lange Phasen, in denen ein Stich '
            'nur abstumpfen würde.',
            14.0, 20.0, (0.6, 0.8, 1.0, 1.0, 0.8, 0.6, 0.4, 0.3, 0.4)),
    Profile('welle', ROLE_STIM, 'Welle',
            'Rollend, weich an- und abschwellend. Das ruhige Grundprofil für lange Reize.',
            8.0, 14.0, (0.3, 0.5, 0.7, 0.9, 1.0, 0.9, 0.7, 0.5, 0.3, 0.2, 0.2, 0.25)),
    Profile('flirren', ROLE_STIM, 'Flirren',
            'Fein, oberflächlich, kribbelnd. Bleibt präsent, ohne zu ermüden.',
            60.0, 90.0, (1.0, 0.85, 1.0, 0.85)),
    Profile('zweitakt', ROLE_REWARD, 'Zweitakt',
            'Zwei deutliche Schläge, dann Ruhe — unverwechselbar und nie mit einer Strafe zu '
            'verwechseln. Entspricht den zwei sanften Stößen des Halsbands.',
            18.0, 24.0, (1.0, 0.9, 0.0, 1.0, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0)),
    Profile('warm', ROLE_REWARD, 'Warm',
            'Tief, satt, gleichmäßig tragend. Für längere Belohnungen, bei denen ein Takt '
            'aufdringlich würde.',
            10.0, 14.0, (0.85, 0.9, 0.95, 1.0, 1.0, 0.95, 0.9, 0.85, 0.85, 0.9, 0.95, 1.0, 1.0, 0.95, 0.9)),
)

BY_KEY = {p.key: p for p in PROFILES}


def get(key):
    return BY_KEY.get((key or '').strip().lower())


def for_role(role):
    """Profiles a track with this role may use. A reward can never be given a
    punishment profile - that is the point of fixing the roles here."""
    return [p for p in PROFILES if p.role == role]


def default_for(role):
    p = for_role(role)
    return p[0].key if p else None


def role_label(role):
    de = ROLE_LABELS.get(role)
    return (i18n._(de[0]), i18n._(de[1])) if de else (role, '')


def channel_label(channel):
    de = CHANNELS.get(channel)
    return (i18n._(de[0]), i18n._(de[1])) if de else (channel or '—', '')


def mode_label(mode):
    de = MODE_LABELS.get(mode)
    return (i18n._(de[0]), i18n._(de[1])) if de else (mode, '')


def couple_label(couple):
    de = COUPLE_LABELS.get(couple)
    return (i18n._(de[0]), i18n._(de[1])) if de else ('—', '')


# --------------------------------------------------------------------------- #
# Conversion for the bridge. Kept here so central and firmware agree; the bridge
# reimplements the same two lines.
def period_value(hz):
    """Coyote frequency value (10..240) for a frequency in Hz.

    The device takes a compressed period: 10..1000 ms map to 10..240, in three
    segments. The formula is quoted verbatim from the vendor documentation
    (DG-LAB-OPENSOURCE, coyote/v3/README.md) and uses INTEGER division:

        10..100 ms   -> value = period
        100..600 ms  -> value = (period - 100) / 5 + 100
        600..1000 ms -> value = (period - 600) / 10 + 200

    Integer, not rounded: rounding disagreed with the firmware on 380 of the
    991 possible periods (103 ms gave 101 here and 100 on the device). The
    device is what the value is FOR, so the device's arithmetic wins — checked
    by firmware/.../CoyoteBridge/test/check_against_central.py.

    Reference points: 100 ms -> 100 (10 Hz), 650 ms -> 205 (1.53 Hz). The
    vendor's own table prints 204 for 650 ms, which contradicts both the
    formula and the 1.53 Hz next to it; the formula is right.
    """
    hz = max(0.5, min(500.0, float(hz)))
    # floor(x + 0.5) rather than round(): Python rounds half to EVEN, so 80 Hz
    # (12.5 ms) became 12 here and 13 on the device — profile 'stich' sits
    # exactly on that half. Ten of 208 catalogue frames disagreed.
    period_ms = int(math.floor(1000.0 / hz + 0.5))
    period_ms = max(10, min(1000, period_ms))
    if period_ms <= 100:
        v = period_ms
    elif period_ms <= 600:
        v = (period_ms - 100) // 5 + 100
    else:
        v = (period_ms - 600) // 10 + 200
    return max(10, min(240, int(v)))


def frame(profile, intensity_pct, step):
    """One 100 ms frame of the profile: (frequency value, intensity 0..100).

    `step` counts frames since the start, so the loop keeps running while the
    curve changes the intensity underneath it.
    """
    if not profile:
        return (period_value(10.0), 0)
    n = len(profile.shape)
    f = profile.shape[int(step) % n] if n else 1.0
    # Sweep the band with the same loop, so the character has movement in pitch
    # as well as in level.
    span = profile.hz_high - profile.hz_low
    hz = profile.hz_low + span * f
    # Two traps at once, both found by check_against_central.py (2026-09-11):
    #   * floor(x + 0.5), not round(): Python rounds half to EVEN, so round(22.5)
    #     is 22 while the firmware's lroundf() gives 23.
    #   * the shape factor goes in as an INTEGER percent. `45 * 0.7` is
    #     31.499999999999996 in binary floating point and rounds DOWN, while the
    #     firmware computes 45 * 70 / 100 = 31.5 exactly and rounds UP.
    # One unit in a hundred is nothing on the skin, but two implementations
    # that disagree are a bug waiting for a bad day.
    f_pct = int(math.floor(f * 100 + 0.5))
    value = max(0, min(100, int(math.floor(float(intensity_pct) * f_pct / 100.0 + 0.5))))
    return (period_value(hz), value)
