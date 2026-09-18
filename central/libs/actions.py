# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Registry of all programme actions (tasks).

Principle (decided 2026-09-06): the catalogue lives exclusively in the code.
Handler, parameter schema, required device capability and safety class stand
here together. The database knows only the action code as a string
(program_commands.pc_command) and the parameters (pc_parameter).

Used by
  - the programme engine (libs/slaveprogram.py): validation + dispatch
  - the central unit at startup (check of all stored programmes)
  - later the web UI: form fields, selection by device capability

Parameter format in pc_parameter: '|'-separated in the order of
ActionDef.params (existing data stays valid). A switch to JSON is possible
later without a change to the registry (adapt parse_params).
"""

from dataclasses import dataclass

import i18n


@dataclass(frozen=True)
class Param:
    name: str
    type: type = int
    min: int = None
    max: int = None
    unit: str = ''
    description: str = ''        # whole sentence: what the value does (web editor shows it under the field)
    default: object = None       # set = parameter optional (only allowed at the end)
    label: str = ''              # speaking name for forms; empty = name
    # The value is the number of a record, not a free number. A form builds a
    # SELECTION LIST out of it instead of a number field — otherwise one copies
    # numbers down and guesses (Philine 2026-09-11). The value says at the same
    # time which records come into question, and the server checks exactly the
    # same restriction when saving:
    #   waveform_task    task on the time axis, scorable
    #   waveform_stim    stimulus or reward on the time axis, playable
    #   waveform_couple  coupling on the depth axis
    # 0 stays allowed everywhere and means "none" or "the central chooses".
    ref: str = ''
    # Which ENVELOPE of the device this value runs against. The registry says
    # what the installation knows in principle; a single device often lets
    # less through — a collar at most 40 instead of 99 pulse strength.
    # Without this mapping the supervisor sets a value, the device caps it
    # silently, and nobody learns of it (finding Philine 2026-09-11).
    # The keys stand in devicemodels.ENVELOPE_KEYS.
    limit: str = ''


# Reference kinds (see Param.ref). The catalogue stands here so that registry,
# web interface and REST API use the same names.
REF_WAVEFORM_TASK = 'waveform_task'
REF_WAVEFORM_STIM = 'waveform_stim'
REF_WAVEFORM_COUPLE = 'waveform_couple'


@dataclass(frozen=True)
class ActionDef:
    code: str                    # program_commands.pc_command
    name_de: str                 # source text German; .name returns the translated version
    desc_de: str                 # source text German; .description returns the translated version
    handler: str                 # method on `slave`; None = engine-internal only (WAIT)
    capability: str = None       # required device capability (libs/devicemodels.CAPABILITIES)
    params: tuple = ()
    physical: bool = False       # acts on the body -> consent + envelope (doc 03)
    implemented: bool = True
    # Wait time in seconds until the next step may run: f(params) -> int
    cooldown: object = None
    # Logbook (doc 14): trainable task -> run with grade/points. V-Cage, lock,
    # timer, random etc. are frames (trainable=False, no reward).
    trainable: bool = False
    # blocking: the programme waits for the result (result event) of the task,
    # at most timeout(params) seconds. Collar modes keep running in the
    # background (not blocking, end via REMOTE_CONTROL or maximum duration).
    blocking: bool = False
    timeout: object = None

    # Display texts run through i18n: German stands as source text up in the
    # code, translations in libs/lang_<code>.py. Missing one, German remains.
    @property
    def name(self):
        return i18n._(self.name_de)

    @property
    def description(self):
        return i18n._(self.desc_de)

    def next_delay(self, params):
        if self.cooldown is None:
            return 0
        return int(self.cooldown(params))

    def timeout_s(self, params):
        if self.timeout is None:
            return 0
        return int(self.timeout(params))


# Common optional parameter of trainable tasks (always as the last one):
# allowed punishments for the run still to count as "passed" (grade B).
def P_MAX_PUNISH():
    return Param('max_punish', int, 0, 50, '', label='Erlaubte Bestrafungen', default=-1,
                 description='So viele Bestrafungen darf der Durchgang haben und gilt trotzdem als '
                             'bestanden (Note B; 0 Bestrafungen = A). -1 = Vorgabe der Anlage '
                             '(Einstellung default_max_punish, Vorgabe 2).')


class ActionError(ValueError):
    pass


def param_label(p):
    """Speaking name of a parameter in the current language."""
    return i18n._(p.label or p.name)


def param_desc(p):
    """Description of a parameter in the current language."""
    return i18n._(p.description)


ACTIONS = (
    ActionDef(
        code='SHOCK', name_de='Stromimpuls', handler='shock', capability='shock', physical=True,
        desc_de='Ein einzelner Impuls über das Halsband. Erst läuft der Countdown (große Zahl '
                    'auf dem Display), dann sendet das Halsband für die angegebene Dauer. Stärke = '
                    'die aktuellen Halsband-Einstellungen (COLLAR_SETTINGS). Das Halsband kappt die '
                    'Dauer an seiner Hüllkurve tx_max_ms.',
        params=(Param('seconds', int, 1, 10, 's', label='Dauer', limit='tx_max_ms shock_seconds_max',
                      description='Wie lange der Impuls gesendet wird. Das Halsband kappt an seiner '
                                  'Hüllkurve tx_max_ms (Vorgabe 1 s) und lehnt längere Impulse ab.'),
                Param('countdown', int, 0, 600, 's', label='Countdown',
                      description='Vorlaufzeit bis zum Impuls, sichtbar als Zähler auf dem Display. '
                                  '0 = sofort.'),
                Param('warn', int, 0, 1, '', label='Vorwarnung', default=1,
                      description='1 = zu Beginn des Countdowns ein Warnsignal (Vibration + Ton, '
                                  '0,3 s), 0 = ohne Vorwarnung.')),
        cooldown=lambda p: p['seconds'] + p['countdown'] + 10,
    ),
    ActionDef(
        code='VIBE', name_de='Vibration', handler='vibe', capability='vibe', physical=True,
        desc_de='Nur Vibration am Halsband, kein Stromimpuls. Für Aufmerksamkeit oder Belohnung.',
        params=(Param('level', int, 0, 99, '', label='Stärke', limit='vibe_max',
                      description='Vibrationsstärke auf der Skala des Halsbands (0 = aus, 99 = maximal). '
                                  'Das Halsband kappt an vibe_max.'),
                Param('ms', int, 50, 5000, 'ms', label='Dauer', default=300,
                      description='Dauer in Millisekunden (300 = kurzer Stoß, 1000 = eine Sekunde).')),
    ),
    ActionDef(
        code='BEEP', name_de='Ton', handler='piep', capability='beep',
        desc_de='Nur ein Ton am Halsband, kein Stromimpuls. Als Signal oder Warnung.',
        params=(Param('level', int, 0, 99, '', label='Lautstärke', limit='beep_max',
                      description='Tonstärke auf der Skala des Halsbands (0 = aus, 99 = maximal).'),
                Param('ms', int, 50, 5000, 'ms', label='Dauer', default=300,
                      description='Dauer in Millisekunden.')),
    ),
    # --- Fixed, autonomous modes of the collar (decision 2026-09-06) -------
    # The collar decides and punishes by itself; the central unit only
    # switches the mode on/off and receives events. max_min is capped by the
    # collar to its envelope (mode_max_min). warn = warning signal before
    # every pulse. Mode off: REMOTE_CONTROL (mode 0) or STOP of the device.
    ActionDef(
        code='PET', name_de='Modus: Pet', handler='pet', capability='mode_pet', physical=True,
        desc_de='Der Sklave muss auf allen vieren bleiben. Ist er für dieses Halsband '
                    'kalibriert (Sklaven → Kalibrieren: Haltung "auf allen vieren" und "stehend"), '
                    'schickt die Zentrale beide Haltungen mit, und das Halsband erkennt Aufstehen '
                    'daran, welcher Haltung es näher ist — der Winkel unten spielt dann keine Rolle. '
                    'Ohne Kalibrierung lernt das Halsband nach dem Start einige Sekunden die Haltung '
                    'ein (Display zählt herunter, Ton = "jetzt gilt es") und nutzt den Winkel. '
                    'Aufstehen → Impuls, solange er steht alle repeat_s Sekunden wieder; zurück auf '
                    'alle viere → Ende. Der Modus läuft bis REMOTE_CONTROL oder Maximaldauer.',
        params=(Param('max_min', int, 0, 60, 'min', limit='mode_max_min', label='Maximaldauer', default=0,
                      description='Nach so vielen Minuten endet der Modus von selbst. '
                                  '0 = die im Halsband hinterlegte Obergrenze (mode_max_min, Vorgabe 60 min).'),
                Param('warn', int, 0, 1, '', label='Vorwarnung', default=1,
                      description='1 = vor jedem Impuls ein Warnsignal (Vibration + Ton), 1,5 s später '
                                  'der Impuls. 0 = Impuls ohne Vorwarnung.'),
                Param('angle', int, 15, 85, 'Grad', label='Aufsteh-Winkel', default=45,
                      description='Nur ohne Kalibrierung: ab dieser Neigung gegenüber der eingelernten '
                                  'Haltung gilt der Sklave als aufgerichtet. Auf allen vieren liegt das '
                                  'Halsband etwa waagerecht, im Stehen etwa senkrecht (≈ 90°). 45 ist ein '
                                  'guter Start; kleiner = strenger, größer = nur echtes Aufstehen.'),
                Param('repeat_s', int, 5, 300, 's', label='Wiederholung', default=15,
                      description='Solange der Sklave aufgerichtet bleibt, folgt alle so viele '
                                  'Sekunden ein weiterer Impuls.'),
                Param('cal_s', int, 0, 30, 's', label='Einlernzeit', default=5,
                      description='Nur ohne Kalibrierung: Sekunden nach dem Start, in denen der '
                                  'Sklaven die Haltung einnehmen soll; das Halsband merkt sie sich als '
                                  'Referenz. 0 = die Haltung im Moment des Starts gilt sofort.'),
                P_MAX_PUNISH()),
        trainable=True,
    ),
    ActionDef(
        code='STATUE', name_de='Modus: Statue', handler='statue', capability='mode_statue', physical=True,
        desc_de='Der Sklave verharrt in einer Haltung. Nach dem Start hat er cal_s Sekunden, '
                    'die Haltung einzunehmen (Ton = "jetzt gilt es"); danach misst das Halsband den '
                    'Winkel zur eingelernten Haltung. Weicht er mehr als die Toleranz ab, folgt nach '
                    'kurzer Karenz ein Impuls, danach alle repeat_s Sekunden, bis er zurück ist. '
                    'Trainierbare Aufgabe (Logbuch): Bestrafungen zählen, Dauer = Maximaldauer.',
        params=(Param('max_min', int, 1, 60, 'min', limit='mode_max_min', label='Dauer',
                      description='So viele Minuten muss die Haltung gehalten werden; danach endet der '
                                  'Modus von selbst. Das Halsband kappt an mode_max_min.'),
                Param('warn', int, 0, 1, '', label='Vorwarnung', default=1,
                      description='1 = vor jedem Impuls Vibration + Ton, 0 = ohne.'),
                Param('angle', int, 5, 60, 'Grad', label='Toleranz', default=20,
                      description='Erlaubte Abweichung von der eingelernten Haltung in Grad. 20 = '
                                  'deutliches Wackeln erlaubt, 10 = streng, 5 = fast unmöglich.'),
                Param('repeat_s', int, 5, 300, 's', label='Wiederholung', default=15,
                      description='Solange die Haltung verlassen bleibt, folgt alle so viele Sekunden '
                                  'ein weiterer Impuls.'),
                Param('cal_s', int, 0, 30, 's', label='Einnehmzeit', default=3,
                      description='Sekunden nach dem Start, um die Haltung einzunehmen; sie wird dann '
                                  'als Referenz gemerkt.'),
                P_MAX_PUNISH()),
        trainable=True,
    ),
    ActionDef(
        code='SLEEP_DEPRIVATION', name_de='Modus: Schlafentzug', handler='sleep_deprivation',
        capability='mode_sleep_dep', physical=True,
        desc_de='Der Sklave darf sich nicht zur Ruhe legen. Bewegt er sich für still_s '
                    'Sekunden gar nicht (Bewegungssensor im Halsband), gibt es einen Impuls und '
                    'danach alle repeat_s Sekunden wieder, bis er sich bewegt. Läuft bis '
                    'REMOTE_CONTROL oder Maximaldauer.',
        params=(Param('max_min', int, 0, 60, 'min', limit='mode_max_min', label='Maximaldauer', default=0,
                      description='Nach so vielen Minuten endet der Modus von selbst. '
                                  '0 = Obergrenze des Halsbands (mode_max_min, Vorgabe 60 min).'),
                Param('warn', int, 0, 1, '', label='Vorwarnung', default=1,
                      description='1 = vor jedem Impuls Vibration + Ton, 0 = ohne.'),
                Param('still_s', int, 10, 1800, 's', label='Ruhezeit bis Impuls', default=60,
                      description='So viele Sekunden ohne jede Bewegung lösen den ersten Impuls aus. '
                                  '60 = eine Minute Stillhalten wird bestraft.'),
                Param('repeat_s', int, 5, 600, 's', label='Wiederholung', default=30,
                      description='Bleibt der Sklave weiter still, folgt alle so viele Sekunden '
                                  'ein weiterer Impuls.'),
                P_MAX_PUNISH()),
        trainable=True,
    ),
    ActionDef(
        code='V_CAGE', name_de='Modus: V-Cage', handler='v_cage',
        capability='mode_v_cage', physical=True,
        desc_de='Der Sklave muss in Funkreichweite der Anlage bleiben. Wird das WLAN '
                    'schwächer als die Schwelle, warnt das Halsband IMMER zuerst (Vibration + Ton). '
                    'Kommt er nicht innerhalb von warn_s zurück, folgt ein Impuls, danach alle '
                    'repeat_s Sekunden — aber höchstens punish_max_s lang, dann hört das Halsband '
                    'von selbst auf zu bestrafen. Zurück in Reichweite setzt alles zurück.',
        params=(Param('max_min', int, 0, 60, 'min', limit='mode_max_min', label='Maximaldauer', default=0,
                      description='Nach so vielen Minuten endet der Modus von selbst. '
                                  '0 = Obergrenze des Halsbands (mode_max_min, Vorgabe 60 min).'),
                Param('rssi', int, -95, -40, 'dBm', label='Schwelle (Signalstärke)', default=-75,
                      description='Fällt die WLAN-Signalstärke unter diesen Wert, gilt der Sklave '
                                  'als außerhalb. -60 = nah am Access Point (kleiner Radius), '
                                  '-75 = mittlerer Radius, -85 = fast Reichweitenende (großer Radius).'),
                Param('warn_s', int, 2, 120, 's', label='Warnzeit', default=10,
                      description='Zeit zwischen Warnung und erstem Impuls — die Chance, zurückzukommen.'),
                Param('repeat_s', int, 5, 300, 's', label='Wiederholung', default=15,
                      description='Bleibt er außerhalb, folgt alle so viele Sekunden ein weiterer '
                                  'Impuls (jeweils mit erneuter Warnung).'),
                Param('punish_max_s', int, 10, 3600, 's', label='Bestrafung höchstens', default=600,
                      limit='cage_pun_max_s',
                      description='Nach so vielen Sekunden außerhalb hört das Halsband auf zu bestrafen '
                                  '(Ereignis cage_giveup). 600 = 10 Minuten. Das Halsband kappt an '
                                  'seiner Hüllkurve cage_pun_max.')),
    ),
    ActionDef(
        code='RANDOM', name_de='Modus: Zufall', handler='random_mode',
        capability='mode_random', physical=True,
        desc_de='Impulse in zufälligen Abständen — der Sklave weiß nie, wann der nächste '
                    'kommt. Läuft bis zur Anzahl, bis REMOTE_CONTROL oder Maximaldauer.',
        params=(Param('max_min', int, 0, 60, 'min', limit='mode_max_min', label='Maximaldauer', default=0,
                      description='Nach so vielen Minuten endet der Modus von selbst. '
                                  '0 = Obergrenze des Halsbands (mode_max_min, Vorgabe 60 min).'),
                Param('warn', int, 0, 1, '', label='Vorwarnung', default=1,
                      description='1 = vor jedem Impuls Vibration + Ton, 0 = ohne.'),
                Param('min_s', int, 5, 3600, 's', label='Kürzester Abstand', default=10,
                      description='Mindestens so viele Sekunden zwischen zwei Impulsen.'),
                Param('max_s', int, 5, 3600, 's', label='Längster Abstand', default=340,
                      description='Höchstens so viele Sekunden zwischen zwei Impulsen. Der Abstand '
                                  'wird jedes Mal neu zwischen min_s und max_s gewürfelt.'),
                Param('count', int, 0, 1000, '', label='Anzahl', default=0,
                      description='Nach so vielen Impulsen endet der Modus. 0 = keine Begrenzung, '
                                  'es gilt nur die Maximaldauer.')),
    ),
    ActionDef(
        code='TIMER', name_de='Modus: Timer', handler='timer_mode',
        capability='mode_timer', physical=True,
        desc_de='Impulse in festem Takt. Das Display zählt zum nächsten Impuls herunter. '
                    'Läuft bis zur Anzahl, bis REMOTE_CONTROL oder Maximaldauer.',
        params=(Param('max_min', int, 0, 60, 'min', limit='mode_max_min', label='Maximaldauer', default=0,
                      description='Nach so vielen Minuten endet der Modus von selbst. '
                                  '0 = Obergrenze des Halsbands (mode_max_min, Vorgabe 60 min).'),
                Param('warn', int, 0, 1, '', label='Vorwarnung', default=1,
                      description='1 = vor jedem Impuls Vibration + Ton, 0 = ohne.'),
                Param('interval_s', int, 5, 3600, 's', label='Takt', default=60,
                      description='Abstand zwischen zwei Impulsen in Sekunden (60 = jede Minute).'),
                Param('count', int, 0, 1000, '', label='Anzahl', default=0,
                      description='Nach so vielen Impulsen endet der Modus. 0 = keine Begrenzung, '
                                  'es gilt nur die Maximaldauer.')),
    ),
    ActionDef(
        code='REMOTE_CONTROL', name_de='Modus: aus / Fernsteuerung', handler='remote_control',
        capability='mode_remote',
        desc_de='Beendet den laufenden Halsband-Modus (Pet, Schlafentzug, V-Cage, Zufall, Timer). '
                    'Danach reagiert das Halsband nur noch auf Einzelkommandos wie SHOCK, VIBE, BEEP. '
                    'Gehört ans Ende jedes Modus-Abschnitts, sonst läuft der Modus bis zur Maximaldauer.',
    ),
    ActionDef(
        code='MAGLOCK', name_de='Magnetschloss', handler='maglock', capability='lock', physical=True,
        desc_de='Verriegelt die Fesseln am Andreaskreuz. Zuerst läuft der Countdown zum Anlegen '
                    '(Magnete sind bereits an); sobald alle bestückten Pötte den Puck melden, startet '
                    'die Haltezeit. Nach Ablauf lösen die Magnete von selbst. Nicht rechtzeitig '
                    'angelegt = Ereignis not_attached an die Zentrale (kein Impuls).',
        params=(Param('minutes', int, 1, 240, 'min', limit='lock_minutes_max', label='Haltezeit',
                      description='So viele Minuten hält das Schloss, gezählt ab dem Moment, in dem '
                                  'alle Fesseln sitzen. Das Schloss kappt an seiner Hüllkurve '
                                  'lock_max_min (Vorgabe 240 min).'),
                Param('countdown', int, 0, 600, 's', label='Zeit zum Anlegen', default=30,
                      description='So viele Sekunden hat der Sklave, um die Fesseln an die '
                                  'Magnete zu setzen (Display zählt herunter).'),
                # HOW MANY CUFFS THIS STEP NEEDS (doc 42 point 4). The lock reports
                # a cuff it cannot use as `degraded`; whether three are enough is
                # the step's decision, not the device's — "all four" for a cross,
                # "two suffice" for the wrists (decision Philine 2026-09-16).
                Param('cuffs', int, 1, 4, '', label='Fesseln nötig', default=4,
                      description='So viele Fesseln muss das Schloss nutzen können. Meldet es '
                                  'weniger (Fessel abgemeldet), wird der Schritt an diesem Gerät '
                                  'nicht ausgeführt und die Programmprüfung sagt es vorher.')),
    ),
    ActionDef(
        code='UNLOCK', name_de='Magnetschloss lösen', handler='unlock', capability='lock',
        desc_de='Löst das Magnetschloss sofort, auch vor Ablauf der Haltezeit.',
    ),
    ActionDef(
        code='COLLAR_SETTINGS', name_de='Halsband-Einstellungen', handler='collar_settings',
        capability='collar', physical=True,
        desc_de='Setzt die Stärken, mit denen das Halsband ab jetzt arbeitet — für SHOCK und für '
                    'alle Modi. Bleibt im Halsband gespeichert, auch über einen Neustart. Das Halsband '
                    'kappt an seiner Hüllkurve (zap_max, vibe_max, beep_max, tx_max_ms).',
        params=(Param('shock', int, 0, 99, '', limit='zap_max', label='Impulsstärke',
                      description='Stärke des Stromimpulses auf der Skala des Halsbands (0–99). '
                                  'Vorgabe der Anlage 10; das Halsband lässt höchstens zap_max zu (Vorgabe 40).'),
                Param('vibe', int, 0, 99, '', label='Vibrationsstärke', limit='vibe_max',
                      description='Stärke der Vibration (0–99), auch für die Vorwarnung. Vorgabe 25.'),
                Param('beep', int, 0, 99, '', label='Tonstärke', limit='beep_max',
                      description='Lautstärke des Tons (0–99), auch für die Vorwarnung. Vorgabe 20.'),
                Param('duration', int, 50, 5000, 'ms', limit='tx_max_ms', label='Impulsdauer',
                      description='Sendedauer eines Impulses in Millisekunden, die in den Modi gilt '
                                  '(250 = eine Viertelsekunde). Vorgabe 250, Obergrenze tx_max_ms.')),
    ),
    # --- Trainer (ToF distance sensor), firmware Trainer-3.x ----------------
    # Depths relative to the calibration of the slave (posture 'depth' in
    # slave_calibration: resting distance and greatest depth in mm). The
    # central unit converts percent into millimetres; without a calibration
    # the trainer takes its own defaults (rest 200 mm, depth 60 mm).
    ActionDef(
        code='TRAINER_REPETITION', name_de='Blowjob-/Deepthroat-Trainer: Wiederholung', handler='trainer_repetition',
        capability='trainer_rep', physical=True,
        desc_de='Geführtes Training: eine vorgegebene Zahl Stöße, jeder ein Stück tiefer. Der '
                    'Trainer zeigt das Ziel an; wird die Zieltiefe eines Stoßes nicht erreicht oder '
                    'die Zeit je Stoß überschritten, zählt ein Fehlstoß (Verstoß -> Bestrafung über '
                    'den Bestrafungskanal, z. B. Halsband). Ende nach der Anzahl oder bei max_miss '
                    'Fehlstößen. Note aus Treffern und Bestrafungen.',
        params=(Param('count', int, 1, 200, '', label='Anzahl Stöße',
                      description='So viele Stöße umfasst der Durchgang.'),
                Param('depth_start', int, 10, 100, '%', label='Starttiefe', default=40,
                      description='Zieltiefe des ersten Stoßes in Prozent der kalibrierten größten '
                                  'Tiefe (100 % = so tief wie bei der Kalibrierung).'),
                Param('depth_end', int, 10, 100, '%', label='Endtiefe', default=90,
                      description='Zieltiefe des letzten Stoßes in Prozent; dazwischen steigt das Ziel '
                                  'gleichmäßig.'),
                Param('stroke_s', int, 2, 60, 's', label='Zeit je Stoß', default=8,
                      description='Innerhalb so vieler Sekunden muss der nächste Stoß erfolgen, sonst '
                                  'zählt ein Fehlstoß.'),
                Param('max_miss', int, 0, 50, '', label='Abbruch nach Fehlstößen', default=0,
                      description='Nach so vielen Fehlstößen endet der Durchgang als nicht bestanden. '
                                  '0 = kein Abbruch, alle Stöße werden ausgeführt.'),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: p['count'] * p['stroke_s'] + 60,
    ),
    ActionDef(
        code='TRAINER_ENDURANCE', name_de='Blowjob-/Deepthroat-Trainer: Ausdauer', handler='trainer_endurance',
        capability='trainer_end', physical=True,
        desc_de='Eine Tiefe halten. Sobald die Zieltiefe erreicht ist, läuft die Haltezeit; wird '
                    'vorher losgelassen, zählt ein Verstoß (Bestrafung) und die Zeit beginnt neu. '
                    'Erreicht die Haltezeit das Ziel, ist der Durchgang bestanden. Bestzeit wird '
                    'geführt (persönlicher Rekord, Bonus).',
        params=(Param('depth', int, 10, 100, '%', label='Tiefe', default=70,
                      description='Zu haltende Tiefe in Prozent der kalibrierten größten Tiefe.'),
                Param('hold_s', int, 3, 600, 's', label='Haltezeit',
                      description='So viele Sekunden muss die Tiefe ohne Unterbrechung gehalten werden.'),
                Param('max_s', int, 30, 3600, 's', limit='trainer_max_min', label='Zeit insgesamt', default=300,
                      description='Nach so vielen Sekunden endet der Durchgang, auch ohne Erfolg '
                                  '(Note nach längster gehaltener Zeit).'),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: p['max_s'] + 30,
    ),
    ActionDef(
        code='TRAINER_FREEFORM', name_de='Blowjob-/Deepthroat-Trainer: frei', handler='trainer_freeform',
        capability='trainer_free', physical=True,
        desc_de='Freies Training über eine Dauer, ohne Vorgabe der Tiefe. Der Trainer zählt Stöße '
                    'und misst Tiefe; optional gibt ein Takt (Schläge pro Minute) den Rhythmus vor, '
                    'dann zählt die Abweichung vom Takt. Keine Verstöße außer Untätigkeit.',
        params=(Param('minutes', int, 1, 30, 'min', label='Dauer', limit='trainer_max_min',
                      description='Dauer des freien Trainings in Minuten.'),
                Param('bpm', int, 0, 120, '/min', label='Takt', default=0,
                      description='Vorgegebener Takt in Stößen pro Minute (der Trainer blinkt/piept im '
                                  'Takt). 0 = kein Takt, nur zählen.'),
                Param('idle_s', int, 5, 300, 's', label='Untätig ab', default=30,
                      description='So viele Sekunden ohne Stoß gelten als Untätigkeit (Verstoß).'),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: p['minutes'] * 60 + 30,
    ),
    # Waveform routine (project doc 17). The routine itself lives in the database
    # (table `routines`); this step only names it. `routine` 0 means the central
    # picks one for the participant's task level — the level SELECTS the waveform
    # instead of scaling a target.
    ActionDef(
        code='TRAINER_ROUTINE', name_de='Blowjob-/Deepthroat-Trainer: Routine', handler='trainer_routine',
        capability='trainer_routine', physical=True,
        desc_de='Eine Wellenform nachfahren: die Zentrale gibt über die Zeit eine Zieltiefe mit '
                'Toleranz vor, der Trainer bewertet jede Abtastung. Die Kurve wird unter '
                '„Routinen" gezeichnet und ist dieser Aufgabe über ihre Stufe zugeordnet — '
                'Stufe 5 heißt: die Wellenform der Stufe 5. Abweichung außerhalb der Toleranz '
                'gibt nach der Auslöseschwelle eine Bestrafung über den Kanal; weggehen gilt als '
                'Pause und kostet nichts. Ergebnis ist ein Score von 0 bis 10000.',
        params=(Param('routine', int, 0, 100000, '', label='Routine', default=0,
                      ref=REF_WAVEFORM_TASK,
                      description='Nummer der Wellenform. 0 = die Zentrale wählt die Wellenform, die '
                                  'zur Aufgabenstufe des Sklaven passt (empfohlen).'),
                Param('repeats', int, 1, 20, '', label='Wiederholungen', default=1,
                      description='So oft läuft die Wellenform hintereinander. Zwischen zwei Durchläufen '
                                  'interpoliert das Gerät einen Übergang.'),
                P_MAX_PUNISH(),
                # NEW PARAMETERS GO LAST: steps are stored positionally ("0|1|2"),
                # so inserting in the middle would silently reinterpret max_punish.
                Param('kopplung', int, 0, 100000, '', label='Kopplung', default=0,
                      ref=REF_WAVEFORM_COUPLE,
                      description='Nummer einer Wellenform auf der TIEFENACHSE, die währenddessen mitläuft: '
                                  'sie gibt vor, wie Vibration und E-Stim auf die gemessene Tiefe reagieren '
                                  '(zum Beispiel unangenehm, solange nicht geschluckt ist, und stimulierend, '
                                  'sobald geschluckt ist). 0 = keine Kopplung.')),
        trainable=True, blocking=True,
        # The device reports the result; allow the whole routine plus a margin.
        timeout=lambda p: 60 + 1800 * max(1, int(p.get('repeats') or 1)),
    ),
    # A waveform as a programme of its own (project doc 19): stimulation, reward or
    # a shaped punishment, without a trainer. Not scored - there is no target to
    # miss - so it is a frame, not a task (trainable=False).
    ActionDef(
        code='ESTIM_ROUTINE', name_de='E-Stim: Wellenform abspielen', handler='estim_routine',
        capability='estim_routine', physical=True,
        desc_de='Spielt eine Wellenform über die E-Stim-Bridge: die Kurve stellt die Intensität, '
                'den Rhythmus gibt das Profil vor. Wie stark das höchstens werden darf, steht am '
                'Gerät selbst — der Regler und die dort eingestellte Obergrenze sind die Decke, die '
                'Wellenform formt nur darunter. Wird nicht bewertet. Ohne neuen Rahmen hört die '
                'Ausgabe nach einer Zehntelsekunde von selbst auf.',
        params=(Param('routine', int, 1, 100000, '', label='Wellenform',
                      ref=REF_WAVEFORM_STIM,
                      description='Nummer der Wellenform. Sie muss auf der Zeitachse liegen und den '
                                  'Zweck „Reiz" oder „Belohnung" haben.'),
                Param('repeats', int, 1, 20, '', label='Wiederholungen', default=1,
                      description='So oft läuft die Wellenform hintereinander.'),
                Param('max_pct', int, 1, 100, '%', label='Höchstens', default=100, limit='estim_max_pct',
                      description='Deckelt alle Spuren dieser Wellenform zusätzlich — in Prozent dessen, '
                                  'was am Gerät ohnehin schon erlaubt ist.')),
        trainable=False, blocking=False,
        # The bridge plays on its own; the programme waits for the waveform to run
        # out before the next step, like any other timed frame.
        cooldown=lambda p: 5 + 0,
    ),
    ActionDef(
        code='TRAINER_CALIBRATE', name_de='Blowjob-/Deepthroat-Trainer: Tiefe messen', handler='trainer_calibrate',
        capability='depth_cal',
        desc_de='Kalibrierung: der Trainer misst einige Sekunden den Ruheabstand und die größte '
                    'erreichte Tiefe und meldet sie (Ereignis depth_captured). Die Zentrale speichert '
                    'sie als Referenz des Sklaven für diesen Trainer. Normalerweise über das '
                    'Web (Sklaven -> Kalibrieren), hier als Programmschritt.',
        params=(Param('seconds', int, 3, 60, 's', label='Messdauer', default=15,
                      description='So lange wird gemessen; in dieser Zeit so tief wie möglich.'),),
        cooldown=lambda p: p['seconds'] + 5,
    ),
    # --- TaskPad (buttons + LEDs + vibration motor), firmware TaskPad-1.x ------
    # The pad has no stimulator: it reports violations as a fault event, the
    # central unit publishes the punishment on the channel of the slave.
    ActionDef(
        code='NOSE_BUTTON', name_de='Nasenknopf', handler='nose_button', capability='task_nose',
        desc_de='Einen Taster mit der Nase gedrückt halten, bis die Zielzeit erreicht ist. Kurzes '
                    'Wackeln unter der Toleranz ist eine Warnung (Ton/Vibration); fällt der Knopf '
                    'länger ab, ist der Durchgang verloren und es folgt eine Bestrafung über den '
                    'Kanal. Erschwernis: der Vibrationsmotor im Pad läuft während des Haltens. '
                    'Note aus gehaltener Zeit und Wacklern.',
        params=(Param('target_s', int, 5, 3600, 's', label='Zielzeit', limit='task_max_min',
                      description='So viele Sekunden muss der Knopf ununterbrochen gedrückt bleiben.'),
                Param('wobble_ms', int, 50, 2000, 'ms', label='Toleranz Wackler', default=300,
                      description='So lange darf der Knopf zwischendurch loslassen, ohne dass der '
                                  'Durchgang verloren ist (zählt als Wackler).'),
                Param('vibe', int, 0, 3, '', label='Vibration', default=1, limit='vibe_max',
                      description='Stärke des Vibrationsmotors während des Haltens (0 = aus, 3 = stark).'),
                Param('button', int, 0, 4, '', label='Taster', default=1,
                      description='Welcher Taster gedrückt werden muss (LED leuchtet). 0 = beliebiger.'),
                Param('start_s', int, 3, 120, 's', label='Zeit zum Drücken', default=15,
                      description='So viele Sekunden nach dem Start muss der Knopf erstmals gedrückt '
                                  'sein, sonst gilt der Durchgang als verloren.'),
                P_MAX_PUNISH()),
        # Deadline of the central unit >= maximum duration in the pad (start_s + target_s + max(15, target_s/4)) + reserve
        trainable=True, blocking=True, timeout=lambda p: p['target_s'] + p['start_s'] + max(45, p['target_s'] // 4 + 30),
    ),
    ActionDef(
        code='REACTION', name_de='Reaktion', handler='reaction', capability='task_reaction',
        desc_de='Eine LED leuchtet zufällig auf; der zugehörige Taster muss innerhalb der Frist '
                    'gedrückt werden. Verpasst oder falsch = Verstoß (Bestrafung über den Kanal). '
                    'Note aus Verpassten; die Reaktionszeit zählt nur als persönliche Bestzeit '
                    '(Rangliste misst Gehorsam, nicht Talent).',
        params=(Param('rounds', int, 1, 200, '', label='Runden',
                      description='So viele Signale werden gegeben.'),
                Param('deadline_ms', int, 200, 10000, 'ms', label='Frist', default=1500,
                      description='Innerhalb so vieler Millisekunden nach dem Aufleuchten muss gedrückt sein.'),
                Param('gap_min_s', int, 1, 60, 's', label='Pause mindestens', default=2,
                      description='Kürzester Abstand zwischen zwei Signalen.'),
                Param('gap_max_s', int, 1, 300, 's', label='Pause höchstens', default=8,
                      description='Längster Abstand zwischen zwei Signalen (zufällig dazwischen).'),
                Param('vibe', int, 0, 3, '', label='Ablenkung', default=0, limit='vibe_max',
                      description='Vibrationsmotor als Ablenkung während der Wartezeit (0 = aus).'),
                P_MAX_PUNISH()),
        # deadline >= pad: rounds * (gap_max + deadline + 1 s) + 10 s
        trainable=True, blocking=True, timeout=lambda p: p['rounds'] * (p['gap_max_s'] + p['deadline_ms'] // 1000 + 2) + 30,
    ),
    ActionDef(
        code='RHYTHM', name_de='Takt', handler='rhythm', capability='task_rhythm',
        desc_de='Im vorgegebenen Takt drücken: LED und Ton geben den Schlag, der Taster muss '
                    'innerhalb der Toleranz um den Schlag gedrückt werden. Abweichung = Warnung; '
                    'mehrere Aussetzer in Folge = Verstoß. Note aus getroffenen Schlägen.',
        params=(Param('bpm', int, 20, 180, '/min', label='Takt',
                      description='Schläge pro Minute.'),
                Param('beats', int, 4, 1000, '', label='Schläge',
                      description='So viele Schläge umfasst der Durchgang.'),
                Param('tol_ms', int, 50, 1000, 'ms', label='Toleranz', default=150,
                      description='Erlaubte Abweichung vom Schlag in Millisekunden (früher oder später).'),
                Param('fault_after', int, 1, 20, '', label='Verstoß nach Aussetzern', default=3,
                      description='So viele verpasste Schläge in Folge ergeben einen Verstoß.'),
                Param('button', int, 0, 4, '', label='Taster', default=1,
                      description='Welcher Taster den Takt schlägt. 0 = beliebiger.'),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: int(p['beats'] * 60 / p['bpm']) + 60,
    ),
    ActionDef(
        code='MEMORY', name_de='Merkfolge', handler='memory', capability='task_memory',
        desc_de='Eine Folge von LEDs leuchtet auf und muss nachgedrückt werden; jede Runde wird '
                    'sie um ein Signal länger. Falscher Taster = Verstoß und Ende. Note: Zielrunden '
                    'erreicht ja/nein; die erreichte Rundenzahl zählt als persönliche Bestleistung.',
        params=(Param('rounds', int, 1, 30, '', label='Zielrunden',
                      description='So viele Runden (Folgenlänge) müssen geschafft werden.'),
                Param('show_ms', int, 150, 2000, 'ms', label='Anzeigedauer', default=600,
                      description='So lange leuchtet jedes Signal der Folge.'),
                Param('vibe', int, 0, 3, '', label='Störreiz', default=0, limit='vibe_max',
                      description='Vibrationsmotor während der Anzeige der Folge (0 = aus).'),
                P_MAX_PUNISH()),
        # deadline >= pad: rounds * 40 s + 10 s (15 s per press possible)
        trainable=True, blocking=True, timeout=lambda p: p['rounds'] * 40 + 60,
    ),
    # --- Further holding tasks (firmware to follow, hardware open: doc 14 7.2) ----
    ActionDef(
        code='TRAY', name_de='Tablett', handler='hold_task', capability='task_tray',
        desc_de='Ein Tablett (Neigungssensor) oder ein Glas auf einer Wägezelle muss ruhig '
                    'gehalten werden. Kippen über die Toleranz = Warnung, Verschütten/Absetzen = '
                    'Verstoß. Firmware folgt; die Aktion ist bereits im Logbuch vorgesehen.',
        params=(Param('target_s', int, 10, 3600, 's', label='Dauer', limit='task_max_min'),
                Param('tolerance', int, 1, 45, 'Grad', label='Toleranz', default=10),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: p['target_s'] + 60,
    ),
    ActionDef(
        code='SILENCE', name_de='Schweigen', handler='hold_task', capability='task_silence',
        desc_de='Kein Laut über der Schwelle (Mikrofonpegel) für die Dauer. Überschreitung = '
                    'Verstoß. Firmware folgt.',
        params=(Param('target_s', int, 10, 3600, 's', label='Dauer', limit='task_max_min'),
                Param('tolerance', int, 1, 100, '%', label='Schwelle', default=40),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: p['target_s'] + 60,
    ),
    ActionDef(
        code='KNEEL', name_de='Kniekissen', handler='hold_task', capability='task_kneel',
        desc_de='Auf beiden Knien bleiben (Druckmatte): entlastet ein Knie länger als die '
                    'Toleranz, ist das ein Verstoß. Firmware folgt.',
        params=(Param('target_s', int, 10, 3600, 's', label='Dauer', limit='task_max_min'),
                Param('tolerance', int, 1, 60, 's', label='Toleranz', default=3),
                P_MAX_PUNISH()),
        trainable=True, blocking=True, timeout=lambda p: p['target_s'] + 60,
    ),
    # --- Frames: channel and attention -------------------------------------------
    ActionDef(
        code='PUNISH', name_de='Bestrafung (Kanal)', handler='channel_punish', physical=True,
        desc_de='Eine Bestrafung über den Bestrafungskanal des Sklaven: alle ihm zugeordneten '
                    'Reizgeber (heute das Halsband) führen sie in ihrer Stärkestufe aus. Zählt für '
                    'den gerade laufenden Durchgang als Bestrafung. Mindestpause und Tageslimit des '
                    'Kanals gelten.',
        params=(Param('level', int, 1, 3, '', label='Stärkestufe', default=1,
                      description='1 = leicht, 2 = mittel, 3 = stark — jedes Gerät bildet die Stufe auf '
                                  'seine eigene Hüllkurve ab (Halsband: pun_lvl1..3).'),
                Param('kind', str, None, None, '', label='Art', default='any',
                      description='any = jedes Gerät mit Reizgeber; shock, vibe, beep, strike = nur '
                                  'Geräte, die diese Art können.')),
    ),
    ActionDef(
        code='REWARD', name_de='Belohnung (Kanal)', handler='channel_reward',
        desc_de='Eine Belohnung über den Belohnungskanal (z. B. sanftes Vibrationsmuster am '
                    'Halsband, später Vibrator). Wird im Logbuch als Belohnung vermerkt.',
        params=(Param('level', int, 1, 3, '', label='Stärkestufe', default=1),
                Param('kind', str, None, None, '', label='Art', default='any')),
    ),
    ActionDef(
        code='ATTENTION_ON', name_de='Aufmerksamkeit an', handler='attention_on',
        desc_de='Wächter-Aufmerksamkeit: in zufälligen Abständen piept das Halsband (und das '
                    'TaskPad blinkt/vibriert); der Sklave muss innerhalb der Frist einen Taster '
                    'am TaskPad drücken. Verpasst = Bestrafung über den Kanal, gezählt für die gerade '
                    'laufende Aufgabe. Läuft bis ATTENTION_OFF oder Abmeldung.',
        params=(Param('min_s', int, 10, 3600, 's', label='Abstand mindestens', default=60),
                Param('max_s', int, 10, 7200, 's', label='Abstand höchstens', default=300),
                Param('window_s', int, 2, 60, 's', label='Frist', default=5,
                      description='So viele Sekunden nach dem Signal muss gedrückt sein.')),
    ),
    ActionDef(
        code='ATTENTION_OFF', name_de='Aufmerksamkeit aus', handler='attention_off',
        desc_de='Beendet die Wächter-Aufmerksamkeit.',
    ),
    ActionDef(
        code='INSTRUCTION', name_de='Anweisung (Pause)', handler='instruction',
        desc_de='Eine neutrale Anweisung an den Sklaven, die als Pause zählt — zum Beispiel '
                    '„Du darfst jetzt etwas essen“. Der Text steht auf der Anzeige und dem LCD, der '
                    'Block läuft die angegebene Dauer und wird nicht bewertet: keine Note, keine '
                    'Punkte, keine Bestrafung. Eine Bestätigung ist nicht nötig (nicht jede Anlage '
                    'hat Taster); die Verantwortung liegt beim Sklaven. Im Tagesplan ist das die '
                    'Blockart „Pause“.',
        params=(Param('minutes', int, 1, 240, 'min', label='Dauer',
                      description='So lange steht die Anweisung und so lange zählt die Pause.'),
                Param('text', str, None, None, '', label='Anweisung', default='Pause.',
                      description='Der angezeigte Satz. Ohne senkrechten Strich (|), der trennt die '
                                  'Parameter in der Datenbank.')),
        cooldown=lambda p: p['minutes'] * 60,
    ),
    ActionDef(
        code='WAIT', name_de='Warten', handler=None,
        desc_de='Pause im Programm. Der nächste Schritt startet erst nach Ablauf. Laufende '
                    'Halsband-Modi und ein verriegeltes Schloss laufen währenddessen weiter.',
        params=(Param('minutes', int, 0, None, 'min', label='Dauer',
                      description='Wartezeit in Minuten.'),),
        cooldown=lambda p: p['minutes'] * 60,
    ),
    ActionDef(
        code='WAITEVENT', name_de='Auf Ereignis warten', handler=None, implemented=False,
        desc_de='OFFEN (Review B6): Welches Ereignis, aus welchem Topic?',
    ),
)

ACTIONS_BY_CODE = {a.code: a for a in ACTIONS}


def get(code):
    return ACTIONS_BY_CODE.get(code)


def parse_params(action, raw):
    """Check a '|'-separated parameter string against the schema of the action.

    Returns dict name -> value or raises ActionError with a readable reason.
    """
    raw = (raw or '').strip()
    values = raw.split('|') if raw else []
    required = sum(1 for p in action.params if p.default is None)
    if len(values) < required or len(values) > len(action.params):
        raise ActionError(
            f'{action.code}: erwartet {required}..{len(action.params)} Parameter '
            f'({", ".join(p.name for p in action.params)}), bekommen {len(values)}: {raw!r}')

    result = {}
    for idx, p in enumerate(action.params):
        if idx >= len(values):
            result[p.name] = p.default          # optional parameter, the default applies
            continue
        v = values[idx]
        try:
            val = p.type(v.strip())
        except (TypeError, ValueError):
            raise ActionError(f'{action.code}: Parameter {p.name}={v!r} ist kein {p.type.__name__}')
        if p.min is not None and val < p.min:
            raise ActionError(f'{action.code}: {p.name}={val} unter Minimum {p.min}')
        if p.max is not None and val > p.max:
            raise ActionError(f'{action.code}: {p.name}={val} über Maximum {p.max}')
        result[p.name] = val
    return result


def parse_dict(action, values):
    """Check parameters from a dict (REST API / app) against the schema.

    Missing optional parameters get their default; missing mandatory parameters,
    wrong types and range violations raise ActionError. Returns dict name -> value.
    """
    values = values or {}
    result = {}
    for p in action.params:
        if p.name not in values or values[p.name] in (None, ''):
            if p.default is None:
                raise ActionError(f'{action.code}: Parameter {p.name} fehlt')
            result[p.name] = p.default
            continue
        v = values[p.name]
        try:
            if isinstance(v, bool):
                v = int(v)
            val = p.type(v if not isinstance(v, str) else v.strip())
        except (TypeError, ValueError):
            raise ActionError(f'{action.code}: Parameter {p.name}={v!r} ist kein {p.type.__name__}')
        if p.min is not None and val < p.min:
            raise ActionError(f'{action.code}: {p.name}={val} unter Minimum {p.min}')
        if p.max is not None and val > p.max:
            raise ActionError(f'{action.code}: {p.name}={val} über Maximum {p.max}')
        result[p.name] = val
    return result


def to_raw(action, params):
    """dict -> '|' string for program_commands.pc_parameter (leave out optional defaults at the end)."""
    vals = [str(params[p.name]) for p in action.params]
    while vals and action.params[len(vals) - 1].default is not None and \
            vals[-1] == str(action.params[len(vals) - 1].default):
        vals.pop()
    return '|'.join(vals)


def schema():
    """Registry as a JSON-capable structure (web editor, app)."""
    out = []
    for a in ACTIONS:
        if not a.implemented:
            continue
        out.append({
            'code': a.code, 'name': a.name, 'description': a.description,
            'capability': a.capability, 'physical': a.physical,
            'trainable': a.trainable, 'blocking': a.blocking,
            'device_command': a.handler is not None,      # False: programme step only (WAIT)
            'params': [{'name': p.name, 'label': p.label or p.name, 'unit': p.unit,
                        'min': p.min, 'max': p.max, 'default': p.default,
                        'type': 'str' if p.type is str else 'int',
                        'required': p.default is None, 'description': p.description,
                        'ref': p.ref or None,
                        # Which envelope key of the DEVICE this value runs
                        # against. The registry max is what the plant knows;
                        # one device often passes less. Keys: devicemodels
                        # .ENVELOPE_KEYS, reported per device in `limits`.
                        'limit': p.limit or None}
                       for p in a.params],
        })
    return out


def validate_step(command, raw):
    """Check a stored programme step. Returns (action, params) or raises ActionError."""
    action = get(command)
    if action is None:
        raise ActionError(f'unbekannte Aktion {command!r}')
    if not action.implemented:
        raise ActionError(f'{action.code}: noch nicht implementiert')
    return action, parse_params(action, raw)


def validate_program(rows):
    """rows: iterable of dicts with pc_id, pc_command, pc_parameter.
    Returns a list of error texts (empty = valid)."""
    errors = []
    for row in rows:
        try:
            validate_step(row['pc_command'], row['pc_parameter'])
        except ActionError as e:
            errors.append(f'Schritt {row["pc_id"]}: {e}')
    return errors


def program_warnings(rows):
    """Hints that do not make a programme invalid but are almost certainly an oversight
    (Philine 2026-09-10, after a test run: "Restraint 120 minutes" opened after 300 ms).

    MAGLOCK is NOT blocking — the lock counts its holding time itself, so that collar
    modes can run in the meantime. An UNLOCK directly after it therefore releases at once,
    and a MAGLOCK as the last step ends the programme while the lock still holds.
    Both need a WAIT.

    Returns a list of dicts {pc_id, code, text}.
    """
    steps = [r for r in rows]
    out = []
    for i, row in enumerate(steps):
        code = row.get('pc_command')
        a = get(code)
        # Collar modes (pet, statue, schlafentzug, zaun, zufall, timer) are
        # not blocking either: if REMOTE_CONTROL or the next mode follows right
        # away, the mode was on for only a moment.
        if a and a.capability and a.capability.startswith('mode_') and a.capability != 'mode_remote':
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            na = get(nxt.get('pc_command')) if nxt else None
            if nxt is None:
                out.append({'pc_id': row.get('pc_id'), 'code': code,
                            'text': f'{a.name} ist der letzte Schritt: das Programm ist beendet, während der '
                                    'Modus noch läuft. Ein WAIT über die gewünschte Dauer und danach ein '
                                    'REMOTE_CONTROL gehören dahinter.'})
            elif na is not None and (na.code == 'REMOTE_CONTROL' or
                                     (na.capability or '').startswith('mode_')):
                out.append({'pc_id': row.get('pc_id'), 'code': code,
                            'text': f'{a.name} wird vom nächsten Schritt sofort wieder abgeschaltet — der '
                                    'Modus läuft nur einen Augenblick. Dazwischen gehört ein WAIT über die '
                                    'gewünschte Dauer.'})
        if code != 'MAGLOCK':
            continue
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        if nxt is None:
            out.append({'pc_id': row.get('pc_id'), 'code': code,
                        'text': 'MAGLOCK ist der letzte Schritt: das Programm ist beendet, während das '
                                'Schloss noch hält. Ein WAIT über die Haltezeit gehört dahinter (das '
                                'Schloss löst nach Ablauf ohnehin von selbst).'})
        elif nxt.get('pc_command') == 'UNLOCK':
            out.append({'pc_id': row.get('pc_id'), 'code': code,
                        'text': 'UNLOCK folgt unmittelbar auf MAGLOCK und löst deshalb sofort wieder — '
                                'MAGLOCK wartet nicht auf die Haltezeit. Dazwischen gehört ein WAIT '
                                '(oder das UNLOCK entfällt, dann löst das Schloss selbst).'})
    return out
