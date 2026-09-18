// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  MagLock — reference device on the PunisherDevice base
//
//  Holding magnet (80 kg) in a PC-CF pot, armature plate ("puck": 3 washers
//  + 2 PC-CF discs as a heat barrier) with an eyelet. Microswitch on top =
//  seating detection (CONTROLPIN). Up to four channels as on the board
//  (relays active LOW). Restraints for a St Andrew's cross — nobody is
//  hung up, no risk of falling.
//
//  Safety philosophy (Philine): strength before weakness. Under PULL the
//  magnet keeps holding — a brief loss of seating during the locking does
//  NOT trigger, it is only reported.
//  One is let out by:
//    - emergency-stop bumper: cuts the mains voltage of the device, software-
//      independent -> the magnet falls (hard safeguard, doc 03 B.2).
//    - EMERGENCY / broker failsafe / central-unit timeout: at once (software).
//    - timer expiry or unlock: releases (no risk of falling -> no warning time).
//  The only switch per pot is the microswitch = seating detection.
//
//  The base takes over: WiFi/MQTT/LWT/Heartbeat/Watchdog/EMERGENCY/OTA/cmd/Config.
//  No direct device-to-device command any more — only events to the central unit.
// =====================================================================
#include <Wire.h>
#include "Waveshare_LCD1602_RGB.h"
#include "PunisherDevice.h"
#include "creds.h"

// A build with placeholder credentials must not happen (see PunisherCreds.h).
// If this line fails to compile, `creds.h` still holds the CHANGEME values
// from the repository — fill them in, then build again.
#include <PunisherCreds.h>
PUN_REQUIRE_REAL_CREDS();

#include "version.h"

// --- Hardware ---------------------------------------------------------
// Index 0..3 = physical port 1..4 (order mirrored compared with v2, because
// the ports on the board lie the other way round than the old pin arrays).
#define MAG_COUNT   4
const uint8_t RELAY_PINS[MAG_COUNT]     = { 11, 10, 13, 12 };  // active LOW
const uint8_t CONTROL_PINS[MAG_COUNT]   = { 15, 16, 17, 18 };  // bond, LOW = seated
const uint8_t AVAILABLE_PINS[MAG_COUNT] = {  4,  5,  6,  7 };  // LOW = channel populated
#define RELAY_ON   LOW
#define RELAY_OFF  HIGH

#define LOCK_MINUTES_MAX_DEFAULT 240   // envelope (doc 03 C); compiled in fixed (Philine 2026-09-10)

uint8_t GLYPH_QUARTER[8] = {0,0,0,0,0,0,0x1F,0x1F};   // not populated
uint8_t GLYPH_HALF[8]    = {0,0,0,0,0x1F,0x1F,0x1F,0x1F}; // populated
uint8_t GLYPH_FULL[8]    = {0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F}; // populated + switch

Waveshare_LCD1602_RGB lcd(16, 2);
PunisherDevice        dev;
const char* CAPS[] = { "lock" };

// --- LCD helpers ------------------------------------------------------
static char l0buf[20];
void lcdColor(uint8_t r, uint8_t g, uint8_t b) { lcd.setRGB(r, g, b); }
void lcdLine0(const char* t) { snprintf(l0buf, sizeof(l0buf), "%-16.16s", t); lcd.setCursor(0,0); lcd.send_string(l0buf); }
void lcdLine1(const char* t) { char b[16]; snprintf(b, sizeof(b), "%-12.12s", t); lcd.setCursor(0,1); lcd.send_string(b); }

// =====================================================================
class MagLockHandler : public PunisherHandler {
 public:
  enum LState { L_IDLE, L_COUNTDOWN, L_LOCKED };

  void setup() {
    for (uint8_t i = 0; i < MAG_COUNT; i++) {
      pinMode(RELAY_PINS[i], OUTPUT);
      digitalWrite(RELAY_PINS[i], RELAY_OFF);
      _bond[i].begin(INPUT_PULLUP);      // active LOW, debounced
      _avail[i].begin(INPUT_PULLUP);
    }
    lcd.init(); lcd.noAutoscroll(); lcd.leftToRight(); lcd.noCursor(); lcd.stopBlink();
    lcd.customSymbol(0, GLYPH_QUARTER);
    lcd.customSymbol(1, GLYPH_HALF);
    lcd.customSymbol(2, GLYPH_FULL);
    lcdColor(0, 0, 255); lcd.clear();
    lcdLine0("Magnetic Cuff"); lcdLine1("Boot ...");
  }

