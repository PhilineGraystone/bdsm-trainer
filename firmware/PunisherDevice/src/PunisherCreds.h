// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#pragma once
// A build with placeholder credentials must not happen. (2.1.0)
//
// WHY THIS EXISTS
//
// Every `creds.h` ships with `CHANGEME-…` in it, and that is right: the
// repository must not carry the credentials of this installation. But nothing
// stopped a sketch from being built and flashed exactly like that, and the
// result is a device that behaves almost normally — it comes up, it opens its
// setup portal, it may even reach a broker. What it does NOT do is get into
// this installation, because its signature is computed with the wrong key.
//
// That failure looks like a hardware fault from the outside: a device that is
// there and is refused. The question "did you fill in creds.h" is asked on the
// third evening, not the first (request Philine 2026-09-15).
//
// So the build stops instead. A compiler error at the right moment is worth
// more than any amount of documentation at the wrong one.
//
// HOW IT WORKS
//
// The values in `creds.h` are `constexpr char X[]`, not `const char*`. That
// one change is what makes them readable at compile time — the contents of a
// pointer are not a constant expression, the contents of a constexpr array
// are. They still decay to `const char*` everywhere they are used, so nothing
// else about the sketches changes.
//
// Checked are the prefix `CHANGEME` and, where a value has to say something,
// its length. Not whether a value is CORRECT — that cannot be decided here,
// and a check that pretends to know more than it does is worse than a narrow
// one that is right.
//
// WHY LENGTH AS WELL (2.1.1)
//
// Philine built the guard under C++11 and found the way past it: `constexpr char
// PROJECT_KEY[] = "";` went through. The prefix check asks whether a value
// still carries the placeholder — an empty value carries none. It is not the
// repository's text, so the guard waved it through, and the device came up
// with no signature at all: exactly the state the guard exists to prevent.
//
// So the question is asked differently for each value, because the values are
// not alike:
//
//   PROJECT_KEY   must be there and must be long. It is the one secret of the
//                 installation. Empty means "this device signs nothing".
//   OTA_PASSWORD  empty means OTA IS SWITCHED OFF — a legitimate choice, and
//                 the only one a `constexpr char[]` can express (an array is
//                 never a null pointer). Anything non-empty must be long
//                 enough to be a password; "a" is worse than none, because it
//                 looks like protection.
//   the rest      empty is legitimate and documented: whoever leaves SSID and
//                 broker empty enters them in the setup portal. Only the
//                 placeholder is refused there.
//
// WHERE IT IS INVOKED
//
// In the SKETCH, after `creds.h` and after the sketch's own switches — not in
// `creds.h` itself. SelfTest decides with `WITH_NETWORK` whether it goes on
// the air at all, and that switch is set after the include. A guard in
// `creds.h` would have to guess.

// The two switches for TLS (2.3, project document 53). They are MACROS and not
// `constexpr`, for one reason: a creds.h written before 2.3 does not have them,
// and it must still compile and mean what it always meant — clear text on 1883.
// Only a macro can be defaulted like that; a missing constexpr is a
// compiler error, and locking out every older creds.h would be a poor way to
// introduce an option that is switched off by default anyway.
#ifndef MQTT_TLS
#define MQTT_TLS 0
#endif
#ifndef MQTT_PORT
#define MQTT_PORT (MQTT_TLS ? 8883 : 1883)
#endif
// Wipe the device's stored configuration (NVS) at the next start. Off by
// default; a creds.h from before 2.3.2 does not know the switch and keeps
// behaving as before. See PunisherDevice::begin() for what it does and why.
#ifndef PUNISHER_NVS_CLEAR
#define PUNISHER_NVS_CLEAR 0
#endif

