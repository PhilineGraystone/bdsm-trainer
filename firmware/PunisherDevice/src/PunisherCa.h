// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#pragma once
// The broker certificate this device is willing to accept — or nothing. (2.3)
//
// EMPTY IS THE NORMAL CASE, and it is not an oversight.
//
// With `MQTT_TLS 1` in creds.h the device talks TLS to the broker. What it
// does NOT do by default is check the certificate: the installation has no
// certificate authority, and it deliberately does not want one. A CA means a
// key to keep, a signing step, a rollover date and four more places where a
// mistake locks every device out — and above all it means that whoever
// rebuilds this installation has to understand all of it before anything
// works at all (decision Philine 2026-09-16, project document 53).
//
// WHAT THE EMPTY CASE BUYS, AND WHAT IT DOES NOT
//
// Encryption without a check protects against LISTENING IN. That is the case
// this is about: up to 2.2 the states, the names, the pulse levels and — on
// every connect — the password of the `punisher-device` account went over
// the WLAN in the clear, and anyone with a receiver read along.
//
// It does not protect against somebody who actively redirects inside the WLAN
// and pretends to be the broker. He becomes the endpoint himself and sees
// everything again. What he still cannot do is give an order: every command
// is signed with the project key, and that one he only gets by taking a
// device apart.
//
// IF YOU DO WANT THE CHECK
//
// Paste the broker's certificate below, exactly as `tools/mqtt_tls.sh` wrote
// it (the PEM block including both BEGIN/END lines). Then this is a PIN on
// that one certificate — no chain, no authority, no expiry handling beyond
// the certificate's own dates.
//
// Two things to know before you do:
//
//   1. A pinned device only ever accepts THIS certificate. Renew it on the
//      broker and every device is locked out until it is flashed again.
//   2. mbedTLS checks the validity dates against the device's clock, and the
//      device has none of its own — it learns the time from the central
//      unit's heartbeat, which arrives AFTER the connection. That is why
//      begin() sets the clock to the build time (PunisherDevice.cpp): a
//      clock that stands at 1970 makes every certificate "not yet valid" and
//      the handshake fails before the first heartbeat can ever arrive.
//
// Written as a raw string so the PEM keeps its line breaks and needs no
// escaping.

constexpr char PUNISHER_CA_CERT[] = R"PEM()PEM";

namespace punca {

// Is there a certificate here at all? Anything that does not begin with a PEM
// header is treated as absent — a stray blank line or a copied-in fingerprint
// must not end up as a "certificate" that mbedTLS then refuses to parse, with
// an error that names everything except the cause.
constexpr bool isRealCa(const char* s) {
  return s != nullptr &&
         s[0] == '-' && s[1] == '-' && s[2] == '-' && s[3] == '-' && s[4] == '-' &&
         s[5] == 'B' && s[6] == 'E' && s[7] == 'G' && s[8] == 'I' && s[9] == 'N';
}

}  // namespace punca
