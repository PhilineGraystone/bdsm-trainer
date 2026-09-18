// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  PunisherDevice — common device base of the Punisher installation (ESP32)
//
//  Contract: see project document 07-firmware-framework.md
//
//  The base takes over everything they have in common:
//    WiFi, MQTT (reconnect, LWT, keepalive), subscriptions, hello/response,
//    time-based heartbeat, watchdog on the central unit's heartbeat,
//    registration (slave_id/slave_name), command envelope with TTL,
//    EMERGENCY (freeze until power cycle), state/event/log publishers,
//    OTA only in the safe state, hardware watchdog, debouncing.
//
//  The device supplies a PunisherHandler with:
//    safeState()   — harmless immediately (mandatory)
//    onCommand()   — device-specific actions (mandatory)
//    onTick()      — periodic logic of its own
//    reportState() — state fields
//    isActive()    — is an action running right now? (controls the heartbeat
//                    rate, the OTA lock, the central-unit watchdog)
//    onPunish()/onReward() — punishment/reward channel (stimulators only)
//
//  Event classes (doc 14, mandatory since 3.1.0): every event carries
//  "cls" — punish (punishment carried out), warn (warning signal), fault
//  (violation by a device without a stimulator: the central unit decides it),
//  reward, pause, result (end of a run with metrics), info (the rest).
//  The central unit counts punishments at the execution, not at the dispatch.
//
//  Reading channel (doc 19 5.2, since 3.2.0): punisher/slaves/<slave_id>/live,
//  likewise published only by the central unit. A device that couples its
//  output to the performance sets cfg.liveListener and gets onLive(). No
//  envelope, no answer: a reading is state, not an instruction. Missing
//  fields stay pessimistic (doc 19: missing != 0).
//
//  Punishment channel (doc 14 3a): punisher/slaves/<slave_id>/punish|reward,
//  published exclusively by the central unit in the cmd envelope
//  {action:"punish", args:{level,kind,reason,source}, id, ts_ms, ttl_ms}.
//  A stimulator sets cfg.punishListener = true and names its kinds
//  (punishKinds, e.g. "shock","vibe"); the base subscribes to the channel on
//  the assignment of a slave, unsubscribes on release, checks id/TTL/kind
//  and calls onPunish(). Everything else (the envelope!) the device decides.
// =====================================================================
#pragma once

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <WiFiClientSecure.h>
#include <Arduino_JSON.h>
#include <Preferences.h>

// --------------------------------------------------------------------- //
struct PunisherConfig {
  // Network
  const char* ssid;
  const char* password;
  const char* broker;
  uint16_t    port          = 1883;
  // TLS to the broker (2.3, project document 53). Off by default: clear text
  // on 1883 is the state of the repository, so that a rebuild runs without a
  // certificate having to exist first. With `true` the device speaks TLS —
  // and checks the certificate only if src/PunisherCa.h carries one. Empty
  // there means: encrypt, do not check. That protects against listening in,
  // not against somebody who actively redirects in the WLAN; he cannot give
  // an order either way, because every command is signed.
  bool        tls           = false;
  // Wipe the stored configuration (NVS) at this start and say so. Set by the
  // sketch from PUNISHER_NVS_CLEAR in creds.h; see begin() for the reason.
  bool        clearNvs      = false;
  const char* mqttUser;
  const char* mqttPass;
  const char* clientId;

  // Identity.
  //
  // modelUuid is compiled in and says WHAT the device is (decision
  // 2026-09-06). deviceUuid says WHICH one it is — and from 2.0 on it is no
  // longer set, but DERIVED from the efuse MAC and the chip type
  // (PunisherIdentity.h). The field remains only as a way to read: begin()
  // fills it, after that the device's own UUID stands here. A value a sketch
  // writes in here beforehand is overwritten.
  const char* modelUuid;
  const char* deviceUuid          = nullptr;   // output, not input

  // Version of the sketch. The name is only a name; the comparison goes over
  // the three numbers (see PunisherVersion.h).
  const char* sketchName          = "";
  uint16_t    sketchMajor         = 0;
  uint16_t    sketchMinor         = 0;
  uint16_t    sketchPatch         = 0;

