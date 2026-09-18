// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#include "PunisherDevice.h"
#include "PunisherVersion.h"
#include "PunisherIdentity.h"
#include "PunisherCrypto.h"
#include <ArduinoOTA.h>
#include <esp_task_wdt.h>
#include <esp_idf_version.h>
#include <esp_system.h>
#include <sys/time.h>
#include <time.h>
#include <string.h>

#include "PunisherCa.h"
#include <WebServer.h>
#include <DNSServer.h>
#include <stdarg.h>

PunisherDevice* PunisherDevice::_instance = nullptr;

// --------------------------------------------------------------------- //
// WHAT THE LAST LIFE LEFT BEHIND (2.2.0, decision Philine 2026-09-16)
//
// "MagLock restarted three times today because of a brownout" beats
// "something was odd". For that the device has to tell the central unit, at
// every start, WHY it restarted and what it was doing just before — and the
// second half survives only in memory that a reset does not clear.
//
// The `RTC_NOINIT` attribute is exactly that: RTC slow memory, untouched by every reset
// the chip can perform on itself (software, panic, watchdogs, brownout). It
// does NOT survive a power cut, and it is garbage after one — which is why
// there is a magic word: a start without the word is a start after power
// loss, and the values are reported as unknown rather than as zero. Zero
// would be a lie with a number in it.
//
// The uptime is written once a second in loop(), not on every message: an
// RTC write costs nothing worth mentioning, and a second of imprecision in
// "how long did it run before it died" is not worth a write per command.
// WHERE THE LOOP WAS WHEN IT STOPPED COMING BACK (2.3.1, diagnosis)
//
// A task watchdog reset prints a backtrace, and on a dual-core ESP32 that
// backtrace is of whatever ran at that instant — which, when loopTask is
// BLOCKED rather than busy, is the idle task. It then names
// `esp_vApplicationIdleHook` and says nothing at all about where loopTask
// hangs (finding at the collar, 2026-09-16).
//
// So the loop leaves a breadcrumb instead: the number of the section it
// entered last, and the millisecond it entered it. Both live in the same RTC
// memory as the rest of the trace, so they survive the reset that follows,
// and the next start prints them. Two stores per section, no serial output
// while it runs — a device that is hanging must not be slowed down by the
// thing that is supposed to observe it.
//
// OFF BY DEFAULT since 2.3.2. It gave up the place the loop was stuck on
// 2026-09-16 and is, after that, what it is: a tool for a fault that is not
// happening. At 0 nothing of this section reaches the binary — the macro is
// an empty block. Whoever needs it again writes a 1.
#ifndef PUNISHER_PHASE_TRACE
#define PUNISHER_PHASE_TRACE 0
#endif

namespace {
// "PUN2": the layout grew. The old word would make a start after the update
// read the new fields out of the old positions — garbage with a number in it.
constexpr uint32_t PUN_RTC_MAGIC = 0x50554e32u;      // "PUN2"
struct PunRtcTrace {
  uint32_t magic;
  uint32_t uptimeS;        // seconds since the previous start
  uint32_t bootCount;      // starts since the last power loss
  char     lastCmd[24];    // last command action handled
  char     lastErr[64];    // last logf("error"|"warn") text
  uint16_t phase;          // section of loop()/begin() entered last
  uint32_t phaseMs;        // millis() when it was entered
  uint32_t heapFree;       // free heap at the last full second
  uint32_t heapMax;        // largest contiguous block at the same moment
};
RTC_NOINIT_ATTR PunRtcTrace g_trace;

#if PUNISHER_PHASE_TRACE
// The sections. The numbers are what the next start prints; the names are so
// that nobody has to count lines in this file to read them.
struct PunPhase { uint16_t n; const char* name; };
constexpr PunPhase PUN_PHASES[] = {
  { 10, "begin: Watchdog" },      { 11, "begin: WLAN starten" },
  { 12, "begin: TLS" },           { 13, "begin: Puffer" },
  { 14, "begin: fertig" },
  { 20, "loop: Anfang" },         { 21, "loop: Bauteilpruefung" },
  { 22, "loop: WLAN" },           { 23, "loop: MQTT getrennt" },
  { 24, "loop: verbinden" },      { 25, "loop: OTA" },
  { 26, "loop: Notfall" },        { 27, "loop: Zentralen-Watchdog" },
  { 28, "loop: Zustand senden" }, { 29, "loop: Eigenlogik" },
  { 30, "loop: Herzschlag" },     { 31, "loop: Ende" },
  { 40, "verbinden: connect" },   { 41, "verbinden: available" },
  { 42, "verbinden: abonnieren" },{ 43, "verbinden: hello" },
  { 44, "verbinden: Herzschlag" },{ 45, "verbinden: Zustand" },
  { 46, "verbinden: onConnected" },
  // 50..59 belong to the sketch. The framework cannot name what a sketch
  // does, so it reserves the range and the sketch fills it — see
  // PunisherDevice::phase() and the collar's onTick().
  { 50, "Sketch: IMU" },          { 51, "Sketch: RSSI" },
  { 52, "Sketch: Modus" },        { 53, "Sketch: Impuls" },
  { 54, "Sketch: Anzeige" },      { 55, "Sketch: Ende" },
};
const char* phaseName(uint16_t n) {
  for (const PunPhase& p : PUN_PHASES) if (p.n == n) return p.name;
  return "?";
}
#endif  // PUNISHER_PHASE_TRACE

#if PUNISHER_PHASE_TRACE
#define PUN_PHASE(n) do { g_trace.phase = (n); g_trace.phaseMs = millis(); } while (0)
#else
#define PUN_PHASE(n) do { } while (0)
#endif

const char* resetReasonName(esp_reset_reason_t r) {
  switch (r) {
    case ESP_RST_POWERON:   return "poweron";
    case ESP_RST_EXT:       return "external";
    case ESP_RST_SW:        return "software";
    case ESP_RST_PANIC:     return "panic";
    case ESP_RST_INT_WDT:   return "int_wdt";
    case ESP_RST_TASK_WDT:  return "task_wdt";
    case ESP_RST_WDT:       return "wdt";
    case ESP_RST_DEEPSLEEP: return "deepsleep";
    case ESP_RST_BROWNOUT:  return "brownout";
    case ESP_RST_SDIO:      return "sdio";
    default:                return "unknown";
  }
}
}  // namespace

// Forward: the definition is below with the other signature functions,
// but it is already needed in onMessage().
static bool topicIsSigned(const char* topic);

PunisherDevice::PunisherDevice() : _mqtt(_wifi) {}

// --------------------------------------------------------------------- //
void PunisherDevice::topic(char* dst, size_t n, const char* suffix) {
  snprintf(dst, n, "punisher/devices/%s/%s", _cfg.deviceUuid, suffix);
}

