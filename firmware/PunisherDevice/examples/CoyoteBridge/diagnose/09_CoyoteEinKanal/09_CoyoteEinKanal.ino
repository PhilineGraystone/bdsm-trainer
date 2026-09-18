// =====================================================================
//  Stufe 9 — EIN KANAL, EIN STECKER, FÜNF FRAGEN
//
//  Philine, 11.09.2026: „Ich glaube nicht, dass Kanal A auch einen Wert braucht.
//  Ich glaube langsam, dass der Kanal einen eingesteckten Stecker braucht — ich
//  habe aber nur einen Stecker hier. Daher kann ich immer nur einen Kanal
//  prüfen."
//
//  Das ist die bessere Erklärung, und sie macht meine überflüssig. Ich hatte
//  aus zwei Messungen geschlossen, Kanal B brauche eine Stärke auf Kanal A —
//  dabei war der Unterschied zwischen den beiden Läufen möglicherweise nur,
//  WO DER STECKER STECKTE. Ein Gerät, das ohne Last nicht ausgibt, erklärt
//  dasselbe, ohne eine Eigenschaft zu erfinden, die in keiner Doku steht.
//
//  ALSO: diese Skizze prüft GENAU EINEN KANAL, und zwar den, in dem der
//  Stecker steckt. Fünf Versuche, die diesen einen Kanal vollständig
//  beschreiben. Danach steckt man den Stecker um, ändert EINE Zeile hier oben,
//  flasht neu — und hat dieselbe Messung für den anderen Kanal.
//
//  ZWEI DINGE STELLEN, DANN STARTEN:
//     1. den Stecker in den Kanal, der geprüft werden soll
//     2. TEST_KANAL unten auf denselben Kanal setzen
//
//  DER ZEUGE IST DIE ELEKTRODE, nicht die Anzeige. Die Anzeige der Coyote hat
//  uns schon zweimal in die Irre geführt: einmal, weil sie nichts zeigte,
//  obwohl die Daten ankamen, und einmal, weil unklar blieb, was sie eigentlich
//  anzeigt. Was an der Elektrode ankommt, ist die Frage.
//
//  ACHTUNG: GIBT WIRKLICH AUS, auf dem Kanal, in dem der Stecker steckt.
//  STAERKE anfangs klein halten (Vorgabe 280 ≈ App 40) und erst erhöhen, wenn
//  bei Versuch 3 gar nichts kommt.
// =====================================================================

// ================== HIER EINSTELLEN =================================
#define TEST_KANAL   'A'      // 'A' oder 'B' — wo steckt der Stecker?
#define STAERKE      280      // 0..2047, App-Anzeige ist etwa ein Siebtel
// ====================================================================

#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

#define HOLD_S    4
#define SCAN_S    6

