// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// Check run for PunisherCrypto and PunisherIdentity — runs on the
// workstation, without an ESP32.
//
//   g++ -std=c++17 -I../src -o /tmp/t test_crypto_identity.cpp \
//       ../src/PunisherCrypto.cpp ../src/PunisherIdentity.cpp && /tmp/t
//
// Three things are checked:
//   1. SHA-256 against the official vectors from FIPS 180-4
//   2. HMAC-SHA256 against the vectors from RFC 4231
//   3. UUID derivation and signature against fixed expected values, which
//      test_against_central.py recomputes from central/libs/punsign.py
//
// Points 1 and 2 answer "does the firmware compute correctly", point 3 "does
// it compute the same as the central unit". Both are needed: two sides can be
// wrong in perfect harmony.

#include <cstdio>
#include <cstring>
#include <string>

#include "PunisherCrypto.h"
#include "PunisherIdentity.h"

static int checks = 0;
static int fails = 0;

static void expect(const char* what, const std::string& got, const std::string& want) {
  checks++;
  if (got == want) {
    printf("  OK   %s\n", what);
  } else {
    fails++;
    printf("  FEHL %s\n       erwartet %s\n       bekommen %s\n",
           what, want.c_str(), got.c_str());
  }
}

static std::string hexOf(const uint8_t* b, size_t n) {
  char out[200];
  pun::toHex(b, n, out);
  return std::string(out);
}

static std::string sha(const std::string& s) {
  uint8_t h[32];
  pun::sha256((const uint8_t*)s.data(), s.size(), h);
  return hexOf(h, 32);
}

static std::string hmacHex(const std::string& key, const std::string& msg) {
  uint8_t h[32];
  pun::hmacSha256((const uint8_t*)key.data(), key.size(),
                  (const uint8_t*)msg.data(), msg.size(), h);
  return hexOf(h, 32);
}

int main() {
  printf("SHA-256 (FIPS 180-4)\n");
  expect("leere Eingabe", sha(""),
         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  expect("\"abc\"", sha("abc"),
         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  expect("448 Bit", sha("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
         "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
  // 896 bits: spans two blocks and checks the padding at the boundary
  expect("896 Bit",
         sha("abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmn"
             "hijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu"),
         "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1");
  {
    // Exactly 55, 56 and 64 bytes — the three spots at which the padding
    // is decided and at which home-grown implementations fail in
    // droves.
    std::string a(55, 'a'), b(56, 'a'), c(64, 'a');
    expect("55 x 'a'", sha(a),
           "9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318");
    expect("56 x 'a'", sha(b),
           "b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a");
    expect("64 x 'a'", sha(c),
           "ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb");
  }

  printf("\nHMAC-SHA256 (RFC 4231)\n");
  {
    std::string key(20, (char)0x0b);
    expect("Fall 1", hmacHex(key, "Hi There"),
           "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
  }
  expect("Fall 2", hmacHex("Jefe", "what do ya want for nothing?"),
         "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
  {
    // Case 6: key longer than one block -> has to be hashed
    std::string key(131, (char)0xaa);
    expect("Fall 6 (langer Schluessel)",
           hmacHex(key, "Test Using Larger Than Block-Size Key - Hash Key First"),
           "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
  }

  printf("\nGeraeteidentitaet\n");
  {
    // Two invented MACs from the locally administered range (02:...), of the
    // same kind that the bench's fakes carry.
    const uint8_t m1[6] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};
    const uint8_t m2[6] = {0x02, 0x00, 0x00, 0x00, 0x00, 0x02};
    char u1[37], u2[37], u3[37];
    pun::deriveUuid(m1, pun::CHIP_STR_ESP32, u1);
    pun::deriveUuid(m2, pun::CHIP_STR_ESP32, u2);
    pun::deriveUuid(m1, pun::CHIP_STR_ESP32S3, u3);

    checks++;
    if (strcmp(u1, u2) != 0) printf("  OK   verschiedene MAC -> verschiedene UUID\n");
    else { fails++; printf("  FEHL zwei MACs ergaben dieselbe UUID\n"); }

    checks++;
    if (strcmp(u1, u3) != 0) printf("  OK   anderer Chiptyp -> andere UUID\n");
    else { fails++; printf("  FEHL Chiptyp geht nicht in die UUID ein\n"); }

    // Shape: 8-4-4-4-12, version 5, variant RFC 4122
    checks++;
    bool form = strlen(u1) == 36 && u1[8] == '-' && u1[13] == '-' &&
                u1[18] == '-' && u1[23] == '-' && u1[14] == '5' &&
                (u1[19] == '8' || u1[19] == '9' || u1[19] == 'a' || u1[19] == 'b');
    if (form) printf("  OK   Form, Version 5 und Variante stimmen\n");
    else { fails++; printf("  FEHL UUID-Form falsch: %s\n", u1); }

    // Fixed expected values — test_against_central.py recomputes the same
    // ones from central/libs/punsign.py.
    expect("UUID 02:00:00:00:00:01 / esp32", std::string(u1),
           "c0291207-a276-5771-8f23-586b527a8d57");
    expect("UUID 02:00:00:00:00:01 / esp32s3", std::string(u3),
           "508e6d00-0b7e-5df8-8bba-c0eb9852170a");

    char mac[18];
    pun::formatMac(m1, mac);
    expect("MAC-Schreibweise", std::string(mac), "02:00:00:00:00:01");
  }

  printf("\nSignatur\n");
  {
    const std::string key = "CHANGEME-PROJECT-KEY";
    const std::string topic = "punisher/devices/abc/cmd";
    const std::string body = "{\"action\":\"punish\",\"id\":7,\"ts_ms\":1000,\"ttl_ms\":5000}";
    expect("HMAC ueber Topic und Koerper", hmacHex(key, topic + "\n" + body),
           "95d993a3ce28d8cd117695f907ca356a8cb1a348962cb9e713898fe63dd45788");

    // A single changed character in the topic must yield a completely
    // different signature — otherwise a command could be passed on to a
    // different device.
    checks++;
    if (hmacHex(key, topic + "\n" + body) !=
        hmacHex(key, "punisher/devices/abd/cmd\n" + body))
      printf("  OK   anderes Topic -> andere Signatur\n");
    else { fails++; printf("  FEHL Topic geht nicht in die Signatur ein\n"); }

    checks++;
    const char* a = "aaaaaaaa";
    if (pun::equalsConstTime(a, "aaaaaaaa", 8) &&
        !pun::equalsConstTime(a, "aaaaaaab", 8))
      printf("  OK   Vergleich in konstanter Zeit\n");
    else { fails++; printf("  FEHL equalsConstTime\n"); }
  }

  printf("\n%d Pruefungen, %d Fehler\n", checks, fails);
  return fails == 0 ? 0 : 1;
}
