# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""Device identity and message signature — the side of the central unit.

Twin of firmware/PunisherDevice/src/PunisherIdentity.* and
PunisherCrypto.*. Both sides must compute bit for bit alike; that is proven in
firmware/PunisherDevice/test/test_crypto_identity.cpp, which computes the same
cases and holds them against the output of this module.

WHAT STANDS HERE AND WHY

1. UUID FROM THE MAC
   Up to 1.x the device_UUID stood by hand in creds.h. From 2.0 on it is
   derived:

       UUID = SHA-256( NAMESPACE(16) || MAC(6) || chip type(ASCII) )[:16]
              with the version and variant nibble set (UUIDv5 form)

   That protects against ERRORS, not against manipulation: a changed firmware
   can report whatever it likes. The efuse value is unchangeable, the reported
   value is not.

2. SIGNATURE
   A project key lies on the central unit and on every device. With it every
   message is signed in both directions (HMAC-SHA256).

   NOT signed is the emergency stop — in both directions. A forged emergency
   shutdown switches off, that is the harmless direction. An emergency stop
   that fails a signature check would be the dangerous one.

   The envelope looks like this:

       {"v": 1, "sig": "<64 hex>", "body": "<the exact JSON string>"}

   WHY THE BODY IS A STRING AND NOT AN OBJECT
   Bytes are what get signed. If the signature went over an object, both sides
   would have to agree on a canonical spelling — order of the keys, whitespace,
   number format, escapes. That is exactly where such methods fail in practice,
   and silently at that: it fits for years, until one side changes its JSON
   library. Here the signed string itself is transmitted. There is nothing to
   canonicalise.

   The topic goes into the hash as well. Without that, a command for device A
   could be captured and replayed at device B — the same valid signature, a
   different human at the other end.

3. LOGIN (question and answer)
   A fixed value in the `hello` would be a show token: read along once,
   reusable as often as one likes. The central unit therefore sends a random
   number and the device answers with HMAC(key, nonce || mac || uuid).
