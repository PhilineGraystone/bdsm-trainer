// =====================================================================
//  Stufe 1 der Fehlersuche — beweist Board, Upload, Partition und Serial.
//
//  KEINE Bibliothek, kein WLAN, kein BLE, kein NVS. Wenn DAS nicht läuft,
//  liegt es nicht an der Brücke, sondern an Board-Einstellungen oder
//  Toolchain. Läuft es, ist die Strecke sauber und wir suchen weiter oben.
//
//  Erwartet: im Sekundentakt eine Zeile, dazu blinkt die LED (falls der Pin
//  stimmt — ohne passende LED zählt allein die Textausgabe).
// =====================================================================

// GPIO48 ist auf dem DevKitC-1 eine RGB-LED (WS2812) und leuchtet an einem
// einfachen digitalWrite NICHT. Zum Prüfen ggf. auf den Pin einer echten LED
// ändern; die Textausgabe reicht für diese Stufe.
#define LED_PIN 48

void setup() {
  Serial.begin(115200);
  // USB-CDC steht erst, wenn der PC sie geöffnet hat.
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 2000) delay(10);
  delay(300);
  Serial.println();
  Serial.println("=== Stufe 1: Board lebt ===");
  Serial.printf("Chip      : %s rev %d, %d Kerne\n",
                ESP.getChipModel(), ESP.getChipRevision(), ESP.getChipCores());
  Serial.printf("Flash     : %u MB\n", ESP.getFlashChipSize() / (1024 * 1024));
  Serial.printf("PSRAM     : %u kB (0 = aus oder nicht erkannt)\n", ESP.getPsramSize() / 1024);
  Serial.printf("Freier RAM: %u kB\n", ESP.getFreeHeap() / 1024);
  Serial.printf("Sketch    : %u kB von %u kB Partition\n",
                ESP.getSketchSize() / 1024,
                (ESP.getSketchSize() + ESP.getFreeSketchSpace()) / 1024);
  Serial.printf("Reset-Grund: %d  (1=POWERON, 3=SW, 5=DEEPSLEEP, 6=SDIO,\n"
                "              7/8=TG-WDT, 9=RTC-WDT, 12=SW-CPU, 14=BROWNOUT)\n",
                (int) esp_reset_reason());
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  static uint32_t n = 0;
  digitalWrite(LED_PIN, HIGH); delay(100);
  digitalWrite(LED_PIN, LOW);  delay(900);
  Serial.printf("läuft seit %lu s (Durchlauf %lu, freier RAM %u kB)\n",
                millis() / 1000, (unsigned long) ++n, ESP.getFreeHeap() / 1024);
}
