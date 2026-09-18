# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Registry of the device models.

Principle (settled 2026-09-06): whatever only changes with a release belongs
in the code. The mapping model -> capabilities is laid down by the firmware,
so it lives here. The database only holds which physical device
(devices.dev_name) has which model (devices.dev_model).

A device reports its model UUID on announce; that is how the model is found
(MODELS_BY_UUID). devices.dev_model uses the short code.
"""

from dataclasses import dataclass, field

import i18n


@dataclass(frozen=True)
class DeviceModel:
    code: str                      # value in devices.dev_model
    uuid: str                      # the firmware's answer to {"initial": "functions"}
    name: str
    capabilities: frozenset        # see CAPABILITIES
    # Envelope (security architecture C). None = not laid down yet.
    # OPEN: settle the values with the content team / a specialist. As long as
    # it is None, no limiting happens in the central unit — the firmware has to
    # hold its own, harder limits anyway.
    envelope: dict = field(default_factory=dict)

    # TWO FLOORS PER MODEL (decision Philine 2026-09-13)
    #
    # fw_min_*      below this the device is REFUSED, not warned about
    # fw_current_*  above this it is current; in between it runs with a notice
    #
    # Why two and not one: a freshly flashed framework with an old sketch
    # falls straight through a single floor. On the bridge that would be a
    # firmware that writes the channel register by the old contract while
    # the central unit has long since assumed the new one.
    #
    # None = no floor. For a model whose firmware does not exist yet, that is
    # the honest value — an invented minimum version would otherwise lock out
    # the first device that is ever built.
    #
    # RAISED TO 2.1.0 ON 2026-09-15, and deliberately so. 2.0.0 carried three
    # holes that a device cannot be talked out of from here: its will sat on a
    # signed topic and was therefore thrown away, so the central unit never
    # learned that it had gone; its command checks treated a missing field as
    # permission; and `response` was unsigned although the central unit acts on
    # it. None of that can be repaired from the central side — so 2.0.0 is
    # refused rather than warned about (decision Philine).
    #
    # 2.1.1 RAISES ONLY `current`, NOT THE FLOOR — and that distinction is the
    # whole point of having two numbers. What 2.1.1 changes happens at BUILD
    # time: the guard against placeholder credentials now also catches an empty
    # value, and OTA is held to the same rule. On the air a 2.1.1 device and a
    # 2.1.0 device are indistinguishable. Refusing 2.1.0 would mean an
    # installation flashed yesterday standing still today, for a fault that
    # does not exist on it. It gets the notice, not the bar.
    #
    # The replay guard of the same day is a matter for the CENTRAL UNIT alone
    # (punsign.ReplayGuard): no device publishes on a control topic.
    #
    # 2.1.2, the same reasoning: the callback buffer and the pessimistic live
    # defaults are device-side repairs, but this central unit sends chunks
    # that fit the OLD limit (CHUNK_POINTS 40) and always sends both live
    # fields — so a 2.1.0 device never meets either fault from here.
    fw_min_framework: tuple = (2, 1, 0)
    fw_min_sketch: tuple = (2, 1, 0)
    fw_current_framework: tuple = (2, 3, 2)
    fw_current_sketch: tuple = (2, 3, 2)

    def has(self, capability):
        return capability in self.capabilities


# Capabilities that actions (libs/actions.py) refer to
CAPABILITIES = {
    'shock', 'vibe', 'beep', 'stretch', 'switch', 'lock', 'collar',
    'mode_pet', 'mode_v_cage', 'mode_sleep_dep', 'mode_remote',
    'mode_random', 'mode_timer', 'mode_statue',
    # Trainer (ToF): three modes + waveform routine + depth calibration
    'trainer_rep', 'trainer_end', 'trainer_free', 'trainer_routine', 'depth_cal',
    # TaskPad (buttons/LEDs/vibration): tasks as modes + confirmation button
    'task_nose', 'task_reaction', 'task_rhythm', 'task_memory', 'task_confirm',
    # Holding tasks of further devices (firmware to follow)
    'task_tray', 'task_silence', 'task_kneel',
    # E-stim bridge (doc 19): two channels of the Coyote, one electrode pair each
    'estim_a', 'estim_b', 'estim_routine',
}

# Speaking names of the capabilities for the display (web: device list, edit device).
# Per capability (short for the tile, detailed for the tooltip). Order here =
# order in the display.
CAP_LABELS = {
    'shock':            ('Stromimpuls', 'Einzelner Stromimpuls über das Halsband'),
    'vibe':             ('Vibration', 'Vibration ohne Stromimpuls'),
    'beep':             ('Ton', 'Signalton ohne Stromimpuls'),
    'collar':           ('Halsband-Einstellungen', 'Stärken für Impuls, Vibration und Ton setzen'),
    'lock':             ('Magnetschloss', 'Fesseln verriegeln und lösen'),
    'stretch':          ('Streckung', 'Schrittmotor des Stretcher and Shocker'),
    'switch':           ('Schalter', 'Relais/Schalter des Stretcher and Shocker'),
    'mode_pet':         ('Modus: Pet', 'Auf allen vieren bleiben — Aufstehen bestraft das Halsband selbst'),
    'mode_statue':      ('Modus: Statue', 'Eingelernte Haltung halten (Toleranzwinkel)'),
    'mode_sleep_dep':   ('Modus: Schlafentzug', 'Keine Bewegung über die Schwelle = Bestrafung'),
    'mode_v_cage':  ('Modus: V-Cage', 'Käfig ohne Gitter über die Funkfeldstärke'),
    'mode_random':      ('Modus: Zufall', 'Impuls in zufälligen Abständen'),
    'mode_timer':       ('Modus: Timer', 'Impuls in festem Takt'),
    'mode_remote':      ('Modus: Fernsteuerung', 'Kein eigener Modus, nur Einzelkommandos'),
    'trainer_rep':      ('Wiederholung', 'Blowjob-/Deepthroat-Trainer: geführte Stöße, jeder ein Stück tiefer'),
    'trainer_end':      ('Ausdauer', 'Blowjob-/Deepthroat-Trainer: eine Tiefe halten'),
    'trainer_free':     ('Freies Training', 'Blowjob-/Deepthroat-Trainer: freie Dauer, optional mit Takt'),
    'trainer_routine':  ('Routine', 'Blowjob-/Deepthroat-Trainer: eine Wellenform nachfahren'),
    'estim_a':          ('E-Stim Kanal A', 'Erstes Elektrodenpaar der Coyote'),
    'estim_b':          ('E-Stim Kanal B', 'Zweites Elektrodenpaar der Coyote'),
    'estim_routine':    ('E-Stim: Wellenform', 'Eine Wellenform als Reiz, Belohnung oder Bestrafung abspielen'),
    'depth_cal':        ('Tiefe messen', 'Blowjob-/Deepthroat-Trainer: Ruheabstand und größte Tiefe kalibrieren'),
    'task_nose':        ('Nasenknopf', 'Taster mit der Nase gedrückt halten'),
    'task_reaction':    ('Reaktion', 'Auf die aufleuchtende LED den richtigen Taster drücken'),
    'task_rhythm':      ('Takt', 'Im vorgegebenen Takt drücken'),
    'task_memory':      ('Merkfolge', 'LED-Folge nachdrücken, jede Runde eine länger'),
    'task_confirm':     ('Bestätigungstaster', 'Antwort auf das Aufmerksamkeitssignal des Wächters'),
    'task_tray':        ('Tablett', 'Tablett ruhig halten (Firmware folgt)'),
    'task_silence':     ('Schweigen', 'Kein Laut über der Schwelle (Firmware folgt)'),
    'task_kneel':       ('Kniekissen', 'Auf beiden Knien bleiben (Firmware folgt)'),
}


def cap_label(capability):
    """(short, detailed) of a capability; unknown capabilities return the code."""
    pair = CAP_LABELS.get(capability)
    if pair is None:
        return (capability, i18n._('unbekannte Fähigkeit {c}', c=str(capability)))
    return (i18n._(pair[0]), i18n._(pair[1]))


def cap_list(capabilities):
    """Capabilities in display order: [(code, short, detailed)]."""
    caps = set(capabilities or ())
    out = [(c, *cap_label(c)) for c in CAP_LABELS if c in caps]
    out += [(c, *cap_label(c)) for c in sorted(caps - set(CAP_LABELS))]
    return out


# Devices WITH a stimulus source listen on the punishment channel (doc 14 3a);
# the central unit uses that only for the display ("who would punish") — the
# devices report their own kinds in the hello (punish_kinds).
PUNISHERS = {'collar_v1': ('shock', 'vibe', 'beep'),
             'coyote_bridge': ('estim',)}

MODELS = (
    DeviceModel(
        code='stretcher_shocker',
        uuid='eaa4cae0-65d6-4cf2-80ef-d8d0f8e8f6f0',
        name='Stretcher and Shocker',
        capabilities=frozenset({'shock', 'stretch'}),
        envelope={'shock_seconds_max': 10},
    ),
    DeviceModel(
        code='collar_v1',
        uuid='73903cef-049d-4439-a9ab-f05825e0ef25',
        name='Collar v1.0',
        capabilities=frozenset({
            'shock', 'vibe', 'beep', 'collar',
            # Fixed, autonomous modes (firmware Collar-3.0, decision 2026-09-06)
            'mode_pet', 'mode_v_cage', 'mode_sleep_dep', 'mode_remote',
            'mode_random', 'mode_timer',
            'mode_statue',            # Collar-3.2: hold a posture (doc 14)
        }),
        # The envelope lives in the collar (NVS): zap_max, tx_max_ms, pulse_gap_ms,
        # mode_max_min, cage_pun_max, pun_lvl1..3. Here for documentation only.
        envelope={'zap_max': 40, 'vibe_max': 99, 'beep_max': 99,
                  'tx_max_ms': 1000, 'pulse_gap_ms': 3000,
                  'mode_max_min': 60, 'cage_pun_max_s': 600,
                  'pun_lvl': (10, 20, 30)},
    ),
    DeviceModel(
        code='maglock_v1_2',
        uuid='1acf784c-4bfd-4a06-b4ff-ee578a37fac4',
        name='magLock v1.2',
        capabilities=frozenset({'lock'}),
        envelope={'lock_minutes_max': 240},
    ),
    DeviceModel(
        code='trainer_tof',
        uuid='df404a58-47b8-4cb1-963c-c957a1b8f700',
        name='Blowjob-/Deepthroat-Trainer (ToF)',
        # Firmware Trainer-3.0 on PunisherDevice: Repetition / Endurance / Freeform,
        # depth calibration. No stimulus source -> violations as fault, punishment
        # over the slave's channel.
        capabilities=frozenset({'trainer_rep', 'trainer_end', 'trainer_free', 'depth_cal'}),
        envelope={'trainer_max_min': 30},
    ),
    DeviceModel(
        code='trainer_tof2',
        uuid='c1f4e9b2-6a37-4d58-9b0e-2f7a5c81d340',
        name='Blowjob-/Deepthroat-Trainer 2 (ToF + Kamera)',
        # Project doc 17: ESP32-S3 N16R8 CAM. The laser is the only measurement, the
        # camera checks that a head is present and takes stills to the TF card, two
        # NeoPixel strips and the OLED give feedback. Routines live in an external
        # 24LC512 as a cache. No buzzer.
        capabilities=frozenset({'trainer_rep', 'trainer_end', 'trainer_free',
                                'trainer_routine', 'depth_cal'}),
        envelope={'trainer_max_min': 30},
    ),
    DeviceModel(
        code='coyote_bridge',
        uuid='7a3d9e54-1c8b-4f26-b0d3-5e9c71a4f882',
        name='E-Stim-Bridge (DG-LAB Coyote V2/V3)',
        # Project doc 19: an ESP32 as BLE central for ONE Coyote, speaking MQTT to
        # the central unit like any other device. The Coyote stores nothing and
        # wants a frame every 100 ms, so the BRIDGE is the player: it holds the
        # waveform in its EEPROM and streams from it. Which generation is attached
        # is reported in `hello`; the central always speaks in percent.
        #
        # The curve drives the per-frame INTENSITY only, never the strength: the
        # dial on the device and the wearer's own limit are the ceiling, the
        # waveform shapes below it (doc 19 §4.3).
        capabilities=frozenset({'estim_a', 'estim_b', 'estim_routine'}),
        envelope={'estim_event_max_s': 20, 'estim_max_pct': 100,
                  'estim_run_max_s': 1800, 'estim_day_max_s': 3600},
    ),
    DeviceModel(
        code='taskpad',
        uuid='5b1e2a7c-9d3f-4c61-8e2a-7f0d4b9a1c22',
        name='TaskPad',
        # Firmware TaskPad-1.0: 1-4 lit buttons, vibration motor, buzzer.
        capabilities=frozenset({'task_nose', 'task_reaction', 'task_rhythm', 'task_memory', 'task_confirm'}),
        envelope={'task_max_min': 60, 'vibe_max': 3},
    ),
    DeviceModel(
        code='holdsensor',
        # Placeholder without firmware: no floor, otherwise the central unit locks
        # out the first device that is ever built for it.
        fw_min_framework=None, fw_min_sketch=None,
        fw_current_framework=None, fw_current_sketch=None,
        uuid='c4a7d2e9-3b18-4f6a-9d05-2e8b7c1f6a30',
        name='Halte-Sensor (Tablett / Schweigen / Kniekissen)',
        # Placeholder for the three holding tasks; firmware and sensors open (doc 14 7.2).
        capabilities=frozenset({'task_tray', 'task_silence', 'task_kneel'}),
        envelope={'task_max_min': 60},
    ),
    DeviceModel(
        code='selftest',
        uuid='0f2b6c81-95d4-4a17-8e63-1c7fb0d2a944',
        name='SelfTest (Prüfchip, kann nichts)',
        # The sketch examples/SelfTest: it recomputes the hashes on the chip
        # itself, derives the UUID and announces itself — no more than that. NO
        # capabilities, and that is the point: a test chip must never pass as a
        # device in any program step.
        #
        # WHY THIS MODEL EXISTS (finding Philine 2026-09-14): the creds.h of the
        # SelfTest carried the model UUID of the Coyote bridge. The test chip
        # therefore stood in the device list as "E-Stim-Bridge" with three
        # e-stim capabilities, and "Create" would have produced an entry that
        # promises the installation a stimulus device where a chip without an
        # output sits. The firmware reported `caps=[]` — only, the program flow
        # looks at the MODEL, not at the report.
        capabilities=frozenset(),
        envelope={},
    ),
)

MODELS_BY_CODE = {m.code: m for m in MODELS}
MODELS_BY_UUID = {m.uuid: m for m in MODELS}

for _m in MODELS:
    _unknown = _m.capabilities - CAPABILITIES
    assert not _unknown, f'Modell {_m.code}: unbekannte Fähigkeiten {_unknown}'


# --------------------------------------------------------------------------- #
# Envelopes: what a device lets through AT MOST (doc 03 C). The values here
# mirror the ENV_ constants of the firmware — the device remains authoritative:
# it reports its own values in the `hello`, so the installation does not have
# to guess.
#
# (That possibility arrived with PunisherDevice 3.3.0, so out of the numbering
# BEFORE 2.0. With 2.0 the framework version jumped to a new series and is
# therefore NUMERICALLY SMALLER than the old one — a comparison against "3.3.0"
# would be the wrong way round today. Nothing is therefore compared against
# that number anywhere; all that counts is whether the device sends the values
# along or not.)
#
# What for: the action registry says what the INSTALLATION knows (SHOCK up to
# 60 s). A single device often lets less through (the collar 1 s) and caps
# silently or refuses. Without this table the supervisor sets a value that
# never arrives — and does not find out (finding Philine 2026-09-11).
ENVELOPE_KEYS = {
    'zap_max':           'Impulsstärke des Halsbands',
    'vibe_max':          'Vibrationsstärke',
    'beep_max':          'Tonstärke',
    'tx_max_ms':         'längste Sendedauer eines Impulses',
    'mode_max_min':      'längste Laufzeit eines Modus',
    'cage_pun_max_s':   'V-Cage: längste Bestrafung',
    'lock_minutes_max':  'längste Verriegelung',
    'trainer_max_min':   'längstes freies Training',
    'task_max_min':      'längste Pad-Aufgabe',
    'shock_seconds_max': 'längster Impuls',
    'estim_max_pct':     'höchste E-Stim-Intensität',
    'estim_day_max_s':   'E-Stim-Ausgabe je Tag',
    'estim_run_max_s':   'längster E-Stim-Lauf am Stück',
    'estim_event_max_s': 'längstes Kanal-Ereignis',
    'pulse_gap_ms':      'Mindestabstand zweier Impulse',
    'pun_lvl':           'Bestrafungskanal: Impuls je Stufe',
}

# Keys where LARGER is the stricter one. For all others less is the tighter
# limit — for a cool-down time between two pulses it is longer. Anyone looking
# for the sharpest limit across several devices has to take the maximum here
# and the minimum everywhere else (programcheck.strictest).
LARGER_IS_STRICTER = {'pulse_gap_ms'}


# --------------------------------------------------------------------------- #
# COMPONENTS — what a device can report as out of order (doc 42 point 4)
#
# A device does not tell the central unit what it CAN do; the model does. What
# a device may tell is what it cannot do TODAY: `degraded: ["cuff3"]` in the
# hello. Discovery as STATUS, never as promise — a device can only ever take
# capabilities away from itself, never add one (decision Philine 2026-09-16,
# after the SelfTest incident of 2026-09-14 in which a test chip claimed the
# bridge's capabilities).
#
# Per model: component id -> the capabilities that depend on it. A capability
# is lost only when EVERY component that carries it is out — a MagLock with
# three cuffs still locks. Whether three are enough is decided at the ACTION
# (MAGLOCK has a parameter `cuffs`), not here.
#
# `stuck:<component>` is not a degradation, it is a safety case: a cuff that
# holds without power is a person who cannot get out. That blocks the device
# for everything that closes, see torturedevice.
COMPONENTS = {
    'maglock_v1_2': {'cuff1': frozenset({'lock'}), 'cuff2': frozenset({'lock'}),
                     'cuff3': frozenset({'lock'}), 'cuff4': frozenset({'lock'})},
    'collar_v1':    {'imu': frozenset({'mode_pet', 'mode_statue', 'mode_sleep_dep'})},
    'trainer_tof':  {'tof': frozenset({'trainer_rep', 'trainer_end', 'trainer_free',
                                       'trainer_routine', 'depth_cal'})},
    'trainer_tof2': {'tof': frozenset({'trainer_rep', 'trainer_end', 'trainer_free',
                                       'trainer_routine', 'depth_cal'})},
    'coyote_bridge': {'ble': frozenset({'estim_a', 'estim_b', 'estim_routine'})},
}

# Components counted as a set — how many of them a step may require.
COUNTED = {'maglock_v1_2': ('cuff', 4)}


def degraded_of(hello):
    """The `degraded` list of a hello, cleaned: strings only, no duplicates.
    None when the firmware does not report at all (below 2.2.0)."""
    d = (hello or {}).get('degraded')
    if not isinstance(d, (list, tuple)):
        return None
    out = []
    for x in d:
        if isinstance(x, str) and x and x not in out:
            out.append(x[:32])
    return out


def stuck_of(degraded):
    """The safety cases among the degraded entries: `stuck:<component>`."""
    return [x.split(':', 1)[1] for x in (degraded or []) if x.startswith('stuck:')]


def effective_capabilities(model, reported=None, degraded=None):
    """What a device can do RIGHT NOW: the model's promise, narrowed.

    Narrowed twice, never widened:
      * by what the firmware reports — a capability the model does not know
        is refused (that is the SelfTest hole), one the firmware does not
        report is dropped (older sketch on this model);
      * by what the device reports as degraded — a capability is lost when
        every component carrying it is out.
    Returns (capabilities, refused) — `refused` is what the firmware claimed
    beyond its model, for the log.
    """
    if model is None:
        return set(reported or ()), set()
    caps = set(model.capabilities)
    refused = set()
    if reported:
        rep = set(reported)
        refused = rep - caps
        caps &= rep
    comp = COMPONENTS.get(model.code, {})
    if degraded and comp:
        out = set(x.split(':', 1)[1] if x.startswith('stuck:') else x for x in degraded)
        for cap in list(caps):
            carriers = [c for c, cc in comp.items() if cap in cc]
            if carriers and all(c in out for c in carriers):
                caps.discard(cap)
    return caps, refused


def available_count(model, degraded):
    """For a counted component set: how many are usable. None = not counted."""
    if model is None or model.code not in COUNTED:
        return None
    prefix, total = COUNTED[model.code]
    out = set(x.split(':', 1)[1] if x.startswith('stuck:') else x for x in (degraded or []))
    return total - sum(1 for c in out if c.startswith(prefix))


# --------------------------------------------------------------------------- #
# SETTINGS SCHEMA — the form comes from here (doc 42 point 5)
#
# Per model: what a device stores in NVS and reads with cfgInt()/cfgStr() at
# start. Type, bounds, unit, default, label — the web builds the card
# "device settings" from this and sends `config`. The schema lives HERE and
# not on the device, on purpose: a device that told the central unit its
# bounds could tell it `max: 100000` for a hold time. The bounds are the
# compiled ceilings of the sketches; NVS can only tighten below them, which is
# also what the sketches enforce with constrain().
#
# Field: (key, type, min, max, unit, default, label_de, help_de)
Setting = __import__('collections').namedtuple(
    'Setting', 'key type min max unit default label help')

_COLLAR_SETTINGS = (
    Setting('zap_max', int, 0, 40, '', 40, 'Impuls höchstens',
            'Stärkster Impuls, den dieses Halsband überhaupt abgibt (Skala 0..99, gebaut bis 40).'),
    Setting('vibe_max', int, 0, 99, '', 99, 'Vibration höchstens', ''),
    Setting('beep_max', int, 0, 99, '', 99, 'Ton höchstens', ''),
    Setting('tx_max_ms', int, 50, 1000, 'ms', 1000, 'Längster Impuls', ''),
    Setting('mode_max_min', int, 1, 60, 'min', 60, 'Längster Modus', ''),
    Setting('pulse_gap_ms', int, 3000, 600000, 'ms', 3000, 'Mindestabstand zweier Impulse',
            'Egal aus welcher Quelle. Verhindert, dass ein verkürzter Impuls durch einen schnellen zweiten nachgeholt wird.'),
)
SETTINGS = {
    'collar_v1': _COLLAR_SETTINGS,
    'maglock_v1_2': (
        Setting('lock_max_min', int, 1, 240, 'min', 240, 'Längste Haltezeit', ''),
    ),
    'trainer_tof': (Setting('trainer_max_min', int, 1, 30, 'min', 30, 'Längstes Training', ''),),
    'trainer_tof2': (Setting('trainer_max_min', int, 1, 30, 'min', 30, 'Längstes Training', ''),),
    'taskpad': (
        Setting('task_max_min', int, 1, 60, 'min', 60, 'Längste Aufgabe', ''),
        Setting('vibe_max', int, 0, 3, '', 3, 'Vibration höchstens', ''),
    ),
    'coyote_bridge': (
        Setting('estim_max_pct', int, 1, 100, '%', 100, 'Ausgabe höchstens',
                'Obergrenze jeder Intensität, in Prozent der Decke der Teilnehmerin.'),
        Setting('estim_day_max', int, 60, 3600, 's', 3600, 'Ausgabe je Tag höchstens', ''),
        Setting('estim_event_ms', int, 200, 20000, 'ms', 1200, 'Dauer eines Kanal-Ereignisses', ''),
        Setting('estim_lvl1', int, 1, 100, '%', 25, 'Stufe 1 (Gerätevorgabe)',
                'Rückfall, wenn die Teilnehmerin keine eigenen Stufen hat (Doc 31).'),
        Setting('estim_lvl2', int, 1, 100, '%', 45, 'Stufe 2 (Gerätevorgabe)', ''),
        Setting('estim_lvl3', int, 1, 100, '%', 70, 'Stufe 3 (Gerätevorgabe)', ''),
        Setting('coyote_mac', str, 0, 17, '', '', 'Feste Coyote (MAC)',
                'Leer = die erste Coyote, die antwortet. Gesetzt = nur diese.'),
    ),
}


def settings_of(model):
    """The settings schema of a model, or an empty tuple."""
    return SETTINGS.get(model.code, ()) if model else ()


def validate_settings(model, form):
    """Check submitted values against the schema.

    Returns (accepted: {key: str}, errors: [text]). Accepted values are strings
    — that is what the device stores. An empty value means "back to default"
    (the key is cleared on the device). Nothing outside the schema passes:
    an unknown key is not sent, not even to be refused by the device.
    """
    ok, errs = {}, []
    for st in settings_of(model):
        if st.key not in form:
            continue
        raw = (form.get(st.key) or '').strip()
        if raw == '':
            ok[st.key] = ''
            continue
        if st.type is int:
            try:
                v = int(raw)
            except ValueError:
                errs.append(f'{st.label}: keine Zahl')
                continue
            if v < st.min or v > st.max:
                errs.append(f'{st.label}: {v} liegt nicht in {st.min}..{st.max}')
                continue
            ok[st.key] = str(v)
        else:
            if len(raw) > st.max:
                errs.append(f'{st.label}: zu lang (höchstens {st.max})')
                continue
            ok[st.key] = raw
    return ok, errs


def envelope_of(model, reported=None):
    """The envelope of a device: what the model promises, overridden by what
    the running firmware reports in the `hello`.

    The firmware has the last word — it is the one that caps. The model is only
    the default for devices with older firmware that does not report anything yet.
    """
    out = dict((model.envelope or {}) if model else {})
    for k, v in (reported or {}).items():
        if k not in ENVELOPE_KEYS:
            continue
        # `True` is an int in Python. A device that reports a flag where a
        # number belongs must not silently become a limit of 1.
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[k] = int(v)
        elif isinstance(v, (list, tuple)) and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            out[k] = tuple(int(x) for x in v)
    return {k: v for k, v in out.items() if v is not None}


# What a limit looks like in the unit of its field. The key says in which unit
# the envelope counts, the parameter in which unit the form counts — in between
# it is converted, always rounded DOWNWARDS, so that the converted limit is
# never larger than the real one.
_UNIT_OF_KEY = {'_ms': 'ms', '_s': 's', '_min': 'min'}
_PER_UNIT = {'ms': 1, 's': 1000, 'min': 60000}      # in milliseconds


def _key_unit(key):
    for suffix, unit in _UNIT_OF_KEY.items():
        if key.endswith(suffix):
            return unit
    return ''


def limit_for(envelope, key, unit=''):
    """Upper limit of a parameter out of the envelope, in the unit of the
    parameter. Returns None when the envelope says nothing about it.

    The units of the two sides rarely agree: the collar counts its transmit
    duration in milliseconds, the field SHOCK.seconds in seconds; the pad
    counts its longest task in minutes, the field TRAY.target_s in seconds.
    Without conversion it would say 1000 seconds there where the device stops
    at one.
    """
    if not envelope or not key:
        return None
    # A field may name several keys, separated by spaces: the same field is
    # called `tx_max_ms` on the collar and `shock_seconds_max` on the
    # stretcher. The SHARPEST limit the device names applies — if it names
    # none, the registry applies.
    best = None
    for k in key.split():
        v = envelope.get(k)
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue    # e.g. `pun_lvl`: a graduated scale, not an upper limit
        src, dst = _key_unit(k), unit
        if src and dst and src != dst and dst in _PER_UNIT:
            v = max(1, int(float(v) * _PER_UNIT[src] // _PER_UNIT[dst]))
        v = int(v)
        best = v if best is None else min(best, v)
    return best


def by_uuid(uuid):
    return MODELS_BY_UUID.get(uuid)


def by_code(code):
    return MODELS_BY_CODE.get(code)
