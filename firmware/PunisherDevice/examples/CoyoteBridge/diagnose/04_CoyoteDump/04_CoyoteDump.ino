// =====================================================================
//  Stufe 4 der Fehlersuche — WAS BIETET DIE COYOTE WIRKLICH AN?
//
//  Anlass: zwei Runden lang blieben beide Kanäle still, und zwar vollständig —
//  „der Coyote fippt nur, es gibt kein Output, auch die LED am Gerät zeigt
//  nichts" (Philine 11.09.2026). Dass die geräteeigene Anzeige dunkel bleibt, ist
//  die eigentliche Nachricht: dann ist es nicht die Elektrodenlage und nicht
//  unsere Kurvenrechnung. Dann KOMMT NICHTS AN.
//
//  Diese Skizze redet mit der Coyote OHNE Punisher, ohne WLAN, ohne MQTT, ohne
//  unsere Wellenformen. Sie tut genau vier Dinge und schreibt alles über USB:
//
//     1. BLE scannen und jedes Gerät zeigen, das sich meldet
//     2. verbinden und den GANZEN GATT-Baum ausgeben — jeden Dienst, jede
//        Charakteristik, und vor allem deren EIGENSCHAFTEN
//        (read / write / write-without-response / notify)
//     3. lesbare Charakteristiken auslesen und als Hex zeigen
//     4. die Stärke schreiben — EINMAL mit Antwort, EINMAL ohne — und
//        jedes Mal zurücklesen. Welcher der beiden Wege ankommt, steht danach
//        schwarz auf weiß da.
//
//  Punkt 4 ist der Kern. Ein „Write Command" (ohne Antwort) ist ein
//  Feuer-und-vergiss: der ESP32 meldet Erfolg, sobald das Paket draußen ist.
//  Ein Server, der diese Eigenschaft nicht anbietet, wirft es weg und sagt
//  nichts. Von außen sieht das aus wie: alles funktioniert, nichts passiert.
//
//  ACHTUNG: Punkt 4 SCHREIBT WIRKLICH EINE STÄRKE. Die Elektroden bitte
//  abziehen oder auf den Tisch legen, bevor du das laufen lässt. Der Wert ist
//  bewusst klein (TEST_PCT), aber er ist nicht null — sonst bewiese er nichts.
//
//  Board: ESP32-S3, NimBLE-Arduino (1.4.x oder 2.x).
//  Ergebnis bitte vollständig zurückschicken; die Zeilen mit "EIGENSCHAFTEN"
//  und "SCHREIBPROBE" sind die, auf die es ankommt.
// =====================================================================

// NimBLE-Arduino 2.x = 1. Auf 0 setzen, wenn 1.4.x installiert ist.
#define COYOTE_NIMBLE_V2 1

#include <NimBLEDevice.h>

// Wie stark die Schreibprobe schreibt, in Prozent. Klein, aber nicht null.
// V2 rechnet das auf 0..2047 um, V3 auf 0..200.
#define TEST_PCT   10
#define SCAN_S      6

