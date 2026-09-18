# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Red or green — is there anything to look at on this device? (doc 42 point 2)

TWO COLOURS, AND A LIST, NOT A SUM

The proposal was a health score in percent. Decided against it (Philine
2026-09-15): "80 % warning" tells the supervisor nothing about a participant
wearing a collar. Red tells her to look, and then the device card says WHY.

So red is a LIST OF CONDITIONS, each of which suffices on its own — not a
weighted mean. A mean hides which combination produced the colour; a list can
be read, and every condition can be tested with its counter-proof. Everything
this module returns is a reason the supervisor can act on.

WHAT MAKES A DEVICE RED

  offline        no sign of life — the one everybody agrees on
  emergency      the device sits in its frozen state
  blocked        firmware below the floor; it accepts no commands
  outdated       firmware below the current version; it runs, with a notice
  restart        an unwanted restart today (brownout, panic, watchdog), or
                 ANY restart in the last ten minutes
  rssi           the signal is weaker than the installation tolerates
  heap           free memory below the limit — the usual prelude to a panic
  safety         a safety event today: emergency, mac mismatch, rejected
                 signature, refused control telegram
  degraded       the device reports a component it cannot use (doc 42 point 4)

What is NOT here, deliberately: response times and MQTT drop counts. Both
need a history the installation does not keep yet, and a condition that reads
"unknown" as "fine" would be the opposite of the fail-safe rule everywhere
else. They come when the data does.

The thresholds are module constants with an optional `[health]` section in
config.ini. Constants, so that a bench without a config gets the same answer
as the installation.

ACKNOWLEDGING, AND WHY IT BINDS TO THE CONTENT (2.3.3, doc 55)

"A monitor that is permanently red is one nobody takes seriously any more"
(Philine 2026-09-16). After a flash a device stands red until midnight, because
the restarts of today are counted — including the ones somebody caused on
purpose.

So every condition carries a MARK: the content that produced it. The restart
counts per reason, the list of components for `degraded`, the measured value
for signal and memory. An acknowledgement is stored against (device, key,
mark), and it holds only while the mark is unchanged. A second brownout stays
quiet, a third reports again.

An acknowledged condition is NOT deleted — it moves to `acked` and stays
readable in the interface, greyed out, with who and when. Hiding it would be
the same failure as the permanent red, only harder to notice.

