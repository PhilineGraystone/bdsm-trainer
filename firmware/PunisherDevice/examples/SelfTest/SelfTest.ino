// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  SelfTest — the check run for firmware 2.0, on the chip itself.
//
//  WHAT THIS IS THERE FOR
//
//  Two questions that can only be answered on real hardware:
//
//    1. Does the 2.0 state compile at all? The sketch pulls in the whole
//       framework — PunisherDevice, PunisherCrypto, PunisherIdentity,
//       PunisherVersion. If it goes through the compiler, the base goes through.
//
//    2. Does the chip compute THE SAME as the central unit? SHA-256 and HMAC
//       are written ourselves; on the workstation they are checked against
//       FIPS 180-4 and RFC 4231, but the ESP32 is a different machine. The
//       sketch recomputes the same official test vectors here.
//
//  IT DOES NOTHING. No stimulator, no output, no relay, no motor.
//  safeState() is empty because there is nothing to switch off.
//
//  CONNECTION: USB only. Serial console at 115200.
//
//  TWO OPERATING MODES
//
//    WITH_NETWORK 0  (default)  only the self-test over the console. Runs on
//                               any ESP32 on the bench, without WLAN, without
//                               a broker, without the installation.
//    WITH_NETWORK 1             register in addition. Then the values in
//                               creds.h have to be right, PROJECT_KEY included
//                               — and in the device list of the central unit an
//                               unknown device turns up that waits to be
//                               assigned. That is exactly how it should be.
//
//  THE EFUSE LOCK IS OFF HERE, and it needs TWO switches so that it does not
//  fall by accident. It is irreversible.
// =====================================================================

#include "creds.h"
#include "version.h"

#include <PunisherDevice.h>
#include "PunisherCrypto.h"
#include "PunisherIdentity.h"
#include "PunisherVersion.h"

#define WITH_NETWORK 0

// A build with placeholder credentials must not happen (see PunisherCreds.h)
// — but only once this chip goes on the air. With WITH_NETWORK 0 it talks to
// nobody, and then a fresh chip may be checked without any secrets at all.
#include <PunisherCreds.h>
#if WITH_NETWORK
PUN_REQUIRE_REAL_CREDS();
PUN_REQUIRE_REAL_OTA();
#endif


// Both lines have to be 1 for the burn to happen. Irreversible, once per chip.
// Before and afterwards `espefuse.py summary` — and the first burn belongs on
// a sacrificial chip, not on an installation device.
#define BURN_MAC_FUSES         0
#define BURN_MAC_FUSES_CONFIRM 0

static int checks = 0;
static int fails  = 0;

static void ok(const char* what, bool good, const char* got = nullptr) {
  checks++;
  if (good) {
    Serial.printf("  OK   %s\n", what);
  } else {
    fails++;
    Serial.printf("  FEHL %s%s%s\n", what, got ? "  -> " : "", got ? got : "");
  }
}

static String sha(const String& in) {
  uint8_t h[32];
  pun::sha256((const uint8_t*) in.c_str(), in.length(), h);
  char hex[65];
  pun::toHex(h, 32, hex);
  return String(hex);
}

static String hmacHex(const String& key, const String& msg) {
  uint8_t h[32];
  pun::hmacSha256((const uint8_t*) key.c_str(), key.length(),
                  (const uint8_t*) msg.c_str(), msg.length(), h);
  char hex[65];
  pun::toHex(h, 32, hex);
  return String(hex);
}

static void expect(const char* what, const String& got, const char* want) {
  checks++;
  if (got == want) {
    Serial.printf("  OK   %s\n", what);
  } else {
    fails++;
    Serial.printf("  FEHL %s\n       erwartet %s\n       bekommen %s\n",
                  what, want, got.c_str());
  }
}