"""

import hashlib
import hmac
import json
import secrets
import time

# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #

# Namespace of the project. NEVER change — every change hands out new
# identities to all devices of the installation. Mirror image of
# pun::IDENTITY_NAMESPACE in PunisherIdentity.cpp.
IDENTITY_NAMESPACE = bytes([
    0xa6, 0x36, 0x46, 0xd6, 0x57, 0x88, 0x45, 0x6a,
    0xb1, 0xe6, 0xfe, 0x59, 0xd5, 0x4b, 0xcf, 0x19,
])

# Chip types as a string. What stands here goes into the hash; that is why it
# is a table of its own and not the enum of the IDF, whose numbers can shift
# with a core update.
CHIP_TYPES = ('esp32', 'esp32s2', 'esp32s3', 'esp32c3', 'esp32c6', 'esp32h2',
              'unknown')


def mac_bytes(mac):
    """'aa:bb:cc:dd:ee:ff' (or 'aabbccddeeff', '-' allowed) -> 6 bytes."""
    if isinstance(mac, (bytes, bytearray)):
        if len(mac) != 6:
            raise ValueError('MAC braucht 6 Byte')
        return bytes(mac)
    clean = str(mac).replace(':', '').replace('-', '').replace('.', '').strip()
    if len(clean) != 12:
        raise ValueError(f'MAC unlesbar: {mac!r}')
    return bytes.fromhex(clean)


def mac_text(mac):
    """6 bytes or any spelling -> 'aa:bb:cc:dd:ee:ff' (lower case)."""
    b = mac_bytes(mac)
    return ':'.join(f'{x:02x}' for x in b)


def device_uuid(mac, chip):
    """The derived device UUID. Mirror image of pun::deriveUuid."""
    if chip not in CHIP_TYPES:
        # No error: a new chip type shall not stop the installation. It gets
        # its own, stable UUID, and the device list shows an unknown type.
        chip = str(chip)
    h = hashlib.sha256(IDENTITY_NAMESPACE + mac_bytes(mac)
                       + chip.encode('ascii', 'strict')).digest()
    u = bytearray(h[:16])
    u[6] = (u[6] & 0x0f) | 0x50          # Version 5
    u[8] = (u[8] & 0x3f) | 0x80          # variant RFC 4122
    hx = u.hex()
    return f'{hx[0:8]}-{hx[8:12]}-{hx[12:16]}-{hx[16:20]}-{hx[20:32]}'


# --------------------------------------------------------------------------- #
# Signature
# --------------------------------------------------------------------------- #

ENVELOPE_VERSION = 1

# WHAT GETS SIGNED — and what deliberately does not.
#
# Signed is everything that acts on a device or claims something about a
# device: commands, settings, login, state, events, log, readings and the two
# channels of the slave (on which the stimulators listen — a forged entry
# there lands on skin).
SIGNED_SUFFIXES = ('cmd', 'settings', 'hello', 'state', 'event', 'log', 'live',
                   'punish', 'reward', 'response')

# NOT signed, each with a reason:
#
#   emergency   the emergency stop, in BOTH directions. A forged emergency
#               shutdown switches off — that is the harmless direction. An
#               emergency stop that fails a signature check would be the
#               dangerous one.
#   available   the last will (LWT), and since 2.1.0 the ONLY place a device
#               is declared gone. The broker sends it when the connection
#               breaks off; at that moment the device computes nothing any
#               more, so it cannot supply a signature with a valid timestamp
#               at all. A forged "offline" message lets the central unit
#               believe a device is gone — it triggers nothing.
#   central/#   leaderboard and session for the display. Nothing acts there,
#               and the display shall show something even when things jam.
#               ONE EXCEPTION lives under that prefix and is signed:
#               punisher/central/heartbeat (see SIGNED_CENTRAL).
#
# `response` stood here until 2.1.0, on two grounds that had both expired: that
# it carried a bare model UUID instead of JSON (true only up to 1.x), and that
# "nothing is triggered there" (untrue — the central unit sends a waveform again
# when a device answers that it does not hold it). It is signed now.


# THE HEARTBEAT IS THE ONE THING UNDER central/ THAT IS SIGNED (2.1.0).
#
# It looks like a sign of life and is two things more:
#
#   * It is the ONLY clock the devices have. They own no RTC; they take the
#     time out of this message. Since 2.1.0 a device drops every command whose
#     age it cannot judge — which means whoever writes this message decides
#     what "fresh" means on every device in the installation.
#   * It resets the 120-second watchdog. That watchdog is what puts a device
#     into its safe state when the central unit falls silent. A forged
#     heartbeat keeps every device armed while the central unit is long dead.
#
# Both of those act, and both act on skin. The rest of central/ stays unsigned
# for the reason given above (finding Philine 2026-09-15).
SIGNED_CENTRAL = ('punisher/central/heartbeat',
                  'punisher/central/request',
                  'punisher/central/reload')

# WHY request AND reload ARE IN THERE (finding Philine 2026-09-15).
#
# `punisher/central/request` is the control path. What arrives there is handed
# to handle_requests() in punisher.py, and that calls logbook.punish() — a real
# punishment over the channel, on skin. It was accepted unsigned, and it was
# accepted BEFORE the signature check, so anyone with publish rights at the
# broker could trigger a punishment past the web login entirely. The `user`
# field comes out of the message as well, so the audit log would have carried
# a name of the sender's choosing.
#
# `reload` only makes the central unit re-read the database. Far less, but it
# is still an instruction from outside, and there is no reason for it to be
# the one command anybody may give.


# THE CONTROL PATH: what gives the central unit an INSTRUCTION (2.1.1).
#
# These two are the only topics on which something from outside tells the
# central unit to do something. They are a class of their own, and not because
# they are signed — everything in SIGNED_SUFFIXES is — but because of what a
# SECOND copy of the same message does.
#
# A `state` sent twice says the same thing twice: the device is still in that
# state. A `request` sent twice is a second punishment. The signature cannot
# tell the difference: it proves WHO wrote a message, never how often that
# message may be delivered.
#
# Philine demonstrated exactly that on 2026-09-15 — the same signed telegram
# published twice, two punishments over the channel, both in the audit log —
# and named what he wanted for it: id, boot_id/session_id, seq, ts_ms, ttl_ms,
# mandatory, and a central unit that refuses ids and sequences it has already
# seen. That is ReplayGuard below.
CONTROL_TOPICS = ('punisher/central/request',
                  'punisher/central/reload')

# Mandatory in every control telegram. A missing field is NOT permission — the
# same rule the firmware has followed since 2.1.0 for commands.
CONTROL_FIELDS = ('id', 'boot_id', 'seq', 'ts_ms', 'ttl_ms')

# The ceiling for the lifetime a sender may declare for itself. Without it,
# `ttl_ms: 86400000` would be a telegram usable for a day.
CONTROL_MAX_TTL_MS = 120000

# How far a clock may run ahead before the telegram counts as wrong rather than
# early. Central unit and web interface sit on the same machine; this is room
# for the millisecond, not for a badly set clock.
CONTROL_FUTURE_MS = 5000


def signed_topic(topic):
    """Does this topic belong in the signed envelope?"""
    t = str(topic)
    if t in SIGNED_CENTRAL:
        return True
    if not (t.startswith('punisher/devices/') or t.startswith('punisher/slaves/')):
        return False
    return t.rsplit('/', 1)[-1] in SIGNED_SUFFIXES


def unsigned_topic(topic):
    return not signed_topic(topic)


def control_topic(topic):
    """Does this topic carry an INSTRUCTION to the central unit?

    One rule, one place — as with signed_topic(). Whoever asks somewhere else
    whether a topic starts with `punisher/central/` has written a second rule
    beside the rule, and that one stops covering on the day a third control
    topic is added.
    """
    return str(topic) in CONTROL_TOPICS


def control_envelope(boot_id, seq, ts_ms=None, ttl_ms=None):
    """The mandatory fields of a control telegram, for the SENDING side.

    Lives here and not in the web interface so that both sides read the same
    list. Whoever adds a field to CONTROL_FIELDS sees at once what has to
    supply it.
    """
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    if ttl_ms is None:
        ttl_ms = 15000
    return {'id': f'{boot_id}-{int(seq)}', 'boot_id': str(boot_id),
            'seq': int(seq), 'ts_ms': int(ts_ms), 'ttl_ms': int(ttl_ms)}


class ReplayGuard:
    """Has this control telegram already been here? (2.1.1)

    Three checks, and each one catches something the others do not:

      ts_ms + ttl_ms   bound the WINDOW. Without them a recording from last
                       year would still be usable — including after a restart
                       of the central unit, which is the moment at which the
                       two memories below are empty.
      boot_id + seq    a sequence per sender that only ever climbs. This is the
                       one that catches the replay: a captured telegram carries
                       the boot_id and the seq it was written with, and that
                       number is spent.
      id               refused a second time as well. It catches nothing that
                       seq does not already catch, and it is in here all the
                       same: it is what stands in the log when a telegram is
                       refused, and a refusal one cannot attribute is half a
                       refusal.

    WHAT IT DOES NOT DO — and this belongs written down, not assumed:

    A new boot_id is accepted without question, because the web interface may
    be restarted and then legitimately begins at seq 1. Against a REPLAY that
    is no hole (the recording carries the old boot_id). Against someone who can
    SIGN it is one — they simply invent a boot_id. The same person could send
    one telegram with an enormous seq and thereby spend every number below it,
    until the web interface next restarts.

    Both need the project key, and whoever holds that key can write any
    telegram they like in any case. That is the shared-key question (finding
    Philine 2026-09-15, still open, see project document 03), and it is not
    solved here; nothing in this class pretends otherwise. What is solved here
    is the replay — and that one needed no key at all.

    A REJECTED telegram spends nothing: neither its seq nor its id is
    remembered. Otherwise a stream of rubbish from outside would eat the
    numbers of the real sender.
    """

    def __init__(self, keep=512, max_senders=32):
        self.keep = int(keep)
        self.max_senders = int(max_senders)
        self.seq_of = {}         # boot_id -> highest seq seen
        self.seen_at = {}        # boot_id -> time.time() of the last telegram
        self.ids = {}            # id -> monotonic sequence number of the entry
        self._n = 0

    def _remember(self, boot_id, seq, mid):
        self.seq_of[boot_id] = seq
        self.seen_at[boot_id] = time.time()
        self._n += 1
        self.ids[mid] = self._n
        # Bounded, both of them. An attacker who publishes as fast as they can
        # must not be able to eat the memory of the central unit.
        if len(self.ids) > self.keep:
            for k in sorted(self.ids, key=self.ids.get)[:len(self.ids) - self.keep]:
                self.ids.pop(k, None)
        if len(self.seen_at) > self.max_senders:
            oldest = min(self.seen_at, key=self.seen_at.get)
            self.seen_at.pop(oldest, None)
            self.seq_of.pop(oldest, None)

    def check(self, body, now_ms=None):
        """(True, None) when the telegram may act, otherwise (False, reason)."""
        if not isinstance(body, dict):
            return False, 'Steuertelegramm ist kein Objekt'
        missing = [f for f in CONTROL_FIELDS if f not in body]
        if missing:
            return False, 'Pflichtfeld fehlt: ' + ', '.join(missing)
        try:
            ts = int(body['ts_ms'])
            ttl = int(body['ttl_ms'])
            seq = int(body['seq'])
        except (TypeError, ValueError):
            return False, 'ts_ms, ttl_ms oder seq unlesbar'
        mid = body['id']
        boot = body['boot_id']
        if not isinstance(mid, str) or not mid:
            return False, 'id ist keine Zeichenkette'
        if not isinstance(boot, str) or not boot:
            return False, 'boot_id ist keine Zeichenkette'
        if seq < 0:
            return False, f'seq {seq} ist negativ'
        if ttl <= 0 or ttl > CONTROL_MAX_TTL_MS:
            return False, f'ttl_ms {ttl} ausserhalb 1..{CONTROL_MAX_TTL_MS}'
        now = int(time.time() * 1000) if now_ms is None else int(now_ms)
        age = now - ts
        if age > ttl:
            return False, f'abgelaufen ({age} ms alt, ttl {ttl} ms)'
        if age < -CONTROL_FUTURE_MS:
            return False, f'aus der Zukunft ({-age} ms)'
        last = self.seq_of.get(boot)
        if last is not None and seq <= last:
            return False, f'seq {seq} bereits verbraucht (zuletzt {last})'
        if mid in self.ids:
            return False, f'id {mid!r} bereits verwendet'
        self._remember(boot, seq, mid)
        return True, None


def _mac(key, data):
    if isinstance(key, str):
        key = key.encode('utf-8')
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def sign(key, topic, body_obj):
    """Build an envelope around body_obj. Returns the JSON string to be sent."""
    body = json.dumps(body_obj, separators=(',', ':'), ensure_ascii=True,
                      sort_keys=True)
    sig = _mac(key, (str(topic) + '\n' + body).encode('utf-8'))
    return json.dumps({'v': ENVELOPE_VERSION, 'sig': sig, 'body': body},
                      separators=(',', ':'), ensure_ascii=True)


def verify(key, topic, raw, max_age_ms=None, now_ms=None, require_ts=False):
    """Check the envelope and return the body.

    Returns (body_dict, None) on success, otherwise (None, reason). The reason
    is plain text and belongs in the log — a silent refusal is the worst thing
    in an installation that acts on skin: nobody goes looking for the error.

    require_ts (2.1.1): a body WITHOUT `ts_ms` is refused. Off by default, and
    that is not laziness — a device has no clock of its own before the first
    heartbeat of the central unit, and `hello`, `state` and `log` have
    therefore always gone through without a timestamp. Rather no statement
    about the time than a demonstrably false one.

    For a control telegram that reasoning does not hold: the web interface sits
    on the same machine as the central unit and always knows what time it is.
    There the missing field was a hole — the age check ran only when the field
    happened to be there, so a correctly signed request without `ts_ms` was as
    good as fresh for ever (finding Philine 2026-09-15).
    """
    try:
        outer = json.loads(raw)
    except (ValueError, TypeError):
        return None, 'kein JSON'
    if not isinstance(outer, dict):
        return None, 'Umschlag ist kein Objekt'
    if outer.get('v') != ENVELOPE_VERSION:
        return None, f"Umschlagversion {outer.get('v')!r} statt {ENVELOPE_VERSION}"
    body = outer.get('body')
    sig = outer.get('sig')
    if not isinstance(body, str) or not isinstance(sig, str):
        return None, 'sig oder body fehlt'
    want = _mac(key, (str(topic) + '\n' + body).encode('utf-8'))
    if not hmac.compare_digest(want, sig):
        return None, 'Signatur stimmt nicht'
    try:
        obj = json.loads(body)
    except ValueError:
        return None, 'Koerper ist kein JSON'
    if require_ts and not (isinstance(obj, dict) and 'ts_ms' in obj):
        return None, 'ts_ms fehlt'
    if max_age_ms is not None and isinstance(obj, dict) and 'ts_ms' in obj:
        now = int(time.time() * 1000) if now_ms is None else int(now_ms)
        try:
            age = now - int(obj['ts_ms'])
        except (TypeError, ValueError):
            return None, 'ts_ms unlesbar'
        # Both directions: too old is a replay, too far in the future is a
        # misset clock — both belong reported.
        if age > int(max_age_ms):
            return None, f'zu alt ({age} ms)'
        if age < -int(max_age_ms):
            return None, f'aus der Zukunft ({-age} ms)'
    return obj, None


# --------------------------------------------------------------------------- #
# Login: question and answer
# --------------------------------------------------------------------------- #

def new_nonce():
    """32 hex characters. Fresh for every login, never reused."""
    return secrets.token_hex(16)


def login_proof(key, nonce, mac, uuid):
    """What the device must answer to the question."""
    msg = f'{nonce}\n{mac_text(mac)}\n{uuid}'.encode('utf-8')
    return _mac(key, msg)


def check_login(key, nonce, mac, uuid, answer):
    """True when the answer of the device is right."""
    if not isinstance(answer, str):
        return False
    return hmac.compare_digest(login_proof(key, nonce, mac, uuid), answer)
