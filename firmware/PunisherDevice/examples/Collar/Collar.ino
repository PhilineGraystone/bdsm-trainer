// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  Collar — collar control device on the PunisherDevice base
//
//  Hardware (confirmed Philine 2026-09-06): ESP32-WROVER-B (PSRAM, 4 MB flash),
//  SSD1306 OLED 128x64 (I2C 0x3c), MPU6050 (I2C 0x68), 433 MHz transmitter on
//  GPIO 27, which drives an off-the-shelf training collar
//  (protocol TxCmdSequence from the V1 prototype, adopted unchanged).
//
//  Operating model (decision Philine 2026-09-06):
//    The modes are FIXED, AUTONOMOUS modes. In a mode the collar decides for
//    itself and punishes locally — the central unit only switches the mode on
//    and off and receives events. In the program a pre-warning signal (beep +
//    vibration) before every punishment can be switched on or off (warn).
//
//      idle/remote (0) : no mode; only single commands (shock/vibe/beep)
//      cage        (1) : V-Cage. ALWAYS warns first. RSSI threshold
//                        configurable. Punishes for at most cage_pun_max_s
//                        (default 600 s = 10 min) and then stops.
//      random      (2) : pulse at random intervals (min_s..max_s)
//      sleep       (3) : sleep deprivation — no motion -> punishment
//      pet         (4) : stay on all fours — standing up -> pulse
//      timer       (5) : pulse every interval_s
//      statue      (6) : hold the pose — do not leave the learned pose
//
//    pet/sleep/random/timer run until they are switched, limited by the
//    maximum duration stored in the collar (mode_max_min, default 60 min).
//
//  Envelope (doc 03 C): zap_max, vibe_max, beep_max, tx_max_ms, pulse_gap_ms,
//  mode_max_min, cage_pun_max, warn_def. Anything beyond that is
//  rejected/clamped. The #defines below are the absolute ceiling; the setup
//  portal can only LOWER them for THIS collar, never raise them (doc 23).
//  One exception: pulse_gap_ms, the minimum gap between two pulses — there
//  longer is the safer one, so the #define is the floor and the portal can
//  only extend the gap.
//
//  Event classes (base 3.1, doc 14): shock -> cls punish (with cid, when from
//  the punishment channel), warn -> warn, mode_end -> result with metrics
//  (duration_s, punish, warn, violations, out_s). Punishment channel: the
//  collar listens as a stimulus device (kinds shock, vibe, beep) on
//  punisher/slaves/<id>/punish; strength level 1..3 -> ENV_PUN_LVL1..3 (default
//  10/20/30, clamped to zap_max). Reward channel: vibe/beep as a reward.
//
//  Safety: safeState() = mode off, no pulse pending, transmitter LOW.
//  The collar itself only sends while the transmitter radiates — no pulse
//  without active radiating, which is why "not sending" is the safe state.
//  The base handles WiFi/MQTT/LWT/heartbeat/watchdog/EMERGENCY/OTA/cmd/config.
// =====================================================================
#include <Wire.h>
#include <math.h>
#include <Preferences.h>
#include "SSD1306Wire.h"
#include "PunisherDevice.h"
#include "creds.h"

// A build with placeholder credentials must not happen (see PunisherCreds.h).
// If this line fails to compile, `creds.h` still holds the CHANGEME values
// from the repository — fill them in, then build again.
#include <PunisherCreds.h>
PUN_REQUIRE_REAL_CREDS();

#include "version.h"
#include "images.h"
#include "own_font.h"

// --- Hardware ---------------------------------------------------------
#define TX_PIN          27
#define IMU_ADDR        0x68
#define OLED_ADDR       0x3c
#define COLLAR_CHANNEL  1          // channel of the training collar (1..3)

// --- Envelope: fixed limits (compiled in, doc 03 C) -----------------------
// Envelope. The #define values are the UPPER LIMIT, which cannot be raised;
// via the setup portal every collar can be LOWERED individually
// (zap_max=25 on one, 40 on the other). Decision Philine
// 2026-09-11 — before that the same compiled-in value applied to all devices.
#define ENV_ZAP_MAX         40     // 0..99 scale of the collar
#define ENV_VIBE_MAX        99
#define ENV_BEEP_MAX        99
#define ENV_TX_MAX_MS       1000   // longest send duration of one pulse
#define ENV_PULSE_GAP_MS    3000   // minimum gap between two pulses (any source)
#define ENV_MODE_MAX_MIN    60     // longest run time of one mode
#define ENV_CAGE_PUN_MAX_S 600    // V-Cage: punish for at most this long
#define ENV_WARN_DEFAULT    1      // pre-warning on when the program says nothing
#define ENV_PUN_LVL1        10     // punishment channel: zap per strength level 1..3
#define ENV_PUN_LVL2        20
#define ENV_PUN_LVL3        30

// --- Operating values (defaults from V1; changeable via collar_settings) -
#define DEF_ZAP    10
#define DEF_VIBE   25
#define DEF_BEEP   20
#define DEF_TX_MS  250

#define WARN_MS         300        // duration of the warning signal (vibe + beep, no zap)
#define WARN_LEAD_MS    1500       // gap from warning -> pulse without countdown
#define OVERLAY_MS      1000       // display "Shock"/"Warning"
#define SETTINGS_MS     5000       // display of the new settings (as in V1)
#define SHOW_SETTINGS   1          // 0 = display as in the first Collar-3.0 version (icon only), for the A/B test

// --- 433 MHz protocol (V1, unchanged) ------------------------------------
static const char  TX_ID[]     = "0010101011000011";
static const int   IntervalLow = 720;
static const int   StartHigh   = 1400;
static const int   StartLow    = 440;
static const int   OneHigh     = 662;
static const int   OneLow      = 440;
static const int   ZeroHigh    = 316;
static const int   ZeroLow     = 380;

SSD1306Wire     display(OLED_ADDR, SDA, SCL);
PunisherDevice  dev;
const char* CAPS[] = { "shock", "vibe", "beep", "collar",
                       "mode_pet", "mode_v_cage", "mode_sleep_dep", "mode_remote",
                       "mode_random", "mode_timer", "mode_statue" };
const char* PUNISH_KINDS[] = { "shock", "vibe", "beep" };   // punishment channel
const char* REWARD_KINDS[] = { "vibe", "beep" };            // reward channel

// =====================================================================
//  433 MHz transmitter
// =====================================================================
// Builds the 47-bit telegram like V1 (TxID + channel + zap + vibe + beep + checksum + '0').
static void buildFrame(int chan, int z, int v, int b, char* seq) {
  const char* collarNo = "00";
  char cs[8] = "0000000";
  switch (chan) {
    case 1: collarNo = "10"; strcpy(cs, "1000000"); break;
    case 2: collarNo = "11"; strcpy(cs, "1100000"); break;
    case 3: collarNo = "01"; strcpy(cs, "0100000"); break;
  }
  char zb[8] = "0000000", vb[8] = "0000000", bb[8] = "0000000";
  for (int i = 0; i <= 6; i++) { zb[i] = bitRead(z, i) + 48; cs[i] = (cs[i] ^ zb[i]) + 48; }
  for (int i = 0; i <= 6; i++) { vb[i] = bitRead(v, i) + 48; cs[i] = (cs[i] ^ vb[i]) + 48; }
  for (int i = 0; i <= 6; i++) { bb[i] = bitRead(b, i) + 48; cs[i] = (cs[i] ^ bb[i]) + 48; }
  snprintf(seq, 48, "%s%s%s%s%s%s0", TX_ID, collarNo, zb, vb, bb, cs);
}

// Sends the telegram continuously for `ms` milliseconds (blocking, like V1;
// the receiving collar needs one continuous burst). The duration is clamped
// by the envelope tx_max_ms before this function is called.
static void txBurst(int z, int v, int b, unsigned long ms) {
  char seq[48];
  buildFrame(COLLAR_CHANNEL, z, v, b, seq);
  unsigned long start = millis();
  while (millis() - start < ms) {
    digitalWrite(TX_PIN, LOW);  delayMicroseconds(IntervalLow);
    digitalWrite(TX_PIN, HIGH); delayMicroseconds(StartHigh);
    digitalWrite(TX_PIN, LOW);  delayMicroseconds(StartLow);
    for (int n = 0; n < 47; n++) {
      if (seq[n] == '1') { digitalWrite(TX_PIN, HIGH); delayMicroseconds(OneHigh);  digitalWrite(TX_PIN, LOW); delayMicroseconds(OneLow); }
      else               { digitalWrite(TX_PIN, HIGH); delayMicroseconds(ZeroHigh); digitalWrite(TX_PIN, LOW); delayMicroseconds(ZeroLow); }
    }
  }
  digitalWrite(TX_PIN, LOW);
}

// =====================================================================
//  MPU6050 (raw over I2C; no library needed)
// =====================================================================
static bool imuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(IMU_ADDR); Wire.write(reg); Wire.write(val);
  return Wire.endTransmission() == 0;
}
static bool imuRead(uint8_t reg, uint8_t* buf, uint8_t n) {
  Wire.beginTransmission(IMU_ADDR); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int) IMU_ADDR, (int) n, (int) true) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}
