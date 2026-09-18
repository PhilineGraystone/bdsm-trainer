#!/usr/bin/env python3
# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""The central unit's side: central/libs/punsign.py.

Two tasks:

1. Recompute the same expected values that test_crypto_identity.cpp has
   compiled in as constants. Should they diverge, firmware and central unit
   have drifted apart — and that shows up here, not only later on a device
   that can no longer log in.

2. Check the envelope, and do so with COUNTER-PROOFS. A signature check that
   merely confirms that correct input passes proves nothing: a check that
   always says "yes" passes it too. Every acceptance here has its counterpart
   that MUST be rejected.

Call:  python3 test_against_central.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(
    HERE, '..', '..', '..', 'central', 'libs')))

import punsign as p          # noqa: E402

checks = 0
fails = 0


def ok(what, cond):
    global checks, fails
    checks += 1
    if cond:
        print(f'  OK   {what}')
    else:
        fails += 1
        print(f'  FEHL {what}')


def eq(what, got, want):
    ok(f'{what}', got == want)
    if got != want:
        print(f'       erwartet {want}\n       bekommen {got}')


KEY = 'CHANGEME-PROJECT-KEY'
TOPIC = 'punisher/devices/abc/cmd'

print('Gleichstand mit der Firmware')
eq('UUID 02:00:00:00:00:01 / esp32',
   p.device_uuid('02:00:00:00:00:01', 'esp32'),
   'c0291207-a276-5771-8f23-586b527a8d57')
eq('UUID 02:00:00:00:00:01 / esp32s3',
   p.device_uuid('02:00:00:00:00:01', 'esp32s3'),
   '508e6d00-0b7e-5df8-8bba-c0eb9852170a')
eq('MAC-Schreibweise', p.mac_text('02-00-00-00-00-01'), '02:00:00:00:00:01')
eq('MAC auch ohne Trenner', p.mac_text('020000000001'), '02:00:00:00:00:01')

print('\nUUID-Eigenschaften')
ok('verschiedene MAC -> verschiedene UUID',
   p.device_uuid('02:00:00:00:00:01', 'esp32')
   != p.device_uuid('02:00:00:00:00:02', 'esp32'))
ok('anderer Chiptyp -> andere UUID',
   p.device_uuid('02:00:00:00:00:01', 'esp32')
   != p.device_uuid('02:00:00:00:00:01', 'esp32s3'))
ok('dieselbe Eingabe -> dieselbe UUID (kein Zufall drin)',
   p.device_uuid('02:00:00:00:00:01', 'esp32')
   == p.device_uuid('02:00:00:00:00:01', 'esp32'))
u = p.device_uuid('02:00:00:00:00:01', 'esp32')
ok('Version 5 und Variante RFC 4122', u[14] == '5' and u[19] in '89ab')

print('\nUmschlag: was durchgehen MUSS')
body = {'action': 'punish', 'id': 7, 'ts_ms': 1000, 'ttl_ms': 5000}
raw = p.sign(KEY, TOPIC, body)
got, why = p.verify(KEY, TOPIC, raw)
ok('richtig signiert geht durch', got == body and why is None)

print('\nUmschlag: was abgelehnt werden MUSS (Gegenproben)')
got, why = p.verify('ein-anderer-schluessel', TOPIC, raw)
ok(f'falscher Schluessel -> abgelehnt ({why})', got is None)

got, why = p.verify(KEY, 'punisher/devices/xyz/cmd', raw)
ok(f'anderes Geraetetopic -> abgelehnt ({why})', got is None)

tampered = raw.replace('\\"id\\":7', '\\"id\\":8')
got, why = p.verify(KEY, TOPIC, tampered)
ok(f'veraenderter Koerper -> abgelehnt ({why})', got is None)

got, why = p.verify(KEY, TOPIC, '{"v":1,"body":"{}"}')
ok(f'Signatur fehlt -> abgelehnt ({why})', got is None)

got, why = p.verify(KEY, TOPIC, 'kein json')
ok(f'kein JSON -> abgelehnt ({why})', got is None)

got, why = p.verify(KEY, TOPIC, raw.replace('"v":1', '"v":2'))
ok(f'fremde Umschlagversion -> abgelehnt ({why})', got is None)

# Replay: the very same, entirely valid envelope, just later.
got, why = p.verify(KEY, TOPIC, raw, max_age_ms=5000, now_ms=1000 + 20000)
ok(f'zu alt -> abgelehnt ({why})', got is None)
got, why = p.verify(KEY, TOPIC, raw, max_age_ms=5000, now_ms=1000 + 1000)
ok('innerhalb der Frist -> geht durch', got == body)
got, why = p.verify(KEY, TOPIC, raw, max_age_ms=5000, now_ms=1000 - 20000)
ok(f'aus der Zukunft -> abgelehnt ({why})', got is None)

print('\nNothalt bleibt ungeprueft')
ok('Broadcast-Nothalt', p.unsigned_topic('punisher/emergency'))
ok('Nothalt je Geraet', p.unsigned_topic('punisher/devices/abc/emergency'))
ok('ein Befehl dagegen nicht', not p.unsigned_topic('punisher/devices/abc/cmd'))

print('\nAnmeldung: Frage und Antwort')
nonce = p.new_nonce()
mac, uuid = '02:00:00:00:00:01', u
answer = p.login_proof(KEY, nonce, mac, uuid)
ok('richtige Antwort wird angenommen', p.check_login(KEY, nonce, mac, uuid, answer))
ok('zwei Fragen sind nie gleich', p.new_nonce() != p.new_nonce())
ok('Antwort auf eine ANDERE Frage wird abgelehnt',
   not p.check_login(KEY, p.new_nonce(), mac, uuid, answer))
ok('Antwort eines Geraets mit anderer MAC wird abgelehnt',
   not p.check_login(KEY, nonce, '02:00:00:00:00:09', uuid, answer))
ok('falscher Projektschluessel wird abgelehnt',
   not p.check_login('fremd', nonce, mac, uuid, answer))
ok('leere Antwort wird abgelehnt', not p.check_login(KEY, nonce, mac, uuid, ''))

print(f'\n{checks} Pruefungen, {fails} Fehler')
sys.exit(0 if fails == 0 else 1)
