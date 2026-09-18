// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// PunisherCrypto - see PunisherCrypto.h for the reasoning.
#include "PunisherCrypto.h"

namespace pun {
namespace {

inline uint32_t ror(uint32_t x, uint32_t n) { return (x >> n) | (x << (32 - n)); }

const uint32_t K[64] = {
  0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
  0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
  0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
  0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
  0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
  0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
  0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
  0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
  0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
  0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
  0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

}  // namespace

void Sha256::reset() {
  _h[0] = 0x6a09e667u; _h[1] = 0xbb67ae85u; _h[2] = 0x3c6ef372u; _h[3] = 0xa54ff53au;
  _h[4] = 0x510e527fu; _h[5] = 0x9b05688cu; _h[6] = 0x1f83d9abu; _h[7] = 0x5be0cd19u;
  _bits = 0;
  _used = 0;
}

void Sha256::block(const uint8_t* p) {
  uint32_t w[64];
  for (int i = 0; i < 16; i++) {
    w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
           ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
  }
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = ror(w[i - 15], 7) ^ ror(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = ror(w[i - 2], 17) ^ ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = _h[0], b = _h[1], c = _h[2], d = _h[3];
  uint32_t e = _h[4], f = _h[5], g = _h[6], h = _h[7];
  for (int i = 0; i < 64; i++) {
    uint32_t S1 = ror(e, 6) ^ ror(e, 11) ^ ror(e, 25);
    uint32_t ch = (e & f) ^ ((~e) & g);
    uint32_t t1 = h + S1 + ch + K[i] + w[i];
    uint32_t S0 = ror(a, 2) ^ ror(a, 13) ^ ror(a, 22);
    uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = S0 + mj;
    h = g; g = f; f = e; e = d + t1;
    d = c; c = b; b = a; a = t1 + t2;
  }
  _h[0] += a; _h[1] += b; _h[2] += c; _h[3] += d;
  _h[4] += e; _h[5] += f; _h[6] += g; _h[7] += h;
}

void Sha256::update(const uint8_t* data, size_t len) {
  _bits += (uint64_t)len * 8;
  while (len > 0) {
    size_t take = 64 - _used;
    if (take > len) take = len;
    memcpy(_buf + _used, data, take);
    _used += take; data += take; len -= take;
    if (_used == 64) { block(_buf); _used = 0; }
  }
}

void Sha256::finish(uint8_t out[32]) {
  uint64_t bits = _bits;
  uint8_t pad = 0x80;
  update(&pad, 1);
  _bits = bits;                       // the padding does not count
  uint8_t zero = 0x00;
  while (_used != 56) { update(&zero, 1); _bits = bits; }
  uint8_t len[8];
  for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - i * 8));
  update(len, 8);
  for (int i = 0; i < 8; i++) {
    out[i * 4]     = (uint8_t)(_h[i] >> 24);
    out[i * 4 + 1] = (uint8_t)(_h[i] >> 16);
    out[i * 4 + 2] = (uint8_t)(_h[i] >> 8);
    out[i * 4 + 3] = (uint8_t)(_h[i]);
  }
}

void sha256(const uint8_t* data, size_t len, uint8_t out[32]) {
  Sha256 s;
  s.update(data, len);
  s.finish(out);
}

void hmacSha256(const uint8_t* key, size_t keyLen,
                const uint8_t* msg, size_t msgLen, uint8_t out[32]) {
  uint8_t k[64];
  memset(k, 0, sizeof(k));
  if (keyLen > 64) {
    sha256(key, keyLen, k);          // a key longer than one block is hashed (RFC 2104)
  } else {
    memcpy(k, key, keyLen);
  }
  uint8_t inner[64], outer[64];
  for (int i = 0; i < 64; i++) { inner[i] = k[i] ^ 0x36; outer[i] = k[i] ^ 0x5c; }

  uint8_t h1[32];
  Sha256 s1;
  s1.update(inner, 64);
  s1.update(msg, msgLen);
  s1.finish(h1);

  Sha256 s2;
  s2.update(outer, 64);
  s2.update(h1, 32);
  s2.finish(out);
}

void hmacSha256(const char* key, const char* msg, uint8_t out[32]) {
  hmacSha256((const uint8_t*)key, strlen(key), (const uint8_t*)msg, strlen(msg), out);
}

void toHex(const uint8_t* in, size_t len, char* out) {
  static const char* d = "0123456789abcdef";
  for (size_t i = 0; i < len; i++) {
    out[i * 2]     = d[(in[i] >> 4) & 0x0f];
    out[i * 2 + 1] = d[in[i] & 0x0f];
  }
  out[len * 2] = '\0';
}

bool equalsConstTime(const char* a, const char* b, size_t len) {
  uint8_t diff = 0;
  for (size_t i = 0; i < len; i++) diff |= (uint8_t)(a[i] ^ b[i]);
  return diff == 0;
}

}  // namespace pun