  // Project key for the signature (HMAC-SHA256). Without it the device
  // registers unsigned, and the central unit rejects it.
  const char* projectKey          = nullptr;

  const char* const* capabilities = nullptr;
  size_t      capabilityCount     = 0;

  // OTA: nullptr = off. Otherwise allowed only in the safe state.
  const char* otaPassword   = nullptr;

  // Times (ms)
  // Decision Philine 2026-09-06: 120 s instead of 3 s. The installation runs in
  // a 2.4 GHz WLAN in a public space; short dropouts are normal, and within
  // the controlled setting with a supervisor present (emergency-stop bumper)
  // a radio dropout should not release a lock.
  unsigned long centralTimeoutMs   = 120000;  // central unit silent while an action runs -> safeState
  unsigned long brokerFailsafeMs   = 120000;  // broker gone -> safeState
  unsigned long reconnectMs        = 5000;
  unsigned long heartbeatIdleMs    = 10000;
  unsigned long heartbeatActiveMs  = 5000;
  unsigned long stateIntervalMs    = 30000;   // periodic state, in addition to changes
  unsigned long cmdDefaultTtlMs    = 5000;    // when the envelope carries no ttl_ms
  uint32_t      wdtSeconds         = 15;      // hardware watchdog, 0 = off

  // 1536 since 2.0: the signed envelope costs 64 characters of signature plus
  // the escaping of the body. With 768 the longest commands fell through.
  uint16_t      mqttBufferSize     = 1536;
  uint16_t      mqttKeepAliveS     = 15;
  bool          serialLog          = true;

  // One-time configuration via the web interface: if the device is not
  // provisioned (no stored state in NVS), it opens an access point and a
  // config web form at boot. The compiled-in values (from the prototypes) are
  // the defaults in the form. After saving, the device boots normally (STA).
  // A 'factory_reset' command resets it.
  bool          webConfigPortal    = true;
  const char*   apPassword         = "punisher-setup";  // AP of the config portal

  // Punishment/reward channel per slave (doc 14 3a). Only devices WITH a
  // stimulator set punishListener; punishKinds names the kinds the device can
  // carry out ("shock", "vibe", "strike", ...). kind:"any" hits every
  // listening device. Devices without a stimulator (TaskPad, trainer) report
  // fault events instead.
  bool                punishListener   = false;
  const char* const*  punishKinds      = nullptr;
  size_t              punishKindCount  = 0;
  bool                rewardListener   = false;
  const char* const*  rewardKinds      = nullptr;
  size_t              rewardKindCount  = 0;

  // Reading channel of the slave (doc 19 §5.2), since 3.2.0. Only devices that
  // COUPLE their output to the performance (e-stim bridge) set this. The base
  // subscribes to `punisher/slaves/<id>/live` with the assignment and calls
  // onLive(). No command envelope: a reading is state, not an instruction —
  // hence no id/TTL check. How old a value may be, the device decides.
  bool                liveListener     = false;
};

// Reading of the slave (doc 19 §5.2). The central unit is the only publisher
// on this channel and already converts "away" into silence; the device checks
// it itself nonetheless.
//
// MISSING IS NOT ZERO: if a field does not come along, it stays pessimistic —
// depth 0 (no depth, no share) and err 1.0 (accuracy unknown, no share).
// err = 0.0 on the other hand is the PERFECT run and earns the full share.
// The have flags stand beside it, in case a device wants to look more closely.
struct PunisherLive {
  float         depth     = 0.0f;   // 0..100 % of the slave's own range
  float         err       = 1.0f;   // 0..1 normalised error against the tolerance band
  bool          away      = true;   // she is away → every track to zero
  bool          valid     = false;  // measurement usable
  bool          haveDepth = false;
  bool          haveErr   = false;
  unsigned long atMs      = 0;      // millis() of receipt (freshness check)
};

