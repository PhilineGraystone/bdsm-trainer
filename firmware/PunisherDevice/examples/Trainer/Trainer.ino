// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  Trainer — ToF distance trainer on the PunisherDevice base (doc 14 §7.1)
//
//  Hardware (prototype Blowjob_Trainer.ino): ESP32, VL53L1X ToF distance sensor
//  (I2C, short mode, 50 ms), SH1106 OLED 128x64 (I2C 0x3c). In addition a
//  passive buzzer (beat, feedback) and the board LED.
//
//  The sensor measures the distance (mm) to the head. "Depth" = the way from the
//  resting distance (rest_mm, nothing in front) towards the sensor; the slave's
//  greatest depth (deep_mm) comes from her calibration (posture 'depth' in the
//  central unit, command calibrate_depth) — targets in percent refer to that
//  (the leaderboard measures obedience, not anatomy: doc 14 §6.5).
//
//  Modes (command "trainer" {mode, ...}):
//    repetition : count strokes, the target per stroke rises from depth_start to
//                 depth_end (mm from the central unit, or percent); too shallow or
//                 stroke_s exceeded = missed stroke (fault "miss"); max_miss
//                 ends it as failed. Result hits/misses/best_depth_mm.
//    endurance  : hold depth; letting go before hold_s = fault "released_early",
//                 the hold time starts over; hold_s reached = done. best_hold_s.
//    freeform   : duration_s free; count strokes, average the depth, optionally a beat
//                 (bpm, buzzer) with beat deviation; idle_s without a stroke = fault "idle".
//    off        : ends it.
//  Command "calibrate_depth" {seconds}: measure the resting distance (maximum) and the
//  greatest depth (minimum) -> event depth_captured {rest_mm, deep_mm, n}.
//
//  No stimulator: faults are fault events, the central unit punishes over
//  the channel of the slave. Result: trainer_end (cls result).
//  Envelope (compiled in for good): ENV_TRAINER_MAX_MIN (30). safeState(): mode off, buzzer off.
// =====================================================================
#include <Wire.h>
#include <VL53L1X.h>            // Pololu VL53L1X
#include "SH1106Wire.h"          // ThingPulse esp8266-oled-ssd1306
#include "PunisherDevice.h"
#include "creds.h"

// A build with placeholder credentials must not happen (see PunisherCreds.h).
// If this line fails to compile, `creds.h` still holds the CHANGEME values
// from the repository — fill them in, then build again.
#include <PunisherCreds.h>
PUN_REQUIRE_REAL_CREDS();

#include "version.h"

#define OLED_ADDR   0x3c
#define BUZZER_PIN  5
#define LED_PIN     2
#define BUZZ_CH     2

#define ENV_TRAINER_MAX_MIN 30
#define DEF_REST_MM   200        // default resting distance without calibration
#define DEF_DEEP_MM    60        // default greatest depth without calibration
#define ENTER_MM       20        // stroke begins: this much closer than rest
#define EXIT_MM        10        // stroke ends: nearly back at rest
#define SENSOR_MAX_MM 400        // beyond that: nothing in front

SH1106Wire     display(OLED_ADDR, SDA, SCL);
VL53L1X        tof;
PunisherDevice dev;
const char* CAPS[] = { "trainer_rep", "trainer_end", "trainer_free", "depth_cal" };

// =====================================================================
class TrainerHandler : public PunisherHandler {
 public:
  enum Mode : uint8_t { M_IDLE = 0, M_REP, M_END, M_FREE, M_CAL };
  static const char* modeName(uint8_t m) {
    static const char* n[] = { "idle", "repetition", "endurance", "freeform", "calibrate" };
    return m <= M_CAL ? n[m] : "?";
  }

