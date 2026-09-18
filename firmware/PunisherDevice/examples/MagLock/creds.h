// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
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

constexpr char MQTT_CLIENT[] PROGMEM = "magcuff";
constexpr char model_UUID[] PROGMEM = "1acf784c-4bfd-4a06-b4ff-ee578a37fac4";
constexpr char SERIALNUMBER[] PROGMEM = "CHANGEME-SERIAL";
constexpr char ntpServer[] PROGMEM = "pool.ntp.org";
const long  gmtOffset_sec PROGMEM       = 3600;
const int   daylightOffset_sec PROGMEM  = 3600;