static bool imuBegin(uint8_t& whoami) {
  if (!imuWrite(0x6B, 0x80)) return false;       // Reset
  delay(100);
  imuWrite(0x6B, 0x01);                          // clock: PLL gyro X (as in V1)
  imuWrite(0x19, 0x07);                          // sample rate divider
  imuWrite(0x1A, 0x03);                          // DLPF ~44 Hz (smooth the noise)
  imuWrite(0x1B, 0x00);                          // gyro ±250 °/s
  imuWrite(0x1C, 0x00);                          // accel ±2 g
  if (!imuRead(0x75, &whoami, 1)) return false;
  // 0x68 = MPU6050; 0x70/0x71/0x73 = MPU6500/9250/9255 (same registers)
  return whoami == 0x68 || whoami == 0x70 || whoami == 0x71 || whoami == 0x73;
}
// Returns acceleration in g and angular rate in °/s.
static bool imuSample(float& ax, float& ay, float& az, float& gx, float& gy, float& gz) {
  uint8_t d[14];
  if (!imuRead(0x3B, d, 14)) return false;
  ax = (int16_t)((d[0] << 8) | d[1]) / 16384.0f;
  ay = (int16_t)((d[2] << 8) | d[3]) / 16384.0f;
  az = (int16_t)((d[4] << 8) | d[5]) / 16384.0f;
  gx = (int16_t)((d[8] << 8) | d[9])  / 131.0f;
  gy = (int16_t)((d[10] << 8) | d[11]) / 131.0f;
  gz = (int16_t)((d[12] << 8) | d[13]) / 131.0f;
  return true;
}

// =====================================================================
class CollarHandler : public PunisherHandler {
 public:
  enum Mode : uint8_t { M_IDLE = 0, M_CAGE = 1, M_RANDOM = 2, M_SLEEP = 3, M_PET = 4, M_TIMER = 5, M_STATUE = 6 };
  static const uint8_t M_LAST = M_STATUE;
  static const char* modeName(uint8_t m) {
    static const char* n[] = { "idle", "cage", "random", "sleep", "pet", "timer", "statue" };
    return m <= M_LAST ? n[m] : "?";
  }

  // ------------------------------------------------------------------
  void setup() {
    pinMode(TX_PIN, OUTPUT); digitalWrite(TX_PIN, LOW);

    Wire.begin();
    Wire.setClock(400000UL);
    display.init();
    display.flipScreenVertically();
    display.clear();
    display.setFont(ArialMT_Plain_10);
    display.drawString(2, 20, "Collar boot ...");
    display.display();

    _imuOk = imuBegin(_whoami);
    if (!_imuOk) Serial.println("IMU nicht gefunden - pet/sleep nicht verfügbar");
  }

  // Call after dev.begin() (operating values from the NVS, clamped to the fixed envelope).
  // Envelope of this one collar: the NVS lowers, the #define caps.
  void loadEnvelope() {
    _envZap   = (uint8_t) constrain(dev.cfgInt("zap_max",   ENV_ZAP_MAX),   0L, (long) ENV_ZAP_MAX);
    _envVibe  = (uint8_t) constrain(dev.cfgInt("vibe_max",  ENV_VIBE_MAX),  0L, (long) ENV_VIBE_MAX);
    _envBeep  = (uint8_t) constrain(dev.cfgInt("beep_max",  ENV_BEEP_MAX),  0L, (long) ENV_BEEP_MAX);
    _envTxMs  = (uint16_t) constrain(dev.cfgInt("tx_max_ms", ENV_TX_MAX_MS), 50L, (long) ENV_TX_MAX_MS);
    _envMode  = (uint16_t) constrain(dev.cfgInt("mode_max_min", ENV_MODE_MAX_MIN), 1L, (long) ENV_MODE_MAX_MIN);
    // The cooldown is the one value the portal clamps the OTHER way round. For
    // every limit above, lower is safer and the #define is the ceiling. For a
    // gap between two pulses, LONGER is safer - so the #define is the floor and
    // the portal may only extend it. A portal able to shorten the cooldown
    // would be a portal able to make the collar more dangerous.
    _envGapMs = (uint32_t) constrain(dev.cfgInt("pulse_gap_ms", ENV_PULSE_GAP_MS),
                                     (long) ENV_PULSE_GAP_MS, 600000L);
  }

  // Without the IMU there is no posture — pet, statue and sleep deprivation
  // are gone (2.2.0, doc 42 point 4). The central unit narrows by this.
  void reportDegraded(JSONVar& out) override { if (!_imuOk) out[0] = "imu"; }

  // What the central unit has to know about this device in order not to offer
  // values that it clamps anyway (doc 23).
  void reportLimits(JSONVar& j) override {
    j["zap_max"]      = (int) _envZap;
    j["vibe_max"]     = (int) _envVibe;
    j["beep_max"]     = (int) _envBeep;
    j["tx_max_ms"]    = (int) _envTxMs;
    j["mode_max_min"] = (int) _envMode;
    j["cage_pun_max_s"] = (int)(ENV_CAGE_PUN_MAX_S);
    // The cooldown is not a cap on any field, so nothing is measured against
    // it. It is reported because it is what keeps a shortened pulse from being
    // made up by a rapid second one - the plant should be able to show it
    // (Philine 2026-09-11).
    j["pulse_gap_ms"] = (int) _envGapMs;
  }

  void loadSettings() {
    _prefs.begin("collar", false);
    _zap  = _prefs.getUChar("zap",  DEF_ZAP);
    _vibe = _prefs.getUChar("vibe", DEF_VIBE);
    _beep = _prefs.getUChar("beep", DEF_BEEP);
    _txMs = _prefs.getUShort("tx_ms", DEF_TX_MS);
    _petCalStored = _prefs.getBool("pet_cal", false);
    if (_petCalStored) {
      _petRefStored[0] = _prefs.getInt("pcx", 0) / 1000.0f;
      _petRefStored[1] = _prefs.getInt("pcy", 0) / 1000.0f;
      _petRefStored[2] = _prefs.getInt("pcz", 1000) / 1000.0f;
    }
    _standCalStored = _prefs.getBool("stand_cal", false);
    if (_standCalStored) {
      _standRefStored[0] = _prefs.getInt("psx", 0) / 1000.0f;
      _standRefStored[1] = _prefs.getInt("psy", 0) / 1000.0f;
      _standRefStored[2] = _prefs.getInt("psz", 1000) / 1000.0f;
    }
    _gyroBias[0] = _prefs.getInt("gbx", 0) / 100.0f;      // °/s * 100
    _gyroBias[1] = _prefs.getInt("gby", 0) / 100.0f;
    _gyroBias[2] = _prefs.getInt("gbz", 0) / 100.0f;
    clampSettings();
  }

  // --- Mandatory: immediately harmless ---------------------------------
  void safeState() override {
    if (_mode != M_IDLE) endMode("stop");
    _pulse.pending = false;
    digitalWrite(TX_PIN, LOW);
    _dirty = true;
  }
  bool isActive() override { return _mode != M_IDLE || _pulse.pending; }

