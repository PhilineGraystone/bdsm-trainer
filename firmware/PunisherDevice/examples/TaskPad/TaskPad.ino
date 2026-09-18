// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  TaskPad — task pad on the PunisherDevice base (doc 14 §7.3)
//
//  Hardware: ESP32 (DevKit), 1-4 buttons with LED, vibration motor (PWM over
//  transistor/MOSFET), passive buzzer. Pins below; NUM_BUTTONS = populated
//  buttons (1..4). Buttons against GND, internal pull-up; LEDs active HIGH.
//
//  Tasks (modes) — the central unit starts them with "task" {kind, ...}:
//    nose      : hold the button pressed for target_s (nose button). Releasing
//                shorter than wobble_ms = wobble (warn), longer = lost (fault
//                + task_end lost). The vibration motor runs during the hold.
//    reaction  : an LED lights up at random, the right button within deadline_ms.
//                Missed/wrong = fault. Metrics: hits, misses, mean_rt_ms, best_rt_ms.
//    rhythm    : LED+buzzer give the beat (bpm); button within tol_ms around
//                the beat. Dropouts in a row >= fault_after = fault.
//    memory    : press the LED sequence back, one signal longer per round; wrong =
//                fault + end. Metric: rounds_reached.
//  Further commands: "cue" {ms, vibe, led} (attention signal; the answer =
//  "test" {led, vibe, ms} (diagnosis), "task" {kind:"off"} ends it.
//
//  The pad has NO stimulator: violations are fault events; the central unit
//  decides and publishes the punishment on the channel of the slave
//  (e.g. collar). Result of a run: task_end (cls result).
//
//  Envelope (compiled in fixed): ENV_TASK_MAX_MIN (60) longest task, ENV_VIBE_MAX (3).
//  safeState(): task off, motor off, LEDs off. Base: WiFi/MQTT/LWT/Heartbeat/
//  Watchdog/EMERGENCY/OTA/cmd/Config.
// =====================================================================
#include "PunisherDevice.h"
#include "creds.h"

// A build with placeholder credentials must not happen (see PunisherCreds.h).
// If this line fails to compile, `creds.h` still holds the CHANGEME values
// from the repository — fill them in, then build again.
#include <PunisherCreds.h>
PUN_REQUIRE_REAL_CREDS();

#include "version.h"

// --- Hardware ---------------------------------------------------------
#define NUM_BUTTONS  4
const uint8_t BUTTON_PINS[4] = { 32, 33, 25, 26 };   // buttons (active LOW, pull-up)
const uint8_t LED_PINS[4]    = { 16, 17, 18, 19 };   // LEDs (active HIGH)
#define VIBE_PIN     23                              // motor over a transistor, PWM
#define BUZZER_PIN    5                              // passive buzzer
#define VIBE_CH       0                              // LEDC channels
#define BUZZ_CH       2

#define ENV_TASK_MAX_MIN  60
#define ENV_VIBE_MAX       3
static const uint8_t VIBE_DUTY[4] = { 0, 90, 160, 255 };   // level 0..3 -> PWM

PunisherDevice dev;
const char* CAPS[] = { "task_nose", "task_reaction", "task_rhythm", "task_memory", "task_confirm" };

// =====================================================================
class TaskPadHandler : public PunisherHandler {
 public:
  enum Kind : uint8_t { K_IDLE = 0, K_NOSE, K_REACTION, K_RHYTHM, K_MEMORY };
  static const char* kindName(uint8_t k) {
    static const char* n[] = { "idle", "nose", "reaction", "rhythm", "memory" };
    return k <= K_MEMORY ? n[k] : "?";
  }

  void setup() {
    for (uint8_t i = 0; i < NUM_BUTTONS; i++) { _btn[i].begin(INPUT_PULLUP); pinMode(LED_PINS[i], OUTPUT); digitalWrite(LED_PINS[i], LOW); }
    ledcSetup(VIBE_CH, 1000, 8); ledcAttachPin(VIBE_PIN, VIBE_CH); ledcWrite(VIBE_CH, 0);
    ledcSetup(BUZZ_CH, 2000, 8); ledcAttachPin(BUZZER_PIN, BUZZ_CH); ledcWrite(BUZZ_CH, 0);
    for (uint8_t i = 0; i < NUM_BUTTONS; i++) { digitalWrite(LED_PINS[i], HIGH); delay(80); digitalWrite(LED_PINS[i], LOW); }
  }

