#!/usr/bin/env python3
"""Rechnet die Firmware gegen die Zentrale gegen.

Die Brücke und die Zentrale halten dieselben Zahlen zweimal: Profile, die
Frequenzumrechnung, die Interpolation der Kurve, die Kopplung und den CRC über
den Drahtstrom. Zwei Implementierungen derselben Sache driften auseinander,
sobald niemand hinsieht — hier sieht jemand hin.

    python3 check_against_central.py [pfad/zu/libs]

Erwartet das kompilierte ./t daneben (siehe test_coyotewave.cpp).
"""
import os
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
# The central unit's libs, relative to THIS file — not a path on one
# developer's machine. The old default was an absolute path on one bench —
# a fact about that bench, not about the repository (finding Philine 2026-09-15).
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(
    os.path.join(_HERE, '..', '..', '..', '..', '..', 'central', 'libs'))
sys.path.insert(0, LIBS)

# i18n braucht eine Flask-Umgebung; für den Vergleich reicht ein Stub, wir
# vergleichen Zahlen, keine Texte.
if 'i18n' not in sys.modules:
    import types
    stub = types.ModuleType('i18n')
    stub._ = lambda s, **kw: s.format(**kw) if kw else s
    stub.d = lambda d: d
    sys.modules['i18n'] = stub

import profiles          # noqa: E402
import routines          # noqa: E402

fails = []


def check(name, cond, info=''):
    print(('  OK   ' if cond else '  FAIL ') + name + (('  ' + info) if info and not cond else ''))
    if not cond:
        fails.append(name)


def run_dump():
    exe = os.path.join(HERE, 't')
    if not os.path.exists(exe):
        print('Erst bauen: g++ -std=c++11 -O2 -I.. -o t test_coyotewave.cpp')
        sys.exit(2)
    out = subprocess.run([exe, 'dump'], capture_output=True, text=True, check=True).stdout
    return [l.split(',') for l in out.splitlines() if l and not l.startswith('#')]


rows = run_dump()

# --------------------------------------------------------------------- #
# 1. Profilkatalog: Schlüssel, Rollen, Frequenzbänder, Schleifen
fw_keys = sorted({r[1] for r in rows if r[0] == 'P'})
py_keys = sorted(p.key for p in profiles.PROFILES)
check('Dieselben Profile in Firmware und Zentrale', fw_keys == py_keys,
      f'{fw_keys} vs {py_keys}')

# 2. Jeder einzelne Rahmen, durch die ECHTE Funktion der Zentrale gerechnet
#    (nicht nachgebaut - sonst prüfte der Vergleich die Nachbildung).
#    Verglichen wird, was auf den Draht geht: der gestauchte Frequenzwert und
#    die Intensität.
bad = []
for r in rows:
    if r[0] != 'P':
        continue
    key, step, inten = r[1], int(r[2]), int(r[3])
    hz_fw, per_fw, v3_fw, out_fw = float(r[4]), int(r[5]), int(r[6]), int(r[7])
    v3_py, out_py = profiles.frame(profiles.get(key), inten, step)
    if v3_fw != v3_py or out_fw != out_py:
        bad.append(f'{key}/{step}/{inten}: v3 {v3_fw} vs {v3_py}, out {out_fw} vs {out_py}')
check('Jeder Profilrahmen stimmt in Frequenzwert und Intensität überein',
      not bad, '; '.join(bad[:3]) + (f' ({len(bad)} von {sum(1 for r in rows if r[0] == "P")})' if bad else ''))

# 3. Die Frequenzumrechnung selbst, über den ganzen Bereich
def _v3(ms):
    if ms <= 100:
        return ms
    if ms <= 600:
        return (ms - 100) // 5 + 100
    return (ms - 600) // 10 + 200


bad = []
for ms in range(10, 1001):
    want = max(10, min(240, _v3(ms)))
    got = profiles.period_value(1000.0 / ms)
    if got != want:
        bad.append(f'{ms} ms: Zentrale {got}, Formel {want}')
