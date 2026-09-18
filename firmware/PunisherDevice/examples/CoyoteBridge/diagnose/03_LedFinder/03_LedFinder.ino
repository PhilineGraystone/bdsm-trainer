// =====================================================================
//  Stufe 3 der Fehlersuche — WELCHE LED hat dieses Board, und an welchem Pin?
//
//  Anlass: die Brücke blinkte nicht (Philine 2026-09-11, GPIO48). Eine WS2812
//  leuchtet an einem digitalWrite nicht — sie will ein Datentelegramm, keinen
//  Pegel. Und je nach Board-Fassung sitzt sie an 48, 47 oder 38.
//
//  Diese Skizze probiert beides an mehreren Pins durch und SAGT DAZU, was sie
//  gerade tut. Man schaut auf die Platine und liest mit: was leuchtet, wenn
//  welche Zeile kommt, ist die Antwort.
//
//  Ablauf je Kandidat, jeweils mit Ansage:
//     1. WS2812: rot, grün, blau, aus   (neopixelWrite)
//     2. einfacher Pegel: 3x an/aus     (digitalWrite)
//  Danach von vorn. Abbruch mit Reset.
//
//  Ergebnis bitte notieren als: Pin + welche der beiden Fassungen.
// =====================================================================

// Kandidaten, in dieser Reihenfolge. 48 = DevKitC-1 v1.0, 47/38 = spätere
// Fassungen und einige Nachbauten, 2 = klassisches ESP32-DevKit, 21/undefiniert
// = eigene LED mit Vorwiderstand.
const int PINS[] = { 48, 47, 38, 2, 21 };
const int N_PINS = sizeof(PINS) / sizeof(PINS[0]);

#define STEP_MS 700

void say(const char* what, int pin) {
  Serial.printf("[%6lu] GPIO %-2d : %s\n", millis() / 100, pin, what);
  Serial.flush();
}

void setup() {
  Serial.begin(115200);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 3: LED suchen ===");
  Serial.printf("Chip: %s rev %d\n", ESP.getChipModel(), ESP.getChipRevision());
#ifdef RGB_BUILTIN
  Serial.printf("Der Arduino-Core meldet eine eingebaute RGB-LED an GPIO %d.\n", (int) RGB_BUILTIN);
#else
  Serial.println("Der Arduino-Core meldet KEINE eingebaute RGB-LED (RGB_BUILTIN nicht gesetzt).");
#endif
  Serial.println("Auf die Platine schauen und mitlesen: was leuchtet, wenn welche Zeile kommt.");
  Serial.println("Notieren: Pin + ob es die WS2812- oder die Pegel-Fassung war.");
  Serial.println();
}

void loop() {
  for (int i = 0; i < N_PINS; i++) {
    const int pin = PINS[i];

    // --- Fassung A: WS2812 (Datentelegramm) --------------------------
    // Drei satte Farben nacheinander. Leuchtet hier etwas, ist es eine
    // adressierbare LED und die Brücke muss neopixelWrite() benutzen.
    say("WS2812 rot", pin);        neopixelWrite(pin, 60,  0,  0); delay(STEP_MS);
    say("WS2812 gruen", pin);      neopixelWrite(pin,  0, 60,  0); delay(STEP_MS);
    say("WS2812 blau", pin);       neopixelWrite(pin,  0,  0, 60); delay(STEP_MS);
    say("WS2812 aus", pin);        neopixelWrite(pin,  0,  0,  0); delay(300);

    // --- Fassung B: einfacher Pegel ----------------------------------
    // Blinkt es HIER, ist es eine gewöhnliche LED und digitalWrite genügt.
    say("Pegel 3x blinken", pin);
    pinMode(pin, OUTPUT);
    for (int k = 0; k < 3; k++) {
      digitalWrite(pin, HIGH); delay(200);
      digitalWrite(pin, LOW);  delay(200);
    }
    delay(400);
  }
  Serial.println("--- Durchlauf zu Ende, faengt von vorn an ---");
  Serial.println();
}