  // --- Commands --------------------------------------------------------
  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    // Single pulse: {"seconds": 1, "countdown": 5, "warn": true}
    // seconds = send duration (contract with the central unit); alternatively "ms" directly.
    if (strcmp(action, "shock") == 0) {
      if (_pulse.pending) { snprintf(err, errLen, "busy"); return false; }
      long ms = args.hasOwnProperty("ms") ? (long)(int) args["ms"]
              : args.hasOwnProperty("seconds") ? (long)(int) args["seconds"] * 1000L : _txMs;
      long cd = argInt(args, "countdown", 0, 0, 600);
      long maxMs = (long) _envTxMs;
      if (ms <= 0) { snprintf(err, errLen, "duration <= 0"); return false; }
      if (ms > maxMs) { snprintf(err, errLen, "duration > tx_max_ms (%ld)", maxMs); return false; }
      if (!schedulePulse(_zap, _vibe, _beep, (uint16_t) ms, (uint16_t) cd, argWarn(args), "remote")) {
        snprintf(err, errLen, "busy"); return false;
      }
      return true;
    }
    // Vibration only / tone only: {"level": 0..99, "ms": 300}
    if (strcmp(action, "vibe") == 0 || strcmp(action, "beep") == 0) {
      if (_pulse.pending) { snprintf(err, errLen, "busy"); return false; }
      bool isVibe = action[0] == 'v';
      long lvl = argInt(args, "level", isVibe ? _vibe : _beep, 0, 99);
      lvl = min(lvl, (long)(isVibe ? _envVibe : _envBeep));
      long ms  = argInt(args, "ms", WARN_MS, 50, (long) _envTxMs);
      showOverlay(OV_WARN);
      txBurst(0, isVibe ? lvl : 0, isVibe ? 0 : lvl, ms);
      JSONVar ev; ev["level"] = (int) lvl; ev["ms"] = (int) ms; dev.publishEvent(action, ev, "info");
      return true;
    }
    // Intensities: {"shock":10,"vibe":25,"beep":20,"duration":250}
    // duration in ms (>= 50) — values below that are read as seconds (legacy stock).
    if (strcmp(action, "collar_settings") == 0) {
      if (args.hasOwnProperty("shock")) _zap  = (uint8_t) constrain((int) args["shock"], 0, 99);
      if (args.hasOwnProperty("vibe"))  _vibe = (uint8_t) constrain((int) args["vibe"],  0, 99);
      if (args.hasOwnProperty("beep"))  _beep = (uint8_t) constrain((int) args["beep"],  0, 99);
      if (args.hasOwnProperty("duration")) {
        long d = (int) args["duration"];
        if (d > 0 && d < 50) d *= 1000;
        _txMs = (uint16_t) constrain(d, 50L, 65000L);
      }
      clampSettings();
      _prefs.putUChar("zap", _zap); _prefs.putUChar("vibe", _vibe);
      _prefs.putUChar("beep", _beep); _prefs.putUShort("tx_ms", _txMs);
      dev.publishState();
#if SHOW_SETTINGS
      showOverlay(OV_SETTINGS, SETTINGS_MS);    // show the new values large for 5 s (as in V1)
#endif
      return true;
    }
    // Mode: {"mode": 4 | "pet", "warn": true, "max_min": 30, ...mode-specific}
    if (strcmp(action, "mode") == 0) {
      int m = parseMode(args);
      if (m < 0) { snprintf(err, errLen, "unknown mode"); return false; }
      // Mode 0 means EXPLICITLY switching off — something other than the
      // change to another mode. The central unit distinguishes the two:
      // on "off" the requirement "V-Cage stays on" must not bring the cage
      // back by itself when the supervisor has just switched it off by
      // hand.
      if (m == M_IDLE) { if (_mode != M_IDLE) endMode("off"); return true; }
      return startMode((uint8_t) m, args, err, errLen);
    }
    // Calibration (web assistant): average one pose over `seconds`.
    // {"pose":"pet"|"stand","seconds":2}. Result as the event pose_captured
    // {pose,x,y,z,n,still,gyro_bias}; copy in the NVS as a fallback. During the
    // measurement hold still -> the gyro zero point is determined along with it (sleep deprivation).
    if (strcmp(action, "capture_pose") == 0 || strcmp(action, "calibrate_pet") == 0) {
      if (!_imuOk) { snprintf(err, errLen, "no imu"); return false; }
      if (_mode != M_IDLE) { snprintf(err, errLen, "busy"); return false; }
      if (_cap.active) { snprintf(err, errLen, "capture running"); return false; }
      const char* pose = (const char*) args["pose"];
      _cap.stand = pose && strcmp(pose, "stand") == 0;
      long secs = argInt(args, "seconds", 2, 1, 10);
      _cap.active = true; _cap.n = 0; _cap.moved = false;
      _cap.sum[0] = _cap.sum[1] = _cap.sum[2] = 0; _cap.gsum[0] = _cap.gsum[1] = _cap.gsum[2] = 0;
      _cap.until = millis() + secs * 1000UL;
      _dirty = true;
      return true;
    }
    // Live attitude readings for the web: {"seconds": 1..120} -> event imu every 200 ms
    if (strcmp(action, "imu_stream") == 0) {
      if (!_imuOk) { snprintf(err, errLen, "no imu"); return false; }
      long secs = argInt(args, "seconds", 30, 0, 120);
      _streamUntil = secs ? millis() + secs * 1000UL : 0;
      return true;
    }
    // Diagnosis (idle only, within the envelope): {"zap":0,"vibe":30,"beep":30,"ms":250}
    if (strcmp(action, "test_tx") == 0) {
      if (_mode != M_IDLE || _pulse.pending) { snprintf(err, errLen, "busy"); return false; }
      long z = min(argInt(args, "zap", 0, 0, 99),  (long) _envZap);
      long v = min(argInt(args, "vibe", 0, 0, 99), (long) _envVibe);
      long b = min(argInt(args, "beep", 0, 0, 99), (long) _envBeep);
      long ms = argInt(args, "ms", DEF_TX_MS, 50, (long) _envTxMs);
      txBurst(z, v, b, ms);
      JSONVar ev; ev["zap"] = (int) z; ev["vibe"] = (int) v; ev["beep"] = (int) b; ev["ms"] = (int) ms;
      dev.publishEvent("test_tx", ev, "info");
      return true;
    }
    snprintf(err, errLen, "unknown action");
    return false;
  }

  void reportState(JSONVar& j) override {
    j["mode"] = modeName(_mode);
    j["mode_id"] = (int) _mode;
    j["shock"] = (int) _zap; j["vibe"] = (int) _vibe; j["beep"] = (int) _beep; j["tx_ms"] = (int) _txMs;
    j["imu"] = _imuOk;
    j["pet_cal"] = _petCalStored;
    j["stand_cal"] = _standCalStored;
    j["shocks"] = (int) _shockCount;

    // Which condition the wearer is in ON THE DEVICE, and since when. The
    // collar always knew it, but never said it (request Philine 2026-09-11).
    j["cond"] = condName(_cond);
    j["cond_prev"] = condName(_condPrev);
    j["cond_since_s"] = (int)(_condSince ? ((millis() - _condSince) / 1000UL) : 0UL);
    j["cond_changes"] = (int) _condChanges;

    // Is a pulse pending right now? When searching, the answer to "why is
    // nothing happening now?" - a pending pulse makes every further one bounce
    // off (`if (_pulse.pending) return false`).
    j["pulse"] = _pulse.pending;
    if (_pulse.pending) {
      long inMs = (long)(_pulse.fireAt - millis());
      j["pulse_in_s"] = (int)((inMs > 0 ? inMs : 0) / 1000);
      j["pulse_src"] = _pulse.source;
      j["pulse_zap"] = (int) _pulse.zap;
      j["pulse_warn"] = _pulse.warn;
    }

    // Reserve and run time, as on the bridge. A stack overflow does not report
    // itself on the ESP over the serial console one is watching.
    j["stack_free"] = (int) uxTaskGetStackHighWaterMark(NULL);
    j["heap_free"]  = (int) ESP.getFreeHeap();
    j["uptime_s"]   = (int)(millis() / 1000UL);
    if (_mode != M_IDLE) {
      j["remaining_s"] = (int) (((long)(_mc.endAt - millis())) / 1000);
      j["warn"] = _mc.warn;
      if (_mode == M_CAGE) {
        j["rssi"] = (int) _rssiEma; j["cage_out"] = _cageOut; j["cage_gaveup"] = _cageGaveUp;
        // THE DISTANCE TO THE EDGE, not only the side of it (2.2.0, doc 42
        // point 3). An RSSI on its own is no proximity — only against the
        // threshold this collar uses does "-72" mean "about to be outside".
        // So the threshold and the hysteresis travel with the value, and the
        // margin is computed here, where the same numbers decide.
        j["rssi_thr"]     = (int) _mc.rssiThr;
        j["hyst_db"]      = (int) _mc.hystDb;
        j["cage_margin_db"] = (int) (_rssiEma - _mc.rssiThr);   // > 0 inside, < 0 outside
        if (_cageOut) {
          j["cage_out_s"]   = (int) ((millis() - _cageOutSince) / 1000UL);
          j["cage_warned"]  = _cageWarned;
          // When the next pulse is due — first after warn_s, then every
          // repeat_s — or -1 when the cage has given up. What the screen shows
          // as "pulse in 7 s" is exactly what this collar is about to do.
          long nextMs;
          if (_cageGaveUp) nextMs = -1000;
          else if (millis() - _cageOutSince < _mc.warnS * 1000UL)
            nextMs = (long)(_mc.warnS * 1000UL - (millis() - _cageOutSince));
          else if (_cageLastPunish)
            nextMs = (long)(_mc.cageRepeatS * 1000UL) - (long)(millis() - _cageLastPunish);
          else nextMs = 0;
          j["cage_next_s"] = (int) (nextMs < 0 ? (_cageGaveUp ? -1 : 0) : (nextMs + 999) / 1000);
        }
      }
      if (_mode == M_PET)   { j["standing"] = _petStanding; j["angle"] = (int) _petAngle; }
      if (_mode == M_STATUE){ j["out"] = _petStanding; j["angle"] = (int) _petAngle; j["tolerance"] = (int) _mc.petDeg; }
      j["mode_punish"] = (int) _modePunish;
      j["mode_warn"] = (int) _modeWarn;
      j["mode_violations"] = (int) _modeViolations;
      // Time OUTSIDE, including the stretch that is still running - otherwise,
      // for a wearer who is currently outside, the time would stand still.
      {
        unsigned long outMs = _modeOutMs + (_modeOutSince ? (millis() - _modeOutSince) : 0UL);
        j["mode_out_s"] = (int)(outMs / 1000UL);
      }
      j["mode_since_s"] = (int)((millis() - _mc.startAt) / 1000UL);
      if (_mode == M_SLEEP) { j["still_s"] = (int) ((millis() - _lastMotion) / 1000); }
    }
  }

  void onConnected() override { _dirty = true; }
  void onRegistered(uint16_t, const char*) override { _dirty = true; }
  void onUnregistered() override { _dirty = true; }
  void onEmergency(const char*) override {
    display.clear(); display.setFont(ArialMT_Plain_10);
    display.drawString(2, 10, "!! EMERGENCY !!"); display.drawString(2, 30, "Halsband gesperrt.");
    display.drawString(2, 45, "Neustart noetig."); display.display();
  }
  void onIdentify() override {
    for (int i = 0; i < 4; i++) { display.invertDisplay(); delay(150); display.normalDisplay(); delay(150); }
    _dirty = true;
  }

  // ------------------------------------------------------------------
  void onTick(unsigned long now) override {
    if (dev.isEmergency()) return;

    dev.phase(50);
    if (_imuOk && now - _lastImu >= 20) { _lastImu = now; sampleImu(now); }
    dev.phase(51);
    if (now - _lastRssi >= 500) { _lastRssi = now; sampleRssi(); }
    dev.phase(52);

    // Mode run time limit
    if (_mode != M_IDLE && (long)(_mc.endAt - now) <= 0) endMode("max_duration");

    switch (_mode) {
      case M_PET:    tickPet(now);    break;
      case M_STATUE: tickStatue(now); break;
      case M_SLEEP:  tickSleep(now);  break;
      case M_CAGE:  tickCage(now);  break;
      case M_RANDOM:
      case M_TIMER:  tickTimer(now);  break;
      default: break;
    }

    dev.phase(53);
    tickPulse(now);
    if (_overlay != OV_NONE && (long)(_overlayUntil - now) <= 0) { _overlay = OV_NONE; _dirty = true; }
    dev.phase(54);
    if (_dirty || now - _lastDraw >= 1000) { _lastDraw = now; _dirty = false; draw(now); }
    dev.phase(55);
  }

 private:
  // Envelope of this device (the NVS lowers, the #define caps) — see loadEnvelope()
  uint8_t  _envZap  = ENV_ZAP_MAX;
  uint8_t  _envVibe = ENV_VIBE_MAX;
  uint8_t  _envBeep = ENV_BEEP_MAX;
  uint16_t _envTxMs = ENV_TX_MAX_MS;
  uint16_t _envMode = ENV_MODE_MAX_MIN;
  // The exception: here the #define is the FLOOR, not the ceiling — a longer
  // cooldown is the safer one (see loadEnvelope()).
  uint32_t _envGapMs = ENV_PULSE_GAP_MS;

  // --- Settings / envelope ---------------------------------------------
  Preferences _prefs;
  uint8_t  _zap = DEF_ZAP, _vibe = DEF_VIBE, _beep = DEF_BEEP;
  uint16_t _txMs = DEF_TX_MS;
  uint32_t _shockCount = 0;

  void clampSettings() {
    _zap  = (uint8_t) min((long) _zap,  (long) _envZap);
    _vibe = (uint8_t) min((long) _vibe, (long) _envVibe);
    _beep = (uint8_t) min((long) _beep, (long) _envBeep);
    _txMs = (uint16_t) min((long) _txMs, (long) _envTxMs);
  }
  static long argInt(JSONVar& a, const char* k, long def, long lo, long hi) {
    long v = a.hasOwnProperty(k) ? (long)(int) a[k] : def;
    return constrain(v, lo, hi);
  }
  bool argWarn(JSONVar& a) {
    if (a.hasOwnProperty("warn")) {
      // true/1 -> on, false/0 -> off (JSONVar returns a bool only for a JSON bool, an int only for a number)
      return ((bool) a["warn"]) || ((int) a["warn"]) != 0;
    }
    return (long)(ENV_WARN_DEFAULT) != 0;
  }
  static int parseMode(JSONVar& a) {
    if (!a.hasOwnProperty("mode")) return -1;
    const char* s = (const char*) a["mode"];   // NULL when it is not a string
    if (s) {
      for (int i = 0; i <= M_LAST; i++) if (strcmp(s, modeName(i)) == 0) return i;
      if (strcmp(s, "remote") == 0) return M_IDLE;
      return -1;
    }
    int m = (int) a["mode"];
    return (m >= 0 && m <= M_LAST) ? m : -1;
  }

  // --- Pulse sequence (the one place that radiates) -----------------------
  // Sequence: [warning: vibe+beep] -> countdown/lead -> pulse. Minimum gap
  // pulse_gap_ms between two pulses, independent of the source.
  struct Pulse {
    bool pending = false, warn = false, warned = false;
    uint8_t zap = 0, vibe = 0, beep = 0;
    uint16_t ms = 0, countdown = 0;
    unsigned long fireAt = 0;
    char source[12] = {0};
    unsigned long cid = 0;          // channel id (mapping in the central unit), 0 = no channel
    char reason[24] = {0};          // reason from the channel (e.g. nose_button_lost)
  } _pulse;
  unsigned long _lastShockEnd = 0;
  // Counters of the running mode (for the result event mode_end, cls result)
  // --- Condition of the wearer ON THE DEVICE, and since when ---------- //
  //
  // The collar always knew whether she is standing, whether she is outside,
  // whether she is moving - but never SINCE WHEN. When searching, that is
  // exactly the question: "she is being punished" is not information, "she has
  // been out of the pose for 0:14, it last changed 3 s ago" is one (request
  // Philine 2026-09-11: "which condition the slave is in at the device, with the
  // last change, that makes debugging easier").
  //
  // All changes run through setCond(). One place, so that no mode can forget
  // to record it - that is exactly where the display would then be silently
  // wrong, and nobody notices it.
  enum Cond : uint8_t {
    C_NONE = 0,      // no mode, or one without a condition (timer, random)
    C_OK,            // pose taken / inside the V-Cage / lying still
    C_OUT,           // pose left (pet: standing; statue: moving)
    C_OUTSIDE,       // outside the V-Cage
    C_MOVING,        // sleep deprivation: is moving
  };
  static const char* condName(Cond c) {
    switch (c) {
      case C_OK:      return "ok";
      case C_OUT:     return "out";
      case C_OUTSIDE: return "outside";
      case C_MOVING:  return "moving";
      default:        return "none";
    }
  }
  void setCond(Cond c, unsigned long now) {
    if (c == _cond) return;
    _condPrev = _cond;
    _cond = c;
    _condSince = now;
    _condChanges++;
    _dirty = true;          // a change is to be reported at once, not in 30 s
  }

  Cond          _cond = C_NONE, _condPrev = C_NONE;
  unsigned long _condSince = 0;
  uint16_t      _condChanges = 0;

  uint16_t _modePunish = 0, _modeWarn = 0, _modeViolations = 0;
  unsigned long _modeOutMs = 0, _modeOutSince = 0;

  bool schedulePulse(uint8_t zap, uint8_t vibe, uint8_t beep, uint16_t ms, uint16_t countdownS, bool warn, const char* source,
                     unsigned long cid = 0, const char* reason = nullptr) {
    if (_pulse.pending) return false;
    unsigned long now = millis();
    _pulse.zap = min((long) zap, (long) _envZap);
    _pulse.vibe = vibe; _pulse.beep = beep;
    _pulse.ms = (uint16_t) min((long) ms, (long) _envTxMs);
    _pulse.countdown = countdownS; _pulse.warn = warn; _pulse.warned = false;
    _pulse.cid = cid; strlcpy(_pulse.reason, reason ? reason : "", sizeof(_pulse.reason));
    strlcpy(_pulse.source, source, sizeof(_pulse.source));
    unsigned long fireAt = now + (countdownS ? countdownS * 1000UL : (warn ? WARN_LEAD_MS : 0));
    unsigned long gapEnd = _lastShockEnd + (unsigned long) _envGapMs;
    if (_lastShockEnd && (long)(gapEnd - fireAt) > 0) fireAt = gapEnd;
    _pulse.fireAt = fireAt; _pulse.pending = true;
    _dirty = true;
    return true;
  }
  void tickPulse(unsigned long now) {
    if (!_pulse.pending) return;
    if (_pulse.warn && !_pulse.warned) {
      _pulse.warned = true;
      showOverlay(OV_WARN);
      txBurst(0, max(_pulse.vibe, (uint8_t) 30), max(_pulse.beep, (uint8_t) 20), WARN_MS);
      if (_mode != M_IDLE && strcmp(_pulse.source, modeName(_mode)) == 0) _modeWarn++;
      JSONVar ev; ev["source"] = _pulse.source; if (_pulse.cid) ev["cid"] = (double) _pulse.cid;
      dev.publishEvent("warn", ev, "warn");
      return;
    }
    if ((long)(_pulse.fireAt - now) > 0) return;
    _pulse.pending = false;
    showOverlay(OV_SHOCK);
    txBurst(_pulse.zap, _pulse.vibe, _pulse.beep, _pulse.ms);
    _lastShockEnd = millis();
    _shockCount++;
    if (_mode != M_IDLE && strcmp(_pulse.source, modeName(_mode)) == 0) _modePunish++;
    JSONVar ev; ev["level"] = (int) _pulse.zap; ev["vibe"] = (int) _pulse.vibe; ev["beep"] = (int) _pulse.beep;
    ev["ms"] = (int) _pulse.ms; ev["source"] = _pulse.source;
    if (_pulse.cid) { ev["cid"] = (double) _pulse.cid; ev["reason"] = _pulse.reason; }
    dev.publishEvent("shock", ev, "punish");
  }

  // --- Punishment channel (base checks id/TTL/kind; here: strength level -> envelope) --
  uint8_t punishZap(uint8_t level) {
    long z = level >= 3 ? (long)(ENV_PUN_LVL3)
           : level == 2 ? (long)(ENV_PUN_LVL2) : (long)(ENV_PUN_LVL1);
    return (uint8_t) constrain(min(z, (long) _envZap), 0L, 99L);
  }
  bool onPunish(const PunisherRequest& r, char* err, size_t errLen) override {
    if (dev.isEmergency()) { snprintf(err, errLen, "emergency"); return false; }
    long maxMs = (long) _envTxMs;
    if (strcmp(r.kind, "vibe") == 0 || strcmp(r.kind, "beep") == 0) {
      // mild punishment without current: strong vibration or loud tone
      if (_pulse.pending) { snprintf(err, errLen, "busy"); return false; }
      uint8_t lvl = (uint8_t) min((long)(r.level >= 3 ? 90 : (r.level == 2 ? 60 : 30)),
                                  (long)(r.kind[0] == 'v' ? _envVibe : _envBeep));
      showOverlay(OV_WARN);
      txBurst(0, r.kind[0] == 'v' ? lvl : 0, r.kind[0] == 'v' ? 0 : lvl, (unsigned long) min(600L, maxMs));
      JSONVar ev; ev["kind"] = r.kind; ev["level"] = (int) lvl; ev["cid"] = (double) r.id; ev["reason"] = r.reason; ev["source"] = "channel";
      dev.publishEvent(r.kind, ev, "punish");
      return true;
    }
    // shock / any: pulse with zap by strength level, pre-warning by the channel argument or the default
    bool warn = r.args->hasOwnProperty("warn") ? (((bool)(*r.args)["warn"]) || ((int)(*r.args)["warn"]) != 0)
                                               : (long)(ENV_WARN_DEFAULT) != 0;
    if (!schedulePulse(punishZap(r.level), _vibe, _beep, _txMs, 0, warn, "channel", r.id, r.reason)) {
      snprintf(err, errLen, "busy"); return false;
    }
    return true;
  }
  bool onReward(const PunisherRequest& r, char* err, size_t errLen) override {
    if (dev.isEmergency()) { snprintf(err, errLen, "emergency"); return false; }
    if (_pulse.pending) { snprintf(err, errLen, "busy"); return false; }
    // Reward: gentle vibration pattern (2 short bursts) or double tone
    bool vibe = strcmp(r.kind, "beep") != 0;
    uint8_t lvl = (uint8_t) min((long)(r.level >= 3 ? 60 : (r.level == 2 ? 45 : 30)),
                                (long)(vibe ? _envVibe : _envBeep));
    for (int i = 0; i < 2; i++) { txBurst(0, vibe ? lvl : 0, vibe ? 0 : lvl, 200); delay(150); }
    JSONVar ev; ev["kind"] = vibe ? "vibe" : "beep"; ev["level"] = (int) lvl; ev["cid"] = (double) r.id; ev["reason"] = r.reason;
    dev.publishEvent("reward", ev, "reward");
    return true;
  }
  // Punishment out of a mode (operating values, warning per the mode flag)
  void punish(const char* source, bool forceWarn = false) {
    schedulePulse(_zap, _vibe, _beep, _txMs, 0, _mc.warn || forceWarn, source);
  }

  // --- Modes ----------------------------------------------------------------
  uint8_t _mode = M_IDLE;
  struct ModeCfg {
    bool warn = true;
    unsigned long startAt = 0, endAt = 0;
    // pet
    float    petDeg = 45, petHystDeg = 10; uint16_t petGraceMs = 2000, petRepeatS = 15; uint8_t petCalS = 5;
    // sleep
    float    sleepThrG = 0.05f; uint16_t stillS = 60, sleepRepeatS = 30; float gyroThr = 15.0f;
    // cage
    int      rssiThr = -75; uint8_t hystDb = 5; uint16_t warnS = 10, cageRepeatS = 15, punMaxS = ENV_CAGE_PUN_MAX_S;
    // random / timer
    uint16_t minS = 10, maxS = 340, intervalS = 60, countMax = 0;
  } _mc;

  bool startMode(uint8_t m, JSONVar& a, char* err, size_t errLen) {
    if ((m == M_PET || m == M_SLEEP || m == M_STATUE) && !_imuOk) { snprintf(err, errLen, "no imu"); return false; }
    if (_mode != M_IDLE) endMode("switched");
    _pulse.pending = false;

    long maxMinEnv = (long) _envMode;
    long maxMin = argInt(a, "max_min", maxMinEnv, 0, maxMinEnv);
    if (maxMin <= 0) maxMin = maxMinEnv;       // 0/absent = maximum of the collar
    _mc = ModeCfg();
    _mc.warn = argWarn(a);
    _mc.startAt = millis();
    _mc.endAt = _mc.startAt + (unsigned long) maxMin * 60000UL;
    _modePunish = _modeWarn = _modeViolations = 0; _modeOutMs = 0; _modeOutSince = 0;
    // A new mode starts with a fresh condition. C_OK when the mode knows a
    // condition at all - otherwise C_NONE, so that the display does not claim
    // "ok" for timer and random, where nothing is measured.
    _condPrev = _cond;
    _cond = (m == M_PET || m == M_STATUE || m == M_CAGE || m == M_SLEEP) ? C_OK : C_NONE;
    _condSince = _mc.startAt;
    _condChanges = 0;

    switch (m) {
      case M_PET: {
        _mc.petDeg     = argInt(a, "angle", 45, 15, 85);
        _mc.petGraceMs = argInt(a, "grace_ms", 2000, 500, 10000);
        _mc.petRepeatS = argInt(a, "repeat_s", 15, 5, 300);
        _mc.petCalS    = argInt(a, "cal_s", 5, 0, 30);
        _mc.petHystDeg = argInt(a, "hyst", 10, 0, 40);
        // References: 1. from the command (calibration of the slave from the DB),
        // 2. from the NVS of the collar, 3. learning after the mode start (pet pose only).
        _petTwoPose = false; _petCalUntil = 0;
        bool haveRef = readVec(a, "ref_pet", _petRef);
        bool haveStand = readVec(a, "ref_stand", _standRef);
        if (!haveRef && (a.hasOwnProperty("stored") ? ((int) a["stored"]) != 0 : true) && _petCalStored) {
          memcpy(_petRef, _petRefStored, sizeof(_petRef)); haveRef = true;
          if (!haveStand && _standCalStored) { memcpy(_standRef, _standRefStored, sizeof(_standRef)); haveStand = true; }
        }
        if (haveRef && haveStand) {
          float sep = angleBetween(_petRef, _standRef);
          if (sep < 20.0f) { snprintf(err, errLen, "calibration poses too close (%d deg)", (int) sep); return false; }
          _petTwoPose = true;
        } else if (!haveRef) {
          if (_mc.petCalS == 0) { memcpy(_petRef, _lp, sizeof(_petRef)); }             // pose now = reference
          else { _petCalUntil = millis() + _mc.petCalS * 1000UL; if (!_petCalUntil) _petCalUntil = 1;
                 _petCalN = 0; _petCalSum[0] = _petCalSum[1] = _petCalSum[2] = 0; }
        }
        _petStanding = false; _petSince = 0; _petLastPunish = 0;
        break;
      }
      case M_STATUE: {
        // Hold the pose: reference = pose learned after cal_s seconds (or the ref
        // passed in), tolerance `angle` degrees (default 20), hysteresis hyst.
        _mc.petDeg     = argInt(a, "angle", 20, 5, 60);
        _mc.petHystDeg = argInt(a, "hyst", 5, 0, 20);
        _mc.petGraceMs = argInt(a, "grace_ms", 1500, 300, 10000);
        _mc.petRepeatS = argInt(a, "repeat_s", 15, 5, 300);
        _mc.petCalS    = argInt(a, "cal_s", 3, 0, 30);
        _petTwoPose = false; _petCalUntil = 0;
        if (!readVec(a, "ref", _petRef)) {
          if (_mc.petCalS == 0) { memcpy(_petRef, _lp, sizeof(_petRef)); }
          else { _petCalUntil = millis() + _mc.petCalS * 1000UL; if (!_petCalUntil) _petCalUntil = 1;
                 _petCalN = 0; _petCalSum[0] = _petCalSum[1] = _petCalSum[2] = 0; }
        }
        _petStanding = false; _petSince = 0; _petLastPunish = 0;
        break;
      }
      case M_SLEEP:
        _mc.sleepThrG    = argInt(a, "thr_mg", 50, 10, 500) / 1000.0f;
        _mc.gyroThr      = argInt(a, "gyro_dps", 15, 3, 100);
        _mc.stillS       = argInt(a, "still_s", 60, 10, 1800);
        _mc.sleepRepeatS = argInt(a, "repeat_s", 30, 5, 600);
        _lastMotion = millis(); _sleepInactive = false; _sleepLastPunish = 0;
        break;
      case M_CAGE: {
        long punEnv = (long)(ENV_CAGE_PUN_MAX_S);
        _mc.rssiThr      = argInt(a, "rssi", -75, -95, -40);
        _mc.hystDb       = argInt(a, "hyst_db", 5, 1, 20);
        _mc.warnS        = argInt(a, "warn_s", 10, 2, 120);
        _mc.cageRepeatS = argInt(a, "repeat_s", 15, 5, 300);
        _mc.punMaxS      = argInt(a, "punish_max_s", punEnv, 10, punEnv);
        _mc.warn = true;                 // V-Cage ALWAYS warns (default Philine)
        _cageOut = false; _cageGaveUp = false; _cageOutSince = 0; _cageLastPunish = 0; _cageWarned = false;
        _rssiEma = WiFi.RSSI();
        break;
      }
      case M_RANDOM:
        _mc.minS = argInt(a, "min_s", 10, 5, 3600);
        _mc.maxS = argInt(a, "max_s", 340, _mc.minS, 3600);
        _mc.countMax = argInt(a, "count", 0, 0, 1000);
        _timerCount = 0; _nextFire = millis() + random(_mc.minS, _mc.maxS + 1) * 1000UL;
        break;
      case M_TIMER:
        _mc.intervalS = argInt(a, "interval_s", 60, 5, 3600);
        _mc.countMax  = argInt(a, "count", 0, 0, 1000);
        _timerCount = 0; _nextFire = millis() + _mc.intervalS * 1000UL;
        break;
      default: snprintf(err, errLen, "unknown mode"); return false;
    }
    _mode = m;
    _dirty = true;
    JSONVar ev; ev["mode"] = modeName(m); ev["warn"] = _mc.warn; ev["max_min"] = (int) maxMin;
    if (m == M_PET) ev["detect"] = _petTwoPose ? "two_pose" : (_petCalUntil ? "learn" : "angle");
    if (m == M_STATUE) ev["tolerance"] = (int) _mc.petDeg;
    dev.publishEvent("mode_start", ev, "info");
    dev.publishState();
    return true;
  }
  void endMode(const char* reason) {
    if (_mode == M_IDLE) return;
    unsigned long now = millis();
    if (_modeOutSince) { _modeOutMs += now - _modeOutSince; _modeOutSince = 0; }
    setCond(C_NONE, now);
    // Result of the run (cls result): from it the central unit derives grade and points.
    JSONVar ev; ev["mode"] = modeName(_mode); ev["reason"] = reason; ev["shocks"] = (int) _shockCount;
    ev["duration_s"] = (int) ((now - _mc.startAt) / 1000UL);
    ev["punish"] = (int) _modePunish; ev["warn"] = (int) _modeWarn;
    ev["violations"] = (int) _modeViolations; ev["out_s"] = (int) (_modeOutMs / 1000UL);
    ev["max_min"] = (int) ((_mc.endAt - _mc.startAt) / 60000UL);
    _mode = M_IDLE;
    _pulse.pending = false;
    _dirty = true;
    dev.publishEvent("mode_end", ev, "result");
    dev.publishState();
  }

  // --- IMU evaluation ---------------------------------------------------
  bool     _imuOk = false; uint8_t _whoami = 0;
  unsigned long _lastImu = 0;
  float    _lp[3] = {0, 0, 1};          // low-pass filtered gravity direction (g)
  float    _aMag = 1.0f, _gyroMag = 0;
  unsigned long _lastMotion = 0;

  void sampleImu(unsigned long now) {
    float ax, ay, az, gx, gy, gz;
    if (!imuSample(ax, ay, az, gx, gy, gz)) { _imuFail++; if (_imuFail > 50) { _imuOk = false; dev.logf("error", "IMU ausgefallen"); if (_mode == M_PET || _mode == M_SLEEP || _mode == M_STATUE) endMode("imu_lost"); } return; }   // review 2026-09-10: statue added
    _imuFail = 0;
    const float k = 0.1f;               // ~0.3 s time constant at 50 Hz
    _lp[0] += k * (ax - _lp[0]); _lp[1] += k * (ay - _lp[1]); _lp[2] += k * (az - _lp[2]);
    _aMag = sqrtf(ax * ax + ay * ay + az * az);
    gx -= _gyroBias[0]; gy -= _gyroBias[1]; gz -= _gyroBias[2];
    _gyroMag = sqrtf(gx * gx + gy * gy + gz * gz);
    // Motion: the magnitude deviates from 1 g, or the angular rate is above the threshold
    bool moving = fabsf(_aMag - 1.0f) > _mc.sleepThrG || _gyroMag > _mc.gyroThr;
    if (moving) _lastMotion = now;
    // Average the pet calibration
    if ((_mode == M_PET || _mode == M_STATUE) && _petCalUntil) { _petCalSum[0] += ax; _petCalSum[1] += ay; _petCalSum[2] += az; _petCalN++; }
    // Pose measurement (web assistant)
    if (_cap.active) {
      _cap.sum[0] += ax; _cap.sum[1] += ay; _cap.sum[2] += az;
      _cap.gsum[0] += gx + _gyroBias[0]; _cap.gsum[1] += gy + _gyroBias[1]; _cap.gsum[2] += gz + _gyroBias[2];  // raw readings for the new bias
      _cap.n++;
      if (moving) _cap.moved = true;
      if ((long)(_cap.until - now) <= 0) finishCapture();
    }
    // Live readings for the web
    if (_streamUntil && (long)(_streamUntil - now) > 0 && now - _lastStream >= 200) {
      _lastStream = now;
      JSONVar ev;
      ev["ax"] = roundf(_lp[0] * 1000) / 1000; ev["ay"] = roundf(_lp[1] * 1000) / 1000; ev["az"] = roundf(_lp[2] * 1000) / 1000;
      ev["gyro"] = roundf(_gyroMag * 10) / 10; ev["moving"] = moving;
      if (_petCalStored || _mode == M_PET) ev["angle_pet"] = (int) angleBetween(_lp, (_mode == M_PET) ? _petRef : _petRefStored);
      if (_standCalStored || (_mode == M_PET && _petTwoPose)) ev["angle_stand"] = (int) angleBetween(_lp, (_mode == M_PET) ? _standRef : _standRefStored);
      if (_mode == M_PET) ev["standing"] = _petStanding;
      ev["rssi"] = WiFi.RSSI();
      dev.publishEvent("imu", ev, "info");
    } else if (_streamUntil && (long)(_streamUntil - now) <= 0) {
      _streamUntil = 0;
    }
  }

  // --- Finish the pose measurement: event + NVS fallback ----------------------------
  struct Capture { bool active = false, stand = false, moved = false; unsigned long until = 0; uint32_t n = 0; float sum[3] = {0,0,0}, gsum[3] = {0,0,0}; } _cap;
  unsigned long _streamUntil = 0, _lastStream = 0;
  float _gyroBias[3] = {0, 0, 0};

  void finishCapture() {
    _cap.active = false;
    JSONVar ev; ev["pose"] = _cap.stand ? "stand" : "pet"; ev["n"] = (int) _cap.n; ev["still"] = !_cap.moved;
    if (_cap.n < 10) { ev["error"] = "too few samples"; dev.publishEvent("pose_failed", ev, "info"); return; }
    float v[3] = { _cap.sum[0] / _cap.n, _cap.sum[1] / _cap.n, _cap.sum[2] / _cap.n };
    float* dst = _cap.stand ? _standRefStored : _petRefStored;
    memcpy(dst, v, sizeof(v));
    if (_cap.stand) { _standCalStored = true; _prefs.putInt("psx", (int)(v[0]*1000)); _prefs.putInt("psy", (int)(v[1]*1000)); _prefs.putInt("psz", (int)(v[2]*1000)); _prefs.putBool("stand_cal", true); }
    else            { _petCalStored = true;   _prefs.putInt("pcx", (int)(v[0]*1000)); _prefs.putInt("pcy", (int)(v[1]*1000)); _prefs.putInt("pcz", (int)(v[2]*1000)); _prefs.putBool("pet_cal", true); }
    // Take the gyro zero point only from a still measurement
    if (!_cap.moved) {
      for (int i = 0; i < 3; i++) _gyroBias[i] = _cap.gsum[i] / _cap.n;
      _prefs.putInt("gbx", (int)(_gyroBias[0]*100)); _prefs.putInt("gby", (int)(_gyroBias[1]*100)); _prefs.putInt("gbz", (int)(_gyroBias[2]*100));
      JSONVar gb; gb[0] = roundf(_gyroBias[0]*10)/10; gb[1] = roundf(_gyroBias[1]*10)/10; gb[2] = roundf(_gyroBias[2]*10)/10; ev["gyro_bias"] = gb;
    }
    ev["x"] = roundf(v[0]*1000)/1000; ev["y"] = roundf(v[1]*1000)/1000; ev["z"] = roundf(v[2]*1000)/1000;
    if (_petCalStored && _standCalStored) ev["separation"] = (int) angleBetween(_petRefStored, _standRefStored);
    txBurst(0, 0, max(_beep, (uint8_t) 20), 150);          // short tone: measurement done
    dev.publishEvent("pose_captured", ev, "info");
    dev.publishState();
    _dirty = true;
  }

  // --- Vector helpers ------------------------------------------------------------------
  static float angleBetween(const float* a, const float* b) {
    float dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
    float n = sqrtf(a[0]*a[0] + a[1]*a[1] + a[2]*a[2]) * sqrtf(b[0]*b[0] + b[1]*b[1] + b[2]*b[2]);
    float c = n > 0 ? constrain(dot / n, -1.0f, 1.0f) : 1.0f;
    return acosf(c) * 180.0f / PI;
  }
  // Read the JSON array [x,y,z]; false when absent/invalid
  static bool readVec(JSONVar& a, const char* key, float* out) {
    if (!a.hasOwnProperty(key)) return false;
    JSONVar v = a[key];
    if (v.length() != 3) return false;
    float t[3] = { (float)(double) v[0], (float)(double) v[1], (float)(double) v[2] };
    if (sqrtf(t[0]*t[0] + t[1]*t[1] + t[2]*t[2]) < 0.3f) return false;
    memcpy(out, t, sizeof(t));
    return true;
  }
  uint8_t _imuFail = 0;

  // --- PET: pose against the reference "on all fours" -------------------
  float _petRef[3] = {0, 0, 1}, _petRefStored[3] = {0, 0, 1}, _petCalSum[3] = {0, 0, 0};
  float _standRef[3] = {0, 1, 0}, _standRefStored[3] = {0, 1, 0};
  bool  _petCalStored = false, _standCalStored = false, _petStanding = false, _petTwoPose = false;
  unsigned long _petCalUntil = 0, _petSince = 0, _petLastPunish = 0;
  uint32_t _petCalN = 0; float _petAngle = 0;

  void tickPet(unsigned long now) {
    if (_petCalUntil) {                          // learning phase: the slave takes the pose
      if ((long)(_petCalUntil - now) > 0) return;
      if (_petCalN > 10) { for (int i = 0; i < 3; i++) _petRef[i] = _petCalSum[i] / _petCalN; }
      else { memcpy(_petRef, _lp, sizeof(_petRef)); }
      _petCalUntil = 0;
      txBurst(0, 0, max(_beep, (uint8_t) 20), WARN_MS);     // "now it counts"
      JSONVar ev; ev["x"] = _petRef[0]; ev["y"] = _petRef[1]; ev["z"] = _petRef[2]; dev.publishEvent("pet_armed", ev, "info");
      _dirty = true;
      return;
    }
    // Angle to the pet reference; with two poses: closer to "standing" than to
    // "on all fours" (hysteresis hyst degrees against flutter at the boundary),
    // otherwise the fixed angle petDeg.
    _petAngle = angleBetween(_lp, _petRef);
    bool over;
    if (_petTwoPose) {
      float aStand = angleBetween(_lp, _standRef);
      over = _petStanding ? (aStand < _petAngle + _mc.petHystDeg) : (aStand + _mc.petHystDeg < _petAngle);
    } else {
      over = _petStanding ? (_petAngle > _mc.petDeg - _mc.petHystDeg) : (_petAngle > _mc.petDeg);
    }
    if (over) {
      if (!_petSince) _petSince = now;
      if (!_petStanding && now - _petSince >= _mc.petGraceMs) {
        _petStanding = true; _dirty = true; _modeViolations++; _modeOutSince = now;
        setCond(C_OUT, now);
        JSONVar ev; ev["angle"] = (int) _petAngle; dev.publishEvent("pet_violation", ev, "info");
      }
      if (_petStanding && (!_petLastPunish || now - _petLastPunish >= _mc.petRepeatS * 1000UL) && !_pulse.pending) {
        _petLastPunish = now; punish("pet");
      }
    } else {
      _petSince = 0;
      if (_petStanding) {
        _petStanding = false; _petLastPunish = 0; _dirty = true;
        setCond(C_OK, now);
        if (_modeOutSince) { _modeOutMs += now - _modeOutSince; _modeOutSince = 0; }
        dev.publishEvent("pet_ok", "info");
      }
    }
  }

  // --- STATUE: do not leave the learned pose (tolerance angle) ---------------
  void tickStatue(unsigned long now) {
    if (_petCalUntil) {                          // learning phase: take the pose
      if ((long)(_petCalUntil - now) > 0) return;
      if (_petCalN > 10) { for (int i = 0; i < 3; i++) _petRef[i] = _petCalSum[i] / _petCalN; }
      else { memcpy(_petRef, _lp, sizeof(_petRef)); }
      _petCalUntil = 0;
      txBurst(0, 0, max(_beep, (uint8_t) 20), WARN_MS);     // "now it counts"
      JSONVar ev; ev["x"] = _petRef[0]; ev["y"] = _petRef[1]; ev["z"] = _petRef[2]; ev["tolerance"] = (int) _mc.petDeg;
      dev.publishEvent("statue_armed", ev, "info");
      _dirty = true;
      return;
    }
    _petAngle = angleBetween(_lp, _petRef);
    bool over = _petStanding ? (_petAngle > _mc.petDeg - _mc.petHystDeg) : (_petAngle > _mc.petDeg);
    if (over) {
      if (!_petSince) _petSince = now;
      if (!_petStanding && now - _petSince >= _mc.petGraceMs) {
        _petStanding = true; _dirty = true; _modeViolations++; _modeOutSince = now;
        setCond(C_OUT, now);
        JSONVar ev; ev["angle"] = (int) _petAngle; dev.publishEvent("statue_violation", ev, "info");
      }
      if (_petStanding && (!_petLastPunish || now - _petLastPunish >= _mc.petRepeatS * 1000UL) && !_pulse.pending) {
        _petLastPunish = now; punish("statue");
      }
    } else {
      _petSince = 0;
      if (_petStanding) {
        _petStanding = false; _petLastPunish = 0; _dirty = true;
        setCond(C_OK, now);
        if (_modeOutSince) { _modeOutMs += now - _modeOutSince; _modeOutSince = 0; }
        dev.publishEvent("statue_ok", "info");
      }
    }
  }

  // --- SLEEP: no motion -> punishment -----------------------------------
  bool _sleepInactive = false; unsigned long _sleepLastPunish = 0;
  void tickSleep(unsigned long now) {
    bool still = now - _lastMotion >= _mc.stillS * 1000UL;
    if (still) {
      if (!_sleepInactive) { _sleepInactive = true; _dirty = true; _modeViolations++; _modeOutSince = now;
                             setCond(C_OUT, now);   // still = the violation in this mode
                             dev.publishEvent("inactive", "info"); }
      if ((!_sleepLastPunish || now - _sleepLastPunish >= _mc.sleepRepeatS * 1000UL) && !_pulse.pending) {
        _sleepLastPunish = now; punish("sleep");
      }
    } else if (_sleepInactive) {
      _sleepInactive = false; _sleepLastPunish = 0; _dirty = true;
      setCond(C_MOVING, now);
      if (_modeOutSince) { _modeOutMs += now - _modeOutSince; _modeOutSince = 0; }
      dev.publishEvent("active", "info");
    }
  }

  // --- CAGE: V-Cage -----------------------------------------------------
  float _rssiEma = -50; unsigned long _lastRssi = 0;
  bool _cageOut = false, _cageGaveUp = false, _cageWarned = false;
  unsigned long _cageOutSince = 0, _cageLastPunish = 0;
  // Live proximity (2.2.0): the state goes out every 30 s or on a change, and
  // a wearer walking towards the edge is neither. So while the cage runs the
  // state is also published when the margin moves by 3 dB, at most every 2 s
  // — that is what makes the bar on the screen move before the pulse comes,
  // which is the point of showing it at all (decision Philine 2026-09-16).
  int           _cageReportedMargin = 999;
  unsigned long _cageLastReport = 0;

  void sampleRssi() {
    // Without WiFi there is no RSSI -> count it as "far outside" (-100).
    int r = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : -100;
    if (r == 0) r = -100;
    _rssiEma += 0.25f * (r - _rssiEma);
  }
  void tickCage(unsigned long now) {
    {
      int margin = (int) (_rssiEma - _mc.rssiThr);
      // Outside, the countdown to the next pulse is what moves — so out there
      // it is every 2 s regardless of the margin.
      if (now - _cageLastReport >= 2000 && (_cageOut || abs(margin - _cageReportedMargin) >= 3)) {
        _cageReportedMargin = margin; _cageLastReport = now;
        dev.publishState();
      }
    }
    bool outNow = _cageOut ? (_rssiEma < _mc.rssiThr + _mc.hystDb) : (_rssiEma < _mc.rssiThr);
    if (outNow && !_cageOut) {
      _cageOut = true; _cageOutSince = now; _cageWarned = false; _cageLastPunish = 0; _dirty = true;
      setCond(C_OUTSIDE, now);
      JSONVar ev; ev["rssi"] = (int) _rssiEma; dev.publishEvent("cage_out", ev, "info");
    } else if (!outNow && _cageOut) {
      _cageOut = false; _cageGaveUp = false; _dirty = true;
      setCond(C_OK, now);
      JSONVar ev; ev["rssi"] = (int) _rssiEma; dev.publishEvent("cage_ok", ev, "info");
      return;
    }
    if (!_cageOut || _cageGaveUp) return;

    // 1. Always warn first, 2. after warn_s the first pulse, 3. repeat every
    // repeat_s, 4. stop after punish_max_s (cage_giveup).
    if (!_cageWarned) {
      _cageWarned = true;
      showOverlay(OV_WARN);
      txBurst(0, max(_vibe, (uint8_t) 30), max(_beep, (uint8_t) 20), WARN_MS);
      JSONVar ev; ev["source"] = "cage"; dev.publishEvent("warn", ev, "warn");
      return;
    }
    if (now - _cageOutSince >= _mc.punMaxS * 1000UL) {
      _cageGaveUp = true; _dirty = true;
      dev.publishEvent("cage_giveup", "info");
      return;
    }
    if (now - _cageOutSince < _mc.warnS * 1000UL) return;
    if ((!_cageLastPunish || now - _cageLastPunish >= _mc.cageRepeatS * 1000UL) && !_pulse.pending) {
      _cageLastPunish = now;
      punish("cage", true);          // renewed warning before every pulse
    }
  }

  // --- RANDOM / TIMER -----------------------------------------------------
  unsigned long _nextFire = 0; uint16_t _timerCount = 0;
  void tickTimer(unsigned long now) {
    if ((long)(_nextFire - now) > 0 || _pulse.pending) return;
    punish(_mode == M_RANDOM ? "random" : "timer");
    _timerCount++;
    if (_mc.countMax && _timerCount >= _mc.countMax) { endMode("count"); return; }
    _nextFire = now + (_mode == M_RANDOM ? random(_mc.minS, _mc.maxS + 1) : _mc.intervalS) * 1000UL;
  }

  // --- Display ---------------------------------------------------------------
  enum Overlay : uint8_t { OV_NONE, OV_WARN, OV_SHOCK, OV_SETTINGS };
  Overlay _overlay = OV_NONE; unsigned long _overlayUntil = 0, _lastDraw = 0;
  bool _dirty = true;
  void showOverlay(Overlay o, unsigned long ms = OVERLAY_MS) { _overlay = o; _overlayUntil = millis() + ms; _dirty = true; draw(millis()); }

  // Operating values as a text block (x = left edge)
  void drawSettings(int x, int y, int dy) {
    char b[20];
    snprintf(b, sizeof(b), "Shock: %u", _zap);  display.drawString(x, y,        b);
    snprintf(b, sizeof(b), "Vibe:  %u", _vibe); display.drawString(x, y + dy,   b);
    snprintf(b, sizeof(b), "Beep:  %u", _beep); display.drawString(x, y + 2*dy, b);
    snprintf(b, sizeof(b), "Dura:  %u", _txMs); display.drawString(x, y + 3*dy, b);
  }

  void bigNumber(long v) {
    display.setFont(Roboto_Mono_Bold_45);
    display.setTextAlignment(TEXT_ALIGN_CENTER);
    display.drawString(64, 8, String(v));
    display.setTextAlignment(TEXT_ALIGN_LEFT);
    display.setFont(ArialMT_Plain_10);
  }
  void draw(unsigned long now) {
    display.clear();
    display.setFont(ArialMT_Plain_10);
    display.setTextAlignment(TEXT_ALIGN_LEFT);
    if (_overlay == OV_SHOCK)      { display.drawXbm(32, 0, 64, 64, shocked); display.display(); return; }
    if (_overlay == OV_WARN)       { display.drawXbm(32, 0, 64, 64, warning_icon); display.display(); return; }
    if (_overlay == OV_SETTINGS)   { drawSettings(2, 0, 15); display.drawString(70, 0, "neu"); display.display(); return; }

    if (_cap.active) {                        // pose measurement: hold still
      display.drawString(2, 8, _cap.stand ? "Messung: STEHEND" : "Messung: AUF ALLEN VIEREN");
      bigNumber(((long)(_cap.until - now) + 999) / 1000);
      display.drawString(2, 54, "Ruhig halten ...");
      display.display(); return;
    }
    // Countdown of a single pulse: large number
    if (_pulse.pending && _pulse.countdown) {
      long rem = ((long)(_pulse.fireAt - now) + 999) / 1000;
      if (rem > 0) { bigNumber(rem); display.display(); return; }
    }

    char line[24];
    switch (_mode) {
      case M_IDLE:
        if (!dev.mqttConnected()) { display.drawString(2, 20, "Verbinde ..."); display.drawString(2, 40, WiFi.localIP().toString()); }
        else if (!dev.isRegistered()) { display.drawString(2, 20, "Waiting for SlaveID ..."); display.drawString(2, 40, "I will play with you ..."); }
        else {
#if SHOW_SETTINGS
          // registered: icon on the left, slave and current settings on the right (visible as in V1)
          display.drawXbm(0, 0, 64, 64, bondage);
          char nm[12]; snprintf(nm, sizeof(nm), "%.11s", dev.slaveName());
          display.drawString(68, 0, nm);
          drawSettings(68, 14, 12);
#else
          display.drawXbm(32, 0, 64, 64, bondage);
#endif
        }
        break;
      case M_PET:
        if (_petCalUntil) { bigNumber(((long)(_petCalUntil - now) + 999) / 1000); display.drawString(2, 54, "Auf alle Viere!"); }
        else { display.drawXbm(32, 0, 64, 64, pet_icon); }
        break;
      case M_STATUE:
        if (_petCalUntil) { bigNumber(((long)(_petCalUntil - now) + 999) / 1000); display.drawString(2, 54, "Haltung einnehmen!"); }
        else {
          display.setFont(ArialMT_Plain_16); display.drawString(2, 14, _petStanding ? "STATUE  !!" : "STATUE");
          display.setFont(ArialMT_Plain_10);
          snprintf(line, sizeof(line), "%d / %d Grad", (int) _petAngle, (int) _mc.petDeg); display.drawString(2, 40, line);
        }
        break;
      case M_SLEEP:
        display.drawXbm(34, 0, 60, 36, sleep_icon);
        snprintf(line, sizeof(line), "still %lus", (unsigned long)((now - _lastMotion) / 1000));
        display.drawString(2, 52, line);
        break;
      case M_CAGE:
        display.drawXbm(34, 0, 60, 36, WiFi_Logo);
        snprintf(line, sizeof(line), "RSSI %d / %d%s", (int) _rssiEma, _mc.rssiThr, _cageGaveUp ? " STOP" : (_cageOut ? " OUT" : ""));
        display.drawString(2, 52, line);
        break;
      case M_RANDOM:
      case M_TIMER: {
        long rem = ((long)(_nextFire - now) + 999) / 1000;
        if (_mode == M_TIMER && rem >= 0 && rem < 100) bigNumber(rem);
        else display.drawXbm(32, 0, 64, 64, random_icon);
        break;
      }
    }
    if (_mode != M_IDLE) {
      long remS = ((long)(_mc.endAt - now)) / 1000;
      snprintf(line, sizeof(line), "%s %ld:%02ld", modeName(_mode), remS / 60, remS % 60);
      display.setTextAlignment(TEXT_ALIGN_RIGHT);
      display.drawString(127, 0, line);
      display.setTextAlignment(TEXT_ALIGN_LEFT);
    }
    display.display();
  }
};

CollarHandler handler;

// =====================================================================
void setup() {
  Serial.begin(115200);
  randomSeed(esp_random());
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
  cfg.punishListener = true;  cfg.punishKinds = PUNISH_KINDS; cfg.punishKindCount = sizeof(PUNISH_KINDS) / sizeof(PUNISH_KINDS[0]);
  cfg.rewardListener = true;  cfg.rewardKinds = REWARD_KINDS; cfg.rewardKindCount = sizeof(REWARD_KINDS) / sizeof(REWARD_KINDS[0]);
  cfg.otaPassword = "punisher";     // OTA only in the safe state
  dev.begin(cfg, handler);          // web config portal if needed, then NVS overrides
  // Order matters: first the envelope of this device from the NVS, then the
  // operating values that are clamped to it. Both after dev.begin(), because cfgInt
  // needs the opened NVS — and before the first hello, which only goes out with
  // the MQTT connection in loop().
  handler.loadEnvelope();
  handler.loadSettings();           // load operating values, clamp to the envelope
}

void loop() {
  dev.loop();
}
