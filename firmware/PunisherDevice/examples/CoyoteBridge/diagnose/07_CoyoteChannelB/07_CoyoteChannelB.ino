// =====================================================================
//  Stufe 7 — UND WAS IST MIT KANAL B?
//
//  Stufe 6 hat Kanal A geklärt (Philine 11.09.2026): Ausgabe kam bei
//
//      Versuch 2  Stärke Bit 21-11 = 420,  Wellenform nach 0x1506   -> JA
//      Versuch 4  beide Stärken,           Wellenform auf beide     -> JA
//      Versuch 1  Stärke Bit 21-11 = 420,  Wellenform nach 0x1505   -> nein
//      Versuch 3  Stärke Bit 10-0  = 420,  Wellenform nach 0x1505   -> nein
//
//  Damit ist EIN Paar bewiesen: die obere Stärkehälfte gehört zu 0x1506, und
//  dieses Paar gibt aus. Das ist der Kanal, den die Brücke ab sofort „A" nennt.
//
//  ABER: Versuch 3 hätte Kanal B sein sollen, und der blieb still. Das ist
//  nicht bewiesen falsch, es ist UNGEKLÄRT — und ein Kanal, von dem wir nicht
//  wissen, ob er ausgibt, ist im Betrieb schlimmer als einer, der es nicht tut.
//  Die halbe Anlage (Belohnung läuft auf B, Doc 19 §6.2) hängt daran.
//
//  Vier kurze Versuche, die die Frage einkreisen. Jeder sagt an, was er prüft.
//
//  ACHTUNG: gibt WIRKLICH aus, Stärke 420 (App etwa 60).
//  WENN MÖGLICH: Elektroden NUR an Kanal B stecken und dazuschreiben, ob und
//  wann es dort ankommt. Sonst reicht die Leistungsanzeige — dann bitte sagen,
//  ob sie eine Seite oder zwei anzeigt.
// =====================================================================

#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

#define STRENGTH   420
#define HOLD_S       4
#define SCAN_S       6

