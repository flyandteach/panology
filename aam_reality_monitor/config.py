"""Configuration for the AAM Reality Monitor."""
from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_ROOT / "data"
REPORTS_DIR = PACKAGE_ROOT / "generated_reports"

OEMS_FILE = DATA_DIR / "oems.json"
EVIDENCE_FILE = DATA_DIR / "evidence.json"
CLAIMS_FILE = DATA_DIR / "claims.json"
SCORING_WEIGHTS_FILE = DATA_DIR / "scoring_weights.json"

VALID_EVIDENCE_CATEGORIES = {
    "certification",
    "operational",
    "infrastructure",
    "production",
    "financial",
    "claim_reality",
    "general",
}

VALID_SOURCE_TYPES = {
    "regulator",
    "company_filing",
    "company_press_release",
    "flight_tracking",
    "aircraft_registry",
    "airport_document",
    "local_government",
    "trade_press",
    "general_news",
    "analyst_report",
    "manual_note",
}

VALID_CLAIM_STATUS = {
    "verified",
    "partially_supported",
    "unverified",
    "contradicted",
    "outdated",
    "promotional_only",
}
