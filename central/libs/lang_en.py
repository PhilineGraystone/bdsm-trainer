# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""English translation catalogue.

The German source text is the key — see libs/i18n.py. A missing entry falls back
to German, so nothing ever breaks; it only stays untranslated.

Adding another language: copy this file to lang_<code>.py, translate the values,
and add the code to i18n.LANGS.

Sections
  1  actions (names)
  2  parameter labels
  3  device capabilities
  4  metrics, grades
  5  badges, privileges
  6  rule engine (triggers, conditions, effects)
  7  day model (block kinds, states)
  8  web interface (navigation, headings, buttons, messages)
"""

TEXTS = {

    # ----------------------------------------------------------------- 1. actions
    'Stromimpuls': 'Electric pulse',
    'Vibration': 'Vibration',
    'Ton': 'Beep',
    'Modus: Pet': 'Mode: pet',
    'Modus: Statue': 'Mode: statue',
    'Modus: Schlafentzug': 'Mode: sleep deprivation',
    'Modus: V-Cage': 'Mode: V-Cage',
    'Modus: Zufall': 'Mode: random',
    'Modus: Timer': 'Mode: timer',
    'Modus: aus / Fernsteuerung': 'Mode: off / remote control',
    'Modus: Fernsteuerung': 'Mode: remote control',
    'Magnetschloss': 'Magnetic lock',
    'Magnetschloss lösen': 'Release magnetic lock',
    'Halsband-Einstellungen': 'Collar settings',
    'Blowjob-/Deepthroat-Trainer: Wiederholung': 'Blowjob/deepthroat trainer: repetition',
    'Blowjob-/Deepthroat-Trainer: Ausdauer': 'Blowjob/deepthroat trainer: endurance',
    'Blowjob-/Deepthroat-Trainer: frei': 'Blowjob/deepthroat trainer: freeform',
    'Blowjob-/Deepthroat-Trainer: Tiefe messen': 'Blowjob/deepthroat trainer: measure depth',
    'Blowjob-/Deepthroat-Trainer: Routine': 'Blowjob/deepthroat trainer: routine',
    'Nasenknopf': 'Nose button',
    'Reaktion': 'Reaction',
    'Takt': 'Rhythm',
    'Merkfolge': 'Memory sequence',
    'Tablett': 'Tray',
    'Schweigen': 'Silence',
    'Kniekissen': 'Kneeling pad',
    'Bestrafung (Kanal)': 'Punishment (channel)',
    'Belohnung (Kanal)': 'Reward (channel)',
    'Aufmerksamkeit an': 'Attention on',
    'Aufmerksamkeit aus': 'Attention off',
    'Anweisung (Pause)': 'Instruction (break)',
    'Warten': 'Wait',
    'Auf Ereignis warten': 'Wait for event',

    # -------------------------------------------------------- 2. parameter labels
    'Abbruch nach Fehlstößen': 'Abort after missed strokes',
    'Ablenkung': 'Distraction',
    'Abstand höchstens': 'Longest gap',
    'Abstand mindestens': 'Shortest gap',
    'Anweisung': 'Instruction',
    'Anzahl': 'Count',
    'Anzahl Stöße': 'Number of strokes',
    'Anzeigedauer': 'Display time',
    'Art': 'Kind',
    'Aufsteh-Winkel': 'Standing-up angle',
    'Bestrafung höchstens': 'Punishment at most',
    'Countdown': 'Countdown',
    'Dauer': 'Duration',
    'Einlernzeit': 'Learn-in time',
    'Einnehmzeit': 'Time to take position',
    'Endtiefe': 'Final depth',
    'Erlaubte Bestrafungen': 'Allowed punishments',
    'Frist': 'Deadline',
    'Haltezeit': 'Hold time',
    'Impulsdauer': 'Pulse duration',
    'Impulsstärke': 'Pulse strength',
    'Kürzester Abstand': 'Shortest interval',
    'Längster Abstand': 'Longest interval',
    'Lautstärke': 'Volume',
    'Maximaldauer': 'Maximum duration',
    'Messdauer': 'Measuring time',
    'Pause höchstens': 'Break at most',
    'Pause mindestens': 'Break at least',
    'Ruhezeit bis Impuls': 'Stillness before pulse',
    'Runden': 'Rounds',
    'Schläge': 'Beats',
    'Schwelle': 'Threshold',
    'Schwelle (Signalstärke)': 'Threshold (signal strength)',
    'Starttiefe': 'Start depth',
    'Stärke': 'Strength',
    'Stärkestufe': 'Strength level',
    'Störreiz': 'Distraction stimulus',
    'Taster': 'Buttons',
    'Tiefe': 'Depth',
    'Toleranz': 'Tolerance',
    'Toleranz Wackler': 'Wobble tolerance',
    'Tonstärke': 'Beep strength',
    'Untätig ab': 'Idle after',
    'Verstoß nach Aussetzern': 'Fault after misses',
    'Vibrationsstärke': 'Vibration strength',
    'Vorwarnung': 'Advance warning',
    'Warnzeit': 'Warning time',
    'Wiederholung': 'Repeat interval',
    'Zeit insgesamt': 'Total time',
    'Zeit je Stoß': 'Time per stroke',
    'Zeit zum Anlegen': 'Time to attach',
    'Zeit zum Drücken': 'Time to press',
    'Zielrunden': 'Target rounds',
    'Zielzeit': 'Target time',
    'Wiederholungen': 'Repeats',

    # ---------------------------------------------------- 3. device capabilities
    'Einzelner Stromimpuls über das Halsband': 'A single electric pulse through the collar',
    'Vibration ohne Stromimpuls': 'Vibration without an electric pulse',
    'Signalton ohne Stromimpuls': 'Signal tone without an electric pulse',
    'Stärken für Impuls, Vibration und Ton setzen': 'Set strengths for pulse, vibration and tone',
    'Fesseln verriegeln und lösen': 'Lock and release restraints',
    'Streckung': 'Stretching',
    'Schrittmotor des Stretcher and Shocker': 'Stepper motor of the Stretcher and Shocker',
    'Schalter': 'Switch',
    'Relais/Schalter des Stretcher and Shocker': 'Relay/switch of the Stretcher and Shocker',
    'Auf allen vieren bleiben — Aufstehen bestraft das Halsband selbst':
        'Stay on all fours — the collar punishes standing up by itself',
    'Eingelernte Haltung halten (Toleranzwinkel)': 'Hold a learned posture (tolerance angle)',
    'Keine Bewegung über die Schwelle = Bestrafung': 'No movement above the threshold = punishment',
    'Käfig ohne Gitter über die Funkfeldstärke': 'A cage without bars, made from radio signal strength',
    'Impuls in zufälligen Abständen': 'Pulse at random intervals',
    'Impuls in festem Takt': 'Pulse at a fixed interval',
    'Kein eigener Modus, nur Einzelkommandos': 'No mode of its own, single commands only',
    'Blowjob-/Deepthroat-Trainer: geführte Stöße, jeder ein Stück tiefer':
        'Blowjob/deepthroat trainer: guided strokes, each one a little deeper',
    'Ausdauer': 'Endurance',
    'Blowjob-/Deepthroat-Trainer: eine Tiefe halten': 'Blowjob/deepthroat trainer: hold one depth',
    'Freies Training': 'Free training',
    'Blowjob-/Deepthroat-Trainer: freie Dauer, optional mit Takt':
        'Blowjob/deepthroat trainer: free duration, optionally with a rhythm',
    'Tiefe messen': 'Measure depth',
    'Routine': 'Routine',
    'Blowjob-/Deepthroat-Trainer: eine Wellenform nachfahren': 'Blowjob/deepthroat trainer: follow a waveform',
    'Blowjob-/Deepthroat-Trainer: Ruheabstand und größte Tiefe kalibrieren':
        'Blowjob/deepthroat trainer: calibrate resting distance and greatest depth',
    'Taster mit der Nase gedrückt halten': 'Hold a button down with the nose',
    'Auf die aufleuchtende LED den richtigen Taster drücken': 'Press the right button for the lit LED',
    'Im vorgegebenen Takt drücken': 'Press in the given rhythm',
    'LED-Folge nachdrücken, jede Runde eine länger': 'Repeat the LED sequence, one longer each round',
    'Bestätigungstaster': 'Acknowledge button',
    'Antwort auf das Aufmerksamkeitssignal des Wächters': 'Answer to the guard attention signal',
    'Tablett ruhig halten (Firmware folgt)': 'Hold a tray steady (firmware to come)',
    'Kein Laut über der Schwelle (Firmware folgt)': 'No sound above the threshold (firmware to come)',
    'Auf beiden Knien bleiben (Firmware folgt)': 'Stay on both knees (firmware to come)',

    # --------------------------------------------------------------- 4. metrics
    'Dauer (s)': 'duration (s)',
    'gehalten (s)': 'held (s)',
    'Bestrafungen': 'punishments',
    'Warnungen': 'warnings',
    'Verstöße': 'faults',
    'außerhalb (s)': 'out of range (s)',
    'Treffer': 'hits',
    'Fehler': 'misses',
    'tiefster Stoß (mm)': 'deepest stroke (mm)',
    'längstes Halten (s)': 'longest hold (s)',
    'Stöße': 'strokes',
    'Reaktion Ø (ms)': 'reaction avg (ms)',
    'Reaktion beste (ms)': 'reaction best (ms)',
    'Taktabweichung Ø (ms)': 'rhythm deviation avg (ms)',
    'Wackler': 'wobbles',
    'Taktabweichung (%)': 'rhythm deviation (%)',
    'im Ziel (%)': 'in zone (%)',
    'Abtastungen': 'ticks',
    'ungültige Abtastungen': 'invalid ticks',
    'Abweichung Ø (%)': 'deviation avg (%)',

    # ------------------------------------------------------ 5. badges, privileges
    'Erste A': 'First A',
    'Erster Durchgang mit Note A': 'First run graded A',
    'Zehn': 'Ten',
    '10 bestandene Durchgänge': '10 runs passed',
    'Fünfzig': 'Fifty',
    '50 bestandene Durchgänge': '50 runs passed',
    'Hundert': 'Hundred',
    '100 bestandene Durchgänge': '100 runs passed',
    'Zehn Stunden Pet': 'Ten hours of pet',
    '10 Stunden im Pet-Modus insgesamt': '10 hours in pet mode in total',
    'Pflichtbewusst': 'Dutiful',
    'Erster vollständig bestandener Wochenplan': 'First weekly plan completed in full',
    'Wochenbester': 'Best of the week',
    'Bestes Wochenergebnis in einer Aufgabe': 'Best weekly result in a task',
    'Standhaft': 'Steadfast',
    'Vier Wochenbewertungen in Folge ohne Abstieg': 'Four weekly reviews in a row without demotion',
    'Halbzeit': 'Halfway',
    'Rang 5 erreicht': 'Reached rank 5',
    'Vollendet': 'Complete',
    'Rang 10 erreicht': 'Reached rank 10',
    'Duellant': 'Duellist',
    'Eine Herausforderung gewonnen': 'Won a challenge',
    'Makellos': 'Flawless',
    'Eine Woche mit Training und ohne einzige Bestrafung': 'A week with training and not one punishment',
    'Ohne Fesseln': 'No restraints',
    'MAGLOCK-Schritte werden im Programm übersprungen': 'MAGLOCK steps are skipped in the program',
    'Immer Vorwarnung': 'Always warned',
    'Bestrafungen kommen stets mit Vorwarnung (Kanal warn=1)':
        'Punishments always come with an advance warning (channel warn=1)',
    'Freier Aufenthalt': 'Free time',
    'Kein freies Training am Ende des Tages — der Tag endet, wenn der Plan erfüllt ist':
        'No free training at the end of the day — the day ends once the plan is done',

    # -------------------------------------------------------------- 6. rule set
    'Herausforderung entschieden': 'Challenge decided',
    'Wochenbewertung': 'Weekly review',
    'Wochenplan vollständig': 'Weekly plan complete',
    'Wochenplan unvollständig': 'Weekly plan incomplete',
    'Strafregister-Schwelle erreicht': 'Punishment record threshold reached',
    'Durchgang bestanden': 'Run passed',
    'Durchgang nicht bestanden': 'Run failed',
    'Kapitulation (Tag vorzeitig beendet)': 'Capitulation (day ended early)',
    'Tag regulär beendet': 'Day finished normally',
    'immer': 'always',
    'Platz 1': 'Place 1',
    'Platz 2': 'Place 2',
    'Platz 3 oder schlechter': 'Place 3 or worse',
    'letzter Platz': 'last place',
    'nicht angetreten': 'did not enter',
    'Rang 3 oder niedriger': 'Rank 3 or lower',
    'Rang 8 oder höher': 'Rank 8 or higher',
    'Note A': 'Grade A',
    'Bestrafung über den Kanal': 'Punishment over the channel',
    'Stärkestufe 1..3': 'Strength level 1..3',
    'Belohnung über den Kanal': 'Reward over the channel',
    'Privileg erteilen': 'Grant privilege',
    'Schlüssel, optional :Wochen — z. B. free_stay:1': 'Key, optionally :weeks — e.g. free_stay:1',
    'Privileg entziehen': 'Revoke privilege',
    'Schlüssel': 'Key',
    'Nachsitz-Aufgabe in den Plan': 'Add a detention task to the plan',
    'leer = die Aufgabe des Anlasses': 'empty = the task of the trigger',
    'Tagesdauer ändern': 'Change day length',
    '+30 / -15 (relativ) oder 300 (absolut), in Minuten': '+30 / -15 (relative) or 300 (absolute), in minutes',
    'Punkte gutschreiben/abziehen': 'Add or deduct points',
    'z. B. 20 oder -10': 'e.g. 20 or -10',
    'Abzeichen verleihen': 'Award a badge',
    'Schlüssel aus der Abzeichenliste': 'Key from the badge list',

    # ------------------------------------------------------------- 7. day model
    'Wochenplan': 'Weekly plan',
    'Zeitbudget: die Zentrale arbeitet offene Planaufgaben ab':
        'Time budget: the central works through open plan tasks',
    'Programm': 'Program',
    'ein festes Programm läuft einmal durch': 'one fixed program runs once',
    'freies Training': 'free training',
    'Zeitbudget: die Zentrale wählt passende Aufgaben, halbe Gewichtung':
        'Time budget: the central picks suitable tasks, at half weight',
    'Pause / Anweisung': 'Break / instruction',
    'neutrale Anweisung, zählt als Pause': 'a neutral instruction, counts as a break',
    # Task decisions per day plan (doc 58 §1–3). "block_in" and "block_out" are
    # opposites and both are needed: sleep deprivation only at night is the one,
    # "no action X after 22:00" the other.
    'erlaubt': 'allowed',
    'Die Zentrale darf die Aufgabe von sich aus wählen.':
        'The central unit may pick the task by itself.',
    'gesperrt, immer': 'blocked, always',
    'Die Zentrale wählt sie nie von selbst. Die Aufsicht kann sie weiterhin starten.':
        'The central unit never picks it by itself. The supervisor can still start it.',
    'gesperrt, nur zwischen': 'blocked, only between',
    'Innerhalb des Zeitfensters gesperrt, sonst erlaubt — für Ruhezeiten.':
        'Blocked inside the time window, allowed otherwise — for quiet hours.',
    'gesperrt, außer zwischen': 'blocked, except between',
    'Außerhalb des Zeitfensters gesperrt — für Aufgaben, die nur zu einer Tageszeit Sinn ergeben.':
        'Blocked outside the time window — for tasks that only make sense at one time of day.',
    'über Mitternacht': 'over midnight',
    # The editor of those decisions (doc 58 §5)
    'Welche Aufgaben dieser Tagesplan zulässt': 'Which tasks this day plan permits',
    'zurück zu den Tagesplänen': 'back to the day plans',
    'Angekreuzt wird, was die Zentrale <b>nicht von selbst</b> wählen soll. Das betrifft das freie Training '
    'und den Mystery-Zug — die beiden Stellen, an denen die Zentrale selbst greift. Der Wochenplan bleibt '
    'unberührt, dort hat ein Mensch zugeordnet, und die Aufsicht kann jede Aufgabe weiterhin von Hand starten.':
        'Tick what the central unit must <b>not pick by itself</b>. That concerns free training and the mystery '
        'draw — the two places where the central unit reaches in on its own. The weekly plan stays untouched, a '
        'human assigned it there, and the supervisor can still start any task by hand.',
    'Alles auf dieser Seite kann den Tag nur <b>kleiner</b> machen; Decke, Auflagen und '
    '<span class="mono">config.ini [safety]</span> stehen unverändert darüber. Eine Aufgabe ohne Kreuz ist '
    'erlaubt — und weil beim Speichern über jede Aufgabe entschieden wird, erscheint eine, die später neu in '
    'den Katalog kommt, als <span class="pill act">neu</span>.':
        'Everything on this page can only make the day <b>smaller</b>; the ceiling, the sanctions and '
        '<span class="mono">config.ini [safety]</span> stand above it unchanged. A task without a tick is '
        'allowed — and because saving decides about every task, one that enters the catalogue later shows up '
        'as <span class="pill act">new</span>.',
    'Beim Zeitfenster zählt der <b>ganze Durchgang</b>: eine Aufgabe, die um 21:55 anfinge und 40 Minuten '
    'dauert, endete um 22:35 — sie kommt dann nicht dran. „von“ später als „bis“ heißt über Mitternacht.':
        'For the time window the <b>whole run</b> counts: a task starting at 21:55 that takes 40 minutes would '
        'end at 22:35 — so it does not come up. A "from" later than the "to" means over midnight.',
    'Diese Aufgabe kam in den Katalog, nachdem hier zuletzt entschieden wurde.':
        'This task entered the catalogue after the last decision was made here.',
    'neu': 'new',
    'Wie gesperrt': 'How blocked',
    'Ziehen setzt das Fenster; die Uhrzeiten daneben bleiben änderbar.':
        'Dragging sets the window; the times next to it stay editable.',
    'Entscheidungen speichern': 'Save decisions',
    'Gespeichert wird über alle Aufgaben — auch über die ohne Kreuz.':
        'Saving covers every task — the unticked ones too.',
    '„{task}“: das Zeitfenster fehlt oder ist leer — von und bis müssen verschiedene Uhrzeiten sein.':
        '"{task}": the time window is missing or empty — from and to have to be different times.',
    'Entscheidungen gespeichert — {n} von {all} Aufgaben gesperrt.':
        'Decisions saved — {n} of {all} tasks blocked.',
    'gesperrt': 'blocked',
    # The mystery pool as a picker instead of a typed list (doc 58 §6)
    'Mystery-Pool': 'Mystery pool',
    'Block': 'Block',
    'Angekreuzt wird, was in diesem Block <b>gezogen werden darf</b>. Die Zentrale wählt darin Zeitpunkt '
    'und Eintrag selbst; der Bildschirm zeigt bis dahin „?“. Im Prüfprotokoll steht <b>vorher</b>, was '
    'gezogen wurde — nur die Teilnehmerin weiß es nicht.':
        'Tick what <b>may be drawn</b> in this block. The central unit picks the moment and the entry inside '
        'it; until then the screen shows "?". The audit log says <b>beforehand</b> what was drawn — only the '
        'participant does not know.',
    'Der Pool ist die <b>Sicherheitsgrenze</b>: gezogen wird nur, was hier steht <b>und</b> was für sie '
    'ohnehin erlaubt ist. Decke, Auflagen, Budgets und die Aufgabensperren des Tagesplans gelten '
    'unverändert — der Pool kann nichts erlauben, was ohne ihn nicht auch möglich wäre.':
        'The pool is the <b>safety boundary</b>: only what stands here <b>and</b> is allowed for her anyway '
        'gets drawn. The ceiling, the sanctions, the budgets and the day plan task decisions hold '
        'unchanged — the pool cannot allow anything that would not be possible without it.',
    'Ein Pool darf Aufgaben <b>und</b> Belohnungen enthalten, nicht nur Strafen: einer, der beides kann, '
    'wirkt stärker als einer, der nur droht.':
        'A pool may hold tasks <b>and</b> rewards, not only punishments: one that can do both works more '
        'strongly than one that only threatens.',
    'Über den Kanal': 'Over the channel',
    'Stufe 1 bis 3. Die Stärke selbst kommt aus der Kalibrierung der Teilnehmerin, nicht von hier.':
        'Level 1 to 3. The strength itself comes from her calibration, not from here.',
    'Pool speichern': 'Save pool',
    'Ein leerer Pool ist erlaubt — dieser Block zieht dann nichts und wird übersprungen.':
        'An empty pool is allowed — the block then draws nothing and is skipped.',
    'leer — zieht nichts': 'empty — draws nothing',
    'wählen': 'choose',
    'Pool (kann leer bleiben)': 'Pool (may stay empty)',
    'leer lassen und danach auswählen': 'leave empty and pick afterwards',
    'Der Pool ist die Sicherheitsgrenze: gezogen wird nur, was drinsteht UND was für sie ohnehin erlaubt '
    'ist — Decke, Auflagen, Budgets und die Aufgabensperren des Plans gelten unverändert. Im Prüfprotokoll '
    'steht vorher, was gezogen wurde. Das Feld kann leer bleiben: danach wird der Pool auf einer eigenen '
    'Seite angekreuzt statt getippt.':
        'The pool is the safety boundary: only what stands in it AND is allowed for her anyway gets drawn — '
        'the ceiling, the sanctions, the budgets and the plan task decisions hold unchanged. The audit log '
        'says beforehand what was drawn. The field may stay empty: the pool is then ticked on a screen of '
        'its own instead of typed.',
    'Der Pool ist zu lang — höchstens 255 Zeichen, also rund zwanzig Einträge.':
        'The pool is too long — at most 255 characters, so about twenty entries.',
    'Der Pool wurde nicht vollständig erkannt — bitte melden.':
        'The pool was not recognised in full — please report this.',
    'Pool gespeichert — {n} Einträge.': 'Pool saved — {n} entries.',
    'Der Pool ist jetzt leer — dieser Block zieht nichts.':
        'The pool is empty now — this block draws nothing.',
    # Help at the two fields of the rule editor that had none (doc 58 §5),
    # and what the filtering by trigger says (doc 58 §8).
    'Eine Herausforderung ist entschieden, die Platzierungen stehen fest.':
        'A challenge has been decided, the placements are settled.',
    'Die Wochenbewertung ist gelaufen: Rang, Platz und Punkte der Woche stehen.':
        'The weekly review has run: rank, place and points of the week are settled.',
    'Der Wochenplan ist vollständig — durch den letzten Durchgang oder bei der Wochenbewertung.':
        'The weekly plan is complete — through the last run or at the weekly review.',
    'Bei der Wochenbewertung war der Wochenplan nicht vollständig.':
        'At the weekly review the weekly plan was not complete.',
    'Im Strafregister der Woche ist die eingestellte Schwelle erreicht.':
        'The set threshold in this week\'s punishment record has been reached.',
    'Ein Durchgang wurde bestanden.': 'A run was passed.',
    'Ein Durchgang wurde nicht bestanden.': 'A run was not passed.',
    'Sie hat den Tag vorzeitig beendet — die Marke ein zweites Mal aufgelegt.':
        'She ended the day early — placing the tag a second time.',
    'Der Tag ist regulär zu Ende gegangen.': 'The day came to its regular end.',
    'Ein Budget ist ausgeschöpft: Bestrafungen, Belohnungen oder Durchgänge.':
        'A budget is used up: punishments, rewards or runs.',
    'Eine Serie hat einen Meilenstein erreicht.': 'A streak has reached a milestone.',
    'Eine Serie ist gerissen.': 'A streak has broken.',
    'Die Regel greift bei jedem Anlass dieser Art.': 'The rule applies to every occasion of this kind.',
    'Erster Platz.': 'First place.',
    'Zweiter Platz.': 'Second place.',
    'Dritter Platz oder schlechter.': 'Third place or worse.',
    'Letzter Platz des Feldes.': 'Last place of the field.',
    'Sie ist gar nicht angetreten.': 'She did not take part at all.',
    'Ihr Rang ist 3 oder niedriger — je kleiner die Zahl, desto höher der Rang.':
        'Her rank is 3 or lower — the smaller the number, the higher the rank.',
    'Ihr Rang ist 8 oder höher, also weit unten.': 'Her rank is 8 or higher, so far down.',
    'Der Durchgang wurde mit A bewertet.': 'The run was graded A.',
    'Es war das Budget für Bestrafungen.': 'It was the budget for punishments.',
    'Es war das Budget für Belohnungen.': 'It was the budget for rewards.',
    'Es war ein Budget für Durchgänge — auch das einer einzelnen Aufgabe.':
        'It was a budget for runs — including that of a single task.',
    'Das Tagesbudget, nicht das der Woche.': 'The daily budget, not the weekly one.',
    'Das Wochenbudget, nicht das des Tages.': 'The weekly budget, not the daily one.',
    'Die Serie stand bei mindestens 2.': 'The streak stood at 2 or more.',
    'Die Serie stand bei mindestens 3.': 'The streak stood at 3 or more.',
    'Die Serie stand bei mindestens 5.': 'The streak stood at 5 or more.',
    'Die Serie stand bei mindestens 7.': 'The streak stood at 7 or more.',
    'Die Serie stand bei mindestens 10.': 'The streak stood at 10 or more.',
    'Nur diese eine Serie, keine andere.': 'Only this one streak, no other.',
    'Es stehen nur die Bedingungen zur Wahl, die zu diesem Anlass überhaupt passen — eine Platzierung '
    'gibt es nur, wo etwas platziert wurde.':
        'Only the conditions that can fit this occasion are offered — there is a placement only where '
        'something was placed.',
    'Diese Bedingung gehört nicht zu diesem Anlass — die Regel könnte nie zutreffen. Die Liste zeigt nur '
    'die passenden Bedingungen.':
        'This condition does not belong to this occasion — the rule could never apply. The list shows only '
        'the fitting conditions.',
    'Die Bedingung gehört zu einem anderen Anlass. Diese Regel steht in der Liste, sieht eingerichtet aus '
    'und kann nie zutreffen — bitte Bedingung oder Anlass ändern.':
        'The condition belongs to another occasion. This rule sits in the list, looks configured and can '
        'never apply — please change the condition or the occasion.',
    'trifft nie zu': 'never applies',
    # The value of an effect as separate fields instead of one syntax (doc 58 §5)
    'Privileg': 'Privilege',
    'Wochen (0 = ohne Ende)': 'Weeks (0 = without an end)',
    'Auflage': 'Sanction',
    'Wie lange': 'For how long',
    'bis jemand sie aufhebt': 'until somebody lifts it',
    'bis zum Ende des Tages': 'until the end of the day',
    'für so viele Stunden': 'for this many hours',
    '… und zusätzlich bis so viele Durchgänge bestanden sind (0 = keine)':
        '… and on top of that until this many runs are passed (0 = none)',
    'die Aufgabe des Anlasses': 'the task of the occasion',
    'um so viele Minuten ändern': 'change by this many minutes',
    'auf so viele Minuten setzen': 'set to this many minutes',
    'Punkte (negativ = Abzug)': 'Points (negative = deduction)',
    'erst morgen, nicht heute': 'tomorrow, not today',
    # Duplicate and adjust (doc 58 §9) — learning the model at a working case
    # instead of at an empty form.
    # Narrowing limits (doc 60)
    'Einengen (gilt auch, wenn die Aufgabe erlaubt ist): leer = keine Grenze. Eine Grenze kann nur '
    'weniger bewirken, nie mehr.':
        'Narrowing (applies whether or not the task is allowed): empty = no limit. A limit can only '
        'cause less, never more.',
    'Diese Wellenformen hier nicht': 'Not these waveforms here',
    'Ausgeschlossen, nicht festgelegt: eine festgelegte Wellenform könnte eine sein, die die Auswahl nach '
    'Stufe nie getroffen hätte — das wäre keine Einengung. Bleibt keine übrig, kommt die Aufgabe hier '
    'nicht dran.':
        'Excluded, not pinned: a pinned waveform could be one the pick by level would never have made — '
        'that would not be a narrowing. If none is left, the task does not come up here.',
    'Wellenform(en) ausgeschlossen': 'waveform(s) excluded',
    'duplizieren': 'duplicate',
    'Diese Regel als Vorlage in das Formular übernehmen und dort anpassen.':
        'Take this rule into the form as a template and adjust it there.',
    'aus einer vorhandenen übernommen': 'taken from an existing one',
    'Legt eine Kopie an — mit Blöcken und Aufgabenentscheidungen, aber nie als Vorgabe.':
        'Creates a copy — with blocks and task decisions, but never as the default.',
    'Legt eine Kopie mit allen Schritten an — zugeordnet ist sie niemandem.':
        'Creates a copy with every step — assigned to nobody.',
    '„{name}“ angelegt — Blöcke und Aufgabenentscheidungen sind mitgekommen.':
        '"{name}" created — blocks and task decisions came along.',
    '„{name}“ angelegt — die Schritte sind mitgekommen, zugeordnet ist sie niemandem.':
        '"{name}" created — the steps came along, it is assigned to nobody.',
    # Idle is not a block kind one can choose — it is the state of a day that
    # currently has nothing to do (doc 58 §4); only the views name it.
    'Leerlauf': 'Idle',
    'gerade ist nichts möglich — der Tag wartet und sieht wieder nach':
        'nothing is possible right now — the day waits and looks again',
    'Warten.': 'Wait.',
    'Tag beendet': 'Day finished',
    'kapituliert': 'capitulated',
    'abgebrochen': 'aborted',

    # --------------------------------------------------------- 8. web interface
    # Navigation
    'Live': 'Live',
    'Sklaven': 'Slaves',
    'Programme': 'Programs',
    'Geräte': 'Devices',
    'Logbuch': 'Logbook',
    'Rangliste': 'Leaderboard',
    'Tagesplan': 'Day plan',
    'Mehr ▾': 'More ▾',
    'Protokoll': 'Audit log',
    'Ränge': 'Ranks',
    'Punktesystem': 'Points',
    'Herausforderungen': 'Challenges',
    'Belohnung und Bestrafung': 'Reward and punishment',
    'Export': 'Export',
    'Abmelden': 'Sign out',
    'Sprache': 'Language',

    # recurring buttons and words
    'Speichern': 'Save',
    'Löschen': 'Delete',
    'Anlegen': 'Create',
    'Hinzufügen': 'Add',
    'Bearbeiten': 'Edit',
    'Woche': 'Week',
    'aktuell': 'current',
    'nächste': 'next',
    'Aufgabe': 'Task',
    'Ziel': 'Target',
    'Status': 'Status',
    'Art': 'Kind',
    'von': 'by',
    'Name': 'Name',
    'Notiz': 'Note',
    'Vorgabe': 'Default',
    'offen': 'open',
    'entschieden': 'decided',
    'ungültig': 'void',
    'bestanden': 'passed',
    'nicht bestanden': 'failed',
    'vorgeschlagen': 'proposed',
    'Plan': 'Plan',
    'Nachsitzen': 'Detention',
    'Herausforderung': 'Challenge',
    'Platz': 'Place',
    'Punkte': 'Points',
    'Note': 'Grade',
    'Strafen': 'Punishments',
    'Bestleistung': 'Personal best',
    'Rang': 'Rank',
    'Dauer (min)': 'Duration (min)',
    'keine': 'none',
    'alle': 'all',
    'Sklavenfeld': 'Field of slaves',
    'Jetzt entscheiden': 'Decide now',
    'Herausforderung ansetzen': 'Set up challenge',
    'Block hinzufügen': 'Add block',
    'Neuer Tagesplan': 'New day plan',
    'Regel hinzufügen': 'Add rule',
    'Regel anlegen': 'Create rule',
    'Anlass': 'Trigger',
    'Bedingung': 'Condition',
    'Wirkung': 'Effect',
    'Wert': 'Value',
    'Ordnungszahl': 'Order',
    'Tagesablauf': 'Day schedule',
    'Tagesdauer (min)': 'Day length (min)',
    'Tagespläne': 'Day plans',
    'Struktur eines Trainingstages': 'Structure of a training day',
    'Plan erzeugen': 'Generate plan',
    'Wochenbewertung Vorwoche': 'Weekly review of last week',
    'Aufgabenliste je Sklave und Woche': 'Task list per slave and week',
    'eine Aufgabe, alle Sklaven, eine Bestenliste': 'one task, all slaves, one leaderboard',
    'Regeln: Anlass → Bedingung → Wirkung': 'Rules: trigger → condition → effect',
    'Was die Wirkungen tun': 'What the effects do',
    'Privilegien': 'Privileges',
    'Abzeichen': 'Badges',
    'Ansetzen': 'Set up',
    'Liste': 'List',
    'Inhalt': 'Content',
    'nächste offene Aufgabe': 'next open task',
    'nächste offene': 'next open',
    'Zentrale wählt': 'the central chooses',
    'Einheit': 'Unit',
    'Sekunden / Anzahl': 'seconds / count',
    'Minuten': 'minutes',
    'erlaubte Strafen': 'allowed punishments',
    'Aufgabenstufen': 'Task levels',
    'Letzte Durchgänge': 'Recent runs',
    'Zeugnis': 'Report',
    'Kanal': 'Channel',
    'Bestrafen': 'Punish',
    'Belohnen': 'Reward',
    'Grund': 'Reason',
    'Stufe': 'Level',
    'setzen': 'set',
    'erteilen': 'grant',
    'entziehen': 'revoke',
    'einfrieren (keine Wochenbewertung)': 'freeze (no weekly review)',
    'Rang setzen': 'Set rank',
    'Rang und Punkte': 'Rank and points',
    'Wochenpunkte (Score)': 'Weekly points (score)',
    'Gesamtpunkte': 'Total points',
    'Letzter Durchgang': 'Last run',
    'Privileg erteilen ': 'Grant privilege ',
    # --- waveform routines (doc 17) ------------------------------------- #
    'Wellenformen': 'Waveforms',
    'Wellenform': 'Waveform',
    'Wellenform (Pflicht)': 'Waveform (required)',
    'Routinen für den Blowjob-/Deepthroat-Trainer': 'Routines for the blowjob/deepthroat trainer',
    'Eine Wellenform gibt über die Zeit eine Zieltiefe mit Toleranz vor; das Gerät bewertet jede '
    'Abtastung und liefert am Ende eine Note von 0 bis 10000. Gemessen wird in Prozent des eigenen '
    'kalibrierten Bereichs des Sklaven, nie in Millimetern.':
        'A waveform sets a target depth with a tolerance over time; the device scores every sample and '
        'reports a score from 0 to 10000 at the end. Everything is measured in percent of the '
        "slave's own calibrated range, never in millimetres.",
    'Die Stufe wählt die Wellenform': 'The level selects the waveform',
    'sie skaliert kein Ziel. Ein Sklave auf Stufe 5 bekommt die Wellenform der Stufe 5; gibt es '
    'keine, gilt die nächstniedrigere. Der Zielwert der Planaufgabe ist die Mindestnote.':
        'it does not scale a target. A slave on level 5 gets the level 5 waveform; if there is '
        'none, the next lower one applies. The target of a plan task is the required score.',
    'Stützpunkte': 'Breakpoints',
    'Mindestnote': 'Required score',
    'Vollausschlag': 'Full scale',
    'Vollausschlag (%)': 'Full scale (%)',
    'Toleranz (%)': 'Tolerance (%)',
    'Übergang (ms)': 'Transition (ms)',
    'Tiefe (%)': 'Depth (%)',
    'Anfahrt (s)': 'Approach (s)',
    'Zeit (s)': 'Time (s)',
    'Noch keine Wellenform — unten eine anlegen.': 'No waveform yet - create one below.',
    'Neue Wellenform': 'New waveform',
    'Vollausschlag: die Abweichung, bei der eine Abtastung null Punkte gibt. Übergang: wie lange das '
    'Gerät zwischen zwei Durchläufen interpoliert. Kanal-Stufen 0 bis 3, 0 bedeutet: kein Impuls.':
        'Full scale: the deviation at which a sample scores zero. Transition: how long the device '
        'interpolates between two passes. Channel levels 0 to 3, where 0 means no pulse.',
    'Alle Wellenformen': 'All waveforms',
    'Hinweise': 'Notes',
    'Hinweise blockieren nichts — die Aufsicht zeichnet die Kurve und sieht, wo es unangenehm wird. '
    'Die harte Grenze steht in der Firmware und lässt sich über MQTT nicht anheben.':
        'Notes never block anything - the supervisor draws the curve and is shown where it gets '
        'unpleasant. The hard limit lives in the firmware and cannot be raised over MQTT.',
    'Kurve': 'Curve',
    'Oben ist die Ruhelage, unten die größte Tiefe — beides in Prozent des eigenen kalibrierten '
    'Bereichs. Das grüne Band ist die Toleranz: innerhalb kostet eine Abtastung nichts, außerhalb '
    'zählt die Abweichung quadratisch.':
        "The top is the resting position, the bottom the greatest depth - both in percent of the "
        "slave's own calibrated range. The green band is the tolerance: inside it a sample "
        'costs nothing, outside the deviation counts squared.',
    'Prüfsumme': 'Checksum',
    'verwendet in {n} Aufgaben/Herausforderungen': 'used by {n} tasks/challenges',
    'Zeichnen': 'Drawing',
    'Eine Kiste ist ein Halt auf einer Tiefe: Anfahrt, dann halten. Eine Rampe ist ein einzelner '
    'Stützpunkt — das Gerät interpoliert dorthin. Beides hängt hinten an die Kurve an; Zeiten '
    'einzelner Punkte lassen sich unten korrigieren.':
        'A box is a hold at one depth: approach, then hold. A ramp is a single breakpoint - the device '
        'interpolates towards it. Both are appended to the end of the curve; the time of an individual '
        'breakpoint can be corrected below.',
    'Kiste anhängen': 'Append box',
    'Rampe anhängen': 'Append ramp',
    'Kurve leeren': 'Clear curve',
    'Alle Stützpunkte löschen?': 'Delete every breakpoint?',
    'Übernehmen': 'Apply',
    'Noch keine Stützpunkte — oben eine Kiste anhängen.': 'No breakpoints yet - append a box above.',
    'Höchstens {n} Stützpunkte; Zeiten werden nach dem Speichern neu sortiert.':
        'At most {n} breakpoints; times are re-sorted after saving.',
    'Eigenschaften': 'Properties',
    'Kopieren': 'Copy',
    '(Kopie)': '(copy)',
    'Wellenform wirklich löschen?': 'Really delete this waveform?',
    'bitte wählen': 'please choose',
    'nach Stufe': 'by level',
    # messages
    'Die Wellenform braucht einen Namen.': 'The waveform needs a name.',
    'Eine Wellenform mit diesem Namen gibt es schon.': 'A waveform with that name already exists.',
    'Wellenformen nicht verfügbar - Migration 008 fehlt.':
        'Waveforms are not available - migration 008 is missing.',
    'Wellenform angelegt — jetzt die Kurve zeichnen.': 'Waveform created - now draw the curve.',
    'Wellenform gespeichert.': 'Waveform saved.',
    'Wellenform kopiert.': 'Waveform copied.',
    'Wellenform gelöscht.': 'Waveform deleted.',
    'Eine offene Herausforderung nutzt diese Wellenform.':
        'An open challenge is using this waveform.',
    'Mehr als {n} Stützpunkte nimmt das Gerät nicht an.':
        'The device does not accept more than {n} breakpoints.',
    'Kurve geändert: {n} Stützpunkte, {s} s.': 'Curve changed: {n} breakpoints, {s} s.',
    'Diese Aufgabe braucht eine feste Wellenform — sonst läuft jeden Sklaven '
    'nach ihrer eigenen Stufe eine andere Kurve und sie liefen nebeneinander '
    'statt gegeneinander.':
        'This task needs a fixed waveform - otherwise every slave runs a different curve on her '
        'own level and they would be running side by side instead of against each other.',
    'Trainer {dev} ohne Tiefenkalibrierung - Gerätevorgaben gelten':
        'Trainer {dev} has no depth calibration - the device defaults apply',
    'Wellenform {id} ist unbekannt - Aufgabe entfällt':
        'Waveform {id} is unknown - the task is skipped',
    'Wellenform {id} ist keine bewertbare Aufgabe - Aufgabe entfällt':
        'Waveform {id} is not a scoreable task - the task is skipped',
    'Wellenform {id} ist kein abspielbarer Reiz (Zweck oder Achse passen nicht) - Schritt entfällt':
        'Waveform {id} is not a playable stimulus (purpose or axis do not fit) - the step is skipped',
    'Eine Aufgabe läuft ab und wird bewertet — sie braucht die Zeitachse. '
    'Für eine Kurve über der Tiefe den Zweck „Reiz" oder „Belohnung" wählen.':
        'A task runs and is scored — it needs the time axis. '
        'For a curve over the depth, choose the purpose "stimulus" or "reward".',
    'Auf der Tiefenachse gibt es keine Zieltiefen-Spur — erst die Rolle '
    'der Spur ändern, dann die Achse wechseln.':
        'There is no target-depth track on the depth axis — change the role '
        'of the track first, then switch the axis.',
    'unbekannte Fähigkeit {c}': 'unknown capability {c}',

    # device testing (doc 22)
    'Gerät testen': 'Test device',
    'Testen': 'Test',
    'Bearbeiten': 'Edit',
    'Auslösen': 'Trigger',
    'Zurück zur Übersicht': 'Back to the list',
    'Modell': 'Model',
    'device_UUID': 'device_UUID',
    'meldet': 'reports',
    'letztes Ereignis': 'last event',
    'offline': 'offline',
    'Blinken': 'Identify',
    'Stopp': 'Stop',
    'vor {n} s': '{n} s ago',
    'wirkt körperlich': 'acts physically',
    'wartet auf Ergebnis': 'waits for the result',
    'Am Gerät löst das wirklich aus. Fortfahren?':
        'This really fires on the device. Continue?',
    'Was hier ausgelöst wird, wirkt sofort und wirklich.':
        'What you trigger here happens immediately and for real.',
    'Es zählt aber nicht: kein Durchgang, keine Note, keine Punkte, keine Bestrafung. '
    'Im Protokoll steht es trotzdem — eine von Hand ausgelöste körperliche Wirkung gehört nachvollziehbar.':
        'It does not count, though: no run, no grade, no points, no punishment. It is still in the '
        'log — a physical effect triggered by hand belongs on the record.',
    'Das Gerät ist offline — es lässt sich nichts auslösen.':
        'The device is offline — nothing can be triggered.',
    'Dieses Gerät meldet keine Fähigkeit, zu der es eine Aktion gibt.':
        'This device reports no capability that has an action.',
    'Diese Aktion hat keine Parameter.': 'This action has no parameters.',
    'Keine passende Wellenform vorhanden — erst eine anlegen.':
        'No matching waveform — create one first.',
    '— keine —': '— none —',
    'Die Liste kommt aus der Aktions-Registry im Code und ist auf das gefiltert, was die laufende '
    'Firmware dieses Geräts meldet. Ein neues Gerätemodell erscheint hier von selbst — es gibt '
    'keine zweite Liste, die veralten könnte.':
        'The list comes from the action registry in the code, filtered by what this device\'s '
        'running firmware reports. A new device model shows up here by itself — there is no second '
        'list that could go stale.',
    '{action} an {dev} gesendet: {params}': '{action} sent to {dev}: {params}',
    'Wellenform {id} gibt es nicht.': 'Waveform {id} does not exist.',

    # E-stim bridge: state and binding (doc 22 §8)
    'Coyote an dieser Bridge': 'Coyote on this bridge',
    'verbunden': 'connected',
    'keine Coyote': 'no Coyote',
    'Zuordnung': 'Binding',
    'fest': 'fixed',
    'frei': 'free',
    'nur dieses Gerät': 'this device only',
    'nimmt die erste Coyote, die antwortet': 'takes the first Coyote that answers',
    'wartet auf': 'waiting for',
    'Ausgabe': 'Output',
    'Regler': 'dial',
    'Regler am Gerät': 'dial on the device',
    'heute': 'today',
    'Diese Coyote fest zuordnen': 'Bind this Coyote',
    'Zuordnung lösen': 'Release binding',
    'oder eine MAC von Hand': 'or a MAC by hand',
    'Übernehmen': 'Apply',
    'Nützlich, wenn die gewünschte Coyote gerade aus ist. Die Bridge trennt eine '
    'bestehende Verbindung sofort und sucht neu.':
        'Useful when the Coyote you want is switched off. The bridge drops an existing '
        'connection right away and searches again.',
    'Bindung gesendet — der Zustand zeigt in ein paar Sekunden, ob die Bridge verbunden ist.':
        'Binding sent — the state will show in a few seconds whether the bridge is connected.',
    'Gerät ist nicht online.': 'The device is not online.',
    'Aufgabe nicht vorbereitbar': 'task could not be prepared',
    'Logbuch nicht verfügbar.': 'Logbook not available.',
    'Strafe': 'Punishment',
    'Belohnung': 'Reward',
    'Bearbeiten': 'Edit',
    'Anlegen': 'Create',
    'Name': 'Name',
    'Notiz': 'Note',
    'Dauer': 'Duration',
    'Toleranz': 'Tolerance',
    'Speichern': 'Save',
    'Löschen': 'Delete',
    'Halten (s)': 'Hold (s)',
    'Datenbank liegt hinter dem Code: Migration(en) {v} fehlen. Die Zentrale spielt sie beim Start '
    'automatisch ein — oder von Hand: python3 libs/dbmigrate.py':
        'The database is behind the code: migration(s) {v} are missing. The central unit applies them '
        'automatically on start-up - or by hand: python3 libs/dbmigrate.py',
    # --- waveform generator, tracks and E-Stim (doc 19) ------------------ #
    'Kurven für Trainer, Vibration und E-Stim': 'Curves for the trainer, vibration and e-stim',
    'Eine Wellenform ist eine Kurve mit einer X-Achse, einem Zweck und einer oder mehreren Spuren. '
    'Eine Spur ist entweder die Zieltiefe, die nachgefahren und bewertet wird, oder ein Ausgang: '
    'Bestrafung, Stimulation oder Belohnung. Gemessen und ausgegeben wird immer in Prozent — nie in '
    'Millimetern und nie in Volt.':
        'A waveform is a curve with an X axis, a purpose and one or more tracks. A track is either '
        'the target depth, which is followed and scored, or an output: punishment, stimulation or '
        'reward. Everything is measured and emitted in percent - never in millimetres and never in volts.',
    'Die fünf Beispiele unten sind zum Vergleichen da: sie zeigen, wie eine brauchbare Kurve aussieht, '
    'und lassen sich kopieren.':
        'The five examples below are there to compare against: they show what a workable curve looks '
        'like, and they can be copied.',
    'Was es ist': 'What it is',
    'Beispiel': 'Example',
    'X-Achse': 'X axis',
    'Zweck': 'Purpose',
    'Vollausschlag: die Abweichung, bei der eine Abtastung null Punkte gibt. Übergang: wie lange das '
    'Gerät zwischen zwei Durchläufen interpoliert. Die erste Spur wird passend zum Zweck gleich mit '
    'angelegt.':
        'Full scale: the deviation at which a sample scores zero. Transition: how long the device '
        'interpolates between two passes. The first track is created along with it, to match the purpose.',
    'Spur': 'Track',
    'Spur bearbeiten': 'Edit track',
    'Abspielen': 'Play',
    'Anhalten': 'Pause',
    'Kurve speichern': 'Save curve',
    'Sollwert': 'Target',
    'Die Zeichenfläche konnte nicht starten': 'The canvas could not start',
    'Ausgabe': 'Output',
    'Klicken setzt einen Stützpunkt, Ziehen verschiebt ihn, Rechtsklick löscht ihn. Oben ist die '
    'Ruhelage, unten die größte Tiefe — tiefer ist hier wirklich weiter unten. Geändert wird immer nur '
    'die oben gewählte Spur; die anderen liegen blass dahinter, damit man sieht, wie sie zusammenspielen.':
        'Click to place a breakpoint, drag to move it, right-click to delete it. The top is the resting '
        'position, the bottom the greatest depth - deeper really is further down here. Only the track '
        'selected above is changed; the others sit faintly behind it so you can see how they work together.',
    'Klicken setzt einen Stützpunkt, Ziehen verschiebt ihn, Rechtsklick löscht ihn. Unten ist nichts, '
    'oben volle Stärke — mehr ist hier weiter oben. Geändert wird immer nur die oben gewählte Spur; die '
    'anderen liegen blass dahinter, damit man sieht, wie sie zusammenspielen.':
        'Click to place a breakpoint, drag to move it, right-click to delete it. The bottom is nothing, '
        'the top is full strength - more is further up here. Only the track selected above is changed; '
        'the others sit faintly behind it so you can see how they work together.',
    'Änderungen auf der Fläche sind erst nach „Kurve speichern" in der Datenbank.':
        'Changes on the canvas only reach the database after "Save curve".',
    'Spuren': 'Tracks',
    'Eine Spur ist eine Kurve mit einer Rolle. Die Rolle entscheidet den Charakter — welches Profil die '
    'Bridge spielt —, nicht die Höhe. Belohnung und Bestrafung müssen sich fühlbar unterscheiden, '
    'deshalb sind die Profile fest je Rolle vergeben.':
        'A track is a curve with a role. The role decides the character - which profile the bridge plays '
        '- not the height. Reward and punishment have to feel different, so the profiles are fixed per role.',
    'Rolle': 'Role',
    'Profil': 'Profile',
    'Modus': 'Mode',
    'Kopplung an': 'Coupled to',
    'Spur mitsamt Kurve löschen?': 'Delete the track and its curve?',
    'Neue Spur': 'New track',
    'Spur hinzufügen': 'Add track',
    'Je Kanal klingt immer nur eine Spur: kommen zwei gleichzeitig, gilt Bestrafung vor Stimulation vor '
    'Belohnung. Zwei Rollen gleichzeitig gehören deshalb auf die zwei Kanäle — das sind zwei '
    'Elektrodenpaare und fühlt sich getrennt an.':
        'Only one track sounds per channel: if two are active at once, punishment beats stimulation '
        'beats reward. Two roles at the same time therefore belong on the two channels - those are two '
        'pairs of electrodes and feel separate.',
    'Zeichnen mit Werten': 'Drawing with numbers',
    'Für alle, die lieber Zahlen eingeben als zu ziehen: eine Kiste ist ein Halt (Anfahrt, dann halten), '
    'eine Rampe ein einzelner Stützpunkt. Beides hängt hinten an die gewählte Spur an und wird sofort '
    'gespeichert.':
        'For anyone who would rather type than drag: a box is a hold (approach, then hold), a ramp is a '
        'single breakpoint. Both are appended to the selected track and saved straight away.',
    'Wert (%)': 'Value (%)',
    'Anfahrt (%)': 'Approach (%)',
    'Halten (%)': 'Hold (%)',
    'Alle Stützpunkte dieser Spur löschen?': 'Delete every breakpoint of this track?',
    'Spur leeren': 'Clear track',
    'Der Zweck steht am Kopf und sagt, WO die Wellenform auftaucht. Die Rolle steht an der Spur und '
    'sagt, WAS sie am Ausgang tut. Die beiden werden gern verwechselt — deshalb stehen sie hier '
    'beieinander.':
        'The purpose sits on the head and says WHERE the waveform appears. The role sits on the track '
        'and says WHAT it does at the output. The two get mixed up easily - which is why they stand '
        'together here.',
    'gespeichert': 'saved',
    'ungespeicherte Änderungen': 'unsaved changes',
    'keine Kopplung: gibt nichts aus': 'no live value: emits nothing',
    'Tiefe in Prozent des eigenen kalibrierten Bereichs des Sklaven — 0 ist die Ruhelage, 100 der '
    'tiefste gemessene Punkt.':
        "Depth in percent of the slave's own calibrated range - 0 is the resting position, 100 the "
        'deepest measured point.',
    'Prozent der Decke, die der Träger am Gerät selbst eingestellt hat — nicht Prozent der '
    'Geräteleistung. Was hier 70 % heißt, sind 70 % von dem, was er erlaubt hat.':
        'Percent of the ceiling the wearer set on the device himself - not percent of what the device '
        'can do. 70 % here means 70 % of what he has allowed.',
    'Gekoppelt: der Wert der Kurve ist die Obergrenze, wie viel ankommt entscheidet sie.':
        'Coupled: the curve value is the upper limit; how much arrives is up to her.',
    'Absolut: der Wert der Kurve kommt so heraus.': 'Absolute: the curve value is what comes out.',
    'Mehr als {n} Spuren gehen nicht.': 'More than {n} tracks is not possible.',
    'Spur {n} angelegt.': 'Track {n} created.',
    'Spur {n} gespeichert.': 'Track {n} saved.',
    'Spur {n} gelöscht.': 'Track {n} deleted.',
    'Die letzte Spur lässt sich nicht löschen — sonst gäbe es nichts zu zeichnen.':
        'The last track cannot be deleted - there would be nothing left to draw.',
    'bewertet, Mindestnote {n}': 'scored, required score {n}',
    'gekoppelt': 'coupled',
    '1 Spur: ': '1 track: ',
    '{n} Spuren: ': '{n} tracks: ',
    'Wellenform {id} ist keine Kopplung (falsche Achse)':
        'Waveform {id} is not a coupling (wrong axis)',
    # axes, purposes, roles, channels, modes, profiles
    'Zeit': 'Time', 'Tiefe': 'Depth', 'Zeitachse': 'time axis', 'Tiefenachse': 'depth axis',
    'Die Kurve läuft ab: X ist die Zeit seit dem Start.':
        'The curve runs: X is the time since the start.',
    'Die Kurve läuft nicht ab, sie folgt dem, was gemessen wird: X ist die Tiefe in Prozent des eigenen '
    'Bereichs.':
        "The curve does not run, it follows what is measured: X is the depth in percent of the "
        "slave's own range.",
    'Aufgabe': 'Task', 'Reiz': 'Stimulus',
    'Kommt in Wochenplan und Herausforderung, wird bewertet und hat eine Mindestnote.':
        'Goes into the weekly plan and into challenges, is scored and has a required score.',
    'Läuft als eigenes Programm oder als Kopplung mit, wird nicht bewertet.':
        'Runs as a programme of its own or alongside as a coupling; not scored.',
    'Wird nur für Erreichtes gegeben. Kann nie eine Planaufgabe sein — sie lässt sich nicht verfehlen.':
        'Given only for something achieved. Can never be a plan task - it cannot be failed.',
    'Zieltiefe': 'Target depth',
    'Die Kurve, die nachgefahren und bewertet wird. Kein Ausgang.':
        'The curve that is followed and scored. Not an output.',
    'Unangenehm. Harter Einsatz, damit sie sich von einer Belohnung unterscheidet — nicht nur in der '
    'Höhe, sondern im Gefühl.':
        'Unpleasant. A hard onset, so it differs from a reward - not only in height but in feel.',
    'Weder Lob noch Strafe: Reiz, der die Aufgabe begleitet.':
        'Neither praise nor punishment: a stimulus that accompanies the task.',
    'Angenehm und unverwechselbar. Wird nur für Erreichtes gegeben.':
        'Pleasant and unmistakable. Given only for something achieved.',
    'Position': 'Position', 'Genauigkeit': 'Accuracy',
    'Wie tief sie gerade ist, bestimmt den Anteil.': 'How deep she is right now decides the share.',
    'Wie gut sie im Toleranzband liegt, bestimmt den Anteil.':
        'How well she holds the tolerance band decides the share.',
    'Absolut': 'Absolute', 'Gekoppelt': 'Coupled',
    'Der Wert der Kurve kommt so heraus.': 'The curve value is what comes out.',
    'Der Wert der Kurve ist die Obergrenze; wie viel davon ankommt, hängt von ihr ab.':
        'The curve value is the upper limit; how much of it arrives depends on her.',
    'Kanal A': 'Channel A', 'Kanal B': 'Channel B', 'Vibration': 'Vibration',
    'Erstes Elektrodenpaar der Coyote.': 'First pair of electrodes on the Coyote.',
    'Zweites Elektrodenpaar der Coyote.': 'Second pair of electrodes on the Coyote.',
    'Vibrator statt Strom.': 'A vibrator instead of current.',
    'Stich': 'Sting', 'Haken': 'Hook', 'Welle': 'Wave', 'Flirren': 'Shimmer',
    'Zweitakt': 'Two-beat', 'Warm': 'Warm',
    'Harter Einsatz, beißend, kein Nachlassen. Das schärfste Profil.':
        'Hard onset, biting, no let-up. The sharpest profile.',
    'Langsames Ziehen, unangenehm ohne Spitze. Für lange Phasen, in denen ein Stich nur abstumpfen würde.':
        'A slow pull, unpleasant without a peak. For long phases where a sting would only go dull.',
    'Rollend, weich an- und abschwellend. Das ruhige Grundprofil für lange Reize.':
        'Rolling, swelling softly up and down. The calm base profile for long stimulation.',
    'Fein, oberflächlich, kribbelnd. Bleibt präsent, ohne zu ermüden.':
        'Fine, superficial, tingling. Stays present without tiring.',
    'Zwei deutliche Schläge, dann Ruhe — unverwechselbar und nie mit einer Strafe zu verwechseln. '
    'Entspricht den zwei sanften Stößen des Halsbands.':
        'Two distinct beats, then quiet - unmistakable and never to be confused with a punishment. '
        'The same idea as the two gentle pulses of the collar.',
    'Tief, satt, gleichmäßig tragend. Für längere Belohnungen, bei denen ein Takt aufdringlich würde.':
        'Deep, full, evenly carrying. For longer rewards where a beat would become intrusive.',
    'E-Stim Kanal A': 'E-stim channel A', 'E-Stim Kanal B': 'E-stim channel B',
    'E-Stim: Wellenform': 'E-stim: waveform',
    'Eine Wellenform als Reiz, Belohnung oder Bestrafung abspielen':
        'Play a waveform as stimulation, reward or punishment',
    'E-Stim: Wellenform abspielen': 'E-stim: play a waveform',
    # --- envelope per device (doc 23) ------------------------------------
    'Hüllkurve dieses Geräts': "This device's envelope",
    'von der laufenden Firmware gemeldet': 'reported by the running firmware',
    'gemeldet': 'reported',
    'aus dem Modellkatalog; die Firmware meldet ihre Grenzen noch nicht':
        'from the model catalogue; this firmware does not report its limits yet',
    'aus dem Katalog': 'from the catalogue',
    'Was dieses Gerät höchstens durchlässt. Die Felder unten sind darauf begrenzt — '
    'ein größerer Wert würde vom Gerät still gekappt oder abgelehnt.':
        'The most this device will pass. The fields below are limited to it - a larger '
        'value would be silently capped or refused by the device.',
    'Dieses Gerät lässt höchstens {n} durch': 'This device passes at most {n}',
    'die Anlage kennt bis {n}': 'the plant knows up to {n}',
    '{field}: {wanted} lässt dieses Gerät nicht durch — gesendet wurden {sent}{unit}.':
        '{field}: this device does not pass {wanted} - {sent}{unit} was sent.',
    # labels of the envelope keys (devicemodels.ENVELOPE_KEYS)
    'Impulsstärke des Halsbands': 'Collar pulse strength',
    'längste Sendedauer eines Impulses': 'longest transmission of one pulse',
    'längste Laufzeit eines Modus': 'longest run of a mode',
    'V-Cage: längste Bestrafung': 'V-Cage: longest punishment',
    'längste Verriegelung': 'longest lock',
    'längstes freies Training': 'longest free training',
    'längste Pad-Aufgabe': 'longest pad task',
    'längster Impuls': 'longest pulse',
    'höchste E-Stim-Intensität': 'highest e-stim intensity',
    'E-Stim-Ausgabe je Tag': 'e-stim output per day',
    'längster E-Stim-Lauf am Stück': 'longest e-stim run in one go',
    'längstes Kanal-Ereignis': 'longest channel event',
    'Mindestabstand zweier Impulse': 'shortest gap between two pulses',
    'Bestrafungskanal: Impuls je Stufe': 'Punishment channel: pulse per level',
    # --- programme against devices (doc 24) ------------------------------
    'Neu': 'New',
    'Zuletzt unbekannter Tag an der Zentrale:': 'Last unknown tag at the central unit:',
    'als Sklaven anlegen': 'create as a slave',
    'RFID': 'RFID',
    'Aktives Programm': 'Active programme',
    'Passt': 'Fits',
    'keins': 'none',
    'Zuordnen': 'Assign',
    'Noch keine Sklaven.': 'No slaves yet.',
    '{n} Stellen, an denen das Programm nicht zu den Geräten passt':
        '{n} places where the programme does not fit the devices',
    '{n} aktiv': '{n} active',
    '{n} Stellen': '{n} places',
    'Programm und Geräte passen nicht zusammen': 'Programme and devices do not fit together',
    'Was hier steht, läuft nicht so, wie es im Programm steht. Gemessen wird gegen die engste '
    'Hüllkurve aller zugeordneten Geräte mit der passenden Fähigkeit — welches den Schritt '
    'bekommt, steht vorher nicht fest.':
        'What is listed here will not run the way the programme says. It is measured against the '
        'tightest envelope of all assigned devices with the matching capability - which one gets '
        'the step is not settled in advance.',
    'Zu hohe Werte werden beim Senden auf die Grenze des Geräts gekappt und im Logbuch vermerkt '
    '— der Durchgang läuft, aber nicht wie geplant.':
        'Values that are too high are capped to the device limit when sent and noted in the '
        'logbook - the run happens, but not as planned.',
    'aktiv': 'active',
    'zugeordnet': 'assigned',
    'Bei wem dieses Programm nicht aufgeht': 'For whom this programme does not work out',
    'fehlt': 'missing',
    'Schritt {n}': 'Step {n}',
    'geht so nicht mehr durch die Anlage': 'no longer passes the plant at all',
    'kein zugeordnetes Gerät kann das': 'no assigned device can do this',
    'durchgelassen werden {n}': '{n} will pass',
    'Kalibrierung fehlt': 'calibration missing',
    'das Gerät hat sich nie gemeldet': 'the device has never reported in',
    'Zuordnungen gespeichert — die Zentrale übernimmt sie sofort, auch bei angemeldetem Sklaven.':
        'Assignments saved - the central unit adopts them at once, even with a slave signed in.',
    'Diese Zuordnung passt an {n} Stellen nicht zu den Geräten — {a} davon im aktiven Programm. '
    'Die Tafel weiter unten sagt, wo.':
        'This assignment does not fit the devices in {n} places - {a} of them in the active '
        'programme. The panel below says where.',
    # --- headroom of the bridge (doc 21 §7b) -----------------------------
    'Reserve': 'Headroom',
    'Stack': 'stack',
    'Heap': 'heap',
    'knapp': 'tight',
    'Bridge läuft seit': 'Bridge up for',
    '{n} Abbrüche der Coyote': '{n} Coyote dropouts',
    'Sklaven „{name}" samt Logbuch, Plänen und Foto gelöscht.':
        'Slave "{name}" deleted, along with logbook, plans and photo.',
    # --- note about an unknown tag ---------------------------------------
    'Unbekannter Tag': 'Unknown tag',
    'Sklaven anlegen': 'Create slave',
    'verwerfen': 'dismiss',
    'Der Tag soll niemandem gehören — Merker wegräumen.':
        'The tag is not meant to belong to anyone - clear the note.',
    'Merker für den unbekannten Tag {rfid} verworfen.':
        'Note about the unknown tag {rfid} dismissed.',
    'Es lag kein unbekannter Tag vor.': 'There was no unknown tag.',
    'Spitze des letzten Laufs': 'Peak of the last run',
    # --- what the collar sees right now (doc 25) -------------------------
    'in Haltung': 'in position',
    'Haltung verlassen': 'position left',
    'außerhalb des V-Cage': 'outside the V-Cage',
    'bewegt sich': 'moving',
    'nichts gemessen': 'nothing measured',
    'seit': 'for',
    'davor': 'before that',
    '{n} Wechsel': '{n} changes',
    '{n} Wechsel in diesem Modus': '{n} changes in this mode',
    'Impuls steht an': 'Pulse pending',
    'in {n} s': 'in {n} s',
    'mit Vorwarnung': 'with a warning first',
    'Modus läuft': 'Mode running for',
    'Impulse': 'pulses',
    'Warnungen': 'warnings',
    'Verstoße': 'violations',
    'draußen': 'outside',
    'Was das Halsband gerade sieht': 'What the collar sees right now',
    'Rest': 'left',
    'Zustand': 'Condition',
    'Neigung': 'Tilt',
    'erlaubt bis': 'allowed up to',
    'Funkstärke': 'Signal strength',
    'V-Cage hat aufgegeben': 'V-Cage gave up',
    'reglos seit': 'motionless for',
    'Impuls': 'Pulse',
    'steht an': 'pending',
    'keiner': 'none',
    'in diesem Modus': 'in this mode',
    'außerhalb der Haltung': 'out of position',
    'Einstellungen': 'Settings',
    '{n} Impulse insgesamt': '{n} pulses in total',
    'läuft seit': 'up for',
    'V-Cage': 'V-Cage',
    'Stärke': 'Strength',
    'Vibration': 'Vibration',
    'Ton': 'Tone',
    'Modus': 'Mode',
    '{dev}: was das Gerät gerade sieht': '{dev}: what the device sees right now',
    # --- sanctions (doc 26) -----------------------------------------------
    'Abgewiesen, nicht angezeigt:': 'Refused, not shown:',
    'Meist eine Firmware unter 2.0 oder ein anderer Projektschlüssel. Solche Geräte werden nicht als Gerät geführt — der Grund steht im Protokoll.':
        'Usually firmware below 2.0, or a different project key. Such devices are not kept as '
        'devices at all - the reason is in the log.',
    'Auflagen': 'Sanctions',
    'noch offen': 'still open',
    'ohne Einfluss auf die Wochenpunkte': 'no effect on the weekly points',
    'Dauer anhängen: <code>:2</code> = zwei Stunden, <code>:d</code> = bis zum Ende des Tages, '
    '<code>:r3</code> = bis drei Durchgänge bestanden sind. Ohne Angabe läuft die Auflage, bis jemand sie aufhebt.':
        'Append a duration: <code>:2</code> = two hours, <code>:d</code> = until the end of the day, '
        '<code>:r3</code> = until three runs have been passed. With nothing given the sanction runs '
        'until somebody lifts it.',
    'Unbekannte Auflage — Schlüssel aus der Liste rechts.':
        'Unknown sanction - use a key from the list on the right.',
    'Aufheben nimmt nur den Schlüssel, keine Dauer.':
        'Lifting takes only the key, not a duration.',
    'Die Dauer in Stunden muss größer als 0 sein.':
        'The duration in hours must be greater than 0.',
    'Auflage verhängen': 'Impose a sanction',
    'Auflage verhängt.': 'Sanction imposed.',
    'Auflage aufgehoben.': 'Sanction lifted.',
    'Diese Auflage läuft schon.': 'That sanction is already running.',
    'Auflage verhängt — OHNE Ende. Sie läuft, bis jemand sie aufhebt.':
        'Sanction imposed - with NO end. It runs until somebody lifts it.',
    'Auflage verhängen? Sie wirkt sofort und bis zum Ende.':
        'Impose the sanction? It takes effect at once and runs to its end.',
    'Verhängen': 'Impose',
    'aufheben': 'lift',
    'bis': 'until',
    'bis Tagesende': 'until the end of the day',
    'noch {n} Durchgänge': '{n} runs to go',
    'ohne Ende': 'no end',
    'Stunden': 'Hours',
    'Durchgänge': 'Runs',
    'Grund': 'Reason',
    'keine': 'none',
    'steht im Protokoll und auf ihrer Seite': 'shown in the log and on her page',
    'Was zuerst eintritt, beendet die Auflage. Ohne jede Angabe läuft sie, bis jemand sie '
    'aufhebt — das ist erlaubt, wird aber gern vergessen.':
        'Whichever comes first ends the sanction. With nothing given it runs until somebody '
        'lifts it - which is allowed, but easily forgotten.',
    'Auflage: in Fesseln': 'Sanction: in restraints',
    'Privileg: ohne Fesseln': 'Privilege: without restraints',
    'Belohnung zurückgehalten — Auflage „Keine Belohnungen"':
        'Reward withheld - sanction "No rewards"',
    # catalogue
    'In Fesseln': 'In restraints',
    'MAGLOCK-Schritte werden Pflicht, UNLOCK-Schritte entfallen — das Schloss bleibt zu. '
    'Sticht das Privileg „Ohne Fesseln" aus.':
        'MAGLOCK steps become mandatory, UNLOCK steps are dropped - the lock stays shut. '
        'Beats the privilege "Without restraints".',
    'V-Cage bleibt an': 'The V-Cage stays on',
    'Ein laufender V-Cage fällt nicht mehr von selbst weg: endet ein anderer '
    'Halsband-Modus oder läuft die Maximaldauer ab, kommt er zurück. '
    'EINSCHALTEN tut die Auflage nichts — das bleibt ein Handgriff der Aufsicht. '
    'Ein Not-Aus beendet ihn und holt ihn nicht zurück.':
        'A running V-Cage no longer falls away on its own: when another collar mode ends, or '
        'the maximum duration runs out, it comes back. The sanction never SWITCHES IT ON - '
        'that stays a deliberate act by the supervisor. An emergency stop ends it and does '
        'not bring it back.',
    'Keine Belohnungen': 'No rewards',
    'Belohnungen im Kanal werden zurückgehalten. Steht im Protokoll, damit niemand einen '
    'Fehler vermutet.':
        'Rewards on the channel are withheld. It is written to the log so nobody suspects a '
        'fault.',
    'Ohne Vorwarnung': 'Without a warning',
    'Bestrafungen kommen ohne die Vorwarnung, die sonst vorausgeht. Sticht das Privileg '
    '„Immer Vorwarnung" aus.':
        'Punishments come without the warning that otherwise precedes them. Beats the '
        'privilege "Always a warning".',
    'Auflage verhängen': 'Impose a sanction',
    'Auflage aufheben': 'Lift a sanction',
    'Schlüssel, optional :Stunden, :d (bis Tagesende), :rN (nach N bestandenen '
    'Durchgängen) — z. B. restrained:2 oder restrained:d:r3':
        'Key, optionally :hours, :d (until the end of the day), :rN (after N passed runs) - '
        'e.g. restrained:2 or restrained:d:r3',
    'Schlüssel': 'Key',
    # --- raw output / silent channel (doc 27) ----------------------------
    'Achtung': 'Attention',
    'Stärke am Gerät ist 0': 'Strength at the device is 0',
    'Die Anlage gibt aus, aber die Impulshöhe kommt vom Regler am Gerät — bei 0 kommt nichts '
    'an. Die Stärke setzt die Anlage nie, sie gehört der Trägerin.':
        'The plant is emitting, but the pulse height comes from the dial on the device - at 0 '
        'nothing arrives. The plant never sets the strength; it belongs to the wearer.',
    'Rohausgabe': 'Raw output',
    'Rohausgabe — für den stummen Kanal': 'Raw output - for the silent channel',
    'Rohausgabe starten': 'Start raw output',
    'Rohausgabe beendet.': 'Raw output stopped.',
    'läuft': 'running',
    'noch {n} s': '{n} s to go',
    'Sekunden': 'Seconds',
    'Kanal': 'Channel',
    'Das gibt wirklich aus. Fortfahren?': 'This really emits. Continue?',
    'Schreibt X/Y/Z unverändert an einen Kanal, ohne Wellenform, ohne Profil, ohne Umrechnung. '
    'Die Vorgabe 1/9/20 ist der Wert, den die Hersteller-Doku als 100 Hz mit 100 µs '
    'Impulsbreite nennt — der volle Ausschlag ihrer eigenen Beispiele. Kommt DABEI nichts an, '
    'liegt es nicht an der Anlage: dann steht die Stärke am Gerät auf 0, oder die Elektroden '
    'sitzen nicht.':
        'Writes X/Y/Z unchanged to one channel - no waveform, no profile, no conversion. The '
        'default 1/9/20 is what the manufacturer documentation calls 100 Hz at 100 us pulse '
        'width, the full swing of their own examples. If NOTHING arrives then, it is not the '
        'plant: the strength at the device is 0, or the electrodes are not seated.',
    'Rohausgabe gestartet: Kanal {ch}, X={x} Y={y} Z={z} ({us} µs) für {s} s. Kommt DABEI '
    'nichts an, liegt es nicht an der Umrechnung — dann steht die Stärke am Gerät auf 0 oder '
    'die Elektroden sitzen nicht.':
        'Raw output started: channel {ch}, X={x} Y={y} Z={z} ({us} us) for {s} s. If nothing '
        'arrives THEN, it is not the conversion - the strength at the device is 0 or the '
        'electrodes are not seated.',

    # --- doc 28: the strength belongs to the installation, the ceiling to the slave ---
    'Gerät meldet': 'device reports',
    'Decke': 'ceiling',
    'aus der Kalibrierung dem Sklaven — die Kurve fährt darunter':
        "from the slave's calibration - the curve runs below it",
    'keine gesetzt': 'none set',
    'ohne Decke gibt die Bridge nichts aus — die Kalibrierung steht bei dem Sklaven':
        'without a ceiling the bridge emits nothing - the calibration is on the slave',
    'Stärke kommt am Gerät nicht an': 'the strength is not reaching the device',
    'Stärke kommt nicht an': 'strength not arriving',
    'Die Bridge schreibt eine Stärke, das Gerät meldet trotzdem 0. Das ist ein Fehler, keine Erklärung — Verbindung, Generation und die Charakteristik PWM_AB2 prüfen.':
        'The bridge writes a strength and the device still reports 0. That is a fault, not an '
        'explanation - check the connection, the generation and the PWM_AB2 characteristic.',
    'Schreibt Stärke und X/Y/Z unverändert an einen Kanal, ohne Wellenform, ohne Profil, ohne Umrechnung. Die Vorgabe 1/9/20 ist der Wert, den die Hersteller-Doku als 100 Hz mit 100 µs Impulsbreite nennt — der volle Ausschlag ihrer eigenen Beispiele. Kommt DABEI nichts an, liegt es nicht an der Anlage: dann sitzen die Elektroden nicht, oder der Kanal ist ein anderer.':
        'Writes strength and X/Y/Z unchanged to one channel - no waveform, no profile, no '
        "conversion. The default 1/9/20 is what the maker's documentation calls 100 Hz with a "
        '100 us pulse width, the full swing of its own examples. If nothing arrives THEN, it is '
        'not the plant: the electrodes are not seated, or the channel is a different one.',
    'Damit tastet man sich an die Stärke heran': 'This is how you feel your way to the strength',
    'niedrig anfangen, langsam erhöhen, und die Zahl, bei der Schluss ist, bei dem Sklaven als Kalibrierung eintragen. Sie ist die einzige Obergrenze, die danach gilt.':
        'start low, raise slowly, and record the number where it stops as the calibration on the '
        'slave. It is the only ceiling that applies afterwards.',
    'Stärke %': 'strength %',
    'Kalibrierung fehlt — der Schritt gibt nichts aus':
        'calibration missing - this step emits nothing',
    'Kalibrierung fehlt — es gelten die Gerätevorgaben':
        'calibration missing - the device defaults apply',
    'Für diesen Sklave ist an diesem Gerät keine E-Stim-Stärke '
    'kalibriert — ohne sie gibt die Bridge nichts aus. Zum Prüfen ohne '
    'Sklave die Rohausgabe benutzen.':
        'No e-stim strength is calibrated for this slave at this device - without it the '
        'bridge emits nothing. To test without a slave, use the raw output.',
    'E-Stim {dev} ohne Kalibrierung - kein Reiz':
        'e-stim {dev} has no calibration - no stimulus',
    'E-Stim-Kalibrierung gelöscht — dieses Gerät gibt für sie nichts mehr aus.':
        'E-stim calibration deleted - this device will emit nothing for her from now on.',
    'Bitte zwei Zahlen zwischen 0 und 100 eintragen.': 'Please enter two numbers between 0 and 100.',
    'Beide Kanäle auf 0 heißt: keine Ausgabe. Zum Abschalten lieber löschen.':
        'Both channels at 0 means no output. To switch it off, delete it instead.',
    'E-Stim-Stärke gesetzt: A {a} %, B {b} %.': 'E-stim strength set: A {a} %, B {b} %.',
    'Bitte eine Stärke in Prozent angeben — ohne sie gibt die Bridge nichts aus.':
        'Please give a strength in percent - without it the bridge emits nothing.',
    'Rohausgabe gestartet: Kanal {ch}, Stärke {str} %, X={x} Y={y} Z={z} ({us} µs) '
    'für {s} s. Kommt DABEI nichts an, liegt es nicht an der Umrechnung — dann '
    'sitzen die Elektroden nicht oder der Kanal ist ein anderer.':
        'Raw output started: channel {ch}, strength {str} %, X={x} Y={y} Z={z} ({us} us) for '
        '{s} s. If nothing arrives THEN, it is not the conversion - the electrodes are not '
        'seated, or the channel is a different one.',

    # --- doc 31: pulse levels per slave ---
    # Capitalised: since doc 32 the text is also the LABEL of the level row,
    # not just an insert inside a message. As an insert, "Punishment: levels
    # set" reads just as correctly.
    'Bestrafung': 'Punishment',
    '{what}: Stufen zurückgesetzt — es gilt wieder 25/45/70.':
        '{what}: levels reset - 25/45/70 applies again.',
    'Bitte drei Zahlen zwischen 1 und 100 eintragen.': 'Please enter three numbers between 1 and 100.',
    'Die Stufen müssen aufsteigend sein: Stufe 1 ≤ Stufe 2 ≤ Stufe 3.':
        'The levels must ascend: level 1 <= level 2 <= level 3.',
    '{what}: Stufen gesetzt — {a} / {b} / {c} % ihrer Decke.':
        '{what}: levels set - {a} / {b} / {c} % of her ceiling.',

    # --- doc 32: profile per level and the try button ---
    'Setzen': 'Set',
    'Vorgabe': 'default',
    'Dieses Profil kennt die Anlage nicht: {p}': 'The installation does not know this profile: {p}',
    'Bestrafung und Belohnung würden dasselbe Profil benutzen ({p}). Dann sind sie '
    'derselbe Reiz in zwei Höhen — bitte für eine von beiden ein anderes wählen.':
        'Punishment and reward would use the same profile ({p}). Then they are the same stimulus '
        'at two heights - please pick a different one for one of them.',
    '{what}: Stufen gesetzt — {a} / {b} / {c} % ihrer Decke, Profil {p}.':
        '{what}: levels set - {a} / {b} / {c} % of her ceiling, profile {p}.',
    'Speichern und Stufe {n} einmal ausgeben — 2 s, wird nicht gebucht':
        'Save and emit level {n} once - 2 s, not booked',
    'Stufe {n} jetzt wirklich ausgeben? Die Elektroden müssen sitzen.':
        'Really emit level {n} now? The electrodes must be seated.',
    'auf 25/45/70 und das Vorgabeprofil zurücksetzen': 'reset to 25/45/70 and the default profile',
    'Stufen und Profil zurücksetzen?': 'Reset levels and profile?',
    'Gespeichert. Ausprobieren ging nicht: das Gerät ist nicht online.':
        'Saved. Trying it out was not possible: the device is not online.',
    'Gespeichert. Ausprobieren ging nicht: das Gerät gibt gerade schon etwas aus. '
    'Erst anhalten, dann proben.':
        'Saved. Trying it out was not possible: the device is already emitting. Stop it first, '
        'then probe.',
    'Gespeichert. Ausprobieren ging nicht: für dieses Gerät ist ihre Stärke noch nicht '
    'kalibriert — ohne sie gibt die Bridge nichts aus.':
        'Saved. Trying it out was not possible: her strength is not yet calibrated for this '
        'device - without it the bridge emits nothing.',
    'Gespeichert — und Stufe {n} läuft jetzt: {p} auf Kanal {ch}, {pct} % ihrer Decke, 2 s. '
    'Die Probe wird nicht gebucht.':
        'Saved - and level {n} is running now: {p} on channel {ch}, {pct} % of her ceiling, 2 s. '
        'The probe is not booked.',
    'Ihre Bridges tragen hier verschiedene Profile ein — dann benutzt die Zentrale die Vorgabe {p}, '
    'also an keinem Gerät das eingetragene. Bitte angleichen.':
        'Her bridges carry different profiles here - the central then uses the default {p}, so on '
        'no device the one entered. Please make them agree.',
    # --- doc 33: calibration run and tab cards ---------
    'Überblick': 'Overview',
    'Programme und Geräte': 'Programmes and devices',
    'Kalibrierung': 'Calibration',
    'Tagesablauf': 'Day',
    'Rang, Auflagen, Kanal': 'Rank, sanctions, channel',
    'Wochenplan': 'Weekly plan',
    'Verlauf': 'History',
    'Foto': 'Photo',
    'Bearbeiten': 'Edit',
    'Zugeordnet': 'Assigned',
    'Aktives Programm': 'Active programme',
    'keines': 'none',
    'Programm und Geräte passen zusammen — keine offenen Stellen.':
        'Programme and devices fit together - nothing open.',
    'Zugeordnet = darf gewählt werden. Genau eines ist aktiv und startet bei der Anmeldung.':
        'Assigned = may be chosen. Exactly one is active and starts at login.',
    'Gerät': 'Device',
    'auch bei {who} — bei gleichzeitiger Anmeldung behält es, wer zuerst da ist':
        'also with {who} - on simultaneous login it stays with whoever is there first',
    'Zuordnungen speichern': 'Save assignments',
    'Die Zentrale übernimmt Änderungen sofort — auch bei angemeldetem Sklaven (laufendes Programm '
    'behält seine Position).':
        'The central applies changes immediately - even while the slave is logged in (a running '
        'programme keeps its position).',
    'Winkel zwischen den Haltungen': 'Angle between the postures',
    'Kalibrieren': 'Calibrate',
    'Ruhe / größte Tiefe': 'Rest / greatest depth',
    'Tiefe nicht kalibriert': 'Depth not calibrated',
    '15 s messen: Sklaven so tief wie möglich. Jetzt starten?':
        'Measure for 15 s: slave as deep as possible. Start now?',
    'Tiefenkalibrierung löschen': 'Delete depth calibration',
    'Tiefenkalibrierung löschen?': 'Delete depth calibration?',
    'Stärke setzen': 'Set strength',
    'E-Stim-Kalibrierung löschen — das Gerät gibt für sie dann nichts mehr aus':
        'Delete e-stim calibration - the device will then emit nothing for her',
    'E-Stim-Kalibrierung löschen? Das Gerät gibt für sie danach nichts mehr aus.':
        'Delete e-stim calibration? The device will emit nothing for her afterwards.',
    'Diese Geräte bekommen bei der Anmeldung den Sklaven zugewiesen. Kalibriert wird auf der Karte Kalibrierung.':
        'These devices get the slave assigned at login. Calibrating is done on the Calibration card.',
    'Keine Programme vorhanden': 'No programmes yet',
    'anlegen': 'create one',
    'kein aktives Programm': 'no active programme',
    'Keine Geräte angelegt': 'No devices yet',
    'Modell': 'Model',
    'Status': 'Status',
    'E-Stim fehlt': 'e-stim missing',
    'kalibriert': 'calibrated',
    'fehlt': 'missing',
    'Haltung': 'Posture',
    'ja': 'yes',
    'nein': 'no',
    'Haltung kalibriert': 'Posture calibrated',
    'Haltung nicht kalibriert': 'Posture not calibrated',
    'nur': 'only',
    'nicht zugeordnet': 'not assigned',
    'Dieses Gerät ist ihr nicht zugeordnet — kalibrieren lässt es sich trotzdem.':
        'This device is not assigned to her - it can still be calibrated.',
    'E-Stim: Decke': 'E-stim: ceiling',
    'E-Stim: Impulsstufen und Profil': 'E-stim: impulse levels and profile',
    'nicht kalibriert — gibt nichts aus': 'not calibrated - emits nothing',
    'Höchste Impulshöhe je Kanal': 'Highest pulse height per channel',
    'Vorher mit der Rohausgabe herantasten — die Zahl ist eine Empfindung, kein Messwert.':
        'Feel your way there with the raw output first - the number is a sensation, not a measurement.',
    'Rohausgabe': 'Raw output',
    'Kalibrierdurchgang': 'Calibration run',
    'Kalibrierdurchgang läuft.': 'Calibration run in progress.',
    'Kalibrierdurchgang ist scharf gestellt.': 'Calibration run is armed.',
    'Sie ist angemeldet, aber es läuft kein Programm und kein Tagesplan — ihr Tag ist unberührt. '
    'Mit dem Abmelden ist der Durchgang zu Ende.':
        'She is logged in, but no programme and no day plan are running - her day is untouched. '
        'Logging out ends the run.',
    'Die nächste Anmeldung startet kein Programm und keinen Tag.':
        'The next login starts no programme and no day.',
    'gesetzt von {who}': 'set by {who}',
    'Steht seit {h} Stunden scharf. Wenn das nicht mehr gewollt ist, bitte abschalten — sonst verliert sie '
    'bei der nächsten Anmeldung ihren Tagesstart.':
        'Armed for {h} hours. If that is no longer wanted, please switch it off - otherwise she loses her '
        'day start at the next login.',
    'Kalibrieren geht nur angemeldet — sonst sind ihr die Geräte nicht zugewiesen. Eine normale Anmeldung '
    'öffnet aber ihren Tag, und vorzeitiges Abmelden gilt als Kapitulation. Dieser Schalter macht die '
    'NÄCHSTE Anmeldung zu einem reinen Kalibrierdurchgang: kein Programm, kein Tagesplan, keine Routine, '
    'keine Punkte. Mit dem Abmelden ist er zu Ende und sie kann sich ganz normal anmelden — ihr Tag ist '
    'unberührt.':
        'Calibrating only works while she is logged in - otherwise the devices are not assigned to her. But '
        'a normal login opens her day, and logging out early counts as capitulation. This switch turns the '
        'NEXT login into a pure calibration run: no programme, no day plan, no routine, no points. Logging '
        'out ends it and she can log in normally afterwards - her day is untouched.',
    'läuft gerade': 'running now',
    'scharf gestellt': 'armed',
    'aus': 'off',
    'Abschalten': 'Switch off',
    'Für die nächste Anmeldung scharf stellen': 'Arm for the next login',
    'Die nächste Anmeldung wird ein reiner Kalibrierdurchgang. Fortfahren?':
        'The next login will be a pure calibration run. Continue?',
    'Von Hand bestrafen und belohnen geht im Durchgang weiter (Karte „Rang, Auflagen, Kanal"), und alles '
    'wird protokolliert — nur gewertet wird nichts.':
        'Punishing and rewarding by hand still works during the run (card "Rank, sanctions, channel"), and '
        'everything is logged - only nothing is scored.',
    'Kalibrierdurchgang scharf gestellt. Die nächste Anmeldung startet kein Programm und keinen Tag; mit '
    'dem Abmelden ist der Durchgang zu Ende und sie kann sich normal anmelden.':
        'Calibration run armed. The next login starts no programme and no day; logging out ends the run and '
        'she can log in normally.',
    'Kalibrierdurchgang abgeschaltet — die nächste Anmeldung läuft wieder normal.':
        'Calibration run switched off - the next login runs normally again.',
    'Dafür fehlt Migration 014 — die Zentrale spielt sie beim nächsten Start ein.':
        'Migration 014 is missing for this - the central applies it at the next start.',

    'Prozent ihrer Decke, nicht der Geräteleistung. Bestrafung läuft auf Kanal A, '
    'Belohnung auf B. Das Profil bestimmt die Wellenform, nicht die Höhe — am Po trägt eine andere als an der '
    'Scham. ▶ gibt die Stufe einmal aus; das zählt auf den Tagesvorrat, wird aber nicht gebucht.':
        'Percent of HER ceiling, not of the device power. Punishment runs on channel A, reward on B. '
        'The profile sets the WAVEFORM, not the height - a different one carries on the buttocks than '
        'on the genitals. The play button emits the level once; that counts against the day budget, '
        'but is not booked.',
    # --- tab card "Ueberblick" and device list (2.0) -----------------------
    #
    # Rule (Philine 2026-09-13): German is the master language, and whatever is
    # already English within German stays as it stands — "Bridge", never
    # "Bruecke". The other way round that means here: MAC, chip and firmware
    # need no translation, they are the same word in both languages.
    # Units in the waveform editor. They are listed although they read the
    # same in both languages — otherwise the coverage check reports them as a
    # gap, and a check that keeps raising false alarms gets overlooked
    # sooner or later.
    's': 's',
    'min': 'min',
    '%': '%',

    'Aktuelle Aufgabe': 'Current task',
    'Folgende Aufgaben': 'Upcoming tasks',
    'Stand der Geräte': 'Devices',
    'Nicht angemeldet.': 'Not logged in.',
    'Angemeldet, gerade läuft nichts.': 'Logged in, nothing running.',
    'Nichts offen in dieser Woche.': 'Nothing open this week.',
    'Keine Geräte zugeordnet.': 'No devices assigned.',
    'kein Foto': 'no photo',
    'Tag': 'Day',
    'danach': 'then',
    'noch {n} min': '{n} min left',
    'KALIBRIERUNG': 'CALIBRATION',
    'Kein Programm, kein Tag — nichts wird gewertet.':
        'No program, no day - nothing is scored.',
    'online': 'online',
    'gesperrt': 'blocked',
    'MAC': 'MAC',
    'Chip': 'Chip',
    'Firmware': 'firmware',
    'zuletzt': 'last seen',
    'die Schreibsperre der MAC ist gebrannt': 'the MAC write protection is burned',
    'efuse-MAC des Chips — daraus wird die device_UUID abgeleitet':
        'efuse MAC of the chip - the device_UUID is derived from it',
    'efuse-MAC:': 'efuse MAC:',
    'Kommt aus der Meldung des Geräts und wird mit gespeichert — aus ihr ist die '
    'device_UUID abgeleitet.':
        'Comes out of the device\'s own announcement and is saved along with it - the '
        'device_UUID is derived from it.',
    'Aus ihr ist die device_UUID abgeleitet. Meldet sich unter dieser Adresse ein '
    'anderer Chip, wird das Gerät gesperrt statt still übernommen.':
        'The device_UUID is derived from it. If a different chip reports under this '
        'address, the device is blocked rather than silently taken over.',
    'Gemeldet, aber keinem Gerät zugeordnet': 'Seen, but not assigned to any device',
    'Diese Geräte haben sich mit einer MAC gemeldet, die in keinem Eintrag steht. '
    'Sie werden NICHT von selbst aufgenommen — so wie ein unbekannter RFID-Tag auch '
    'nicht von selbst zu einem Sklave wird. Wer dazugehört, wird hier bewusst '
    'angelegt.':
        'These devices reported a MAC that is in no record. They are NOT taken in by '
        'themselves - just as an unknown RFID tag does not become a slave by '
        'itself. Whoever belongs here is added deliberately.',

    # --- messages of the supervisor interface (phase 5) --------------------
    'Ränge gespeichert.': 'Ranks saved.',
    'Punktesystem gespeichert — gilt für alle folgenden Durchgänge.':
        'Scoring saved - applies to every following run.',
    'Tagesmodell nicht verfügbar — Migration 007 fehlt.':
        'Day model unavailable - the day_plans/rules tables are missing.',
    'Regelwerk nicht verfügbar — Migration 007 fehlt.':
        'Rule set unavailable - the day_plans/rules tables are missing.',
    'Alle Vorschläge bestätigt.': 'All proposals confirmed.',
    'PDF-Erzeugung nicht verfügbar (reportlab fehlt) — Seite im Browser drucken.':
        'PDF generation unavailable (reportlab missing) - print the page from the browser.',
    'Tagesplan gelöscht — betroffene Sklaven fallen auf die Vorgabe zurück.':
        'Day plan deleted - affected slaves fall back to the default.',
    'Unbekannte oder nicht trainierbare Aufgabe.': 'Unknown task, or one that cannot be trained.',
    'Herausforderung gelöscht.': 'Challenge deleted.',
    'Tagesplan angelegt — jetzt Blöcke hinzufügen.': 'Day plan created - now add blocks.',
    'Für diese Woche läuft schon eine offene Herausforderung in dieser Aufgabe — entscheide oder lösche sie erst, sonst zählt derselbe Durchgang für beide.':
        'An open challenge for this task is already running this week - decide or delete it first, otherwise the same run counts for both.',
    'EMERGENCY an alle Geräte gesendet. Geräte bleiben bis zum Aus-/Einschalten gesperrt.':
        'EMERGENCY sent to every device. They stay frozen until power is cycled.',
    'Foto gespeichert — die Anzeige nutzt es ab sofort.':
        'Photo saved - the display uses it from now on.',
    'Gerät gelöscht.': 'Device deleted.',
    'EMERGENCY nicht ausgelöst: Bestätigungswort fehlt.':
        'EMERGENCY not triggered: the confirmation word is missing.',
    'Das aktive Programm muss zugeordnet sein — Zuordnung ergänzt.':
        'The active program must be assigned - the assignment was added.',
    'Keine Datei gewählt.': 'No file chosen.',
    'Kalibrierung gelöscht.': 'Calibration deleted.',
    'Tiefenkalibrierung gelöscht.': 'Depth calibration deleted.',
    'Schritt gelöscht.': 'Step deleted.',
    'Name und RFID sind Pflicht.': 'Name and RFID are required.',
    'Name ist Pflicht.': 'Name is required.',
    'device_UUID und ein gültiges Modell sind Pflicht.':
        'device_UUID and a valid model are required.',
    'CSRF-Token fehlt oder ist ungültig': 'CSRF token missing or invalid',
    'Diese RFID ist bereits einem anderen Sklaven zugeordnet.':
        'This RFID already belongs to another slave.',
    'Diese device_UUID ist schon angelegt.': 'This device_UUID already exists.',
    'Ein Tagesplan mit diesem Namen gibt es schon.': 'A day plan with this name already exists.',
    'Ein anderer Tagesplan hat diesen Namen schon.': 'Another day plan already has this name.',
    'Ein Programm mit diesem Namen gibt es schon.': 'A program with this name already exists.',

    # --- interface texts that up to 2.0 never went through the translation
    # at all (phase 5). They sat as raw German text in the templates and
    # therefore showed up in German on the English page as well — which
    # nobody ever reports, because it does not look broken, only
    # unfinished.
    'Ablauf: der Reihe nach. WAIT und SHOCK erzeugen Wartezeiten; Modi und das Magnetschloss laufen im Gerät weiter, bis REMOTE_CONTROL (Modus aus), UNLOCK oder ihre Maximaldauer greift — deshalb gehört hinter einen Modus oder MAGLOCK ein WAIT über die gewünschte Dauer. Im Tagesmodell wählt die Zentrale das Programm zu einer Wochenplanaufgabe selbst und überschreibt dabei deren Zielwert; die Aufgabenliste hier ist auf die Geräte gefiltert, die in der Anlage eingetragen sind.':
        'Sequence: in order. WAIT and SHOCK create waiting times; modes and the magnetic lock keep running in the device until REMOTE_CONTROL (mode off), UNLOCK or their maximum duration takes effect - which is why a WAIT over the intended duration belongs after a mode or MAGLOCK. In the day model the central unit picks the program for a weekly task itself and overrides its target; the task list here is filtered to the devices registered in the installation.',
    'Aktion enthält':
        'Action contains',
    'Alle im Feld bekommen die Aufgabe als':
        'Everyone in the field gets the task as',
    'Alles lösen, Geräte einfrieren bis Power-Cycle. Der Not-Aus-Bumper bleibt der harte Weg.':
        'Release everything, freeze devices until power is cycled. The emergency bumper stays the hard way.',
    'Alte Vorschläge gültig setzen':
        'Mark old proposals valid',
    'Alter der Werte':
        'Age of the values',
    'Alternativsatz (neutral, z. B. für die Museumsanzeige)':
        'Alternative set (neutral, e.g. for the museum display)',
    'Aufgaben je Tag) — er ist':
        'tasks per day) - it is',
    'Aufgaben muss\n      der Sklave in der Woche mindestens mit der Mindestnote bestehen.':
        'tasks the slave must pass in the week, at least with the minimum grade.',
    'Aufstieg nur, wenn alle Plan- und Nachsitz-Aufgaben der\n      Woche bestanden sind.':
        'Promotion only if every plan and detention task of the week is passed.',
    'Automatik: zwei A/B in Folge → Stufe +1 (Ziel schwerer, z. B. Dauer +10 %, Toleranz enger, Störreiz +1); zwei D–F in Folge → −1. Die Stufe fließt in die Punkte ein (Basis = Stufe × 10).':
        'Automatic: two A/B in a row -> level +1 (harder target, e.g. duration +10 %, tighter tolerance, distraction +1); two D-F in a row -> -1. The level feeds into the points (base = level x 10).',
    'Begründung':
        'Reason',
    'Beide Haltungen messen, dann erscheint hier die Qualität.':
        'Measure both poses, then the quality appears here.',
    'Bemerkung der Aufsicht':
        "Supervisor's remark",
    'Bemerkung der Aufsicht (erscheint im Zeugnis)':
        "Supervisor's remark (appears in the report)",
    'Beschreibung (wird auf der Anzeige genannt)':
        'Description (named on the display)',
    'Bestleistung der Disziplin':
        'Personal best of the discipline',
    'Bezeichnung (frei, z. B. „Halsband 1“ oder Client-ID)':
        'Label (free, e.g. „Collar 1“ or client ID)',
    'Der Sklave hat kein Gerät mit dieser Funktion — er kann die Aufgabe nicht erfüllen':
        'The slave has no device with this capability - the task cannot be fulfilled',
    'Die Zentrale erzeugt aus Rang, Stufen und Verlauf einen tagesfüllenden Plan — sofort gültig':
        'The central unit builds a full day from rank, levels and history - effective immediately',
    'Durchgang mit Note und Punkten im Logbuch; Aufgabenstufe des Sklaven verschärft die Parameter':
        "Run with grade and points in the logbook; the slave's task level tightens the parameters",
    'Durchgänge trainierbarer Aufgaben mit Note und Punkten':
        'Runs of trainable tasks, with grade and points',
    'Ein Durchgang erfüllt eine Planaufgabe, wenn Ziel ≥ Planziel, Note bestanden und Bestrafungen ≤ erlaubt. Alle Plan-/Nachsitz-Aufgaben bestanden = Wochenbonus.':
        'A run fulfils a plan task when target >= plan target, grade passed and punishments <= allowed. All plan and detention tasks passed = weekly bonus.',
    'Ein Kalibrierdurchgang zählt nicht als Anmeldung':
        'A calibration run does not count as a login',
    'Ein neuer Plan startet ohne Blöcke; ohne Blöcke füllt die Zentrale den Tag mit freiem Training.':
        'A new plan starts without blocks; without blocks the central unit fills the day with free training.',
    'Export für das Inhaltsteam':
        'Export for the content team',
    'Foto für die Anzeige':
        'Photo for the display',
    'Gerät (UUID-Anfang)':
        'Device (start of UUID)',
    'Gerät fehlt':
        'Device missing',
    'Gerät löschen':
        'Delete device',
    'Geräte online':
        'Devices online',
    'Gleichstand: weniger Bestrafungen, dann frühere Zeit. Aufsichts-Einträge geben keine Ranglistenpunkte; Rahmen (V-Cage, Schloss, Timer, Zufall) zählen nicht.':
        'Tie: fewer punishments, then the earlier time. Supervisor entries give no leaderboard points; frames (V-Cage, lock, timer, random) do not count.',
    'Hauptsatz (Vorgabe: demütigend)':
        'Main set (default: humiliating)',
    'Hier steht, was bei welchem Anlass passiert — nichts davon ist fest\n  im Programm verdrahtet. Jede Regel prüft eine Bedingung und führt eine Wirkung aus; treffen mehrere Regeln zu,\n  laufen sie alle in der Reihenfolge ihrer Ordnungszahl.':
        'This is what happens on which occasion - none of it is wired into the program. Every rule checks a condition and carries out an effect; where several rules match, they all run in the order of their position number.',
    'Hinweise zum Ablauf':
        'Notes on the sequence',
    'In der Anlage ist überhaupt kein Gerät mit dieser Funktion eingetragen':
        'No device with this capability is registered in the installation at all',
    'JPEG oder PNG, Hochformat empfohlen (max. 8 MB)':
        'JPEG or PNG, portrait recommended (max. 8 MB)',
    'Jetzt anstoßen (Wochenplan)':
        'Trigger now (weekly plan)',
    'Kein Plan für diese Woche — auf der Sklavenseite anlegen oder Vorschlag erzeugen.':
        'No plan for this week - create one on the slave page, or generate a proposal.',
    'Kein Sklavenfeld — die Herausforderung wird beim Entscheiden ungültig.':
        'No field of slaves - the challenge becomes void when decided.',
    'Kein Sklavenfeld.':
        'No field of slaves.',
    'Keine Einträge.':
        'No entries.',
    'Keine Geräte angelegt.':
        'No devices registered.',
    'Keine Parameter.':
        'No parameters.',
    'Keine Regeln — dann passiert außer der Bewertung nichts.':
        'No rules - then nothing happens beyond the scoring.',
    'Laufende Durchgänge':
        'Running sessions',
    'Live-Werte für 90 s':
        'Live values for 90 s',
    'Läuft sonst automatisch am Montag':
        'Otherwise runs automatically on Monday',
    'Löschen eines Sklaven (Sklaven → Bearbeiten → Löschen) entfernt Logbuch, Pläne, Rang, Abzeichen, Kalibrierung und Foto mit (ON DELETE CASCADE). Ein bereits erzeugter Export bleibt davon unberührt. Salz:':
        'Deleting a slave (Slaves -> Edit -> Delete) removes logbook, plans, rank, badges, calibration and photo with them (ON DELETE CASCADE). An export already produced is unaffected. Salt:',
    'Namen und Aufstiegsbedingungen (Doc 14 §4a)':
        'Names and promotion conditions (doc 14 §4a)',
    'Noch kein Gerät gesehen.':
        'No device seen yet.',
    'Noch kein Tagesplan angelegt.':
        'No day plan created yet.',
    'Noch keine Blöcke — unten einen hinzufügen.':
        'No blocks yet - add one below.',
    'Noch keine Durchgänge.':
        'No runs yet.',
    'Noch keine Programme.':
        'No programs yet.',
    'Noch keine Schritte. Rechts einen hinzufügen.':
        'No steps yet. Add one on the right.',
    'Noch keine gewerteten Durchgänge in dieser Woche.':
        'No scored runs this week yet.',
    'Noch keine gewerteten Durchgänge.':
        'No scored runs yet.',
    'Noch offen: Platzierungen stehen erst\n  nach der Entscheidung fest.':
        'Still open: placings are only fixed after the decision.',
    'Note: schlechtere Teilnote aus erreichtem Ziel und Bestrafungen (0 = A, ≤ erlaubt = B, ≤ 2× = C …). Punkte = Stufe × Basis × Notenfaktor − Malus je Bestrafung + Boni (Bestleistung, Serie, Wochenplan). Je Aufgabe und Tag zählen nur die besten Durchgänge für die Rangliste.':
        'Grade: the worse of the two part grades from target reached and punishments (0 = A, <= allowed = B, <= 2x = C ...). Points = level x base x grade factor - malus per punishment + bonuses (personal best, streak, weekly plan). Per task and day, only the best runs count for the leaderboard.',
    'Nur wirksam, wenn der Sklave angemeldet ist (dann horchen seine Reizgeber). Zählt für den laufenden Durchgang; Mindestpause und Tageslimit des Kanals gelten. Im Kalibrierdurchgang geht das weiter — dort gibt es nur keinen Durchgang, für den es zählt.':
        "Only effective while the slave is logged in (then her stimulus devices are listening). Counts towards the running session; the channel's minimum gap and daily limit apply. In a calibration run this still works - there is simply no session for it to count towards.",
    'Online, aber nicht angelegt':
        'Online, but not registered',
    'Plan vollständig':
        'Plan complete',
    'Platzierungen gelten für die Herausforderung und die Wochenrangliste; „nicht angetreten“ nur für die Herausforderung.':
        'Placings apply to the challenge and to the weekly leaderboard; „did not start“ only to the challenge.',
    'Programm löschen':
        'Delete program',
    'Punkte = Aufgabenstufe × base_per_level × Notenfaktor − malus_punish × Bestrafungen (nie unter 0) + bonus_best bei neuer persönlicher Bestleistung + Serienbonus (bonus_streak_step je Folgetag mit Training, höchstens bonus_streak_cap) + bonus_week beim vollständigen Wochenplan + bonus_challenge für den Sieger einer Herausforderung. Rangliste: je Aufgabe und Tag zählen die besten N Durchgänge — N steht seit 2.3 als Budget „Durchgänge“ (Seite Budgets). Nachsitzen ab detention_punish Bestrafungen in der Woche; Letzter der Wochenrangliste bekommt Nachsitzen, wenn detention_last = 1. Die Sicherheitsgrenzen des Bestrafungskanals (Mindestpause, Tageslimit) stehen in config.ini [safety] und sind hier bewusst nicht änderbar. Der Rang selbst gibt keine Punkte.':
        'Points = task level x base_per_level x grade factor - malus_punish x punishments (never below 0) + bonus_best for a new personal best + streak bonus (bonus_streak_step per following day with training, at most bonus_streak_cap) + bonus_week for a complete weekly plan + bonus_challenge for the winner of a challenge. Leaderboard: per task and day the best N runs count — since 2.3, N is the budget "Runs" (page Budgets). Detention from detention_punish punishments in the week; the last of the weekly leaderboard gets detention if detention_last = 1. The safety limits of the punishment channel (minimum gap, daily limit) live in config.ini [safety] and are deliberately not editable here. The rank itself gives no points.',
    'Rang 10 ist der höchste: er wird gehalten, nicht mehr aufgestiegen. Änderungen wirken sofort auf Anzeige, Prognose und die nächste Wochenbewertung.':
        'Rank 10 is the highest: it is held, not promoted beyond. Changes take effect immediately on the display, the forecast and the next weekly review.',
    'STOPP alle Geräte':
        'STOP all devices',
    'Schritt anhängen':
        'Append step',
    'Schritt hinzufügen':
        'Add step',
    'Seit dem Start des Webinterface noch keine Ereignisse.':
        'No events since the web interface started.',
    'Sicherer Zustand, Geräte bleiben bedienbar.':
        'Safe state, devices stay operable.',
    'Sklave geht auf alle viere, Kopf in der normalen Haltung.':
        'Slave goes on all fours, head in the normal posture.',
    'Sklaven löschen':
        'Delete slave',
    'Vollständiges Protokoll →':
        'Full audit log →',
    'Vorgabe für alle ohne eigene Zuordnung':
        'Default for everyone without their own assignment',
    'Vorschau für':
        'Preview for',
    'Wann die Regel geprüft wird.':
        'When the rule is checked.',
    'Was geübt wird. Wählbar ist nur, was zu den\n      Geräten des Sklaven passt; alles andere kann er nicht erfüllen.':
        "What is practised. Only what fits the slave's devices can be chosen; anything else cannot be fulfilled.",
    'Was hier eingestellt wird':
        'What is set here',
    'Welche Note ein Durchgang mindestens haben muss, damit die\n      Aufgabe für den Aufstieg zählt (A ist die beste).':
        'The minimum grade a run must reach for the task to count towards promotion (A is the best).',
    'Wer nicht angetreten ist, steht hinten':
        'Whoever did not start comes last',
    'Wie viele Bestrafungen der Durchgang verträgt, bevor er als\n      nicht bestanden gilt. Die Hüllkurven der Geräte und':
        'How many punishments the run tolerates before it counts as failed. The envelopes of the devices and',
    'Zahlen und Schalter des Logbuchs (Tabelle scoring)':
        'Numbers and switches of the logbook (table scoring)',
    'Zurück':
        'Back',
    'Zweiter Namenssatz für dieselben Ränge — für die\n      Museumsanzeige, wo der Hauptsatz zu drastisch ist. Unten wird umgeschaltet.':
        'A second set of names for the same ranks - for the museum display, where the main set is too drastic. Switched below.',
    'auch wenn in dieser Woche schon eine offene Herausforderung in derselben Aufgabe läuft':
        'even if an open challenge in the same task is already running this week',
    'bestandene Aufgaben in der Woche (Mindestnote), davon Wochenbester in n Aufgaben (Vergleich mit den anderen Sklaven, relativ zur Aufgabenstufe; zählt nur, wenn ≥ 2 Sklaven die Aufgabe gemacht haben). „Aufgaben = 0“ heißt: alle Aufgaben des Wochenplans. Abstieg: Wochenplan nicht vollständig oder kein Training — ohne Schonfrist.':
        'passed tasks in the week (minimum grade), of which best of the week in n tasks (compared with the other slaves, relative to the task level; counts only if >= 2 slaves did the task). „Tasks = 0“ means: every task of the weekly plan. Demotion: weekly plan incomplete or no training - without grace.',
    'bestätigen':
        'confirm',
    'device_UUID (MQTT-Topic-Segment, aus dem hello des Geräts)':
        "device_UUID (MQTT topic segment, from the device's hello)",
    'dieselbe\n  Aufgabe mit demselben Ziel in den Wochenplan. Gewertet wird der beste gewertete Durchgang der Woche, in dem das Ziel\n  erreicht wurde. Reihenfolge:':
        'the same task with the same target into the weekly plan. Scored is the best scored run of the week in which the target was reached. Order:',
    'diesen Sklaven mit diesem Halsband':
        'this slave with this collar',
    'entfernt auch Programm- und Gerätezuordnungen; das Protokoll bleibt.':
        'also removes program and device assignments; the audit log stays.',
    'ist ein':
        'is a',
    'kein Gerät in der Anlage':
        'no such device in the installation',
    'kein Plan':
        'no plan',
    'n. gezählt':
        'th counted',
    'nicht angelegt':
        'not registered',
    'noch keine':
        'none yet',
    'noch nicht gemessen':
        'not measured yet',
    'nur möglich, wenn es keinem Sklaven zugeordnet ist.':
        'only possible while it is assigned to no slave.',
    'nur möglich, wenn kein Sklave es zugeordnet hat.':
        'only possible while no slave has it assigned.',
    'persönliche Bestleistung':
        'personal best',
    'sofort gültig':
        'effective immediately',
    'stehen\n      darüber — eine Zahl hier hebt keine Grenze an.':
        'stand above it - a number here raises no limit.',
    'stehen über jeder Regel':
        'stand above every rule',
    'von der Aufsicht gesetzt; Automatik pausiert bis zum nächsten Durchgang':
        'set by the supervisor; the automatic adjustment pauses until the next run',
    'wofür diese Regel gedacht ist':
        'what this rule is meant for',
    'zählt nicht für die Rangliste (Anti-Grinding)':
        'does not count for the leaderboard (anti-grinding)',
    'Ältere Vorschläge dieser Woche gültig setzen':
        'Mark older proposals of this week valid',
    'älter →':
        'older →',
    'öffnen':
        'open',
    'überschreibt':
        'overrides',
    '„Erkannt als“ rechnet mit den gespeicherten Haltungen genauso wie das Halsband (ohne Hysterese). Sklaven aufstehen und hinknien lassen — wechselt die Anzeige zuverlässig, passt die Kalibrierung.':
        '„Detected as“ uses the stored poses exactly as the collar does (without hysteresis). Have the slave stand up and kneel down - if the display switches reliably, the calibration fits.',
    '„ungültig“ = ein Schritt passt nicht zur Aktions-Registry; die Zentrale startet solche Programme nicht (Meldung am LCD).':
        '„invalid“ = a step does not match the action registry; the central unit does not start such programs (message on the LCD).',

    # --- phase 5: text that never went through _() (2026-09-14) ---------
    ') in einer ZIP-Datei. Sklaven erscheinen als stabile Pseudonyme (T + 8 Hex-Zeichen aus einem Salz in der config.ini) — keine Namen, keine RFID, keine Fotos. Damit lassen sich Verhalten, Noten, Bestrafungen und Rangverläufe auswerten, ohne Personen zu erkennen.':
        ') in one ZIP file. Slaves appear as stable pseudonyms (T + 8 hex characters from a salt in config.ini) - no names, no RFID, no photos. That allows behaviour, grades, punishments and rank histories to be studied without recognising anyone.',
    '); in der Datenbank steht nur, welches physische Gerät welches Modell hat. Die Funktionen bestimmen, welche Programmschritte und Wochenaufgaben mit diesem Gerät überhaupt möglich sind. Ist ein Gerät online, wird die Liste mit dem verglichen, was seine Firmware meldet:':
        '); the database only records which physical device is which model. The functions decide which programme steps and weekly tasks are possible with this device at all. When a device is online, the list is compared with what its firmware reports:',
    ', Umfang':
        ', size',
    ', dann die':
        ', then the',
    ', dann die Note, dann weniger Bestrafungen, dann der frühere Durchgang.':
        ', then the grade, then fewer punishments, then the earlier run.',
    '. Die Zentrale':
        '. The central unit',
    '. Sklaven ohne passendes Gerät sind markiert — sie können nicht antreten und würden als Niederlage gewertet.':
        '. Slaves without a suitable device are marked - they cannot take part and would be counted as a defeat.',
    '. Vorzeitiges Abmelden gilt als':
        '. Logging off early counts as',
    ': solange es reicht, kommt die nächste Aufgabe im selben Block. Die Vorlage wird wiederholt, bis die Tagesdauer des Sklaven abgelaufen ist. Über allem stehen die harten Grenzen aus':
        ": as long as there is time, the next task follows in the same block. The template repeats until the slave's day is over. Above all of it stand the hard limits from",
    '; eine erneute Anmeldung am selben Tag geht nur, wenn sie hier erlaubt ist.':
        '; logging in again on the same day is only possible if it is allowed here.',
    '= Teil der Bestenliste über alle Sklaven.':
        '= part of the leaderboard across all slaves.',
    '= abgeschlossen. Der Plan gilt als vollständig, wenn alle Plan- und Nachsitz-Aufgaben bestanden sind.':
        '= finished. The plan counts as complete when every plan and detention task has been passed.',
    '= aus einer Regel entstanden,':
        '= created by a rule,',
    '= das Modell kann es, die Firmware meldet es nicht (zu alte Firmware),':
        '= the model can do it, the firmware does not report it (firmware too old),',
    '= die Firmware kann mehr, als die Registry kennt.':
        '= the firmware can do more than the registry knows.',
    '= regulär,':
        '= regular,',
    '= von der Zentrale erzeugt, wird montags automatisch aktiv;':
        '= created by the central unit, becomes active automatically on Monday;',
    '= zählt;':
        '= counts;',
    'an; danach führt die Zentrale ihn durch den Tag. Die':
        'to start; from then on the central unit takes him through the day. The',
    'an; danach führt die Zentrale ihn durch den Tag. Hier steht nur die':
        'to start; from then on the central unit takes him through the day. Here stands only the',
    'den Wert im Programm, damit Plan und Programm nicht auseinanderlaufen.':
        'the value in the programme, so plan and programme do not drift apart.',
    'den Wochenplan über die Woche: in jedem Trainingsblock nimmt sie die nächste offene Aufgabe und lässt dazu das passende Programm des Sklaven laufen. Es gibt hier keinen Startknopf — der Tag beginnt mit der Anmeldung.':
        "the weekly plan across the week: in every training block it takes the next open task and runs the slave's matching programme with it. There is no start button here - the day begins with logging in.",
    'in den Wochenplan der gewählten Woche.':
        'into the weekly plan of the chosen week.',
    'in den nächsten':
        'in the next',
    'in der config.ini (sonst das Web-Secret; ohne festes Secret wechseln die Pseudonyme bei jedem Neustart des Webinterface).':
        'in config.ini (otherwise the web secret; without a fixed secret the pseudonyms change every time the web interface restarts).',
    'und wartet nicht auf eine Bestätigung; die Aufsicht ändert, ergänzt oder löscht ihn hier. Ein Plan gilt als vollständig, wenn alle Plan- und Nachsitz-Aufgaben bestanden sind; unvollständig = Abstieg bei der Wochenbewertung.':
        'and does not wait for confirmation; the supervisor changes, extends or deletes it here. A plan counts as complete when every plan and detention task has been passed; incomplete = demotion at the weekly review.',
    'und werden der Zentrale mit dem PET-Schritt mitgegeben.':
        'and are handed to the central unit with the PET step.',
    '— Verweigerung ist eine Niederlage. Entschieden wird automatisch, sobald jeder im Feld ein Ergebnis hat, sonst spätestens bei der Wochenbewertung. Was Platz 1, Platz 2 und die hinteren Plätze bekommen, steht nicht hier, sondern unter':
        '- refusing is a defeat. It is decided automatically as soon as everyone in the field has a result, at the latest at the weekly review. What first place, second place and the lower places receive is not set here but under',
    '— eine Regel wählt eine Stärkestufe, sie kann keine Grenze anheben. Bestrafungen und Belohnungen brauchen einen anwesenden Sklaven; ist er nicht angemeldet, warten sie bis zu seinem nächsten Tagesbeginn.':
        '- a rule picks a strength step, it cannot raise a limit. Punishments and rewards need a slave who is present; if he is not logged in they wait until his next day begins.',
    '— er öffnet keinen Tag (Karte Kalibrierung).':
        '- it does not open a day (Calibration card).',
    '— kein Fehler, aber fast sicher nicht so gemeint:':
        '- not an error, but almost certainly not what was meant:',
    '— sie bestimmen, welche Programmschritte und Wochenaufgaben mit dem Gerät möglich sind':
        '- they decide which programme steps and weekly tasks are possible with the device',
    '— was in den Trainingsblöcken passiert, nimmt die Zentrale aus dem Wochenplan. Ein Block der Art':
        '- what happens in the training blocks comes from the weekly plan. A block of the kind',
    '— zweite Rangliste: dieselbe Aufgabe für alle':
        '- second leaderboard: the same task for everyone',
    'Der Zielwert der Aufgabe in ihrer eigenen Einheit — Dauer in Sekunden/Minuten, sonst eine Anzahl (Treffer, Runden, Wiederholungen). Der Zielwert der Planaufgabe':
        "The task's target in its own unit - duration in seconds/minutes, otherwise a count (hits, rounds, repetitions). The target of the plan task",
    'Die Hüllkurven der Geräte und die Grenzen aus':
        'The device envelopes and the limits from',
    'Die Zeile eines Rangs beschreibt die Bedingung für den Aufstieg':
        "A rank's row describes the condition for promotion",
    'Die Zentrale erzeugt den Plan sonntags automatisch für die nächste Woche (Einstellung':
        'The central unit creates the plan automatically on Sunday for the coming week (setting',
    'Eine Herausforderung setzt':
        'A challenge sets',
    'In so vielen Aufgaben muss er der Beste der Woche sein — verglichen wird relativ zur Aufgabenstufe, und nur wenn mindestens zwei Sklaven die Aufgabe gemacht haben. 0 = wird nicht verlangt.':
        'He must be best of the week in this many tasks - compared relative to the task level, and only when at least two slaves have done the task. 0 = not required.',
    'Modelle und Fähigkeiten sind Code (':
        'Models and capabilities are code (',
    'Nichts angekreuzt =':
        'Nothing ticked =',
    'Rang: mindestens so viele':
        'Rank: at least this many',
    'So viele':
        'This many',
    'Der Wochenplan sagt':
        'The weekly plan says',
    '+ Neu':
        '+ New',
    '0 = alle':
        '0 = all',
    'ABSTIEG':
        'DEMOTION',
    'AUFSTIEG':
        'PROMOTION',
    'Abbrechen':
        'Cancel',
    'Ablauf':
        'Sequence',
    'Abstieg':
        'Demotion',
    'Aufstieg':
        'Promotion',
    'Aktion':
        'Action',
    'Aktiver Namenssatz':
        'Active name set',
    'Aktueller Block':
        'Current block',
    'Alternativname':
        'Alternative name',
    'Angemeldete Sklaven':
        'Slaves logged in',
    'Anmelden':
        'Log in',
    'Anmeldung · Punisher Aufsicht':
        'Login · Punisher supervision',
    'Aufgaben':
        'Tasks',
    'Aufgaben des Wochenplans.':
        'tasks of the weekly plan.',
    'Bedeutung':
        'Meaning',
    'Beginn / geplantes Ende':
        'Start / planned end',
    'Benutzer':
        'User',
    'Beschreibung':
        'Description',
    'Best':
        'Best',
    'Bewegung':
        'Movement',
    'Bonus':
        'Bonus',
    'Bonus: Wochenplan':
        'Bonus: weekly plan',
    'Details':
        'Details',
    'Drehrate':
        'Rotation rate',
    'Drucken':
        'Print',
    'Eingriff':
        'Intervention',
    'Entfernen':
        'Remove',
    'Ereignisprotokoll':
        'Event log',
    'Ereignisse (live, MQTT)':
        'Events (live, MQTT)',
    'Erkannt als':
        'Recognised as',
    'Erteilen':
        'Grant',
    'Filtern':
        'Filter',
    'Formel':
        'Formula',
    'Funktionen':
        'Functions',
    'Funktionen dieses Modells':
        'Functions of this model',
    'Gesamt':
        'Total',
    'Gespeichert':
        'Saved',
    'Herausforderungen verwalten':
        'Manage challenges',
    'Heute':
        'Today',
    'Hochladen':
        'Upload',
    'Kapitulation':
        'Capitulation',
    'Live-Status':
        'Live status',
    'Metriken':
        'Metrics',
    'Modell / FW':
        'Model / FW',
    'Noten':
        'Grades',
    'Nur diese Aufgabe':
        'Only this task',
    'Parameter':
        'Parameters',
    'Passwort':
        'Password',
    'Pflicht':
        'Mandatory',
    'Prognose':
        'Forecast',
    'Protokoll (Datenbank)':
        'Log (database)',
    'Punisher · Aufsicht':
        'Punisher · supervision',
    'Punisher · Devious City · automatisch aus dem Logbuch erzeugt':
        'Punisher · Devious City · generated automatically from the logbook',
    'Quelle':
        'Source',
    'Quelle/Art':
        'Source/kind',
    'Rang · Punkte':
        'Rank · points',
    'Rangliste dieser Woche':
        'Leaderboard of this week',
    'Schritt':
        'Step',
    'Schritte':
        'Steps',
    'Schwerkraft x / y / z':
        'Gravity x / y / z',
    'Signal':
        'Signal',
    'Sklaven-ID':
        'Slave ID',
    'Struktur':
        'Structure',
    'Tagesdauer':
        'Length of day',
    'Teiln.':
        'Slave',
    'Vektor (g)':
        'Vector (g)',
    'Wochenpunkte':
        'Weekly points',
    'ZEUGNIS':
        'REPORT',
    'ZIP herunterladen':
        'Download ZIP',
    'Zeitbudget':
        'Time budget',
    'Zentrale':
        'Central unit',
    'Zeugnisse':
        'Reports',
    'Zugeordnet bei':
        'Assigned to',
    'Das Halsband ist offline — Kalibrieren geht nur mit eingeschaltetem, verbundenem Gerät.':
        'The collar is offline - calibrating only works with the device switched on and connected.',
    'Der Sklave meldet sich':
        'The slave logs in',
    'Ein Sklave meldet sich':
        'A slave logs in',
    'Für diese Woche liegt noch keine Bewertung vor (sie läuft am Montag).':
        'There is no review for this week yet (it runs on Monday).',
    'Für diese Woche liegt noch keine Bewertung vor — sie läuft automatisch am Montag.':
        'There is no review for this week yet - it runs automatically on Monday.',
    'Für diesen Sklave ist noch kein Tag verzeichnet.':
        'No day is recorded for this slave yet.',
    'In dieser Woche ist keine Herausforderung angesetzt.':
        'No challenge is set for this week.',
    'Leer — Migration 003 eingespielt?':
        'Empty - has migration 003 been applied?',
    'Logbuch aus: Migration 005 fehlt.':
        'Logbook off: migration 005 is missing.',
    'RFID (Inhalt Block 8, wie im Log „Slave not found - RFID …“)':
        'RFID (content of block 8, as in the log "Slave not found - RFID ...")',
    'Sklave steht aufrecht, Blick geradeaus.':
        'The slave stands upright, looking straight ahead.',
    'Wiederanmeldung nach Kapitulation erlaubt':
        'Logging in again after capitulation is allowed',
    'Winkel zu „auf allen vieren“':
        'Angle to "on all fours"',
    'Winkel zu „stehend“':
        'Angle to "standing"',
    'zu nah beieinander — das Halsband lehnt diese Kalibrierung ab':
        'too close together - the collar refuses this calibration',
    '1 leicht':
        '1 light',
    '2 mittel':
        '2 medium',
    '3 stark':
        '3 strong',
    '1 · Auf allen vieren messen':
        '1 · Measure on all fours',
    '2 · Stehend messen':
        '2 · Measure standing',
    'ab (JJJJ-MM-TT [HH:MM])':
        'from (YYYY-MM-DD [HH:MM])',
    'aktiv bei':
        'active at',
    'aktuelle':
        'current',
    'alle Reizgeber':
        'all stimulus devices',
    'alle Sklaven':
        'all slaves',
    'allen Sklaven des Feldes':
        'every slave in the field',
    'auf allen vieren':
        'on all fours',
    'blau':
        'blue',
    'eingefroren':
        'frozen',
    'einmal am Tag':
        'once a day',
    'gemessen':
        'measured',
    'gut trennbar':
        'clearly separable',
    'knapp, besser neu messen':
        'tight, better measured again',
    'manuell':
        'manual',
    'niemandem':
        'nobody',
    'oder':
        'or',
    'rot':
        'red',
    'ruhig':
        'still',
    's / Anzahl':
        's / count',
    'stehend':
        'standing',
    'streckt':
        'stretches',
    'unterschiedliche':
        'different',
    'wann':
        'when',
    'was':
        'what',
    '– Vorgabe –':
        '- default -',
    '— Score, setzt montags zurück':
        '- score, resets on Monday',
    '— alle Wochen':
        '- all weeks',
    '← Rangliste':
        '← Leaderboard',
    '← neuer':
        '← newer',
    '≤ Strafen':
        '≤ punishments',
    'PUNISHER':
        'PUNISHER',
    'auto_plan':
        'auto_plan',
    'plan_day_tasks':
        'plan_day_tasks',
    'challenge':
        'challenge',
    'shock':
        'shock',
    'vibe':
        'vibe',
    'beep':
        'beep',

    # --- phase 5, second pass: text around Jinja values -----------------
    'Abstand der Haltungen':
        'Distance between the poses',
    'Alternativsatz':
        'Alternative set',
    'Hauptsatz':
        'Main set',
    'Aufgaben ≥ Mindestnote':
        'Tasks ≥ minimum grade',
    'Aufmerksamkeit':
        'Attention',
    'Der Sklave trägt das Halsband so, wie er es später trägt. Zwei Haltungen werden je {n} Sekunden gemessen; dabei ruhig halten (das Halsband piept, wenn die Messung fertig ist). Aus beiden Haltungen entscheidet das Halsband im Pet-Modus, welcher es gerade näher ist — ein fester Winkel ist dann nicht mehr nötig. Die Werte gelten für':
        'The slave wears the collar the way he will wear it later. Two poses are measured for {n} seconds each; hold still while it happens (the collar beeps when the measurement is done). From the two poses the collar decides, in pet mode, which one it is closer to - a fixed angle is then no longer needed. The values apply to',
    'Du darfst jetzt etwas essen.':
        'You may eat something now.',
    'EMERGENCY eintippen':
        'Type EMERGENCY',
    'Heartbeat':
        'Heartbeat',
    'Liegt als pics/slaves/{id}.jpg|png auf dem Pi; die HDMI-Anzeige zeigt es neben Name und Plan.':
        'Stored as pics/slaves/{id}.jpg|png on the Pi; the HDMI display shows it next to name and plan.',
    'Modell „{m}“ unbekannt':
        'Model "{m}" unknown',
    'Pause.':
        'Break.',
    'Planaufgabe(n)':
        'plan task(s)',
    'Position zwischen den Haltungen':
        'Position between the poses',
    'Pseudonymisierter Export aller Durchgänge ({n}), Wochenbewertungen, Wochenpläne, Ränge, Stufen und Abzeichen als CSV (Trennzeichen':
        'Pseudonymised export of all runs ({n}), weekly reviews, weekly plans, ranks, levels and badges as CSV (separator',
    'Punisher Aufsicht':
        'Punisher supervision',
    'Schloss':
        'Lock',
    'Schritt mit':
        'Step with',
    'Seite':
        'Page',
    'Sieger':
        'Winner',
    'St.':
        'Lv.',
    'Str.':
        'pun.',
    'Tag einfach an der Zentrale auflegen, dann hier neu laden.':
        'Just hold the tag to the central unit, then reload this page.',
    'Tagesdauer höchstens':
        'Day at most',
    'Vorbelegt mit dem zuletzt unbekannten Tag':
        'Pre-filled with the last unknown tag',
    'Vorlage':
        'Template',
    'beendet':
        'finished',
    'bestandene Aufgaben':
        'tasks passed',
    'blockierend':
        'blocking',
    'braucht':
        'needs',
    'die laufende Firmware meldet diese Funktion NICHT':
        'the running firmware does NOT report this function',
    'dieser Sklave hat kein Gerät dafür':
        'this slave has no device for it',
    'gesamt':
        'total',
    'im Feld':
        'in the field',
    'in der Anlage ist kein Gerät mit dieser Funktion eingetragen':
        'no device with this function is recorded in the installation',
    'ist der Hebel für Regeln: eine Belohnung kürzt sie, eine Bestrafung verlängert sie — mindestens 15 min, höchstens {n} min aus':
        'is the lever for rules: a reward shortens it, a punishment lengthens it - at least 15 min, at most {n} min, from',
    'leer =':
        'empty =',
    'läuft — Block':
        'running — block',
    'meldet die Firmware zusätzlich (Registry älter als die Firmware)':
        'the firmware reports it in addition (registry older than the firmware)',
    'min Pause — keine Regel und keine Bestrafung hebt sie an.':
        'min of break - no rule and no punishment lifts it.',
    'min Training zwingend':
        'min of training, mandatory',
    'min freies Training':
        'min of free training',
    'min je Durchlauf':
        'min per pass',
    'min seit der letzten Pause':
        'min since the last break',
    'min, nach':
        'min, after',
    'noch nichts empfangen':
        'nothing received yet',
    'nächster in':
        'next in',
    'sagt':
        'says',
    'seit {n} s still':
        'silent for {n} s',
    'trainiert wird, der':
        'is trained, the',
    'vollständig':
        'complete',
    'vor':
        'ago',
    'z. B. Museumstag':
        'e.g. Museum day',
    '{a} von {b} bekannt':
        '{a} of {b} known',
    '– Programm gelöscht –':
        '- programme deleted -',

    # --- phase 5, third pass: literals in Jinja expressions -------------
    'Neues Gerät': 'New device',
    'Gerät bearbeiten': 'Edit device',
    'Neues Programm': 'New programme',
    'Programm bearbeiten': 'Edit programme',
    'aktuelle Woche': 'current week',
    'nächste Woche': 'next week',

    # --- phase 5: forecast texts out of logbook.py ----------------------
    'Aufstieg in Reichweite — Wochenplan halten': 'Promotion within reach - keep the weekly plan',
    'Aufstieg in Reichweite': 'Promotion within reach',
    'Noch kein Training diese Woche': 'No training this week yet',
    'Wochenplan {a}/{b}': 'Weekly plan {a}/{b}',
    ' — Abstieg droht': ' - demotion looms',
    'noch {n} Aufgabe(n) ≥ {g}': '{n} more task(s) ≥ {g}',
    'noch {n} Bestwert(e)': '{n} more best result(s)',
    'Wochenplan vollständig nötig': 'the weekly plan must be complete',
    'Rang wird gehalten': 'Rank is held',
    # Boot and crash history (doc 42 point 1)
    'Neustarts': 'Restarts',
    'Heute:': 'Today:',
    'Heute kein Neustart.': 'No restart today.',
    'Wann': 'When',
    'Lief davor': 'Ran before',
    'Letztes Kommando': 'Last command',
    'Letzter Fehler': 'Last error',
    'unbekannt': 'unknown',
    'Noch kein Start gemeldet — eine Firmware ab 2.2.0 meldet jeden Start mit Grund.':
        'No start reported yet — a firmware from 2.2.0 on reports every start with its reason.',
    # Device health, red or green (doc 42 point 2)
    'Gesundheit': 'Health',
    '{n} Gerät(e) rot': '{n} device(s) red',
    'alle Geräte grün': 'all devices green',
    'alles in Ordnung': 'all fine',
    'EMERGENCY — eingefroren': 'EMERGENCY — frozen',
    'Signal schwach ({r} dBm)': 'weak signal ({r} dBm)',
    'wenig Speicher ({k} kB frei)': 'low memory ({k} kB free)',
    'Komponenten abgemeldet: {c}': 'components reported out: {c}',
    'gesperrt: {r}': 'blocked: {r}',
    'Firmware nicht aktuell': 'firmware not current',
    'heute neu gestartet: {w}': 'restarted today: {w}',
    'vor {m} min neu gestartet': 'restarted {m} min ago',
    '{n} Sicherheitsereignis(se) heute': '{n} safety event(s) today',
    # Discovery as status (doc 42 point 4)
    'braucht {w} Fesseln, das Gerät hat {h}': 'needs {w} cuffs, the device has {h}',
    'Komponente klemmt: {c}': 'component stuck: {c}',
    'Fesseln nötig': 'cuffs needed',
    'So viele Fesseln muss das Schloss nutzen können. Meldet es weniger (Fessel abgemeldet), wird der Schritt an diesem Gerät nicht ausgeführt und die Programmprüfung sagt es vorher.':
        'This many cuffs the lock must be able to use. If it reports fewer (a cuff reported out), the step is not run on this device, and the programme check says so beforehand.',
    'abgemeldet': 'reported out',
    'vom Gerät abgemeldet': 'reported out by the device',
    'meldet die Firmware zusätzlich (Registry älter als die Firmware) — wird NICHT genutzt':
        'reported additionally by the firmware (registry older than the firmware) — NOT used',
    'heute nicht nutzbar: die tragende Komponente ist abgemeldet':
        'not usable today: the carrying component is reported out',
    # V-Cage proximity (doc 42 point 3)
    'Funkstärke {r} dBm, Grenze {t} dBm': 'signal {r} dBm, threshold {t} dBm',
    'Warnung': 'Warning',
    'drinnen': 'inside',
    'nahe der Grenze': 'near the edge',
    # Device settings schema (doc 42 point 5)
    'Impuls höchstens': 'Pulse at most',
    'Vibration höchstens': 'Vibration at most',
    'Ton höchstens': 'Tone at most',
    'Längster Impuls': 'Longest pulse',
    'Längster Modus': 'Longest mode',
    'Längste Haltezeit': 'Longest hold',
    'Längstes Training': 'Longest training',
    'Längste Aufgabe': 'Longest task',
    'Ausgabe höchstens': 'Output at most',
    'Ausgabe je Tag höchstens': 'Output per day at most',
    'Dauer eines Kanal-Ereignisses': 'Duration of a channel event',
    'Stufe 1 (Gerätevorgabe)': 'Level 1 (device default)',
    'Stufe 2 (Gerätevorgabe)': 'Level 2 (device default)',
    'Stufe 3 (Gerätevorgabe)': 'Level 3 (device default)',
    'Feste Coyote (MAC)': 'Fixed Coyote (MAC)',
    'Stärkster Impuls, den dieses Halsband überhaupt abgibt (Skala 0..99, gebaut bis 40).': 'Strongest pulse this collar emits at all (scale 0..99, built up to 40).',
    'Egal aus welcher Quelle. Verhindert, dass ein verkürzter Impuls durch einen schnellen zweiten nachgeholt wird.': 'Whatever the source. Prevents a shortened pulse from being made up by a rapid second one.',
    'Obergrenze jeder Intensität, in Prozent der Decke der Teilnehmerin.': "Upper limit of every intensity, in percent of the participant's ceiling.",
    'Rückfall, wenn die Teilnehmerin keine eigenen Stufen hat (Doc 31).': 'Fallback when the participant has no levels of her own (doc 31).',
    'Leer = die erste Coyote, die antwortet. Gesetzt = nur diese.': 'Empty = the first Coyote that answers. Set = only this one.',
    'Geräteeinstellungen': 'Device settings',
    'Gespeichert im Gerät, gültig ab seinem nächsten Start. Leer = Vorgabe des Geräts. Die Grenzen sind die gebauten Obergrenzen — enger geht, weiter nicht.': 'Stored in the device, effective from its next start. Empty = device default. The bounds are the compiled ceilings — tighter is possible, wider is not.',
    'gespeichert: {k}': 'stored: {k}',
    'abgewiesen: {k}': 'refused: {k}',
    'Gerät startet neu': 'device restarting',
    'nicht gemeldet, Vorgabe {d}': 'not reported, default {d}',
    'Gerät danach neu starten (nur im Leerlauf möglich)': 'restart the device afterwards (only possible when idle)',
    'An das Gerät senden': 'Send to the device',
    'Nichts geändert.': 'Nothing changed.',
    'Einstellungen gesendet — sie gelten ab dem nächsten Start des Geräts.': "Settings sent — they apply from the device's next start.",

    # --- budgets and cooldowns (2.3, doc 44 §1) ---------------------------
    'Budget ausgeschöpft': 'Budget exhausted',
    'Budget: Bestrafungen': 'Budget: punishments',
    'Budget: Belohnungen': 'Budget: rewards',
    'Budget: Durchgänge': 'Budget: runs',
    'Budget je Tag': 'Budget per day',
    'Budget je Woche': 'Budget per week',
    'Belohnungen': 'Rewards',
    'diese Woche': 'this week',
    'Budget ausgeschöpft: {what} {per} ({n})': 'Budget exhausted: {what} {per} ({n})',
    'Belohnung verfallen — Abstand {s} s nicht eingehalten': 'Reward lapsed — {s} s gap not kept',
    'Bestrafungen über den Kanal': 'Punishments over the channel',
    'Wie viele je Tag oder Woche, und wie dicht — unter der Decke aus config.ini [safety].':
        'How many per day or week, and how close — beneath the ceiling from config.ini [safety].',
    'Belohnungen über den Kanal': 'Rewards over the channel',
    'Eine Belohnung lange nach dem Anlass ist keine: Vorgabe „verfällt“.':
        'A reward long after the occasion is none: default "lapses".',
    'Durchgänge (alle Aufgaben)': 'Runs (all tasks)',
    'Anzahl = wie viele je Tag für die Rangliste zählen (Anti-Grinding); Abstand = Pause zwischen zwei Durchgängen.':
        'Count = how many per day count towards the leaderboard (anti-grinding); gap = pause between two runs.',
    'Budgets': 'Budgets',
    'Budgets und Cooldowns': 'Budgets and cooldowns',
    'wie oft, und wie dicht': 'how often, and how close',
    'Ein Budget sagt, wie oft etwas in einem Zeitraum passieren darf (Anzahl), ein Cooldown, wie dicht (Abstand). Eine Zeile für eine Teilnehmerin gilt zusätzlich zur Zeile für alle — die strengere gewinnt.':
        'A budget says how often something may happen in a period (count), a cooldown how close together (gap). A row for one participant applies in addition to the row for all — the tighter one wins.',
    'Die Decke des Bestrafungskanals aus': 'The ceiling of the punishment channel from',
    'gilt unter jedem Budget': 'applies beneath every budget',
    'sie steht hier als Zeile, ändern lässt sie sich hier nicht. Ein Budget kann nur verschärfen.':
        'it is shown here as a row, but cannot be changed here. A budget can only tighten.',
    'Ist ein Budget ausgeschöpft, feuert der Anlass „Budget ausgeschöpft“ im Regelwerk — einmal je Zeitraum.':
        'When a budget is exhausted, the trigger "Budget exhausted" fires in the rule set — once per period.',
    'Was': 'What',
    'Für wen': 'For whom',
    'Zeitraum': 'Period',
    'Abstand': 'Gap',
    'in der Pause': 'inside the pause',
    'In der Pause': 'Inside the pause',
    'nachholen': 'catch up',
    'verfällt': 'lapses',
    'Decke — nicht über das Web änderbar': 'Ceiling — not editable over the web',
    'Budget löschen?': 'Delete budget?',
    'Keine Budgets — dann gilt nur die Decke.': 'No budgets — then only the ceiling applies.',
    'Budget setzen': 'Set a budget',
    'alle Aufgaben': 'all tasks',
    'Abstand (s)': 'Gap (s)',
    'nachholen — wartet und kommt dann': 'catch up — waits and then arrives',
    'wofür dieses Budget gedacht ist': 'what this budget is for',
    'Dieselbe Zeile (Was, Für wen, Zeitraum) wird überschrieben, nicht verdoppelt. Ein leeres Feld heißt: keine Grenze dieser Art.':
        'The same row (what, for whom, period) is overwritten, not duplicated. An empty field means: no limit of that kind.',
    'Wozu das gut ist': 'What it is for',
    'Beispiel „höchstens drei Verstöße pro Woche“: Bestrafungen · alle · Woche · Anzahl 3. Die vierte wird abgewiesen, und im Regelwerk kann auf „Budget ausgeschöpft“ mit Bedingung „Budget: Bestrafungen“ eine Auflage folgen.':
        'Example "at most three violations per week": punishments · all · week · count 3. The fourth is refused, and in the rule set a sanction can follow "Budget exhausted" with the condition "Budget: punishments".',
    'Bei Durchgängen heißt Anzahl: so viele zählen je Tag für die Rangliste (Anti-Grinding). Der Abstand ist eine Pause zwischen zwei Durchgängen derselben Aufgabe; der Tagesplan nimmt dann erst eine andere.':
        'For runs, count means: this many per day count towards the leaderboard (anti-grinding). The gap is a pause between two runs of the same task; the day plan then takes another one first.',
    'Unbekannter Schlüssel.': 'Unknown key.',
    'Teilnehmerin: Zahl erwartet.': 'Participant: number expected.',
    'Teilnehmerin unbekannt.': 'Participant unknown.',
    '{name}: {lo}..{hi}': '{name}: {lo}..{hi}',
    'Anzahl oder Abstand — eins von beiden muss stehen.': 'Count or gap — one of the two must be set.',
    'Über der Decke aus config.ini [safety] ({cap}) — ein Budget kann nur verschärfen.':
        'Above the ceiling from config.ini [safety] ({cap}) — a budget can only tighten.',
    'Budgets nicht verfügbar — Migration 005 fehlt.': 'Budgets not available — migration 005 missing.',
    'Budget gespeichert.': 'Budget saved.',
    'Budget geändert.': 'Budget changed.',
    'Budget gelöscht.': 'Budget deleted.',
    'keine Zählgrenze': 'no count limit',
    'bearbeiten': 'edit',
    'Durchgänge ': 'Runs ',

    # --- pause / holiday (2.3, doc 44 §2) ----------------------------------
    'Pausen': 'Pauses',
    'Pause und Urlaub': 'Pause and holiday',
    'die Woche steht': 'the week stands',
    'Während einer Pause öffnet keine Anmeldung einen Tag, keine Regel feuert, keine Wochenaufgabe wird fällig, der Kanal schweigt. Eine Woche, die ganz in der Pause liegt, wird nicht bewertet: der Rang bleibt, offene Planaufgaben rücken in die nächste Woche, Serien überbrücken die Tage. Im Zeugnis steht „pausiert“ — nicht „nicht angetreten“.':
        'During a pause no login opens a day, no rule fires, no weekly task falls due, the channel is silent. A week that lies entirely in the pause is not graded: the rank stays, open plan tasks move on to the next week, streaks bridge the days. The report card says "paused" — not "did not show up".',
    'Eine Pause endet mit ihrem Datum. Wer sie früher beenden will, löscht sie.': 'A pause ends with its date. To end it earlier, delete it.',
    'Von': 'From',
    'Bis': 'To',
    'Bis (einschließlich)': 'To (inclusive)',
    'kommt': 'coming',
    'vorbei': 'over',
    'beenden': 'end',
    'Pause beenden? Ab sofort gilt wieder alles.': 'End the pause? Everything applies again from now on.',
    'Keine Pause eingetragen.': 'No pause entered.',
    'nur laufende und kommende': 'only running and coming',
    'auch vergangene zeigen': 'show past ones too',
    'Pause eintragen': 'Enter a pause',
    'alle — die ganze Anlage': 'all — the whole installation',
    'Urlaub, krank, Umbau — steht im Protokoll und auf ihrer Seite': 'holiday, ill, rebuild — appears in the audit and on her page',
    'Eintragen': 'Enter',
    'Datum: JJJJ-MM-TT erwartet.': 'Date: YYYY-MM-DD expected.',
    'Das Ende liegt vor dem Anfang.': 'The end lies before the start.',
    'Die Pause läge ganz in der Vergangenheit.': 'The pause would lie entirely in the past.',
    'Länger als ein Jahr — das ist kein Urlaub mehr.': 'Longer than a year — that is no holiday any more.',
    'Pausen nicht verfügbar — Migration 006 fehlt.': 'Pauses not available — migration 006 missing.',
    'Pause eingetragen — bis {until}.': 'Pause entered — until {until}.',
    'Pause beendet.': 'Pause ended.',
    'Pause': 'Pause',
    'Pause bis': 'Pause until',
    '(ganze Anlage)': '(whole installation)',
    'Keine Anmeldung öffnet einen Tag, keine Regel feuert, der Kanal schweigt. Die Woche steht.': 'No login opens a day, no rule fires, the channel is silent. The week stands.',
    'Urlaub': 'holiday',
    'Pause bis {until} — kein Kanal': 'Pause until {until} — no channel',
    'pausiert': 'paused',
    '{n} von 7 Tagen pausiert': '{n} of 7 days paused',
    'die Woche steht: nichts bewertet, der Rang bleibt': 'the week stands: nothing graded, the rank stays',

    # --- streaks (2.3, doc 44 §3) ------------------------------------------
    'Serie: Meilenstein erreicht': 'Streak: milestone reached',
    'Serie gebrochen': 'Streak broken',
    'Serie: mindestens 2': 'Streak: at least 2',
    'Serie: mindestens 3': 'Streak: at least 3',
    'Serie: mindestens 5': 'Streak: at least 5',
    'Serie: mindestens 7': 'Streak: at least 7',
    'Serie: mindestens 10': 'Streak: at least 10',
    'Tage ohne Verstoß': 'Days without a violation',
    'Angetretene Tage in Folge ohne Bestrafung über den Kanal. Ein Verstoß oder ein ausgelassener Tag bricht sie.':
        'Attended days in a row with no punishment over the channel. A violation or a missed day breaks it.',
    'Trainingstage': 'Training days',
    'Angetretene Tage in Folge. Ein ausgelassener Tag bricht sie.': 'Attended days in a row. A missed day breaks it.',
    'Durchgänge bestanden': 'Runs passed',
    'Bestandene Durchgänge in Folge — einer Aufgabe oder aller. Ein nicht bestandener bricht sie.':
        'Runs passed in a row — of one task or of any. A failed one breaks it.',
    'Durchgänge gescheitert': 'Runs failed',
    'Nicht bestandene Durchgänge in Folge. Ein bestandener bricht sie. Für Ketten: „zweimal gescheitert → …“':
        'Runs failed in a row. A passed one breaks it. For chains: "failed twice → …"',
    'Wochen mit vollem Plan': 'Weeks with the full plan',
    'Wochen in Folge mit vollständigem Wochenplan. Eine unvollständige bricht sie.':
        'Weeks in a row with the weekly plan complete. An incomplete one breaks it.',
    'Tage': 'days',
    'Wochen': 'weeks',
    'Serie: {name} — {n} {unit}': 'Streak: {name} — {n} {unit}',
    'Serie gebrochen: {name} — {n} {unit}': 'Streak broken: {name} — {n} {unit}',
    'Serien': 'Streaks',
    'Zähler mit Zähl- und Reset-Bedingung': 'counters with a counting and a reset condition',
    'Eine Serie zählt etwas in Folge — Tage ohne Verstoß, bestandene Durchgänge, volle Wochenpläne — und beginnt bei null, wenn die Reset-Bedingung eintritt. Erreicht sie einen Meilenstein, feuert im Regelwerk der Anlass „Serie: Meilenstein erreicht“; reißt sie, feuert „Serie gebrochen“. Was daraus folgt, steht dort — hier steht nur, was gezählt wird.':
        'A streak counts something in a row — days without a violation, runs passed, full weekly plans — and starts at zero when the reset condition occurs. When it reaches a milestone, the trigger "Streak: milestone reached" fires in the rule set; when it breaks, "Streak broken" fires. What follows is decided there — here it only says what is counted.',
    'Der Verlust wird angezeigt': 'The loss is shown',
    '„Serie gebrochen: 6 Tage“ steht einen Tag lang auf dem Bildschirm und auf der Teilnehmerseite.':
        '"Streak broken: 6 days" stays on the screen and the participant page for a day.',
    'Meilensteine': 'Milestones',
    'läuft bei': 'running for',
    'Rekord': 'Record',
    'Teilnehmerinnen': 'participants',
    'Alle Zähler dieser Serie auf null?': 'Reset every counter of this streak to zero?',
    'Zähler 0': 'Counters 0',
    'Serie löschen? Die Zähler gehen mit.': 'Delete the streak? The counters go with it.',
    'Keine Serien — dann wird nichts in Folge gezählt.': 'No streaks — then nothing is counted in a row.',
    'Serie anlegen': 'Create a streak',
    'Kurz, ohne Leerzeichen — so heißt sie in Regeln (Bedingung „Serie: …“) und im Protokoll. Derselbe Schlüssel überschreibt.':
        'Short, no spaces — that is its name in rules (condition "Streak: …") and in the audit. The same key overwrites.',
    'Bei jedem dieser Werte feuert „Serie: Meilenstein erreicht“ einmal. Leer: die Serie zählt und bricht, aber nichts feiert sie.':
        'At each of these values "Streak: milestone reached" fires once. Empty: the streak counts and breaks, but nothing celebrates it.',
    'Die Arten': 'The kinds',
    'Pausierte Tage zählen nicht und brechen nicht. Eine Kette „zweimal gescheitert → Eskalation“ ist eine Serie „Durchgänge gescheitert“ mit Meilenstein 2 und eine Regel auf „Serie: Meilenstein erreicht“ mit Bedingung „Serie: …“.':
        'Paused days neither count nor break. A chain "failed twice → escalation" is a streak "Runs failed" with milestone 2 and a rule on "Streak: milestone reached" with the condition "Streak: …".',
    'Schlüssel: Buchstaben, Ziffern, _ und - — er steht in Regeln und Protokoll.': 'Key: letters, digits, _ and - — it appears in rules and the audit.',
    'Ein Name fehlt — der steht auf dem Bildschirm.': 'A name is missing — that is what the screen shows.',
    'Unbekannte Aufgabe.': 'Unknown task.',
    'Serien nicht verfügbar — Migration 007 fehlt.': 'Streaks not available — migration 007 missing.',
    'Serie gespeichert.': 'Streak saved.',
    'Serie geändert.': 'Streak changed.',
    'Serie gelöscht.': 'Streak deleted.',
    'Zähler zurückgesetzt.': 'Counters reset.',
    'nächster Meilenstein': 'next milestone',
    'z. B. clean': 'e.g. clean',

    # --- rule set extension (2.3, doc 44 §4) --------------------------------
    'zu jeder Zeit': 'at any time',
    'nach 22:00': 'after 22:00',
    'nach 20:00': 'after 20:00',
    'nach 18:00': 'after 18:00',
    'vor 8:00': 'before 8:00',
    'vor 10:00': 'before 10:00',
    'vormittags (vor 12:00)': 'in the morning (before 12:00)',
    'nachmittags (ab 12:00)': 'in the afternoon (from 12:00)',
    'am Wochenende': 'at the weekend',
    'werktags': 'on weekdays',
    'montags': 'on Mondays',
    'freitags': 'on Fridays',
    'sonntags': 'on Sundays',
    'Beides muss zutreffen. Die Uhr ist die der Zentrale, im Moment des Anlasses.': 'Both have to hold. The clock is the central unit\'s, at the moment of the trigger.',
    'Grenzen': 'Bounds',
    'die Automatik bewegt sich nur dazwischen': 'the automatic system only moves between them',
    'Grenzen je Aufgabe halten die Automatik in einem Fenster — leer heißt: 1 bis level_max der Anlage.':
        'Bounds per task keep the automatic system in a window — empty means: 1 to the installation\'s level_max.',
    'Stufengrenzen nicht verfügbar — Migration 008 fehlt.': 'Level bounds not available — migration 008 missing.',
    'Stufengrenzen {code}: {lo}–{hi}.': 'Level bounds {code}: {lo}–{hi}.',

    # --- day form (2.3, doc 44 §5) ------------------------------------------
    'leicht': 'easy',
    'normal': 'normal',
    'streng': 'strict',
    'Impulse schwächer, Aufgabenstufe eine tiefer, Belohnungen großzügiger.': 'Pulses weaker, task level one lower, rewards more generous.',
    'Alles wie eingestellt.': 'Everything as set.',
    'Impulse stärker (nie über der Decke), Aufgabenstufe eine höher, Belohnungen knapper.': 'Pulses stronger (never above the ceiling), task level one higher, rewards scarcer.',
    'Tagesform setzen': 'Set the day form',
    'easy / normal / strict, optional :+1 für morgen — z. B. strict:+1. Gilt für den einen Tag und fällt dann auf normal.':
        'easy / normal / strict, optionally :+1 for tomorrow — e.g. strict:+1. Holds for that one day and then falls back to normal.',
    'Tagesform: easy, normal oder strict — optional :+1 für morgen.': 'Day form: easy, normal or strict — optionally :+1 for tomorrow.',
    'Tagesform nicht verfügbar — Migration 009 fehlt.': 'Day form not available — migration 009 missing.',
    'Tagesform {form} für {day} gesetzt — gilt bis Tagesende, dann wieder normal.': 'Day form {form} set for {day} — holds until the end of the day, then normal again.',
    'Tagesform': 'Day form',
    'gesetzt von': 'set by',
    'morgen': 'tomorrow',
    'für morgen': 'for tomorrow',
    'steht im Protokoll': 'appears in the audit',
    'Gilt bis Tagesende und fällt dann auf normal — es sei denn, eine Regel setzt sie wieder. Impulse nie über der Decke, Stufe nur innerhalb ihrer Grenzen; Bestrafungsbudgets bleiben unberührt.':
        'Holds until the end of the day and then falls back to normal — unless a rule sets it again. Pulses never above the ceiling, level only inside its bounds; punishment budgets stay untouched.',

    # --- mystery (2.3, doc 44 §6) --------------------------------------------
    'Mystery': 'Mystery',
    'die Zentrale zieht im Fenster Zeitpunkt und Eintrag aus dem Pool; der Bildschirm zeigt „?“': 'the central unit draws moment and entry from the pool inside the window; the screen shows "?"',
    'Pool': 'Pool',
    'Mystery-Pool: „{entry}“ ist kein Aufgabencode und kein punish:N / reward:N.': 'Mystery pool: "{entry}" is neither a task code nor punish:N / reward:N.',
    'Ein Mystery-Block braucht einen Pool — mindestens einen Eintrag.': 'A mystery block needs a pool — at least one entry.',
    'Der Pool ist die Sicherheitsgrenze: gezogen wird nur, was drinsteht UND was für sie ohnehin erlaubt ist — Decke, Auflagen, Budgets gelten unverändert. Aufgabencodes, punish:1–3, reward:1–3, durch Komma getrennt. Im Prüfprotokoll steht vorher, was gezogen wurde.':
        'The pool is the safety boundary: only what is in it AND what is allowed for her anyway gets drawn — ceiling, sanctions, budgets apply unchanged. Task codes, punish:1–3, reward:1–3, comma separated. The audit says beforehand what was drawn.',
    'z. B. PET, NOSE_BUTTON, punish:2, reward:1': 'e.g. PET, NOSE_BUTTON, punish:2, reward:1',

    # --- scenarios (2.3, doc 44 §7) ------------------------------------------
    'Szenarien': 'Scenarios',
    'Szenario': 'Scenario',
    'das Bündel mit Namen': 'the bundle with a name',
    'Ein Szenario ist kein neues Regelsystem. Es bündelt, was es schon gibt — Tagesplan (mit Mystery-Blöcken), Auflagen, Budgets, Tagesform — unter einem Namen, für eine Teilnehmerin, mit einem Klick und einem Enddatum. Aktivieren schreibt in genau die Tabellen, in denen die Teile leben; das Enddatum nimmt alles wieder heraus: Plan zurück, Auflagen aufgehoben, Budgets weg, Tagesform normal.':
        'A scenario is not a new rule system. It bundles what exists already — day plan (with mystery blocks), sanctions, budgets, day form — under a name, for one participant, with one click and an end date. Activating writes into the very tables the pieces live in; the end date takes it all back out: plan restored, sanctions lifted, budgets gone, day form normal.',
    'Aktiviert wird auf der Teilnehmerseite (Karte „Rang, Auflagen, Kanal“).': 'Activation happens on the participant page (card "Rank, sanctions, channel").',
    'Läuft gerade': 'Running now',
    'Teilnehmerin': 'Participant',
    'läuft bei {n}': 'running for {n}',
    'ihr eigener': 'her own',
    'Szenario löschen? Wo es läuft, wird es beendet.': 'Delete the scenario? Where it runs, it ends.',
    'Keine Szenarien — unten eines anlegen.': 'No scenarios — create one below.',
    'Szenario bearbeiten': 'Edit scenario',
    'Szenario anlegen': 'Create scenario',
    'z. B. Strict, Weekend, Einführung': 'e.g. Strict, Weekend, Induction',
    'ihren eigenen lassen': 'leave hers',
    'nicht anfassen': 'leave alone',
    '(eine Zeile je Budget: Schlüssel Zeitraum Anzahl Abstand nachholen/verfällt — „-“ für keine)': '(one line per budget: key period count gap queue/drop — "-" for none)',
    'Was leer bleibt, wird beim Aktivieren nicht angefasst. Die Decke aus config.ini [safety] gilt unter jedem Szenario; ein Budget kann nur verschärfen.':
        'What stays empty is not touched on activation. The ceiling from config.ini [safety] applies beneath every scenario; a budget can only tighten.',
    'Ein Name fehlt.': 'A name is missing.',
    'Tagesplan: Zahl erwartet.': 'Day plan: number expected.',
    'Tagesplan unbekannt.': 'Day plan unknown.',
    'Unbekannte Auflage: {key}': 'Unknown sanction: {key}',
    # Budget rows of the scenario editor (2.5): chosen, no longer typed.
    'Ein Budget begrenzt, wie <b>oft</b> etwas passiert und wie <b>dicht</b> zwei Male aufeinander folgen dürfen. Leer lassen, was nicht begrenzt werden soll — aber eines von beiden muss stehen, sonst ist die Zeile keine Grenze.':
        'A budget limits how <b>often</b> something happens and how <b>close</b> two occurrences may follow each other. Leave empty what is not to be limited — but one of the two must be set, otherwise the row is no limit at all.',
    '<b>Anzahl</b> — wie oft im Zeitraum. <b>Abstand</b> — wie viele Sekunden mindestens dazwischen liegen müssen. <b>zu dicht?</b> — was mit dem geschieht, was innerhalb des Abstands anfällt: <i>nachholen</i> schiebt es hinter die Pause, <i>verfällt</i> lässt es weg. Für Belohnungen ist <i>verfällt</i> die Vorgabe — eine Belohnung zwanzig Minuten nach dem Anlass ist keine.':
        '<b>Count</b> — how often within the period. <b>Gap</b> — how many seconds must lie between two occurrences at least. <b>too close?</b> — what happens to whatever arrives inside the gap: <i>catch up</i> pushes it behind the pause, <i>lapses</i> drops it. For rewards <i>lapses</i> is the default — a reward twenty minutes after the occasion is none.',
    '— keins —': '— none —',
    'Durchgänge {task}': 'Runs {task}',
    'Nur diese eine Aufgabe: Anzahl zählt für die Rangliste, Abstand ist die Pause bis zur Wiederholung.':
        'This one task only: count is what counts towards the leaderboard, gap is the pause until it may repeat.',
    'je Tag': 'per day',
    'je Woche': 'per week',
    'zu dicht?': 'too close?',
    'Unbekanntes Budget: {key}': 'Unknown budget: {key}',
    '„{key}“: mindestens eine Angabe — Anzahl oder Abstand.': '"{key}": at least one entry — count or gap.',
    'Budget-Zeile {n} passt nicht: „{line}“ — Form: key day|week Anzahl Abstand queue|drop': 'Budget line {n} does not fit: "{line}" — form: key day|week count gap queue|drop',
    'Szenarien nicht verfügbar — Migration 011 fehlt.': 'Scenarios not available — migration 011 missing.',
    'Diesen Namen gibt es schon.': 'That name exists already.',
    'Szenario gespeichert.': 'Scenario saved.',
    'Szenario gelöscht — wo es lief, ist es beendet.': 'Scenario deleted — where it ran, it has ended.',
    'Szenario beendet — Plan, Auflagen, Budgets und Tagesform sind zurück.': 'Scenario ended — plan, sanctions, budgets and day form are back.',
    'Szenario nicht aktiviert: {why}': 'Scenario not activated: {why}',
    'Szenario aktiv bis {until}.': 'Scenario active until {until}.',
    'aktiviert von': 'activated by',
    'Szenario beenden? Plan, Auflagen, Budgets und Tagesform gehen zurück.': 'End the scenario? Plan, sanctions, budgets and day form go back.',
    'keines angelegt': 'none created',
    'Aktivieren': 'Activate',
    'Szenarien verwalten': 'Manage scenarios',
    'z. B. reward day 3 - drop': 'e.g. reward day 3 - drop',
    'quittieren':
        'acknowledge',
    'zurücknehmen':
        'undo',
    'quittiert':
        'acknowledged',
    'quittiert von {b}, {a}':
        'acknowledged by {b}, {a}',
    'Zur Kenntnis genommen — bis sich der Inhalt ändert':
        'Noted — until the content changes',
    'Quittierung zurückgenommen.':
        'Acknowledgement withdrawn.',
    'Diese Bedingung lässt sich nicht quittieren.':
        'This condition cannot be acknowledged.',
    'Die Bedingung besteht nicht mehr.':
        'The condition is gone.',
    'Quittiert: {k}':
        'Acknowledged: {k}',
    'Gerät nicht gefunden.':
        'Device not found.',
    'JPEG oder PNG (max. 8 MB)':
        'JPEG or PNG (max. 8 MB)',
    'Das Original bleibt erhalten; gezeigt wird ein Ausschnitt im Verhältnis 4:5 — so wie Webseite und HDMI-Anzeige ihn ohnehin zeichnen.':
        'The original is kept; what is shown is a 4:5 section — the ratio the web page and the HDMI display draw anyway.',
    'Ausschnitt wählen':
        'Choose the section',
    'Ziehen verschiebt, der Regler zoomt. Was im Rahmen steht, steht später auf der Anzeige.':
        'Drag to move, the slider zooms. What is inside the frame is what the display shows.',
    'Original':
        'Original',
    'Zoom':
        'Zoom',
    'Ausschnitt speichern':
        'Save section',
    'Mitte':
        'Centre',
    'Original {w} × {h} Pixel':
        'Original {w} × {h} pixels',
    'Ausschnitt gespeichert — die Anzeige nutzt ihn ab sofort.':
        'Section saved — the display uses it from now on.',
    'Foto gespeichert — unten lässt sich der Ausschnitt wählen.':
        'Photo saved — the section can be chosen below.',
    'Das Bild lässt sich nicht lesen.':
        'The image cannot be read.',
    'Kein Original vorhanden — bitte neu hochladen.':
        'No original present — please upload again.',
}