  // --- Mandatory: immediately harmless (all magnets de-energised) -----
  // Envelope of this device: NVS lowers it, the #define caps it (doc 23).
  void loadEnvelope() {
    _envLockMin = (uint16_t) constrain(dev.cfgInt("lock_max_min", LOCK_MINUTES_MAX_DEFAULT),
                                       1L, (long)(LOCK_MINUTES_MAX_DEFAULT));
  }
  void reportLimits(JSONVar& j) override { j["lock_minutes_max"] = (int) _envLockMin; }

  // WHICH CUFFS ARE NOT THERE TODAY (2.2.0, doc 42 point 4). A pot without a
  // magnet on its AVAILABLE line is a cuff this lock cannot use; the central
  // unit narrows what it asks of this device by it, and a step that needs
  // all four is not run here. The step decides how many it needs — a cross
  // wants four, wrists want two (decision Philine 2026-09-16).
  //
  // NOT reported: "stuck". The bond line senses a SEATED puck, not a held
  // one — a puck resting on a de-energised magnet looks the same as one that
  // is held. This hardware cannot tell the two apart, so this sketch does not
  // claim to. The central unit knows `stuck:` as a contract for a lock that
  // can measure it.
  void reportDegraded(JSONVar& out) override {
    int n = 0;
    for (uint8_t i = 0; i < MAG_COUNT; i++) {
      if (!avail(i)) { char b[8]; snprintf(b, sizeof(b), "cuff%u", (unsigned) i + 1); out[n++] = b; }
    }
  }
  uint8_t availCount() { uint8_t n = 0; for (uint8_t i=0;i<MAG_COUNT;i++) if (avail(i)) n++; return n; }

  void safeState() override { relaysOff(); _l = L_IDLE; }
  bool isActive() override { return _l == L_COUNTDOWN || _l == L_LOCKED; }

