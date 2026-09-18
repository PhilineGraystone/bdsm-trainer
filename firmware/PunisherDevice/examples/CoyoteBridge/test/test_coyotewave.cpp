// =====================================================================
//  Selbsttest der rechnenden Hälfte der Brücke — läuft auf dem PC.
//
//      g++ -std=c++11 -O2 -I.. -o t test_coyotewave.cpp && ./t
//      ./t dump        # CSV für check_against_central.py
//
//  Geprüft wird gegen die VERÖFFENTLICHTEN Beispieldaten von DG-LAB
//  (github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE), nicht gegen selbst
//  ausgedachte Werte — sonst prüfte der Test nur, ob der Code tut, was er tut.
//  Der zweite Teil (dump) vergleicht dieselben Funktionen mit der Zentrale.
// =====================================================================
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <vector>

#include "CoyoteWave.h"

using namespace coyote;

static int fails = 0;
static int checks = 0;

static void check(const char* name, bool ok, const std::string& info = "") {
  checks++;
  if (ok) {
    printf("  OK   %s\n", name);
  } else {
    fails++;
    printf("  FAIL %s%s%s\n", name, info.empty() ? "" : "  ", info.c_str());
  }
}

static std::string hex(const uint8_t* b, int n) {
  std::string s;
  char t[4];
  for (int i = 0; i < n; i++) { snprintf(t, sizeof(t), "%02X", b[i]); s += t; }
  return s;
}

// --------------------------------------------------------------------- //
static void testV3Freq() {
  // coyote/README.md, Tabelle "波形频率 / 输出值" und die beiden e.g.-Reihen
  // aus coyote/v3/README.md.
  struct { uint16_t ms; uint8_t want; } T[] = {
    {10, 10}, {20, 20}, {50, 50}, {100, 100}, {110, 102}, {150, 110},
    {680, 208}, {750, 215},
    // e.g. 1: Perioden zu 1..10 Hz
    {1000, 240}, {500, 180}, {333, 146}, {250, 130}, {200, 120},
    {166, 113}, {142, 108}, {125, 105}, {111, 102},
    // e.g. 2: 100..1000 ms in Hundertern
    {300, 140}, {400, 160}, {600, 200}, {700, 210}, {800, 220}, {900, 230},
  };
  bool ok = true;
  std::string bad;
  for (size_t i = 0; i < sizeof(T) / sizeof(T[0]); i++) {
    uint8_t got = v3FreqValue(T[i].ms);
    if (got != T[i].want) {
      ok = false;
      char b[64]; snprintf(b, sizeof(b), "%u ms -> %u statt %u; ", T[i].ms, got, T[i].want);
      bad += b;
    }
  }
  check("V3-Frequenzwerte wie in der DG-LAB-Tabelle", ok, bad);

  // Die Tabelle nennt für 650 ms den Wert 204, die Formel ergibt 205. 205 passt
  // zu der dort ebenfalls genannten Frequenz 1,53 Hz (204 wären 640 ms =
  // 1,5625 Hz). Wir folgen der Formel und halten die Abweichung fest.
  check("650 ms folgt der Formel (205), nicht dem Tabellentippfehler (204)",
        v3FreqValue(650) == 205);
  check("Frequenzwert bleibt im erlaubten Bereich",
        v3FreqValue(1) >= 10 && v3FreqValue(5000) <= 240);
}

