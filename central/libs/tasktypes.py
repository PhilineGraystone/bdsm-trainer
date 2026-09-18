# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Task types of the logbook (doc 14) — code registry, no mirror in the DB.

For every trainable action (libs/actions.py, trainable=True) this states
  - what the target of the run consists of (duration, repetitions, rounds),
  - how the task level sharpens the parameters (scale/bump),
  - which metrics the result event (cls result) of the device delivers,
  - how the grade A–F comes out of that,
  - which metric counts as the personal best performance,
  - whether a violation ends the run (fail_ends) or only counts.

Grading rule (doc 14 §4): duration/counting tasks over the achieved share of
the target AND the punishments; the worse of the two partial grades applies.
  Share:     >= 100 % A · >= 75 % C · >= 50 % D · >= 25 % E · otherwise F
  Penalties: 0 A · <= max B · <= 2×max C · <= 3×max D · <= 4×max E · otherwise F
Tasks in which a violation does not mean the end (Pet, sleep deprivation,
statue) are graded only over the punishments, provided they ran to the end;
an abort (stop, EMERGENCY, sign-off, device gone) is not scored.
"""

from dataclasses import dataclass, field

import i18n

GRADES = 'ABCDEF'


def worse(a, b):
    return a if GRADES.index(a) >= GRADES.index(b) else b


def grade_ratio(ratio):
    if ratio >= 0.999:
        return 'A'
    if ratio >= 0.75:
        return 'C'
    if ratio >= 0.5:
        return 'D'
    if ratio >= 0.25:
        return 'E'
    return 'F'


def grade_punish(punish, max_punish):
    punish = int(punish or 0)
    m = max(0, int(max_punish))
    if punish == 0:
        return 'A'
    if m == 0:
        return 'CDEF'[min(punish - 1, 3)]
    if punish <= m:
        return 'B'
    if punish <= 2 * m:
        return 'C'
    if punish <= 3 * m:
        return 'D'
    if punish <= 4 * m:
        return 'E'
    return 'F'


def grade_combined(ratio, punish, max_punish):
    """Share of the target AND punishments: the worse partial grade; 100 % with
    punishments within max = B."""
    g = worse(grade_ratio(ratio), grade_punish(punish, max_punish))
    return g


@dataclass(frozen=True)
class TaskType:
    code: str
    kind: str                       # 'duration' | 'count' | 'precision'
    target_param: str               # parameter that holds the target
    target_factor: int = 1          # conversion into the target unit (min -> s: 60)
    target_unit: str = 's'
    fail_ends: bool = False         # a violation ends the run (nose button) instead of only counting
    best_metric: str = 'duration_s'
    best_higher: bool = True
    # Task level: param -> factor per level above 1 (multiplicative, rounded)
    scale: dict = field(default_factory=dict)
    # Task level: param -> (step every n levels, +/-1, upper limit) for distractions
    bump: dict = field(default_factory=dict)
    # Result event of the device: name(s) of the event
    result_events: tuple = ('mode_end',)
    # Target default for the automatic weekly plan (in the target unit)
    plan_default: int = 600
    plan_step: float = 1.1          # proposal: last target × factor
    # Estimated duration of a run in seconds: f(params) -> int. None = the target value
    # in seconds (duration tasks). With it the central unit fills the blocks of the day
    # plan (doc 14 §12.1) — counting tasks need the conversion target -> time.
    est: object = None
    # Metric against which the achieved share is measured when it is not the
    # running time (endurance: longest hold against the hold time). The share
    # then counts towards the grade (review 2026-09-10: before that a timeout
    # without holding gave a share of 1.0 and the grade came only from the
    # punishments).
    ratio_metric: str = None
    # The task level SELECTS a variant instead of scaling a target (project doc 17:
    # each waveform carries its own level). `scale`/`bump` stay empty in that case.
    level_select: bool = False

    def target(self, params):
        """Target in the task's own unit. 0 means it does not come from a step
        parameter but from the task itself (see level_select)."""
        v = params.get(self.target_param)
        if v is None:
            return 0
        return int(v) * self.target_factor

    def apply_level(self, params, level, level_max=10):
        """Sharpen the parameters according to the task level (level 1 = unchanged)."""
        level = max(1, min(int(level or 1), level_max))
        if level == 1:
            return dict(params)
        out = dict(params)
        for name, factor in self.scale.items():
            if name in out and out[name] not in (None, 0):
                out[name] = int(round(out[name] * (factor ** (level - 1))))
        for name, (every, step, cap) in self.bump.items():
            if name in out and out[name] is not None:
                out[name] = max(0, min(cap, out[name] + step * ((level - 1) // every)))
        return out

    def est_seconds(self, params):
        """Estimated duration of a run (seconds) out of the parameters."""
        try:
            if self.est is not None:
                return max(30, int(self.est(params)))
            return max(30, int(self.target(params)))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return 300

    def achieved_ratio(self, run, metrics, reason):
        """Share of the target that the run has achieved (0..1)."""
        target = run.target or 0
        if self.ratio_metric:
            v = metrics.get(self.ratio_metric)
            if v is None:
                return 1.0 if reason == 'done' else 0.0
            return min(1.0, float(v) / target) if target else (1.0 if reason == 'done' else 0.0)
        if self.kind == 'duration':
            if not self.fail_ends:
                # Did the mode run to its intended end? (max_duration, switched, off, count)
                #
                # `off` came with 2.0: since then the collar reports the
                # explicit switching off (command mode 0) separately from the
                # change to another mode. Were it missing here, every run that a
                # REMOTE_CONTROL step ends as planned would suddenly get a grade
                # by duration instead of the full one — and nobody would have
                # noticed it except the slave.
                return 1.0 if reason in ('max_duration', 'switched', 'off', 'count', 'done', 'program') else \
                    min(1.0, (metrics.get('duration_s') or 0) / target) if target else 0.0
            held = metrics.get('held_s', metrics.get('duration_s', 0)) or 0
            return min(1.0, held / target) if target else (1.0 if reason == 'done' else 0.0)
        if self.kind in ('count', 'precision'):
            hits = metrics.get('hits', metrics.get('rounds_reached', metrics.get('strokes')))
            if hits is None:
                return 1.0 if reason == 'done' else 0.0
            return min(1.0, hits / target) if target else (1.0 if reason == 'done' else 0.0)
        return 1.0 if reason == 'done' else 0.0

    def grade(self, run, metrics, reason, punish, max_punish):
        ratio = self.achieved_ratio(run, metrics, reason)
        if self.kind == 'duration' and not self.fail_ends and not self.ratio_metric:
            return grade_punish(punish, max_punish), ratio
        return grade_combined(ratio, punish, max_punish), ratio

    def best_value(self, metrics):
        v = metrics.get(self.best_metric)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def is_better(self, new, old):
        if new is None:
            return False
        if old is None:
            return True
        return new > old if self.best_higher else new < old


TASKS = (
    # Collar modes: the device punishes locally, the result comes with mode_end (cls result)
    TaskType('PET', 'duration', 'max_min', 60, 's', fail_ends=False, best_metric='duration_s',
             scale={'max_min': 1.1}, bump={'angle': (2, -5, 85), 'repeat_s': (3, -2, 300)},
             plan_default=1800),
    TaskType('SLEEP_DEPRIVATION', 'duration', 'max_min', 60, 's', fail_ends=False, best_metric='duration_s',
             scale={'max_min': 1.1}, bump={'still_s': (2, -5, 1800)}, plan_default=1800),
    TaskType('STATUE', 'duration', 'max_min', 60, 's', fail_ends=False, best_metric='duration_s',
             scale={'max_min': 1.1}, bump={'angle': (2, -2, 60)}, plan_default=300),
    # Trainer
    TaskType('TRAINER_REPETITION', 'count', 'count', 1, 'x', fail_ends=True, best_metric='best_depth_mm',
             est=lambda p: p['count'] * p['stroke_s'],
             best_higher=False, scale={'count': 1.1}, bump={'depth_end': (1, 3, 100), 'stroke_s': (2, -1, 60)},
             result_events=('trainer_end',), plan_default=20),
    TaskType('TRAINER_ENDURANCE', 'duration', 'hold_s', 1, 's', fail_ends=False, best_metric='best_hold_s',
             est=lambda p: p['max_s'],
             scale={'hold_s': 1.15}, bump={'depth': (1, 3, 100)}, result_events=('trainer_end',), plan_default=30,
             ratio_metric='best_hold_s'),
    TaskType('TRAINER_FREEFORM', 'duration', 'minutes', 60, 's', fail_ends=False, best_metric='strokes',
             scale={'minutes': 1.1}, result_events=('trainer_end',), plan_default=300),
    # Waveform routine (project doc 17). The target is the required score and comes
    # from the task or from the waveform, never from a step parameter; the level picks
    # which waveform runs.
    TaskType('TRAINER_ROUTINE', 'precision', 'min_score', 1, 'score', fail_ends=False,
             best_metric='score', best_higher=True, result_events=('trainer_end',),
             plan_default=6000, plan_step=1.0, level_select=True, ratio_metric='score',
             est=lambda p: 300 * max(1, int(p.get('repeats') or 1))),    # TaskPad
    TaskType('NOSE_BUTTON', 'duration', 'target_s', 1, 's', fail_ends=True, best_metric='held_s',
             est=lambda p: p['target_s'] + p['start_s'],
             scale={'target_s': 1.15}, bump={'vibe': (3, 1, 3), 'wobble_ms': (2, -30, 2000)},
             result_events=('task_end',), plan_default=120),
    TaskType('REACTION', 'count', 'rounds', 1, 'x', fail_ends=False, best_metric='mean_rt_ms', best_higher=False,
             est=lambda p: p['rounds'] * ((p['gap_min_s'] + p['gap_max_s']) / 2 + p['deadline_ms'] / 1000),
             scale={'deadline_ms': 0.92}, bump={'vibe': (3, 1, 3)}, result_events=('task_end',), plan_default=20),
    TaskType('RHYTHM', 'precision', 'beats', 1, 'x', fail_ends=False, best_metric='mean_dev_ms', best_higher=False,
             est=lambda p: p['beats'] * 60 / max(1, p['bpm']) + 5,
             scale={'tol_ms': 0.9, 'bpm': 1.05}, result_events=('task_end',), plan_default=60),
    TaskType('MEMORY', 'count', 'rounds', 1, 'x', fail_ends=True, best_metric='rounds_reached',
             est=lambda p: p['rounds'] * (p['rounds'] + 1) / 2 * (p['show_ms'] / 1000 + 0.6) + p['rounds'] * 4,
             scale={'show_ms': 0.9}, bump={'rounds': (2, 1, 30), 'vibe': (3, 1, 3)},
             result_events=('task_end',), plan_default=6),
    # Holding tasks (firmware to follow)
    TaskType('TRAY', 'duration', 'target_s', 1, 's', fail_ends=True, best_metric='held_s',
             scale={'target_s': 1.15}, bump={'tolerance': (2, -1, 45)}, result_events=('task_end',), plan_default=180),
    TaskType('SILENCE', 'duration', 'target_s', 1, 's', fail_ends=False, best_metric='duration_s',
             scale={'target_s': 1.15}, result_events=('task_end',), plan_default=600),
    TaskType('KNEEL', 'duration', 'target_s', 1, 's', fail_ends=False, best_metric='duration_s',
             scale={'target_s': 1.15}, bump={'tolerance': (2, -1, 60)}, result_events=('task_end',), plan_default=600),
)

TASKS_BY_CODE = {t.code: t for t in TASKS}

# Aid for display/web: short names of the metrics
METRIC_LABELS = {
    'duration_s': 'Dauer (s)', 'held_s': 'gehalten (s)', 'punish': 'Bestrafungen', 'warn': 'Warnungen',
    'violations': 'Verstöße', 'out_s': 'außerhalb (s)', 'hits': 'Treffer', 'misses': 'Fehler',
    'best_depth_mm': 'tiefster Stoß (mm)', 'best_hold_s': 'längstes Halten (s)', 'strokes': 'Stöße',
    'mean_rt_ms': 'Reaktion Ø (ms)', 'best_rt_ms': 'Reaktion beste (ms)', 'mean_dev_ms': 'Taktabweichung Ø (ms)',
    'rounds_reached': 'Runden', 'wobbles': 'Wackler', 'tempo_dev_pct': 'Taktabweichung (%)',
    # waveform routine (project doc 17)
    'score': 'Score', 'in_zone_pct': 'im Ziel (%)', 'ticks': 'Abtastungen',
    'ticks_invalid': 'ungültige Abtastungen', 'mean_dev_pct': 'Abweichung Ø (%)',
}


def get(code):
    return TASKS_BY_CODE.get(code)


def is_trainable(code):
    return code in TASKS_BY_CODE


def metric_label(key):
    """Label of a metric in the current language."""
    return i18n._(METRIC_LABELS.get(key, key))