  // --- Commands -------------------------------------------------------
  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    if (strcmp(action, "lock") == 0) {
      if (_l != L_IDLE) { snprintf(err, errLen, "busy"); return false; }
      if (!args.hasOwnProperty("lock_in_minutes") || !args.hasOwnProperty("countdown_in_seconds")) {
        snprintf(err, errLen, "missing args"); return false;
      }
      long maxMin = (long) _envLockMin;
      long mins   = (int) args["lock_in_minutes"];
      long cd     = (int) args["countdown_in_seconds"];
      if (mins <= 0 || mins > maxMin) { snprintf(err, errLen, "minutes out of envelope"); return false; }
      if (cd < 0 || cd > 600)         { snprintf(err, errLen, "countdown 0..600 s"); return false; }
      if (!anyAvail()) { snprintf(err, errLen, "no magnet connected"); return false; }
      // The step's own requirement, checked here as well: the central unit
      // already refuses, but a lock is the wrong place to be trusting.
      if (args.hasOwnProperty("cuffs")) {
        int need = (int) args["cuffs"];
        if (need > 0 && availCount() < need) { snprintf(err, errLen, "needs %d cuffs, have %u", need, (unsigned) availCount()); return false; }
      }
      startLock((uint32_t) mins, (uint32_t) cd);
      return true;
    }
    if (strcmp(action, "unlock") == 0) {
      if (_l != L_IDLE) release("unlock");
      return true;
    }
    // Diagnosis: switch one port briefly and report all pin states.
    // Only when idle. args: {"port": 1..4, "ms": 300}
    if (strcmp(action, "test_port") == 0) {
      if (_l != L_IDLE) { snprintf(err, errLen, "busy"); return false; }
      int port = args.hasOwnProperty("port") ? (int) args["port"] : 0;
      int ms   = args.hasOwnProperty("ms")   ? (int) args["ms"]   : 300;
      if (port < 1 || port > MAG_COUNT) { snprintf(err, errLen, "port 1..%d", MAG_COUNT); return false; }
      if (ms < 50 || ms > 2000) ms = 300;
      uint8_t i = port - 1;
      JSONVar ev;
      ev["port"] = port;
      ev["relay_pin"] = RELAY_PINS[i]; ev["control_pin"] = CONTROL_PINS[i]; ev["avail_pin"] = AVAILABLE_PINS[i];
      ev["avail_before"] = avail(i); ev["bond_before"] = bond(i);
      digitalWrite(RELAY_PINS[i], RELAY_ON);
      delay(ms);
      // no debouncing runs during the pulse -> read the raw values
      ev["avail_during"] = (digitalRead(AVAILABLE_PINS[i]) == LOW);
      ev["bond_during"]  = (digitalRead(CONTROL_PINS[i])   == LOW);
      digitalWrite(RELAY_PINS[i], RELAY_OFF);
      dev.publishEvent("test_port", ev);
      return true;
    }
    snprintf(err, errLen, "unknown action");
    return false;
  }

  void reportState(JSONVar& j) override {
    static const char* n[] = {"idle","countdown","locked"};
    j["lock"] = n[_l];
    if (_l == L_LOCKED) j["remaining_s"] = (int) ((long)(_lockEnd - millis()) / 1000);
    JSONVar mags;
    for (uint8_t i = 0; i < MAG_COUNT; i++) { JSONVar m; m["avail"]=avail(i); m["bond"]=bond(i); mags[i]=m; }
    j["magnets"] = mags;
  }

  void onConnected() override { if (_l == L_IDLE) showIdle(); }
  void onRegistered(uint16_t, const char*) override { showIdle(); }
  void onUnregistered() override { showIdle(); }
  void onEmergency(const char*) override { lcdColor(255,0,255); lcdLine0("!! EMERGENCY !!"); lcdLine1("Power cycle"); drawIcons(true); }
  void onIdentify() override { for (int i=0;i<6;i++){ lcdColor(255,255,255); delay(80); lcdColor(0,0,255); delay(80);} showIdle(); }

  void onTick(unsigned long now) override {
    pollInputs();                       // every round, so that the debouncing takes effect
    if (dev.isEmergency()) return;
    if (now - _lastIcon >= 250) { _lastIcon = now; drawIcons(false); }

    switch (_l) {
      case L_IDLE: break;

      case L_COUNTDOWN:
        if (allAvailBonded()) { beginTimer(); break; }
        if ((long)(_cdEnd - now) > 0) {
          if (now - _lastTick >= 1000) {
            _lastTick = now;
            char b[16]; snprintf(b, sizeof(b), "%03ld s", ((long)(_cdEnd - now) + 999) / 1000);
            lcdLine0("Attach cuffs"); lcdLine1(b);
          }
        } else if (now - _lastNotAttached >= 1000) {
          _lastNotAttached = now;
          dev.publishEvent("not_attached");   // the central unit decides the consequence
          lcdLine0("Attach overdue"); lcdLine1("");
        }
        break;

      case L_LOCKED: {
        // Strength before weakness: brief loss of seating -> only report, keep holding.
        for (uint8_t i = 0; i < MAG_COUNT; i++) {
          bool b = bond(i);
          if (!b && _wasBonded[i] && avail(i)) { JSONVar ev; ev["magnet"]=i; dev.publishEvent("bond_lost", ev); }
          _wasBonded[i] = b;
        }
        long rem = (long)(_lockEnd - now);
        if (rem <= 0) { release("timer"); break; }
        if (now - _lastTick >= 1000) {
          _lastTick = now;
          long s = (rem + 999) / 1000;
          char b[16]; snprintf(b, sizeof(b), "  %02ld:%02ld:%02ld", s/3600, (s%3600)/60, s%60);
          lcdLine0("Timer Cuff lock"); lcdLine1(b);
        }
        break;
      }
    }
  }

 private:
  uint16_t _envLockMin = LOCK_MINUTES_MAX_DEFAULT;   // envelope, can be lowered via NVS

  LState        _l = L_IDLE;
  uint32_t      _mins = 0;
  unsigned long _cdEnd = 0, _lockEnd = 0;
  unsigned long _lastTick = 0, _lastNotAttached = 0, _lastIcon = 0;
  bool          _wasBonded[MAG_COUNT] = {false,false,false,false};
  uint8_t       _prevIcon[MAG_COUNT] = {255,255,255,255};

  // Debounced (30 ms): otherwise the microswitch and the plug detection bounce
  // and produce multiple bond_lost events or flickering icons.
  Debounced _avail[MAG_COUNT] = { Debounced(AVAILABLE_PINS[0]), Debounced(AVAILABLE_PINS[1]),
                                  Debounced(AVAILABLE_PINS[2]), Debounced(AVAILABLE_PINS[3]) };
  Debounced _bond[MAG_COUNT]  = { Debounced(CONTROL_PINS[0]),   Debounced(CONTROL_PINS[1]),
                                  Debounced(CONTROL_PINS[2]),   Debounced(CONTROL_PINS[3]) };
  void pollInputs() { for (uint8_t i=0;i<MAG_COUNT;i++){ _avail[i].update(); _bond[i].update(); } }
  bool avail(uint8_t i) { return _avail[i].active(); }
  bool bond(uint8_t i)  { return _bond[i].active(); }
  bool anyAvail() { for (uint8_t i=0;i<MAG_COUNT;i++) if (avail(i)) return true; return false; }
  void relaysOff() { for (uint8_t i=0;i<MAG_COUNT;i++) digitalWrite(RELAY_PINS[i], RELAY_OFF); }
  void relaysOn()  { for (uint8_t i=0;i<MAG_COUNT;i++) if (avail(i)) digitalWrite(RELAY_PINS[i], RELAY_ON); }

  bool allAvailBonded() {
    bool any = false;
    for (uint8_t i=0;i<MAG_COUNT;i++){ if(!avail(i)) continue; any=true; if(!bond(i)) return false; }
    return any;
  }

  void startLock(uint32_t mins, uint32_t cd) {
    _mins = mins; _cdEnd = millis() + cd*1000UL; _l = L_COUNTDOWN;
    _lastTick = 0; _lastNotAttached = 0;
    relaysOn();
    lcdColor(255,0,0); lcdLine0("Timer Cuff lock"); lcdLine1("Countdown");
    JSONVar ev; ev["minutes"]=(int)mins; ev["countdown"]=(int)cd; dev.publishEvent("lock_start", ev);
  }
  void beginTimer() {
    _lockEnd = millis() + _mins*60000UL; _l = L_LOCKED;
    for (uint8_t i=0;i<MAG_COUNT;i++) _wasBonded[i]=bond(i);
    dev.publishEvent("locked");
  }
  void release(const char* reason) {
    relaysOff(); _l = L_IDLE;
    JSONVar ev; ev["reason"]=reason; dev.publishEvent("released", ev);
    lcdColor(0,255,0); lcdLine0("   RELEASE"); lcdLine1("done"); drawIcons(true);
  }
  void showIdle() {
    lcdColor(0,255,0);
    lcdLine0(dev.isRegistered() ? dev.slaveName() : "Magnetic Cuff");
    lcdLine1(dev.isRegistered() ? "Wait for cmd" : "Waiting ...");
    drawIcons(true);
  }
  uint8_t iconFor(uint8_t i){ if(!avail(i)) return 0; if(!bond(i)) return 1; return 2; }
  void drawIcons(bool force){
    for (uint8_t i=0;i<MAG_COUNT;i++){ uint8_t ic=iconFor(i);
      if(force||ic!=_prevIcon[i]){ lcd.setCursor(12+i,1); lcd.write_char(ic); _prevIcon[i]=ic; } }
  }
};

MagLockHandler handler;

// =====================================================================
void setup() {
  Wire.begin();
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
  cfg.capabilities = CAPS; cfg.capabilityCount = 1;
  cfg.otaPassword = "punisher";     // OTA only in the safe state
  // cfg.webConfigPortal = true;     // default: unconfigured -> AP + web setup
  dev.begin(cfg, handler);
  handler.loadEnvelope();          // web config portal if applicable, then NVS overrides
}

void loop() {
  dev.loop();
}