static void testV2Pack() {
  // coyote/v2/example.md, eingebaute Wellenformen "呼吸" und "潮汐".
  struct { uint8_t x; uint16_t y; uint8_t z; const char* want; } T[] = {
    {1,  9, 0,  "210100"}, {1,  9, 4,  "210102"}, {1,  9, 8,  "210104"},
    {1,  9, 12, "210106"}, {1,  9, 16, "210108"}, {1,  9, 20, "21010A"},
    {1, 10, 3,  "418101"}, {1, 12, 6,  "810103"}, {1, 13, 10, "A10105"},
    {1, 15, 13, "E18106"}, {1, 17, 16, "210208"}, {1, 18, 20, "41020A"},
    {1, 20, 18, "810209"}, {1, 21, 16, "A10208"}, {1, 23, 15, "E18207"},
    {1, 25, 13, "218306"}, {1, 25, 0,  "210300"}, {1, 41, 13, "218506"},
  };
  bool ok = true;
  std::string bad;
  for (size_t i = 0; i < sizeof(T) / sizeof(T[0]); i++) {
    uint8_t out[3];
    v2Bytes(v2Pack(T[i].x, T[i].y, T[i].z), out);
    std::string got = hex(out, 3);
    if (got != T[i].want) {
      ok = false;
      char b[96];
      snprintf(b, sizeof(b), "{%u,%u,%u} -> %s statt %s; ",
               T[i].x, T[i].y, T[i].z, got.c_str(), T[i].want);
      bad += b;
    }
  }
  check("V2-Bytes (Little Endian) wie in den DG-LAB-Beispielen", ok, bad);

  // Gegenprobe: dieselben Bytes wieder auseinandernehmen.
  uint16_t a, b;
  uint8_t raw[3];
  v2Bytes(((uint32_t) 1234 << 11) | 567, raw);
  v2ReadStrength(raw, a, b);
  check("V2-Stärke liest sich zurück, wie sie gepackt war", a == 1234 && b == 567);
}

static void testV2XY() {
  // coyote/v2/README.md, "更多例子": die Reihe mit steigender Frequenz.
  struct { uint16_t f; uint8_t x; uint16_t y; } T[] = {
    {10, 1, 9}, {15, 1, 14}, {30, 2, 28}, {60, 3, 57}, {90, 4, 86}, {140, 5, 135},
  };
  bool ok = true;
  std::string bad;
  for (size_t i = 0; i < sizeof(T) / sizeof(T[0]); i++) {
    uint8_t x; uint16_t y;
    v2XY(T[i].f, x, y);
    if (x != T[i].x || y != T[i].y) {
      ok = false;
      char b[80];
      snprintf(b, sizeof(b), "%u -> {%u,%u} statt {%u,%u}; ", T[i].f, x, y, T[i].x, T[i].y);
      bad += b;
    }
  }
  check("V2 X/Y wie in den DG-LAB-Beispielen", ok, bad);

  // X + Y muss immer die Periode ergeben, sonst stimmt die Frequenz nicht.
  bool sum = true, ratio = true;
  for (uint16_t f = 10; f <= 1000; f++) {
    uint8_t x; uint16_t y;
    v2XY(f, x, y);
    if ((uint32_t) x + y != f) sum = false;
    if (x > 31 || y > 1023) ratio = false;
    // X:Y nie über 1:9 — darüber wird das Gefühl laut Doku schwächer
    if (y < (uint16_t) x * 9 && f > 10) ratio = false;
  }
  check("X + Y ergibt über den ganzen Bereich die Periode", sum);
  check("X und Y bleiben im Protokollbereich und unter dem 1:9-Verhältnis", ratio);
}

static void testV2Z() {
  check("V2 Z: 100 % Intensität sind 20 (offizielle Zuordnung V3 = V2 Z × 5)", v2Z(100) == 20);
  check("V2 Z: 0 bleibt 0", v2Z(0) == 0);
  check("V2 Z: 50 % sind 10", v2Z(50) == 10);
  bool cap = true;
  for (int i = 0; i <= 255; i++) if (v2Z((uint8_t) i) > 20) cap = false;
  // Die Doku warnt ab Z 20 (100 µs) vor stechendem Schmerz — 20 ist die Decke,
  // nicht der Protokollmaximalwert 31.
  check("V2 Z überschreitet nie 20, auch bei Unsinn als Eingabe", cap);
}