  void setup() {
    pinMode(LED_PIN, OUTPUT); digitalWrite(LED_PIN, LOW);
    ledcSetup(BUZZ_CH, 2000, 8); ledcAttachPin(BUZZER_PIN, BUZZ_CH); ledcWrite(BUZZ_CH, 0);
    Wire.begin(); Wire.setClock(400000UL);
    display.init(); display.flipScreenVertically(); display.clear();
    display.setFont(ArialMT_Plain_10); display.drawString(2, 20, "Trainer boot ..."); display.display();
    tof.setTimeout(500);
    _tofOk = tof.init();
    if (_tofOk) { tof.setDistanceMode(VL53L1X::Short); tof.setMeasurementTimingBudget(50000); tof.startContinuous(50); }
    else Serial.println("VL53L1X nicht gefunden");
  }
  void loadEnvelope() {
    _envMaxMin = (uint16_t) constrain(dev.cfgInt("trainer_max_min", ENV_TRAINER_MAX_MIN),
                                      1L, (long)(ENV_TRAINER_MAX_MIN));
  }
  void reportLimits(JSONVar& j) override { j["trainer_max_min"] = (int) _envMaxMin; }

  // Without the ToF sensor there is no depth — nothing this trainer does
  // works (2.2.0, doc 42 point 4). Better a device that says so in its hello
  // than one that plays a waveform against a reading it does not have.
  void reportDegraded(JSONVar& out) override { if (!_tofOk) out[0] = "tof"; }

  void loadSettings() {
    _prefs.begin("trainer", false);
    _restStored = _prefs.getUShort("rest_mm", DEF_REST_MM);
    _deepStored = _prefs.getUShort("deep_mm", DEF_DEEP_MM);
  }

