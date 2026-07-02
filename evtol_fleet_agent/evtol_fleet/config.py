from __future__ import annotations

import os
from pathlib import Path

FAA_REGISTRY_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"

OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
)
OPENSKY_API_BASE = "https://opensky-network.org/api"

# OpenSky's /flights/aircraft endpoint rejects windows longer than 30 days;
# stay a day under that to leave margin for clock skew.
OPENSKY_MAX_WINDOW_SECONDS = 29 * 24 * 3600

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = os.environ.get("EVTOL_DB_PATH", str(PACKAGE_ROOT / "data" / "evtol_fleet.db"))

OPENSKY_CLIENT_ID = os.environ.get("OPENSKY_CLIENT_ID")
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET")

# Substrings matched case-insensitively against the FAA registry "NAME" (registrant)
# field. eVTOL makers sometimes register aircraft under a slightly different legal
# name than their public brand, so each manufacturer maps to a list of patterns.
MANUFACTURER_NAME_PATTERNS: dict[str, list[str]] = {
    "Joby": ["JOBY AERO", "JOBY AVIATION"],
    "Archer": ["ARCHER AVIATION"],
    "BETA": ["BETA TECHNOLOGIES", "BETA AIR"],
}

# Escape hatch for aircraft registered under a trust/leasing entity that owner-name
# matching won't catch. Map raw FAA N-numbers (with the "N" prefix) to a manufacturer
# key from MANUFACTURER_NAME_PATTERNS above.
MANUAL_N_NUMBER_OVERRIDES: dict[str, str] = {}