static void testV3Frame() {
  uint8_t f[20];
  v3BuildFrame(f, 10, 0, 10, 0);
  // Deutung 0b1111 (Byte 1 = 0x0F): beide Kanäle ABSOLUT. Stärke 0 heißt hier
  // wirklich "auf null setzen", nicht "nicht anfassen" — der Unterschied ist
  // genau der Fehler, der beide Kanäle taub gemacht hat (Doc 28 §2).
  check("V3-Rahmen: Kopf, Deutung absolut, Stärke 0, vier Gruppen je Kanal",
        hex(f, 20) == "B00F00000A0A0A0A000000000A0A0A0A00000000", hex(f, 20));

  v3BuildFrame(f, v3FreqValue(100), 30, v3FreqValue(20), 75);
  bool layout = (f[0] == 0xB0) &&
                (f[4] == 100 && f[5] == 100 && f[6] == 100 && f[7] == 100) &&
                (f[8] == 30 && f[11] == 30) &&
                (f[12] == 20 && f[15] == 20) &&
                (f[16] == 75 && f[19] == 75);
  check("V3-Rahmen: Frequenz und Intensität liegen an den richtigen Stellen", layout);

  // Die Stärke wird jetzt geschrieben — aber IMMER absolut und IMMER im
  // Bereich des Protokolls (0..200). Absolut ist die Zusage, die den Fehler
  // ausschließt, den relative Änderungen hätten: ein verlorener Rahmen
  // verschiebt bei absoluter Deutung nichts, bei relativer für immer.
  bool always = true;
  for (int a = 0; a <= 255; a += 7) {
    for (int b = 0; b <= 255; b += 11) {
      v3BuildFrame(f, (uint8_t) a, (uint8_t) b, (uint8_t) b, (uint8_t) a,
                   (uint8_t) a, (uint8_t) b);
      if (f[1] != 0x0F || f[2] > 200 || f[3] > 200) { always = false; break; }
    }
  }
  check("V3-Rahmen setzt die Stärke immer absolut und nie über 200", always);

  // Prozent -> Geräteeinheit, beide Generationen. Die Anlage rechnet überall
  // in Prozent; hier ist die einzige Stelle, an der daraus Gerätewerte werden.
  check("V2: 0 % -> 0, 100 % -> 2047, 50 % -> 1024",
        v2Strength(0) == 0 && v2Strength(100) == 2047 && v2Strength(50) == 1024);
  check("V3: 0 % -> 0, 100 % -> 200, 50 % -> 100",
        v3Strength(0) == 0 && v3Strength(100) == 200 && v3Strength(50) == 100);
  check("Prozent über 100 wird geklemmt, nicht überlaufen",
        v2Strength(255) == 2047 && v3Strength(255) == 200);
  uint16_t sa = 0, sb = 0;
  uint8_t sbuf[3];
  v2Bytes(v2PackStrength(v2Strength(70), v2Strength(30)), sbuf);
  v2ReadStrength(sbuf, sa, sb);
  check("V2-Stärke: geschrieben und zurückgelesen ergibt dasselbe",
        sa == v2Strength(70) && sb == v2Strength(30));

  // Ungültige Werte würden das Gerät ALLE VIER Gruppen des Kanals verwerfen
  // lassen — deshalb klemmt der Bauer sie in den gültigen Bereich.
  v3BuildFrame(f, 0, 200, 5, 255);
  bool clamp = true;
  for (int i = 4; i < 8; i++)  if (f[i] < 10 || f[i] > 240) clamp = false;
  for (int i = 8; i < 12; i++) if (f[i] > 100) clamp = false;
  for (int i = 12; i < 16; i++) if (f[i] < 10 || f[i] > 240) clamp = false;
  for (int i = 16; i < 20; i++) if (f[i] > 100) clamp = false;
  check("V3-Rahmen klemmt Frequenz und Intensität in den gültigen Bereich", clamp);
}