// Request from the punishment/reward channel (pre-checked: id, TTL, kind).
struct PunisherRequest {
  uint8_t       level;      // 1..3 abstract strength level; the device maps it onto its envelope
  const char*   kind;       // "any" | "shock" | "vibe" | "strike" | ...
  const char*   reason;     // e.g. "nose_button_lost", "attention_missed"
  const char*   source;     // device_UUID of the triggering device or "central"
  unsigned long id;         // cmd-id — report it back in the punish event as "cid" (matching in the central unit)
  JSONVar*      args;       // complete args (device-specific additions)
};

// --------------------------------------------------------------------- //
enum PunisherState : uint8_t {
  PD_BOOT = 0,
  PD_IDLE,        // connected, waiting
  PD_ACTIVE,      // device reports isActive()
  PD_EMERGENCY    // frozen until power cycle
};

class PunisherDevice;

class PunisherHandler {
 public:
  virtual ~PunisherHandler() {}
  // Mandatory: put the device into the harmless state immediately. Must be
  // idempotent and must not block.
  virtual void safeState() = 0;
  // Mandatory: carry out the action. false + err = refused (reported as an event).
  virtual bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) = 0;

  virtual void onTick(unsigned long nowMs) {}
  virtual void reportState(JSONVar& out) {}
  // The envelope of the device for the `hello` (since 3.3.0): what it lets
  // through AT MOST, with the keys from libs/devicemodels.ENVELOPE_KEYS
  // (zap_max, mode_max_min, tx_max_ms, lock_minutes_max ...). The installation
  // limits its forms with it, instead of offering values the device caps
  // anyway. Leaving it empty means: the central unit takes the model catalogue.
  virtual void reportLimits(JSONVar& out) { (void) out; }
  // What the device cannot use TODAY (2.2.0, doc 42 point 4): component ids
  // into `out`, e.g. out[0] = "cuff3", or "stuck:cuff2" for a component that
  // is a safety case rather than a missing one. The central unit narrows the
  // model's capabilities by this — it never widens them: a device can only
  // ever report itself smaller. Leaving it empty means: everything works.
  // Polled every few seconds; a change re-sends the hello.
  virtual void reportDegraded(JSONVar& out) { (void) out; }
  virtual bool isActive() { return false; }
  virtual void onRegistered(uint16_t slaveId, const char* slaveName) {}
  virtual void onUnregistered() {}
  virtual void onEmergency(const char* source) {}
  virtual void onCentralLost() {}
  virtual void onCentralBack() {}
  virtual void onIdentify() {}
  virtual void onConnected() {}
  // Punishment/reward channel (only if cfg.punishListener/rewardListener).
  // false + err = refused (event punish_rejected / reward_rejected).
  virtual bool onPunish(const PunisherRequest& r, char* err, size_t errLen) { (void) r; snprintf(err, errLen, "no punish"); return false; }
  virtual bool onReward(const PunisherRequest& r, char* err, size_t errLen) { (void) r; snprintf(err, errLen, "no reward"); return false; }
  // Reading of the slave (only if cfg.liveListener). No answer, no refusal:
  // it is an observation, not an order.
  virtual void onLive(const PunisherLive& live) { (void) live; }
};

// --------------------------------------------------------------------- //
class PunisherDevice {
 public:
  PunisherDevice();

  void begin(const PunisherConfig& cfg, PunisherHandler& handler);
  void loop();

  // --- Publishing ----------------------------------------------------
  // Event classes: "punish" | "warn" | "fault" | "reward" | "pause" | "result" | "info"
  void publishState();                                   // immediately
  void publishEvent(const char* event, const char* cls = "info");                // {"event":..,"cls":..}
  void publishEvent(const char* event, JSONVar& data, const char* cls = "info"); // {"event":.., ...data}
  // Answer to a command (since 3.2.0). Goes to devices/<uuid>/response —
  // there the central unit expects the acknowledgement of a transfer, unlike
  // the event stream. Needed e.g. for routine_commit: a refusal with
  // "routine" in the text makes the central unit send the waveform again.
  void publishResponse(JSONVar& j);
  void logf(const char* level, const char* fmt, ...);    // Serial + MQTT log
  void requestEmergency(const char* source);             // device triggers it itself