void PunisherDevice::begin(const PunisherConfig& cfg, PunisherHandler& handler) {
  _cfg = cfg;
  _h   = &handler;
  _instance = this;

  Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
  // ESP32-S3 & co. with native USB: Serial is a CDC connection that only
  // comes up once the PC has opened it. Without this short wait the first
  // lines (AP name of the config portal!) are lost. After 1.5 s it carries on,
  // so that a device without a connected PC does not hang.
  unsigned long _cdc = millis();
  while (!Serial && (millis() - _cdc) < 1500) delay(10);
#endif
  delay(50);
  // Deliberately early and unconditional: this is the first sign of life of
  // the application. If nothing follows, the device is hanging in the config
  // portal (normal on the first start) - if nothing comes at all, Serial talks
  // on a different port than the ROM bootloader (on S3: "USB CDC On Boot").
  Serial.printf("\n[PunisherDevice] %s %s boot\n",
                cfg.clientId ? cfg.clientId : "?", cfg.sketchName ? cfg.sketchName : "?");

  // The device always starts safe.
  _h->safeState();
  _state = PD_BOOT;

  // Read what the previous life left, THEN start this one's record. The order
  // matters: everything below this point may log, and a log line would
  // overwrite the error we are about to report.
  _resetReason = resetReasonName(esp_reset_reason());
  if (g_trace.magic == PUN_RTC_MAGIC) {
    _prevUptimeS = g_trace.uptimeS;
    strncpy(_prevCmd, g_trace.lastCmd, sizeof(_prevCmd) - 1); _prevCmd[sizeof(_prevCmd) - 1] = 0;
    strncpy(_prevErr, g_trace.lastErr, sizeof(_prevErr) - 1); _prevErr[sizeof(_prevErr) - 1] = 0;
    _haveTrace = true;
    g_trace.bootCount++;
  } else {
    _haveTrace = false;               // power loss, or first start ever: nothing to report
    memset(&g_trace, 0, sizeof(g_trace));
    g_trace.magic = PUN_RTC_MAGIC;
    g_trace.bootCount = 1;
  }
#if PUNISHER_PHASE_TRACE
  // Read the breadcrumb of the previous life BEFORE this one overwrites it.
  // It is only worth a line when the previous life ended badly — after a
  // normal restart the last section is simply "wherever it happened to be".
  uint16_t prevPhase = _haveTrace ? g_trace.phase : 0;
  uint32_t prevPhaseMs = _haveTrace ? g_trace.phaseMs : 0;
  uint32_t prevHeap = _haveTrace ? g_trace.heapFree : 0;
  uint32_t prevHeapMax = _haveTrace ? g_trace.heapMax : 0;
#endif
  g_trace.uptimeS = 0;
  g_trace.lastCmd[0] = 0;
  g_trace.lastErr[0] = 0;
  g_trace.phase = 0;
  g_trace.phaseMs = 0;
  g_trace.heapFree = 0;
  g_trace.heapMax = 0;
  // A fresh id for this life. Random, not a counter: a counter restarts from
  // one after a power loss, and the central unit would then see the same
  // (device, id) twice and drop the second start as a repetition.
  snprintf(_bootId, sizeof(_bootId), "%08lx", (unsigned long) esp_random());
  Serial.printf("[PunisherDevice] boot %s reason=%s prev_uptime=%s\n", _bootId, _resetReason,
                _haveTrace ? String(_prevUptimeS).c_str() : "unknown");
#if PUNISHER_PHASE_TRACE
  if (_haveTrace && prevPhase) {
    Serial.printf("[PunisherDevice] davor zuletzt: Phase %u (%s) bei %lu ms, "
                  "Heap %lu, groesster Block %lu\n",
                  (unsigned) prevPhase, phaseName(prevPhase),
                  (unsigned long) prevPhaseMs, (unsigned long) prevHeap,
                  (unsigned long) prevHeapMax);
  }
#endif

  // Load the NVS and, if needed, configure it once, BEFORE topics/network are
  // built from the (possibly overwritten) identity.
  // Identity first: the UUID is derived from the efuse MAC and the chip type
  // (PunisherIdentity.h) and can be set neither in creds.h nor in the
  // portal. One handle less that can be forgotten — and MAC
  // and UUID can no longer drift apart.
  pun::readBaseMac(_ownMac);
  pun::formatMac(_ownMac, _ownMacTxt);
  pun::deriveUuid(_ownMac, pun::chipType(), _ownUuid);
  _cfg.deviceUuid = _ownUuid;

  _prefs.begin("pun", false);
  // A RUNTIME FLAG, NOT AN #if: this file is compiled as a library and never
  // sees the sketch's creds.h. The sketch reads PUNISHER_NVS_CLEAR and hands
  // it over as cfg.clearNvs — the same road MQTT_TLS takes.
  if (_cfg.clearNvs) {
    // THE WAY OUT WHEN A STORED VALUE HAS OUTLIVED THE COMPILED ONE.
    //
    // Everything the setup portal or a `config` command ever saved wins over
    // creds.h — see applyStoredConfig(). That is right while the stored value
    // is the newer one, and wrong the moment creds.h moves on: a collar that
    // went through the portal before TLS kept `port = 1883` in its NVS, creds.h
    // said 8883, and the device talked TLS to the clear-text port until the
    // watchdog killed it (finding Philine 2026-09-16). The only other way to clear
    // the NVS is the `factory_reset` command — over MQTT, which a device that
    // cannot connect never receives.
    //
    // So: a switch in creds.h, flashed at the device, with a cable. It wipes
    // on EVERY start while it is 1 and says so, loudly, each time — the same
    // rule as BURN_MAC_FUSES: an action that runs at every start is announced
    // at every start, so nobody forgets to switch it back.
    Serial.println(F("[PunisherDevice] NVS WIRD GELOESCHT (PUNISHER_NVS_CLEAR 1 in creds.h)."));
    Serial.println(F("[PunisherDevice] Danach wieder auf 0 setzen und neu flashen, sonst bei jedem Start."));
    _prefs.clear();
    // And NOT into the portal afterwards. The portal is for a device whose
    // creds.h has nothing to say; this one was reset PRECISELY so that its
    // creds.h speaks again — and the build guards in PunisherCreds.h refuse
    // a creds.h that is incomplete. Whoever wants the portal instead has the
    // `factory_reset` command, which clears and does not set this flag.
    _prefs.putBool("provisioned", true);
    Serial.println(F("[PunisherDevice] Es gelten wieder die Werte aus creds.h; kein Portal."));
  }
  applyStoredConfig();
  if (_cfg.webConfigPortal && !isProvisioned()) {
    runConfigPortal();      // blocks; on "Save" a reboot follows
    applyStoredConfig();    // (only reached if the portal ends without saving)
  }

  // Topics only now — deviceUuid may have been changed by the config.
  topic(_tAvailable, sizeof(_tAvailable), "available");
  topic(_tResponse,  sizeof(_tResponse),  "response");
  topic(_tHello,     sizeof(_tHello),     "hello");
  topic(_tState,     sizeof(_tState),     "state");
  topic(_tEvent,     sizeof(_tEvent),     "event");
  topic(_tLog,       sizeof(_tLog),       "log");
  topic(_tSettings,  sizeof(_tSettings),  "settings");
  topic(_tCmd,       sizeof(_tCmd),       "cmd");
  topic(_tEmergency, sizeof(_tEmergency), "emergency");

  PUN_PHASE(10);
  setupWdt();

  PUN_PHASE(11);
  WiFi.persistent(false);          // no flash writes on every begin()
  WiFi.setHostname(_cfg.clientId);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);     // the core takes care of reconnects after a connection loss
  WiFi.begin(_cfg.ssid, _cfg.password);
  _wifiBeginMs = millis();

  // ---------------------------------------------------------------- //
  // TLS (2.3, project document 53)
  //
  // Up to 2.2 everything on the way over the WLAN was in the clear — states,
  // names, pulse levels, and on every connect the password of the device
  // account. This closes that. Whether the certificate is also CHECKED is
  // decided by PunisherCa.h: a certificate there means a pin on exactly that
  // one, an empty file means encrypt without checking. Both are legitimate
  // and the log says which of the two is running, because from the outside
  // the difference is invisible.
  PUN_PHASE(12);
  if (_cfg.tls) {
    setupClock();
    if (punca::isRealCa(PUNISHER_CA_CERT)) {
      _wifiTls.setCACert(PUNISHER_CA_CERT);
      Serial.println(F("MQTT: TLS, Zertifikat wird geprueft"));
    } else {
      // setInsecure() and not "no TLS": the handshake happens, the traffic is
      // encrypted, only the identity of the other end is not established.
      _wifiTls.setInsecure();
      Serial.println(F("MQTT: TLS, Zertifikat NICHT geprueft"));
    }
    // THE HANDSHAKE HAS TO FIT UNDER THE WATCHDOG (2.3.1).
    //
    // `setSocketTimeout(5)` further down bounds what PubSubClient waits for —
    // the CONNACK. It does NOT bound the TLS handshake underneath. That one
    // has its own limit inside WiFiClientSecure, and the default is 120
    // SECONDS. Against a watchdog of `wdtSeconds` that is not a timeout, it
    // is a reset: a broker that accepts the TCP connection and then says
    // nothing blocks connectMqtt() inside loop() until the watchdog reboots
    // the device — precisely the failure mode setSocketTimeout() was put
    // there to rule out (finding Philine 2026-09-16, magcuff).
    //
    // BOTH BRAKES, NOT ONE. In 2.3.1 only setHandshakeTimeout() stood here,
    // and I took setTimeout() out on the grounds that it had been a stub in
    // WiFiClientSecure for several core versions (arduino-esp32 issues 6429
    // and 7355). That reasoning was about OLD cores and it was wrong for this
    // one: setTimeout() is inherited from NetworkClient, where it sets the
    // socket receive timeout — and that is the only thing that bounds a recv
    // which is already BLOCKED.
    //
    // The difference matters because the two limits cover different failures.
    // setHandshakeTimeout() is checked in the handshake loop between socket
    // operations; it ends a handshake that keeps coming back with "want read".
    // It cannot end one that is sitting inside a blocking recv — that hang is
    // documented and unfixed (arduino-esp32 issue 5928), and it is what a
    // collar with TLS did here on 2026-09-16 while the same firmware on an S3
    // came through.
    //
    // Derived from the watchdog, never a fixed number: whoever raises or
    // lowers wdtSeconds in a sketch must not have to remember these lines as
    // well. A third of it leaves room for the name lookup and the TCP
    // connect, which happen in the same pass through loop().
    uint32_t hs = _cfg.wdtSeconds ? (_cfg.wdtSeconds / 3) : 10;
    if (hs < 2) hs = 2;
    _wifiTls.setHandshakeTimeout(hs);
    _wifiTls.setTimeout(hs);
    Serial.printf("MQTT: TLS-Handshake und Socket hoechstens %us (Watchdog %us)\n",
                  (unsigned) hs, (unsigned) _cfg.wdtSeconds);
    _mqtt.setClient(_wifiTls);
  } else {
    Serial.println(F("MQTT: ohne TLS (Klartext)"));
  }
  PUN_PHASE(13);
  _mqtt.setServer(_cfg.broker, _cfg.port);
  _mqtt.setBufferSize(_cfg.mqttBufferSize);
  // The receive buffer of the callback is the SAME size as the one PubSubClient
  // was just given — allocated once, here, and never again. Until 2.1.1 the
  // callback had its own fixed 1 KB array on the stack and refused anything
  // from 990 bytes on, while the sketch had raised the library buffer to 1536
  // (the bridge to 2048). The library accepted the packet, the callback threw
  // it away, and the log said "payload too large" for a message that was
  // entirely within the contract: a `routine_chunk` with 50 points and large
  // values is 1046 bytes in its envelope (finding Philine 2026-09-15).
  //
  // Heap, not stack: 2 KB on the loop task's stack is not nothing, and the
  // envelope is unpacked into a second copy right next to it.
  _rxCap = _cfg.mqttBufferSize;
  _rx = (char*) malloc(_rxCap);
  if (!_rx) { _rxCap = 0; logf("error", "no memory for the receive buffer"); }
  _mqtt.setKeepAlive(_cfg.mqttKeepAliveS);
  // Review 2026-09-10: on connect() PubSubClient waits up to 15 s for the
  // CONNACK (default) — exactly the watchdog time. A broker that accepts TCP
  // but does not answer would otherwise have triggered a WDT reset.
  _mqtt.setSocketTimeout(5);
  _mqtt.setCallback(_mqttCallback);
  PUN_PHASE(14);
}

// --------------------------------------------------------------------- //
// A clock, roughly, before the first TLS handshake. (2.3)
//
// THE DEVICE HAS NO CLOCK OF ITS OWN. It learns the time from the central
// unit's heartbeat (`_centralOffsetMs`) — and that arrives AFTER the MQTT
// connection, which is to say after the TLS handshake. mbedTLS checks a
// certificate's validity dates against the system clock, and that one stands
// at 1970 on every start: every certificate is then "not yet valid", the
// handshake fails, no connection is made, no heartbeat arrives, and the clock
// stays at 1970. Hen and egg, and the usual way TLS dies on an ESP32.
//
// So the clock is set to the BUILD TIME. It is wrong — by as long as the
// firmware has been running — but it is wrong in the only direction that is
// harmless here: never before the certificate was issued. What it cannot
// notice is an EXPIRED certificate, and that is the price. It is only paid by
// installations that check at all (PunisherCa.h); with an empty CA file
// mbedTLS checks no dates and this function only makes the log timestamps
// plausible.
//
// No NTP. Without the check nobody needs the exact time, and a service that
// has to answer before the first connection is one more thing that can fail
// in a room without internet.
// The sketch's way into the breadcrumb trail. Numbers 50..59 are reserved for
// it; anything else would overwrite a section of the framework and make the
// trace point at the wrong place — which is worse than no trace, because it
// looks like an answer.
void PunisherDevice::phase(uint16_t n) {
#if PUNISHER_PHASE_TRACE
  if (n >= 50 && n <= 59) PUN_PHASE(n);
#else
  (void) n;
#endif
}

// --------------------------------------------------------------------- //
void PunisherDevice::setupClock() {
  struct tm tm = {};
  char mon[4] = {0};
  int day = 0, year = 0, h = 0, m = 0, sec = 0;
  if (sscanf(__DATE__, "%3s %d %d", mon, &day, &year) != 3) return;
  if (sscanf(__TIME__, "%d:%d:%d", &h, &m, &sec) != 3) return;
  static const char* MONTHS = "JanFebMarAprMayJunJulAugSepOctNovDec";
  const char* at = strstr(MONTHS, mon);
  if (!at) return;
  tm.tm_mon  = (at - MONTHS) / 3;
  tm.tm_mday = day;
  tm.tm_year = year - 1900;
  tm.tm_hour = h;
  tm.tm_min  = m;
  tm.tm_sec  = sec;
  time_t t = mktime(&tm);
  if (t <= 0) return;
  struct timeval tv = { .tv_sec = t, .tv_usec = 0 };
  settimeofday(&tv, nullptr);
}