Three conditions cannot be acknowledged at all (decision Philine 2026-09-16):
`blocked` (the device takes no commands anyway; only a flash lifts that),
`emergency` (a state that must be cleared, not noted), and `safety` (whoever
clicks that away clicks away exactly what the checks were built for).
"""

import datetime

import i18n

# --- thresholds ------------------------------------------------------------ #
RSSI_MIN_DBM = -80          # weaker than this and the collar drops out of the
                            # V-Cage by itself; a device that lives here is a
                            # device that will vanish
HEAP_MIN_BYTES = 40000      # an ESP32 with less than this free is one JSON
                            # away from a panic
RESTART_RECENT_S = 600      # any restart within this window is red
UNWANTED_RESET = ('brownout', 'panic', 'task_wdt', 'int_wdt', 'wdt', 'unknown')
SAFETY_ACTIONS = ('emergency', 'device_mac_mismatch', 'signature_rejected',
                  'control_rejected', 'device_blocked')

# What may never be acknowledged. Decided, not derived — the reasons are at
# the top of this file.
NOT_ACKABLE = ('blocked', 'emergency', 'safety')


def configure(cfg):
    """Read `[health]` from the config, if present. Only known keys, only ints."""
    global RSSI_MIN_DBM, HEAP_MIN_BYTES, RESTART_RECENT_S
    if cfg is None or 'health' not in cfg:
        return
    h = cfg['health']
    try:
        RSSI_MIN_DBM = int(h.get('rssi_min_dbm', RSSI_MIN_DBM))
        HEAP_MIN_BYTES = int(h.get('heap_min_bytes', HEAP_MIN_BYTES))
        RESTART_RECENT_S = int(h.get('restart_recent_s', RESTART_RECENT_S))
    except (TypeError, ValueError):
        pass


class Health:
    """The answer: `red` and the reasons, each (key, text, mark).

    `reasons` are the open ones — they make the device red. `acked` are the
    ones somebody has taken note of with exactly this content; they stay
    readable but no longer colour the device. Two lists and not a flag,
    because the interface has to show both without asking twice.
    """

    def __init__(self):
        self.reasons = []
        self.acked = []          # (key, text, mark, by, at)

    def add(self, key, text, mark=''):
        """Add a condition. `mark` is the content an acknowledgement binds to.

        Empty mark = the condition has no content worth distinguishing (it is
        simply there or not). It is then still acknowledgeable — the mark is
        just constant.
        """
        self.reasons.append((key, text, str(mark)))

    def ackable(self, key):
        return key not in NOT_ACKABLE

    def apply_acks(self, acks):
        """Move every condition whose (key, mark) is acknowledged to `acked`.

        acks: {key: {'mark': str, 'by': str, 'at': datetime}}

        A condition that cannot be acknowledged stays where it is, even if a
        row exists for it — the rule lives here and not only in the interface,
        so that an old row or a hand-written INSERT cannot turn a device green
        that must not be.
        """
        if not acks:
            return self
        open_, done = [], list(self.acked)
        for key, text, mark in self.reasons:
            a = acks.get(key)
            if a and self.ackable(key) and str(a.get('mark', '')) == mark:
                done.append((key, text, mark, a.get('by', ''), a.get('at')))
            else:
                open_.append((key, text, mark))
        self.reasons, self.acked = open_, done
        return self

    @property
    def red(self):
        return bool(self.reasons)

    @property
    def colour(self):
        return 'red' if self.red else 'green'

    @property
    def keys(self):
        return [k for k, _, _ in self.reasons]

    def text(self):
        return ' · '.join(t for _, t, _ in self.reasons)

    def acked_text(self):
        return ' · '.join(t for _, t, _, _, _ in self.acked)

    def as_dict(self):
        return {'red': self.red,
                'reasons': [{'key': k, 'text': t, 'mark': m, 'ackable': self.ackable(k)}
                            for k, t, m in self.reasons],
                'acked': [{'key': k, 'text': t, 'mark': m, 'by': b,
                           'at': a.isoformat(sep=' ', timespec='minutes') if a else ''}
                          for k, t, m, b, a in self.acked]}


def judge(dev, boots_today=None, safety_today=0, blocked_reason='', outdated_reason='',
          now=None, acks=None):
    """Judge ONE device.

    dev            the entry from webmqtt.snapshot(): uuid, online, hello, state
    boots_today    rows of device_boots for this device since midnight
                   (dicts with db_reason, db_seen); None = table not there
    safety_today   number of safety events for this device today (audit_log)
    blocked_reason from devices.dev_blocked / fwversion — non-empty = blocked
    outdated_reason from fwversion when the device runs below `current`
    acks           {key: {'mark','by','at'}} from device_acks for this device
    """
    now = now or datetime.datetime.now()
    h = Health()
    st = (dev or {}).get('state') or {}
    hello = (dev or {}).get('hello') or {}

    if not (dev or {}).get('online'):
        # The mark carries SINCE WHEN. Without it one acknowledgement of
        # "offline" would cover every future outage of this device as well —
        # the condition would be switched off, not taken note of.
        h.add('offline', i18n._('offline'),
              mark='seit %s' % int((dev or {}).get('last_seen') or 0))
        # Nothing below can be judged about a device that is not there — its
        # state is history. The restart and safety lines still apply: they
        # are about today, not about now.
    else:
        if st.get('state') == 'emergency':
            h.add('emergency', i18n._('EMERGENCY — eingefroren'), mark='emergency')
        rssi = st.get('rssi')
        if isinstance(rssi, (int, float)) and rssi != 0 and rssi < RSSI_MIN_DBM:
            h.add('rssi', i18n._('Signal schwach ({r} dBm)', r=int(rssi)), mark=str(int(rssi)))
        heap = st.get('heap_free', (hello.get('boot') or {}).get('heap_free'))
        if isinstance(heap, (int, float)) and heap and heap < HEAP_MIN_BYTES:
            h.add('heap', i18n._('wenig Speicher ({k} kB frei)', k=int(heap) // 1024),
                  mark=str(int(heap) // 1024))
        deg = hello.get('degraded')
        if isinstance(deg, (list, tuple)) and deg:
            # Sorted, so that the same set in a different order is the same
            # content — the firmware makes no promise about the order.
            h.add('degraded', i18n._('Komponenten abgemeldet: {c}', c=', '.join(str(x) for x in deg)),
                  mark=','.join(sorted(str(x) for x in deg)))

    if blocked_reason:
        h.add('blocked', i18n._('gesperrt: {r}', r=blocked_reason), mark=blocked_reason)
    elif outdated_reason:
        # The mark is the version, not the sentence: a device that is
        # deliberately left on an older version stays acknowledged until it is
        # flashed to something else.
        h.add('outdated', i18n._('Firmware nicht aktuell'), mark=outdated_reason)

    if boots_today:
        unwanted = [b for b in boots_today if (b.get('db_reason') or 'unknown') in UNWANTED_RESET]
        recent = [b for b in boots_today
                  if b.get('db_seen') and (now - b['db_seen']).total_seconds() < RESTART_RECENT_S]
        if unwanted:
            by = {}
            for b in unwanted:
                by[b['db_reason']] = by.get(b['db_reason'], 0) + 1
            # THE CASE THIS WAS BUILT FOR. The mark is the count per reason,
            # so a device that was restarted twice while flashing goes green
            # once that is acknowledged — and red again at the third restart,
            # which is exactly the one nobody caused on purpose.
            h.add('restart', i18n._('heute neu gestartet: {w}',
                                    w=', '.join(f'{n}× {r}' for r, n in sorted(by.items()))),
                  mark=','.join(f'{r}={n}' for r, n in sorted(by.items())))
        elif recent:
            last = max(b['db_seen'] for b in recent)
            h.add('restart', i18n._('vor {m} min neu gestartet',
                                    m=int((now - last).total_seconds() // 60)),
                  mark=last.strftime('%Y-%m-%d %H:%M'))

    if safety_today:
        h.add('safety', i18n._('{n} Sicherheitsereignis(se) heute', n=int(safety_today)),
              mark=str(int(safety_today)))
    return h.apply_acks(acks)