namespace pun {

// The minimum length of a secret. Not a security claim — a bar below which a
// value is demonstrably not a secret but a typing accident.
constexpr int MIN_KEY_LEN = 16;      // PROJECT_KEY
constexpr int MIN_OTA_LEN = 8;       // OTA_PASSWORD, when OTA is on at all

// Does this value still carry the placeholder from the repository?
//
// Everything here is written as a single return, or as one recursive step, so
// that it is a constant expression under C++11 as well — the ESP32 core 2.x
// compiles with gnu++11, 3.x with gnu++17, and this has to hold on both. That
// rules out loops and local variables: C++11 allows a constexpr function one
// return statement and nothing else.
constexpr bool isPlaceholder(const char* s) {
  return s != nullptr &&
         s[0] == 'C' && s[1] == 'H' && s[2] == 'A' && s[3] == 'N' &&
         s[4] == 'G' && s[5] == 'E' && s[6] == 'M' && s[7] == 'E';
}

// Is the value empty — or absent altogether?
constexpr bool isEmpty(const char* s) {
  return s == nullptr || s[0] == '\0';
}

// At least n characters? Counts no further than it has to; that keeps the
// recursion depth at n and not at the length of the text.
constexpr bool atLeast(const char* s, int n) {
  return n <= 0 ? true
                : (s == nullptr || s[0] == '\0') ? false
                                                 : atLeast(s + 1, n - 1);
}

// The three questions, each by the name of what it is for. A static_assert
// whose condition reads `!isPlaceholder(X) && !isEmpty(X) && atLeast(X, 16)`
// says WHAT is being checked; one that reads `isRealKey(X)` says WHY.
constexpr bool isRealKey(const char* s) {
  return !isPlaceholder(s) && atLeast(s, MIN_KEY_LEN);
}

// Empty is allowed here and means: this value comes from the setup portal.
constexpr bool isRealOrPortal(const char* s) {
  return !isPlaceholder(s);
}

// Empty is allowed here too, and means: OTA is switched off.
constexpr bool isRealOtaOrOff(const char* s) {
  return !isPlaceholder(s) && (isEmpty(s) || atLeast(s, MIN_OTA_LEN));
}

}  // namespace pun

// The credentials a device needs to take part in the installation.
//
// PROJECT_KEY is the one that decides membership; the rest is how it reaches
// the broker at all. They are checked together because a build is either meant
// for this installation or it is not.
#define PUN_REQUIRE_REAL_CREDS()                                               \
  static_assert(pun::isRealKey(PROJECT_KEY),                                   \
                "creds.h: PROJECT_KEY is the placeholder, empty or too "       \
                "short. Without the real key this device signs nothing and "   \
                "is refused by the central unit.");                            \
  static_assert(pun::isRealOrPortal(SSID),                                     \
                "creds.h: SSID is still the placeholder (empty is allowed: "   \
                "then it comes from the setup portal).");                      \
  static_assert(pun::isRealOrPortal(PASSWORD),                                 \
                "creds.h: PASSWORD is still the placeholder.");                \
  static_assert(pun::isRealOrPortal(MQTT_BROKER),                              \
                "creds.h: MQTT_BROKER is still the placeholder.");             \
  static_assert(pun::isRealOrPortal(MQTT_USER),                                \
                "creds.h: MQTT_USER is still the placeholder.");               \
  static_assert(pun::isRealOrPortal(MQTT_PASS),                                \
                "creds.h: MQTT_PASS is still the placeholder.")

// Separate, because only some sketches offer OTA. An OTA password that still
// reads CHANGEME is an open door to the firmware of a device that sits on a
// person — and a one-character one is the same door with a sign on it.
//
// EMPTY is the way to switch OTA off. It used to say "nullptr" here, and that
// was no longer true from the moment the values became `constexpr char[]`: an
// array is never a null pointer, so that route had silently ceased to exist
// (found while closing the finding of 2026-09-15). setupOta() treats empty as
// off since 2.1.1.
#define PUN_REQUIRE_REAL_OTA()                                                 \
  static_assert(pun::isRealOtaOrOff(OTA_PASSWORD),                             \
                "creds.h: OTA_PASSWORD is the placeholder or too short. Set "  \
                "at least 8 characters, or leave it empty to switch OTA off.")