// --------------------------------------------------------------------- //
void PunisherDevice::setupWdt() {
  if (_cfg.wdtSeconds == 0) return;
#if ESP_IDF_VERSION_MAJOR >= 5
  // ESP32 Arduino core 3.x / IDF 5.x: new struct API. The core already
  // initialises the TWDT (idle tasks) -> init then returns INVALID_STATE, we
  // only reconfigure. Otherwise init.
  esp_task_wdt_config_t twdt = {
    .timeout_ms     = _cfg.wdtSeconds * 1000,
    .idle_core_mask = 0,      // do not watch the idle tasks
    .trigger_panic  = true,   // reboot on timeout
  };
  // ASK FIRST, THEN ACT.
  //
  // Earlier this read init() and, when that returned INVALID_STATE,
  // reconfigure(). Technically right — but on the failed init the IDF itself
  // prints a RED error line ("TWDT already initialized"), and that then
  // appears at EVERY start of EVERY device. An error message that means
  // nothing is worse than none: it eventually costs somebody an evening,
  // and it gets everyone used to overlooking red lines.
  //
  // The Arduino core brings the TWDT along for the idle tasks anyway, so the
  // normal case is reconfigure().
  esp_err_t e = esp_task_wdt_reconfigure(&twdt);
  if (e != ESP_OK) e = esp_task_wdt_init(&twdt);
  esp_task_wdt_add(NULL);
#else
  // ESP32 Arduino core 2.x / IDF 4.x: old API (seconds + panic bool).
  esp_task_wdt_init(_cfg.wdtSeconds, true);
  esp_task_wdt_add(NULL);
#endif
  _wdtStarted = true;
}
void PunisherDevice::feedWdt() {
  // Only feed when this task is registered (the config portal runs BEFORE
  // setupWdt(); a reset() without registration only puts errors into the log).
  if (!_wdtStarted) return;
  esp_task_wdt_reset();
}

// --------------------------------------------------------------------- //
void PunisherDevice::setupOta() {
  // EMPTY means OTA is off — and that is the only way left to say it since
  // creds.h holds `constexpr char[]` instead of `const char*`: an array is
  // never a null pointer, so `if (!_cfg.otaPassword)` could no longer be false
  // for any sketch that sets the field at all. OTA would have come up with an
  // empty password (2.1.1, found while closing the finding of 2026-09-15).
  if (!_cfg.otaPassword || !_cfg.otaPassword[0] || _otaStarted) return;
  ArduinoOTA.setHostname(_cfg.clientId);
  ArduinoOTA.setPassword(_cfg.otaPassword);
  ArduinoOTA.setMdnsEnabled(true);          // announcement _arduino._tcp for the IDE
  ArduinoOTA.onStart([]() {
    // OTA only in the safe state: first release everything, then update.
    if (_instance && _instance->_h) _instance->_h->safeState();
    if (_instance) _instance->logf("info", "OTA start");
  });
  ArduinoOTA.onError([](ota_error_t e) {
    if (_instance) _instance->logf("warn", "OTA error %d", (int) e);
  });
  ArduinoOTA.begin();
  _otaStarted = true;
  logf("info", "OTA ready: host=%s.local ip=%s port=3232",
       _cfg.clientId, WiFi.localIP().toString().c_str());
}

// --------------------------------------------------------------------- //
void PunisherDevice::connectWifi(unsigned long now) {
  if (WiFi.status() == WL_CONNECTED) {
    if (_wifiBeginMs != 0 && _cfg.serialLog) {
      Serial.printf("WiFi: connected ssid=%s ip=%s host=%s rssi=%d\n",
                    WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(),
                    _cfg.clientId, WiFi.RSSI());
    }
    _wifiBeginMs = 0;
    return;
  }
  // Do NOT disturb a connection setup in progress: another WiFi.begin()
  // aborts the handshake ("sta is connecting, cannot set config").
  // Only start a fresh attempt after a real timeout.
  if (_wifiBeginMs == 0) { _wifiBeginMs = now; return; }   // AutoReconnect is running
  if (now - _wifiBeginMs < WIFI_RETRY_MS) return;
  _wifiBeginMs = now;
  if (_cfg.serialLog) Serial.println("WiFi: retry");
  WiFi.disconnect(false, false);
  delay(50);
  WiFi.begin(_cfg.ssid, _cfg.password);
}

bool PunisherDevice::connectMqtt() {
  // THE LAST WORD BELONGS ON `available`, NOT ON `state`.
  //
  // Until 2.1.0 the will sat on `state` and carried bare JSON. But `state` is
  // one of the SIGNED topics — and the will cannot be signed: the broker sends
  // it at a moment when this device has long stopped computing, so there is
  // nobody here to produce a signature with a fresh timestamp. The central unit
  // therefore threw the will away, every single time:
  //
  //     ERROR MQTT: <uuid> — Nachricht auf state abgewiesen:
  //                          Umschlagversion None statt 1
  //
  // and went on believing the device was there — kept its assignment to a
  // slave, kept sending commands into the void (finding Philine 2026-09-15).
  //
  // `available` is the topic the protocol MEANT for this; punsign.py says so in
  // as many words. It is deliberately unsigned, and the reason given there is
  // exactly this one. A forged "offline" costs nothing: it makes the central
  // unit believe a device is gone, and that triggers no output.
  //
  // Retained on both sides, so that a central unit starting later finds the
  // truth and not a stale "online".
  PUN_PHASE(40);
  unsigned long connectStart = millis();
  bool ok = _mqtt.connect(_cfg.clientId, _cfg.mqttUser, _cfg.mqttPass,
                          _tAvailable, 0, true, "offline");
  if (!ok) {
    // SAY WHY, NOT ONLY THAT.
    //
    // `rc=-2` is PubSubClient's MQTT_CONNECT_FAILED and means exactly one
    // thing: the client underneath returned false. Whether that was the TCP
    // connect, the TLS handshake, or a timeout is invisible from there — and
    // that is the whole question when a device will not come in (collar,
    // 2026-09-16). mbedTLS knows the reason; lastError() puts it into words.
    //
    // The duration belongs beside it: a refused connection comes back in
    // milliseconds, a handshake that ran into its limit takes seconds. The
    // two look the same in the return value and different in the clock.
    if (_cfg.serialLog) {
      char err[160] = {0};
      int mbed = 0;
      if (_cfg.tls) mbed = _wifiTls.lastError(err, sizeof(err));
      Serial.printf("MQTT connect failed rc=%d nach %lu ms an %s:%u\n",
                    _mqtt.state(), (unsigned long) (millis() - connectStart),
                    _cfg.broker ? _cfg.broker : "?", (unsigned) _cfg.port);
      if (mbed || err[0]) Serial.printf("  mbedTLS %d: %s\n", mbed, err);
    }
    return false;
  }
  // Clear the retained "offline" of the previous life BEFORE anything else is
  // said. Otherwise the central unit reads the hello of a device whose last
  // retained word still says it is gone.
  PUN_PHASE(41); publishRaw(_tAvailable, "online", true);
  PUN_PHASE(42); subscribeAll();
  PUN_PHASE(43); publishHello();
  PUN_PHASE(44); publishHeartbeat();
  PUN_PHASE(45); publishState();
  PUN_PHASE(46); if (_h) _h->onConnected();
  if (_cfg.serialLog) Serial.println("MQTT connected");
  return true;
}

void PunisherDevice::subscribeAll() {
  _mqtt.subscribe(_tSettings);
  _mqtt.subscribe(_tCmd);
  _mqtt.subscribe(_tEmergency);
  _mqtt.subscribe("punisher/emergency");
  _mqtt.subscribe("punisher/central/heartbeat");
  // Subscribe again to the channel of the assigned slave after a reconnect
  if (_tPunish[0]) _mqtt.subscribe(_tPunish);
  if (_tReward[0]) _mqtt.subscribe(_tReward);
  if (_tLive[0])   _mqtt.subscribe(_tLive);
}

// The punishment/reward channel follows the assignment: only an assigned
// device acting as a stimulus device listens, and only on the channel of ITS slave.
void PunisherDevice::updateChannelSubscriptions(uint16_t oldId, uint16_t newId) {
  (void) oldId;
  if (_tPunish[0] && _mqtt.connected()) _mqtt.unsubscribe(_tPunish);
  if (_tReward[0] && _mqtt.connected()) _mqtt.unsubscribe(_tReward);
  if (_tLive[0]   && _mqtt.connected()) _mqtt.unsubscribe(_tLive);
  _tPunish[0] = _tReward[0] = _tLive[0] = '\0';
  if (newId == 0) return;
  if (_cfg.punishListener) {
    snprintf(_tPunish, sizeof(_tPunish), "punisher/slaves/%u/punish", (unsigned) newId);
    if (_mqtt.connected()) _mqtt.subscribe(_tPunish);
  }
  if (_cfg.rewardListener) {
    snprintf(_tReward, sizeof(_tReward), "punisher/slaves/%u/reward", (unsigned) newId);
    if (_mqtt.connected()) _mqtt.subscribe(_tReward);
  }
  if (_cfg.liveListener) {
    snprintf(_tLive, sizeof(_tLive), "punisher/slaves/%u/live", (unsigned) newId);
    if (_mqtt.connected()) _mqtt.subscribe(_tLive);
  }
}

// --------------------------------------------------------------------- //
void PunisherDevice::_mqttCallback(char* topic, uint8_t* payload, unsigned int len) {
  if (_instance) _instance->onMessage(topic, payload, len);
}

void PunisherDevice::onMessage(char* topic, uint8_t* payload, unsigned int len) {
  // EMERGENCY first, in every state, without parsing.
  if (strcmp(topic, _tEmergency) == 0 || strcmp(topic, "punisher/emergency") == 0) {
    if (_state != PD_EMERGENCY) enterEmergency(
        strcmp(topic, "punisher/emergency") == 0 ? "broadcast" : "device");
    return;
  }
  if (_state == PD_EMERGENCY) return;  // frozen

  // The signed envelope is larger than its content: the signature costs
  // 64 characters, and the body sits inside it as an escaped string, so every
  // quotation mark is doubled. The limit here is the ONE the sketch configured
  // (mqttBufferSize), not a second number of its own — a second number is how
  // this callback came to refuse messages the library had already accepted
  // (2.1.1, see begin()). What the library delivers always fits: its buffer
  // holds header, topic and payload together, so `len` is below the cap by
  // construction, and the check is for the day somebody changes that.
  if (!_rx || len >= _rxCap) { logf("warn", "payload too large on %s (%u B)", topic, (unsigned) len); return; }
  char* buf = _rx;
  memcpy(buf, payload, len);
  buf[len] = '\0';

  // NOTE: the heartbeat used to be handled HERE, above the envelope check,
  // because it was not signed. Since 2.1.0 it is, so it goes through the same
  // door as everything else — see below. Handling it early was what let anyone
  // with access to the broker set this device's clock and hold its watchdog
  // open (finding Philine 2026-09-15).

  // Open the envelope BEFORE the content triggers anything.
  String inner;
  if (_cfg.projectKey && _cfg.projectKey[0] && topicIsSigned(topic)) {
    if (!openEnvelope(topic, buf, inner)) return;
    if (inner.length() >= _rxCap) { logf("warn", "body too large on %s", topic); return; }
    strncpy(buf, inner.c_str(), _rxCap - 1);
    buf[_rxCap - 1] = '\0';
  }

  JSONVar j = JSON.parse(buf);
  if (JSON.typeof(j) == "undefined") { logf("warn", "bad json on %s", topic); return; }

  if (strcmp(topic, "punisher/central/heartbeat") == 0) { handleCentralHeartbeat(j); return; }
  if (strcmp(topic, _tSettings) == 0) { handleSettings(j); return; }
  if (strcmp(topic, _tCmd) == 0)      { handleCmd(j); return; }
  if (_tPunish[0] && strcmp(topic, _tPunish) == 0) { handleChannel(j, true);  return; }
  if (_tReward[0] && strcmp(topic, _tReward) == 0) { handleChannel(j, false); return; }
  if (_tLive[0]   && strcmp(topic, _tLive)   == 0) { handleLive(j);           return; }
}

