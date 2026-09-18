#!/usr/bin/env python3
# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Holds the firmware's version numbers up against one another.

They exist in three places — PunisherVersion.h, library.properties and a
version.h per sketch — and that is exactly how they drift apart: somebody
raises one and forgets the other. After that a device reports a version it is
not, and the central unit's minimum-version floor checks against a number
nobody has maintained. So a machine checks it here.

It is also checked that no creds.h still carries a version or a device_UUID:
both were dropped with 2.0, and a forgotten leftover would be a value that
somebody picks up again later.

Call:  python3 test_versions.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.normpath(os.path.join(HERE, '..'))

checks = 0
fails = 0


def ok(what, cond, detail=''):
    global checks, fails
    checks += 1
    if cond:
        print(f'  OK   {what}')
    else:
        fails += 1
        print(f'  FEHL {what}' + (f'\n       {detail}' if detail else ''))


def defines(path):
    out = {}
    for line in open(path, encoding='utf-8'):
        m = re.match(r'\s*#define\s+(\w+)\s+(.+?)\s*$', line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"')
    return out


print('Framework')
v = defines(os.path.join(FW, 'src', 'PunisherVersion.h'))
fw = (v.get('PUNISHERDEVICE_VERSION_MAJOR'),
      v.get('PUNISHERDEVICE_VERSION_MINOR'),
      v.get('PUNISHERDEVICE_VERSION_PATCH'))
ok('alle drei Zahlen stehen in PunisherVersion.h', all(fw))
fw_txt = '.'.join(x for x in fw if x)
ok(f'VERSION_STR passt zu den Zahlen ({fw_txt})',
   v.get('PUNISHERDEVICE_VERSION_STR') == fw_txt,
   f"STR={v.get('PUNISHERDEVICE_VERSION_STR')} Zahlen={fw_txt}")

props = {}
for line in open(os.path.join(FW, 'library.properties'), encoding='utf-8'):
    if '=' in line:
        k, _, val = line.partition('=')
        props[k.strip()] = val.strip()
ok(f'library.properties traegt dieselbe Version ({fw_txt})',
   props.get('version') == fw_txt,
   f"library.properties={props.get('version')} PunisherVersion.h={fw_txt}")

print('\nSketche')
ex = os.path.join(FW, 'examples')
sketches = sorted(d for d in os.listdir(ex) if os.path.isdir(os.path.join(ex, d)))
ok('es gibt Sketche', bool(sketches))
for d in sketches:
    vh = os.path.join(ex, d, 'version.h')
    if not os.path.exists(vh):
        ok(f'{d}: version.h vorhanden', False)
        continue
    sv = defines(vh)
    trio = (sv.get('SKETCH_VERSION_MAJOR'), sv.get('SKETCH_VERSION_MINOR'),
            sv.get('SKETCH_VERSION_PATCH'))
    ok(f'{d}: Name und drei Zahlen', bool(sv.get('SKETCH_NAME')) and all(trio),
       f'{sv}')
    # The major MUST match the framework: 2.0 is incompatible with 1.x in both
    # directions, there is no such thing as a mixed device.
    ok(f'{d}: Major wie das Framework ({fw[0]})', trio[0] == fw[0],
       f'Sketch={trio[0]} Framework={fw[0]}')

    ino = os.path.join(ex, d, f'{d}.ino')
    if os.path.exists(ino):
        src = open(ino, encoding='utf-8').read()
        ok(f'{d}: bindet version.h ein', '#include "version.h"' in src)
        ok(f'{d}: setzt keine deviceUuid mehr', 'cfg.deviceUuid' not in src)
        ok(f'{d}: benutzt kein cfg.fwVersion mehr', 'cfg.fwVersion' not in src)
        ok(f'{d}: reicht den Projektschluessel durch', 'cfg.projectKey' in src)

print('\ncreds.h — was dort nicht mehr stehen darf')
import glob
for p in sorted(glob.glob(os.path.join(ex, '*', 'creds.h'))):
    name = os.path.basename(os.path.dirname(p))
    s = open(p, encoding='utf-8').read()
    ok(f'{name}: keine device_UUID mehr', 'device_UUID' not in s)
    ok(f'{name}: keine FW_VERSION mehr', 'FW_VERSION' not in s)
    ok(f'{name}: traegt einen PROJECT_KEY', 'PROJECT_KEY' in s)

print(f'\n{checks} Pruefungen, {fails} Fehler')
sys.exit(0 if fails == 0 else 1)