  // --- State ---------------------------------------------------------
  PunisherState state() const { return _state; }
  bool isEmergency() const { return _state == PD_EMERGENCY; }
  bool isRegistered() const { return _slaveId > 0; }
  uint16_t slaveId() const { return _slaveId; }
  const char* slaveName() const { return _slaveName; }
  bool centralAlive() const { return _centralAlive; }
  bool mqttConnected() { return _mqtt.connected(); }
  // Time of the central unit (ms), as soon as a heartbeat has arrived; else millis()
  unsigned long long centralNowMs() const;
  bool hasCentralTime() const { return _haveOffset; }

  // --- One-time configuration (NVS) -----------------------------------
  // Readable by the device code; the default holds as long as nothing is stored.
  // The config console can set any key, device-specific ones included.
  long   cfgInt(const char* key, long def);
  String cfgStr(const char* key, const char* def);
  // SET a device-specific value (since 3.3.0). For things that are settled in
  // operation instead of at assembly — such as binding a bridge to exactly
  // one BLE device. An empty value deletes the key.
  // Device-specific keys only: network and identity stay reserved for the
  // config portal, so that a device cannot lock itself out of the
  // installation by command.
  bool   cfgSet(const char* key, const char* value);

  PubSubClient& raw() { return _mqtt; }

  // Leave a breadcrumb in the trace that survives a watchdog reset (2.3.1).
  // Only 50..59; the framework keeps the rest for itself. Costs two stores
  // and is compiled away entirely with PUNISHER_PHASE_TRACE 0.
  void phase(uint16_t n);

 private:
  PunisherConfig   _cfg;
  PunisherHandler* _h = nullptr;
  WiFiClient       _wifi;
  // The TLS client sits next to the plain one instead of replacing it: which
  // of the two PubSubClient gets is decided in begin() from the config, and a
  // WiFiClientSecure that is never connected costs a handful of bytes — the
  // mbedTLS context is only allocated on connect().
  WiFiClientSecure _wifiTls;
  PubSubClient     _mqtt;
  PunisherState    _state = PD_BOOT;

  // NVS + buffer for overridden connection/identity values.
  // The _cfg pointers are bent onto these strings when NVS has values.
  Preferences _prefs;
  String _sSsid, _sPass, _sBroker, _sUser, _sMqttPass, _sClient, _sModelUuid;

  // Own identity, read from the efuse resp. derived from it in begin().
  // _ownUuid carries _cfg.deviceUuid — the pointer points here, so the buffer
  // must not fall away.
  // Signature: build and open the envelope. The transmitted string is the
  // signed one — there is nothing to canonicalise.
  String signEnvelope(const char* topic, const String& body);
  bool   openEnvelope(const char* topic, const char* raw, String& out);

  uint8_t _ownMac[6]  = {0};
  char    _ownUuid[37] = {0};
  char    _ownMacTxt[18] = {0};

  uint16_t _slaveId = 0;
  char     _slaveName[32] = {0};

  // Topics (precomputed)
  char _tAvailable[96], _tResponse[96], _tHello[96], _tState[96], _tEvent[96],
       _tLog[96], _tSettings[96], _tCmd[96], _tEmergency[96];
  // Channel topics of the assigned slave (empty = not subscribed)
  char _tPunish[64] = {0}, _tReward[64] = {0}, _tLive[64] = {0};

  // Times
  unsigned long _lastReconnect = 0, _disconnectedSince = 0;
  unsigned long _lastHeartbeat = 0, _lastState = 0, _lastCentral = 0;
  unsigned long _wifiBeginMs = 0;              // start of the current WLAN attempt