// --------------------------------------------------------------------- //
void PunisherDevice::touchCentral() {
  // A SIGN OF LIFE, AND ONLY FROM A MESSAGE THAT PASSED EVERY CHECK.
  //
  // Call this LAST, never first. Until 2.1.0 every handler called it before
  // the duplicate and freshness checks — so a recorded, validly signed message
  // could not be executed twice, but it could still reset this timer. Which
  // means it could hold the 120-second failsafe open, and that failsafe is the
  // thing that puts a device into its safe state when the central unit falls
  // silent (finding Philine 2026-09-15).
  //
  // The rule: what is not good enough to act on is not good enough to prove
  // that anyone is still there.
  _lastCentral = millis();
  if (!_centralAlive) {
    _centralAlive = true;
    if (_h) _h->onCentralBack();
  }
}

void PunisherDevice::handleCentralHeartbeat(JSONVar& j) {
  // The signature says WHO sent this. It does not say WHEN — a recorded
  // heartbeat stays validly signed forever, and replaying an old one would
  // wind this device's clock backwards. Everything that is then judged by
  // that clock (every TTL, since 2.1.0) would judge by a wrong one.
  //
  // So: only ever forwards. The central unit sends one per second; a
  // timestamp that is not newer than the last accepted one is either a
  // repetition or a replay, and neither has anything to tell us.
  //
  // The first one has nothing to compare against and is taken as it comes.
  // That is the bootstrap, and it is not a hole one can widen: without the
  // project key there is no valid heartbeat at all.
  if (!j.hasOwnProperty("ts_ms")) {
    logf("warn", "heartbeat without ts_ms dropped");
    return;
  }
  long long ts = (long long)(double) j["ts_ms"];
  if (_haveOffset && ts <= _lastCentralTsMs) {
    logf("warn", "heartbeat not newer (%lldms) dropped", _lastCentralTsMs - ts);
    return;
  }
  _lastCentralTsMs  = ts;
  _centralOffsetMs  = ts - (long long) millis();
  _haveOffset       = true;
  // Only a heartbeat that was accepted counts as a sign of life. Otherwise a
  // replayed one would keep the watchdog open — which is half of what this
  // change is about.
  touchCentral();
}

void PunisherDevice::handleSettings(JSONVar& j) {
  // SAME DOOR AS A COMMAND (2.1.0). A setting carries the assignment to a
  // slave — which channel this device listens on afterwards. Until 2.0.0 it
  // went past both guards: no duplicate check, no age check, nothing. A
  // recorded assignment could be played back at any later time and would put
  // this device back on a person it had been taken off.
  if (seenCmdId(j, "settings")) return;
  if (staleCmd(j, "settings")) return;
  touchCentral();                       // only now — see touchCentral()
  if (j.hasOwnProperty("initial")) {
    // Up to 2.0.0 the bare model UUID went out here, unsigned and not JSON —
    // the answer shape of 1.x. The central unit has not read it for a long
    // time: it takes model and capabilities out of the hello that follows.
    // Gone with 2.1.0, together with the signing exception it justified.
    publishHello();
  }
  // Review 2026-09-10: accept a release (slave_id 0) even without slave_name,
  // treat invalid values (negative, not a number, > 65535) like a release —
  // before that a negative value would have subscribed to a foreign channel via uint16 wraparound.
  if (j.hasOwnProperty("slave_id")) {
    double sidRaw = (double) j["slave_id"];
    int sid = (sidRaw >= 1 && sidRaw <= 65535) ? (int) sidRaw : 0;
    uint16_t oldId = _slaveId;
    if (sid == 0) {
      _slaveId = 0; _slaveName[0] = '\0';
      updateChannelSubscriptions(oldId, 0);
      if (_h) { _h->safeState(); _h->onUnregistered(); }
      publishState();
    } else {
      _slaveId = (uint16_t) sid;
      const char* nm = j.hasOwnProperty("slave_name") ? (const char*) j["slave_name"] : nullptr;
      snprintf(_slaveName, sizeof(_slaveName), "%s", nm ? nm : "");
      if (oldId != _slaveId) updateChannelSubscriptions(oldId, _slaveId);
      if (_h) _h->onRegistered(_slaveId, _slaveName);
      publishState();
    }
  }
}

// --- shared checks for cmd and channel -----------------------------------
//
// FAIL-CLOSED SINCE 2.1.0. What is missing is not permission.
//
// Until 2.0.0 all three of these guards answered "no objection" when the field
// they check was absent: no `id` meant "not a duplicate", no `ts_ms` meant "not
// stale", no `kind` meant "matches everything". The replay protection was
// therefore a request to the sender rather than a check, and a message that
// carried none of the three ran straight through (finding Philine 2026-09-15).
//
// The central unit has always sent id, ts_ms and ttl_ms with every command and
// a kind with every channel message — checked before the change was made.
// Nothing legitimate is refused by this; only what was never built by this
// installation.

// Duplicate protection: never execute the same id twice (makes QoS 1 safe; a
// doubled pulse through redelivery would otherwise be possible).
// true = drop this message.
bool PunisherDevice::seenCmdId(JSONVar& j, const char* what) {
  if (!j.hasOwnProperty("id")) {
    logf("warn", "%s without id dropped", what);
    return true;
  }
  unsigned long id = (unsigned long)(double) j["id"];
  if (id == 0) {
    logf("warn", "%s with id=0 dropped", what);
    return true;
  }
  for (uint8_t i = 0; i < CMD_ID_RING; i++) {
    if (_cmdIds[i] == id) { logf("warn", "duplicate %s id=%lu dropped", what, id); return true; }
  }
  _cmdIds[_cmdIdPos] = id;
  _cmdIdPos = (_cmdIdPos + 1) % CMD_ID_RING;
  return false;
}

// Freshness: discard what is older than its TTL. true = drop this message.
//
// THE WINDOW AFTER A RESTART WAS THE WORST OF THE THREE. Without the central
// unit's time this check used to wave everything through — and that is exactly
// the moment a recorded, validly signed `punish` could be replayed into. The
// envelope proves WHO sent it, never WHEN; the only clock that says when is
// this one. No clock now means no command, and the wait is short: the central
// unit's heartbeat arrives once a second.
bool PunisherDevice::staleCmd(JSONVar& j, const char* what) {
  if (!_haveOffset) {
    logf("warn", "%s dropped: no central time yet", what);
    return true;
  }
  if (!j.hasOwnProperty("ts_ms")) {
    logf("warn", "%s without ts_ms dropped", what);
    return true;
  }
  long long ts  = (long long)(double) j["ts_ms"];
  long long ttl = j.hasOwnProperty("ttl_ms") ? (long long)(double) j["ttl_ms"]
                                             : (long long) _cfg.cmdDefaultTtlMs;
  long long now = (long long) centralNowMs();
  if (now - ts > ttl) { logf("warn", "stale %s dropped (age=%lldms)", what, now - ts); return true; }
  // A timestamp from the future is as wrong as one from the past, and it would
  // survive every TTL. One TTL of tolerance for the jitter of a borrowed clock.
  if (ts - now > ttl) { logf("warn", "%s from the future dropped (%lldms)", what, ts - now); return true; }
  return false;
}

bool PunisherDevice::kindMatches(const char* kind, const char* const* list, size_t n) {
  if (!kind || !kind[0] || strcmp(kind, "any") == 0) return true;
  for (size_t i = 0; i < n; i++) if (list && list[i] && strcmp(list[i], kind) == 0) return true;
  return false;
}

// Punishment/reward channel: {action:"punish"|"reward", args:{level,kind,reason,source}, id, ts_ms, ttl_ms}
void PunisherDevice::handleChannel(JSONVar& j, bool punish) {
  const char* what = punish ? "punish" : "reward";
  if (_slaveId == 0) return;                          // the release came in between
  if (seenCmdId(j, what)) return;
  if (staleCmd(j, what)) return;
  touchCentral();                                     // only now — see touchCentral()
  JSONVar args = j.hasOwnProperty("args") ? j["args"] : JSONVar();
  // Arduino_JSON returns a NULL pointer for non-strings (null, number) —
  // so normalise all text fields before the device sees them (review 2026-09-10).
  const char* kind = args.hasOwnProperty("kind") ? (const char*) args["kind"] : nullptr;
  // A MISSING KIND IS NOT "any". Until 2.0.0 it became one, and a channel
  // message without a kind therefore hit whatever this device could do. The
  // central unit always sends one — explicitly "any" when it means any.
  if (!kind || !kind[0]) {
    logf("warn", "%s without kind dropped", what);
    return;
  }
  if (!kindMatches(kind, punish ? _cfg.punishKinds : _cfg.rewardKinds,
                   punish ? _cfg.punishKindCount : _cfg.rewardKindCount)) return;   // not for this device
  PunisherRequest r;
  int lvl = args.hasOwnProperty("level") ? (int) args["level"] : 1;
  r.level  = (uint8_t) (lvl < 1 ? 1 : (lvl > 3 ? 3 : lvl));
  r.kind   = kind;
  r.reason = args.hasOwnProperty("reason") ? (const char*) args["reason"] : nullptr;
  r.source = args.hasOwnProperty("source") ? (const char*) args["source"] : nullptr;
  if (!r.reason) r.reason = "";
  if (!r.source) r.source = "central";
  r.id     = j.hasOwnProperty("id") ? (unsigned long)(double) j["id"] : 0;
  r.args   = &args;
  char err[80] = {0};
  bool ok = _h ? (punish ? _h->onPunish(r, err, sizeof(err)) : _h->onReward(r, err, sizeof(err))) : false;
  if (!ok) {
    JSONVar ev; ev["cid"] = (double) r.id; ev["kind"] = r.kind; ev["reason"] = r.reason;
    ev["error"] = err[0] ? err : "rejected";
    publishEvent(punish ? "punish_rejected" : "reward_rejected", ev, "info");
    logf("warn", "%s rejected: %s", what, err[0] ? err : "?");
  }
}