// ---------------------------------------------------------------------
void runSelfTest() {
  Serial.println();
  Serial.println("=====================================================");
  Serial.printf("  Punisher SelfTest — %s %d.%d.%d (lib %s)\n",
                SKETCH_NAME, SKETCH_VERSION_MAJOR, SKETCH_VERSION_MINOR,
                SKETCH_VERSION_PATCH, PUNISHERDEVICE_VERSION_STR);
  Serial.println("=====================================================");

  // --- 1. SHA-256 against FIPS 180-4 ---------------------------------
  Serial.println("\nSHA-256 (FIPS 180-4)");
  expect("leere Eingabe", sha(""),
         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  expect("\"abc\"", sha("abc"),
         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  expect("448 Bit", sha("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
         "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
  {
    // 55, 56 and 64 bytes: the three places where the padding is decided. If
    // an implementation is wrong anywhere, then here.
    String a, b, c;
    for (int i = 0; i < 55; i++) a += 'a';
    for (int i = 0; i < 56; i++) b += 'a';
    for (int i = 0; i < 64; i++) c += 'a';
    expect("55 x 'a'", sha(a),
           "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318");
    expect("56 x 'a'", sha(b),
           "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a");
    expect("64 x 'a'", sha(c),
           "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb");
  }

  // --- 2. HMAC-SHA256 against RFC 4231 -------------------------------
  Serial.println("\nHMAC-SHA256 (RFC 4231)");
  {
    String key;
    for (int i = 0; i < 20; i++) key += (char) 0x0b;
    expect("Fall 1", hmacHex(key, "Hi There"),
           "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
  }
  expect("Fall 2", hmacHex("Jefe", "what do ya want for nothing?"),
         "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
  {
    // key longer than one block -> has to be hashed
    String key;
    for (int i = 0; i < 131; i++) key += (char) 0xaa;
    expect("Fall 6 (langer Schluessel)",
           hmacHex(key, "Test Using Larger Than Block-Size Key - Hash Key First"),
           "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
  }

  // --- 3. Derivation against the central unit ------------------------
  //
  // Fixed input, fixed expected value. central/libs/punsign.py computes the
  // same number. If it matches here, chip and central unit compute the same —
  // and that independently of which chip it is.
  Serial.println("\nAbleitung (Gleichstand mit der Zentrale)");
  {
    const uint8_t probe[6] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};
    char u[37];
    pun::deriveUuid(probe, pun::CHIP_STR_ESP32, u);
    expect("Testvektor 02:00:00:00:00:01 / esp32", String(u),
           "c0291207-a276-5771-8f23-586b527a8d57");
    pun::deriveUuid(probe, pun::CHIP_STR_ESP32S3, u);
    expect("Testvektor 02:00:00:00:00:01 / esp32s3", String(u),
           "508e6d00-0b7e-5df8-8bba-c0eb9852170a");

    char mac[18];
    pun::formatMac(probe, mac);
    expect("MAC-Schreibweise", String(mac), "02:00:00:00:00:01");
  }
  {
    const String key   = "CHANGEME-PROJECT-KEY";
    const String topic = "punisher/devices/abc/cmd";
    const String body  = "{\"action\":\"punish\",\"id\":7,\"ts_ms\":1000,\"ttl_ms\":5000}";
    expect("Signatur ueber Topic und Koerper", hmacHex(key, topic + "\n" + body),
           "95d993a3ce28d8cd117695f907ca356a8cb1a348962cb9e713898fe63dd45788");
    ok("anderes Topic -> andere Signatur",
       hmacHex(key, topic + "\n" + body)
       != hmacHex(key, "punisher/devices/abd/cmd\n" + body));
  }

  // --- 4. This hardware ----------------------------------------------
  Serial.println("\nDieser Chip");
  {
    uint8_t mac[6];
    pun::readBaseMac(mac);
    char macTxt[18], uuid[37];
    pun::formatMac(mac, macTxt);
    pun::deriveUuid(mac, pun::chipType(), uuid);

    Serial.printf("  Chiptyp        %s\n", pun::chipType());
    Serial.printf("  efuse-MAC      %s\n", macTxt);
    Serial.printf("  device_UUID    %s\n", uuid);
    Serial.printf("  MAC gesperrt   %s\n", pun::macFusesLocked() ? "ja" : "nein");
    Serial.printf("  Framework      %s\n", PUNISHERDEVICE_VERSION_STR);
    Serial.printf("  Sketch         %s %d.%d.%d\n", SKETCH_NAME,
                  SKETCH_VERSION_MAJOR, SKETCH_VERSION_MINOR, SKETCH_VERSION_PATCH);

    ok("die MAC ist nicht null", mac[0] || mac[1] || mac[2] || mac[3] || mac[4] || mac[5]);
    ok("der Chiptyp ist bekannt", strcmp(pun::chipType(), pun::CHIP_STR_UNKNOWN) != 0,
       pun::chipType());
    ok("die UUID hat die richtige Form",
       strlen(uuid) == 36 && uuid[14] == '5'
       && (uuid[19] == '8' || uuid[19] == '9' || uuid[19] == 'a' || uuid[19] == 'b'),
       uuid);

    // Computing twice has to give the same twice. Sounds silly; but that is
    // exactly how an uninitialised buffer shows up.
    char again[37];
    pun::deriveUuid(mac, pun::chipType(), again);
    ok("zweimal gerechnet, zweimal dasselbe", strcmp(uuid, again) == 0);

    Serial.println();
    Serial.println("  Diese UUID traegt das Geraet in der Anlage. Notiere sie");
    Serial.println("  zusammen mit der MAC — die Zentrale zeigt beide an, wenn");
    Serial.println("  sich das Geraet meldet.");
  }

  Serial.println();
  Serial.printf("%d Pruefungen, %d Fehler — %s\n", checks, fails,
                fails == 0 ? "BESTANDEN" : "NICHT BESTANDEN");
  if (fails) {
    Serial.println();
    Serial.println("ACHTUNG: rechnet dieser Chip anders als die Zentrale, kann");
    Serial.println("sich kein Geraet dieser Bauart anmelden. Nicht ausliefern,");
    Serial.println("bevor das geklaert ist.");
  }
  Serial.println("=====================================================");
}

// ---------------------------------------------------------------------
#if WITH_NETWORK
class SelfTestHandler : public PunisherHandler {
 public:
  // There is nothing to switch off. That is not negligence but the purpose:
  // this device can do nothing to anybody.
  void safeState() override {}

  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    (void) args;
    if (!strcmp(action, "identify")) {          // from the base, here only output
      Serial.println("SelfTest: identify");
      return true;
    }
    snprintf(err, errLen, "SelfTest fuehrt nichts aus");
    return false;
  }

  void reportState(JSONVar& out) override {
    out["selftest"] = true;
    out["checks"]   = checks;
    out["fails"]    = fails;
  }
};

static SelfTestHandler handler;
static PunisherDevice dev;
#endif

void setup() {
  Serial.begin(115200);
  delay(1500);                     // time to open the console

  runSelfTest();

#if BURN_MAC_FUSES && BURN_MAC_FUSES_CONFIRM
  Serial.println();
  Serial.println("efuse: Schreibsperre der MAC wird gebrannt — UNUMKEHRBAR");
  Serial.printf("efuse: vorher gesperrt: %s\n", pun::macFusesLocked() ? "ja" : "nein");
  bool burned = pun::lockMacFuses();
  Serial.printf("efuse: nachher gesperrt: %s (Rueckgabe %s)\n",
                pun::macFusesLocked() ? "ja" : "nein", burned ? "ok" : "FEHLER");
  Serial.println("efuse: jetzt `espefuse.py summary` und mit dem Stand davor vergleichen.");
#endif

#if WITH_NETWORK
  PunisherConfig cfg;
  cfg.ssid        = SSID;
  cfg.password    = PASSWORD;
  cfg.broker      = MQTT_BROKER;
  cfg.tls         = MQTT_TLS;            // TLS (2.3, Doc 53)
  cfg.port        = MQTT_PORT;
  cfg.clearNvs    = PUNISHER_NVS_CLEAR;  // wipe stored config once (2.3.2)
  cfg.mqttUser    = MQTT_USER;
  cfg.mqttPass    = MQTT_PASS;
  cfg.clientId    = MQTT_CLIENT;
  cfg.modelUuid   = model_UUID;          // deviceUuid is derived
  cfg.sketchName  = SKETCH_NAME;
  cfg.sketchMajor = SKETCH_VERSION_MAJOR;
  cfg.sketchMinor = SKETCH_VERSION_MINOR;
  cfg.sketchPatch = SKETCH_VERSION_PATCH;
  cfg.projectKey  = PROJECT_KEY;
  cfg.otaPassword = OTA_PASSWORD;
  // No capabilities: this device can do nothing, and that is the honest
  // report. The central unit then offers no action for it either.
  cfg.capabilities    = nullptr;
  cfg.capabilityCount = 0;
  dev.begin(cfg, handler);
  Serial.println("SelfTest: angemeldet — die Zentrale sollte ein unbekanntes");
  Serial.println("Geraet anzeigen, das auf Zuordnung wartet.");
#else
  Serial.println();
  Serial.println("WITH_NETWORK ist 0 — es wird nichts gesendet. Fuer den Test");
  Serial.println("in der Anlage auf 1 setzen und creds.h ausfuellen.");
#endif
}

void loop() {
#if WITH_NETWORK
  dev.loop();
#else
  delay(1000);
#endif
}