static void testProfiles() {
  bool roles = true;
  for (uint8_t i = 0; i < PROFILE_COUNT; i++) {
    const Profile& p = PROFILES[i];
    if (p.n == 0 || !p.shape) roles = false;
    if (p.hzLow <= 0.0f || p.hzHigh < p.hzLow) roles = false;
    for (uint8_t k = 0; k < p.n; k++) if (p.shape[k] > 100) roles = false;
  }
  check("Alle Profile haben eine Schleife und ein sinnvolles Frequenzband", roles);

  // Belohnung und Bestrafung dürfen sich kein Profil teilen — das ist der
  // Kern von Doc 19 §3: der Unterschied muss im Charakter liegen.
  bool split = true;
  for (uint8_t i = 0; i < PROFILE_COUNT; i++)
    for (uint8_t k = i + 1; k < PROFILE_COUNT; k++)
      if (!strcmp(PROFILES[i].key, PROFILES[k].key)) split = false;
  check("Kein Profil kommt doppelt vor", split);

  check("Jede Rolle hat ein Vorgabeprofil",
        profileForRole(ROLE_PUNISH) && profileForRole(ROLE_STIM) && profileForRole(ROLE_REWARD));
  check("Ein unbekannter Profilname liefert nichts (und die Rolle greift ein)",
        profileByKey("gibtsnicht") == nullptr);

  // Seit Doc 32 waehlt die Zentrale das Profil; die Vorgabe der Rolle ist nur
  // noch der Rueckfall. Sie muss GENAU das sein, was bis dahin fest im Code
  // stand - sonst aendert sich fuer einen Bestand ohne Eintrag klammheimlich
  // die Wellenform, und niemand hat etwas entschieden.
  check("Der Rueckfall der Bestrafung ist weiterhin 'stich'",
        profileForRole(ROLE_PUNISH) && !strcmp(profileForRole(ROLE_PUNISH)->key, "stich"));
  check("Der Rueckfall der Belohnung ist weiterhin 'zweitakt'",
        profileForRole(ROLE_REWARD) && !strcmp(profileForRole(ROLE_REWARD)->key, "zweitakt"));

  // Jeder Schluessel, den die Zentrale anbieten kann, muss hier ankommen. Steht
  // in libs/profiles.py einer, den die Firmware nicht kennt, waehlt die Aufsicht
  // ihn aus, speichert ihn - und das Geraet spielt still etwas anderes.
  const char* fromCentral[] = {"stich", "haken", "welle", "flirren", "zweitakt", "warm"};
  bool known = true;
  for (uint8_t i = 0; i < sizeof(fromCentral) / sizeof(fromCentral[0]); i++)
    if (!profileByKey(fromCentral[i])) known = false;
  check("Jeder Profilschluessel der Zentrale ist der Firmware bekannt", known);

  // Jedes Profil muss über seine ganze Schleife im Protokollbereich bleiben.
  bool band = true;
  for (uint8_t i = 0; i < PROFILE_COUNT; i++) {
    const Profile& p = PROFILES[i];
    for (uint8_t k = 0; k < p.n; k++) {
      float hz = p.hzLow + (p.hzHigh - p.hzLow) * ((float) p.shape[k] / 100.0f);
      uint8_t v = v3FreqValue(periodMsFromHz(hz));
      if (v < 10 || v > 240) band = false;
    }
  }
  check("Jedes Profil bleibt über seine ganze Schleife im Frequenzbereich 10..240", band);
}

static void testCurve() {
  Point pts[] = {{0, 0, 15}, {3000, 35, 12}, {8000, 35, 12}, {11000, 15, 15}};
  check("Kurve: vor dem ersten Punkt gilt der erste Wert", valueAt(pts, 4, 0) == 0.0f);
  check("Kurve: hinter dem letzten Punkt gilt der letzte Wert", valueAt(pts, 4, 99999) == 15.0f);
  check("Kurve: Stützpunkt trifft genau", valueAt(pts, 4, 3000) == 35.0f);
  check("Kurve: Mitte einer Rampe wird interpoliert",
        valueAt(pts, 4, 1500) > 17.4f && valueAt(pts, 4, 1500) < 17.6f);
  check("Kurve: waagerechtes Stück bleibt waagerecht", valueAt(pts, 4, 5000) == 35.0f);
  check("Leere Kurve gibt nichts", valueAt(nullptr, 0, 100) == 0.0f);
}