// Reading channel: {ts_ms, device, depth, err, away, valid} — doc 19 §5.2.
//
// AN OBSERVATION IS NOT EXEMPT FROM BEING FRESH (2.1.0).
//
// It used to be waved through with no check at all, on the grounds that it is
// an observation rather than a command. But a coupled waveform follows this
// value, and doc 19 §6 says a stale reading has to silence every track. A
// recorded reading, played back, refreshed `atMs` and therefore counted as
// fresh — the installation would have gone on stimulating from a posture it no
// longer measures, which is exactly the case §6 was written for (finding
// Philine 2026-09-15).
//
// There is no `id` on this channel and it does not need one: readings are a
// stream and their timestamps only ever go up. Anything not newer than the
// last accepted one is a repetition or a replay, and neither is an observation
// of now.
//
// MISSING IS NOT NULL — a field that does not come along stays at the
// pessimistic default of the struct (depth 0, err 1.0). `err` = 0.0 is by
// contrast the perfect run and must come through as 0.0; an `|| 1.0` at
// this place would have swallowed exactly the earned reward.
void PunisherDevice::handleLive(JSONVar& j) {
  if (_slaveId == 0 || !_h) return;                   // the release came in between
  if (staleCmd(j, "live")) return;                    // too old, or no clock to judge by
  long long ts = (long long)(double) j["ts_ms"];      // staleCmd proved it is there
  if (ts <= _lastLiveTsMs) {
    logf("warn", "live not newer (%lldms) dropped", _lastLiveTsMs - ts);
    return;
  }
  _lastLiveTsMs = ts;
  touchCentral();                                     // only now — see touchCentral()
  PunisherLive live;
  if (j.hasOwnProperty("depth")) { live.depth = (float)(double) j["depth"]; live.haveDepth = true; }
  if (j.hasOwnProperty("err"))   { live.err   = (float)(double) j["err"];   live.haveErr   = true; }
  // MISSING IS PESSIMISTIC — here too (2.1.1). Until then a reading without
  // `valid` counted as valid and one without `away` as present, which is the
  // one place in this file where an absent field was read as permission. A
  // coupled track follows this value onto skin; the honest reading of "I was
  // not told whether this is usable" is "it is not" (finding Philine 2026-09-15).
  live.away  = j.hasOwnProperty("away")  ? (bool) j["away"]  : true;
  live.valid = j.hasOwnProperty("valid") ? (bool) j["valid"] : false;
  if (!live.valid) live.away = true;                  // unusable = as good as gone
  if (live.away) {
    live.haveDepth = false; live.haveErr = false;     // nothing measured about a person who is not there
  }
  if (live.depth < 0.0f) live.depth = 0.0f;
  if (live.depth > 100.0f) live.depth = 100.0f;
  if (live.err < 0.0f) live.err = 0.0f;
  if (live.err > 1.0f) live.err = 1.0f;
  live.atMs = millis();
  _h->onLive(live);
}

void PunisherDevice::handleCmd(JSONVar& j) {
  if (!j.hasOwnProperty("action")) { logf("warn", "cmd without action"); return; }
  const char* action = (const char*) j["action"];
  // Review 2026-09-10: action not a string (number/null) -> NULL pointer -> strcmp() crashes.
  if (!action || !action[0]) { logf("warn", "cmd with non-string action"); return; }

  if (seenCmdId(j, action)) return;     // duplicate protection (QoS 1 redelivery)
  strncpy(g_trace.lastCmd, action, sizeof(g_trace.lastCmd) - 1);   // for the next life's hello
  g_trace.lastCmd[sizeof(g_trace.lastCmd) - 1] = 0;
  if (staleCmd(j, action)) return;      // TTL
  touchCentral();                       // only now — see touchCentral()

  // Commands of the base itself.
  if (strcmp(action, "identify") == 0) { if (_h) _h->onIdentify(); return; }
  if (strcmp(action, "stop") == 0) {
    // Gentle stop: safe state, but do NOT freeze (the device stays
    // operable). For EMERGENCY there is the separate emergency topic.
    if (_h) _h->safeState();
    publishEvent("stopped");
    return;
  }
  if (strcmp(action, "factory_reset") == 0) {
    logf("warn", "factory_reset requested - clearing config and rebooting");
    if (_h) _h->safeState();
    factoryReset();  // reboot -> comes up unconfigured in the config portal
    return;
  }

  JSONVar args = j.hasOwnProperty("args") ? j["args"] : JSONVar();
  // SETTINGS BY COMMAND (2.2.0, doc 42 point 5): {"action":"config",
  // "args":{"set":{"zap_max":"60", ...}, "restart":true}}. The central unit
  // holds the schema — type, bounds, unit, per model — and generates the form
  // from it; this device only stores what it is given, in NVS, under the
  // same keys its sketch reads with cfgInt()/cfgStr(). Protected keys (the
  // ones the setup portal owns) are refused in cfgSet(), and every key is
  // answered individually, so that a typo in the central unit's schema shows
  // up as "refused" and not as a value that silently never took effect.
  //
  // Sketches read their config at start. So the change is stored now and
  // TAKES EFFECT AT THE NEXT START — the answer says so, and `restart` asks
  // for that start. Refused while the device is active: a lock in the middle
  // of a hold does not reboot because somebody edited a form.
  if (strcmp(action, "config") == 0) {
    JSONVar ans; ans["action"] = "config";
    JSONVar setv = args.hasOwnProperty("set") ? args["set"] : JSONVar();
    JSONVar stored = JSON.parse("[]"), refused = JSON.parse("[]");
    int ns = 0, nr = 0;
    if (JSON.typeof(setv) == "object") {
      JSONVar keys = setv.keys();
      for (int i = 0; i < keys.length(); i++) {
        const char* k = (const char*) keys[i];
        String v = JSON.stringify(setv[k]);
        if (v.length() >= 2 && v[0] == '"') v = v.substring(1, v.length() - 1);   // unquote a string value
        if (cfgSet(k, v.c_str())) stored[ns++] = k; else refused[nr++] = k;
      }
    }
    ans["stored"] = stored; ans["refused"] = refused;
    ans["effective"] = "next_start";
    bool wantRestart = args.hasOwnProperty("restart") && (bool) args["restart"];
    if (wantRestart && _h && _h->isActive()) { ans["restart"] = "refused: device active"; wantRestart = false; }
    else ans["restart"] = wantRestart ? "yes" : "no";
    ans["ok"] = (nr == 0);
    publishResponse(ans);
    if (wantRestart) {
      logf("info", "config stored, restarting as asked");
      if (_h) _h->safeState();
      delay(300);
      ESP.restart();
    }
    return;
  }

  char err[80] = {0};
  bool ok = _h ? _h->onCommand(action, args, err, sizeof(err)) : false;
  if (!ok) {
    JSONVar ev;
    ev["action"] = action;
    ev["error"]  = err[0] ? err : "rejected";
    publishEvent("cmd_rejected", ev);
    logf("warn", "cmd '%s' rejected: %s", action, err[0] ? err : "?");
  }
}

// --------------------------------------------------------------------- //
void PunisherDevice::enterEmergency(const char* source) {
  if (_h) _h->safeState();
  _state = PD_EMERGENCY;
  if (_h) _h->onEmergency(source);
  JSONVar ev; ev["source"] = source;
  publishEvent("emergency", ev);
  // Review 2026-09-10: retained state immediately to "emergency" — before that the
  // last idle/active state stayed at the broker, because loop() returns early in an emergency.
  publishState();
  logf("crit", "EMERGENCY (%s) - frozen until power cycle", source);
}

void PunisherDevice::requestEmergency(const char* source) {
  if (_state != PD_EMERGENCY) enterEmergency(source);
}

void PunisherDevice::goSafe(const char* reason) {
  if (_h) _h->safeState();
  JSONVar ev; ev["reason"] = reason;
  publishEvent("safe_state", ev);
  logf("warn", "safe state: %s", reason);
}

// --------------------------------------------------------------------- //
void PunisherDevice::publishRaw(const char* topic, const char* payload, bool retain) {
  if (_mqtt.connected()) _mqtt.publish(topic, payload, retain);
}

// --------------------------------------------------------------------- //
// SIGNATURE
//
// What gets signed is what acts on a device or claims something about one:
// cmd, settings, hello, state, event, log, live, punish, reward, response.
// NOT signed: the emergency stop (switching off is the harmless direction) and
// the last word at the broker (available — the broker sends it when we have
// long stopped computing).
//
// `response` was the third exception until 2.1.0, on the grounds that up to 1.x
// it carried a bare model UUID instead of JSON and that nothing was triggered
// by it. Both halves had stopped being true: in 2.0 every answer is JSON, and
// the central unit does act on one — it sends a waveform again when a device
// says it does not hold it. An unsigned message that makes the installation
// transmit is not an exception one keeps.
//
// The transmitted string IS the signed one. There is nothing to
// canonicalise — that is exactly where such procedures otherwise fail, and
// only years later, when one side changes its JSON library.

static bool topicIsSigned(const char* topic) {
  // The one signed topic under central/ (2.1.0). It carries the only clock
  // this device has and it resets the 120-second watchdog — see the block
  // above and punsign.py, which keeps the same list on the other side.
  if (strcmp(topic, "punisher/central/heartbeat") == 0) return true;
  const char* last = strrchr(topic, '/');
  if (!last) return false;
  last++;
  static const char* SIGNED[] = {"cmd", "settings", "hello", "state", "event",
                                 "log", "live", "punish", "reward", "response"};
  for (size_t i = 0; i < sizeof(SIGNED) / sizeof(SIGNED[0]); i++)
    if (strcmp(last, SIGNED[i]) == 0) return true;
  return false;
}

String PunisherDevice::signEnvelope(const char* topic, const String& body) {
  uint8_t h[32];
  String msg = String(topic) + "\n" + body;
  pun::hmacSha256((const uint8_t*) _cfg.projectKey, strlen(_cfg.projectKey),
                  (const uint8_t*) msg.c_str(), msg.length(), h);
  char hex[65];
  pun::toHex(h, 32, hex);
  JSONVar env;
  env["v"]    = 1;
  env["sig"]  = hex;
  env["body"] = body;          // Arduino_JSON escapes the string itself
  return JSON.stringify(env);
}

bool PunisherDevice::openEnvelope(const char* topic, const char* raw, String& out) {
  JSONVar env = JSON.parse(raw);
  if (JSON.typeof(env) == "undefined") { logf("warn", "envelope: no json on %s", topic); return false; }
  if (!env.hasOwnProperty("sig") || !env.hasOwnProperty("body")) {
    logf("warn", "envelope: unsigned message on %s", topic);
    return false;
  }
  if ((int) env["v"] != 1) { logf("warn", "envelope: version %d on %s", (int) env["v"], topic); return false; }
  String body = (const char*) env["body"];
  uint8_t h[32];
  String msg = String(topic) + "\n" + body;
  pun::hmacSha256((const uint8_t*) _cfg.projectKey, strlen(_cfg.projectKey),
                  (const uint8_t*) msg.c_str(), msg.length(), h);
  char hex[65];
  pun::toHex(h, 32, hex);
  String sig = (const char*) env["sig"];
  if (sig.length() != 64 || !pun::equalsConstTime(hex, sig.c_str(), 64)) {
    // Reject LOUDLY. A silent rejection looks like a loose contact,
    // and after that somebody searches for hours at the wrong end.
    logf("error", "envelope: signature mismatch on %s", topic);
    return false;
  }
  out = body;
  return true;
}

void PunisherDevice::publishJson(const char* topic, JSONVar& j, bool retain) {
  String s = JSON.stringify(j);
  if (_cfg.projectKey && _cfg.projectKey[0] && topicIsSigned(topic))
    s = signEnvelope(topic, s);
  if (_mqtt.connected()) _mqtt.publish(topic, s.c_str(), retain);
}

