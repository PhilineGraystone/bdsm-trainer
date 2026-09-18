// =====================================================================
//  Stufe 5 — DIE ZWEI HÄLFTEN GETRENNT: Stärke und Wellenform
//
//  Was Stufe 4 bewiesen hat (Messung Philine 11.09.2026):
//    * PWM_AB2, PWM_A34 und PWM_B34 melden write=0, write_nr=1 — sie können
//      NUR ohne Antwort beschrieben werden. Unsere alte Schreibart war also
//      richtig, meine Vermutung war falsch.
//    * Beide Schreibwege kommen an: zurückgelesen kommt exakt heraus, was
//      hineinging. Die Strecke ESP -> Coyote funktioniert.
//
//  Damit ist klar, was Stufe 4 NICHT konnte: sie hat je Charakteristik EINMAL
//  geschrieben. Die Hersteller-Doku sagt aber (v2/README.md):
//
//      „每一组【X,Y,Z】参数仅在 0.1S 时间内有效 … 如果你需要波形持续输出，
//       那么你需要每隔 0.1 秒向设备发送参数【1,9,20】"
//      (Jeder Satz X/Y/Z gilt nur 0,1 s. Für eine anhaltende Ausgabe muss man
//       alle 0,1 s neu senden.)
//
//  Ein einzelner Schreibvorgang ergibt also 100 ms Ausgabe und dann Stille —
//  zu kurz, um es zu bemerken, wenn man dabei auf die Konsole schaut.
//
//  DIESE SKIZZE TRENNT DIE ZWEI HÄLFTEN, und das ist ihr ganzer Zweck:
//
//    PHASE A — nur die STÄRKE, keine Wellenform.
//      Die Stärke ist das, was die Coyote in ihrem Ring anzeigt. Sie bleibt
//      im Gerät stehen, bis jemand sie ändert. Wenn die ANZEIGE beim Hochgehen
//      mitgeht, kommt die Stärke an — unabhängig davon, ob Impulse herauskommen.
//      Geht sie NICHT mit, ist die Anzeige der Beweis, dass unsere Schreib-
//      vorgänge zwar in der Charakteristik landen, aber nichts bewirken.
//
//    PHASE B — Stärke bleibt stehen, jetzt der STROM von Wellenformrahmen.
//      Alle 100 ms {1,9,20} = 100 Hz, 100 µs. Genau das, was die Brücke tut,
//      und genau das, was Stufe 4 nicht getan hat.
//
//  Danach wissen wir, welche der beiden Hälften fehlt. Vorher raten wir.
//
//  ACHTUNG: DAS GIBT WIRKLICH AUS. Elektroden abziehen. Die Stärke geht bis
//  STRENGTH_MAX (Vorgabe 700 von 2047, in der App etwa 100).
//
//  Bitte notieren: was macht die ANZEIGE der Coyote in Phase A, was in Phase B?
// =====================================================================

#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

#define STRENGTH_MAX   700     // 0..2047. 700 entspricht in der App etwa 100.
#define STEP_MS       1500     // wie lange jede Stufe in Phase A steht
#define STREAM_S         8     // Dauer des Rahmenstroms in Phase B
#define SCAN_S           6