static NimBLEUUID svcV3()  { return NimBLEUUID((uint16_t) 0x180C); }
static NimBLEUUID wrV3()   { return NimBLEUUID((uint16_t) 0x150A); }
static NimBLEUUID svcV2()  { return NimBLEUUID("955a180b-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID ab2V2()  { return NimBLEUUID("955a1504-0fe2-f5aa-a094-84b8d4f3e8ad"); }
static NimBLEUUID a34V2()  { return NimBLEUUID("955a1505-0fe2-f5aa-a094-84b8d4f3e8ad"); }

static NimBLEClient* client = nullptr;

static void line() { Serial.println("---------------------------------------------"); }

static void hex(const uint8_t* d, size_t n) {
  for (size_t i = 0; i < n; i++) Serial.printf("%02X", d[i]);
}

// ---------------------------------------------------------------------
//  Der GATT-Baum, vollständig. Das hier ist die Landkarte, die uns gefehlt hat.
// ---------------------------------------------------------------------
static void dumpTree() {
  Serial.println();
  Serial.println("=== GATT-BAUM ===");
#if COYOTE_NIMBLE_V2
  const std::vector<NimBLERemoteService*>& svcs = client->getServices(true);
#else
  std::vector<NimBLERemoteService*>* svcsp = client->getServices(true);
  const std::vector<NimBLERemoteService*>& svcs = *svcsp;
#endif
  for (auto* s : svcs) {
    Serial.printf("Dienst %s\n", s->getUUID().toString().c_str());
#if COYOTE_NIMBLE_V2
    const std::vector<NimBLERemoteCharacteristic*>& chs = s->getCharacteristics(true);
#else
    std::vector<NimBLERemoteCharacteristic*>* chsp = s->getCharacteristics(true);
    const std::vector<NimBLERemoteCharacteristic*>& chs = *chsp;
#endif
    for (auto* c : chs) {
      // DIESE ZEILE ist der Grund für die ganze Skizze.
      Serial.printf("   EIGENSCHAFTEN %s : read=%d write=%d write_nr=%d notify=%d indicate=%d\n",
                    c->getUUID().toString().c_str(),
                    (int) c->canRead(), (int) c->canWrite(), (int) c->canWriteNoResponse(),
                    (int) c->canNotify(), (int) c->canIndicate());
      if (c->canRead()) {
        std::string v = c->readValue();
        Serial.printf("      Wert (%u Byte): ", (unsigned) v.size());
        hex((const uint8_t*) v.data(), v.size());
        Serial.println();
      }
    }
  }
  line();
}

// ---------------------------------------------------------------------
//  Die Schreibprobe. Beide Wege, jeweils mit Rücklesen.
// ---------------------------------------------------------------------
static void probeWrite(NimBLERemoteCharacteristic* c, const char* what,
                       const uint8_t* payload, size_t n) {
  if (!c) { Serial.printf("SCHREIBPROBE %s: Charakteristik fehlt\n", what); return; }
  for (int withResponse = 1; withResponse >= 0; withResponse--) {
    Serial.printf("SCHREIBPROBE %s, %s Antwort: ", what, withResponse ? "MIT" : "OHNE");
    hex(payload, n);
    bool ok = c->writeValue(payload, n, withResponse != 0);
    Serial.printf("  -> writeValue meldet %s", ok ? "Erfolg" : "FEHLER");
    // Zurücklesen ist der einzige ehrliche Zeuge: ohne Antwort meldet der
    // Stack immer Erfolg, auch wenn das Gerät das Paket weggeworfen hat.
    if (c->canRead()) {
      delay(150);
      std::string v = c->readValue();
      Serial.print(",  zurückgelesen: ");
      hex((const uint8_t*) v.data(), v.size());
      bool same = (v.size() == n) && (memcmp(v.data(), payload, n) == 0);
      Serial.print(same ? "   ** ANGEKOMMEN **" : "   (nicht angekommen)");
    } else {
      Serial.print(",  nicht lesbar - bitte am GERÄT schauen, ob die Anzeige reagiert");
    }
    Serial.println();
    delay(1200);
  }
  // Wieder auf null, damit nichts stehen bleibt.
  uint8_t zero[3] = {0, 0, 0};
  c->writeValue(zero, n > 3 ? 3 : n, true);
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 4: was bietet die Coyote an? ===");
  Serial.printf("NimBLE-Modus: %s\n", COYOTE_NIMBLE_V2 ? "2.x" : "1.4.x");
  Serial.println("ACHTUNG: diese Skizze SCHREIBT eine kleine Staerke.");
  Serial.println("Elektroden bitte abziehen. Start in 5 s ...");
  delay(5000);

  NimBLEDevice::init("PunisherDump");
  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);

  Serial.printf("\nScanne %d s ...\n", SCAN_S);
#if COYOTE_NIMBLE_V2
  NimBLEScanResults res = scan->getResults(SCAN_S * 1000, false);
#else
  NimBLEScanResults res = scan->start(SCAN_S, false);
#endif
  Serial.printf("%d Geraete gefunden:\n", res.getCount());

  int target = -1;
  bool v3 = false;
  for (int i = 0; i < res.getCount(); i++) {
#if COYOTE_NIMBLE_V2
    const NimBLEAdvertisedDevice* adv = res.getDevice(i);
#else
    NimBLEAdvertisedDevice* adv = const_cast<NimBLEAdvertisedDevice*>(res.getDevice(i));
#endif
    if (!adv) continue;
    String name = String(adv->getName().c_str());
    Serial.printf("  [%d] %s  rssi %d  name \"%s\"\n", i,
                  adv->getAddress().toString().c_str(), adv->getRSSI(), name.c_str());
    // Beide Erkennungswege zeigen, nicht nur den, den wir benutzen: wenn die
    // Coyote ihren Dienst nicht mitannonciert, faellt unsere Bruecke auf den
    // Namen zurueck - und wenn BEIDE nicht passen, ist genau das die Antwort.
    bool byS3 = adv->isAdvertisingService(svcV3());
    bool byS2 = adv->isAdvertisingService(svcV2());
    if (byS3 || byS2 || name == "47L121000" || name == "D-LAB ESTIM01") {
      Serial.printf("      -> sieht nach Coyote aus (Dienst V3=%d V2=%d, Name passt=%d)\n",
                    (int) byS3, (int) byS2,
                    (int)(name == "47L121000" || name == "D-LAB ESTIM01"));
      if (target < 0) {
        target = i;
        v3 = byS3 || name == "47L121000";
      }
    }
  }
  if (target < 0) {
    Serial.println("\nKEINE COYOTE GEFUNDEN. Ist sie an, und ist sie mit KEINER App verbunden?");
    Serial.println("(Eine Coyote, die schon mit dem Handy verbunden ist, annonciert nicht mehr.)");
    return;
  }

#if COYOTE_NIMBLE_V2
  const NimBLEAdvertisedDevice* adv = res.getDevice(target);
#else
  NimBLEAdvertisedDevice* adv = const_cast<NimBLEAdvertisedDevice*>(res.getDevice(target));
#endif
  Serial.printf("\nVerbinde mit [%d], vermutete Generation: %s\n", target, v3 ? "V3" : "V2");
  client = NimBLEDevice::createClient();
  client->setConnectTimeout(5000);
  if (!client->connect(const_cast<NimBLEAdvertisedDevice*>(adv))) {
    Serial.println("VERBINDEN FEHLGESCHLAGEN. Das ist dann schon die Antwort.");
    return;
  }
  Serial.println("verbunden.");
  Serial.printf("MTU: %d\n", client->getMTU());

  dumpTree();

  Serial.println("=== SCHREIBPROBE ===");
  Serial.println("Bitte JETZT auf die Anzeige der Coyote schauen: reagiert sie?");
  line();
  if (v3) {
    NimBLERemoteService* s = client->getService(svcV3());
    NimBLERemoteCharacteristic* w = s ? s->getCharacteristic(wrV3()) : nullptr;
    // B0: Kopf, Deutung 0b1111 (beide absolut), Staerke A/B, dann 4x Frequenz
    // und 4x Intensitaet je Kanal. 100 Hz Periode = Frequenzwert 10.
    uint8_t f[20];
    memset(f, 0, sizeof(f));
    f[0] = 0xB0;
    f[1] = 0x0F;
    f[2] = (uint8_t)((TEST_PCT * 200) / 100);
    f[3] = 0;
    for (int i = 0; i < 4; i++) { f[4 + i] = 10; f[8 + i] = 100; f[12 + i] = 10; f[16 + i] = 0; }
    probeWrite(w, "V3 WRITE(0x150A)", f, sizeof(f));
  } else {
    NimBLERemoteService* s = client->getService(svcV2());
    NimBLERemoteCharacteristic* ab2 = s ? s->getCharacteristic(ab2V2()) : nullptr;
    NimBLERemoteCharacteristic* a34 = s ? s->getCharacteristic(a34V2()) : nullptr;
    // Staerke A = TEST_PCT von 2047, B = 0. Bit 21-11 = A, Bit 10-0 = B,
    // danach in Little Endian.
    uint32_t sA = ((uint32_t) TEST_PCT * 2047U) / 100U;
    uint32_t packed = (sA << 11);
    uint8_t buf[3] = { (uint8_t)(packed & 0xFF), (uint8_t)((packed >> 8) & 0xFF),
                       (uint8_t)((packed >> 16) & 0xFF) };
    probeWrite(ab2, "V2 PWM_AB2(0x1504) Staerke", buf, 3);

    // X=1, Y=9, Z=20  ->  100 Hz, 100 us. Der Arbeitswert der Hersteller-Doku.
    uint32_t wave = ((uint32_t) 20 << 15) | ((uint32_t) 9 << 5) | (uint32_t) 1;
    uint8_t wb[3] = { (uint8_t)(wave & 0xFF), (uint8_t)((wave >> 8) & 0xFF),
                      (uint8_t)((wave >> 16) & 0xFF) };
    probeWrite(a34, "V2 PWM_A34(0x1505) Wellenform", wb, 3);
  }

  line();
  Serial.println("Fertig. Bitte den GANZEN Text zurueckschicken.");
  Serial.println("Entscheidend: die Zeilen EIGENSCHAFTEN (write_nr=0 oder 1)");
  Serial.println("und SCHREIBPROBE (welcher Weg ** ANGEKOMMEN ** meldet).");
  client->disconnect();
}

void loop() {
  delay(1000);
}