void PunisherDevice::publishHello() {
  JSONVar j;
  j["model"]      = _cfg.modelUuid;
  j["device"]     = _cfg.deviceUuid;

  // WHO the device is: the efuse MAC. Immutable in the chip — the REPORTED
  // value is not, that is a check against errors, not against
  // tampering. The central unit binds devices to slaves through it.
  j["mac"]  = _ownMacTxt;
  j["chip"] = pun::chipType();
  j["mac_locked"] = pun::macFusesLocked();

  // TWO versions, two floors in the central unit. Separated into name and numbers,
  // so that nobody has to cut a version out of a string any more.
  JSONVar fwF, fwS;
  fwF["major"] = (int) PUNISHERDEVICE_VERSION_MAJOR;
  fwF["minor"] = (int) PUNISHERDEVICE_VERSION_MINOR;
  fwF["patch"] = (int) PUNISHERDEVICE_VERSION_PATCH;
  j["fw_framework"] = fwF;
  fwS["name"]  = _cfg.sketchName;
  fwS["major"] = (int) _cfg.sketchMajor;
  fwS["minor"] = (int) _cfg.sketchMinor;
  fwS["patch"] = (int) _cfg.sketchPatch;
  j["fw_sketch"] = fwS;

  // Assembled readably only for logs and display. NOT for comparing.
  char disp[64];
  snprintf(disp, sizeof(disp), "%s %u.%u.%u (lib %s)",
           _cfg.sketchName ? _cfg.sketchName : "?",
           (unsigned) _cfg.sketchMajor, (unsigned) _cfg.sketchMinor,
           (unsigned) _cfg.sketchPatch, PUNISHERDEVICE_VERSION_STR);
  j["fw_version"] = disp;

  JSONVar caps;
  for (size_t i = 0; i < _cfg.capabilityCount; i++) caps[i] = _cfg.capabilities[i];
  j["capabilities"] = caps;

  // THIS LIFE, AND THE END OF THE LAST ONE (2.2.0). The central unit keeps a
  // row per (device, boot id); the hello is retained and is re-sent on
  // request, so the id is what makes a start count once. What the previous
  // life left behind is absent — not zero — when the RTC memory was lost.
  JSONVar boot;
  boot["id"]        = _bootId;
  boot["reason"]    = _resetReason;
  boot["heap_free"] = (int) ESP.getFreeHeap();
  boot["count"]     = (int) g_trace.bootCount;
  if (_haveTrace) {
    boot["uptime_before_s"] = (int) _prevUptimeS;
    if (_prevCmd[0]) boot["last_cmd"] = _prevCmd;
    if (_prevErr[0]) boot["last_err"] = _prevErr;
  }
  j["boot"] = boot;

  // WHAT IS OUT OF ORDER — status, never promise (2.2.0, doc 42 point 4).
  // Always present, possibly empty: an empty list says "self-check fine", a
  // missing key says "firmware too old to report". Those are different
  // statements, and the central unit reads them differently.
  // Starts as an EMPTY ARRAY — a default JSONVar is null, and null on the
  // wire would read as "not reported".
  JSONVar degraded = JSON.parse("[]");
  if (_h) _h->reportDegraded(degraded);
  j["degraded"] = degraded;
  _degradedLast = JSON.stringify(degraded);
  // The ENVELOPE of the device: what it lets through at most (doc 03 C).
  // Without this report the central unit has to guess what a single device
  // takes — it then showed values that the device silently clamps (finding
  // Philine 2026-09-11). The device knows it itself; so it says it.
  if (_h) {
    JSONVar lim;
    _h->reportLimits(lim);
    if (JSON.stringify(lim) != "{}") j["limits"] = lim;
  }
  if (_cfg.punishListener) {                   // stimulus device: which kinds the channel can address
    JSONVar pk;
    for (size_t i = 0; i < _cfg.punishKindCount; i++) pk[i] = _cfg.punishKinds[i];
    j["punish_kinds"] = pk;
  }
  if (_cfg.rewardListener) {
    JSONVar rk;
    for (size_t i = 0; i < _cfg.rewardKindCount; i++) rk[i] = _cfg.rewardKinds[i];
    j["reward_kinds"] = rk;
  }
  // retained: the device description stays at the broker, so that a freshly started
  // central unit knows all devices at once (Homie: attributes retained).
  publishJson(_tHello, j, true);
}

void PunisherDevice::publishHeartbeat() {
  // NOT retained: the retained value on this topic is the answer to "is this
  // device there at all" and is written exactly twice — "online" on connect,
  // "offline" by the broker as the will. A retained sign of life would
  // overwrite the will's ground truth with a stale "ping".
  publishRaw(_tAvailable, "ping");
  _lastHeartbeat = millis();
}

void PunisherDevice::publishState() {
  JSONVar j;
  static const char* names[] = {"boot", "idle", "active", "emergency"};
  j["state"]    = names[_state];
  j["slave_id"] = (int) _slaveId;
  if (_slaveId) j["slave_name"] = _slaveName;
  j["ip"]   = WiFi.localIP().toString();   // for OTA / diagnosis without a serial cable
  j["rssi"] = WiFi.RSSI();
  // For display only. Comparing is done over the numbers in the hello — here
  // deliberately the same readable format as there.
  char fw[64];
  snprintf(fw, sizeof(fw), "%s %u.%u.%u (lib %s)",
           _cfg.sketchName ? _cfg.sketchName : "?",
           (unsigned) _cfg.sketchMajor, (unsigned) _cfg.sketchMinor,
           (unsigned) _cfg.sketchPatch, PUNISHERDEVICE_VERSION_STR);
  j["fw"]   = fw;
  j["ota"]  = _otaStarted;
  if (_h) _h->reportState(j);
  publishJson(_tState, j, true);   // retained: the current state stays at the broker
  _lastState = millis();
}

void PunisherDevice::publishEvent(const char* event, const char* cls) {
  JSONVar j; publishEvent(event, j, cls);
}
void PunisherDevice::publishEvent(const char* event, JSONVar& data, const char* cls) {
  data["event"]    = event;
  data["cls"]      = (cls && cls[0]) ? cls : "info";
  data["slave_id"] = (int) _slaveId;

  // A timestamp ONLY when we actually know the time.
  //
  // This device has no clock of its own. It borrows one from the heartbeat of
  // the central unit (handleCentralHeartbeat -> _centralOffsetMs, 1 Hz). Before
  // that centralNowMs() returns the run time since the start — a few thousand milliseconds.
  //
  // If that value stood in the event, the central unit computed an age of about
  // 1.7*10^12 ms and rejected the message as "too old": the event was gone
  // (finding 2026-09-14). Affected was exactly the window between connecting
  // and the first heartbeat — and the whole time in which a device runs
  // while the central unit is not there.
  //
  // Without `ts_ms` the central unit skips the age check (punsign.verify
  // only checks when the field is there) — the same rule by which `hello`,
  // `state` and `log` have always gone through without a timestamp. Rather NO
  // statement about the time than a demonstrably false one.
  if (hasCentralTime()) data["ts_ms"] = (double) centralNowMs();

  publishJson(_tEvent, data);
}

void PunisherDevice::publishResponse(JSONVar& j) {
  publishJson(_tResponse, j);
}

void PunisherDevice::logf(const char* level, const char* fmt, ...) {
  char msg[160];
  va_list ap; va_start(ap, fmt);
  vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  if (_cfg.serialLog) { Serial.print('['); Serial.print(level); Serial.print("] "); Serial.println(msg); }
  // Remember the last thing that went wrong, for the next life's hello.
  if (level && (level[0] == 'e' || level[0] == 'w')) {
    strncpy(g_trace.lastErr, msg, sizeof(g_trace.lastErr) - 1);
    g_trace.lastErr[sizeof(g_trace.lastErr) - 1] = 0;
  }
  JSONVar j; j["level"] = level; j["msg"] = msg;
  publishJson(_tLog, j);
}

unsigned long long PunisherDevice::centralNowMs() const {
  if (_haveOffset) return (unsigned long long)((long long) millis() + _centralOffsetMs);
  return (unsigned long long) millis();
}

// --------------------------------------------------------------------- //
void PunisherDevice::loop() {
  PUN_PHASE(20);
  feedWdt();
  serialConsole();
  unsigned long now = millis();
  if (now - _traceWrittenMs >= 1000) {
    g_trace.uptimeS = now / 1000; _traceWrittenMs = now;
#if PUNISHER_PHASE_TRACE
    // Once a second, not per pass: the value is meant to say how much was
    // left shortly before the freeze, not to cost time while it runs.
    g_trace.heapFree = ESP.getFreeHeap();
    g_trace.heapMax  = ESP.getMaxAllocHeap();
#endif
  }
  // A component that drops out (or comes back) is a new hello: the retained
  // description at the broker must say what is true now.
  PUN_PHASE(21);
  if (_h && _mqtt.connected() && now - _degradedCheckMs >= 5000) {
    _degradedCheckMs = now;
    JSONVar d = JSON.parse("[]"); _h->reportDegraded(d);
    String cur = JSON.stringify(d);
    if (cur != _degradedLast) {
      logf("warn", "components changed: %s", cur.c_str());
      publishHello();
    }
  }

  PUN_PHASE(22);
  connectWifi(now);

  // --- MQTT connection + broker failsafe -----------------------------
  PUN_PHASE(23);
  if (!_mqtt.connected()) {
    if (_disconnectedSince == 0) {
      _disconnectedSince = now;
      // Deliberately do NOT touch _lastCentral: the central-unit watchdog above
      // is meant to fire after centralTimeoutMs while an action is running.
      if (_cfg.serialLog) Serial.println("MQTT lost");
    }
    if (!_brokerFailsafeFired &&
        (long)(now - _disconnectedSince) >= (long) _cfg.brokerFailsafeMs) {
      _brokerFailsafeFired = true;
      if (_state != PD_EMERGENCY) goSafe("broker failsafe");
    }
    if (WiFi.status() == WL_CONNECTED &&
        (_lastReconnect == 0 || (long)(now - _lastReconnect) >= (long) _cfg.reconnectMs)) {
      _lastReconnect = now;
      PUN_PHASE(24);
      if (connectMqtt()) { _disconnectedSince = 0; _brokerFailsafeFired = false; }
    }
  } else {
    _mqtt.loop();
    _disconnectedSince = 0;
  }

  // --- OTA only in the safe state (not active, no emergency) ----------
  PUN_PHASE(25);
  if (_cfg.otaPassword && WiFi.status() == WL_CONNECTED &&
      _state != PD_EMERGENCY && !(_h && _h->isActive())) {
    setupOta();
    ArduinoOTA.handle();
  }

  PUN_PHASE(26);
  if (_state == PD_EMERGENCY) {
    // Frozen: only keep connection/heartbeat/state, nothing else.
    if (_mqtt.connected() && (long)(now - _lastHeartbeat) >= (long) _cfg.heartbeatIdleMs) {
      publishHeartbeat();
    }
    if (_mqtt.connected() && (long)(now - _lastState) >= (long) _cfg.stateIntervalMs) publishState();
    return;
  }

  // --- Watchdog on the central unit ----------------------------------
  // While an action is running, something must come from the central unit
  // regularly (heartbeat, cmd or settings). If that stays away — no matter
  // whether because of a broker failure, a WiFi break or a dead central unit —
  // safe state. Deliberately NOT coupled to _centralAlive: the flag only serves
  // the callbacks onCentralLost()/onCentralBack() and is no timer.
  //
  // FAULT fixed (2026-09-06, collar test): `now` came from the beginning of the
  // round, but _lastCentral had just been set in _mqtt.loop() by the
  // cmd that started the action -> _lastCentral > now -> the
  // unsigned difference overflowed (~4 billion ms >= 120 s) and the
  // watchdog fired 8 ms after mode_start. Therefore: take the time freshly
  // here AND compare signed.
  PUN_PHASE(27);
  now = millis();
  if (_h && _h->isActive() && _lastCentral != 0 &&
      (long)(now - _lastCentral) >= (long) _cfg.centralTimeoutMs) {
    _lastCentral = 0;                 // fire once, not every round
    if (_centralAlive) { _centralAlive = false; if (_h) _h->onCentralLost(); }
    goSafe("central heartbeat timeout");
  }

  // --- State of the device (idle/active) ------------------------------
  PUN_PHASE(28);
  bool active = _h && _h->isActive();
  PunisherState want = active ? PD_ACTIVE : PD_IDLE;
  if (_state != want) { _state = want; publishState(); }

  // --- Own logic -----------------------------------------------------
  PUN_PHASE(29);
  if (_h) _h->onTick(now);

  // --- Heartbeat + periodic state ------------------------------------
  // (signed: publishState()/publishHeartbeat() may already have run in this
  //  round, then the stamp lies after `now`)
  PUN_PHASE(30);
  unsigned long hb = active ? _cfg.heartbeatActiveMs : _cfg.heartbeatIdleMs;
  if (_mqtt.connected() && (long)(now - _lastHeartbeat) >= (long) hb) publishHeartbeat();
  if (_mqtt.connected() && (long)(now - _lastState) >= (long) _cfg.stateIntervalMs) publishState();
  PUN_PHASE(31);
}