  // --- Mandatory ----------------------------------------------------------------
  void loadEnvelope() {
    _envTaskMin = (uint16_t) constrain(dev.cfgInt("task_max_min", ENV_TASK_MAX_MIN),
                                       1L, (long)(ENV_TASK_MAX_MIN));
    _envVibe    = (uint8_t) constrain(dev.cfgInt("vibe_max", ENV_VIBE_MAX), 0L, (long)(ENV_VIBE_MAX));
  }
  void reportLimits(JSONVar& j) override {
    j["task_max_min"] = (int) _envTaskMin;
    j["vibe_max"]     = (int) _envVibe;
  }

  void safeState() override {
    if (_kind != K_IDLE) endTask("stop", false);
    vibe(0); buzz(0); ledsOff(); _cueUntil = 0;
  }
  bool isActive() override { return _kind != K_IDLE; }

  // --- Commands -------------------------------------------------------------------
  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    if (strcmp(action, "task") == 0) {
      const char* k = (const char*) args["kind"];
      if (!k) { snprintf(err, errLen, "kind missing"); return false; }
      if (strcmp(k, "off") == 0) { if (_kind != K_IDLE) endTask("switched", false); return true; }
      if (_kind != K_IDLE) endTask("switched", false);
      if (strcmp(k, "nose") == 0)          return startNose(args, err, errLen);
      if (strcmp(k, "reaction") == 0)      return startReaction(args, err, errLen);
      if (strcmp(k, "rhythm") == 0)        return startRhythm(args, err, errLen);
      if (strcmp(k, "memory") == 0)        return startMemory(args, err, errLen);
      snprintf(err, errLen, "unknown kind"); return false;
    }
    if (strcmp(action, "cue") == 0) {           // attention signal
      long ms = argInt(args, "ms", 1500, 200, 60000);
      _cueVibe = (uint8_t) argInt(args, "vibe", 2, 0, ENV_VIBE_MAX);
      _cueLed  = (int8_t) argInt(args, "led", 0, 0, NUM_BUTTONS);
      _cueUntil = millis() + ms; _cueStart = millis();
      return true;
    }
    if (strcmp(action, "test") == 0) {          // diagnosis: LED/motor/buzzer briefly
      long ms = argInt(args, "ms", 500, 50, 3000);
      long led = argInt(args, "led", 0, 0, NUM_BUTTONS);
      long v = argInt(args, "vibe", 0, 0, 3);
      if (led) digitalWrite(LED_PINS[led - 1], HIGH);
      vibe((uint8_t) v); buzz(1500);
      delay(ms);
      vibe(0); buzz(0); ledsOff();
      return true;
    }
    snprintf(err, errLen, "unknown action");
    return false;
  }

  void reportState(JSONVar& j) override {
    j["task"] = kindName(_kind);
    j["buttons"] = NUM_BUTTONS;
    if (_kind != K_IDLE) {
      j["remaining_s"] = (int) (((long)(_endAt - millis())) / 1000);
      j["progress"] = (int) _progress;
      j["target"] = (int) _target;
      j["faults"] = (int) _faults;
    }
  }
  void onEmergency(const char*) override { for (uint8_t i = 0; i < NUM_BUTTONS; i++) digitalWrite(LED_PINS[i], HIGH); }
  void onIdentify() override { for (int r = 0; r < 3; r++) { for (uint8_t i = 0; i < NUM_BUTTONS; i++) digitalWrite(LED_PINS[i], HIGH); delay(120); ledsOff(); delay(120); } }

  // --- Tick -------------------------------------------------------------------------
  void onTick(unsigned long now) override {
    // read the buttons debounced; remember the edges
    for (uint8_t i = 0; i < NUM_BUTTONS; i++) {
      if (_btn[i].update()) {
        if (_btn[i].active()) onPress(i, now); else onRelease(i, now);
      }
    }
    if (dev.isEmergency()) return;
    // attention signal: LED blinks, motor buzzes until answer/expiry
    if (_cueUntil) {
      if ((long)(_cueUntil - now) <= 0) { _cueUntil = 0; vibe(0); if (_kind == K_IDLE) ledsOff(); }
      else {
        bool on = ((now / 250) % 2) == 0;
        if (_cueLed) digitalWrite(LED_PINS[_cueLed - 1], on); else for (uint8_t i = 0; i < NUM_BUTTONS; i++) digitalWrite(LED_PINS[i], on);
        if (_kind != K_NOSE) vibe(on ? _cueVibe : 0);
      }
    }
    if (_buzzUntil && (long)(_buzzUntil - now) <= 0) { _buzzUntil = 0; buzz(0); }
    if (_kind == K_IDLE) return;
    // Maximum duration reached: with the nose button it is still held here (releasing/
    // not starting end earlier) -> planned end, the central unit grades by the time held
    // (review 2026-09-10: before that "lost", although it was held). Otherwise guard time.
    if ((long)(_endAt - now) <= 0) { endTask(_kind == K_NOSE ? "max_duration" : "timeout", _kind != K_NOSE); return; }
    switch (_kind) {
      case K_NOSE:     tickNose(now); break;
      case K_REACTION: tickReaction(now); break;
      case K_RHYTHM:   tickRhythm(now); break;
      case K_MEMORY:   tickMemory(now); break;
      default: break;
    }
  }

 private:
  uint16_t _envTaskMin = ENV_TASK_MAX_MIN;           // envelope, can be lowered via NVS
  uint8_t  _envVibe    = ENV_VIBE_MAX;

  Debounced _btn[4] = { Debounced(BUTTON_PINS[0]), Debounced(BUTTON_PINS[1]), Debounced(BUTTON_PINS[2]), Debounced(BUTTON_PINS[3]) };
  uint8_t  _kind = K_IDLE;
  unsigned long _startAt = 0, _endAt = 0, _buzzUntil = 0, _cueUntil = 0, _cueStart = 0;
  uint8_t  _cueVibe = 2; int8_t _cueLed = 0;
  uint16_t _progress = 0, _target = 0, _faults = 0, _warns = 0;

  // --- Helpers ------------------------------------------------------------------------
  static long argInt(JSONVar& a, const char* k, long def, long lo, long hi) {
    long v = a.hasOwnProperty(k) ? (long)(int) a[k] : def;
    return constrain(v, lo, hi);
  }
  void vibe(uint8_t level) { level = (uint8_t) min((long) level, (long)(ENV_VIBE_MAX)); ledcWrite(VIBE_CH, VIBE_DUTY[min(level, (uint8_t) 3)]); }
  void buzz(int freq) { if (freq <= 0) ledcWrite(BUZZ_CH, 0); else { ledcWriteTone(BUZZ_CH, freq); ledcWrite(BUZZ_CH, 128); } }
  void beep(int freq, unsigned long ms) { buzz(freq); _buzzUntil = millis() + ms; }
  void ledsOff() { for (uint8_t i = 0; i < NUM_BUTTONS; i++) digitalWrite(LED_PINS[i], LOW); }
  void ledOnly(int8_t idx) { for (uint8_t i = 0; i < NUM_BUTTONS; i++) digitalWrite(LED_PINS[i], (idx >= 0 && i == idx) ? HIGH : LOW); }
  void ev(const char* name, JSONVar& j, const char* cls) { dev.publishEvent(name, j, cls); }
  void ev(const char* name, const char* cls) { JSONVar j; ev(name, j, cls); }

  bool beginTask(uint8_t kind, JSONVar& a, long maxS) {
    long capS = (long)(ENV_TASK_MAX_MIN) * 60L;
    if (maxS > capS) maxS = capS;
    _kind = kind; _startAt = millis(); _endAt = _startAt + (unsigned long) maxS * 1000UL;
    _progress = 0; _faults = 0; _warns = 0;
    JSONVar j; j["kind"] = kindName(kind); j["max_s"] = (int) maxS;
    if (a.hasOwnProperty("target_s")) j["target_s"] = (int) a["target_s"];
    ev("task_start", j, "info");
    dev.publishState();
    return true;
  }
  void endTask(const char* reason, bool failed) {
    if (_kind == K_IDLE) return;
    uint8_t k = _kind; _kind = K_IDLE;
    vibe(0); buzz(0); ledsOff();
    JSONVar j; j["kind"] = kindName(k); j["reason"] = reason;
    j["duration_s"] = (int) ((millis() - _startAt) / 1000UL);
    j["faults"] = (int) _faults; j["warn"] = (int) _warns; j["failed"] = failed;
    fillResult(k, j);
    ev("task_end", j, "result");
    dev.publishState();
  }
  void fault(const char* reason, JSONVar& j) { _faults++; j["reason"] = reason; ev("fault", j, "fault"); beep(300, 400); }

  // Random button (with several of them, not the same one twice)
  int8_t randomButton(int8_t avoid) {
    if (NUM_BUTTONS == 1) return 0;
    int8_t b; do { b = (int8_t) random(0, NUM_BUTTONS); } while (b == avoid);
    return b;
  }

  // ================================================================ NOSE
  struct { int8_t button; uint16_t targetS, wobbleMs, startS; uint8_t vibeLvl; bool holding, everPressed;
           unsigned long holdSince, releasedAt; uint16_t wobbles; unsigned long heldMs; int8_t pressedBtn; } _n;

  bool startNose(JSONVar& a, char* err, size_t errLen) {
    _n.targetS  = (uint16_t) argInt(a, "target_s", 60, 5, 36000);
    _n.wobbleMs = (uint16_t) argInt(a, "wobble_ms", 300, 50, 5000);
    _n.vibeLvl  = (uint8_t) argInt(a, "vibe", 1, 0, 3);
    _n.button   = (int8_t) argInt(a, "button", 1, 0, NUM_BUTTONS) - 1;   // -1 = any
    _n.startS   = (uint16_t) argInt(a, "start_s", 15, 3, 600);
    _n.holding = _n.everPressed = false; _n.wobbles = 0; _n.heldMs = 0; _n.releasedAt = 0; _n.pressedBtn = -1;
    _target = _n.targetS;
    // Maximum duration: start deadline + target + room for wobbles (review 2026-09-10: before
    // only +5 s — as few as 17 wobbles of 300 ms would have ended a clean run as "lost")
    beginTask(K_NOSE, a, (long) _n.startS + _n.targetS + max(15L, (long) _n.targetS / 4));
    ledOnly(_n.button);                         // the target button lights up; -1 = all off
    if (_n.button < 0) for (uint8_t i = 0; i < NUM_BUTTONS; i++) digitalWrite(LED_PINS[i], HIGH);
    return true;
  }
  bool noseAccepts(uint8_t i) { return _n.button < 0 || i == _n.button; }
  void tickNose(unsigned long now) {
    if (!_n.everPressed) {
      if (now - _startAt >= _n.startS * 1000UL) { JSONVar j; j["held_s"] = 0; fault("not_started", j); endTask("not_started", true); }
      return;
    }
    if (_n.holding) {
      unsigned long held = _n.heldMs + (now - _n.holdSince);
      _progress = (uint16_t) (held / 1000UL);
      if (held >= _n.targetS * 1000UL) { beep(1200, 300); endTask("done", false); return; }
      // the target LED blinks slowly as progress
      digitalWrite(LED_PINS[_n.button < 0 ? 0 : _n.button], ((now / 500) % 2) == 0);
    } else if (_n.releasedAt && now - _n.releasedAt >= _n.wobbleMs) {
      // released for longer than the tolerance -> lost
      JSONVar j; j["held_s"] = (int) (_n.heldMs / 1000UL); j["wobbles"] = (int) _n.wobbles;
      fault("nose_button_lost", j);
      endTask("lost", true);
    }
  }
  void nosePress(uint8_t i, unsigned long now) {
    if (!noseAccepts(i)) return;
    if (_n.holding) return;                     // second button during the hold: ignore (review 2026-09-10: it reset holdSince)
    if (!_n.everPressed) { _n.everPressed = true; beep(900, 120); }
    if (_n.releasedAt && !_n.holding) {         // back in time: wobble
      _n.wobbles++; _warns++;
      JSONVar j; j["ms"] = (int) (now - _n.releasedAt); j["wobbles"] = (int) _n.wobbles; ev("wobble", j, "warn");
      beep(600, 150);
    }
    _n.holding = true; _n.holdSince = now; _n.releasedAt = 0; _n.pressedBtn = i;
    vibe(_n.vibeLvl);
  }
  void noseRelease(uint8_t i, unsigned long now) {
    if (!_n.holding || i != _n.pressedBtn) return;
    _n.heldMs += now - _n.holdSince;
    _n.holding = false; _n.releasedAt = now;
    vibe(0);
  }

  // ================================================================ REACTION
  struct { uint16_t rounds, deadlineMs, gapMinMs, gapMaxMs; uint8_t vibeLvl; int8_t lit; unsigned long litAt, nextAt;
           uint16_t hits, misses; unsigned long rtSum, rtBest; } _r;

  bool startReaction(JSONVar& a, char* err, size_t errLen) {
    _r.rounds     = (uint16_t) argInt(a, "rounds", 10, 1, 500);
    _r.deadlineMs = (uint16_t) argInt(a, "deadline_ms", 1500, 200, 20000);
    _r.gapMinMs   = (uint16_t) argInt(a, "gap_min_ms", 2000, 300, 60000);
    _r.gapMaxMs   = (uint16_t) argInt(a, "gap_max_ms", 8000, _r.gapMinMs, 60000);
    _r.vibeLvl    = (uint8_t) argInt(a, "vibe", 0, 0, 3);
    _r.lit = -1; _r.hits = _r.misses = 0; _r.rtSum = 0; _r.rtBest = 0;
    _target = _r.rounds;
    _r.nextAt = millis() + random(_r.gapMinMs, _r.gapMaxMs + 1);
    return beginTask(K_REACTION, a, (long) _r.rounds * ((_r.gapMaxMs + _r.deadlineMs) / 1000 + 1) + 10);
  }
  void tickReaction(unsigned long now) {
    if (_r.lit < 0) {
      vibe(_r.vibeLvl && ((now / 700) % 3) == 0 ? _r.vibeLvl : 0);     // distraction: short bursts
      if ((long)(_r.nextAt - now) <= 0) {
        _r.lit = randomButton(-1); _r.litAt = now; ledOnly(_r.lit); vibe(0);
      }
      return;
    }
    if (now - _r.litAt > _r.deadlineMs) {
      JSONVar j; j["n"] = (int) (_r.hits + _r.misses + 1); j["button"] = _r.lit + 1;
      _r.misses++; ledsOff(); _r.lit = -1;
      fault("missed", j);
      afterReactionRound(now);
    }
  }
  void reactionPress(uint8_t i, unsigned long now) {
    if (_r.lit < 0) return;                     // pressing without a signal: ignore
    unsigned long rt = now - _r.litAt;
    JSONVar j; j["n"] = (int) (_r.hits + _r.misses + 1); j["button"] = i + 1; j["rt_ms"] = (int) rt;
    if ((int8_t) i == _r.lit) {
      _r.hits++; _r.rtSum += rt; if (!_r.rtBest || rt < _r.rtBest) _r.rtBest = rt;
      ledsOff(); _r.lit = -1; beep(1200, 80);
      ev("hit", j, "info");
    } else {
      _r.misses++; ledsOff(); _r.lit = -1;
      fault("wrong", j);
    }
    afterReactionRound(now);
  }
  void afterReactionRound(unsigned long now) {
    _progress = _r.hits + _r.misses;
    if (_progress >= _r.rounds) { endTask("done", false); return; }
    _r.nextAt = now + random(_r.gapMinMs, _r.gapMaxMs + 1);
  }

  // ================================================================ RHYTHM
  struct { uint16_t bpm, beats, tolMs, faultAfter; int8_t button; unsigned long beatMs, firstBeat; uint16_t beatIdx, hits, misses, consecMiss;
           long devSum; bool beatPressed, beatGiven; } _t;

  bool startRhythm(JSONVar& a, char* err, size_t errLen) {
    _t.bpm        = (uint16_t) argInt(a, "bpm", 60, 20, 240);
    _t.beats      = (uint16_t) argInt(a, "beats", 32, 4, 5000);
    _t.tolMs      = (uint16_t) argInt(a, "tol_ms", 150, 30, 2000);
    _t.faultAfter = (uint16_t) argInt(a, "fault_after", 3, 1, 50);
    _t.button     = (int8_t) argInt(a, "button", 1, 0, NUM_BUTTONS) - 1;
    _t.beatMs = 60000UL / _t.bpm;
    _t.beatIdx = 0; _t.hits = _t.misses = _t.consecMiss = 0; _t.devSum = 0; _t.beatPressed = false; _t.beatGiven = false;
    _target = _t.beats;
    _t.firstBeat = millis() + 2000;             // two seconds of lead-in
    return beginTask(K_RHYTHM, a, (long) (_t.beats * _t.beatMs) / 1000 + 10);
  }
  unsigned long beatTime(uint16_t idx) { return _t.firstBeat + (unsigned long) idx * _t.beatMs; }
  void tickRhythm(unsigned long now) {
    if (_t.beatIdx >= _t.beats) {
      if ((long)(beatTime(_t.beats - 1) + _t.tolMs + 50 - now) <= 0) endTask("done", false);
      return;
    }
    unsigned long bt = beatTime(_t.beatIdx);
    // Give the beat (LED + click) exactly at beat time — even when it has already been
    // pressed (too early): the beat is the default, not the answer (review 2026-09-10)
    if ((long)(bt - now) <= 0 && !_t.beatGiven) {
      _t.beatGiven = true; ledOnly(_t.button < 0 ? 0 : _t.button); beep(2000, 40);
    }
    if ((long)(bt + 70 - now) <= 0) ledsOff();
    // window for this beat over?
    if ((long)(bt + _t.tolMs - now) <= 0) {
      if (!_t.beatPressed) {
        _t.misses++; _t.consecMiss++;
        JSONVar j; j["beat"] = (int) (_t.beatIdx + 1); ev("beat_miss", j, "warn"); _warns++;
        if (_t.consecMiss >= _t.faultAfter) { _t.consecMiss = 0; JSONVar f; f["beat"] = (int) (_t.beatIdx + 1); fault("rhythm_fault", f); }
      }
      _t.beatIdx++; _t.beatPressed = false; _t.beatGiven = false; _progress = _t.beatIdx;
    }
  }
  void rhythmPress(uint8_t i, unsigned long now) {
    if (_t.button >= 0 && (int8_t) i != _t.button) return;
    if (_t.beatIdx >= _t.beats) return;
    // What is judged is always the current beat (the window of the previous one is
    // closed): dev_ < -tol = too early, |dev_| <= tol = hit. One press counts as the
    // attempt for this beat — a too early one as well; a second one in the same
    // window no longer counts.
    unsigned long bt = beatTime(_t.beatIdx);
    long dev_ = (long)(now - bt);
    if (_t.beatPressed) return;                 // double click in the same window
    if (labs(dev_) <= (long) _t.tolMs) {
      _t.hits++; _t.consecMiss = 0; _t.devSum += labs(dev_); _t.beatPressed = true;
    } else {
      JSONVar j; j["beat"] = (int) (_t.beatIdx + 1); j["dev_ms"] = (int) dev_; ev("beat_off", j, "warn"); _warns++;
      _t.beatPressed = true;                    // the beat counts as attempted but not hit
      _t.misses++; _t.consecMiss++;
      if (_t.consecMiss >= _t.faultAfter) { _t.consecMiss = 0; JSONVar f; f["beat"] = (int) (_t.beatIdx + 1); fault("rhythm_fault", f); }
    }
  }

  // ================================================================ MEMORY
  enum MPhase : uint8_t { M_SHOW, M_INPUT, M_PAUSE };
  struct { uint16_t roundsTarget, showMs; uint8_t vibeLvl; uint8_t seq[32]; uint8_t len, showIdx, inputIdx; MPhase phase;
           unsigned long phaseAt; bool ledOn; uint16_t reached; } _m;

  bool startMemory(JSONVar& a, char* err, size_t errLen) {
    if (NUM_BUTTONS < 2) { snprintf(err, errLen, "need 2+ buttons"); return false; }
    _m.roundsTarget = (uint16_t) argInt(a, "rounds", 6, 1, 30);
    _m.showMs       = (uint16_t) argInt(a, "show_ms", 600, 150, 3000);
    _m.vibeLvl      = (uint8_t) argInt(a, "vibe", 0, 0, 3);
    _m.len = 0; _m.reached = 0;
    _target = _m.roundsTarget;
    beginTask(K_MEMORY, a, (long) _m.roundsTarget * 40 + 10);
    memoryNextRound();
    return true;
  }
  void memoryNextRound() {
    // Repetitions allowed (review 2026-09-10: with "never the same one" the sequence
    // with two buttons was pure alternation and therefore predictable)
    if (_m.len < 32) _m.seq[_m.len++] = (uint8_t) randomButton(-1);
    _m.showIdx = 0; _m.inputIdx = 0; _m.phase = M_PAUSE; _m.phaseAt = millis() + 900; _m.ledOn = false;
    JSONVar j; j["round"] = (int) _m.len; ev("round", j, "info");
  }
  void tickMemory(unsigned long now) {
    if (_m.phase == M_PAUSE) {
      if ((long)(_m.phaseAt - now) <= 0) { _m.phase = M_SHOW; _m.phaseAt = now; _m.ledOn = false; vibe(_m.vibeLvl); }
      return;
    }
    if (_m.phase == M_SHOW) {
      if (!_m.ledOn && (long)(_m.phaseAt - now) <= 0) {
        if (_m.showIdx >= _m.len) { ledsOff(); vibe(0); _m.phase = M_INPUT; _m.phaseAt = now; beep(900, 60); return; }
        ledOnly(_m.seq[_m.showIdx]); beep(600 + 200 * _m.seq[_m.showIdx], 80);
        _m.ledOn = true; _m.phaseAt = now + _m.showMs;
      } else if (_m.ledOn && (long)(_m.phaseAt - now) <= 0) {
        ledsOff(); _m.ledOn = false; _m.showIdx++; _m.phaseAt = now + 250;
      }
      return;
    }
    // input: 15 s per round, otherwise missed (review 2026-09-10: previously reported as "wrong")
    if (_m.phase == M_INPUT && now - _m.phaseAt > 15000UL) {
      JSONVar j; j["round"] = (int) _m.len; fault("missed", j); endTask("timeout", true);
    }
  }
  void memoryPress(uint8_t i, unsigned long now) {
    if (_m.phase != M_INPUT) return;
    beep(600 + 200 * i, 60);
    if (i != _m.seq[_m.inputIdx]) {
      JSONVar j; j["round"] = (int) _m.len; j["expected"] = _m.seq[_m.inputIdx] + 1; j["pressed"] = i + 1;
      fault("wrong", j); endTask("wrong", true); return;
    }
    _m.inputIdx++; _m.phaseAt = now;            // the deadline applies per press, not per round
    if (_m.inputIdx >= _m.len) {
      _m.reached = _m.len; _progress = _m.reached;
      if (_m.reached >= _m.roundsTarget) { beep(1500, 400); endTask("done", false); return; }
      memoryNextRound();
    }
  }

  // ================================================================= Result / buttons
  void fillResult(uint8_t k, JSONVar& j) {
    switch (k) {
      case K_NOSE: {
        unsigned long held = _n.heldMs + (_n.holding ? (millis() - _n.holdSince) : 0);
        j["held_s"] = (int) (held / 1000UL); j["target_s"] = (int) _n.targetS; j["wobbles"] = (int) _n.wobbles; break; }
      case K_REACTION:
        j["hits"] = (int) _r.hits; j["misses"] = (int) _r.misses; j["rounds"] = (int) _r.rounds;
        if (_r.hits) { j["mean_rt_ms"] = (int) (_r.rtSum / _r.hits); j["best_rt_ms"] = (int) _r.rtBest; }
        break;
      case K_RHYTHM:
        j["hits"] = (int) _t.hits; j["misses"] = (int) _t.misses; j["beats"] = (int) _t.beats;
        if (_t.hits) j["mean_dev_ms"] = (int) (_t.devSum / _t.hits);
        break;
      case K_MEMORY:
        j["rounds_reached"] = (int) _m.reached; j["rounds"] = (int) _m.roundsTarget; break;
      default: break;
    }
  }
  void onPress(uint8_t i, unsigned long now) {
    if (dev.isEmergency()) return;
    // attention signal answered
    if (_cueUntil) {
      JSONVar j; j["button"] = i + 1; j["cue"] = true; j["rt_ms"] = (int) (now - _cueStart);
      _cueUntil = 0; vibe(_kind == K_NOSE && _n.holding ? _n.vibeLvl : 0); if (_kind == K_IDLE) ledsOff();
      ev("press", j, "info");
      if (_kind != K_NOSE) return;              // in the nose button the press additionally counts towards the hold
    }
    switch (_kind) {
      case K_IDLE: { JSONVar j; j["button"] = i + 1; ev("press", j, "info"); break; }
      case K_NOSE: nosePress(i, now); break;
      case K_REACTION: reactionPress(i, now); break;
      case K_RHYTHM: rhythmPress(i, now); break;
      case K_MEMORY: memoryPress(i, now); break;
    }
  }
  void onRelease(uint8_t i, unsigned long now) {
    if (_kind == K_NOSE) noseRelease(i, now);
  }
};

TaskPadHandler handler;

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
  cfg.otaPassword = "punisher";     // OTA only in the safe state
  // no punishListener: the pad has no stimulator (violations -> fault -> channel via the central unit)
  dev.begin(cfg, handler);
  handler.loadEnvelope();
}

void loop() {
  dev.loop();
}