  // Serial console. `_conConfirm` holds the deadline for the confirmation of
  // a destructive command; 0 means nothing is waiting. A command that clears
  // a device must not be one stray byte away (2.3.2).
  char          _conBuf[80] = {0};
  uint8_t       _conLen = 0;
  unsigned long _conConfirm = 0;
  static const unsigned long WIFI_RETRY_MS = 30000;  // after that a fresh begin()
  bool          _brokerFailsafeFired = false;
  bool          _centralAlive = false;
  bool          _haveOffset = false;
  long long     _centralOffsetMs = 0;   // central_ts - millis()
  long long     _lastCentralTsMs  = 0;  // last ACCEPTED heartbeat: only forwards (2.1.0)
  long long     _lastLiveTsMs     = 0;  // last ACCEPTED reading: likewise (2.1.0)
  char*         _rx               = nullptr;  // receive buffer, mqttBufferSize bytes (2.1.1)
  uint16_t      _rxCap            = 0;
  // Boot trace (2.2.0): this life's id and what the last one left behind.
  char          _bootId[9]        = {0};
  const char*   _resetReason      = "unknown";
  bool          _haveTrace        = false;
  uint32_t      _prevUptimeS      = 0;
  char          _prevCmd[24]      = {0};
  char          _prevErr[64]      = {0};
  unsigned long _traceWrittenMs   = 0;
  // Degraded components as last reported (2.2.0); a change re-sends the hello.
  String        _degradedLast;
  unsigned long _degradedCheckMs  = 0;
  bool          _otaStarted = false;
  bool          _wdtStarted = false;    // task registered with the TWDT (only after setupWdt)

  // Duplicate protection for cmd ids (ring of the last N ids; cmd and channel
  // share the ring — the central unit issues both ids from ONE sequence)
  static const uint8_t CMD_ID_RING = 8;
  unsigned long _cmdIds[CMD_ID_RING] = {0};
  uint8_t       _cmdIdPos = 0;

  // Internal
  void connectWifi(unsigned long now);
  bool connectMqtt();
  void subscribeAll();
  void onMessage(char* topic, uint8_t* payload, unsigned int len);
  void handleSettings(JSONVar& j);
  void handleCmd(JSONVar& j);
  void handleChannel(JSONVar& j, bool punish);
  void handleLive(JSONVar& j);
  bool seenCmdId(JSONVar& j, const char* what);
  bool staleCmd(JSONVar& j, const char* what);
  bool kindMatches(const char* kind, const char* const* list, size_t n);
  void updateChannelSubscriptions(uint16_t oldId, uint16_t newId);
  void handleCentralHeartbeat(JSONVar& j);
  void touchCentral();
  void enterEmergency(const char* source);
  void goSafe(const char* reason);
  void publishHello();
  void publishHeartbeat();
  void publishRaw(const char* topic, const char* payload, bool retain = false);
  void publishJson(const char* topic, JSONVar& j, bool retain = false);
  void setupOta();
  void setupClock();      // build time into the RTC, before the TLS handshake (2.3)
  void setupWdt();
  void feedWdt();
  void topic(char* dst, size_t n, const char* suffix);

  void applyStoredConfig();          // apply NVS overrides to _cfg
  bool isProvisioned();

  // Serial console (2.3.2): `help`, `show`, `nvs clear`, `reboot`. Reads
  // whole lines without ever blocking — everything here runs inside loop(),
  // where a wait of more than a few milliseconds is a watchdog reset.
  void serialConsole();
  void consoleLine(String line);
  void consoleShow();
  void runConfigPortal();            // AP + web form, blocks until saved
  String configFormHtml();
  void factoryReset();               // clear NVS + reboot

  static PunisherDevice* _instance;
  static void _mqttCallback(char* topic, uint8_t* payload, unsigned int len);
};

// --------------------------------------------------------------------- //
//  Small debouncer for switches/sensors
// --------------------------------------------------------------------- //
class Debounced {
 public:
  Debounced(uint8_t pin, int activeLevel = LOW, unsigned long stableMs = 30)
    : _pin(pin), _active(activeLevel), _stableMs(stableMs) {}
  void begin(int mode = INPUT_PULLUP) {
    pinMode(_pin, mode);
    _raw = _stable = (digitalRead(_pin) == _active);
    _since = millis();
  }
  // true when the stable state has changed
  bool update() {
    bool r = (digitalRead(_pin) == _active);
    unsigned long now = millis();
    if (r != _raw) { _raw = r; _since = now; }
    if (r != _stable && (now - _since) >= _stableMs) { _stable = r; return true; }
    return false;
  }
  bool active() const { return _stable; }
 private:
  uint8_t _pin; int _active; unsigned long _stableMs;
  bool _raw = false, _stable = false; unsigned long _since = 0;
};
