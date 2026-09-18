// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#pragma once
// PunisherIdentity — which device is this?
//
// Up to 1.x the device_UUID was written into creds.h by hand. That is a step
// one can forget while flashing, and two devices carrying the same UUID then
// talk under the same address. From 2.0 on the UUID is DERIVED:
//
//     UUID = SHA-256( NAMESPACE(16 bytes) || MAC(6 bytes) || chip type(ASCII) )
//            of that the first 16 bytes, version and variant nibble set
//
// The MAC is the chip's efuse base MAC (esp_efuse_mac_get_default) and it
// cannot be altered; so the UUID cannot either, and it can no longer diverge
// from the MAC.
//
// WHAT THIS ACHIEVES AND WHAT IT DOES NOT
// It protects against MISTAKES, not against tampering: whoever has the source
// can report whatever he wants — an invented MAC included. The efuse value
// cannot be altered, the REPORTED value can. For the step forgotten while
// flashing it is the right control, and it is nothing beyond that.
//
// WHY THE CHIP TYPE AS A STRING AND NOT AS AN IDF ENUM
// esp_chip_info() returns a number out of an enum of the IDF. Should its
// values shift with a core update, the UUID of EVERY device would silently
// change, and the installation would be facing nothing but unknown
// identities. The mapping therefore sits below in plain text and changes only
// when we change it.

#include <stddef.h>
#include <stdint.h>

namespace pun {

// Namespace of this project. NEVER change it — every change hands out new
// identities to all devices of the installation.
extern const uint8_t IDENTITY_NAMESPACE[16];

// Chip type strings. Whatever is written here goes into the hash.
extern const char* const CHIP_STR_ESP32;
extern const char* const CHIP_STR_ESP32S2;
extern const char* const CHIP_STR_ESP32S3;
extern const char* const CHIP_STR_ESP32C3;
extern const char* const CHIP_STR_ESP32C6;
extern const char* const CHIP_STR_ESP32H2;
extern const char* const CHIP_STR_UNKNOWN;

// The plain computation — no hardware, so that it can be checked against the
// central unit on a workstation. out needs 37 bytes (36 + NUL).
void deriveUuid(const uint8_t mac[6], const char* chip, char out[37]);

// MAC as "aa:bb:cc:dd:ee:ff", out needs 18 bytes.
void formatMac(const uint8_t mac[6], char out[18]);

#if defined(ESP32) || defined(ESP_PLATFORM)
// The efuse base MAC of this chip.
void readBaseMac(uint8_t mac[6]);
// Chip type of this chip, as one of the strings above.
const char* chipType();
// Convenience: UUID of this device.
void ownUuid(char out[37]);

// Set the write lock on the MAC fields (efuse). Irreversible.
// Returns true when the lock is in place afterwards — including the case where
// it was already in place before. false means: could not be set.
bool lockMacFuses();
// Is the lock in place?
bool macFusesLocked();
#endif

}  // namespace pun
