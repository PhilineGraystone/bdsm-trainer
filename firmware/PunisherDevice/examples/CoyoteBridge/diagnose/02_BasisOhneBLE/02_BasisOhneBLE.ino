// =====================================================================
//  Stufe 2 der Fehlersuche — die PunisherDevice-Basis ALLEIN.
//
//  WLAN, MQTT, NVS und das Config-Portal, aber KEIN NimBLE und keine
//  Brückenlogik. Damit trennt sich, ob die gemeinsame Basis auf dem S3
//  läuft (sie lief bisher nur auf klassischen ESP32) oder ob die Brücke
//  darüber das Problem ist.
//
//  Erwartet nach dem Flashen eines JUNGFRÄULICHEN Geräts:
//     [PunisherDevice] diagnose-s3 DIAG-1.0 boot
//     [Config] AP 'diagnose-s3-setup' pass 'punisher-setup' -> http://192.168.4.1/
//  und ein sichtbares WLAN 'diagnose-s3-setup'. Das Blockieren im Portal
//  ist KEIN Fehler, sondern das normale Verhalten ohne Konfiguration.
// =====================================================================
#include "PunisherDevice.h"

PunisherDevice dev;
static const char* CAPS[] = {"diag"};

class DiagHandler : public PunisherHandler {
 public:
  void safeState() override { Serial.println("[diag] safeState()"); }
  bool onCommand(const char* action, JSONVar& args, char* err, size_t errLen) override {
    (void) args;
    Serial.printf("[diag] Kommando '%s'\n", action);
    snprintf(err, errLen, "diagnose kennt keine Aktionen");
    return false;
  }
  void reportState(JSONVar& j) override { j["diag"] = true; }
  void onTick(unsigned long now) override {
    if (now - _last < 5000) return;
    _last = now;
    Serial.printf("[diag] %lu s, RAM %u kB, WLAN %d, MQTT %d\n",
                  now / 1000, ESP.getFreeHeap() / 1024,
                  (int) WiFi.status(), (int) dev.mqttConnected());
  }
 private:
  unsigned long _last = 0;
};
DiagHandler handler;

void setup() {
  PunisherConfig cfg;
  cfg.ssid = "CHANGEME-SSID";
  cfg.password = "CHANGEME-WLAN";
  cfg.broker = "CHANGEME-BROKER";
  cfg.mqttUser = "CHANGEME-USER";
  cfg.mqttPass = "CHANGEME-PASS";
  cfg.clientId = "diagnose-s3";
  cfg.modelUuid = "00000000-0000-4000-8000-000000000000";
  cfg.deviceUuid = "00000000-0000-4000-8000-0000000000d1";
  cfg.fwVersion = "DIAG-1.0";
  cfg.capabilities = CAPS;
  cfg.capabilityCount = 1;
  dev.begin(cfg, handler);
  Serial.println("[diag] begin() ist zurückgekehrt - Gerät ist konfiguriert");
}

void loop() { dev.loop(); }