static void testCoupling() {
  Live l;
  l.fresh = true; l.away = false; l.depth = 100.0f; l.err = 0.0f;

  check("Absolut: der Kurvenwert kommt heraus",
        outputAt(MODE_ABSOLUTE, COUPLE_POSITION, 80.0f, l) == 80.0f);

  // DER Fall, der schon zweimal falsch war: err 0.0 ist der PERFEKTE Lauf.
  // Ein `err || 1.0` läse die 0.0 als fehlend und verweigerte genau die
  // verdiente Belohnung.
  check("Genauigkeit perfekt (err 0.0) gibt den vollen Wert",
        outputAt(MODE_COUPLED, COUPLE_ACCURACY, 80.0f, l) == 80.0f);
  l.err = 1.0f;
  check("Genauigkeit daneben (err 1.0) gibt nichts",
        outputAt(MODE_COUPLED, COUPLE_ACCURACY, 80.0f, l) == 0.0f);
  l.err = 0.5f;
  check("Genauigkeit halb gibt die Hälfte",
        outputAt(MODE_COUPLED, COUPLE_ACCURACY, 80.0f, l) == 40.0f);

  l.err = 0.0f; l.depth = 50.0f;
  check("Position: halbe Tiefe gibt den halben Wert",
        outputAt(MODE_COUPLED, COUPLE_POSITION, 80.0f, l) == 40.0f);
  l.depth = 0.0f;
  check("Position: ganz flach gibt nichts",
        outputAt(MODE_COUPLED, COUPLE_POSITION, 80.0f, l) == 0.0f);

  // Ohne frischen Messwert: nichts. Nie das Maximum — eine abgerissene
  // Messung darf niemals nach oben ausschlagen.
  l.fresh = false; l.depth = 100.0f; l.err = 0.0f;
  check("Ohne frischen Messwert gibt eine gekoppelte Spur nichts",
        outputAt(MODE_COUPLED, COUPLE_POSITION, 100.0f, l) == 0.0f &&
        outputAt(MODE_COUPLED, COUPLE_ACCURACY, 100.0f, l) == 0.0f);
  check("Ohne frischen Messwert bleibt eine ABSOLUTE Spur unberührt",
        outputAt(MODE_ABSOLUTE, COUPLE_POSITION, 100.0f, l) == 100.0f);

  l.fresh = true; l.away = true;
  check("Weg: gekoppelte Spuren geben nichts",
        outputAt(MODE_COUPLED, COUPLE_POSITION, 100.0f, l) == 0.0f);
}

static void testPrecedence() {
  check("Vorfahrt: Bestrafung vor Stimulation vor Belohnung",
        precedence(ROLE_PUNISH) > precedence(ROLE_STIM) &&
        precedence(ROLE_STIM) > precedence(ROLE_REWARD) &&
        precedence(ROLE_REWARD) > precedence(ROLE_TARGET));
}

static void testNames() {
  check("Rollennamen der Zentrale werden erkannt",
        roleFromName("zieltiefe") == ROLE_TARGET && roleFromName("bestrafung") == ROLE_PUNISH &&
        roleFromName("stimulation") == ROLE_STIM && roleFromName("belohnung") == ROLE_REWARD);
  check("Unbekannte Rolle bleibt unbekannt", roleFromName("quatsch") == ROLE_UNKNOWN);
  check("Kanäle, Modi, Kopplung und Achse werden erkannt",
        channelFromName("a") == CH_A && channelFromName("b") == CH_B &&
        channelFromName("") == CH_NONE && modeFromName("gekoppelt") == MODE_COUPLED &&
        modeFromName(nullptr) == MODE_ABSOLUTE &&
        coupleFromName("genauigkeit") == COUPLE_ACCURACY &&
        axisFromName("tiefe") == AXIS_DEPTH && axisFromName("zeit") == AXIS_TIME);
}

