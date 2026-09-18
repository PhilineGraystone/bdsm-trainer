// =====================================================================
//  Stufe 6 — WELCHE CHARAKTERISTIK IST WELCHER KANAL?
//
//  Das ist jetzt keine Vermutung mehr, sondern die einzige Erklärung, die zu
//  allen vier Messungen passt.
//
//  WAS WIR WISSEN (Stufe 4 und 5, Philine 11.09.2026):
//    * Die Bytes kommen an. Zurückgelesen kommt exakt heraus, was hineinging.
//    * Die Stärke wird gespeichert: 0, 140, 280, 420, 560, 700 — alle sauber
//      zurückgelesen.
//    * Während des Rahmenstroms BLINKT die Status-LED der Coyote. Das Gerät
//      verarbeitet die Wellenformrahmen also.
//    * Und trotzdem: die LEISTUNGSANZEIGE bleibt aus, es kommt nichts heraus.
//
//  WAS DAS BEDEUTET
//  Die offizielle Tabelle (coyote/v2/README.md) sagt in ihrer Beschreibungs-
//  spalte etwas anderes als in ihren Bitnamen — und wir haben uns bisher auf
//  die Bitnamen verlassen:
//
//      | PWM_A34 | B 通道波形数据  (B-Kanal-Wellenformdaten) | … Az, Ay, Ax |
//      | PWM_B34 | A 通道波形数据  (A-Kanal-Wellenformdaten) | … Bz, By, Bx |
//
//  Nimmt man die BESCHREIBUNG ernst, erklärt sich alles: wir haben die Stärke
//  auf Kanal A gelegt (700) und die Wellenform nach 0x1505 geschrieben — also
//  auf Kanal B, dessen Stärke 0 ist. Und die stille Wellenform (Z=0) ging nach
//  0x1506, also auf Kanal A, der die Höhe hatte.
//
//      Kanal A:  Höhe 700, Breite 0   ->  nichts
//      Kanal B:  Höhe 0,   Breite 20  ->  nichts
//
//  Zwei halbe Kanäle, kein ganzer. Genau das, was zu sehen war: das Gerät
//  arbeitet (Status-LED), aber es kommt nirgends etwas heraus.
//
//  DIESE SKIZZE PROBIERT ALLE VIER KOMBINATIONEN DURCH und sagt jede an.
//  Die Leistungsanzeige der Coyote ist der Zeuge — die Haut braucht es nicht.
//
//  ACHTUNG: gibt WIRKLICH aus, Stärke bis STRENGTH (Vorgabe 420, App etwa 60).
//  Elektroden abziehen. Wenn du mit Elektroden messen willst, steck sie NUR an
//  EINEN Kanal und schreib dazu, an welchen.
// =====================================================================

#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

#define STRENGTH     420     // 0..2047, entspricht in der App etwa 60
#define HOLD_S         4     // wie lange jede Kombination streamt
#define SCAN_S         6

