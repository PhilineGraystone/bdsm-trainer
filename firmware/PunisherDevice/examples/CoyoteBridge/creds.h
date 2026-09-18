// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// Defaults for the config portal (taken into NVS on the first start).
//
// PLACEHOLDERS - replace with the installation's values before flashing, or
// leave empty and enter everything in the setup portal (access point
// "<client_id>-setup", password "punisher-setup").
constexpr char SSID[] PROGMEM = "CHANGEME-SSID";
constexpr char PASSWORD[] PROGMEM = "CHANGEME-WLAN";
constexpr char MQTT_BROKER[] PROGMEM = "CHANGEME-BROKER";
// MQTT_USER is the DEVICE account (2.1.1): `punisher-device`, the same on every
// device of the installation. It is a separate account from the central unit's
// and the web interface's so that the broker's access list can tell them
// apart — a device may report about itself and listen, and it may NOT publish
// on punisher/central/# or punisher/slaves/#. That is what closes the path on
// which a device with exchanged firmware could have triggered a punishment
// (finding Philine 2026-09-15, project document 40).
constexpr char MQTT_USER[] PROGMEM = "CHANGEME-USER";
constexpr char MQTT_PASS[] PROGMEM = "CHANGEME-PASS";
// Project key for the signature. THE SAME ON THE CENTRAL UNIT AND ON EVERY
// DEVICE. Without it, no device gets into this installation.
constexpr char PROJECT_KEY[] PROGMEM = "CHANGEME-PROJECT-KEY";

// TLS to the broker (2.3, project document 53). DEFAULT: off — clear text on
// 1883, so that this state runs without a single step being taken and nobody
// has to produce a certificate first. To switch it on: both lines to 1 and
// 8883, create the certificate on the broker (tools/mqtt_tls.sh) and enable
// the listener there.
//
// The certificate is CHECKED only if src/PunisherCa.h carries one. Without
// that, TLS means: encrypted, but the other end is not established — it helps
// against listening in, not against active redirection inside the WLAN. Even
// there nobody can give an order; that needs the project key.
#define MQTT_TLS  0
#define MQTT_PORT 1883

// Set to 1 to wipe the STORED configuration of this device at the next start
// — everything the setup portal or a `config` command ever saved (broker,
// account, port, settings). The values compiled in from this file apply again.
// The device says so on the serial console and keeps running; set it back to
// 0 and flash once more, or it wipes on every start. Needed when a stored
// value outlives the one written here: a collar provisioned before TLS kept
// port 1883 in its NVS and talked TLS to it (finding Philine 2026-09-16).
#define PUNISHER_NVS_CLEAR 0

constexpr char MQTT_CLIENT[] PROGMEM = "coyote01";

// Model "E-Stim-Bridge (DG-LAB Coyote V2/V3)" from libs/devicemodels.py - do NOT change.
constexpr char model_UUID[] PROGMEM = "7a3d9e54-1c8b-4f26-b0d3-5e9c71a4f882";

// OTA: an EMPTY value switches it off (not nullptr — these are arrays and an
// array is never a null pointer; 2.1.1). Otherwise at least 8 characters.
// Set the password before the exhibition
// (project doc 08).
constexpr char OTA_PASSWORD[] PROGMEM = "CHANGEME-OTA";

// Device-specific values come from NVS and can be set in the portal as one
// "key=value" per line:
//
//   coyote_mac      MAC of this bridge's own Coyote, e.g. "aa:bb:cc:dd:ee:ff".
//                   EMPTY = the first Coyote found. In the museum, where
//                   several of them are within radio range, it belongs set.
//   estim_max_pct   own ceiling for the intensity in percent (default 100).
//                   It only lowers; the compiled-in limit cannot be raised.
//   estim_day_max   seconds of output per slave and day (default 3600).
//   estim_lvl1/2/3  intensity of channel steps 1..3 (default 25/45/70).
//   estim_event_ms  length of one channel event in ms (default 1200).
