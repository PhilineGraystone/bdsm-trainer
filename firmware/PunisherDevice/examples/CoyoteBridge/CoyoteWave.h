// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// =====================================================================
//  CoyoteWave — the computing half of the e-stim bridge (project doc 19).
//
//  Deliberately WITHOUT Arduino, BLE or MQTT: there is only arithmetic here.
//  That way exactly the part which lands on the skin can be recomputed on
//  the PC against the central unit (libs/profiles.py, libs/routines.py) and
//  against DG-LAB's example data — see test/test_coyotewave.cpp.
//
//  The three things this file has to get right:
//
//  1. THE CURVE DRIVES THE STRENGTH, the width is fixed (since 2026-09-11,
//     doc 28). The strength IS the pulse height; whoever does not write it
//     puts out nothing. Until then the opposite stood here, and both
//     channels were deaf. The ceiling of this height comes from the slave's
//     calibration and is applied above in the .ino - this file only
//     converts, it decides nothing.
//  2. MISSING IS NOT ZERO (doc 19 §5.2). err 0.0 is the perfect run and
//     earns the full share; a MISSING reading is unknown and gives nothing.
//     The difference is a refused reward.
//  3. Profile and curve are separate: the profile makes the CHARACTER
//     (rhythm, frequency), the curve only the HEIGHT. A reward thereby stays
//     distinguishable from a punishment even at the same height.
//
//  Source of the protocol: github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE,
//  coyote/v2/README.md, coyote/v3/README.md, coyote/README.md.
// =====================================================================
#pragma once

// Marker by which the sketch recognises that it REALLY got this file.
// Without it a missing or outdated CoyoteWave.h ends in ninety follow-up
// errors, none of which names the cause (finding Philine 2026-09-11:
// "'coyote' is not a namespace-name" and 89 more).
#define COYOTE_WAVE_H 2

#include <math.h>
#include <stdint.h>
#include <string.h>

