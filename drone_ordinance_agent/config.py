"""
Configuration for the Drone Hub / Vertiport Ordinance Agent.
Aligned with WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).
"""

import os

# --- LLM ---
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
TEMPERATURE = 0.4  # Lower temp for regulatory precision

# --- File Paths ---
EXPORTS_DIR = "exports"
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# --- Tier Classification — primary metric: dedicated hub area (sq ft)
# Secondary triggers for Tier 3: multiple operators, high-volume ops, major infrastructure
# Source: WSDOT Drone Hub Land Use Guidance v5.3, Table 1
TIER_SQFT = {
    "tier_1_max": 9999,     # < 10,000 sq ft
    "tier_2_max": 20000,    # 10,000 – 20,000 sq ft
    "tier_3_min": 20001,    # >= 20,001 sq ft (or triggers below)
}

# Tier 3 secondary triggers (any one is sufficient even if sqft < 20,000)
TIER_3_SECONDARY_TRIGGERS = {
    "multiple_operators": True,       # more than one UAS operator sharing the hub
    "high_volume_per_hour": 100,      # > 100 flights in any rolling 60-min period
    "daily_flights_threshold": 300,   # > 300 takeoffs+landings per calendar month = persistent high activity
    "overnight_ground_activity": True,
    "permanent_charging_docking": True,
}

# --- Advisory Setback Thresholds (feet from OPERATIONAL BOUNDARY, not parcel line)
# Source: WSDOT v5.3 Table 2 (advisory defaults for local adaptation)
# These are starting points — local jurisdictions calibrate to context
ADVISORY_SETBACKS = {
    "urban": {
        "residential_default_ft": 150,
        "residential_minimum_ft": 150,   # may be reduced below 150 by discretionary approval
        "school_hospital_ft": 300,       # heightened review threshold
    },
    "suburban": {
        "residential_default_ft": 300,
        "residential_minimum_ft": 150,   # reducible to 150 ft by discretionary approval
        "school_hospital_ft": 300,
    },
    "rural": {
        "residential_default_ft": 300,
        "residential_minimum_ft": 300,   # not reducible by default; land generally available
        "school_hospital_ft": 300,
    },
    "dense_urban": {
        "residential_default_ft": 150,
        "residential_minimum_ft": 150,
        "school_hospital_ft": 300,
    },
}

# Tier 3 sensitive-receptor review threshold
TIER_3_REVIEW_THRESHOLD_FT = 300  # planning-level starting point per WSDOT v5.3

# Notice radii for approval hearings
NOTICE_RADIUS_TIER_1_2_FT = 300
NOTICE_RADIUS_TIER_3_FT = 500

# High-volume operations threshold
HIGH_VOLUME_FLIGHTS_PER_HOUR = 100

# --- Zone Compatibility Matrix — Source: WSDOT v5.3 Table 3
# P = Permitted (administrative, non-discretionary)
# C = Conditional / Special Use (discretionary, public hearing)
# X = Prohibited
ZONE_COMPATIBILITY = {
    "Residential (all)":                        {"tier_1": "X", "tier_2": "X", "tier_3": "X"},
    "Neighborhood Commercial / Mixed Use":       {"tier_1": "C", "tier_2": "C", "tier_3": "C"},
    "Regional Commercial / Retail":             {"tier_1": "P", "tier_2": "P", "tier_3": "C"},
    "Industrial / Logistics":                   {"tier_1": "P", "tier_2": "P", "tier_3": "C"},
    "Airport-Related / Aviation Overlay":       {"tier_1": "P", "tier_2": "P", "tier_3": "C"},
    "Institutional":                            {"tier_1": "C", "tier_2": "C", "tier_3": "C"},
}

# --- Airport Proximity (miles) — for coordination notes
AIRPORT_PROXIMITY_MILES = {
    "class_b": 30,
    "class_c": 20,
    "class_d": 10,
    "class_e": 5,
    "class_g": 3,
    "heliport": 2,
    "vertiport": 1,
    "none": 0,
}

# --- Environmental Review Thresholds ---
ENV_TRIGGERS = {
    "noise_flights_per_hour": 100,       # High-volume ground-noise concern
    "acreage_threshold": 2.0,            # Phase I ESA / SEPA/NEPA triggered above this
    "wetland_buffer_feet": 300,
    "floodplain_buffer_feet": 500,
}

# --- Display ---
SEPARATOR = "=" * 70
THIN_SEPARATOR = "-" * 70
