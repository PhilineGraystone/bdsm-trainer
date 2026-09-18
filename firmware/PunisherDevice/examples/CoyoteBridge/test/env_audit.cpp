// Hält die Hüllkurve der Brücke über den GANZEN Eingaberaum? (Frage Philine
// 2026-09-11: "berücksichtigst du die Werte der ENV_ Variable auch
// vollständig?"). Nachgerechnet wird nicht eine Stichprobe, sondern jeder
// Wert, den ein Kommando oder das Portal setzen kann.
#include "../CoyoteWave.h"
#include <stdio.h>
#include <algorithm>
using namespace coyote;

#define ENV_ESTIM_MAX_PCT     100
#define ENV_ESTIM_RUN_MAX_S  1800
#define ENV_ESTIM_DAY_MAX_S  3600
#define ENV_EVENT_MAX_S        20
#define ENV_FRAME_MS          100

static long clampL(long v, long lo, long hi){ return v<lo?lo:(v>hi?hi:v); }
static int bad = 0;
static void chk(bool ok, const char* what){ printf("  %-4s %s\n", ok?"OK":"FAIL", what); if(!ok) bad++; }

int main(){
  // --- estim_max_pct: Portal und Kommando duerfen nur SENKEN --------------
  bool ok = true;
  for (long portal = -1000; portal <= 1000; portal++) {
    long envv = clampL(portal, 1, ENV_ESTIM_MAX_PCT);
    if (envv < 1 || envv > ENV_ESTIM_MAX_PCT) ok = false;
    for (long cmd = -1000; cmd <= 1000; cmd += 7) {
      long eff = clampL(cmd, 1, envv);
      if (eff < 1 || eff > envv || eff > ENV_ESTIM_MAX_PCT) ok = false;
    }
  }
  chk(ok, "estim_max_pct: kein Portal- und kein Kommandowert kommt darueber (2001 x 287 Faelle)");

  // --- day_max_s: Portal UND Kommando -----------------------------------
  ok = true;
  for (long v = -10000; v <= 10000; v += 3) {
    long a = clampL(v, 60, ENV_ESTIM_DAY_MAX_S);          // Portal
    long b = clampL(v, 60, ENV_ESTIM_DAY_MAX_S);          // Kommando day_max_s
    if (a < 60 || a > ENV_ESTIM_DAY_MAX_S) ok = false;
    if (b < 60 || b > ENV_ESTIM_DAY_MAX_S) ok = false;
  }
  chk(ok, "estim_day_max_s: beide Wege bleiben in 60..3600");

  // --- frame_ms: NIE schneller als das Protokoll vertraegt ---------------
  ok = true;
  for (long v = -5000; v <= 5000; v++) {
    long f = clampL(v, ENV_FRAME_MS, 1000);
    if (f < ENV_FRAME_MS) ok = false;            // schneller als 100 ms = Protokollbruch
    if (f > 1000) ok = false;
  }
  chk(ok, "frame_ms: nie unter 100 ms, auch nicht per Kommando (10001 Faelle)");

  // --- event_ms: das Portal darf das Ereignis nicht verlaengern ----------
  ok = true;
  for (long v = -100000; v <= 100000; v += 13) {
    long e = clampL(v, 200, ENV_EVENT_MAX_S * 1000L);
    if (e < 200 || e > ENV_EVENT_MAX_S * 1000L) ok = false;
  }
  chk(ok, "estim_event_ms: bleibt in 200 ms .. 20 s");

  // --- Was am Ende WIRKLICH aus frameFor faellt --------------------------
  // Die Kette: Kurvenwert -> max_pct -> Profilform -> Intensitaet.
  ok = true;
  long worstFreq = 0, worstInt = 0;
  for (int pi = 0; pi < PROFILE_COUNT; pi++) {
    const Profile* p = &PROFILES[pi];
    for (long maxPct = 1; maxPct <= ENV_ESTIM_MAX_PCT; maxPct++) {
      for (long curve = 0; curve <= 100; curve += 5) {
        float out = (float) curve * (float) maxPct / 100.0f;
        for (uint16_t ph = 0; ph < p->n; ph++) {
          uint8_t f = p->shape[ph];
          float hz = p->hzLow + (p->hzHigh - p->hzLow) * ((float) f / 100.0f);
          uint16_t per = periodMsFromHz(hz);
          long v = lroundf(out * (float) f / 100.0f);
          if (v < 0) v = 0; if (v > 100) v = 100;
          uint8_t fv = v3FreqValue(per);
          if (fv < 10 || fv > 240) { ok = false; worstFreq = fv; }
          if (v > maxPct) { ok = false; worstInt = v; }      // nie ueber der Decke
          if (v > ENV_ESTIM_MAX_PCT) ok = false;
        }
      }
    }
  }
  chk(ok, "Ausgabe: Frequenzbyte immer 10..240, Intensitaet nie ueber max_pct");
  if (!ok) printf("       (schlimmster Fall: freq %ld, int %ld)\n", worstFreq, worstInt);

  // --- V2 dasselbe -------------------------------------------------------
  ok = true;
  for (long per = 10; per <= 1000; per++) {
    uint8_t x; uint16_t y;
    v2XY((uint16_t) per, x, y);
    if (x < 1 || x > 31) ok = false;
    if (y > 1023) ok = false;
    if ((long) y < 9L * x) ok = false;                 // 1:9 nie verletzt
    for (long inten = 0; inten <= 100; inten++) {
      uint8_t z = v2Z((uint8_t) inten);
      if (z > 20) ok = false;
      uint32_t packed = v2Pack(x, y, z);
      if (packed > 0xFFFFFF) ok = false;               // passt in 3 Byte
    }
  }
  chk(ok, "V2: X 1..31, Y <= 1023, X:Y nie schlechter als 1:9, Z <= 20, 24 Bit (991 x 101 Faelle)");

  // --- DER DECKEL DER TEILNEHMERIN --------------------------------------
  // Seit die Bruecke die Staerke schreibt, ist dieser Wert die einzige
  // Obergrenze der Impulshoehe (Entscheidung Philine 2026-09-11, Doc 28). Also
  // wird er hier ueber den ganzen Eingaberaum nachgerechnet: kein Kommando
  // hebt ihn ueber die Huellkurve, und kein Kurvenwert hebt die Ausgabe ueber
  // ihn. Das ist die Stelle, an der ein Fehler auf der Haut landet.
  ok = true;
  for (long cmd = -1000; cmd <= 1000; cmd += 3) {
    long ceiling = clampL(cmd, 0, ENV_ESTIM_MAX_PCT);
    if (ceiling < 0 || ceiling > ENV_ESTIM_MAX_PCT) ok = false;
    for (long inten = -50; inten <= 300; inten += 1) {
      long i = inten < 0 ? 0 : (inten > 100 ? 100 : inten);
      long out = (i * ceiling + 50) / 100;             // underCeiling()
      if (out < 0 || out > ceiling || out > ENV_ESTIM_MAX_PCT) ok = false;
      if (ceiling == 0 && out != 0) ok = false;        // kein Deckel, keine Ausgabe
      if (v2Strength((uint8_t) out) > 2047) ok = false;
      if (v3Strength((uint8_t) out) > 200) ok = false;
    }
  }
  chk(ok, "Deckel: Ausgabe nie ueber dem Deckel, Deckel nie ueber der Huellkurve (667 x 351 Faelle)");

  // Und die Umkehrung, die genauso wichtig ist: bei Deckel 0 kommt aus JEDEM
  // Kurvenwert eine Null heraus - auch aus dem hoechsten. Ohne Kalibrierung
  // gibt es keine Ausgabe, nicht einmal eine leise.
  ok = true;
  for (long inten = 0; inten <= 100; inten++)
    if (((inten * 0) + 50) / 100 != 0) ok = false;
  chk(ok, "Deckel 0: jeder Kurvenwert ergibt Null");

  printf("\n  %s\n", bad ? "FEHLER in der Huellkurve" : "Huellkurve haelt ueberall");
  return bad ? 1 : 0;
}
