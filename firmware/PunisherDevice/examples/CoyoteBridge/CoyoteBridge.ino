// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  CoyoteBridge - the installation's e-stim bridge (project doc 19)
//
//  An ESP32-S3 as a BLE central in front of ONE DG-LAB Coyote (V2 or V3)
//  and as an ordinary device of the installation: own UUID, own hello, own
//  envelope, own trail in the audit log. One bridge per Coyote.
//
//  WHAT THE BRIDGE DOES
//    * Receive waveforms (routine_begin/track/chunk/commit), reassemble
//      every track ITSELF and hash it ITSELF - the central unit is checked,
//      not believed (doc 17 §7).
//    * Write a frame to the Coyote every 100 ms: the profile makes the
//      rhythm, the curve the height (= the strength; the width is fixed).
//    * Listen to the slave's reading and align coupled tracks to it
//      (doc 19 §2.4, §5.2).
//    * React to punishment and reward in the slave's channel (doc 14 3a) -
//      like the collar, reward included.
//
//  THE STRENGTH - UNTIL 2026-09-11 THE OPPOSITE STOOD HERE
//    * The bridge WRITES the strength, and on every frame. It is the pulse
//      height, and in this operating mode it cannot be set at the device at
//      all any more (finding Philine 2026-09-11). Before, this said "we never
//      write it" - that was the reason both channels were deaf: a height of
//      zero stays zero, however wide the pulse.
//    * THE CEILING comes from the slave's calibration and travels with
//      every command (str_a/str_b, percent per channel). There is NO
//      default: without a ceiling no run and no raw output starts. It is
//      the only upper limit on the height (decision Philine 2026-09-11) -
//      which is why it is not half written down somewhere else as well.
//    * The V3's soft limit (BF) the bridge still does not write (decision
//      Philine 2026-09-11): both generations are treated alike, the capping
//      happens in the firmware.
//    * The strength STAYS in the device until someone changes it. That is
//      why it is written to 0 explicitly on connect, stop, emergency stop
//      and connection loss - not merely the waveform switched off.
//    * It does not hold a waveform across a restart (decision Philine
//      2026-09-11): after a reset the output is off anyway, and the central
//      unit sends the waveform again at registration.
//
//  DEAD-MAN SWITCH FOR FREE (doc 19 §4.4)
//    Both generations only put out as long as a frame arrives every 100 ms.
//    Broker gone, WLAN gone, firmware crashed, ESP in reset -> the output
//    stops by itself after 0.1 s. safeState() therefore simply means: no
//    more frames (plus one last frame at intensity 0, so that the 100 ms
//    window already begun falls silent too).
//
//  HARDWARE
//    ESP32-S3 (BLE + WLAN), one status LED (WS2812 on LED_PIN). No display
//    (decision Philine 2026-09-11) - the state goes over MQTT to the central
//    unit and to the display.
//    LED: the COLOUR says what is going on, readable from two metres away
//    without having to count blink patterns (decision Philine 2026-09-11):
//        red slow      no connection to the central unit
//        blue slow     central unit there, but no Coyote - searching
//        green slow    Coyote connected, nothing running
//        green fast    output running
//        white         identify ("blink" from the web interface)
//        red fast      daily budget spent, nothing goes out any more
//
//  LIBRARIES
//    PunisherDevice >= 3.2.0 (reading channel), NimBLE-Arduino 2.x.
//    For NimBLE-Arduino 1.4.x: set COYOTE_NIMBLE_V2 to 0 (see below).
//
//  STATUS: the arithmetic (profiles, frequency conversion, byte packing,
//    CRC, coupling) has been recomputed on the PC against the central unit
//    and against DG-LAB's example data (test/test_coyotewave.cpp). The BLE
//    part has not run on any hardware yet - first build and bench at Philine's.
// =====================================================================

// NimBLE-Arduino 2.x = 1. Set to 0 when 1.4.x is installed; only the scan
// callbacks are affected, everything else is the same in both versions.
#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

#include "PunisherDevice.h"
#include "CoyoteWave.h"
#include "creds.h"

// A build with placeholder credentials must not happen (see PunisherCreds.h).
// If this line fails to compile, `creds.h` still holds the CHANGEME values
// from the repository — fill them in, then build again.
#include <PunisherCreds.h>
PUN_REQUIRE_REAL_CREDS();
PUN_REQUIRE_REAL_OTA();

#include "version.h"

// Does the arithmetic actually arrive? `#include "CoyoteWave.h"` finds the
// file NEXT TO this .ino - if it is not there, the compiler breaks off with
// an avalanche that starts at `'coyote' is not a namespace-name` and in
// which the cause appears nowhere (finding Philine 2026-09-11). These three
// lines turn that into a sentence.
//
// Into the sketch folder, all on the same level as this file:
//     CoyoteBridge.ino   CoyoteWave.h   creds.h   partitions.csv
// PunisherDevice, by contrast, is a LIBRARY and belongs in
// Documents/Arduino/libraries/PunisherDevice/.
#if !defined(COYOTE_WAVE_H)
#error "CoyoteWave.h is missing from the sketch folder (or is an old version). The file has to sit NEXT TO CoyoteBridge.ino - see the comment right above this line."
#elif COYOTE_WAVE_H < 2
#error "CoyoteWave.h is older than this sketch. Take both from the same package."
#endif

using namespace coyote;

// The loopTask gets 8 kB of stack by Arduino default. On this bridge the
// MQTT callback, the JSON parsing of a waveform and the 100 ms player run
// inside it on top of each other; NimBLE sits alongside with buffers of its
// own. 8 kB are tight for that, and a stack overflow looks exactly like a
// crash without a message on the S3 - the panic goes to UART0, not to the
// USB-CDC one is watching through.
//
// 16 kB cost RAM that this board (8 MB PSRAM, 512 kB SRAM) has. They are no
// substitute for frugal functions, but the safety margin around them.
#if defined(SET_LOOP_TASK_STACK_SIZE) || defined(ARDUINO_ARCH_ESP32)
SET_LOOP_TASK_STACK_SIZE(16 * 1024);
#endif

// --------------------------------------------------------------------- //
//  Envelope. Compiled in, so that no command and no portal can raise it -
//  only lower it. This is the bridge's OWN hard limit, on top of the
//  ceiling at the wearer's device and the central unit's daily budget.
// --------------------------------------------------------------------- //
#define ENV_ESTIM_MAX_PCT     100   // upper limit of every intensity, in % of the ceiling
#define ENV_ESTIM_RUN_MAX_S  1800   // longest run in one go (30 min)
#define ENV_ESTIM_DAY_MAX_S  3600   // output seconds per day, fallback when none given
#define ENV_EVENT_MAX_S        20   // longest channel event
#define ENV_FRAME_MS          100   // beat to the Coyote; below that the protocol fails

// Status LED: one WS2812 (addressable), driven with neopixelWrite(). That
// is the difference it first failed on: a WS2812 does NOT light up on a
// digitalWrite - it wants a data telegram, not a level (finding Philine
// 2026-09-11).
//
// Which pin: GPIO48 on the DevKitC-1 v1.0, GPIO47 or GPIO38 on later
// versions and some clones. Which one it is on this board is settled by
// diagnose/03_LedFinder. Without the right pin only the indicator is
// missing - the bridge carries on working in full.
#ifndef LED_PIN
#define LED_PIN               48
#endif
// A WS2812 at full level dazzles and draws current for nothing. 48 out of
// 255 is enough in a lit room and is not unpleasant in the dark.
#ifndef LED_LEVEL
#define LED_LEVEL             48
#endif
// neopixelWrite() comes from the ESP32 Arduino core (2.0.6 and up). An
// older core otherwise reports an error in the middle of the LED function,
// and one goes looking for it there instead of in the board settings.
#if !defined(ESP_ARDUINO_VERSION) || ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(2, 0, 6)
#error "This sketch needs the ESP32 Arduino core 2.0.6 or newer (neopixelWrite)."
#endif
#define MAX_TRACKS             8    // doc 19 §2.3
#define MAX_POINTS           600    // per slot (time axis / depth axis)
#define BLE_RESCAN_MS      10000
// Longest gap between two state messages, AS LONG AS something is running.
// 500 ms are fluid enough for the eye and nothing for MQTT.
#define STATE_RUN_MS         500

// Storage slots: the AXIS decides where a waveform belongs. Time axis =
// something that runs off (ESTIM_ROUTINE). Depth axis = a coupling that
// follows what is measured. Holding both at once is necessary because the
// central unit transfers the coupling before the task.
#define SLOT_TIME   0
#define SLOT_DEPTH  1
#define SLOT_COUNT  2

// --------------------------------------------------------------------- //
struct TrackDef {
  uint8_t        no       = 0;
  Role           role     = ROLE_UNKNOWN;
  Channel        channel  = CH_NONE;
  Mode           mode     = MODE_ABSOLUTE;
  Couple         couple   = COUPLE_POSITION;
  const Profile* profile  = nullptr;
  uint16_t       first    = 0;      // index into the slot's point storage
  uint16_t       n        = 0;
  uint32_t       crc      = 0;
};

struct Slot {
  bool     valid      = false;
  bool     building   = false;
  uint32_t id         = 0;
  uint32_t crc        = 0;
  Axis     axis       = AXIS_TIME;
  uint8_t  nTracks    = 0;
  uint32_t durationMs = 0;
  TrackDef tracks[MAX_TRACKS];
  Point    pts[MAX_POINTS];
  uint16_t used       = 0;
  // Structure
  int8_t   curTrack   = -1;         // index into tracks[] for incoming blocks
  uint16_t nextSeq    = 0;
  bool     broken     = false;      // gap/overflow: reject at commit
  const char* brokenWhy = "";

  // Clear the slot WITHOUT building a Slot temporary.
  //
  // This read `sl = Slot();`. That looks harmless and is harmless on a PC -
  // on the ESP32 it puts a temporary of a good 5 kB on the loopTask's stack,
  // which has 8 kB by Arduino default. Together with what the MQTT callback
  // and the JSON parsing already occupy, that is enough for a stack overflow
  // - and it happens exactly when a waveform arrives, that is, at the first
  // start of a task (finding 2026-09-11).
  //
  // The two large arrays are NOT zeroed: `used`/`n` say how far they are
  // valid, and nobody reads beyond that anyway. That saves zeroing 5 kB on
  // every transfer as well.
  void reset() {
    valid = false; building = false;
    id = 0; crc = 0;
    axis = AXIS_TIME;
    nTracks = 0; durationMs = 0; used = 0;
    curTrack = -1; nextSeq = 0;
    broken = false; brokenWhy = "";
    for (uint8_t i = 0; i < MAX_TRACKS; i++) tracks[i] = TrackDef();
  }
};