static void testCrc() {
  // Bekannte Werte des CRC32 aus zlib; der dritte ist ein echter Drahtstrom
  // (zwei Stützpunkte) und wird in check_against_central.py gegengerechnet.
  Crc32 c;
  c.reset();
  const char* s = "123456789";
  c.add((const uint8_t*) s, 9);
  check("CRC32 von \"123456789\" ist CBF43926", c.value() == 0xCBF43926u,
        std::string("got ") + std::to_string(c.value()));
  c.reset();
  check("CRC32 von nichts ist 0", c.value() == 0u);
}

// --------------------------------------------------------------------- //
//  CSV für den Vergleich mit der Zentrale.
static void dump() {
  printf("# profile,step,intensity_in,hz,period_ms,v3value,intensity_out\n");
  const int INTS[] = {100, 70, 45, 25};
  for (uint8_t i = 0; i < PROFILE_COUNT; i++) {
    const Profile& p = PROFILES[i];
    for (size_t k = 0; k < sizeof(INTS) / sizeof(INTS[0]); k++) {
      for (uint8_t s = 0; s < p.n; s++) {
        uint8_t f = p.shape[s % p.n];
        float hz = p.hzLow + (p.hzHigh - p.hzLow) * ((float) f / 100.0f);
        uint16_t per = periodMsFromHz(hz);
        long v = lroundf((float) INTS[k] * (float) f / 100.0f);
        printf("P,%s,%u,%d,%.4f,%u,%u,%ld\n", p.key, s, INTS[k], hz, per, v3FreqValue(per), v);
      }
    }
  }
  printf("# curve,x,value\n");
  Point pts[] = {{0, 0, 15}, {3000, 35, 12}, {8000, 35, 12}, {11000, 15, 15},
                 {14000, 60, 10}, {20000, 60, 10}};
  for (uint32_t x = 0; x <= 21000; x += 250)
    printf("C,%u,%.6f\n", x, valueAt(pts, 6, x));

  printf("# wire crc: dx,value,tol per point\n");
  const uint16_t DX[]  = {0, 300, 500, 300};
  const uint8_t  VAL[] = {0, 35, 35, 15};
  const uint8_t  TOL[] = {15, 12, 12, 15};
  Crc32 c; c.reset();
  for (int i = 0; i < 4; i++) {
    uint8_t b[4];
    wireBytes(DX[i], VAL[i], TOL[i], b);
    c.add(b, 4);
    printf("W,%u,%u,%u\n", DX[i], VAL[i], TOL[i]);
  }
  printf("CRC,%u\n", c.value());

  printf("# coupling: mode,couple,value,depth,err,fresh,away,out\n");
  const float VS[] = {100.0f, 80.0f, 45.0f};
  const float DS[] = {0.0f, 25.0f, 50.0f, 100.0f};
  const float ES[] = {0.0f, 0.25f, 0.5f, 1.0f};
  for (size_t a = 0; a < 3; a++)
    for (size_t b = 0; b < 4; b++)
      for (size_t e = 0; e < 4; e++) {
        Live l; l.fresh = true; l.away = false; l.depth = DS[b]; l.err = ES[e];
        printf("K,gekoppelt,position,%.1f,%.1f,%.2f,1,0,%.6f\n",
               VS[a], DS[b], ES[e], outputAt(MODE_COUPLED, COUPLE_POSITION, VS[a], l));
        printf("K,gekoppelt,genauigkeit,%.1f,%.1f,%.2f,1,0,%.6f\n",
               VS[a], DS[b], ES[e], outputAt(MODE_COUPLED, COUPLE_ACCURACY, VS[a], l));
      }
}

int main(int argc, char** argv) {
  if (argc > 1 && !strcmp(argv[1], "dump")) { dump(); return 0; }
  printf("CoyoteWave — Selbsttest gegen die DG-LAB-Beispieldaten\n\n");
  testV3Freq();
  testV2Pack();
  testV2XY();
  testV2Z();
  testV3Frame();
  testProfiles();
  testCurve();
  testCoupling();
  testPrecedence();
  testNames();
  testCrc();
  printf("\n%d Prüfungen, %d Fehler\n", checks, fails);
  return fails ? 1 : 0;
}
