// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
// PunisherIdentity — see PunisherIdentity.h for the rationale.
#include "PunisherIdentity.h"
#include "PunisherCrypto.h"

#if defined(ESP32) || defined(ESP_PLATFORM)
#include "esp_mac.h"
#include "esp_chip_info.h"
#include "esp_efuse.h"
#include "esp_efuse_table.h"
#endif

namespace pun {

// a63646d6-5788-456a-b1e6-fe59d54bcf19
const uint8_t IDENTITY_NAMESPACE[16] = {
  0xa6, 0x36, 0x46, 0xd6, 0x57, 0x88, 0x45, 0x6a,
  0xb1, 0xe6, 0xfe, 0x59, 0xd5, 0x4b, 0xcf, 0x19
};

const char* const CHIP_STR_ESP32   = "esp32";
const char* const CHIP_STR_ESP32S2 = "esp32s2";
const char* const CHIP_STR_ESP32S3 = "esp32s3";
const char* const CHIP_STR_ESP32C3 = "esp32c3";
const char* const CHIP_STR_ESP32C6 = "esp32c6";
const char* const CHIP_STR_ESP32H2 = "esp32h2";
const char* const CHIP_STR_UNKNOWN = "unknown";

void deriveUuid(const uint8_t mac[6], const char* chip, char out[37]) {
  Sha256 s;
  s.update(IDENTITY_NAMESPACE, 16);
  s.update(mac, 6);
  s.update(chip);
  uint8_t h[32];
  s.finish(h);

  uint8_t u[16];
  for (int i = 0; i < 16; i++) u[i] = h[i];
  u[6] = (uint8_t)((u[6] & 0x0f) | 0x50);   // version 5 (name-based, SHA-1/256)
  u[8] = (uint8_t)((u[8] & 0x3f) | 0x80);   // variant RFC 4122

  static const char* d = "0123456789abcdef";
  int p = 0;
  for (int i = 0; i < 16; i++) {
    if (i == 4 || i == 6 || i == 8 || i == 10) out[p++] = '-';
    out[p++] = d[(u[i] >> 4) & 0x0f];
    out[p++] = d[u[i] & 0x0f];
  }
  out[p] = '\0';
}

void formatMac(const uint8_t mac[6], char out[18]) {
  static const char* d = "0123456789abcdef";
  int p = 0;
  for (int i = 0; i < 6; i++) {
    if (i) out[p++] = ':';
    out[p++] = d[(mac[i] >> 4) & 0x0f];
    out[p++] = d[mac[i] & 0x0f];
  }
  out[p] = '\0';
}

#if defined(ESP32) || defined(ESP_PLATFORM)

void readBaseMac(uint8_t mac[6]) {
  // Base MAC from the efuse, NOT the interface MAC currently in use:
  // station, AP, BT and Ethernet are derived from it and differ from it.
  esp_efuse_mac_get_default(mac);
}

const char* chipType() {
  esp_chip_info_t info;
  esp_chip_info(&info);
  // The values on the left are the IDF's enum (::CHIP_ESP32 ...), on the right
  // our own strings. Exactly this mapping is the point: should the IDF shift
  // its numbers around, nothing changes here.
  switch (info.model) {
    case ::CHIP_ESP32:   return pun::CHIP_STR_ESP32;
    case ::CHIP_ESP32S2: return pun::CHIP_STR_ESP32S2;
    case ::CHIP_ESP32S3: return pun::CHIP_STR_ESP32S3;
    case ::CHIP_ESP32C3: return pun::CHIP_STR_ESP32C3;
#if defined(CHIP_ESP32C6)
    case ::CHIP_ESP32C6: return pun::CHIP_STR_ESP32C6;
#endif
#if defined(CHIP_ESP32H2)
    case ::CHIP_ESP32H2: return pun::CHIP_STR_ESP32H2;
#endif
    default: return pun::CHIP_STR_UNKNOWN;
  }
}

void ownUuid(char out[37]) {
  uint8_t mac[6];
  readBaseMac(mac);
  deriveUuid(mac, chipType(), out);
}

// --------------------------------------------------------------------------
// efuse write protection of the MAC fields.
//
// What gets burned is EXCLUSIVELY the write protection of the MAC — not the
// whole block. Block 0 also holds flash and boot configuration; a blanket
// write protect across it is the way to render a device useless.
//
// Efuse bits only flip from 0 to 1. Without the lock a MAC could therefore be
// altered in one direction, or a custom MAC could be slipped in that overlays
// the base MAC. With the lock, no longer. Flashing stays possible — that is
// deliberate.
//
// Irreversible. The first burn belongs on a sacrificial chip, with
// `espefuse.py summary` before and after.

static const esp_efuse_desc_t** macWriteDisable() {
#if defined(ESP_EFUSE_WR_DIS_MAC)
  return ESP_EFUSE_WR_DIS_MAC;
#elif defined(ESP_EFUSE_WR_DIS_MAC_FACTORY)
  return ESP_EFUSE_WR_DIS_MAC_FACTORY;            // older IDF releases
#else
  return nullptr;
#endif
}

static const esp_efuse_desc_t** customMacWriteDisable() {
#if defined(ESP_EFUSE_WR_DIS_CUSTOM_MAC)
  return ESP_EFUSE_WR_DIS_CUSTOM_MAC;
#elif defined(ESP_EFUSE_WR_DIS_MAC_CUSTOM)
  return ESP_EFUSE_WR_DIS_MAC_CUSTOM;
#else
  return nullptr;                                 // target without a custom MAC field
#endif
}

static bool fuseSet(const esp_efuse_desc_t** field) {
  if (field == nullptr) return true;              // not present here: counts as set
  uint8_t bit = 0;
  if (esp_efuse_read_field_blob(field, &bit, 1) != ESP_OK) return false;
  return bit != 0;
}

bool macFusesLocked() {
  return fuseSet(macWriteDisable()) && fuseSet(customMacWriteDisable());
}

bool lockMacFuses() {
  if (macFusesLocked()) return true;              // already set: nothing to do
  bool ok = true;
  if (macWriteDisable() && !fuseSet(macWriteDisable())) {
    ok = esp_efuse_write_field_bit(macWriteDisable()) == ESP_OK && ok;
  }
  if (customMacWriteDisable() && !fuseSet(customMacWriteDisable())) {
    ok = esp_efuse_write_field_bit(customMacWriteDisable()) == ESP_OK && ok;
  }
  return ok && macFusesLocked();
}

#endif  // ESP32

}  // namespace pun