// --------------------------------------------------------------------- //
PunisherDevice dev;
static const char* CAPS[]        = {"estim_a", "estim_b", "estim_routine"};
static const char* PUNISH_KINDS[] = {"estim"};
static const char* REWARD_KINDS[] = {"estim"};

// --------------------------------------------------------------------- //
//  The link to the Coyote. Everything version-dependent sits here.
// --------------------------------------------------------------------- //
class CoyoteLink {
 public:
  enum Gen : uint8_t { GEN_NONE = 0, GEN_V2, GEN_V3 };

  // V3: Standard-Basis-UUID. V2: eigene Basis 955Axxxx-0FE2-F5AA-A094-84B8D4F3E8AD.
  static NimBLEUUID svcV3()   { return NimBLEUUID((uint16_t) 0x180C); }
  static NimBLEUUID wrV3()    { return NimBLEUUID((uint16_t) 0x150A); }
  static NimBLEUUID ntfV3()   { return NimBLEUUID((uint16_t) 0x150B); }
  static NimBLEUUID svcV2()   { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
  static NimBLEUUID ab2V2()   { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
  static NimBLEUUID a34V2()   { return NimBLEUUID("955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"); }
  static NimBLEUUID b34V2()   { return NimBLEUUID("955a1506-0fe2-f5aa-a094-84b8d4f3e8ad"); }

  void begin(const String& wantMac) {
    // NimBLE's notify callbacks are plain function pointers and cannot carry
    // anything along; hence this one static pointer. There is exactly one
    // bridge per ESP, so exactly one instance.
    _self = this;
    _wantMac = wantMac;
    _wantMac.toLowerCase();
    NimBLEDevice::init("");
    NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  }

  bool connected() const { return _client && _client->isConnected(); }
  Gen  generation() const { return _gen; }
  const String& boundMac() const { return _wantMac; }

  // Set or release the binding during operation. Empty = the first one found
  // again. Takes effect IMMEDIATELY: an existing connection to another device
  // is dropped, so that one sees from the result whether the binding takes
  // hold, instead of finding out at the next restart.
  void bind(const String& mac) {
    _wantMac = mac;
    _wantMac.toLowerCase();
    if (_wantMac.length() && connected()) {
      String cur = _mac;
      cur.toLowerCase();
      if (cur != _wantMac) {
        dev.logf("info", "coyote binding changed - dropping %s", _mac.c_str());
        // SILENCE IT FIRST, THEN DISCONNECT. The waveform does expire by itself
        // after 0.1 s, but the STRENGTH stays standing in the device. Cutting the
        // connection without clearing it leaves it behind there - and we have seen
        // on the bench that a write without a response is lost on disconnect
        // (level 5: at the next start 700 was still in the device). Zeroing on
        // connect catches it, but skipping this would mean relying on that.
        silenceAll();
        _client->disconnect();
      }
    }
    _lastTry = 0;             // search again at once
  }
  const char* genName() const { return _gen == GEN_V3 ? "v3" : (_gen == GEN_V2 ? "v2" : "none"); }
  const String& mac() const { return _mac; }
  uint16_t drops() const { return _drops; }
  uint16_t strengthA() const { return _strA; }
  uint16_t strengthB() const { return _strB; }
  uint8_t battery() const { return _batt; }

  // Non-blocking: scans, connects, keeps the connection.
  void loop(unsigned long now) {
    if (connected()) return;
    if (_gen != GEN_NONE) {            // the connection was there and is gone
      _gen = GEN_NONE; _mac = ""; _wr = nullptr; _waveA = nullptr; _waveB = nullptr;
      _ab2 = nullptr;
      // What we last wrote applies to THIS connection only. 0xFFFF means
      // "nothing written" and forces the next write - otherwise the bridge holds
      // a strength for set that is not in the freshly connected device at all.
      _wroteA = _wroteB = 0xFFFF;
      _drops++;
      // How often the Coyote has lost the connection SINCE THE BRIDGE HAS BEEN
      // RUNNING. That is the difference by which one recognises who restarts: if
      // the counter climbs, it was the Coyote. If it starts at 0 again, it was
      // the bridge (question Philine 2026-09-11: "the Coyote restarts").
      dev.logf("warn", "coyote disconnected (drop %u)", (unsigned) _drops);
      dev.publishEvent("coyote_lost", "fault");
      dev.publishState();
    }
    if (now - _lastTry < BLE_RESCAN_MS) return;
    _lastTry = now;
    scanOnce();
  }

  // X/Y/Z unchanged to ONE channel. For fault-finding only: nothing is
  // converted here, nothing capped except by our own envelope, and the other
  // channel stays silent. On the V3 there is no X/Y/Z - there an intensity is
  // made out of Z and the period is computed back out of X/Y, so that the
  // same button does something on both generations.
  // --- HOW we write, not only WHAT --------------------------------------- //
  //
  // THE FAULT THAT KEPT EVERYTHING SILENT (finding Philine 2026-09-11: "the
  // Coyote only flips, there is no output - the LED on the device shows
  // nothing either").
  //
  // Every write here stood at `writeValue(..., false)`, that is, "write
  // command" - writing WITHOUT a response. That is fire-and-forget: the ESP32
  // reports success as soon as the packet is out, whether anyone accepts it
  // or not. A GATT server that does NOT offer the "write without response"
  // property discards such packets silently.
  //
  // And the Coyote does not offer it: the official tables list every write
  // point as 写 (write request), nowhere 写无响应. So all that time we were
  // posting into a letterbox that was none - the bridge saw nothing but
  // successful writes, the device got nothing, and that is why its own
  // display stayed dark as well.
  //
  // That also explains why the correction from doc 28 (really write the
  // strength) changed nothing: the new writes were of the same kind as the
  // old ones.
  //
  // From now on the CHARACTERISTIC decides, not our assumption: if it offers
  // "without response", we take that (faster, and the 100 ms beat likes it);
  // otherwise we write WITH a response. And on connect it is logged what the
  // device actually offers - so that this question never has to be guessed
  // again.
  // What does this characteristic really offer? Exactly this line was
  // missing: we assumed "without response" would work, and nobody ever
  // looked. It costs one log line per connection and answers the question the
  // installation was silent on for a day.
  void reportProps(const char* name, NimBLERemoteCharacteristic* c) {
    if (!c) { dev.logf("warn", "coyote characteristic %s MISSING", name); return; }
    dev.logf("info", "coyote characteristic %s: read=%d write=%d write_nr=%d notify=%d indicate=%d",
             name, (int) c->canRead(), (int) c->canWrite(), (int) c->canWriteNoResponse(),
             (int) c->canNotify(), (int) c->canIndicate());
  }

  static bool wr(NimBLERemoteCharacteristic* c, const uint8_t* d, size_t n) {
    if (!c) return false;
    return c->writeValue(d, n, !c->canWriteNoResponse());
  }

  bool writeRaw(uint8_t ch, uint8_t x, uint16_t y, uint8_t z, uint8_t strPct) {
    if (!connected()) return false;
    if (_gen == GEN_V2) {
      // Height first, then width. Without strength every X/Y/Z is silent.
      writeStrengthV2(ch ? 0 : strPct, ch ? strPct : 0);
      uint8_t buf[3];
      v2Bytes(v2Pack(x, y, z), buf);
      NimBLERemoteCharacteristic* c = ch ? _waveB : _waveA;
      NimBLERemoteCharacteristic* o = ch ? _waveA : _waveB;
      uint8_t zero[3];
      v2Bytes(v2Pack(1, 9, 0), zero);
      if (o) wr(o, zero, 3);
      return wr(c, buf, 3);
    }
    if (_gen == GEN_V3) {
      uint8_t inten = (uint8_t) min(100, (int) z * 5);      // Z 20 -> 100 %
      uint16_t per = (uint16_t) max(10, min(1000, (int) x + (int) y));
      uint8_t f[20];
      v3BuildFrame(f, v3FreqValue(per), ch ? 0 : inten,
                      v3FreqValue(per), ch ? inten : 0,
                      ch ? 0 : v3Strength(strPct), ch ? v3Strength(strPct) : 0);
      return wr(_wr, f, sizeof(f));
    }
    return false;
  }

  // One frame to both channels. outA/outB are the FINISHED output share in
  // percent (curve x profile shape x the slave's ceiling) - the bridge adds
  // nothing to it here, it only converts into device units.
  //
  // Since 2026-09-11 this share drives the STRENGTH, that is, the pulse
  // height. The width is fixed at the working value (V2 Z=20 = 100 µs, V3
  // waveform strength 100). Before it was the other way round, and the usable
  // range lay almost entirely below the threshold of perception (doc 28 §3).
  // Zero stays zero in both: strength 0 AND width 0.
  bool writeFrame(uint16_t perA, uint8_t outA, uint16_t perB, uint8_t outB) {
    if (!connected()) return false;
    if (outA > 100) outA = 100;
    if (outB > 100) outB = 100;
    if (_gen == GEN_V3) {
      uint8_t f[20];
      v3BuildFrame(f, v3FreqValue(perA), outA ? 100 : 0,
                      v3FreqValue(perB), outB ? 100 : 0,
                      v3Strength(outA), v3Strength(outB));
      return wr(_wr, f, sizeof(f));
    }
    if (_gen == GEN_V2) {
      writeStrengthV2(outA, outB);
      uint8_t x; uint16_t y; uint8_t buf[3];
      v2XY(perA, x, y);
      v2Bytes(v2Pack(x, y, outA ? V2_Z_WORK : 0), buf);
      bool ok = wr(_waveA, buf, 3);
      v2XY(perB, x, y);
      v2Bytes(v2Pack(x, y, outB ? V2_Z_WORK : 0), buf);
      ok = wr(_waveB, buf, 3) && ok;
      return ok;
    }
    return false;
  }

  // The V2's strength lives in a characteristic of its own and STAYS STANDING
  // until someone changes it ("通道强度会立刻改变并且一直保持"). That is why it is
  // written along on every frame, and why it MUST be set to 0 explicitly on
  // stop, emergency stop and connection loss - otherwise it is still there at
  // the next connect.
  //
  // On the V3 the strength belongs in the B0 frame and is written there; this
  // function is a no-op.
  bool writeStrengthV2(uint8_t pctA, uint8_t pctB, bool force = false) {
    if (_gen != GEN_V2 || !_ab2) return false;
    // ONLY ON CHANGE. Since the writes run WITH a response (see wr()), every
    // one of them costs a round trip over the radio link. The strength STAYS in
    // the device - so it does not have to be repeated at all, unlike the
    // waveform, which expires after 0.1 s and is therefore heard anew on every
    // beat. Without that distinction there would be three round trips per
    // 100 ms on the V2, and with a sluggish connection interval that is not enough.
    // `force` for every path that SWITCHES OFF. On the way up one may rely on a
    // remembered value, on the way to silence one may not: if the memory were
    // ever wrong, a strength nobody wanted any more would stay standing.
    // Downwards, therefore, it is always really written.
    uint16_t a = v2Strength(pctA), b = v2Strength(pctB);
    if (!force && a == _wroteA && b == _wroteB) return true;
    uint8_t buf[3];
    v2Bytes(v2PackStrength(a, b), buf);
    bool ok = wr(_ab2, buf, 3);
    if (ok) { _wroteA = a; _wroteB = b; }
    return ok;
  }

  // Everything to zero, both generations. A call that assumes nothing.
  void silenceAll() {
    if (!connected()) return;
    writeFrame(100, 0, 100, 0);
    writeStrengthV2(0, 0, true);      // switching off is never skipped
  }

 private:
  void scanOnce() {
    NimBLEScan* scan = NimBLEDevice::getScan();
    scan->setActiveScan(true);
#if COYOTE_NIMBLE_V2
    NimBLEScanResults res = scan->getResults(3000, false);
#else
    NimBLEScanResults res = scan->start(3, false);
#endif
    for (int i = 0; i < res.getCount(); i++) {
#if COYOTE_NIMBLE_V2
      const NimBLEAdvertisedDevice* adv = res.getDevice(i);
#else
      NimBLEAdvertisedDevice* adv = const_cast<NimBLEAdvertisedDevice*>(res.getDevice(i));
#endif
      if (!adv) continue;
      String found = String(adv->getAddress().toString().c_str());
      found.toLowerCase();
      // Bound: only exactly this device. Unbound: the first Coyote that answers -
      // convenient on the desk, in the museum the MAC belongs set.
      if (_wantMac.length() && found != _wantMac) continue;
      Gen g = GEN_NONE;
      if (adv->isAdvertisingService(svcV3())) g = GEN_V3;
      else if (adv->isAdvertisingService(svcV2())) g = GEN_V2;
      else {
        String n = String(adv->getName().c_str());
        if (n == "47L121000") g = GEN_V3;
        else if (n == "D-LAB ESTIM01") g = GEN_V2;
      }
      if (g == GEN_NONE) continue;
      if (connectTo(adv, g)) {
        scan->clearResults();
        return;
      }
    }
    scan->clearResults();
  }

#if COYOTE_NIMBLE_V2
  bool connectTo(const NimBLEAdvertisedDevice* adv, Gen g) {
#else
  bool connectTo(NimBLEAdvertisedDevice* adv, Gen g) {
#endif
    if (!_client) {
      _client = NimBLEDevice::createClient();
      _client->setConnectTimeout(5000);
    }
    if (!_client->connect(const_cast<NimBLEAdvertisedDevice*>(adv))) {
      dev.logf("warn", "coyote connect failed");
      return false;
    }
    NimBLERemoteService* svc = _client->getService(g == GEN_V3 ? svcV3() : svcV2());
    if (!svc) { _client->disconnect(); return false; }

    // THE GENERATION HAS TO BE SET HERE, NOT ONLY AT THE END.
    //
    // Until 2.1 it stood right at the bottom, after the setup. Everything that
    // wanted to write during the setup checked `_gen`, though - and `_gen` was
    // still GEN_NONE there. That hit exactly the one line that had been added
    // for safety: setting the strength to zero on connect (doc 28). It never
    // ran. A safeguard that silently does nothing is worse than none, because
    // one invokes it.
    _gen = g;
    _wroteA = _wroteB = 0xFFFF;

    if (g == GEN_V3) {
      _wr = svc->getCharacteristic(wrV3());
      NimBLERemoteCharacteristic* ntf = svc->getCharacteristic(ntfV3());
      reportProps("WRITE(0x150A)", _wr);
      reportProps("NOTIFY(0x150B)", ntf);
      if (!_wr) { _gen = GEN_NONE; _client->disconnect(); return false; }
      if (ntf && ntf->canNotify()) {
#if COYOTE_NIMBLE_V2
        ntf->subscribe(true, [](NimBLERemoteCharacteristic* c, uint8_t* d, size_t n, bool isNotify) {
          _self->onNotifyV3(d, n);
        });
#else
        ntf->registerForNotify([](NimBLERemoteCharacteristic* c, uint8_t* d, size_t n, bool isNotify) {
          _self->onNotifyV3(d, n);
        });
#endif
      }
    } else {
      // THIS IS SWAPPED HERE, AND DELIBERATELY SO.
      // Channel A sits on PWM_B34 (0x1506), channel B on PWM_A34 (0x1505).
      // Measured at the device (doc 30): only 0x1506 together with the strength
      // from bits 21-11 puts out anything at all. Before it stood the other way
      // round, and because of that pulse height and pulse width lay on DIFFERENT
      // channels - two half channels, no whole one, and therefore never output.
      _waveA = svc->getCharacteristic(b34V2());
      _waveB = svc->getCharacteristic(a34V2());
      _ab2   = svc->getCharacteristic(ab2V2());
      reportProps("PWM_AB2(0x1504)", _ab2);
      reportProps("PWM_B34(0x1506) = Kanal A", _waveA);
      reportProps("PWM_A34(0x1505) = Kanal B", _waveB);
      if (!_waveA || !_waveB) { _gen = GEN_NONE; _client->disconnect(); return false; }
      // Without PWM_AB2 we cannot set the strength - and without strength there
      // is no pulse height. A V2 that lacks this characteristic is useless to us;
      // better to say so right away than to be silent later.
      if (!_ab2) {
        dev.logf("warn", "coyote v2 without PWM_AB2 - strength cannot be set");
        dev.publishEvent("coyote_no_strength_char", "fault");
        _gen = GEN_NONE;
        _client->disconnect();
        return false;
      }
      // To zero first on EVERY connect. The strength stays standing in the device
      // until someone changes it - an old value from an earlier run would
      // otherwise take effect again immediately, without anyone having wanted it.
      // (The same caution the V3 documentation demands for the soft limit.)
      writeStrengthV2(0, 0);
      // Then READ once, not only subscribe: the Coyote reports on its own only
      // when the strength CHANGES (finding Philine 2026-09-11).
      //
      // This read is now also the COUNTER-PROOF to writing: it says whether our
      // write arrived at all. A write command the server discards looks like
      // success at our end - only the device's own readback can contradict.
      if (_ab2 && _ab2->canRead()) {
        std::string v = _ab2->readValue();
        if (v.size() >= 3) {
          onNotifyV2Strength((const uint8_t*) v.data(), v.size());
          dev.logf("info", "coyote v2 strength read: A=%u B=%u", (unsigned) _strA, (unsigned) _strB);
        }
      }
      if (_ab2 && _ab2->canNotify()) {
#if COYOTE_NIMBLE_V2
        _ab2->subscribe(true, [](NimBLERemoteCharacteristic* c, uint8_t* d, size_t n, bool isNotify) {
          _self->onNotifyV2Strength(d, n);
        });
#else
        _ab2->registerForNotify([](NimBLERemoteCharacteristic* c, uint8_t* d, size_t n, bool isNotify) {
          _self->onNotifyV2Strength(d, n);
        });
#endif
      }
    }
    // Request a short connection interval (7.5-15 ms). Writing with a response
    // means one round trip per write, and a round trip takes at least one
    // interval. At the default (up to 50 ms) two writes no longer fitted into
    // the 100 ms beat. The device may refuse - then it runs with whatever it
    // offers.
    _client->updateConnParams(6, 12, 0, 400);
    _mac = String(adv->getAddress().toString().c_str());
    dev.logf("info", "coyote %s connected (%s)", genName(), _mac.c_str());
    JSONVar ev; ev["generation"] = genName(); ev["address"] = _mac;
    dev.publishEvent("coyote_found", ev, "info");
    dev.publishState();
    return true;
  }

  // B1: 0xB1 + seq + actual strength A + actual strength B. We listen in
  // because this is the ONLY feedback on whether the value we wrote arrived -
  // and because someone can turn the knob while we are writing.
  void onNotifyV3(const uint8_t* d, size_t n) {
    if (!d || n < 4 || d[0] != 0xB1) return;
    _strA = d[2]; _strB = d[3];
  }
  void onNotifyV2Strength(const uint8_t* d, size_t n) {
    if (!d || n < 3) return;
    v2ReadStrength(d, _strA, _strB);
  }

 public:
  static CoyoteLink* _self;

 private:
  NimBLEClient*               _client = nullptr;
  NimBLERemoteCharacteristic* _wr = nullptr;    // V3 write
  // MEASURED, NOT ASSUMED (Philine 2026-09-11, doc 30):
  //   PWM_B34 (0x1506) + strength in bits 21-11  ->  puts out
  //   PWM_A34 (0x1505) + strength in bits 10-0   ->  does NOT put out
  // The registers are therefore named after the ONE channel and carry the
  // data of the OTHER - exactly as the description column of the
  // manufacturer's table says and contrary to the bit names beside it, which
  // we had relied on. That is why these two pointers point at the CHANNELS,
  // not at the registers.
  NimBLERemoteCharacteristic* _waveA = nullptr;   // channel A  -> register PWM_B34 (0x1506)
  NimBLERemoteCharacteristic* _waveB = nullptr;   // channel B  -> register PWM_A34 (0x1505)
  NimBLERemoteCharacteristic* _ab2 = nullptr;   // V2 strength (read AND write)
  Gen           _gen = GEN_NONE;
  String        _mac, _wantMac;
  unsigned long _lastTry = 0;
  uint16_t      _strA = 0, _strB = 0;
  uint16_t      _wroteA = 0xFFFF, _wroteB = 0xFFFF;   // last WRITTEN (0xFFFF = never)
  uint16_t _drops = 0;   // the Coyote's connection drops since the bridge started
  uint8_t       _batt = 0;
};
CoyoteLink* CoyoteLink::_self = nullptr;

// --------------------------------------------------------------------- //
class BridgeHandler : public PunisherHandler {
 public:
  void setup() {
    // No pinMode: neopixelWrite() sets the pin up itself (RMT).
    ledRaw(0, 0, 0);
    // Red-green-blue, before anything can block. Two things at once: the sign
    // of life of the application in case the serial output lands on a different
    // port than the ROM bootloader (the normal case on the S3 as long as "USB
    // CDC On Boot" is off) - and the proof that the pin is right AND all three
    // channels of the LED work. A single-colour blink would not have revealed
    // at the first build whether only one colour is missing.
    ledRaw(LED_LEVEL, 0, 0); delay(150);
    ledRaw(0, LED_LEVEL, 0); delay(150);
    ledRaw(0, 0, LED_LEVEL); delay(150);
    ledRaw(0, 0, 0);
  }

  void begin() {
    _maxPctEnv  = (uint8_t) clampL(dev.cfgInt("estim_max_pct", ENV_ESTIM_MAX_PCT), 1, ENV_ESTIM_MAX_PCT);
    _dayMaxS    = (uint32_t) clampL(dev.cfgInt("estim_day_max", ENV_ESTIM_DAY_MAX_S), 60, ENV_ESTIM_DAY_MAX_S);
    _lvlPct[0]  = (uint8_t) clampL(dev.cfgInt("estim_lvl1", 25), 1, 100);
    _lvlPct[1]  = (uint8_t) clampL(dev.cfgInt("estim_lvl2", 45), 1, 100);
    _lvlPct[2]  = (uint8_t) clampL(dev.cfgInt("estim_lvl3", 70), 1, 100);
    _eventMs    = (uint32_t) clampL(dev.cfgInt("estim_event_ms", 1200), 200, ENV_EVENT_MAX_S * 1000L);
    _link.begin(dev.cfgStr("coyote_mac", ""));
  }

  // No Coyote on the air, no stimulus (2.2.0, doc 42 point 4). Reported as a
  // degraded component so that the programme check says "the bridge has no
  // Coyote" before the day, instead of a skipped step during it.
  void reportDegraded(JSONVar& out) override { if (!_link.connected()) out[0] = "ble"; }

  // Envelope of THIS bridge, as compiled and as the portal configured it. The
  // central unit otherwise only knows the model catalogue and would offer
  // values that this bridge silently caps (Doc 23).
  void reportLimits(JSONVar& j) override {
    j["estim_max_pct"]     = (int) _maxPctEnv;
    j["estim_day_max_s"]   = (int) _dayMaxS;
    j["estim_run_max_s"]   = (int) ENV_ESTIM_RUN_MAX_S;
    j["estim_event_max_s"] = (int) ENV_EVENT_MAX_S;
  }

  // ---------------- Duties of the base class ------------------------- //
  void safeState() override {
    if (_running) {
      JSONVar ev; ev["frames"] = (double) _frames;
      dev.publishEvent("estim_end", ev, "info");
    }
    _running = false;
    _eventCh[0].until = _eventCh[1].until = 0;
    // The raw output goes into onTick() BEFORE everything else and bypasses
    // every computation path - then it has to be switched off explicitly here
    // as well. Otherwise the emergency stop would not have caught it: the next
    // beat would simply have carried on writing frames. (Finding while
    // reviewing the raw output 2026-09-11.)
    _rawUntil = 0;
    // The warning "strength is 0" only applies while something is being put
    // out. Without the reset the state kept reporting it after the stop - and
    // at the next run not at all, because the flag no longer changed.
    _mutedWarned = false;
    // One last frame at intensity 0, then silence. The dead-man switch alone
    // would do as well, but the 100 ms window already begun should not run out
    // on top.
    _link.silenceAll();
    ledRaw(0, 0, 0);
  }

  // Raw output is output too. Reporting only `_running` here would let the
  // framework (dead-man switch, display, LED) believe the device is silent
  // while it is writing.
  bool isActive() override { return _running || _rawUntil != 0; }

  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    if (!strcmp(action, "routine_begin"))  return cmdBegin(args, err, errLen);
    if (!strcmp(action, "routine_track"))  return cmdTrack(args, err, errLen);
    if (!strcmp(action, "routine_chunk"))  return cmdChunk(args, err, errLen);
    if (!strcmp(action, "routine_commit")) return cmdCommit(args, err, errLen);
    if (!strcmp(action, "estim"))          return cmdEstim(args, err, errLen);
    if (!strcmp(action, "coyote"))         return cmdCoyote(args, err, errLen);
    snprintf(err, errLen, "unknown action");
    return false;
  }

  void reportState(JSONVar& j) override {
    j["estim"]      = _running ? "on" : "off";
    j["coyote"]     = _link.genName();
    j["ble"]        = _link.connected();
    if (_link.connected()) j["address"] = _link.mac();
    // Bound = the bridge takes ONLY this device. Empty = the first one that
    // answers. Belongs in the state, otherwise there is no way to see during
    // operation whether the bridge is tied to one device.
    j["bound"]      = _link.boundMac();
    j["a"]          = (int) _lastOut[0];
    j["b"]          = (int) _lastOut[1];
    // What the device REPORTS as its strength (device units: V2 0..2047,
    // V3 0..200). Since 2026-09-11 we write this value ourselves - the
    // readback is therefore the check whether our write arrived.
    j["strength_a"] = (int) _link.strengthA();
    j["strength_b"] = (int) _link.strengthB();
    // The slave's ceiling this run was started with. 0 means: none set yet,
    // so nothing is running either.
    j["ceiling_a"] = (int) _strMaxA;
    j["ceiling_b"] = (int) _strMaxB;
    // True if we are putting out and the device still reports strength 0: then
    // our write did NOT arrive. That is a fault, not an explanation.
    j["no_strength"] = _mutedWarned;
    if (_rawUntil) {
      JSONVar r;
      r["x"] = (int) _rawX; r["y"] = (int) _rawY; r["z"] = (int) _rawZ;
      r["us"] = (int) _rawZ * 5; r["channel"] = _rawCh ? "b" : "a";
      r["strength"] = (int) _rawStr;
      r["left_s"] = (int)(((long)(_rawUntil - millis())) / 1000);
      j["raw"] = r;
    }
    // The peak of the last run. A waveform 5 s short is over before anyone
    // looks, the question "did anything arrive at all?" is not - so the highest
    // value stays until the next run begins.
    j["peak_a"]     = (int) _peakOut[0];
    j["peak_b"]     = (int) _peakOut[1];
    j["day_s"]      = (int) _daySeconds;
    j["max_pct"]    = (int) _maxPctEnv;
    // How much stack was still free in the worst case? A crash from a stack
    // overflow does NOT announce itself over USB-CDC on the S3 (the panic goes
    // to UART0) - all one sees is a device restarting. Having this number in
    // the state turns "it crashes" into a measurement: if it drops towards zero
    // when a waveform starts, it is the stack.
    j["drops"]      = (int) _link.drops();
    j["stack_free"] = (int) uxTaskGetStackHighWaterMark(NULL);
    j["heap_free"]  = (int) ESP.getFreeHeap();
    // Uptime of the BRIDGE. If it jumps back, the bridge restarted; if it keeps
    // running while `drops` climbs, it was the Coyote.
    j["uptime_s"]   = (int)(millis() / 1000UL);
    for (uint8_t s = 0; s < SLOT_COUNT; s++) {
      if (!_slot[s].valid) continue;
      JSONVar r;
      r["id"]     = (double) _slot[s].id;
      r["crc32"]  = (double) _slot[s].crc;
      r["tracks"] = (int) _slot[s].nTracks;
      j[s == SLOT_TIME ? "routine" : "couple"] = r;
    }
  }

  void onIdentify() override { _identifyUntil = millis() + 3000; }
  // The daily budget belongs to the slave, not to the bridge: a new assignment
  // starts it over. The real bookkeeping is the central unit's anyway
  // (doc 19 §6.4) - this here is the second line.
  void onRegistered(uint16_t, const char*) override { _dayMs = 0; _daySeconds = 0; }
  void onUnregistered() override { stopRun("unregistered"); }
  void onCentralLost() override { stopRun("central lost"); }
  void onEmergency(const char*) override { safeState(); }

  // Reading: just remember it. What it means is the player's decision.
  void onLive(const PunisherLive& live) override {
    _live.depth = live.depth;
    _live.err   = live.err;
    _live.away  = live.away;
    _live.fresh = true;
    _liveAt     = live.atMs;
  }

  // Channel punishment/reward (doc 14 3a). Level 1..3 -> intensity from the
  // catalogue, profile by role: punishment on A with "stich", reward on B
  // with "zweitakt". The difference has to be FELT, not merely be a number -
  // hence fixed, distinct profiles (doc 19 §3).
  bool onPunish(const PunisherRequest& r, char* err, size_t errLen) override {
    return fireEvent(r, true, err, errLen);
  }
  bool onReward(const PunisherRequest& r, char* err, size_t errLen) override {
    return fireEvent(r, false, err, errLen);
  }

  // ---------------- Takt --------------------------------------------- //
  void onTick(unsigned long now) override {
    _link.loop(now);
    led(now);

    // Raw output for fault-finding: it goes before everything else and uses not
    // a single one of our computation paths. That is why it proves something.
    if (_rawUntil) {
      if ((long)(now - _rawUntil) >= 0) {
        _rawUntil = 0;
        _link.silenceAll();
        // HOW MANY frames really went out, and how many of them the radio link
        // accepted. Without that number, "nothing arrived" cannot be told apart
        // from "we sent nothing" - and those two were confused for hours during
        // fault-finding (doc 29).
        JSONVar ev;
        ev["frames"] = (double) _rawFrames;
        ev["written"] = (double) _rawOk;
        dev.publishEvent("coyote_raw_end", ev, "info");
        dev.logf("info", "coyote raw output ended: %lu frames sent, %lu accepted by the link",
                 (unsigned long) _rawFrames, (unsigned long) _rawOk);
        dev.publishState();
      } else if (now - _lastFrame >= _frameMs) {
        _lastFrame = now;
        _rawFrames++;
        if (_link.writeRaw(_rawCh, _rawX, _rawY, _rawZ, _rawStr)) _rawOk++;
      }
      return;
    }

    // Reading stale? Then it is unknown - and unknown means give nothing, not
    // "the last value still applies".
    if (_live.fresh && (now - _liveAt) > _staleMs) _live.fresh = false;

    if (now - _lastFrame < _frameMs) return;
    _lastFrame = now;
    if (!_running) return;
    playFrame(now);
  }

 private:
  // ---------------- Transfer ------------------------------------------ //
  // The blocks arrive over TCP and therefore in the order the central unit
  // sends them; we append them consecutively and check the number strictly.
  // A gap is not patched up but rejected at commit - then the central unit
  // sends the waveform again (doc 17 §7).
  bool cmdBegin(JSONVar& args, char* err, size_t errLen) {
    Axis axis = axisFromName(argStr(args, "axis"));
    uint8_t s = (axis == AXIS_DEPTH) ? SLOT_DEPTH : SLOT_TIME;
    Slot& sl = _slot[s];
    if (_running && _runSlot == s) {
      // The running waveform is being overwritten right now: better to stop
      // honestly than to play half old, half new support points.
      stopRun("replaced");
    }
    sl.reset();          // NOT `sl = Slot();` - see Slot::reset()
    sl.building = true;
    sl.id   = (uint32_t)(double) args["routine_id"];
    sl.crc  = (uint32_t)(double) args["crc32"];
    sl.axis = axis;
    return true;
  }

  bool cmdTrack(JSONVar& args, char* err, size_t errLen) {
    Slot* sl = slotOf((uint32_t)(double) args["routine_id"], true);
    if (!sl) { snprintf(err, errLen, "no transfer"); return false; }
    if (sl->nTracks >= MAX_TRACKS) { sl->broken = true; sl->brokenWhy = "too many tracks"; return true; }
    TrackDef& t = sl->tracks[sl->nTracks];
    t.no      = (uint8_t)(int) args["track"];
    t.role    = roleFromName(argStr(args, "role"));
    t.channel = channelFromName(argStr(args, "channel"));
    t.mode    = modeFromName(argStr(args, "mode"));
    t.couple  = coupleFromName(argStr(args, "couple"));
    t.crc     = (uint32_t)(double) args["crc32"];
    t.profile = profileByKey(argStr(args, "profile"));
    if (!t.profile && t.role != ROLE_TARGET) t.profile = profileForRole(t.role);
    t.first   = sl->used;
    t.n       = 0;
    sl->curTrack = (int8_t) sl->nTracks;
    sl->nTracks++;
    sl->nextSeq = 0;
    return true;
  }

  bool cmdChunk(JSONVar& args, char* err, size_t errLen) {
    Slot* sl = slotOf((uint32_t)(double) args["routine_id"], true);
    if (!sl || sl->curTrack < 0) { snprintf(err, errLen, "no transfer"); return false; }
    TrackDef& t = sl->tracks[sl->curTrack];
    if ((uint8_t)(int) args["track"] != t.no) { sl->broken = true; sl->brokenWhy = "track out of order"; return true; }
    uint16_t seq = (uint16_t)(int) args["seq"];
    if (seq != sl->nextSeq) { sl->broken = true; sl->brokenWhy = "chunk out of order"; return true; }
    sl->nextSeq++;
    JSONVar pts = args["points"];
    int n = pts.length();
    uint32_t x = t.n ? sl->pts[t.first + t.n - 1].x : 0;
    uint32_t step = (sl->axis == AXIS_TIME) ? 10u : 1u;   // 10 ms and 0.1 % respectively
    for (int i = 0; i < n; i++) {
      if (sl->used >= MAX_POINTS) { sl->broken = true; sl->brokenWhy = "too many points"; return true; }
      JSONVar p = pts[i];
      uint16_t dx = (uint16_t)(double) p[0];
      uint8_t  v  = (uint8_t)(int) p[1];
      uint8_t  tl = (uint8_t)(int) p[2];
      x += (uint32_t) dx * step;
      sl->pts[sl->used].x = x;
      sl->pts[sl->used].v = v;
      sl->pts[sl->used].tol = tl;
      sl->used++;
      t.n++;
    }
    return true;
  }

  bool cmdCommit(JSONVar& args, char* err, size_t errLen) {
    uint32_t id = (uint32_t)(double) args["routine_id"];
    uint32_t want = (uint32_t)(double) args["crc32"];
    Slot* sl = slotOf(id, true);
    if (!sl) { respondFail("routine incomplete", id, -1, 0); snprintf(err, errLen, "no transfer"); return false; }
    if (sl->broken) {
      dev.logf("warn", "waveform %lu rejected: %s", (unsigned long) id, sl->brokenWhy);
      respondFail("routine incomplete", id, -1, 0);
      sl->building = false; sl->valid = false;
      snprintf(err, errLen, "%s", sl->brokenWhy);
      return false;
    }
    // Hash every track itself, then the whole. The bridge does not believe the
    // central unit, it recomputes (doc 17 §7).
    Crc32 whole; whole.reset();
    for (uint8_t i = 0; i < sl->nTracks; i++) {
      TrackDef& t = sl->tracks[i];
      Crc32 c; c.reset();
      uint32_t prev = 0;
      uint32_t step = (sl->axis == AXIS_TIME) ? 10u : 1u;
      for (uint16_t k = 0; k < t.n; k++) {
        const Point& p = sl->pts[t.first + k];
        uint16_t dx = (uint16_t)((p.x - prev) / step);
        prev = p.x;
        uint8_t b[4];
        wireBytes(dx, p.v, p.tol, b);
        c.add(b, 4);
        whole.add(b, 4);
      }
      if (c.value() != t.crc) {
        dev.logf("warn", "waveform %lu track %u crc mismatch: device %08lX central %08lX",
                 (unsigned long) id, (unsigned) t.no,
                 (unsigned long) c.value(), (unsigned long) t.crc);
        respondFail("routine crc mismatch", id, (int) t.no, c.value());
        sl->building = false; sl->valid = false;
        snprintf(err, errLen, "crc mismatch");
        return false;
      }
    }
    if (whole.value() != want) {
      dev.logf("warn", "waveform %lu crc mismatch: device %08lX central %08lX",
               (unsigned long) id, (unsigned long) whole.value(), (unsigned long) want);
      respondFail("routine crc mismatch", id, -1, whole.value());
      sl->building = false; sl->valid = false;
      snprintf(err, errLen, "crc mismatch");
      return false;
    }
    sl->durationMs = 0;
    for (uint8_t i = 0; i < sl->nTracks; i++) {
      TrackDef& t = sl->tracks[i];
      if (t.n && sl->pts[t.first + t.n - 1].x > sl->durationMs) sl->durationMs = sl->pts[t.first + t.n - 1].x;
    }
    sl->building = false;
    sl->valid = true;
    sl->curTrack = -1;
    JSONVar r;
    r["ok"] = true; r["action"] = "routine_commit";
    r["routine_id"] = (double) id; r["crc32"] = (double) whole.value();
    r["tracks"] = (int) sl->nTracks;
    respond(r);
    dev.logf("info", "waveform %lu stored: %u tracks, %u points, crc %08lX",
             (unsigned long) id, (unsigned) sl->nTracks, (unsigned) sl->used,
             (unsigned long) whole.value());
    return true;
  }

  // ---------------- Binding to ONE Coyote ----------------------------- //
  // `coyote {op: "bind"}`                 -> keep the one currently connected
  // `coyote {op: "bind", address: "..."}` -> exactly this one, even if it is off
  // `coyote {op: "unbind"}`               -> the first one found again
  //
  // In the museum several Coyotes lie within radio range; without a binding
  // the bridge grabs whatever answers first. Until now the binding could only
  // be set in the setup portal - so only by picking the device up. Now it
  // works from within the installation (request Philine 2026-09-11).
  bool cmdCoyote(JSONVar& args, char* err, size_t errLen) {
    const char* op = argStr(args, "op");
    if (!op) { snprintf(err, errLen, "op missing"); return false; }

    // --- Raw output: a known frame, past EVERYTHING -----------------------
    //
    // When the channels stay silent, there are three suspects: the strength at
    // the device (the pulse height - without it nothing comes out, whatever the
    // curve says), our mapping intensity -> pulse width, and the question
    // whether PWM_A34 really sits on channel A (the official table contradicts
    // itself there, doc 21 §8).
    //
    // `op: "raw"` writes X/Y/Z unchanged, default {1,9,20} - exactly the value
    // the DG-LAB documentation calls "100 Hz, 100 us" and that its own example
    // waveforms use for full deflection. If it stays silent AT THAT, it is not
    // our arithmetic.
    //
    // The strength has to come along explicitly here too. No default, for the
    // same reason as in cmdEstim: a guessed pulse height does not exist on this
    // device. The device's envelope caps it on top of that.
    if (!strcmp(op, "raw")) {
      if (!_link.connected()) { snprintf(err, errLen, "no coyote"); return false; }
      if (_running) { snprintf(err, errLen, "busy"); return false; }
      int rs = argInt(args, "strength", -1);
      if (rs < 0) { snprintf(err, errLen, "strength missing"); return false; }
      _rawStr = (uint8_t) clampL(rs, 0, (long) _maxPctEnv);
      _rawX  = (uint8_t) clampL(argInt(args, "x", 1), 0, 31);
      _rawY  = (uint16_t) clampL(argInt(args, "y", 9), 0, 1023);
      _rawZ  = (uint8_t) clampL(argInt(args, "z", 20), 0, 20);   // 20 = 100 us, our own ceiling
      _rawCh = (uint8_t) clampL(argInt(args, "channel", 0), 0, 1);
      _rawUntil = millis() + (unsigned long) clampL(argInt(args, "seconds", 5), 1, 30) * 1000UL;
      _rawFrames = _rawOk = 0;
      JSONVar ev;
      ev["x"] = (int) _rawX; ev["y"] = (int) _rawY; ev["z"] = (int) _rawZ;
      ev["strength"] = (int) _rawStr;
      ev["channel"] = _rawCh ? "b" : "a";
      ev["strength_a"] = (int) _link.strengthA();
      ev["strength_b"] = (int) _link.strengthB();
      dev.publishEvent("coyote_raw", ev, "info");
      dev.logf("warn", "coyote raw output %s: X=%u Y=%u Z=%u (%u us) at %u%% strength for %lu ms",
               _rawCh ? "B" : "A", (unsigned) _rawX, (unsigned) _rawY, (unsigned) _rawZ,
               (unsigned) _rawZ * 5, (unsigned) _rawStr,
               (unsigned long)(_rawUntil - millis()));
      dev.publishState();
      return true;
    }
    if (!strcmp(op, "raw_stop")) {
      _rawUntil = 0;
      _link.silenceAll();
      dev.publishState();
      return true;
    }

    // --- Probe: ONE pulse, exactly as the punishment would play it ---------
    //
    // `coyote {op:"probe", channel:"a"|"b", profile:"stich", pct:45,
    //          str_a:60, str_b:60, seconds:2}`
    //
    // WHAT FOR: where the electrodes sit decides profile AND height, and the
    // form of the day shifts both. "If 50 % was still bearable on Tuesday, it
    // can already be otherwise on Thursday" (Philine 2026-09-12). Entering a value
    // without having felt it is guesswork.
    //
    // TWO PROPERTIES THAT ARE NOT NEGOTIABLE:
    //
    //  1. It goes through armEvent() - the same path as the real punishment. A
    //     probe on a computation path of its own may feel right and still prove
    //     nothing (doc 32 §4).
    //  2. It reports `estim_probe`, NOT `punish`. A probe is not a punishment:
    //     it must not appear in the logbook and must not cost anything
    //     (doc 22: "A test is not an achievement").
    //
    // The daily budget counts it all the same - that one counts current through
    // a human being, not bookings. playEventOnly() does that by itself.
    if (!strcmp(op, "probe")) {
      if (!_link.connected()) { snprintf(err, errLen, "no coyote"); return false; }
      if (_running && !_eventOnly) { snprintf(err, errLen, "busy"); return false; }
      if (_rawUntil)              { snprintf(err, errLen, "raw output running"); return false; }
      if (_daySeconds >= _dayMaxS) { snprintf(err, errLen, "day budget spent"); return false; }
      // The ceiling is mandatory here too, for the same reason as in fireEvent:
      // the level says HOW MUCH of the ceiling, never how high it lies. A probe
      // without a ceiling would be a guessed pulse height, and there is no such thing.
      int sa = argInt(args, "str_a", -1);
      int sb = argInt(args, "str_b", -1);
      if (sa < 0 || sb < 0) {
        snprintf(err, errLen, "no calibration");
        dev.publishEvent("estim_no_calibration", "warn");
        return false;
      }
      _strMaxA = (uint8_t) clampL(sa, 0, (long) _maxPctEnv);
      _strMaxB = (uint8_t) clampL(sb, 0, (long) _maxPctEnv);
      const char* chs = argStr(args, "channel");
      uint8_t ch = (chs && (chs[0] == 'b' || chs[0] == 'B')) ? 1 : 0;
      Role role = ch ? ROLE_REWARD : ROLE_PUNISH;
      const Profile* p = profileByKey(argStr(args, "profile"));
      if (!p) p = profileForRole(role);
      uint8_t pct = (uint8_t) clampL(argInt(args, "pct", 25), 1, 100);
      uint32_t durMs = (uint32_t) clampL(argInt(args, "seconds", 0), 0, ENV_EVENT_MAX_S) * 1000UL;
      if (!durMs) durMs = _eventMs;
      armEvent(ch, role, p, pct, durMs);
      JSONVar ev;
      ev["channel"] = ch ? "b" : "a";
      ev["profile"] = p ? p->key : "";
      ev["pct"] = (int) pct;
      ev["ms"] = (int) durMs;
      ev["str_a"] = (int) _strMaxA;
      ev["str_b"] = (int) _strMaxB;
      dev.publishEvent("estim_probe", ev, "info");
      dev.logf("warn", "estim probe on channel %s: profile %s at %u%% of ceiling A=%u B=%u for %lu ms",
               ch ? "B" : "A", p ? p->key : "-", (unsigned) pct,
               (unsigned) _strMaxA, (unsigned) _strMaxB, (unsigned long) durMs);
      dev.publishState();
      return true;
    }

    if (!strcmp(op, "unbind")) {
      dev.cfgSet("coyote_mac", "");
      _link.bind("");
      dev.publishEvent("coyote_unbound", "info");
      dev.publishState();
      return true;
    }
    if (strcmp(op, "bind")) { snprintf(err, errLen, "unknown op"); return false; }

    const char* given = argStr(args, "address");
    String mac = given ? String(given) : _link.mac();
    mac.trim();
    mac.toLowerCase();
    // A MAC or nothing at all: a typo would otherwise bind the bridge silently
    // to a device that does not exist, and it would never find one again.
    if (mac.length() != 17) {
      snprintf(err, errLen, "no coyote connected and no valid address given");
      return false;
    }
    for (uint8_t i = 0; i < 17; i++) {
      char c = mac[i];
      bool sep = (i % 3) == 2;
      if (sep ? (c != ':') : !isxdigit((int) c)) {
        snprintf(err, errLen, "address is not a MAC (aa:bb:cc:dd:ee:ff)");
        return false;
      }
    }
    if (!dev.cfgSet("coyote_mac", mac.c_str())) {
      snprintf(err, errLen, "could not store the binding");
      return false;
    }
    _link.bind(mac);
    JSONVar ev; ev["address"] = mac;
    dev.publishEvent("coyote_bound", ev, "info");
    dev.publishState();
    return true;
  }

  // ---------------- Abspielen ---------------------------------------- //
  bool cmdEstim(JSONVar& args, char* err, size_t errLen) {
    const char* m = argStr(args, "mode");
    if (!m) { snprintf(err, errLen, "mode missing"); return false; }
    if (!strcmp(m, "off")) { stopRun("commanded"); return true; }

    uint32_t id = (uint32_t)(double) args["routine_id"];
    uint32_t crc = (uint32_t)(double) args["crc32"];
    bool couple = !strcmp(m, "couple");
    uint8_t s = couple ? SLOT_DEPTH : SLOT_TIME;
    Slot& sl = _slot[s];
    // "routine unknown" is the keyword on which the central unit transfers the
    // waveform again (libs/punmqtt.py) - hence exactly this wording.
    if (!sl.valid || sl.id != id || sl.crc != crc) {
      respondFail("routine unknown", id, -1, sl.valid ? sl.crc : 0);
      snprintf(err, errLen, "routine unknown");
      return false;
    }
    if (!_link.connected()) { snprintf(err, errLen, "no coyote"); return false; }
    if (_daySeconds >= _dayMaxS) { snprintf(err, errLen, "day budget spent"); return false; }

    // THE CEILING. Since the bridge writes the strength itself, the strength is
    // the pulse height - and the only limit against it is the value from the
    // slave's calibration (decision Philine 2026-09-11, doc 28). There is NO
    // default: without str_a/str_b nothing runs. Better a run that does not
    // start than a run at a guessed height.
    int sa = argInt(args, "str_a", -1);
    int sb = argInt(args, "str_b", -1);
    if (sa < 0 || sb < 0) {
      snprintf(err, errLen, "no calibration");
      dev.logf("warn", "estim refused: the command carries no strength ceiling (str_a/str_b)");
      dev.publishEvent("estim_no_calibration", "warn");
      return false;
    }
    _strMaxA = (uint8_t) clampL(sa, 0, (long) _maxPctEnv);
    _strMaxB = (uint8_t) clampL(sb, 0, (long) _maxPctEnv);

    // The installation's limits, capped by our own. The central unit may lower,
    // never raise.
    _frameMs  = (uint32_t) clampL(argInt(args, "frame_ms", ENV_FRAME_MS), ENV_FRAME_MS, 1000);
    _staleMs  = (uint32_t) clampL(argInt(args, "stale_ms", 1500), 200, 10000);
    if (argInt(args, "day_max_s", 0) > 0)
      _dayMaxS = (uint32_t) clampL(argInt(args, "day_max_s", ENV_ESTIM_DAY_MAX_S), 60, ENV_ESTIM_DAY_MAX_S);
    _maxPct   = (uint8_t) clampL(argInt(args, "max_pct", 100), 1, _maxPctEnv);
    _repeats  = (uint16_t) clampL(argInt(args, "repeats", 1), 1, 20);

    _runSlot   = s;
    _coupleRun = couple;
    _eventOnly = false;
    _running   = true;
    _startedAt = millis();
    _frames    = 0;
    _phase[0] = _phase[1] = 0;
    _phaseProfile[0] = _phaseProfile[1] = nullptr;
    JSONVar ev;
    ev["routine_id"] = (double) id; ev["mode"] = m; ev["tracks"] = (int) sl.nTracks;
    ev["max_pct"] = (int) _maxPct;
    dev.publishEvent("estim_start", ev, "info");
    dev.publishState();
    return true;
  }

  void stopRun(const char* why) {
    if (!_running) return;
    _running = false;
    _eventOnly = false;
    JSONVar ev; ev["reason"] = why; ev["frames"] = (double) _frames;
    // The peak belongs in the event: a waveform 5 s short is over before anyone
    // looks, but "did anything arrive at all?" stays answerable this way
    // (finding Philine 2026-09-11).
    ev["peak_a"] = (int) _peakOut[0];
    ev["peak_b"] = (int) _peakOut[1];
    dev.publishEvent("estim_end", ev, "info");
    _link.silenceAll();
    _lastOut[0] = _lastOut[1] = 0;
    dev.publishState();
  }

  // One frame. This is where all the rules from doc 19 §6 come together.
  void playFrame(unsigned long now) {
    // Envelope: no run without an end.
    if ((now - _startedAt) / 1000UL > (unsigned long) ENV_ESTIM_RUN_MAX_S) { stopRun("run limit"); return; }
    if (_daySeconds >= _dayMaxS) { stopRun("day budget spent"); return; }

    // A channel event without a running waveform: only the event's own beat,
    // and done as soon as it has run out.
    if (_eventOnly) {
      playEventOnly(now);
      return;
    }

    Slot& sl = _slot[_runSlot];
    if (!sl.valid) { stopRun("waveform gone"); return; }

    uint32_t x = 0;
    if (sl.axis == AXIS_TIME) {
      uint32_t t = now - _startedAt;
      if (sl.durationMs) {
        if (t > sl.durationMs * (uint32_t) _repeats) { stopRun("done"); return; }
        x = t % sl.durationMs;
      } else {
        x = t;
      }
    } else {
      // Depth axis: X IS the reading. Without a fresh reading X has no meaning -
      // then the whole waveform outputs nothing, the absolute tracks included.
      // Otherwise the installation would play on from a frozen value and punish
      // someone for a posture it no longer measures. (Finding of the check
      // 2026-09-11; the test fake had a gap here.)
      if (!_live.fresh) { emit(100, 0, 100, 0); return; }
      float d = _live.depth;
      if (d < 0.0f) d = 0.0f;
      if (d > 100.0f) d = 100.0f;
      x = (uint32_t) lroundf(d * 10.0f);
    }

    // Per channel the track with the highest precedence (doc 19 §6.2).
    Role    bestRole[2] = {ROLE_UNKNOWN, ROLE_UNKNOWN};
    float   bestOut[2]  = {0.0f, 0.0f};
    const Profile* bestProf[2] = {nullptr, nullptr};

    for (uint8_t i = 0; i < sl.nTracks; i++) {
      TrackDef& t = sl.tracks[i];
      if (t.role == ROLE_TARGET) continue;                 // is graded, puts nothing out
      uint8_t ch = (t.channel == CH_A) ? 0 : (t.channel == CH_B ? 1 : 255);
      if (ch > 1) continue;                                // not a channel of this bridge (vibe, for instance)
      float v = valueAt(&sl.pts[t.first], t.n, x);
      float out = outputAt(t.mode, t.couple, v, _live);
      // "Gone" takes EVERY track to zero, the punishment included (doc 19 §6.1):
      // otherwise stopping would cost more than carrying on.
      if (_live.away && _live.fresh) out = 0.0f;
      out = out * (float) _maxPct / 100.0f;
      if (precedence(t.role) > precedence(bestRole[ch])) {
        bestRole[ch] = t.role; bestOut[ch] = out; bestProf[ch] = t.profile;
      }
    }

    // A channel event beats the running track: it is the answer to something
    // that has JUST happened and must not be lost.
    for (uint8_t ch = 0; ch < 2; ch++) {
      if (_eventCh[ch].until && (long)(now - _eventCh[ch].until) < 0) {
        bestRole[ch] = _eventCh[ch].role;
        bestOut[ch]  = (float) _eventCh[ch].pct;
        bestProf[ch] = _eventCh[ch].profile;
      } else if (_eventCh[ch].until) {
        _eventCh[ch].until = 0;
      }
    }

    uint16_t per[2]; uint8_t inten[2];
    for (uint8_t ch = 0; ch < 2; ch++) frameFor(ch, bestRole[ch], bestOut[ch], bestProf[ch], per[ch], inten[ch]);
    emit(per[0], inten[0], per[1], inten[1]);
    _frames++;
    if (_emitted) {
      _dayMs += _frameMs;
      _daySeconds = _dayMs / 1000UL;
    }
  }

  // Channel event without a waveform: only the two event tracks.
  void playEventOnly(unsigned long now) {
    bool any = false;
    Role r[2] = {ROLE_UNKNOWN, ROLE_UNKNOWN};
    float o[2] = {0.0f, 0.0f};
    const Profile* p[2] = {nullptr, nullptr};
    for (uint8_t ch = 0; ch < 2; ch++) {
      if (_eventCh[ch].until && (long)(now - _eventCh[ch].until) < 0) {
        r[ch] = _eventCh[ch].role;
        o[ch] = (float) _eventCh[ch].pct * (float) _maxPctEnv / 100.0f;
        p[ch] = _eventCh[ch].profile;
        any = true;
      } else if (_eventCh[ch].until) {
        _eventCh[ch].until = 0;
      }
    }
    if (!any) { _eventOnly = false; stopRun("event done"); return; }
    uint16_t per[2]; uint8_t inten[2];
    for (uint8_t ch = 0; ch < 2; ch++) frameFor(ch, r[ch], o[ch], p[ch], per[ch], inten[ch]);
    emit(per[0], inten[0], per[1], inten[1]);
    _frames++;
    if (_emitted) { _dayMs += _frameMs; _daySeconds = _dayMs / 1000UL; }
  }

  // Profile + height -> one frame. The profile keeps its own beat per channel
  // and starts over at every profile change - otherwise a "zweitakt" would
  // fall into the middle of its own pause and be unrecognisable.
  void frameFor(uint8_t ch, Role role, float out, const Profile* prof,
                uint16_t& periodMs, uint8_t& intensity) {
    if (out < 0.0f) out = 0.0f;
    if (out > 100.0f) out = 100.0f;
    if (!prof || out <= 0.0f) {
      periodMs = 100; intensity = 0;         // valid frequency, no output
      _phase[ch] = 0; _phaseProfile[ch] = prof;
      return;
    }
    if (_phaseProfile[ch] != prof) { _phase[ch] = 0; _phaseProfile[ch] = prof; }
    uint8_t f = prof->shape[_phase[ch] % prof->n];
    _phase[ch]++;
    float hz = prof->hzLow + (prof->hzHigh - prof->hzLow) * ((float) f / 100.0f);
    periodMs  = periodMsFromHz(hz);
    long v = lroundf(out * (float) f / 100.0f);
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    intensity = (uint8_t) v;
    (void) role;
  }

  // The slave's ceiling, the ONLY upper limit on the pulse height (decision
  // Philine 2026-09-11: calibration per slave, no second value in the envelope,
  // no soft limit in the device). It arrives with the command; without it
  // nothing runs at all - see cmdEstim().
  static uint8_t underCeiling(uint8_t intensityPct, uint8_t ceilingPct) {
    if (intensityPct > 100) intensityPct = 100;
    if (ceilingPct > 100) ceilingPct = 100;
    return (uint8_t)(((uint16_t) intensityPct * (uint16_t) ceilingPct + 50U) / 100U);
  }

  void emit(uint16_t perA, uint8_t intA, uint16_t perB, uint8_t intB) {
    // Curve value x ceiling = what really goes out. From here on nobody adds
    // anything any more.
    uint8_t outA = underCeiling(intA, _strMaxA);
    uint8_t outB = underCeiling(intB, _strMaxB);
    _link.writeFrame(perA, outA, perB, outB);
    _lastOut[0] = outA;
    _lastOut[1] = outB;
    if (outA > _peakOut[0]) _peakOut[0] = outA;
    if (outB > _peakOut[1]) _peakOut[1] = outB;

    // We WRITE the strength ourselves now. If the device still reports 0 after
    // that, our write did not arrive - that is a real fault and no longer an
    // explanation.
    //
    // Until 2026-09-11 the same warning meant the opposite: "the knob on the
    // device is at 0, that is fine". That was wrong (doc 28 §2).
    bool mute = (outA && !_link.strengthA()) || (outB && !_link.strengthB());
    if (mute != _mutedWarned) {
      _mutedWarned = mute;
      if (mute) {
        JSONVar ev;
        ev["strength_a"] = (int) _link.strengthA();
        ev["strength_b"] = (int) _link.strengthB();
        ev["out_a"] = (int) outA; ev["out_b"] = (int) outB;
        dev.publishEvent("estim_strength_not_set", ev, "fault");
        dev.logf("warn", "we wrote a strength but the device still reports 0 (A=%u B=%u) - the write did not take",
                 (unsigned) _link.strengthA(), (unsigned) _link.strengthB());
      }
      dev.publishState();
    }
    // Report the state DURING the run. Before, it was published only at
    // estim_start and estim_end - that is, at exactly the two points where the
    // output is 0: a waveform begins at rest, and at the end it is explicitly
    // set to 0. In between it was running, and the web interface showed
    // "A 0 % - B 0 %" the whole time (finding Philine 2026-09-11). With a waveform
    // 4.8 s long one otherwise NEVER sees anything.
    //
    // Not on every frame: that would be ten state messages per second. At most
    // every STATE_RUN_MS, and only if something really changed - a jump from or
    // to zero always counts, otherwise only from two percentage points up.
    unsigned long now = millis();
    bool jump  = (outA == 0) != (_shownOut[0] == 0) || (outB == 0) != (_shownOut[1] == 0);
    bool moved = absdiff(outA, _shownOut[0]) >= 2 || absdiff(outB, _shownOut[1]) >= 2;
    if ((jump || moved) && (now - _lastRunState) >= STATE_RUN_MS) {
      _lastRunState = now;
      _shownOut[0] = outA; _shownOut[1] = outB;
      dev.publishState();
    }
    // What counts for the daily budget is what really went out - not what the
    // curve wanted. At ceiling 0 the clock does not run.
    _emitted = (outA != 0) || (outB != 0);
  }

  static uint8_t absdiff(uint8_t a, uint8_t b) { return a > b ? a - b : b - a; }

  bool fireEvent(const PunisherRequest& r, bool punish, char* err, size_t errLen) {
    if (!_link.connected()) { snprintf(err, errLen, "no coyote"); return false; }
    if (_daySeconds >= _dayMaxS) { snprintf(err, errLen, "day budget spent"); return false; }
    // A channel event needs the ceiling too. It arrives over
    // punisher/slaves/<id>/punish and therefore knows WHO it is about - the
    // central unit attaches str_a/str_b. Without them no output; the abstract
    // level 1..3 only says HOW MUCH of the ceiling, never how high it lies.
    if (r.args) {
      int sa = argInt(*r.args, "str_a", -1);
      int sb = argInt(*r.args, "str_b", -1);
      if (sa < 0 || sb < 0) {
        snprintf(err, errLen, "no calibration");
        dev.publishEvent("estim_no_calibration", "warn");
        return false;
      }
      _strMaxA = (uint8_t) clampL(sa, 0, (long) _maxPctEnv);
      _strMaxB = (uint8_t) clampL(sb, 0, (long) _maxPctEnv);
    } else {
      snprintf(err, errLen, "no calibration");
      return false;
    }
    uint8_t ch = punish ? 0 : 1;                         // Strafe auf A, Lob auf B
    Role role = punish ? ROLE_PUNISH : ROLE_REWARD;
    // WHICH waveform.
    //
    // Until 2026-09-12 this read a fixed `profileByKey(punish ? "stich" :
    // "zweitakt")` - a decision about anatomy, taken by a device that does not
    // know where the electrodes are stuck. `stich` runs at 50..80 Hz; on the
    // backside too little, on the genitals too much (finding Philine 2026-09-12,
    // doc 32). The central unit now sends the key along.
    //
    // If this build does not know the key, the role's first profile applies -
    // not silence. A punishment pulse that fails to happen because of an unknown
    // name is the worse surprise.
    const Profile* p = profileByKey(argStr(*r.args, "profile"));
    if (!p) p = profileForRole(role);
    // HOW MUCH of the ceiling this level uses.
    //
    // Until 2026-09-12 this lived exclusively here in the device (NVS
    // estim_lvl1/2/3, default 25/45/70) - that is, per BRIDGE instead of per
    // person, and reachable only through the setup portal. How hard a punishment
    // turns out is a property of the slave, though, not of the box on the wall
    // (question Philine 2026-09-12, doc 31). The central unit now sends the value
    // along; the device default stays the fallback if none comes.
    uint8_t pct = (uint8_t) clampL(argInt(*r.args, "pct", _lvlPct[(r.level ? r.level : 1) - 1]), 1, 100);
    armEvent(ch, role, p, pct, _eventMs);
    // ONE LINE INTO THE LOG, and with everything that determines the outcome.
    //
    // Until 2026-09-12 there was NOTHING here. A punishment in which nothing
    // happens was therefore indistinguishable from one that never arrived - the
    // log kept silent the same way in both cases (finding Philine 2026-09-12:
    // "raw output works, the test does not"). The raw output and the probe have
    // always written such a line; of all paths, the one used in operation had
    // none.
    dev.logf("warn", "estim %s on channel %s: profile %s at %u%% for %lu ms, ceiling A=%u B=%u",
             punish ? "punish" : "reward", ch ? "B" : "A", p ? p->key : "-",
             (unsigned) pct, (unsigned long) _eventMs,
             (unsigned) _strMaxA, (unsigned) _strMaxB);
    JSONVar ev;
    ev["cid"] = (double) r.id; ev["level"] = (int) r.level; ev["kind"] = "estim";
    ev["channel"] = punish ? "a" : "b";
    ev["pct"] = (int) pct;
    ev["profile"] = p ? p->key : "";
    dev.publishEvent(punish ? "punish" : "reward", ev, punish ? "punish" : "reward");
    return true;
  }

  // Arm an event track. The ONLY place that does so - punishment, reward and
  // the probe (op "probe") all go through here. This is not tidying up: a
  // probe on a computation path of its own would prove how the OTHER path
  // feels, and that is exactly nothing (doc 32 §4).
  void armEvent(uint8_t ch, Role role, const Profile* p, uint8_t pct, uint32_t durMs) {
    _eventCh[ch].role    = role;
    _eventCh[ch].pct     = (uint8_t) clampL(pct, 1, 100);
    _eventCh[ch].profile = p;
    _eventCh[ch].until   = millis() + durMs;
    _phase[ch] = 0; _phaseProfile[ch] = nullptr;
    // An event may arrive without a running waveform as well: then the beat
    // plays for its duration only.
    if (!_running) { _running = true; _runSlot = SLOT_TIME; _startedAt = millis(); _eventOnly = true; }
  }

  // ---------------- Odds and ends ------------------------------------ //
  Slot* slotOf(uint32_t id, bool building) {
    for (uint8_t s = 0; s < SLOT_COUNT; s++)
      if (_slot[s].id == id && (!building || _slot[s].building)) return &_slot[s];
    return nullptr;
  }

  void respond(JSONVar& j) { dev.publishResponse(j); }
  void respondFail(const char* why, uint32_t id, int track, uint32_t mine) {
    JSONVar j;
    j["ok"] = false; j["error"] = why; j["routine_id"] = (double) id;
    if (track >= 0) j["track"] = track;
    if (mine) j["crc32"] = (double) mine;
    respond(j);
  }

  // Write the LED. Only if something really changes: neopixelWrite() briefly
  // halts the interrupts for its telegram, and doing that every 100 ms next to
  // a live BLE connection is trouble for nothing.
  void ledRaw(uint8_t r, uint8_t g, uint8_t b) {
    uint32_t want = ((uint32_t) r << 16) | ((uint32_t) g << 8) | b;
    if (want == _ledShown) return;
    _ledShown = want;
    neopixelWrite(LED_PIN, r, g, b);
  }

  // The COLOUR says what is going on; the blinking only whether something is
  // running. That way the state is readable from two metres away without
  // counting patterns (Philine 2026-09-11: "otherwise one is blind").
  void led(unsigned long now) {
    uint8_t r = 0, g = 0, b = 0;
    unsigned long period = 1500UL;      // langsam = Ruhe
    bool steady = false;

    if (_identifyUntil && (long)(now - _identifyUntil) < 0) {
      r = g = b = LED_LEVEL; steady = true;             // weiss: identify
    } else if (!dev.centralAlive()) {
      r = LED_LEVEL;                                    // red slow: no central unit
    } else if (_daySeconds >= _dayMaxS) {
      r = LED_LEVEL; period = 250UL;                    // red fast: budget spent
    } else if (!_link.connected()) {
      b = LED_LEVEL;                                    // blue: looking for a Coyote
    } else {
      g = LED_LEVEL;                                    // green: Coyote there
      if (_running) period = 250UL;                     // fast: something is running
    }

    // The dark part of the beat is the longer one: an LED that is on a quarter
    // of the time draws less attention than one that shines constantly - in the
    // museum the device sits on a human being.
    if (steady || (now % period) < (period / 4)) ledRaw(r, g, b);
    else ledRaw(0, 0, 0);
  }

  static const char* argStr(JSONVar& a, const char* k) {
    if (!a.hasOwnProperty(k)) return nullptr;
    const char* s = (const char*) a[k];
    return (s && s[0]) ? s : nullptr;
  }
  static long argInt(JSONVar& a, const char* k, long def) {
    return a.hasOwnProperty(k) ? (long)(double) a[k] : def;
  }
  static long clampL(long v, long lo, long hi) { return v < lo ? lo : (v > hi ? hi : v); }

  struct ChannelEvent {
    unsigned long  until   = 0;
    Role           role    = ROLE_UNKNOWN;
    uint8_t        pct     = 0;
    const Profile* profile = nullptr;
  };

  CoyoteLink   _link;
  Slot         _slot[SLOT_COUNT];
  Live         _live;
  unsigned long _liveAt = 0;

  bool          _running   = false;
  bool          _coupleRun = false;
  bool          _eventOnly = false;
  uint8_t       _runSlot   = SLOT_TIME;
  unsigned long _startedAt = 0, _lastFrame = 0, _identifyUntil = 0;
  uint32_t      _ledShown = 0xFFFFFFFF;   // last written; invalid = the first write goes through
  uint32_t      _frames = 0;
  uint16_t      _repeats = 1;
  uint32_t      _frameMs = ENV_FRAME_MS, _staleMs = 1500;
  uint8_t       _maxPct = 100, _maxPctEnv = ENV_ESTIM_MAX_PCT;
  uint8_t       _lvlPct[3] = {25, 45, 70};
  uint32_t      _eventMs = 1200;
  uint32_t      _dayMs = 0, _daySeconds = 0, _dayMaxS = ENV_ESTIM_DAY_MAX_S;
  // The slave's ceiling, in percent per channel. NO default: 0 means "not
  // set", and without a set value no run starts (doc 28 §4).
  uint8_t       _strMaxA = 0, _strMaxB = 0;
  bool          _emitted = false;       // did anything really go out in the last frame?
  // Raw output (fault-finding): X/Y/Z unchanged, until _rawUntil
  uint8_t       _rawX = 1, _rawZ = 20, _rawCh = 0, _rawStr = 0;
  uint32_t      _rawFrames = 0, _rawOk = 0;   // sent / accepted by the link
  uint16_t      _rawY = 9;
  unsigned long _rawUntil = 0;
  bool          _mutedWarned = false;   // the strength did not arrive in the device
  uint8_t       _peakOut[2] = {0, 0};    // highest output of the LAST run
  uint8_t       _shownOut[2] = {0, 0};   // what was last reported
  unsigned long _lastRunState = 0;
  uint8_t       _lastOut[2] = {0, 0};
  uint16_t      _phase[2] = {0, 0};
  const Profile* _phaseProfile[2] = {nullptr, nullptr};
  ChannelEvent  _eventCh[2];
};

// --------------------------------------------------------------------- //
BridgeHandler handler;

void setup() {
  // Serial.begin() is the base class's job - called a second time here, it
  // would briefly drop the USB-CDC connection just established on the S3.
  handler.setup();

  PunisherConfig cfg;
  cfg.ssid = SSID; cfg.password = PASSWORD;
  cfg.broker = MQTT_BROKER; cfg.mqttUser = MQTT_USER; cfg.mqttPass = MQTT_PASS;
  cfg.tls = MQTT_TLS; cfg.port = MQTT_PORT;      // TLS (2.3, Doc 53)
  cfg.clearNvs = PUNISHER_NVS_CLEAR;             // wipe stored config once (2.3.2)
  cfg.clientId = MQTT_CLIENT;
  cfg.modelUuid   = model_UUID;          // deviceUuid is derived, not set
  cfg.sketchName  = SKETCH_NAME;
  cfg.sketchMajor = SKETCH_VERSION_MAJOR;
  cfg.sketchMinor = SKETCH_VERSION_MINOR;
  cfg.sketchPatch = SKETCH_VERSION_PATCH;
  cfg.projectKey  = PROJECT_KEY;
  cfg.capabilities = CAPS; cfg.capabilityCount = sizeof(CAPS) / sizeof(CAPS[0]);
  cfg.otaPassword = OTA_PASSWORD;
  // Stimulator: listens for punishment AND reward in the slave's channel.
  cfg.punishListener = true;
  cfg.punishKinds = PUNISH_KINDS; cfg.punishKindCount = 1;
  cfg.rewardListener = true;
  cfg.rewardKinds = REWARD_KINDS; cfg.rewardKindCount = 1;
  // Couples the output to the performance -> needs the reading channel.
  cfg.liveListener = true;
  // Waveforms are larger than a state packet: room for one block of 50
  // support points plus envelope.
  cfg.mqttBufferSize = 2048;

  dev.begin(cfg, handler);
  handler.begin();
}

void loop() {
  dev.loop();
}