check('Die Zentrale rechnet die Frequenz wie die offizielle Formel',
      not bad, '; '.join(bad[:3]) + (f' ({len(bad)} Abweichungen)' if bad else ''))

# 4. Kurveninterpolation gegen routines.target_at()
PTS = [(0, 0, 15), (3000, 35, 12), (8000, 35, 12), (11000, 15, 15),
       (14000, 60, 10), (20000, 60, 10)]
bad = []
for r in rows:
    if r[0] != 'C':
        continue
    x, v_fw = int(r[1]), float(r[2])
    v_py = routines.target_at(PTS, x)[0]
    if abs(v_fw - v_py) > 0.01:
        bad.append(f'x={x}: {v_fw} vs {v_py}')
check('Die Kurve wird auf beiden Seiten gleich interpoliert', not bad, '; '.join(bad[:3]))

# 5. Drahtformat und CRC gegen routines.serialise()
wire = [(int(r[1]), int(r[2]), int(r[3])) for r in rows if r[0] == 'W']
crc_fw = int([r[1] for r in rows if r[0] == 'CRC'][0])
blob = b''
x = 0
for dx, v, tol in wire:
    blob += dx.to_bytes(2, 'little') + bytes((v, tol))
crc_py = zlib.crc32(blob) & 0xFFFFFFFF
check('CRC32 über den Drahtstrom stimmt überein', crc_fw == crc_py,
      f'{crc_fw:08X} vs {crc_py:08X}')

# Und die Gegenprobe über den echten Serialisierer der Zentrale: dieselben
# Stützpunkte als (x, wert, toleranz) ergeben denselben Bytestrom.
pts_abs, x = [], 0
for dx, v, tol in wire:
    x += dx * 10
    pts_abs.append((x, v, tol))
check('Der Bytestrom der Zentrale ist derselbe',
      zlib.crc32(routines.serialise(pts_abs, routines.AXIS_TIME)) & 0xFFFFFFFF == crc_fw)

# 6. Kopplung gegen routines.output_at()
bad = []
for r in rows:
    if r[0] != 'K':
        continue
    mode, couple = r[1], r[2]
    value, depth, err = float(r[3]), float(r[4]), float(r[5])
    out_fw = float(r[8])
    track = {'rt_mode': mode, 'rt_couple': couple}
    live = {'depth': depth, 'err': err}
    out_py = routines.output_at(track, [(0, int(value), 0), (10, int(value), 0)], 5, live)
    if abs(out_fw - out_py) > 0.01:
        bad.append(f'{couple} v={value} d={depth} e={err}: {out_fw} vs {out_py}')
check('Die Kopplung rechnet auf beiden Seiten gleich', not bad, '; '.join(bad[:3]))

# 7. Rollen, Kanäle und Modi: die Namen auf dem Draht
check('Rollennamen der Zentrale sind die der Firmware',
      set(profiles.ROLES) == {'zieltiefe', 'bestrafung', 'stimulation', 'belohnung'})
check('Kanalnamen der Zentrale sind die der Firmware',
      set(profiles.CHANNELS) == {'a', 'b', 'vibe'})
check('Die Firmware kennt jede Rolle, die eine Ausgabespur haben kann',
      set(profiles.OUTPUT_ROLES) <= {'bestrafung', 'stimulation', 'belohnung'})

# 8. Das Profil einer Rolle: die Firmware nimmt bei unbekanntem Schlüssel das
#    erste Profil der Rolle — das muss dasselbe sein wie profiles.default_for().
for role in profiles.OUTPUT_ROLES:
    want = profiles.default_for(role)
    first = next((p.key for p in profiles.PROFILES if p.role == role), None)
    check(f'Vorgabeprofil der Rolle {role} ist eindeutig ({want})', want == first)

print()
if fails:
    print('ABWEICHUNGEN: ' + ', '.join(fails))
    sys.exit(1)
print('Firmware und Zentrale rechnen gleich.')
