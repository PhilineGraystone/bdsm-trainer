# coding=utf-8
# SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
"""TLS for the broker connection — one place, three processes (doc 53).

WHAT THIS IS FOR

Central unit, web interface and display talk to the broker over localhost;
the DEVICES come over the WLAN. Up to 2.2 everything on that path is in the
clear — states, names, pulse levels, and on connect the password of the
`punisher-device` account. Whoever listens in the WLAN reads it.

THREE STATES, AND EACH ONE SAYS SO

    off          port 1883, clear text. The state of the repository, and the
                 one a third party gets without doing anything.
    encrypted    port 8883, the certificate is NOT checked. Protects against
                 LISTENING IN — the case this is about.
    checked      port 8883, and the certificate has to be the one named in
                 `tls_ca`. That is a pin on exactly this certificate, not a
                 chain: the installation has no certificate authority and
                 deliberately does not want one (decision Philine 2026-09-16 —
                 whoever rebuilds this should get it running without first
                 understanding a CA).

WHAT `encrypted` DOES NOT DO, said plainly because the difference matters:
it protects against somebody who listens, not against somebody who actively
redirects in the WLAN and pretends to be the broker. That one becomes the
endpoint himself and sees everything again. What he still cannot do is give
an order: every command is signed and he does not have the project key.

The state is logged at every start. Not as a warning — clear text is a
documented, legitimate setting for a bench — but it is said, because the
difference between "encrypted" and "checked" is invisible from the outside
and nobody should have to guess which of the three is running.
"""

import logging
import os
import ssl

logger = logging.getLogger(__name__)

OFF, ENCRYPTED, CHECKED = 'off', 'encrypted', 'checked'

# What the three states are called in the log. German, like every other line
# the supervisor reads there.
TEXT = {OFF: 'ohne TLS (Klartext)',
        ENCRYPTED: 'TLS, Zertifikat NICHT geprueft',
        CHECKED: 'TLS, Zertifikat geprueft gegen {ca}'}


def wanted(config):
    """Which of the three states does the configuration ask for?

    `tls` switches it on; `tls_ca` additionally switches the check on. A
    `tls_ca` without `tls` is a typo with consequences — it would silently be
    clear text — so it counts as switched on.
    """
    m = config['mqtt'] if config is not None and 'mqtt' in config else {}
    ca = (m.get('tls_ca') or '').strip()
    on = str(m.get('tls', '0')).strip().lower() in ('1', 'yes', 'true', 'on')
    if ca:
        return CHECKED
    return ENCRYPTED if on else OFF


def port(config, default=1883):
    """The port to use. Explicit beats implicit; without an entry TLS means 8883.

    Without this rule an installation that switches on `tls` and forgets the
    port would talk TLS to the clear-text listener and get a handshake error
    that names everything except the cause.
    """
    m = config['mqtt'] if config is not None and 'mqtt' in config else {}
    if m.get('port'):
        return int(m['port'])
    return 8883 if wanted(config) != OFF else default


def configure(client, config, log=None):
    """Apply TLS to a paho client. Returns the state, or raises.

    Raising is deliberate: a configuration that asks for TLS and cannot get it
    must not quietly fall back to clear text. That is the one failure mode
    this module exists to prevent.
    """
    log = log or logger
    state = wanted(config)
    if state == OFF:
        log.info('MQTT: %s', TEXT[OFF])
        return OFF
    m = config['mqtt']
    ca = (m.get('tls_ca') or '').strip()
    if state == CHECKED:
        if not os.path.exists(ca):
            raise FileNotFoundError(f'tls_ca: {ca} gibt es nicht')
        client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED,
                       tls_version=ssl.PROTOCOL_TLS_CLIENT)
        log.info('MQTT: %s', TEXT[CHECKED].format(ca=ca))
        return CHECKED
    # encrypted, not checked. Both switches are needed: cert_reqs=CERT_NONE
    # alone still leaves the hostname check on, and that fails on a
    # self-signed certificate whose name does not match the address used.
    client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(True)
    log.info('MQTT: %s', TEXT[ENCRYPTED])
    return ENCRYPTED