static NimBLEUUID svcV2() { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uAB2()  { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID u1505() { return NimBLEUUID("955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID u1506() { return NimBLEUUID("955a1506-0fe2-f5aa-a094-84b8d4f3e8ad"); }

static NimBLEClient* client = nullptr;
static NimBLERemoteCharacteristic *ab2 = nullptr, *c1505 = nullptr, *c1506 = nullptr;

static bool put(NimBLERemoteCharacteristic* c, uint32_t p) {
  if (!c) return false;
  uint8_t b[3] = { (uint8_t)(p & 0xFF), (uint8_t)((p >> 8) & 0xFF), (uint8_t)((p >> 16) & 0xFF) };
  return c->writeValue(b, 3, false);
}
// hi = Bit 21-11, lo = Bit 10-0. Absichtlich NICHT "A" und "B" genannt:
// welche Hälfte welcher Buchse gehört, ist genau die offene Frage.
static uint32_t packStrength(uint16_t hi, uint16_t lo) {
  if (hi > 2047) hi = 2047;
  if (lo > 2047) lo = 2047;
  return ((uint32_t) hi << 11) | (uint32_t) lo;
}
static uint32_t packWave(uint8_t x, uint16_t y, uint8_t z) {
  return ((uint32_t)(z & 0x1F) << 15) | ((uint32_t)(y & 0x3FF) << 5) | (uint32_t)(x & 0x1F);
}

static void trial(const char* name, uint16_t hi, uint16_t lo,
                  bool on1505, bool on1506, const char* frage) {
  Serial.println();
  Serial.println("-------------------------------------------------");
  Serial.printf("VERSUCH: %s\n", name);
  Serial.printf("   Staerke  Bit21-11=%u  Bit10-0=%u   |   Z=20 auf %s%s\n",
                hi, lo, on1505 ? "0x1505 " : "", on1506 ? "0x1506" : "");
  Serial.printf("   Frage: %s\n", frage);
  Serial.println("   >>> JETZT hinschauen (Anzeige, und wenn Elektroden dran: wo) <<<");
  put(ab2, packStrength(hi, lo));
  delay(120);
  unsigned long tEnd = millis() + (unsigned long) HOLD_S * 1000UL;
  while ((long)(millis() - tEnd) < 0) {
    put(c1505, packWave(1, 9, on1505 ? 20 : 0));
    put(c1506, packWave(1, 9, on1506 ? 20 : 0));
    delay(100);
  }
  put(c1505, packWave(1, 9, 0));
  put(c1506, packWave(1, 9, 0));
  put(ab2, packStrength(0, 0));
  delay(400);                 // sonst geht das Abschalten beim Trennen verloren
  Serial.println("   (aus)");
  delay(1500);
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 7: und was ist mit Kanal B? ===");
  Serial.println("ACHTUNG: gibt WIRKLICH aus. Wenn moeglich Elektroden NUR an Kanal B.");
  Serial.println("Start in 5 s ...");
  delay(5000);

  NimBLEDevice::init("PunisherChanB");
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
  if (target < 0) { Serial.println("Keine V2 gefunden."); return; }
#if COYOTE_NIMBLE_V2
  const NimBLEAdvertisedDevice* adv = res.getDevice(target);
#else
  NimBLEAdvertisedDevice* adv = const_cast<NimBLEAdvertisedDevice*>(res.getDevice(target));
#endif
  client = NimBLEDevice::createClient();
  client->setConnectTimeout(5000);
  if (!client->connect(const_cast<NimBLEAdvertisedDevice*>(adv))) {
    Serial.println("Verbinden fehlgeschlagen."); return;
  }
  NimBLERemoteService* s = client->getService(svcV2());
  if (!s) { Serial.println("Dienst fehlt."); return; }
  ab2 = s->getCharacteristic(uAB2());
  c1505 = s->getCharacteristic(u1505());
  c1506 = s->getCharacteristic(u1506());
  if (!ab2 || !c1505 || !c1506) { Serial.println("Charakteristik fehlt."); return; }
  Serial.println("verbunden.");
  Serial.println();
  Serial.println("Zur Erinnerung, schon bewiesen: Bit21-11 + 0x1506 gibt aus.");
  Serial.println("Offen ist nur, ob es die ZWEITE Seite ueberhaupt gibt.");

  // A: Bekommt 0x1506 seine Hoehe vielleicht aus der UNTEREN Haelfte?
  //    Dann waere unser ganzes Bild der Staerkeaufteilung falsch.
  trial("A) untere Staerkehaelfte + 0x1506",
        0, STRENGTH, false, true,
        "Haengt 0x1506 doch an der unteren Staerkehaelfte?");

  // B: 0x1505 mit BEIDEN Staerken. Wenn 0x1505 ueberhaupt je ausgibt, dann hier.
  trial("B) BEIDE Staerkehaelften + nur 0x1505",
        STRENGTH, STRENGTH, true, false,
        "Gibt 0x1505 unter irgendeiner Bedingung aus?");

  // C: Die zweite Buchse mit der oberen Haelfte - falls beide Register an
  //    derselben Haelfte haengen und sich nur die Buchse unterscheidet.
  trial("C) obere Staerkehaelfte + nur 0x1505",
        STRENGTH, 0, true, false,
        "Wie Versuch 1 aus Stufe 6 - zur Gegenkontrolle, bleibt es dabei?");

  // D: Beides voll, aber nur 0x1506 - der bekannte Gutfall als Bezugspunkt.
  //    Wenn HIER nichts kommt, war etwas an diesem Durchgang anders.
  trial("D) beide Staerken + nur 0x1506   (bekannter Gutfall)",
        STRENGTH, STRENGTH, false, true,
        "Kontrolle: hier MUSS Ausgabe kommen, sonst stimmt am Aufbau etwas nicht");

  Serial.println();
  Serial.println("=================================================");
  Serial.println("Fertig, alles auf null.");
  Serial.println("BITTE je Versuch A-D: Ausgabe ja/nein, und wenn Elektroden dran:");
  Serial.println("an welcher Buchse.");
  Serial.println();
  Serial.println("Kommt bei A etwas  -> die Staerkehaelften sind anders verteilt,");
  Serial.println("                      als die Doku sagt.");
  Serial.println("Kommt bei B etwas  -> 0x1505 lebt, es brauchte nur die andere Haelfte.");
  Serial.println("Kommt bei B und C nichts, bei D aber schon  -> dieses Geraet gibt nur");
  Serial.println("                      ueber EINEN Kanal aus. Dann ist das keine");
  Serial.println("                      Software-Frage mehr, sondern eine am Geraet:");
  Serial.println("                      sitzt an Buchse B ueberhaupt ein Kabel?");
  delay(500);
  client->disconnect();
}

void loop() { delay(1000); }