static NimBLEUUID svcV2()  { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID c1503()  { return NimBLEUUID("955a1503-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID ab2V2()  { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID a34V2()  { return NimBLEUUID("955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID b34V2()  { return NimBLEUUID("955a1506-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID c1507()  { return NimBLEUUID("955a1507-0fe2-f5aa-a094-84b8d4f3e8ad"); }

static NimBLEClient* client = nullptr;
static NimBLERemoteCharacteristic *ab2 = nullptr, *a34 = nullptr, *b34 = nullptr;
static NimBLERemoteCharacteristic *x1503 = nullptr, *x1507 = nullptr;

static void hex(const uint8_t* d, size_t n) { for (size_t i = 0; i < n; i++) Serial.printf("%02X", d[i]); }

static void show(const char* what, NimBLERemoteCharacteristic* c) {
  if (!c || !c->canRead()) { Serial.printf("   %s: nicht lesbar\n", what); return; }
  std::string v = c->readValue();
  Serial.printf("   %s = ", what);
  hex((const uint8_t*) v.data(), v.size());
  Serial.println();
}

// Schreiben IMMER ohne Antwort: genau das, und nur das, bieten diese
// Charakteristiken an (Messung Stufe 4: write=0, write_nr=1).
static bool put(NimBLERemoteCharacteristic* c, uint32_t packed) {
  if (!c) return false;
  uint8_t b[3] = { (uint8_t)(packed & 0xFF), (uint8_t)((packed >> 8) & 0xFF),
                   (uint8_t)((packed >> 16) & 0xFF) };
  return c->writeValue(b, 3, false);
}

// PWM_AB2: Bit 21-11 = Stärke A, Bit 10-0 = Stärke B.
static uint32_t packStrength(uint16_t a, uint16_t b) {
  if (a > 2047) a = 2047;
  if (b > 2047) b = 2047;
  return ((uint32_t) a << 11) | (uint32_t) b;
}
// PWM_A34/B34: Bit 19-15 = Z, Bit 14-5 = Y, Bit 4-0 = X.
static uint32_t packWave(uint8_t x, uint16_t y, uint8_t z) {
  return ((uint32_t)(z & 0x1F) << 15) | ((uint32_t)(y & 0x3FF) << 5) | (uint32_t)(x & 0x1F);
}

static uint16_t readStrengthA() {
  if (!ab2 || !ab2->canRead()) return 0xFFFF;
  std::string v = ab2->readValue();
  if (v.size() < 3) return 0xFFFF;
  const uint8_t* d = (const uint8_t*) v.data();
  uint32_t p = (uint32_t) d[0] | ((uint32_t) d[1] << 8) | ((uint32_t) d[2] << 16);
  return (uint16_t)((p >> 11) & 0x7FF);
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 5: Staerke und Wellenform getrennt ===");
  Serial.println("ACHTUNG: das gibt WIRKLICH aus. Elektroden abziehen.");
  Serial.println("Bitte die ANZEIGE der Coyote beobachten, nicht die Haut.");
  Serial.println("Start in 5 s ...");
  delay(5000);

  NimBLEDevice::init("PunisherStream");
  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);
#if COYOTE_NIMBLE_V2
  NimBLEScanResults res = scan->getResults(SCAN_S * 1000, false);
#else
  NimBLEScanResults res = scan->start(SCAN_S, false);
#endif
  int target = -1;
  for (int i = 0; i < res.getCount(); i++) {
#if COYOTE_NIMBLE_V2
    const NimBLEAdvertisedDevice* adv = res.getDevice(i);
#else
    NimBLEAdvertisedDevice* adv = const_cast<NimBLEAdvertisedDevice*>(res.getDevice(i));
#endif
    if (adv && String(adv->getName().c_str()) == "D-LAB ESTIM01") { target = i; break; }
  }
  if (target < 0) {
    Serial.println("Keine V2 gefunden. Haengt sie am Handy? Dann annonciert sie nicht.");
    return;
  }
#if COYOTE_NIMBLE_V2
  const NimBLEAdvertisedDevice* adv = res.getDevice(target);
#else
  NimBLEAdvertisedDevice* adv = const_cast<NimBLEAdvertisedDevice*>(res.getDevice(target));
#endif
  client = NimBLEDevice::createClient();
  client->setConnectTimeout(5000);
  if (!client->connect(const_cast<NimBLEAdvertisedDevice*>(adv))) {
    Serial.println("Verbinden fehlgeschlagen.");
    return;
  }
  Serial.println("verbunden.");
  NimBLERemoteService* s = client->getService(svcV2());
  if (!s) { Serial.println("Dienst 955a180b fehlt."); return; }
  ab2   = s->getCharacteristic(ab2V2());
  a34   = s->getCharacteristic(a34V2());
  b34   = s->getCharacteristic(b34V2());
  x1503 = s->getCharacteristic(c1503());
  x1507 = s->getCharacteristic(c1507());

  Serial.println("\nVORHER:");
  show("1503 (undokumentiert)", x1503);
  show("1504 PWM_AB2 Staerke  ", ab2);
  show("1505 PWM_A34          ", a34);
  show("1506 PWM_B34          ", b34);
  show("1507 (undokumentiert) ", x1507);

  // ---------------- PHASE A: nur die Staerke -------------------------
  Serial.println();
  Serial.println("=== PHASE A: NUR die Staerke, KEINE Wellenform ===");
  Serial.println("Die Staerke ist das, was die Coyote in ihrem Ring anzeigt.");
  Serial.println("BITTE JETZT AUF DIE ANZEIGE SCHAUEN: geht sie mit?");
  Serial.println("(Impulse darf es hier keine geben - ohne X/Y/Z kommt nichts.)");
  const uint16_t steps[] = { 0, 140, 280, 420, 560, (uint16_t) STRENGTH_MAX };
  for (unsigned i = 0; i < sizeof(steps) / sizeof(steps[0]); i++) {
    put(ab2, packStrength(steps[i], 0));
    delay(200);
    uint16_t back = readStrengthA();
    Serial.printf("  Staerke A geschrieben %4u  ->  zurueckgelesen %4u  (App-Anzeige etwa %u)%s\n",
                  steps[i], back, (unsigned)(steps[i] / 7),
                  back == steps[i] ? "" : "   ** WEICHT AB **");
    delay(STEP_MS);
  }

  // ---------------- PHASE B: der Rahmenstrom -------------------------
  Serial.println();
  Serial.println("=== PHASE B: Staerke bleibt stehen, jetzt der STROM ===");
  Serial.printf("Alle 100 ms {X=1,Y=9,Z=20} = 100 Hz, 100 us, %d s lang.\n", STREAM_S);
  Serial.println("Genau das tut die Bruecke. Stufe 4 hat NUR EINMAL geschrieben -");
  Serial.println("und ein Satz X/Y/Z gilt laut Doku nur 0,1 s.");
  Serial.println("BITTE AUF DIE ANZEIGE SCHAUEN: aendert sich jetzt etwas?");
  unsigned long tEnd = millis() + (unsigned long) STREAM_S * 1000UL;
  unsigned long lastSay = 0;
  uint32_t frames = 0;
  while ((long)(millis() - tEnd) < 0) {
    put(a34, packWave(1, 9, 20));       // Kanal A: der Arbeitswert der Doku
    put(b34, packWave(1, 9, 0));        // Kanal B ausdruecklich still
    frames++;
    if (millis() - lastSay >= 1000) {
      lastSay = millis();
      Serial.printf("  ... %lu Rahmen, Staerke A jetzt %u\n",
                    (unsigned long) frames, readStrengthA());
    }
    delay(100);
  }

  Serial.println();
  Serial.println("NACHHER:");
  show("1503 (undokumentiert)", x1503);
  show("1504 PWM_AB2 Staerke  ", ab2);
  show("1505 PWM_A34          ", a34);
  show("1506 PWM_B34          ", b34);
  show("1507 (undokumentiert) ", x1507);

  // Alles aus. Ohne Rahmen hoert die Ausgabe nach 0,1 s von selbst auf, aber
  // die Staerke bleibt stehen - die muss ausdruecklich zurueck.
  put(a34, packWave(1, 9, 0));
  put(b34, packWave(1, 9, 0));
  put(ab2, packStrength(0, 0));
  Serial.println("\nAlles auf null. Fertig.");
  Serial.println();
  Serial.println("BITTE ZURUECKMELDEN, in genau diesen zwei Punkten:");
  Serial.println("  1. PHASE A - ging die ANZEIGE der Coyote mit hoch?");
  Serial.println("  2. PHASE B - kam waehrend des Stroms Ausgabe (Anzeige/Ton/Gefuehl)?");
  client->disconnect();
}

void loop() { delay(1000); }
