// SPDX-License-Identifier: LicenseRef-Devious-City-1.0-or-later
#pragma once
// Version of the PunisherDevice framework.
//
// WHY THE NUMBERS AND THE NAME ARE SEPARATE
//
// Up to 1.x creds.h held a single string: "CoyoteBridge-2.7". The central unit
// had to cut the version out of it. That works until somebody touches the
// display name - and then the central unit compares strings and notices
// nothing. From 2.0 on there are three numbers, and the name is only a name.
//
// TWO VERSIONS, TWO FLOORS
// A device reports both: the framework's (this file, the same on every device)
// and its sketch's (version.h in the sketch). The central unit keeps a minimum
// version for both, per model. An old sketch on a fresh framework would slip
// through otherwise - on a bridge that would be firmware writing the channel
// register differently while the central unit has long assumed the new
// contract.

#define PUNISHERDEVICE_VERSION_MAJOR 2
#define PUNISHERDEVICE_VERSION_MINOR 3
#define PUNISHERDEVICE_VERSION_PATCH 2

// For display and logs only. Comparing always goes over the three numbers.
#define PUNISHERDEVICE_VERSION_STR "2.3.2"

// Must match library.properties. The test run test_versions.py holds the two
// against each other so they cannot drift apart.
