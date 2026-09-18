// =====================================================================
//  Stufe 10 — WARUM GEHT DIE ROHAUSGABE, ABER DIE BESTRAFUNG NICHT?
//
//  Philine, 12.09.2026: „Wenn ich Rohdaten schicke, funktioniert der Coyote;
//  wenn ich den Test starte (egal ob Bestrafung oder Belohnung), funktioniert
//  er nicht."
//
//  ZUERST NACHGERECHNET, BEVOR GERATEN WIRD. Was die Brücke auf dem
//  Ereignisweg wirklich schreibt (mit ihrem eigenen CoyoteWave.h gerechnet,
//  Decke 60 %):
//
//     Rohausgabe, die geht:  X=1  Y=9   Z=20   Staerke 819 von 2047
//     stich    Stufe 1..3:   X=1  Y=12  Z=20   Staerke 307 / 553 / 860
//     zweitakt Stufe 1..3:   X=3  Y=39  Z=20   Staerke 307 / 553 / 860
//     welle/warm:            X=3  Y=68  Z=20   Staerke 307 / 553 / 860
//
//  Damit sind zwei bequeme Erklaerungen schon tot:
//    * "zu schwach" — Stufe 3 liegt mit 860 UEBER der Rohausgabe, die geht.
//    * "unsinnige Werte" — X, Y und Z liegen alle im erlaubten Bereich.
//
//  Es bleiben genau drei Unterschiede zwischen den beiden Wegen, und diese
//  Skizze trennt sie, indem sie IMMER DIESELBE STAERKE schreibt und nur je
//  einen Unterschied hinzunimmt:
//
//     Versuch 1   X=1 Y=9      wie die Rohausgabe            (Kontrolle)
//     Versuch 2   X=1 Y=12     Periode von 'stich'
//     Versuch 3   X=3 Y=39     Periode von 'zweitakt'
//     Versuch 4   X=3 Y=68     Periode von 'welle' / 'warm'
//     Versuch 5   beide Kanaele je Rahmen beschrieben, wie writeFrame()
//     Versuch 6   zusaetzlich die Staerke in JEDEM Rahmen, wie bei einem
//                 Profil mit wechselnder Form (haken, zweitakt, warm)
//
//  ABLESEN:
//     1 still          -> der Aufbau stimmt nicht, 2-6 sagen dann nichts
//     1 geht, 2 still  -> die PERIODE ist es. Dann liegt der Fehler in v2XY()
//                         oder das Geraet mag X/Y nur in engen Grenzen.
//     1-4 gehen, 5 still -> es liegt daran, dass je Rahmen BEIDE Kanaele
//                         geschrieben werden.
//     1-5 gehen, 6 still -> die Staerke je Rahmen ist zu viel fuer die
//                         Funkstrecke (drei Umlaeufe je 100 ms).
//     alle gehen       -> es liegt NICHT an den Werten und nicht am Funk.
//                         Dann kommt der Ereignisweg in der Bruecke gar nicht
//                         erst bis zum Schreiben, und der naechste Blick
//                         gehoert ihrem Log, nicht der Coyote.
//
//  ZWEI DINGE STELLEN, DANN STARTEN:
//     1. den Stecker in den Kanal, der geprueft werden soll
//     2. TEST_KANAL unten auf denselben Kanal setzen
//
//  DER ZEUGE IST DIE ELEKTRODE, nicht die Anzeige. Die Anzeige der Coyote hat
//  in diesem Projekt schon zweimal in die Irre gefuehrt.
//
//  ACHTUNG: GIBT WIRKLICH AUS. Staerke klein anfangen.
// =====================================================================

// ================== HIER EINSTELLEN =================================
#define TEST_KANAL   'A'      // 'A' oder 'B' — wo steckt der Stecker?
#define STAERKE      280      // 0..2047, App-Anzeige ist etwa ein Siebtel
// ====================================================================

#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

#define HOLD_S    4
#define SCAN_S    6
#define Z_WORK    20          // 100 us — derselbe Arbeitswert wie in der Bruecke