// =====================================================================
//  Serial console (2.3.2)
// =====================================================================
//
// WHY THIS EXISTS
//
// Everything the setup portal or a `config` command stored beats creds.h,
// silently, for the life of the device (applyStoredConfig). That is right
// while the stored value is the newer one and wrong the moment creds.h moves
// on — a collar provisioned before TLS kept `port = 1883` and talked TLS to
// the clear-text port until the watchdog killed it (finding Philine
// 2026-09-16). Until 2.3.1 there was no way out at the device: `port` is a
// protected key, and `factory_reset` arrives over MQTT, which a device that
// cannot connect never receives.
//
// The switch PUNISHER_NVS_CLEAR in creds.h is one way out, and it costs a
// flash. This is the other, and it costs a cable and one line typed — which
// is what one has in hand anyway when a device will not come in.
//
// NEVER BLOCKING. Every line here is read inside loop(). A console that waits
// for input is a watchdog reset with a prompt in front of it.
void PunisherDevice::serialConsole() {
  while (Serial.available()) {
    int c = Serial.read();
    if (c < 0 || c == '\r') continue;
    if (c != '\n') {
      // A line longer than the buffer is truncated, not wrapped: a wrapped
      // rest would arrive as its own "command" and could confirm something.
      if (_conLen < sizeof(_conBuf) - 1) _conBuf[_conLen++] = (char) c;
      continue;
    }
    _conBuf[_conLen] = 0;
    String line(_conBuf);
    _conLen = 0;
    line.trim();
    if (line.length()) consoleLine(line);
  }
  // A confirmation that nobody gives expires. Otherwise a `nvs clear` typed
  // yesterday would be waiting for the device name that somebody types today
  // for an entirely different reason.
  if (_conConfirm && (long) (millis() - _conConfirm) >= 0) {
    _conConfirm = 0;
    Serial.println(F("Abgebrochen: keine Bestaetigung."));
  }
}

void PunisherDevice::consoleShow() {
  Serial.println(F("--- Geraet ---"));
  Serial.printf("  Name       %s\n", _cfg.clientId ? _cfg.clientId : "?");
  Serial.printf("  UUID       %s\n", _cfg.deviceUuid ? _cfg.deviceUuid : "?");
  Serial.printf("  Modell     %s\n", _cfg.modelUuid ? _cfg.modelUuid : "?");
  Serial.printf("  MAC        %s\n", _ownMacTxt);
  Serial.printf("  Firmware   %s / Sketch %s %u.%u.%u\n", PUNISHERDEVICE_VERSION_STR,
                _cfg.sketchName ? _cfg.sketchName : "?", (unsigned) _cfg.sketchMajor,
                (unsigned) _cfg.sketchMinor, (unsigned) _cfg.sketchPatch);
  Serial.println(F("--- Verbindung ---"));
  Serial.printf("  WLAN       %s (%s, %d dBm)\n",
                WiFi.status() == WL_CONNECTED ? "verbunden" : "getrennt",
                WiFi.localIP().toString().c_str(),
                WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0);
  Serial.printf("  Broker     %s:%u, TLS %s\n", _cfg.broker ? _cfg.broker : "?",
                (unsigned) _cfg.port, _cfg.tls ? "an" : "aus");
  Serial.printf("  Konto      %s\n", _cfg.mqttUser ? _cfg.mqttUser : "(keines)");
  Serial.printf("  MQTT       %s\n", _mqtt.connected() ? "verbunden" : "getrennt");
  // WHERE EACH VALUE COMES FROM. Without this the console would show what the
  // device uses and still not say whether it can be changed by reflashing.
  Serial.println(F("--- gespeichert im NVS (schlaegt creds.h) ---"));
  bool any = false;
  static const char* KEYS[] = {"ssid", "pass", "broker", "port", "mqtt_user",
                               "mqtt_pass", "client_id", "model_uuid"};
  for (size_t i = 0; i < sizeof(KEYS) / sizeof(KEYS[0]); i++) {
    if (!_prefs.isKey(KEYS[i])) continue;
    any = true;
    // Secrets by name only. The console is for somebody with the cable in
    // hand, and that is still no reason to print the WLAN password.
    bool secret = !strcmp(KEYS[i], "pass") || !strcmp(KEYS[i], "mqtt_pass");
    if (secret) Serial.printf("  %-10s (gesetzt)\n", KEYS[i]);
    else if (!strcmp(KEYS[i], "port")) Serial.printf("  %-10s %u\n", KEYS[i], (unsigned) _cfg.port);
    else Serial.printf("  %-10s %s\n", KEYS[i], _prefs.getString(KEYS[i], "").c_str());
  }
  if (!any) Serial.println(F("  (nichts — es gelten die Werte aus creds.h)"));
  Serial.printf("--- Laufzeit %lu s, Heap %lu frei, groesster Block %lu ---\n",
                (unsigned long) (millis() / 1000), (unsigned long) ESP.getFreeHeap(),
                (unsigned long) ESP.getMaxAllocHeap());
}

void PunisherDevice::consoleLine(String line) {
  // A pending confirmation swallows the next line, whatever it says. That is
  // deliberate: the answer to "type the device name" must not be able to be a
  // command by accident.
  if (_conConfirm) {
    _conConfirm = 0;
    if (_cfg.clientId && line == _cfg.clientId) {
      // ASKED AGAIN, ON PURPOSE. Up to twenty seconds passed since the
      // question, and in those twenty seconds the central unit can have
      // started an action. The check at the command was about the state then;
      // this one is about the state now (finding while writing t_console.py).
      if (_h && _h->isActive()) {
        Serial.println(F("Abgelehnt: das Geraet ist inzwischen aktiv. Nichts geloescht."));
        return;
      }
      Serial.println(F("NVS wird geloescht, danach Neustart."));
      if (_h) _h->safeState();
      _prefs.clear();
      // Same reasoning as PUNISHER_NVS_CLEAR: the device was cleared so that
      // creds.h applies again, not so that it comes up in the setup portal.
      _prefs.putBool("provisioned", true);
      delay(200);
      ESP.restart();
    }
    Serial.println(F("Name stimmt nicht. Abgebrochen, nichts geloescht."));
    return;
  }
  if (line == "help" || line == "?") {
    Serial.println(F("  show       Zustand, Verbindung, was im NVS steht"));
    Serial.println(F("  nvs clear  gespeicherte Konfiguration loeschen (fragt nach)"));
    Serial.println(F("  reboot     neu starten"));
    return;
  }
  if (line == "show") { consoleShow(); return; }
  if (line == "nvs clear" || line == "reboot") {
    // NOT WHILE SOMETHING IS RUNNING. Both commands end this life of the
    // device, and a device that is acting on a person does not get restarted
    // because somebody had a console open. Same rule as the `config` command
    // with restart=true.
    if (_h && _h->isActive()) {
      Serial.println(F("Abgelehnt: das Geraet ist gerade aktiv."));
      return;
    }
    if (line == "reboot") {
      Serial.println(F("Neustart."));
      if (_h) _h->safeState();
      delay(200);
      ESP.restart();
    }
    Serial.printf("Loescht ALLES, was Portal und `config` gespeichert haben "
                  "(Broker, Konto, Port, Einstellungen).\n"
                  "Danach gelten wieder die Werte aus creds.h.\n"
                  "Zum Bestaetigen den Geraetenamen eingeben: %s\n",
                  _cfg.clientId ? _cfg.clientId : "?");
    _conConfirm = millis() + 20000;
    return;
  }
  Serial.printf("Unbekannt: '%s'. `help` zeigt die Befehle.\n", line.c_str());
}

// =====================================================================
//  One-time configuration (NVS / serial console)
// =====================================================================
static bool looksNumeric(const String& s) {
  if (s.length() == 0) return false;
  size_t i = (s[0] == '-') ? 1 : 0;
  if (i >= s.length()) return false;
  for (; i < s.length(); i++) if (!isdigit((int) s[i])) return false;
  return true;
}

long PunisherDevice::cfgInt(const char* key, long def) {
  if (!_prefs.isKey(key)) return def;
  // A value that was stored as text (older cfgSet) is still read as a number.
  if (_prefs.getType(key) == PT_STR) return atol(_prefs.getString(key, "").c_str());
  return _prefs.getLong(key, def);
}
String PunisherDevice::cfgStr(const char* key, const char* def) {
  if (!_prefs.isKey(key)) return String(def);
  return _prefs.getString(key, def);
}

// Protected keys: everything that brings the device into the network and into
// the installation. Anyone who could change these by command could lock a
// device out of the installation with a typo — and then only the cable helps.
static bool _cfgProtected(const char* key) {
  static const char* LOCKED[] = {"ssid", "pass", "broker", "port", "mqtt_user",
                                 "mqtt_pass", "client_id", "device_uuid",
                                 "model_uuid", "provisioned"};
  for (size_t i = 0; i < sizeof(LOCKED) / sizeof(LOCKED[0]); i++)
    if (!strcmp(key, LOCKED[i])) return true;
  return false;
}