namespace coyote {

// --------------------------------------------------------------------- //
//  Catalogue: roles, channels, modes. Mirror of libs/profiles.py — the names
//  arrive as text over MQTT and are translated here once.
// --------------------------------------------------------------------- //
enum Role : uint8_t { ROLE_TARGET = 0, ROLE_PUNISH, ROLE_STIM, ROLE_REWARD, ROLE_UNKNOWN = 255 };
enum Mode : uint8_t { MODE_ABSOLUTE = 0, MODE_COUPLED };
enum Couple : uint8_t { COUPLE_POSITION = 0, COUPLE_ACCURACY };
enum Channel : uint8_t { CH_NONE = 0, CH_A, CH_B, CH_VIBE };
enum Axis : uint8_t { AXIS_TIME = 0, AXIS_DEPTH };

inline Role roleFromName(const char* s) {
  if (!s) return ROLE_UNKNOWN;
  if (!strcmp(s, "zieltiefe"))   return ROLE_TARGET;
  if (!strcmp(s, "bestrafung"))  return ROLE_PUNISH;
  if (!strcmp(s, "stimulation")) return ROLE_STIM;
  if (!strcmp(s, "belohnung"))   return ROLE_REWARD;
  return ROLE_UNKNOWN;
}
inline Channel channelFromName(const char* s) {
  if (!s || !s[0]) return CH_NONE;
  if (!strcmp(s, "a"))    return CH_A;
  if (!strcmp(s, "b"))    return CH_B;
  if (!strcmp(s, "vibe")) return CH_VIBE;
  return CH_NONE;
}
inline Mode modeFromName(const char* s) {
  return (s && !strcmp(s, "gekoppelt")) ? MODE_COUPLED : MODE_ABSOLUTE;
}
inline Couple coupleFromName(const char* s) {
  return (s && !strcmp(s, "genauigkeit")) ? COUPLE_ACCURACY : COUPLE_POSITION;
}
inline Axis axisFromName(const char* s) {
  return (s && !strcmp(s, "tiefe")) ? AXIS_DEPTH : AXIS_TIME;
}

// Right of way per channel (doc 19 §6.2): the protocol yields one frame per
// 100 ms and channel, two characters at once give no third one but mush.
// Punishment > stimulation > reward. The editor warns where it bites.
inline uint8_t precedence(Role r) {
  switch (r) {
    case ROLE_PUNISH: return 3;
    case ROLE_STIM:   return 2;
    case ROLE_REWARD: return 1;
    default:          return 0;
  }
}

// --------------------------------------------------------------------- //
//  Profiles. The rhythm is compiled in (doc 01: catalogue in the code), the
//  curve only sets the height. `shape` is one entry per 100 ms frame,
//  0..100 = share of the intensity the curve demands at that moment.
//
//  Identical to libs/profiles.py — there as floating point 0.0..1.0, here as
//  percent; test_coyotewave.cpp computes both against each other.
// --------------------------------------------------------------------- //
struct Profile {
  const char*    key;
  Role           role;
  float          hzLow;
  float          hzHigh;
  uint8_t        n;
  const uint8_t* shape;
};

static const uint8_t SHAPE_STICH[]    = {100, 100};
static const uint8_t SHAPE_HAKEN[]    = {60, 80, 100, 100, 80, 60, 40, 30, 40};
static const uint8_t SHAPE_WELLE[]    = {30, 50, 70, 90, 100, 90, 70, 50, 30, 20, 20, 25};
static const uint8_t SHAPE_FLIRREN[]  = {100, 85, 100, 85};
static const uint8_t SHAPE_ZWEITAKT[] = {100, 90, 0, 100, 90, 0, 0, 0, 0, 0};
static const uint8_t SHAPE_WARM[]     = {85, 90, 95, 100, 100, 95, 90, 85, 85, 90, 95, 100, 100, 95, 90};

static const Profile PROFILES[] = {
  {"stich",    ROLE_PUNISH, 50.0f, 80.0f, 2,  SHAPE_STICH},
  {"haken",    ROLE_PUNISH, 14.0f, 20.0f, 9,  SHAPE_HAKEN},
  {"welle",    ROLE_STIM,    8.0f, 14.0f, 12, SHAPE_WELLE},
  {"flirren",  ROLE_STIM,   60.0f, 90.0f, 4,  SHAPE_FLIRREN},
  {"zweitakt", ROLE_REWARD, 18.0f, 24.0f, 10, SHAPE_ZWEITAKT},
  {"warm",     ROLE_REWARD, 10.0f, 14.0f, 15, SHAPE_WARM},
};
static const uint8_t PROFILE_COUNT = sizeof(PROFILES) / sizeof(PROFILES[0]);

inline const Profile* profileByKey(const char* key) {
  if (!key || !key[0]) return nullptr;
  for (uint8_t i = 0; i < PROFILE_COUNT; i++)
    if (!strcmp(PROFILES[i].key, key)) return &PROFILES[i];
  return nullptr;
}
// Default profile of a role — takes hold when the central unit sends a key
// this build does not know. Better the right character with the wrong name
// than silence.
inline const Profile* profileForRole(Role r) {
  for (uint8_t i = 0; i < PROFILE_COUNT; i++)
    if (PROFILES[i].role == r) return &PROFILES[i];
  return nullptr;
}

// --------------------------------------------------------------------- //
//  Frequency. Both generations compute in WAVEFORM FREQUENCY = duration of
//  one output block in milliseconds (10..1000), not in hertz:
//      1 Hz -> 1000 ms, 10 Hz -> 100 ms, 50 Hz -> 20 ms, 100 Hz -> 10 ms.
//  (coyote/README.md, "波形频率")
// --------------------------------------------------------------------- //
inline uint16_t periodMsFromHz(float hz) {
  if (hz < 1.0f) hz = 1.0f;
  if (hz > 100.0f) hz = 100.0f;
  long ms = lroundf(1000.0f / hz);
  if (ms < 10) ms = 10;
  if (ms > 1000) ms = 1000;
  return (uint16_t) ms;
}

// V3 squeezes the period into one byte. The three segments are taken
// verbatim from coyote/v3/README.md and must stay exactly like this —
// integer division, no rounding, otherwise the bridge deviates from the
// central unit's reference.
//
// Note on the source: the table in coyote/README.md gives 204 as the value
// for 650 ms; the formula yields 205, and 205 also fits the frequency of
// 1.53 Hz named there (640 ms would be 1.56 Hz). We follow the FORMULA.
inline uint8_t v3FreqValue(uint16_t periodMs) {
  if (periodMs < 10) periodMs = 10;
  if (periodMs > 1000) periodMs = 1000;
  uint16_t v;
  if (periodMs <= 100)      v = periodMs;
  else if (periodMs <= 600) v = (uint16_t)((periodMs - 100) / 5 + 100);
  else                      v = (uint16_t)((periodMs - 600) / 10 + 200);
  if (v < 10) v = 10;
  if (v > 240) v = 240;
  return (uint8_t) v;
}

// V2 splits the same period into X pulses and Y milliseconds of pause.
// Recommendation of the documentation: X = sqrt(F/1000) * 15, Y = F - X, and
// X:Y not above 1:9 - otherwise the sensation gets weaker.
//
// Rounded down, not rounded: the example series in coyote/v2/README.md
// themselves waver between the two ({1,9} for 10 ms is rounded down, {5,95}
// for 100 ms rounded). Rounding down keeps X small and thereby the ratio on
// the safe side of the 1:9 limit.
inline void v2XY(uint16_t periodMs, uint8_t& x, uint16_t& y) {
  if (periodMs < 10) periodMs = 10;
  if (periodMs > 1000) periodMs = 1000;
  long xi = (long) floorf(sqrtf((float) periodMs / 1000.0f) * 15.0f);
  // The 1:9 ratio is a limit, not a recommendation: Y must be at least 9·X.
  // The square-root formula alone violates that at periods of 18 and 19 ms
  // (it yields X=2, so 2:16) — and that is exactly where the profile "stich"
  // sits with 50..80 Hz. Additionally capping X at periodMs/10 repairs those
  // two values and leaves all the examples of the documentation unchanged.
  // (Finding of the self-test, 2026-09-11.)
  long cap = (long) periodMs / 10;
  if (xi > cap) xi = cap;
  if (xi < 1) xi = 1;
  if (xi > 31) xi = 31;
  long yi = (long) periodMs - xi;
  if (yi < 0) yi = 0;
  if (yi > 1023) yi = 1023;
  x = (uint8_t) xi;
  y = (uint16_t) yi;
}

// Pulse width. Officially (coyote/README.md): "V3 波形强度 = V2 (Z * 5)",
// so V2 Z 20 corresponds to V3 intensity 100. Above Z 20 (100 µs) the
// documentation explicitly warns of stabbing pain — which is why 20 is the
// ceiling here and not the protocol maximum value of 31.
inline uint8_t v2Z(uint8_t intensityPct) {
  if (intensityPct > 100) intensityPct = 100;
  return (uint8_t) ((intensityPct + 2) / 5);   // 0..20, rounded half up
}

// PWM_A34 / PWM_B34: 24 Bit, Bit 4-0 = X, Bit 14-5 = Y, Bit 19-15 = Z.
inline uint32_t v2Pack(uint8_t x, uint16_t y, uint8_t z) {
  return ((uint32_t)(z & 0x1F) << 15) | ((uint32_t)(y & 0x3FF) << 5) | (uint32_t)(x & 0x1F);
}
// V2 needs the conversion to little endian (v3/README.md says explicitly
// that V3, unlike V2, does NOT need it). Recomputed against the examples of
// the documentation: {1,9,0} -> 210100, {1,10,3} -> 418101, {1,9,20} -> 21010A.
inline void v2Bytes(uint32_t packed, uint8_t out[3]) {
  out[0] = (uint8_t)(packed & 0xFF);
  out[1] = (uint8_t)((packed >> 8) & 0xFF);
  out[2] = (uint8_t)((packed >> 16) & 0xFF);
}
// PWM_AB2: bit 21-11 = strength A, bit 10-0 = strength B (0..2047 each).
//
// ATTENTION, THE OPPOSITE ONCE STOOD HERE. Until 2026-09-11 this place said
// "READ ONLY, the strength belongs to the wearer (doc 19 §4.3)". That was
// wrong, and it made both channels deaf: the pulse height IS the strength,
// and whoever never writes it puts out nothing. The official table lists
// 0x1504 as "读/写/通知" — read, WRITE, notify.
//
// The ceiling now comes from the calibration per slave (decision Philine
// 2026-09-11, doc 28) and travels along with the command. Without it the
// bridge puts out nothing — not even quietly.
inline void v2ReadStrength(const uint8_t in[3], uint16_t& a, uint16_t& b) {
  uint32_t v = (uint32_t) in[0] | ((uint32_t) in[1] << 8) | ((uint32_t) in[2] << 16);
  a = (uint16_t)((v >> 11) & 0x7FF);
  b = (uint16_t)(v & 0x7FF);
}
inline uint32_t v2PackStrength(uint16_t a, uint16_t b) {
  if (a > 2047) a = 2047;
  if (b > 2047) b = 2047;
  return ((uint32_t) a << 11) | (uint32_t) b;
}

// Percent -> device unit. The two generations count differently:
// V2 knows 0..2047 (the manufacturer's app shows a seventh of that, so
// 0..292), V3 knows 0..200. The installation therefore computes in percent
// everywhere and converts only here - otherwise the database holds a number
// that means something on only one device type.
inline uint16_t v2Strength(uint8_t pct) {
  if (pct > 100) pct = 100;
  return (uint16_t)(((uint32_t) pct * 2047U + 50U) / 100U);
}
inline uint8_t v3Strength(uint8_t pct) {
  if (pct > 100) pct = 100;
  return (uint8_t)(((uint16_t) pct * 200U + 50U) / 100U);
}

// The working width. Since the switch to the strength as the lever, Z is
// fixed: the curve drives the HEIGHT, the width stays at the working value
// of the manufacturer's documentation (Z=20 = 100 µs). Zero stays zero -
// silence is still written as width 0 AND strength 0, doubly so on purpose.
static const uint8_t V2_Z_WORK = 20;

// V3 frame B0, 20 bytes, every 100 ms:
//   0xB0 | Seq(4) Interpretation(4) | A setpoint | B setpoint | A freq x4 | A int x4 | B freq x4 | B int x4
//
// Interpretation (4 bits): the upper two bits apply to A, the lower two to B.
//   0b00 unchanged · 0b01 relative up · 0b10 relative down · 0b11 ABSOLUTE
//
// We ALWAYS write 0b1111, so both channels absolute. Absolute is
// self-correcting: every frame states the full setpoint, a lost frame shifts
// nothing. Relative would have made every packet loss add up permanently -
// with a quantity that determines the pulse height, that is not an
// acceptable kind of error.
//
// Seq stays 0: then the documentation demands no acknowledgement and no
// waiting for B1 (recommended only for Seq != 0). Until 2026-09-11
// interpretation 0b0000 stood here ("do not touch the strength") - that was
// the reason the V3 was mute as well.
//
// Careful, protocol trap: if ONE value of a channel lies outside its range
// (freq 10..240, int 0..100), the device discards ALL FOUR groups of that
// channel. Silence is therefore written as a valid frequency with intensity
// 0, not as frequency 0.
inline void v3BuildFrame(uint8_t out[20],
                         uint8_t freqA, uint8_t intA,
                         uint8_t freqB, uint8_t intB,
                         uint8_t strA = 0, uint8_t strB = 0) {
  memset(out, 0, 20);
  out[0] = 0xB0;
  out[1] = 0x0F;          // Seq 0, interpretation 0b1111 -> both channels absolute
  if (strA > 200) strA = 200;
  if (strB > 200) strB = 200;
  out[2] = strA;          // A channel strength, absolute
  out[3] = strB;          // B channel strength, absolute
  if (freqA < 10) freqA = 10;
  if (freqB < 10) freqB = 10;
  if (intA > 100) intA = 100;
  if (intB > 100) intB = 100;
  for (uint8_t i = 0; i < 4; i++) {
    out[4 + i]  = freqA;
    out[8 + i]  = intA;
    out[12 + i] = freqB;
    out[16 + i] = intB;
  }
}

// --------------------------------------------------------------------- //
//  Curve. The same linear interpolation as routines.target_at() in the
//  central unit and as the preview in the editor — one formula in three
//  places, so that supervisor, installation and device mean the same thing.
// --------------------------------------------------------------------- //
struct Point {
  uint32_t x;     // time axis: ms since start. Depth axis: 0.1 % (0..1000)
  uint8_t  v;     // 0..100
  uint8_t  tol;   // 0..100, without meaning on output tracks
};

inline float valueAt(const Point* pts, uint16_t n, uint32_t x) {
  if (!pts || n == 0) return 0.0f;
  if (x <= pts[0].x) return (float) pts[0].v;
  for (uint16_t i = 0; i + 1 < n; i++) {
    if (x <= pts[i + 1].x) {
      uint32_t span = pts[i + 1].x - pts[i].x;
      if (span == 0) return (float) pts[i + 1].v;
      float f = (float)(x - pts[i].x) / (float) span;
      return (float) pts[i].v + ((float) pts[i + 1].v - (float) pts[i].v) * f;
    }
  }
  return (float) pts[n - 1].v;
}

// Reading of the slave, exactly as the central unit passes it on.
struct Live {
  float depth = 0.0f;     // 0..100 %
  float err   = 1.0f;     // 0..1, 0 = perfectly within the band
  bool  away  = true;
  bool  fresh = false;    // younger than live_stale_ms
};

// What an output track really puts out, 0..100 % of the wearer's ceiling.
//
// absolute -> the curve value.
// coupled  -> the curve value is the UPPER LIMIT, the reading decides the
//             share. Without a fresh reading: nothing. Never the maximum - a
//             measurement that has broken off must never swing upwards.
//
// The None case sits here in `fresh`: a missing reading is unknown and gives
// nothing, a reading with err 0.0 is the perfect run and gives everything.
// Whoever confuses the two refuses exactly the earned reward.
inline float outputAt(Mode mode, Couple couple, float value, const Live& live) {
  if (value < 0.0f) value = 0.0f;
  if (value > 100.0f) value = 100.0f;
  if (mode != MODE_COUPLED) return value;
  if (!live.fresh || live.away) return 0.0f;
  float share;
  if (couple == COUPLE_ACCURACY) {
    float e = live.err;
    if (e < 0.0f) e = 0.0f;
    if (e > 1.0f) e = 1.0f;
    share = 1.0f - e;
  } else {
    float d = live.depth;
    if (d < 0.0f) d = 0.0f;
    if (d > 100.0f) d = 100.0f;
    share = d / 100.0f;
  }
  float out = value * share;
  if (out < 0.0f) out = 0.0f;
  if (out > 100.0f) out = 100.0f;
  return out;
}

// --------------------------------------------------------------------- //
//  CRC32 (IEEE, like zlib.crc32) over the wire stream. The bridge REASSEMBLES
//  every track from the blocks itself and hashes it itself — it does not
//  believe the central unit, it checks it (doc 17 §7). Bitwise instead of a
//  table: 4 bytes per support point, no kilobyte of table is worth it there.
// --------------------------------------------------------------------- //
class Crc32 {
 public:
  void reset() { _c = 0xFFFFFFFFu; }
  void add(uint8_t b) {
    _c ^= b;
    for (uint8_t k = 0; k < 8; k++)
      _c = (_c >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(_c & 1)));
  }
  void add(const uint8_t* p, uint16_t n) { for (uint16_t i = 0; i < n; i++) add(p[i]); }
  uint32_t value() const { return _c ^ 0xFFFFFFFFu; }
 private:
  uint32_t _c = 0xFFFFFFFFu;
};

// One support point on the wire: dx as uint16 little endian, value, tolerance.
inline void wireBytes(uint16_t dx, uint8_t v, uint8_t tol, uint8_t out[4]) {
  out[0] = (uint8_t)(dx & 0xFF);
  out[1] = (uint8_t)((dx >> 8) & 0xFF);
  out[2] = v;
  out[3] = tol;
}

}  // namespace coyote
