# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Which broker account does this process speak as? (2.1.1)

WHY THIS IS A MODULE AND NOT THREE LINES IN THREE FILES

The broker's access list (config/mosquitto/punisher.acl) can only separate what
the broker can tell apart. Up to 2.1.0 the central unit, the web interface, the
display and every device connected as the same `punisher` — so no rule about
"what may a device publish" could bite at all, and a compromised device could
have written a validly signed `punisher/central/request` (finding Philine
2026-09-15, project document 40).

From 2.1.1 each process has a section of its own, and each falls back to
`[mqtt]` when that section is missing. The fallback exists so that an
installation upgraded without touching config.ini keeps running — but it is
reported, every time, because an access list without effect is worse than no
access list: it looks like protection.

One place, so the three call sites cannot drift into three different answers
about what counts as "has an account of its own".
"""


def account(config, section):
    """(user, password, has_own_section) for this process.

    `section` is 'mqtt_web' or 'mqtt_display'; the central unit uses 'mqtt'
    directly, because it is the one that has always had it.
    """
    base = config['mqtt'] if 'mqtt' in config else {}
    own = section in config and (config[section].get('username') or '').strip()
    src = config[section] if own else base
    return (src.get('username', '') or '').strip(), src.get('password', '') or '', bool(own)
