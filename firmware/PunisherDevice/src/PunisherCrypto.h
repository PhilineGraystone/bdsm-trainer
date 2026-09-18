// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#pragma once
// PunisherCrypto — SHA-256 and HMAC-SHA256, self-contained.
//
// WHY NOT mbedTLS, WHICH SITS IN THE ESP32 ANYWAY
//
// This computation must be bit-identical on BOTH sides: in the firmware and in
// the central unit (central/libs/punsign.py). Bit-identity can only be proven
// if both sides can be run side by side — and that works with an
// implementation that can also be compiled on a workstation without dragging
// half of the IDF along. The check run test/test_crypto_identity.cpp does
// exactly that.
//
// On top of that: the names of the mbedTLS interface have shifted repeatedly
// between IDF releases. An installation whose devices no longer compute the
// same signature as the central unit after a core update goes down as a whole.
// SHA-256 is two hundred lines that can be checked against the official test
// vectors; this dependency is not worth it.
//
// Checked against FIPS 180-4 (SHA-256) and RFC 4231 (HMAC-SHA256) as well as
// against Python's hashlib/hmac. See test/test_crypto_identity.cpp.

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace pun {

static const size_t SHA256_LEN = 32;

class Sha256 {
 public:
  Sha256() { reset(); }
  void reset();
  void update(const uint8_t* data, size_t len);
  void update(const char* s) { update((const uint8_t*)s, strlen(s)); }
  // Writes 32 bytes to out. Afterwards the state is spent.
  void finish(uint8_t out[32]);

 private:
  void block(const uint8_t* p);
  uint32_t _h[8];
  uint64_t _bits;
  uint8_t _buf[64];
  size_t _used;
};

// One-shot computation.
void sha256(const uint8_t* data, size_t len, uint8_t out[32]);

// HMAC-SHA256 per RFC 2104. Key of arbitrary length.
void hmacSha256(const uint8_t* key, size_t keyLen,
                const uint8_t* msg, size_t msgLen,
                uint8_t out[32]);

// Convenience overload for strings.
void hmacSha256(const char* key, const char* msg, uint8_t out[32]);

// 32 bytes -> 64 lowercase hex characters, null-terminated (65-byte target).
void toHex(const uint8_t* in, size_t len, char* out);

// Constant-time comparison. true = equal.
// A comparison using strcmp betrays through its runtime how many characters
// match; that lets a signature be guessed character by character.
bool equalsConstTime(const char* a, const char* b, size_t len);

}  // namespace pun