static NimBLEUUID svcV2() { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uAB2()  { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
// Zuordnung aus Stufe 6 und 7, gemessen: 0x1506 gehört zu Kanal A und der
// oberen Stärkehälfte, 0x1505 zu Kanal B und der unteren.
static NimBLEUUID uWaveA() { return NimBLEUUID("955a1506-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uWaveB() { return NimBLEUUID("955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"); }

static NimBLEClient* client = nullptr;
static NimBLERemoteCharacteristic *ab2 = nullptr, *waveA = nullptr, *waveB = nullptr;

static const bool TEST_IST_A = (TEST_KANAL == 'A' || TEST_KANAL == 'a');

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

// Alles in der Sprache „geprüfter Kanal" / „anderer Kanal" — welcher davon
// A und welcher B ist, macht die eine Einstellung oben.
static void versuch(int nr, const char* frage, const char* erwartung,
                    uint16_t strTest, uint8_t zTest,
                    uint16_t strAnder, uint8_t zAnder) {
  Serial.println();
  Serial.println("-------------------------------------------------");
  Serial.printf("VERSUCH %d: %s\n", nr, frage);
  Serial.printf("   geprueft (Kanal %c, STECKER HIER): Staerke %4u, Breite %3u us\n",
                TEST_IST_A ? 'A' : 'B', strTest, (unsigned) zTest * 5);
  Serial.printf("   anderer  (Kanal %c, ohne Stecker): Staerke %4u, Breite %3u us\n",
                TEST_IST_A ? 'B' : 'A', strAnder, (unsigned) zAnder * 5);
  Serial.printf("   Erwartung: %s\n", erwartung);
  Serial.println("   >>> KOMMT AN DER ELEKTRODE ETWAS AN? <<<");

  uint16_t sA = TEST_IST_A ? strTest : strAnder;
  uint16_t sB = TEST_IST_A ? strAnder : strTest;
  put(ab2, packStrength(sA, sB));
  delay(120);
  unsigned long tEnd = millis() + (unsigned long) HOLD_S * 1000UL;
  while ((long)(millis() - tEnd) < 0) {
    put(TEST_IST_A ? waveA : waveB, packWave(1, 9, zTest));
    put(TEST_IST_A ? waveB : waveA, packWave(1, 9, zAnder));
    delay(100);
  }
  // Aus, und DANN warten. Ein Schreibvorgang ohne Antwort, der noch in der
  // Warteschlange steht, geht beim Trennen verloren (Befund aus Stufe 5).
  put(waveA, packWave(1, 9, 0));
  put(waveB, packWave(1, 9, 0));
  put(ab2, packStrength(0, 0));
  delay(400);
  Serial.println("   (aus)");
  delay(1500);
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 9: ein Kanal, ein Stecker ===");
  Serial.printf("EINGESTELLT: Stecker steckt in KANAL %c, Staerke %d\n",
                TEST_IST_A ? 'A' : 'B', (int) STAERKE);
  Serial.println("Stimmt das nicht, jetzt abbrechen und TEST_KANAL oben aendern.");
  Serial.println();
  Serial.println("ACHTUNG: gibt WIRKLICH aus, auf dem Kanal mit dem Stecker.");
  Serial.println("Zeuge ist die ELEKTRODE, nicht die Anzeige.");
  Serial.println("Start in 8 s ...");
  delay(8000);

  NimBLEDevice::init("PunisherEinKanal");
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
  ab2   = s->getCharacteristic(uAB2());
  waveA = s->getCharacteristic(uWaveA());
  waveB = s->getCharacteristic(uWaveB());
  if (!ab2 || !waveA || !waveB) { Serial.println("Charakteristik fehlt."); return; }
  Serial.println("verbunden.");

  // --- Zwei Kontrollen zuerst. Ein Test ohne Kontrolle misst irgendetwas. ---

  // 1. Breite ohne Höhe. Muss still sein — sonst wäre die Stärke gar nicht die
  //    Impulshöhe, und die ganze Doc 28 wäre wieder offen.
  versuch(1, "Breite ohne Hoehe (Staerke 0)",
             "NICHTS  - sonst ist unser Bild der Staerke falsch",
             0, 20, 0, 0);

  // 2. Höhe ohne Breite. DAS IST DIE WICHTIGSTE KONTROLLE DES PROJEKTS.
  //    Die ganze Sicherheitsrechnung der Anlage steht darauf, dass eine
  //    gesetzte Stärke ohne Impulsbreite nichts tut (Doc 28, Doc 30 §4).
  versuch(2, "Hoehe ohne Breite (Breite 0)  << WICHTIGSTE KONTROLLE >>",
             "NICHTS  - wenn hier etwas kommt, sofort melden",
             STAERKE, 0, 0, 0);

  // --- Und jetzt die eigentliche Frage, in drei Stufen. ---

  // 3. Der Kanal ganz allein. Wenn das reicht, braucht er den Nachbarn nicht,
  //    und meine Schwellentheorie aus Stufe 8 war Unsinn.
  versuch(3, "der gepruefte Kanal GANZ ALLEIN",
             "AUSGABE, wenn der Kanal den Nachbarn nicht braucht",
             STAERKE, 20, 0, 0);

  // 4. Mit Stärke auf dem Nachbarn, aber ohne Breite dort. Genau der
  //    Unterschied zwischen Stufe 6 V3 und Stufe 7 B.
  versuch(4, "derselbe Kanal, plus STAERKE auf dem Nachbarn (ohne Breite dort)",
             "wenn NUR hier Ausgabe kommt und bei 3 nicht: der Nachbar wird gebraucht",
             STAERKE, 20, STAERKE, 0);

  // 5. Beide Seiten voll. Der Bezugspunkt: kommt hier nichts, war am Aufbau
  //    etwas anders, und die Versuche 3 und 4 sagen nichts.
  versuch(5, "beide Seiten voll  (Bezugspunkt)",
             "AUSGABE - kommt hier nichts, stimmt am Aufbau etwas nicht",
             STAERKE, 20, STAERKE, 20);

  Serial.println();
  Serial.println("=================================================");
  Serial.printf("Fertig fuer Kanal %c. Alles auf null.\n", TEST_IST_A ? 'A' : 'B');
  Serial.println();
  Serial.println("BITTE je Versuch 1-5: kam an der ELEKTRODE etwas an?");
  Serial.println();
  Serial.println("  1 und 2 muessen STILL sein. Besonders 2.");
  Serial.println("  Kommt bei 3 etwas  -> der Kanal laeuft allein, meine");
  Serial.println("                        Schwellentheorie war falsch.");
  Serial.println("  Kommt erst bei 4   -> der Nachbar wird wirklich gebraucht.");
  Serial.println("  Kommt erst bei 5   -> der Nachbar braucht auch eine Breite.");
  Serial.println("  Kommt bei KEINEM   -> dieser Kanal gibt gar nicht aus.");
  Serial.println();
  Serial.println("DANN: Stecker in den anderen Kanal, TEST_KANAL oben aendern,");
  Serial.println("neu flashen, dasselbe noch einmal. Damit ist jeder Kanal einmal");
  Serial.println("mit Last gemessen worden - und die Steckerfrage ist beantwortet.");
  delay(500);
  client->disconnect();
}

void loop() { delay(1000); }
