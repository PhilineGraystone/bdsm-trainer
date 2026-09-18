# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Mystery block (project document 44 §6) — the pool and the draw.

A `mystery` block in the day plan carries a POOL of allowed entries in its
text field and a time window (its minutes). The central unit draws, inside
the block, a moment and one entry; the screen shows "?" instead of the next
task. The pool is the safety boundary: the draw only ever takes what is in
it AND what is allowed for this slave anyway — a task she has the device for,
a punishment or reward that the channel, the ceiling, the sanctions and the
budgets would let through at that moment. Nothing here bypasses a limit; the
draw just decides WHICH of the allowed things happens, and WHEN.

The pool may hold tasks, punishments AND rewards (decision Philine
2026-09-16): a pool that can only threaten is weaker than one that can do
both.

Pool syntax (the block's text field), comma separated:
    PET, NOSE_BUTTON        task codes (trainable actions)
    punish:2                a punishment over the channel, level 1..3
    reward:1                a reward over the channel, level 1..3

The draw is written to the audit log BEFORE it happens (`mystery_drawn`, with
the moment) — only the slave does not know.
"""

import random

import actions
import tasktypes

PUNISH, REWARD, TASK = 'punish', 'reward', 'task'


def parse_pool(text):
    """'PET, punish:2, reward:1' -> [('task','PET',None), ('punish',None,2), ('reward',None,1)].
    Unknown entries are dropped silently here; the editor refuses them up front."""
    out = []
    for raw in str(text or '').replace(';', ',').split(','):
        p = raw.strip()
        if not p:
            continue
        low = p.lower()
        if low.startswith((PUNISH + ':', REWARD + ':')):
            kind, _, lvl = low.partition(':')
            if lvl.strip().isdigit() and 1 <= int(lvl) <= 3:
                out.append((kind, None, int(lvl)))
            continue
        if low in (PUNISH, REWARD):
            out.append((low, None, 1))
            continue
        code = p.upper()
        a = actions.get(code)
        if a is not None and a.trainable and tasktypes.get(code) is not None:
            out.append((TASK, code, None))
    return out


def pool_error(text):
    """None when every entry is valid, else the first offending entry (for the editor)."""
    for raw in str(text or '').replace(';', ',').split(','):
        p = raw.strip()
        if not p:
            continue
        if parse_pool(p):
            continue
        return p
    if not parse_pool(text):
        return ''
    return None


def describe(entry):
    kind, code, lvl = entry
    if kind == TASK:
        a = actions.get(code)
        return a.name if a else code
    return '%s:%d' % (kind, lvl)


def draw(entries, rnd=None):
    """One entry out of the allowed ones, uniformly. None for an empty list."""
    if not entries:
        return None
    return (rnd or random).choice(list(entries))


def draw_delay(budget_s, need_s, gap_s, rnd=None):
    """A moment inside the window: at least gap_s from now, and early enough that
    `need_s` (the drawn entry's own duration) still fits before the window ends."""
    lo = max(0, int(gap_s))
    hi = max(lo, int(budget_s) - int(need_s) - int(gap_s))
    return (rnd or random).randint(lo, hi)