bool PunisherDevice::cfgSet(const char* key, const char* value) {
  if (!key || !key[0] || strlen(key) > 15) return false;   // NVS: max. 15 characters
  if (_cfgProtected(key)) {
    logf("warn", "cfgSet('%s') refused: reserved for the setup portal", key);
    return false;
  }
  if (!value || !value[0]) {
    _prefs.remove(key);
    logf("info", "config '%s' cleared", key);
    return true;
  }
  // A number is stored as a number. cfgInt() reads with getLong(), and a
  // Preferences entry written as a string does not come back through
  // getLong() — it returns the default, silently. Until 2.2.0 this always
  // wrote strings; it only ever held one key (coyote_mac), which IS a string,
  // so nobody noticed.
  {
    const char* p = value;
    if (*p == '-') p++;
    bool numeric = *p != 0;
    for (; *p; p++) if (*p < '0' || *p > '9') { numeric = false; break; }
    if (numeric) {
      _prefs.remove(key);                       // a string of the same name would keep its type
      bool okn = _prefs.putLong(key, atol(value)) > 0;
      logf(okn ? "info" : "warn", "config '%s' = %s%s", key, value, okn ? "" : " FAILED");
      return okn;
    }
  }
  bool ok = _prefs.putString(key, value) > 0;
  logf(ok ? "info" : "warn", "config '%s' = '%s'%s", key, value, ok ? "" : " FAILED");
  return ok;
}

// Map the NVS values (if present) onto _cfg. The String members hold
// the buffers that _cfg then points to.
void PunisherDevice::applyStoredConfig() {
  // SAY WHAT WAS OVERRIDDEN. Until 2.3.1 this ran in silence, and a value
  // from the NVS looked exactly like one from creds.h — there was no way to
  // tell from the outside which of the two the device was running on. The
  // port from a pre-TLS portal run cost a day that way (2026-09-16). One line
  // at start, only when there is something to say; secrets by name only.
  String seen;
  #define OV(field, member, key, show)                   \
    if (_prefs.isKey(key)) {                             \
      member = _prefs.getString(key, _cfg.field);        \
      _cfg.field = member.c_str();                       \
      if (seen.length()) seen += ", ";                   \
      seen += key;                                       \
      if (show) { seen += "="; seen += member; }         \
    }
  OV(ssid,       _sSsid,      "ssid",       true);
  OV(password,   _sPass,      "pass",       false);
  OV(broker,     _sBroker,    "broker",     true);
  OV(mqttUser,   _sUser,      "mqtt_user",  true);
  OV(mqttPass,   _sMqttPass,  "mqtt_pass",  false);
  OV(clientId,   _sClient,    "client_id",  true);
  // device_uuid is NO LONGER taken from the NVS — it is derived.
  OV(modelUuid,  _sModelUuid, "model_uuid", true);
  #undef OV
  if (_prefs.isKey("port")) {
    _cfg.port = (uint16_t) _prefs.getUShort("port", _cfg.port);
    if (seen.length()) seen += ", ";
    seen += "port="; seen += String((unsigned) _cfg.port);
  }
  if (seen.length()) {
    Serial.print(F("[PunisherDevice] aus dem NVS statt aus creds.h: "));
    Serial.println(seen);
  }
}


// --------------------------------------------------------------------- //
bool PunisherDevice::isProvisioned() {
  return _prefs.getBool("provisioned", false);
}

void PunisherDevice::factoryReset() {
  // Deregister cleanly: set retained offline, so that the central unit does not
  // have to wait for the LWT. Same topic as the will (see connectMqtt) — one
  // place that says whether a device is there, not two that can disagree.
  publishRaw(_tAvailable, "offline", true);
  _prefs.clear();
  delay(200);
  ESP.restart();
}

static void htmlAttr(String& out, const char* v) {
  String s = v ? String(v) : String();
  s.replace("&", "&amp;"); s.replace("'", "&#39;"); s.replace("<", "&lt;");
  out += s;
}

String PunisherDevice::configFormHtml() {
  char portbuf[8]; snprintf(portbuf, sizeof(portbuf), "%u", _cfg.port);
  String h = F("<!doctype html><html><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>Punisher Setup</title><style>body{font-family:sans-serif;max-width:34em;"
    "margin:1em auto;padding:0 1em}label{display:block;margin:.6em 0 .15em;font-size:.9em}"
    "input,textarea{width:100%;padding:.4em;box-sizing:border-box}h1{font-size:1.2em}"
    ".hint{color:#888;font-weight:normal;font-size:.85em}"
    "button{margin-top:1em;padding:.6em 1.2em}</style></head><body>"
    "<h1>Punisher Geraete-Setup</h1><form method=POST action=/save>");
  // A SECRET IS NOT SENT BACK OUT (2.1.0).
  //
  // Until 2.1.0 the WLAN and MQTT passwords stood in the `value=` of a plain
  // text input. Whoever reached this page read both in clear — and the page is
  // reachable over an access point whose password is the same on every device
  // of this kind (finding Philine 2026-09-15). A setup page is not a password
  // safe: it is there to SET something, and setting does not require being
  // shown what is already there.
  //
  // Empty means unchanged. The save handler has always only written non-empty
  // fields, so this needs no second mechanism — only that the field arrives
  // empty and says why.
  struct F2 { const char* label; const char* name; const char* val; bool secret; };
  F2 fields[] = {
    {"Client-ID (Hostname)", "client_id",   _cfg.clientId, false},
    {"Model UUID",           "model_uuid",  _cfg.modelUuid, false},
    {"WLAN SSID",            "ssid",        _cfg.ssid,      false},
    {"WLAN Passwort",        "pass",        _cfg.password,  true},
    {"MQTT Broker",          "broker",      _cfg.broker,    false},
    {"MQTT Port",            "port",        portbuf,        false},
    {"MQTT Benutzer",        "mqtt_user",   _cfg.mqttUser,  false},
    {"MQTT Passwort",        "mqtt_pass",   _cfg.mqttPass,  true},
  };
  for (auto& f : fields) {
    h += "<label>"; h += f.label;
    if (f.secret) {
      // Say whether something is stored — that much is useful and gives
      // nothing away — but never what.
      h += (f.val && f.val[0]) ? " <span class=hint>(gesetzt, leer lassen = unveraendert)</span>"
                               : " <span class=hint>(nicht gesetzt)</span>";
    }
    h += "</label><input name='"; h += f.name;
    if (f.secret) {
      h += "' type=password autocomplete=new-password value=''>";
    } else {
      h += "' value='"; htmlAttr(h, f.val); h += "'>";
    }
  }
  h += F("<label>Zusatz (key=wert pro Zeile, geraetespezifische Schluessel; die Huellkurve ist fest einkompiliert)</label>"
         "<textarea name=extra rows=4></textarea>"
         "<button type=submit>Speichern &amp; Neustart</button></form>"
         "<p style='color:#888;font-size:.8em'>Nach dem Speichern startet das Geraet "
         "neu und verbindet sich normal.</p></body></html>");
  return h;
}

void PunisherDevice::runConfigPortal() {
  if (_h) _h->safeState();
  String apSsid = String(_cfg.clientId) + "-setup";
  const char* apPass = (_cfg.apPassword && _cfg.apPassword[0]) ? _cfg.apPassword : nullptr;
  WiFi.mode(WIFI_AP);
  WiFi.softAP(apSsid.c_str(), apPass);
  IPAddress ip = WiFi.softAPIP();
  Serial.printf("\n[Config] AP '%s' pass '%s' -> http://%s/\n",
                apSsid.c_str(), apPass ? apPass : "(offen)", ip.toString().c_str());

  // Captive portal: every DNS name -> AP address, every foreign URL -> the form.
  // That way the "sign in" window opens automatically when connecting,
  // without one having to know the IP.
  DNSServer dns;
  dns.start(53, "*", ip);

  WebServer server(80);
  bool done = false;
  String rootUrl = String("http://") + ip.toString() + "/";

  auto redirectToForm = [&]() {
    server.sendHeader("Location", rootUrl, true);
    server.sendHeader("Cache-Control", "no-cache");
    server.send(302, "text/plain", "");
  };

  server.on("/", HTTP_GET, [&]() {
    server.send(200, "text/html; charset=utf-8", configFormHtml());
  });
  // Known portal detection URLs of the operating systems -> redirect
  server.on("/generate_204",        redirectToForm);   // Android
  server.on("/gen_204",             redirectToForm);   // Android (old)
  server.on("/hotspot-detect.html", redirectToForm);   // iOS / macOS
  server.on("/library/test/success.html", redirectToForm); // iOS (old)
  server.on("/connecttest.txt",     redirectToForm);   // Windows
  server.on("/ncsi.txt",            redirectToForm);   // Windows (old)
  server.on("/fwlink",              redirectToForm);   // Windows
  server.on("/canonical.html",      redirectToForm);   // Firefox
  server.on("/success.txt",         redirectToForm);   // Firefox
  server.onNotFound(redirectToForm);                   // everything else
  server.on("/save", HTTP_POST, [&]() {
    auto save = [&](const char* name) {
      if (server.hasArg(name)) {
        String v = server.arg(name);
        if (v.length()) _prefs.putString(name, v);
      }
    };
    save("client_id"); save("model_uuid");   // device_uuid is derived
    save("ssid"); save("pass"); save("broker");
    save("mqtt_user"); save("mqtt_pass");
    if (server.hasArg("port") && server.arg("port").length())
      _prefs.putUShort("port", (uint16_t) server.arg("port").toInt());

    String rejected;                                  // NVS: key max. 15 characters
    if (server.hasArg("extra")) {                    // key=value per line
      String ex = server.arg("extra");
      int start = 0;
      while (start < (int) ex.length()) {
        int nl = ex.indexOf('\n', start); if (nl < 0) nl = ex.length();
        String line = ex.substring(start, nl); line.trim();
        int eq = line.indexOf('=');
        if (eq > 0) {
          String k = line.substring(0, eq); k.trim();
          String v = line.substring(eq + 1); v.trim();
          if (k.length() > 15) {
            rejected += k; rejected += " (zu lang, max 15) ";
          } else if (k.length()) {
            if (looksNumeric(v)) _prefs.putLong(k.c_str(), v.toInt());
            else                 _prefs.putString(k.c_str(), v);
          }
        }
        start = nl + 1;
      }
    }
    _prefs.putBool("provisioned", true);
    String page = F("<!doctype html><meta charset=utf-8><body style='font-family:sans-serif'>"
                    "<h1>Gespeichert</h1><p>Das Geraet startet neu ...</p>");
    if (rejected.length()) {
      page += F("<p style='color:#b00'>Nicht gespeichert (Schluessel zu lang): ");
      page += rejected; page += F("</p>");
    }
    page += F("</body>");
    server.send(200, "text/html; charset=utf-8", page);
    done = true;
  });
  server.begin();

  // Remind every 10 s WHERE the device is. Without this hint a waiting portal
  // looks in the serial monitor like a hanging device —
  // and that is exactly what one then searches for, for hours (Philine, 2026-09-11).
  unsigned long lastHint = 0;
  while (true) {
    feedWdt();
    dns.processNextRequest();
    server.handleClient();
    if (done) { delay(500); ESP.restart(); }
    unsigned long now = millis();
    if (now - lastHint >= 10000) {
      lastHint = now;
      Serial.printf("[Config] warte auf Einrichtung — WLAN '%s', dann http://%s/ "
                    "(%d verbunden)\n",
                    apSsid.c_str(), ip.toString().c_str(), WiFi.softAPgetStationNum());
    }
    delay(2);
  }
}
