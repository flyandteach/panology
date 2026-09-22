from __future__ import annotations

import os
from pathlib import Path

# The FAA's human-facing download page; ReleasableAircraft.zip below is the actual
# file it links to, and is what download_registry() fetches directly.
FAA_REGISTRY_PAGE_URL = (
    "https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/"
    "releasable_aircraft_download"
)
FAA_REGISTRY_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"

OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
)
OPENSKY_API_BASE = "https://opensky-network.org/api"

# OpenSky's /flights/aircraft endpoint rejects intervals longer than 2 days
# ("The given time interval must not be larger than 2 days!", REST API docs).
# Requests are also billed in credits by the number of UTC calendar days they
# touch (1-2 days = 30 credits, 3+ days costs far more), so windows are aligned
# to UTC midnight and never span more than 2 calendar days.
OPENSKY_MAX_WINDOW_SECONDS = 2 * 24 * 3600
DAY_SECONDS = 24 * 3600

# /flights/aircraft only returns flights that departed AND arrived inside
# [begin, end], so a flight straddling a window edge would be lost. Sync in
# one-UTC-day steps, each request reaching back this far into the previous day.
# A day plus 3 hours still touches only 2 calendar days (cheapest credit tier),
# and eVTOL/test flights are far shorter than 3 hours. Duplicates from the
# overlap are dropped by the flights table's primary key.
OPENSKY_SYNC_STEP_SECONDS = DAY_SECONDS
OPENSKY_WINDOW_OVERLAP_SECONDS = 3 * 3600

# OpenSky only publishes /flights data for "the previous day or earlier" (flights
# are built by a nightly batch job). Never mark anything newer than this many
# days ago as synced, or flights that land in the batch later are skipped forever.
OPENSKY_SETTLE_DAYS = 2

# If OpenSky says to wait longer than this after a 429 (credits exhausted),
# stop the run cleanly and resume next time instead of sleeping for hours.
OPENSKY_MAX_RETRY_AFTER_SECONDS = 120

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = os.environ.get("EVTOL_DB_PATH", str(PACKAGE_ROOT / "data" / "evtol_fleet.db"))

# Committed to the repo by the "eVTOL fleet registry refresh" GitHub Actions workflow,
# which runs on a schedule from CI (unrestricted egress) rather than from the deployed
# app, since registry.faa.gov's bot/IP protection can block hosting-platform requests
# outright. The app reads this file directly — no live FAA call needed at runtime.
DEFAULT_REGISTRY_SNAPSHOT_PATH = os.environ.get(
    "EVTOL_REGISTRY_SNAPSHOT_PATH", str(PACKAGE_ROOT / "data" / "tracked_aircraft.json")
)

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