  void safeState() override { if (_mode != M_IDLE) endMode("stop", false); buzz(0); digitalWrite(LED_PIN, LOW); _dirty = true; }
  bool isActive() override { return _mode != M_IDLE; }

  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    if (strcmp(action, "trainer") == 0) {
      if (!_tofOk) { snprintf(err, errLen, "no sensor"); return false; }
      const char* m = (const char*) args["mode"];
      if (!m) { snprintf(err, errLen, "mode missing"); return false; }
      if (strcmp(m, "off") == 0) { if (_mode != M_IDLE) endMode("switched", false); return true; }
      if (_mode != M_IDLE) endMode("switched", false);
      // references: from the command (calibration of the slave), otherwise NVS/default
      _rest = (uint16_t) argInt(args, "rest_mm", _restStored, 60, SENSOR_MAX_MM);
      _deep = (uint16_t) argInt(args, "deep_mm", _deepStored, 10, _rest - 10);
      if (strcmp(m, "repetition") == 0) return startRep(args, err, errLen);
      if (strcmp(m, "endurance") == 0)  return startEnd(args, err, errLen);
      if (strcmp(m, "freeform") == 0)   return startFree(args, err, errLen);
      snprintf(err, errLen, "unknown mode"); return false;
    }
    if (strcmp(action, "calibrate_depth") == 0) {
      if (!_tofOk) { snprintf(err, errLen, "no sensor"); return false; }
      if (_mode != M_IDLE) { snprintf(err, errLen, "busy"); return false; }
      long secs = argInt(args, "seconds", 15, 3, 120);
      _mode = M_CAL; _startAt = millis(); _endAt = _startAt + secs * 1000UL;
      _calMin = SENSOR_MAX_MM; _calMax = 0; _calN = 0;
      _dirty = true; dev.publishState();
      return true;
    }
    snprintf(err, errLen, "unknown action");
    return false;
  }

  void reportState(JSONVar& j) override {
    j["trainer"] = modeName(_mode);
    j["dist_mm"] = (int) _dist;
    j["depth_pct"] = (int) pct(_dist);
    j["rest_mm"] = (int) _rest; j["deep_mm"] = (int) _deep;
    j["sensor"] = _tofOk;
    if (_mode != M_IDLE) {
      j["remaining_s"] = (int) (((long)(_endAt - millis())) / 1000);
      j["hits"] = (int) _hits; j["misses"] = (int) _misses; j["faults"] = (int) _faults;
      if (_mode == M_REP) j["target_mm"] = (int) repTarget(_hits + _misses);
      if (_mode == M_END) j["hold_s"] = (int) (_holding ? (millis() - _holdSince) / 1000UL : 0);
    }
  }
  void onConnected() override { _dirty = true; }
  void onRegistered(uint16_t, const char*) override { _dirty = true; }
  void onUnregistered() override { _dirty = true; }
  void onEmergency(const char*) override {
    display.clear(); display.setFont(ArialMT_Plain_10);
    display.drawString(2, 10, "!! EMERGENCY !!"); display.drawString(2, 30, "Trainer gesperrt."); display.drawString(2, 45, "Neustart noetig."); display.display();
  }
  void onIdentify() override { for (int i = 0; i < 4; i++) { display.invertDisplay(); delay(150); display.normalDisplay(); delay(150); } _dirty = true; }

  void onTick(unsigned long now) override {
    if (dev.isEmergency()) return;
    if (_tofOk && tof.dataReady()) sample(now);
    if (_buzzUntil && (long)(_buzzUntil - now) <= 0) { _buzzUntil = 0; buzz(0); }
    if (_mode != M_IDLE && _mode != M_CAL && (long)(_endAt - now) <= 0) {
      endMode(_mode == M_FREE ? "max_duration" : "timeout", _mode == M_END);
    }
    switch (_mode) {
      case M_REP:  tickRep(now); break;
      case M_END:  tickEnd(now); break;
      case M_FREE: tickFree(now); break;
      case M_CAL:  if ((long)(_endAt - now) <= 0) finishCal(); break;
      default: break;
    }
    if (_dirty || now - _lastDraw >= 250) { _lastDraw = now; _dirty = false; draw(now); }
  }

 private:
  uint16_t _envMaxMin = ENV_TRAINER_MAX_MIN;         // envelope, can be lowered via NVS

  Preferences _prefs;
  bool _tofOk = false, _dirty = true;
  uint8_t _mode = M_IDLE;
  uint16_t _dist = SENSOR_MAX_MM, _rest = DEF_REST_MM, _deep = DEF_DEEP_MM, _restStored = DEF_REST_MM, _deepStored = DEF_DEEP_MM;
  unsigned long _startAt = 0, _endAt = 0, _lastDraw = 0, _buzzUntil = 0, _lastSample = 0;
  uint16_t _hits = 0, _misses = 0, _faults = 0, _warns = 0;
  // stroke detection
  bool _in = false; uint16_t _strokeMin = SENSOR_MAX_MM; unsigned long _strokeStart = 0, _lastStrokeEnd = 0; uint16_t _bestDepth = SENSOR_MAX_MM;
  // calibration
  uint16_t _calMin = SENSOR_MAX_MM, _calMax = 0; uint32_t _calN = 0;

  static long argInt(JSONVar& a, const char* k, long def, long lo, long hi) {
    long v = a.hasOwnProperty(k) ? (long)(int) a[k] : def;
    return constrain(v, lo, hi);
  }
  void buzz(int freq) { if (freq <= 0) ledcWrite(BUZZ_CH, 0); else { ledcWriteTone(BUZZ_CH, freq); ledcWrite(BUZZ_CH, 128); } }
  void beep(int freq, unsigned long ms) { buzz(freq); _buzzUntil = millis() + ms; }
  void ev(const char* name, JSONVar& j, const char* cls) { dev.publishEvent(name, j, cls); }
  void fault(const char* reason, JSONVar& j) { _faults++; j["reason"] = reason; ev("fault", j, "fault"); beep(300, 400); }
  // depth in percent of the calibrated greatest depth (0 = rest, 100 = deep_mm)
  float pct(uint16_t d) {
    if (_rest <= _deep) return 0;
    float p = (float)(_rest - d) * 100.0f / (float)(_rest - _deep);
    return constrain(p, 0.0f, 150.0f);
  }
  uint16_t mmFromPct(long p) { return (uint16_t) constrain((long) _rest - (long)(_rest - _deep) * p / 100L, 10L, (long) _rest); }

  void sample(unsigned long now) {
    uint16_t d = tof.read(false);
    if (tof.timeoutOccurred() || d == 0 || d > SENSOR_MAX_MM) d = SENSOR_MAX_MM;
    _dist = (uint16_t) (0.6f * _dist + 0.4f * d);        // light smoothing
    _lastSample = now;
    if (_mode == M_CAL) {
      if (_dist < _calMin) _calMin = _dist;
      if (_dist > _calMax && _dist < SENSOR_MAX_MM) _calMax = _dist;
      _calN++;
      return;
    }
    // stroke detection (all modes): in below rest-ENTER, out above rest-EXIT
    if (!_in && _dist < _rest - ENTER_MM) { _in = true; _strokeMin = _dist; _strokeStart = now; }
    else if (_in) {
      if (_dist < _strokeMin) _strokeMin = _dist;
      if (_dist > _rest - EXIT_MM) { _in = false; _lastStrokeEnd = now; onStroke(_strokeMin, now); }
    }
  }

  long beginMode(uint8_t m, long maxS) {
    long capS = (long)(ENV_TRAINER_MAX_MIN) * 60L;
    if (maxS > capS) maxS = capS;
    _mode = m; _startAt = millis(); _endAt = _startAt + (unsigned long) maxS * 1000UL;
    _hits = _misses = _faults = _warns = 0; _bestDepth = SENSOR_MAX_MM; _in = false; _lastStrokeEnd = _startAt;
    _dirty = true;
    return maxS;
  }
  void endMode(const char* reason, bool failed) {
    if (_mode == M_IDLE) return;
    uint8_t m = _mode; _mode = M_IDLE; buzz(0); _dirty = true;
    if (m == M_CAL) { dev.publishState(); return; }
    JSONVar j; j["mode"] = modeName(m); j["reason"] = reason; j["failed"] = failed;
    j["duration_s"] = (int) ((millis() - _startAt) / 1000UL);
    j["hits"] = (int) _hits; j["misses"] = (int) _misses; j["faults"] = (int) _faults; j["warn"] = (int) _warns;
    if (_bestDepth < SENSOR_MAX_MM) { j["best_depth_mm"] = (int) _bestDepth; j["best_depth_pct"] = (int) pct(_bestDepth); }
    if (m == M_END) { j["best_hold_s"] = (int) (_bestHoldMs / 1000UL); j["attempts"] = (int) _attempts; j["hold_s"] = (int) _holdS; }
    if (m == M_FREE) {
      j["strokes"] = (int) _strokes;
      if (_strokes) j["mean_depth_pct"] = (int) (_depthSum / _strokes);
      if (_bpm && _tempoN) j["tempo_dev_pct"] = (int) (_tempoDevSum / _tempoN);
    }
    ev("trainer_end", j, "result");
    dev.publishState();
  }

  // ---------------------------------------------------------------- REPETITION
  uint16_t _count = 0, _startMm = 0, _endMm = 0, _strokeS = 8, _maxMiss = 0;
  bool startRep(JSONVar& a, char* err, size_t errLen) {
    _count   = (uint16_t) argInt(a, "count", 10, 1, 500);
    _strokeS = (uint16_t) argInt(a, "stroke_s", 8, 2, 120);
    _maxMiss = (uint16_t) argInt(a, "max_miss", 0, 0, 500);
    long ps = argInt(a, "depth_start_pct", 40, 5, 150), pe = argInt(a, "depth_end_pct", 90, 5, 150);
    _startMm = a.hasOwnProperty("depth_start_mm") ? (uint16_t) argInt(a, "depth_start_mm", mmFromPct(ps), 10, _rest) : mmFromPct(ps);
    _endMm   = a.hasOwnProperty("depth_end_mm")   ? (uint16_t) argInt(a, "depth_end_mm", mmFromPct(pe), 10, _rest)   : mmFromPct(pe);
    long maxS = beginMode(M_REP, (long) _count * _strokeS + 15);
    JSONVar j; j["mode"] = "repetition"; j["count"] = (int) _count; j["start_mm"] = (int) _startMm; j["end_mm"] = (int) _endMm; j["max_s"] = (int) maxS;
    ev("trainer_start", j, "info"); dev.publishState();
    return true;
  }
  uint16_t repTarget(uint16_t n) {        // target of the n-th stroke (0-based), linear from start to end
    if (_count <= 1) return _endMm;
    long t = (long) _startMm + ((long) _endMm - (long) _startMm) * (long) n / (long)(_count - 1);
    return (uint16_t) constrain(t, 10L, (long) _rest);
  }
  void tickRep(unsigned long now) {
    // time window per stroke exceeded -> missed stroke without a stroke
    if (!_in && now - _lastStrokeEnd > _strokeS * 1000UL) {
      _lastStrokeEnd = now; _misses++;
      JSONVar j; j["n"] = (int) (_hits + _misses); j["target_mm"] = (int) repTarget(_hits + _misses - 1); fault("miss", j);
      checkRepEnd();
    }
  }
  void checkRepEnd() {
    if (_maxMiss && _misses >= _maxMiss) { endMode("max_miss", true); return; }
    if (_hits + _misses >= _count) endMode("done", false);
  }

  // ---------------------------------------------------------------- ENDURANCE
  uint16_t _depthMm = 0, _holdS = 30, _tolMm = 15, _attempts = 0; bool _holding = false; unsigned long _holdSince = 0, _bestHoldMs = 0;
  bool startEnd(JSONVar& a, char* err, size_t errLen) {
    _holdS   = (uint16_t) argInt(a, "hold_s", 30, 3, 3600);
    _tolMm   = (uint16_t) argInt(a, "tol_mm", 15, 3, 60);
    long pd  = argInt(a, "depth_pct", 70, 5, 150);
    _depthMm = a.hasOwnProperty("depth_mm") ? (uint16_t) argInt(a, "depth_mm", mmFromPct(pd), 10, _rest) : mmFromPct(pd);
    _holding = false; _attempts = 0; _bestHoldMs = 0;
    long maxS = beginMode(M_END, argInt(a, "max_s", 300, 30, 7200));
    JSONVar j; j["mode"] = "endurance"; j["depth_mm"] = (int) _depthMm; j["hold_s"] = (int) _holdS; j["max_s"] = (int) maxS;
    ev("trainer_start", j, "info"); dev.publishState();
    return true;
  }
  void tickEnd(unsigned long now) {
    bool deep = _dist <= _depthMm + _tolMm;
    if (deep && !_holding) { _holding = true; _holdSince = now; _attempts++; beep(900, 80); JSONVar j; j["attempt"] = (int) _attempts; ev("hold", j, "info"); }
    if (_holding) {
      unsigned long held = now - _holdSince;
      if (held > _bestHoldMs) _bestHoldMs = held;
      if (held >= _holdS * 1000UL) { _hits = 1; beep(1500, 400); endMode("done", false); return; }
      if (_dist > _depthMm + _tolMm + 10) {              // let go (hysteresis)
        _holding = false; _misses++;
        JSONVar j; j["held_s"] = (int) (held / 1000UL); j["attempt"] = (int) _attempts; fault("released_early", j);
      }
    }
  }

  // ---------------------------------------------------------------- FREEFORM
  uint16_t _bpm = 0, _idleS = 30, _strokes = 0, _tempoN = 0; unsigned long _nextBeat = 0, _depthSum = 0, _tempoDevSum = 0, _lastIdleFault = 0;
  bool startFree(JSONVar& a, char* err, size_t errLen) {
    _bpm   = (uint16_t) argInt(a, "bpm", 0, 0, 240);
    _idleS = (uint16_t) argInt(a, "idle_s", 30, 5, 600);
    _strokes = 0; _tempoN = 0; _depthSum = 0; _tempoDevSum = 0; _lastIdleFault = 0;
    long maxS = beginMode(M_FREE, argInt(a, "duration_s", 300, 30, 7200));
    _nextBeat = _bpm ? millis() + 60000UL / _bpm : 0;
    JSONVar j; j["mode"] = "freeform"; j["duration_s"] = (int) maxS; j["bpm"] = (int) _bpm;
    ev("trainer_start", j, "info"); dev.publishState();
    return true;
  }
  void tickFree(unsigned long now) {
    if (_bpm && (long)(_nextBeat - now) <= 0) { _nextBeat += 60000UL / _bpm; beep(1800, 40); digitalWrite(LED_PIN, HIGH); }
    if (_bpm && ((long)(_nextBeat - now) < (long)(60000UL / _bpm) - 80)) digitalWrite(LED_PIN, LOW);
    if (!_in && now - _lastStrokeEnd > _idleS * 1000UL && now - _lastIdleFault > _idleS * 1000UL) {
      _lastIdleFault = now; JSONVar j; j["idle_s"] = (int) ((now - _lastStrokeEnd) / 1000UL); fault("idle", j);
    }
  }

  // ---------------------------------------------------------------- stroke evaluated
  void onStroke(uint16_t minMm, unsigned long now) {
    if (minMm < _bestDepth) _bestDepth = minMm;
    JSONVar j; j["depth_mm"] = (int) minMm; j["depth_pct"] = (int) pct(minMm);
    if (_mode == M_REP) {
      uint16_t n = _hits + _misses;
      uint16_t target = repTarget(n);
      j["n"] = (int) (n + 1); j["target_mm"] = (int) target;
      if (minMm <= target) { _hits++; j["hit"] = true; ev("stroke", j, "info"); beep(1200, 80); }
      else { _misses++; j["hit"] = false; ev("stroke", j, "info"); fault("miss", j); }
      checkRepEnd();
    } else if (_mode == M_FREE) {
      _strokes++; _depthSum += (unsigned long) pct(minMm);
      if (_bpm && _strokes > 1) {
        long interval = (long)(now - _prevStroke); long beat = 60000L / _bpm;
        _tempoDevSum += (unsigned long) (labs(interval - beat) * 100L / beat); _tempoN++;
      }
      _prevStroke = now;
      j["n"] = (int) _strokes; ev("stroke", j, "info");
    }
  }
  unsigned long _prevStroke = 0;

  // ---------------------------------------------------------------- calibration
  void finishCal() {
    _mode = M_IDLE; _dirty = true;
    JSONVar j; j["n"] = (int) _calN;
    if (_calN < 20 || _calMax == 0 || _calMin >= _calMax - 20) { j["error"] = "too few samples or no depth"; ev("depth_failed", j, "info"); return; }
    _restStored = _calMax; _deepStored = _calMin;
    _prefs.putUShort("rest_mm", _restStored); _prefs.putUShort("deep_mm", _deepStored);
    _rest = _restStored; _deep = _deepStored;
    j["rest_mm"] = (int) _calMax; j["deep_mm"] = (int) _calMin;
    beep(1200, 200);
    ev("depth_captured", j, "info");
    dev.publishState();
  }

  // ---------------------------------------------------------------- display
  void bar(int y, float p, const char* label) {
    display.drawString(2, y, label);
    display.drawRect(2, y + 12, 124, 10);
    int w = (int) constrain(p, 0.0f, 100.0f) * 122 / 100;
    display.fillRect(3, y + 13, w, 8);
  }
  void draw(unsigned long now) {
    display.clear(); display.setFont(ArialMT_Plain_10); display.setTextAlignment(TEXT_ALIGN_LEFT);
    char line[28];
    switch (_mode) {
      case M_IDLE:
        if (!dev.mqttConnected()) { display.drawString(2, 20, "Verbinde ..."); }
        else if (!dev.isRegistered()) { display.drawString(2, 20, "Waiting for SlaveID ..."); }
        else { char nm[14]; snprintf(nm, sizeof(nm), "%.13s", dev.slaveName()); display.drawString(2, 2, nm); }
        snprintf(line, sizeof(line), "%d mm  (%d%%)", (int) _dist, (int) pct(_dist)); display.drawString(2, 50, line);
        if (_tofOk) bar(22, pct(_dist), "Tiefe");
        else display.drawString(2, 30, "Sensor fehlt!");
        break;
      case M_CAL: {
        display.drawString(2, 2, "KALIBRIERUNG: so tief wie moeglich");
        long rem = ((long)(_endAt - now) + 999) / 1000;
        snprintf(line, sizeof(line), "%ld s  min %d  max %d", rem, (int) _calMin, (int) _calMax); display.drawString(2, 50, line);
        bar(22, pct(_dist), "Tiefe");
        break; }
      case M_REP: {
        uint16_t n = _hits + _misses; uint16_t target = repTarget(n);
        snprintf(line, sizeof(line), "Stoss %d/%d  Ziel %d%%", n + 1, _count, (int) pct(target)); display.drawString(2, 2, line);
        bar(16, pct(_dist), "");
        display.drawVerticalLine(3 + (int) constrain(pct(target), 0.0f, 100.0f) * 122 / 100, 26, 12);   // target marker
        snprintf(line, sizeof(line), "Treffer %d  Fehl %d", _hits, _misses); display.drawString(2, 42, line);
        snprintf(line, sizeof(line), "Zeit %lds", (long) _strokeS - (long)((now - _lastStrokeEnd) / 1000UL)); display.drawString(2, 53, line);
        break; }
      case M_END: {
        unsigned long held = _holding ? (now - _holdSince) / 1000UL : 0;
        snprintf(line, sizeof(line), "HALTEN %lu/%d s", held, _holdS); display.drawString(2, 2, line);
        bar(16, pct(_dist), "");
        display.drawVerticalLine(3 + (int) constrain(pct(_depthMm), 0.0f, 100.0f) * 122 / 100, 26, 12);
        snprintf(line, sizeof(line), "Versuch %d  best %lus", _attempts, _bestHoldMs / 1000UL); display.drawString(2, 42, line);
        break; }
      case M_FREE: {
        long rem = ((long)(_endAt - now) + 999) / 1000;
        snprintf(line, sizeof(line), "FREI %ld:%02ld  %d Stoesse", rem / 60, rem % 60, _strokes); display.drawString(2, 2, line);
        bar(16, pct(_dist), "");
        if (_bpm) { snprintf(line, sizeof(line), "Takt %d/min", _bpm); display.drawString(2, 42, line); }
        break; }
    }
    if (_mode != M_IDLE && _mode != M_CAL) {
      long remS = ((long)(_endAt - now)) / 1000;
      snprintf(line, sizeof(line), "%ld:%02ld", remS / 60, remS % 60);
      display.setTextAlignment(TEXT_ALIGN_RIGHT); display.drawString(127, 53, line); display.setTextAlignment(TEXT_ALIGN_LEFT);
    }
    display.display();
  }
};

TrainerHandler handler;

// =====================================================================
void setup() {
  Serial.begin(115200);
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
  cfg.otaPassword = "punisher";
  // no punishListener: no stimulator (faults -> fault -> channel via the central unit)
  dev.begin(cfg, handler);
  handler.loadEnvelope();
  handler.loadSettings();
}

void loop() {
  dev.loop();
}
