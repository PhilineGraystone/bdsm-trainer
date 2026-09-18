// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#pragma once
// Version of this sketch.
//
// The NAME is only a name; comparing goes over the three numbers. The central
// unit keeps, per model, a minimum version for the sketch AND one for the
// framework (PunisherVersion.h) - both have to be met, or the device is
// refused rather than merely warned about.
//
// 2.0.0: derived device UUID, signed messages, structured versions. Not
//        compatible with 1.x, in either direction.
// 2.1.0: the will moved to `available` (it could not be signed on `state` and
//        was thrown away), the command checks fail closed instead of open, and
//        `response` is signed. The central unit requires 2.1.0 — a device below
//        it carries the open checks and is refused.
// 2.1.1: the build guard also refuses an EMPTY credential (a placeholder check
//        alone let `constexpr char PROJECT_KEY[] = "";` through), and OTA is
//        held to the same rule — empty now means OTA off. NOTHING ON THE AIR
//        CHANGED, so the floor stays at 2.1.0: a 2.1.0 device speaks the same
//        protocol and is not refused.
// 2.2.0: every hello carries `boot` — a random id for this life, the reset
//        reason, free heap, and what the previous life left in RTC memory
//        (uptime, last command, last error). The central unit keeps one row
//        per (device, boot id). A MINOR step because the hello grew; floor
//        stays 2.1.0 — a device without `boot` simply has no history.
// 2.2.1: `degraded` in the hello (components the device cannot use today),
//        the `config` command (settings from the central unit's schema into
//        NVS), and V-Cage proximity in the collar's state. All additive; floor
//        stays 2.1.0.
// 2.1.2: the receive buffer of the MQTT callback is the configured
//        mqttBufferSize, not a fixed 1 KB (a legal 50-point chunk fell through),
//        and a live reading without `valid`/`away` is read pessimistically.
//        Floor stays 2.1.0: the central unit now sends chunks that fit the old
//        limit, and it always sends both live fields.
// 2.3.0: TLS to the broker (project document 53). Off in this state —
//        `MQTT_TLS 1` in creds.h switches it on, and src/PunisherCa.h decides
//        whether the certificate is checked as well (empty = encrypt without
//        checking). Plus a rough clock from the build time, because a device
//        without a clock of its own could not check a certificate at all.
// 2.3.1: the TLS handshake is bounded to a third of the watchdog time. Until
//        2.3.0 it kept the default of WiFiClientSecure — 120 seconds — and a
//        broker that accepted the connection and then said nothing blocked
//        loop() until the watchdog rebooted the device. No change on the air;
//        floor stays 2.1.0.
// 2.3.2: a way out of the stored configuration. Everything the setup portal
//        saved beats creds.h, and until now nothing said so and nothing could
//        undo it at the device. Now: the start says which values come from the
//        NVS, `nvs clear` on the serial console wipes them after confirmation,
//        and PUNISHER_NVS_CLEAR in creds.h does the same at flash time. Plus
//        the connect failure names duration, target, port and the mbedTLS
//        reason instead of only `rc=-2`. Nothing on the air; floor stays 2.1.0.

#define SKETCH_NAME          "MagLock"
#define SKETCH_VERSION_MAJOR 2
#define SKETCH_VERSION_MINOR 3
#define SKETCH_VERSION_PATCH 2