static NimBLEUUID svcV2() { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uAB2()  { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uA34()  { return NimBLEUUID("955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uB34()  { return NimBLEUUID("955a1506-0fe2-f5aa-a094-84b8d4f3e8ad"); }

static NimBLEClient* client = nullptr;
static NimBLERemoteCharacteristic *ab2 = nullptr, *c1505 = nullptr, *c1506 = nullptr;

// Diese Charakteristiken bieten NUR "ohne Antwort" an (Messung Stufe 4).
static bool put(NimBLERemoteCharacteristic* c, uint32_t p) {
  if (!c) return false;
  uint8_t b[3] = { (uint8_t)(p & 0xFF), (uint8_t)((p >> 8) & 0xFF), (uint8_t)((p >> 16) & 0xFF) };
  return c->writeValue(b, 3, false);
}
static uint32_t packStrength(uint16_t a, uint16_t b) {
  if (a > 2047) a = 2047;
  if (b > 2047) b = 2047;
  return ((uint32_t) a << 11) | (uint32_t) b;
}
static uint32_t packWave(uint8_t x, uint16_t y, uint8_t z) {
  return ((uint32_t)(z & 0x1F) << 15) | ((uint32_t)(y & 0x3FF) << 5) | (uint32_t)(x & 0x1F);
}

// Eine Kombination: Stärke setzen, dann HOLD_S Sekunden Rahmen streamen.
// Nur die Charakteristik, die "aktiv" sein soll, bekommt Z=20; die andere Z=0.
static void trial(const char* name, uint16_t sA, uint16_t sB,
                  bool on1505, bool on1506, const char* expect) {
  Serial.println();
  Serial.println("-------------------------------------------------");
  Serial.printf("VERSUCH: %s\n", name);
  Serial.printf("   Staerke A=%u  B=%u   |   Z=20 auf %s%s%s\n", sA, sB,
                on1505 ? "0x1505 " : "", on1506 ? "0x1506" : "",
                (!on1505 && !on1506) ? "nichts" : "");
  Serial.printf("   Erwartung, wenn die Doku-Beschreibung stimmt: %s\n", expect);
  Serial.println("   >>> JETZT auf die LEISTUNGSANZEIGE der Coyote schauen <<<");
  put(ab2, packStrength(sA, sB));
  delay(120);
  unsigned long tEnd = millis() + (unsigned long) HOLD_S * 1000UL;
  uint32_t n = 0;
  while ((long)(millis() - tEnd) < 0) {
    put(c1505, packWave(1, 9, on1505 ? 20 : 0));
    put(c1506, packWave(1, 9, on1506 ? 20 : 0));
    n++;
    delay(100);
  }
  // Wellenform aus, Staerke aus, und DANN warten: ein Schreibvorgang ohne
  // Antwort, der noch in der Warteschlange steht, geht beim Trennen verloren.
  // Genau das ist in Stufe 5 passiert - dort stand beim naechsten Start noch
  // die alte Staerke 700 im Geraet.
  put(c1505, packWave(1, 9, 0));
  put(c1506, packWave(1, 9, 0));
  put(ab2, packStrength(0, 0));
  delay(400);
  Serial.printf("   (%lu Rahmen gesendet, jetzt wieder alles auf null)\n", (unsigned long) n);
  delay(1500);
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 6: welche Charakteristik ist welcher Kanal? ===");
  Serial.println("ACHTUNG: gibt WIRKLICH aus. Elektroden abziehen, oder nur an EINEN Kanal.");
  Serial.println("Zeuge ist die LEISTUNGSANZEIGE der Coyote, nicht die Haut.");
  Serial.println("Start in 5 s ...");
  delay(5000);

  NimBLEDevice::init("PunisherChan");
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
  if (target < 0) { Serial.println("Keine V2 gefunden (haengt sie am Handy?)."); return; }
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
  if (!s) { Serial.println("Dienst 955a180b fehlt."); return; }
  ab2   = s->getCharacteristic(uAB2());
  c1505 = s->getCharacteristic(uA34());
  c1506 = s->getCharacteristic(uB34());
  if (!ab2 || !c1505 || !c1506) { Serial.println("Charakteristik fehlt."); return; }
  Serial.println("verbunden.");

  // 1. So, wie die Bruecke es bisher gemacht hat. Wenn die Doku-Beschreibung
  //    stimmt, ist das genau die Kombination, die NICHTS ergibt - und das ist
  //    das, was bisher zu sehen war.
  trial("1) wie bisher: Staerke auf A, Wellenform nach 0x1505",
        STRENGTH, 0, true, false,
        "NICHTS (Hoehe auf A, Breite auf B)");

  // 2. Die Gegenprobe: Wellenform nach 0x1506. Laut Beschreibungsspalte ist
  //    0x1506 der A-Kanal - dann trifft die Breite dieselbe Seite wie die Hoehe.
  trial("2) Staerke auf A, Wellenform nach 0x1506",
        STRENGTH, 0, false, true,
        "AUSGABE auf Kanal A");

  // 3. Und die Spiegelprobe: Staerke auf B, Wellenform nach 0x1505.
  trial("3) Staerke auf B, Wellenform nach 0x1505",
        0, STRENGTH, true, false,
        "AUSGABE auf Kanal B");

  // 4. Beide Seiten voll. Wenn hier nichts kommt, liegt es an keiner
  //    Zuordnung, sondern am Geraet selbst.
  trial("4) beide Staerken, beide Wellenformen",
        STRENGTH, STRENGTH, true, true,
        "AUSGABE auf BEIDEN Kanaelen");

  Serial.println();
  Serial.println("=================================================");
  Serial.println("Fertig, alles auf null.");
  Serial.println("BITTE ZURUECKMELDEN, je Versuch 1-4:");
  Serial.println("  ging die LEISTUNGSANZEIGE an? (und wenn ja, auf welcher Seite)");
  Serial.println();
  Serial.println("Kommt bei 2 Ausgabe und bei 1 nicht, dann sind PWM_A34 und");
  Serial.println("PWM_B34 in unserem Code vertauscht - dann ist es ein Einzeiler.");
  Serial.println("Kommt bei KEINEM etwas, liegt es nicht an der Zuordnung.");
  delay(500);
  client->disconnect();
}

void loop() { delay(1000); }