static NimBLEUUID svcV2() { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID uAB2()  { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
// Zuordnung aus Stufe 6 und 7, gemessen (Doc 30): 0x1506 gehoert zu Kanal A
// und der oberen Staerkehaelfte, 0x1505 zu Kanal B und der unteren.
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

// Ein Versuch. `beideKanaele` und `staerkeJeRahmen` sind die zwei Eigenschaften,
// die writeFrame() von der Rohausgabe unterscheiden — sie kommen erst in den
// letzten beiden Versuchen dazu, damit ein Ausfall genau EINEM Unterschied
// zuzuordnen ist.
static void versuch(int nr, const char* was, uint8_t x, uint16_t y,
                    bool beideKanaele, bool staerkeJeRahmen) {
  Serial.println();
  Serial.println("-------------------------------------------------");
  Serial.printf("VERSUCH %d: %s\n", nr, was);
  Serial.printf("   Kanal %c (STECKER HIER): X=%u Y=%u Z=%u (%u us), Staerke %u\n",
                TEST_IST_A ? 'A' : 'B', (unsigned) x, (unsigned) y,
                (unsigned) Z_WORK, (unsigned) Z_WORK * 5, (unsigned) STAERKE);
  Serial.printf("   Periode %u ms (%.1f Hz) | anderer Kanal: %s | Staerke: %s\n",
                (unsigned)(x + y), 1000.0f / (float)(x + y),
                beideKanaele ? "wird je Rahmen mit Z=0 beschrieben" : "unberuehrt",
                staerkeJeRahmen ? "je Rahmen neu" : "einmal am Anfang");
  Serial.println("   >>> KOMMT AN DER ELEKTRODE ETWAS AN? <<<");

  uint16_t sA = TEST_IST_A ? STAERKE : 0;
  uint16_t sB = TEST_IST_A ? 0 : STAERKE;
  if (!staerkeJeRahmen) {
    put(ab2, packStrength(sA, sB));
    delay(120);
  }
  unsigned long tEnd = millis() + (unsigned long) HOLD_S * 1000UL;
  while ((long)(millis() - tEnd) < 0) {
    // Genau die Reihenfolge aus writeFrame(): erst die Staerke, dann A, dann B.
    if (staerkeJeRahmen) put(ab2, packStrength(sA, sB));
    put(TEST_IST_A ? waveA : waveB, packWave(x, y, Z_WORK));
    if (beideKanaele) put(TEST_IST_A ? waveB : waveA, packWave(x, y, 0));
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
  Serial.println("=== Stufe 10: Rohausgabe gegen Ereignisweg ===");
  Serial.printf("EINGESTELLT: Stecker in KANAL %c, Staerke %d (bei allen Versuchen gleich)\n",
                TEST_IST_A ? 'A' : 'B', (int) STAERKE);
  Serial.println("Stimmt das nicht, jetzt abbrechen und TEST_KANAL oben aendern.");
  Serial.println();
  Serial.println("Die Staerke bleibt ueber alle sechs Versuche GLEICH.");
  Serial.println("Nur so sagt ein Ausfall etwas ueber den Unterschied aus.");
  Serial.println("Start in 8 s ...");
  delay(8000);

  NimBLEDevice::init("PunisherEreignis");
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

  // Kontrolle zuerst. Ein Versuch ohne Kontrolle misst irgendetwas.
  versuch(1, "wie die ROHAUSGABE (Kontrolle)                X=1 Y=9",   1,  9, false, false);

  // Nur die Periode aendert sich — sonst nichts.
  versuch(2, "Periode von 'stich'    (77 Hz)                X=1 Y=12",  1, 12, false, false);
  versuch(3, "Periode von 'zweitakt' (24 Hz)                X=3 Y=39",  3, 39, false, false);
  versuch(4, "Periode von 'welle'/'warm' (14 Hz)            X=3 Y=68",  3, 68, false, false);

  // Jetzt die beiden Eigenschaften von writeFrame(), einzeln dazu.
  versuch(5, "wie writeFrame(): BEIDE Kanaele je Rahmen     X=1 Y=12",  1, 12, true,  false);
  versuch(6, "dazu die Staerke in JEDEM Rahmen              X=1 Y=12",  1, 12, true,  true);

  Serial.println();
  Serial.println("=================================================");
  Serial.println("Fertig. Alles auf null.");
  Serial.println();
  Serial.println("BITTE je Versuch 1-6: kam an der ELEKTRODE etwas an?");
  Serial.println();
  Serial.println("  1 still            -> Aufbau pruefen, 2-6 sagen dann nichts");
  Serial.println("  1 geht, 2 still    -> die PERIODE ist es (v2XY / Grenzen des Geraets)");
  Serial.println("  2 geht, 3 oder 4 still -> nur die LANGEN Perioden sind das Problem");
  Serial.println("  1-4 gehen, 5 still -> beide Kanaele je Rahmen ist zu viel");
  Serial.println("  1-5 gehen, 6 still -> die Staerke je Rahmen ist zu viel");
  Serial.println("  alle gehen         -> es liegt NICHT an den Werten.");
  Serial.println("                        Dann schreibt die Bruecke gar nicht erst,");
  Serial.println("                        und ihr Log ist der naechste Blick.");
  delay(500);
  client->disconnect();
}

void loop() { delay(1000); }
